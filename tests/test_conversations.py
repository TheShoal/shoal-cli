"""Tests for the canonical conversation event model."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from shoal.core.conversations import (
    claw_turn_to_event,
    generate_event_id,
    journal_entry_to_event,
    qmd_turn_to_event,
    render_event_as_journal_content,
    summary_to_event,
)
from shoal.core.journal import JournalEntry, append_entry, journal_path
from shoal.core.lobster_conversations import LobsterTurn
from shoal.core.qmd import event_to_qmd_turn, export_journal_to_qmd, read_qmd_turns


@pytest.fixture
def qmd_fixtures_dir() -> Path:
    """Return path to QMD test fixtures."""
    return Path(__file__).parent / "fixtures" / "qmd"


class TestGenerateEventId:
    """Test deterministic event id generation."""

    def test_is_deterministic_for_identical_inputs(self) -> None:
        timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        first = generate_event_id(
            kind="journal_entry",
            timestamp=timestamp,
            session_id="sess-123",
            source="manual",
            content_markdown="Operator note",
        )
        second = generate_event_id(
            kind="journal_entry",
            timestamp=timestamp,
            session_id="sess-123",
            source="manual",
            content_markdown="Operator note",
        )

        assert first == second

    def test_changes_when_payload_changes(self) -> None:
        timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        first = generate_event_id(
            kind="summary",
            timestamp=timestamp,
            session_id="sess-123",
            source="dreamer",
            summary="First summary",
        )
        second = generate_event_id(
            kind="summary",
            timestamp=timestamp,
            session_id="sess-123",
            source="dreamer",
            summary="Second summary",
        )

        assert first != second


class TestJournalEntryConversion:
    """Test conversion from journal entries into canonical events."""

    def test_generic_entry_preserves_markdown_without_fake_chat_fields(self) -> None:
        entry = JournalEntry(
            timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
            source="manual",
            content="Operator note\n\n- capture logs\n- restart worker",
        )

        event = journal_entry_to_event(entry, "sess-123", "alpha")

        assert event.kind == "journal_entry"
        assert event.content_markdown == entry.content
        assert event.prompt is None
        assert event.response is None
        assert event.summary is None

    def test_qmd_style_entry_parses_into_chat_turn(self) -> None:
        entry = JournalEntry(
            timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
            source="qmd-sync",
            content=(
                "**[claw:claude-sonnet-4 turn:evt-123]** What is Python?\n\n"
                "> Python is a programming language.\n\n"
                "(100 tokens, $0.0010)"
            ),
        )

        event = journal_entry_to_event(entry, "sess-123", "alpha")

        assert event.kind == "chat_turn"
        assert event.event_id == "evt-123"
        assert event.model == "claude-sonnet-4"
        assert event.prompt == "What is Python?"
        assert event.response == "Python is a programming language."
        assert event.tokens == 100
        assert event.cost_usd == pytest.approx(0.001)


class TestQmdRoundTrip:
    """Test QMD conversion against the canonical event model."""

    def test_generic_event_round_trips_without_fake_prompt_response(self) -> None:
        entry = JournalEntry(
            timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
            source="manual",
            content="A plain journal entry with no prompt/response split.",
        )

        event = journal_entry_to_event(entry, "sess-123", "alpha")
        turn = event_to_qmd_turn(event)
        restored = qmd_turn_to_event(turn, session_name="alpha")

        assert restored.kind == "journal_entry"
        assert restored.content_markdown == entry.content
        assert restored.prompt is None
        assert restored.response is None
        assert restored.metadata["kind"] == "journal_entry"
        assert render_event_as_journal_content(restored) == entry.content


class TestClawTurnConversion:
    """Test conversion from Lobster-compatible turns into canonical events."""

    def test_preserves_structured_fields_from_fixture(self, qmd_fixtures_dir: Path) -> None:
        record = json.loads((qmd_fixtures_dir / "2025-W03" / "turn-001.json").read_text())
        turn = LobsterTurn.from_json_record(record)

        event = claw_turn_to_event(turn, session_id="sess-123", session_name="alpha")

        assert event.kind == "chat_turn"
        assert event.session_id == "sess-123"
        assert event.metadata["claw_id"] == "claw-alpha"
        assert event.thinking == (
            "User is asking a simple geography question. Provide direct answer with context."
        )
        assert event.prompt_summary == "What is the capital of France?"
        assert event.response_summary == "The capital of France is Paris."
        assert event.prompt_tokens == 15
        assert event.response_tokens == 42
        assert event.cost_usd == pytest.approx(0.0003)


class TestSummaryEvent:
    """Test canonical summary event creation."""

    def test_summary_to_event_uses_summary_kind_and_metadata(self) -> None:
        event = summary_to_event(
            session_id="sess-123",
            session_name="alpha",
            source="dreamer",
            summary="Worker is blocked on MCP approval.",
            timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
            correlation_id="wf-123",
            tags=("summary", "dreamer"),
            metadata={"producer": "dreamer"},
        )

        assert event.kind == "summary"
        assert event.summary == "Worker is blocked on MCP approval."
        assert event.correlation_id == "wf-123"
        assert event.tags == ("summary", "dreamer")
        assert event.metadata["producer"] == "dreamer"
        assert event.prompt is None
        assert event.response is None


class TestQmdArtifactsDualPlane:
    """Test the markdown/body split for QMD artifacts."""

    def test_generic_entry_keeps_full_text_in_markdown_only(self, tmp_path: Path) -> None:
        session_id = "sess-dual-generic"
        content = "Operator note\n\n- capture logs\n- restart worker"

        with patch("shoal.core.journal.data_dir", return_value=tmp_path):
            append_entry(session_id, content, source="manual")
            output_dir = tmp_path / "qmd-export"
            exported = export_journal_to_qmd(
                journal_path(session_id),
                output_dir,
                session_id,
                "alpha",
            )

        assert exported == 1

        week_dir = next(output_dir.iterdir())
        json_file = next(week_dir.glob("*.json"))
        md_file = next(week_dir.glob("*.md"))

        record = json.loads(json_file.read_text())
        markdown = md_file.read_text()

        assert record["kind"] == "journal_entry"
        assert record["schema_version"] == 1
        assert record["body_markdown"] == md_file.name
        assert "prompt" not in record
        assert "response" not in record
        assert "content_markdown" not in record
        assert content not in json_file.read_text()
        assert "## Content" in markdown
        assert content in markdown

        turns = read_qmd_turns(output_dir, session_id=session_id)
        assert len(turns) == 1
        restored = qmd_turn_to_event(turns[0], session_name="alpha")
        assert restored.kind == "journal_entry"
        assert restored.content_markdown == content

    def test_chat_turn_keeps_full_prompt_and_response_in_markdown_only(
        self, tmp_path: Path
    ) -> None:
        session_id = "sess-dual-chat"
        content = (
            "**[claw:claude-sonnet-4 turn:evt-123]** Explain dual-plane storage.\n\n"
            "> Markdown carries full text while JSON stores structured metadata.\n\n"
            "(100 tokens, $0.0010)"
        )

        with patch("shoal.core.journal.data_dir", return_value=tmp_path):
            append_entry(session_id, content, source="qmd-sync")
            output_dir = tmp_path / "qmd-export"
            exported = export_journal_to_qmd(
                journal_path(session_id),
                output_dir,
                session_id,
                "alpha",
            )

        assert exported == 1

        week_dir = next(output_dir.iterdir())
        json_file = next(week_dir.glob("*.json"))
        md_file = next(week_dir.glob("*.md"))

        record = json.loads(json_file.read_text())
        markdown = md_file.read_text()

        assert record["kind"] == "chat_turn"
        assert record["event_id"] == "evt-123"
        assert "prompt" not in record
        assert "response" not in record
        assert "Explain dual-plane storage." not in json_file.read_text()
        assert (
            "Markdown carries full text while JSON stores structured metadata."
            not in json_file.read_text()
        )
        assert "## Prompt" in markdown
        assert "Explain dual-plane storage." in markdown
        assert "## Response" in markdown
        assert "Markdown carries full text while JSON stores structured metadata." in markdown

        turns = read_qmd_turns(output_dir, session_id=session_id)
        assert len(turns) == 1
        assert turns[0].prompt == "Explain dual-plane storage."
        assert (
            turns[0].response == "Markdown carries full text while JSON stores structured metadata."
        )
        restored = qmd_turn_to_event(turns[0], session_name="alpha")
        assert restored.kind == "chat_turn"
        assert restored.prompt == "Explain dual-plane storage."
        assert (
            restored.response == "Markdown carries full text while JSON stores structured metadata."
        )
