"""Fin repository and download services."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from shoal.models.fin import FinSource


def registry_url(raw: str, registry_url: str) -> str:
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


def download_fin(url: str) -> Path:
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
    import httpx

    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=30) as response:
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False, suffix=filename) as tmp:
                for chunk in response.iter_bytes():
                    tmp.write(chunk)
                tmp_path = Path(tmp.name)
    except httpx.HTTPStatusError as exc:
        raise ValueError(
            f"Failed to download fin: HTTP {exc.response.status_code} from {url}"
        ) from exc
    except httpx.HTTPError as exc:
        raise ValueError(f"Failed to download fin: {exc}") from exc

    extract_dir = dest.parent / f"{dest.name}.tmp"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True)

    try:
        shutil.unpack_archive(tmp_path, extract_dir)
        if dest.exists():
            shutil.rmtree(dest)
        extract_dir.rename(dest)
    finally:
        tmp_path.unlink(missing_ok=True)
        if extract_dir.exists():
            shutil.rmtree(extract_dir)

    return dest


def resolve_fin(source: FinSource, registry_base_url: str = "https://fins.shoal.dev") -> Path:
    """Resolve source to a local path, downloading if needed.

    Args:
        source: The fin source to resolve.
        registry_base_url: Base URL for the fin registry (used for ``registry`` kind).

    Returns:
        Path to the (possibly just-downloaded) fin directory.

    Raises:
        ValueError: If ``kind`` is unrecognised.
    """
    if source.kind == "local":
        return Path(source.raw)
    if source.kind == "http":
        return download_fin(source.raw)
    if source.kind == "registry":
        url = registry_url(source.raw, registry_base_url)
        return download_fin(url)
    raise ValueError(f"Unknown source kind: {source.kind}")
