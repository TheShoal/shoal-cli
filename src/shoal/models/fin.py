"""Pydantic models for fin contract manifests."""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Literal

import httpx
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


def _registry_url(raw: str, registry_url: str) -> str:
    """Convert a ``fin:<name>[@<version>]`` shorthand to a registry download URL.

    Args:
        raw: Source string starting with ``fin:``.
        registry_url: Registry base URL (no trailing slash required).

    Returns:
        Full URL pointing to the versioned ``.tar.gz`` archive.
    """
    # Strip the "fin:" prefix
    spec = raw[len("fin:") :]
    if "@" in spec:
        name, _, version = spec.partition("@")
        version = version or "latest"
    else:
        name = spec
        version = "latest"
    return f"{registry_url.rstrip('/')}/{name}/{version}.tar.gz"


def _download_fin(url: str) -> Path:
    """Download a fin archive from *url* and extract it to a local cache directory.

    Only ``.tar.gz`` and ``.zip`` archives are accepted.  The archive is
    extracted into a deterministic subdirectory of the shoal downloads cache.
    If the destination already exists it is removed before re-extraction so
    re-installs always land a clean copy.

    Args:
        url: Direct download URL ending in ``.tar.gz`` or ``.zip``.

    Returns:
        Path to the extracted fin directory.

    Raises:
        ValueError: If the URL extension is not ``.tar.gz`` or ``.zip``.
    """
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    downloads_dir = data_home / "shoal" / "fins" / "_downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    filename = url.rstrip("/").split("/")[-1]

    if filename.endswith(".tar.gz"):
        stem = filename[: -len(".tar.gz")]
    elif filename.endswith(".zip"):
        stem = filename[: -len(".zip")]
    else:
        raise ValueError(
            f"Unsupported archive extension for fin download: {filename!r}. "
            "Expected .tar.gz or .zip"
        )

    dest = downloads_dir / stem
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    response = httpx.get(url, follow_redirects=True, timeout=30)
    response.raise_for_status()

    with tempfile.NamedTemporaryFile(delete=False, suffix=filename) as tmp:
        tmp.write(response.content)
        tmp_path = Path(tmp.name)

    try:
        if filename.endswith(".tar.gz"):
            with tarfile.open(tmp_path, "r:gz") as tf:
                tf.extractall(dest)  # noqa: S202  # nosec B202 — trusted fin registry source
        else:
            with zipfile.ZipFile(tmp_path) as zf:
                zf.extractall(dest)  # noqa: S202  # nosec B202 — trusted fin registry source
    finally:
        tmp_path.unlink(missing_ok=True)

    return dest


class FinSource(BaseModel):
    """Resolved source for a fin install."""

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

    def resolve(self, registry_url: str = "https://fins.shoal.dev") -> Path:
        """Resolve source to a local path, downloading if needed.

        Args:
            registry_url: Base URL for the fin registry (used for ``registry`` kind).

        Returns:
            Path to the (possibly just-downloaded) fin directory.

        Raises:
            ValueError: If ``kind`` is unrecognised (should never happen with
                a validated model).
        """
        if self.kind == "local":
            return Path(self.raw)
        if self.kind == "http":
            return _download_fin(self.raw)
        if self.kind == "registry":
            url = _registry_url(self.raw, registry_url)
            return _download_fin(url)
        raise ValueError(f"Unknown source kind: {self.kind}")
