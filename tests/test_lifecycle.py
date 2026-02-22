"""Unit tests for services/lifecycle.py — core lifecycle operations."""

from unittest.mock import patch

import pytest

from shoal.core.state import create_session, get_session, update_session
from shoal.models.state import SessionStatus
from shoal.services.lifecycle import (
    DirtyWorktreeError,
    LifecycleError,
    _rollback_async,
    create_session_lifecycle,
    fork_session_lifecycle,
    kill_session_lifecycle,
    reconcile_mcp_pool,
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
            cleaned = reconcile_mcp_pool()

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
            cleaned = reconcile_mcp_pool()

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
            cleaned = reconcile_mcp_pool()
        assert "orphan" in cleaned
        assert not (socket_dir / "orphan.sock").exists()


@pytest.mark.asyncio
class TestStartupExceptionNarrowing:
    """Verify narrowed exception handling only catches expected types."""

    async def test_runtime_error_propagates_uncaught(self, mock_dirs, tmp_path):
        """RuntimeError from startup should propagate, not be wrapped."""
        wt = tmp_path / "worktree"
        wt.mkdir()

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session"),
            patch("shoal.core.tmux.set_environment"),
            patch("shoal.core.tmux.kill_session"),
            patch(
                "shoal.core.tmux.run_command",
                side_effect=RuntimeError("unexpected"),
            ),
            patch("shoal.core.git.worktree_remove", return_value=True),
            pytest.raises(RuntimeError, match="unexpected"),
        ):
            await create_session_lifecycle(
                session_name="narrow-test",
                tool="claude",
                git_root="/tmp/repo",
                wt_path=str(wt),
                work_dir=str(wt),
                branch_name="feat/test",
                tool_command="claude",
                startup_commands=["send-keys -t {tmux_session} 'echo hi' Enter"],
            )


@pytest.mark.asyncio
class TestDirtyWorktreeProtection:
    """Verify dirty worktree detection in kill_session_lifecycle."""

    async def test_dirty_worktree_blocks_kill(self, mock_dirs):
        """Dirty worktree should raise DirtyWorktreeError without force."""
        s = await create_session("dirty-wt", "claude", "/tmp/repo", worktree="/tmp/wt")

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.git.worktree_is_dirty", return_value=True),
            patch("pathlib.Path.is_dir", return_value=True),
            patch("subprocess.run") as mock_run,
            pytest.raises(DirtyWorktreeError, match="uncommitted"),
        ):
            mock_run.return_value.stdout = " M file.txt"
            await kill_session_lifecycle(
                session_id=s.id,
                tmux_session=s.tmux_session,
                worktree=s.worktree,
                git_root=s.path,
                remove_worktree=True,
            )

    async def test_clean_worktree_proceeds(self, mock_dirs):
        """Clean worktree should proceed normally."""
        s = await create_session("clean-wt", "claude", "/tmp/repo", worktree="/tmp/wt")

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.git.worktree_is_dirty", return_value=False),
            patch("shoal.core.git.worktree_remove", return_value=True),
            patch("pathlib.Path.is_dir", return_value=True),
        ):
            summary = await kill_session_lifecycle(
                session_id=s.id,
                tmux_session=s.tmux_session,
                worktree=s.worktree,
                git_root=s.path,
                remove_worktree=True,
            )
            assert summary["worktree_removed"] is True

    async def test_force_overrides_dirty_check(self, mock_dirs):
        """Force flag should override dirty worktree check."""
        s = await create_session("force-wt", "claude", "/tmp/repo", worktree="/tmp/wt")

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.git.worktree_is_dirty", return_value=True),
            patch("shoal.core.git.worktree_remove", return_value=True),
            patch("pathlib.Path.is_dir", return_value=True),
        ):
            summary = await kill_session_lifecycle(
                session_id=s.id,
                tmux_session=s.tmux_session,
                worktree=s.worktree,
                git_root=s.path,
                remove_worktree=True,
                force=True,
            )
            assert summary["worktree_removed"] is True

    async def test_dirty_files_in_exception(self, mock_dirs):
        """DirtyWorktreeError should contain dirty file list."""
        s = await create_session("files-wt", "claude", "/tmp/repo", worktree="/tmp/wt")

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.git.worktree_is_dirty", return_value=True),
            patch("pathlib.Path.is_dir", return_value=True),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value.stdout = " M file.txt\n?? new.py"
            try:
                await kill_session_lifecycle(
                    session_id=s.id,
                    tmux_session=s.tmux_session,
                    worktree=s.worktree,
                    git_root=s.path,
                    remove_worktree=True,
                )
            except DirtyWorktreeError as exc:
                assert "file.txt" in exc.dirty_files
                assert "new.py" in exc.dirty_files


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSessionExistsError:
    """Tests for SessionExistsError paths in create and fork."""

    async def test_create_raises_session_exists_on_collision(self, mock_dirs):
        """create_session_lifecycle raises SessionExistsError on tmux name collision."""
        from shoal.services.lifecycle import SessionExistsError

        # has_session returns True to simulate tmux collision
        with (
            pytest.raises(SessionExistsError, match="collides|already exists"),
            patch("shoal.core.tmux.has_session", return_value=True),
        ):
            await create_session_lifecycle(
                session_name="collision",
                tool="claude",
                git_root="/tmp/repo",
                wt_path="",
                work_dir="/tmp/repo",
                branch_name="main",
                tool_command="claude",
                startup_commands=[],
            )

    async def test_fork_raises_session_exists_on_collision(self, mock_dirs):
        """fork_session_lifecycle raises SessionExistsError on tmux name collision."""
        from shoal.services.lifecycle import SessionExistsError

        # has_session returns True to simulate tmux collision
        with (
            pytest.raises(SessionExistsError, match="collides|already exists"),
            patch("shoal.core.tmux.has_session", return_value=True),
        ):
            await fork_session_lifecycle(
                session_name="fork-dup",
                source_tool="claude",
                source_path="/tmp/repo",
                source_branch="main",
                wt_path="",
                work_dir="/tmp/repo",
                new_branch="feat/fork",
                tool_command="claude",
                startup_commands=[],
            )


