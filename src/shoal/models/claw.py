"""Pydantic models for the claw scheduler subsystem."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ClawTaskStatus(StrEnum):
    """Lifecycle status of a claw task."""

    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    dead_letter = "dead_letter"
    cancelled = "cancelled"


class ClawTaskType(StrEnum):
    """Scheduling mode for a claw task."""

    once = "once"
    recurring = "recurring"
    cron = "cron"


class TaskResult(StrEnum):
    """Outcome of a task handler execution."""

    succeeded = "succeeded"
    retryable_failure = "retryable_failure"
    permanent_failure = "permanent_failure"


class SummaryBudget(StrEnum):
    """Controls how much text the summarizer should produce."""

    paragraph = "paragraph"
    short = "short"
    headline = "headline"


class ClawTask(BaseModel):
    """A scheduled task in the claw subsystem."""

    model_config = ConfigDict(extra="forbid")

    id: int
    session: str | None = None
    task_type: ClawTaskType = ClawTaskType.once
    name: str
    handler: str
    cron_expr: str | None = None
    interval_seconds: float | None = None
    payload_json: str = "{}"
    run_at: str
    status: ClawTaskStatus = ClawTaskStatus.pending
    retry_count: int = 0
    max_retries: int = 3
    correlation_id: str | None = None
    created_at: str
    last_run_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    metadata_json: str | None = None
