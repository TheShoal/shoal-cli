"""Models for agent heartbeat (push status) requests."""

from __future__ import annotations

from pydantic import BaseModel, Field

from shoal.models.state import SessionStatus


class HeartbeatRequest(BaseModel):
    """Payload pushed by an agent at end-of-turn or after tool use."""

    status: SessionStatus
    summary: str = ""
    turn_number: int | None = None
    tool_name: str | None = None
    tool_result: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
