"""Tests for MCP proxy stdio-to-socket bridge."""

import logging
import sys
from unittest.mock import patch

import pytest

from shoal.services.mcp_proxy import main


def test_mcp_proxy_no_args(caplog: pytest.LogCaptureFixture) -> None:
    """Proxy should exit with usage message when no MCP name provided."""
    with (
        caplog.at_level(logging.ERROR, logger="shoal.mcp_proxy"),
        patch.object(sys, "argv", ["shoal-mcp-proxy"]),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        assert any("Usage: shoal-mcp-proxy" in r.message for r in caplog.records)


def test_mcp_proxy_socket_not_found(tmp_path: object, caplog: pytest.LogCaptureFixture) -> None:
    """Proxy should exit with error when socket doesn't exist."""
    state = tmp_path / "state"  # type: ignore[operator]
    state.mkdir()
    (state / "mcp-pool" / "sockets").mkdir(parents=True)

    with (
        caplog.at_level(logging.ERROR, logger="shoal.mcp_proxy"),
        patch.object(sys, "argv", ["shoal-mcp-proxy", "test-server"]),
        patch("shoal.services.mcp_proxy.state_dir", return_value=state),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        messages = " ".join(r.message for r in caplog.records)
        assert "MCP socket not found" in messages
        assert "test-server" in messages


def test_mcp_proxy_runs_bridge(tmp_path: object) -> None:
    """Proxy should call asyncio.run with _run_bridge when socket exists."""

    def _close_coro(coro) -> None:
        if hasattr(coro, "close"):
            coro.close()

    state = tmp_path / "state"  # type: ignore[operator]
    socket_path = state / "mcp-pool" / "sockets" / "test-server.sock"
    socket_path.parent.mkdir(parents=True)
    socket_path.touch()

    with (
        patch.object(sys, "argv", ["shoal-mcp-proxy", "test-server"]),
        patch("shoal.services.mcp_proxy.state_dir", return_value=state),
        patch("shoal.services.mcp_proxy._run_bridge") as mock_bridge,
        patch("shoal.services.mcp_proxy.asyncio.run") as mock_run,
    ):
        mock_run.side_effect = _close_coro
        main()
        mock_run.assert_called_once()
        mock_bridge.assert_called_once_with(str(socket_path))
        assert mock_run.call_count == 1


def test_mcp_proxy_invalid_name(caplog: pytest.LogCaptureFixture) -> None:
    """Proxy should reject invalid MCP names."""
    with (
        caplog.at_level(logging.ERROR, logger="shoal.mcp_proxy"),
        patch.object(sys, "argv", ["shoal-mcp-proxy", "bad;name"]),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        assert any("Invalid MCP name" in r.message for r in caplog.records)


def test_mcp_proxy_rejects_underscore_prefix(caplog: pytest.LogCaptureFixture) -> None:
    """Proxy should reject names starting with underscore."""
    with (
        caplog.at_level(logging.ERROR, logger="shoal.mcp_proxy"),
        patch.object(sys, "argv", ["shoal-mcp-proxy", "_bad"]),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        assert any("Invalid MCP name" in r.message for r in caplog.records)


def test_mcp_proxy_rejects_long_name(caplog: pytest.LogCaptureFixture) -> None:
    """Proxy should reject names longer than 64 characters."""
    long_name = "a" * 65
    with (
        caplog.at_level(logging.ERROR, logger="shoal.mcp_proxy"),
        patch.object(sys, "argv", ["shoal-mcp-proxy", long_name]),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        assert any("Invalid MCP name" in r.message for r in caplog.records)


def test_proxy_timeout_constants() -> None:
    """Verify timeout constants are set."""
    from shoal.services import mcp_proxy

    assert mcp_proxy._CONNECT_TIMEOUT == 30
    assert mcp_proxy._IDLE_TIMEOUT == 120
