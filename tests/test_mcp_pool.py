"""Tests for services.mcp_pool module."""

import asyncio
import pathlib
import signal
import sys
from contextlib import suppress
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

        pid, _socket, cmd = mcp_pool.start_mcp_server("memory")

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


# --- validate_mcp_name ---


def test_validate_mcp_name_empty():
    with pytest.raises(ValueError, match="cannot be empty"):
        mcp_pool.validate_mcp_name("")


def test_validate_mcp_name_invalid():
    with pytest.raises(ValueError, match="Invalid MCP name"):
        mcp_pool.validate_mcp_name("../bad-name")


def test_validate_mcp_name_valid():
    mcp_pool.validate_mcp_name("memory")
    mcp_pool.validate_mcp_name("my-server-01")


# --- read_port ---


def test_read_port_exists(mock_dirs):
    port_path = mcp_pool.mcp_port_file("test-server")
    port_path.parent.mkdir(parents=True, exist_ok=True)
    port_path.write_text("8390")
    assert mcp_pool.read_port("test-server") == 8390


def test_read_port_not_found(mock_dirs):
    assert mcp_pool.read_port("nonexistent") is None


def test_read_port_invalid(mock_dirs):
    port_path = mcp_pool.mcp_port_file("bad")
    port_path.parent.mkdir(parents=True, exist_ok=True)
    port_path.write_text("not-a-number")
    assert mcp_pool.read_port("bad") is None


# --- start_mcp_server HTTP mode ---


def test_start_mcp_server_http_mode(mock_dirs):
    with (
        patch("shoal.services.mcp_pool.subprocess.Popen") as mock_popen,
        patch("shoal.services.mcp_pool.time.sleep"),
    ):
        mock_process = MagicMock()
        mock_process.pid = 54321
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process

        pid, path, cmd = mcp_pool.start_mcp_server(
            "shoal-orchestrator", "shoal-mcp-server", http=True, http_port=9000
        )

        assert pid == 54321
        assert cmd == "shoal-mcp-server"
        assert "ports" in str(path)
        assert path.read_text() == "9000"

        call_args = mock_popen.call_args[0][0]
        assert call_args == ["shoal-mcp-server", "--http", "9000"]

        pid_path = mcp_pool.mcp_pid_file("shoal-orchestrator")
        assert pid_path.read_text() == "54321"


def test_start_mcp_server_http_mode_default_port(mock_dirs):
    with (
        patch("shoal.services.mcp_pool.subprocess.Popen") as mock_popen,
        patch("shoal.services.mcp_pool.time.sleep"),
    ):
        mock_process = MagicMock()
        mock_process.pid = 11111
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process

        _pid, path, _cmd = mcp_pool.start_mcp_server(
            "shoal-orchestrator", "shoal-mcp-server", http=True
        )

        call_args = mock_popen.call_args[0][0]
        assert call_args == ["shoal-mcp-server", "--http", "8390"]
        assert path.read_text() == "8390"


def test_start_mcp_server_http_mode_fails(mock_dirs):
    with (
        patch("shoal.services.mcp_pool.subprocess.Popen") as mock_popen,
        patch("shoal.services.mcp_pool.time.sleep"),
    ):
        mock_process = MagicMock()
        mock_process.pid = 99999
        mock_process.poll.return_value = 1
        mock_popen.return_value = mock_process

        with pytest.raises(RuntimeError, match="HTTP mode"):
            mcp_pool.start_mcp_server("shoal-orchestrator", "shoal-mcp-server", http=True)


# --- start_mcp_server socket mode failure ---


def test_start_mcp_server_socket_mode_fails(mock_dirs):
    with (
        patch("shoal.services.mcp_pool.subprocess.Popen") as mock_popen,
        patch("shoal.services.mcp_pool.time.sleep"),
    ):
        mock_process = MagicMock()
        mock_process.pid = 88888
        mock_process.poll.return_value = 1
        mock_popen.return_value = mock_process

        with pytest.raises(RuntimeError, match="Failed to start MCP server"):
            mcp_pool.start_mcp_server("memory", "npx -y @modelcontextprotocol/server-memory")

        socket_path = mcp_pool.mcp_socket("memory")
        assert not socket_path.exists()


