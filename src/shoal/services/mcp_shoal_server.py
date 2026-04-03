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
from typing import TYPE_CHECKING, Any, Literal, cast

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
from shoal.services import git_tools
from shoal.services.batch import AUTO_ENTER_TOOLS, execute_batch
from shoal.services.batch import session_snapshot as build_session_snapshot
from shoal.services.runtime_provider import provider_for_session, runtime_payload

if TYPE_CHECKING:
    from shoal.models.config import ToolConfig

logger = logging.getLogger("shoal.mcp_server")


# ---------------------------------------------------------------------------
# Lifespan: DB init / cleanup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(server: Any) -> AsyncIterator[dict[str, Any]]:
    """Initialize DB and lifecycle hooks on startup, clean up on shutdown."""
    from shoal.core.config import ensure_dirs
    from shoal.core.db import ShoalDB, get_db
    from shoal.services.lifecycle import register_builtin_hooks

    ensure_dirs()
    await get_db()
    register_builtin_hooks()  # Wire journal, fish, and status-transition hooks
    yield {}
    await ShoalDB.reset_instance()


# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------


def _mcp_instructions() -> str:
    """Build MCP server instructions, prepending SOUL.md if available."""
    from shoal.core.config import soul_text

    base = (
        "Shoal session orchestration tools. Use these to manage parallel "
        "AI coding agent sessions: list, create, kill, send keys, and "
        "check status. Sessions are identified by name."
    )
    soul = soul_text()
    if soul:
        return f"{soul}\n\n---\n\n{base}"
    return base


mcp = FastMCP(
    name="shoal-orchestrator",
    instructions=_mcp_instructions(),
    version=shoal.__version__,
    lifespan=_lifespan,
)


# ---------------------------------------------------------------------------
# Tool: list_sessions
# ---------------------------------------------------------------------------


@mcp.tool(
    name="list_sessions",
    description=(
        "List all Shoal sessions with their current status. "
        "Pass `path` to return only sessions whose git root matches that "
        "directory or whose worktree falls under it."
    ),
    annotations={"readOnlyHint": True},
)
async def list_sessions_tool(path: str | None = None) -> list[dict[str, Any]]:
    """List all active Shoal sessions, optionally filtered to a repo path."""
    from shoal.core.state import filter_sessions_by_path, list_sessions

    sessions = await list_sessions()
    if path is not None:
        sessions = filter_sessions_by_path(sessions, path)
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
    pane_lines: int = 50,
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
        tool: AI tool to use (omp, claude, codex, gemini, pi). Defaults to config.
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

    # Validate worktree/branch co-dependency
    if branch and not worktree:
        raise ToolError("branch=True requires a worktree name. Pass worktree=<name> to create one.")

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
            branch_prefix = template_cfg.git.branch_prefix if template_cfg else ""
            branch_name = git.infer_branch_name(worktree, branch_prefix)
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
        provider = provider_for_session(session)
        await provider.async_wait_for_ready(session, tool_cfg, ready_timeout=5.0)
        await provider.async_send_input(
            session,
            prompt,
            delay=tool_cfg.send_keys_delay,
        )

    return {
        "id": session.id,
        "name": session.name,
        "tool": session.tool,
        "status": session.status.value,
        "runtime": runtime_payload(session.runtime),
        "branch": session.branch,
        "worktree": session.worktree,
    }


# ---------------------------------------------------------------------------
# Tool: kill_session
# ---------------------------------------------------------------------------


@mcp.tool(
    name="kill_session",
    description=(
        "Kill a session and optionally remove its git worktree. "
        "For batch kills, use batch_execute with multiple KillSessionBatchOp entries."
    ),
    annotations={"destructiveHint": True},
)
async def kill_session_tool(
    session: str,
    remove_worktree: bool = False,
    force: bool = False,
) -> dict[str, object]:
    """Kill a session."""
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
# Tool: session_summary
# ---------------------------------------------------------------------------


