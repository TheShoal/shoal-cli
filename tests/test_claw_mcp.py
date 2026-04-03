"""Tests for claw scheduler MCP tools.

Tests the 5 claw MCP tools by calling the underlying tool functions directly
with a real in-memory SQLite database (same pattern as test_agent_bus_*.py).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from shoal.core.db import ShoalDB

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db(tmp_path):
    db_path = tmp_path / "shoal.db"
    ShoalDB._initialized = False
    db = ShoalDB(db_path)
    await db.connect()
    yield db
    await db.close()
    ShoalDB._initialized = False


def _past_iso(seconds: int = 60) -> str:
    return (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()


def _future_iso(seconds: int = 3600) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


# ---------------------------------------------------------------------------
# schedule_claw_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_claw_task(db: ShoalDB):
    from shoal.services.mcp_shoal_server import schedule_claw_task_tool

    with patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=db):
        result = await schedule_claw_task_tool(
            name="test-job",
            handler="purge_messages",
            session="sess-a",
            payload_json='{"days": 7}',
        )

    assert result["name"] == "test-job"
    assert result["handler"] == "purge_messages"
    assert result["session"] == "sess-a"
    assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_schedule_claw_task_with_run_at(db: ShoalDB):
    from shoal.services.mcp_shoal_server import schedule_claw_task_tool

    future = _future_iso(7200)
    with patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=db):
        result = await schedule_claw_task_tool(
            name="deferred",
            handler="summarize_journal",
            run_at=future,
        )

    assert result["run_at"] == future


@pytest.mark.asyncio
async def test_schedule_recurring_task(db: ShoalDB):
    from shoal.services.mcp_shoal_server import schedule_claw_task_tool

    with patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=db):
        result = await schedule_claw_task_tool(
            name="recurring-cleanup",
            handler="purge_messages",
            task_type="recurring",
            interval_seconds=3600.0,
        )

    assert result["task_type"] == "recurring"
    assert result["interval_seconds"] == 3600.0


# ---------------------------------------------------------------------------
# list_claw_tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_claw_tasks_empty(db: ShoalDB):
    from shoal.services.mcp_shoal_server import list_claw_tasks_tool

    with patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=db):
        result = await list_claw_tasks_tool()

    assert result == []


@pytest.mark.asyncio
async def test_list_claw_tasks_filters_session(db: ShoalDB):
    from shoal.services.mcp_shoal_server import list_claw_tasks_tool

    await db.create_claw_task(name="a", handler="h", run_at=_past_iso(), session="sess-a")
    await db.create_claw_task(name="b", handler="h", run_at=_past_iso(), session="sess-b")

    with patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=db):
        result = await list_claw_tasks_tool(session="sess-a")

    assert len(result) == 1
    assert result[0]["name"] == "a"


@pytest.mark.asyncio
async def test_list_claw_tasks_filters_status(db: ShoalDB):
    from shoal.services.mcp_shoal_server import list_claw_tasks_tool

    tid = await db.create_claw_task(name="x", handler="h", run_at=_past_iso(), session="s")
    await db.claim_claw_task(tid)

    with patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=db):
        pending = await list_claw_tasks_tool(session="s", status="pending")
        running = await list_claw_tasks_tool(session="s", status="running")

    assert len(pending) == 0
    assert len(running) == 1


# ---------------------------------------------------------------------------
# get_claw_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_claw_task(db: ShoalDB):
    from shoal.services.mcp_shoal_server import get_claw_task_tool

    tid = await db.create_claw_task(name="look-me-up", handler="h", run_at=_past_iso())

    with patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=db):
        result = await get_claw_task_tool(task_id=tid)

    assert result["name"] == "look-me-up"
    assert result["id"] == tid


@pytest.mark.asyncio
async def test_get_claw_task_not_found(db: ShoalDB):
    from fastmcp.exceptions import ToolError

    from shoal.services.mcp_shoal_server import get_claw_task_tool

    with (
        patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=db),
        pytest.raises(ToolError, match="not found"),
    ):
        await get_claw_task_tool(task_id=99999)


# ---------------------------------------------------------------------------
# cancel_claw_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_claw_task(db: ShoalDB):
    from shoal.services.mcp_shoal_server import cancel_claw_task_tool

    tid = await db.create_claw_task(name="cancel-me", handler="h", run_at=_future_iso())

    with patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=db):
        result = await cancel_claw_task_tool(task_id=tid)

    assert result["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_claw_task_not_pending(db: ShoalDB):
    from fastmcp.exceptions import ToolError

    from shoal.services.mcp_shoal_server import cancel_claw_task_tool

    tid = await db.create_claw_task(name="running", handler="h", run_at=_past_iso())
    await db.claim_claw_task(tid)

    with (
        patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=db),
        pytest.raises(ToolError, match="Cannot cancel"),
    ):
        await cancel_claw_task_tool(task_id=tid)


# ---------------------------------------------------------------------------
# watch_claw_tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watch_claw_tasks_returns_due(db: ShoalDB):
    from shoal.services.mcp_shoal_server import watch_claw_tasks_tool

    await db.create_claw_task(name="due-now", handler="h", run_at=_past_iso())

    with patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=db):
        result = await watch_claw_tasks_tool(timeout_seconds=2.0, poll_interval=0.1)

    assert len(result) >= 1
    assert result[0]["name"] == "due-now"


@pytest.mark.asyncio
async def test_watch_claw_tasks_timeout_returns_empty(db: ShoalDB):
    from shoal.services.mcp_shoal_server import watch_claw_tasks_tool

    with patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=db):
        result = await watch_claw_tasks_tool(timeout_seconds=0.3, poll_interval=0.1)

    assert result == []


# ---------------------------------------------------------------------------
# Round-trip: schedule + list + get + cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_list_get_cancel_roundtrip(db: ShoalDB):
    from shoal.services.mcp_shoal_server import (
        cancel_claw_task_tool,
        get_claw_task_tool,
        list_claw_tasks_tool,
        schedule_claw_task_tool,
    )

    with patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=db):
        # Schedule
        created = await schedule_claw_task_tool(
            name="roundtrip", handler="purge_messages", session="rt-sess"
        )
        tid = int(created["id"])  # type: ignore[arg-type]

        # List
        tasks = await list_claw_tasks_tool(session="rt-sess")
        assert len(tasks) == 1
        assert tasks[0]["id"] == tid

        # Get
        fetched = await get_claw_task_tool(task_id=tid)
        assert fetched["name"] == "roundtrip"

        # Cancel
        cancelled = await cancel_claw_task_tool(task_id=tid)
        assert cancelled["status"] == "cancelled"

        # Verify cancelled doesn't appear in pending list
        pending = await list_claw_tasks_tool(session="rt-sess", status="pending")
        assert len(pending) == 0
