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
        mock_start.assert_called_once_with("test-mcp", "mcp-command")


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
