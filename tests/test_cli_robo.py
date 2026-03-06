"""Tests for cli/robo.py."""

import asyncio
import os
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from shoal.cli.robo import _read_robo_pid, _robo_pid_file, app

runner = CliRunner()


def test_robo_setup_success(mock_dirs):
    """Test robo setup command."""
    result = runner.invoke(app, ["setup", "test-robo"])
    assert result.exit_code == 0
    assert "Created profile" in result.stdout
    assert "Robo 'test-robo' ready" in result.stdout

    config_dir, state_dir = mock_dirs
    profile_path = config_dir / "robo" / "test-robo.toml"
    robo_dir = state_dir / "robo" / "test-robo"
    assert profile_path.exists()
    assert robo_dir.exists()
    assert (robo_dir / "AGENTS.md").exists()
    assert (robo_dir / "task-log.md").exists()


def test_robo_start_success(mock_dirs):
    """Test robo start command."""
    # First setup the profile
    runner.invoke(app, ["setup", "start-me"])

    with (
        patch("shoal.core.tmux.has_session", return_value=False),
        patch("shoal.core.tmux.new_session") as mock_new,
        patch("shoal.core.tmux.send_keys") as mock_send,
        patch("shoal.core.tmux.set_environment"),
    ):
        result = runner.invoke(app, ["start", "start-me"])
        assert result.exit_code == 0
        assert "Robo 'start-me' started" in result.stdout
        mock_new.assert_called_once()
        mock_send.assert_called_once()


