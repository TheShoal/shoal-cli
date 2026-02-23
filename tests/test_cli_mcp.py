"""Tests for cli/mcp.py."""

import asyncio
from unittest.mock import patch

from typer.testing import CliRunner

from shoal.cli.mcp import app
from shoal.core.db import with_db
from shoal.core.state import create_session, update_session

runner = CliRunner()


def test_mcp_start_success(mock_dirs):
    """Test starting an MCP server."""
    with (
        patch("shoal.cli.mcp.is_mcp_running", return_value=False),
        patch(
            "shoal.cli.mcp.start_mcp_server", return_value=(1234, "/tmp/mcp.sock", "mcp-command")
        ) as mock_start,
    ):
        result = runner.invoke(app, ["start", "test-mcp", "--command", "mcp-command"])
        assert result.exit_code == 0
        assert "MCP server 'test-mcp' started" in result.stdout
        mock_start.assert_called_once_with("test-mcp", "mcp-command", http=False, http_port=None)


def test_mcp_start_already_running(mock_dirs):
    """Test starting an MCP server that is already running."""
    with (
        patch("shoal.cli.mcp.is_mcp_running", return_value=True),
        patch("shoal.cli.mcp.read_pid", return_value=1234),
    ):
        result = runner.invoke(app, ["start", "test-mcp"])
        assert result.exit_code == 1
        assert "is already running" in result.stdout


def test_mcp_stop_success(mock_dirs):
    """Test stopping an MCP server."""

    async def setup():
        s = await create_session("test-s", "claude", "/tmp")
        await update_session(s.id, mcp_servers=["test-mcp"])

    asyncio.run(with_db(setup()))

    with patch("shoal.cli.mcp.stop_mcp_server") as mock_stop:
        result = runner.invoke(app, ["stop", "test-mcp"])
        assert result.exit_code == 0
        assert "MCP server 'test-mcp' stopped" in result.stdout
        mock_stop.assert_called_once_with("test-mcp")


def test_mcp_attach_success(mock_dirs, tmp_path):
    """Test attaching an MCP server to a session."""
    socket_path = tmp_path / "mcp.sock"
    socket_path.touch()

    async def setup():
        await create_session("test-s", "claude", "/tmp")

    asyncio.run(with_db(setup()))

    with (
        patch("shoal.cli.mcp.mcp_socket", return_value=socket_path),
        patch("shoal.cli.mcp.is_mcp_running", return_value=True),
        patch("shoal.cli.mcp.add_mcp_to_session") as mock_add,
        patch("shoal.services.mcp_configure.subprocess.run"),
    ):
        result = runner.invoke(app, ["attach", "test-s", "test-mcp"])
        assert result.exit_code == 0
        assert "Attached MCP 'test-mcp' to session 'test-s'" in result.stdout
        mock_add.assert_called_once()


def test_mcp_attach_auto_start(mock_dirs, tmp_path):
    """Test attaching auto-starts a server from registry."""
    socket_path = tmp_path / "mcp.sock"
    # socket doesn't exist initially

    async def setup():
        await create_session("test-s", "claude", "/tmp")

    asyncio.run(with_db(setup()))

    with (
        patch("shoal.cli.mcp.mcp_socket", return_value=socket_path),
        patch("shoal.cli.mcp.is_mcp_running", return_value=False),
        patch(
            "shoal.core.config.load_mcp_registry",
            return_value={"memory": "npx -y @modelcontextprotocol/server-memory"},
        ),
        patch(
            "shoal.cli.mcp.start_mcp_server",
            return_value=(1234, socket_path, "npx -y @modelcontextprotocol/server-memory"),
        ),
        patch("shoal.cli.mcp.add_mcp_to_session"),
        patch("shoal.services.mcp_configure.subprocess.run"),
    ):
        result = runner.invoke(app, ["attach", "test-s", "memory"])
        assert result.exit_code == 0
        assert "Auto-started" in result.stdout