@mcp.tool(
    name="session_summary",
    description=(
        "Return the latest Dreamer LLM summary for a session. "
        "Dreamer must be enabled and have completed at least one summarization cycle. "
        "Falls back to the most recent journal entry tagged [dreamer] when the "
        "in-process Dreamer singleton is unavailable."
    ),
    annotations={"readOnlyHint": True},
)
async def session_summary_tool(session: str) -> dict[str, object]:
    """Return the latest Dreamer summary for a session."""
    import asyncio

    from shoal.core.journal import read_journal
    from shoal.core.message_bus import receive_messages as _recv_msgs
    from shoal.core.state import find_by_name, get_session
    from shoal.services.dreamer import get_dreamer

    # Resolve session
    session_id = await find_by_name(session)
    if session_id is None:
        raise ToolError(f"Session not found: {session}")
    s = await get_session(session_id)
    if s is None:
        raise ToolError(f"Session not found: {session}")

    # Collect active workflow IDs from unconsumed messages.
    try:
        recent = await _recv_msgs(s.name, limit=100, unconsumed_only=True)
        active_workflow_ids: list[str] = sorted(
            {m["correlation_id"] for m in recent if m.get("correlation_id")}
        )
    except Exception:
        active_workflow_ids = []

    # 1. Try in-process Dreamer singleton (fastest path).
    dreamer = get_dreamer()
    if dreamer is not None:
        summary = dreamer.get_summary(s.id)
        if summary:
            return {
                "session": s.name,
                "summary": summary,
                "source": "dreamer",
                "active_workflow_ids": active_workflow_ids,
            }

    # 2. Try structured QMD artifact index (persisted summaries, fastest cold path).
    try:
        from shoal.core.conversation_index import get_index

        idx = await get_index()
        row = await idx.latest_summary(s.id)
        if row is not None and row.get("summary"):
            return {
                "session": s.name,
                "summary": row["summary"],
                "source": "index",
                "active_workflow_ids": active_workflow_ids,
            }
    except Exception:  # noqa: S110
        pass  # index unavailable; fall through to journal

    # 3. Fall back to the most recent dreamer journal entry.
    entries = await asyncio.to_thread(read_journal, s.id, limit=50)
    for entry in reversed(entries):
        if entry.source == "dreamer":
            return {
                "session": s.name,
                "summary": entry.content,
                "source": "journal",
                "active_workflow_ids": active_workflow_ids,
            }

    return {
        "session": s.name,
        "summary": None,
        "source": None,
        "active_workflow_ids": active_workflow_ids,
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Tool: send_session_message
# ---------------------------------------------------------------------------


@mcp.tool(
    name="send_session_message",
    description=(
        "Post a message from the current session to another session via the Agent Bus. "
        "Supports typed envelopes: kind (event/request/response/handoff/approval_request/"
        "approval_decision/error), correlation_id for workflow tracing, priority (1-5), "
        "and optional metadata. Backward-compatible: omitting new fields defaults to "
        "kind='event', priority=3."
    ),
)
async def send_session_message_tool(
    to: str,
    topic: str,
    payload: str,
    from_session: str = "",
    kind: str = "event",
    correlation_id: str | None = None,
    reply_to_message_id: int | None = None,
    priority: int = 3,
    requires_ack: bool = False,
    metadata_json: str | None = None,
) -> dict[str, object]:
    """Post a typed message to another session."""
    from shoal.core.message_bus import send_message

    msg_id = await send_message(
        from_session=from_session or "mcp",
        to_session=to,
        topic=topic,
        payload=payload,
        kind=kind,
        correlation_id=correlation_id,
        reply_to_message_id=reply_to_message_id,
        priority=priority,
        requires_ack=requires_ack,
        metadata_json=metadata_json,
    )
    return {"id": msg_id, "to": to, "topic": topic, "kind": kind, "correlation_id": correlation_id}


# ---------------------------------------------------------------------------
# Tool: receive_session_messages
# ---------------------------------------------------------------------------


@mcp.tool(
    name="receive_session_messages",
    description=(
        "Fetch messages for a session from the Agent Bus. "
        "Supports filtering by topic, kind, correlation_id, and after_id for incremental "
        "polling. By default returns only unconsumed messages. "
        "Call send_session_message to post messages."
    ),
    annotations={"readOnlyHint": True},
)
async def receive_session_messages_tool(
    session: str,
    topic: str | None = None,
    kind: str | None = None,
    correlation_id: str | None = None,
    unconsumed_only: bool = True,
    limit: int = 50,
    after_id: int | None = None,
) -> list[dict[str, object]]:
    """Fetch messages for a session."""
    from shoal.core.message_bus import receive_messages

    return await receive_messages(
        session,
        topic,
        kind=kind,
        correlation_id=correlation_id,
        unconsumed_only=unconsumed_only,
        limit=limit,
        after_id=after_id,
    )


# ---------------------------------------------------------------------------
# Tool: mark_session_message_consumed
# ---------------------------------------------------------------------------


@mcp.tool(
    name="mark_session_message_consumed",
    description="Mark an Agent Bus message as consumed by its recipient.",
)
async def mark_session_message_consumed_tool(message_id: int) -> dict[str, object]:
    """Mark a message as consumed."""
    from shoal.core.message_bus import mark_consumed

    await mark_consumed(message_id)
    return {"id": message_id, "consumed": True}


# ---------------------------------------------------------------------------
# Tool: mark_session_message_acked
# ---------------------------------------------------------------------------


@mcp.tool(
    name="mark_session_message_acked",
    description=(
        "Acknowledge an Agent Bus message after the described action has been completed. "
        "Distinct from mark_session_message_consumed: consumed removes from the pending "
        "queue; acked signals the described work is done."
    ),
)
async def mark_session_message_acked_tool(message_id: int) -> dict[str, object]:
    """Acknowledge a message."""
    from shoal.core.message_bus import mark_acked

    await mark_acked(message_id)
    return {"id": message_id, "acked": True}


# ---------------------------------------------------------------------------
# Tools: session actions (request / list / approve / deny)
# ---------------------------------------------------------------------------


@mcp.tool(
    name="request_session_action",
    description=(
        "Request a privileged action requiring approval from a target session or role. "
        "Actions are separate from ordinary messages and carry an explicit approval "
        "lifecycle (pending → approved/denied). Returns the action ID."
    ),
)
async def request_session_action_tool(
    requester_session: str,
    action_type: str,
    payload_json: str,
    target_session: str | None = None,
    target_role: str | None = None,
    correlation_id: str | None = None,
    metadata_json: str | None = None,
) -> dict[str, object]:
    """Submit an action request."""
    from shoal.core.action_bus import request_action

    action_id = await request_action(
        requester_session,
        action_type,
        payload_json,
        target_session=target_session,
        target_role=target_role,
        correlation_id=correlation_id,
        metadata_json=metadata_json,
    )
    return {
        "id": action_id,
        "action_type": action_type,
        "status": "pending",
        "correlation_id": correlation_id,
    }


@mcp.tool(
    name="list_pending_session_actions",
    description=(
        "List pending action requests visible to the current session. "
        "Filter by target_session, target_role, or correlation_id."
    ),
    annotations={"readOnlyHint": True},
)
async def list_pending_session_actions_tool(
    target_session: str | None = None,
    target_role: str | None = None,
    correlation_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    """List pending action requests."""
    from shoal.core.action_bus import list_pending_actions

    actions = await list_pending_actions(
        target_session=target_session,
        target_role=target_role,
        correlation_id=correlation_id,
        limit=limit,
    )
    return [a.model_dump(mode="json") for a in actions]


@mcp.tool(
    name="approve_session_action",
    description="Approve a pending session action request.",
)
async def approve_session_action_tool(
    action_id: int,
    resolved_by: str,
    reason: str | None = None,
) -> dict[str, object]:
    """Approve an action."""
    from shoal.core.action_bus import approve_action

    action = await approve_action(action_id, resolved_by, reason)
    if action is None:
        return {"error": f"action {action_id} not found"}
    return action.model_dump(mode="json")


@mcp.tool(
    name="deny_session_action",
    description="Deny a pending session action request.",
)
async def deny_session_action_tool(
    action_id: int,
    resolved_by: str,
    reason: str | None = None,
) -> dict[str, object]:
    """Deny an action."""
    from shoal.core.action_bus import deny_action

    action = await deny_action(action_id, resolved_by, reason)
    if action is None:
        return {"error": f"action {action_id} not found"}
    return action.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Tool: watch_session_messages
# ---------------------------------------------------------------------------


@mcp.tool(
    name="watch_session_messages",
    description=(
        "Watch for new Agent Bus messages, returning when at least one arrives "
        "or timeout_seconds elapses. Internally polls; callers get event-like "
        "semantics. Supports the same filters as receive_session_messages "
        "(topic, kind, correlation_id, after_id) plus a timeout."
    ),
)
async def watch_session_messages_tool(
    session: str,
    topic: str | None = None,
    kind: str | None = None,
    correlation_id: str | None = None,
    after_id: int | None = None,
    timeout_seconds: float = 30.0,
) -> list[dict[str, object]]:
    """Block until a matching message arrives or timeout."""
    from shoal.core.message_bus import watch_messages

    return await watch_messages(
        session,
        topic=topic,
        kind=kind,
        correlation_id=correlation_id,
        after_id=after_id,
        timeout_seconds=timeout_seconds,
    )


# ---------------------------------------------------------------------------
# Tool: get_workflow_messages
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_workflow_messages",
    description=(
        "Retrieve all messages sharing a correlation ID, across all sessions. "
        "Use to reconstruct a complete workflow trace regardless of which "
        "sessions sent or received each message."
    ),
    annotations={"readOnlyHint": True},
)
async def get_workflow_messages_tool(
    correlation_id: str,
    kind: str | None = None,
    limit: int = 50,
    after_id: int | None = None,
) -> list[dict[str, object]]:
    """Return all messages for a workflow correlation ID."""
    from shoal.core.message_bus import get_workflow_messages

    return await get_workflow_messages(correlation_id, kind=kind, limit=limit, after_id=after_id)


# ---------------------------------------------------------------------------
# Tool: watch_session_actions
# ---------------------------------------------------------------------------


@mcp.tool(
    name="watch_session_actions",
    description=(
        "Watch for pending action requests targeting a session or role, returning "
        "when at least one appears or timeout_seconds elapses. Supports "
        "correlation_id filter for workflow-scoped approval gating."
    ),
)
async def watch_session_actions_tool(
    target_session: str | None = None,
    target_role: str | None = None,
    correlation_id: str | None = None,
    timeout_seconds: float = 30.0,
) -> list[dict[str, object]]:
    """Block until a pending action request appears or timeout."""
    from shoal.core.action_bus import watch_pending_actions

    actions = await watch_pending_actions(
        target_session=target_session,
        target_role=target_role,
        correlation_id=correlation_id,
        timeout_seconds=timeout_seconds,
    )
    return [a.model_dump(mode="json") for a in actions]


# ---------------------------------------------------------------------------
# Tool: get_failure_context
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_failure_context",
    description=(
        "Return the most recent command failure context for a session. "
        "The Proactive Supervisor stores these when the Watcher detects an error. "
        "Consume the packet after use to avoid re-injection on the next turn."
    ),
    annotations={"readOnlyHint": True},
)
async def get_failure_context_tool(
    session: str,
    consume: bool = False,
) -> dict[str, object]:
    """Return pending failure context for a session."""
    from shoal.core.state import find_by_name, get_session
    from shoal.services.proactive_supervisor import get_proactive_supervisor

    session_id = await find_by_name(session)
    if session_id is None:
        raise ToolError(f"Session not found: {session}")
    s = await get_session(session_id)
    if s is None:
        raise ToolError(f"Session not found: {session}")

    supervisor = get_proactive_supervisor()
    if supervisor is None:
        # Fall through to DB directly even without in-process supervisor.
        from shoal.core.db import get_db

        db = await get_db()
        ctx = await db.get_failure_context(s.id)
    else:
        ctx = await supervisor.get_failure_context(s.id)

    if ctx is None:
        return {"session": s.name, "context": None}

    if consume:
        from shoal.core.db import get_db

        db = await get_db()
        await db.consume_failure_context(int(str(ctx["id"])))

    return {"session": s.name, "context": ctx}


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
# Tool: branch_status
# ---------------------------------------------------------------------------


