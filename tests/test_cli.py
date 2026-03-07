"""CLI tests with typer.testing.CliRunner."""

import asyncio
from unittest.mock import patch

from typer.testing import CliRunner

import shoal
from shoal.cli import app

runner = CliRunner()


class TestVersion:
    def test_version_command(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert f"shoal {shoal.__version__}" in result.output

    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert f"shoal {shoal.__version__}" in result.output


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
        # Rich table may wrap "(was running)" across lines
        assert "was" in result.output and "running" in result.output

    def test_ls_nerd_fonts_off(self, mock_dirs):
        """When use_nerd_fonts=False, ls uses Unicode fallback icons."""
        from shoal.core.state import create_session
        from shoal.core.theme import Symbols

        asyncio.run(create_session("nf-test", "claude", "/tmp/repo"))

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch(
                "shoal.cli.session_view.load_config",
                return_value=_config_with_nerd(False),
            ),
        ):
            result = runner.invoke(app, ["ls"])

        assert result.exit_code == 0
        # Unicode status icon should appear (e.g. "●" for idle)
        assert Symbols.BULLET_STOPPED in result.output or "idle" in result.output

    def test_ls_nerd_fonts_on(self, mock_dirs):
        """When use_nerd_fonts=True (default), ls uses Nerd Font glyphs."""
        from shoal.core.state import create_session

        asyncio.run(create_session("nf-test-on", "claude", "/tmp/repo"))

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch(
                "shoal.cli.session_view.load_config",
                return_value=_config_with_nerd(True),
            ),
        ):
            result = runner.invoke(app, ["ls"])

        assert result.exit_code == 0
        assert "nf-test-on" in result.output


def _config_with_nerd(use_nerd: bool) -> object:
    from shoal.models.config import GeneralConfig, ShoalConfig

    return ShoalConfig(general=GeneralConfig(use_nerd_fonts=use_nerd))


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

    def test_unknown_template(self, mock_dirs, tmp_path):
        result = runner.invoke(app, ["new", str(tmp_path), "--template", "nonexistent"])
        assert result.exit_code == 1
        assert "Template 'nonexistent' not found" in result.output


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
        _, _tmp_state = mock_dirs
        # Robo ls reads profiles from config dir, which has default.toml
        result = runner.invoke(app, ["robo", "ls"])
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


class TestTemplate:
    def test_ls_empty(self, mock_dirs):
        result = runner.invoke(app, ["template", "ls"])
        assert result.exit_code == 0
        assert "No templates found" in result.output

    def test_show(self, mock_dirs):
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "feature-dev.toml").write_text(
            """
[template]
name = "feature-dev"
tool = "opencode"

[[windows]]
name = "dev"

[[windows.panes]]
split = "root"
command = "opencode"
"""
        )

        result = runner.invoke(app, ["template", "show", "feature-dev"])
        assert result.exit_code == 0
        assert '"name": "feature-dev"' in result.output

    def test_validate_all_ok(self, mock_dirs):
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "feature-dev.toml").write_text(
            """
[template]
name = "feature-dev"

[[windows]]
name = "dev"

[[windows.panes]]
split = "root"
command = "opencode"
"""
        )

        result = runner.invoke(app, ["template", "validate"])
        assert result.exit_code == 0
        assert "OK" in result.output

    def test_validate_invalid(self, mock_dirs):
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "broken.toml").write_text(
            """
[template]
name = "broken"

[[windows]]
name = "dev"

[[windows.panes]]
split = "root"
"""
        )

        result = runner.invoke(app, ["template", "validate"])
        assert result.exit_code == 1
        assert "INVALID" in result.output


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

    def test_rename_invalid_name(self, mock_dirs):
        """Test that renaming to an invalid name fails with validation error."""
        from shoal.core.state import create_session

        asyncio.run(create_session("valid-name", "claude", "/tmp/repo"))

        with patch("shoal.core.tmux.has_session", return_value=False):
            result = runner.invoke(app, ["rename", "valid-name", "bad;name"])

        assert result.exit_code == 1
        assert "must contain only" in result.output


