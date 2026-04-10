"""CLI tests for report commands."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from shoal.cli import app
from shoal.models.config.workspace import (
    TeamConfig,
    TeamReportTargetConfig,
    WorkspaceConfig,
)

runner = CliRunner()


def test_report_session_success(mock_dirs) -> None:
    """Session reports render markdown output."""
    with patch(
        "shoal.services.report.generate_session_report",
        new=AsyncMock(return_value="# Session Report: alpha\n\nBody"),
    ):
        result = runner.invoke(app, ["report", "session", "alpha"])

    assert result.exit_code == 0
    assert "Session Report: alpha" in result.output


def test_report_session_missing_session(mock_dirs) -> None:
    """Session report surfaces missing-session errors."""
    with patch(
        "shoal.services.report.generate_session_report",
        new=AsyncMock(side_effect=RuntimeError("Session not found: alpha")),
    ):
        result = runner.invoke(app, ["report", "session", "alpha"])

    assert result.exit_code == 1
    assert "Session not found: alpha" in result.output


def test_report_team_success(mock_dirs) -> None:
    """Team reports resolve team config and render markdown."""
    ws_cfg = WorkspaceConfig(
        name="test",
        teams={"be": TeamConfig(name="Backend", linear_slug="BE")},
    )
    with (
        patch("shoal.cli.report.git.git_root", return_value="/tmp/fake"),
        patch("shoal.cli._helpers.load_workspace_config", return_value=ws_cfg),
        patch(
            "shoal.services.report.generate_team_report",
            new=AsyncMock(return_value="# Backend Team Status\n\nTeam body"),
        ),
    ):
        result = runner.invoke(app, ["report", "team", "--team", "be"])

    assert result.exit_code == 0
    assert "Backend Team Status" in result.output


def test_report_sprint_unknown_team(mock_dirs) -> None:
    """Sprint reports fail clearly for unknown teams."""
    ws_cfg = WorkspaceConfig(
        name="test",
        teams={"be": TeamConfig(name="Backend", linear_slug="BE")},
    )
    with (
        patch("shoal.cli.report.git.git_root", return_value="/tmp/fake"),
        patch("shoal.cli._helpers.load_workspace_config", return_value=ws_cfg),
    ):
        result = runner.invoke(app, ["report", "sprint", "--team", "fe"])

    assert result.exit_code == 1
    assert "Unknown team 'fe'" in result.output


def test_report_sprint_post_success(mock_dirs) -> None:
    """Sprint reports can be posted to a configured Linear target."""
    ws_cfg = WorkspaceConfig(
        name="test",
        teams={
            "be": TeamConfig(
                name="Backend",
                linear_slug="BE",
                report=TeamReportTargetConfig(type="project", slug="backend-platform"),
            )
        },
    )
    posted = SimpleNamespace(
        report="# Cycle: BE current — Sprint Summary\n\nBody",
        target_kind="project",
        target_name="Backend Platform",
        update_url="https://linear.app/update/proj-1",
        health="onTrack",
    )
    with (
        patch("shoal.cli.report.git.git_root", return_value="/tmp/fake"),
        patch("shoal.cli._helpers.load_workspace_config", return_value=ws_cfg),
        patch("shoal.services.report.post_sprint_report", new=AsyncMock(return_value=posted)),
    ):
        result = runner.invoke(app, ["report", "sprint", "--team", "be", "--post"])

    assert result.exit_code == 0
    assert "Sprint Summary" in result.output
    assert "Posted project update (onTrack) to Backend Platform" in result.output


def test_report_sprint_post_requires_target(mock_dirs) -> None:
    """Posting requires a configured report target."""
    ws_cfg = WorkspaceConfig(
        name="test",
        teams={"be": TeamConfig(name="Backend", linear_slug="BE")},
    )
    with (
        patch("shoal.cli.report.git.git_root", return_value="/tmp/fake"),
        patch("shoal.cli._helpers.load_workspace_config", return_value=ws_cfg),
    ):
        result = runner.invoke(app, ["report", "sprint", "--team", "be", "--post"])

    assert result.exit_code == 1
    assert "has no [teams.be.report] target configured" in result.output