def test_robo_start_not_found(mock_dirs):
    """Test robo start with missing profile."""
    result = runner.invoke(app, ["start", "nonexistent"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_robo_stop_success(mock_dirs):
    """Test robo stop command."""
    # Setup profile
    runner.invoke(app, ["setup", "stop-me"])

    with (
        patch("shoal.core.tmux.has_session", return_value=True),
        patch("shoal.core.tmux.kill_session") as mock_kill,
    ):
        result = runner.invoke(app, ["stop", "stop-me"])
        assert result.exit_code == 0
        assert "Robo 'stop-me' stopped" in result.stdout
        mock_kill.assert_called_once()


def test_robo_stop_not_running(mock_dirs):
    """Test robo stop when not running."""
    with patch("shoal.core.tmux.has_session", return_value=False):
        result = runner.invoke(app, ["stop", "not-running"])
        assert result.exit_code == 1
        assert "is not running" in result.stdout


def test_robo_status_empty(mock_dirs):
    """Test robo status with no robos."""
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "No robos configured" in result.stdout


def test_robo_status_with_robos(mock_dirs):
    """Test robo status with active robos."""
    # We must patch with_db to NOT reset the instance between calls in this test
    # so that state persists across multiple runner.invoke calls.
    # Alternatively, we can just use the DB directly to setup state.

    from datetime import UTC, datetime

    from shoal.core.db import get_db
    from shoal.models.state import RoboState, SessionStatus

    async def setup():
        db = await get_db()
        state = RoboState(
            name="status-test",
            tool="opencode",
            tmux_session="__status-test",
            status=SessionStatus.running,
            started_at=datetime.now(UTC),
        )
        await db.save_robo(state)

    # We don't use with_db here because we want it to persist for the next call
    asyncio.run(setup())

    with patch("shoal.core.tmux.has_session", return_value=True):
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Robo: status-test" in result.stdout
        assert "running" in result.stdout


def test_robo_watch_profile_not_found(mock_dirs):
    """Test robo watch with missing profile."""
    result = runner.invoke(app, ["watch", "nonexistent"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_robo_watch_shows_config(mock_dirs):
    """Test robo watch prints config summary."""
    runner.invoke(app, ["setup", "watch-me"])

    def _close_coro(coro: object) -> None:
        if hasattr(coro, "close"):
            coro.close()  # type: ignore[call-arg]
        return None

    with patch("shoal.cli.robo.asyncio.run", side_effect=_close_coro):
        result = runner.invoke(app, ["watch", "watch-me"])
    assert result.exit_code == 0
    assert "Robo watch" in result.stdout
    assert "poll_interval" in result.stdout
    assert "waiting_timeout" in result.stdout
    assert "auto_approve" in result.stdout


def test_robo_watch_default_profile(mock_dirs):
    """Test robo watch uses 'default' profile when no arg given."""
    runner.invoke(app, ["setup", "default"])

    def _close_coro(coro: object) -> None:
        if hasattr(coro, "close"):
            coro.close()  # type: ignore[call-arg]
        return None

    with patch("shoal.cli.robo.asyncio.run", side_effect=_close_coro):
        result = runner.invoke(app, ["watch"])
    assert result.exit_code == 0
    assert "profile: default" in result.stdout


def test_robo_watch_with_supervisor(mock_dirs):
    """Test robo watch calls RoboSupervisor.run() when module exists."""
    import types

    runner.invoke(app, ["setup", "sup-test"])

    mock_module = types.ModuleType("shoal.services.robo_supervisor")

    class MockRoboSupervisor:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        async def run(self) -> None:
            pass

    mock_module.RoboSupervisor = MockRoboSupervisor  # type: ignore[attr-defined]

    with patch.dict("sys.modules", {"shoal.services.robo_supervisor": mock_module}):
        result = runner.invoke(app, ["watch", "sup-test"])
        assert result.exit_code == 0
        assert "Robo watch" in result.stdout
        assert "not implemented yet" not in result.stdout


# ------------------------------------------------------------------
# Daemon mode tests
# ------------------------------------------------------------------


def test_robo_pid_file_path(mock_dirs):
    """_robo_pid_file returns expected path within runtime_dir."""
    pid_file = _robo_pid_file("myprofile")
    assert pid_file.name == "robo-myprofile.pid"


def test_read_robo_pid_missing(mock_dirs):
    """_read_robo_pid returns None when no PID file exists."""
    assert _read_robo_pid("no-such-profile") is None


def test_read_robo_pid_stale(mock_dirs, tmp_path):
    """_read_robo_pid removes stale PID file and returns None."""
    pid_file = _robo_pid_file("stale-test")
    pid_file.write_text("99999999")  # very unlikely real PID

    # If the process doesn't exist, os.kill raises ProcessLookupError
    with patch("shoal.cli.robo.os.kill", side_effect=ProcessLookupError):
        result = _read_robo_pid("stale-test")
    assert result is None
    assert not pid_file.exists()


def test_read_robo_pid_alive(mock_dirs):
    """_read_robo_pid returns the PID when the process is alive."""
    pid = os.getpid()
    pid_file = _robo_pid_file("alive-test")
    pid_file.write_text(str(pid))

    result = _read_robo_pid("alive-test")
    assert result == pid


def test_robo_watch_daemon_launches_subprocess(mock_dirs):
    """robo watch --daemon launches subprocess and prints pid."""
    runner.invoke(app, ["setup", "daemon-test"])

    mock_proc = MagicMock()
    mock_proc.pid = 12345

    with (
        patch("shoal.cli.robo._read_robo_pid", return_value=None),
        patch("shoal.cli.robo.subprocess.Popen", return_value=mock_proc) as mock_popen,
    ):
        result = runner.invoke(app, ["watch", "daemon-test", "--daemon"])

    assert result.exit_code == 0
    assert "12345" in result.stdout
    assert "daemon" in result.stdout
    mock_popen.assert_called_once()
    call_args = mock_popen.call_args
    # Verify profile name is passed as argv to the subprocess
    cmd = call_args[0][0]
    assert "shoal.services.robo_supervisor" in cmd
    assert "daemon-test" in cmd
    assert call_args[1]["start_new_session"] is True


def test_robo_watch_daemon_already_running(mock_dirs):
    """robo watch --daemon errors when daemon is already running."""
    runner.invoke(app, ["setup", "dup-test"])

    with patch("shoal.cli.robo._read_robo_pid", return_value=9876):
        result = runner.invoke(app, ["watch", "dup-test", "--daemon"])

    assert result.exit_code == 1
    assert "9876" in result.stdout
    assert "already running" in result.stdout


def test_robo_watch_stop_success(mock_dirs):
    """watch-stop sends SIGTERM and removes PID file."""
    import signal as _signal

    fake_pid = 99998
    pid_file = _robo_pid_file("stop-test")

    with (
        patch("shoal.cli.robo._read_robo_pid", return_value=fake_pid) as mock_read,
        patch("shoal.cli.robo.os.kill") as mock_kill,
    ):
        result = runner.invoke(app, ["watch-stop", "stop-test"])

    assert result.exit_code == 0
    assert str(fake_pid) in result.stdout
    assert "stopped" in result.stdout
    mock_read.assert_called_once_with("stop-test")
    mock_kill.assert_called_once_with(fake_pid, _signal.SIGTERM)
    assert not pid_file.exists()


def test_robo_watch_stop_not_running(mock_dirs):
    """watch-stop errors when daemon is not running."""
    with patch("shoal.cli.robo._read_robo_pid", return_value=None):
        result = runner.invoke(app, ["watch-stop", "gone-test"])

    assert result.exit_code == 1
    assert "not running" in result.stdout


def test_robo_watch_status_running(mock_dirs):
    """watch-status reports running when PID is alive."""
    with patch("shoal.cli.robo._read_robo_pid", return_value=5555):
        result = runner.invoke(app, ["watch-status", "live-test"])

    assert result.exit_code == 0
    assert "5555" in result.stdout
    assert "running" in result.stdout


def test_robo_watch_status_not_running(mock_dirs):
    """watch-status reports not running when no PID."""
    with patch("shoal.cli.robo._read_robo_pid", return_value=None):
        result = runner.invoke(app, ["watch-status", "dead-test"])

    assert result.exit_code == 0
    assert "not running" in result.stdout


def test_robo_watch_stop_default_profile(mock_dirs):
    """watch-stop uses 'default' profile when no arg given."""
    with patch("shoal.cli.robo._read_robo_pid", return_value=None):
        result = runner.invoke(app, ["watch-stop"])
    assert result.exit_code == 1
    assert "not running" in result.stdout


def test_robo_watch_status_default_profile(mock_dirs):
    """watch-status uses 'default' profile when no arg given."""
    with patch("shoal.cli.robo._read_robo_pid", return_value=None):
        result = runner.invoke(app, ["watch-status"])
    assert result.exit_code == 0
    assert "default" in result.stdout
