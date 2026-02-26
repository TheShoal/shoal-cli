"""Tests for services/fin_runtime.py."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from shoal.services.fin_runtime import (
    FinRuntimeError,
    configure_fin,
    install_fin,
    list_fins,
    load_fin_manifest,
    run_fin,
    validate_fin,
)


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def _create_fin(tmp_path: Path) -> Path:
    fin_root = tmp_path / "example-fin"
    bin_dir = fin_root / "bin"
    bin_dir.mkdir(parents=True)

    (fin_root / "fin.toml").write_text(
        """
name = "example-fin"
version = "0.1.0"
fin_contract_version = 1
capability = "example.capability"

[entrypoints]
install = "bin/install"
configure = "bin/configure"
run = "bin/run"
validate = "bin/validate"
""".strip()
        + "\n"
    )

    _write_executable(
        bin_dir / "install",
        "#!/bin/sh\necho install-ok\nexit 0\n",
    )
    _write_executable(
        bin_dir / "configure",
        '#!/bin/sh\necho "configure:$SHOAL_FIN_CONFIG"\nexit 0\n',
    )
    _write_executable(
        bin_dir / "validate",
        '#!/bin/sh\nif [ "$1" = "--strict" ]; then echo strict-ok; fi\nexit 0\n',
    )
    _write_executable(
        bin_dir / "run",
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "payload = {\n"
        '  "args": sys.argv[1:],\n'
        '  "root": os.environ.get("SHOAL_FIN_ROOT"),\n'
        '  "config": os.environ.get("SHOAL_FIN_CONFIG"),\n'
        '  "format": os.environ.get("SHOAL_OUTPUT_FORMAT"),\n'
        '  "log_level": os.environ.get("SHOAL_LOG_LEVEL"),\n'
        "}\n"
        "print(json.dumps(payload))\n"
        "sys.exit(0)\n",
    )

    return fin_root


def test_load_manifest_from_root(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    root, manifest = load_fin_manifest(fin_root)
    assert root == fin_root
    assert manifest.name == "example-fin"
    assert manifest.fin_contract_version == 1


def test_load_manifest_rejects_wrong_contract(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    manifest_path = fin_root / "fin.toml"
    manifest_path.write_text(
        manifest_path.read_text().replace("fin_contract_version = 1", "fin_contract_version = 2")
    )

    with pytest.raises(FinRuntimeError, match="Unsupported fin_contract_version"):
        load_fin_manifest(fin_root)


def test_validate_fin_passes_strict_flag(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    result = validate_fin(fin_root, strict=True)
    assert result.exit_code == 0
    assert "strict-ok" in result.stdout


def test_install_fin_executes_install_entrypoint(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    result = install_fin(fin_root)
    assert result.exit_code == 0
    assert "install-ok" in result.stdout


def test_configure_fin_passes_config_env(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    cfg = tmp_path / "fin.env"
    cfg.write_text("KEY=VALUE\n")
    result = configure_fin(fin_root, config_path=str(cfg))
    assert result.exit_code == 0
    assert f"configure:{cfg.resolve()}" in result.stdout


def test_run_fin_passes_args_and_env(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    cfg = tmp_path / "fin.env"
    cfg.write_text("KEY=VALUE\n")

    result = run_fin(
        fin_root,
        config_path=str(cfg),
        output_format="json",
        args=["hello", "world"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["args"] == ["hello", "world"]
    assert payload["root"] == str(fin_root)
    assert payload["config"] == str(cfg.resolve())
    assert payload["format"] == "json"


def test_run_fin_includes_shoal_log_level(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    logger = logging.getLogger("shoal")
    original_level = logger.level
    try:
        logger.setLevel(logging.WARNING)
        result = run_fin(fin_root, config_path=None, output_format="json", args=[])
    finally:
        logger.setLevel(original_level)

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["log_level"] == "WARNING"


def test_run_fin_non_executable_entrypoint_fails(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    run_path = fin_root / "bin" / "run"
    run_path.chmod(0o644)

    with pytest.raises(FinRuntimeError, match="not executable"):
        run_fin(fin_root, config_path=None, output_format="text", args=[])


def test_list_fins_reports_valid_and_invalid(tmp_path: Path) -> None:
    valid_root = _create_fin(tmp_path)
    invalid_root = tmp_path / "broken-fin"
    invalid_root.mkdir(parents=True)
    (invalid_root / "fin.toml").write_text("name = 'broken'\n")

    items = list_fins(tmp_path)
    by_root = {item.root: item for item in items}

    valid = by_root[str(valid_root)]
    assert valid.status == "valid"
    assert valid.name == "example-fin"

    invalid = by_root[str(invalid_root)]
    assert invalid.status == "invalid"
    assert invalid.error is not None
    assert "Invalid manifest" in invalid.error
