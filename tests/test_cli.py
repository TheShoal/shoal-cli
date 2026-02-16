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

    def test_grouping(self, mock_dirs):
        from shoal.core.state import create_session

        asyncio.run(create_session("proj1-a", "claude", "/tmp/proj1"))
        asyncio.run(create_session("proj1-b", "claude", "/tmp/proj1"))
        asyncio.run(create_session("proj2-a", "claude", "/tmp/proj2"))

        with patch("shoal.core.tmux.has_session", return_value=True):
            result = runner.invoke(app, ["ls"])

        assert result.exit_code == 0
        assert "proj1" in result.output
        assert "proj2" in result.output

    def test_ghost_detection(self, mock_dirs):
        from shoal.core.state import create_session, update_session
        from shoal.models.state import SessionStatus

        s = asyncio.run(create_session("ghost-session", "claude", "/tmp/repo"))
        asyncio.run(update_session(s.id, status=SessionStatus.running))

        # Mock tmux.has_session to return False so it becomes a ghost
        with patch("shoal.core.tmux.has_session", return_value=False):
            result = runner.invoke(app, ["ls"])

        assert result.exit_code == 0
        assert "ghost" in result.output
        assert "(running)" in result.output


class TestPrune:
    def test_prune_command(self, mock_dirs):
        from shoal.core.state import create_session, update_session
        from shoal.models.state import SessionStatus

        s1 = asyncio.run(create_session("active", "claude", "/tmp/repo"))
        asyncio.run(update_session(s1.id, status=SessionStatus.running))

        s2 = asyncio.run(create_session("stopped", "claude", "/tmp/repo"))
        asyncio.run(update_session(s2.id, status=SessionStatus.stopped))

        # Run prune
        result = runner.invoke(app, ["prune", "--force"])
        assert result.exit_code == 0
        assert "Removed session 'stopped'" in result.output

        from shoal.core.state import get_session

        assert asyncio.run(get_session(s1.id)) is not None
        assert asyncio.run(get_session(s2.id)) is None

    def test_prune_empty(self, mock_dirs):
        result = runner.invoke(app, ["prune", "--force"])
        assert result.exit_code == 0
        assert "No stopped sessions to prune" in result.output


class TestStatus:
    def test_empty(self, mock_dirs):
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "No active sessions" in result.output

    def test_st_alias(self, mock_dirs):
        result = runner.invoke(app, ["st"])
        assert result.exit_code == 0
        assert "No active sessions" in result.output


class TestNew:
    def test_missing_git_repo(self, mock_dirs, tmp_path):
        result = runner.invoke(app, ["new", str(tmp_path)])
        assert result.exit_code == 1
        assert "Not a git repository" in result.output

    def test_unknown_tool(self, mock_dirs, tmp_path):
        result = runner.invoke(app, ["new", str(tmp_path), "-t", "nonexistent"])
        assert result.exit_code == 1
        assert "Unknown tool" in result.output

    def test_add_alias(self, mock_dirs, tmp_path):
        """Test that 'add' still works as a hidden alias for backward compatibility."""
        result = runner.invoke(app, ["add", str(tmp_path)])
        assert result.exit_code == 1
        assert "Not a git repository" in result.output


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


class TestRobo:
    def test_ls_empty(self, mock_dirs):
        _, tmp_state = mock_dirs
        # Robo ls reads profiles from config dir, which has default.toml
        result = runner.invoke(app, ["robo", "ls"])
        assert result.exit_code == 0

    def test_conductor_alias(self, mock_dirs):
        """Test that 'conductor' still works as a hidden alias for backward compatibility."""
        result = runner.invoke(app, ["conductor", "ls"])
        assert result.exit_code == 0

    def test_cond_alias(self, mock_dirs):
        """Test that 'cond' still works as a hidden alias for backward compatibility."""
        result = runner.invoke(app, ["cond", "ls"])
        assert result.exit_code == 0

    def test_send(self, mock_dirs):
        from shoal.core.state import create_session

        s = asyncio.run(create_session("test-session", "claude", "/tmp/repo"))

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch("shoal.core.tmux.send_keys") as mock_send,
        ):
            result = runner.invoke(app, ["robo", "send", "test-session", "ls -la"])

            assert result.exit_code == 0
            assert "Sent keys to 'test-session'" in result.output
            mock_send.assert_called_once_with(s.tmux_session, "ls -la")

    def test_approve(self, mock_dirs):
        from shoal.core.state import create_session

        s = asyncio.run(create_session("test-session", "claude", "/tmp/repo"))

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch("shoal.core.tmux.send_keys") as mock_send,
        ):
            result = runner.invoke(app, ["robo", "approve", "test-session"])

            assert result.exit_code == 0
            assert "Sent keys to 'test-session'" in result.output
            mock_send.assert_called_once_with(s.tmux_session, "")


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
