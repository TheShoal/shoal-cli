"""Shared application-level batching for Shoal MCP and HTTP APIs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import override

from shoal.models.batch import (
    AppendJournalBatchOp,
    BatchError,
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
    SessionSnapshotItem,
    SessionSnapshotRequest,
    SessionSnapshotResponse,
    SessionStatusBatchOp,
)
from shoal.models.state import SessionState
from shoal.services.runtime_provider import provider_for_session, runtime_payload

logger = logging.getLogger(__name__)

AUTO_ENTER_TOOLS: frozenset[str] = frozenset({"claude", "codex", "gemini", "pi"})


BatchPayload = object


SessionScopedBatchOp = BatchOperation


@dataclass(slots=True)
class BatchOperationFailure(Exception):
    """Expected per-item failure captured in the batch envelope."""

    code: str
    message: str

    @override
    def __str__(self) -> str:
        return self.message


@dataclass(slots=True)
class SessionCache:
    """Bulk-aware session resolution cache with invalidation for destructive ops."""

    resolved_by_ref: dict[str, str | None] = field(default_factory=dict)
    sessions_by_id: dict[str, SessionState | None] = field(default_factory=dict)
    refs_by_session: dict[str, set[str]] = field(default_factory=dict)

    async def prime(self, refs: Iterable[str]) -> None:
        from shoal.core.state import get_sessions, resolve_sessions

        unique_refs = list(dict.fromkeys(ref for ref in refs if ref))
        missing_refs = [ref for ref in unique_refs if ref not in self.resolved_by_ref]
        if missing_refs:
            resolved = await resolve_sessions(missing_refs)
            for ref, session_id in resolved.items():
                self.resolved_by_ref[ref] = session_id
                if session_id:
                    self.refs_by_session.setdefault(session_id, set()).add(ref)

        missing_ids = [
            session_id
            for session_id in {sid for sid in self.resolved_by_ref.values() if sid}
            if session_id not in self.sessions_by_id
        ]
        if not missing_ids:
            return

        loaded = await get_sessions(missing_ids)
        for session_id in missing_ids:
            self.sessions_by_id[session_id] = loaded.get(session_id)

    def peek_resolved(self, ref: str) -> str | None:
        return self.resolved_by_ref.get(ref)

    async def resolve(self, ref: str) -> str | None:
        from shoal.core.state import resolve_session

        if ref not in self.resolved_by_ref:
            session_id = await resolve_session(ref)
            self.resolved_by_ref[ref] = session_id
            if session_id:
                self.refs_by_session.setdefault(session_id, set()).add(ref)
        return self.resolved_by_ref.get(ref)

    async def resolve_required(self, ref: str) -> str:
        session_id = await self.resolve(ref)
        if not session_id:
            raise BatchOperationFailure("session_not_found", f"Session not found: {ref}")
        return session_id

    async def session(self, ref: str) -> SessionState | None:
        from shoal.core.state import get_session

        session_id = await self.resolve(ref)
        if not session_id:
            return None

        if session_id not in self.sessions_by_id:
            self.sessions_by_id[session_id] = await get_session(session_id)
        return self.sessions_by_id.get(session_id)

    async def require(self, ref: str) -> tuple[str, SessionState]:
        session_id = await self.resolve(ref)
        if not session_id:
            raise BatchOperationFailure("session_not_found", f"Session not found: {ref}")

        session = await self.session(ref)
        if session is None:
            raise BatchOperationFailure("session_not_found", f"Session not found: {ref}")
        return session_id, session

    def invalidate(self, session_id: str) -> None:
        self.sessions_by_id.pop(session_id, None)
        for ref in self.refs_by_session.pop(session_id, set()):
            self.resolved_by_ref.pop(ref, None)


async def execute_batch(request: BatchExecutionRequest) -> BatchExecutionResponse:
    """Execute heterogeneous session operations with shared resolution and caching."""

    cache = SessionCache()
    refs = _session_refs_for_ops(request.ops)
    if len(request.ops) > 1 or len(set(refs)) > 1:
        await cache.prime(refs)

    # Kill batches touch shared git/worktree state beyond a single session, and
    # aggregate status reads must observe earlier writes in batch order.
    if _requires_serial_execution(request.ops):
        return BatchExecutionResponse(
            results=await _execute_serial(
                request.ops, cache, stop_on_error=not request.continue_on_error
            )
        )
    if not request.continue_on_error:
        return BatchExecutionResponse(results=await _execute_serial(request.ops, cache))

    return BatchExecutionResponse(
        results=await _execute_parallel(request.ops, cache, request.max_parallelism)
    )


def _requires_serial_execution(ops: Sequence[BatchOperation]) -> bool:
    return any(_requires_global_ordering(op) for op in ops)


def _requires_global_ordering(op: BatchOperation) -> bool:
    match op:
        case KillSessionBatchOp():
            return True
        case SessionStatusBatchOp(session=None):
            return True
    return False


async def session_snapshot(request: SessionSnapshotRequest) -> SessionSnapshotResponse:
    """Capture a supervisor-friendly read snapshot across many sessions."""

    cache = SessionCache()
    await cache.prime(request.sessions)

    semaphore = asyncio.Semaphore(request.max_parallelism)
    results: list[SessionSnapshotItem | None] = [None] * len(request.sessions)

    async def run(index: int, ref: str) -> None:
        async with semaphore:
            try:
                _session_id, session_state = await cache.require(ref)
                provider = provider_for_session(session_state)
                payload: dict[str, object] = {"id": session_state.id, "name": session_state.name}
                for field in request.fields:
                    match field:
                        case "status":
                            payload["status"] = session_state.status.value
                        case "pane_tail":
                            payload["pane_tail"] = await provider.async_capture_output(
                                session_state, lines=request.pane_lines
                            )
                        case "mcp_servers":
                            payload["mcp_servers"] = session_state.mcp_servers
                        case "last_activity":
                            payload["last_activity"] = session_state.last_activity.isoformat()
                        case "status_since":
                            payload["status_since"] = session_state.status_since.isoformat()
                        case "tool":
                            payload["tool"] = session_state.tool
                        case "path":
                            payload["path"] = session_state.path
                        case "branch":
                            payload["branch"] = session_state.branch
                        case "worktree":
                            payload["worktree"] = session_state.worktree
                        case "pid":
                            payload["pid"] = session_state.pid
                        case "created_at":
                            payload["created_at"] = session_state.created_at.isoformat()
                        case "runtime":
                            payload["runtime"] = runtime_payload(session_state.runtime)
                results[index] = SessionSnapshotItem(session=ref, success=True, result=payload)
            except BatchOperationFailure as exc:
                results[index] = SessionSnapshotItem(
                    session=ref,
                    success=False,
                    error=BatchError(code=exc.code, message=exc.message),
                )
            except Exception as exc:  # pragma: no cover - defensive envelope for callers
                logger.exception("Unexpected session snapshot failure", extra={"session": ref})
                results[index] = SessionSnapshotItem(
                    session=ref,
                    success=False,
                    error=BatchError(code="internal_error", message=_error_message(exc)),
                )

    async with asyncio.TaskGroup() as task_group:
        for index, ref in enumerate(request.sessions):
            task_group.create_task(run(index, ref))

    return SessionSnapshotResponse(results=[item for item in results if item is not None])


async def _execute_serial(
    ops: Sequence[BatchOperation], cache: SessionCache, *, stop_on_error: bool = True
) -> list[BatchItemResult]:
    results: list[BatchItemResult] = []
    for index, op in enumerate(ops):
        item = await _execute_item(index, op, cache)
        results.append(item)
        if item.success or not stop_on_error:
            continue

        # Stop-on-error is explicit policy; serial scheduling alone still preserves
        # best-effort partial success when continue_on_error=True.
        for skipped_index, skipped_op in enumerate(ops[index + 1 :], start=index + 1):
            results.append(_skipped_item(skipped_index, skipped_op))
        break
    return results


async def _execute_parallel(
    ops: Sequence[BatchOperation], cache: SessionCache, max_parallelism: int
) -> list[BatchItemResult]:
    semaphore = asyncio.Semaphore(max_parallelism)
    results: list[BatchItemResult | None] = [None] * len(ops)
    tails: dict[str, asyncio.Future[None]] = {}
    loop = asyncio.get_running_loop()

    async def run(
        index: int,
        op: BatchOperation,
        previous: asyncio.Future[None] | None,
        completion: asyncio.Future[None] | None,
    ) -> None:
        try:
            if previous is not None:
                await previous
            async with semaphore:
                results[index] = await _execute_item(index, op, cache)
        finally:
            if completion is not None and not completion.done():
                completion.set_result(None)

    async with asyncio.TaskGroup() as task_group:
        for index, op in enumerate(ops):
            key = _target_key(op, cache)
            previous = tails.get(key) if key else None
            completion = loop.create_future() if key else None
            if key and completion is not None:
                tails[key] = completion
            task_group.create_task(run(index, op, previous, completion))

    return [item for item in results if item is not None]


async def _execute_item(index: int, op: BatchOperation, cache: SessionCache) -> BatchItemResult:
    session_ref = _session_ref(op)
    try:
        payload = await _dispatch(op, cache)
        return BatchItemResult(
            index=index,
            op=op.op,
            session=session_ref,
            success=True,
            result=payload,
        )
    except BatchOperationFailure as exc:
        return BatchItemResult(
            index=index,
            op=op.op,
            session=session_ref,
            success=False,
            error=BatchError(code=exc.code, message=exc.message),
        )
    except Exception as exc:  # pragma: no cover - defensive envelope for callers
        logger.exception(
            "Unexpected batch operation failure", extra={"op": op.op, "session": session_ref}
        )
        return BatchItemResult(
            index=index,
            op=op.op,
            session=session_ref,
            success=False,
            error=BatchError(code="internal_error", message=_error_message(exc)),
        )


async def _dispatch(op: BatchOperation, cache: SessionCache) -> BatchPayload:
    match op:
        case SessionInfoBatchOp():
            _session_id, session_state = await cache.require(op.session)
            return _session_info_payload(session_state)
        case SessionStatusBatchOp(session=None):
            from shoal.core.state import list_sessions

            return _status_counts_payload(await list_sessions())
        case SessionStatusBatchOp(session=session_ref) if session_ref is not None:
            _session_id, session_state = await cache.require(session_ref)
            return {"name": session_state.name, "status": session_state.status.value}
        case CapturePaneBatchOp():
            _session_id, session_state = await cache.require(op.session)
            content = await provider_for_session(session_state).async_capture_output(
                session_state, lines=op.lines
            )
            return {"content": content}
        case SendKeysBatchOp():
            import asyncio as async_tools

            from shoal.core.config import load_tool_config

            _session_id, session_state = await cache.require(op.session)
            auto_enter = (
                op.enter if op.enter is not None else session_state.tool in AUTO_ENTER_TOOLS
            )
            try:
                tool_cfg = await async_tools.to_thread(load_tool_config, session_state.tool)
                delay = tool_cfg.send_keys_delay
            except FileNotFoundError:
                delay = 0.0

            await provider_for_session(session_state).async_send_input(
                session_state,
                op.keys,
                enter=auto_enter,
                delay=delay,
            )
            return {"message": f"Keys sent to session '{session_state.name}'"}
        case KillSessionBatchOp():
            from shoal.services.lifecycle import DirtyWorktreeError, kill_session_lifecycle

            _session_id, session_state = await cache.require(op.session)
            try:
                summary = await kill_session_lifecycle(
                    session_id=session_state.id,
                    tmux_session=session_state.tmux_runtime.session_name,
                    worktree=session_state.worktree,
                    git_root=session_state.path,
                    branch=session_state.branch,
                    remove_worktree=op.remove_worktree,
                    force=op.force,
                )
            except DirtyWorktreeError as exc:
                raise BatchOperationFailure(
                    "dirty_worktree",
                    (
                        f"Worktree has uncommitted changes: {session_state.worktree}. "
                        f"Dirty files: {exc.dirty_files}. Use force=True to remove anyway."
                    ),
                ) from exc

            cache.invalidate(session_state.id)
            return {
                "session": session_state.name,
                "tmux_killed": summary["tmux_killed"],
                "worktree_removed": summary["worktree_removed"],
                "branch_deleted": summary["branch_deleted"],
                "db_deleted": summary["db_deleted"],
                "journal_archived": summary["journal_archived"],
            }
        case ReadHistoryBatchOp():
            from shoal.core.db import get_db

            session_id = await cache.resolve_required(op.session)
            db = await get_db()
            return await db.get_status_transitions(session_id, limit=op.limit)
        case ReadJournalBatchOp():
            from shoal.core.journal import read_journal

            session_id = await cache.resolve_required(op.session)
            entries = await asyncio.to_thread(read_journal, session_id, op.limit)
            return [
                {
                    "timestamp": entry.timestamp.isoformat(),
                    "source": entry.source,
                    "content": entry.content,
                }
                for entry in entries
            ]
        case AppendJournalBatchOp():
            from shoal.core.journal import append_entry, build_journal_metadata, journal_exists

            session_id = await cache.resolve_required(op.session)
            metadata = None
            if not await asyncio.to_thread(journal_exists, session_id):
                metadata_session = await cache.session(op.session)
                if metadata_session is not None:
                    metadata = build_journal_metadata(metadata_session)

            path = await asyncio.to_thread(
                append_entry,
                session_id,
                op.entry,
                op.source,
                metadata=metadata,
            )
            return {"message": f"Journal entry appended to {_path_name(path)}"}

    raise BatchOperationFailure("unsupported_operation", f"Unsupported batch op: {op.op}")


def _session_info_payload(session_state: SessionState) -> dict[str, object]:
    return {
        "id": session_state.id,
        "name": session_state.name,
        "tool": session_state.tool,
        "status": session_state.status.value,
        "path": session_state.path,
        "branch": session_state.branch,
        "worktree": session_state.worktree,
        "runtime": runtime_payload(session_state.runtime),
        "pid": session_state.pid,
        "mcp_servers": session_state.mcp_servers,
        "created_at": session_state.created_at.isoformat(),
        "last_activity": session_state.last_activity.isoformat(),
        "status_since": session_state.status_since.isoformat(),
    }


def _status_counts_payload(sessions: Sequence[SessionState]) -> dict[str, int]:
    counts: dict[str, int] = {
        "total": len(sessions),
        "running": 0,
        "waiting": 0,
        "error": 0,
        "idle": 0,
        "stopped": 0,
        "unknown": 0,
    }
    for session_state in sessions:
        counts[session_state.status.value] = counts.get(session_state.status.value, 0) + 1
    return counts


def _session_ref(op: BatchOperation) -> str | None:
    match op:
        case SessionInfoBatchOp(session=session):
            return session
        case SessionStatusBatchOp(session=session):
            return session
        case CapturePaneBatchOp(session=session):
            return session
        case SendKeysBatchOp(session=session):
            return session
        case KillSessionBatchOp(session=session):
            return session
        case ReadHistoryBatchOp(session=session):
            return session
        case ReadJournalBatchOp(session=session):
            return session
        case AppendJournalBatchOp(session=session):
            return session
    return None


def _session_refs_for_ops(ops: Sequence[BatchOperation]) -> list[str]:
    refs: list[str] = []
    for op in ops:
        session = _session_ref(op)
        if session:
            refs.append(session)
    return refs


def _target_key(op: SessionScopedBatchOp, cache: SessionCache) -> str | None:
    session_ref = _session_ref(op)
    if session_ref is None:
        return None

    session_id = cache.peek_resolved(session_ref)
    return session_id or f"session:{session_ref}"


def _skipped_item(index: int, op: BatchOperation) -> BatchItemResult:
    return BatchItemResult(
        index=index,
        op=op.op,
        session=_session_ref(op),
        success=False,
        error=BatchError(code="skipped", message="Skipped after previous batch failure"),
    )


def _error_message(exc: Exception) -> str:
    return str(exc) or exc.__class__.__name__


def _path_name(path: Path) -> str:
    return path.name
