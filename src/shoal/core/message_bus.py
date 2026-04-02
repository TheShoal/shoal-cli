"""Agent Bus — session-to-session message passing via SQLite.

Provides a lightweight async message queue backed by the Shoal SQLite
database.  Sessions can post messages to named topics and other sessions
can receive and acknowledge them.

The design is intentionally simple: SQLite polling at ~500 ms is sufficient
for agent coordination use cases.  No external broker is required.

Usage::

    from shoal.core.message_bus import send_message, receive_messages, mark_consumed

    # Session A sends a message to session B
    msg_id = await send_message(
        from_session="agent-a",
        to_session="agent-b",
        topic="handoff",
        payload=json.dumps({"pr_url": "https://github.com/..."}),
    )

    # Session B polls for messages
    messages = await receive_messages("agent-b", unconsumed_only=True)
    for msg in messages:
        await mark_consumed(msg["id"])
"""

from __future__ import annotations

import logging

logger = logging.getLogger("shoal.message_bus")


async def send_message(
    from_session: str,
    to_session: str,
    topic: str,
    payload: str,
) -> int:
    """Post a message from one session to another.

    Args:
        from_session: Sender session name or ID.
        to_session: Recipient session name or ID.
        topic: Message topic (e.g. ``"handoff"``, ``"command_failed"``).
        payload: Arbitrary string payload (typically JSON).

    Returns:
        Auto-assigned message ID.
    """
    from shoal.core.db import get_db

    db = await get_db()
    msg_id = await db.send_message(from_session, to_session, topic, payload)
    logger.debug("AgentBus: sent msg %d  %s→%s [%s]", msg_id, from_session, to_session, topic)
    return msg_id


async def receive_messages(
    session: str,
    topic: str | None = None,
    *,
    unconsumed_only: bool = True,
    limit: int = 50,
) -> list[dict[str, object]]:
    """Retrieve messages addressed to a session.

    Args:
        session: Recipient session name or ID.
        topic: Optional topic filter.
        unconsumed_only: If True (default), only return unconsumed messages.
        limit: Maximum number of messages to return.

    Returns:
        List of message dicts with keys: id, from_session, to_session, topic,
        payload, created_at, consumed_at.  Ordered oldest-first.
    """
    from shoal.core.db import get_db

    db = await get_db()
    return await db.receive_messages(session, topic, unconsumed_only=unconsumed_only, limit=limit)


async def mark_consumed(message_id: int) -> None:
    """Mark a message as consumed.

    Args:
        message_id: ID of the message to mark consumed.
    """
    from shoal.core.db import get_db

    db = await get_db()
    await db.mark_message_consumed(message_id)
    logger.debug("AgentBus: consumed msg %d", message_id)


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
