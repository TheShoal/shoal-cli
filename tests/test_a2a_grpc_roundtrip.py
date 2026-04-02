"""In-process gRPC round-trip tests for the A2A bridge.

Skipped when grpcio is not installed (default dev env).
Run explicitly with:

    uv run --extra claw pytest tests/test_a2a_grpc_roundtrip.py -v

The test spins up a real grpc.aio.server() in-process, registers a minimal
AgentLoopServicer, and exercises ClawClient.get_agent_card(),
ClawClient.send_message(), and ClawClient.list_tasks() against it.
"""

from __future__ import annotations

from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Optional gRPC imports — guarded so this file is safely importable in CI
# without grpcio installed.
# ---------------------------------------------------------------------------
try:
    import grpc.aio  # noqa: I001 — import order below is intentional (descriptor pool)

    from shoal.core.claw_client import ClawClient

    # a2a_core_pb2 must be in the descriptor pool before a2a_claw_pb2_grpc is imported
    # (a2a_claw_pb2_grpc transitively loads a2a_claw_pb2 which depends on a2a_core.proto).
    # The noqa: I001 above suppresses ruff's auto-merge of the two proto import lines.
    from shoal.core.proto import a2a_core_pb2
    from shoal.core.proto import a2a_claw_pb2_grpc

    # Import a2a_bridge after proto stubs — its module body patches ClawClient.
    from shoal.integrations.lobster import a2a_bridge as _bridge

    _grpc_for_test: bool = _bridge.GRPC_AVAILABLE
except (ImportError, TypeError):
    _grpc_for_test = False

pytestmark = pytest.mark.skipif(
    not _grpc_for_test,
    reason="grpcio not installed; run with `uv run --extra claw pytest`",
)


# ---------------------------------------------------------------------------
# Minimal in-process AgentLoop servicer
# ---------------------------------------------------------------------------


class _TestAgentLoopServicer(a2a_claw_pb2_grpc.AgentLoopServicer):
    """Minimal async servicer for round-trip tests."""

    async def GetAgentCard(self, request: Any, context: Any) -> Any:
        return a2a_core_pb2.AgentCard(  # type: ignore[attr-defined]
            name="round-trip-claw",
            version="3.0.0",
            endpoint="grpc://localhost:0",
            description="Test round-trip Claw",
            provider=a2a_core_pb2.AgentProvider(  # type: ignore[attr-defined]
                organization="test-lobster-party",
                url="https://test.usmobile.com",
            ),
            capabilities=a2a_core_pb2.AgentCapabilities(  # type: ignore[attr-defined]
                streaming=True,
                push_notifications=False,
                state_transition_reports=True,
            ),
        )

    async def SendMessage(self, request: Any, context: Any) -> Any:
        echo = ""
        for part in request.message.parts:
            if part.HasField("text"):
                echo = f"echo: {part.text.text}"
                break
        return a2a_core_pb2.SendMessageResponse(  # type: ignore[attr-defined]
            message=a2a_core_pb2.Message(  # type: ignore[attr-defined]
                id="resp-1",
                role=a2a_core_pb2.ROLE_AGENT,  # type: ignore[attr-defined]
                parts=[
                    a2a_core_pb2.Part(  # type: ignore[attr-defined]
                        text=a2a_core_pb2.TextPart(text=echo)  # type: ignore[attr-defined]
                    )
                ],
            )
        )

    async def ListTasks(self, request: Any, context: Any) -> Any:
        return a2a_core_pb2.ListTasksResponse(tasks=[])  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def claw_client_and_server() -> Any:
    """Start an in-process gRPC server and yield a connected ClawClient."""
    server = grpc.aio.server()
    a2a_claw_pb2_grpc.add_AgentLoopServicer_to_server(  # type: ignore[no-untyped-call]
        _TestAgentLoopServicer(), server
    )
    port = server.add_insecure_port("localhost:0")
    await server.start()

    client = ClawClient(claw_id="round-trip-claw", endpoint=f"grpc://localhost:{port}")
    try:
        yield client
    finally:
        await client.close()
        await server.stop(grace=0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_agent_card_round_trip(claw_client_and_server: Any) -> None:
    """GetAgentCard: proto serialization → ClawClient → AgentCard Pydantic model."""
    client = claw_client_and_server

    card = await client.get_agent_card()

    from shoal.models.config.agent_card import AgentCard

    assert isinstance(card, AgentCard)
    assert card.name == "round-trip-claw"
    assert card.version == "3.0.0"
    assert card.description == "Test round-trip Claw"
    assert card.provider.organization == "test-lobster-party"
    assert card.provider.url == "https://test.usmobile.com"
    assert card.capabilities.streaming is True
    assert card.capabilities.push_notifications is False
    assert card.capabilities.state_transition_reports is True


@pytest.mark.asyncio
async def test_send_message_round_trip(claw_client_and_server: Any) -> None:
    """SendMessage: request serialization → response deserialization → dict."""
    client = claw_client_and_server

    result = await client.send_message("hello from shoal")

    assert isinstance(result, dict)
    assert "task_id" in result
    assert "response" in result
    assert "state" in result
    assert result["response"] == "echo: hello from shoal"
    assert result["state"] == "completed"


@pytest.mark.asyncio
async def test_list_tasks_empty(claw_client_and_server: Any) -> None:
    """ListTasks: empty response returns empty list without error."""
    client = claw_client_and_server

    tasks = await client.list_tasks()

    assert tasks == []


@pytest.mark.asyncio
async def test_send_message_preserves_explicit_task_id(claw_client_and_server: Any) -> None:
    """Explicit task_id is echoed back in the response dict."""
    client = claw_client_and_server

    result = await client.send_message("ping", task_id="explicit-tid")

    # Servicer returns a message (not a task oneof), so task_id stays as explicit-tid.
    assert result["task_id"] == "explicit-tid"


@pytest.mark.asyncio
async def test_channel_reuse(claw_client_and_server: Any) -> None:
    """Two consecutive calls share the same channel (no reconnect errors)."""
    client = claw_client_and_server

    card1 = await client.get_agent_card()
    card2 = await client.get_agent_card()

    assert card1.name == card2.name
    assert client._channel is not None
