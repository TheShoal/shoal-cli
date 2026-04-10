"""Tests for weekly report generation."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, patch

import pytest

from shoal.cli.report import _get_current_iso_week, _parse_iso_week
from shoal.models.state import SessionState, SessionStatus, TmuxRuntimeState


def _make_session(
    *,
    name: str = "test",
    completed_at: datetime | None = None,
    tags: list[str] | None = None,
) -> SessionState:
    """Helper to build a SessionState for testing."""
    return SessionState(
        id="test-id",
        name=name,
        tool="omp",
        path="/repo",
        branch="main",
        runtime=TmuxRuntimeState(session_name="test", session_id="test-id", window_id="0"),
        status=SessionStatus.idle,
        completed_at=completed_at,
        tags=tags or [],
    )


class TestIsoWeekParsing:
    """Tests for ISO week string parsing."""

    def test_parse_valid_week(self) -> None:
        """Parse a valid ISO week string."""
        start, end = _parse_iso_week("2026-W15")
        assert start == date(2026, 4, 6)  # Monday
        assert end == date(2026, 4, 12)  # Sunday

    def test_parse_week_1(self) -> None:
        """Parse week 1 of a year."""
        start, end = _parse_iso_week("2026-W01")
        assert start.weekday() == 0  # Monday
        assert end.weekday() == 6  # Sunday
        assert (end - start).days == 6

    def test_parse_invalid_format(self) -> None:
        """Reject invalid week format."""
        with pytest.raises(ValueError, match="Invalid ISO week format"):
            _parse_iso_week("2026-15")

    def test_parse_invalid_week_number(self) -> None:
        """Reject invalid week number."""
        with pytest.raises(ValueError, match="Invalid week number"):
            _parse_iso_week("2026-W54")

    def test_get_current_week(self) -> None:
        """Get current ISO week string."""
        week = _get_current_iso_week()
        assert week.startswith("20")  # Year 20xx
        assert "-W" in week
        # Should be parseable
        start, end = _parse_iso_week(week)
        today = datetime.now(UTC).date()
        assert start <= today <= end


class TestWeeklySummaryGeneration:
    """Tests for weekly summary report generation."""

    @pytest.mark.asyncio
    async def test_generate_weekly_no_sessions(self) -> None:
        """Generate weekly summary with no completed sessions."""
        from shoal.services.report import generate_weekly_summary

        with patch("shoal.core.state.list_sessions", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []

            week_start = date(2026, 4, 6)
            week_end = date(2026, 4, 12)

            report = await generate_weekly_summary(
                week_start=week_start,
                week_end=week_end,
            )

            assert "Weekly Summary" in report
            assert "2026-04-06" in report
            assert "2026-04-12" in report

    @pytest.mark.asyncio
    async def test_generate_weekly_with_completed_sessions(self) -> None:
        """Generate weekly summary with completed sessions in range."""
        from shoal.services.report import generate_weekly_summary

        week_start = date(2026, 4, 6)
        week_end = date(2026, 4, 12)
        completed_time = datetime(2026, 4, 8, 10, 0, 0, tzinfo=UTC)  # Wednesday

        session = _make_session(name="feature-x", completed_at=completed_time)

        with patch("shoal.core.state.list_sessions", new_callable=AsyncMock) as mock_list:
            with patch(
                "shoal.services.report._build_session_report_data", new_callable=AsyncMock
            ) as mock_build:
                from shoal.services.report import SessionReportData

                mock_list.return_value = [session]
                mock_build.return_value = SessionReportData(
                    session_name="feature-x",
                    tool="omp",
                    branch="feat/x",
                    status="Done",
                    last_active="2026-04-08T10:00:00",
                    journal_entries=["Made progress"],
                    dreamer_summary="(no summary)",
                )

                report = await generate_weekly_summary(
                    week_start=week_start,
                    week_end=week_end,
                )

                assert "Weekly Summary" in report
                assert "feature-x" in report or "Completed sessions" in report

    @pytest.mark.asyncio
    async def test_generate_weekly_filters_by_date(self) -> None:
        """Only include sessions completed within the week."""
        from shoal.services.report import generate_weekly_summary

        week_start = date(2026, 4, 6)
        week_end = date(2026, 4, 12)

        # Session completed before the week
        before = _make_session(
            name="before", completed_at=datetime(2026, 4, 5, 23, 59, 59, tzinfo=UTC)
        )
        # Session completed during the week
        during = _make_session(
            name="during", completed_at=datetime(2026, 4, 8, 10, 0, 0, tzinfo=UTC)
        )
        # Session completed after the week
        after = _make_session(name="after", completed_at=datetime(2026, 4, 13, 0, 0, 1, tzinfo=UTC))

        with patch("shoal.core.state.list_sessions", new_callable=AsyncMock) as mock_list:
            with patch(
                "shoal.services.report._build_session_report_data", new_callable=AsyncMock
            ) as mock_build:
                from shoal.services.report import SessionReportData

                mock_list.return_value = [before, during, after]
                # Only "during" should be processed
                mock_build.return_value = SessionReportData(
                    session_name="during",
                    tool="omp",
                    branch="feat/x",
                    status="Done",
                    last_active="2026-04-08T10:00:00",
                    journal_entries=[],
                    dreamer_summary="",
                )

                await generate_weekly_summary(
                    week_start=week_start,
                    week_end=week_end,
                )

                # Should only build data for "during"
                assert mock_build.call_count == 1
                called_session = mock_build.call_args[0][0]
                assert called_session.name == "during"

    @pytest.mark.asyncio
    async def test_generate_weekly_team_filter(self) -> None:
        """Filter sessions by team slug."""
        from shoal.services.report import generate_weekly_summary

        week_start = date(2026, 4, 6)
        week_end = date(2026, 4, 12)
        completed_time = datetime(2026, 4, 8, 10, 0, 0, tzinfo=UTC)

        be_session = _make_session(name="be-work", completed_at=completed_time, tags=["team:be"])
        fe_session = _make_session(name="fe-work", completed_at=completed_time, tags=["team:fe"])

        with patch("shoal.core.state.list_sessions", new_callable=AsyncMock) as mock_list:
            with patch(
                "shoal.services.report._build_session_report_data", new_callable=AsyncMock
            ) as mock_build:
                from shoal.services.report import SessionReportData

                mock_list.return_value = [be_session, fe_session]
                mock_build.return_value = SessionReportData(
                    session_name="be-work",
                    tool="omp",
                    branch="feat/x",
                    status="Done",
                    last_active="2026-04-08T10:00:00",
                    journal_entries=[],
                    dreamer_summary="",
                )

                await generate_weekly_summary(
                    week_start=week_start,
                    week_end=week_end,
                    team_slug="be",
                )

                # Should only build data for be-session
                assert mock_build.call_count == 1
                called_session = mock_build.call_args[0][0]
                assert called_session.name == "be-work"

    @pytest.mark.asyncio
    async def test_fallback_when_llm_unavailable(self) -> None:
        """Weekly report falls back to template when LLM call fails."""
        from shoal.services.report import generate_weekly_summary

        week_start = date(2026, 4, 6)
        week_end = date(2026, 4, 12)

        with patch("shoal.core.state.list_sessions", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []

            # LLM is unavailable (ai_client module was removed in v0.41.0),
            # so this will use the fallback path automatically
            report = await generate_weekly_summary(
                week_start=week_start,
                week_end=week_end,
            )

            # Should still generate a report using the fallback
            assert "Weekly Summary" in report
            assert "Shipped" in report or "External context" in report


class TestWeeklyCLI:
    """Tests for the weekly CLI command."""

    @pytest.mark.asyncio
    async def test_weekly_command_defaults_to_current_week(self) -> None:
        """When no --week is provided, use current week."""
        from shoal.cli.report import _report_weekly_impl

        with patch("shoal.services.report.generate_weekly_summary", new_callable=AsyncMock) as mock:
            mock.return_value = "# Weekly Summary\n\nTest"

            await _report_weekly_impl(week="", team="", model="test-model", post=False)

            # Should call with parsed dates
            assert mock.called
            call_kwargs = mock.call_args.kwargs
            assert "week_start" in call_kwargs
            assert "week_end" in call_kwargs
            assert isinstance(call_kwargs["week_start"], date)
            assert isinstance(call_kwargs["week_end"], date)

    @pytest.mark.asyncio
    async def test_weekly_command_parses_iso_week(self) -> None:
        """Parse --week argument as ISO week."""
        from shoal.cli.report import _report_weekly_impl

        with patch("shoal.services.report.generate_weekly_summary", new_callable=AsyncMock) as mock:
            mock.return_value = "# Weekly Summary\n\nTest"

            await _report_weekly_impl(week="2026-W15", team="", model="test-model", post=False)

            call_kwargs = mock.call_args.kwargs
            assert call_kwargs["week_start"] == date(2026, 4, 6)
            assert call_kwargs["week_end"] == date(2026, 4, 12)
