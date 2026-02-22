"""Unit tests for services/lifecycle.py — core lifecycle operations."""

from unittest.mock import patch

import pytest

from shoal.core.state import create_session, get_session, update_session
from shoal.models.state import SessionStatus
from shoal.services.lifecycle import (
    _reconcile_mcp_pool,
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


@pytest.mark.asyncio
class TestMcpProvisioning:
    """Tests for _provision_mcp_servers()."""

    async def test_create_with_mcp(self, mock_dirs):
        """MCP servers are provisioned during session creation."""
        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session"),
            patch("shoal.core.tmux.set_environment"),
            patch("shoal.core.tmux.set_pane_title"),
            patch("shoal.core.tmux.preferred_pane", return_value="_test"),
            patch("shoal.core.tmux.pane_pid", return_value=42),
            patch("shoal.core.tmux.pane_coordinates", return_value=("$1", "@0")),
            patch("shoal.core.tmux.run_command"),
            patch(
                "shoal.core.config.load_mcp_registry",
                return_value={"memory": "npx mem"},
            ),
            patch("shoal.services.mcp_pool.is_mcp_running", return_value=False),
            patch(
                "shoal.services.mcp_pool.start_mcp_server",
                return_value=(123, "/tmp/s.sock", "npx mem"),
            ),
            patch("shoal.services.mcp_configure.subprocess.run"),
        ):
            session = await create_session_lifecycle(
                session_name="mcp-test",
                tool="claude",
                git_root="/tmp/repo",
                wt_path="",
                work_dir="/tmp/repo",
                branch_name="main",
                tool_command="claude",
                startup_commands=[],
                mcp_servers=["memory"],
            )

            assert "memory" in session.mcp_servers

    async def test_mcp_failure_does_not_block(self, mock_dirs):
        """Session creation succeeds even if MCP provisioning fails."""
        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session"),
            patch("shoal.core.tmux.set_environment"),
            patch("shoal.core.tmux.set_pane_title"),
            patch("shoal.core.tmux.preferred_pane", return_value="_test"),
            patch("shoal.core.tmux.pane_pid", return_value=42),
            patch("shoal.core.tmux.pane_coordinates", return_value=("$1", "@0")),
            patch("shoal.core.tmux.run_command"),
            patch(
                "shoal.core.config.load_mcp_registry",
                return_value={"memory": "npx mem"},
            ),
            patch("shoal.services.mcp_pool.is_mcp_running", return_value=False),
            patch(
                "shoal.services.mcp_pool.start_mcp_server",
                side_effect=RuntimeError("failed"),
            ),
        ):
            session = await create_session_lifecycle(
                session_name="mcp-fail-test",
                tool="claude",
                git_root="/tmp/repo",
                wt_path="",
                work_dir="/tmp/repo",
                branch_name="main",
                tool_command="claude",
                startup_commands=[],
                mcp_servers=["memory"],
            )

            # Session is created despite MCP failure
            assert session.name == "mcp-fail-test"
            assert session.mcp_servers == []

    async def test_mcp_partial_failure(self, mock_dirs):
        """Only successfully provisioned MCPs appear in the session."""
        call_count = 0

        def start_side_effect(name, command):
            nonlocal call_count
            call_count += 1
            if name == "github":
                raise RuntimeError("github failed")
            return (123, "/tmp/s.sock", command)

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session"),
            patch("shoal.core.tmux.set_environment"),
            patch("shoal.core.tmux.set_pane_title"),
            patch("shoal.core.tmux.preferred_pane", return_value="_test"),
            patch("shoal.core.tmux.pane_pid", return_value=42),
            patch("shoal.core.tmux.pane_coordinates", return_value=("$1", "@0")),
            patch("shoal.core.tmux.run_command"),
            patch(
                "shoal.core.config.load_mcp_registry",
                return_value={"memory": "npx mem", "github": "npx gh"},
            ),
            patch("shoal.services.mcp_pool.is_mcp_running", return_value=False),
            patch(
                "shoal.services.mcp_pool.start_mcp_server",
                side_effect=start_side_effect,
            ),
            patch("shoal.services.mcp_configure.subprocess.run"),
        ):
            session = await create_session_lifecycle(
                session_name="partial-mcp-test",
                tool="claude",
                git_root="/tmp/repo",
                wt_path="",
                work_dir="/tmp/repo",
                branch_name="main",
                tool_command="claude",
                startup_commands=[],
                mcp_servers=["memory", "github"],
            )

            # Only memory succeeded
            assert "memory" in session.mcp_servers
            assert "github" not in session.mcp_servers

    async def test_template_mcp_merge_with_flag(self, mock_dirs):
        """Template MCP list merges with --mcp flag (union, deduped)."""
        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session"),
            patch("shoal.core.tmux.set_environment"),
            patch("shoal.core.tmux.set_pane_title"),
            patch("shoal.core.tmux.preferred_pane", return_value="_test"),
            patch("shoal.core.tmux.pane_pid", return_value=42),
            patch("shoal.core.tmux.pane_coordinates", return_value=("$1", "@0")),
            patch("shoal.core.tmux.run_command"),
            patch(
                "shoal.core.config.load_mcp_registry",
                return_value={"memory": "npx mem", "github": "npx gh", "fetch": "npx f"},
            ),
            patch("shoal.services.mcp_pool.is_mcp_running", return_value=False),
            patch(
                "shoal.services.mcp_pool.start_mcp_server",
                return_value=(123, "/tmp/s.sock", "npx cmd"),
            ),
            patch("shoal.services.mcp_configure.subprocess.run"),
        ):
            # Simulate merged list: template has ["memory"] + flag has ["github"]
            # Merged in cli/session.py: sorted({"memory", "github"}) = ["github", "memory"]
            session = await create_session_lifecycle(
                session_name="merge-test",
                tool="claude",
                git_root="/tmp/repo",
                wt_path="",
                work_dir="/tmp/repo",
                branch_name="main",
                tool_command="claude",
                startup_commands=[],
                mcp_servers=["github", "memory"],
            )

            assert "memory" in session.mcp_servers
            assert "github" in session.mcp_servers


