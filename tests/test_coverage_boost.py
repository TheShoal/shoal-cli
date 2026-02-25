"""Coverage boost tests for template.py, watcher.py, and worktree.py."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from shoal.cli.template import app as template_app
from shoal.cli.worktree import app as worktree_app
from shoal.core.db import with_db
from shoal.core.state import create_session, update_session
from shoal.models.state import SessionStatus
from shoal.services.watcher import Watcher, _find_session_tool_pane

runner = CliRunner()


# ---------------------------------------------------------------------------
# _find_session_tool_pane unit tests
# ---------------------------------------------------------------------------


class TestFindSessionToolPane:
    def test_finds_matching_pane(self) -> None:
        panes = [
            {"id": "%1", "title": "bash", "command": "bash"},
            {"id": "%2", "title": "shoal:abc123", "command": "claude"},
        ]
        result = _find_session_tool_pane(panes, "shoal:abc123")
        assert result == "%2"

    def test_returns_none_when_no_match(self) -> None:
        panes = [
            {"id": "%1", "title": "bash", "command": "bash"},
        ]
        result = _find_session_tool_pane(panes, "shoal:abc123")
        assert result is None

    def test_returns_none_for_empty_panes(self) -> None:
        result = _find_session_tool_pane([], "shoal:abc123")
        assert result is None

    def test_pane_missing_title_key(self) -> None:
        panes: list[dict[str, str]] = [{"id": "%1", "command": "bash"}]
        result = _find_session_tool_pane(panes, "shoal:abc123")
        assert result is None


# ---------------------------------------------------------------------------
# Template CLI tests
# ---------------------------------------------------------------------------


class TestTemplateLs:
    def test_ls_empty(self, mock_dirs: tuple[Path, Path]) -> None:
        """template ls with no templates shows 'No templates found'."""
        result = runner.invoke(template_app, ["ls"])
        assert result.exit_code == 0
        assert "No templates found" in result.output

    def test_ls_with_templates(self, mock_dirs: tuple[Path, Path]) -> None:
        """template ls lists valid templates with metadata columns."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "dev-session.toml").write_text(
            """
[template]
name = "dev-session"
description = "Development session"
tool = "claude"

[[windows]]
name = "editor"

[[windows.panes]]
split = "root"
command = "nvim"
"""
        )

        result = runner.invoke(template_app, ["ls"])
        assert result.exit_code == 0
        assert "dev-session" in result.output
        assert "claude" in result.output

    def test_ls_with_invalid_template(self, mock_dirs: tuple[Path, Path]) -> None:
        """template ls shows 'invalid template' for broken TOML."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        # Missing required 'command' in pane
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

        result = runner.invoke(template_app, ["ls"])
        assert result.exit_code == 0
        assert "invalid" in result.output and "template" in result.output

    def test_ls_with_multiple_windows_and_panes(self, mock_dirs: tuple[Path, Path]) -> None:
        """template ls correctly counts windows and panes."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "multi.toml").write_text(
            """
[template]
name = "multi"
tool = "opencode"
description = "Multi-window template"

[[windows]]
name = "main"

[[windows.panes]]
split = "root"
command = "opencode"

[[windows.panes]]
split = "right"
command = "bash"

[[windows]]
name = "aux"

[[windows.panes]]
split = "root"
command = "htop"
"""
        )

        result = runner.invoke(template_app, ["ls"])
        assert result.exit_code == 0
        assert "multi" in result.output

    def test_default_invokes_ls(self, mock_dirs: tuple[Path, Path]) -> None:
        """Calling template with no subcommand defaults to ls."""
        result = runner.invoke(template_app, [])
        assert result.exit_code == 0
        assert "No templates found" in result.output


class TestTemplateShow:
    def test_show_found(self, mock_dirs: tuple[Path, Path]) -> None:
        """template show prints JSON for a valid template."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "mytemplate.toml").write_text(
            """
[template]
name = "mytemplate"
tool = "claude"

[[windows]]
name = "dev"

