"""Integration test for the fins-template contract-v1 scaffold."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shoal.cli import app

runner = CliRunner()


@pytest.mark.integration
def test_fins_template_scaffold_contract_v1_roundtrip(tmp_path: Path) -> None:
    shoal_root = Path(__file__).resolve().parents[2]
    template_root = shoal_root / "fins-template"
    bootstrap_script = template_root / "scripts" / "bootstrap.fish"

    if not template_root.exists() or not bootstrap_script.exists():
        pytest.skip("fins-template repo not available for cross-repo integration test")
    if shutil.which("fish") is None:
        pytest.skip("fish shell is required for fins-template bootstrap")

    fin_name = "contract-guard-fin"
    bootstrap = subprocess.run(
        ["fish", str(bootstrap_script), fin_name, str(tmp_path)],
        cwd=template_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert bootstrap.returncode == 0, bootstrap.stderr or bootstrap.stdout

    fin_root = tmp_path / fin_name

    inspect_result = runner.invoke(app, ["fin", "inspect", str(fin_root)])
    assert inspect_result.exit_code == 0
    inspect_payload = json.loads(inspect_result.stdout)
    assert inspect_payload["name"] == fin_name
    assert inspect_payload["fin_contract_version"] == 1

    validate_result = runner.invoke(app, ["fin", "validate", str(fin_root), "--strict"])
    assert validate_result.exit_code == 0
    assert "validate: checks passed" in validate_result.stdout

    run_result = runner.invoke(
        app,
        ["fin", "run", str(fin_root), "--output", "json", "--", "sample-action"],
    )
    assert run_result.exit_code == 0
    run_payload = json.loads(run_result.stdout)
    assert run_payload["capability"] == f"{fin_name}.capability"
    assert run_payload["action"] == "sample-action"
    assert run_payload["status"] == "success"