@pytest.mark.asyncio
class TestForkSessionLifecycle:
    """Tests for fork_session_lifecycle() happy and error paths."""

    async def test_fork_happy_path(self, mock_dirs):
        """Fork creates a session with correct fields."""
        from shoal.services.lifecycle import fork_session_lifecycle

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session"),
            patch("shoal.core.tmux.set_environment"),
            patch("shoal.core.tmux.set_pane_title"),
            patch("shoal.core.tmux.preferred_pane", return_value="_test"),
            patch("shoal.core.tmux.pane_pid", return_value=99),
            patch("shoal.core.tmux.pane_coordinates", return_value=("$2", "@1")),
            patch("shoal.core.tmux.run_command"),
        ):
            session = await fork_session_lifecycle(
                session_name="fork-test",
                source_tool="claude",
                source_path="/tmp/repo",
                source_branch="main",
                wt_path="/tmp/wt",
                work_dir="/tmp/wt",
                new_branch="feat/fork",
                tool_command="claude",
                startup_commands=[],
            )

        assert session.name == "fork-test"
        assert session.status == SessionStatus.running
        assert session.pid == 99
        assert session.tmux_session_id == "$2"
        assert session.tmux_window == "@1"

    async def test_fork_with_mcp(self, mock_dirs):
        """Fork with MCP provisioning."""
        from shoal.services.lifecycle import fork_session_lifecycle

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
            session = await fork_session_lifecycle(
                session_name="fork-mcp-test",
                source_tool="claude",
                source_path="/tmp/repo",
                source_branch="main",
                wt_path="/tmp/wt",
                work_dir="/tmp/wt",
                new_branch="feat/fork",
                tool_command="claude",
                startup_commands=[],
                mcp_servers=["memory"],
            )

        assert "memory" in session.mcp_servers

    async def test_fork_no_pid(self, mock_dirs):
        """Fork proceeds when pane PID is None."""
        from shoal.services.lifecycle import fork_session_lifecycle

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session"),
            patch("shoal.core.tmux.set_environment"),
            patch("shoal.core.tmux.set_pane_title"),
            patch("shoal.core.tmux.preferred_pane", return_value="_test"),
            patch("shoal.core.tmux.pane_pid", return_value=None),
            patch("shoal.core.tmux.pane_coordinates", return_value=None),
            patch("shoal.core.tmux.run_command"),
        ):
            session = await fork_session_lifecycle(
                session_name="fork-no-pid",
                source_tool="claude",
                source_path="/tmp/repo",
                source_branch="main",
                wt_path="",
                work_dir="/tmp/repo",
                new_branch="feat/fork",
                tool_command="claude",
                startup_commands=[],
            )

        assert session.name == "fork-no-pid"
        assert session.status == SessionStatus.running
        assert session.pid is None


@pytest.mark.asyncio
class TestKillSessionLifecycleExtended:
    """Extended kill lifecycle tests for uncovered paths."""

    async def test_kill_with_worktree_and_branch_delete(self, mock_dirs):
        """Kill removes worktree and deletes non-protected branch."""
        s = await create_session("kill-wt-br", "claude", "/tmp/repo", worktree="/tmp/wt")

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch("shoal.core.tmux.kill_session"),
            patch("shoal.core.git.worktree_is_dirty", return_value=False),
            patch("shoal.core.git.worktree_remove", return_value=True),
            patch("shoal.core.git.branch_delete", return_value=True),
            patch("pathlib.Path.is_dir", return_value=True),
        ):
            summary = await kill_session_lifecycle(
                session_id=s.id,
                tmux_session=s.tmux_session,
                worktree="/tmp/wt",
                git_root="/tmp/repo",
                branch="feat/my-feature",
                remove_worktree=True,
            )

        assert summary["tmux_killed"] is True
        assert summary["worktree_removed"] is True
        assert summary["branch_deleted"] is True
        assert summary["db_deleted"] is True

    async def test_kill_skips_protected_branch_delete(self, mock_dirs):
        """Kill does not delete main or master branches."""
        s = await create_session("kill-main", "claude", "/tmp/repo", worktree="/tmp/wt")

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.git.worktree_is_dirty", return_value=False),
            patch("shoal.core.git.worktree_remove", return_value=True),
            patch("shoal.core.git.branch_delete") as mock_branch_delete,
            patch("pathlib.Path.is_dir", return_value=True),
        ):
            summary = await kill_session_lifecycle(
                session_id=s.id,
                tmux_session=s.tmux_session,
                worktree="/tmp/wt",
                git_root="/tmp/repo",
                branch="main",
                remove_worktree=True,
            )

        assert summary["branch_deleted"] is False
        mock_branch_delete.assert_not_called()

    async def test_kill_skips_worktree_when_dir_missing(self, mock_dirs):
        """Kill skips worktree removal when the directory does not exist."""
        s = await create_session("kill-nodir", "claude", "/tmp/repo", worktree="/tmp/wt")

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("pathlib.Path.is_dir", return_value=False),
            patch("shoal.core.git.worktree_remove") as mock_wt_rm,
        ):
            summary = await kill_session_lifecycle(
                session_id=s.id,
                tmux_session=s.tmux_session,
                worktree="/tmp/wt",
                git_root="/tmp/repo",
                remove_worktree=True,
            )

        assert summary["worktree_removed"] is False
        mock_wt_rm.assert_not_called()

    async def test_kill_no_worktree_flag(self, mock_dirs):
        """Kill without remove_worktree flag skips worktree handling."""
        s = await create_session("kill-nowt", "claude", "/tmp/repo", worktree="/tmp/wt")

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.git.worktree_remove") as mock_wt_rm,
        ):
            summary = await kill_session_lifecycle(
                session_id=s.id,
                tmux_session=s.tmux_session,
                worktree="/tmp/wt",
                git_root="/tmp/repo",
                remove_worktree=False,
            )

        assert summary["worktree_removed"] is False
        mock_wt_rm.assert_not_called()
        assert summary["db_deleted"] is True


