"""CLI tests with typer.testing.CliRunner."""

import asyncio
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from shoal.cli import app

runner = CliRunner()


class TestVersion:
    def test_version_command(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "shoal 0.4.0" in result.output


class TestLs:
    def test_empty(self, mock_dirs):
        result = runner.invoke(app, ["ls"])
        assert result.exit_code == 0
        assert "No sessions" in result.output


class TestStatus:
    def test_empty(self, mock_dirs):
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "No active sessions" in result.output

    def test_st_alias(self, mock_dirs):
        result = runner.invoke(app, ["st"])
        assert result.exit_code == 0
        assert "No active sessions" in result.output


class TestAdd:
    def test_missing_git_repo(self, mock_dirs, tmp_path):
        result = runner.invoke(app, ["add", str(tmp_path)])
        assert result.exit_code == 1
        assert "Not a git repository" in result.output

    def test_unknown_tool(self, mock_dirs, tmp_path):
        result = runner.invoke(app, ["add", str(tmp_path), "-t", "nonexistent"])
        assert result.exit_code == 1
        assert "Unknown tool" in result.output


class TestDetach:
    def test_not_in_tmux(self, mock_dirs):
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("shoal.core.tmux.is_inside_tmux", return_value=False),
        ):
            result = runner.invoke(app, ["detach"])
            assert result.exit_code == 1
            assert "Not inside a tmux session" in result.output


class TestWatcher:
    def test_status_not_running(self, mock_dirs):
        result = runner.invoke(app, ["watcher", "status"])
        assert result.exit_code == 0
        assert "not running" in result.output

    def test_stop_not_running(self, mock_dirs):
        result = runner.invoke(app, ["watcher", "stop"])
        assert result.exit_code == 1
        assert "not running" in result.output


class TestMcp:
    def test_ls_empty(self, mock_dirs):
        result = runner.invoke(app, ["mcp", "ls"])
        assert result.exit_code == 0
        assert "No MCP servers" in result.output

    def test_status_empty(self, mock_dirs):
        result = runner.invoke(app, ["mcp", "status"])
        assert result.exit_code == 0
        assert "(0 total)" in result.output


class TestConductor:
    def test_ls_empty(self, mock_dirs):
        _, tmp_state = mock_dirs
        # Conductor ls reads profiles from config dir, which has default.toml
        result = runner.invoke(app, ["conductor", "ls"])
        assert result.exit_code == 0

    def test_cond_alias(self, mock_dirs):
        result = runner.invoke(app, ["cond", "ls"])
        assert result.exit_code == 0


class TestWorktree:
    def test_ls_empty(self, mock_dirs):
        result = runner.invoke(app, ["wt", "ls"])
        assert result.exit_code == 0
        assert "No worktrees" in result.output

    def test_worktree_alias(self, mock_dirs):
        result = runner.invoke(app, ["worktree", "ls"])
        assert result.exit_code == 0


class TestInfo:
    def test_info_not_found(self, mock_dirs):
        result = runner.invoke(app, ["info", "nonexistent"])
        assert result.exit_code == 1
        assert "Session not found" in result.output

    def test_info_success(self, mock_dirs):
        from shoal.core.state import create_session
        asyncio.run(create_session("test-session", "claude", "/tmp/repo"))

        result = runner.invoke(app, ["info", "test-session"])
        assert result.exit_code == 0
        assert "Session: test-session" in result.output
        assert "claude" in result.output


class TestRename:
    def test_rename_success(self, mock_dirs):
        from shoal.core.state import create_session, find_by_name
        asyncio.run(create_session("old-name", "claude", "/tmp/repo"))

        with patch("shoal.core.tmux.has_session", return_value=False):
            result = runner.invoke(app, ["rename", "old-name", "new-name"])

        assert result.exit_code == 0
        assert "Renamed session: old-name → new-name" in result.output

        assert asyncio.run(find_by_name("new-name")) is not None
        assert asyncio.run(find_by_name("old-name")) is None

    def test_rename_not_found(self, mock_dirs):
        result = runner.invoke(app, ["rename", "nonexistent", "new"])
        assert result.exit_code == 1
        assert "Session not found" in result.output


class TestLogs:
    def test_logs_not_found(self, mock_dirs):
        result = runner.invoke(app, ["logs", "nonexistent"])
        assert result.exit_code == 1
        assert "Session not found" in result.output


class TestCheck:
    def test_check_command(self, mock_dirs):
        result = runner.invoke(app, ["check"])
        assert result.exit_code == 0
        assert "Dependency Check" in result.output
        assert "Directories" in result.output


class TestInit:
    def test_init_command(self, mock_dirs, tmp_path):
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Shoal initialized successfully" in result.output
