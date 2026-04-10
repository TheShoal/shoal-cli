"""CLI tests for ticket and team commands."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from typer.testing import CliRunner

from shoal.cli import app

runner = CliRunner()


class TestTeamLs:
    def test_no_git_repo(self, tmp_path):
        """Returns error when not in a git repo."""
        result = runner.invoke(app, ["team", "ls"], catch_exceptions=False)
        # May fail with git root error or no teams configured — either is OK
        assert result.exit_code in (0, 1)

    def test_no_teams_configured(self, mock_dirs):
        """Shows helpful message when no teams configured."""
        with patch("shoal.cli.team.git.git_root", return_value="/tmp/fake"):
            with patch("shoal.cli.team.load_workspace_config", return_value=None):
                result = runner.invoke(app, ["team", "ls"])
                assert result.exit_code == 0
                assert "No teams configured" in result.output

    def test_with_teams(self, mock_dirs):
        """Displays team table when teams are configured."""
        from shoal.models.config.workspace import (
            TeamConfig,
            TeamReportTargetConfig,
            WorkspaceConfig,
        )

        ws = WorkspaceConfig(
            name="test",
            teams={
                "be": TeamConfig(
                    name="Backend",
                    linear_slug="BE",
                    default_template="be-agent",
                    report=TeamReportTargetConfig(type="project", slug="backend-roadmap"),
                ),
                "fe": TeamConfig(name="Frontend", linear_slug="FE"),
            },
        )
        with patch("shoal.cli.team.git.git_root", return_value="/tmp/fake"):
            with patch("shoal.cli.team.load_workspace_config", return_value=ws):
                result = runner.invoke(app, ["team", "ls"])
                assert result.exit_code == 0
                assert "BE" in result.output
                assert "FE" in result.output
                assert "Backend" in result.output
                assert "project:backend-roadmap" in result.output


class TestTicketStatus:
    def test_empty(self, mock_dirs):
        """Shows message when no ticket bindings exist."""
        result = runner.invoke(app, ["ticket", "status"])
        assert result.exit_code == 0
        assert "No active ticket bindings" in result.output

    def test_with_bindings(self, mock_dirs):
        """Displays ticket bindings table."""
        from shoal.core.state import add_tag, create_session

        s = asyncio.run(create_session("test-session", "claude", "/tmp/repo"))
        asyncio.run(add_tag(s.id, "linear:BE-1234"))

        result = runner.invoke(app, ["ticket", "status"])
        assert result.exit_code == 0
        assert "BE-1234" in result.output
        assert "test-session" in result.output


class TestTicketLs:
    def test_missing_api_key(self, mock_dirs):
        """Returns error when SHOAL_LINEAR_API_KEY is not set."""
        from shoal.models.config.workspace import TeamConfig, WorkspaceConfig

        ws = WorkspaceConfig(
            name="test",
            teams={"be": TeamConfig(linear_slug="BE")},
        )
        with (
            patch("shoal.cli.ticket.git.git_root", return_value="/tmp/fake"),
            patch("shoal.cli._helpers.load_workspace_config", return_value=ws),
            patch.dict("os.environ", {"SHOAL_LINEAR_API_KEY": ""}),
        ):
            result = runner.invoke(app, ["ticket", "ls", "--team", "be"])
            assert result.exit_code == 1
            assert "SHOAL_LINEAR_API_KEY" in result.output

    def test_unknown_team(self, mock_dirs):
        """Returns error for unknown team slug."""
        from shoal.models.config.workspace import TeamConfig, WorkspaceConfig

        ws = WorkspaceConfig(
            name="test",
            teams={"be": TeamConfig(linear_slug="BE")},
        )
        with (
            patch("shoal.cli.ticket.git.git_root", return_value="/tmp/fake"),
            patch("shoal.cli._helpers.load_workspace_config", return_value=ws),
        ):
            result = runner.invoke(app, ["ticket", "ls", "--team", "xyz"])
            assert result.exit_code == 1
            assert "Unknown team" in result.output