@pytest.mark.asyncio
class TestCreateSessionLifecycleExtended:
    """Extended create lifecycle tests for uncovered paths."""

    async def test_create_no_pid(self, mock_dirs):
        """Create proceeds when pane PID is None."""
        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session"),
            patch("shoal.core.tmux.set_environment"),
            patch("shoal.core.tmux.set_pane_title"),
            patch("shoal.core.tmux.preferred_pane", return_value="_test"),
            patch("shoal.core.tmux.pane_pid", return_value=None),
            patch("shoal.core.tmux.pane_coordinates", return_value=None),
            patch("shoal.core.tmux.run_command"),
        ):
            session = await create_session_lifecycle(
                session_name="no-pid",
                tool="claude",
                git_root="/tmp/repo",
                wt_path="",
                work_dir="/tmp/repo",
                branch_name="main",
                tool_command="claude",
                startup_commands=[],
            )

        assert session.pid is None
        assert session.tmux_session_id == ""
        assert session.tmux_window == ""

    async def test_create_with_startup_commands(self, mock_dirs):
        """Create runs startup commands with interpolation."""
        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session"),
            patch("shoal.core.tmux.set_environment"),
            patch("shoal.core.tmux.set_pane_title"),
            patch("shoal.core.tmux.preferred_pane", return_value="_test"),
            patch("shoal.core.tmux.pane_pid", return_value=42),
            patch("shoal.core.tmux.pane_coordinates", return_value=("$1", "@0")),
            patch("shoal.core.tmux.run_command") as mock_run,
        ):
            session = await create_session_lifecycle(
                session_name="cmd-test",
                tool="claude",
                git_root="/tmp/repo",
                wt_path="",
                work_dir="/tmp/repo",
                branch_name="main",
                tool_command="claude",
                startup_commands=["send-keys -t {tmux_session} 'echo {session_name}' Enter"],
            )

        assert session.name == "cmd-test"
        # Verify startup command was called (plus potential other run_command calls)
        assert mock_run.call_count >= 1

    async def test_create_with_worktree(self, mock_dirs, tmp_path):
        """Create with a worktree path sets session fields."""
        wt = tmp_path / "worktree"
        wt.mkdir()

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
                session_name="wt-create",
                tool="claude",
                git_root="/tmp/repo",
                wt_path=str(wt),
                work_dir=str(wt),
                branch_name="feat/wt",
                tool_command="claude",
                startup_commands=[],
            )

        assert session.name == "wt-create"
        assert session.worktree == str(wt)


@pytest.mark.asyncio
class TestReconcileSessionsExtended:
    """Extended reconcile tests for MCP pool integration."""

    async def test_reconcile_includes_mcp_cleanup(self, mock_dirs):
        """Reconcile result includes MCP pool cleanup entries."""
        _, tmp_state = mock_dirs
        socket_dir = tmp_state / "mcp-pool" / "sockets"
        pid_dir = tmp_state / "mcp-pool" / "pids"

        # Create a dead MCP entry
        (socket_dir / "stale-mcp.sock").touch()
        (pid_dir / "stale-mcp.pid").write_text("99999")

        with (
            patch("shoal.services.mcp_pool.is_mcp_running", return_value=False),
        ):
            reconciled = await reconcile_sessions()

        mcp_entries = [r for r in reconciled if r[0] == "mcp"]
        assert len(mcp_entries) == 1
        assert "stale-mcp" in mcp_entries[0][1]

    async def test_reconcile_mixed_sessions_and_mcp(self, mock_dirs):
        """Reconcile handles both stale sessions and dead MCP."""
        _, tmp_state = mock_dirs
        socket_dir = tmp_state / "mcp-pool" / "sockets"
        pid_dir = tmp_state / "mcp-pool" / "pids"

        # Create a stale session
        s = await create_session("stale-mixed", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.running)

        # Create a dead MCP entry
        (socket_dir / "dead-mixed.sock").touch()
        (pid_dir / "dead-mixed.pid").write_text("99999")

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.services.mcp_pool.is_mcp_running", return_value=False),
        ):
            reconciled = await reconcile_sessions()

        session_entries = [r for r in reconciled if r[0] != "mcp"]
        mcp_entries = [r for r in reconciled if r[0] == "mcp"]
        assert len(session_entries) == 1
        assert session_entries[0][0] == s.id
        assert len(mcp_entries) == 1


@pytest.mark.asyncio
class TestSyncRollback:
    """Tests for the sync _rollback() helper."""

    async def test_sync_rollback_kills_tmux(self, mock_dirs):
        """Sync rollback kills tmux session."""
        from shoal.services.lifecycle import _rollback

        with patch("shoal.core.tmux.kill_session") as mock_kill:
            warnings = _rollback(tmux_name="test-sync")
            mock_kill.assert_called_once_with("test-sync")
            assert warnings == []

    async def test_sync_rollback_removes_worktree(self, mock_dirs, tmp_path):
        """Sync rollback removes worktree."""
        from shoal.services.lifecycle import _rollback

        wt = tmp_path / "worktree"
        wt.mkdir()

        with patch("shoal.core.git.worktree_remove", return_value=True) as mock_rm:
            warnings = _rollback(wt_path=str(wt), git_root="/tmp/repo")
            mock_rm.assert_called_once()
            assert warnings == []

    async def test_sync_rollback_skips_missing_worktree(self, mock_dirs):
        """Sync rollback skips non-existent worktree."""
        from shoal.services.lifecycle import _rollback

        warnings = _rollback(wt_path="/nonexistent/path", git_root="/tmp/repo")
        assert warnings == []

    async def test_sync_rollback_handles_tmux_failure(self, mock_dirs):
        """Sync rollback logs warning on tmux kill failure."""
        from shoal.services.lifecycle import _rollback

        with patch("shoal.core.tmux.kill_session", side_effect=RuntimeError("tmux dead")):
            warnings = _rollback(tmux_name="bad-session")
            assert len(warnings) == 1
            assert "tmux" in warnings[0]

    async def test_sync_rollback_handles_worktree_failure(self, mock_dirs, tmp_path):
        """Sync rollback logs warning on worktree removal failure."""
        from shoal.services.lifecycle import _rollback

        wt = tmp_path / "worktree"
        wt.mkdir()

        with patch("shoal.core.git.worktree_remove", side_effect=RuntimeError("wt stuck")):
            warnings = _rollback(wt_path=str(wt), git_root="/tmp/repo")
            assert len(warnings) == 1
            assert "worktree" in warnings[0]

    async def test_sync_rollback_empty_is_noop(self, mock_dirs):
        """Sync rollback with no params is a no-op."""
        from shoal.services.lifecycle import _rollback

        warnings = _rollback()
        assert warnings == []

    async def test_sync_rollback_skips_worktree_without_git_root(self, mock_dirs, tmp_path):
        """Sync rollback skips worktree removal when git_root is empty."""
        from shoal.services.lifecycle import _rollback

        wt = tmp_path / "worktree"
        wt.mkdir()

        with patch("shoal.core.git.worktree_remove") as mock_rm:
            warnings = _rollback(wt_path=str(wt), git_root="")
            mock_rm.assert_not_called()
            assert warnings == []


