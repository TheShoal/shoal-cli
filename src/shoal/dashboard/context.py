"""Template context builders for the Shoal web dashboard.

Pure functions: SessionState → template-friendly dicts.  No I/O, no DB access.
"""

from __future__ import annotations

import html
import re
from collections import Counter
from datetime import UTC, datetime

from shoal.core.urgency import UrgencyTier, derive_urgency
from shoal.models.state import SessionState, SessionStatus, TmuxRuntimeState

# ---------------------------------------------------------------------------
# Urgency tier → CSS class name
# ---------------------------------------------------------------------------

_TIER_CSS: dict[UrgencyTier, str] = {
    UrgencyTier.error: "tier-error",
    UrgencyTier.blocked: "tier-blocked",
    UrgencyTier.waiting: "tier-waiting",
    UrgencyTier.review: "tier-review",
    UrgencyTier.running: "tier-running",
    UrgencyTier.stale: "tier-stale",
    UrgencyTier.idle: "tier-idle",
    UrgencyTier.stopped: "tier-stopped",
    UrgencyTier.unknown: "tier-unknown",
}

_TOOL_ICONS: dict[str, str] = {
    "claude": "◆",
    "aider": "✦",
    "cursor": "⬡",
    "codex": "∞",
    "amp": "⚡",
    "goose": "🪿",
}

_SOURCE_ICONS: dict[str, str] = {
    "system": "⚙",
    "mcp": "◎",
    "user": "◉",
    "supervisor": "◈",
    "": "◌",
}


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def relative_time(dt: datetime, now: datetime | None = None) -> str:
    """Return a human-readable relative time string.

    Args:
        dt: The datetime to describe.
        now: Reference time; defaults to datetime.now(UTC).

    Returns:
        Strings like "just now", "2m ago", "3h ago", "5d ago".
    """
    if now is None:
        now = datetime.now(UTC)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    delta_seconds = (now - dt).total_seconds()

    if delta_seconds < 60:
        return "just now"
    if delta_seconds < 3600:
        minutes = int(delta_seconds / 60)
        return f"{minutes}m ago"
    if delta_seconds < 86400:
        hours = int(delta_seconds / 3600)
        return f"{hours}h ago"
    days = int(delta_seconds / 86400)
    return f"{days}d ago"


# ---------------------------------------------------------------------------
# Session card context
# ---------------------------------------------------------------------------


def session_card_context(
    session: SessionState,
    now: datetime | None = None,
) -> dict[str, object]:
    """Build template context for a single session card.

    Args:
        session: The session state to convert.
        now: Reference time for urgency/relative-time calculations.

    Returns:
        A flat dict suitable for rendering session_card.html.
    """
    if now is None:
        now = datetime.now(UTC)

    tier, urgency_label = derive_urgency(session, now=now)
    tool_icon = _TOOL_ICONS.get(session.tool.lower(), "◇")

    runtime_kind = session.runtime.kind.value if session.runtime else "unknown"

    return {
        "id": session.id,
        "name": session.name,
        "tool": session.tool,
        "tool_icon": tool_icon,
        "status": session.status.value,
        "status_label": urgency_label,
        "tier_css": _TIER_CSS.get(tier, "tier-unknown"),
        "tier_name": tier.name,
        "status_source": session.status_source.value if session.status_source else "watcher",
        "runtime_kind": runtime_kind,
        "show_approve_action": runtime_kind == "tmux",
        "branch": session.branch or "",
        "worktree": session.worktree or "",
        "mcp_servers": session.mcp_servers,
        "last_activity": relative_time(session.last_activity, now=now),
        "created_at": relative_time(session.created_at, now=now),
        "parent_id": session.parent_id or "",
        "tags": session.tags,
        "template_name": session.template_name or "",
    }


# ---------------------------------------------------------------------------
# Fleet board context
# ---------------------------------------------------------------------------


