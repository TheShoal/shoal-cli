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
from typing import TYPE_CHECKING, Any, cast

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import ValidationError

import shoal
from shoal.models.batch import (
    AppendJournalBatchOp,
    BatchExecutionRequest,
    BatchExecutionResponse,
    BatchItemResult,
    BatchOperation,
    CapturePaneBatchOp,
    KillSessionBatchOp,
    ReadHistoryBatchOp,
    ReadJournalBatchOp,
    SendKeysBatchOp,
    SessionInfoBatchOp,
    SessionSnapshotRequest,
    SessionStatusBatchOp,
    SnapshotField,
)
from shoal.services.batch import AUTO_ENTER_TOOLS, execute_batch
from shoal.services.batch import session_snapshot as build_session_snapshot

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
# Helper utilities for batch-backed tools
# ---------------------------------------------------------------------------


def _result_error_message(item: BatchItemResult) -> str:
    if item.error is not None:
        return item.error.message
    return "Batch operation failed"


async def _run_single_op(op: BatchOperation) -> object:
    response = await execute_batch(
        BatchExecutionRequest(ops=[op], continue_on_error=False, max_parallelism=1)
    )
    item = response.results[0]
    if not item.success:
        raise ToolError(_result_error_message(item))
    return item.result


def _legacy_multi_result(
    session_refs: list[str], response: BatchExecutionResponse
) -> dict[str, object]:
    results: dict[str, object] = {}
    for requested, item in zip(session_refs, response.results, strict=True):
        if item.success:
            results[requested] = item.result if item.result is not None else {}
            continue
        results[requested] = {"error": _result_error_message(item)}
    return {"results": results}


# ---------------------------------------------------------------------------
# Tool: session_status
# ---------------------------------------------------------------------------


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
) -> dict[str, object]:
    """Get session status counts or per-session status."""
    if session is None:
        return cast(
            dict[str, object], await _run_single_op(SessionStatusBatchOp(op="session_status"))
        )

    if isinstance(session, list):
        response = await execute_batch(
            BatchExecutionRequest(
                ops=[SessionStatusBatchOp(op="session_status", session=name) for name in session]
            )
        )
        return _legacy_multi_result(session, response)

    return cast(
        dict[str, object],
        await _run_single_op(SessionStatusBatchOp(op="session_status", session=session)),
    )


# ---------------------------------------------------------------------------
# Tool: session_info
# ---------------------------------------------------------------------------


@mcp.tool(
    name="session_info",
    description="Get detailed information about a specific session by name or ID.",
    annotations={"readOnlyHint": True},
)
async def session_info_tool(session: str) -> dict[str, object]:
    """Get full details for a session."""
    return cast(
        dict[str, object],
        await _run_single_op(SessionInfoBatchOp(op="session_info", session=session)),
    )


# ---------------------------------------------------------------------------
# Tool: send_keys
# ---------------------------------------------------------------------------


# CLI-based tools where Enter is auto-appended after send_keys by default.
# TUI-based tools (e.g. opencode) handle input natively and may not need
# auto-Enter — callers can override with the explicit enter parameter.
_AUTO_ENTER_TOOLS: frozenset[str] = AUTO_ENTER_TOOLS


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
) -> dict[str, object]:
    """Send keys to a session."""
    if isinstance(session, list):
        response = await execute_batch(
            BatchExecutionRequest(
                ops=[
                    SendKeysBatchOp(op="send_keys", session=name, keys=keys, enter=enter)
                    for name in session
                ]
            )
        )
        return _legacy_multi_result(session, response)

    return cast(
        dict[str, object],
        await _run_single_op(
            SendKeysBatchOp(op="send_keys", session=session, keys=keys, enter=enter)
        ),
    )


# ---------------------------------------------------------------------------
# Tool: capture_pane
# ---------------------------------------------------------------------------


@mcp.tool(
    name="capture_pane",
    description="Read last N lines from a session's terminal output.",
    annotations={"readOnlyHint": True},
)
async def capture_pane_tool(session: str | list[str], lines: int = 20) -> dict[str, object]:
    """Capture recent terminal output from a session's pane."""
    if isinstance(session, list):
        response = await execute_batch(
            BatchExecutionRequest(
                ops=[
                    CapturePaneBatchOp(op="capture_pane", session=name, lines=lines)
                    for name in session
                ]
            )
        )
        return _legacy_multi_result(session, response)

    return cast(
        dict[str, object],
        await _run_single_op(CapturePaneBatchOp(op="capture_pane", session=session, lines=lines)),
    )


# ---------------------------------------------------------------------------
# Tool: read_history
# ---------------------------------------------------------------------------


@mcp.tool(
    name="read_history",
    description="Get status transition history for a session.",
    annotations={"readOnlyHint": True},
)
async def read_history_tool(session: str, limit: int = 50) -> list[dict[str, object]]:
    """Read status transition history for a session."""
    return cast(
        list[dict[str, object]],
        await _run_single_op(ReadHistoryBatchOp(op="read_history", session=session, limit=limit)),
    )


# ---------------------------------------------------------------------------
# Tool: session_snapshot
# ---------------------------------------------------------------------------


