"""Urgency derivation for operator-board display.

This module is pure: no I/O, no DB access, no side effects.  It takes a
SessionState plus the current time (injected for testability) and returns
a UrgencyTier and a human-readable age label.

Urgency tiers (high to low):
    error       — session is in error state; needs immediate attention
    blocked     — session has been waiting longer than blocked_after_minutes
    waiting     — session is waiting (within the blocked threshold)
    review      — session is idle and tagged "review-ready"
    running     — session is actively running; no action needed
    stale       — session has been idle longer than stale_after_minutes
    idle        — session is idle within the stale threshold
    stopped     — session is stopped
    unknown     — status not recognised

Sort order for the operator board follows the tier order above: error
sessions surface first, stopped sessions last.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import IntEnum

from shoal.models.state import SessionState, SessionStatus


class UrgencyTier(IntEnum):
    """Operator-board priority, lower value = higher urgency."""

    error = 0
    blocked = 1
    waiting = 2
    review = 3
    running = 4
    stale = 5
    idle = 6
    stopped = 7
    unknown = 8


def _age_minutes(since: datetime, now: datetime) -> float:
    return (now - since).total_seconds() / 60


def _fmt_age(minutes: float) -> str:
    """Human-readable age string: '4m', '2h', '3d'."""
    if minutes < 60:
        return f"{int(minutes)}m"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.0f}h"
    return f"{hours / 24:.0f}d"


def derive_urgency(
    session: SessionState,
    *,
    now: datetime | None = None,
    blocked_after_minutes: int = 5,
    stale_after_minutes: int = 30,
) -> tuple[UrgencyTier, str]:
    """Return (tier, label) for a session.

    Args:
        session: The session to evaluate.
        now: Current UTC time; defaults to datetime.now(UTC).  Inject in
            tests to get deterministic results.
        blocked_after_minutes: Minutes waiting before tier becomes blocked.
        stale_after_minutes: Minutes idle before tier becomes stale.

    Returns:
        A (UrgencyTier, label) tuple.  label is a short string suitable for
        display in the status column, e.g. "waiting 8m", "blocked 23m",
        "stale 2h", or just "running".
    """
    if now is None:
        now = datetime.now(UTC)

    # Ensure now is timezone-aware for comparison.
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    status = session.status
    since = session.status_since
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)

    age_min = _age_minutes(since, now)

    match status:
        case SessionStatus.error:
            return UrgencyTier.error, "error"

        case SessionStatus.waiting:
            if age_min >= blocked_after_minutes:
                return UrgencyTier.blocked, f"blocked {_fmt_age(age_min)}"
            return UrgencyTier.waiting, f"waiting {_fmt_age(age_min)}"

        case SessionStatus.running:
            return UrgencyTier.running, "running"

        case SessionStatus.idle:
            if "review-ready" in session.tags:
                return UrgencyTier.review, "review-ready"
            if age_min >= stale_after_minutes:
                return UrgencyTier.stale, f"stale {_fmt_age(age_min)}"
            return UrgencyTier.idle, "idle"

        case SessionStatus.stopped:
            return UrgencyTier.stopped, "stopped"

        case _:
            return UrgencyTier.unknown, status.value


def sort_key(
    session: SessionState,
    *,
    now: datetime | None = None,
    blocked_after_minutes: int = 5,
    stale_after_minutes: int = 30,
) -> tuple[int, str]:
    """Stable sort key: (tier_value, session_name).

    Use as the key function when sorting a list of sessions for operator-board
    display.  Lower tier value = higher urgency = appears first.
    """
    tier, _ = derive_urgency(
        session,
        now=now,
        blocked_after_minutes=blocked_after_minutes,
        stale_after_minutes=stale_after_minutes,
    )
    return (int(tier), session.name)
