"""CLI tests with typer.testing.CliRunner."""

from unittest.mock import patch

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
