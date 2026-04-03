from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from shoal.models.config import ToolConfig
from shoal.models.state import LobsterRuntimeState, SessionState
from shoal.services.runtime_providers.lobster import LobsterRuntimeProvider


@pytest.fixture
def provider():
    return LobsterRuntimeProvider()


@pytest.fixture
def session():
    runtime = LobsterRuntimeState(
        lobster_id="test_claw",
        endpoint="grpc://localhost:50051",
        employee_id="emp_1",
    )
    return SessionState(
        id="test_session",
        name="test_session",
        tool="test_tool",
        path="/tmp/test",
        runtime=runtime,
    )


def test_exists_no_running_loop_success(provider, session):
    """Test exists() when there is no running loop (RuntimeError) and async_exists succeeds."""
    with (
        patch("asyncio.get_running_loop", side_effect=RuntimeError("no loop")),
        patch.object(provider, "async_exists", new_callable=AsyncMock) as mock_async_exists,
    ):
        mock_async_exists.return_value = True
        assert provider.exists(session) is True


def test_exists_no_running_loop_exception(provider, session):
    """Test exists() when asyncio.run raises an exception."""
    with (
        patch("asyncio.get_running_loop", side_effect=RuntimeError("no loop")),
        patch.object(provider, "async_exists", new_callable=AsyncMock) as mock_async_exists,
    ):
        mock_async_exists.side_effect = Exception("failed to connect")
        assert provider.exists(session) is False


@pytest.mark.asyncio
async def test_async_wait_for_ready_with_sleep():
    """Test wait_for_ready where it has to sleep before succeeding."""
    provider = LobsterRuntimeProvider()

    runtime = LobsterRuntimeState(
        lobster_id="test_claw",
        endpoint="grpc://localhost:50051",
        employee_id="emp_1",
    )
    session = SessionState(
        id="test_session",
        name="test_session",
        tool="test_tool",
        path="/tmp/test",
        runtime=runtime,
    )

    tool_config = ToolConfig(name="test", command="echo")

    mock_client = AsyncMock()
    # First call failed/unhealthy, second call healthy
    mock_client.health.side_effect = [
        {"healthy": False},  # not ready
        Exception("connection error"),  # some exception
        {"healthy": True},  # ready
    ]

    # We need to return an async context manager object that has a health method
    context_mgr = AsyncMock()
    context_mgr.__aenter__.return_value = mock_client

    with (
        patch.object(provider, "_get_client", return_value=context_mgr),
        patch("asyncio.get_event_loop") as mock_loop,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        # We need elapsed < ready_timeout for 3 iterations
        mock_loop.return_value.time.side_effect = [0, 1, 2, 3, 4]

        await provider.async_wait_for_ready(session, tool_config, ready_timeout=10.0)
        assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_async_observe_success(provider, session):
    """Test async_observe when it successfully gets health."""
    tool_config = ToolConfig(name="test", command="echo")

    mock_client = AsyncMock()
    mock_client.health.return_value = {"healthy": True}

    context_mgr = AsyncMock()
    context_mgr.__aenter__.return_value = mock_client

    with patch.object(provider, "_get_client", return_value=context_mgr):
        obs = await provider.async_observe(session, tool_config, lines=10)

        assert obs.alive is True
        assert obs.runtime == session.runtime


def test_grpc_not_available_import_error():
    """Test coverage for the GRPC_AVAILABLE = False fallback."""
    import importlib
    import sys

    # Force the module variables by mocking import
    with patch.dict(sys.modules, {"shoal.core.lobster_client": None}):
        import shoal.services.runtime_providers.lobster as lobster_mod

        importlib.reload(lobster_mod)

        provider = lobster_mod.LobsterRuntimeProvider()

        session = SessionState(
            id="t", name="t", tool="t", path="/", runtime=LobsterRuntimeState(lobster_id="c")
        )

        with pytest.raises(RuntimeError, match="grpcio is required"):
            provider._get_client(session)

    # Reload again to restore the real module
    importlib.reload(lobster_mod)


@patch("shoal.services.runtime_providers.lobster.RuntimeLobsterClient")
def test_get_client_success(mock_client, provider, session):
    """Test _get_client success path."""
    client = provider._get_client(session)
    assert client is not None


def test_payload_success(provider, session):
    payload = provider.payload(session.runtime)
    assert isinstance(payload, dict)
    assert payload["lobster_id"] == session.runtime.lobster_id


def test_summary_success(provider, session):
    summary = provider.summary(session.runtime)
    assert isinstance(summary, dict)
    assert summary["lobster_id"] == session.runtime.lobster_id
