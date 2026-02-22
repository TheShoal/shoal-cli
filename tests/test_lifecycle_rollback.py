"""Rollback integration tests — verify create/fork failures clean up all resources."""

from unittest.mock import patch

import pytest

from shoal.core.state import list_sessions
from shoal.services.lifecycle import (
    StartupCommandError,
    TmuxSetupError,
    create_session_lifecycle,
    fork_session_lifecycle,
)

# ---------------------------------------------------------------------------
# Create rollback matrix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCreateRollback:
    async def test_tmux_failure_rolls_back_db_and_worktree(self, mock_dirs, tmp_path):
        """When tmux.new_session fails, DB row and worktree should be cleaned up."""
        wt = tmp_path / "worktree"
        wt.mkdir()

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session", side_effect=RuntimeError("no tmux")),
            patch("shoal.core.git.worktree_remove", return_value=True) as mock_wt_rm,
            pytest.raises(TmuxSetupError, match="Failed to create tmux session"),
        ):
            await create_session_lifecycle(
                session_name="tmux-fail",
                tool="claude",
                git_root="/tmp/repo",
                wt_path=str(wt),
                work_dir=str(wt),
                branch_name="feat/test",
                tool_command="claude",
                startup_commands=[],
            )

        # DB should be empty
        sessions = await list_sessions()
        assert len(sessions) == 0

        # Worktree removal attempted
        mock_wt_rm.assert_called_once()

    async def test_startup_failure_rolls_back_all(self, mock_dirs, tmp_path):
        """When startup commands fail, DB + tmux + worktree should be cleaned up."""
        wt = tmp_path / "worktree"
        wt.mkdir()

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session"),
            patch("shoal.core.tmux.set_environment"),
            patch("shoal.core.tmux.kill_session") as mock_tmux_kill,
            patch("shoal.core.tmux.run_command", side_effect=ValueError("bad cmd")),
            patch("shoal.core.git.worktree_remove", return_value=True) as mock_wt_rm,
            pytest.raises(StartupCommandError, match="Startup command failed"),
        ):
            await create_session_lifecycle(
                session_name="startup-fail",
                tool="claude",
                git_root="/tmp/repo",
                wt_path=str(wt),
                work_dir=str(wt),
                branch_name="feat/test",
                tool_command="claude",
                startup_commands=["send-keys -t {tmux_session} 'echo hi' Enter"],
            )

        # All resources cleaned up
        sessions = await list_sessions()
        assert len(sessions) == 0
        mock_tmux_kill.assert_called()
        mock_wt_rm.assert_called_once()

    async def test_template_interpolation_failure_rollback(self, mock_dirs, tmp_path):
        """Bad template variable causes full rollback."""
        from unittest.mock import MagicMock

        wt = tmp_path / "worktree"
        wt.mkdir()

        # Create a mock template with a bad variable reference
        template_cfg = MagicMock()
        template_cfg.windows = [MagicMock()]
        template_cfg.windows[0].name = "{nonexistent_var}"
        template_cfg.windows[0].cwd = None
        template_cfg.windows[0].focus = False
        template_cfg.windows[0].panes = []
        template_cfg.windows[0].layout = None
        template_cfg.name = "bad-template"

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session"),
            patch("shoal.core.tmux.set_environment"),
            patch("shoal.core.tmux.kill_session") as mock_tmux_kill,
            patch("shoal.core.git.worktree_remove", return_value=True),
            pytest.raises(StartupCommandError),
        ):
            await create_session_lifecycle(
                session_name="template-fail",
                tool="claude",
                git_root="/tmp/repo",
                wt_path=str(wt),
                work_dir=str(wt),
                branch_name="feat/test",
                tool_command="claude",
                startup_commands=[],
                template_cfg=template_cfg,
            )

        sessions = await list_sessions()
        assert len(sessions) == 0
        mock_tmux_kill.assert_called()

    async def test_partial_rollback_logs_warnings(self, mock_dirs, tmp_path):
        """When worktree removal also fails during rollback, a warning is logged."""
        wt = tmp_path / "worktree"
        wt.mkdir()

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session"),
            patch("shoal.core.tmux.set_environment"),
            patch("shoal.core.tmux.kill_session"),
            patch("shoal.core.tmux.run_command", side_effect=ValueError("bad cmd")),
            patch("shoal.core.git.worktree_remove", side_effect=RuntimeError("wt stuck")),
            patch("shoal.services.lifecycle.logger") as mock_logger,
            pytest.raises(StartupCommandError),
        ):
            await create_session_lifecycle(
                session_name="partial-rollback",
                tool="claude",
                git_root="/tmp/repo",
                wt_path=str(wt),
                work_dir=str(wt),
                branch_name="feat/test",
                tool_command="claude",
                startup_commands=["send-keys -t {tmux_session} 'echo hi' Enter"],
            )

        # Verify warning was logged for the failed worktree removal
        warning_calls = [
            call for call in mock_logger.warning.call_args_list if "worktree" in str(call).lower()
        ]
        assert len(warning_calls) >= 1

    async def test_no_worktree_rollback_when_no_wt_path(self, mock_dirs):
        """When there's no worktree, rollback should not attempt worktree removal."""
        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session", side_effect=RuntimeError("no tmux")),
            patch("shoal.core.git.worktree_remove") as mock_wt_rm,
            pytest.raises(TmuxSetupError),
        ):
            await create_session_lifecycle(
                session_name="no-wt",
                tool="claude",
                git_root="/tmp/repo",
                wt_path="",
                work_dir="/tmp/repo",
                branch_name="main",
                tool_command="claude",
                startup_commands=[],
            )

        mock_wt_rm.assert_not_called()
        sessions = await list_sessions()
        assert len(sessions) == 0


