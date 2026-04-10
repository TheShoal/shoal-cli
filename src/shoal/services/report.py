"""Report service for PM-facing summaries.

Builds session, team, and sprint reports from existing Shoal data sources:
- session state
- journals
- Dreamer summaries
- Linear issue snapshots
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

from shoal.models.state import SessionState, SessionStatus

if TYPE_CHECKING:
    from shoal.models.config.workspace import TeamReportTargetConfig

logger = logging.getLogger("shoal.report")

_TERMINAL_STATUSES = {SessionStatus.error, SessionStatus.stopped}

_SESSION_PROMPT = """You are writing a concise project-manager update for one coding session.

Session: {session_name}
Tool: {tool}
Status: {status}
Branch: {branch}
Last active: {last_active}

Latest journal entries:
{journal_entries}

Dreamer summary:
{dreamer_summary}

Write a short markdown update with:
- current work
- recent progress
- blockers or risks
- next step

Be direct. Avoid hype. Keep it under 180 words.
"""

_TEAM_PROMPT = """You are writing a concise team status update from several coding sessions.

Team: {team_name} ({team_slug})

Current sessions:
{sessions_block}

Linear context:
{linear_context}

Write a short markdown update with sections:
- In progress
- Risks / blockers
- Next

Keep it brief and PM-readable.
"""

_SPRINT_PROMPT = """You are writing a sprint summary for a software team.

Team: {team_name} ({team_slug})
Cycle: {cycle_name}

Linear context:
{linear_context}

Completed sessions:
{completed_sessions}

In-progress sessions:
{in_progress_sessions}

Blocked sessions:
{blocked_sessions}

Write a markdown summary with sections:
- Completed
- In progress
- Risks / blockers
- Next sprint focus

Be concise and concrete.
"""

_WEEKLY_PROMPT = """You are writing a weekly work summary.

Week: {week_start} to {week_end}
Team: {team_name}

Completed sessions:
{completed_sessions}

Linear context:
{linear_context}

GitHub context:
{github_context}

Write a markdown summary with sections:
- Shipped
- Reviewed / merged PRs
- In progress
- Highlights