def fleet_context(
    sessions: list[SessionState],
    now: datetime | None = None,
) -> dict[str, object]:
    """Build template context for the fleet overview page.

    Sessions are sorted by urgency tier (most urgent first).

    Args:
        sessions: All sessions to display.
        now: Reference time for urgency/relative-time calculations.

    Returns:
        A dict with ``session_cards`` (sorted) and aggregate ``counts``.
    """
    if now is None:
        now = datetime.now(UTC)

    tier_order = list(UrgencyTier)

    cards = sorted(
        [session_card_context(s, now=now) for s in sessions],
        key=lambda c: (
            tier_order.index(next(t for t in UrgencyTier if t.name == c["tier_name"])),
            str(c["name"]),
        ),
    )

    status_counts = Counter(s.status for s in sessions)
    counts: dict[str, int] = {
        "total": len(sessions),
        "running": status_counts.get(SessionStatus.running, 0),
        "waiting": status_counts.get(SessionStatus.waiting, 0),
        "error": status_counts.get(SessionStatus.error, 0),
        "idle": status_counts.get(SessionStatus.idle, 0),
        "stopped": status_counts.get(SessionStatus.stopped, 0),
        "unknown": status_counts.get(SessionStatus.unknown, 0),
    }
    counts["attention"] = counts["error"] + counts["waiting"]

    return {
        "session_cards": cards,
        "counts": counts,
    }


# ---------------------------------------------------------------------------
# Session detail context
# ---------------------------------------------------------------------------


def session_detail_context(
    session: SessionState,
    now: datetime | None = None,
) -> dict[str, object]:
    """Build template context for the session detail page.

    Args:
        session: The session to display.
        now: Reference time for relative-time calculations.

    Returns:
        A dict with full session metadata for session.html.
    """
    if now is None:
        now = datetime.now(UTC)

    tier, urgency_label = derive_urgency(session, now=now)
    tool_icon = _TOOL_ICONS.get(session.tool.lower(), "◇")

    runtime_kind = session.runtime.kind.value if session.runtime else "unknown"
    runtime_detail: dict[str, str] = {}
    if isinstance(session.runtime, TmuxRuntimeState):
        runtime_detail["tmux_session"] = session.runtime.session_name

    completed_at: str | None = None
    if session.completed_at is not None:
        completed_at = relative_time(session.completed_at, now=now)

    send_placeholder = "Send keys to session…"

    return {
        "id": session.id,
        "name": session.name,
        "tool": session.tool,
        "tool_icon": tool_icon,
        "status": session.status.value,
        "status_label": urgency_label,
        "tier_css": _TIER_CSS.get(tier, "tier-unknown"),
        "tier_name": tier.name,
        "branch": session.branch or "",
        "worktree": session.worktree or "",
        "path": session.path or "",
        "mcp_servers": session.mcp_servers,
        "parent_id": session.parent_id or "",
        "tags": session.tags,
        "template_name": session.template_name or "",
        "pid": session.pid,
        "runtime_kind": runtime_kind,
        "runtime_detail": runtime_detail,
        "show_approve_action": runtime_kind == "tmux",
        "send_placeholder": send_placeholder,
        "created_at_iso": session.created_at.isoformat(),
        "created_at": relative_time(session.created_at, now=now),
        "last_activity_iso": session.last_activity.isoformat(),
        "last_activity": relative_time(session.last_activity, now=now),
        "status_since_iso": session.status_since.isoformat(),
        "status_since": relative_time(session.status_since, now=now),
        "completed_at": completed_at,
    }


# ---------------------------------------------------------------------------
# Journal entry rendering
# ---------------------------------------------------------------------------

_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_CODE = re.compile(r"`([^`]+)`")


def _basic_md_to_html(text: str) -> str:
    """Convert bold and inline code markdown to HTML.

    Args:
        text: Markdown-formatted text.

    Returns:
        HTML string with ``<strong>`` and ``<code>`` tags.
    """
    text = html.escape(text)
    text = _MD_BOLD.sub(r"<strong>\1</strong>", text)
    text = _MD_CODE.sub(r"<code>\1</code>", text)
    lines = text.split("\n")
    return "<br>".join(lines)