@mcp.tool(
    name="session_snapshot",
    description=(
        "Capture selected fields across multiple sessions in one read-optimized call. "
        "Use this for supervisor-style inspection."
    ),
    annotations={"readOnlyHint": True},
)
async def session_snapshot_tool(
    sessions: list[str],
    fields: list[SnapshotField] | None = None,
    pane_lines: int = 20,
    max_parallelism: int = 8,
) -> dict[str, object]:
    """Capture a read-optimized snapshot for multiple sessions."""
    request_data: dict[str, object] = {
        "sessions": sessions,
        "pane_lines": pane_lines,
        "max_parallelism": max_parallelism,
    }
    if fields is not None:
        request_data["fields"] = fields

    try:
        request = SessionSnapshotRequest.model_validate(request_data)
    except ValidationError as exc:
        raise ToolError(str(exc)) from exc

    response = await build_session_snapshot(request)
    return cast(dict[str, object], response.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Tool: batch_execute
# ---------------------------------------------------------------------------


@mcp.tool(
    name="batch_execute",
    description="Execute mixed Shoal session operations in one application-level batch.",
    annotations={"destructiveHint": True},
)
async def batch_execute_tool(
    ops: list[dict[str, object]],
    continue_on_error: bool = True,
    max_parallelism: int = 8,
) -> dict[str, object]:
    """Execute a heterogeneous batch of Shoal session operations."""
    try:
        request = BatchExecutionRequest.model_validate(
            {
                "ops": ops,
                "continue_on_error": continue_on_error,
                "max_parallelism": max_parallelism,
            }
        )
    except ValidationError as exc:
        raise ToolError(str(exc)) from exc

    response = await execute_batch(request)
    return cast(dict[str, object], response.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Prompt delivery helper
# ---------------------------------------------------------------------------

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

        await tmux.async_wait_for_ready(
            await tmux.async_first_pane(session.tmux_session), tool_cfg, timeout=5.0
        )
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


@mcp.tool(
    name="kill_session",
    description="Kill a session and optionally remove its git worktree.",
    annotations={"destructiveHint": True},
)
async def kill_session_tool(
    session: str | list[str],
    remove_worktree: bool = False,
    force: bool = False,
) -> dict[str, object]:
    """Kill a session."""
    if isinstance(session, list):
        response = await execute_batch(
            BatchExecutionRequest(
                ops=[
                    KillSessionBatchOp(
                        op="kill_session",
                        session=name,
                        remove_worktree=remove_worktree,
                        force=force,
                    )
                    for name in session
                ]
            )
        )
        return _legacy_multi_result(session, response)

    return cast(
        dict[str, object],
        await _run_single_op(
            KillSessionBatchOp(
                op="kill_session",
                session=session,
                remove_worktree=remove_worktree,
                force=force,
            )
        ),
    )


# ---------------------------------------------------------------------------
# Tool: append_journal
# ---------------------------------------------------------------------------


@mcp.tool(
    name="append_journal",
    description="Append an entry to a session's journal.",
    annotations={"destructiveHint": True},
)
async def append_journal_tool(session: str, entry: str, source: str = "mcp") -> dict[str, object]:
    """Append a journal entry for a session."""
    return cast(
        dict[str, object],
        await _run_single_op(
            AppendJournalBatchOp(
                op="append_journal",
                session=session,
                entry=entry,
                source=source,
            )
        ),
    )


# ---------------------------------------------------------------------------
# Tool: read_journal
# ---------------------------------------------------------------------------


@mcp.tool(
    name="read_journal",
    description="Read journal entries for a session.",
    annotations={"readOnlyHint": True},
)
async def read_journal_tool(session: str, limit: int = 10) -> list[dict[str, object]]:
    """Read recent journal entries for a session."""
    return cast(
        list[dict[str, object]],
        await _run_single_op(ReadJournalBatchOp(op="read_journal", session=session, limit=limit)),
    )



# ---------------------------------------------------------------------------
# Tool: wait_for_completion
# ---------------------------------------------------------------------------


@mcp.tool(
    name="wait_for_completion",
    description="Poll until a session emits session_completed or timeout elapses.",
)
async def wait_for_completion_tool(
    session: str,
    timeout_seconds: int = 300,
) -> dict[str, object]:
    """Poll until session is marked complete or timeout elapses."""
    import asyncio
    import time

    from shoal.core.state import find_by_name, get_session

    session_id = await find_by_name(session)
    if session_id is None:
        raise ToolError(f"Session not found: {session}")

    state = await get_session(session_id)
    if state is None:
        raise ToolError(f"Session not found: {session}")

    if state.completed_at is not None:
        return {
            "completed": True,
            "completed_at": state.completed_at.isoformat(),
            "waited_seconds": 0,
        }

    if timeout_seconds <= 0:
        return {"completed": False, "waited_seconds": 0}

    start = time.monotonic()
    elapsed = 0
    while elapsed < timeout_seconds:
        await asyncio.sleep(5)
        elapsed = int(time.monotonic() - start)

        state = await get_session(session_id)
        if state is not None and state.completed_at is not None:
            return {
                "completed": True,
                "completed_at": state.completed_at.isoformat(),
                "waited_seconds": elapsed,
            }

    return {"completed": False, "waited_seconds": timeout_seconds}


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
