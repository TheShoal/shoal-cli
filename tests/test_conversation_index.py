"""Tests for src/shoal/core/conversation_index.py.

Covers:
- first ingest of an event
- re-ingest idempotency (no duplicate rows)
- session filter via recent_events
- workflow filter via workflow_events
- latest_summary returns newest summary for a session
- tag retrieval via conversation_tags
- rebuild from disk (ingest_from_disk)
- get_checkpoint set after disk ingest
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from shoal.core.conversation_index import ConversationIndex, get_index
from shoal.core.conversations import ConversationEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(
    *,
    session_id: str = "sess-1",
    session_name: str = "alpha",
    kind: str = "summary",
    source: str = "dreamer",
    summary: str = "All good.",
    correlation_id: str | None = None,
    tags: tuple[str, ...] = ("summary",),
    ts: datetime | None = None,
) -> ConversationEvent:
    from shoal.core.conversations import generate_event_id

    timestamp = ts or datetime(2026, 1, 3, 12, 0, 0, tzinfo=UTC)
    eid = generate_event_id(
        kind=kind,
        timestamp=timestamp,
        session_id=session_id,
        source=source,
        summary=summary,
    )
    return ConversationEvent(
        id=eid,
        timestamp=timestamp,
        session_id=session_id,
        session_name=session_name,
        source=source,
        kind=kind,
        summary=summary,
        correlation_id=correlation_id,
        tags=tags,
    )


@pytest.fixture
async def idx(tmp_path: Path) -> AsyncGenerator[ConversationIndex, None]:
    db_path = tmp_path / "test_index.db"
    instance = ConversationIndex(db_path)
    await instance.connect()
    yield instance
    await instance.close()


# ---------------------------------------------------------------------------
# Basic ingest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_ingest_returns_true(idx: ConversationIndex) -> None:
    ev = _event()
    inserted = await idx.ingest(ev)
    assert inserted is True


@pytest.mark.asyncio
async def test_reingest_is_idempotent(idx: ConversationIndex) -> None:
    ev = _event()
    await idx.ingest(ev)
    inserted_again = await idx.ingest(ev)
    assert inserted_again is False


@pytest.mark.asyncio
async def test_ingest_stores_all_fields(idx: ConversationIndex) -> None:
    ev = _event(
        session_id="sess-x",
        session_name="beta",
        kind="workflow_summary",
        source="claw",
        summary="Workflow complete.",
        correlation_id="wf-abc",
        tags=("summary", "workflow"),
    )
    await idx.ingest(ev)

    rows = await idx.recent_events(session_id="sess-x")
    assert len(rows) == 1
    row = rows[0]
    assert row["session_id"] == "sess-x"
    assert row["session_name"] == "beta"
    assert row["kind"] == "workflow_summary"
    assert row["source"] == "claw"
    assert row["summary"] == "Workflow complete."
    assert row["correlation_id"] == "wf-abc"


# ---------------------------------------------------------------------------
# recent_events filters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recent_events_session_filter(idx: ConversationIndex) -> None:
    await idx.ingest(_event(session_id="sess-a"))
    await idx.ingest(
        _event(
            session_id="sess-b",
            ts=datetime(2026, 1, 3, 13, 0, 0, tzinfo=UTC),
        )
    )

    rows = await idx.recent_events(session_id="sess-a")
    assert len(rows) == 1
    assert rows[0]["session_id"] == "sess-a"


@pytest.mark.asyncio
async def test_recent_events_kind_filter(idx: ConversationIndex) -> None:
    await idx.ingest(_event(kind="summary", source="dreamer"))
    await idx.ingest(
        _event(
            kind="workflow_summary",
            source="claw",
            ts=datetime(2026, 1, 3, 13, 0, 0, tzinfo=UTC),
        )
    )

    rows = await idx.recent_events(kind="summary")
    assert all(r["kind"] == "summary" for r in rows)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_recent_events_since_filter(idx: ConversationIndex) -> None:
    base = datetime(2026, 1, 3, 12, 0, 0, tzinfo=UTC)
    await idx.ingest(_event(ts=base))
    await idx.ingest(
        _event(
            session_id="sess-2",
            ts=base + timedelta(hours=2),
        )
    )

    rows = await idx.recent_events(since=base + timedelta(hours=1))
    assert len(rows) == 1
    assert rows[0]["session_id"] == "sess-2"


@pytest.mark.asyncio
async def test_recent_events_newest_first(idx: ConversationIndex) -> None:
    base = datetime(2026, 1, 3, 12, 0, 0, tzinfo=UTC)
    await idx.ingest(_event(session_id="sess-old", ts=base))
    await idx.ingest(
        _event(
            session_id="sess-new",
            ts=base + timedelta(hours=1),
        )
    )

    rows = await idx.recent_events()
    assert rows[0]["session_id"] == "sess-new"
    assert rows[1]["session_id"] == "sess-old"


# ---------------------------------------------------------------------------
# latest_summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_latest_summary_returns_newest(idx: ConversationIndex) -> None:
    base = datetime(2026, 1, 3, 12, 0, 0, tzinfo=UTC)
    await idx.ingest(_event(session_id="sess-1", summary="Old summary.", ts=base))
    await idx.ingest(
        _event(
            session_id="sess-1",
            summary="New summary.",
            ts=base + timedelta(minutes=30),
        )
    )

    row = await idx.latest_summary("sess-1")
    assert row is not None
    assert row["summary"] == "New summary."


@pytest.mark.asyncio
async def test_latest_summary_returns_none_when_empty(idx: ConversationIndex) -> None:
    result = await idx.latest_summary("no-such-session")
    assert result is None


# ---------------------------------------------------------------------------
# workflow_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_events_correlation_filter(idx: ConversationIndex) -> None:
    await idx.ingest(_event(correlation_id="wf-1", kind="workflow_summary", source="claw"))
    await idx.ingest(
        _event(
            correlation_id="wf-2",
            kind="workflow_summary",
            source="claw",
            ts=datetime(2026, 1, 3, 13, 0, 0, tzinfo=UTC),
        )
    )

    rows = await idx.workflow_events("wf-1")
    assert len(rows) == 1
    assert rows[0]["correlation_id"] == "wf-1"


# ---------------------------------------------------------------------------
# tags_for_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tags_for_event(idx: ConversationIndex) -> None:
    ev = _event(tags=("summary", "dreamer", "session"))
    await idx.ingest(ev)

    tags = await idx.tags_for_event(ev.id)
    assert sorted(tags) == ["dreamer", "session", "summary"]


@pytest.mark.asyncio
async def test_tags_for_event_empty(idx: ConversationIndex) -> None:
    ev = _event(tags=())
    await idx.ingest(ev)

    tags = await idx.tags_for_event(ev.id)
    assert tags == []


# ---------------------------------------------------------------------------
# ingest_from_disk (rebuild)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_from_disk(tmp_path: Path) -> None:
    """Events written to disk via persist_summary_event are picked up by ingest_from_disk."""
    db_path = tmp_path / "idx.db"
    instance = ConversationIndex(db_path)
    await instance.connect()

    with patch("shoal.core.qmd.data_dir", return_value=tmp_path):
        from shoal.core.qmd import persist_summary_event

        persist_summary_event(
            session_id="sess-disk",
            session_name="disk-session",
            source="dreamer",
            summary="Disk-persisted summary.",
            tags=("summary", "dreamer"),
        )

        count = await instance.ingest_from_disk(tmp_path / "conversations")

    assert count == 1
    rows = await instance.recent_events(session_id="sess-disk", kind="summary")
    assert len(rows) == 1
    assert rows[0]["summary"] == "Disk-persisted summary."

    await instance.close()


@pytest.mark.asyncio
async def test_ingest_from_disk_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "idx.db"
    instance = ConversationIndex(db_path)
    await instance.connect()

    with patch("shoal.core.qmd.data_dir", return_value=tmp_path):
        from shoal.core.qmd import persist_summary_event

        persist_summary_event(
            session_id="sess-disk2",
            session_name="idempotent",
            source="claw",
            summary="Once only.",
        )

        first = await instance.ingest_from_disk(tmp_path / "conversations")
        second = await instance.ingest_from_disk(tmp_path / "conversations")

    assert first == 1
    assert second == 0  # already indexed

    await instance.close()


@pytest.mark.asyncio
async def test_ingest_from_disk_nonexistent_dir(tmp_path: Path) -> None:
    db_path = tmp_path / "idx.db"
    instance = ConversationIndex(db_path)
    await instance.connect()

    count = await instance.ingest_from_disk(tmp_path / "nonexistent")
    assert count == 0

    await instance.close()


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checkpoint_set_after_disk_ingest(tmp_path: Path) -> None:
    db_path = tmp_path / "idx.db"
    instance = ConversationIndex(db_path)
    await instance.connect()

    conversations_dir = tmp_path / "conversations"
    with patch("shoal.core.qmd.data_dir", return_value=tmp_path):
        from shoal.core.qmd import persist_summary_event

        persist_summary_event(
            session_id="sess-cp",
            session_name="cp-session",
            source="dreamer",
            summary="Checkpoint test.",
        )
        await instance.ingest_from_disk(conversations_dir)

    checkpoint = await instance.get_checkpoint(conversations_dir)
    assert checkpoint is not None
    assert "ingested_at" in checkpoint

    await instance.close()


# ---------------------------------------------------------------------------
# get_index singleton helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_index_returns_connected_singleton(tmp_path: Path) -> None:
    await ConversationIndex.reset_instance()
    try:
        idx1 = await get_index(db_path=tmp_path / "s.db")
        idx2 = await get_index(db_path=tmp_path / "s.db")
        assert idx1 is idx2
    finally:
        await ConversationIndex.reset_instance()