def test_mcp_attach_not_in_registry(mock_dirs, tmp_path):
    """Test attaching an MCP server that is not running and not in registry."""
    socket_path = tmp_path / "mcp.sock"
    # socket doesn't exist

    async def setup():
        await create_session("test-s", "claude", "/tmp")

    asyncio.run(with_db(setup()))

    with (
        patch("shoal.cli.mcp.mcp_socket", return_value=socket_path),
        patch("shoal.cli.mcp.is_mcp_running", return_value=False),
        patch("shoal.core.config.load_mcp_registry", return_value={}),
    ):
        result = runner.invoke(app, ["attach", "test-s", "test-mcp"])
        assert result.exit_code == 1
        assert "is not running" in result.stdout


def test_mcp_logs_shows_content(mock_dirs, tmp_path):
    """Test mcp logs command shows log content."""
    from shoal.services import mcp_pool

    log_path = mcp_pool.mcp_log_file("test-server")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("line1\nline2\nline3\n")

    result = runner.invoke(app, ["logs", "test-server"])
    assert result.exit_code == 0
    assert "line1" in result.stdout
    assert "line3" in result.stdout


def test_mcp_logs_missing_file(mock_dirs):
    """Test mcp logs command with no log file."""
    result = runner.invoke(app, ["logs", "nonexistent"])
    assert result.exit_code == 1
    assert "No log file" in result.stdout


def test_mcp_logs_tail(mock_dirs, tmp_path):
    """Test mcp logs --tail flag limits output."""
    from shoal.services import mcp_pool

    log_path = mcp_pool.mcp_log_file("test-server")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"line{i}" for i in range(100)]
    log_path.write_text("\n".join(lines) + "\n")

    result = runner.invoke(app, ["logs", "test-server", "--tail", "5"])
    assert result.exit_code == 0
    assert "line95" in result.stdout
    assert "line10" not in result.stdout


def test_mcp_doctor_no_servers(mock_dirs):
    """Test doctor with no servers."""
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "No MCP servers" in result.stdout


def test_mcp_doctor_dead_pid(mock_dirs):
    """Test doctor shows dead PID when server not running."""
    from shoal.services import mcp_pool

    socket_dir = mcp_pool.mcp_socket("test").parent
    socket_dir.mkdir(parents=True, exist_ok=True)
    (socket_dir / "test.sock").touch()

    pid_path = mcp_pool.mcp_pid_file("test")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("99999")

    with patch("shoal.cli.mcp.is_mcp_running", return_value=False):
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "test" in result.stdout
    assert "dead" in result.stdout


def test_mcp_doctor_probe_success(mock_dirs):
    """Test doctor with a successful FastMCP probe."""
    from shoal.cli.mcp import _ProbeResult
    from shoal.services import mcp_pool

    socket_dir = mcp_pool.mcp_socket("memory").parent
    socket_dir.mkdir(parents=True, exist_ok=True)
    (socket_dir / "memory.sock").touch()

    pid_path = mcp_pool.mcp_pid_file("memory")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("1234")

    probe_result = _ProbeResult(
        connected=True,
        server_name="memory-server",
        server_version="1.2.0",
        tool_count=5,
        latency_ms=42.0,
    )

    with (
        patch("shoal.cli.mcp.is_mcp_running", return_value=True),
        patch("shoal.cli.mcp._probe_server", return_value=probe_result),
        patch("shoal.cli.mcp.asyncio.run", return_value=probe_result),
    ):
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "memory" in result.stdout
    assert "ok" in result.stdout
    assert "1.2.0" in result.stdout
    assert "42ms" in result.stdout
    assert "5" in result.stdout


def test_mcp_doctor_probe_timeout(mock_dirs):
    """Test doctor handles probe timeout gracefully."""
    from shoal.cli.mcp import _ProbeResult
    from shoal.services import mcp_pool

    socket_dir = mcp_pool.mcp_socket("slow-server").parent
    socket_dir.mkdir(parents=True, exist_ok=True)
    (socket_dir / "slow-server.sock").touch()

    pid_path = mcp_pool.mcp_pid_file("slow-server")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("1234")

    probe_result = _ProbeResult(error="timeout")

    with (
        patch("shoal.cli.mcp.is_mcp_running", return_value=True),
        patch("shoal.cli.mcp._probe_server", return_value=probe_result),
        patch("shoal.cli.mcp.asyncio.run", return_value=probe_result),
    ):
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "timeout" in result.stdout


