"""Pydantic models for the Shoal claw scheduling and trigger system."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class TriggerKind(StrEnum):
    """Supported trigger kinds."""

    cron = "cron"
    event = "event"
    file = "file"
    timer = "timer"
    webhook = "webhook"


class ExecutionStatus(StrEnum):
    """Status of a trigger execution."""

    running = "running"
    completed = "completed"
    error = "error"
    timeout = "timeout"


class TriggerDef(BaseModel):
    """A persistent trigger definition stored in SQLite."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    kind: TriggerKind
    enabled: bool = True

    # When — set depending on kind:
    cron_expr: str = ""
    """5-field cron expression (minute hour dom month dow)."""
    event_name: str = ""
    """LifecycleEvent value, e.g. ``session_completed``."""
    event_filter: dict[str, str] = Field(default_factory=dict)
    """Exact-match filter on event kwargs."""
    file_pattern: str = ""
    """fnmatch glob for file-change triggers."""
    fire_at: str = ""
    """ISO-8601 timestamp for one-shot timer triggers."""

    # What to spawn:
    template: str
    """Template name for the spawned session."""
    prompt: str = ""
    """Initial prompt sent to the session after creation."""
    session_name_prefix: str = ""
    """Prefix for auto-generated session names."""
    tags: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)

    # Control:
    max_concurrent: int = 1
    """Maximum active sessions from this trigger."""
    cooldown_seconds: int = 60
    """Minimum seconds between firings."""
    robo_supervised: bool = False
    """Start a robo watch alongside the spawned session."""

    # Bookkeeping (updated by daemon):
    last_fired_at: str = ""
    fire_count: int = 0
    created_at: str = ""


class TriggerExecution(BaseModel):
    """One execution of a trigger — links trigger to spawned session."""

    model_config = ConfigDict(extra="forbid")

    id: str
    trigger_id: str
    trigger_name: str
    session_id: str
    session_name: str
    status: ExecutionStatus = ExecutionStatus.running
    started_at: str
    completed_at: str = ""
