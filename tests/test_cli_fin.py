"""Tests for fin CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from shoal.cli import app

runner = CliRunner()


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def _create_fin(tmp_path: Path, *, run_exit: int = 0) -> Path:
    fin_root = tmp_path / "cli-fin"
    bin_dir = fin_root / "bin"
    bin_dir.mkdir(parents=True)

    (fin_root / "fin.toml").write_text(
        """
name = "cli-fin"
version = "0.1.0"
fin_contract_version = 1
capability = "demo.capability"

[entrypoints]
install = "bin/install"
configure = "bin/configure"
run = "bin/run"
validate = "bin/validate"
""".strip()
        + "\n"
    )

    _write_executable(bin_dir / "install", "#!/bin/sh\nexit 0\n")
    _write_executable(bin_dir / "configure", "#!/bin/sh\nexit 0\n")
    _write_executable(
        bin_dir / "validate",
        '#!/bin/sh\nif [ "$1" = "--strict" ]; then echo strict; fi\nexit 0\n',
    )
    _write_executable(
        bin_dir / "run",
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        'print(json.dumps({"args": sys.argv[1:], "config": os.getenv("SHOAL_FIN_CONFIG")}))\n'
        f"sys.exit({run_exit})\n",
    )

    return fin_root


def test_fin_inspect_outputs_manifest(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    result = runner.invoke(app, ["fin", "inspect", str(fin_root)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["name"] == "cli-fin"
    assert payload["fin_contract_version"] == 1
    assert payload["capability"] == "demo.capability"


def test_fin_validate_strict(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    result = runner.invoke(app, ["fin", "validate", str(fin_root), "--strict"])
    assert result.exit_code == 0
    assert "strict" in result.stdout


def test_fin_run_passthrough_args(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    cfg = tmp_path / "fin.env"
    cfg.write_text("KEY=VALUE\n")

    result = runner.invoke(
        app,
        ["fin", "run", str(fin_root), "--config", str(cfg), "--", "hello", "world"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["args"] == ["hello", "world"]
    assert payload["config"] == str(cfg.resolve())


def test_fin_run_preserves_exit_code(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path, run_exit=7)
    result = runner.invoke(app, ["fin", "run", str(fin_root)])
    assert result.exit_code == 7
