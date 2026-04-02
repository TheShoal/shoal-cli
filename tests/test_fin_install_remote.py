"""Tests for fin remote install: FinSource parse classification and install_fin HTTP path.

Registry URL helpers and download logic are tested in test_services_fin_repo.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from shoal.models.fin import FinEntrypoints, FinManifest, FinSource
from shoal.services.fin_runtime import FinExecutionResult

# -- FinSource.parse classification ------------------------------------------


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


# -- install_fin: HTTP source delegates to fin_repo.resolve_fin --------------


def test_install_fin_with_http_source(tmp_path: Path) -> None:
    """install_fin delegates to fin_repo.resolve_fin for non-local sources."""
    from shoal.services.fin_runtime import install_fin

    local_fin = tmp_path / "resolved-fin"
    local_fin.mkdir()

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

    with (
        patch("shoal.services.fin_runtime._resolve_fin", return_value=local_fin),
        patch("shoal.services.fin_runtime.load_fin_manifest", return_value=(local_fin, manifest)),
        patch(
            "shoal.services.fin_runtime.resolve_entrypoint",
            return_value=local_fin / "bin" / "install",
        ),
        patch(
            "shoal.services.fin_runtime.execute_entrypoint",
            return_value=FinExecutionResult(exit_code=0, stdout="", stderr=""),
        ),
        patch("shoal.services.fin_runtime.register_fin"),
    ):
        result = install_fin("https://example.com/test-fin.tar.gz")

    assert result.exit_code == 0
