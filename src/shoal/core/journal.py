"""Append-only session journals stored as flat markdown files.

Each session gets a ``<session_id>.md`` file under ``state_dir() / "journals"``.
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

import shoal
from shoal.core.config import state_dir

logger = logging.getLogger("shoal.journal")

MAX_JOURNAL_SIZE_BYTES = 1_048_576  # 1 MB advisory threshold


@dataclass(frozen=True)
class JournalEntry:
    """A single journal entry."""

    timestamp: datetime
    source: str
    content: str


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


def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter from the beginning of text."""
    return _FRONTMATTER_RE.sub("", text)


def read_frontmatter(session_id: str) -> dict[str, str] | None:
    """Read YAML frontmatter from a journal file. Returns None if absent."""
    path = journal_path(session_id)
    if not path.exists():
        return None
    text = path.read_text()
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


_ENTRY_RE = re.compile(
    r"^## (\d{4}-\d{2}-\d{2}T[\d:.+Z-]+)\s*\[([^\]]*)\]\s*\n\n(.*?)(?=\n---|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _journals_dir() -> Path:
    return state_dir() / "journals"


def journal_path(session_id: str) -> Path:
    """Return the journal file path for a session."""
    return _journals_dir() / f"{session_id}.md"


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