# --- stop_mcp_server edge cases ---


def test_stop_mcp_server_sigkill_needed(mock_dirs):

    pid_path = mcp_pool.mcp_pid_file("stubborn")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("77777")

    socket_path = mcp_pool.mcp_socket("stubborn")
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.touch()

    with (
        patch("os.kill") as mock_kill,
        patch("shoal.services.mcp_pool.time.sleep"),
    ):
        mock_kill.side_effect = [None, None, None]
        mcp_pool.stop_mcp_server("stubborn")

        assert mock_kill.call_count == 3
        mock_kill.assert_any_call(77777, signal.SIGTERM)
        mock_kill.assert_any_call(77777, 0)
        mock_kill.assert_any_call(77777, signal.SIGKILL)

    assert not pid_path.exists()
    assert not socket_path.exists()


def test_stop_mcp_server_already_dead(mock_dirs):
    pid_path = mcp_pool.mcp_pid_file("dead")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("66666")

    with (
        patch("os.kill", side_effect=ProcessLookupError) as mock_kill,
        patch("shoal.services.mcp_pool.time.sleep"),
    ):
        mcp_pool.stop_mcp_server("dead")
        mock_kill.assert_called_once()

    assert not pid_path.exists()


def test_stop_mcp_server_cleans_port_file(mock_dirs):
    pid_path = mcp_pool.mcp_pid_file("http-srv")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("55555")

    port_path = mcp_pool.mcp_port_file("http-srv")
    port_path.parent.mkdir(parents=True, exist_ok=True)
    port_path.write_text("8390")

    with (
        patch("os.kill", side_effect=ProcessLookupError),
        patch("shoal.services.mcp_pool.time.sleep"),
    ):
        mcp_pool.stop_mcp_server("http-srv")

    assert not port_path.exists()


def test_stop_mcp_server_invalid_pid(mock_dirs):
    pid_path = mcp_pool.mcp_pid_file("badpid")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("not-a-number")

    mcp_pool.stop_mcp_server("badpid")
    assert not pid_path.exists()


# --- mcp_port_file path ---


def test_mcp_port_file_path(mock_dirs):
    result = mcp_pool.mcp_port_file("memory")
    assert "mcp-pool/ports/memory.port" in str(result)


# --- _pool_main ---


def test_pool_main_insufficient_args(mock_dirs):
    with patch("sys.argv", ["mcp_pool"]), pytest.raises(SystemExit, match="1"):
        mcp_pool._pool_main()


def test_pool_main_runs_serve(mock_dirs):
    with (
        patch("sys.argv", ["mcp_pool", "memory", "echo hello"]),
        patch("asyncio.run") as mock_run,
    ):
        mock_run.side_effect = KeyboardInterrupt
        mcp_pool._pool_main()

        mock_run.assert_called_once()
        # Verify socket directory was created
        socket_path = mcp_pool.mcp_socket("memory")
        assert socket_path.parent.exists()


# --- _handle_client (spawn failure path) ---


@pytest.mark.asyncio
async def test_handle_client_spawn_failure():
    """_handle_client closes writer when command spawn fails."""
    reader = asyncio.StreamReader()
    transport = MagicMock()
    protocol = MagicMock()
    writer = asyncio.StreamWriter(transport, protocol, reader, asyncio.get_event_loop())

    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("no such cmd")):
        await mcp_pool._handle_client(reader, writer, "nonexistent-command")

    transport.close.assert_called()


# --- _serve (starts and stops unix server) ---


@pytest.mark.asyncio
async def test_serve_creates_unix_server(tmp_path):
    """_serve creates a Unix socket server that can be cancelled."""
    sock_path = str(tmp_path / "test.sock")

    task = asyncio.create_task(mcp_pool._serve(sock_path, "echo hello"))
    await asyncio.sleep(0.1)

    # Verify socket was created
    assert pathlib.Path(sock_path).exists()

    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
