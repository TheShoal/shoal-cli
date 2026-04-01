# SPDX-License-Identifier: MIT
"""Session state CRUD — all state stored in SQLite."""

from __future__ import annotations

import asyncio
import os
import secrets
import subprocess
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from shoal.core.config import load_tool_config
from shoal.core.db import get_db
from shoal.core.session_names import (
    build_tmux_session_name,
    validate_session_name,
)
from shoal.core.theme import Symbols
from shoal.models.state import SessionState, SessionStatus, TmuxRuntimeState


def generate_id(length: int = 8) -> str:
    """Generate a short unique session ID from [a-z0-9]."""
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def build_nvim_socket_path(tmux_session_id: str, tmux_window_id: str) -> str:
    """Build Neovim socket path from tmux IDs.

    Uses ``XDG_RUNTIME_DIR`` if set, falling back to ``/tmp``.
    """
    base = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return f"{base}/nvim-{tmux_session_id}-{tmux_window_id}.sock"


async def resolve_nvim_socket(session: SessionState) -> str | None:
    """Resolve and persist a session's Neovim socket from current tmux IDs."""
    from shoal.core import tmux

    runtime = session.tmux_runtime
    if not tmux.has_session(runtime.session_name):
        return None

    pane_target = tmux.preferred_pane(runtime.session_name, f"shoal:{session.id}")
    coordinates = tmux.pane_coordinates(pane_target)
    if not coordinates:
        return None

    tmux_session_id, tmux_window_id = coordinates
    socket = build_nvim_socket_path(tmux_session_id, tmux_window_id)

    updated_runtime = runtime
    if runtime.session_id != tmux_session_id:
        updated_runtime = updated_runtime.model_copy(update={"session_id": tmux_session_id})
    if updated_runtime.window_id != tmux_window_id:
        updated_runtime = updated_runtime.model_copy(update={"window_id": tmux_window_id})
    if updated_runtime.nvim_socket != socket:
        updated_runtime = updated_runtime.model_copy(update={"nvim_socket": socket})

    if updated_runtime != runtime:
        await update_session(session.id, runtime=updated_runtime)

    return socket


async def create_session(
    name: str,
    tool: str,
    git_root: str,
    worktree: str = "",
    branch: str = "",
    parent_id: str = "",
    tags: list[str] | None = None,
    template_name: str = "",
) -> SessionState:
    """Create a new session state in DB and return the session.

    Raises:
        ValueError: If session name validation fails or tmux name collision detected.
    """
    from shoal.core import tmux

    validate_session_name(name)
    session_id = generate_id()
    tmux_session = build_tmux_session_name(name)

    # Check for tmux name collision from lossy sanitization
    if tmux.has_session(tmux_session):
        raise ValueError(
            f"Tmux session '{tmux_session}' already exists. "
            f"Session name '{name}' collides with an existing session after sanitization "
            f"(characters '.', ':', '/' are replaced with '-'). Choose a different name."
        )
    now = datetime.now(UTC)

    session = SessionState(
        id=session_id,
        name=name,
        tool=tool,
        path=git_root,
        worktree=worktree,
        branch=branch,
        runtime=TmuxRuntimeState(session_name=tmux_session),
        status=SessionStatus.idle,
        pid=None,
        mcp_servers=[],
        parent_id=parent_id,
        tags=tags or [],
        template_name=template_name,
        created_at=now,
        last_activity=now,
    )

    db = await get_db()
    await db.save_session(session)
    return session


async def get_session(session_id: str) -> SessionState | None:
    """Read a session from DB, or None if not found."""
    db = await get_db()
    return await db.get_session(session_id)


async def get_sessions(session_ids: Iterable[str]) -> dict[str, SessionState]:
    """Read multiple sessions keyed by session ID."""
    ids = list(dict.fromkeys(session_ids))
    if not ids:
        return {}

    db = await get_db()
    return await db.get_sessions(ids)


async def update_session(session_id: str, **fields: Any) -> SessionState | None:
    """Update specific fields on a session in DB.

    Raises:
        ValueError: If name field validation fails.
    """
    # Validate name if it's being updated
    if "name" in fields:
        validate_session_name(fields["name"])

    db = await get_db()
    return await db.update_session(session_id, **fields)


async def delete_session(session_id: str) -> bool:
    """Delete a session from DB."""
    db = await get_db()
    session = await db.get_session(session_id)
    if session:
        await db.delete_session(session_id)
        return True
    return False


async def list_sessions() -> list[SessionState]:
    """Return all sessions."""
    db = await get_db()
    return await db.list_sessions()


