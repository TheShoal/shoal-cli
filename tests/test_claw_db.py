"""Tests for the claw scheduler DB layer (claw_tasks CRUD)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _past_iso(seconds: int = 60) -> str:
    return (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()


def _future_iso(seconds: int = 3600) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


# ---------------------------------------------------------------------------
# create + get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_get_claw_task(db: ShoalDB):
    task_id = await db.create_claw_task(
        name="test-task",
        handler="purge_messages",
        run_at=_now_iso(),
        session="sess-a",
        payload_json='{"days": 7}',
    )
    assert task_id > 0

    task = await db.get_claw_task(task_id)
    assert task is not None
    assert task["name"] == "test-task"
    assert task["handler"] == "purge_messages"
    assert task["session"] == "sess-a"
    assert task["status"] == "pending"
    assert task["retry_count"] == 0
    assert task["payload_json"] == '{"days": 7}'


@pytest.mark.asyncio
async def test_get_nonexistent_task_returns_none(db: ShoalDB):
    assert await db.get_claw_task(99999) is None


@pytest.mark.asyncio
async def test_create_system_task_null_session(db: ShoalDB):
    task_id = await db.create_claw_task(
        name="system-cleanup",
        handler="purge_messages",
        run_at=_now_iso(),
    )
    task = await db.get_claw_task(task_id)
    assert task is not None
    assert task["session"] is None


@pytest.mark.asyncio
async def test_create_with_all_optional_fields(db: ShoalDB):
    task_id = await db.create_claw_task(
        name="full-task",
        handler="summarize_journal",
        run_at=_now_iso(),
        session="sess-b",
        task_type="recurring",
        cron_expr=None,
        interval_seconds=300.0,
        payload_json='{"budget": "short"}',
        max_retries=5,
        correlation_id="wf-123",
        metadata_json='{"source": "test"}',
    )
    task = await db.get_claw_task(task_id)
    assert task is not None
    assert task["task_type"] == "recurring"
    assert task["interval_seconds"] == 300.0
    assert task["max_retries"] == 5
    assert task["correlation_id"] == "wf-123"
    assert task["metadata_json"] == '{"source": "test"}'


# ---------------------------------------------------------------------------
# list_due_tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_due_tasks_returns_only_pending_past(db: ShoalDB):
    past = _past_iso(120)
    future = _future_iso(3600)

    await db.create_claw_task(name="due", handler="h", run_at=past)
    await db.create_claw_task(name="not-due", handler="h", run_at=future)

    due = await db.list_due_tasks(_now_iso())
    assert len(due) == 1
    assert due[0]["name"] == "due"


@pytest.mark.asyncio
async def test_list_due_tasks_respects_limit(db: ShoalDB):
    past = _past_iso(120)
    for i in range(5):
        await db.create_claw_task(name=f"task-{i}", handler="h", run_at=past)

    due = await db.list_due_tasks(_now_iso(), limit=3)
    assert len(due) == 3


@pytest.mark.asyncio
async def test_list_due_tasks_excludes_non_pending(db: ShoalDB):
    past = _past_iso(120)
    tid = await db.create_claw_task(name="claimed", handler="h", run_at=past)
    await db.claim_claw_task(tid)

    due = await db.list_due_tasks(_now_iso())
    assert len(due) == 0


# ---------------------------------------------------------------------------
# list_session_tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_session_tasks_filters_by_session(db: ShoalDB):
    await db.create_claw_task(name="a-task", handler="h", run_at=_now_iso(), session="sess-a")
    await db.create_claw_task(name="b-task", handler="h", run_at=_now_iso(), session="sess-b")
    await db.create_claw_task(name="sys-task", handler="h", run_at=_now_iso())

    a_tasks = await db.list_session_tasks("sess-a")
    assert len(a_tasks) == 1
    assert a_tasks[0]["name"] == "a-task"

    sys_tasks = await db.list_session_tasks(None)
    assert len(sys_tasks) == 1
    assert sys_tasks[0]["name"] == "sys-task"


@pytest.mark.asyncio
async def test_list_session_tasks_filters_by_status(db: ShoalDB):
    tid = await db.create_claw_task(name="t", handler="h", run_at=_now_iso(), session="s")
    await db.claim_claw_task(tid)

    pending = await db.list_session_tasks("s", status="pending")
    assert len(pending) == 0

    running = await db.list_session_tasks("s", status="running")
    assert len(running) == 1


# ---------------------------------------------------------------------------
# claim_claw_task (CAS)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_task_transitions_to_running(db: ShoalDB):
    tid = await db.create_claw_task(name="t", handler="h", run_at=_now_iso())
    assert await db.claim_claw_task(tid) is True

    task = await db.get_claw_task(tid)
    assert task is not None
    assert task["status"] == "running"
    assert task["last_run_at"] is not None


@pytest.mark.asyncio
async def test_claim_task_fails_on_double_claim(db: ShoalDB):
    tid = await db.create_claw_task(name="t", handler="h", run_at=_now_iso())
    assert await db.claim_claw_task(tid) is True
    assert await db.claim_claw_task(tid) is False


@pytest.mark.asyncio
async def test_claim_task_fails_on_nonexistent(db: ShoalDB):
    assert await db.claim_claw_task(99999) is False


# ---------------------------------------------------------------------------
# complete_claw_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_task_sets_done(db: ShoalDB):
    tid = await db.create_claw_task(name="t", handler="h", run_at=_now_iso())
    await db.claim_claw_task(tid)
    await db.complete_claw_task(tid)

    task = await db.get_claw_task(tid)
    assert task is not None
    assert task["status"] == "done"
    assert task["completed_at"] is not None


# ---------------------------------------------------------------------------
# fail_claw_task — retry and dead-letter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fail_task_retryable_resets_to_pending(db: ShoalDB):
    tid = await db.create_claw_task(
        name="t", handler="h", run_at=_now_iso(), max_retries=3
    )
    await db.claim_claw_task(tid)
    await db.fail_claw_task(tid, "oops")

    task = await db.get_claw_task(tid)
    assert task is not None
    assert task["status"] == "pending"
    assert task["retry_count"] == 1
    assert task["error"] == "oops"
    # run_at should be in the future (backoff)
    assert str(task["run_at"]) > _now_iso()


@pytest.mark.asyncio
async def test_fail_task_exhausted_retries_dead_letters(db: ShoalDB):
    tid = await db.create_claw_task(
        name="t", handler="h", run_at=_now_iso(), max_retries=1
    )
    await db.claim_claw_task(tid)
    await db.fail_claw_task(tid, "fatal")

    task = await db.get_claw_task(tid)
    assert task is not None
    assert task["status"] == "dead_letter"
    assert task["retry_count"] == 1


@pytest.mark.asyncio
async def test_fail_task_permanent_dead_letters_immediately(db: ShoalDB):
    tid = await db.create_claw_task(
        name="t", handler="h", run_at=_now_iso(), max_retries=5
    )
    await db.claim_claw_task(tid)
    await db.fail_claw_task(tid, "permanent", permanent=True)

    task = await db.get_claw_task(tid)
    assert task is not None
    assert task["status"] == "dead_letter"
    assert task["retry_count"] == 1


# ---------------------------------------------------------------------------
# cancel_claw_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_pending_task(db: ShoalDB):
    tid = await db.create_claw_task(name="t", handler="h", run_at=_now_iso())
    assert await db.cancel_claw_task(tid) is True

    task = await db.get_claw_task(tid)
    assert task is not None
    assert task["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_running_task_fails(db: ShoalDB):
    tid = await db.create_claw_task(name="t", handler="h", run_at=_now_iso())
    await db.claim_claw_task(tid)
    assert await db.cancel_claw_task(tid) is False


# ---------------------------------------------------------------------------
# reschedule_recurring_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reschedule_recurring_creates_new_task(db: ShoalDB):
    tid = await db.create_claw_task(
        name="recurring-t",
        handler="h",
        run_at=_now_iso(),
        task_type="recurring",
        interval_seconds=600.0,
        session="sess-a",
        correlation_id="wf-1",
    )

    new_id = await db.reschedule_recurring_task(tid)
    assert new_id is not None
    assert new_id != tid

    new_task = await db.get_claw_task(new_id)
    assert new_task is not None
    assert new_task["name"] == "recurring-t"
    assert new_task["handler"] == "h"
    assert new_task["session"] == "sess-a"
    assert new_task["task_type"] == "recurring"
    assert new_task["status"] == "pending"
    # Should be scheduled ~600s in the future
    assert str(new_task["run_at"]) > _now_iso()


@pytest.mark.asyncio
async def test_reschedule_once_returns_none(db: ShoalDB):
    tid = await db.create_claw_task(
        name="once-t", handler="h", run_at=_now_iso(), task_type="once"
    )
    assert await db.reschedule_recurring_task(tid) is None


@pytest.mark.asyncio
async def test_reschedule_nonexistent_returns_none(db: ShoalDB):
    assert await db.reschedule_recurring_task(99999) is None
