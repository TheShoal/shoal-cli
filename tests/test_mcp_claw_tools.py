"""Tests for MCP Claw tools in mcp_shoal_server module."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_claw_client() -> Generator[MagicMock, None, None]:
    """Create a mock ClawClient class."""
    with patch("shoal.services.mcp_shoal_server.ClawClient") as mock:
        client_instance = AsyncMock()
        client_instance.status = AsyncMock()
        client_instance.health = AsyncMock()
        client_instance.close = AsyncMock()
        mock.return_value = client_instance
        yield mock


@pytest.fixture
def mock_config_with_claws() -> Generator[MagicMock, None, None]:
    """Mock config with claw configuration."""
    mock_cfg = MagicMock()
    mock_cfg.claw.grpc_addr = "localhost:50051"
    mock_cfg.claw.employee_id = "emp-123"
    mock_cfg.claw.conversations_dir = None
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
        import shoal.integrations.lobster.lobster_a2a as lobster_a2a

        with patch.object(lobster_a2a, "GRPC_AVAILABLE", True):
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
        import shoal.integrations.lobster.lobster_a2a as lobster_a2a

        with patch.object(lobster_a2a, "GRPC_AVAILABLE", True):
            result = await list_claws_tool()

    assert len(result) == 2
    assert {"name": "alpha", "grpc_addr": "localhost:50051"} in result
    assert {"name": "beta", "grpc_addr": "localhost:50052"} in result


async def test_list_claws_not_available() -> None:
    """list_claws raises error when grpcio not installed."""
    import shoal.integrations.lobster.lobster_a2a as lobster_a2a
    from shoal.services.mcp_shoal_server import list_claws_tool

    with patch.object(lobster_a2a, "GRPC_AVAILABLE", False):
        with pytest.raises(ToolError, match="Claw tools require grpcio"):
            await list_claws_tool()


# ---------------------------------------------------------------------------
# claw_status tests
# ---------------------------------------------------------------------------


async def test_claw_status_single(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """claw_status returns status for a single claw."""
    import shoal.integrations.lobster.lobster_a2a as lobster_a2a
    from shoal.services.mcp_shoal_server import claw_status_tool

    with patch.object(lobster_a2a, "GRPC_AVAILABLE", True):
        mock_claw_client.return_value.status.return_value = {"state": "READY"}

        result = await claw_status_tool(claw_id="claw-1")

        assert result == {"state": "READY", "grpc_addr": "localhost:50051"}
        mock_claw_client.assert_called_once_with(
            claw_id="claw-1",
            endpoint="localhost:50051",
            employee_id="emp-123",
            config=mock_config_with_claws.claw,
        )
        mock_claw_client.return_value.status.assert_called_once_with()
        mock_claw_client.return_value.close.assert_called_once()


async def test_claw_status_batch(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """claw_status returns status for multiple claws."""
    import shoal.integrations.lobster.lobster_a2a as lobster_a2a
    from shoal.services.mcp_shoal_server import claw_status_tool

    with patch.object(lobster_a2a, "GRPC_AVAILABLE", True):
        mock_claw_client.return_value.status.return_value = {"state": "ACTIVE"}

        result = cast(dict[str, Any], await claw_status_tool(claw_id=["claw-1", "claw-2"]))

        assert "results" in result
        results = cast(dict[str, Any], result["results"])
        assert results["claw-1"] == {"state": "ACTIVE", "grpc_addr": "localhost:50051"}
        assert results["claw-2"] == {"state": "ACTIVE", "grpc_addr": "localhost:50052"}
        assert mock_claw_client.call_count == 2
        assert mock_claw_client.return_value.status.call_count == 2
        assert mock_claw_client.return_value.close.call_count == 2


async def test_claw_status_error(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """claw_status handles errors gracefully."""
    import shoal.integrations.lobster.lobster_a2a as lobster_a2a
    from shoal.services.mcp_shoal_server import claw_status_tool

    with patch.object(lobster_a2a, "GRPC_AVAILABLE", True):
        mock_claw_client.return_value.status.side_effect = RuntimeError("Connection failed")

        result = cast(dict[str, Any], await claw_status_tool(claw_id="claw-1"))

        assert "error" in result
        assert "Connection failed" in cast(str, result["error"])


async def test_claw_status_not_available() -> None:
    """claw_status raises error when grpcio not installed."""
    import shoal.integrations.lobster.lobster_a2a as lobster_a2a
    from shoal.services.mcp_shoal_server import claw_status_tool

    with patch.object(lobster_a2a, "GRPC_AVAILABLE", False):
        with pytest.raises(ToolError, match="Claw tools require grpcio"):
            await claw_status_tool(claw_id="claw-1")


# ---------------------------------------------------------------------------
# claw_health tests
# ---------------------------------------------------------------------------


async def test_claw_health_healthy(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """claw_health returns healthy status."""
    import shoal.integrations.lobster.lobster_a2a as lobster_a2a
    from shoal.services.mcp_shoal_server import claw_health_tool

    with patch.object(lobster_a2a, "GRPC_AVAILABLE", True):
        mock_claw_client.return_value.health.return_value = {"healthy": True, "issues": []}

        result = await claw_health_tool(claw_id="claw-1")

        assert result == {"healthy": True, "issues": []}
        mock_claw_client.assert_called_once_with(
            claw_id="claw-1",
            endpoint="localhost:50051",
            employee_id="emp-123",
            config=mock_config_with_claws.claw,
        )
        mock_claw_client.return_value.health.assert_called_once_with()
        mock_claw_client.return_value.close.assert_called_once()


async def test_claw_health_unhealthy(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """claw_health returns unhealthy status with issues."""
    import shoal.integrations.lobster.lobster_a2a as lobster_a2a
    from shoal.services.mcp_shoal_server import claw_health_tool

    with patch.object(lobster_a2a, "GRPC_AVAILABLE", True):
        mock_claw_client.return_value.health.return_value = {
            "healthy": False,
            "issues": ["Claw reported unhealthy"],
        }

        result = cast(dict[str, Any], await claw_health_tool(claw_id="claw-1"))

        assert result["healthy"] is False
        assert "Claw reported unhealthy" in cast(list[str], result["issues"])


async def test_claw_health_exception(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """claw_health handles exceptions gracefully."""
    import shoal.integrations.lobster.lobster_a2a as lobster_a2a
    from shoal.services.mcp_shoal_server import claw_health_tool

    with patch.object(lobster_a2a, "GRPC_AVAILABLE", True):
        mock_claw_client.return_value.health.side_effect = RuntimeError("gRPC error")

        result = cast(dict[str, Any], await claw_health_tool(claw_id="claw-1"))

        assert result["healthy"] is False
        issues = cast(list[str], result["issues"])
        assert "gRPC error" in issues[0]


async def test_claw_health_not_available() -> None:
    """claw_health raises error when grpcio not installed."""
    import shoal.integrations.lobster.lobster_a2a as lobster_a2a
    from shoal.services.mcp_shoal_server import claw_health_tool

    with patch.object(lobster_a2a, "GRPC_AVAILABLE", False):
        with pytest.raises(ToolError, match="Claw tools require grpcio"):
            await claw_health_tool(claw_id="claw-1")


# ---------------------------------------------------------------------------
# send_to_claw tests
# ---------------------------------------------------------------------------


async def test_send_to_claw_success(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """send_to_claw delegates to send_a2a_message_tool."""
    import shoal.integrations.lobster.lobster_a2a as lobster_a2a
    from shoal.services.mcp_shoal_server import send_to_claw_tool

    with patch.object(lobster_a2a, "GRPC_AVAILABLE", True):
        with patch.object(lobster_a2a, "send_a2a_message_tool", new_callable=AsyncMock) as mock_a2a:
            mock_a2a.return_value = {"response": "A2A Response", "task_id": "t-1"}

            result = await send_to_claw_tool(claw_id="claw-1", message="Test message")

            assert result == {"response": "A2A Response", "task_id": "t-1"}
            mock_a2a.assert_called_once_with(
                claw_id="claw-1",
                message="Test message",
                employee_id=None,
            )


async def test_send_to_claw_with_employee_id(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """send_to_claw uses provided employee_id."""
    import shoal.integrations.lobster.lobster_a2a as lobster_a2a
    from shoal.services.mcp_shoal_server import send_to_claw_tool

    with patch.object(lobster_a2a, "GRPC_AVAILABLE", True):
        with patch.object(lobster_a2a, "send_a2a_message_tool", new_callable=AsyncMock) as mock_a2a:
            await send_to_claw_tool(claw_id="claw-1", message="Hello", employee_id="custom-emp")

            mock_a2a.assert_called_once_with(
                claw_id="claw-1",
                message="Hello",
                employee_id="custom-emp",
            )


async def test_send_to_claw_not_available() -> None:
    """send_to_claw raises error when grpcio not installed."""
    import shoal.integrations.lobster.lobster_a2a as lobster_a2a
    from shoal.services.mcp_shoal_server import send_to_claw_tool

    with patch.object(lobster_a2a, "GRPC_AVAILABLE", False):
        with pytest.raises(ToolError, match="Claw tools require grpcio"):
            await send_to_claw_tool(claw_id="claw-1", message="Test")


# ---------------------------------------------------------------------------
# get_agent_card tests
# ---------------------------------------------------------------------------


async def test_get_agent_card_success(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """get_agent_card returns AgentCard for a Claw."""
    # Import module first so it can be patched
    import shoal.integrations.lobster.lobster_a2a as lobster_a2a
    from shoal.services.mcp_shoal_server import get_agent_card_tool

    # Mock will use the lobster_a2a module which has its own ClawClient
    with patch.object(lobster_a2a, "GRPC_AVAILABLE", True):
        with patch("shoal.integrations.lobster.lobster_a2a.ClawClient") as mock_a2a_client:
            from shoal.models.config.agent_card import (
                AgentCapabilities,
                AgentCard,
                AgentProvider,
            )

            expected_card = AgentCard(
                name="claw-1",
                version="1.0.0",
                provider=AgentProvider(organization="us-mobile", url="https://usmobile.com"),
                capabilities=AgentCapabilities(streaming=True),
                endpoint="localhost:50051",
            )
            client_instance = AsyncMock()
            client_instance.get_agent_card = AsyncMock(return_value=expected_card)
            mock_a2a_client.return_value = client_instance

            result = await get_agent_card_tool(claw_id="claw-1")

    assert "name" in result
    assert "version" in result


async def test_get_agent_card_not_available() -> None:
    """get_agent_card raises error when grpcio not installed."""
    import shoal.integrations.lobster.lobster_a2a as lobster_a2a
    from shoal.services.mcp_shoal_server import get_agent_card_tool

    with patch.object(lobster_a2a, "GRPC_AVAILABLE", False):
        with pytest.raises(ToolError, match="Claw A2A bridge requires grpcio"):
            await get_agent_card_tool(claw_id="claw-1")


async def test_get_agent_card_not_found() -> None:
    """get_agent_card raises error when claw not configured."""
    import shoal.integrations.lobster.lobster_a2a as lobster_a2a
    from shoal.services.mcp_shoal_server import get_agent_card_tool

    with patch.object(lobster_a2a, "GRPC_AVAILABLE", True):
        with pytest.raises(ToolError, match="Claw 'unknown' not found"):
            await get_agent_card_tool(claw_id="unknown")


# ---------------------------------------------------------------------------
# send_a2a_message tests
# ---------------------------------------------------------------------------


async def test_send_a2a_message_success(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """send_a2a_message successfully sends work to a Claw."""
    import shoal.integrations.lobster.lobster_a2a as lobster_a2a
    from shoal.services.mcp_shoal_server import send_a2a_message_tool

    with patch.object(lobster_a2a, "GRPC_AVAILABLE", True):
        with patch("shoal.integrations.lobster.lobster_a2a.ClawClient") as mock_a2a_client:
            client_instance = AsyncMock()
            client_instance.send_message = AsyncMock(return_value={"response": "Done"})
            mock_a2a_client.return_value = client_instance

            result = await send_a2a_message_tool(claw_id="claw-1", message="Work")

    assert result == {"response": "Done"}


async def test_send_a2a_message_with_employee_id(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """send_a2a_message uses provided employee_id."""
    import shoal.integrations.lobster.lobster_a2a as lobster_a2a
    from shoal.services.mcp_shoal_server import send_a2a_message_tool

    with patch.object(lobster_a2a, "GRPC_AVAILABLE", True):
        with patch("shoal.integrations.lobster.lobster_a2a.ClawClient") as mock_a2a_client:
            client_instance = AsyncMock()
            client_instance.send_message = AsyncMock(return_value={"response": "Done"})
            mock_a2a_client.return_value = client_instance

            await send_a2a_message_tool(claw_id="claw-1", message="Work", employee_id="custom-emp")

            mock_a2a_client.assert_called_once_with(
                claw_id="claw-1",
                endpoint="localhost:50051",
                employee_id="custom-emp",
                config=mock_config_with_claws.claw,
            )
            client_instance.send_message.assert_called_once_with(
                message="Work",
                task_id=None,
            )


async def test_send_a2a_message_failure(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """send_a2a_message handles client failures."""
    import shoal.integrations.lobster.lobster_a2a as lobster_a2a
    from shoal.services.mcp_shoal_server import send_a2a_message_tool

    with patch.object(lobster_a2a, "GRPC_AVAILABLE", True):
        with patch("shoal.integrations.lobster.lobster_a2a.ClawClient") as mock_a2a_client:
            client_instance = AsyncMock()
            client_instance.send_message.side_effect = RuntimeError("gRPC failed")
            mock_a2a_client.return_value = client_instance

            with pytest.raises(ToolError, match="Failed to send message"):
                await send_a2a_message_tool(claw_id="claw-1", message="Test")


async def test_send_a2a_message_not_available() -> None:
    """send_a2a_message raises error when grpcio not installed."""
    from shoal.services.mcp_shoal_server import send_a2a_message_tool

    with patch("shoal.integrations.lobster.lobster_a2a.GRPC_AVAILABLE", False):
        with pytest.raises(ToolError, match="Claw A2A bridge requires grpcio"):
            await send_a2a_message_tool(claw_id="claw-1", message="Test")


# ---------------------------------------------------------------------------
# list_a2a_tasks tests
# ---------------------------------------------------------------------------


async def test_list_a2a_tasks_success(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """list_a2a_tasks returns tasks list."""
    from shoal.services.mcp_shoal_server import list_a2a_tasks_tool

    with patch("shoal.integrations.lobster.lobster_a2a.GRPC_AVAILABLE", True):
        with patch("shoal.integrations.lobster.lobster_a2a.ClawClient") as mock_a2a_client:
            client_instance = AsyncMock()
            client_instance.list_tasks = AsyncMock(return_value=[])
            client_instance.close = AsyncMock()
            mock_a2a_client.return_value = client_instance

            result = cast(dict[str, Any], await list_a2a_tasks_tool(claw_id="claw-1"))

    assert "tasks" in result
    assert "claw_id" in result
    assert result["claw_id"] == "claw-1"


async def test_list_a2a_tasks_with_filters(
    mock_claw_client: MagicMock, mock_config_with_claws: MagicMock
) -> None:
    """list_a2a_tasks accepts context_id and status filters."""
    from shoal.services.mcp_shoal_server import list_a2a_tasks_tool

    with patch("shoal.integrations.lobster.lobster_a2a.GRPC_AVAILABLE", True):
        with patch("shoal.integrations.lobster.lobster_a2a.ClawClient") as mock_a2a_client:
            client_instance = AsyncMock()
            client_instance.list_tasks = AsyncMock(return_value=[])
            client_instance.close = AsyncMock()
            mock_a2a_client.return_value = client_instance

            result = cast(
                dict[str, Any],
                await list_a2a_tasks_tool(
                    claw_id="claw-1", context_id="ctx-123", status="completed"
                ),
            )

    assert "tasks" in result


async def test_list_a2a_tasks_not_available() -> None:
    """list_a2a_tasks raises error when grpcio not installed."""
    from shoal.services.mcp_shoal_server import list_a2a_tasks_tool

    with patch("shoal.integrations.lobster.lobster_a2a.GRPC_AVAILABLE", False):
        with pytest.raises(ToolError, match="Claw A2A bridge requires grpcio"):
            await list_a2a_tasks_tool(claw_id="claw-1")


# ---------------------------------------------------------------------------
# sync_claw_conversations tests
# ---------------------------------------------------------------------------


async def test_sync_claw_conversations_dir_fallback(
    mock_config_with_claws: MagicMock,
) -> None:
    """sync_claw_conversations falls back to config or home dir."""
    from pathlib import Path

    from shoal.services.mcp_shoal_server import sync_claw_conversations_tool

    # Mock session resolution
    with patch("shoal.core.state.find_by_name", return_value="sess-123"):
        mock_session = MagicMock()
        mock_session.id = "sess-123"
        mock_session.name = "test-session"
        with patch("shoal.core.state.get_session", return_value=mock_session):
            # Mock sync functions to avoid IO
            with patch("shoal.core.qmd.import_qmd_to_journal", return_value=5) as mock_import:
                # 1. Test config fallback
                mock_config_with_claws.claw.conversations_dir = "/path/from/config"
                await sync_claw_conversations_tool(session="test-session")
                assert mock_import.call_args.kwargs["conversations_dir"] == Path(
                    "/path/from/config"
                )
                assert mock_import.call_args.kwargs["session_id"] == "sess-123"
                assert mock_import.call_args.kwargs["since"] is None
                assert mock_import.call_args.kwargs["journal_path"].name == "sess-123.md"

                # 2. Test home dir fallback when config is None
                mock_config_with_claws.claw.conversations_dir = None
                with patch("os.path.expanduser", return_value="/mock/home"):
                    await sync_claw_conversations_tool(session="test-session")
                    assert mock_import.call_args.kwargs["conversations_dir"] == Path(
                        "/mock/home/conversations"
                    )
                    assert mock_import.call_args.kwargs["session_id"] == "sess-123"
                    assert mock_import.call_args.kwargs["since"] is None
                    assert mock_import.call_args.kwargs["journal_path"].name == "sess-123.md"
