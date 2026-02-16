"""FastAPI server for shoal — exposes session management over HTTP."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import shoal
from shoal.core import git, tmux
from shoal.core.config import ensure_dirs, load_config, load_tool_config
from shoal.core.db import ShoalDB, get_db
from shoal.core.state import (
    add_mcp_to_session,
    create_session,
    delete_session,
    get_session,
    list_sessions,
    remove_mcp_from_session,
    update_session,
)
from shoal.models.state import SessionStatus
from shoal.services.mcp_pool import (
    KNOWN_SERVERS,
    is_mcp_running,
    mcp_socket,
    read_pid,
    start_mcp_server,
    stop_mcp_server,
)

logger = logging.getLogger(__name__)


class SessionStatusEnum(StrEnum):
    running = "running"
    waiting = "waiting"
    error = "error"
    idle = "idle"
    stopped = "stopped"
    unknown = "unknown"


class SessionCreate(BaseModel):
    path: str | None = None
    tool: str
    worktree: str | None = None
    branch: bool = False
    name: str | None = None


class SessionResponse(BaseModel):
    id: str
    name: str
    tool: str
    path: str
    worktree: str | None
    branch: str | None
    tmux_session: str
    status: SessionStatusEnum
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


class SendKeysRequest(BaseModel):
    """Request to send keys to a session."""

    keys: str


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)


manager = ConnectionManager()
status_poller_task: asyncio.Task | None = None


async def poll_status_changes():
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
        try:
            await status_poller_task
        except asyncio.CancelledError:
            pass
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


def _session_to_response(s) -> SessionResponse:
    return SessionResponse(
        id=s.id,
        name=s.name,
        tool=s.tool,
        path=s.path,
        worktree=s.worktree or None,
        branch=s.branch or None,
        tmux_session=s.tmux_session,
        status=SessionStatusEnum(s.status.value),
        pid=s.pid,
        mcp_servers=s.mcp_servers,
        created_at=s.created_at,
        last_activity=s.last_activity,
    )


@app.get("/", response_model=dict)
async def root():
    return {"service": "shoal", "version": shoal.__version__}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/status", response_model=StatusResponse)
async def get_status():
    sessions = await list_sessions()
    counts = {"running": 0, "waiting": 0, "error": 0, "idle": 0, "stopped": 0}
    for s in sessions:
        counts[s.status.value] = counts.get(s.status.value, 0) + 1
    return StatusResponse(
        total=len(sessions),
        running=counts["running"],
        waiting=counts["waiting"],
        error=counts["error"],
        idle=counts["idle"],
        stopped=counts["stopped"],
        version=shoal.__version__,
    )


@app.get("/sessions", response_model=list[SessionResponse])
async def list_sessions_api():
    ensure_dirs()
    sessions = await list_sessions()
    return [_session_to_response(s) for s in sessions]


@app.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session_api(session_id: str):
    s = await get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_to_response(s)


@app.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session_api(data: SessionCreate):
    ensure_dirs()
    cfg = load_config()

    resolved_path = data.path if data.path else "."
    if not git.is_git_repo(resolved_path):
        raise HTTPException(status_code=400, detail="Not a git repository")

    tool = data.tool
    if not tool:
        tool = cfg.general.default_tool

    try:
        load_tool_config(tool)
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {tool}")

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
        if data.worktree:
            session_name = f"{project_name}/{data.worktree}"
        else:
            session_name = project_name

    # find_by_name is now async
    from shoal.core.state import find_by_name

    existing_id = await find_by_name(session_name)
    if existing_id:
        raise HTTPException(status_code=409, detail=f"Session '{session_name}' already exists")

    session = await create_session(session_name, tool, root, work_dir, branch_name)
    tool_cfg = load_tool_config(tool)
    tmux_session = session.tmux_session

    try:
        tmux.new_session(tmux_session, cwd=work_dir)
    except Exception as e:
        await delete_session(session.id)
        raise HTTPException(status_code=500, detail=f"Failed to create tmux session: {e}")

    tmux.set_environment(tmux_session, "SHOAL_SESSION_ID", session.id)
    tmux.set_environment(tmux_session, "SHOAL_SESSION_NAME", session_name)

    # Run startup commands
    cfg = load_config()
    for cmd in cfg.tmux.startup_commands:
        interpolated = cmd.format(
            tool_command=tool_cfg.command,
            work_dir=work_dir,
            session_name=session_name,
            tmux_session=tmux_session,
        )
        tmux.run_command(interpolated)

    await update_session(session.id, status=SessionStatus.running)
    pane = tmux.pane_pid(tmux_session)
    if pane:
        await update_session(session.id, pid=pane)

    await manager.broadcast({"type": "session_created", "session_id": session.id})
    updated_session = await get_session(session.id)
    return _session_to_response(updated_session)


@app.delete("/sessions/{session_id}", status_code=204)
async def delete_session_api(session_id: str):
    s = await get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    if tmux.has_session(s.tmux_session):
        tmux.kill_session(s.tmux_session)

    await delete_session(session_id)
    await manager.broadcast({"type": "session_deleted", "session_id": session_id})


@app.post("/sessions/{session_id}/attach")
async def attach_session_api(session_id: str):
    s = await get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if not tmux.has_session(s.tmux_session):
        raise HTTPException(status_code=400, detail="Tmux session not found")
    tmux.switch_client(s.tmux_session)
    return {"message": f"Attached to {s.tmux_session}"}


@app.post("/sessions/{session_id}/send")
async def send_keys_api(session_id: str, body: SendKeysRequest):
    s = await get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    tmux.send_keys(s.tmux_session, body.keys)
    return {"message": "Keys sent"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# =============================================================================
# MCP Server Pool Endpoints
# =============================================================================


async def _get_mcp_info(name: str) -> McpResponse:
    """Get MCP server status and associated sessions."""
    pid = read_pid(name)
    if pid is not None and is_mcp_running(name):
        status = "running"
    elif pid is not None:
        status = "dead"
    else:
        status = "orphaned"

    socket = str(mcp_socket(name))

    # Find sessions using this MCP
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
async def list_mcp_servers():
    """List all MCP servers in the pool."""
    ensure_dirs()
    socket_dir = mcp_socket("").parent
    if not socket_dir.exists():
        return []

    servers: list[McpResponse] = []
    for sock_path in socket_dir.glob("*.sock"):
        name = sock_path.stem
        servers.append(await _get_mcp_info(name))
    return servers


@app.get("/mcp/known")
async def list_known_servers():
    """List known MCP server commands."""
    return [{"name": k, "command": v} for k, v in KNOWN_SERVERS.items()]


@app.get("/mcp/{name}", response_model=McpResponse)
async def get_mcp_server(name: str):
    """Get details of a specific MCP server."""
    socket = mcp_socket(name)
    if not socket.exists() and not read_pid(name):
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    return await _get_mcp_info(name)


@app.post("/mcp", response_model=McpResponse, status_code=201)
async def start_mcp_server_api(data: McpCreate):
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
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    await manager.broadcast({"type": "mcp_started", "name": name, "pid": pid})
    return await _get_mcp_info(name)


@app.delete("/mcp/{name}", status_code=204)
async def stop_mcp_server_api(name: str):
    """Stop an MCP server and clean up sessions."""
    try:
        stop_mcp_server(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' is not running")

    # Remove MCP from any sessions that reference it
    all_sessions = await list_sessions()
    for s in all_sessions:
        if name in s.mcp_servers:
            await remove_mcp_from_session(s.id, name)

    await manager.broadcast({"type": "mcp_stopped", "name": name})


@app.post("/sessions/{session_id}/mcp/{mcp_name}")
async def attach_mcp_to_session(session_id: str, mcp_name: str):
    """Attach an MCP server to a session."""
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
async def detach_mcp_from_session(session_id: str, mcp_name: str):
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

    uvicorn.run(app, host="0.0.0.0", port=8080)
