"""Tests for the claw scheduler loop."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from shoal.core.claw_scheduler import ClawScheduler
from shoal.core.db import ShoalDB
from shoal.models.claw import ClawTask, TaskResult

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
# Handler helpers
# ---------------------------------------------------------------------------


class SuccessHandler:
    """Handler that always succeeds and records calls."""

    def __init__(self) -> None:
        self.calls: list[ClawTask] = []

    async def __call__(self, task: ClawTask) -> TaskResult:
        self.calls.append(task)
        return TaskResult.succeeded


class FailHandler:
    """Handler that always returns retryable failure."""

    async def __call__(self, task: ClawTask) -> TaskResult:
        return TaskResult.retryable_failure


class ExplodingHandler:
    """Handler that raises an exception."""

    async def __call__(self, task: ClawTask) -> TaskResult:
        raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_drains_one_due_task(db: ShoalDB):
    handler = SuccessHandler()
    scheduler = ClawScheduler(db, {"test_handler": handler}, tick_seconds=0.05)

    await db.create_claw_task(name="t1", handler="test_handler", run_at=_past_iso())

    await scheduler.start()
    await asyncio.sleep(0.2)
    await scheduler.stop()

    assert len(handler.calls) == 1
    assert handler.calls[0].name == "t1"

    # Task should be marked done
    task = await db.get_claw_task(handler.calls[0].id)
    assert task is not None
    assert task["status"] == "done"


@pytest.mark.asyncio
async def test_scheduler_ignores_future_tasks(db: ShoalDB):
    handler = SuccessHandler()
    scheduler = ClawScheduler(db, {"test_handler": handler}, tick_seconds=0.05)

    await db.create_claw_task(name="future", handler="test_handler", run_at=_future_iso())

    await scheduler.start()
    await asyncio.sleep(0.2)
    await scheduler.stop()

    assert len(handler.calls) == 0


@pytest.mark.asyncio
async def test_scheduler_handles_unknown_handler(db: ShoalDB):
    scheduler = ClawScheduler(db, {}, tick_seconds=0.05)

    tid = await db.create_claw_task(name="orphan", handler="missing_handler", run_at=_past_iso())

    await scheduler.start()
    await asyncio.sleep(0.2)
    await scheduler.stop()

    task = await db.get_claw_task(tid)
    assert task is not None
    assert task["status"] == "dead_letter"


@pytest.mark.asyncio
async def test_scheduler_retryable_failure(db: ShoalDB):
    scheduler = ClawScheduler(db, {"fail": FailHandler()}, tick_seconds=0.05)

    tid = await db.create_claw_task(
        name="will-fail", handler="fail", run_at=_past_iso(), max_retries=3
    )

    await scheduler.start()
    await asyncio.sleep(0.2)
    await scheduler.stop()

    task = await db.get_claw_task(tid)
    assert task is not None
    # Should be reset to pending with retry_count incremented
    assert task["status"] == "pending"
    assert task["retry_count"] == 1


@pytest.mark.asyncio
async def test_scheduler_handler_exception_is_retryable(db: ShoalDB):
    scheduler = ClawScheduler(db, {"explode": ExplodingHandler()}, tick_seconds=0.05)

    tid = await db.create_claw_task(
        name="will-explode", handler="explode", run_at=_past_iso(), max_retries=3
    )

    await scheduler.start()
    await asyncio.sleep(0.2)
    await scheduler.stop()

    task = await db.get_claw_task(tid)
    assert task is not None
    assert task["status"] == "pending"
    assert task["retry_count"] == 1
    assert task["error"] == "boom"


@pytest.mark.asyncio
async def test_scheduler_signal_wakes_immediately(db: ShoalDB):
    handler = SuccessHandler()
    # Long tick so it would normally wait
    scheduler = ClawScheduler(db, {"h": handler}, tick_seconds=10.0)

    await scheduler.start()

    # Schedule a task and signal
    await db.create_claw_task(name="signaled", handler="h", run_at=_past_iso())
    scheduler.signal()

    await asyncio.sleep(0.2)
    await scheduler.stop()

    assert len(handler.calls) == 1


@pytest.mark.asyncio
async def test_scheduler_reschedules_recurring(db: ShoalDB):
    handler = SuccessHandler()
    scheduler = ClawScheduler(db, {"h": handler}, tick_seconds=0.05)

    tid = await db.create_claw_task(
        name="recurring",
        handler="h",
        run_at=_past_iso(),
        task_type="recurring",
        interval_seconds=600.0,
    )

    await scheduler.start()
    await asyncio.sleep(0.2)
    await scheduler.stop()

    # Original should be done
    task = await db.get_claw_task(tid)
    assert task is not None
    assert task["status"] == "done"

    # A new pending task should exist
    session_tasks = await db.list_session_tasks(None)
    pending = [t for t in session_tasks if t["status"] == "pending"]
    assert len(pending) == 1
    assert pending[0]["name"] == "recurring"
    assert pending[0]["id"] != tid


@pytest.mark.asyncio
async def test_scheduler_start_stop_lifecycle(db: ShoalDB):
    scheduler = ClawScheduler(db, {}, tick_seconds=0.05)

    assert scheduler.running is False
    await scheduler.start()
    assert scheduler.running is True
    await scheduler.stop()
    assert scheduler.running is False