[[windows.panes]]
split = "root"
command = "claude"
"""
        )

        result = runner.invoke(template_app, ["show", "mytemplate"])
        assert result.exit_code == 0
        assert '"name": "mytemplate"' in result.output
        assert '"tool": "claude"' in result.output

    def test_show_not_found(self, mock_dirs: tuple[Path, Path]) -> None:
        """template show prints error and exits 1 for missing template."""
        result = runner.invoke(template_app, ["show", "nonexistent"])
        assert result.exit_code == 1
        assert "Template not found" in result.output

    def test_show_not_found_with_available(self, mock_dirs: tuple[Path, Path]) -> None:
        """template show lists available templates when one is not found."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "good.toml").write_text(
            """
[template]
name = "good"
tool = "opencode"

[[windows]]
name = "dev"

[[windows.panes]]
split = "root"
command = "opencode"
"""
        )

        result = runner.invoke(template_app, ["show", "missing"])
        assert result.exit_code == 1
        assert "Template not found" in result.output
        assert "Available:" in result.output
        assert "good" in result.output

    def test_show_invalid_template(self, mock_dirs: tuple[Path, Path]) -> None:
        """template show prints error for invalid template content."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "invalid.toml").write_text(
            """
[template]
name = "invalid"

[[windows]]
name = "dev"

[[windows.panes]]
split = "root"
"""
        )

        result = runner.invoke(template_app, ["show", "invalid"])
        assert result.exit_code == 1
        assert "invalid" in result.output and "template" in result.output


class TestTemplateValidate:
    def test_validate_no_templates(self, mock_dirs: tuple[Path, Path]) -> None:
        """template validate with no templates prints 'No templates found'."""
        result = runner.invoke(template_app, ["validate"])
        assert result.exit_code == 0
        assert "No templates found" in result.output

    def test_validate_all_ok(self, mock_dirs: tuple[Path, Path]) -> None:
        """template validate with valid templates shows OK."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "valid.toml").write_text(
            """
[template]
name = "valid"

[[windows]]
name = "dev"

[[windows.panes]]
split = "root"
command = "opencode"
"""
        )

        result = runner.invoke(template_app, ["validate"])
        assert result.exit_code == 0
        assert "OK" in result.output
        assert "valid" in result.output

    def test_validate_single_by_name(self, mock_dirs: tuple[Path, Path]) -> None:
        """template validate <name> validates only the named template."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "specific.toml").write_text(
            """
[template]
name = "specific"

[[windows]]
name = "dev"

[[windows.panes]]
split = "root"
command = "nvim"
"""
        )

        result = runner.invoke(template_app, ["validate", "specific"])
        assert result.exit_code == 0
        assert "OK" in result.output
        assert "specific" in result.output

    def test_validate_single_missing(self, mock_dirs: tuple[Path, Path]) -> None:
        """template validate <name> for a missing template shows MISSING."""
        result = runner.invoke(template_app, ["validate", "ghost"])
        assert result.exit_code == 1
        assert "MISSING" in result.output

    def test_validate_invalid_template(self, mock_dirs: tuple[Path, Path]) -> None:
        """template validate with an invalid template shows INVALID."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "bad.toml").write_text(
            """
[template]
name = "bad"

[[windows]]
name = "dev"

[[windows.panes]]
split = "root"
"""
        )

        result = runner.invoke(template_app, ["validate"])
        assert result.exit_code == 1
        assert "INVALID" in result.output

    def test_validate_mixed_results(self, mock_dirs: tuple[Path, Path]) -> None:
        """template validate shows OK and INVALID together."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "good.toml").write_text(
            """
[template]
name = "good"

[[windows]]
name = "dev"

[[windows.panes]]
split = "root"
command = "nvim"
"""
        )
        (templates / "bad.toml").write_text(
            """
[template]
name = "bad"

[[windows]]
name = "dev"

