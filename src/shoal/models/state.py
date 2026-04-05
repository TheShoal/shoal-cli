"""Pydantic models for shoal runtime state."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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
    session_completed = "session_completed"
    # Proactive events (P1)
    file_changed = "file_changed"
    """Fired by FsWatcher when a file in a session's worktree is modified."""
    command_failed = "command_failed"
    """Fired by Watcher when a shell command exits with a non-zero code."""
    trigger_fired = "trigger_fired"
    """Legacy event emitted when automation spawns a session."""


class RuntimeKind(StrEnum):
    tmux = "tmux"


class RuntimeCapability(StrEnum):
    attach = "attach"
    send_input = "send_input"
    capture_output = "capture_output"
    rename = "rename"
    editor_socket = "editor_socket"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TmuxRuntimeState(BaseModel):
    kind: Literal[RuntimeKind.tmux] = RuntimeKind.tmux
    session_name: str
    session_id: str = ""
    window_id: str = ""
    nvim_socket: str = ""


RuntimeState = TmuxRuntimeState
AnyRuntimeState = TmuxRuntimeState


class SessionState(BaseModel):
    """Represents a single shoal session — stored in SQLite."""

    id: str
    name: str
    tool: str
    path: str  # git root
    worktree: str = ""
    branch: str = ""
    runtime: AnyRuntimeState
    status: SessionStatus = SessionStatus.idle

    @property
    def tmux_runtime(self) -> TmuxRuntimeState:
        """Narrow runtime to TmuxRuntimeState. Raises TypeError for non-tmux sessions."""
        if not isinstance(self.runtime, TmuxRuntimeState):
            msg = f"Expected tmux runtime, got {self.runtime.kind}"
            raise TypeError(msg)
        return self.runtime

    pid: int | None = None
    dreamer_pane_id: str = ""
    mcp_servers: list[str] = Field(default_factory=list)
    parent_id: str = ""
    tags: list[str] = Field(default_factory=list)
    template_name: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    last_activity: datetime = Field(default_factory=_utcnow)
    status_since: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_tmux_runtime(cls, data: object) -> object:
        """Translate pre-v0.25.0 tmux fields into the nested runtime shape."""
        if not isinstance(data, dict) or "runtime" in data:
            return data

        tmux_session = data.get("tmux_session")
        if not isinstance(tmux_session, str) or not tmux_session:
            return data

        migrated: dict[str, object] = dict(data)
        migrated["runtime"] = TmuxRuntimeState(
            session_name=tmux_session,
            session_id=str(migrated.pop("tmux_session_id", "")),
            window_id=str(migrated.pop("tmux_window", "")),
            nvim_socket=str(migrated.pop("nvim_socket", "")),
        ).model_dump()
        migrated.pop("tmux_session", None)
        return migrated

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate session name for security and compatibility."""
        from shoal.core.session_names import validate_session_name

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
