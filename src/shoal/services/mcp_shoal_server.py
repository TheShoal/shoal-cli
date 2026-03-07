"""Shoal MCP server — exposes session orchestration as MCP tools.

Runs as a stdio process, spawned per connection by the MCP pool.
AI agents (especially robo supervisors) use these tools to manage
sessions natively via the MCP protocol.

Requires the ``mcp`` optional dependency: ``pip install shoal[mcp]``
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

import shoal

if TYPE_CHECKING:
    from shoal.models.config import ToolConfig

logger = logging.getLogger("shoal.mcp_server")


# ---------------------------------------------------------------------------
# Lifespan: DB init / cleanup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(server: Any) -> AsyncIterator[dict[str, Any]]:
    """Initialize DB on startup, clean up on shutdown."""
    from shoal.core.config import ensure_dirs
    from shoal.core.db import ShoalDB, get_db

    ensure_dirs()
    await get_db()
    yield {}
    await ShoalDB.reset_instance()


# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="shoal-orchestrator",
    instructions=(
        "Shoal session orchestration tools. Use these to manage parallel "
        "AI coding agent sessions: list, create, kill, send keys, and "
        "check status. Sessions are identified by name."
    ),
    version=shoal.__version__,
    lifespan=_lifespan,
)


# ---------------------------------------------------------------------------
# Tool: list_sessions
# ---------------------------------------------------------------------------


@mcp.tool(
    name="list_sessions",
    description="List all Shoal sessions with their current status.",
    annotations={"readOnlyHint": True},
)
async def list_sessions_tool() -> list[dict[str, Any]]:
    """List all active Shoal sessions."""
    from shoal.core.state import list_sessions

    sessions = await list_sessions()
    return [
        {
            "id": s.id,
            "name": s.name,
            "tool": s.tool,
            "status": s.status.value,
            "path": s.path,
            "branch": s.branch,
            "worktree": s.worktree,
            "mcp_servers": s.mcp_servers,
        }
        for s in sessions
    ]


# ---------------------------------------------------------------------------
# Tool: session_status
# ---------------------------------------------------------------------------


async def _session_status_single(session: str) -> dict[str, Any]:
    from shoal.core.state import get_session, resolve_session

    session_id = await resolve_session(session)
    if not session_id:
        raise ToolError(f"Session not found: {session}")

    s = await get_session(session_id)
    if not s:
        raise ToolError(f"Session not found: {session}")

    return {"name": s.name, "status": s.status.value}


@mcp.tool(
    name="session_status",
    description=(
        "Get aggregate status counts across all sessions, or the status of "
        "specific sessions by name."
    ),
    annotations={"readOnlyHint": True},
)
async def session_status_tool(
    session: str | list[str] | None = None,
) -> dict[str, Any]:
    """Get session status counts or per-session status.

    Args:
        session: Optional session name, ID, or list thereof. When omitted,
                 returns aggregate counts across all sessions. When provided,
                 returns status for the specified session(s).
    """
    from shoal.core.state import list_sessions

    if session is None:
        sessions = await list_sessions()
        counts: dict[str, Any] = {
            "total": len(sessions),
            "running": 0,
            "waiting": 0,
            "error": 0,
            "idle": 0,
            "stopped": 0,
            "unknown": 0,
        }
        for s in sessions:
            key = s.status.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    if isinstance(session, list):
        results: dict[str, Any] = {}
        for name in session:
            try:
                results[name] = await _session_status_single(name)
            except ToolError as e:
                results[name] = {"error": str(e)}
        return {"results": results}

    return await _session_status_single(session)


# ---------------------------------------------------------------------------
# Tool: session_info
# ---------------------------------------------------------------------------


@mcp.tool(
    name="session_info",
    description="Get detailed information about a specific session by name or ID.",
    annotations={"readOnlyHint": True},
)
async def session_info_tool(session: str) -> dict[str, Any]:
    """Get full details for a session.

    Args:
        session: Session name or ID to look up.
    """
    from shoal.core.state import get_session, resolve_session

    session_id = await resolve_session(session)
    if not session_id:
        raise ToolError(f"Session not found: {session}")

    s = await get_session(session_id)
    if not s:
        raise ToolError(f"Session not found: {session}")

    return {
        "id": s.id,
        "name": s.name,
        "tool": s.tool,
        "status": s.status.value,
        "path": s.path,
        "branch": s.branch,
        "worktree": s.worktree,
        "tmux_session": s.tmux_session,
        "pid": s.pid,
        "mcp_servers": s.mcp_servers,
        "created_at": s.created_at.isoformat(),
        "last_activity": s.last_activity.isoformat(),
    }


# ---------------------------------------------------------------------------
# Tool: send_keys
# ---------------------------------------------------------------------------

# CLI-based tools where Enter is auto-appended after send_keys by default.
# TUI-based tools (e.g. opencode) handle input natively and may not need
# auto-Enter — callers can override with the explicit enter parameter.
_AUTO_ENTER_TOOLS: frozenset[str] = frozenset({"claude", "codex", "gemini", "pi"})


async def _send_keys_single(
    session: str, keys: str, enter: bool | None
) -> dict[str, str]:
    import asyncio

    from shoal.core import tmux
    from shoal.core.config import load_tool_config
    from shoal.core.state import get_session, resolve_session

    session_id = await resolve_session(session)
    if not session_id:
        raise ToolError(f"Session not found: {session}")

    s = await get_session(session_id)
    if not s:
        raise ToolError(f"Session not found: {session}")

    auto_enter = enter if enter is not None else s.tool in _AUTO_ENTER_TOOLS

    # Load send_keys_delay from the tool's config profile (default 0.0)
    try:
        tool_cfg = await asyncio.to_thread(load_tool_config, s.tool)
        delay = tool_cfg.send_keys_delay
    except FileNotFoundError:
        delay = 0.0

    # Use preferred_pane to target the titled pane (shoal:<id>), not just the
    # active pane in the session.  Without this, keys land in whatever pane
    # happens to be active, which may not be the tool pane.
    pane_target = await tmux.async_preferred_pane(s.tmux_session, f"shoal:{s.id}")
    await tmux.async_send_keys(pane_target, keys, enter=auto_enter, delay=delay)
    return {"message": f"Keys sent to session '{s.name}'"}


@mcp.tool(
    name="send_keys",
    description=(
        "Send keystrokes to a session's tmux pane. Use this to interact with agents. "
        "Whether Enter is pressed depends on the session's tool profile — "
        "override with the enter parameter if needed."
    ),
    annotations={"destructiveHint": True},
)
async def send_keys_tool(
    session: str | list[str], keys: str, enter: bool | None = None
) -> dict[str, Any]:
    """Send keys to a session.

    Args:
        session: Session name, ID, or list thereof.
        keys: The keystrokes to send (e.g., 'y' or 'ls -la').
        enter: Whether to press Enter after keys. Auto-detected from tool
               profile if not specified (True for claude/codex/gemini/pi).
    """
    if isinstance(session, list):
        results: dict[str, Any] = {}
        for name in session:
            try:
                results[name] = await _send_keys_single(name, keys, enter)
            except ToolError as e:
                results[name] = {"error": str(e)}
        return {"results": results}

    return await _send_keys_single(session, keys, enter)


# ---------------------------------------------------------------------------
# Tool: capture_pane
# ---------------------------------------------------------------------------


async def _capture_pane_single(session: str, lines: int) -> dict[str, str]:
    from shoal.core import tmux
    from shoal.core.state import get_session, resolve_session

    session_id = await resolve_session(session)
    if not session_id:
        raise ToolError(f"Session not found: {session}")

    s = await get_session(session_id)
    if not s:
        raise ToolError(f"Session not found: {session}")

    pane_target = await tmux.async_preferred_pane(s.tmux_session, f"shoal:{s.id}")
    content = await tmux.async_capture_pane(pane_target, lines)
    return {"content": content}


@mcp.tool(
    name="capture_pane",
    description="Read last N lines from a session's terminal output.",
    annotations={"readOnlyHint": True},
)
async def capture_pane_tool(
    session: str | list[str], lines: int = 20
) -> dict[str, Any]:
    """Capture recent terminal output from a session's pane.

    Args:
        session: Session name, ID, or list thereof.
        lines: Number of lines to capture (default: 20).
    """
    if isinstance(session, list):
        results: dict[str, Any] = {}
        for name in session:
            try:
                results[name] = await _capture_pane_single(name, lines)
            except ToolError as e:
                results[name] = {"error": str(e)}
        return {"results": results}

    return await _capture_pane_single(session, lines)


# ---------------------------------------------------------------------------
# Tool: read_history
# ---------------------------------------------------------------------------


@mcp.tool(
    name="read_history",
    description="Get status transition history for a session.",
    annotations={"readOnlyHint": True},
)
async def read_history_tool(session: str, limit: int = 50) -> list[dict[str, Any]]:
    """Read status transition history for a session.

    Args:
        session: Session name or ID.
        limit: Maximum number of transitions to return (default: 50).
    """
    from shoal.core.db import get_db
    from shoal.core.state import resolve_session

    session_id = await resolve_session(session)
    if not session_id:
        raise ToolError(f"Session not found: {session}")

    db = await get_db()
    return await db.get_status_transitions(session_id, limit=limit)


# ---------------------------------------------------------------------------
# Prompt delivery helper
# ---------------------------------------------------------------------------


def _tool_command_for_session(
    tool_cfg: ToolConfig,
    prompt: str | None,
    session_id: str,
) -> str:
    """Return the tool launch command, with prompt baked in for native modes.

    For ``input_mode = "keys"`` (or when there is no prompt) the plain base
    command is returned unchanged so the existing post-launch ``send_keys``
    path fires as before.
    """
    if not prompt or tool_cfg.input_mode == "keys":
        return tool_cfg.command

    from shoal.core.prompt_delivery import build_tool_command_with_prompt

    return build_tool_command_with_prompt(tool_cfg, prompt, session_id)


# ---------------------------------------------------------------------------
# Tool: create_session
# ---------------------------------------------------------------------------


@mcp.tool(
    name="create_session",
    description=(
        "Create a new Shoal session. Optionally create a git worktree for branch isolation."
    ),
    annotations={"destructiveHint": True},
)
async def create_session_tool(
    name: str,
    path: str = ".",
    tool: str | None = None,
    worktree: str | None = None,
    branch: bool = False,
    template: str | None = None,
    mcp_servers: list[str] | None = None,
    prompt: str | None = None,
) -> dict[str, Any]:
    """Create a new agent session.

    Args:
        name: Session name (required).
        path: Project directory (defaults to current directory).
        tool: AI tool to use (opencode, claude, codex, gemini, pi). Defaults to config.
        worktree: Create a git worktree with this name.
        branch: Create a new branch for the worktree.
        template: Session template name to apply.
        mcp_servers: MCP servers to provision (e.g. ["memory", "github"]).
        prompt: Initial prompt to send to the agent after startup. Enter is pressed automatically.
    """
    from shoal.core import git
    from shoal.core.config import ensure_dirs, load_config, load_template, load_tool_config
    from shoal.core.state import find_by_name
    from shoal.services.lifecycle import (
        SessionExistsError,
        StartupCommandError,
        TmuxSetupError,
        create_session_lifecycle,
    )

    ensure_dirs()
    cfg = load_config()

    # Resolve path
    if not git.is_git_repo(path):
        raise ToolError(f"Not a git repository: {path}")

    # Resolve tool
    resolved_tool = tool or cfg.general.default_tool
    try:
        tool_cfg = load_tool_config(resolved_tool)
    except FileNotFoundError:
        raise ToolError(f"Unknown tool: {resolved_tool}") from None

    # Resolve template
    template_cfg = None
    if template:
        try:
            template_cfg = load_template(template)
        except FileNotFoundError:
            raise ToolError(f"Template not found: {template}") from None
        except ValueError as e:
            raise ToolError(f"Invalid template '{template}': {e}") from None

        if not tool and template_cfg.tool:
            resolved_tool = template_cfg.tool
            tool_cfg = load_tool_config(resolved_tool)

        if template_cfg.mcp:
            merged = set(mcp_servers or []) | set(template_cfg.mcp)
            mcp_servers = sorted(merged)

    root = git.git_root(path)
    work_dir = path
    branch_name = ""
    wt_path = ""

    if worktree:
        wt_dir_name = worktree.replace("/", "-")
        wt_path = f"{root}/.worktrees/{wt_dir_name}"
        Path(root, ".worktrees").mkdir(parents=True, exist_ok=True)
        if branch:
            branch_name = git.infer_branch_name(worktree)
            git.worktree_add(root, wt_path, branch=branch_name)
        else:
            git.worktree_add(root, wt_path)
            branch_name = git.current_branch(wt_path)
        work_dir = wt_path
    else:
        branch_name = git.current_branch(path)

    # Check name collision
    existing = await find_by_name(name)
    if existing:
        raise ToolError(
            f"Session '{name}' already exists. "
            "Use a different name or kill the existing session first."
        )

    try:
        session = await create_session_lifecycle(
            session_name=name,
            tool=resolved_tool,
            git_root=root,
            wt_path=wt_path,
            work_dir=work_dir,
            branch_name=branch_name,
            tool_command=_tool_command_for_session(tool_cfg, prompt, name),
            startup_commands=cfg.tmux.startup_commands,
            template_cfg=template_cfg,
            worktree_name=worktree or "",
            mcp_servers=mcp_servers,
        )
    except SessionExistsError as e:
        raise ToolError(str(e)) from e
    except TmuxSetupError as e:
        raise ToolError(f"Failed to create tmux session: {e}") from e
    except StartupCommandError as e:
        raise ToolError(f"Startup command failed: {e}") from e
    except ValueError as e:
        raise ToolError(f"Invalid session configuration: {e}") from e

    if prompt and tool_cfg.input_mode == "keys":
        from shoal.core import tmux

        await tmux.async_wait_for_ready(f"{session.tmux_session}:0.0", tool_cfg, timeout=5.0)
        await tmux.async_send_keys(session.tmux_session, prompt, delay=tool_cfg.send_keys_delay)

    return {
        "id": session.id,
        "name": session.name,
        "tool": session.tool,
        "status": session.status.value,
        "tmux_session": session.tmux_session,
        "branch": session.branch,
        "worktree": session.worktree,
    }


# ---------------------------------------------------------------------------
# Tool: kill_session
# ---------------------------------------------------------------------------


async def _kill_session_single(
    session: str,
    remove_worktree: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    from shoal.core.state import get_session, resolve_session
    from shoal.services.lifecycle import DirtyWorktreeError, kill_session_lifecycle

    session_id = await resolve_session(session)
    if not session_id:
        raise ToolError(f"Session not found: {session}")

    s = await get_session(session_id)
    if not s:
        raise ToolError(f"Session not found: {session}")

    try:
        summary = await kill_session_lifecycle(
            session_id=s.id,
            tmux_session=s.tmux_session,
            worktree=s.worktree,
            git_root=s.path,
            branch=s.branch,
            remove_worktree=remove_worktree,
            force=force,
        )
    except DirtyWorktreeError as e:
        raise ToolError(
            f"Worktree has uncommitted changes: {s.worktree}. "
            f"Dirty files: {e.dirty_files}. "
            "Use force=True to remove anyway."
        ) from e

    return {
        "session": s.name,
        "tmux_killed": summary["tmux_killed"],
        "worktree_removed": summary["worktree_removed"],
        "branch_deleted": summary["branch_deleted"],
        "db_deleted": summary["db_deleted"],
        "journal_archived": summary["journal_archived"],
    }


@mcp.tool(
    name="kill_session",
    description="Kill a session and optionally remove its git worktree.",
    annotations={"destructiveHint": True},
)
async def kill_session_tool(
    session: str | list[str],
    remove_worktree: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Kill a session.

    Args:
        session: Session name, ID, or list thereof.
        remove_worktree: Also remove the git worktree and branch.
        force: Force removal even if worktree has uncommitted changes.
    """
    if isinstance(session, list):
        results: dict[str, Any] = {}
        for name in session:
            try:
                results[name] = await _kill_session_single(name, remove_worktree, force)
            except ToolError as e:
                results[name] = {"error": str(e)}
        return {"results": results}

    return await _kill_session_single(session, remove_worktree, force)