@pytest.mark.asyncio
class TestRollbackAsyncExtended:
    """Extended tests for _rollback_async() with async tmux/git calls."""

    async def test_rollback_async_calls_async_kill(self, mock_dirs):
        """Async rollback uses async_kill_session."""
        with patch("shoal.core.tmux.async_kill_session") as mock_kill:
            warnings = await _rollback_async(tmux_name="async-kill")
            mock_kill.assert_called_once_with("async-kill")
            assert warnings == []

    async def test_rollback_async_calls_async_worktree_remove(self, mock_dirs, tmp_path):
        """Async rollback uses async_worktree_remove."""
        wt = tmp_path / "worktree"
        wt.mkdir()

        with patch("shoal.core.git.async_worktree_remove", return_value=True) as mock_rm:
            warnings = await _rollback_async(wt_path=str(wt), git_root="/tmp/repo")
            mock_rm.assert_called_once()
            assert warnings == []

    async def test_rollback_async_skips_worktree_without_git_root(self, mock_dirs, tmp_path):
        """Async rollback skips worktree removal when git_root is empty."""
        wt = tmp_path / "worktree"
        wt.mkdir()

        with patch("shoal.core.git.async_worktree_remove") as mock_rm:
            warnings = await _rollback_async(wt_path=str(wt), git_root="")
            mock_rm.assert_not_called()
            assert warnings == []

    async def test_rollback_async_partial_failure(self, mock_dirs, tmp_path):
        """Async rollback continues when individual steps fail."""
        s = await create_session("async-partial", "claude", "/tmp/repo")
        wt = tmp_path / "worktree"
        wt.mkdir()

        with (
            patch(
                "shoal.core.tmux.async_kill_session",
                side_effect=RuntimeError("async tmux dead"),
            ),
            patch(
                "shoal.core.git.async_worktree_remove",
                side_effect=RuntimeError("async wt stuck"),
            ),
        ):
            warnings = await _rollback_async(
                session_id=s.id,
                tmux_name="bad-async",
                wt_path=str(wt),
                git_root="/tmp/repo",
            )

        # DB row still deleted
        assert await get_session(s.id) is None
        # tmux and worktree failures produce warnings
        assert len(warnings) == 2

    async def test_rollback_async_db_failure(self, mock_dirs):
        """Async rollback logs warning when DB delete fails."""
        with patch(
            "shoal.services.lifecycle.delete_session",
            side_effect=RuntimeError("db error"),
        ):
            warnings = await _rollback_async(session_id="nonexistent-id")
            assert len(warnings) == 1
            assert "DB row" in warnings[0]


@pytest.mark.asyncio
class TestStartupCommandHelpers:
    """Tests for _run_default_startup_commands (sync) and preview variants."""

    async def test_run_default_startup_commands(self, mock_dirs):
        """Sync startup commands are interpolated and executed."""
        from shoal.services.lifecycle import _run_default_startup_commands

        with patch("shoal.core.tmux.run_command") as mock_run:
            _run_default_startup_commands(
                ["send-keys -t {tmux_session} 'echo {session_name}' Enter"],
                tool_command="claude",
                work_dir="/tmp/repo",
                session_name="test-session",
                tmux_session="_test-session",
            )

        mock_run.assert_called_once_with("send-keys -t _test-session 'echo test-session' Enter")

    async def test_run_default_startup_commands_skips_bad_variable(self, mock_dirs):
        """Sync startup commands skip commands with missing variables."""
        from shoal.services.lifecycle import _run_default_startup_commands

        with patch("shoal.core.tmux.run_command") as mock_run:
            _run_default_startup_commands(
                [
                    "send-keys -t {nonexistent_var} Enter",
                    "send-keys -t {tmux_session} 'ok' Enter",
                ],
                tool_command="claude",
                work_dir="/tmp/repo",
                session_name="test",
                tmux_session="_test",
            )

        # Only the valid command should be run
        assert mock_run.call_count == 1
        mock_run.assert_called_once_with("send-keys -t _test 'ok' Enter")

    async def test_preview_default_startup_commands(self, mock_dirs):
        """Preview returns interpolated command strings."""
        from shoal.services.lifecycle import _preview_default_startup_commands

        result = _preview_default_startup_commands(
            [
                "send-keys -t {tmux_session} 'cd {work_dir}' Enter",
                "send-keys -t {tmux_session} '{tool_command}' Enter",
            ],
            tool_command="claude",
            work_dir="/tmp/repo",
            session_name="test",
            tmux_session="_test",
        )

        assert len(result) == 2
        assert result[0] == "send-keys -t _test 'cd /tmp/repo' Enter"
        assert result[1] == "send-keys -t _test 'claude' Enter"

    async def test_preview_default_startup_commands_raises_on_bad_var(self, mock_dirs):
        """Preview raises ValueError on missing template variable."""
        from shoal.services.lifecycle import _preview_default_startup_commands

        with pytest.raises(ValueError, match="Missing startup command variable"):
            _preview_default_startup_commands(
                ["send-keys -t {nonexistent_var} Enter"],
                tool_command="claude",
                work_dir="/tmp/repo",
                session_name="test",
                tmux_session="_test",
            )


