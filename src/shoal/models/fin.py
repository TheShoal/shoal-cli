"""Pydantic models for fin contract manifests."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FinEntrypoints(BaseModel):
    """Lifecycle wrapper paths declared in ``fin.toml``."""

    model_config = ConfigDict(extra="forbid")

    install: str
    configure: str
    run: str
    validate_entrypoint: str = Field(alias="validate")


class FinManifest(BaseModel):
    """Contract-v1 fin manifest."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    fin_contract_version: int
    capability: str
    entrypoints: FinEntrypoints
