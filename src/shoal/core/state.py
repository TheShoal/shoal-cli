"""Session state CRUD — all state stored as JSON in ~/.local/share/shoal/sessions/."""

from __future__ import annotations

import secrets
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from shoal.core.config import ensure_dirs, load_tool_config, state_dir
from shoal.models.state import SessionState, SessionStatus


def generate_id(length: int = 8) -> str:
    """Generate a short unique session ID from [a-z0-9]."""
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def session_file(session_id: str) -> Path:
    """Return path to session JSON file."""
    return state_dir() / "sessions" / f"{session_id}.json"


def create_session(
    name: str,
    tool: str,
    git_root: str,
    worktree: str = "",
    branch: str = "",
) -> SessionState:
    """Create a new session state file and return the session."""
    ensure_dirs()
    session_id = generate_id()
    tmux_session = f"shoal_{session_id}"
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

    path = session_file(session_id)
    path.write_text(session.model_dump_json(indent=2))
    return session


def get_session(session_id: str) -> SessionState | None:
    """Read a session from disk, or None if not found."""
    path = session_file(session_id)
    if not path.exists():
        return None
    return SessionState.model_validate_json(path.read_text())


def update_session(session_id: str, **fields: object) -> SessionState | None:
    """Update specific fields on a session and write back to disk."""
    session = get_session(session_id)
    if session is None:
        return None
    updated = session.model_copy(update=fields)
    session_file(session_id).write_text(updated.model_dump_json(indent=2))
    return updated


def delete_session(session_id: str) -> bool:
    """Delete a session state file."""
    path = session_file(session_id)
    if path.exists():
        path.unlink()
        return True
    return False


def list_sessions() -> list[str]:
    """Return all session IDs."""
    sessions_dir = state_dir() / "sessions"
    if not sessions_dir.exists():
        return []
    return sorted(p.stem for p in sessions_dir.glob("*.json"))


def find_by_name(name: str) -> str | None:
    """Find a session ID by name."""
    for session_id in list_sessions():
        session = get_session(session_id)
        if session and session.name == name:
            return session_id
    return None


def touch_session(session_id: str) -> None:
    """Update last_activity timestamp."""
    update_session(session_id, last_activity=datetime.now(UTC))


def add_mcp_to_session(session_id: str, mcp_name: str) -> None:
    """Add an MCP server to a session's list."""
    session = get_session(session_id)
    if session is None:
        return
    servers = list(set(session.mcp_servers) | {mcp_name})
    update_session(session_id, mcp_servers=servers)


def remove_mcp_from_session(session_id: str, mcp_name: str) -> None:
    """Remove an MCP server from a session's list."""
    session = get_session(session_id)
    if session is None:
        return
    servers = [s for s in session.mcp_servers if s != mcp_name]
    update_session(session_id, mcp_servers=servers)


def resolve_session(name_or_id: str) -> str | None:
    """Resolve a name or ID to a session ID. Returns None if not found."""
    # Try as direct ID first
    if session_file(name_or_id).exists():
        return name_or_id
    # Try by name
    return find_by_name(name_or_id)


def resolve_session_interactive(name_or_id: str | None = None) -> str:
    """Resolve session with fzf fallback. Raises SystemExit on failure."""
    if name_or_id:
        result = resolve_session(name_or_id)
        if result:
            return result
        print(f"Session not found: {name_or_id}", file=sys.stderr)
        raise SystemExit(1)

    # No argument — use fzf picker
    sessions = list_sessions()
    if not sessions:
        print("No sessions found", file=sys.stderr)
        raise SystemExit(1)

    lines: list[str] = []
    for sid in sessions:
        session = get_session(sid)
        if session:
            icon = _get_tool_icon(session.tool)
            lines.append(f"{sid}\t{icon} {session.name}\t{session.tool}\t{session.status.value}")

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
