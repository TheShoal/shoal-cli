"""Session action and approval model for the Shoal Agent Bus."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

ActionType = Literal[
    "merge_branch",
    "run_release",
    "edit_protected_path",
    "escalate",
    "request_human_approval",
    "custom",
]


class ActionStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    expired = "expired"
    cancelled = "cancelled"
    executed = "executed"
    failed = "failed"


class SessionAction(BaseModel):
    """An action request that requires explicit approval before execution.

    Actions are distinct from ordinary Agent Bus messages: they represent
    privileged operations and carry an explicit approval lifecycle.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    id: int | None = None
    requester_session: str
    target_session: str | None = None
    target_role: str | None = None
    action_type: str  # ActionType literal or custom string
    payload_json: str
    correlation_id: str | None = None
    status: ActionStatus = ActionStatus.pending
    requested_at: datetime | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    decision_reason: str | None = None
    metadata_json: str | None = None