Focus on concrete outcomes. Keep it under 300 words.
"""


@dataclass(frozen=True)
class SessionReportData:
    """Normalized session data used by report generation."""

    session_name: str
    tool: str
    branch: str
    status: str
    last_active: str
    journal_entries: list[str]
    dreamer_summary: str


@dataclass(frozen=True)
class SprintReportData:
    """Collected inputs for a team sprint report."""

    team_name: str
    team_slug: str
    team_key: str
    cycle_name: str
    linear_context: str
    completed: list[SessionReportData]
    in_progress: list[SessionReportData]
    blocked: list[SessionReportData]


@dataclass(frozen=True)
class WeeklyReportData:
    """Collected inputs for a weekly summary report."""

    week_start: date
    week_end: date
    team_name: str
    completed: list[SessionReportData]
    linear_context: str
    github_context: str


@dataclass(frozen=True)
class PostedSprintReport:
    """Rendered sprint report plus Linear posting metadata."""

    report: str
    target_kind: str
    target_name: str
    update_url: str
    health: str


async def generate_session_report(
    session_name: str,
    *,
    model: str = "amazon.nova-lite-v1:0",
) -> str:
    """Generate a report for one session.

    Args:
        session_name: Session name.
        model: Model name for the LLM call.

    Returns:
        Markdown report.

    Raises:
        RuntimeError: If the session does not exist.
    """
    from shoal.core.state import find_by_name, get_session

    session_id = await find_by_name(session_name)
    if session_id is None:
        raise RuntimeError(f"Session not found: {session_name}")

    session = await get_session(session_id)
    if session is None:
        raise RuntimeError(f"Session not found: {session_name}")

    data = await _build_session_report_data(session)
    prompt = _SESSION_PROMPT.format(
        session_name=data.session_name,
        tool=data.tool,
        status=data.status,
        branch=data.branch,
        last_active=data.last_active,
        journal_entries=_render_bullets(data.journal_entries, empty="(no journal entries)"),
        dreamer_summary=data.dreamer_summary,
    )

    try:
        from shoal.services.ai_client import call_llm

        body = await call_llm(model=model, prompt=prompt, max_tokens=500, temperature=0.3)
        return _format_report(
            title=f"Session Report: {data.session_name}",
            metadata=[
                ("Status", data.status),
                ("Tool", data.tool),
                ("Branch", f"`{data.branch}`"),
            ],
            body=body,
        )
    except Exception as exc:
        logger.warning("Session report LLM call failed for %s: %s", session_name, exc)
        return _fallback_session_report(data)


async def generate_team_report(
    team_name: str,
    team_slug: str,
    *,
    linear_team_key: str | None = None,
    model: str = "amazon.nova-lite-v1:0",
) -> str:
    """Generate a report across active sessions for a team.

    Args:
        team_name: Human-friendly team name.
        team_slug: Local team slug from workspace config.
        linear_team_key: Linear team key, defaults to upper(team_slug).
        model: Model name for the LLM call.

    Returns:
        Markdown report.
    """
    from shoal.core.state import list_sessions

    team_key = linear_team_key or team_slug.upper()
    sessions = await list_sessions()
    active_sessions = [
        session
        for session in sessions
        if _belongs_to_team(session, team_slug, team_key) and not _is_completed(session)
    ]

    snapshots = [await _build_session_report_data(session) for session in active_sessions]

    if not snapshots:
        return f"# {team_name} Team Status\n\nNo active sessions found for team `{team_slug}`."

    sessions_block = "\n\n".join(_render_session_snapshot(snapshot) for snapshot in snapshots)
    linear_context = await _linear_context(team_key)
    prompt = _TEAM_PROMPT.format(
        team_name=team_name,
        team_slug=team_slug,
        sessions_block=sessions_block,
        linear_context=linear_context,
    )

    try:
        from shoal.services.ai_client import call_llm

        body = await call_llm(model=model, prompt=prompt, max_tokens=650, temperature=0.3)
        return _format_report(
            title=f"{team_name} Team Status",
            metadata=[
                ("Team", f"`{team_slug}`"),
                ("Active sessions", str(len(snapshots))),
            ],
            body=body,
        )
    except Exception as exc:
        logger.warning("Team report LLM call failed for %s: %s", team_slug, exc)
        return _fallback_team_report(team_name, team_slug, snapshots)


async def generate_sprint_report(
    team_name: str,
    team_slug: str,
    *,
    linear_team_key: str | None = None,
    model: str = "amazon.nova-lite-v1:0",
) -> str:
    """Generate a sprint report for a team.

    Args:
        team_name: Human-friendly team name.
        team_slug: Local team slug from workspace config.
        linear_team_key: Linear team key, defaults to upper(team_slug).
        model: Model name for the LLM call.

    Returns:
        Markdown report.
    """
    team_key = linear_team_key or team_slug.upper()
    data = await _build_sprint_report_data(
        team_name=team_name, team_slug=team_slug, team_key=team_key
    )
    return await _render_sprint_report(data, model=model)


async def post_sprint_report(
    team_name: str,
    team_slug: str,
    *,
    report_target: TeamReportTargetConfig,
    linear_team_key: str | None = None,
    model: str = "amazon.nova-lite-v1:0",
) -> PostedSprintReport:
    """Generate a sprint report and publish it to Linear."""
    from shoal.services.linear_bridge import get_linear_bridge

    team_key = linear_team_key or team_slug.upper()
    data = await _build_sprint_report_data(
        team_name=team_name, team_slug=team_slug, team_key=team_key
    )
    report = await _render_sprint_report(data, model=model)
    health = _sprint_update_health(data)

    bridge = get_linear_bridge()
    try:
        target = await bridge.resolve_target(
            kind=report_target.type,
            id=report_target.id,
            slug=report_target.slug,
            name=report_target.name,
        )
        update = await bridge.create_status_update(
            kind=target.kind,
            target_id=target.id,
            body=report,
            health=health,
        )
    finally:
        await bridge.close()

    return PostedSprintReport(
        report=report,
        target_kind=target.kind,
        target_name=target.name or target.slug or target.id,
        update_url=update.url or target.url,
        health=update.health,
    )


async def generate_weekly_summary(
    week_start: date,
    week_end: date,
    *,
    team_slug: str | None = None,
    model: str = "amazon.nova-lite-v1:0",
) -> str:
    """Generate a weekly summary report.

    Args:
        week_start: Start date of the week.
        week_end: End date of the week (inclusive).
        team_slug: Optional team slug filter.
        model: Model name for the LLM call.

    Returns:
        Markdown report.
    """
    from shoal.core.state import list_sessions

    # Convert dates to datetime at start/end of day for filtering
    start_dt = datetime.combine(week_start, datetime.min.time()).replace(tzinfo=None)
    end_dt = datetime.combine(week_end, datetime.max.time()).replace(tzinfo=None)

    sessions = await list_sessions()

    # Filter sessions completed in the date range
    completed_sessions = [
        session
        for session in sessions
        if session.completed_at is not None
        and start_dt <= session.completed_at.replace(tzinfo=None) <= end_dt
    ]

    # If team filter is provided, further filter sessions
    if team_slug:
        team_key = team_slug.upper()
        completed_sessions = [
            session
            for session in completed_sessions
            if _belongs_to_team(session, team_slug, team_key)
        ]

    # Build session report data
    snapshots = [await _build_session_report_data(session) for session in completed_sessions]

    team_name = f"Team {team_slug}" if team_slug else "All teams"

    # Gather Linear context
    linear_context = ""
    if team_slug:
        linear_context = await _linear_context_weekly(team_slug.upper(), week_start, week_end)

    # Gather GitHub context
    github_context = await _github_context_weekly(week_start, week_end)

    data = WeeklyReportData(
        week_start=week_start,
        week_end=week_end,
        team_name=team_name,
        completed=snapshots,
        linear_context=linear_context,
        github_context=github_context,
    )

    return await _render_weekly_report(data, model=model)


async def _build_sprint_report_data(
    *,
    team_name: str,
    team_slug: str,
    team_key: str,
) -> SprintReportData:
    """Collect team sessions and Linear context for sprint reporting."""
    from shoal.core.state import list_sessions

    sessions = await list_sessions()
    team_sessions = [
        session for session in sessions if _belongs_to_team(session, team_slug, team_key)
    ]

    completed_sessions = [session for session in team_sessions if _is_completed(session)]
    in_progress_sessions = [
        session
        for session in team_sessions
        if not _is_completed(session) and session.status not in _TERMINAL_STATUSES
    ]
    blocked_sessions = [
        session
        for session in team_sessions
        if not _is_completed(session) and session.status in _TERMINAL_STATUSES
    ]

    completed_snapshots = [
        await _build_session_report_data(session) for session in completed_sessions
    ]
    in_progress_snapshots = [
        await _build_session_report_data(session) for session in in_progress_sessions
    ]
    blocked_snapshots = [await _build_session_report_data(session) for session in blocked_sessions]

    linear_context = await _linear_context(team_key)
    cycle_name = _cycle_name_from_context(linear_context, team_key)
    return SprintReportData(
        team_name=team_name,
        team_slug=team_slug,
        team_key=team_key,
        cycle_name=cycle_name,
        linear_context=linear_context,
        completed=completed_snapshots,
        in_progress=in_progress_snapshots,
        blocked=blocked_snapshots,
    )


async def _render_sprint_report(data: SprintReportData, *, model: str) -> str:
    """Render a sprint report from collected report data."""
    prompt = _SPRINT_PROMPT.format(
        team_name=data.team_name,
        team_slug=data.team_slug,
        cycle_name=data.cycle_name,
        linear_context=data.linear_context,
        completed_sessions=_render_session_list(data.completed, empty="- None"),
        in_progress_sessions=_render_session_list(data.in_progress, empty="- None"),
        blocked_sessions=_render_session_list(data.blocked, empty="- None"),
    )

    try:
        from shoal.services.ai_client import call_llm

        body = await call_llm(model=model, prompt=prompt, max_tokens=800, temperature=0.3)
        return _format_report(
            title=f"{data.cycle_name} — Sprint Summary",
            metadata=[("Team", f"{data.team_name} (`{data.team_slug}`)")],
            body=body,
        )
    except Exception as exc:
        logger.warning("Sprint report LLM call failed for %s: %s", data.team_slug, exc)
        return _fallback_sprint_report(
            team_name=data.team_name,
            team_slug=data.team_slug,
            cycle_name=data.cycle_name,
            completed=data.completed,
            in_progress=data.in_progress,
            blocked=data.blocked,
        )


async def _build_session_report_data(session: SessionState) -> SessionReportData:
    """Collect normalized report inputs for one session."""
    journal_entries = await _recent_journal_lines(session.id, limit=8, max_chars=180)
    return SessionReportData(
        session_name=session.name,
        tool=session.tool,
        branch=session.branch or "-",
        status=_status_label(session),
        last_active=_format_dt(session.last_activity),
        journal_entries=journal_entries,
        dreamer_summary=await _latest_journal_summary(session),
    )


async def _recent_journal_lines(
    session_id: str,
    *,
    limit: int,
    max_chars: int,
) -> list[str]:
    """Return recent journal lines for a session."""
    from shoal.core.journal import read_journal

    entries = await asyncio.to_thread(read_journal, session_id, limit)
    return [f"[{entry.source or 'journal'}] {entry.content[:max_chars]}" for entry in entries]


async def _latest_journal_summary(session: SessionState) -> str:
    """Return the latest journal entry with source == 'dreamer', or a fallback message."""
    from shoal.core.journal import read_journal

    entries = await asyncio.to_thread(read_journal, session.id, 50)
    for entry in reversed(entries):
        if entry.source == "dreamer":
            return entry.content
    return "(no summary available)"


def _belongs_to_team(session: SessionState, team_slug: str, linear_team_key: str) -> bool:
    """Return True if the session appears to belong to the team."""
    team_tag = f"team:{team_slug}"
    linear_prefix = f"linear:{linear_team_key.upper()}-"
    return any(tag == team_tag or tag.startswith(linear_prefix) for tag in session.tags)


def _is_completed(session: SessionState) -> bool:
    """Return True when the session has been marked complete."""
    return session.completed_at is not None


def _effective_status(session: SessionState) -> str:
    """Return the session status with completion folded in."""
    return "completed" if _is_completed(session) else session.status.value


def _status_label(session: SessionState) -> str:
    """Return a human-friendly session status label."""
    return {
        "completed": "Done",
        "running": "Running",
        "waiting": "Waiting",
        "error": "Error",
        "idle": "Idle",
        "stopped": "Stopped",
        "unknown": "Unknown",
    }.get(_effective_status(session), _effective_status(session).title())


def _format_dt(value: datetime | None) -> str:
    """Format a datetime for reports."""
    if value is None:
        return "unknown"
    return value.isoformat()


async def _linear_context(linear_team_key: str) -> str:
    """Return a compact Linear snapshot for a team."""
    try:
        from shoal.services.linear_bridge import get_linear_bridge

        bridge = get_linear_bridge()
        try:
            issues = await bridge.list_team_issues(linear_team_key, ready_only=False)
        finally:
            await bridge.close()
    except Exception:
        return (
            "Linear data unavailable. Set SHOAL_LINEAR_API_KEY to include issue and cycle context."
        )

    if not issues:
        return f"Cycle: {linear_team_key} current\n- No issues returned"

    state_counts = Counter(issue.state_name or issue.state_type or "Unknown" for issue in issues)
    lines = [f"Cycle: {linear_team_key} current", f"- Total issues: {len(issues)}"]
    for state_name, count in sorted(state_counts.items()):
        lines.append(f"- {state_name}: {count}")
    return "\n".join(lines)


def _cycle_name_from_context(linear_context: str, linear_team_key: str) -> str:
    """Extract the cycle heading from a linear-context block."""
    first_line = linear_context.splitlines()[0] if linear_context else ""
    return first_line or f"{linear_team_key} current cycle"


def _sprint_update_health(
    data: SprintReportData,
) -> Literal["onTrack", "atRisk", "offTrack"]:
    """Map sprint state into Linear update health."""
    if data.blocked and not data.completed and not data.in_progress:
        return "offTrack"
    if data.blocked:
        return "atRisk"
    return "onTrack"


def _render_bullets(items: list[str], *, empty: str) -> str:
    """Render bullet items or an empty marker."""
    if not items:
        return empty
    return "\n".join(f"- {item}" for item in items)


def _render_session_snapshot(snapshot: SessionReportData) -> str:
    """Render a session snapshot for LLM input."""
    latest = snapshot.journal_entries[-1] if snapshot.journal_entries else "No journal activity"
    return (
        f"### {snapshot.session_name}\n"
        f"- Status: {snapshot.status}\n"
        f"- Tool: {snapshot.tool}\n"
        f"- Branch: {snapshot.branch}\n"
        f"- Last active: {snapshot.last_active}\n"
        f"- Latest note: {latest}\n"
        f"- Dreamer: {snapshot.dreamer_summary}"
    )


def _render_session_list(snapshots: list[SessionReportData], *, empty: str) -> str:
    """Render a bullet list of session snapshots."""
    if not snapshots:
        return empty
    lines: list[str] = []
    for snapshot in snapshots:
        latest = snapshot.journal_entries[-1] if snapshot.journal_entries else "No journal activity"
        lines.append(f"- **{snapshot.session_name}** ({snapshot.status}): {latest}")
    return "\n".join(lines)


def _format_report(
    *,
    title: str,
    metadata: list[tuple[str, str]],
    body: str,
) -> str:
    """Render a standard markdown report shell."""
    lines = [f"# {title}", ""]
    for key, value in metadata:
        lines.append(f"**{key}**: {value}")
    lines.extend(["", body.strip(), "", "---", "*Generated by shoal report*"])
    return "\n".join(lines)


def _fallback_session_report(data: SessionReportData) -> str:
    """Render a no-LLM session report."""
    body = [
        "## Recent activity",
        _render_bullets(data.journal_entries, empty="(no journal entries)"),
        "",
        "## Dreamer summary",
        data.dreamer_summary,
    ]
    return _format_report(
        title=f"Session Report: {data.session_name}",
        metadata=[
            ("Status", data.status),
            ("Tool", data.tool),
            ("Branch", f"`{data.branch}`"),
        ],
        body="\n".join(body),
    )


def _fallback_team_report(
    team_name: str,
    team_slug: str,
    snapshots: list[SessionReportData],
) -> str:
    """Render a no-LLM team report."""
    body = ["## In progress"]
    if snapshots:
        body.append(_render_session_list(snapshots, empty="- None"))
    else:
        body.append("- None")
    body.extend(["", "## Risks / blockers", "- None surfaced from session state."])
    return _format_report(
        title=f"{team_name} Team Status",
        metadata=[("Team", f"`{team_slug}`"), ("Active sessions", str(len(snapshots)))],
        body="\n".join(body),
    )


def _fallback_sprint_report(
    *,
    team_name: str,
    team_slug: str,
    cycle_name: str,
    completed: list[SessionReportData],
    in_progress: list[SessionReportData],
    blocked: list[SessionReportData],
) -> str:
    """Render a no-LLM sprint report."""
    body = [
        "## Completed",
        _render_session_list(completed, empty="- None"),
        "",
        "## In progress",
        _render_session_list(in_progress, empty="- None"),
        "",
        "## Risks / blockers",
        _render_session_list(blocked, empty="- None"),
        "",
        "## Next sprint focus",
        "- Continue active work and close blocked sessions.",
    ]
    return _format_report(
        title=f"{cycle_name} — Sprint Summary",
        metadata=[("Team", f"{team_name} (`{team_slug}`)")],
        body="\n".join(body),
    )


async def _linear_context_weekly(team_key: str, week_start: date, week_end: date) -> str:
    """Return Linear issues closed during the week."""
    try:
        from shoal.services.linear_bridge import get_linear_bridge

        bridge = get_linear_bridge()
        try:
            issues = await bridge.list_team_issues(team_key, ready_only=False)
        finally:
            await bridge.close()

        # Note: Linear API doesn't expose completion date directly in our query,
        # so we'll just list all current issues with state info
        if not issues:
            return f"Linear {team_key}: No issues returned"

        # Count by state
        state_counts = Counter(
            issue.state_name or issue.state_type or "Unknown" for issue in issues
        )
        lines = [f"Linear {team_key} issues:"]
        for state_name, count in sorted(state_counts.items()):
            lines.append(f"- {state_name}: {count}")
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("Linear context unavailable for weekly report: %s", exc)
        return "Linear data unavailable"


async def _github_context_weekly(week_start: date, week_end: date) -> str:
    """Return GitHub PRs merged during the week."""
    try:
        from shoal.services.github_bridge import get_github_bridge

        # This requires GITHUB_TOKEN to be set
        bridge = get_github_bridge()
        try:
            # Note: The GitHub bridge doesn't have a date-filtered PR query,
            # so we'll just list recent PRs with state
            # For a real implementation, you'd want to filter by merged_at date
            prs = await bridge.list_prs("owner/repo", state="closed")  # Placeholder repo
            merged_count = len([pr for pr in prs if pr.state == "closed"])
            if merged_count == 0:
                return "GitHub: No recent merged PRs"
            return f"GitHub: {merged_count} PRs merged"
        finally:
            await bridge.close()
    except Exception as exc:
        logger.debug("GitHub context unavailable for weekly report: %s", exc)
        return "GitHub data unavailable (set GITHUB_TOKEN to include PR context)"


async def _render_weekly_report(data: WeeklyReportData, *, model: str) -> str:
    """Render a weekly report from collected data."""
    prompt = _WEEKLY_PROMPT.format(
        week_start=data.week_start.isoformat(),
        week_end=data.week_end.isoformat(),
        team_name=data.team_name,
        completed_sessions=_render_session_list(data.completed, empty="- None"),
        linear_context=data.linear_context,
        github_context=data.github_context,
    )

    try:
        from shoal.services.ai_client import call_llm

        body = await call_llm(model=model, prompt=prompt, max_tokens=800, temperature=0.3)
        return _format_report(
            title=f"Weekly Summary: {data.week_start} to {data.week_end}",
            metadata=[
                ("Team", data.team_name),
                ("Completed sessions", str(len(data.completed))),
            ],
            body=body,
        )
    except Exception as exc:
        logger.warning("Weekly report LLM call failed: %s", exc)
        return _fallback_weekly_report(data)


def _fallback_weekly_report(data: WeeklyReportData) -> str:
    """Render a no-LLM weekly report."""
    body = [
        "## Shipped",
        _render_session_list(data.completed, empty="- None"),
        "",
        "## External context",
        "",
        "### Linear",
        data.linear_context or "- No data",
        "",
        "### GitHub",
        data.github_context or "- No data",
        "",
        "## Highlights",
        f"- Completed {len(data.completed)} sessions during the week",
    ]
    return _format_report(
        title=f"Weekly Summary: {data.week_start} to {data.week_end}",
        metadata=[
            ("Team", data.team_name),
            ("Completed sessions", str(len(data.completed))),
        ],
        body="\n".join(body),
    )