@mcp.tool(
    name="branch_status",
    description=(
        "Get git branch info for a session's worktree: branch name, ahead/behind, "
        "dirty, last commit."
    ),
    annotations={"readOnlyHint": True},
)
async def branch_status_tool(session: str) -> dict[str, object]:
    """Return git branch status for the session's worktree."""
    from shoal.core.state import find_by_name, get_session

    session_id = await find_by_name(session)
    if session_id is None:
        raise ToolError(f"Session not found: {session}")

    state = await get_session(session_id)
    if state is None:
        raise ToolError(f"Session not found: {session}")

    if not state.worktree:
        raise ToolError("Session has no worktree")

    return await git_tools.branch_status(state.worktree)


# ---------------------------------------------------------------------------
# Tool: merge_branch
# ---------------------------------------------------------------------------


@mcp.tool(
    name="merge_branch",
    description=(
        "Merge a session's branch into a target branch in its worktree. "
        "Refuses if worktree is dirty."
    ),
    annotations={"destructiveHint": True},
)
async def merge_branch_tool(
    session: str,
    target: str,
    strategy: str = "merge",
) -> dict[str, object]:
    """Merge the session's current branch into target."""
    from shoal.core.state import find_by_name, get_session

    session_id = await find_by_name(session)
    if session_id is None:
        raise ToolError(f"Session not found: {session}")

    state = await get_session(session_id)
    if state is None:
        raise ToolError(f"Session not found: {session}")

    if not state.worktree:
        raise ToolError("Session has no worktree")

    if strategy not in {"merge", "squash"}:
        raise ToolError(f"Invalid strategy: {strategy!r}. Must be 'merge' or 'squash'.")

    resolved_strategy = cast(Literal["merge", "squash"], strategy)
    return await git_tools.merge_branch(
        state.worktree,
        target,
        strategy=resolved_strategy,
    )


