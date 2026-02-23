"""Tests for shoal diag command."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from shoal.cli import app

runner = CliRunner()


class TestDiagCommand:
    def test_diag_runs(self) -> None:
        with (
            patch("shoal.cli.diag._check_db", return_value=(True, "10.0 KB")),
            patch("shoal.cli.diag._check_watcher", return_value=(False, "not running")),
            patch("shoal.cli.diag._check_tmux", return_value=(True, "2 session(s)")),
            patch("shoal.cli.diag._check_mcp_sockets", return_value=(True, "1 socket(s)")),
        ):
            result = runner.invoke(app, ["diag"])
        assert result.exit_code == 0
        assert "database" in result.output

    def test_diag_json(self) -> None:
        with (
            patch("shoal.cli.diag._check_db", return_value=(True, "10.0 KB")),
            patch("shoal.cli.diag._check_watcher", return_value=(True, "pid 1234")),
            patch("shoal.cli.diag._check_tmux", return_value=(True, "2 session(s)")),
            patch("shoal.cli.diag._check_mcp_sockets", return_value=(True, "0 sockets")),
        ):
            result = runner.invoke(app, ["diag", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "healthy"
        assert data["database"]["healthy"] is True

    def test_diag_json_degraded(self) -> None:
        with (
            patch("shoal.cli.diag._check_db", return_value=(False, "not found")),
            patch("shoal.cli.diag._check_watcher", return_value=(False, "not running")),
            patch("shoal.cli.diag._check_tmux", return_value=(False, "not reachable")),
            patch("shoal.cli.diag._check_mcp_sockets", return_value=(True, "0 sockets")),
        ):
            result = runner.invoke(app, ["diag", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "degraded"
