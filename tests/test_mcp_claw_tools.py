"""Tests for MCP Claw tools in mcp_shoal_server module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_claw_client():
    """Create a mock ClawClient class."""
    with patch("shoal.services.mcp_shoal_server.ClawClient") as mock:
        client_instance = AsyncMock()
        client_instance.status = AsyncMock()
        client_instance.health = AsyncMock()
        client_instance.turn = AsyncMock()
        client_instance.close = AsyncMock()
        mock.return_value = client_instance
        yield mock


@pytest.fixture
def mock_config_with_claws():
    """Mock config with claw configuration."""
    mock_cfg = MagicMock()
    mock_cfg.claw.grpc_addr = "localhost:50051"
    mock_cfg.claw.jwt_secret = "test-secret"  # noqa: S105
    mock_cfg.claw.employee_id = "emp-123"
    mock_cfg.claw.known_claws = {
        "claw-1": "localhost:50051",
        "claw-2": "localhost:50052",
    }
    with patch("shoal.core.config.load_config", return_value=mock_cfg):
        yield mock_cfg


# ---------------------------------------------------------------------------
# list_claws tests
# ---------------------------------------------------------------------------


async def test_list_claws_empty() -> None:
    """list_claws returns empty list when no claws configured."""
    from shoal.services.mcp_shoal_server import list_claws_tool

    mock_cfg = MagicMock()
    mock_cfg.claw.known_claws = {}
    with patch("shoal.core.config.load_config", return_value=mock_cfg):
        with patch("shoal.services.mcp_shoal_server._CLAW_TOOLS_AVAILABLE", True):
            result = await list_claws_tool()

    assert result == []


async def test_list_claws_with_known_claws() -> None:
    """list_claws returns configured claws."""
    from shoal.services.mcp_shoal_server import list_claws_tool

    mock_cfg = MagicMock()
    mock_cfg.claw.known_claws = {
        "alpha": "localhost:50051",
        "beta": "localhost:50052",
    }
    with patch("shoal.core.config.load_config", return_value=mock_cfg):
        with patch("shoal.services.mcp_shoal_server._CLAW_TOOLS_AVAILABLE", True):
            result = await list_claws_tool()

    assert len(result) == 2
    assert {"name": "alpha", "grpc_addr": "localhost:50051"} in result
    assert {"name": "beta", "grpc_addr": "localhost:50052"} in result


async def test_list_claws_not_available() -> None:
    """list_claws raises error when grpcio not installed."""
    from shoal.services.mcp_shoal_server import list_claws_tool

    with patch("shoal.services.mcp_shoal_server._CLAW_TOOLS_AVAILABLE", False):
        with pytest.raises(ToolError, match="Claw tools require grpcio"):
            await list_claws_tool()


# ---------------------------------------------------------------------------
# claw_status tests
# ---------------------------------------------------------------------------


async def test_claw_status_single(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """claw_status returns status for a single claw."""
    from shoal.services.mcp_shoal_server import claw_status_tool

    mock_status = MagicMock()
    mock_status.state = "READY"
    mock_claw_client.return_value.status.return_value = mock_status

    result = await claw_status_tool(claw_id="claw-1")

    assert result == {"state": "READY", "grpc_addr": "localhost:50051"}
    mock_claw_client.return_value.status.assert_called_once_with("claw-1")
    mock_claw_client.return_value.close.assert_called_once()


async def test_claw_status_batch(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """claw_status returns status for multiple claws."""
    from shoal.services.mcp_shoal_server import claw_status_tool

    mock_status = MagicMock()
    mock_status.state = "ACTIVE"
    mock_claw_client.return_value.status.return_value = mock_status

    result = await claw_status_tool(claw_id=["claw-1", "claw-2"])

    assert "results" in result
    assert result["results"]["claw-1"] == {"state": "ACTIVE", "grpc_addr": "localhost:50051"}
    assert result["results"]["claw-2"] == {"state": "ACTIVE", "grpc_addr": "localhost:50052"}
    assert mock_claw_client.return_value.close.call_count == 2


async def test_claw_status_error(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """claw_status handles errors gracefully."""
    from shoal.services.mcp_shoal_server import claw_status_tool

    mock_claw_client.return_value.status.side_effect = RuntimeError("Connection failed")

    result = await claw_status_tool(claw_id="claw-1")

    assert "error" in result
    assert "Connection failed" in result["error"]


async def test_claw_status_not_available() -> None:
    """claw_status raises error when grpcio not installed."""
    from shoal.services.mcp_shoal_server import claw_status_tool

    with patch("shoal.services.mcp_shoal_server._CLAW_TOOLS_AVAILABLE", False):
        with pytest.raises(ToolError, match="Claw tools require grpcio"):
            await claw_status_tool(claw_id="claw-1")


# ---------------------------------------------------------------------------
# claw_health tests
# ---------------------------------------------------------------------------


async def test_claw_health_healthy(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """claw_health returns healthy status."""
    from shoal.services.mcp_shoal_server import claw_health_tool

    mock_health = MagicMock()
    mock_health.healthy = True
    mock_claw_client.return_value.health.return_value = mock_health

    result = await claw_health_tool(claw_id="claw-1")

    assert result == {"healthy": True, "issues": []}
    mock_claw_client.return_value.health.assert_called_once_with("claw-1")
    mock_claw_client.return_value.close.assert_called_once()


async def test_claw_health_unhealthy(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """claw_health returns unhealthy status with issues."""
    from shoal.services.mcp_shoal_server import claw_health_tool

    mock_health = MagicMock()
    mock_health.healthy = False
    mock_claw_client.return_value.health.return_value = mock_health

    result = await claw_health_tool(claw_id="claw-1")

    assert result["healthy"] is False
    assert "Claw reported unhealthy" in result["issues"]


async def test_claw_health_exception(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """claw_health handles exceptions gracefully."""
    from shoal.services.mcp_shoal_server import claw_health_tool

    mock_claw_client.return_value.health.side_effect = RuntimeError("gRPC error")

    result = await claw_health_tool(claw_id="claw-1")

    assert result["healthy"] is False
    assert "gRPC error" in result["issues"][0]


async def test_claw_health_not_available() -> None:
    """claw_health raises error when grpcio not installed."""
    from shoal.services.mcp_shoal_server import claw_health_tool

    with patch("shoal.services.mcp_shoal_server._CLAW_TOOLS_AVAILABLE", False):
        with pytest.raises(ToolError, match="Claw tools require grpcio"):
            await claw_health_tool(claw_id="claw-1")


# ---------------------------------------------------------------------------
# send_to_claw tests
# ---------------------------------------------------------------------------


async def test_send_to_claw_success(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """send_to_claw returns response and state."""
    from shoal.services.mcp_shoal_server import send_to_claw_tool

    mock_claw_client.return_value.turn.return_value = "Claw response text"
    mock_status = MagicMock()
    mock_status.state = "ACTIVE"
    mock_claw_client.return_value.status.return_value = mock_status

    result = await send_to_claw_tool(claw_id="claw-1", message="Test message")

    assert result == {"response": "Claw response text", "state": "ACTIVE"}
    mock_claw_client.return_value.turn.assert_called_once_with("claw-1", "emp-123", "Test message")
    mock_claw_client.return_value.close.assert_called_once()


async def test_send_to_claw_with_employee_id(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """send_to_claw uses provided employee_id."""
    from shoal.services.mcp_shoal_server import send_to_claw_tool

    mock_claw_client.return_value.turn.return_value = "Response"
    mock_status = MagicMock()
    mock_status.state = "READY"
    mock_claw_client.return_value.status.return_value = mock_status

    result = await send_to_claw_tool(claw_id="claw-1", message="Hello", employee_id="custom-emp")

    assert result["response"] == "Response"
    mock_claw_client.return_value.turn.assert_called_once_with("claw-1", "custom-emp", "Hello")


async def test_send_to_claw_error(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """send_to_claw handles errors."""
    from shoal.services.mcp_shoal_server import send_to_claw_tool

    mock_claw_client.return_value.turn.side_effect = RuntimeError("Turn failed")

    with pytest.raises(RuntimeError, match="Turn failed"):
        await send_to_claw_tool(claw_id="claw-1", message="Test")

    mock_claw_client.return_value.close.assert_called_once()


async def test_send_to_claw_not_available() -> None:
    """send_to_claw raises error when grpcio not installed."""
    from shoal.services.mcp_shoal_server import send_to_claw_tool

    with patch("shoal.services.mcp_shoal_server._CLAW_TOOLS_AVAILABLE", False):
        with pytest.raises(ToolError, match="Claw tools require grpcio"):
            await send_to_claw_tool(claw_id="claw-1", message="Test")