# ---------------------------------------------------------------------------
# Tool: mark_complete
# ---------------------------------------------------------------------------


@mcp.tool(
    name="mark_complete",
    description=(
        "Mark a session as complete. Sets completed_at, appends a journal entry, "
        "and emits session_completed lifecycle event. Use this when an agent finishes "
        "its task and wants to signal completion to supervisors."
    ),
    annotations={"destructiveHint": True},
)
async def mark_complete_tool(
    session: str,
    summary: str = "",
) -> dict[str, object]:
    """Mark a session as complete with an optional summary."""
    from shoal.services.lifecycle import SessionNotFoundError, complete_session

    try:
        state = await complete_session(name=session, summary=summary)
    except SessionNotFoundError:
        raise ToolError(f"Session not found: {session}") from None
    return {"message": f"Session '{session}' marked as complete", "session_id": state.id}


# ---------------------------------------------------------------------------
# Tool: read_worktree_file
# ---------------------------------------------------------------------------


@mcp.tool(
    name="read_worktree_file",
    description=(
        "Read a file from a session's worktree. Use this to inspect worker outputs "
        "without attaching to the session. Path is relative to the worktree root."
    ),
)
async def read_worktree_file_tool(
    session: str,
    path: str,
    max_lines: int = 200,
) -> dict[str, object]:
    """Read a file from a session's worktree."""
    import asyncio

    from shoal.core.state import find_by_name, get_session

    session_id = await find_by_name(session)
    if session_id is None:
        raise ToolError(f"Session not found: {session}")

    state = await get_session(session_id)
    if state is None:
        raise ToolError(f"Session not found: {session}")

    work_dir = state.worktree or state.path
    file_path = Path(work_dir) / path

    try:
        file_path.resolve().relative_to(Path(work_dir).resolve())
    except ValueError:
        raise ToolError(f"Path traversal denied: {path}") from None

    if not file_path.exists():
        raise ToolError(f"File not found: {path} (in {work_dir})")

    def _read() -> str:
        lines = file_path.read_text().splitlines()
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"
        return "\n".join(lines)

    content = await asyncio.to_thread(_read)
    return {"path": str(file_path), "content": content}


