"""Tests for structured session journals (core, CLI, MCP)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from shoal.core.journal import (
    _parse_journal,
    append_entry,
    archive_journal,
    archived_journal_path,
    delete_journal,
    journal_exists,
    journal_path,
    read_journal,
)


@pytest.fixture()
def journals_dir(tmp_path: Path) -> Path:
    """Create a temporary journals directory and patch state_dir."""
    jdir = tmp_path / "journals"
    jdir.mkdir()
    with patch("shoal.core.journal.state_dir", return_value=tmp_path):
        yield jdir


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


class TestCoreJournal:
    """Test core journal operations."""

    def test_append_creates_file(self, journals_dir: Path) -> None:
        path = append_entry("sess-1", "hello world", source="test")
        assert path.exists()
        assert "hello world" in path.read_text()

    def test_append_multiple_entries(self, journals_dir: Path) -> None:
        append_entry("sess-2", "first", source="a")
        append_entry("sess-2", "second", source="b")
        entries = read_journal("sess-2")
        assert len(entries) == 2
        assert entries[0].content == "first"
        assert entries[1].content == "second"

    def test_read_with_limit(self, journals_dir: Path) -> None:
        for i in range(5):
            append_entry("sess-3", f"entry {i}", source="test")
        entries = read_journal("sess-3", limit=2)
        assert len(entries) == 2
        assert entries[0].content == "entry 3"
        assert entries[1].content == "entry 4"

    def test_read_empty_journal(self, journals_dir: Path) -> None:
        entries = read_journal("nonexistent")
        assert entries == []

    def test_journal_exists(self, journals_dir: Path) -> None:
        assert not journal_exists("sess-x")
        append_entry("sess-x", "test")
        assert journal_exists("sess-x")

    def test_delete_journal(self, journals_dir: Path) -> None:
        append_entry("sess-del", "test")
        assert delete_journal("sess-del") is True
        assert not journal_exists("sess-del")
        assert delete_journal("sess-del") is False

    def test_journal_path(self, journals_dir: Path) -> None:
        path = journal_path("my-session")
        assert path.name == "my-session.md"

    def test_entry_has_timestamp(self, journals_dir: Path) -> None:
        append_entry("sess-ts", "timestamped", source="test")
        entries = read_journal("sess-ts")
        assert len(entries) == 1
        assert entries[0].timestamp.tzinfo is not None
        assert entries[0].source == "test"

    def test_archive_journal(self, journals_dir: Path) -> None:
        append_entry("sess-arch", "content", source="test")
        assert archive_journal("sess-arch") is True
        assert not journal_exists("sess-arch")
        archived = journals_dir / "archive" / "sess-arch.md"
        assert archived.exists()
        assert "content" in archived.read_text()

    def test_archive_nonexistent_journal(self, journals_dir: Path) -> None:
        assert archive_journal("nonexistent") is False

    def test_archive_creates_directory(self, journals_dir: Path) -> None:
        append_entry("sess-first", "first archive")
        archive_dir = journals_dir / "archive"
        assert not archive_dir.exists()
        archive_journal("sess-first")
        assert archive_dir.exists()

    def test_archived_journal_path(self, journals_dir: Path) -> None:
        path = archived_journal_path("my-session")
        assert path.name == "my-session.md"
        assert "archive" in str(path)


class TestParseJournal:
    """Test the markdown parser."""

    def test_parse_single_entry(self) -> None:
        text = "## 2026-02-23T12:00:00+00:00 [cli]\n\nhello world\n\n---\n\n"
        entries = _parse_journal(text)
        assert len(entries) == 1
        assert entries[0].content == "hello world"
        assert entries[0].source == "cli"
        assert entries[0].timestamp == datetime(2026, 2, 23, 12, 0, 0, tzinfo=UTC)

    def test_parse_empty_source(self) -> None:
        text = "## 2026-02-23T12:00:00+00:00 []\n\ncontent here\n\n---\n\n"
        entries = _parse_journal(text)
        assert len(entries) == 1
        assert entries[0].source == ""

    def test_parse_multiline_content(self) -> None:
        text = "## 2026-02-23T12:00:00+00:00 [test]\n\nline 1\nline 2\nline 3\n\n---\n\n"
        entries = _parse_journal(text)
        assert len(entries) == 1
        assert entries[0].content == "line 1\nline 2\nline 3"

    def test_parse_empty_text(self) -> None:
        assert _parse_journal("") == []


class TestJournalCLI:
    """Test the journal CLI command."""

    def test_view_no_session(self, runner: CliRunner, mock_dirs: object) -> None:
        from shoal.cli import app

        result = runner.invoke(app, ["journal", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_view_no_journal(self, runner: CliRunner, mock_dirs: object) -> None:
        from shoal.cli import app

        async def mock_resolve(name: str) -> str:
            return "sess-id-1"

        with (
            patch("shoal.cli.journal.resolve_session", side_effect=mock_resolve),
            patch("shoal.cli.journal.journal_exists", return_value=False),
        ):
            result = runner.invoke(app, ["journal", "my-sess"])
        assert result.exit_code == 0
        assert "No journal" in result.output

    def test_append_via_cli(self, runner: CliRunner, mock_dirs: object) -> None:
        from shoal.cli import app

        async def mock_resolve(name: str) -> str:
            return "sess-id-2"

        with (
            patch("shoal.cli.journal.resolve_session", side_effect=mock_resolve),
            patch("shoal.cli.journal.append_entry") as mock_append,
        ):
            mock_append.return_value = Path("/tmp/sess-id-2.md")
            result = runner.invoke(app, ["journal", "my-sess", "--append", "test entry"])
        assert result.exit_code == 0
        assert "appended" in result.output
        mock_append.assert_called_once_with("sess-id-2", "test entry", source="cli")


class TestJournalMCP:
    """Test MCP journal tools."""

    def test_append_journal_tool(self, mock_dirs: object) -> None:
        from shoal.services.mcp_shoal_server import append_journal_tool

        with (
            patch(
                "shoal.core.state.resolve_session",
                new_callable=AsyncMock,
                return_value="sess-mcp-1",
            ),
            patch("shoal.core.journal.append_entry", return_value=Path("/tmp/sess-mcp-1.md")),
        ):
            result = asyncio.run(append_journal_tool("my-sess", "mcp entry", "mcp"))
        assert "appended" in result["message"]

    def test_read_journal_tool(self, mock_dirs: object) -> None:
        from shoal.core.journal import JournalEntry
        from shoal.services.mcp_shoal_server import read_journal_tool

        entries = [
            JournalEntry(
                timestamp=datetime(2026, 2, 23, 12, 0, 0, tzinfo=UTC),
                source="test",
                content="hello",
            )
        ]
        with (
            patch(
                "shoal.core.state.resolve_session",
                new_callable=AsyncMock,
                return_value="sess-mcp-2",
            ),
            patch("shoal.core.journal.read_journal", return_value=entries),
        ):
            result = asyncio.run(read_journal_tool("my-sess", limit=10))
        assert len(result) == 1
        assert result[0]["content"] == "hello"

    def test_append_journal_session_not_found(self, mock_dirs: object) -> None:
        from fastmcp.exceptions import ToolError

        from shoal.services.mcp_shoal_server import append_journal_tool

        with (
            patch(
                "shoal.core.state.resolve_session",
                new_callable=AsyncMock,
                return_value=None,
            ),
            pytest.raises(ToolError, match="not found"),
        ):
            asyncio.run(append_journal_tool("nope", "entry"))
