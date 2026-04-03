"""Agent Bus message envelope model."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

MessageKind = Literal[
    "event",
    "request",
    "response",
    "handoff",
    "approval_request",
    "approval_decision",
    "error",
]

DEFAULT_KIND: MessageKind = "event"
DEFAULT_PRIORITY: int = 3


class MessageEnvelope(BaseModel):
    """Full Agent Bus message envelope.

    The minimal fields (from_session, to_session, topic, payload) match the
    original schema.  All new fields have defaults so that legacy messages
    round-trip without error.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")
    id: int | None = None
    from_session: str
    to_session: str
    topic: str
    kind: MessageKind = DEFAULT_KIND
    payload: str
    correlation_id: str | None = None
    reply_to_message_id: int | None = None
    priority: int = Field(default=DEFAULT_PRIORITY, ge=1, le=5)
    requires_ack: bool = False
    metadata_json: str | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None
    consumed_at: datetime | None = None
    acked_at: datetime | None = None
