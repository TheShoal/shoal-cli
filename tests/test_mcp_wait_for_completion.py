"""Tests for wait_for_completion MCP tool."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("fastmcp")
from fastmcp.exceptions import ToolError

from shoal.models.state import SessionState, SessionStatus


def _make_session(name: str = "test", completed_at: datetime | None = None) -> SessionState:
    return SessionState(
        id="abc123",
        name=name,
        tool="claude",
        path="/tmp/project",
        tmux_session=f"_{name}",
        status=SessionStatus.running,
        completed_at=completed_at,
    )


# ---------------------------------------------------------------------------
# Already completed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_already_completed() -> None:
    """Session already has completed_at set — returns immediately without polling."""
    from shoal.services.mcp_shoal_server import wait_for_completion_tool

    now = datetime.now(UTC)
    session = _make_session(completed_at=now)

    with (
        patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value="abc123"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=session),
    ):
        result = await wait_for_completion_tool("test", timeout_seconds=300)

    assert result["completed"] is True
    assert result["waited_seconds"] == 0
    assert "completed_at" in result


# ---------------------------------------------------------------------------
# Completes during poll loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_completes_on_second_poll() -> None:
    """Session not done on first poll, completes on second."""
    from shoal.services.mcp_shoal_server import wait_for_completion_tool

    now = datetime.now(UTC)
    incomplete = _make_session(completed_at=None)
    complete = _make_session(completed_at=now)

    # get_session is called once before the loop (pre-check), then once per tick.
    # Tick 1 returns incomplete; tick 2 returns complete.
    get_session_mock = AsyncMock(side_effect=[incomplete, incomplete, complete])

    with (
        patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value="abc123"),
        patch("shoal.core.state.get_session", get_session_mock),
        patch("asyncio.sleep", new_callable=AsyncMock),
        # Hold time fixed so elapsed never exceeds timeout.
        patch("time.monotonic", return_value=0.0),
    ):
        result = await wait_for_completion_tool("test", timeout_seconds=30)

    assert result["completed"] is True
    assert result["waited_seconds"] >= 0
    assert "completed_at" in result


# ---------------------------------------------------------------------------
# Timeout — zero guard path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_timeout_zero() -> None:
    """timeout_seconds=0 hits the early-exit guard and returns immediately."""
    from shoal.services.mcp_shoal_server import wait_for_completion_tool

    incomplete = _make_session(completed_at=None)

    with (
        patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value="abc123"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=incomplete),
    ):
        result = await wait_for_completion_tool("test", timeout_seconds=0)

    assert result["completed"] is False
    assert result["waited_seconds"] == 0


# ---------------------------------------------------------------------------
# Timeout — elapsed exceeds timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_timeout_elapses() -> None:
    """Returns completed: False when monotonic time advances past timeout."""
    from shoal.services.mcp_shoal_server import wait_for_completion_tool

    incomplete = _make_session(completed_at=None)

    # monotonic() call 1 → start=0.0; call 2 → elapsed = int(31.0 - 0.0) = 31 > 30.
    monotonic_values = iter([0.0, 31.0])

    with (
        patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value="abc123"),
        patch("shoal.core.state.get_session", new_callable=AsyncMock, return_value=incomplete),
        patch("asyncio.sleep", new_callable=AsyncMock),
        patch("time.monotonic", side_effect=lambda: next(monotonic_values)),
    ):
        result = await wait_for_completion_tool("test", timeout_seconds=30)

    assert result["completed"] is False


# ---------------------------------------------------------------------------
# Session not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_session_not_found() -> None:
    """Raises ToolError when find_by_name returns None."""
    from shoal.services.mcp_shoal_server import wait_for_completion_tool

    with patch("shoal.core.state.find_by_name", new_callable=AsyncMock, return_value=None):
        with pytest.raises(ToolError):
            await wait_for_completion_tool("ghost", timeout_seconds=10)
