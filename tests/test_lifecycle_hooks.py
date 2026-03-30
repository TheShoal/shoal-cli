"""Tests for the lifecycle hook system (on/emit/clear_hooks + built-in hooks)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shoal.models.state import LifecycleEvent, SessionState, SessionStatus
from shoal.services.lifecycle import (
    _hook_fish_event,
    _hook_journal_on_create,
    clear_hooks,
    create_session_lifecycle,
    emit,
    fork_session_lifecycle,
    kill_session_lifecycle,
    on,
    register_builtin_hooks,
)

# ---------------------------------------------------------------------------
# LifecycleEvent enum
# ---------------------------------------------------------------------------


class TestLifecycleEvent:
    def test_values(self) -> None:
        assert LifecycleEvent.session_created == "session_created"
        assert LifecycleEvent.session_killed == "session_killed"
        assert LifecycleEvent.session_forked == "session_forked"
        assert LifecycleEvent.status_changed == "status_changed"

    def test_member_count(self) -> None:
        assert len(LifecycleEvent) == 5

    def test_is_strenum(self) -> None:
        assert isinstance(LifecycleEvent.session_created, str)


# ---------------------------------------------------------------------------
# Hook registry: on / emit / clear_hooks
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_hooks() -> None:  # type: ignore[misc]
    """Ensure hooks are cleared before and after each test."""
    clear_hooks()
    yield  # type: ignore[misc]
    clear_hooks()


@pytest.mark.asyncio
class TestHookRegistry:
    async def test_on_and_emit(self) -> None:
        cb = AsyncMock()
        on(LifecycleEvent.session_created, cb)
        await emit(LifecycleEvent.session_created, session="fake")
        cb.assert_awaited_once_with(LifecycleEvent.session_created, session="fake")
        assert cb.await_count == 1

    async def test_emit_no_listeners(self) -> None:
        from shoal.services.lifecycle import _hooks

        assert LifecycleEvent.session_killed not in _hooks
        await emit(LifecycleEvent.session_killed, session="x")
        assert LifecycleEvent.session_killed not in _hooks

    async def test_multiple_callbacks_fire_in_order(self) -> None:
        order: list[int] = []

        async def first(event: LifecycleEvent, **kwargs: object) -> None:
            order.append(1)

        async def second(event: LifecycleEvent, **kwargs: object) -> None:
            order.append(2)

        on(LifecycleEvent.session_created, first)
        on(LifecycleEvent.session_created, second)
        await emit(LifecycleEvent.session_created)
        assert order == [1, 2]

    async def test_clear_hooks_removes_all(self) -> None:
        cb = AsyncMock()
        on(LifecycleEvent.session_created, cb)
        clear_hooks()
        await emit(LifecycleEvent.session_created)
        cb.assert_not_awaited()
        assert cb.await_count == 0

    async def test_error_in_hook_does_not_propagate(self) -> None:
        async def bad_hook(event: LifecycleEvent, **kwargs: object) -> None:
            raise RuntimeError("boom")

        good_cb = AsyncMock()
        on(LifecycleEvent.session_created, bad_hook)
        on(LifecycleEvent.session_created, good_cb)

        # Should not raise — error is logged, second hook still fires
        await emit(LifecycleEvent.session_created)
        good_cb.assert_awaited_once()
        assert good_cb.await_count == 1

    async def test_events_are_independent(self) -> None:
        cb_created = AsyncMock()
        cb_killed = AsyncMock()
        on(LifecycleEvent.session_created, cb_created)
        on(LifecycleEvent.session_killed, cb_killed)

        await emit(LifecycleEvent.session_created, session="a")
        cb_created.assert_awaited_once()
        cb_killed.assert_not_awaited()
        assert cb_created.await_count == 1
        assert cb_killed.await_count == 0


# ---------------------------------------------------------------------------
# Lifecycle functions emit correct events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLifecycleEmitsEvents:
    async def test_create_emits_session_created(self, mock_dirs: object) -> None:
        cb = AsyncMock()
        on(LifecycleEvent.session_created, cb)

        with (
            patch("shoal.services.lifecycle.tmux") as mock_tmux,
            patch("shoal.core.context.set_session_id"),
        ):
            mock_tmux.async_new_session = AsyncMock()
            mock_tmux.async_set_environment = AsyncMock()
            mock_tmux.async_set_pane_title = AsyncMock()
            mock_tmux.async_preferred_pane = AsyncMock(return_value="target")
            mock_tmux.async_pane_pid = AsyncMock(return_value=None)
            mock_tmux.async_pane_coordinates = AsyncMock(return_value=None)
            mock_tmux.async_run_command = AsyncMock()
            mock_tmux.async_send_keys = AsyncMock()

            await create_session_lifecycle(
                session_name="hook-test",
                tool="claude",
                git_root="/tmp/repo",
                wt_path="",
                work_dir="/tmp/repo",
                branch_name="main",
                tool_command="claude",
                startup_commands=["echo hello"],
            )

        cb.assert_awaited_once()
        call_kwargs = cb.call_args[1]
        assert isinstance(call_kwargs["session"], SessionState)
        assert call_kwargs["session"].name == "hook-test"

    async def test_fork_emits_session_forked(self, mock_dirs: object) -> None:
        cb = AsyncMock()
        on(LifecycleEvent.session_forked, cb)

        with (
            patch("shoal.services.lifecycle.tmux") as mock_tmux,
            patch("shoal.core.context.set_session_id"),
        ):
            mock_tmux.async_new_session = AsyncMock()
            mock_tmux.async_set_environment = AsyncMock()
            mock_tmux.async_set_pane_title = AsyncMock()
            mock_tmux.async_preferred_pane = AsyncMock(return_value="target")
            mock_tmux.async_pane_pid = AsyncMock(return_value=None)
            mock_tmux.async_pane_coordinates = AsyncMock(return_value=None)
            mock_tmux.async_run_command = AsyncMock()
            mock_tmux.async_send_keys = AsyncMock()

            await fork_session_lifecycle(
                session_name="fork-hook-test",
                source_tool="claude",
                source_path="/tmp/repo",
                source_branch="main",
                wt_path="",
                work_dir="/tmp/repo",
                new_branch="feature",
                tool_command="claude",
                startup_commands=["echo hello"],
            )

        cb.assert_awaited_once()
        call_kwargs = cb.call_args[1]
        assert call_kwargs["session"].name == "fork-hook-test"

    async def test_kill_emits_session_killed(self, mock_dirs: object) -> None:
        from shoal.core.state import create_session

        session = await create_session("kill-hook-test", "claude", "/tmp/repo")

        cb = AsyncMock()
        on(LifecycleEvent.session_killed, cb)

        with (
            patch("shoal.services.lifecycle.tmux") as mock_tmux,
            patch("shoal.core.context.set_session_id"),
        ):
            mock_tmux.async_has_session = AsyncMock(return_value=False)

            await kill_session_lifecycle(
                session_id=session.id,
                tmux_session=session.runtime.session_name,
            )

        cb.assert_awaited_once()
        call_kwargs = cb.call_args[1]
        assert call_kwargs["session"].id == session.id


# ---------------------------------------------------------------------------
# Built-in hooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBuiltinHooks:
    async def test_journal_hook_writes_entry(self, mock_dirs: object) -> None:
        session = SessionState(
            id="test-id",
            name="test-session",
            tool="claude",
            path="/tmp/repo",
            tmux_session="_test-session",
        )

        with patch("shoal.core.journal.append_entry") as mock_append:
            await _hook_journal_on_create(LifecycleEvent.session_created, session=session)

        mock_append.assert_called_once()
        args = mock_append.call_args
        assert args[0][0] == "test-id"
        assert "test-session" in args[0][1]
        assert args[1]["source"] == "lifecycle"

    async def test_journal_hook_skips_without_session(self) -> None:
        with patch("shoal.core.journal.append_entry") as mock_append:
            await _hook_journal_on_create(LifecycleEvent.session_created)

        mock_append.assert_not_called()
        assert mock_append.call_count == 0

    async def test_fish_event_hook_calls_fish(self, mock_dirs: object) -> None:
        session = SessionState(
            id="test-id",
            name="test-session",
            tool="claude",
            path="/tmp/repo",
            tmux_session="_test-session",
        )

        with patch("shoal.services.lifecycle.subprocess.run") as mock_run:
            await _hook_fish_event(LifecycleEvent.session_created, session=session)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "fish"
        assert "shoal_session_created" in args[2]
        assert "test-session" in args[2]

    async def test_fish_event_status_changed_includes_statuses(self) -> None:
        session = SessionState(
            id="test-id",
            name="test-session",
            tool="claude",
            path="/tmp/repo",
            tmux_session="_test-session",
        )

        with patch("shoal.services.lifecycle.subprocess.run") as mock_run:
            await _hook_fish_event(
                LifecycleEvent.status_changed,
                session=session,
                old_status=SessionStatus.running,
                new_status=SessionStatus.waiting,
            )

        fish_cmd = mock_run.call_args[0][0][2]
        assert "running" in fish_cmd
        assert "waiting" in fish_cmd

    async def test_fish_event_skips_without_session(self) -> None:
        with patch("shoal.services.lifecycle.subprocess.run") as mock_run:
            await _hook_fish_event(LifecycleEvent.session_created)

        mock_run.assert_not_called()
        assert mock_run.call_count == 0

    async def test_fish_not_found_is_swallowed(self) -> None:
        session = SessionState(
            id="test-id",
            name="test-session",
            tool="claude",
            path="/tmp/repo",
            tmux_session="_test-session",
        )

        with (
            patch(
                "shoal.services.lifecycle.subprocess.run",
                side_effect=FileNotFoundError("fish"),
            ),
            patch("shoal.services.lifecycle.logger.debug") as mock_debug,
        ):
            await _hook_fish_event(LifecycleEvent.session_created, session=session)

        mock_debug.assert_called_once_with("fish not found, skipping event emission")
        assert mock_debug.call_count == 1

    async def test_register_builtin_hooks(self) -> None:
        register_builtin_hooks()
        # Verify hooks are registered for all events
        from shoal.services.lifecycle import _hooks

        assert len(_hooks[LifecycleEvent.session_created]) >= 2  # journal + fish
        assert len(_hooks[LifecycleEvent.session_forked]) >= 2  # journal + fish
        assert len(_hooks[LifecycleEvent.session_killed]) >= 1  # fish
        assert len(_hooks[LifecycleEvent.status_changed]) >= 3  # record + journal + fish


# ---------------------------------------------------------------------------
# Watcher emits status_changed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestWatcherEmitsStatusChanged:
    async def test_status_change_emits_event(self, mock_dirs: object) -> None:
        from shoal.core.state import create_session
        from shoal.services.runtime_models import RuntimeObservation

        session = await create_session("watcher-test", "claude", "/tmp/repo")

        cb = AsyncMock()
        on(LifecycleEvent.status_changed, cb)

        mock_provider = MagicMock()
        mock_provider.async_observe = AsyncMock(
            return_value=RuntimeObservation(
                alive=True,
                output="some output",
                pid=123,
                runtime=session.runtime,
            )
        )

        with (
            patch("shoal.services.watcher.provider_for_session", return_value=mock_provider),
            patch("shoal.services.watcher.load_tool_config"),
            patch("shoal.services.watcher.detect_status", return_value=SessionStatus.waiting),
            patch("shoal.services.watcher.notify"),
        ):
            from shoal.services.watcher import Watcher

            watcher = Watcher()
            await watcher._poll_cycle()

        cb.assert_awaited_once()
        call_kwargs = cb.call_args[1]
        assert call_kwargs["old_status"] == SessionStatus.idle
        assert call_kwargs["new_status"] == SessionStatus.waiting


# ---------------------------------------------------------------------------
# Status transition hooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestStatusTransitionHooks:
    async def test_record_hook_saves_to_db(self, mock_dirs: object) -> None:
        from shoal.core.db import ShoalDB
        from shoal.services.lifecycle import _hook_record_status_transition

        session = SessionState(
            id="trans-test",
            name="trans-session",
            tool="claude",
            path="/tmp/repo",
            tmux_session="_trans-session",
        )

        await _hook_record_status_transition(
            LifecycleEvent.status_changed,
            session=session,
            old_status=SessionStatus.idle,
            new_status=SessionStatus.running,
        )

        db = await ShoalDB.get_instance()
        transitions = await db.get_status_transitions("trans-test")
        assert len(transitions) == 1
        assert transitions[0]["from_status"] == "idle"
        assert transitions[0]["to_status"] == "running"

    async def test_record_hook_skips_without_session(self) -> None:
        from shoal.services.lifecycle import _hook_record_status_transition

        with patch("shoal.core.db.get_db", new_callable=AsyncMock) as mock_get_db:
            await _hook_record_status_transition(LifecycleEvent.status_changed)

        mock_get_db.assert_not_awaited()
        assert mock_get_db.await_count == 0

    async def test_record_hook_skips_without_statuses(self) -> None:
        from shoal.services.lifecycle import _hook_record_status_transition

        session = SessionState(
            id="x",
            name="x",
            tool="claude",
            path="/tmp",
            tmux_session="_x",
        )
        with patch("shoal.core.db.get_db", new_callable=AsyncMock) as mock_get_db:
            await _hook_record_status_transition(LifecycleEvent.status_changed, session=session)

        mock_get_db.assert_not_awaited()
        assert mock_get_db.await_count == 0

    async def test_journal_hook_writes_status_entry(self, mock_dirs: object) -> None:
        from shoal.services.lifecycle import _hook_journal_on_status_change

        session = SessionState(
            id="journal-trans",
            name="journal-session",
            tool="claude",
            path="/tmp/repo",
            tmux_session="_journal-session",
        )

        with patch("shoal.core.journal.append_entry") as mock_append:
            await _hook_journal_on_status_change(
                LifecycleEvent.status_changed,
                session=session,
                old_status=SessionStatus.running,
                new_status=SessionStatus.waiting,
            )

        mock_append.assert_called_once()
        args = mock_append.call_args
        assert args[0][0] == "journal-trans"
        assert "running" in args[0][1]
        assert "waiting" in args[0][1]
        assert args[1]["source"] == "lifecycle"

    async def test_journal_hook_skips_without_session(self) -> None:
        from shoal.services.lifecycle import _hook_journal_on_status_change

        with patch("shoal.core.journal.append_entry") as mock_append:
            await _hook_journal_on_status_change(LifecycleEvent.status_changed)

        mock_append.assert_not_called()
        assert mock_append.call_count == 0


# ---------------------------------------------------------------------------
# Auto-commit on kill
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAutoCommitOnKill:
    async def test_auto_commit_commits_dirty_worktree(
        self, mock_dirs: object, tmp_path: object
    ) -> None:
        """Commits dirty worktree when auto_commit=True."""
        from shoal.core.state import create_session

        worktree = str(tmp_path)  # type: ignore[arg-type]
        session = await create_session("ac-dirty", "claude", "/tmp/repo", worktree=worktree)

        with (
            patch("shoal.services.lifecycle.tmux") as mock_tmux,
            patch("shoal.core.context.set_session_id"),
            patch("shoal.services.lifecycle.Path") as mock_path,
            patch("shoal.services.lifecycle.git") as mock_git,
            patch("shoal.services.lifecycle.load_config") as mock_cfg,
        ):
            mock_tmux.async_has_session = AsyncMock(return_value=False)
            # Worktree dir exists
            mock_path.return_value.is_dir.return_value = True
            # Worktree is dirty
            mock_git.async_worktree_is_dirty = AsyncMock(return_value=True)
            mock_git.async_stage_all = AsyncMock()
            mock_git.async_commit = AsyncMock()
            mock_git.async_worktree_remove = AsyncMock(return_value=True)
            mock_git.async_branch_delete = AsyncMock(return_value=True)
            # auto_commit enabled
            mock_cfg.return_value.general.auto_commit = True

            result = await kill_session_lifecycle(
                session_id=session.id,
                tmux_session=session.runtime.session_name,
            )

        mock_git.async_stage_all.assert_awaited_once_with(worktree)
        mock_git.async_commit.assert_awaited_once()
        commit_msg = mock_git.async_commit.call_args[0][1]
        assert "ac-dirty" in commit_msg
        assert result["auto_committed"] is True

    async def test_auto_commit_skips_when_disabled(
        self, mock_dirs: object, tmp_path: object
    ) -> None:
        """No commit when auto_commit=False."""
        from shoal.core.state import create_session

        session = await create_session("ac-off", "claude", "/tmp/repo", worktree=str(tmp_path))

        with (
            patch("shoal.services.lifecycle.tmux") as mock_tmux,
            patch("shoal.core.context.set_session_id"),
            patch("shoal.services.lifecycle.Path") as mock_path,
            patch("shoal.services.lifecycle.git") as mock_git,
            patch("shoal.services.lifecycle.load_config") as mock_cfg,
        ):
            mock_tmux.async_has_session = AsyncMock(return_value=False)
            mock_path.return_value.is_dir.return_value = True
            mock_git.async_worktree_is_dirty = AsyncMock(return_value=True)
            mock_git.async_stage_all = AsyncMock()
            mock_git.async_commit = AsyncMock()
            mock_cfg.return_value.general.auto_commit = False

            result = await kill_session_lifecycle(
                session_id=session.id,
                tmux_session=session.runtime.session_name,
            )

        mock_git.async_stage_all.assert_not_awaited()
        mock_git.async_commit.assert_not_awaited()
        assert result["auto_committed"] is False

    async def test_auto_commit_skips_clean_worktree(
        self, mock_dirs: object, tmp_path: object
    ) -> None:
        """No commit when worktree is already clean."""
        from shoal.core.state import create_session

        session = await create_session("ac-clean", "claude", "/tmp/repo", worktree=str(tmp_path))

        with (
            patch("shoal.services.lifecycle.tmux") as mock_tmux,
            patch("shoal.core.context.set_session_id"),
            patch("shoal.services.lifecycle.Path") as mock_path,
            patch("shoal.services.lifecycle.git") as mock_git,
            patch("shoal.services.lifecycle.load_config") as mock_cfg,
        ):
            mock_tmux.async_has_session = AsyncMock(return_value=False)
            mock_path.return_value.is_dir.return_value = True
            mock_git.async_worktree_is_dirty = AsyncMock(return_value=False)
            mock_git.async_stage_all = AsyncMock()
            mock_git.async_commit = AsyncMock()
            mock_cfg.return_value.general.auto_commit = True

            result = await kill_session_lifecycle(
                session_id=session.id,
                tmux_session=session.runtime.session_name,
            )

        mock_git.async_stage_all.assert_not_awaited()
        mock_git.async_commit.assert_not_awaited()
        assert result["auto_committed"] is False

    async def test_auto_commit_skips_no_worktree(self, mock_dirs: object) -> None:
        """No commit when the session has no worktree path."""
        from shoal.core.state import create_session

        # Session with no worktree
        session = await create_session("ac-noworktree", "claude", "/tmp/repo")

        with (
            patch("shoal.services.lifecycle.tmux") as mock_tmux,
            patch("shoal.core.context.set_session_id"),
            patch("shoal.services.lifecycle.git") as mock_git,
            patch("shoal.services.lifecycle.load_config") as mock_cfg,
        ):
            mock_tmux.async_has_session = AsyncMock(return_value=False)
            mock_git.async_stage_all = AsyncMock()
            mock_git.async_commit = AsyncMock()
            mock_cfg.return_value.general.auto_commit = True

            result = await kill_session_lifecycle(
                session_id=session.id,
                tmux_session=session.runtime.session_name,
            )

        mock_git.async_stage_all.assert_not_awaited()
        mock_git.async_commit.assert_not_awaited()
        assert result["auto_committed"] is False

    async def test_auto_commit_failure_does_not_abort_kill(
        self, mock_dirs: object, tmp_path: object
    ) -> None:
        """A failing commit is logged and swallowed; kill proceeds."""
        import subprocess

        from shoal.core.state import create_session

        session = await create_session("ac-fail", "claude", "/tmp/repo", worktree=str(tmp_path))

        with (
            patch("shoal.services.lifecycle.tmux") as mock_tmux,
            patch("shoal.core.context.set_session_id"),
            patch("shoal.services.lifecycle.Path") as mock_path,
            patch("shoal.services.lifecycle.git") as mock_git,
            patch("shoal.services.lifecycle.load_config") as mock_cfg,
        ):
            mock_tmux.async_has_session = AsyncMock(return_value=False)
            mock_path.return_value.is_dir.return_value = True
            mock_git.async_worktree_is_dirty = AsyncMock(return_value=True)
            mock_git.async_stage_all = AsyncMock(
                side_effect=subprocess.CalledProcessError(1, "git add")
            )
            mock_git.async_commit = AsyncMock()
            mock_cfg.return_value.general.auto_commit = True

            # Must not raise
            result = await kill_session_lifecycle(
                session_id=session.id,
                tmux_session=session.runtime.session_name,
            )

        assert result["db_deleted"] is True  # kill completed
        assert result["auto_committed"] is False


# ---------------------------------------------------------------------------
# register_project_hooks + load_project_hooks
# ---------------------------------------------------------------------------


class TestRegisterProjectHooks:
    """Unit tests for .shoal/hooks.toml loading and callback wiring."""

    def setup_method(self) -> None:
        from shoal.services.lifecycle import clear_hooks

        clear_hooks()

    def _write_hooks_toml(self, tmp_path: Path, content: str) -> None:
        shoal_dir = tmp_path / ".shoal"
        shoal_dir.mkdir()
        (shoal_dir / "hooks.toml").write_text(content)

    def test_load_empty_when_no_file(self, tmp_path: Path) -> None:
        from shoal.core.config import load_project_hooks

        with patch("shoal.core.git.git_root") as mock_git_root:
            mock_git_root.return_value = str(tmp_path)
            entries = load_project_hooks()
        assert entries == []

    def test_load_valid_entry(self, tmp_path: Path) -> None:
        from shoal.core.config import load_project_hooks

        self._write_hooks_toml(
            tmp_path,
            '[[hooks]]\nevent = "status_changed"\nwhen_status = "waiting"\ncommand = "echo $SHOAL_SESSION_NAME"',
        )
        with patch("shoal.core.git.git_root") as mock_git_root:
            mock_git_root.return_value = str(tmp_path)
            entries = load_project_hooks()
        assert len(entries) == 1
        assert entries[0].event == "status_changed"
        assert entries[0].when_status == "waiting"
        assert entries[0].command == "echo $SHOAL_SESSION_NAME"

    def test_invalid_event_skipped(self, tmp_path: Path) -> None:
        from shoal.core.config import load_project_hooks

        self._write_hooks_toml(
            tmp_path,
            '[[hooks]]\nevent = "not_a_real_event"\ncommand = "echo hi"',
        )
        with patch("shoal.core.git.git_root") as mock_git_root:
            mock_git_root.return_value = str(tmp_path)
            entries = load_project_hooks()
        assert entries == []

    @pytest.mark.asyncio
    async def test_hook_fires_on_matching_status(self, tmp_path: Path) -> None:
        """when_status filter: hook fires when new_status matches, skips otherwise."""
        from shoal.models.config import ProjectHookEntry
        from shoal.services.lifecycle import _register_one_project_hook, emit

        entry = ProjectHookEntry(event="status_changed", when_status="waiting", command="true")
        # Patch subprocess.run so we can observe calls without executing
        with patch("subprocess.run") as mock_run:
            _register_one_project_hook(entry)
            session = MagicMock(spec=SessionState)
            session.id = "sess-1"
            session.name = "my-session"
            # Fire with matching status — should call subprocess.run
            await emit(
                LifecycleEvent.status_changed,
                session=session,
                old_status=SessionStatus.running,
                new_status=SessionStatus.waiting,
            )
            assert mock_run.called
            # Fire with non-matching status — should NOT call subprocess.run again
            mock_run.reset_mock()
            await emit(
                LifecycleEvent.status_changed,
                session=session,
                old_status=SessionStatus.waiting,
                new_status=SessionStatus.running,
            )
            assert not mock_run.called

    @pytest.mark.asyncio
    async def test_hook_env_vars_injected(self, tmp_path: Path) -> None:
        """SHOAL_SESSION_ID, SHOAL_SESSION_NAME, SHOAL_NEW_STATUS are injected."""

        from shoal.models.config import ProjectHookEntry
        from shoal.services.lifecycle import _register_one_project_hook, emit

        captured_env: dict[str, str] = {}

        def _capture_env(*args: object, **kwargs: object) -> None:
            captured_env.update(kwargs.get("env", {}))

        entry = ProjectHookEntry(event="status_changed", command="true")
        with patch("subprocess.run", side_effect=_capture_env):
            _register_one_project_hook(entry)
            session = MagicMock(spec=SessionState)
            session.id = "abc-123"
            session.name = "be-worker"
            await emit(
                LifecycleEvent.status_changed,
                session=session,
                old_status=SessionStatus.running,
                new_status=SessionStatus.waiting,
            )

        assert captured_env["SHOAL_SESSION_ID"] == "abc-123"
        assert captured_env["SHOAL_SESSION_NAME"] == "be-worker"
        assert captured_env["SHOAL_NEW_STATUS"] == "waiting"
        assert captured_env["SHOAL_OLD_STATUS"] == "running"
        assert captured_env["SHOAL_EVENT"] == "status_changed"

    @pytest.mark.asyncio
    async def test_hook_exception_does_not_propagate(self, tmp_path: Path) -> None:
        """A crashing hook must not surface to the caller of emit()."""
        from shoal.models.config import ProjectHookEntry
        from shoal.services.lifecycle import _register_one_project_hook, emit

        entry = ProjectHookEntry(event="session_completed", command="true")
        with patch("subprocess.run", side_effect=RuntimeError("boom")):
            _register_one_project_hook(entry)
            session = MagicMock(spec=SessionState)
            session.id = "x"
            session.name = "x"
            # Must not raise
            await emit(LifecycleEvent.session_completed, session=session)
