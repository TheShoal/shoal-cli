"""Append-only session journals stored as flat markdown files.

Each session gets a ``<session_id>.md`` file under ``~/.local/share/shoal/journals/``.
Entries follow the format::

    ## <ISO timestamp> [<source>]

    <content>

    ---

Journals created with metadata include Obsidian-compatible YAML frontmatter.
"""

from __future__ import annotations

import logging
import platform
import re
import shutil
import socket
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import shoal
from shoal.core.config import data_dir

logger = logging.getLogger("shoal.journal")

MAX_JOURNAL_SIZE_BYTES = 1_048_576  # 1 MB advisory threshold


@dataclass(frozen=True)
class JournalEntry:
    """A single journal entry."""

    timestamp: datetime
    source: str
    content: str


@dataclass
class SessionOutcome:
    """Structured outcome recorded at session completion."""

    session_id: str
    session_name: str
    goal: str
    commands_failed: list[str]
    commands_worked: list[str]
    root_causes: list[str]
    fixes_applied: list[str]
    lessons: list[str]
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            object.__setattr__(self, "timestamp", datetime.now(tz=UTC).isoformat())


@dataclass(frozen=True)
class JournalMetadata:
    """Metadata written as YAML frontmatter on journal creation."""

    session_id: str
    session_name: str
    tool: str = ""
    branch: str = ""
    worktree: str = ""
    git_root: str = ""
    hostname: str = ""
    platform_name: str = ""
    python_version: str = ""
    shoal_version: str = ""


def build_journal_metadata(session: object) -> JournalMetadata:
    """Build metadata from a SessionState (or any object with matching attrs).

    Uses only in-memory lookups — no I/O, safe to call from any context.
    """
    v = sys.version_info
    return JournalMetadata(
        session_id=getattr(session, "id", ""),
        session_name=getattr(session, "name", ""),
        tool=getattr(session, "tool", ""),
        branch=getattr(session, "branch", ""),
        worktree=getattr(session, "worktree", ""),
        git_root=getattr(session, "path", ""),
        hostname=socket.gethostname(),
        platform_name=platform.system(),
        python_version=f"{v.major}.{v.minor}.{v.micro}",
        shoal_version=shoal.__version__,
    )


def _sanitize_tag(value: str) -> str:
    """Lowercase, replace non-alphanumeric with hyphens, strip edges."""
    return re.sub(r"[^a-z0-9-]", "-", value.lower()).strip("-")


