"""Tests for cli/watcher.py."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from shoal.cli.watcher import app

runner = CliRunner()


def test_watcher_start_foreground(mock_dirs):
    """Test watcher start in foreground."""
    with (
        patch("shoal.cli.watcher._read_pid", return_value=None),
        patch("shoal.services.watcher.Watcher") as mock_watcher_class,
        patch("shoal.core.db.with_db"),
        patch("asyncio.run") as mock_asyncio_run,
    ):
        mock_watcher_instance = MagicMock()
        mock_watcher_class.return_value = mock_watcher_instance

        result = runner.invoke(app, ["start", "--foreground"])
        assert result.exit_code == 0
        mock_watcher_class.assert_called_once()
        mock_asyncio_run.assert_called_once()


def test_watcher_start_background(mock_dirs):
    """Test watcher start in background."""
    with (
        patch("shoal.cli.watcher._read_pid", return_value=None),
        patch("subprocess.Popen") as mock_popen,
    ):
        mock_proc = MagicMock()
        mock_proc.pid = 9999
        mock_popen.return_value = mock_proc

        result = runner.invoke(app, ["start"])
        assert result.exit_code == 0
        assert "Watcher started (pid: 9999)" in result.stdout
        mock_popen.assert_called_once()


def test_watcher_start_already_running(mock_dirs):
    """Test starting watcher when already running."""
    with patch("shoal.cli.watcher._read_pid", return_value=1234):
        result = runner.invoke(app, ["start"])
        assert result.exit_code == 1
        assert "already running" in result.stdout


def test_watcher_stop_success(mock_dirs):
    """Test stopping the watcher."""
    with (
        patch("shoal.cli.watcher._read_pid", return_value=1234),
        patch("os.kill") as mock_kill,
        patch("shoal.cli.watcher._pid_file") as mock_pid_file,
    ):
        mock_path = MagicMock()
        mock_pid_file.return_value = mock_path

        result = runner.invoke(app, ["stop"])
        assert result.exit_code == 0
        assert "Watcher stopped" in result.stdout
        mock_kill.assert_called_once_with(1234, 15)  # SIGTERM
        mock_path.unlink.assert_called_once()


def test_watcher_status_running(mock_dirs):
    """Test watcher status when running."""
    with patch("shoal.cli.watcher._read_pid", return_value=1234):
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "running (pid: 1234)" in result.stdout


def test_watcher_status_not_running(mock_dirs):
    """Test watcher status when not running."""
    with patch("shoal.cli.watcher._read_pid", return_value=None):
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "not running" in result.stdout