@pytest.mark.asyncio
class TestAsyncStartupCommands:
    """Tests for _run_default_startup_commands_async."""

    async def test_async_startup_commands_interpolation(self, mock_dirs):
        """Async startup commands are interpolated and executed."""
        from shoal.services.lifecycle import _run_default_startup_commands_async

        with patch("shoal.core.tmux.async_run_command") as mock_run:
            await _run_default_startup_commands_async(
                ["send-keys -t {tmux_session} '{tool_command}' Enter"],
                tool_command="claude",
                work_dir="/tmp/repo",
                session_name="test-async",
                tmux_session="_test-async",
            )

        mock_run.assert_called_once_with("send-keys -t _test-async 'claude' Enter")

    async def test_async_startup_commands_skip_bad_variable(self, mock_dirs):
        """Async startup commands skip commands with missing variables."""
        from shoal.services.lifecycle import _run_default_startup_commands_async

        with patch("shoal.core.tmux.async_run_command") as mock_run:
            await _run_default_startup_commands_async(
                [
                    "send-keys -t {bad_var} Enter",
                    "send-keys -t {tmux_session} 'ok' Enter",
                ],
                tool_command="claude",
                work_dir="/tmp/repo",
                session_name="test-async",
                tmux_session="_test-async",
            )

        assert mock_run.call_count == 1


@pytest.mark.asyncio
class TestTemplateStartup:
    """Tests for _run_template_startup (sync) with windows and panes."""

    async def test_template_startup_single_window_single_pane(self, mock_dirs):
        """Template with one window and one pane runs correctly."""
        from shoal.models.config import (
            SessionTemplateConfig,
            TemplatePaneConfig,
            TemplateWindowConfig,
        )
        from shoal.services.lifecycle import _run_template_startup

        template = SessionTemplateConfig(
            name="basic",
            windows=[
                TemplateWindowConfig(
                    name="editor",
                    panes=[TemplatePaneConfig(split="root", command="{tool_command}")],
                ),
            ],
        )

        with (
            patch("shoal.core.tmux.run_command") as mock_run_cmd,
            patch("shoal.core.tmux.send_keys") as mock_send,
        ):
            _run_template_startup(
                template,
                tool_command="claude",
                work_dir="/tmp/repo",
                root="/tmp/repo",
                branch_name="main",
                session_name="tmpl-test",
                tmux_session="_tmpl-test",
                worktree_name="",
            )

        # rename-window for window 0
        assert any("rename-window" in str(c) for c in mock_run_cmd.call_args_list)
        # send_keys for the pane command
        mock_send.assert_called_once()
        assert "claude" in mock_send.call_args[0][1]

    async def test_template_startup_multiple_windows(self, mock_dirs):
        """Template with multiple windows creates new-window commands."""
        from shoal.models.config import (
            SessionTemplateConfig,
            TemplatePaneConfig,
            TemplateWindowConfig,
        )
        from shoal.services.lifecycle import _run_template_startup

        template = SessionTemplateConfig(
            name="multi",
            windows=[
                TemplateWindowConfig(
                    name="main",
                    panes=[TemplatePaneConfig(split="root", command="echo main")],
                ),
                TemplateWindowConfig(
                    name="aux",
                    panes=[TemplatePaneConfig(split="root", command="echo aux")],
                ),
            ],
        )

        with (
            patch("shoal.core.tmux.run_command") as mock_run_cmd,
            patch("shoal.core.tmux.send_keys") as mock_send,
        ):
            _run_template_startup(
                template,
                tool_command="claude",
                work_dir="/tmp/repo",
                root="/tmp/repo",
                branch_name="main",
                session_name="multi-tmpl",
                tmux_session="_multi-tmpl",
                worktree_name="",
            )

        # Should have new-window for the second window
        run_cmds = [str(c) for c in mock_run_cmd.call_args_list]
        assert any("new-window" in cmd for cmd in run_cmds)
        assert mock_send.call_count == 2

    async def test_template_startup_with_split_panes(self, mock_dirs):
        """Template with split panes creates split-window commands."""
        from shoal.models.config import (
            SessionTemplateConfig,
            TemplatePaneConfig,
            TemplateWindowConfig,
        )
        from shoal.services.lifecycle import _run_template_startup

        template = SessionTemplateConfig(
            name="split",
            windows=[
                TemplateWindowConfig(
                    name="dev",
                    panes=[
                        TemplatePaneConfig(split="root", command="echo root"),
                        TemplatePaneConfig(split="right", size="50%", command="echo right"),
                        TemplatePaneConfig(split="down", command="echo down"),
                    ],
                ),
            ],
        )

        with (
            patch("shoal.core.tmux.run_command") as mock_run_cmd,
            patch("shoal.core.tmux.send_keys") as mock_send,
        ):
            _run_template_startup(
                template,
                tool_command="claude",
                work_dir="/tmp/repo",
                root="/tmp/repo",
                branch_name="main",
                session_name="split-tmpl",
                tmux_session="_split-tmpl",
                worktree_name="",
            )

        run_cmds = [str(c) for c in mock_run_cmd.call_args_list]
        assert any("split-window" in cmd and "-h" in cmd for cmd in run_cmds)
        assert any("split-window" in cmd and "-v" in cmd for cmd in run_cmds)
        assert mock_send.call_count == 3

    async def test_template_startup_with_pane_title(self, mock_dirs):
        """Template pane with title sets it via set_pane_title."""
        from shoal.models.config import (
            SessionTemplateConfig,
            TemplatePaneConfig,
            TemplateWindowConfig,
        )
        from shoal.services.lifecycle import _run_template_startup

        template = SessionTemplateConfig(
            name="titled",
            windows=[
                TemplateWindowConfig(
                    name="win",
                    panes=[
                        TemplatePaneConfig(
                            split="root",
                            command="echo hi",
                            title="shoal:{session_name}",
                        ),
                    ],
                ),
            ],
        )

        with (
            patch("shoal.core.tmux.run_command"),
            patch("shoal.core.tmux.send_keys"),
            patch("shoal.core.tmux.set_pane_title") as mock_title,
        ):
            _run_template_startup(
                template,
                tool_command="claude",
                work_dir="/tmp/repo",
                root="/tmp/repo",
                branch_name="main",
                session_name="title-test",
                tmux_session="_title-test",
                worktree_name="",
            )

        mock_title.assert_called_once()
        assert "shoal:title-test" in mock_title.call_args[0][1]

    async def test_template_startup_with_layout(self, mock_dirs):
        """Template window with layout applies select-layout."""
        from shoal.models.config import (
            SessionTemplateConfig,
            TemplatePaneConfig,
            TemplateWindowConfig,
        )
        from shoal.services.lifecycle import _run_template_startup

        template = SessionTemplateConfig(
            name="layout",
            windows=[
                TemplateWindowConfig(
                    name="win",
                    layout="main-horizontal",
                    panes=[TemplatePaneConfig(split="root", command="echo hi")],
                ),
            ],
        )

        with (
            patch("shoal.core.tmux.run_command") as mock_run_cmd,
            patch("shoal.core.tmux.send_keys"),
        ):
            _run_template_startup(
                template,
                tool_command="claude",
                work_dir="/tmp/repo",
                root="/tmp/repo",
                branch_name="main",
                session_name="layout-test",
                tmux_session="_layout-test",
                worktree_name="",
            )

        run_cmds = [str(c) for c in mock_run_cmd.call_args_list]
        assert any("select-layout" in cmd and "main-horizontal" in cmd for cmd in run_cmds)

    async def test_template_startup_with_focus(self, mock_dirs):
        """Template window with focus=True selects that window."""
        from shoal.models.config import (
            SessionTemplateConfig,
            TemplatePaneConfig,
            TemplateWindowConfig,
        )
        from shoal.services.lifecycle import _run_template_startup

        template = SessionTemplateConfig(
            name="focus",
            windows=[
                TemplateWindowConfig(
                    name="first",
                    panes=[TemplatePaneConfig(split="root", command="echo 1")],
                ),
                TemplateWindowConfig(
                    name="second",
                    focus=True,
                    panes=[TemplatePaneConfig(split="root", command="echo 2")],
                ),
            ],
        )

        with (
            patch("shoal.core.tmux.run_command") as mock_run_cmd,
            patch("shoal.core.tmux.send_keys"),
        ):
            _run_template_startup(
                template,
                tool_command="claude",
                work_dir="/tmp/repo",
                root="/tmp/repo",
                branch_name="main",
                session_name="focus-test",
                tmux_session="_focus-test",
                worktree_name="",
            )

        run_cmds = [str(c) for c in mock_run_cmd.call_args_list]
        assert any("select-window" in cmd for cmd in run_cmds)

    async def test_template_startup_with_custom_cwd(self, mock_dirs):
        """Template pane 0 with different cwd sends cd command."""
        from shoal.models.config import (
            SessionTemplateConfig,
            TemplatePaneConfig,
            TemplateWindowConfig,
        )
        from shoal.services.lifecycle import _run_template_startup

        template = SessionTemplateConfig(
            name="cwd-test",
            windows=[
                TemplateWindowConfig(
                    name="win",
                    cwd="/tmp/other",
                    panes=[TemplatePaneConfig(split="root", command="echo hi")],
                ),
            ],
        )

        with (
            patch("shoal.core.tmux.run_command"),
            patch("shoal.core.tmux.send_keys") as mock_send,
        ):
            _run_template_startup(
                template,
                tool_command="claude",
                work_dir="/tmp/repo",
                root="/tmp/repo",
                branch_name="main",
                session_name="cwd-test",
                tmux_session="_cwd-test",
                worktree_name="",
            )

        # First call should be cd to custom cwd, second should be the pane command
        calls = mock_send.call_args_list
        assert any("cd" in str(c) and "/tmp/other" in str(c) for c in calls)

    async def test_template_startup_empty_windows(self, mock_dirs):
        """Template with no windows is a no-op."""
        from unittest.mock import MagicMock

        from shoal.services.lifecycle import _run_template_startup

        template = MagicMock()
        template.windows = []

        with (
            patch("shoal.core.tmux.run_command") as mock_run_cmd,
            patch("shoal.core.tmux.send_keys") as mock_send,
        ):
            _run_template_startup(
                template,
                tool_command="claude",
                work_dir="/tmp/repo",
                root="/tmp/repo",
                branch_name="main",
                session_name="empty-test",
                tmux_session="_empty-test",
                worktree_name="",
            )

        mock_run_cmd.assert_not_called()
        mock_send.assert_not_called()


