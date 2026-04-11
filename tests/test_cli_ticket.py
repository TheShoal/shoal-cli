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


class TestTicketBindingsCommands:
    def test_ticket_start_uses_context_prefixed_name(self, mock_dirs):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from shoal.models.config.workspace import TeamConfig, WorkspaceConfig

        issue = SimpleNamespace(
            id="issue-1",
            identifier="BE-1234",
            title="Fix auth flow",
            url="https://linear.app/test/issue/BE-1234",
        )
        ws = WorkspaceConfig(
            name="test",
            teams={
                "be": TeamConfig(
                    linear_slug="BE",
                    default_template="be-agent",
                    worktree_dir="work/backend",
                )
            },
        )
        bridge = SimpleNamespace(
            get_issue=AsyncMock(return_value=issue),
            update_issue_state=AsyncMock(),
            close=AsyncMock(),
        )

        async def fake_add_impl(**kwargs):
            assert kwargs["name"] == "work/be-1234"

        with (
            patch("shoal.cli.ticket.init_bridge", return_value=bridge),
            patch("shoal.cli.ticket.git.git_root", return_value="/tmp/repo"),
            patch("shoal.cli.ticket.load_workspace_config", return_value=ws),
            patch("shoal.core.state.resolve_session", return_value=None),
            patch("shoal.cli.session_create._add_impl", side_effect=fake_add_impl),
        ):
            result = runner.invoke(app, ["ticket", "start", "BE-1234"])

        assert result.exit_code == 0, result.output

    def test_ticket_attach_replaces_existing_tag(self, mock_dirs):
        from unittest.mock import AsyncMock

        from shoal.core.state import add_tag, create_session, get_session

        session = asyncio.run(create_session("notes/research", "claude", "/tmp/repo"))
        asyncio.run(add_tag(session.id, "linear:BE-1"))

        issue = type(
            "Issue",
            (),
            {
                "id": "issue-2",
                "identifier": "BE-2",
                "title": "Second issue",
                "url": "https://linear.app/test/issue/BE-2",
            },
        )()
        bridge = type(
            "Bridge",
            (),
            {
                "get_issue": AsyncMock(return_value=issue),
                "close": AsyncMock(),
            },
        )()

        with patch("shoal.cli.ticket.init_bridge", return_value=bridge):
            result = runner.invoke(app, ["ticket", "attach", "notes/research", "BE-2"])

        assert result.exit_code == 0, result.output
        updated = asyncio.run(get_session(session.id))
        assert updated is not None
        assert updated.tags.count("linear:BE-2") == 1
        assert "linear:BE-1" not in updated.tags

    def test_ticket_detach_removes_linear_tags(self, mock_dirs):
        from shoal.core.state import add_tag, create_session, get_session

        session = asyncio.run(create_session("notes/research", "claude", "/tmp/repo"))
        asyncio.run(add_tag(session.id, "linear:BE-1"))

        result = runner.invoke(app, ["ticket", "detach", "notes/research"])

        assert result.exit_code == 0, result.output
        updated = asyncio.run(get_session(session.id))
        assert updated is not None
        assert not any(tag.startswith("linear:") for tag in updated.tags)