# ---------------------------------------------------------------------------
# Tool: list_worktree_files
# ---------------------------------------------------------------------------


@mcp.tool(
    name="list_worktree_files",
    description=(
        "List files in a session's worktree (git-tracked + untracked). "
        "Use this to see what a worker produced."
    ),
)
async def list_worktree_files_tool(
    session: str,
    glob_pattern: str = "*",
) -> dict[str, object]:
    """List files in a session's worktree."""
    import asyncio

    from shoal.core.state import find_by_name, get_session

    session_id = await find_by_name(session)
    if session_id is None:
        raise ToolError(f"Session not found: {session}")

    state = await get_session(session_id)
    if state is None:
        raise ToolError(f"Session not found: {session}")

    work_dir = state.worktree or state.path

    def _list() -> list[str]:
        root = Path(work_dir)
        return [
            str(f.relative_to(root))
            for f in sorted(root.rglob(glob_pattern))
            if f.is_file() and ".git" not in f.parts and f.is_relative_to(root)
        ][:500]

    file_list = await asyncio.to_thread(_list)
    return {"worktree": work_dir, "files": file_list, "count": len(file_list)}


# ---------------------------------------------------------------------------
# Lobster MCP tools (optional — require grpcio)
# ---------------------------------------------------------------------------


_CLAW_TOOLS_AVAILABLE: bool = False
try:
    from shoal.core.lobster_client import LobsterClient

    _CLAW_TOOLS_AVAILABLE = True
except ImportError:
    pass  # grpcio not installed


# ---------------------------------------------------------------------------
# Tool: list_lobsters
# ---------------------------------------------------------------------------


@mcp.tool(
    name="list_lobsters",
    description="List all configured Lobsters from LobsterConfig.",
    annotations={"readOnlyHint": True},
)
async def list_lobsters_tool() -> list[dict[str, str]]:
    """List all configured Lobster runtimes from config."""
    from shoal.core.config import load_config
    from shoal.integrations.lobster import lobster_a2a

    if not lobster_a2a.GRPC_AVAILABLE:
        raise ToolError("Lobster tools require grpcio. Install with: pip install shoal[lobster]")

    cfg = load_config()
    known_lobsters = cfg.lobster.known_lobsters if hasattr(cfg, "lobster") else {}
    return [{"name": name, "grpc_addr": addr} for name, addr in known_lobsters.items()]


# ---------------------------------------------------------------------------
# Tool: lobster_status
# ---------------------------------------------------------------------------


