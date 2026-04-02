"""Claw runtime configuration models."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class ClawConfig(BaseModel):
    """Configuration for Claw runtime provider.

    Attributes:
        known_claws: Dictionary mapping claw_id to endpoint URL for known Claws.
            Example: {"claw_abc123": "grpc://claw-abc123.lobster-party-runtime.svc:50051"}
        default_timeout: Default timeout in seconds for gRPC calls.
        retry_attempts: Number of retry attempts for failed gRPC calls.
        conversations_dir: Local path to the Claw conversations directory used
            for QMD sync (e.g. ``~/.lobster/conversations``).  When set, this
            path is used as the default for ``shoal handoff --sync-claw``.
    """

    known_claws: dict[str, str] = Field(default_factory=dict)
    default_timeout: float = 30.0
    retry_attempts: int = 3
    conversations_dir: Path | None = None
