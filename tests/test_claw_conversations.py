"""Tests for Claw conversation import/export with QMD format."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from shoal.core.claw_conversations import (
    ClawTurn,
    _get_iso_week_dir,
    _parse_iso_week_dir,
    export_journal_to_qmd,
    read_qmd_turns,
    turns_to_journal_entries,
)
from shoal.core.journal import append_entry, journal_path


@pytest.fixture
def qmd_fixtures_dir() -> Path:
    """Return path to QMD test fixtures."""
    return Path(__file__).parent / "fixtures" / "qmd"


@pytest.fixture
def temp_conversations_dir(tmp_path: Path) -> Path:
    """Create a temporary conversations directory structure."""
    conv_dir = tmp_path / "conversations"
    conv_dir.mkdir()
    return conv_dir


class TestClawTurn:
    """Test ClawTurn dataclass and parsing."""

    def test_from_json_record_basic(self, qmd_fixtures_dir: Path) -> None:
        """Test parsing a basic QMD JSON turn record."""
        json_file = qmd_fixtures_dir / "2025-W03" / "turn-001.json"
        record = json.loads(json_file.read_text())

        turn = ClawTurn.from_json_record(record)

        assert turn.id == "turn-001"
        assert turn.claw_id == "claw-alpha"
        assert turn.event_id == "evt-12345"
        assert turn.prompt == "What is the capital of France?"
        assert "Paris" in turn.response
        assert turn.model == "claude-sonnet-4-20250514"
        assert turn.tokens == 57  # 15 + 42
        assert abs(turn.cost_usd - 0.0003) < 0.0001

    def test_from_json_record_unix_timestamp(self) -> None:
        """Test parsing with Unix timestamp instead of ISO string."""
        record = {
            "id": "turn-unix",
            "timestamp": 1737000000,  # Unix timestamp
            "claw_id": "claw-test",
            "event_id": "evt-001",
            "prompt": "Test prompt",
            "response": "Test response",
            "model": "test-model",
            "tokens": 100,
            "cost_usd": 0.001,
        }

        turn = ClawTurn.from_json_record(record)

        assert turn.id == "turn-unix"
        assert turn.timestamp.tzinfo is not None  # Should be UTC

    def test_from_json_record_separate_tokens(self) -> None:
        """Test token calculation from separate prompt/response counts."""
        record = {
            "id": "turn-tokens",
            "timestamp": "2025-01-15T10:00:00Z",
            "claw_id": "claw-test",
            "event_id": "evt-001",
            "prompt": "Test",
            "response": "Response",
            "model": "test",
            "prompt_tokens": 25,
            "response_tokens": 75,
            "cost_usd": 0.0005,
        }

        turn = ClawTurn.from_json_record(record)

        assert turn.tokens == 100  # 25 + 75

    def test_from_json_record_missing_tokens(self) -> None:
        """Test handling when token counts are missing."""
        record = {
            "id": "turn-no-tokens",
            "timestamp": "2025-01-15T10:00:00Z",
            "claw_id": "claw-test",
            "event_id": "evt-001",
            "prompt": "Test",
            "response": "Response",
            "model": "test",
            "cost_usd": 0.0005,
        }

        turn = ClawTurn.from_json_record(record)

        assert turn.tokens is None


class TestParseIsoWeek:
    """Test ISO week directory parsing."""

    def test_valid_week_dir(self) -> None:
        """Test parsing valid week directory name."""
        assert _parse_iso_week_dir("2025-W03") == (2025, 3)
        assert _parse_iso_week_dir("2024-W52") == (2024, 52)
        assert _parse_iso_week_dir("2025-W01") == (2025, 1)

    def test_invalid_week_dir(self) -> None:
        """Test parsing invalid directory names."""
        assert _parse_iso_week_dir("2025-03") is None
        assert _parse_iso_week_dir("W03-2025") is None
        assert _parse_iso_week_dir("2025-W3") is None  # Needs leading zero
        assert _parse_iso_week_dir("invalid") is None


class TestGetIsoWeekDir:
    """Test ISO week directory generation."""

    def test_get_week_for_date(self) -> None:
        """Test generating week directory from datetime."""
        # January 15, 2025 is in week 3
        dt = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        assert _get_iso_week_dir(dt) == "2025-W03"

        # January 1, 2025 is in week 1
        dt = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        assert _get_iso_week_dir(dt) == "2025-W01"


class TestReadQmdTurns:
    """Test reading QMD turn files."""

    def test_read_fixture_turns(self, qmd_fixtures_dir: Path) -> None:
        """Test reading turns from fixture directory."""
        turns = read_qmd_turns(qmd_fixtures_dir)

        assert len(turns) == 2
        assert turns[0].id == "turn-001"
        assert turns[1].id == "turn-002"
        # Should be sorted by timestamp
        assert turns[0].timestamp < turns[1].timestamp

    def test_read_with_since_filter(self, qmd_fixtures_dir: Path) -> None:
        """Test filtering turns by since timestamp."""
        # Filter to only turns after Jan 15, 2025 12:00
        since = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        turns = read_qmd_turns(qmd_fixtures_dir, since=since)

        assert len(turns) == 1
        assert turns[0].id == "turn-002"

    def test_read_empty_directory(self, temp_conversations_dir: Path) -> None:
        """Test reading from empty directory."""
        turns = read_qmd_turns(temp_conversations_dir)
        assert turns == []

    def test_read_nonexistent_directory(self, tmp_path: Path) -> None:
        """Test reading from non-existent directory."""
        nonexistent = tmp_path / "does_not_exist"
        turns = read_qmd_turns(nonexistent)
        assert turns == []

    def test_read_with_invalid_json(self, temp_conversations_dir: Path) -> None:
        """Test handling of invalid JSON files."""
        week_dir = temp_conversations_dir / "2025-W03"
        week_dir.mkdir()

        # Write invalid JSON
        (week_dir / "bad.json").write_text("not valid json {")

        # Should not raise, just log warning and return empty
        turns = read_qmd_turns(temp_conversations_dir)
        assert turns == []


class TestTurnsToJournalEntries:
    """Test conversion of turns to journal markdown."""

    def test_convert_single_turn(self, qmd_fixtures_dir: Path) -> None:
        """Test converting a single turn to journal entry."""
        json_file = qmd_fixtures_dir / "2025-W03" / "turn-001.json"
        record = json.loads(json_file.read_text())
        turn = ClawTurn.from_json_record(record)

        md = turns_to_journal_entries([turn])

        assert "## 2025-01-15T10:30:00+00:00 — claw-sync" in md
        assert "**[claw:claw-alpha turn:evt-12345]**" in md
        assert "What is the capital of France?" in md
        assert "57 tokens" in md
        assert "$0.0003" in md

    def test_convert_multiple_turns(self, qmd_fixtures_dir: Path) -> None:
        """Test converting multiple turns."""
        turns = read_qmd_turns(qmd_fixtures_dir)
        md = turns_to_journal_entries(turns)

        # Should have two entries
        assert md.count("## ") == 2
        assert "turn-001" in md or "evt-12345" in md
        assert "turn-002" in md or "evt-67890" in md

    def test_convert_with_truncation(self) -> None:
        """Test that long prompts/responses are truncated."""
        turn = ClawTurn(
            id="turn-long",
            timestamp=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
            claw_id="claw-test",
            event_id="evt-001",
            prompt="x" * 500,  # Very long prompt
            response="y" * 500,  # Very long response
            model="test",
            tokens=100,
            cost_usd=0.001,
        )

        md = turns_to_journal_entries([turn])

        # Should be truncated to 200 chars + ...
        assert "x" * 200 + "..." in md
        assert "y" * 200 + "..." in md

    def test_convert_without_metadata(self) -> None:
        """Test conversion when tokens/cost are None."""
        turn = ClawTurn(
            id="turn-no-meta",
            timestamp=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
            claw_id="claw-test",
            event_id="evt-001",
            prompt="Test",
            response="Response",
            model="test",
            tokens=None,
            cost_usd=None,
        )

        md = turns_to_journal_entries([turn])

        # Should not have empty metadata
        assert "()" not in md


class TestExportJournalToQmd:
    """Test exporting journal entries to QMD format."""

    def test_export_claw_sync_entries(self, tmp_path: Path) -> None:
        """Test exporting claw-sync journal entries."""
        session_id = "test-session-export"

        # Mock data_dir to use temp directory
        with patch("shoal.core.journal.data_dir", return_value=tmp_path):
            from shoal.core.journal import append_entry, journal_path

            # Create journal entry (inside patch context so path is correct)
            entry_content = """**[claw:claw-test turn:evt-001]** What is Python?
