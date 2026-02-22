"""Tests for services.mcp_pool module."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from shoal.services import mcp_pool


def test_mcp_socket(tmp_path, mock_dirs):
    """Test mcp_socket returns correct socket path."""
    result = mcp_pool.mcp_socket("memory")
    assert "mcp-pool/sockets/memory.sock" in str(result)


def test_pid_file(tmp_path, mock_dirs):
    """Test mcp_pid_file returns correct PID file path."""
    result = mcp_pool.mcp_pid_file("filesystem")
    assert "mcp-pool/pids/filesystem.pid" in str(result)


def test_read_pid_exists(tmp_path, mock_dirs):
    """Test read_pid when PID file exists."""
    pid_path = mcp_pool.mcp_pid_file("test-server")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("12345")

    result = mcp_pool.read_pid("test-server")
    assert result == 12345


def test_read_pid_not_found(tmp_path, mock_dirs):
    """Test read_pid when PID file doesn't exist."""
    result = mcp_pool.read_pid("nonexistent")
    assert result is None


def test_read_pid_invalid(tmp_path, mock_dirs):
    """Test read_pid with invalid PID content."""
    pid_path = mcp_pool.mcp_pid_file("invalid")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("not-a-number")

    result = mcp_pool.read_pid("invalid")
    assert result is None


def test_is_mcp_running_true(tmp_path, mock_dirs):
    """Test is_mcp_running when process is running."""
    # Write a PID file
    pid_path = mcp_pool.mcp_pid_file("test")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("999")

    with patch("os.kill", return_value=None) as mock_kill:
        result = mcp_pool.is_mcp_running("test")

        assert result is True
        mock_kill.assert_called_once_with(999, 0)


def test_is_mcp_running_false(tmp_path, mock_dirs):
    """Test is_mcp_running when process is not running."""
    # Write a PID file
    pid_path = mcp_pool.mcp_pid_file("test")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("999")

    with patch("shoal.services.mcp_pool.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)

        result = mcp_pool.is_mcp_running("test")

        assert result is False


def test_is_mcp_running_no_pid(tmp_path, mock_dirs):
    """Test is_mcp_running when no PID file exists."""
    result = mcp_pool.is_mcp_running("nonexistent")
    assert result is False


def test_start_mcp_server(tmp_path, mock_dirs):
    """Test start_mcp_server launches a Python subprocess server."""
    with (
        patch("shoal.services.mcp_pool.subprocess.Popen") as mock_popen,
        patch("shoal.services.mcp_pool.time.sleep"),
    ):
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None  # Still running
        mock_popen.return_value = mock_process

        mcp_pool.start_mcp_server("memory", "npx -y @modelcontextprotocol/server-memory")

        # Verify Popen was called with sys.executable module invocation
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args
        cmd = call_args[0][0]
        assert cmd[0] == sys.executable
        assert cmd[1] == "-m"
        assert cmd[2] == "shoal.services.mcp_pool"
        assert cmd[3] == "memory"
        assert cmd[4] == "npx -y @modelcontextprotocol/server-memory"

        # Verify PID file was written
        pid_path = mcp_pool.mcp_pid_file("memory")
        assert pid_path.exists()
        assert pid_path.read_text() == "12345"


def test_start_mcp_server_uses_default(tmp_path, mock_dirs):
    """Test start_mcp_server resolves default command from _DEFAULT_SERVERS."""
    with (
        patch("shoal.services.mcp_pool.subprocess.Popen") as mock_popen,
        patch("shoal.services.mcp_pool.time.sleep"),
    ):
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process

        pid, socket, cmd = mcp_pool.start_mcp_server("memory")

        assert cmd == "npx -y @modelcontextprotocol/server-memory"
        assert pid == 12345


def test_stop_mcp_server(tmp_path, mock_dirs):
    """Test stop_mcp_server terminates a server."""
    # Create PID file and socket
    pid_path = mcp_pool.mcp_pid_file("memory")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("12345")

    socket_path = mcp_pool.mcp_socket("memory")
    socket_path.touch()

    with (
        patch("os.kill") as mock_kill,
        patch("time.sleep"),
    ):
        # Mock first kill succeeds, second kill (poll) finds process gone
        mock_kill.side_effect = [None, ProcessLookupError]

        mcp_pool.stop_mcp_server("memory")

        # Verify kill command was called
        assert mock_kill.call_count >= 1
        assert mock_kill.call_args_list[0][0][0] == 12345

        # Verify PID file and socket were removed
        assert not pid_path.exists()
        assert not socket_path.exists()


def test_stop_mcp_server_not_running(tmp_path, mock_dirs):
    """Test stop_mcp_server when server isn't running."""
    with pytest.raises(FileNotFoundError):
        mcp_pool.stop_mcp_server("nonexistent")


def test_start_mcp_server_unknown(tmp_path, mock_dirs):
    """Test start_mcp_server with unknown name and no command."""
    with pytest.raises(ValueError, match="Unknown MCP server"):
        mcp_pool.start_mcp_server("custom-server")


def test_start_mcp_server_already_running(tmp_path, mock_dirs):
    """Test start_mcp_server when server is already running."""
    socket_path = mcp_pool.mcp_socket("memory")
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.touch()

    pid_path = mcp_pool.mcp_pid_file("memory")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("12345")

    with patch("os.kill", return_value=None), pytest.raises(RuntimeError, match="already running"):
        mcp_pool.start_mcp_server("memory")


def test_mcp_log_file_path(mock_dirs):
    """Test mcp_log_file returns correct log path."""
    result = mcp_pool.mcp_log_file("memory")
    assert "mcp-pool/logs/memory.log" in str(result)


def test_start_creates_log_file(mock_dirs):
    """Test start_mcp_server creates log directory."""
    with (
        patch("shoal.services.mcp_pool.subprocess.Popen") as mock_popen,
        patch("shoal.services.mcp_pool.time.sleep"),
    ):
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process

        mcp_pool.start_mcp_server("memory", "echo test")

        log_dir = mcp_pool.mcp_log_dir()
        assert log_dir.exists()


def test_truncate_log_small_file(tmp_path):
    """Small files should not be truncated."""
    log = tmp_path / "test.log"
    log.write_text("small content")
    original_size = log.stat().st_size

    mcp_pool._truncate_log(log, max_bytes=1024)
    assert log.stat().st_size == original_size


def test_truncate_log_large_file(tmp_path):
    """Large files should be truncated to last half of max_bytes."""
    log = tmp_path / "test.log"
    log.write_bytes(b"x" * 2000)

    mcp_pool._truncate_log(log, max_bytes=1000)
    assert log.stat().st_size == 500


def test_truncate_log_missing_file(tmp_path):
    """Missing files should be a no-op."""
    mcp_pool._truncate_log(tmp_path / "nonexistent.log")


def test_pool_timeout_constants():
    """Verify timeout constants are set."""
    assert mcp_pool._CONNECT_TIMEOUT == 30
    assert mcp_pool._IDLE_TIMEOUT == 120
