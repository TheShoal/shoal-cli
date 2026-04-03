"""Shoal-P1 quality gates: watch surfaces and workflow message retrieval."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from shoal.core.action_bus import (
    approve_action,
    request_action,
    watch_pending_actions,
)
from shoal.core.db import ShoalDB, get_db
from shoal.core.message_bus import (
    get_workflow_messages,
    send_message,
    watch_messages,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def fresh_db(tmp_path):
    """Isolate every test in its own temporary database via the singleton."""
    await ShoalDB.reset_instance()
    with (
        patch("shoal.core.config.data_dir", return_value=tmp_path),
        patch("shoal.core.config.ensure_dirs"),
    ):
        yield
    await ShoalDB.reset_instance()


# ---------------------------------------------------------------------------
# watch_messages: returns immediately when messages are present
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watch_messages_returns_existing():
    """watch_messages returns quickly when messages already exist."""
    await send_message(
        "session-a",
        "inbox",
        "hello",
        "world",
        kind="event",
        correlation_id="wf-1",
    )
    results = await watch_messages(
        "inbox", kind="event", correlation_id="wf-1", timeout_seconds=5.0
    )
    assert len(results) == 1
    assert results[0]["payload"] == "world"
    assert results[0]["kind"] == "event"
    assert results[0]["correlation_id"] == "wf-1"


@pytest.mark.asyncio
async def test_watch_messages_timeout_empty():
    """watch_messages returns [] when no messages arrive before the deadline."""
    results = await watch_messages("no-messages", timeout_seconds=0.1, poll_interval=0.05)
    assert results == []


@pytest.mark.asyncio
async def test_watch_messages_sees_new_message():
    """watch_messages picks up a message posted during the polling window."""

    async def _post():
        await asyncio.sleep(0.12)
        await send_message("sender", "late-rcv", "topic", "late payload")

    task = asyncio.create_task(_post())
    results = await watch_messages("late-rcv", timeout_seconds=1.0, poll_interval=0.05)
    await task
    assert len(results) == 1
    assert results[0]["payload"] == "late payload"


@pytest.mark.asyncio
async def test_watch_messages_after_id_filter():
    """watch_messages respects after_id so earlier messages are excluded."""
    id1 = await send_message("s", "rcv2", "t", "first")
    id2 = await send_message("s", "rcv2", "t", "second")
    results = await watch_messages("rcv2", after_id=id1, timeout_seconds=1.0)
    assert len(results) == 1
    assert results[0]["id"] == id2


# ---------------------------------------------------------------------------
# get_workflow_messages: cross-session retrieval by correlation_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_workflow_messages_cross_session():
    """get_workflow_messages returns messages from multiple sessions sharing a correlation_id."""
    wf = "wf-crosssession"
    await send_message("planner", "worker-a", "t", "from-planner", correlation_id=wf)
    await send_message("worker-a", "planner", "t", "from-worker", correlation_id=wf)
    # Unrelated message should be excluded.
    await send_message("planner", "worker-a", "t", "unrelated")

    results = await get_workflow_messages(wf)
    assert len(results) == 2
    payloads = {r["payload"] for r in results}
    assert payloads == {"from-planner", "from-worker"}
    assert all(r["correlation_id"] == wf for r in results)


@pytest.mark.asyncio
async def test_get_workflow_messages_kind_filter():
    """get_workflow_messages respects the kind filter."""
    wf = "wf-kind"
    await send_message("a", "s", "t", "req", correlation_id=wf, kind="request")
    await send_message("a", "s", "t", "evt", correlation_id=wf, kind="event")

    requests = await get_workflow_messages(wf, kind="request")
    assert len(requests) == 1
    assert requests[0]["kind"] == "request"

    events = await get_workflow_messages(wf, kind="event")
    assert len(events) == 1
    assert events[0]["kind"] == "event"


@pytest.mark.asyncio
async def test_get_workflow_messages_after_id():
    """get_workflow_messages respects after_id."""
    wf = "wf-afterid"
    id1 = await send_message("a", "s", "t", "first", correlation_id=wf)
    id2 = await send_message("a", "s", "t", "second", correlation_id=wf)

    results = await get_workflow_messages(wf, after_id=id1)
    assert len(results) == 1
    assert results[0]["id"] == id2


@pytest.mark.asyncio
async def test_get_workflow_messages_empty():
    """get_workflow_messages returns [] for an unknown correlation_id."""
    results = await get_workflow_messages("wf-nonexistent")
    assert results == []


# ---------------------------------------------------------------------------
# watch_pending_actions: event-like surface over action bus
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watch_pending_actions_sees_existing():
    """watch_pending_actions returns immediately when actions already exist."""
    await request_action(
        requester_session="worker",
        action_type="merge_branch",
        payload_json='{"branch":"feat"}',
        target_session="supervisor",
        correlation_id="wf-act-1",
    )
    results = await watch_pending_actions(
        target_session="supervisor",
        correlation_id="wf-act-1",
        timeout_seconds=5.0,
    )
    assert len(results) == 1
    assert results[0].action_type == "merge_branch"


@pytest.mark.asyncio
async def test_watch_pending_actions_timeout_empty():
    """watch_pending_actions returns [] when no actions appear before the deadline."""
    results = await watch_pending_actions(
        target_session="ghost-supervisor",
        timeout_seconds=0.1,
        poll_interval=0.05,
    )
    assert results == []


@pytest.mark.asyncio
async def test_watch_pending_actions_sees_new_action():
    """watch_pending_actions picks up an action submitted during the polling window."""

    async def _submit():
        await asyncio.sleep(0.12)
        await request_action(
            requester_session="worker-b",
            action_type="run_release",
            payload_json='{"tag":"v1.2"}',
            target_session="release-mgr",
        )

    task = asyncio.create_task(_submit())
    results = await watch_pending_actions(
        target_session="release-mgr",
        timeout_seconds=1.0,
        poll_interval=0.05,
    )
    await task
    assert len(results) == 1
    assert results[0].action_type == "run_release"


@pytest.mark.asyncio
async def test_watch_pending_actions_excludes_resolved():
    """watch_pending_actions does not return already-approved actions."""
    action_id = await request_action(
        requester_session="worker",
        action_type="edit_file",
        payload_json='{"path":"src/a.py"}',
        target_session="supervisor",
    )
    await approve_action(action_id, resolved_by="supervisor")

    results = await watch_pending_actions(
        target_session="supervisor",
        timeout_seconds=0.1,
        poll_interval=0.05,
    )
    assert results == []


# ---------------------------------------------------------------------------
# db.get_workflow_messages: direct layer validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_get_workflow_messages_direct():
    """db.get_workflow_messages returns the same cross-session rows as the bus wrapper."""
    wf = "wf-db-direct"
    await send_message("src", "dest", "t", "p1", correlation_id=wf)
    await send_message("dest", "src", "t", "p2", correlation_id=wf)

    db = await get_db()
    rows = await db.get_workflow_messages(wf)
    assert len(rows) == 2
    assert {r["payload"] for r in rows} == {"p1", "p2"}