def _render_frontmatter(meta: JournalMetadata) -> str:
    """Render Obsidian-compatible YAML frontmatter."""
    created = datetime.now(tz=UTC).isoformat()

    tags = ["shoal"]
    for val in (meta.session_name, meta.tool):
        tag = _sanitize_tag(val)
        if tag and tag not in tags:
            tags.append(tag)

    lines = ["---"]
    lines.append(f"session_id: {meta.session_id}")
    lines.append(f"title: {meta.session_name}")
    lines.append(f"aliases: [{meta.session_name}]")
    if meta.tool:
        lines.append(f"tool: {meta.tool}")
    if meta.branch:
        lines.append(f"branch: {meta.branch}")
    if meta.worktree:
        lines.append(f"worktree: {meta.worktree}")
    if meta.git_root:
        lines.append(f"git_root: {meta.git_root}")
    lines.append(f"created: {created}")
    tags_str = ", ".join(tags)
    lines.append(f"tags: [{tags_str}]")
    if meta.hostname:
        lines.append(f"hostname: {meta.hostname}")
    if meta.platform_name:
        lines.append(f"platform: {meta.platform_name}")
    if meta.python_version:
        lines.append(f"python: {meta.python_version}")
    if meta.shoal_version:
        lines.append(f"shoal_version: {meta.shoal_version}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


def _parse_frontmatter_text(text: str) -> dict[str, str] | None:
    """Parse YAML frontmatter from raw journal text.

    Returns a string-valued dict of key→value pairs, or None if no
    frontmatter block is present.  Values are returned as raw strings
    (YAML inline lists such as ``[a, b]`` are not decoded here).
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    block = m.group(0)
    result: dict[str, str] = {}
    for line in block.splitlines():
        if line == "---":
            continue
        if ": " in line:
            key, value = line.split(": ", 1)
            result[key.strip()] = value.strip()
    return result


def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter from the beginning of text."""
    return _FRONTMATTER_RE.sub("", text)


def read_frontmatter(session_id: str) -> dict[str, str] | None:
    """Read YAML frontmatter from a journal file. Returns None if absent."""
    path = journal_path(session_id)
    if not path.exists():
        return None
    return _parse_frontmatter_text(path.read_text())


_ENTRY_RE = re.compile(
    r"^## (\d{4}-\d{2}-\d{2}T[\d:.+Z-]+)\s*\[([^\]]*)\]\s*\n\n(.*?)(?=\n---|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _journals_dir() -> Path:
    return data_dir() / "journals"


def journal_path(session_id: str) -> Path:
    """Return the journal file path for a session."""
    return _journals_dir() / f"{session_id}.md"


def handoff_artifact_path(session_id: str) -> Path:
    """Return the persisted handoff artifact path for a session."""
    return _journals_dir() / "handoffs" / f"{session_id}.md"


def journal_exists(session_id: str) -> bool:
    """Check if a journal exists for the given session."""
    return journal_path(session_id).exists()


def append_entry(
    session_id: str,
    content: str,
    source: str = "",
    *,
    metadata: JournalMetadata | None = None,
) -> Path:
    """Append a new entry to a session journal. Creates the file if needed.

    On first write (file doesn't exist), writes YAML frontmatter if metadata is provided.
    """
    path = journal_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    is_new = not path.exists()

    timestamp = datetime.now(tz=UTC).isoformat()
    block = f"## {timestamp} [{source}]\n\n{content}\n\n---\n\n"

    with open(path, "a") as f:
        if is_new and metadata is not None:
            f.write(_render_frontmatter(metadata))
        f.write(block)

    # Advisory size warning (best-effort)
    try:
        size = path.stat().st_size
        if size > MAX_JOURNAL_SIZE_BYTES:
            logger.warning(
                "Journal %s exceeds %d bytes (%d bytes). Consider archiving.",
                session_id,
                MAX_JOURNAL_SIZE_BYTES,
                size,
            )
    except OSError:
        pass

    return path


def _parse_journal(text: str) -> list[JournalEntry]:
    """Parse journal markdown into a list of entries."""
    text = _strip_frontmatter(text)
    entries: list[JournalEntry] = []
    for match in _ENTRY_RE.finditer(text):
        ts_str, src, body = match.group(1), match.group(2), match.group(3)
        ts = datetime.fromisoformat(ts_str)
        entries.append(JournalEntry(timestamp=ts, source=src, content=body.strip()))
    return entries


def read_journal(session_id: str, limit: int | None = None) -> list[JournalEntry]:
    """Read journal entries for a session. Returns newest-last.

    Args:
        session_id: The session ID to read the journal for.
        limit: If set, return only the last *limit* entries.
    """
    path = journal_path(session_id)
    if not path.exists():
        return []
    text = path.read_text()
    entries = _parse_journal(text)
    if limit is not None:
        entries = entries[-limit:]
    return entries


def delete_journal(session_id: str) -> bool:
    """Delete a session journal. Returns True if it existed."""
    path = journal_path(session_id)
    if path.exists():
        path.unlink()
        return True
    return False


def archived_journal_path(session_id: str) -> Path:
    """Return the archived journal file path for a session."""
    return _journals_dir() / "archive" / f"{session_id}.md"


def read_archived_journal(session_id: str, limit: int | None = None) -> list[JournalEntry]:
    """Read entries from an archived journal. Returns newest-last.

    Args:
        session_id: The session ID to read the archived journal for.
        limit: If set, return only the last *limit* entries.
    """
    path = archived_journal_path(session_id)
    if not path.exists():
        return []
    text = path.read_text()
    entries = _parse_journal(text)
    if limit is not None:
        entries = entries[-limit:]
    return entries


def find_archived_session_id(identifier: str) -> str | None:
    """Find an archived session ID by scanning frontmatter for a name match.

    Used as fallback when DB resolution fails (session already deleted).
    Scans the archive directory for a journal whose frontmatter ``title`` or
    ``aliases`` field matches *identifier* (case-insensitive).

    Args:
        identifier: Session name or alias to search for.

    Returns:
        Session ID (file stem) if found, None otherwise.
    """
    archive_dir = _journals_dir() / "archive"
    if not archive_dir.exists():
        return None
    identifier_lower = identifier.lower()
    for journal_file in archive_dir.glob("*.md"):
        text = journal_file.read_text()
        # Quick pre-check before parsing to skip unrelated files
        if identifier_lower not in text.lower():
            continue
        frontmatter = _parse_frontmatter_text(text)
        if frontmatter is None:
            continue
        title = frontmatter.get("title", "")
        aliases_raw = frontmatter.get("aliases", "")
        # aliases stored as YAML inline list: "[name1, name2]" — decode manually
        if aliases_raw.startswith("[") and aliases_raw.endswith("]"):
            aliases: list[str] = [a.strip() for a in aliases_raw[1:-1].split(",") if a.strip()]
        elif aliases_raw:
            aliases = [aliases_raw]
        else:
            aliases = []
        candidates = [title, *aliases]
        if any(c.lower() == identifier_lower for c in candidates if c):
            return journal_file.stem
    return None


@dataclass(frozen=True)
class JournalSearchResult:
    """A journal entry with its session ID."""

    session_id: str
    entry: JournalEntry


def search_journals(query: str, limit: int = 10) -> list[JournalSearchResult]:
    """Search across all session journals for entries matching *query*.

    Performs case-insensitive substring matching on entry content.
    Returns up to *limit* results, newest first.
    """
    journals_dir = _journals_dir()
    if not journals_dir.exists():
        return []

    query_lower = query.lower()
    results: list[JournalSearchResult] = []

    for journal_file in journals_dir.glob("*.md"):
        session_id = journal_file.stem
        text = journal_file.read_text()
        entries = _parse_journal(text)
        results.extend(
            JournalSearchResult(session_id=session_id, entry=entry)
            for entry in entries
            if query_lower in entry.content.lower()
        )

    # Sort newest first
    results.sort(key=lambda r: r.entry.timestamp, reverse=True)
    return results[:limit]


def write_handoff_artifact(session_id: str, artifact: HandoffArtifact) -> Path:
    """Write a generated handoff artifact under the journals tree and return its path."""
    path = handoff_artifact_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(artifact.to_markdown())
    return path


def archive_journal(session_id: str) -> bool:
    """Archive a session journal. Returns True if it existed and was archived."""
    path = journal_path(session_id)
    if not path.exists():
        return False
    archive_dir = _journals_dir() / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / f"{session_id}.md"
    shutil.move(str(path), str(dest))
    return True


def outcome_path(session_id: str) -> Path:
    """Return the outcome file path for a session."""
    return _journals_dir() / "outcomes" / f"{session_id}.md"


def save_outcome(outcome: SessionOutcome, journal_dir: Path | None = None) -> Path:
    """Save a SessionOutcome as a dated markdown file with YAML frontmatter.

    Args:
        outcome: The outcome to save.
        journal_dir: If provided, use this directory instead of the default journals dir.
                     Used for testing or custom storage locations.
    """
    if journal_dir is None:
        journal_dir = _journals_dir()

    outcomes_dir = journal_dir / "outcomes"
    outcomes_dir.mkdir(parents=True, exist_ok=True)

    # Build frontmatter
    lines = ["---"]
    lines.append(f"session_id: {outcome.session_id}")
    lines.append(f"session_name: {outcome.session_name}")
    lines.append(f"timestamp: {outcome.timestamp}")
    lines.append("tags: [shoal, session-outcome]")
    lines.append("---")
    lines.append("")

    # Build body
    lines.append(f"# Session Outcome: {outcome.session_name}")
    lines.append("")
    lines.append(f"**Session ID**: `{outcome.session_id}`  ")
    lines.append(f"**Completed**: {outcome.timestamp}")
    lines.append("")

    lines.append("## Goal")
    lines.append("")
    lines.append(outcome.goal)
    lines.append("")

    if outcome.commands_failed:
        lines.append("## Commands Failed")
        lines.append("")
        lines.extend(f"- `{cmd}`" for cmd in outcome.commands_failed)
        lines.append("")

    if outcome.commands_worked:
        lines.append("## Commands Worked")
        lines.append("")
        lines.extend(f"- `{cmd}`" for cmd in outcome.commands_worked)
        lines.append("")

    if outcome.root_causes:
        lines.append("## Root Causes")
        lines.append("")
        lines.extend(f"- {cause}" for cause in outcome.root_causes)
        lines.append("")

    if outcome.fixes_applied:
        lines.append("## Fixes Applied")
        lines.append("")
        lines.extend(f"- {fix}" for fix in outcome.fixes_applied)
        lines.append("")

    if outcome.lessons:
        lines.append("## Lessons Learned")
        lines.append("")
        lines.extend(f"- {lesson}" for lesson in outcome.lessons)
        lines.append("")

    path = outcomes_dir / f"{outcome.session_id}.md"
    path.write_text("\n".join(lines))
    logger.info("Session outcome saved: %s", path)
    return path


@dataclass(frozen=True)
class HandoffArtifact:
    """Structured handoff summary for a session."""

    session_name: str
    tool: str
    branch: str
    status: str
    urgency_label: str
    time_in_status: str
    last_active: str
    recent_entries: list[JournalEntry]
    transition_summary: list[str]
    suggested_next: str
    worktree: str = ""
    git_diff_summary: str = ""
    commit_count: int = 0
    dreamer_summary: str = ""
    workflow_summary: str = ""

    def to_markdown(self) -> str:
        """Render as a markdown handoff document."""
        lines: list[str] = []
        lines.append(f"# Handoff: {self.session_name}")
        lines.append("")
        lines.append("## Status")
        lines.append("")
        lines.append(f"- **Session**: `{self.session_name}`")
        lines.append(f"- **Tool**: {self.tool}")
        lines.append(f"- **Branch**: `{self.branch or '-'}`")
        lines.append(f"- **Status**: {self.urgency_label}")
        lines.append(f"- **Time in status**: {self.time_in_status}")
        lines.append(f"- **Last active**: {self.last_active}")
        if self.worktree:
            lines.append(f"- **Worktree**: `{self.worktree}`")
        lines.append("")
        if self.git_diff_summary or self.commit_count:
            lines.append("## Git context")
            lines.append("")
            if self.commit_count:
                lines.append(f"- **Commits**: {self.commit_count}")
            if self.git_diff_summary:
                lines.append(f"- **Changes**: {self.git_diff_summary}")
            lines.append("")
        if self.transition_summary:
            lines.append("## Recent transitions")
            lines.append("")
            lines.extend(f"- {t}" for t in self.transition_summary)
            lines.append("")
        if self.recent_entries:
            lines.append("## Recent journal")
            lines.append("")
            for entry in self.recent_entries:
                ts = entry.timestamp.strftime("%Y-%m-%d %H:%M")
                src = f" [{entry.source}]" if entry.source else ""
                lines.append(f"### {ts}{src}")
                lines.append("")
                lines.append(entry.content.strip())
                lines.append("")
        if self.dreamer_summary:
            lines.append("## Dreamer summary")
            lines.append("")
            lines.append(self.dreamer_summary.strip())
            lines.append("")
        if self.workflow_summary:
            lines.append("## Workflow summary")
            lines.append("")
            lines.append(self.workflow_summary.strip())
            lines.append("")
        lines.append("## Suggested next action")
        lines.append("")
        lines.append(self.suggested_next)
        lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "session_name": self.session_name,
            "tool": self.tool,
            "branch": self.branch,
            "status": self.status,
            "urgency_label": self.urgency_label,
            "time_in_status": self.time_in_status,
            "last_active": self.last_active,
            "worktree": self.worktree,
            "git_diff_summary": self.git_diff_summary,
            "commit_count": self.commit_count,
            "transition_summary": self.transition_summary,
            "suggested_next": self.suggested_next,
            "dreamer_summary": self.dreamer_summary,
            "workflow_summary": self.workflow_summary,
            "recent_entries": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "source": e.source,
                    "content": e.content,
                }
                for e in self.recent_entries
            ],
        }