@pytest.mark.asyncio
class TestTemplateStartupAsync:
    """Tests for _run_template_startup_async."""

    async def test_async_template_single_window(self, mock_dirs):
        """Async template with one window and one pane runs correctly."""
        from shoal.models.config import (
            SessionTemplateConfig,
            TemplatePaneConfig,
            TemplateWindowConfig,
        )
        from shoal.services.lifecycle import _run_template_startup_async

        template = SessionTemplateConfig(
            name="async-basic",
            windows=[
                TemplateWindowConfig(
                    name="editor",
                    panes=[TemplatePaneConfig(split="root", command="{tool_command}")],
                ),
            ],
        )

        with (
            patch("shoal.core.tmux.async_run_command") as mock_run,
            patch("shoal.core.tmux.async_send_keys") as mock_send,
        ):
            await _run_template_startup_async(
                template,
                tool_command="claude",
                work_dir="/tmp/repo",
                root="/tmp/repo",
                branch_name="main",
                session_name="async-tmpl",
                tmux_session="_async-tmpl",
                worktree_name="",
            )

        assert any("rename-window" in str(c) for c in mock_run.call_args_list)
        mock_send.assert_called_once()

    async def test_async_template_multiple_windows_and_panes(self, mock_dirs):
        """Async template with multiple windows and split panes."""
        from shoal.models.config import (
            SessionTemplateConfig,
            TemplatePaneConfig,
            TemplateWindowConfig,
        )
        from shoal.services.lifecycle import _run_template_startup_async

        template = SessionTemplateConfig(
            name="async-multi",
            windows=[
                TemplateWindowConfig(
                    name="main",
                    focus=True,
                    panes=[
                        TemplatePaneConfig(split="root", command="echo root"),
                        TemplatePaneConfig(
                            split="right",
                            size="30%",
                            command="echo side",
                            title="side-pane",
                        ),
                    ],
                ),
                TemplateWindowConfig(
                    name="aux",
                    layout="even-horizontal",
                    panes=[TemplatePaneConfig(split="root", command="echo aux")],
                ),
            ],
        )

        with (
            patch("shoal.core.tmux.async_run_command") as mock_run,
            patch("shoal.core.tmux.async_send_keys") as mock_send,
            patch("shoal.core.tmux.async_set_pane_title") as mock_title,
        ):
            await _run_template_startup_async(
                template,
                tool_command="claude",
                work_dir="/tmp/repo",
                root="/tmp/repo",
                branch_name="main",
                session_name="async-multi",
                tmux_session="_async-multi",
                worktree_name="",
            )

        run_cmds = [str(c) for c in mock_run.call_args_list]
        assert any("new-window" in cmd for cmd in run_cmds)
        assert any("split-window" in cmd and "-h" in cmd for cmd in run_cmds)
        assert any("select-layout" in cmd for cmd in run_cmds)
        assert any("select-window" in cmd for cmd in run_cmds)
        assert mock_send.call_count == 3
        mock_title.assert_called_once()

    async def test_async_template_empty_windows(self, mock_dirs):
        """Async template with no windows is a no-op."""
        from unittest.mock import MagicMock

        from shoal.services.lifecycle import _run_template_startup_async

        template = MagicMock()
        template.windows = []

        with (
            patch("shoal.core.tmux.async_run_command") as mock_run,
            patch("shoal.core.tmux.async_send_keys") as mock_send,
        ):
            await _run_template_startup_async(
                template,
                tool_command="claude",
                work_dir="/tmp/repo",
                root="/tmp/repo",
                branch_name="main",
                session_name="empty-async",
                tmux_session="_empty-async",
                worktree_name="",
            )

        mock_run.assert_not_called()
        mock_send.assert_not_called()

    async def test_async_template_root_split_converted(self, mock_dirs):
        """Pane with split='root' in non-first position is treated as 'down'."""
        from shoal.models.config import (
            SessionTemplateConfig,
            TemplatePaneConfig,
            TemplateWindowConfig,
        )
        from shoal.services.lifecycle import _run_template_startup_async

        template = SessionTemplateConfig(
            name="root-split",
            windows=[
                TemplateWindowConfig(
                    name="win",
                    panes=[
                        TemplatePaneConfig(split="root", command="echo 1"),
                        # Manually bypass validation for test
                    ],
                ),
            ],
        )

        # Manually add a second pane with split="root" to test conversion
        # We need to bypass Pydantic validation, so just use MagicMock
        from unittest.mock import MagicMock

        extra_pane = MagicMock()
        extra_pane.split = "root"
        extra_pane.size = ""
        extra_pane.command = "echo 2"
        extra_pane.title = ""
        template.windows[0].panes.append(extra_pane)

        with (
            patch("shoal.core.tmux.async_run_command") as mock_run,
            patch("shoal.core.tmux.async_send_keys"),
        ):
            await _run_template_startup_async(
                template,
                tool_command="claude",
                work_dir="/tmp/repo",
                root="/tmp/repo",
                branch_name="main",
                session_name="root-test",
                tmux_session="_root-test",
                worktree_name="",
            )

        # The root split for pane_index > 0 should be converted to "down" (-v)
        run_cmds = [str(c) for c in mock_run.call_args_list]
        assert any("split-window" in cmd and "-v" in cmd for cmd in run_cmds)


