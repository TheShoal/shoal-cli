"""Tests for fin remote install: FinSource model and _download_fin/_registry_url helpers."""

from __future__ import annotations

import tarfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shoal.models.fin import FinSource, _download_fin, _registry_url

# ---------------------------------------------------------------------------
# FinSource.parse classification
# ---------------------------------------------------------------------------


def test_parse_local_path() -> None:
    src = FinSource.parse("./my-fin")
    assert src.kind == "local"
    assert src.raw == "./my-fin"


def test_parse_local_absolute_path() -> None:
    src = FinSource.parse("/home/user/fins/my-fin")
    assert src.kind == "local"


def test_parse_https_url() -> None:
    src = FinSource.parse("https://example.com/my-fin.tar.gz")
    assert src.kind == "http"
    assert src.raw == "https://example.com/my-fin.tar.gz"


def test_parse_http_url() -> None:
    src = FinSource.parse("http://example.com/my-fin.zip")
    assert src.kind == "http"


def test_parse_registry_with_version() -> None:
    src = FinSource.parse("fin:my-fin@1.0.0")
    assert src.kind == "registry"
    assert src.raw == "fin:my-fin@1.0.0"


def test_parse_registry_without_version() -> None:
    src = FinSource.parse("fin:my-fin")
    assert src.kind == "registry"


# ---------------------------------------------------------------------------
# _registry_url helper
# ---------------------------------------------------------------------------


def test_registry_url_with_version() -> None:
    url = _registry_url("fin:my-fin@2.0", "https://fins.shoal.dev")
    assert url == "https://fins.shoal.dev/my-fin/2.0.tar.gz"


def test_registry_url_without_version_defaults_to_latest() -> None:
    url = _registry_url("fin:my-fin", "https://fins.shoal.dev")
    assert url == "https://fins.shoal.dev/my-fin/latest.tar.gz"


def test_registry_url_empty_version_defaults_to_latest() -> None:
    url = _registry_url("fin:my-fin@", "https://fins.shoal.dev")
    assert url == "https://fins.shoal.dev/my-fin/latest.tar.gz"


def test_registry_url_strips_trailing_slash() -> None:
    url = _registry_url("fin:my-fin@1.0", "https://fins.shoal.dev/")
    assert url == "https://fins.shoal.dev/my-fin/1.0.tar.gz"


# ---------------------------------------------------------------------------
# FinSource.resolve dispatch
# ---------------------------------------------------------------------------


def test_resolve_local_returns_path() -> None:
    src = FinSource.parse("./my-fin")
    assert src.resolve() == Path("./my-fin")


def test_resolve_http_calls_download(tmp_path: Path) -> None:
    src = FinSource.parse("https://example.com/my-fin.tar.gz")
    with patch("shoal.models.fin._download_fin", return_value=tmp_path) as mock_dl:
        result = src.resolve()
    mock_dl.assert_called_once_with("https://example.com/my-fin.tar.gz")
    assert result == tmp_path


def test_resolve_registry_builds_url_and_downloads(tmp_path: Path) -> None:
    src = FinSource.parse("fin:my-fin@1.0.0")
    with patch("shoal.models.fin._download_fin", return_value=tmp_path) as mock_dl:
        result = src.resolve(registry_url="https://fins.shoal.dev")
    mock_dl.assert_called_once_with("https://fins.shoal.dev/my-fin/1.0.0.tar.gz")
    assert result == tmp_path


# ---------------------------------------------------------------------------
# _download_fin
# ---------------------------------------------------------------------------


def _make_tar_gz(dest: Path, inner_name: str = "fin.toml") -> Path:
    """Create a minimal .tar.gz archive for testing."""
    archive = dest / "my-fin.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        info = tarfile.TarInfo(name=inner_name)
        info.size = 0
        import io
        tf.addfile(info, io.BytesIO(b""))
    return archive


def test_download_fin_unsupported_extension() -> None:
    with pytest.raises(ValueError, match="Unsupported archive extension"):
        _download_fin("https://example.com/my-fin.tar.bz2")


def test_download_fin_extracts_tar_gz(tmp_path: Path) -> None:
    """_download_fin downloads, extracts, and returns path to extracted dir."""
    import io

    # Build a minimal tar.gz in memory
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo(name="fin.toml")
        content = b"name = 'test'\n"
        info.size = len(content)
        tf.addfile(info, io.BytesIO(content))
    buf.seek(0)
    archive_bytes = buf.read()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.content = archive_bytes

    xdg_home = tmp_path / "xdg"
    with (
        patch("httpx.get", return_value=mock_response),
        patch.dict("os.environ", {"XDG_DATA_HOME": str(xdg_home)}),
    ):
        result = _download_fin("https://example.com/my-fin.tar.gz")

    assert result.is_dir()
    assert result.name == "my-fin"
    assert (result / "fin.toml").exists()


def test_download_fin_overwrites_existing(tmp_path: Path) -> None:
    """Re-downloading clears the previous extraction."""
    import io

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo(name="fin.toml")
        content = b""
        info.size = 0
        tf.addfile(info, io.BytesIO(content))
    buf.seek(0)

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.content = buf.read()

    xdg_home = tmp_path / "xdg"

    # First install — plant a stale file
    stale_dest = xdg_home / "shoal" / "fins" / "_downloads" / "my-fin"
    stale_dest.mkdir(parents=True)
    (stale_dest / "stale.txt").write_text("old")

    with (
        patch("httpx.get", return_value=mock_response),
        patch.dict("os.environ", {"XDG_DATA_HOME": str(xdg_home)}),
    ):
        result = _download_fin("https://example.com/my-fin.tar.gz")

    assert not (result / "stale.txt").exists(), "Stale file should be removed on re-download"


# ---------------------------------------------------------------------------
# install_fin with HTTP source — integration path via FinSource
# ---------------------------------------------------------------------------


def test_install_fin_with_http_source(tmp_path: Path) -> None:
    """install_fin delegates to FinSource.resolve for non-local sources."""
    from shoal.services.fin_runtime import install_fin

    local_fin = tmp_path / "resolved-fin"
    local_fin.mkdir()

    with (
        patch("shoal.models.fin.FinSource.resolve", return_value=local_fin),
        patch("shoal.services.fin_runtime.load_fin_manifest") as mock_manifest,
        patch("shoal.services.fin_runtime.resolve_entrypoint", return_value=local_fin / "bin" / "install"),
        patch("shoal.services.fin_runtime.execute_entrypoint") as mock_exec,
        patch("shoal.services.fin_runtime.register_fin"),
    ):
        from shoal.models.fin import FinEntrypoints, FinManifest
        manifest = FinManifest(
            name="test-fin",
            version="1.0.0",
            fin_contract_version=1,
            capability="test",
            entrypoints=FinEntrypoints(
                install="bin/install",
                configure="bin/configure",
                run="bin/run",
                validate="bin/validate",
            ),
        )
        mock_manifest.return_value = (local_fin, manifest)
        from shoal.services.fin_runtime import FinExecutionResult
        mock_exec.return_value = FinExecutionResult(exit_code=0, stdout="", stderr="")

        result = install_fin("https://example.com/test-fin.tar.gz")

    assert result.exit_code == 0
