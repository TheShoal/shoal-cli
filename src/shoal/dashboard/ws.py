"""Dashboard WebSocket handler — pushes HTML partials on session events."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import WebSocket, WebSocketDisconnect

from shoal.core.state import get_session
from shoal.dashboard.context import session_card_context

if TYPE_CHECKING:
    from jinja2 import Environment

logger = logging.getLogger(__name__)


# Set by init_jinja_env() once the app factory configures Jinja2.
_jinja_env: Environment | None = None


def init_jinja_env(env: Environment) -> None:
    """Store the Jinja2 environment for use in WS push rendering.

    Args:
        env: The configured Jinja2 Environment instance.
    """
    global _jinja_env
    _jinja_env = env


class DashboardWsManager:
    """Manages active dashboard WebSocket connections."""

    def __init__(self) -> None:
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new connection.

        Args:
            websocket: The incoming WebSocket connection.
        """
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a connection.

        Args:
            websocket: The WebSocket connection to remove.
        """
        self.active_connections.discard(websocket)

    async def broadcast_html(self, html: str) -> None:
        """Send an HTML fragment to all connected clients.

        Args:
            html: The HTML partial to broadcast.
        """
        broken: list[WebSocket] = []
        for conn in list(self.active_connections):
            try:
                await conn.send_text(html)
            except Exception:
                logger.warning("Dashboard WS send failed, removing connection")
                broken.append(conn)
        for conn in broken:
            self.active_connections.discard(conn)


ws_manager = DashboardWsManager()

_pending_broadcasts: dict[str, dict[str, object]] = {}
_broadcast_lock = asyncio.Lock()


async def _broadcast_session_card(session_id: str) -> None:
    """Render and broadcast a session card for the given session ID."""
    if _jinja_env is None:
        return
    session = await get_session(session_id)
    if session is None:
        return
    now = datetime.now(UTC)
    card_ctx = session_card_context(session, now=now)
    template = _jinja_env.get_template("partials/session_card.html")
    html = template.render(**card_ctx, oob=True)
    await ws_manager.broadcast_html(html)


async def _flush_broadcasts_after_delay() -> None:
    """Flush any pending broadcasts after a 100ms debounce window."""
    await asyncio.sleep(0.1)
    async with _broadcast_lock:
        for session_id in list(_pending_broadcasts.keys()):
            await _broadcast_session_card(session_id)
        _pending_broadcasts.clear()


async def notify_status_change(event: dict[str, object]) -> None:
    """React to a status_change event from the main poller.

    Batches broadcasts within a 100ms window to avoid flooding clients with
    rapid status changes.  Renders an updated session_card partial and pushes
    it to all dashboard WebSocket clients via HTMX out-of-band swap.
    No-ops if no dashboard WebSocket clients are connected or Jinja2 is not
    yet initialised.

    Args:
        event: The status_change event dict with ``session_id`` key.
    """
    if not ws_manager.active_connections or _jinja_env is None:
        return

    session_id = str(event.get("session_id", ""))
    if not session_id:
        return

    async with _broadcast_lock:
        _pending_broadcasts[session_id] = event
        if len(_pending_broadcasts) == 1:
            # First in batch — schedule flush
            _pending_broadcast_task = asyncio.create_task(_flush_broadcasts_after_delay())  # noqa: RUF006


async def dashboard_ws_endpoint(
    websocket: WebSocket,
) -> None:
    """WebSocket endpoint for live dashboard updates.

    Clients connect here to receive HTML partial pushes.  The server sends
    HTMX out-of-band fragments; clients don't need to send anything.

    Args:
        websocket: The incoming WebSocket connection.
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; actual data flows server→client only.
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.warning("Dashboard WebSocket error", exc_info=True)
    finally:
        ws_manager.disconnect(websocket)
