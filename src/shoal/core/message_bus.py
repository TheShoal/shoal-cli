"""Agent Bus — session-to-session message passing via SQLite.

Provides a lightweight async message queue backed by the Shoal SQLite
database.  Sessions can post messages to named topics and other sessions
can receive and acknowledge them.

The design is intentionally simple: SQLite polling at ~500 ms is sufficient
for agent coordination use cases.  No external broker is required.

Usage::

    from shoal.core.message_bus import send_message, receive_messages, mark_consumed

    # Session A sends a typed request to session B
    msg_id = await send_message(
        from_session="planner",
        to_session="worker-a",
        topic="code-review",
        payload=json.dumps({"path": "src/api.ts"}),
        kind="request",
        correlation_id="wf_01H...",
    )

    # Session B polls for messages
    messages = await receive_messages("worker-a", unconsumed_only=True)
    for msg in messages:
        await mark_consumed(msg["id"])
"""

from __future__ import annotations

import asyncio
import logging

from shoal.models.message import MessageKind

logger = logging.getLogger("shoal.message_bus")


async def send_message(
    from_session: str,
    to_session: str,
    topic: str,
    payload: str,
    *,
    kind: MessageKind = "event",
    correlation_id: str | None = None,
    reply_to_message_id: int | None = None,
    priority: int = 3,
    requires_ack: bool = False,
    metadata_json: str | None = None,
    expires_at: str | None = None,
) -> int:
    """Post a message from one session to another.

    Args:
        from_session: Sender session name or ID.
        to_session: Recipient session name or ID.
        topic: Message topic (e.g. ``"handoff"``, ``"command_failed"``).
        payload: Arbitrary string payload (typically JSON).
        kind: Message kind; one of event, request, response, handoff,
            approval_request, approval_decision, error.  Defaults to
            ``"event"`` for backward compatibility.
        correlation_id: Optional workflow/correlation identifier for
            multi-step workflow tracing.
        reply_to_message_id: ID of a prior message this replies to.
        priority: 1 (highest) - 5 (lowest).  Defaults to 3.
        requires_ack: If True, the recipient should call mark_acked after
            processing.
        metadata_json: Optional JSON string for additional metadata
            (e.g. workflow name, thread ID).
        expires_at: Optional ISO timestamp after which the message
            should be ignored.

    Returns:
        Auto-assigned message ID.
    """
    from shoal.core.db import get_db

    db = await get_db()
    msg_id = await db.send_message(
        from_session,
        to_session,
        topic,
        payload,
        kind=kind,
        correlation_id=correlation_id,
        reply_to_message_id=reply_to_message_id,
        priority=priority,
        requires_ack=requires_ack,
        metadata_json=metadata_json,
        expires_at=expires_at,
    )
    logger.debug(
        "AgentBus: sent msg %d  %s→%s [%s/%s] corr=%s",
        msg_id,
        from_session,
        to_session,
        topic,
        kind,
        correlation_id,
    )
    return msg_id


async def receive_messages(
    session: str,
    topic: str | None = None,
    *,
    kind: str | None = None,
    correlation_id: str | None = None,
    unconsumed_only: bool = True,
    limit: int = 50,
    after_id: int | None = None,
) -> list[dict[str, object]]:
    """Retrieve messages addressed to a session.

    Args:
        session: Recipient session name or ID.
        topic: Optional topic filter.
        kind: Optional kind filter (e.g. ``"request"``, ``"response"``).
        correlation_id: Optional correlation ID filter for workflow-centric
            retrieval.
        unconsumed_only: If True (default), only return unconsumed messages.
        limit: Maximum number of messages to return.
        after_id: If set, only return messages with id > after_id.  Useful
            for incremental polling (watch semantics).

    Returns:
        List of message dicts with all envelope fields.  Ordered oldest-first.
    """
    from shoal.core.db import get_db

    db = await get_db()
    return await db.receive_messages(
        session,
        topic,
        kind=kind,
        correlation_id=correlation_id,
        unconsumed_only=unconsumed_only,
        limit=limit,
        after_id=after_id,
    )


async def mark_consumed(message_id: int) -> None:
    """Mark a message as consumed.

    Args:
        message_id: ID of the message to mark consumed.
    """
    from shoal.core.db import get_db

    db = await get_db()
    await db.mark_message_consumed(message_id)
    logger.debug("AgentBus: consumed msg %d", message_id)


async def mark_acked(message_id: int) -> None:
    """Mark a message as acknowledged by its recipient.

    Acknowledgment is distinct from consumption: a message may be consumed
    (removed from the pending queue) and then separately acknowledged once
    the action it describes has been completed.

    Args:
        message_id: ID of the message to acknowledge.
    """
    from shoal.core.db import get_db

    db = await get_db()
    await db.mark_message_acked(message_id)
    logger.debug("AgentBus: acked msg %d", message_id)


async def watch_messages(
    session: str,
    *,
    topic: str | None = None,
    kind: str | None = None,
    correlation_id: str | None = None,
    after_id: int | None = None,
    timeout_seconds: float = 30.0,
    poll_interval: float = 0.5,
) -> list[dict[str, object]]:
    """Poll for new messages until at least one arrives or the timeout elapses.

    Internally polls the SQLite queue at ``poll_interval`` intervals.
    Consumers can treat the result as a lightweight event-stream response.

    Args:
        session: Recipient session name or ID.
        topic: Optional topic filter.
        kind: Optional kind filter.
        correlation_id: Optional correlation ID filter.
        after_id: Only return messages with id > after_id.
        timeout_seconds: How long to poll before returning an empty list.
        poll_interval: Seconds between polls.

    Returns:
        All matching messages found within the timeout, oldest-first.
        Returns an empty list if no messages arrive before the timeout.
    """
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        messages = await receive_messages(
            session,
            topic,
            kind=kind,
            correlation_id=correlation_id,
            unconsumed_only=True,
            after_id=after_id,
        )
        if messages:
            return messages
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return []
        await asyncio.sleep(min(poll_interval, remaining))


async def get_workflow_messages(
    correlation_id: str,
    *,
    kind: str | None = None,
    limit: int = 50,
    after_id: int | None = None,
) -> list[dict[str, object]]:
    """Return all messages sharing a correlation ID, across all sessions.

    Useful for reconstructing a complete workflow trace regardless of which
    sessions sent or received each message.

    Args:
        correlation_id: Workflow or request correlation identifier.
        kind: Optional message kind filter.
        limit: Maximum messages to return.
        after_id: Only return messages with id > after_id.

    Returns:
        Matching messages in chronological order.
    """
    from shoal.core.db import get_db

    db = await get_db()
    messages = await db.get_workflow_messages(
        correlation_id, kind=kind, limit=limit, after_id=after_id
    )
    logger.debug("AgentBus: workflow %s returned %d messages", correlation_id, len(messages))
    return messages


async def purge_old_messages(older_than_seconds: int = 86_400) -> int:
    """Purge consumed messages older than the given age.

    Args:
        older_than_seconds: Messages consumed more than this many seconds ago
            will be deleted.  Defaults to 24 hours.

    Returns:
        Number of messages deleted.
    """
    from shoal.core.db import get_db

    db = await get_db()
    count = await db.purge_old_messages(older_than_seconds)
    if count:
        logger.info("AgentBus: purged %d old message(s)", count)
    return count
