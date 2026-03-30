"""Pydantic models for Shoal incidents and alert-driven supervision."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AlertSeverity(StrEnum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class IncidentStatus(StrEnum):
    active = "active"
    monitoring = "monitoring"
    resolved = "resolved"


class IncidentRole(StrEnum):
    supervisor = "incident-supervisor"
    investigator = "incident-investigator"
    repro = "incident-repro"
    comms = "incident-comms"
    reviewer = "incident-reviewer"


class ClaudeHookEventName(StrEnum):
    task_created = "TaskCreated"
    task_completed = "TaskCompleted"
    stop_failure = "StopFailure"
    cwd_changed = "CwdChanged"
    file_changed = "FileChanged"
    worktree_create = "WorktreeCreate"
    worktree_remove = "WorktreeRemove"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def slugify_title(value: str) -> str:
    """Return a stable slug stem derived from an incident title."""
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return normalized.strip("-") or "incident"


class AlertPayload(BaseModel):
    """Canonical alert envelope ingested by CLI and API surfaces."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    severity: AlertSeverity
    title: str
    source: str
    reason: str
    score: float | None = None
    url: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=_utcnow)

    @field_validator("title", "source", "reason")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("field must not be empty")
        return stripped


class IncidentLane(BaseModel):
    """One worker lane attached to an incident."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    session_id: str
    session_name: str
    role: IncidentRole
    tool: str
    template_name: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class IncidentEvent(BaseModel):
    """Timeline event persisted on an incident record."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    at: datetime = Field(default_factory=_utcnow)
    kind: str
    source: str = "shoal"
    message: str
    data: dict[str, object] = Field(default_factory=dict)

    @field_validator("kind", "message")
    @classmethod
    def validate_event_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("field must not be empty")
        return stripped


class IncidentRecord(BaseModel):
    """Persistent incident record linked to sessions and timeline events."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    id: str
    slug: str
    status: IncidentStatus = IncidentStatus.active
    git_root: str = ""
    alert: AlertPayload
    supervisor_session_id: str = ""
    lanes: list[IncidentLane] = Field(default_factory=list)
    events: list[IncidentEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class IncidentIngestRequest(BaseModel):
    """Shared ingest contract for CLI and API incident creation."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    alert: AlertPayload
    path: str | None = None
    spawn_supervisor: bool = True
    tool: str | None = None
    template: str | None = None


class IncidentSpawnRequest(BaseModel):
    """Shared contract for spawning incident worker lanes."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    role: IncidentRole
    tool: str | None = None
    template: str | None = None
    name: str | None = None
    summary: str = ""


class IncidentHookEnvelope(BaseModel):
    """Minimal hook payload Shoal records for Claude lifecycle events."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    event_name: ClaudeHookEventName
    session_id: str
    incident_id: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)
