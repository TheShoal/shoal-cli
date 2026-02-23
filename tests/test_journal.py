"""Tests for structured session journals (core, CLI, MCP)."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from shoal.core.journal import (
    MAX_JOURNAL_SIZE_BYTES,
    JournalMetadata,
    _parse_journal,
    _render_frontmatter,
    _sanitize_tag,
    _strip_frontmatter,
    append_entry,
    archive_journal,
    archived_journal_path,
    build_journal_metadata,
    delete_journal,
    journal_exists,
    journal_path,
    read_frontmatter,
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

    def test_parse_with_frontmatter(self) -> None:
        """Frontmatter is stripped before parsing entries."""
        text = (
            "---\nsession_id: abc\ntitle: test\n---\n"
            "## 2026-02-23T12:00:00+00:00 [cli]\n\nhello\n\n---\n\n"
        )
        entries = _parse_journal(text)
        assert len(entries) == 1
        assert entries[0].content == "hello"


class TestFrontmatter:
    """Test YAML frontmatter rendering and parsing."""

    def test_render_frontmatter_basic(self) -> None:
        meta = JournalMetadata(
            session_id="abc123",
            session_name="feature-auth",
            tool="claude",
            branch="feature-auth",
        )
        fm = _render_frontmatter(meta)
        assert fm.startswith("---\n")
        assert fm.endswith("---\n")
        assert "session_id: abc123" in fm
        assert "title: feature-auth" in fm
        assert "aliases: [feature-auth]" in fm
        assert "tool: claude" in fm
        assert "branch: feature-auth" in fm
        assert "tags: [shoal, feature-auth, claude]" in fm

    def test_render_frontmatter_minimal(self) -> None:
        meta = JournalMetadata(session_id="x", session_name="test")
        fm = _render_frontmatter(meta)
        assert "session_id: x" in fm
        assert "title: test" in fm
        # No tool/branch/worktree lines when empty
        assert "tool:" not in fm
        assert "branch:" not in fm

    def test_render_frontmatter_has_created(self) -> None:
        meta = JournalMetadata(session_id="x", session_name="test")
        fm = _render_frontmatter(meta)
        assert "created: 20" in fm

    def test_sanitize_tag(self) -> None:
        assert _sanitize_tag("Feature-Auth") == "feature-auth"
        assert _sanitize_tag("my session!") == "my-session"
        assert _sanitize_tag("  spaces  ") == "spaces"
        assert _sanitize_tag("") == ""

    def test_strip_frontmatter(self) -> None:
        text = "---\nkey: value\n---\nrest of content"
        assert _strip_frontmatter(text) == "rest of content"

    def test_strip_frontmatter_absent(self) -> None:
        text = "no frontmatter here"
        assert _strip_frontmatter(text) == text

    def test_build_journal_metadata(self) -> None:
        session = SimpleNamespace(
            id="abc",
            name="my-sess",
            tool="claude",
            branch="feat",
            worktree="/wt",
            path="/repo",
        )
        meta = build_journal_metadata(session)
        assert meta.session_id == "abc"
        assert meta.session_name == "my-sess"
        assert meta.tool == "claude"
        assert meta.branch == "feat"
        assert meta.worktree == "/wt"
        assert meta.git_root == "/repo"
        assert meta.hostname != ""
        assert meta.platform_name != ""
        assert meta.python_version != ""
        assert meta.shoal_version != ""

    def test_read_frontmatter(self, journals_dir: Path) -> None:
        meta = JournalMetadata(
            session_id="fm-read",
            session_name="test-session",
            tool="claude",
        )
        append_entry("fm-read", "hello", source="test", metadata=meta)
        fm = read_frontmatter("fm-read")
        assert fm is not None
        assert fm["session_id"] == "fm-read"
        assert fm["title"] == "test-session"
        assert fm["tool"] == "claude"

    def test_read_frontmatter_absent(self, journals_dir: Path) -> None:
        append_entry("fm-none", "hello", source="test")
        fm = read_frontmatter("fm-none")
        assert fm is None

    def test_read_frontmatter_no_file(self, journals_dir: Path) -> None:
        assert read_frontmatter("nonexistent") is None

    def test_append_writes_frontmatter_on_new_file(self, journals_dir: Path) -> None:
        meta = JournalMetadata(session_id="new-fm", session_name="test")
        append_entry("new-fm", "content", source="test", metadata=meta)
        text = journal_path("new-fm").read_text()
        assert text.startswith("---\n")
        entries = read_journal("new-fm")
        assert len(entries) == 1
        assert entries[0].content == "content"

    def test_append_skips_frontmatter_on_existing_file(self, journals_dir: Path) -> None:
        """Second append should NOT add frontmatter even if metadata is passed."""
        meta = JournalMetadata(session_id="exist-fm", session_name="test")
        append_entry("exist-fm", "first", source="a", metadata=meta)
        append_entry("exist-fm", "second", source="b", metadata=meta)
        text = journal_path("exist-fm").read_text()
        # Only one frontmatter block
        assert text.count("---\nsession_id:") == 1
        entries = read_journal("exist-fm")
        assert len(entries) == 2

    def test_read_journal_with_frontmatter(self, journals_dir: Path) -> None:
        """read_journal works on files with frontmatter."""
        meta = JournalMetadata(session_id="rj-fm", session_name="test")
        append_entry("rj-fm", "entry one", source="a", metadata=meta)
        append_entry("rj-fm", "entry two", source="b")
        entries = read_journal("rj-fm")
        assert len(entries) == 2
        assert entries[0].content == "entry one"
        assert entries[1].content == "entry two"


class TestSizeWarning:
    """Test advisory size warning on large journals."""

    def test_size_warning_logged(
        self, journals_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Warning is logged when journal exceeds size threshold."""
        # Write a large entry that exceeds MAX_JOURNAL_SIZE_BYTES
        big_content = "x" * (MAX_JOURNAL_SIZE_BYTES + 100)
        with caplog.at_level(logging.WARNING, logger="shoal.journal"):
            append_entry("big-sess", big_content, source="test")
        assert "exceeds" in caplog.text

    def test_no_warning_for_small_journal(
        self, journals_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="shoal.journal"):
            append_entry("small-sess", "tiny", source="test")
        assert "exceeds" not in caplog.text


