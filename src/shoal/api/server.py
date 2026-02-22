"""FastAPI server for shoal — exposes session management over HTTP."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

import shoal
from shoal.core import git, tmux
from shoal.core.config import ensure_dirs, load_config, load_tool_config
from shoal.core.db import ShoalDB, get_db
from shoal.core.state import (
    add_mcp_to_session,
    build_tmux_session_name,
    find_by_name,
    get_session,
    list_sessions,
    remove_mcp_from_session,
    update_session,
)
from shoal.models.state import SessionState, SessionStatus
from shoal.services.lifecycle import (
    SessionExistsError,
    StartupCommandError,
    TmuxSetupError,
    create_session_lifecycle,
    kill_session_lifecycle,
)
from shoal.services.mcp_pool import (
    KNOWN_SERVERS,
    is_mcp_running,
    mcp_socket,
    read_pid,
    start_mcp_server,
    stop_mcp_server,
)

logger = logging.getLogger(__name__)


class SessionCreate(BaseModel):
    path: str | None = None
    tool: str | None = None
    worktree: str | None = None
    branch: bool = False
    name: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        """Validate session name if provided."""
        if v is not None:
            from shoal.core.state import validate_session_name

            validate_session_name(v)
        return v


class SessionResponse(BaseModel):
    id: str
    name: str
    tool: str
    path: str
    worktree: str | None
    branch: str | None
    tmux_session: str
    status: SessionStatus
    pid: int | None
    mcp_servers: list[str]
    created_at: datetime
    last_activity: datetime


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
        from shoal.core.state import validate_session_name

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
                    await manager.broadcast(
                        {
                            "type": "status_change",
                            "session_id": sid,
                            "status": status,
                            "previous": prev,
                        }
                    )

            previous_status = current_status
        except Exception:
            logger.exception("Error in status poller")
        await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    ensure_dirs()
    await get_db()  # Initialize DB
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _session_to_response(s: SessionState) -> SessionResponse:
    return SessionResponse(
        id=s.id,
        name=s.name,
        tool=s.tool,
        path=s.path,
        worktree=s.worktree or None,
        branch=s.branch or None,
        tmux_session=s.tmux_session,
        status=s.status,
        pid=s.pid,
        mcp_servers=s.mcp_servers,
        created_at=s.created_at,
        last_activity=s.last_activity,
    )


@app.get("/", response_model=dict)
async def root() -> dict[str, str]:
    return {"service": "shoal", "version": shoal.__version__}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


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


@app.get("/sessions", response_model=list[SessionResponse])
async def list_sessions_api() -> list[SessionResponse]:
    ensure_dirs()
    sessions = await list_sessions()
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
    work_dir = resolved_path
    branch_name = ""
    wt_path = ""

    if data.worktree:
        wt_dir_name = data.worktree.replace("/", "-")
        wt_path = f"{root}/.worktrees/{wt_dir_name}"
        Path(root, ".worktrees").mkdir(parents=True, exist_ok=True)
        if data.branch:
            branch_name = f"feat/{data.worktree}"
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
async def delete_session_api(session_id: str) -> None:
    s = await get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    await kill_session_lifecycle(
        session_id=s.id,
        tmux_session=s.tmux_session,
    )
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

    # Rename the tmux session
    old_tmux_name = s.tmux_session
    new_tmux_name = build_tmux_session_name(body.name)

    if tmux.has_session(old_tmux_name):
        try:
            tmux.rename_session(old_tmux_name, new_tmux_name)
        except subprocess.CalledProcessError as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to rename tmux session: {e}"
            ) from e

    # Update the session in the database
    try:
        updated = await update_session(
            session_id,
            name=body.name,
            tmux_session=new_tmux_name,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Session not found")

        await manager.broadcast(
            {"type": "session_renamed", "session_id": session_id, "new_name": body.name}
        )
        return _session_to_response(updated)
    except ValueError as e:
        # Validation error from update_session
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/sessions/{session_id}/attach")
async def attach_session_api(session_id: str) -> dict[str, str]:
    s = await get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if not tmux.has_session(s.tmux_session):
        raise HTTPException(status_code=400, detail="Tmux session not found")
    tmux.switch_client(s.tmux_session)
    return {"message": f"Attached to {s.tmux_session}"}


@app.post("/sessions/{session_id}/send")
async def send_keys_api(session_id: str, body: SendKeysRequest) -> dict[str, str]:
    s = await get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    tmux.send_keys(s.tmux_session, body.keys)
    return {"message": "Keys sent"}


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
    """List known MCP server commands."""
    return [{"name": k, "command": v} for k, v in KNOWN_SERVERS.items()]


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
        pid, socket_path, cmd = start_mcp_server(name, data.command)
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
async def attach_mcp_to_session(session_id: str, mcp_name: str) -> dict[str, str]:
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
    if not socket.exists():
        raise HTTPException(status_code=400, detail=f"MCP server '{mcp_name}' is not running")

    if not is_mcp_running(mcp_name):
        raise HTTPException(status_code=400, detail=f"MCP server '{mcp_name}' has a stale socket")

    await add_mcp_to_session(session_id, mcp_name)
    return {
        "message": f"Attached MCP '{mcp_name}' to session '{s.name}'",
        "socket": str(socket),
        "configure_command": f"socat STDIO UNIX-CONNECT:{socket}",
    }


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8080)
