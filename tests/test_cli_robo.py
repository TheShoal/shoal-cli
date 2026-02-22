"""Tests for cli/robo.py."""

import asyncio
from unittest.mock import patch

from typer.testing import CliRunner

from shoal.cli.robo import app

runner = CliRunner()


def test_robo_setup_success(mock_dirs):
    """Test robo setup command."""
    result = runner.invoke(app, ["setup", "test-robo"])
    assert result.exit_code == 0
    assert "Created profile" in result.stdout
    assert "Robo 'test-robo' ready" in result.stdout

    config_dir, _ = mock_dirs
    profile_path = config_dir / "robo" / "test-robo.toml"
    assert profile_path.exists()


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