@pytest.mark.asyncio
class TestPreviewTemplateStartup:
    """Tests for _preview_template_startup."""

    async def test_preview_single_window(self, mock_dirs):
        """Preview returns expected commands for single window template."""
        from shoal.models.config import (
            SessionTemplateConfig,
            TemplatePaneConfig,
            TemplateWindowConfig,
        )
        from shoal.services.lifecycle import _preview_template_startup

        template = SessionTemplateConfig(
            name="preview",
            windows=[
                TemplateWindowConfig(
                    name="editor",
                    panes=[TemplatePaneConfig(split="root", command="{tool_command}")],
                ),
            ],
        )

        result = _preview_template_startup(
            template,
            tool_command="claude",
            work_dir="/tmp/repo",
            root="/tmp/repo",
            branch_name="main",
            session_name="prev-test",
            tmux_session="_prev-test",
            worktree_name="",
        )

        assert any("rename-window" in cmd for cmd in result)
        assert any("send-keys" in cmd and "claude" in cmd for cmd in result)

    async def test_preview_empty_windows(self, mock_dirs):
        """Preview returns empty list for empty windows."""
        from unittest.mock import MagicMock

        from shoal.services.lifecycle import _preview_template_startup

        template = MagicMock()
        template.windows = []

        result = _preview_template_startup(
            template,
            tool_command="claude",
            work_dir="/tmp/repo",
            root="/tmp/repo",
            branch_name="main",
            session_name="prev-empty",
            tmux_session="_prev-empty",
            worktree_name="",
        )

        assert result == []

    async def test_preview_multiple_windows_with_splits(self, mock_dirs):
        """Preview returns new-window, split-window, and layout commands."""
        from shoal.models.config import (
            SessionTemplateConfig,
            TemplatePaneConfig,
            TemplateWindowConfig,
        )
        from shoal.services.lifecycle import _preview_template_startup

        template = SessionTemplateConfig(
            name="preview-multi",
            windows=[
                TemplateWindowConfig(
                    name="main",
                    panes=[
                        TemplatePaneConfig(split="root", command="echo 1"),
                        TemplatePaneConfig(split="right", size="40%", command="echo 2"),
                    ],
                ),
                TemplateWindowConfig(
                    name="aux",
                    focus=True,
                    layout="tiled",
                    panes=[
                        TemplatePaneConfig(split="root", command="echo 3"),
                    ],
                ),
            ],
        )

        result = _preview_template_startup(
            template,
            tool_command="claude",
            work_dir="/tmp/repo",
            root="/tmp/repo",
            branch_name="main",
            session_name="prev-multi",
            tmux_session="_prev-multi",
            worktree_name="",
        )

        assert any("rename-window" in cmd for cmd in result)
        assert any("new-window" in cmd for cmd in result)
        assert any("split-window" in cmd and "-h" in cmd for cmd in result)
        assert any("select-layout" in cmd and "tiled" in cmd for cmd in result)
        assert any("select-window" in cmd for cmd in result)

    async def test_preview_with_pane_title(self, mock_dirs):
        """Preview includes select-pane for titled panes."""
        from shoal.models.config import (
            SessionTemplateConfig,
            TemplatePaneConfig,
            TemplateWindowConfig,
        )
        from shoal.services.lifecycle import _preview_template_startup

        template = SessionTemplateConfig(
            name="preview-title",
            windows=[
                TemplateWindowConfig(
                    name="win",
                    panes=[
                        TemplatePaneConfig(
                            split="root",
                            command="echo hi",
                            title="my-title",
                        ),
                    ],
                ),
            ],
        )

        result = _preview_template_startup(
            template,
            tool_command="claude",
            work_dir="/tmp/repo",
            root="/tmp/repo",
            branch_name="main",
            session_name="prev-title",
            tmux_session="_prev-title",
            worktree_name="",
        )

        assert any("select-pane" in cmd and "my-title" in cmd for cmd in result)

    async def test_preview_with_custom_cwd(self, mock_dirs):
        """Preview includes cd for pane 0 with different cwd."""
        from shoal.models.config import (
            SessionTemplateConfig,
            TemplatePaneConfig,
            TemplateWindowConfig,
        )
        from shoal.services.lifecycle import _preview_template_startup

        template = SessionTemplateConfig(
            name="preview-cwd",
            windows=[
                TemplateWindowConfig(
                    name="win",
                    cwd="/tmp/other",
                    panes=[TemplatePaneConfig(split="root", command="echo hi")],
                ),
            ],
        )

        result = _preview_template_startup(
            template,
            tool_command="claude",
            work_dir="/tmp/repo",
            root="/tmp/repo",
            branch_name="main",
            session_name="prev-cwd",
            tmux_session="_prev-cwd",
            worktree_name="",
        )

        assert any("send-keys" in cmd and "/tmp/other" in cmd for cmd in result)