@pytest.mark.asyncio
class TestMcpCleanup:
    """Tests for MCP cleanup on kill and reconciliation."""

    async def test_kill_stops_orphaned_mcp(self, mock_dirs):
        """Killing last session using an MCP stops that MCP server."""
        s = await create_session("mcp-user", "claude", "/tmp/repo")
        await update_session(s.id, mcp_servers=["memory"])

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch("shoal.core.tmux.kill_session"),
            patch("shoal.services.mcp_pool.is_mcp_running", return_value=True),
            patch("shoal.services.mcp_pool.stop_mcp_server") as mock_stop,
        ):
            summary = await kill_session_lifecycle(
                session_id=s.id,
                tmux_session=s.tmux_session,
            )

        assert summary["mcp_stopped"] is True
        mock_stop.assert_called_once_with("memory")

    async def test_kill_keeps_shared_mcp(self, mock_dirs):
        """MCP server used by another session is NOT stopped."""
        s1 = await create_session("user1", "claude", "/tmp/repo")
        await update_session(s1.id, mcp_servers=["memory"])
        s2 = await create_session("user2", "claude", "/tmp/repo")
        await update_session(s2.id, mcp_servers=["memory"])

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch("shoal.core.tmux.kill_session"),
            patch("shoal.services.mcp_pool.is_mcp_running", return_value=True),
            patch("shoal.services.mcp_pool.stop_mcp_server") as mock_stop,
        ):
            summary = await kill_session_lifecycle(
                session_id=s1.id,
                tmux_session=s1.tmux_session,
            )

        # Should NOT stop since s2 still uses memory
        assert summary["mcp_stopped"] is False
        mock_stop.assert_not_called()

    async def test_reconcile_cleans_dead_mcp(self, mock_dirs):
        """Reconciliation cleans up dead MCP socket/PID files."""
        _, tmp_state = mock_dirs
        socket_dir = tmp_state / "mcp-pool" / "sockets"
        pid_dir = tmp_state / "mcp-pool" / "pids"

        # Create a dead MCP entry
        (socket_dir / "dead-server.sock").touch()
        (pid_dir / "dead-server.pid").write_text("99999")

        with (
            patch("shoal.services.mcp_pool.state_dir", return_value=tmp_state),
            patch("shoal.services.mcp_pool.is_mcp_running", return_value=False),
        ):
            cleaned = _reconcile_mcp_pool()

        assert "dead-server" in cleaned
        assert not (socket_dir / "dead-server.sock").exists()
        assert not (pid_dir / "dead-server.pid").exists()

    async def test_reconcile_preserves_running_mcp(self, mock_dirs):
        """Reconciliation preserves running MCP servers."""
        _, tmp_state = mock_dirs
        socket_dir = tmp_state / "mcp-pool" / "sockets"
        pid_dir = tmp_state / "mcp-pool" / "pids"

        # Create a running MCP entry
        (socket_dir / "running-server.sock").touch()
        (pid_dir / "running-server.pid").write_text("12345")

        with (
            patch("shoal.services.mcp_pool.state_dir", return_value=tmp_state),
            patch("shoal.services.mcp_pool.is_mcp_running", return_value=True),
        ):
            cleaned = _reconcile_mcp_pool()

        assert cleaned == []
        assert (socket_dir / "running-server.sock").exists()
        assert (pid_dir / "running-server.pid").exists()

    async def test_reconcile_cleans_orphaned_socket(self, mock_dirs):
        """Reconciliation cleans socket with no PID file."""
        _, tmp_state = mock_dirs
        socket_dir = tmp_state / "mcp-pool" / "sockets"

        # Orphaned socket (no PID file)
        (socket_dir / "orphan.sock").touch()

        with patch("shoal.services.mcp_pool.state_dir", return_value=tmp_state):
            cleaned = _reconcile_mcp_pool()
        assert "orphan" in cleaned
        assert not (socket_dir / "orphan.sock").exists()
