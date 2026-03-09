"""Tests for core/urgency.py — urgency derivation for the operator board."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shoal.core.urgency import UrgencyTier, derive_urgency, sort_key
from shoal.models.state import SessionState, SessionStatus


def _session(
    *,
    status: SessionStatus = SessionStatus.idle,
    status_since_offset_minutes: float = 0,
    tags: list[str] | None = None,
    name: str = "test",
) -> SessionState:
    """Build a minimal SessionState with a pinned status_since."""
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
        tags=tags or [],
    )


NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)


class TestDeriveUrgency:
    def test_error_is_highest(self):
        s = _session(status=SessionStatus.error)
        tier, label = derive_urgency(s, now=NOW)
        assert tier == UrgencyTier.error
        assert label == "error"

    def test_waiting_within_threshold_is_waiting(self):
        s = _session(status=SessionStatus.waiting, status_since_offset_minutes=3)
        tier, label = derive_urgency(s, now=NOW, blocked_after_minutes=5)
        assert tier == UrgencyTier.waiting
        assert label == "waiting 3m"

    def test_waiting_at_threshold_becomes_blocked(self):
        s = _session(status=SessionStatus.waiting, status_since_offset_minutes=5)
        tier, label = derive_urgency(s, now=NOW, blocked_after_minutes=5)
        assert tier == UrgencyTier.blocked
        assert label == "blocked 5m"

    def test_waiting_beyond_threshold_is_blocked(self):
        s = _session(status=SessionStatus.waiting, status_since_offset_minutes=23)
        tier, label = derive_urgency(s, now=NOW, blocked_after_minutes=5)
        assert tier == UrgencyTier.blocked
        assert label == "blocked 23m"

    def test_running_is_running(self):
        s = _session(status=SessionStatus.running)
        tier, label = derive_urgency(s, now=NOW)
        assert tier == UrgencyTier.running
        assert label == "running"

    def test_idle_within_stale_threshold(self):
        s = _session(status=SessionStatus.idle, status_since_offset_minutes=10)
        tier, label = derive_urgency(s, now=NOW, stale_after_minutes=30)
        assert tier == UrgencyTier.idle
        assert label == "idle"

    def test_idle_at_stale_threshold_becomes_stale(self):
        s = _session(status=SessionStatus.idle, status_since_offset_minutes=30)
        tier, label = derive_urgency(s, now=NOW, stale_after_minutes=30)
        assert tier == UrgencyTier.stale
        assert label == "stale 30m"

    def test_stale_hours_label(self):
        s = _session(status=SessionStatus.idle, status_since_offset_minutes=90)
        tier, label = derive_urgency(s, now=NOW, stale_after_minutes=30)
        assert tier == UrgencyTier.stale
        assert label == "stale 2h"

    def test_stale_days_label(self):
        s = _session(status=SessionStatus.idle, status_since_offset_minutes=60 * 50)
        tier, label = derive_urgency(s, now=NOW, stale_after_minutes=30)
        assert tier == UrgencyTier.stale
        assert label == "stale 2d"

    def test_review_ready_tag_overrides_idle(self):
        s = _session(
            status=SessionStatus.idle,
            status_since_offset_minutes=10,
            tags=["review-ready"],
        )
        tier, label = derive_urgency(s, now=NOW, stale_after_minutes=30)
        assert tier == UrgencyTier.review
        assert label == "review-ready"

    def test_review_ready_tag_with_stale_age(self):
        # review-ready tag takes precedence even when the session would otherwise
        # be stale — it means someone explicitly marked it ready for review.
        s = _session(
            status=SessionStatus.idle,
            status_since_offset_minutes=120,
            tags=["review-ready", "feat"],
        )
        tier, label = derive_urgency(s, now=NOW, stale_after_minutes=30)
        assert tier == UrgencyTier.review
        assert label == "review-ready"

    def test_stopped(self):
        s = _session(status=SessionStatus.stopped)
        tier, label = derive_urgency(s, now=NOW)
        assert tier == UrgencyTier.stopped
        assert label == "stopped"

    def test_unknown_status_falls_through(self):
        s = _session(status=SessionStatus.unknown)
        tier, label = derive_urgency(s, now=NOW)
        assert tier == UrgencyTier.unknown
        assert label == "unknown"

    def test_now_defaults_to_utc(self):
        """derive_urgency without explicit now should not raise."""
        s = _session(status=SessionStatus.running)
        tier, _ = derive_urgency(s)
        assert tier == UrgencyTier.running

    def test_naive_status_since_handled(self):
        """Sessions with naive status_since datetimes don't crash."""
        s = _session(status=SessionStatus.waiting, status_since_offset_minutes=10)
        # Strip timezone info to simulate a legacy record.
        s = s.model_copy(update={"status_since": s.status_since.replace(tzinfo=None)})
        tier, _ = derive_urgency(s, now=NOW, blocked_after_minutes=5)
        assert tier == UrgencyTier.blocked


class TestSortKey:
    def test_sort_order(self):
        error = _session(status=SessionStatus.error, name="e")
        blocked = _session(
            status=SessionStatus.waiting,
            status_since_offset_minutes=10,
            name="b",
        )
        waiting = _session(
            status=SessionStatus.waiting,
            status_since_offset_minutes=2,
            name="w",
        )
        review = _session(
            status=SessionStatus.idle,
            tags=["review-ready"],
            name="r",
        )
        running = _session(status=SessionStatus.running, name="n")
        stale = _session(
            status=SessionStatus.idle,
            status_since_offset_minutes=60,
            name="s",
        )
        idle = _session(status=SessionStatus.idle, name="i")
        stopped = _session(status=SessionStatus.stopped, name="x")

        sessions = [stopped, idle, stale, running, review, waiting, blocked, error]
        sorted_sessions = sorted(
            sessions,
            key=lambda s: sort_key(s, now=NOW, blocked_after_minutes=5, stale_after_minutes=30),
        )
        names = [s.name for s in sorted_sessions]
        assert names == ["e", "b", "w", "r", "n", "s", "i", "x"]

    def test_same_tier_sorted_by_name(self):
        s1 = _session(status=SessionStatus.running, name="zebra")
        s2 = _session(status=SessionStatus.running, name="alpha")
        sorted_sessions = sorted([s1, s2], key=lambda s: sort_key(s, now=NOW))
        assert sorted_sessions[0].name == "alpha"
