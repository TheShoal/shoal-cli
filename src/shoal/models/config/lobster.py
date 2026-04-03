"""Lobster runtime configuration models."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class LobsterConfig(BaseModel):
    """Configuration for Lobster runtime provider.

    Attributes:
        known_lobsters: Dictionary mapping lobster_id to endpoint URL for known Lobsters.
            Example: {"claw_abc123": "grpc://claw-abc123.lobster-party-runtime.svc:50051"}
        grpc_addr: Fallback gRPC endpoint used when a lobster_id is not found in
            ``known_lobsters`` (single-Lobster setups).  Prefer ``known_lobsters`` for
            multi-Lobster deployments.
        employee_id: Employee ID injected into A2A gRPC call metadata and
            legacy Turn request payloads for audit purposes.
        default_timeout: Default timeout in seconds for gRPC calls.
        retry_attempts: Number of retry attempts for failed gRPC calls.
        conversations_dir: Local path to the Lobster conversations directory used
            for QMD sync (e.g. ``~/.lobster/conversations``).  When set, this
            path is used as the default for ``shoal handoff --sync-claw``.
    """

    known_lobsters: dict[str, str] = Field(default_factory=dict)
    grpc_addr: str = ""
    employee_id: str = ""
    default_timeout: float = 30.0
    retry_attempts: int = 3
    conversations_dir: Path | None = None
