"""Live smoke tests for Claw A2A gRPC.

Gated behind SHOAL_CLAW_LIVE_ENDPOINT and SHOAL_CLAW_LIVE_ID.
"""

from __future__ import annotations

import os

import pytest

from shoal.core.lobster_client import LobsterClient
from shoal.integrations.lobster import a2a_bridge as _bridge
from shoal.models.config.lobster import LobsterConfig

LIVE_ENDPOINT = os.environ.get("SHOAL_CLAW_LIVE_ENDPOINT")
LIVE_ID = os.environ.get("SHOAL_CLAW_LIVE_ID")
EMPLOYEE_ID = os.environ.get("SHOAL_CLAW_LIVE_EMPLOYEE_ID", "test-user")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (LIVE_ENDPOINT and LIVE_ID),
        reason="SHOAL_CLAW_LIVE_ENDPOINT and SHOAL_CLAW_LIVE_ID must be set",
    ),
]


@pytest.mark.asyncio
async def test_live_get_agent_card() -> None:
    """Fetch AgentCard from a live Claw."""
    assert LIVE_ENDPOINT and LIVE_ID
    config = LobsterConfig()
    async with LobsterClient(
        claw_id=LIVE_ID,
        endpoint=LIVE_ENDPOINT,
        employee_id=EMPLOYEE_ID,
        config=config,
    ) as client:
        assert _bridge.GRPC_AVAILABLE
        card = await client.get_agent_card()  # type: ignore[attr-defined]
        assert card.name
        assert card.endpoint
        assert card.version


@pytest.mark.asyncio
async def test_live_send_message_and_list_tasks() -> None:
    """Send a message to a live Claw and verify task creation."""
    assert LIVE_ENDPOINT and LIVE_ID
    config = LobsterConfig()
    async with LobsterClient(
        claw_id=LIVE_ID,
        endpoint=LIVE_ENDPOINT,
        employee_id=EMPLOYEE_ID,
        config=config,
    ) as client:
        # 1. Send message
        resp = await client.send_message(  # type: ignore[attr-defined]
            message="ping live smoke test",
        )
        assert resp["task_id"]
        assert "response" in resp
        assert "state" in resp

        # 2. List tasks to verify it shows up
        tasks = await client.list_tasks()  # type: ignore[attr-defined]
        assert any(t["id"] == resp["task_id"] for t in tasks)
