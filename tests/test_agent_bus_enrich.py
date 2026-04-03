"""Tests for the enriched Agent Bus and Session Action primitives.

Covers:
- MessageEnvelope model
- Enriched message schema (kind, correlation_id, priority, requires_ack, etc.)
- receive_messages filtering (kind, correlation_id, after_id)
- mark_acked
- SessionAction model
- session_actions CRUD and lifecycle
- action_bus convenience functions
"""

from __future__ import annotations

import json

import pytest

from shoal.core.db import ShoalDB
from shoal.models.action import ActionStatus, SessionAction
from shoal.models.message import DEFAULT_KIND, DEFAULT_PRIORITY, MessageEnvelope, MessageKind

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db(tmp_path):
    db_path = tmp_path / "shoal.db"
    ShoalDB._initialized = False
    db = ShoalDB(db_path)
    await db.connect()
    yield db
    await db.close()
    ShoalDB._initialized = False


# ---------------------------------------------------------------------------
# MessageEnvelope model
# ---------------------------------------------------------------------------


def test_message_envelope_defaults():
    env = MessageEnvelope(
        from_session="a",
        to_session="b",
        topic="handoff",
        payload="{}",
    )
    assert env.kind == DEFAULT_KIND
    assert env.priority == DEFAULT_PRIORITY
    assert env.requires_ack is False
    assert env.correlation_id is None
    assert env.reply_to_message_id is None


def test_message_envelope_all_fields():
    env = MessageEnvelope(
        from_session="planner",
        to_session="worker",
        topic="code-review",
        kind="request",
        payload='{"path": "src/api.ts"}',
        correlation_id="wf_123",
        reply_to_message_id=None,
        priority=2,
        requires_ack=True,
        metadata_json='{"workflow":"auth"}',
    )
    assert env.kind == "request"
    assert env.priority == 2
    assert env.requires_ack is True
    assert env.correlation_id == "wf_123"


@pytest.mark.parametrize(
    "kind",
    ["event", "request", "response", "handoff", "approval_request", "approval_decision", "error"],
)
def test_message_kind_all_values(kind: MessageKind):
    env = MessageEnvelope(from_session="a", to_session="b", topic="t", payload="{}", kind=kind)
    assert env.kind == kind


# ---------------------------------------------------------------------------
# Enriched message send / receive (DB layer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_message_minimal_backward_compat(db):
    """Minimal call (no new fields) still inserts and round-trips."""
    msg_id = await db.send_message("a", "b", "topic", "payload")
    assert msg_id > 0

    msgs = await db.receive_messages("b")
    assert len(msgs) == 1
    m = msgs[0]
    assert m["kind"] == "event"
    assert m["priority"] == 3
    assert m["requires_ack"] is False
    assert m["correlation_id"] is None
    assert m["acked_at"] is None


@pytest.mark.asyncio
async def test_send_message_full_envelope(db):
    msg_id = await db.send_message(
        "planner",
        "worker",
        "code-review",
        '{"path":"src/api.ts"}',
        kind="request",
        correlation_id="wf_abc",
        priority=2,
        requires_ack=True,
        metadata_json='{"workflow":"auth"}',
    )
    assert msg_id > 0

    msgs = await db.receive_messages("worker")
    assert len(msgs) == 1
    m = msgs[0]
    assert m["kind"] == "request"
    assert m["correlation_id"] == "wf_abc"
    assert m["priority"] == 2
    assert m["requires_ack"] is True
    assert m["metadata_json"] == '{"workflow":"auth"}'


@pytest.mark.asyncio
async def test_receive_filter_by_kind(db):
    await db.send_message("a", "b", "t", "{}", kind="event")
    await db.send_message("a", "b", "t", "{}", kind="request")
    await db.send_message("a", "b", "t", "{}", kind="response")

    events = await db.receive_messages("b", kind="event")
    assert len(events) == 1
    assert events[0]["kind"] == "event"

    requests = await db.receive_messages("b", kind="request")
    assert len(requests) == 1
    assert requests[0]["kind"] == "request"


@pytest.mark.asyncio
async def test_receive_filter_by_correlation_id(db):
    await db.send_message("a", "b", "t", "{}", correlation_id="wf_1")
    await db.send_message("a", "b", "t", "{}", correlation_id="wf_2")
    await db.send_message("a", "b", "t", "{}")  # no correlation

    wf1 = await db.receive_messages("b", correlation_id="wf_1")
    assert len(wf1) == 1
    assert wf1[0]["correlation_id"] == "wf_1"

    wf2 = await db.receive_messages("b", correlation_id="wf_2")
    assert len(wf2) == 1


