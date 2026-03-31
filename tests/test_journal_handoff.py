"""Tests for generate_handoff and persisted handoff artifacts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from rich.markdown import Markdown

from shoal.cli.journal import _render_handoff
from shoal.core.journal import (
    HandoffArtifact,
    JournalEntry,
    generate_handoff,
    write_handoff_artifact,
)
from shoal.models.state import SessionState, SessionStatus


def _session(
    *,
    status: SessionStatus = SessionStatus.idle,
    status_since_offset_minutes: float = 10,
    tags: list[str] | None = None,
    name: str = "auth-impl",
) -> SessionState:
    now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
    since = now - timedelta(minutes=status_since_offset_minutes)
    return SessionState(
        id="abc",
        name=name,
        tool="claude",
        path="/tmp",
        tmux_session="_abc",
        status=status,
        status_since=since,
        last_activity=since,
        tags=tags or [],
    )


NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)


def _entry(content: str, source: str = "test", offset_minutes: float = 0) -> JournalEntry:
    ts = NOW - timedelta(minutes=offset_minutes)
    return JournalEntry(timestamp=ts, source=source, content=content)


def _transition(from_s: str, to_s: str, offset_minutes: float = 0) -> dict[str, str]:
    ts = (NOW - timedelta(minutes=offset_minutes)).isoformat()
    return {"from_status": from_s, "to_status": to_s, "timestamp": ts}


class TestGenerateHandoff:
    def test_returns_handoff_artifact(self):
        s = _session(status=SessionStatus.running)
        result = generate_handoff(s, [], [], now=NOW)
        assert isinstance(result, HandoffArtifact)

    def test_session_metadata_propagated(self):
        s = _session(status=SessionStatus.running)
        result = generate_handoff(s, [], [], now=NOW)
        assert result.session_name == "auth-impl"
        assert result.tool == "claude"

    def test_running_suggests_no_action(self):
        s = _session(status=SessionStatus.running)
        result = generate_handoff(s, [], [], now=NOW)
        assert "No immediate action" in result.suggested_next

    def test_error_suggests_attach(self):
        s = _session(status=SessionStatus.error)
        result = generate_handoff(s, [], [], now=NOW)
        assert "error state" in result.suggested_next
        assert "shoal attach" in result.suggested_next

    def test_blocked_includes_duration(self):
        s = _session(status=SessionStatus.waiting, status_since_offset_minutes=20)
        result = generate_handoff(s, [], [], now=NOW, blocked_after_minutes=5)
        assert "blocked" in result.urgency_label
        assert "shoal attach" in result.suggested_next or "shoal send" in result.suggested_next

    def test_waiting_within_threshold(self):
        s = _session(status=SessionStatus.waiting, status_since_offset_minutes=2)
        result = generate_handoff(s, [], [], now=NOW, blocked_after_minutes=5)
        assert "waiting" in result.urgency_label

    def test_review_ready_tag(self):
        s = _session(status=SessionStatus.idle, tags=["review-ready"])
        result = generate_handoff(s, [], [], now=NOW)
        assert "review-ready" in result.urgency_label
        assert "review" in result.suggested_next.lower()

    def test_stale_suggests_verify(self):
        s = _session(status=SessionStatus.idle, status_since_offset_minutes=60)
        result = generate_handoff(s, [], [], now=NOW, stale_after_minutes=30)
        assert "stale" in result.urgency_label
        assert "Verify" in result.suggested_next or "idle" in result.suggested_next

    def test_recent_entries_limited(self):
        entries = [_entry(f"entry {i}", offset_minutes=i) for i in range(10)]
        s = _session()
        result = generate_handoff(s, entries, [], now=NOW, recent_entry_count=3)
        assert len(result.recent_entries) == 3
        assert result.recent_entries == entries[-3:]

    def test_transitions_summarised(self):
        transitions = [
            _transition("idle", "running", offset_minutes=5),
            _transition("running", "waiting", offset_minutes=2),
        ]
        s = _session()
        result = generate_handoff(s, [], transitions, now=NOW)
        assert len(result.transition_summary) == 2
        assert "idle → running" in result.transition_summary[0]
        assert "running → waiting" in result.transition_summary[1]

    def test_to_markdown_contains_session_name(self):
        s = _session(status=SessionStatus.running)
        result = generate_handoff(s, [], [], now=NOW)
        md = result.to_markdown()
        assert "auth-impl" in md
        assert "## Status" in md
        assert "## Suggested next action" in md

    def test_to_markdown_includes_journal_section(self):
        entries = [_entry("Fixed the auth bug")]
        s = _session()
        result = generate_handoff(s, entries, [], now=NOW)
        md = result.to_markdown()
        assert "## Recent journal" in md
        assert "Fixed the auth bug" in md

    def test_to_markdown_includes_transitions_section(self):
        transitions = [_transition("idle", "running")]
        s = _session()
        result = generate_handoff(s, [], transitions, now=NOW)
        md = result.to_markdown()
        assert "## Recent transitions" in md
        assert "idle → running" in md

    def test_non_session_object_does_not_crash(self):
        """generate_handoff tolerates arbitrary objects gracefully."""
        result = generate_handoff({}, [], [], now=NOW)
        assert isinstance(result, HandoffArtifact)
        assert result.suggested_next


class TestHandoffArtifacts:
    def test_write_handoff_artifact_persists_markdown(self, tmp_path):
        artifact = generate_handoff(_session(), [_entry("Fixed auth")], [], now=NOW)

        with patch("shoal.core.journal.data_dir", return_value=tmp_path):
            path = write_handoff_artifact("abc", artifact)

        assert path == tmp_path / "journals" / "handoffs" / "abc.md"
        assert path.read_text() == artifact.to_markdown()

    def test_render_handoff_writes_artifact_and_prints_saved_path(self, tmp_path):
        session = _session()
        mock_db = AsyncMock()
        mock_db.get_status_transitions = AsyncMock(return_value=[_transition("idle", "running")])

        with (
            patch("shoal.core.journal.data_dir", return_value=tmp_path),
            patch("shoal.cli.journal.read_journal", return_value=[_entry("Fixed auth")]),
            patch("shoal.core.db.get_db", new=AsyncMock(return_value=mock_db)),
            patch("shoal.cli.journal.get_console") as mock_get_console,
        ):
            _render_handoff("abc", session)

        artifact_path = tmp_path / "journals" / "handoffs" / "abc.md"
        assert artifact_path.exists()
        assert "Fixed auth" in artifact_path.read_text()
        mock_print = mock_get_console.return_value.print
        assert any(
            "Saved handoff artifact:" in str(call.args[0])
            and str(artifact_path) in str(call.args[0])
            for call in mock_print.call_args_list
        )
        assert any(isinstance(call.args[0], Markdown) for call in mock_print.call_args_list)
