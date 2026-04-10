"""Integration tests for multi-agent Bus workflow patterns.

Tests the complete request → handoff → approval flow with correlation IDs,
typed messages, and workflow aggregation across multiple sessions.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest

from shoal.core.db import ShoalDB
from shoal.core.message_bus import (
    get_workflow_messages,
    mark_consumed,
    receive_messages,
    send_message,
    watch_messages,
)


@pytest.fixture(autouse=True)
async def fresh_db(tmp_path):  # type: ignore[no-untyped-def]
    """Isolate each test in its own temporary database."""
    await ShoalDB.reset_instance()
    with (
        patch("shoal.core.config.data_dir", return_value=tmp_path),
        patch("shoal.core.config.ensure_dirs"),
    ):
        yield
    await ShoalDB.reset_instance()


@pytest.fixture
def correlation_id() -> str:
    """Generate unique correlation ID for each test."""
    return f"wf_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Complete workflow: planner → workers → planner → reviewer
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_multi_agent_workflow(correlation_id: str) -> None:
    """Test the full planner-worker-reviewer coordination pattern."""
    # Step 1: Planner sends requests to two workers
    req_a_id = await send_message(
        from_session="planner",
        to_session="worker-a",
        topic="code-review",
        payload=json.dumps({"task": "validate_api", "files": ["api.py"]}),
        kind="request",
        correlation_id=correlation_id,
        priority=2,
    )
    req_b_id = await send_message(
        from_session="planner",
        to_session="worker-b",
        topic="code-review",
        payload=json.dumps({"task": "check_tests", "files": ["test_api.py"]}),
        kind="request",
        correlation_id=correlation_id,
        priority=2,
    )
    assert req_a_id > 0
    assert req_b_id > 0

    # Step 2: Workers receive and process requests
    worker_a_msgs = await receive_messages(
        "worker-a",
        kind="request",
        correlation_id=correlation_id,
        unconsumed_only=True,
    )
    assert len(worker_a_msgs) == 1
    assert json.loads(worker_a_msgs[0]["payload"])["task"] == "validate_api"  # type: ignore[arg-type]
    await mark_consumed(worker_a_msgs[0]["id"])  # type: ignore[arg-type]

    worker_b_msgs = await receive_messages(
        "worker-b",
        kind="request",
        correlation_id=correlation_id,
        unconsumed_only=True,
    )
    assert len(worker_b_msgs) == 1
    assert json.loads(worker_b_msgs[0]["payload"])["task"] == "check_tests"  # type: ignore[arg-type]
    await mark_consumed(worker_b_msgs[0]["id"])  # type: ignore[arg-type]

    # Step 3: Workers send handoffs back to planner
    handoff_a_id = await send_message(
        from_session="worker-a",
        to_session="planner",
        topic="task-complete",
        payload=json.dumps({"status": "completed", "findings": "All checks passed"}),
        kind="handoff",
        correlation_id=correlation_id,
        reply_to_message_id=req_a_id,
    )
    handoff_b_id = await send_message(
        from_session="worker-b",
        to_session="planner",
        topic="task-complete",
        payload=json.dumps({"status": "completed", "findings": "Coverage: 95%"}),
        kind="handoff",
        correlation_id=correlation_id,
        reply_to_message_id=req_b_id,
    )
    assert handoff_a_id > 0
    assert handoff_b_id > 0

    # Step 4: Planner receives handoffs
    planner_handoffs = await receive_messages(
        "planner",
        kind="handoff",
        correlation_id=correlation_id,
        unconsumed_only=True,
    )
    assert len(planner_handoffs) == 2
    for msg in planner_handoffs:
        await mark_consumed(msg["id"])  # type: ignore[arg-type]

    # Step 5: Planner aggregates workflow context
    all_messages = await get_workflow_messages(correlation_id)
    assert len(all_messages) == 4  # 2 requests + 2 handoffs
    request_messages = [m for m in all_messages if m["kind"] == "request"]
    handoff_messages = [m for m in all_messages if m["kind"] == "handoff"]
    assert len(request_messages) == 2
    assert len(handoff_messages) == 2

    # Step 6: Planner sends approval request to reviewer
    approval_req_id = await send_message(
        from_session="planner",
        to_session="reviewer",
        topic="approval",
        payload=json.dumps(
            {
                "workflow_id": correlation_id,
                "summary": "2 workers completed successfully",
            }
        ),
        kind="approval_request",
        correlation_id=correlation_id,
    )
    assert approval_req_id > 0

    # Step 7: Reviewer receives and processes
    reviewer_msgs = await receive_messages(
        "reviewer",
        kind="approval_request",
        correlation_id=correlation_id,
        unconsumed_only=True,
    )
    assert len(reviewer_msgs) == 1
    await mark_consumed(reviewer_msgs[0]["id"])  # type: ignore[arg-type]

    # Step 8: Reviewer posts approval decision
    decision_id = await send_message(
        from_session="reviewer",
        to_session="planner",
        topic="review-decision",
        payload=json.dumps({"approved": True, "reason": "All checks passed"}),
        kind="approval_decision",
        correlation_id=correlation_id,
        reply_to_message_id=approval_req_id,
    )
    assert decision_id > 0

    # Step 9: Planner receives approval
    decisions = await receive_messages(
        "planner",
        kind="approval_decision",
        correlation_id=correlation_id,
        unconsumed_only=True,
    )
    assert len(decisions) == 1
    decision_payload = json.loads(decisions[0]["payload"])  # type: ignore[arg-type]
    assert decision_payload["approved"] is True

    # Final verification: complete workflow trace
    final_messages = await get_workflow_messages(correlation_id)
    assert len(final_messages) == 6  # 2 req + 2 handoff + 1 approval_req + 1 approval_dec
    assert all(m["correlation_id"] == correlation_id for m in final_messages)


# ---------------------------------------------------------------------------
# Correlation ID tracking across sessions
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_correlation_id_tracking(correlation_id: str) -> None:
    """Verify get_workflow_messages aggregates across session boundaries."""
    # Send messages from multiple sessions with same correlation_id
    await send_message("session-a", "session-b", "t1", "p1", correlation_id=correlation_id)
    await send_message("session-b", "session-c", "t2", "p2", correlation_id=correlation_id)
    await send_message("session-c", "session-a", "t3", "p3", correlation_id=correlation_id)

    # Unrelated message should not appear
    await send_message("session-x", "session-y", "t4", "p4", correlation_id="other_wf")

    # Aggregate by correlation_id
    workflow_messages = await get_workflow_messages(correlation_id)
    assert len(workflow_messages) == 3
    payloads = {m["payload"] for m in workflow_messages}
    assert payloads == {"p1", "p2", "p3"}
    assert all(m["correlation_id"] == correlation_id for m in workflow_messages)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_workflow_messages_kind_filter(correlation_id: str) -> None:
    """Verify get_workflow_messages respects kind filter."""
    # Mix of message kinds with same correlation_id
    await send_message(
        "planner",
        "worker",
        "t",
        "req1",
        kind="request",
        correlation_id=correlation_id,
    )
    await send_message(
        "planner",
        "worker",
        "t",
        "req2",
        kind="request",
        correlation_id=correlation_id,
    )
    await send_message(
        "worker",
        "planner",
        "t",
        "handoff1",
        kind="handoff",
        correlation_id=correlation_id,
    )
    await send_message(
        "worker",
        "planner",
        "t",
        "evt1",
        kind="event",
        correlation_id=correlation_id,
    )

    # Filter by kind
    requests = await get_workflow_messages(correlation_id, kind="request")
    assert len(requests) == 2
    assert all(m["kind"] == "request" for m in requests)

    handoffs = await get_workflow_messages(correlation_id, kind="handoff")
    assert len(handoffs) == 1
    assert handoffs[0]["kind"] == "handoff"

    # All messages without filter
    all_msgs = await get_workflow_messages(correlation_id)
    assert len(all_msgs) == 4


# ---------------------------------------------------------------------------
# Message consumption and duplicate prevention
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unconsumed_only_prevents_duplicates(correlation_id: str) -> None:
    """Verify unconsumed_only flag prevents duplicate processing."""
    msg_id = await send_message(
        "sender",
        "receiver",
        "topic",
        "payload",
        correlation_id=correlation_id,
    )

    # First receive: message appears
    msgs1 = await receive_messages("receiver", unconsumed_only=True)
    assert len(msgs1) == 1
    assert msgs1[0]["id"] == msg_id

    # Mark consumed
    await mark_consumed(msg_id)

    # Second receive: message does not appear
    msgs2 = await receive_messages("receiver", unconsumed_only=True)
    assert len(msgs2) == 0

    # Without unconsumed_only flag: message still appears
    msgs3 = await receive_messages("receiver", unconsumed_only=False)
    assert len(msgs3) == 1
    assert msgs3[0]["consumed_at"] is not None


# ---------------------------------------------------------------------------
# Event-driven coordination with watch_messages
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_watch_messages_event_driven(correlation_id: str) -> None:
    """Test watch_messages for event-driven coordination."""
    import asyncio

    # Simulate delayed message arrival
    async def delayed_send() -> None:
        await asyncio.sleep(0.2)
        await send_message(
            "worker",
            "planner",
            "result",
            "delayed_result",
            kind="handoff",
            correlation_id=correlation_id,
        )

    # Start watch before message arrives
    task = asyncio.create_task(delayed_send())
    messages = await watch_messages(
        session="planner",
        kind="handoff",
        correlation_id=correlation_id,
        timeout_seconds=2.0,
        poll_interval=0.1,
    )
    await task

    # Verify message was received
    assert len(messages) == 1
    assert messages[0]["payload"] == "delayed_result"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_watch_messages_timeout() -> None:
    """Test watch_messages returns empty list on timeout."""
    messages = await watch_messages(
        session="nonexistent",
        timeout_seconds=0.1,
        poll_interval=0.05,
    )
    assert messages == []


# ---------------------------------------------------------------------------
# Priority and reply threading
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_message_priority_ordering(correlation_id: str) -> None:
    """Verify messages respect priority field."""
    # Send messages with different priorities
    low_id = await send_message(
        "sender",
        "receiver",
        "t",
        "low",
        priority=5,
        correlation_id=correlation_id,
    )
    high_id = await send_message(
        "sender",
        "receiver",
        "t",
        "high",
        priority=1,
        correlation_id=correlation_id,
    )
    medium_id = await send_message(
        "sender",
        "receiver",
        "t",
        "medium",
        priority=3,
        correlation_id=correlation_id,
    )

    # Receive all messages
    messages = await receive_messages("receiver", unconsumed_only=True)
    assert len(messages) == 3

    # Verify priorities are stored
    msg_by_id = {m["id"]: m for m in messages}
    assert msg_by_id[high_id]["priority"] == 1
    assert msg_by_id[medium_id]["priority"] == 3
    assert msg_by_id[low_id]["priority"] == 5


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reply_threading(correlation_id: str) -> None:
    """Verify reply_to_message_id threads messages together."""
    # Original request
    req_id = await send_message(
        "planner",
        "worker",
        "task",
        "do_work",
        kind="request",
        correlation_id=correlation_id,
    )

    # Reply threading
    reply_id = await send_message(
        "worker",
        "planner",
        "result",
        "work_done",
        kind="response",
        correlation_id=correlation_id,
        reply_to_message_id=req_id,
    )

    # Verify reply reference
    messages = await get_workflow_messages(correlation_id)
    reply_msg = next(m for m in messages if m["id"] == reply_id)
    assert reply_msg["reply_to_message_id"] == req_id


# ---------------------------------------------------------------------------
# Error handling patterns
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_error_message_kind(correlation_id: str) -> None:
    """Test error message kind for failure signaling."""
    # Worker sends error
    await send_message(
        "worker",
        "planner",
        "task-failed",
        json.dumps({"error": "Validation failed", "details": "API endpoint unreachable"}),
        kind="error",
        correlation_id=correlation_id,
    )

    # Planner receives error
    errors = await receive_messages(
        "planner",
        kind="error",
        correlation_id=correlation_id,
        unconsumed_only=True,
    )
    assert len(errors) == 1
    error_payload = json.loads(errors[0]["payload"])  # type: ignore[arg-type]
    assert error_payload["error"] == "Validation failed"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_workflow_timeout_handling() -> None:
    """Test timeout handling in watch_messages."""
    correlation_id = f"wf_{uuid.uuid4().hex[:12]}"

    # No messages sent - should timeout
    messages = await watch_messages(
        session="waiting-session",
        kind="handoff",
        correlation_id=correlation_id,
        timeout_seconds=0.2,
        poll_interval=0.05,
    )

    assert messages == []
    # In production: handle timeout with retry, escalation, or error


# ---------------------------------------------------------------------------
# After_id incremental polling
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_after_id_incremental_polling(correlation_id: str) -> None:
    """Verify after_id parameter for incremental message retrieval."""
    # Send initial messages
    id1 = await send_message("s", "r", "t", "msg1", correlation_id=correlation_id)
    id2 = await send_message("s", "r", "t", "msg2", correlation_id=correlation_id)

    # Get messages after id1
    new_messages = await get_workflow_messages(correlation_id, after_id=id1)
    assert len(new_messages) == 1
    assert new_messages[0]["id"] == id2

    # Send another message
    id3 = await send_message("s", "r", "t", "msg3", correlation_id=correlation_id)

    # Incremental retrieval
    latest = await get_workflow_messages(correlation_id, after_id=id2)
    assert len(latest) == 1
    assert latest[0]["id"] == id3
