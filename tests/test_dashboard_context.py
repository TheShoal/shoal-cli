"""Unit tests for shoal.dashboard.context."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shoal.dashboard.context import (
    _basic_md_to_html,
    fleet_context,
    journal_entry_context,
    relative_time,
    session_card_context,
    session_detail_context,
)
from shoal.models.state import SessionState, SessionStatus, TmuxRuntimeState


def _make_session(
    session_id: str = "abc123",
    name: str = "test-session",
    tool: str = "claude",
    status: SessionStatus = SessionStatus.running,
    branch: str = "main",
    mcp_servers: list[str] | None = None,
    tags: list[str] | None = None,
) -> SessionState:
    now = datetime.now(UTC)
    return SessionState(
        id=session_id,
        name=name,
        tool=tool,
        path="/tmp/repo",
        worktree="",
        branch=branch,
        runtime=TmuxRuntimeState(session_name=f"shoal:{session_id}"),
        status=status,
        mcp_servers=mcp_servers or [],
        tags=tags or [],
        created_at=now - timedelta(hours=1),
        last_activity=now - timedelta(minutes=5),
        status_since=now - timedelta(minutes=5),
    )


class TestRelativeTime:
    def test_just_now(self) -> None:
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        dt = now - timedelta(seconds=30)
        assert relative_time(dt, now=now) == "just now"

    def test_minutes(self) -> None:
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        dt = now - timedelta(minutes=7)
        assert relative_time(dt, now=now) == "7m ago"

    def test_hours(self) -> None:
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        dt = now - timedelta(hours=3)
        assert relative_time(dt, now=now) == "3h ago"

    def test_days(self) -> None:
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        dt = now - timedelta(days=5)
        assert relative_time(dt, now=now) == "5d ago"

    def test_naive_dt_treated_as_utc(self) -> None:
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        naive = datetime(2024, 1, 1, 11, 55, 0)  # naive — 5 min ago  # noqa: DTZ001
        result = relative_time(naive, now=now)
        assert result == "5m ago"


class TestBasicMdToHtml:
    def test_bold(self) -> None:
        assert _basic_md_to_html("**bold**") == "<strong>bold</strong>"

    def test_inline_code(self) -> None:
        assert _basic_md_to_html("`code`") == "<code>code</code>"

    def test_newline_to_br(self) -> None:
        assert _basic_md_to_html("line1\nline2") == "line1<br>line2"

    def test_no_markup(self) -> None:
        assert _basic_md_to_html("plain text") == "plain text"


class TestSessionCardContext:
    def test_running_session(self) -> None:
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        session = _make_session(status=SessionStatus.running)
        ctx = session_card_context(session, now=now)

        assert ctx["id"] == "abc123"
        assert ctx["name"] == "test-session"
        assert ctx["tool"] == "claude"
        assert ctx["tool_icon"] == "◆"
        assert ctx["status"] == "running"
        assert ctx["tier_css"] == "tier-running"
        assert ctx["branch"] == "main"

    def test_error_session_tier(self) -> None:
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        session = _make_session(status=SessionStatus.error)
        ctx = session_card_context(session, now=now)

        assert ctx["tier_css"] == "tier-error"
        assert ctx["status_label"] == "error"

    def test_unknown_tool_uses_fallback_icon(self) -> None:
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        session = _make_session(tool="unknown-tool")
        ctx = session_card_context(session, now=now)
        assert ctx["tool_icon"] == "◇"

    def test_mcp_servers_in_context(self) -> None:
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        session = _make_session(mcp_servers=["github", "jira"])
        ctx = session_card_context(session, now=now)
        assert ctx["mcp_servers"] == ["github", "jira"]


class TestFleetContext:
    def test_sorting_puts_error_first(self) -> None:
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        sessions = [
            _make_session("idle-1", status=SessionStatus.idle, name="b-idle"),
            _make_session("error-1", status=SessionStatus.error, name="a-error"),
            _make_session("running-1", status=SessionStatus.running, name="c-run"),
        ]
        ctx = fleet_context(sessions, now=now)
        cards = ctx["session_cards"]
        assert isinstance(cards, list)
        assert cards[0]["tier_name"] == "error"

    def test_counts_are_accurate(self) -> None:
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        sessions = [
            _make_session("r1", status=SessionStatus.running),
            _make_session("r2", status=SessionStatus.running),
            _make_session("e1", status=SessionStatus.error),
            _make_session("i1", status=SessionStatus.idle),
        ]
        ctx = fleet_context(sessions, now=now)
        counts = ctx["counts"]
        assert isinstance(counts, dict)
        assert counts["total"] == 4
        assert counts["running"] == 2
        assert counts["error"] == 1
        assert counts["idle"] == 1

    def test_attention_count_sums_error_and_waiting(self) -> None:
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        sessions = [
            _make_session("e1", status=SessionStatus.error),
            _make_session("w1", status=SessionStatus.waiting),
            _make_session("r1", status=SessionStatus.running),
        ]
        ctx = fleet_context(sessions, now=now)
        counts = ctx["counts"]
        assert isinstance(counts, dict)
        assert counts["attention"] == 2


class TestSessionDetailContext:
    def test_tmux_runtime_detail(self) -> None:
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        session = _make_session()
        ctx = session_detail_context(session, now=now)

        assert ctx["runtime_kind"] == "tmux"
        detail = ctx["runtime_detail"]
        assert isinstance(detail, dict)
        assert "tmux_session" in detail
        assert detail["tmux_session"] == "shoal:abc123"

    def test_completed_at_is_none_when_not_set(self) -> None:
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        session = _make_session()
        ctx = session_detail_context(session, now=now)
        assert ctx["completed_at"] is None


class TestJournalEntryContext:
    def test_basic_entry(self) -> None:
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        class _Entry:
            timestamp = now - timedelta(minutes=3)
            source = "system"
            content = "Session created with **tool** `claude`."

        ctx = journal_entry_context(_Entry(), now=now)

        assert ctx["source"] == "system"
        assert ctx["source_icon"] == "⚙"
        assert ctx["timestamp_rel"] == "3m ago"
        assert "<strong>tool</strong>" in str(ctx["content_html"])
        assert "<code>claude</code>" in str(ctx["content_html"])

    def test_empty_source_uses_fallback_icon(self) -> None:
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        class _Entry:
            timestamp = now
            source = ""
            content = "test"

        ctx = journal_entry_context(_Entry(), now=now)
        assert ctx["source_icon"] == "◌"