@mcp.tool(
    name="lobster_status",
    description="Get status for one or more Lobster runtimes.",
    annotations={"readOnlyHint": True},
)
async def lobster_status_tool(lobster_id: str | list[str]) -> dict[str, object]:
    """Get status for one or more Lobsters."""
    from shoal.core.config import load_config
    from shoal.integrations.lobster import lobster_a2a

    if not lobster_a2a.GRPC_AVAILABLE:
        raise ToolError("Lobster tools require grpcio. Install with: pip install shoal[lobster]")

    cfg = load_config()
    known_lobsters = cfg.lobster.known_lobsters if hasattr(cfg, "lobster") else {}

    if isinstance(lobster_id, list):
        results: dict[str, object] = {}
        for cid in lobster_id:
            grpc_addr = known_lobsters.get(cid, cfg.lobster.grpc_addr)
            try:
                client = LobsterClient(
                    lobster_id=cid,
                    endpoint=grpc_addr,
                    employee_id=cfg.lobster.employee_id,
                    config=cfg.lobster,
                )
                status = await client.status()
                results[cid] = {"state": status["state"], "grpc_addr": grpc_addr}
                await client.close()
            except Exception as e:
                results[cid] = {"error": str(e)}
        return {"results": results}

    grpc_addr = known_lobsters.get(lobster_id, cfg.lobster.grpc_addr)
    client = LobsterClient(
        lobster_id=lobster_id,
        endpoint=grpc_addr,
        employee_id=cfg.lobster.employee_id,
        config=cfg.lobster,
    )
    try:
        status = await client.status()
        return {"state": status["state"], "grpc_addr": grpc_addr}
    except Exception as e:
        return {"error": str(e)}
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Tool: lobster_health
# ---------------------------------------------------------------------------


@mcp.tool(
    name="lobster_health",
    description="Check health of a Lobster runtime.",
    annotations={"readOnlyHint": True},
)
async def lobster_health_tool(lobster_id: str) -> dict[str, object]:
    """Check health of a Lobster. Returns {healthy: bool, issues: list[str]}."""
    from shoal.core.config import load_config
    from shoal.integrations.lobster import lobster_a2a

    if not lobster_a2a.GRPC_AVAILABLE:
        raise ToolError("Lobster tools require grpcio. Install with: pip install shoal[lobster]")

    cfg = load_config()
    grpc_addr = cfg.lobster.known_lobsters.get(lobster_id, cfg.lobster.grpc_addr)
    client = LobsterClient(
        lobster_id=lobster_id,
        endpoint=grpc_addr,
        employee_id=cfg.lobster.employee_id,
        config=cfg.lobster,
    )
    try:
        health = await client.health()
        return {"healthy": health["healthy"], "issues": health.get("issues", [])}
    except Exception as e:
        return {"healthy": False, "issues": [str(e)]}
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Tool: send_to_claw
# ---------------------------------------------------------------------------


@mcp.tool(
    name="send_to_claw",
    description=(
        "[Deprecated: use send_a2a_message] Send a message to a Claw runtime. "
        "Delegates to the A2A SendMessage RPC internally."
    ),
    annotations={"destructiveHint": True},
)
async def send_to_claw_tool(claw_id: str, message: str, employee_id: str = "") -> dict[str, object]:
    """Send a message to a Claw via A2A (deprecated wrapper around send_a2a_message)."""
    from shoal.integrations.lobster import lobster_a2a

    if not lobster_a2a.GRPC_AVAILABLE:
        raise ToolError("Lobster tools require grpcio. Install with: pip install shoal[lobster]")

    return await lobster_a2a.send_a2a_message_tool(
        lobster_id=claw_id,
        message=message,
        employee_id=employee_id or None,
    )


# ---------------------------------------------------------------------------
# Tool: get_agent_card (A2A Bridge)
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_agent_card",
    description=(
        "Get a Claw runtime's AgentCard for agent discovery via A2A protocol. "
        "Returns metadata about the Claw's capabilities, skills, and endpoint. "
        "Requires grpcio optional dependency."
    ),
    annotations={"readOnlyHint": True},
)
async def get_agent_card_tool(lobster_id: str) -> dict[str, object]:
    """Get AgentCard from a Claw runtime via A2A protocol.

    Args:
        lobster_id: The Lobster identifier to query.

    Returns:
        Dictionary containing the AgentCard with fields:
        - name: Agent name
        - version: Agent version
        - provider: Organization info {organization, url}
        - capabilities: {streaming, push_notifications, state_transition_reports}
        - skills: List of {id, name, description, tags}
        - endpoint: gRPC endpoint URL
        - description: Human-readable description
        - metadata: Additional key-value pairs

    Raises:
        ToolError: If grpcio is not installed or Claw is not configured.
    """
    from shoal.integrations.lobster import lobster_a2a

    if not lobster_a2a.GRPC_AVAILABLE:
        raise ToolError(
            "Lobster A2A bridge requires grpcio. Install with: pip install shoal[lobster]"
        )

    return cast(dict[str, object], await lobster_a2a.get_agent_card_tool(lobster_id))


# ---------------------------------------------------------------------------
# Tool: send_a2a_message (A2A Bridge)
# ---------------------------------------------------------------------------


