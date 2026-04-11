"""FastAPI router for Shoal web dashboard HTML views."""

from __future__ import annotations

import html
import logging
import re
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from shoal.core import journal as journal_core
from shoal.core.state import get_session, list_sessions
from shoal.dashboard.context import (
    fleet_context,
    flow_context,
    journal_entry_context,
    session_detail_context,
)
from shoal.dashboard.ws import dashboard_ws_endpoint, init_jinja_env
from shoal.services.runtime_provider import provider_for_session

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

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


@router.get("/partials/status-bar", response_class=HTMLResponse, response_model=None)
async def status_bar_partial(
    request: Request,
    format: str | None = None,
) -> HTMLResponse | JSONResponse:
    """Return the live status bar fragment (polled every 5s).

    Args:
        request: The incoming request.
        format: If "json", return structured JSON instead of HTML fragment.
    """
    sessions = await list_sessions()
    now = datetime.now(UTC)
    ctx = fleet_context(sessions, now=now)

    if format == "json":
        return JSONResponse(content=ctx)

    return _get_templates().TemplateResponse(
        request,
        "partials/status_bar.html",
        {**ctx, "request": request},
    )


@router.get("/partials/session-list", response_class=HTMLResponse, response_model=None)
async def session_list_partial(
    request: Request,
    status: str | None = None,
    q: str | None = None,
    format: str | None = None,
) -> HTMLResponse | JSONResponse:
    """Return filtered session-list fragment for HTMX swaps.

    Args:
        request: The incoming request.
        status: Optional status filter: "all", "attention", "running", "idle", "stopped".
        q: Optional name search string (case-insensitive substring).
        format: If "json", return structured JSON instead of HTML fragment.
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

    if format == "json":
        return JSONResponse(content=ctx)

    return _get_templates().TemplateResponse(
        request,
        "partials/session_list.html",
        {**ctx, "request": request},
    )


# ---------------------------------------------------------------------------
# Session detail
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}", response_class=HTMLResponse, response_model=None)
async def session_detail(
    request: Request,
    session_id: str,
    format: str | None = None,
) -> HTMLResponse | JSONResponse:
    """Render the session detail page."""
    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    now = datetime.now(UTC)
    ctx = session_detail_context(session, now=now)

    if format == "json":
        return JSONResponse(content=ctx)

    return _get_templates().TemplateResponse(
        request,
        "session.html",
        {**ctx, "request": request},
    )


@router.get("/partials/journal/{session_id}", response_class=HTMLResponse, response_model=None)
async def journal_partial(
    request: Request,
    session_id: str,
    limit: int = 20,
    format: str | None = None,
) -> HTMLResponse | JSONResponse:
    """Return the journal timeline fragment.

    Args:
        request: The incoming request.
        session_id: The session whose journal to render.
        limit: Maximum number of entries to return (most recent).
        format: If "json", return structured JSON instead of HTML fragment.
    """
    entries = journal_core.read_journal(session_id, limit=limit)
    now = datetime.now(UTC)
    entry_ctxs = [journal_entry_context(e, now=now) for e in entries]

    if format == "json":
        return JSONResponse(content={"entries": entry_ctxs})

    return _get_templates().TemplateResponse(
        request,
        "partials/journal_timeline.html",
        {"entries": entry_ctxs, "request": request},
    )


@router.get("/partials/pane/{session_id}", response_class=HTMLResponse, response_model=None)
async def pane_partial(
    request: Request,
    session_id: str,
    lines: int = 50,
    format: str | None = None,
) -> HTMLResponse | JSONResponse:
    """Return the terminal pane capture fragment.

    Args:
        request: The incoming request.
        session_id: The session whose pane to capture.
        lines: Number of lines to capture.
        format: If "json", return structured JSON instead of HTML fragment.
    """
    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    pane_text = ""
    try:
        raw_text = await provider_for_session(session).async_capture_output(session, lines=lines)
        pane_text = html.escape(_ANSI_ESCAPE.sub("", raw_text))
    except Exception:
        logger.warning("pane capture failed for %s", session_id, exc_info=True)

    if format == "json":
        return JSONResponse(content={"session_id": session_id, "pane_text": pane_text})

    return _get_templates().TemplateResponse(
        request,
        "partials/pane_output.html",
        {"pane_text": pane_text, "session_id": session_id, "request": request},
    )


# ---------------------------------------------------------------------------
# MCP Matrix
# ---------------------------------------------------------------------------


async def _mcp_context() -> dict[str, object]:
    """Load sessions, servers, and stacks into a template context dict."""
    from shoal.core.mcp_stacks import available_mcp_servers, load_mcp_stacks
    from shoal.dashboard.context import mcp_matrix_context

    sessions = await list_sessions()
    servers = available_mcp_servers()
    stacks = load_mcp_stacks()
    stack_list: list[dict[str, object]] = [
        {"name": s.name, "description": s.description, "servers": s.servers, "source": s.source}
        for s in stacks.values()
    ]
    return mcp_matrix_context(sessions, servers, stack_list)


async def _mcp_render(request: Request, template: str) -> HTMLResponse:
    """Build context and render an MCP template."""
    ctx = await _mcp_context()
    return _get_templates().TemplateResponse(request, template, {**ctx, "request": request})


@router.get("/mcp-matrix", response_class=HTMLResponse)
async def mcp_matrix(request: Request) -> HTMLResponse:
    """Render the MCP server-session matrix page."""
    return await _mcp_render(request, "mcp_matrix.html")


@router.get("/partials/mcp-grid", response_class=HTMLResponse, response_model=None)
async def mcp_grid_partial(
    request: Request,
    format: str | None = None,
) -> HTMLResponse | JSONResponse:
    """Return the MCP grid fragment for HTMX swaps.

    Args:
        request: The incoming request.
        format: If "json", return structured JSON instead of HTML fragment.
    """
    if format == "json":
        ctx = await _mcp_context()
        return JSONResponse(content=ctx)

    return await _mcp_render(request, "partials/mcp_grid.html")


@router.post("/mcp-toggle", response_class=HTMLResponse)
async def mcp_toggle(request: Request) -> HTMLResponse:
    """Toggle a single MCP server assignment for a session.

    Reads form data: session_id, mcp_name, action ("add" or "remove").
    Returns the updated MCP grid partial.
    """
    from shoal.core.state import add_mcp_to_session, remove_mcp_from_session
    from shoal.services.mcp_configure import configure_omp_mcp, remove_omp_mcp

    form = await request.form()
    session_id = str(form.get("session_id", ""))
    mcp_name = str(form.get("mcp_name", ""))
    action = str(form.get("action", ""))

    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if action == "add":
        await add_mcp_to_session(session_id, mcp_name)
        # Also configure OMP to use this server
        try:
            configure_omp_mcp(mcp_name)
        except Exception as exc:
            logger.warning("Failed to configure OMP for %s: %s", mcp_name, exc)
    elif action == "remove":
        await remove_mcp_from_session(session_id, mcp_name)
        # Also remove from OMP config
        try:
            remove_omp_mcp(mcp_name)
        except Exception as exc:
            logger.warning("Failed to remove %s from OMP: %s", mcp_name, exc)

    return await _mcp_render(request, "partials/mcp_grid.html")


@router.post("/mcp-apply-stack", response_class=HTMLResponse)
async def mcp_apply_stack(request: Request) -> HTMLResponse:
    """Apply or remove an MCP stack for a session.

    Reads form data: session_id, stack_name, action ("apply" or "remove").
    Returns the updated MCP grid partial.
    """
    from shoal.core.mcp_stacks import load_mcp_stacks
    from shoal.core.state import add_mcp_to_session, remove_mcp_from_session

    form = await request.form()
    session_id = str(form.get("session_id", ""))
    stack_name = str(form.get("stack_name", ""))
    action = str(form.get("action", ""))

    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    stacks = load_mcp_stacks()
    if stack_name not in stacks:
        raise HTTPException(status_code=404, detail="Stack not found")

    stack = stacks[stack_name]
    for server in stack.servers:
        if action == "apply":
            await add_mcp_to_session(session_id, server)
        elif action == "remove":
            await remove_mcp_from_session(session_id, server)

    return await _mcp_render(request, "partials/mcp_grid.html")


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    """Dashboard WebSocket: receives live HTML partial pushes."""
    await dashboard_ws_endpoint(websocket)