class TestSplitPercentage:
    """Tests for _split_percentage helper."""

    def test_valid_percentage(self):
        from shoal.services.lifecycle import _split_percentage

        assert _split_percentage("50%") == 50
        assert _split_percentage("1%") == 1
        assert _split_percentage("99%") == 99

    def test_valid_number_without_percent(self):
        from shoal.services.lifecycle import _split_percentage

        assert _split_percentage("50") == 50

    def test_empty_string(self):
        from shoal.services.lifecycle import _split_percentage

        assert _split_percentage("") is None

    def test_whitespace_only(self):
        from shoal.services.lifecycle import _split_percentage

        assert _split_percentage("  ") is None

    def test_zero_out_of_range(self):
        from shoal.services.lifecycle import _split_percentage

        assert _split_percentage("0") is None

    def test_hundred_out_of_range(self):
        from shoal.services.lifecycle import _split_percentage

        assert _split_percentage("100") is None

    def test_non_numeric(self):
        from shoal.services.lifecycle import _split_percentage

        assert _split_percentage("abc") is None

    def test_whitespace_stripped(self):
        from shoal.services.lifecycle import _split_percentage

        assert _split_percentage("  50%  ") == 50


class TestFormatValue:
    """Tests for _format_value helper."""

    def test_successful_format(self):
        from shoal.services.lifecycle import _format_value

        result = _format_value("{name}-{tool}", {"name": "test", "tool": "claude"}, "test")
        assert result == "test-claude"

    def test_missing_variable_raises(self):
        from shoal.services.lifecycle import _format_value

        with pytest.raises(ValueError, match="Missing template variable"):
            _format_value("{missing_var}", {"name": "test"}, "test field")

    def test_no_variables(self):
        from shoal.services.lifecycle import _format_value

        result = _format_value("static-text", {}, "test")
        assert result == "static-text"


class TestExceptionHierarchy:
    """Tests for the lifecycle exception hierarchy."""

    def test_lifecycle_error_attributes(self) -> None:
        err = LifecycleError("msg", session_id="s1", operation="create")
        assert err.session_id == "s1"
        assert err.operation == "create"
        assert str(err) == "msg"

    def test_tmux_setup_error_is_lifecycle_error(self) -> None:
        from shoal.services.lifecycle import TmuxSetupError

        err = TmuxSetupError("tmux failed")
        assert isinstance(err, LifecycleError)

    def test_startup_command_error_is_lifecycle_error(self) -> None:
        from shoal.services.lifecycle import StartupCommandError

        err = StartupCommandError("cmd failed")
        assert isinstance(err, LifecycleError)

    def test_session_exists_error_is_lifecycle_error(self) -> None:
        from shoal.services.lifecycle import SessionExistsError

        err = SessionExistsError("exists")
        assert isinstance(err, LifecycleError)

    def test_dirty_worktree_error_attributes(self) -> None:
        err = DirtyWorktreeError(
            "dirty",
            session_id="s1",
            dirty_files=" M file.txt\n?? new.py",
        )
        assert isinstance(err, LifecycleError)
        assert err.dirty_files == " M file.txt\n?? new.py"
        assert err.session_id == "s1"
        assert err.operation == "kill"


@pytest.mark.asyncio
class TestLifecycleErrorAttributes:
    """Verify lifecycle error attributes set by lifecycle functions."""

    async def test_tmux_setup_error_has_session_id(self, mock_dirs):
        from shoal.services.lifecycle import TmuxSetupError

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session", side_effect=RuntimeError("no tmux")),
        ):
            try:
                await create_session_lifecycle(
                    session_name="err-attr",
                    tool="claude",
                    git_root="/tmp/repo",
                    wt_path="",
                    work_dir="/tmp/repo",
                    branch_name="main",
                    tool_command="claude",
                    startup_commands=[],
                )
            except TmuxSetupError as exc:
                assert exc.session_id != ""
                assert exc.operation == "create"

    async def test_startup_error_has_session_id(self, mock_dirs):
        from shoal.services.lifecycle import StartupCommandError

        with (
            patch("shoal.core.tmux.has_session", return_value=False),
            patch("shoal.core.tmux.new_session"),
            patch("shoal.core.tmux.set_environment"),
            patch("shoal.core.tmux.kill_session"),
            patch("shoal.core.tmux.run_command", side_effect=ValueError("bad")),
        ):
            try:
                await create_session_lifecycle(
                    session_name="err-startup",
                    tool="claude",
                    git_root="/tmp/repo",
                    wt_path="",
                    work_dir="/tmp/repo",
                    branch_name="main",
                    tool_command="claude",
                    startup_commands=["send-keys -t {tmux_session} 'echo' Enter"],
                )
            except StartupCommandError as exc:
                assert exc.session_id != ""
                assert exc.operation == "create"