[[windows.panes]]
split = "root"
"""
        )

        result = runner.invoke(template_app, ["validate"])
        assert result.exit_code == 1
        assert "OK" in result.output
        assert "INVALID" in result.output


# ---------------------------------------------------------------------------
# Watcher service tests
# ---------------------------------------------------------------------------


class TestWatcherPollCycle:
    async def test_skips_stopped_sessions(self, mock_dirs: tuple[Path, Path]) -> None:
        """Watcher _poll_cycle should skip sessions with status=stopped."""
        s = await create_session("stopped-sess", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.stopped)

        watcher = Watcher()

        # If it tries to check tmux, this will fail -- so no patch needed for has_session
        with patch("shoal.core.tmux.has_session") as mock_has:
            await watcher._poll_cycle()
            mock_has.assert_not_called()

    async def test_missing_tool_config_skips_session(self, mock_dirs: tuple[Path, Path]) -> None:
        """Watcher should log warning and skip when tool config is missing."""
        s = await create_session("no-tool", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.running)

        watcher = Watcher()

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch(
                "shoal.services.watcher.load_tool_config",
                side_effect=FileNotFoundError("no config"),
            ),
            patch("shoal.services.watcher.logger") as mock_logger,
        ):
            await watcher._poll_cycle()
            mock_logger.warning.assert_called_once()

    async def test_no_tagged_pane_skips(self, mock_dirs: tuple[Path, Path]) -> None:
        """Watcher should skip sessions where no pane has the shoal:<id> title."""
        s = await create_session("no-pane", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.running)

        watcher = Watcher()

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch(
                "shoal.core.tmux.list_panes",
                return_value=[{"id": "%1", "title": "bash", "command": "bash"}],
            ),
            patch("shoal.core.tmux.capture_pane") as mock_capture,
        ):
            await watcher._poll_cycle()
            mock_capture.assert_not_called()

    async def test_empty_pane_content_skips(self, mock_dirs: tuple[Path, Path]) -> None:
        """Watcher should skip when pane capture returns empty string."""
        s = await create_session("empty-pane", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.running, pid=100)

        watcher = Watcher()

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch(
                "shoal.core.tmux.list_panes",
                return_value=[{"id": "%1", "title": f"shoal:{s.id}", "command": "claude"}],
            ),
            patch("shoal.core.tmux.pane_pid", return_value=100),
            patch("shoal.core.tmux.capture_pane", return_value=""),
            patch("shoal.services.watcher.detect_status") as mock_detect,
        ):
            await watcher._poll_cycle()
            mock_detect.assert_not_called()

    async def test_status_transition_running_to_waiting(self, mock_dirs: tuple[Path, Path]) -> None:
        """Watcher should update status and notify on running->waiting."""
        from shoal.core.state import get_session

        s = await create_session("trans-sess", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.running, pid=100)

        watcher = Watcher()

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch(
                "shoal.core.tmux.list_panes",
                return_value=[{"id": "%1", "title": f"shoal:{s.id}", "command": "claude"}],
            ),
            patch("shoal.core.tmux.pane_pid", return_value=100),
            patch("shoal.core.tmux.capture_pane", return_value="Yes/No prompt"),
            patch(
                "shoal.services.watcher.detect_status",
                return_value=SessionStatus.waiting,
            ),
            patch("shoal.services.watcher.notify") as mock_notify,
        ):
            await watcher._poll_cycle()

            updated = await get_session(s.id)
            assert updated is not None
            assert updated.status == SessionStatus.waiting
            mock_notify.assert_called_once()

    async def test_status_no_change_no_update(self, mock_dirs: tuple[Path, Path]) -> None:
        """Watcher should not update state when status hasn't changed."""
        from shoal.core.state import get_session

        s = await create_session("stable-sess", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.running, pid=100)

        watcher = Watcher()

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch(
                "shoal.core.tmux.list_panes",
                return_value=[{"id": "%1", "title": f"shoal:{s.id}", "command": "claude"}],
            ),
            patch("shoal.core.tmux.pane_pid", return_value=100),
            patch("shoal.core.tmux.capture_pane", return_value="working on task"),
            patch(
                "shoal.services.watcher.detect_status",
                return_value=SessionStatus.running,
            ),
            patch("shoal.services.watcher.notify") as mock_notify,
        ):
            await watcher._poll_cycle()

            updated = await get_session(s.id)
            assert updated is not None
            assert updated.status == SessionStatus.running
            mock_notify.assert_not_called()

    async def test_tmux_gone_marks_stopped(self, mock_dirs: tuple[Path, Path]) -> None:
        """When tmux session disappears, watcher marks session as stopped."""
        from shoal.core.state import get_session

        s = await create_session("gone-sess", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.running, pid=100)

        watcher = Watcher()

        with patch("shoal.core.tmux.has_session", return_value=False):
            await watcher._poll_cycle()

            updated = await get_session(s.id)
            assert updated is not None
            assert updated.status == SessionStatus.stopped

    async def test_pid_found_first_time(self, mock_dirs: tuple[Path, Path]) -> None:
        """Watcher records PID when session has no PID but pane does."""
        from shoal.core.state import get_session

        s = await create_session("no-pid", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.running, pid=None)

        watcher = Watcher()

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch(
                "shoal.core.tmux.list_panes",
                return_value=[{"id": "%1", "title": f"shoal:{s.id}", "command": "claude"}],
            ),
            patch("shoal.core.tmux.pane_pid", return_value=999),
            patch("shoal.core.tmux.capture_pane", return_value="some output"),
            patch(
                "shoal.services.watcher.detect_status",
                return_value=SessionStatus.running,
            ),
        ):
            await watcher._poll_cycle()

            updated = await get_session(s.id)
            assert updated is not None
            assert updated.pid == 999


