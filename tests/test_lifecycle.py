"""Unit tests for services/lifecycle.py — core lifecycle operations."""

from unittest.mock import patch

import pytest

from shoal.core.state import create_session, get_session
from shoal.models.state import SessionStatus
from shoal.services.lifecycle import (
    _rollback_async,
    create_session_lifecycle,
    kill_session_lifecycle,
    reconcile_sessions,
)


@pytest.mark.asyncio
class TestRollbackAsync:
    """Tests for _rollback_async()."""

    async def test_rollback_deletes_db_row(self, mock_dirs):
        s = await create_session("to-rollback", "claude", "/tmp/repo")
        assert await get_session(s.id) is not None

        warnings = await _rollback_async(session_id=s.id)
        assert warnings == []
        assert await get_session(s.id) is None

    async def test_rollback_kills_tmux(self, mock_dirs):
        with patch("shoal.core.tmux.kill_session") as mock_kill:
            warnings = await _rollback_async(tmux_name="test-session")
            mock_kill.assert_called_once_with("test-session")
            assert warnings == []

    async def test_rollback_removes_worktree(self, mock_dirs, tmp_path):
        wt = tmp_path / "worktree"
        wt.mkdir()
        with patch("shoal.core.git.worktree_remove", return_value=True) as mock_rm:
            warnings = await _rollback_async(wt_path=str(wt), git_root="/tmp/repo")
            mock_rm.assert_called_once()
            assert warnings == []

    async def test_rollback_skips_missing_worktree(self, mock_dirs):
        warnings = await _rollback_async(wt_path="/nonexistent/path", git_root="/tmp/repo")
        assert warnings == []

    async def test_rollback_partial_failure_logs_warnings(self, mock_dirs, tmp_path):
        """If one rollback step fails, the others still run."""
        s = await create_session("partial", "claude", "/tmp/repo")
        wt = tmp_path / "worktree"
        wt.mkdir()

        with (
            patch("shoal.core.tmux.kill_session", side_effect=RuntimeError("tmux dead")),
            patch("shoal.core.git.worktree_remove", side_effect=RuntimeError("wt stuck")),
        ):
            warnings = await _rollback_async(
                session_id=s.id,
                tmux_name="bad-session",
                wt_path=str(wt),
                git_root="/tmp/repo",
            )
            # DB row should still be deleted (it doesn't fail)
            assert await get_session(s.id) is None
            # But tmux and worktree failures produce warnings
            assert len(warnings) == 2
            assert any("tmux" in w for w in warnings)
            assert any("worktree" in w for w in warnings)

    async def test_rollback_empty_params(self, mock_dirs):
        """Calling rollback with no params is a no-op."""
        warnings = await _rollback_async()
        assert warnings == []


@pytest.mark.asyncio
class TestCreateSessionLifecycle:
    """Tests for create_session_lifecycle() happy path."""

    async def test_happy_path(self, mock_dirs):
        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session"),
            patch("shoal.core.tmux.set_environment"),
            patch("shoal.core.tmux.set_pane_title"),
            patch("shoal.core.tmux.preferred_pane", return_value="_test"),
            patch("shoal.core.tmux.pane_pid", return_value=42),
            patch("shoal.core.tmux.pane_coordinates", return_value=("$1", "@0")),
            patch("shoal.core.tmux.run_command"),
        ):
            session = await create_session_lifecycle(
                session_name="test",
                tool="claude",
                git_root="/tmp/repo",
                wt_path="",
                work_dir="/tmp/repo",
                branch_name="main",
                tool_command="claude",
                startup_commands=[],
            )

            assert session.name == "test"
            assert session.status == SessionStatus.running
            assert session.pid == 42
            assert session.tmux_session_id == "$1"
            assert session.tmux_window == "@0"


@pytest.mark.asyncio
class TestReconcileSessions:
    """Tests for reconcile_sessions()."""

    async def test_marks_stopped_when_tmux_gone(self, mock_dirs):
        from shoal.core.state import update_session

        s = await create_session("alive", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.running)

        with patch("shoal.core.tmux.has_session", return_value=False):
            reconciled = await reconcile_sessions()

        assert len(reconciled) == 1
        assert reconciled[0][0] == s.id
        assert "marked stopped" in reconciled[0][2]

        updated = await get_session(s.id)
        assert updated.status == SessionStatus.stopped

    async def test_ignores_already_stopped(self, mock_dirs):
        from shoal.core.state import update_session

        s = await create_session("already-stopped", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.stopped)

        reconciled = await reconcile_sessions()
        assert len(reconciled) == 0

    async def test_ignores_live_sessions(self, mock_dirs):
        from shoal.core.state import update_session

        s = await create_session("live", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.running)

        with patch("shoal.core.tmux.has_session", return_value=True):
            reconciled = await reconcile_sessions()

        assert len(reconciled) == 0

    async def test_multiple_stale(self, mock_dirs):
        from shoal.core.state import update_session

        s1 = await create_session("stale1", "claude", "/tmp/repo")
        await update_session(s1.id, status=SessionStatus.running)
        s2 = await create_session("stale2", "claude", "/tmp/repo")
        await update_session(s2.id, status=SessionStatus.waiting)

        with patch("shoal.core.tmux.has_session", return_value=False):
            reconciled = await reconcile_sessions()

        assert len(reconciled) == 2
        ids = {r[0] for r in reconciled}
        assert s1.id in ids
        assert s2.id in ids


@pytest.mark.asyncio
class TestKillSessionLifecycle:
    async def test_kill_basic(self, mock_dirs):
        s = await create_session("to-kill", "claude", "/tmp/repo")

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch("shoal.core.tmux.kill_session"),
        ):
            summary = await kill_session_lifecycle(
                session_id=s.id,
                tmux_session=s.tmux_session,
            )

        assert summary["tmux_killed"] is True
        assert summary["db_deleted"] is True
        assert await get_session(s.id) is None

    async def test_kill_tmux_already_dead(self, mock_dirs):
        s = await create_session("dead-tmux", "claude", "/tmp/repo")

        with patch("shoal.core.tmux.has_session", return_value=False):
            summary = await kill_session_lifecycle(
                session_id=s.id,
                tmux_session=s.tmux_session,
            )

        assert summary["tmux_killed"] is False
        assert summary["db_deleted"] is True