# ---------------------------------------------------------------------------
# Fork rollback matrix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestForkRollback:
    async def test_fork_tmux_failure_rolls_back(self, mock_dirs, tmp_path):
        """Fork tmux failure should clean up DB row + worktree."""
        wt = tmp_path / "worktree"
        wt.mkdir()

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session", side_effect=RuntimeError("no tmux")),
            patch("shoal.core.git.worktree_remove", return_value=True) as mock_wt_rm,
            pytest.raises(TmuxSetupError),
        ):
            await fork_session_lifecycle(
                session_name="fork-tmux-fail",
                source_tool="claude",
                source_path="/tmp/repo",
                source_branch="main",
                wt_path=str(wt),
                work_dir=str(wt),
                new_branch="feat/fork",
                tool_command="claude",
                startup_commands=[],
            )

        sessions = await list_sessions()
        assert len(sessions) == 0
        mock_wt_rm.assert_called_once()

    async def test_fork_startup_failure_rolls_back(self, mock_dirs, tmp_path):
        """Fork startup failure should clean up DB + tmux + worktree (fixes previous gap)."""
        wt = tmp_path / "worktree"
        wt.mkdir()

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session"),
            patch("shoal.core.tmux.set_environment"),
            patch("shoal.core.tmux.kill_session") as mock_tmux_kill,
            patch("shoal.core.tmux.run_command", side_effect=ValueError("bad cmd")),
            patch("shoal.core.git.worktree_remove", return_value=True) as mock_wt_rm,
            pytest.raises(StartupCommandError),
        ):
            await fork_session_lifecycle(
                session_name="fork-startup-fail",
                source_tool="claude",
                source_path="/tmp/repo",
                source_branch="main",
                wt_path=str(wt),
                work_dir=str(wt),
                new_branch="feat/fork",
                tool_command="claude",
                startup_commands=["send-keys -t {tmux_session} 'echo hi' Enter"],
            )

        # All three resources cleaned up
        sessions = await list_sessions()
        assert len(sessions) == 0
        mock_tmux_kill.assert_called()
        mock_wt_rm.assert_called_once()


# ---------------------------------------------------------------------------
# API boundary validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestApiBoundaryValidation:
    async def test_mcp_path_traversal_rejected(self, async_client):
        """POST /mcp with path traversal name should be rejected."""
        response = await async_client.post(
            "/mcp",
            json={"name": "../../../etc"},
        )
        assert response.status_code in (400, 422)

    async def test_mcp_shell_injection_rejected(self, async_client):
        """POST /mcp with shell injection should be rejected."""
        response = await async_client.post(
            "/mcp",
            json={"name": "$(whoami)"},
        )
        assert response.status_code in (400, 422)