@mcp.tool(
    name="send_a2a_message",
    description=(
        "Send a message to a Claw runtime via A2A protocol. "
        "Submits work to the Claw and returns the response. "
        "Requires grpcio optional dependency."
    ),
    annotations={"destructiveHint": True},
)
async def send_a2a_message_tool(
    lobster_id: str,
    message: str,
    task_id: str | None = None,
    employee_id: str | None = None,
) -> dict[str, object]:
    """Send a message to a Claw runtime via A2A SendMessage RPC.

    Args:
        lobster_id: The Lobster identifier to send work to.
        message: The message/work payload to process.
        task_id: Optional task ID for idempotency (generated if not provided).
        employee_id: Optional employee ID for audit trail (uses config default if not provided).

    Returns:
        Dictionary containing:
        - task_id: The task identifier
        - response: The Claw's response text
        - state: Current Claw state after processing

    Raises:
        ToolError: If grpcio is not installed or Claw is not configured.
    """
    from shoal.integrations.lobster import lobster_a2a

    if not lobster_a2a.GRPC_AVAILABLE:
        raise ToolError(
            "Lobster A2A bridge requires grpcio. Install with: pip install shoal[lobster]"
        )

    return await lobster_a2a.send_a2a_message_tool(
        lobster_id=lobster_id,
        message=message,
        task_id=task_id,
        employee_id=employee_id,
    )


# ---------------------------------------------------------------------------
# Tool: list_a2a_tasks (A2A Bridge)
# ---------------------------------------------------------------------------


@mcp.tool(
    name="list_a2a_tasks",
    description=(
        "List tasks for a Claw runtime via A2A protocol. "
        "Returns tasks with optional filtering by context or status. "
        "Requires grpcio optional dependency."
    ),
    annotations={"readOnlyHint": True},
)
async def list_a2a_tasks_tool(
    lobster_id: str,
    context_id: str | None = None,
    status: str | None = None,
) -> dict[str, object]:
    """List tasks from a Claw runtime via A2A ListTasks RPC.

    Args:
        lobster_id: The Lobster identifier to query.
        context_id: Optional context ID to filter tasks by.
        status: Optional task state to filter by (e.g., "working", "completed").

    Returns:
        Dictionary containing list of tasks with their states and metadata.

    Raises:
        ToolError: If grpcio is not installed or Claw is not configured.
    """
    from shoal.integrations.lobster import lobster_a2a

    if not lobster_a2a.GRPC_AVAILABLE:
        raise ToolError(
            "Lobster A2A bridge requires grpcio. Install with: pip install shoal[lobster]"
        )

    return cast(
        dict[str, object],
        await lobster_a2a.list_a2a_tasks_tool(
            lobster_id=lobster_id,
            context_id=context_id,
            status=status,
        ),
    )


# ---------------------------------------------------------------------------
# Tool: sync_lobster_conversations
# ---------------------------------------------------------------------------


@mcp.tool(
    name="sync_lobster_conversations",
    description=(
        "Sync conversations between Shoal journal and Lobster Party QMD format. "
        "Imports QMD turns into session journal or exports journal entries to QMD."
    ),
    annotations={"destructiveHint": True},
)
async def sync_lobster_conversations_tool(
    session: str,
    direction: str = "import",
    since: str | None = None,
    conversations_dir: str | None = None,
) -> dict[str, object]:
    """Sync conversations between Shoal journal and QMD format.

    Args:
        session: Session name or ID.
        direction: Sync direction - "import", "export", or "both".
        since: ISO timestamp - only import turns after this time.
        conversations_dir: Path to QMD conversations directory.

    Returns:
        Dict with imported and exported counts.
    """
    import asyncio
    from datetime import UTC, datetime

    from shoal.core.config import load_config
    from shoal.core.journal import journal_path
    from shoal.core.qmd import export_journal_to_qmd, import_qmd_to_journal
    from shoal.core.state import find_by_name, get_session

    # Resolve session
    session_id = await find_by_name(session)
    if session_id is None:
        raise ToolError(f"Session not found: {session}")

    s = await get_session(session_id)
    if s is None:
        raise ToolError(f"Session not found: {session}")

    # Parse since timestamp if provided
    since_dt: datetime | None = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=UTC)
        except ValueError as e:
            raise ToolError(f"Invalid timestamp format: {e}") from e

    # Resolve conversations directory
    if conversations_dir is None:
        cfg = load_config()
        if cfg.lobster.conversations_dir:
            conversations_dir = str(cfg.lobster.conversations_dir)
        else:
            import os

            home = os.path.expanduser("~")
            conversations_dir = str(Path(home) / "conversations")

    conv_dir = Path(conversations_dir)
    jpath = journal_path(s.id)

    imported = 0
    exported = 0

    if direction in ("import", "both"):
        imported = await asyncio.to_thread(
            import_qmd_to_journal,
            conversations_dir=conv_dir,
            journal_path=jpath,
            session_id=s.id,
            since=since_dt,
        )

    if direction in ("export", "both"):
        export_dir = conv_dir / "shoal-exports" / s.name
        exported = await asyncio.to_thread(
            export_journal_to_qmd,
            journal_path=jpath,
            output_dir=export_dir,
            session_id=s.id,
            session_name=s.name,
        )

    return {
        "session": s.name,
        "imported": imported,
        "exported": exported,
    }