class TestWatcherStop:
    def test_stop_sets_running_false(self) -> None:
        """_stop() should set _running to False."""
        watcher = Watcher()
        assert watcher._running is True
        watcher._stop()
        assert watcher._running is False

    def test_custom_poll_interval(self) -> None:
        watcher = Watcher(poll_interval=10.0)
        assert watcher.poll_interval == 10.0


# ---------------------------------------------------------------------------
# Worktree CLI tests
# ---------------------------------------------------------------------------


class TestWtLs:
    def test_ls_empty(self, mock_dirs: tuple[Path, Path]) -> None:
        """wt ls with no sessions shows 'No worktrees managed'."""
        result = runner.invoke(worktree_app, ["ls"])
        assert result.exit_code == 0
        assert "No worktrees" in result.output

    def test_ls_with_worktree_sessions(self, mock_dirs: tuple[Path, Path], tmp_path: Path) -> None:
        """wt ls shows sessions that have worktrees."""
        wt_dir = tmp_path / "repo" / ".worktrees" / "feat-ui"
        wt_dir.mkdir(parents=True)

        async def setup() -> None:
            s = await create_session(
                "feat-ui",
                "claude",
                str(tmp_path / "repo"),
                worktree=str(wt_dir),
            )
            await update_session(s.id, branch="feat/ui", status=SessionStatus.running)

        asyncio.run(with_db(setup()))

        result = runner.invoke(worktree_app, ["ls"])
        assert result.exit_code == 0
        assert "feat-ui" in result.output
        assert "feat/ui" in result.output

    def test_ls_worktree_missing_dir(self, mock_dirs: tuple[Path, Path]) -> None:
        """wt ls shows 'missing' when worktree directory doesn't exist."""

        async def setup() -> None:
            s = await create_session(
                "missing-wt",
                "claude",
                "/tmp/repo",
                worktree="/tmp/repo/.worktrees/gone",
            )
            await update_session(s.id, branch="feat/gone", status=SessionStatus.running)

        asyncio.run(with_db(setup()))

        result = runner.invoke(worktree_app, ["ls"])
        assert result.exit_code == 0
        assert "missing-wt" in result.output
        assert "missing" in result.output

    def test_ls_sessions_without_worktree_excluded(self, mock_dirs: tuple[Path, Path]) -> None:
        """wt ls should not show sessions that have no worktree."""

        async def setup() -> None:
            await create_session("no-wt-session", "claude", "/tmp/repo")

        asyncio.run(with_db(setup()))

        result = runner.invoke(worktree_app, ["ls"])
        assert result.exit_code == 0
        assert "No worktrees" in result.output

    def test_default_invokes_ls(self, mock_dirs: tuple[Path, Path]) -> None:
        """Calling wt with no subcommand defaults to ls."""
        result = runner.invoke(worktree_app, [])
        assert result.exit_code == 0
        assert "No worktrees" in result.output


