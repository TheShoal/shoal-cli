"""Tests for MCP proxy stdio-to-socket bridge."""

import sys
from unittest.mock import patch

import pytest

from shoal.services.mcp_proxy import main


def test_mcp_proxy_no_args(capsys):
    """Proxy should exit with usage message when no MCP name provided."""
    with patch.object(sys, "argv", ["shoal-mcp-proxy"]):
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Usage: shoal-mcp-proxy <mcp-name>" in captured.err


def test_mcp_proxy_socket_not_found(tmp_path, capsys):
    """Proxy should exit with error when socket doesn't exist."""
    state = tmp_path / "state"
    state.mkdir()
    (state / "mcp-pool" / "sockets").mkdir(parents=True)

    with (
        patch.object(sys, "argv", ["shoal-mcp-proxy", "test-server"]),
        patch("shoal.services.mcp_proxy.state_dir", return_value=state),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "MCP socket not found" in captured.err
        assert "test-server.sock" in captured.err
        assert "shoal mcp start test-server" in captured.err


def test_mcp_proxy_runs_bridge(tmp_path):
    """Proxy should call asyncio.run with _run_bridge when socket exists."""
    state = tmp_path / "state"
    socket_path = state / "mcp-pool" / "sockets" / "test-server.sock"
    socket_path.parent.mkdir(parents=True)
    socket_path.touch()

    with (
        patch.object(sys, "argv", ["shoal-mcp-proxy", "test-server"]),
        patch("shoal.services.mcp_proxy.state_dir", return_value=state),
        patch("shoal.services.mcp_proxy.asyncio.run") as mock_run,
    ):
        main()
        mock_run.assert_called_once()


def test_mcp_proxy_invalid_name(capsys):
    """Proxy should reject invalid MCP names."""
    with patch.object(sys, "argv", ["shoal-mcp-proxy", "bad;name"]):
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Invalid MCP server name" in captured.err