@pytest.mark.asyncio
async def test_receive_filter_by_after_id(db):
    id1 = await db.send_message("a", "b", "t", "first")
    id2 = await db.send_message("a", "b", "t", "second")
    _id3 = await db.send_message("a", "b", "t", "third")

    # Only messages after id1
    msgs = await db.receive_messages("b", after_id=id1)
    assert len(msgs) == 2
    assert msgs[0]["payload"] == "second"
    assert msgs[1]["payload"] == "third"

    # Only messages after id2
    msgs = await db.receive_messages("b", after_id=id2)
    assert len(msgs) == 1
    assert msgs[0]["payload"] == "third"


@pytest.mark.asyncio
async def test_mark_message_acked(db):
    msg_id = await db.send_message("a", "b", "t", "{}", requires_ack=True)

    msgs = await db.receive_messages("b")
    assert msgs[0]["acked_at"] is None

    await db.mark_message_acked(msg_id)

    msgs = await db.receive_messages("b", unconsumed_only=False)
    assert msgs[0]["acked_at"] is not None


@pytest.mark.asyncio
async def test_reply_to_message_id(db):
    """reply_to_message_id creates a traceable request/response pair."""
    req_id = await db.send_message("planner", "worker", "review", "{}", kind="request")
    resp_id = await db.send_message(
        "worker",
        "planner",
        "review",
        '{"ok":true}',
        kind="response",
        reply_to_message_id=req_id,
    )

    msgs = await db.receive_messages("planner")
    assert len(msgs) == 1
    assert msgs[0]["id"] == resp_id
    assert msgs[0]["reply_to_message_id"] == req_id


# ---------------------------------------------------------------------------
# SessionAction model
# ---------------------------------------------------------------------------


def test_session_action_defaults():
    action = SessionAction(
        requester_session="worker-a",
        action_type="merge_branch",
        payload_json='{"branch":"feat"}',
    )
    assert action.status == ActionStatus.pending
    assert action.target_session is None
    assert action.correlation_id is None
    assert action.resolved_by is None


def test_action_status_values():
    for status in ActionStatus:
        a = SessionAction(
            requester_session="s",
            action_type="merge_branch",
            payload_json="{}",
            status=status,
        )
        assert a.status == status


# ---------------------------------------------------------------------------
# Session actions DB layer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_get_session_action(db):
    action_id = await db.create_session_action(
        "worker-a",
        "merge_branch",
        '{"branch":"feature/auth","target":"main"}',
        target_session="supervisor",
        correlation_id="wf_999",
    )
    assert action_id > 0

    action = await db.get_session_action(action_id)
    assert action is not None
    assert action.id == action_id
    assert action.requester_session == "worker-a"
    assert action.action_type == "merge_branch"
    assert action.status == ActionStatus.pending
    assert action.target_session == "supervisor"
    assert action.correlation_id == "wf_999"
    assert action.requested_at is not None
    assert action.resolved_at is None


@pytest.mark.asyncio
async def test_get_session_action_not_found(db):
    result = await db.get_session_action(99999)
    assert result is None


@pytest.mark.asyncio
async def test_list_pending_session_actions_all(db):
    await db.create_session_action("w1", "merge_branch", "{}", target_session="sup")
    await db.create_session_action("w2", "run_release", "{}", target_session="sup")

    pending = await db.list_pending_session_actions()
    assert len(pending) == 2
    assert all(a.status == ActionStatus.pending for a in pending)


@pytest.mark.asyncio
async def test_list_pending_session_actions_filter_target(db):
    await db.create_session_action("w1", "merge_branch", "{}", target_session="sup-a")
    await db.create_session_action("w2", "merge_branch", "{}", target_session="sup-b")

    for_a = await db.list_pending_session_actions(target_session="sup-a")
    assert len(for_a) == 1
    assert for_a[0].requester_session == "w1"

    for_b = await db.list_pending_session_actions(target_session="sup-b")
    assert len(for_b) == 1


@pytest.mark.asyncio
async def test_list_pending_session_actions_filter_correlation(db):
    await db.create_session_action("w1", "merge_branch", "{}", correlation_id="wf_A")
    await db.create_session_action("w2", "merge_branch", "{}", correlation_id="wf_B")

    wf_a = await db.list_pending_session_actions(correlation_id="wf_A")
    assert len(wf_a) == 1
    assert wf_a[0].correlation_id == "wf_A"