> Python is a programming language.
(100 tokens, $0.0010)"""
            append_entry(session_id, entry_content, source="claw-sync")

            # Export to QMD
            journal_file = journal_path(session_id)
            output_dir = tmp_path / "qmd-export"
            count = export_journal_to_qmd(journal_file, output_dir, "test-session")

            assert count == 1

            # Check that files were created (week dir based on current date)
            week_dir = output_dir / "2026-W14"
            assert week_dir.exists()

            json_files = list(week_dir.glob("*.json"))
            md_files = list(week_dir.glob("*.md"))
            assert len(json_files) == 1
            assert len(md_files) == 1

            # Verify JSON content
            json_data = json.loads(json_files[0].read_text())
            assert json_data["claw_id"] == "claw-test"
            assert json_data["event_id"] == "evt-001"

    def test_export_nonexistent_journal(self, tmp_path: Path) -> None:
        """Test exporting non-existent journal."""
        journal_file = tmp_path / "nonexistent.md"
        output_dir = tmp_path / "output"

        count = export_journal_to_qmd(journal_file, output_dir, "test")
        assert count == 0

    def test_export_no_claw_entries(self, tmp_path: Path) -> None:
        """Test exporting journal with no claw-sync entries."""
        session_id = "test-no-claw"
        journal_file = journal_path(session_id)

        with patch("shoal.core.journal.data_dir", return_value=tmp_path):
            # Add non-claw entry
            append_entry(session_id, "Regular entry", source="manual")

            output_dir = tmp_path / "output"
            count = export_journal_to_qmd(journal_file, output_dir, "test")

            assert count == 0