def generate_handoff(
    session: object,
    entries: list[JournalEntry],
    transitions: list[dict[str, Any]],
    *,
    recent_entry_count: int = 5,
    now: datetime | None = None,
    blocked_after_minutes: int = 5,
    stale_after_minutes: int = 30,
) -> HandoffArtifact:
    """Build a HandoffArtifact from a session and its journal data.

    Pure function — no I/O.  All data is passed in by the caller.

    Args:
        session: A SessionState (or any object with matching attributes).
        entries: Journal entries for the session (newest-last).
        transitions: Status transition dicts from db.get_status_transitions().
        recent_entry_count: How many recent journal entries to include.
        now: Current UTC time; defaults to datetime.now(UTC).
    """
    from shoal.core.urgency import UrgencyTier, derive_urgency
    from shoal.models.state import SessionState

    if now is None:
        now = datetime.now(UTC)

    # Urgency label.
    urgency_label = getattr(session, "status", "unknown")
    time_in_status = "-"
    suggested_next = "Resume work or check session state."

    if isinstance(session, SessionState):
        tier, urgency_label = derive_urgency(
            session,
            now=now,
            blocked_after_minutes=blocked_after_minutes,
            stale_after_minutes=stale_after_minutes,
        )
        since = session.status_since
        if since.tzinfo is None:
            since = since.replace(tzinfo=UTC)
        age_minutes = (now - since).total_seconds() / 60
        if age_minutes < 60:
            time_in_status = f"{int(age_minutes)}m"
        elif age_minutes < 1440:
            time_in_status = f"{age_minutes / 60:.0f}h"
        else:
            time_in_status = f"{age_minutes / 1440:.0f}d"

        match tier:
            case UrgencyTier.error:
                suggested_next = (
                    f"Session is in error state.  Run `shoal attach {session.name}` "
                    "to inspect the terminal and resolve the issue."
                )
            case UrgencyTier.blocked:
                suggested_next = (
                    f"Session has been waiting {time_in_status} and needs input.  "
                    f"Run `shoal attach {session.name}` or approve via `shoal send {session.name}`."
                )
            case UrgencyTier.waiting:
                suggested_next = (
                    f"Session is waiting for approval.  "
                    f"Run `shoal attach {session.name}` or `shoal send {session.name}`."
                )
            case UrgencyTier.review:
                suggested_next = (
                    f"Session is marked review-ready.  Inspect changes with"
                    f" `shoal attach {session.name}` then merge or request changes."
                )
            case UrgencyTier.running:
                suggested_next = "No immediate action needed.  Session is actively running."
            case UrgencyTier.stale:
                suggested_next = (
                    f"Verify the session is still making progress.  "
                    f"Run `shoal attach {session.name}` to inspect."
                )
            case UrgencyTier.idle:
                suggested_next = "Session is idle.  Resume work when ready."
            case UrgencyTier.stopped:
                suggested_next = (
                    "Session is stopped.  Review the journal and decide"
                    " whether to archive or restart."
                )
            case _:
                suggested_next = "Status unknown.  Check session state with `shoal info`."

    # Last active timestamp.
    last_activity = getattr(session, "last_activity", None)
    last_active = last_activity.strftime("%Y-%m-%d %H:%M UTC") if last_activity else "-"

    # Transition summary — newest-first, last 5.
    transition_summary: list[str] = []
    for t in transitions[:5]:
        ts_raw = t.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_raw).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            ts = ts_raw
        from_s = t.get("from_status", "?")
        to_s = t.get("to_status", "?")
        transition_summary.append(f"{ts}  {from_s} \u2192 {to_s}")

    # Recent journal entries.
    recent = entries[-recent_entry_count:] if entries else []

    # Git context — best-effort, only when worktree is available.
    wt = getattr(session, "worktree", "") or ""
    git_diff_summary = ""
    commit_count = 0
    if wt:
        try:
            from shoal.core.git import commit_count_since_main, diff_stat

            git_diff_summary = diff_stat(wt)
            commit_count = commit_count_since_main(wt)
        except Exception:
            logger.debug("git context unavailable for handoff", exc_info=True)

    return HandoffArtifact(
        session_name=getattr(session, "name", ""),
        tool=getattr(session, "tool", ""),
        branch=getattr(session, "branch", ""),
        status=str(urgency_label),
        urgency_label=str(urgency_label),
        time_in_status=time_in_status,
        last_active=last_active,
        recent_entries=recent,
        transition_summary=transition_summary,
        suggested_next=suggested_next,
        worktree=wt,
        git_diff_summary=git_diff_summary,
        commit_count=commit_count,
    )
