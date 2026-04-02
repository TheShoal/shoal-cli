"""FastAPI router for Shoal web dashboard HTML views."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from shoal.core import journal as journal_core
from shoal.core.state import get_session, list_sessions
from shoal.core.tmux import async_capture_pane
from shoal.dashboard.context import (
    fleet_context,
    flow_context,
    journal_entry_context,
    session_detail_context,
)
from shoal.dashboard.ws import dashboard_ws_endpoint, init_jinja_env
from shoal.models.state import TmuxRuntimeState

logger = logging.getLogger(__name__)

router = APIRouter()

# Populated by create_dashboard_app() once templates are configured.
_templates: Jinja2Templates | None = None


def _get_templates() -> Jinja2Templates:
    if _templates is None:
        raise RuntimeError("Dashboard templates not initialised")  # pragma: no cover
    return _templates


def init_templates(templates: Jinja2Templates) -> None:
    """Bind the Jinja2Templates instance to this router module.

    Args:
        templates: The configured Jinja2Templates instance.
    """
    global _templates
    _templates = templates
    init_jinja_env(templates.env)


# ---------------------------------------------------------------------------
# Fleet board (home)
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def fleet_board(request: Request) -> HTMLResponse:
    """Render the fleet overview page."""
    sessions = await list_sessions()
    now = datetime.now(UTC)
    ctx = fleet_context(sessions, now=now)
    return _get_templates().TemplateResponse(
        request,
        "fleet.html",
        {**ctx, "request": request},
    )


# ---------------------------------------------------------------------------
# Flow / team architecture
# ---------------------------------------------------------------------------


@router.get("/flow", response_class=HTMLResponse)
async def flow_architecture(request: Request) -> HTMLResponse:
    """Render the agent team flow / architecture graph.

    Shows the parent-child relationships between sessions as a navigable
    tree, making supervisor-worker topologies visible.
    """
    sessions = await list_sessions()
    ctx = flow_context(sessions)
    return _get_templates().TemplateResponse(
        request,
        "flow.html",
        {**ctx, "request": request},
    )


@router.get("/partials/status-bar", response_class=HTMLResponse)
async def status_bar_partial(request: Request) -> HTMLResponse:
    """Return the live status bar fragment (polled every 5s)."""
    sessions = await list_sessions()
    now = datetime.now(UTC)
    ctx = fleet_context(sessions, now=now)
    return _get_templates().TemplateResponse(
        request,
        "partials/status_bar.html",
        {**ctx, "request": request},
    )


@router.get("/partials/session-list", response_class=HTMLResponse)
async def session_list_partial(
    request: Request,
    status: str | None = None,
    q: str | None = None,
) -> HTMLResponse:
    """Return filtered session-list fragment for HTMX swaps.

    Args:
        request: The incoming request.
        status: Optional status filter: "all", "attention", "running", "idle", "stopped".
        q: Optional name search string (case-insensitive substring).
    """
    sessions = await list_sessions()
    now = datetime.now(UTC)

    if status == "attention":
        from shoal.models.state import SessionStatus

        sessions = [s for s in sessions if s.status in (SessionStatus.error, SessionStatus.waiting)]
    elif status and status != "all":
        from shoal.models.state import SessionStatus

        try:
            filter_status = SessionStatus(status)
            sessions = [s for s in sessions if s.status == filter_status]
        except ValueError:
            pass

    if q:
        sessions = [s for s in sessions if q.lower() in s.name.lower()]

    ctx = fleet_context(sessions, now=now)
    return _get_templates().TemplateResponse(
        request,
        "partials/session_list.html",
        {**ctx, "request": request},
    )


# ---------------------------------------------------------------------------
# Session detail
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}", response_class=HTMLResponse)
async def session_detail(request: Request, session_id: str) -> HTMLResponse:
    """Render the session detail page."""
    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    now = datetime.now(UTC)
    ctx = session_detail_context(session, now=now)
    return _get_templates().TemplateResponse(
        request,
        "session.html",
        {**ctx, "request": request},
    )


@router.get("/partials/journal/{session_id}", response_class=HTMLResponse)
async def journal_partial(
    request: Request,
    session_id: str,
    limit: int = 20,
) -> HTMLResponse:
    """Return the journal timeline fragment.

    Args:
        request: The incoming request.
        session_id: The session whose journal to render.
        limit: Maximum number of entries to return (most recent).
    """
    entries = journal_core.read_journal(session_id, limit=limit)
    now = datetime.now(UTC)
    entry_ctxs = [journal_entry_context(e, now=now) for e in entries]
    return _get_templates().TemplateResponse(
        request,
        "partials/journal_timeline.html",
        {"entries": entry_ctxs, "request": request},
    )


@router.get("/partials/pane/{session_id}", response_class=HTMLResponse)
async def pane_partial(
    request: Request,
    session_id: str,
    lines: int = 50,
) -> HTMLResponse:
    """Return the terminal pane capture fragment.

    Args:
        request: The incoming request.
        session_id: The session whose pane to capture.
        lines: Number of lines to capture.
    """
    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    pane_text = ""
    if isinstance(session.runtime, TmuxRuntimeState):
        try:
            pane_text = await async_capture_pane(
                session.runtime.session_name,
                lines=lines,
            )
        except Exception:
            logger.warning("pane capture failed for %s", session_id, exc_info=True)

    return _get_templates().TemplateResponse(
        request,
        "partials/pane_output.html",
        {"pane_text": pane_text, "session_id": session_id, "request": request},
    )


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    """Dashboard WebSocket: receives live HTML partial pushes."""
    await dashboard_ws_endpoint(websocket)
