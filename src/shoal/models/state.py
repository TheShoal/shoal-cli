"""Pydantic models for shoal runtime state."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class SessionStatus(StrEnum):
    running = "running"
    waiting = "waiting"
    error = "error"
    idle = "idle"
    stopped = "stopped"
    unknown = "unknown"


class LifecycleEvent(StrEnum):
    """Events emitted by the lifecycle service."""

    session_created = "session_created"
    session_killed = "session_killed"
    session_forked = "session_forked"
    status_changed = "status_changed"


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
    tmux_session_id: str = ""
    tmux_window: str = ""
    nvim_socket: str = ""
    status: SessionStatus = SessionStatus.idle
    pid: int | None = None
    mcp_servers: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    last_activity: datetime = Field(default_factory=_utcnow)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate session name for security and compatibility."""
        from shoal.core.state import validate_session_name

        validate_session_name(v)
        return v


class RoboState(BaseModel):
    """Runtime state for a robo instance."""

    name: str
    tool: str
    tmux_session: str
    status: SessionStatus = SessionStatus.running
    started_at: datetime = Field(default_factory=_utcnow)


# Backward compatibility alias
ConductorState = RoboState
