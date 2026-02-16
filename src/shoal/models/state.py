"""Pydantic models for shoal runtime state."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SessionStatus(StrEnum):
    running = "running"
    waiting = "waiting"
    error = "error"
    idle = "idle"
    stopped = "stopped"
    unknown = "unknown"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SessionState(BaseModel):
    """Represents a single shoal session — stored in SQLite."""

    id: str
    name: str
    tool: str
    path: str  # git root
    worktree: str = ""
    branch: str = ""
    tmux_session: str
    tmux_window: str = "0"
    nvim_socket: str = ""
    status: SessionStatus = SessionStatus.idle
    pid: int | None = None
    mcp_servers: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    last_activity: datetime = Field(default_factory=_utcnow)


class RoboState(BaseModel):
    """Runtime state for a robo instance."""

    name: str
    tool: str
    tmux_session: str
    status: SessionStatus = SessionStatus.running
    started_at: datetime = Field(default_factory=_utcnow)


# Backward compatibility alias
ConductorState = RoboState