async def find_by_name(name: str) -> str | None:
    """Find a session ID by name."""
    db = await get_db()
    session = await db.find_session_by_name(name)
    return session.id if session else None


async def find_sessions_by_names(names: Iterable[str]) -> dict[str, SessionState]:
    """Find multiple sessions keyed by session name."""
    unique_names = list(dict.fromkeys(names))
    if not unique_names:
        return {}

    db = await get_db()
    return await db.find_sessions_by_names(unique_names)


async def touch_session(session_id: str) -> None:
    """Update last_activity timestamp."""
    await update_session(session_id, last_activity=datetime.now(UTC))


async def add_mcp_to_session(session_id: str, mcp_name: str) -> None:
    """Add an MCP server to a session's list."""
    session = await get_session(session_id)
    if session is None:
        return
    servers = list(set(session.mcp_servers) | {mcp_name})
    await update_session(session_id, mcp_servers=servers)


async def remove_mcp_from_session(session_id: str, mcp_name: str) -> None:
    """Remove an MCP server from a session's list."""
    session = await get_session(session_id)
    if session is None:
        return
    servers = [s for s in session.mcp_servers if s != mcp_name]
    await update_session(session_id, mcp_servers=servers)


async def add_tag(session_id: str, tag: str) -> None:
    """Add a tag to a session (no-op if already present)."""
    session = await get_session(session_id)
    if session is None:
        return
    if tag not in session.tags:
        await update_session(session_id, tags=[*session.tags, tag])


async def remove_tag(session_id: str, tag: str) -> None:
    """Remove a tag from a session (no-op if not present)."""
    session = await get_session(session_id)
    if session is None:
        return
    if tag in session.tags:
        await update_session(session_id, tags=[t for t in session.tags if t != tag])


async def resolve_session(name_or_id: str) -> str | None:
    """Resolve a name or ID to a session ID. Returns None if not found."""
    # Try as direct ID first
    session = await get_session(name_or_id)
    if session:
        return name_or_id
    # Try by name
    return await find_by_name(name_or_id)


async def resolve_sessions(names_or_ids: Iterable[str]) -> dict[str, str | None]:
    """Resolve many session names or IDs while preserving single-item semantics."""
    refs = list(dict.fromkeys(names_or_ids))
    if not refs:
        return {}

    direct_matches = await get_sessions(refs)
    resolved: dict[str, str | None] = {ref: ref for ref in refs if ref in direct_matches}
    unresolved = [ref for ref in refs if ref not in resolved]
    if not unresolved:
        return resolved

    name_matches = await find_sessions_by_names(unresolved)
    for ref in unresolved:
        session = name_matches.get(ref)
        resolved[ref] = session.id if session else None
    return resolved


async def load_sessions(names_or_ids: Iterable[str]) -> dict[str, SessionState | None]:
    """Load many sessions keyed by the original reference string."""
    refs = list(dict.fromkeys(names_or_ids))
    if not refs:
        return {}

    resolved = await resolve_sessions(refs)
    sessions_by_id = await get_sessions(
        session_id for session_id in resolved.values() if session_id
    )
    return {
        ref: sessions_by_id.get(session_id) if session_id else None
        for ref, session_id in resolved.items()
    }


def resolve_session_interactive(name_or_id: str | None = None) -> str:
    """Resolve session with fzf fallback. Raises SystemExit on failure."""
    from shoal.core.db import with_db

    return asyncio.run(with_db(_resolve_session_interactive_impl(name_or_id)))


async def _resolve_session_interactive_impl(name_or_id: str | None = None) -> str:
    if name_or_id:
        result = await resolve_session(name_or_id)
        if result:
            return result
        print(f"Session not found: {name_or_id}", file=sys.stderr)
        raise SystemExit(1)

    # No argument — use fzf picker
    sessions = await list_sessions()
    if not sessions:
        print("No sessions found", file=sys.stderr)
        raise SystemExit(1)

    lines: list[str] = []
    for session in sessions:
        icon = _get_tool_icon(session.tool)
        lines.append(f"{session.id}\t{icon} {session.name}\t{session.tool}\t{session.status.value}")

    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            ["fzf", "--header=ID\tNAME\tTOOL\tSTATUS", "--delimiter=\t"],
            input="\n".join(lines),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            raise SystemExit(1)
        return proc.stdout.strip().split("\t")[0]
    except FileNotFoundError:
        print("fzf not found — provide a session name or ID", file=sys.stderr)
        raise SystemExit(1) from None


def _get_tool_icon(tool: str) -> str:
    """Get tool icon, falling back to bullet if config not found."""
    try:
        cfg = load_tool_config(tool)
        return cfg.icon
    except FileNotFoundError:
        return Symbols.BULLET_FILLED