def journal_entry_context(
    entry: object,
    now: datetime | None = None,
) -> dict[str, object]:
    """Convert a JournalEntry to template context.

    Args:
        entry: A JournalEntry dataclass instance.
        now: Reference time for relative-time calculations.

    Returns:
        A dict suitable for rendering a single journal entry.
    """
    if now is None:
        now = datetime.now(UTC)

    ts: datetime = getattr(entry, "timestamp", datetime.now(UTC))
    source: str = str(getattr(entry, "source", ""))
    content: str = str(getattr(entry, "content", ""))

    return {
        "timestamp_iso": ts.isoformat(),
        "timestamp_rel": relative_time(ts, now=now),
        "source": source,
        "source_icon": _SOURCE_ICONS.get(source, "◌"),
        "content_html": _basic_md_to_html(content),
        "content_raw": content,
    }


# ---------------------------------------------------------------------------
# Flow architecture context
# ---------------------------------------------------------------------------


def flow_node_context(session: SessionState) -> dict[str, object]:
    """Build template context for a single session node in the flow view."""
    tier, _ = derive_urgency(session)
    return {
        "id": session.id,
        "name": session.name,
        "tool": session.tool,
        "tool_icon": _TOOL_ICONS.get(session.tool.lower(), "◇"),
        "status": session.status.value,
        "tier_css": _TIER_CSS.get(tier, "tier-unknown"),
        "parent_id": session.parent_id or "",
        "children": [],
    }


def flow_context(sessions: list[SessionState]) -> dict[str, object]:
    """Build template context for the agent team flow / architecture view.

    Builds a parent-child adjacency map from all sessions and returns
    root nodes (sessions with no parent) and the full node list.

    Args:
        sessions: All sessions from the database.

    Returns:
        A dict with ``roots`` (root session nodes) and ``nodes`` (all nodes).
    """
    by_id: dict[str, dict[str, object]] = {}
    for s in sessions:
        by_id[s.id] = flow_node_context(s)

    roots: list[dict[str, object]] = []
    for s in sessions:
        if not s.parent_id:
            roots.append(by_id[s.id])
        else:
            parent = by_id.get(s.parent_id)
            if parent is not None:
                existing = parent.get("children")
                if isinstance(existing, list):
                    existing.append(by_id[s.id])
                else:
                    parent["children"] = [by_id[s.id]]

    # Attach children list (empty list for leaf nodes)
    for node in by_id.values():
        if "children" not in node:
            node["children"] = []

    return {
        "roots": roots,
        "nodes": list(by_id.values()),
    }


# ---------------------------------------------------------------------------
# MCP Matrix context
# ---------------------------------------------------------------------------


def mcp_matrix_context(
    sessions: list[SessionState],
    available_servers: list[str],
    stacks: list[dict[str, object]],
) -> dict[str, object]:
    """Build template context for the MCP server assignment matrix.

    Produces a sessions x servers grid showing which MCP servers are
    enabled for each session.

    Args:
        sessions: All sessions to display in the matrix.
        available_servers: Ordered list of MCP server names (columns).
        stacks: Pre-built stack metadata passed through to the template.

    Returns:
        A dict with ``sessions`` (sorted by name), ``servers``, and ``stacks``.
    """
    now = datetime.now(UTC)

    rows: list[dict[str, object]] = []
    for session in sorted(sessions, key=lambda s: s.name.lower()):
        tier, _ = derive_urgency(session, now=now)
        rows.append(
            {
                "id": session.id,
                "name": session.name,
                "status": session.status.value,
                "tier_css": _TIER_CSS.get(tier, "tier-unknown"),
                "tool": session.tool,
                "tool_icon": _TOOL_ICONS.get(session.tool.lower(), "diamond"),
                "mcp_enabled": {srv: srv in session.mcp_servers for srv in available_servers},
                "is_stopped": session.status == SessionStatus.stopped,
            }
        )

    return {
        "sessions": rows,
        "servers": available_servers,
        "stacks": stacks,
    }