@pytest.mark.asyncio
async def test_resolve_session_action_approved(db):
    action_id = await db.create_session_action("worker", "merge_branch", "{}", target_session="sup")

    resolved = await db.resolve_session_action(
        action_id, ActionStatus.approved, "supervisor", "LGTM"
    )
    assert resolved is not None
    assert resolved.status == ActionStatus.approved
    assert resolved.resolved_by == "supervisor"
    assert resolved.decision_reason == "LGTM"
    assert resolved.resolved_at is not None


@pytest.mark.asyncio
async def test_resolve_session_action_denied(db):
    action_id = await db.create_session_action("worker", "merge_branch", "{}", target_session="sup")

    resolved = await db.resolve_session_action(
        action_id, ActionStatus.denied, "supervisor", "Not ready"
    )
    assert resolved is not None
    assert resolved.status == ActionStatus.denied
    assert resolved.decision_reason == "Not ready"


@pytest.mark.asyncio
async def test_list_pending_excludes_resolved(db):
    action_id = await db.create_session_action("w1", "merge_branch", "{}")

    pending = await db.list_pending_session_actions()
    assert len(pending) == 1

    await db.resolve_session_action(action_id, ActionStatus.approved, "sup")

    pending_after = await db.list_pending_session_actions()
    assert len(pending_after) == 0


# ---------------------------------------------------------------------------
# action_bus module
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_bus_request_approve(tmp_path):
    """Round-trip: request → list_pending → approve."""
    from shoal.core.action_bus import approve_action, list_pending_actions, request_action
    from shoal.core.db import ShoalDB

    ShoalDB._initialized = False
    db = ShoalDB(tmp_path / "shoal.db")
    await db.connect()

    # Patch get_db to use our isolated instance
    import shoal.core.db as db_module

    orig = db_module.ShoalDB._instance
    db_module.ShoalDB._instance = db

    try:
        action_id = await request_action(
            "worker",
            "merge_branch",
            json.dumps({"branch": "feat/x"}),
            target_session="supervisor",
            correlation_id="wf_42",
        )
        assert action_id > 0

        pending = await list_pending_actions(target_session="supervisor")
        assert len(pending) == 1
        assert pending[0].action_type == "merge_branch"

        approved = await approve_action(action_id, "supervisor", "looks good")
        assert approved is not None
        assert approved.status == ActionStatus.approved
        assert approved.resolved_by == "supervisor"

        # No longer pending
        pending_after = await list_pending_actions(target_session="supervisor")
        assert len(pending_after) == 0
    finally:
        db_module.ShoalDB._instance = orig
        await db.close()
        ShoalDB._initialized = False


@pytest.mark.asyncio
async def test_action_bus_deny(tmp_path):
    import shoal.core.db as db_module
    from shoal.core.action_bus import deny_action, request_action
    from shoal.core.db import ShoalDB

    ShoalDB._initialized = False
    db = ShoalDB(tmp_path / "shoal2.db")
    await db.connect()
    orig = db_module.ShoalDB._instance
    db_module.ShoalDB._instance = db

    try:
        action_id = await request_action("worker", "run_release", "{}")
        denied = await deny_action(action_id, "supervisor", "premature")
        assert denied is not None
        assert denied.status == ActionStatus.denied
    finally:
        db_module.ShoalDB._instance = orig
        await db.close()
        ShoalDB._initialized = False


# ---------------------------------------------------------------------------
# Schema migration: existing DB gains new columns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_messages_migration_adds_new_columns(tmp_path):
    """A DB with the old minimal schema is migrated transparently."""
    import aiosqlite

    db_path = tmp_path / "old.db"

    # Create old-style DB with only original columns.
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("""
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_session TEXT NOT NULL,
                to_session TEXT NOT NULL,
                topic TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                consumed_at TEXT
            )
        """)
        await conn.execute(
            "INSERT INTO messages (from_session, to_session, topic, payload, created_at)"
            " VALUES ('a', 'b', 't', 'legacy', '2024-01-01T00:00:00+00:00')"
        )
        await conn.commit()

    # Open via ShoalDB — migration should run without error.
    ShoalDB._initialized = False
    db = ShoalDB(db_path)
    await db.connect()

    msgs = await db.receive_messages("b")
    assert len(msgs) == 1
    m = msgs[0]
    # New columns should be present with their defaults.
    assert m["kind"] == "event"
    assert m["priority"] == 3
    assert m["requires_ack"] is False
    assert m["correlation_id"] is None
    assert m["acked_at"] is None

    await db.close()
    ShoalDB._initialized = False
