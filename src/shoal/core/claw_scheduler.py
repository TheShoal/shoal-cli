"""Claw scheduler — async tick loop for background and agent-scheduled tasks.

Inspired by lobster-party's fanout_scheduler.rs. Runs an asyncio loop that:
1. Ticks at a configurable interval
2. Claims one due task per cycle (fair scheduling)
3. Dispatches to a registered TaskHandler
4. Records the result (success, retryable failure, permanent failure)

The scheduler can be woken immediately via signal() when a new task is scheduled.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from shoal.models.claw import ClawTask, ClawTaskStatus, ClawTaskType, TaskResult

if TYPE_CHECKING:
    from shoal.core.db import ShoalDB

logger = logging.getLogger("shoal.claw_scheduler")


# ---------------------------------------------------------------------------
# TaskHandler protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class TaskHandler(Protocol):
    """Protocol for claw task handlers.

    Each handler receives a ClawTask and returns a TaskResult indicating
    success or failure mode.
    """

    async def __call__(self, task: ClawTask) -> TaskResult: ...


# ---------------------------------------------------------------------------
# ClawScheduler
# ---------------------------------------------------------------------------


class ClawScheduler:
    """Async scheduler that claims and executes due claw tasks.

    Fair scheduling: one task per tick cycle. The loop alternates between
    sleeping for tick_seconds and draining the signal event (for immediate
    wake on new task creation).

    Args:
        db: ShoalDB instance for task CRUD.
        handlers: Mapping of handler key to callable.
        tick_seconds: Interval between poll cycles.
    """

    def __init__(
        self,
        db: ShoalDB,
        handlers: dict[str, TaskHandler],
        tick_seconds: float = 5.0,
    ) -> None:
        self._db = db
        self._handlers = handlers
        self._tick_seconds = tick_seconds
        self._signal = asyncio.Event()
        self._running = False
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        """Whether the scheduler loop is active."""
        return self._running

    async def start(self) -> None:
        """Start the scheduler background task."""
        if self._running:
            logger.warning("Claw scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Claw scheduler started (tick=%.1fs, handlers=%s)",
            self._tick_seconds,
            list(self._handlers.keys()),
        )

    async def stop(self) -> None:
        """Graceful shutdown — cancel loop and wait for in-flight work."""
        self._running = False
        self._signal.set()  # Wake the loop so it can exit
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("Claw scheduler stopped")

    def signal(self) -> None:
        """Wake the scheduler immediately (e.g. after scheduling a new task)."""
        self._signal.set()

    # -----------------------------------------------------------------------
    # Internal loop
    # -----------------------------------------------------------------------

    async def _run_loop(self) -> None:
        """Main loop: sleep or wait for signal, then drain one task."""
        while self._running:
            try:
                # Wait for tick or signal, whichever comes first
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(
                        self._signal.wait(), timeout=self._tick_seconds
                    )
                self._signal.clear()

                if not self._running:
                    break

                await self._drain_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Claw scheduler cycle failed")

    async def _drain_once(self) -> None:
        """Claim one due task, execute its handler, record the result."""
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        due = await self._db.list_due_tasks(now, limit=1)
        if not due:
            return

        task_dict = due[0]
        task_id = int(task_dict["id"])  # type: ignore[arg-type]

        # CAS claim — another scheduler instance might beat us
        if not await self._db.claim_claw_task(task_id):
            return

        handler_key = str(task_dict["handler"])
        handler = self._handlers.get(handler_key)

        if handler is None:
            logger.error(
                "No handler registered for %r, dead-lettering task %d",
                handler_key, task_id,
            )
            await self._db.fail_claw_task(
                task_id, f"Unknown handler: {handler_key}", permanent=True
            )
            return

        # Build ClawTask model for the handler
        task = ClawTask(
            id=task_id,
            session=task_dict["session"],  # type: ignore[arg-type]
            task_type=ClawTaskType(str(task_dict["task_type"])),
            name=str(task_dict["name"]),
            handler=handler_key,
            cron_expr=task_dict["cron_expr"],  # type: ignore[arg-type]
            interval_seconds=task_dict["interval_seconds"],  # type: ignore[arg-type]
            payload_json=str(task_dict["payload_json"]),
            run_at=str(task_dict["run_at"]),
            status=ClawTaskStatus(str(task_dict["status"])),
            retry_count=int(task_dict["retry_count"]),  # type: ignore[arg-type]
            max_retries=int(task_dict["max_retries"]),  # type: ignore[arg-type]
            correlation_id=task_dict["correlation_id"],  # type: ignore[arg-type]
            created_at=str(task_dict["created_at"]),
            last_run_at=task_dict["last_run_at"],  # type: ignore[arg-type]
            completed_at=task_dict["completed_at"],  # type: ignore[arg-type]
            error=task_dict["error"],  # type: ignore[arg-type]
            metadata_json=task_dict["metadata_json"],  # type: ignore[arg-type]
        )

        try:
            result = await handler(task)
        except Exception as exc:
            logger.exception("Handler %r raised for task %d", handler_key, task_id)
            await self._db.fail_claw_task(task_id, str(exc))
            return

        match result:
            case TaskResult.succeeded:
                await self._db.complete_claw_task(task_id)
                logger.info("[claw] %s completed (task %d)", handler_key, task_id)
                # Reschedule if recurring
                if task.task_type in (ClawTaskType.recurring, ClawTaskType.cron):
                    new_id = await self._db.reschedule_recurring_task(task_id)
                    if new_id:
                        logger.info("[claw] %s rescheduled as task %d", handler_key, new_id)
            case TaskResult.retryable_failure:
                await self._db.fail_claw_task(task_id, task.error or "retryable failure")
                logger.warning("[claw] %s retryable failure (task %d)", handler_key, task_id)
            case TaskResult.permanent_failure:
                await self._db.fail_claw_task(
                    task_id, task.error or "permanent failure", permanent=True
                )
                logger.error("[claw] %s permanent failure (task %d)", handler_key, task_id)
