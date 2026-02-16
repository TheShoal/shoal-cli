# SPDX-License-Identifier: LicenseRef-USMobile-Proprietary
"""Session state CRUD — all state stored in SQLite."""

from __future__ import annotations

import asyncio
import secrets
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shoal.core.config import ensure_dirs, load_tool_config, state_dir
from shoal.core.db import get_db
from shoal.models.state import SessionState, SessionStatus


def generate_id(length: int = 8) -> str:
    """Generate a short unique session ID from [a-z0-9]."""
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _sanitize_tmux_name(name: str) -> str:
    """Sanitize a name for use in a tmux session name.

    Tmux does not allow '.' or ':' in session names.
    """
    return name.replace(".", "-").replace(":", "-").replace("/", "-")


async def create_session(
    name: str,
    tool: str,
    git_root: str,
    worktree: str = "",
    branch: str = "",
) -> SessionState:
    """Create a new session state in DB and return the session."""
    session_id = generate_id()
    tmux_session = f"shoal_{_sanitize_tmux_name(name)}"
    now = datetime.now(UTC)

    session = SessionState(
        id=session_id,
        name=name,
        tool=tool,
        path=git_root,
        worktree=worktree,
        branch=branch,
        tmux_session=tmux_session,
        tmux_window="0",
        nvim_socket=f"/tmp/nvim-{tmux_session}-0.sock",
        status=SessionStatus.idle,
        pid=None,
        mcp_servers=[],
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


async def update_session(session_id: str, **fields: Any) -> SessionState | None:
    """Update specific fields on a session in DB."""
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


async def resolve_session(name_or_id: str) -> str | None:
    """Resolve a name or ID to a session ID. Returns None if not found."""
    # Try as direct ID first
    session = await get_session(name_or_id)
    if session:
        return name_or_id
    # Try by name
    return await find_by_name(name_or_id)


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
        result = subprocess.run(
            ["fzf", "--header=ID\tNAME\tTOOL\tSTATUS", "--delimiter=\t"],
            input="\n".join(lines),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise SystemExit(1)
        return result.stdout.strip().split("\t")[0]
    except FileNotFoundError:
        print("fzf not found — provide a session name or ID", file=sys.stderr)
        raise SystemExit(1) from None


def _get_tool_icon(tool: str) -> str:
    """Get tool icon, falling back to ● if config not found."""
    try:
        cfg = load_tool_config(tool)
        return cfg.icon
    except FileNotFoundError:
        return "●"
