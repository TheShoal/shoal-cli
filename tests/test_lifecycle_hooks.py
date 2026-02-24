"""Tests for the lifecycle hook system (on/emit/clear_hooks + built-in hooks)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
        assert len(LifecycleEvent) == 4

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

    async def test_emit_no_listeners(self) -> None:
        # Should not raise
        await emit(LifecycleEvent.session_killed, session="x")

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

    async def test_error_in_hook_does_not_propagate(self) -> None:
        async def bad_hook(event: LifecycleEvent, **kwargs: object) -> None:
            raise RuntimeError("boom")

        good_cb = AsyncMock()
        on(LifecycleEvent.session_created, bad_hook)
        on(LifecycleEvent.session_created, good_cb)

        # Should not raise — error is logged, second hook still fires
        await emit(LifecycleEvent.session_created)
        good_cb.assert_awaited_once()

    async def test_events_are_independent(self) -> None:
        cb_created = AsyncMock()
        cb_killed = AsyncMock()
        on(LifecycleEvent.session_created, cb_created)
        on(LifecycleEvent.session_killed, cb_killed)

        await emit(LifecycleEvent.session_created, session="a")
        cb_created.assert_awaited_once()
        cb_killed.assert_not_awaited()


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
                tmux_session=session.tmux_session,
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
        # Should not raise when session kwarg is missing
        await _hook_journal_on_create(LifecycleEvent.session_created)

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
        # Should not raise
        await _hook_fish_event(LifecycleEvent.session_created)

    async def test_fish_not_found_is_swallowed(self) -> None:
        session = SessionState(
            id="test-id",
            name="test-session",
            tool="claude",
            path="/tmp/repo",
            tmux_session="_test-session",
        )

        with patch(
            "shoal.services.lifecycle.subprocess.run",
            side_effect=FileNotFoundError("fish"),
        ):
            # Should not raise
            await _hook_fish_event(LifecycleEvent.session_created, session=session)

    def test_register_builtin_hooks(self) -> None:
        register_builtin_hooks()
        # Verify hooks are registered for all events
        from shoal.services.lifecycle import _hooks

        assert len(_hooks[LifecycleEvent.session_created]) >= 2  # journal + fish
        assert len(_hooks[LifecycleEvent.session_forked]) >= 2  # journal + fish
        assert len(_hooks[LifecycleEvent.session_killed]) >= 1  # fish
        assert len(_hooks[LifecycleEvent.status_changed]) >= 1  # fish


# ---------------------------------------------------------------------------
# Watcher emits status_changed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestWatcherEmitsStatusChanged:
    async def test_status_change_emits_event(self, mock_dirs: object) -> None:
        from shoal.core.state import create_session

        session = await create_session("watcher-test", "claude", "/tmp/repo")

        cb = AsyncMock()
        on(LifecycleEvent.status_changed, cb)

        with (
            patch("shoal.services.watcher.tmux") as mock_tmux,
            patch("shoal.services.watcher.load_tool_config"),
            patch("shoal.services.watcher.detect_status", return_value=SessionStatus.waiting),
            patch("shoal.services.watcher.notify"),
        ):
            mock_tmux.async_has_session = AsyncMock(return_value=True)
            mock_tmux.async_list_panes = AsyncMock(
                return_value=[{"title": f"shoal:{session.id}", "id": "%1"}]
            )
            mock_tmux.async_pane_pid = AsyncMock(return_value=123)
            mock_tmux.async_capture_pane = AsyncMock(return_value="some output")

            from shoal.services.watcher import Watcher

            watcher = Watcher()
            await watcher._poll_cycle()

        cb.assert_awaited_once()
        call_kwargs = cb.call_args[1]
        assert call_kwargs["old_status"] == SessionStatus.idle
        assert call_kwargs["new_status"] == SessionStatus.waiting
