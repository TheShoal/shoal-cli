"""Pydantic models for fin contract manifests."""

from __future__ import annotations

from typing import Literal

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
    default_timeout_seconds: int | None = None
    entrypoints: FinEntrypoints


class FinSource(BaseModel):
    """Resolved source for a fin install.

    Use :func:`~shoal.services.fin_repo.resolve_fin` to download / resolve
    non-local sources to a local ``Path``.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["local", "http", "registry"]
    raw: str  # original input string

    @classmethod
    def parse(cls, source: str) -> FinSource:
        """Classify a source string into local/http/registry.

        Args:
            source: Raw user-supplied fin path or shorthand.

        Returns:
            ``FinSource`` with the appropriate ``kind``.
        """
        if source.startswith(("http://", "https://")):
            return cls(kind="http", raw=source)
        if source.startswith("fin:"):
            return cls(kind="registry", raw=source)
        return cls(kind="local", raw=source)
