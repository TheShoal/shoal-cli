"""Claw scheduler bootstrap — initialize and start/stop the scheduler.

Call ``start_claw`` during application startup (e.g. lifecycle.py) and
``stop_claw`` during shutdown. The scheduler is only created when
``config.claw_scheduler.enabled`` is True.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shoal.core.claw_scheduler import ClawScheduler, TaskHandler
logger = logging.getLogger("shoal.claw_bootstrap")

# Module-level singleton
_scheduler: ClawScheduler | None = None


async def start_claw() -> ClawScheduler | None:
    """Initialize and start the claw scheduler if enabled in config.

    Returns:
        The running ClawScheduler, or None if disabled.
    """
    global _scheduler

    from shoal.core.config import load_config
    from shoal.core.db import get_db

    cfg = load_config()
    if not cfg.claw_scheduler.enabled:
        logger.debug("Claw scheduler disabled in config")
        return None

    from shoal.core.claw_scheduler import ClawScheduler

    db = await get_db()
    await db.connect()

    handlers = _build_handlers(cfg.claw_scheduler.summary_model)

    _scheduler = ClawScheduler(
        db=db,
        handlers=handlers,
        tick_seconds=cfg.claw_scheduler.tick_seconds,
    )
    await _scheduler.start()
    return _scheduler


async def stop_claw() -> None:
    """Stop the claw scheduler if running."""
    global _scheduler

    if _scheduler is not None:
        await _scheduler.stop()
        _scheduler = None


def get_claw_scheduler() -> ClawScheduler | None:
    """Return the running scheduler singleton, or None."""
    return _scheduler


def _build_handlers(summary_model: str) -> dict[str, TaskHandler]:
    """Construct the built-in handler registry.

    Args:
        summary_model: Model identifier for the summarizer.

    Returns:
        Dict mapping handler key to async callable.
    """
    from shoal.core.claw_summarizer import LLMSummarizer, StubSummarizer
    from shoal.models.claw import ClawTask, SummaryBudget, TaskResult

    summarizer = LLMSummarizer(model=summary_model)

    async def purge_messages(task: ClawTask) -> TaskResult:
        """Delete consumed messages older than the configured retention."""
        from shoal.core.db import get_db

        db = await get_db()
        await db.connect()

        import json

        payload = json.loads(task.payload_json) if task.payload_json else {}
        days = int(payload.get("days", 7))
        deleted = await db.purge_old_messages(older_than_seconds=days * 86_400)
        logger.info("[claw] purge_messages completed: %d messages removed", deleted)
        return TaskResult.succeeded

    async def summarize_journal(task: ClawTask) -> TaskResult:
        """Summarize recent journal entries for a session."""
        import json

        payload = json.loads(task.payload_json) if task.payload_json else {}
        session_id = payload.get("session_id", task.session)
        if not session_id:
            logger.warning("[claw] summarize_journal: no session_id in payload")
            return TaskResult.permanent_failure

        budget_str = payload.get("budget", "paragraph")
        budget = SummaryBudget(budget_str)

        try:
            from shoal.core.journal import append_entry, read_journal
            from shoal.core.qmd import persist_summary_event
            from shoal.core.state import get_session

            entries = await asyncio.to_thread(read_journal, session_id, limit=20)
            if not entries:
                return TaskResult.succeeded

            text = "\n".join(f"[{e.timestamp}] {e.content}" for e in entries)
            summary = await summarizer.summarize(text, budget, context=session_id)

            session_record = await get_session(session_id)
            session_name = session_record.name if session_record is not None else session_id

            await asyncio.to_thread(
                persist_summary_event,
                session_id=session_id,
                session_name=session_name,
                source="claw",
                summary=summary,
                tags=("summary", "claw"),
                metadata={
                    "producer": "claw",
                    "budget": budget.value,
                    "entry_count": len(entries),
                    "model": summary_model,
                },
            )
            await asyncio.to_thread(
                append_entry,
                session_id,
                f"[claw-summary] {summary}",
                source="claw",
            )
            logger.info("[claw] summarize_journal completed for %s", session_id)
            return TaskResult.succeeded
        except Exception as exc:
            logger.warning("[claw] summarize_journal failed: %s", exc)
            return TaskResult.retryable_failure

    async def summarize_workflow(task: ClawTask) -> TaskResult:
        """Summarize a workflow's message trace by correlation_id."""
        import json

        payload = json.loads(task.payload_json) if task.payload_json else {}
        corr_id = payload.get("correlation_id", task.correlation_id)
        if not corr_id:
            logger.warning("[claw] summarize_workflow: no correlation_id")
            return TaskResult.permanent_failure

        budget_str = payload.get("budget", "paragraph")
        budget = SummaryBudget(budget_str)

        try:
            from shoal.core.message_bus import get_workflow_messages, send_message
            from shoal.core.qmd import persist_summary_event
            from shoal.core.state import get_session

            messages = await get_workflow_messages(corr_id, limit=50)
            if not messages:
                return TaskResult.succeeded

            trace = "\n".join(
                f"[{m['created_at']}] {m['from_session']} -> {m['to_session']}: {m['payload']}"
                for m in messages
            )
            summary = await summarizer.summarize(trace, budget, context=corr_id)

            session_id = str(task.session or f"workflow:{corr_id}")
            session_name = session_id
            if task.session is not None:
                session_record = await get_session(task.session)
                if session_record is not None:
                    session_name = session_record.name

            await asyncio.to_thread(
                persist_summary_event,
                session_id=session_id,
                session_name=session_name,
                source="claw",
                summary=summary,
                kind="workflow_summary",
                correlation_id=corr_id,
                tags=("summary", "workflow", "claw"),
                metadata={
                    "producer": "claw",
                    "budget": budget.value,
                    "message_count": len(messages),
                    "model": summary_model,
                    "scope": "workflow",
                },
            )

            await send_message(
                from_session="__claw__",
                to_session="__claw__",
                topic="workflow_summary",
                payload=summary,
                kind="event",
                correlation_id=corr_id,
            )
            logger.info("[claw] summarize_workflow completed for %s", corr_id)
            return TaskResult.succeeded
        except Exception as exc:
            logger.warning("[claw] summarize_workflow failed: %s", exc)
            return TaskResult.retryable_failure

    # Use StubSummarizer reference to suppress unused-import if needed
    _ = StubSummarizer

    return {
        "purge_messages": purge_messages,
        "summarize_journal": summarize_journal,
        "summarize_workflow": summarize_workflow,
    }