class TestPruneArchiveAsync:
    """Test that prune uses asyncio.to_thread for archive_journal."""

    def test_prune_calls_archive_via_to_thread(self, mock_dirs: object) -> None:
        """Verify archive_journal is called via asyncio.to_thread in prune."""
        from shoal.cli.session import _prune_impl
        from shoal.models.state import SessionState, SessionStatus

        stopped_session = SessionState(
            id="prune-1",
            name="stopped-sess",
            tool="claude",
            path="/tmp/repo",
            tmux_session="shoal_stopped-sess",
            status=SessionStatus.stopped,
        )

        with (
            patch(
                "shoal.cli.session.list_sessions",
                new_callable=AsyncMock,
                return_value=[stopped_session],
            ),
            patch(
                "shoal.cli.session.delete_session",
                new_callable=AsyncMock,
            ),
            patch("shoal.cli.session.archive_journal") as mock_archive,
        ):
            mock_archive.return_value = True
            asyncio.run(_prune_impl(force=True))
            mock_archive.assert_called_once_with("prune-1")


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

        async def mock_get(sid: str) -> None:
            return None

        with (
            patch("shoal.cli.journal.resolve_session", side_effect=mock_resolve),
            patch("shoal.core.state.get_session", side_effect=mock_get),
            patch("shoal.cli.journal.journal_exists", return_value=False),
        ):
            result = runner.invoke(app, ["journal", "my-sess"])
        assert result.exit_code == 0
        assert "No journal" in result.output

    def test_append_via_cli(self, runner: CliRunner, mock_dirs: object) -> None:
        from shoal.cli import app

        async def mock_resolve(name: str) -> str:
            return "sess-id-2"

        async def mock_get(sid: str) -> None:
            return None

        with (
            patch("shoal.cli.journal.resolve_session", side_effect=mock_resolve),
            patch("shoal.core.state.get_session", side_effect=mock_get),
            patch("shoal.cli.journal.append_entry") as mock_append,
            patch("shoal.cli.journal.journal_exists", return_value=True),
        ):
            mock_append.return_value = Path("/tmp/sess-id-2.md")
            result = runner.invoke(app, ["journal", "my-sess", "--append", "test entry"])
        assert result.exit_code == 0
        assert "appended" in result.output
        mock_append.assert_called_once_with("sess-id-2", "test entry", source="cli", metadata=None)

    def test_append_new_journal_with_metadata(self, runner: CliRunner, mock_dirs: object) -> None:
        """CLI passes metadata when creating a new journal."""
        from shoal.cli import app
        from shoal.models.state import SessionState

        session_state = SessionState(
            id="meta-sess",
            name="my-meta",
            tool="claude",
            path="/repo",
            tmux_session="shoal_my-meta",
        )

        async def mock_resolve(name: str) -> str:
            return "meta-sess"

        async def mock_get(sid: str) -> SessionState:
            return session_state

        with (
            patch("shoal.cli.journal.resolve_session", side_effect=mock_resolve),
            patch("shoal.core.state.get_session", side_effect=mock_get),
            patch("shoal.cli.journal.append_entry") as mock_append,
            patch("shoal.cli.journal.journal_exists", return_value=False),
        ):
            mock_append.return_value = Path("/tmp/meta-sess.md")
            result = runner.invoke(app, ["journal", "my-meta", "--append", "new entry"])
        assert result.exit_code == 0
        # Verify metadata was passed
        call_kwargs = mock_append.call_args
        assert call_kwargs.kwargs["metadata"] is not None
        assert call_kwargs.kwargs["metadata"].session_id == "meta-sess"


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
            patch("shoal.core.journal.journal_exists", return_value=True),
            patch("shoal.core.journal.append_entry", return_value=Path("/tmp/sess-mcp-1.md")),
        ):
            result = asyncio.run(append_journal_tool("my-sess", "mcp entry", "mcp"))
        assert "appended" in result["message"]

    def test_append_journal_new_with_metadata(self, mock_dirs: object) -> None:
        """MCP tool passes metadata when creating a new journal."""
        from shoal.models.state import SessionState
        from shoal.services.mcp_shoal_server import append_journal_tool

        session_state = SessionState(
            id="mcp-new",
            name="mcp-sess",
            tool="claude",
            path="/repo",
            tmux_session="shoal_mcp-sess",
        )

        with (
            patch(
                "shoal.core.state.resolve_session",
                new_callable=AsyncMock,
                return_value="mcp-new",
            ),
            patch(
                "shoal.core.state.get_session",
                new_callable=AsyncMock,
                return_value=session_state,
            ),
            patch("shoal.core.journal.journal_exists", return_value=False),
            patch(
                "shoal.core.journal.append_entry",
                return_value=Path("/tmp/mcp-new.md"),
            ) as mock_append,
        ):
            result = asyncio.run(append_journal_tool("mcp-sess", "first entry", "mcp"))
        assert "appended" in result["message"]
        call_kwargs = mock_append.call_args
        assert call_kwargs.kwargs["metadata"] is not None
        assert call_kwargs.kwargs["metadata"].session_id == "mcp-new"

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
