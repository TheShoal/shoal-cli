"""Shared models for runtime providers."""

from __future__ import annotations

from pydantic import BaseModel

from shoal.models.state import AnyRuntimeState


class RuntimeObservation(BaseModel):
    """Latest provider-owned observation for a session runtime."""

    alive: bool
    output: str = ""
    pid: int | None = None
    runtime: AnyRuntimeState