class TestWtFinish:
    def test_finish_no_worktree(self, mock_dirs: tuple[Path, Path]) -> None:
        """wt finish on session without worktree exits with error."""

        async def setup() -> None:
            await create_session("no-wt", "claude", "/tmp/repo")

        asyncio.run(with_db(setup()))

        result = runner.invoke(worktree_app, ["finish", "no-wt"])
        assert result.exit_code == 1
        assert "has no worktree to finish" in result.output

    def test_finish_session_not_found(self, mock_dirs: tuple[Path, Path]) -> None:
        """wt finish with unknown session exits with error."""
        result = runner.invoke(worktree_app, ["finish", "nonexistent"])
        assert result.exit_code != 0

    def test_finish_no_merge(self, mock_dirs: tuple[Path, Path]) -> None:
        """wt finish --no-merge skips merge and just cleans up."""

        async def setup() -> None:
            s = await create_session(
                "nomerge-sess",
                "claude",
                "/tmp/repo",
                worktree="/tmp/repo/.worktrees/feat",
            )
            await update_session(s.id, branch="feat/skip")

        asyncio.run(with_db(setup()))

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.git.worktree_remove", return_value=True),
            patch("shoal.core.git.branch_delete", return_value=True),
            patch("pathlib.Path.is_dir", return_value=True),
        ):
            result = runner.invoke(worktree_app, ["finish", "nomerge-sess", "--no-merge"])
            assert result.exit_code == 0
            assert "Removed worktree" in result.output
            # Should not attempt merge
            assert "Merging" not in result.output

    def test_finish_merge_success(self, mock_dirs: tuple[Path, Path]) -> None:
        """wt finish merges branch and cleans up on success."""

        async def setup() -> None:
            s = await create_session(
                "merge-sess",
                "claude",
                "/tmp/repo",
                worktree="/tmp/repo/.worktrees/feat",
            )
            await update_session(s.id, branch="feat/merge")

        asyncio.run(with_db(setup()))

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch("shoal.core.tmux.kill_session") as mock_kill,
            patch("shoal.core.git.main_branch", return_value="main"),
            patch("shoal.core.git.checkout"),
            patch("shoal.core.git.merge", return_value=True),
            patch("shoal.core.git.worktree_remove", return_value=True),
            patch("shoal.core.git.branch_delete", return_value=True),
            patch("pathlib.Path.is_dir", return_value=True),
        ):
            result = runner.invoke(worktree_app, ["finish", "merge-sess"])
            assert result.exit_code == 0
            assert "Merged successfully" in result.output
            assert "Removed worktree" in result.output
            assert "Killed tmux session" in result.output
            mock_kill.assert_called_once()

    def test_finish_merge_failure(self, mock_dirs: tuple[Path, Path]) -> None:
        """wt finish exits 1 when merge fails."""

        async def setup() -> None:
            s = await create_session(
                "fail-merge",
                "claude",
                "/tmp/repo",
                worktree="/tmp/repo/.worktrees/feat",
            )
            await update_session(s.id, branch="feat/conflict")

        asyncio.run(with_db(setup()))

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.git.main_branch", return_value="main"),
            patch("shoal.core.git.checkout"),
            patch("shoal.core.git.merge", return_value=False),
        ):
            result = runner.invoke(worktree_app, ["finish", "fail-merge"])
            assert result.exit_code == 1
            assert "Merge failed" in result.output
            assert "resolve conflicts" in result.output

    def test_finish_with_pr(self, mock_dirs: tuple[Path, Path]) -> None:
        """wt finish --pr pushes and opens a PR."""

        async def setup() -> None:
            s = await create_session(
                "pr-sess",
                "claude",
                "/tmp/repo",
                worktree="/tmp/repo/.worktrees/feat",
            )
            await update_session(s.id, branch="feat/pr")

        asyncio.run(with_db(setup()))

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.git.push") as mock_push,
            patch("subprocess.run") as mock_subprocess,
            patch("shoal.core.git.worktree_remove", return_value=True),
            patch("pathlib.Path.is_dir", return_value=True),
        ):
            result = runner.invoke(worktree_app, ["finish", "pr-sess", "--pr"])
            assert result.exit_code == 0
            assert "Opening PR" in result.output
            mock_push.assert_called_once_with(
                "/tmp/repo/.worktrees/feat", "feat/pr", set_upstream=True
            )
            mock_subprocess.assert_called_once()

    def test_finish_worktree_remove_fails(self, mock_dirs: tuple[Path, Path]) -> None:
        """wt finish shows warning when worktree removal fails."""

        async def setup() -> None:
            s = await create_session(
                "rm-fail",
                "claude",
                "/tmp/repo",
                worktree="/tmp/repo/.worktrees/feat",
            )
            await update_session(s.id, branch="feat/rmfail")

        asyncio.run(with_db(setup()))

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.git.worktree_remove", return_value=False),
            patch("shoal.core.git.branch_delete", return_value=True),
            patch("pathlib.Path.is_dir", return_value=True),
        ):
            result = runner.invoke(worktree_app, ["finish", "rm-fail", "--no-merge"])
            assert result.exit_code == 0
            assert "Warning" in result.output
            assert "Failed to remove worktree" in result.output

    def test_finish_tmux_alive_kills_session(self, mock_dirs: tuple[Path, Path]) -> None:
        """wt finish kills tmux session if it is still alive."""

        async def setup() -> None:
            s = await create_session(
                "alive-tmux",
                "claude",
                "/tmp/repo",
                worktree="/tmp/repo/.worktrees/feat",
            )
            await update_session(s.id, branch="feat/alive")

        asyncio.run(with_db(setup()))

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch("shoal.core.tmux.kill_session") as mock_kill,
            patch("shoal.core.git.worktree_remove", return_value=True),
            patch("shoal.core.git.branch_delete", return_value=True),
            patch("pathlib.Path.is_dir", return_value=True),
        ):
            result = runner.invoke(worktree_app, ["finish", "alive-tmux", "--no-merge"])
            assert result.exit_code == 0
            assert "Killed tmux session" in result.output
            mock_kill.assert_called_once()

    def test_finish_does_not_delete_main_branch(self, mock_dirs: tuple[Path, Path]) -> None:
        """wt finish should not try to delete 'main' or 'master' branches."""

        async def setup() -> None:
            s = await create_session(
                "main-branch",
                "claude",
                "/tmp/repo",
                worktree="/tmp/repo/.worktrees/feat",
            )
            await update_session(s.id, branch="main")

        asyncio.run(with_db(setup()))

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.git.worktree_remove", return_value=True),
            patch("shoal.core.git.branch_delete") as mock_branch_del,
            patch("pathlib.Path.is_dir", return_value=True),
        ):
            result = runner.invoke(worktree_app, ["finish", "main-branch", "--no-merge"])
            assert result.exit_code == 0
            # branch_delete should not be called for 'main'
            mock_branch_del.assert_not_called()

    def test_finish_worktree_dir_gone_skips_remove(self, mock_dirs: tuple[Path, Path]) -> None:
        """wt finish skips worktree removal if directory already gone."""

        async def setup() -> None:
            s = await create_session(
                "gone-wt",
                "claude",
                "/tmp/repo",
                worktree="/tmp/nonexistent/.worktrees/feat",
            )
            await update_session(s.id, branch="feat/gone")

        asyncio.run(with_db(setup()))

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.git.worktree_remove") as mock_wt_remove,
            patch("shoal.core.git.branch_delete", return_value=True),
        ):
            result = runner.invoke(worktree_app, ["finish", "gone-wt", "--no-merge"])
            assert result.exit_code == 0
            # worktree_remove should not be called if dir doesn't exist
            mock_wt_remove.assert_not_called()