def test_mcp_doctor_probe_error(mock_dirs):
    """Test doctor shows diagnostic error from probe."""
    from shoal.cli.mcp import _ProbeResult
    from shoal.services import mcp_pool

    socket_dir = mcp_pool.mcp_socket("broken").parent
    socket_dir.mkdir(parents=True, exist_ok=True)
    (socket_dir / "broken.sock").touch()

    pid_path = mcp_pool.mcp_pid_file("broken")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("1234")

    probe_result = _ProbeResult(error="socket unreachable: Connection refused")

    with (
        patch("shoal.cli.mcp.is_mcp_running", return_value=True),
        patch("shoal.cli.mcp._probe_server", return_value=probe_result),
        patch("shoal.cli.mcp.asyncio.run", return_value=probe_result),
    ):
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "socket unreachable" in result.stdout


def test_mcp_doctor_no_fastmcp(mock_dirs):
    """Test doctor gracefully handles missing fastmcp."""
    from shoal.services import mcp_pool

    socket_dir = mcp_pool.mcp_socket("test").parent
    socket_dir.mkdir(parents=True, exist_ok=True)
    (socket_dir / "test.sock").touch()

    pid_path = mcp_pool.mcp_pid_file("test")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("1234")

    import builtins

    real_import = builtins.__import__

    def mock_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "fastmcp":
            raise ImportError("No module named 'fastmcp'")
        return real_import(name, *args, **kwargs)

    with (
        patch("shoal.cli.mcp.is_mcp_running", return_value=True),
        patch("builtins.__import__", side_effect=mock_import),
    ):
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "skip" in result.stdout
    assert "fastmcp" in result.stdout


def test_mcp_start_http_success(mock_dirs):
    """Test starting an MCP server with --http flag."""
    from pathlib import Path

    with (
        patch("shoal.cli.mcp.is_mcp_running", return_value=False),
        patch(
            "shoal.cli.mcp.start_mcp_server",
            return_value=(1234, Path("/tmp/shoal.port"), "shoal-mcp-server"),
        ) as mock_start,
    ):
        result = runner.invoke(app, ["start", "shoal-orchestrator", "--http"])
        assert result.exit_code == 0
        assert "MCP server 'shoal-orchestrator' started" in result.stdout
        assert "http://localhost:8390" in result.stdout
        mock_start.assert_called_once_with("shoal-orchestrator", None, http=True, http_port=None)


def test_mcp_start_http_custom_port(mock_dirs):
    """Test starting an MCP server with --http and --port flags."""
    from pathlib import Path

    with (
        patch("shoal.cli.mcp.is_mcp_running", return_value=False),
        patch(
            "shoal.cli.mcp.start_mcp_server",
            return_value=(1234, Path("/tmp/shoal.port"), "shoal-mcp-server"),
        ) as mock_start,
    ):
        result = runner.invoke(app, ["start", "shoal-orchestrator", "--http", "--port", "9000"])
        assert result.exit_code == 0
        assert "http://localhost:9000" in result.stdout
        mock_start.assert_called_once_with("shoal-orchestrator", None, http=True, http_port=9000)


def test_mcp_ls_shows_http_server(mock_dirs):
    """Test that HTTP servers appear in mcp ls with transport indicator."""
    from shoal.services import mcp_pool

    # Create PID file (HTTP server has no socket)
    pid_path = mcp_pool.mcp_pid_file("shoal-orchestrator")
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("5678")

    # Create port file
    port_path = mcp_pool.mcp_port_file("shoal-orchestrator")
    port_path.parent.mkdir(parents=True, exist_ok=True)
    port_path.write_text("8390")

    with patch("shoal.cli.mcp.is_mcp_running", return_value=True):
        result = runner.invoke(app, ["ls"])
    assert result.exit_code == 0
    assert "shoal-orchestrator" in result.stdout
    assert "http:8390" in result.stdout
