"""Tests for background watcher service."""

from unittest.mock import patch

import pytest

from shoal.core.state import create_session, get_session, update_session
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
            patch(
                "shoal.core.tmux.list_panes",
                return_value=[
                    {"id": "%1", "title": f"shoal:{s.id}", "command": "claude", "active": "1"}
                ],
            ),
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
            patch(
                "shoal.core.tmux.list_panes",
                return_value=[
                    {"id": "%1", "title": f"shoal:{s.id}", "command": "claude", "active": "1"}
                ],
            ),
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
            patch(
                "shoal.core.tmux.list_panes",
                return_value=[
                    {"id": "%1", "title": f"shoal:{s.id}", "command": "claude", "active": "1"}
                ],
            ),
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
            patch(
                "shoal.core.tmux.list_panes",
                return_value=[
                    {"id": "%1", "title": f"shoal:{s.id}", "command": "claude", "active": "1"}
                ],
            ),
            patch("shoal.core.tmux.pane_pid", return_value=100),
            patch("shoal.core.tmux.capture_pane", return_value="❯ Yes/No"),
            patch("shoal.core.detection.detect_status", return_value=SessionStatus.waiting),
            patch("shoal.services.watcher.notify") as mock_notify,
        ):
            await watcher._poll_cycle()

            updated = await get_session(s.id)
            assert updated.status == SessionStatus.waiting
            mock_notify.assert_called_once_with("Shoal", f"Session '{s.name}' is waiting for input")

    async def test_watcher_tracks_titled_pane_even_if_command_changes(self, mock_dirs):
        """Watcher should track the session-titled pane regardless of current command."""
        s = await create_session("test-session", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.running, pid=100)

        watcher = Watcher()

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch(
                "shoal.core.tmux.list_panes",
                return_value=[
                    {"id": "%1", "title": f"shoal:{s.id}", "command": "zsh", "active": "1"}
                ],
            ),
            patch("shoal.core.tmux.capture_pane", return_value="some output") as mock_capture,
            patch(
                "shoal.services.watcher.detect_status", return_value=SessionStatus.running
            ) as mock_detect,
        ):
            await watcher._poll_cycle()

            mock_capture.assert_called_once_with("%1", 20, False)
            mock_detect.assert_called_once()

    async def test_watcher_ignores_active_pane_drift(self, mock_dirs):
        """Watcher should ignore active pane changes and keep tracking the titled pane."""
        s = await create_session("test-session", "claude", "/tmp/repo")
        await update_session(s.id, status=SessionStatus.running, pid=100)

        watcher = Watcher()

        with (
            patch("shoal.core.tmux.has_session", return_value=True),
            patch(
                "shoal.core.tmux.list_panes",
                return_value=[
                    {"id": "%1", "title": f"shoal:{s.id}", "command": "zsh", "active": "0"},
                    {"id": "%2", "title": "", "command": "claude", "active": "1"},
                ],
            ),
            patch("shoal.core.tmux.pane_pid", return_value=100),
            patch("shoal.core.tmux.capture_pane", return_value="some output") as mock_capture,
            patch("shoal.services.watcher.detect_status", return_value=SessionStatus.running),
        ):
            await watcher._poll_cycle()

            mock_capture.assert_called_once_with("%1", 20, False)

    async def test_watcher_warns_on_missing_tool_config(self, mock_dirs):
        """Watcher should log a warning when tool config is missing."""
        s = await create_session("test-session", "claude", "/tmp/repo")
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

            # Verify warning was logged
            mock_logger.warning.assert_called_once()
            call_args = str(mock_logger.warning.call_args)
            assert "Tool config missing" in call_args
            assert s.id in call_args