class TestKill:
    def test_kill_success(self, mock_dirs):
        from shoal.core.state import create_session, get_session

        s = asyncio.run(create_session("to-kill", "claude", "/tmp/repo"))

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch("shoal.core.tmux.kill_session") as mock_tmux_kill,
        ):
            result = runner.invoke(app, ["kill", "to-kill"])
            assert result.exit_code == 0
            assert "Session 'to-kill' (" in result.output
            assert "removed" in result.output
            mock_tmux_kill.assert_called_once_with(s.tmux_session)

        assert asyncio.run(get_session(s.id)) is None

    def test_kill_not_found(self, mock_dirs):
        result = runner.invoke(app, ["kill", "nonexistent"])
        assert result.exit_code == 1
        assert "Session not found" in result.output

    def test_kill_worktree(self, mock_dirs):
        from shoal.core.state import create_session

        asyncio.run(
            create_session("wt-session", "claude", "/tmp/repo", worktree="/tmp/repo/.worktrees/wt")
        )

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.git.worktree_is_dirty", return_value=False),
            patch("shoal.core.git.worktree_remove", return_value=True) as mock_wt_remove,
            patch("pathlib.Path.is_dir", return_value=True),
        ):
            result = runner.invoke(app, ["kill", "wt-session", "--worktree"])
            assert result.exit_code == 0
            assert "Removed worktree" in result.output
            mock_wt_remove.assert_called_once()


class TestLogs:
    def test_logs_not_found(self, mock_dirs):
        result = runner.invoke(app, ["logs", "nonexistent"])
        assert result.exit_code == 1
        assert "Session not found" in result.output

    def test_logs_success(self, mock_dirs):
        from shoal.core.state import create_session

        asyncio.run(create_session("logs-session", "claude", "/tmp/repo"))

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch("shoal.core.tmux.capture_pane", return_value="hello world") as mock_capture,
        ):
            result = runner.invoke(app, ["logs", "logs-session"])
            assert result.exit_code == 0
            assert "hello world" in result.output
            mock_capture.assert_called_once()


class TestAttach:
    def test_attach_tmux_missing(self, mock_dirs):
        from shoal.core.state import create_session

        asyncio.run(create_session("missing-tmux", "claude", "/tmp/repo"))

        with patch("shoal.core.tmux.has_session", return_value=False):
            result = runner.invoke(app, ["attach", "missing-tmux"])
            assert result.exit_code == 1
            assert "Tmux session" in result.output
            assert "not found" in result.output


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

    def test_init_cleans_stale_mcp_sockets(self, mock_dirs):
        """Init should clean up stale MCP sockets and report them."""
        with patch(
            "shoal.services.lifecycle.reconcile_mcp_pool", return_value=["memory", "github"]
        ):
            result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Cleaned 2 stale MCP socket(s)" in result.output
        assert "memory" in result.output
        assert "github" in result.output

    def test_init_no_stale_sockets_no_output(self, mock_dirs):
        """Init should not mention MCP cleanup when nothing to clean."""
        with patch("shoal.services.lifecycle.reconcile_mcp_pool", return_value=[]):
            result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "stale MCP" not in result.output
        assert "Shoal initialized successfully" in result.output

    def test_init_scaffolds_defaults(self, mock_dirs):
        """Init should scaffold config files and report what was created."""
        with patch(
            "shoal.core.config.scaffold_defaults",
            return_value=["config.toml", "tools/claude.toml"],
        ):
            result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Scaffolded 2 config file(s)" in result.output
        assert "config.toml" in result.output

    def test_init_bare_skips_scaffolding(self, mock_dirs):
        """Init --bare should skip scaffolding entirely."""
        with patch("shoal.core.config.scaffold_defaults") as mock_scaffold:
            result = runner.invoke(app, ["init", "--bare"])
        assert result.exit_code == 0
        mock_scaffold.assert_not_called()
        assert "Scaffolded" not in result.output

    def test_init_scaffolds_nothing_when_all_exist(self, mock_dirs):
        """Init should show skip message when all configs already exist."""
        with patch("shoal.core.config.scaffold_defaults", return_value=[]):
            result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "already exist" in result.output