# ---------------------------------------------------------------------------
# Claw scheduler tools
# ---------------------------------------------------------------------------


@mcp.tool(
    name="schedule_claw_task",
    description=(
        "Schedule a one-shot or recurring task in the claw scheduler. "
        "Use for background work like summarization, cleanup, or custom "
        "agent-defined periodic jobs. Returns the new task ID."
    ),
)
async def schedule_claw_task_tool(
    name: str,
    handler: str,
    session: str | None = None,
    task_type: str = "once",
    run_at: str | None = None,
    interval_seconds: float | None = None,
    cron_expr: str | None = None,
    payload_json: str = "{}",
    correlation_id: str | None = None,
    max_retries: int = 3,
) -> dict[str, object]:
    """Schedule a claw task and return its details."""
    from datetime import UTC, datetime

    from shoal.core.db import get_db

    if run_at is None:
        run_at = datetime.now(UTC).isoformat()

    db = await get_db()
    await db.connect()
    task_id = await db.create_claw_task(
        name=name,
        handler=handler,
        run_at=run_at,
        session=session,
        task_type=task_type,
        cron_expr=cron_expr,
        interval_seconds=interval_seconds,
        payload_json=payload_json,
        correlation_id=correlation_id,
        max_retries=max_retries,
    )
    task = await db.get_claw_task(task_id)
    return task or {"id": task_id}


@mcp.tool(
    name="list_claw_tasks",
    description=(
        "List claw scheduler tasks for a session (or system tasks when "
        "session is omitted). Optionally filter by status."
    ),
    annotations={"readOnlyHint": True},
)
async def list_claw_tasks_tool(
    session: str | None = None,
    status: str | None = None,
) -> list[dict[str, object]]:
    """List claw tasks."""
    from shoal.core.db import get_db

    db = await get_db()
    await db.connect()
    return await db.list_session_tasks(session, status=status)


@mcp.tool(
    name="get_claw_task",
    description="Get details of a specific claw task by ID.",
    annotations={"readOnlyHint": True},
)
async def get_claw_task_tool(task_id: int) -> dict[str, object]:
    """Get a claw task by ID."""
    from shoal.core.db import get_db

    db = await get_db()
    await db.connect()
    task = await db.get_claw_task(task_id)
    if task is None:
        raise ToolError(f"Claw task not found: {task_id}")
    return task


@mcp.tool(
    name="cancel_claw_task",
    description=(
        "Cancel a pending claw task by ID. Only pending tasks can be "
        "cancelled; running or completed tasks are unaffected."
    ),
)
async def cancel_claw_task_tool(task_id: int) -> dict[str, object]:
    """Cancel a pending claw task."""
    from shoal.core.db import get_db

    db = await get_db()
    await db.connect()
    cancelled = await db.cancel_claw_task(task_id)
    if not cancelled:
        raise ToolError(f"Cannot cancel task {task_id}: not found or not in pending status")
    task = await db.get_claw_task(task_id)
    return task or {"id": task_id, "status": "cancelled"}


@mcp.tool(
    name="watch_claw_tasks",
    description=(
        "Watch for due claw tasks, returning when at least one is ready "
        "or timeout_seconds elapses. Uses the same poll-based watch pattern "
        "as watch_session_messages."
    ),
)
async def watch_claw_tasks_tool(
    timeout_seconds: float = 30.0,
    poll_interval: float = 1.0,
) -> list[dict[str, object]]:
    """Block until a due task appears or timeout."""
    import asyncio
    from datetime import UTC, datetime

    from shoal.core.db import get_db

    db = await get_db()
    await db.connect()
    elapsed = 0.0
    while elapsed < timeout_seconds:
        now = datetime.now(UTC).isoformat()
        due = await db.list_due_tasks(now, limit=10)
        if due:
            return due
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
    return []


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the Shoal MCP server.

    Supports ``--http [PORT]`` for streamable-http transport (default: stdio).
    HTTP mode is used for benchmarking and remote session support.
    """
    import sys

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
