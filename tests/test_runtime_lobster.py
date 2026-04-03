from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shoal.models.config import ToolConfig
from shoal.models.state import LobsterRuntimeState, SessionState, TmuxRuntimeState
from shoal.services.runtime_providers.lobster import LobsterRuntimeProvider

# Mock for grpc stuff because of optional import in provider
claw_client_mock = MagicMock()
claw_client_mock.LobsterClient = MagicMock()


@pytest.fixture
def provider():
    return LobsterRuntimeProvider()


@pytest.fixture
def session():
    runtime = LobsterRuntimeState(
        lobster_id="test_claw", endpoint="grpc://localhost:50051", employee_id="emp_1"
    )
    return SessionState(
        id="test_session", name="test_session", tool="test_tool", path="/tmp/test", runtime=runtime
    )


@pytest.fixture
def tool_config():
    return ToolConfig(name="test_tool", command="echo hello")


class TestLobsterRuntimeProviderCoverage:
    def test_get_client_raises_if_not_lobster_runtime(self, provider):
        # We manually construct a SessionState as a dict to bypass pydantic validation logic
        # and trigger the check in the provider
        {
            "id": "t",
            "name": "t",
            "tool": "t",
            "path": "/",
            "runtime": TmuxRuntimeState(session_name="t"),
        }
        # This is a bit tricky, let's just make a session with tmux state if possible
        # Or just use an object that fakes it
        session = SessionState(
            id="t", name="t", tool="t", path="/", runtime=TmuxRuntimeState(session_name="t")
        )
        with pytest.raises(ValueError, match="Expected LobsterRuntimeState"):
            provider._get_client(session)

    def test_payload_raises_if_not_lobster_runtime(self, provider):
        with pytest.raises(ValueError, match="Expected LobsterRuntimeState"):
            provider.payload(TmuxRuntimeState(session_name="t"))

    def test_summary_raises_if_not_lobster_runtime(self, provider):
        with pytest.raises(ValueError, match="Expected LobsterRuntimeState"):
            provider.summary(TmuxRuntimeState(session_name="t"))

    def test_exists_in_async_context(self, provider, session):
        # Trigger line 121-124
        with patch("asyncio.get_running_loop", return_value=MagicMock()):
            assert provider.exists(session) is False

    @pytest.mark.asyncio
    async def test_async_exists_handles_exception(self, provider, session):
        with patch.object(provider, "_get_client", side_effect=Exception("grpc fail")):
            assert await provider.async_exists(session) is False

    @pytest.mark.asyncio
    async def test_async_exists_success(self, provider, session):
        # Setup the mock client properly to return a health object
        mock_client = AsyncMock()
        context_mock = AsyncMock()
        context_mock.health.return_value = {"healthy": True}
        mock_client.__aenter__.return_value = context_mock

        with patch.object(provider, "_get_client", return_value=mock_client):
            assert await provider.async_exists(session) is True

    def test_attach_is_noop(self, provider, session):
        provider.attach(session)

    def test_capture_output_is_noop(self, provider, session):
        assert provider.capture_output(session, lines=5) == ""

    @pytest.mark.asyncio
    async def test_async_capture_output_is_noop(self, provider, session):
        assert await provider.async_capture_output(session, lines=5) == ""

    @pytest.mark.asyncio
    async def test_async_send_input_delegates_to_a2a(self, provider, session):
        mock_client = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.send_message.return_value = {"task_id": "t1", "state": "working"}
        mock_client.__aenter__.return_value = mock_ctx
        with patch.object(provider, "_get_client", return_value=mock_client):
            await provider.async_send_input(session, "text")  # must not raise
        mock_ctx.send_message.assert_awaited_once_with(message="text")

    @pytest.mark.asyncio
    async def test_async_wait_for_ready_timeout(self, provider, session, tool_config):
        # mock sleep and loop time
        with (
            patch("asyncio.sleep", return_value=None),
            patch("asyncio.get_event_loop") as mock_loop,
        ):
            mock_loop.return_value.time.side_effect = [0, 10, 20]

            with patch.object(provider, "_get_client", side_effect=Exception("not ready")):
                with pytest.raises(TimeoutError):
                    await provider.async_wait_for_ready(session, tool_config, ready_timeout=5.0)

    @pytest.mark.asyncio
    async def test_async_wait_for_ready_success(self, provider, session, tool_config):
        mock_client = AsyncMock()
        context_mock = AsyncMock()
        context_mock.health.return_value = {"healthy": True}
        mock_client.__aenter__.return_value = context_mock

        with patch.object(provider, "_get_client", return_value=mock_client):
            await provider.async_wait_for_ready(session, tool_config, ready_timeout=5.0)

    @pytest.mark.asyncio
    async def test_async_rename_returns_unchanged_runtime(self, provider, session):
        result = await provider.async_rename(session, "new_name")
        assert result == session.runtime

    @pytest.mark.asyncio
    async def test_async_kill_returns_false(self, provider, session):
        assert await provider.async_kill(session) is False

    @pytest.mark.asyncio
    async def test_async_observe_handles_exception(self, provider, session, tool_config):
        with patch.object(provider, "_get_client", side_effect=Exception("failed")):
            obs = await provider.async_observe(session, tool_config, lines=10)
            assert obs.alive is False
