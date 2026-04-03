"""Proactive Supervisor (Scout loop) — detects failures and pre-fetches context.

Subscribes to :attr:`LifecycleEvent.command_failed` events emitted by the
:class:`~shoal.services.watcher.Watcher`.  On each failure event it captures
the pane snapshot and stores a *failure context packet* in the
``failure_contexts`` SQLite table.  Pisces (or any MCP client) can then call
the ``get_failure_context`` MCP tool at the start of a turn to receive
pre-fetched context and skip the "re-read the terminal" round-trip.

Lifecycle::

    supervisor = init_proactive_supervisor(cfg)
    register_proactive_hook(supervisor)   # wire into lifecycle events
    # Agents call the get_failure_context MCP tool to consume packets.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shoal.models.config.robo import ProactiveSupervisorConfig

logger = logging.getLogger("shoal.proactive_supervisor")


class ProactiveSupervisor:
    """Stores failure context packets and serves them to agents on demand."""

    def __init__(self, config: ProactiveSupervisorConfig) -> None:
        self.config: ProactiveSupervisorConfig = config

    async def on_command_failed(
        self,
        session_id: str,
        session_name: str,
        pane_snapshot: str,
        old_status: str,
    ) -> None:
        """Handle a command_failed lifecycle event.

        Stores a failure context packet in the database.  Old packets for the
        same session are expired based on ``failure_ttl_seconds``.

        Args:
            session_id: Session where the failure occurred.
            session_name: Human-readable session name.
            pane_snapshot: Captured pane output at failure time.
            old_status: The session status before transitioning to ``error``.
        """
        from shoal.core.db import get_db

        db = await get_db()
        context_id = await db.save_failure_context(
            session_id, session_name, pane_snapshot, old_status
        )
        await db.expire_old_failure_contexts(
            session_id, ttl_seconds=self.config.failure_ttl_seconds
        )
        logger.info(
            "ProactiveSupervisor: stored failure context #%d for %s (%s)",
            context_id,
            session_id,
            session_name,
        )

    async def get_failure_context(
        self,
        session_id: str,
        *,
        unconsumed_only: bool = True,
    ) -> dict[str, object] | None:
        """Return the most recent failure context packet for a session.

        Args:
            session_id: Session to query.
            unconsumed_only: If True (default), only return unconsumed packets.

        Returns:
            Dict with keys ``id``, ``session_id``, ``session_name``,
            ``pane_snapshot``, ``old_status``, ``created_at``.
            Returns ``None`` if no packet is available.
        """
        from shoal.core.db import get_db

        db = await get_db()
        return await db.get_failure_context(session_id, unconsumed_only=unconsumed_only)

    async def consume_failure_context(self, context_id: int) -> None:
        """Mark a failure context packet as consumed.

        Args:
            context_id: Packet ID to mark consumed.
        """
        from shoal.core.db import get_db

        db = await get_db()
        await db.consume_failure_context(context_id)


# ---------------------------------------------------------------------------
# Lifecycle hook integration
# ---------------------------------------------------------------------------


def register_proactive_hook(supervisor: ProactiveSupervisor) -> None:
    """Register the proactive supervisor as a lifecycle hook.

    Must be called after the lifecycle service is initialised.

    Args:
        supervisor: Supervisor instance to register.
    """
    from shoal.models.state import LifecycleEvent
    from shoal.services.lifecycle import on

    async def _handle_command_failed(event: LifecycleEvent, **kwargs: object) -> None:
        session = kwargs.get("session")
        pane_snapshot = str(kwargs.get("pane_snapshot", ""))
        old_status = kwargs.get("old_status")

        if session is None:
            return

        from shoal.models.state import SessionState

        if not isinstance(session, SessionState):
            return

        await supervisor.on_command_failed(
            session_id=session.id,
            session_name=session.name,
            pane_snapshot=pane_snapshot,
            old_status=str(old_status) if old_status is not None else "",
        )

    on(LifecycleEvent.command_failed, _handle_command_failed)
    logger.info("ProactiveSupervisor: registered command_failed hook")


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_supervisor_instance: ProactiveSupervisor | None = None


def get_proactive_supervisor() -> ProactiveSupervisor | None:
    """Return the global ProactiveSupervisor singleton if initialised.

    Returns:
        ProactiveSupervisor instance, or None if not yet started.
    """
    return _supervisor_instance


def init_proactive_supervisor(config: ProactiveSupervisorConfig) -> ProactiveSupervisor:
    """Initialise and return the global ProactiveSupervisor singleton.

    Args:
        config: Proactive supervisor configuration.

    Returns:
        Initialised ProactiveSupervisor instance.
    """
    global _supervisor_instance
    _supervisor_instance = ProactiveSupervisor(config)
    return _supervisor_instance
