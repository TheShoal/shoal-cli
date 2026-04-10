"""FastAPI server for shoal — exposes session management over HTTP."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

import shoal
from shoal.core import git, tmux
from shoal.core.config import (
    ensure_dirs,
    load_config,
    load_tool_config,
    load_workspace_config,
)
from shoal.core.db import ShoalDB, get_db
from shoal.core.session_names import validate_session_name
from shoal.core.state import (
    add_mcp_to_session,
    filter_sessions_by_path,
    find_by_name,
    get_session,
    list_sessions,
    remove_mcp_from_session,
    update_session,
)
from shoal.dashboard import create_dashboard_app
from shoal.models.batch import (
    BatchExecutionRequest,
    BatchExecutionResponse,
    SessionSnapshotRequest,
    SessionSnapshotResponse,
)
from shoal.models.heartbeat import HeartbeatRequest
from shoal.models.incident import (
    IncidentHookEnvelope,
    IncidentIngestRequest,
    IncidentRecord,
    IncidentSpawnRequest,
    IncidentStatus,
)
from shoal.models.state import RuntimeKind, SessionState, SessionStatus, StatusSource
from shoal.services.batch import execute_batch
from shoal.services.batch import session_snapshot as build_session_snapshot
from shoal.services.incident import (
    get_incident_record,
    ingest_incident,
    list_incident_records,
    spawn_incident_lane,
)
from shoal.services.incident_hooks import record_claude_hook_event
from shoal.services.lifecycle import (
    DirtyWorktreeError,
    SessionExistsError,
    StartupCommandError,
    TmuxSetupError,
    create_session_lifecycle,
    kill_session_lifecycle,
    register_builtin_hooks,
    register_project_hooks,
)
from shoal.services.mcp_pool import (
    is_mcp_running,
    mcp_socket,
    read_pid,
    start_mcp_server,
    stop_mcp_server,
)
from shoal.services.runtime_provider import provider_for_session, runtime_payload

logger = logging.getLogger(__name__)


class SessionCreate(BaseModel):
    path: str | None = None
    tool: str | None = None
    worktree: str | None = None
    branch: bool = False
    name: str | None = None
    mcp: list[str] | None = None
    repo: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        """Validate session name if provided."""
        if v is not None:
            validate_session_name(v)
        return v


class SessionResponse(BaseModel):
    id: str
    name: str
    tool: str
    path: str
    worktree: str | None
    branch: str | None
    runtime: dict[str, object]
    status: SessionStatus
    pid: int | None
    mcp_servers: list[str]
    created_at: datetime
    last_activity: datetime
    status_since: datetime
    status_source: str = "watcher"
    last_heartbeat: datetime | None = None


class StatusResponse(BaseModel):
    total: int
    running: int
    waiting: int
    error: int
    idle: int
    stopped: int
    unknown: int
    version: str


class McpResponse(BaseModel):
    """MCP server info."""

    name: str
    pid: int | None
    status: str
    socket: str
    sessions: list[str]


class McpCreate(BaseModel):
    """MCP server creation request."""

    name: str
    command: str | None = None

    @field_validator("name")
    @classmethod
    def validate_mcp_name(cls, v: str) -> str:
        """Validate MCP server name."""
        from shoal.services.mcp_pool import validate_mcp_name

        validate_mcp_name(v)
        return v


class SendKeysRequest(BaseModel):
    """Request to send keys to a session."""

    keys: str


class RenameRequest(BaseModel):
    """Request to rename a session."""

    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate new session name."""
        validate_session_name(v)
        return v


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict[str, object]) -> None:
        broken: list[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                logger.warning("WebSocket send failed, removing connection")
                broken.append(connection)
        for conn in broken:
            self.active_connections.discard(conn)


manager = ConnectionManager()
status_poller_task: asyncio.Task[None] | None = None


async def poll_status_changes() -> None:
    """Background task to broadcast status changes."""
    previous_status: dict[str, str] = {}
    while True:
        try:
            sessions = await list_sessions()
            current_status: dict[str, str] = {s.id: s.status.value for s in sessions}

            # Detect changes
            for sid, status in current_status.items():
                prev = previous_status.get(sid)
                if prev != status:
                    event: dict[str, object] = {
                        "type": "status_change",
                        "session_id": sid,
                        "status": status,
                        "previous": prev,
                    }
                    await manager.broadcast(event)
                    from shoal.dashboard.ws import notify_status_change

                    await notify_status_change(event)

            previous_status = current_status
        except Exception:
            logger.exception("Error in status poller")
        await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    ensure_dirs()
    await get_db()  # Initialize DB
    register_builtin_hooks()
    register_project_hooks()
    global status_poller_task
    status_poller_task = asyncio.create_task(poll_status_changes())
    yield
    if status_poller_task:
        status_poller_task.cancel()
        with suppress(asyncio.CancelledError):
            await status_poller_task
    await ShoalDB.reset_instance()  # Clean up DB connection


app = FastAPI(
    title="Shoal API",
    version=shoal.__version__,
    description="HTTP API for AI agent session orchestration",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Inject a request ID into each request context and response headers."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        from shoal.core.context import generate_request_id, set_request_id

        request_id = request.headers.get("x-request-id") or generate_request_id()
        set_request_id(request_id)
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response


app.add_middleware(RequestIdMiddleware)


def _session_to_response(s: SessionState) -> SessionResponse:
    return SessionResponse(
        id=s.id,
        name=s.name,
        tool=s.tool,
        path=s.path,
        worktree=s.worktree or None,
        branch=s.branch or None,
        runtime=runtime_payload(s.runtime),
        status=s.status,
        pid=s.pid,
        mcp_servers=s.mcp_servers,
        created_at=s.created_at,
        last_activity=s.last_activity,
        status_since=s.status_since,
        status_source=s.status_source.value,
        last_heartbeat=s.last_heartbeat,
    )


@app.get("/", response_model=dict)
async def root() -> dict[str, str]:
    return {"service": "shoal", "version": shoal.__version__}


@app.get("/health")
async def health() -> dict[str, object]:
    """Deep health check — DB, watcher, tmux reachability."""
    components: dict[str, dict[str, object]] = {}

    # Check DB
    try:
        db = await get_db()
        await db.connect()
        components["database"] = {"healthy": True}
    except Exception as exc:
        components["database"] = {"healthy": False, "error": str(exc)}

    # Check watcher PID
    import os

    pid_file = Path.home()  # placeholder
    try:
        from shoal.core.config import state_dir

        pid_file = state_dir() / "watcher.pid"
        if pid_file.exists():
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            components["watcher"] = {"healthy": True, "pid": pid}
        else:
            components["watcher"] = {"healthy": False, "error": "not running"}
    except (ValueError, ProcessLookupError):
        components["watcher"] = {"healthy": False, "error": "stale PID"}
    except PermissionError:
        components["watcher"] = {"healthy": True}

    # Check tmux
    try:
        await tmux.async_has_session("__shoal_health_probe__")
        # has_session returns False for non-existent session, which means tmux is reachable
        components["tmux"] = {"healthy": True}
    except Exception:
        components["tmux"] = {"healthy": False, "error": "not reachable"}

    all_healthy = all(c.get("healthy", False) for c in components.values())
    return {
        "status": "healthy" if all_healthy else "degraded",
        "components": components,
    }


@app.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    sessions = await list_sessions()
    counts = {"running": 0, "waiting": 0, "error": 0, "idle": 0, "stopped": 0, "unknown": 0}
    for s in sessions:
        counts[s.status.value] = counts.get(s.status.value, 0) + 1
    return StatusResponse(
        total=len(sessions),
        running=counts["running"],
        waiting=counts["waiting"],
        error=counts["error"],
        idle=counts["idle"],
        stopped=counts["stopped"],
        unknown=counts["unknown"],
        version=shoal.__version__,
    )


@app.post("/batch", response_model=BatchExecutionResponse)
async def batch_execute_api(data: BatchExecutionRequest) -> BatchExecutionResponse:
    """Execute a heterogeneous application-level batch."""
    return await execute_batch(data)


@app.post("/sessions/snapshot", response_model=SessionSnapshotResponse)
async def session_snapshot_api(data: SessionSnapshotRequest) -> SessionSnapshotResponse:
    """Capture selected fields across multiple sessions in one read-optimized call."""
    return await build_session_snapshot(data)


@app.get("/incidents", response_model=list[IncidentRecord])
async def list_incidents_api(status: str | None = None) -> list[IncidentRecord]:
    if status is not None:
        try:
            parsed_status = IncidentStatus(status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid incident status") from exc
    else:
        parsed_status = None

    return await list_incident_records(status=parsed_status)


@app.get("/incidents/{incident_id}", response_model=IncidentRecord)
async def get_incident_api(incident_id: str) -> IncidentRecord:
    incident = await get_incident_record(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@app.post("/incidents", response_model=IncidentRecord, status_code=201)
async def create_incident_api(data: IncidentIngestRequest) -> IncidentRecord:
    return await ingest_incident(data)


@app.post("/incidents/{incident_id}/lanes", response_model=SessionResponse, status_code=201)
async def spawn_incident_lane_api(
    incident_id: str,
    body: IncidentSpawnRequest,
) -> SessionResponse:
    try:
        session = await spawn_incident_lane(incident_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return _session_to_response(session)


@app.post("/incidents/hooks/claude")
async def record_claude_hook_api(data: IncidentHookEnvelope) -> dict[str, object]:
    try:
        incident = await record_claude_hook_event(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "recorded": incident is not None,
        "incident_id": incident.id if incident is not None else None,
    }


@app.get("/sessions", response_model=list[SessionResponse])
async def list_sessions_api(path: str | None = None) -> list[SessionResponse]:
    ensure_dirs()
    sessions = await list_sessions()
    if path is not None:
        sessions = filter_sessions_by_path(sessions, path)
    return [_session_to_response(s) for s in sessions]


@app.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session_api(session_id: str) -> SessionResponse:
    s = await get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_to_response(s)


@app.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session_api(data: SessionCreate) -> SessionResponse:
    ensure_dirs()
    cfg = load_config()

    resolved_path = data.path if data.path else "."
    if not git.is_git_repo(resolved_path):
        raise HTTPException(status_code=400, detail="Not a git repository")

    tool = data.tool
    if not tool:
        tool = cfg.general.default_tool

    try:
        tool_cfg = load_tool_config(tool)
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {tool}") from None

    root = git.git_root(resolved_path)

    # --- Workspace routing: re-target to a sub-repo if inside a meta-repo ---
    ws_cfg = load_workspace_config(root)
    if data.repo and not ws_cfg:
        raise HTTPException(
            status_code=400,
            detail="--repo requires .shoal/workspace.toml in the git root",
        )
    if ws_cfg and ws_cfg.repos:
        try:
            root, resolved_path = git.apply_workspace_routing(
                root,
                resolved_path,
                repo=data.repo,
                worktree=data.worktree,
                repos=ws_cfg.repos,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None

    work_dir = resolved_path
    branch_name = ""
    wt_path = ""

    if data.worktree:
        wt_dir_name = data.worktree.replace("/", "-")
        wt_path = f"{root}/.worktrees/{wt_dir_name}"
        Path(root, ".worktrees").mkdir(parents=True, exist_ok=True)
        if data.branch:
            branch_name = git.infer_branch_name(data.worktree)
            git.worktree_add(root, wt_path, branch=branch_name)
        else:
            git.worktree_add(root, wt_path)
            branch_name = git.current_branch(wt_path)
        work_dir = wt_path
    else:
        branch_name = git.current_branch(resolved_path)

    session_name = data.name
    if not session_name:
        project_name = Path(root).name
        session_name = f"{project_name}/{data.worktree}" if data.worktree else project_name

    existing_id = await find_by_name(session_name)
    if existing_id:
        raise HTTPException(status_code=409, detail=f"Session '{session_name}' already exists")

    try:
        session = await create_session_lifecycle(
            session_name=session_name,
            tool=tool,
            git_root=root,
            wt_path=wt_path,
            work_dir=work_dir,
            branch_name=branch_name,
            tool_command=tool_cfg.command,
            startup_commands=cfg.tmux.startup_commands,
            mcp_servers=data.mcp,
        )
    except SessionExistsError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except TmuxSetupError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except StartupCommandError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    await manager.broadcast({"type": "session_created", "session_id": session.id})
    return _session_to_response(session)


@app.delete("/sessions/{session_id}", status_code=204)
async def delete_session_api(
    session_id: str,
    remove_worktree: bool = False,
    force: bool = False,
) -> None:
    s = await get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        tmux_session = s.runtime.session_name if s.runtime.kind == RuntimeKind.tmux else ""
        await kill_session_lifecycle(
            session_id=s.id,
            tmux_session=tmux_session,
            worktree=s.worktree,
            git_root=s.path,
            branch=s.branch,
            remove_worktree=remove_worktree,
            force=force,
        )
    except DirtyWorktreeError as e:
        raise HTTPException(
            status_code=409,
            detail={"message": str(e), "dirty_files": e.dirty_files},
        ) from e
    await manager.broadcast({"type": "session_deleted", "session_id": session_id})


@app.put("/sessions/{session_id}/rename", response_model=SessionResponse)
async def rename_session_api(session_id: str, body: RenameRequest) -> SessionResponse:
    """Rename a session."""
    # Get the session
    s = await get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    # Check for duplicate name
    existing = await find_by_name(body.name)
    if existing and existing != session_id:
        raise HTTPException(status_code=409, detail=f"Session name '{body.name}' already exists")

    # Rename the runtime backing the session
    try:
        updated_runtime = await provider_for_session(s).async_rename(s, body.name)
        updated = await update_session(
            session_id,
            name=body.name,
            runtime=updated_runtime,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Session not found")

        await manager.broadcast(
            {"type": "session_renamed", "session_id": session_id, "new_name": body.name}
        )
        return _session_to_response(updated)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Failed to rename runtime session: {e}") from e


@app.post("/sessions/{session_id}/attach")
async def attach_session_api(session_id: str) -> dict[str, str]:
    s = await get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if s.runtime.kind != RuntimeKind.tmux:
        raise HTTPException(status_code=400, detail="Attach is only supported for tmux sessions")
    provider = provider_for_session(s)
    if not provider.exists(s):
        raise HTTPException(status_code=400, detail="Runtime session not found")
    provider.attach(s)
    return {"message": f"Attached to {s.tmux_runtime.session_name}"}


@app.post("/sessions/{session_id}/send")
async def send_keys_api(session_id: str, body: SendKeysRequest) -> dict[str, str]:
    s = await get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    await provider_for_session(s).async_send_input(s, body.keys)
    return {"message": "Keys sent"}


@app.post("/sessions/{session_ref}/heartbeat")
async def heartbeat_api(session_ref: str, data: HeartbeatRequest) -> dict[str, object]:
    """Receive a status push from an agent hook."""
    # Resolve by name first, then by ID
    session_id = await find_by_name(session_ref)
    if not session_id:
        s = await get_session(session_ref)
        if not s:
            raise HTTPException(status_code=404, detail="Session not found")
        session_id = s.id

    now = datetime.now(UTC)

    await update_session(
        session_id,
        status=data.status,
        status_source=StatusSource.hook,
        last_heartbeat=now,
    )

    if data.summary:
        from shoal.core.journal import append_entry

        await asyncio.to_thread(
            append_entry,
            session_id,
            f"[heartbeat] {data.summary}",
            "agent-hook",
        )

    return {
        "ok": True,
        "session": session_ref,
        "status": data.status.value,
        "status_source": "hook",
    }


class SendMessageRequest(BaseModel):
    """Request body for posting a message to the Agent Bus."""

    from_session: str = ""
    to: str
    topic: str
    payload: str
    kind: str = "event"
    correlation_id: str | None = None
    priority: int = 3
    requires_ack: bool = False


class ReceiveMessagesRequest(BaseModel):
    """Query parameters for receiving Agent Bus messages."""

    topic: str | None = None
    kind: str | None = None
    correlation_id: str | None = None
    unconsumed_only: bool = True
    limit: int = 50


@app.post("/sessions/{session_ref}/messages/send")
async def send_message_api(session_ref: str, body: SendMessageRequest) -> dict[str, object]:
    """Post a message from one session to another via the Agent Bus."""
    from shoal.core.message_bus import send_message

    msg_id = await send_message(
        from_session=body.from_session or session_ref,
        to_session=body.to,
        topic=body.topic,
        payload=body.payload,
        kind=body.kind,
        correlation_id=body.correlation_id,
        priority=body.priority,
        requires_ack=body.requires_ack,
    )
    return {"id": msg_id, "to": body.to, "topic": body.topic, "kind": body.kind}


@app.get("/sessions/{session_ref}/messages")
async def receive_messages_api(
    session_ref: str,
    topic: str | None = None,
    kind: str | None = None,
    correlation_id: str | None = None,
    unconsumed_only: bool = True,
    limit: int = 50,
) -> list[dict[str, object]]:
    """Fetch messages for a session from the Agent Bus."""
    from shoal.core.message_bus import receive_messages

    return await receive_messages(
        session_ref,
        topic,
        kind=kind,
        correlation_id=correlation_id,
        unconsumed_only=unconsumed_only,
        limit=limit,
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.warning("WebSocket error, disconnecting", exc_info=True)
    finally:
        manager.disconnect(websocket)


# =============================================================================
# MCP Server Pool Endpoints
# =============================================================================


async def _get_mcp_info(name: str, all_sessions: list[SessionState] | None = None) -> McpResponse:
    """Get MCP server status and associated sessions.

    Args:
        name: MCP server name
        all_sessions: Optional pre-fetched session list to avoid N+1 queries.
                     If None, sessions will be fetched.
    """
    pid = read_pid(name)
    if pid is not None and is_mcp_running(name):
        status = "running"
    elif pid is not None:
        status = "dead"
    else:
        status = "orphaned"

    socket = str(mcp_socket(name))

    # Find sessions using this MCP
    if all_sessions is None:
        all_sessions = await list_sessions()
    sessions = [s.name for s in all_sessions if name in s.mcp_servers]

    return McpResponse(
        name=name,
        pid=pid,
        status=status,
        socket=socket,
        sessions=sessions,
    )


@app.get("/mcp", response_model=list[McpResponse])
async def list_mcp_servers() -> list[McpResponse]:
    """List all MCP servers in the pool."""
    ensure_dirs()
    socket_dir = mcp_socket("").parent
    if not socket_dir.exists():
        return []

    # Fetch all sessions once to avoid N+1 queries
    all_sessions = await list_sessions()

    servers: list[McpResponse] = []
    for sock_path in socket_dir.glob("*.sock"):
        name = sock_path.stem
        servers.append(await _get_mcp_info(name, all_sessions))
    return servers


@app.get("/mcp/known")
async def list_known_servers() -> list[dict[str, str]]:
    """List known MCP server commands (from registry + built-in defaults)."""
    from shoal.core.config import load_mcp_registry

    registry = load_mcp_registry()
    return [{"name": k, "command": v} for k, v in registry.items()]


@app.get("/mcp/{name}", response_model=McpResponse)
async def get_mcp_server(name: str) -> McpResponse:
    """Get details of a specific MCP server."""
    socket = mcp_socket(name)
    if not socket.exists() and not read_pid(name):
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    return await _get_mcp_info(name)


@app.post("/mcp", response_model=McpResponse, status_code=201)
async def start_mcp_server_api(data: McpCreate) -> McpResponse:
    """Start an MCP server in the pool."""
    ensure_dirs()
    name = data.name
    socket = mcp_socket(name)

    if socket.exists() and is_mcp_running(name):
        pid = read_pid(name)
        raise HTTPException(
            status_code=409, detail=f"MCP server '{name}' is already running (pid: {pid})"
        )

    try:
        pid, _socket_path, _cmd = start_mcp_server(name, data.command)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    await manager.broadcast({"type": "mcp_started", "name": name, "pid": pid})
    return await _get_mcp_info(name)


@app.delete("/mcp/{name}", status_code=204)
async def stop_mcp_server_api(name: str) -> None:
    """Stop an MCP server and clean up sessions."""
    try:
        stop_mcp_server(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' is not running") from None

    # Remove MCP from any sessions that reference it
    all_sessions = await list_sessions()
    for s in all_sessions:
        if name in s.mcp_servers:
            await remove_mcp_from_session(s.id, name)

    await manager.broadcast({"type": "mcp_stopped", "name": name})


@app.post("/sessions/{session_id}/mcp/{mcp_name}")
async def attach_mcp_to_session(session_id: str, mcp_name: str) -> dict[str, str | bool]:
    """Attach an MCP server to a session."""
    from shoal.services.mcp_pool import validate_mcp_name

    try:
        validate_mcp_name(mcp_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    s = await get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    socket = mcp_socket(mcp_name)
    if not socket.exists() or not is_mcp_running(mcp_name):
        # Auto-start: look up registry and start if known
        from shoal.core.config import load_mcp_registry

        registry = load_mcp_registry()
        command = registry.get(mcp_name)

        if not command:
            raise HTTPException(
                status_code=400,
                detail=f"MCP server '{mcp_name}' is not running and not in registry",
            )

        # Clean up stale socket if needed
        if socket.exists() and not is_mcp_running(mcp_name):
            with suppress(FileNotFoundError):
                stop_mcp_server(mcp_name)

        try:
            start_mcp_server(mcp_name, command)
        except (ValueError, RuntimeError) as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to auto-start MCP server: {e}"
            ) from e

    await add_mcp_to_session(session_id, mcp_name)

    # Auto-configure tool to use this MCP server
    configured: str | None = None
    work_dir = s.worktree or s.path
    from shoal.services.mcp_configure import McpConfigureError, configure_mcp_for_tool

    with suppress(McpConfigureError):
        configured = configure_mcp_for_tool(s.tool, mcp_name, work_dir)

    result: dict[str, str | bool] = {
        "message": f"Attached MCP '{mcp_name}' to session '{s.name}'",
        "socket": str(socket),
        "configure_command": f"shoal-mcp-proxy {mcp_name}",
        "configured": configured is not None,
    }
    if configured:
        result["configure_detail"] = configured
    return result


@app.delete("/sessions/{session_id}/mcp/{mcp_name}", status_code=204)
async def detach_mcp_from_session(session_id: str, mcp_name: str) -> None:
    """Detach an MCP server from a session."""
    s = await get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    if mcp_name not in s.mcp_servers:
        raise HTTPException(
            status_code=400, detail=f"Session '{session_id}' is not attached to MCP '{mcp_name}'"
        )

    await remove_mcp_from_session(session_id, mcp_name)


app.mount("/ui", create_dashboard_app())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8080)