# ---------------------------------------------------------------------------
# Tool: append_journal
# ---------------------------------------------------------------------------


@mcp.tool(
    name="append_journal",
    description="Append an entry to a session's journal.",
    annotations={"destructiveHint": True},
)
async def append_journal_tool(session: str, entry: str, source: str = "mcp") -> dict[str, str]:
    """Append a journal entry for a session.

    Args:
        session: Session name or ID.
        entry: The markdown content to append.
        source: Tag identifying the source (default: "mcp").
    """
    import asyncio

    from shoal.core.journal import (
        append_entry,
        build_journal_metadata,
        journal_exists,
    )
    from shoal.core.state import get_session, resolve_session

    session_id = await resolve_session(session)
    if not session_id:
        raise ToolError(f"Session not found: {session}")

    metadata = None
    if not await asyncio.to_thread(journal_exists, session_id):
        session_state = await get_session(session_id)
        if session_state:
            metadata = build_journal_metadata(session_state)

    path = await asyncio.to_thread(append_entry, session_id, entry, source, metadata=metadata)
    return {"message": f"Journal entry appended to {path.name}"}


# ---------------------------------------------------------------------------
# Tool: read_journal
# ---------------------------------------------------------------------------


@mcp.tool(
    name="read_journal",
    description="Read journal entries for a session.",
    annotations={"readOnlyHint": True},
)
async def read_journal_tool(session: str, limit: int = 10) -> list[dict[str, str]]:
    """Read recent journal entries for a session.

    Args:
        session: Session name or ID.
        limit: Maximum number of entries to return (default: 10).
    """
    import asyncio

    from shoal.core.journal import read_journal
    from shoal.core.state import resolve_session

    session_id = await resolve_session(session)
    if not session_id:
        raise ToolError(f"Session not found: {session}")

    entries = await asyncio.to_thread(read_journal, session_id, limit)
    return [
        {
            "timestamp": e.timestamp.isoformat(),
            "source": e.source,
            "content": e.content,
        }
        for e in entries
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the Shoal MCP server.

    Supports ``--http [PORT]`` for streamable-http transport (default: stdio).
    HTTP mode is used for benchmarking and remote session support.
    """
    import sys
    from typing import Literal

    mode: Literal["stdio", "streamable-http"] = "stdio"
    port = 8390
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        mode = "streamable-http"
        if len(sys.argv) > 2:
            port = int(sys.argv[2])

    if mode == "streamable-http":
        mcp.run(transport=mode, port=port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
