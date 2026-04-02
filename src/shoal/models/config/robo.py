"""Robo profile models (robo/<name>.toml)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MonitoringConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    poll_interval: int = 10
    waiting_timeout: int = 300


class EscalationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notify: bool = True
    auto_respond: bool = False
    escalation_session: str | None = None
    escalation_timeout: int = 300


class TasksConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    log_file: str = "task-log.md"


class ProactiveSupervisorConfig(BaseModel):
    """Proactive supervisor settings embedded in a robo profile."""

    model_config = ConfigDict(extra="forbid")

    auto_enqueue: bool = False
    """Automatically create an implementer session when a command failure is detected."""
    failure_ttl_seconds: int = 3600
    """How long to retain failure context packets (seconds)."""
    trigger_topics: list[str] = Field(default_factory=lambda: ["command_failed"])
    """Agent Bus topic names that trigger the proactive loop."""


class RoboProfileConfig(BaseModel):
    """Robo profile — maps to ~/.config/shoal/robo/<name>.toml."""

    model_config = ConfigDict(extra="forbid")

    name: str = "default"
    tool: str = "pi"
    auto_approve: bool = False
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    escalation: EscalationConfig = Field(default_factory=EscalationConfig)
    tasks: TasksConfig = Field(default_factory=TasksConfig)
    proactive: ProactiveSupervisorConfig = Field(default_factory=ProactiveSupervisorConfig)
