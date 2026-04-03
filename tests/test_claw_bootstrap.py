import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from shoal.core.journal import append_entry, read_journal
from shoal.core.qmd import read_qmd_events
from shoal.models.claw import ClawTask, ClawTaskStatus, ClawTaskType, TaskResult
from shoal.services.claw_bootstrap import _build_handlers


def _build_task(
    *,
    name: str,
    handler: str,
    session: str | None = None,
    correlation_id: str | None = None,
    payload: dict[str, object] | None = None,
) -> ClawTask:
    return ClawTask(
        id=1,
        session=session,
        task_type=ClawTaskType.once,
        name=name,
        handler=handler,
        payload_json=json.dumps(payload or {}),
        run_at="2026-04-03T00:00:00+00:00",
        status=ClawTaskStatus.pending,
        retry_count=0,
        max_retries=3,
        correlation_id=correlation_id,
        created_at="2026-04-03T00:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_summarize_journal_persists_structured_summary(tmp_path: Path) -> None:
    handlers = _build_handlers("amazon.nova-lite-v1:0")
    handler = cast(Callable[[ClawTask], Awaitable[TaskResult]], handlers["summarize_journal"])

    with (
        patch("shoal.core.journal.data_dir", return_value=tmp_path),
        patch("shoal.core.qmd.data_dir", return_value=tmp_path),
        patch(
            "shoal.core.claw_summarizer.LLMSummarizer.summarize",
            new_callable=AsyncMock,
        ) as mock_summarize,
        patch(
            "shoal.core.state.get_session",
            new=AsyncMock(return_value=SimpleNamespace(name="alpha")),
        ),
    ):
        _ = append_entry("sess-1", "Implemented parser retry handling", source="agent")
        mock_summarize.return_value = "Session is stabilizing after the parser fix."

        result = await handler(
            _build_task(name="journal-summary", handler="summarize_journal", session="sess-1")
        )

        assert result == TaskResult.succeeded

        entries = read_journal("sess-1", limit=20)
        assert entries[-1].source == "claw"
        assert entries[-1].content == "[claw-summary] Session is stabilizing after the parser fix."

        events = read_qmd_events(session_id="sess-1", kind="summary", source="claw")
        assert len(events) == 1
        event = events[0]
        assert event.summary == "Session is stabilizing after the parser fix."
        assert event.session_name == "alpha"
        assert event.tags == ("summary", "claw")
        assert event.metadata["producer"] == "claw"
        assert event.metadata["budget"] == "paragraph"
        assert event.metadata["entry_count"] == 1
        assert event.metadata["model"] == "amazon.nova-lite-v1:0"


@pytest.mark.asyncio
async def test_summarize_workflow_persists_structured_summary_and_bus_message(
    tmp_path: Path,
) -> None:
    handlers = _build_handlers("amazon.nova-lite-v1:0")
    handler = cast(
        Callable[[ClawTask], Awaitable[TaskResult]],
        handlers["summarize_workflow"],
    )
    messages = [
        {
            "created_at": "2026-04-03T00:00:00+00:00",
            "from_session": "alpha",
            "to_session": "beta",
            "payload": "Need approval for deploy.",
        },
        {
            "created_at": "2026-04-03T00:01:00+00:00",
            "from_session": "beta",
            "to_session": "alpha",
            "payload": "Approval granted.",
        },
    ]

    with (
        patch("shoal.core.qmd.data_dir", return_value=tmp_path),
        patch(
            "shoal.core.claw_summarizer.LLMSummarizer.summarize",
            new_callable=AsyncMock,
        ) as mock_summarize,
        patch(
            "shoal.core.message_bus.get_workflow_messages",
            new=AsyncMock(return_value=messages),
        ),
        patch("shoal.core.message_bus.send_message", new_callable=AsyncMock) as mock_send,
        patch(
            "shoal.core.state.get_session",
            new=AsyncMock(return_value=SimpleNamespace(name="alpha")),
        ),
    ):
        mock_summarize.return_value = "Workflow reached approval and is ready to proceed."

        result = await handler(
            _build_task(
                name="workflow-summary",
                handler="summarize_workflow",
                session="sess-1",
                correlation_id="wf-123",
            )
        )

        assert result == TaskResult.succeeded
        mock_send.assert_awaited_once_with(
            from_session="__claw__",
            to_session="__claw__",
            topic="workflow_summary",
            payload="Workflow reached approval and is ready to proceed.",
            kind="event",
            correlation_id="wf-123",
        )

        events = read_qmd_events(
            session_id="sess-1",
            kind="workflow_summary",
            correlation_id="wf-123",
            source="claw",
        )
        assert len(events) == 1
        event = events[0]
        assert event.summary == "Workflow reached approval and is ready to proceed."
        assert event.session_name == "alpha"
        assert event.correlation_id == "wf-123"
        assert event.tags == ("summary", "workflow", "claw")
        assert event.metadata["producer"] == "claw"
        assert event.metadata["budget"] == "paragraph"
        assert event.metadata["message_count"] == 2
        assert event.metadata["model"] == "amazon.nova-lite-v1:0"
        assert event.metadata["scope"] == "workflow"
