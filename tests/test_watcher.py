"""Tests for background watcher service."""

import asyncio
from unittest.mock import patch

import pytest

from shoal.core.state import create_session, update_session, get_session
from shoal.models.state import SessionStatus
from shoal.services.watcher import Watcher


@pytest.mark.asyncio
class TestWatcherLogic:
    async def test_watcher_updates_pid(self, mock_dirs):
        s = await create_session("test-session", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.running, pid=100)

        watcher = Watcher()

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch("shoal.core.tmux.pane_pid", return_value=200),
            patch("shoal.core.tmux.capture_pane", return_value="some output"),
            patch("shoal.core.detection.detect_status", return_value=SessionStatus.running),
        ):
            await watcher._poll_cycle()

            updated = await get_session(s.id)
            assert updated.pid == 200

    async def test_watcher_finds_initial_pid(self, mock_dirs):
        s = await create_session("test-session", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.running, pid=None)

        watcher = Watcher()

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch("shoal.core.tmux.pane_pid", return_value=300),
            patch("shoal.core.tmux.capture_pane", return_value="some output"),
            patch("shoal.core.detection.detect_status", return_value=SessionStatus.running),
        ):
            await watcher._poll_cycle()

            updated = await get_session(s.id)
            assert updated.pid == 300

    async def test_watcher_marks_stopped_when_tmux_dies(self, mock_dirs):
        """When tmux session disappears, watcher should mark session as stopped."""
        s = await create_session("test-session", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.running, pid=100)

        watcher = Watcher()

        with patch("shoal.core.tmux.has_session", return_value=False):
            await watcher._poll_cycle()

            updated = await get_session(s.id)
            assert updated.status == SessionStatus.stopped
            assert updated.last_activity is not None

    async def test_watcher_detects_status_change(self, mock_dirs):
        """Watcher should detect and persist status transitions."""
        s = await create_session("test-session", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.running, pid=100)

        watcher = Watcher()

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch("shoal.core.tmux.pane_pid", return_value=100),
            patch("shoal.core.tmux.capture_pane", return_value="Error: something broke"),
            patch("shoal.core.detection.detect_status", return_value=SessionStatus.error),
        ):
            await watcher._poll_cycle()

            updated = await get_session(s.id)
            assert updated.status == SessionStatus.error
            assert updated.last_activity is not None

    async def test_watcher_notification_on_waiting(self, mock_dirs):
        """Watcher should notify when session transitions to waiting."""
        s = await create_session("test-session", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.running, pid=100)

        watcher = Watcher()

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch("shoal.core.tmux.pane_pid", return_value=100),
            patch("shoal.core.tmux.capture_pane", return_value="❯ Yes/No"),
            patch("shoal.core.detection.detect_status", return_value=SessionStatus.waiting),
            patch("shoal.services.watcher.notify") as mock_notify,
        ):
            await watcher._poll_cycle()

            updated = await get_session(s.id)
            assert updated.status == SessionStatus.waiting
            mock_notify.assert_called_once_with("Shoal", f"Session '{s.name}' is waiting for input")
