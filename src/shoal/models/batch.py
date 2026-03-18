"""Shared models for Shoal batch execution and session snapshots."""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BatchError(BaseModel):
    """Structured per-item error for batch execution."""

    code: str
    message: str

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class BatchItemResult(BaseModel):
    """Per-item batch execution result envelope."""

    index: int
    op: str
    session: str | None = None
    success: bool
    result: object | None = None
    error: BatchError | None = None

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class SessionInfoBatchOp(BaseModel):
    op: Literal["session_info"]
    session: str

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class SessionStatusBatchOp(BaseModel):
    op: Literal["session_status"]
    session: str | None = None

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class CapturePaneBatchOp(BaseModel):
    op: Literal["capture_pane"]
    session: str
    lines: int = Field(default=20, ge=1, le=500)

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class SendKeysBatchOp(BaseModel):
    op: Literal["send_keys"]
    session: str
    keys: str
    enter: bool | None = None

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class KillSessionBatchOp(BaseModel):
    op: Literal["kill_session"]
    session: str
    remove_worktree: bool = False
    force: bool = False

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class ReadHistoryBatchOp(BaseModel):
    op: Literal["read_history"]
    session: str
    limit: int = Field(default=50, ge=1, le=500)

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class ReadJournalBatchOp(BaseModel):
    op: Literal["read_journal"]
    session: str
    limit: int = Field(default=10, ge=1, le=500)

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class AppendJournalBatchOp(BaseModel):
    op: Literal["append_journal"]
    session: str
    entry: str
    source: str = "mcp"

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


type BatchOperation = Annotated[
    (
        SessionInfoBatchOp
        | SessionStatusBatchOp
        | CapturePaneBatchOp
        | SendKeysBatchOp
        | KillSessionBatchOp
        | ReadHistoryBatchOp
        | ReadJournalBatchOp
        | AppendJournalBatchOp
    ),
    Field(discriminator="op"),
]


class BatchExecutionRequest(BaseModel):
    """Mixed-operation batch request."""

    ops: list[BatchOperation] = Field(min_length=1)
    continue_on_error: bool = True
    max_parallelism: int = Field(default=8, ge=1, le=32)

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class BatchExecutionResponse(BaseModel):
    """Mixed-operation batch response."""

    results: list[BatchItemResult]

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


type SnapshotField = Literal[
    "status",
    "pane_tail",
    "mcp_servers",
    "last_activity",
    "status_since",
    "tool",
    "path",
    "branch",
    "worktree",
    "pid",
    "created_at",
    "runtime",
]


def _default_snapshot_fields() -> list[SnapshotField]:
    return ["status", "pane_tail", "mcp_servers", "last_activity"]


class SessionSnapshotRequest(BaseModel):
    """Aggregate multi-session read request optimized for supervisors."""

    sessions: list[str] = Field(min_length=1)
    fields: list[SnapshotField] = Field(default_factory=_default_snapshot_fields)
    pane_lines: int = Field(default=20, ge=1, le=500)
    max_parallelism: int = Field(default=8, ge=1, le=32)

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    @field_validator("fields")
    @classmethod
    def dedupe_fields(cls, value: list[SnapshotField]) -> list[SnapshotField]:
        return list(dict.fromkeys(value))


class SessionSnapshotItem(BaseModel):
    """Per-session snapshot result envelope."""

    session: str
    success: bool
    result: dict[str, object] | None = None
    error: BatchError | None = None

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class SessionSnapshotResponse(BaseModel):
    """Supervisor-friendly multi-session snapshot response."""

    results: list[SessionSnapshotItem]

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")
