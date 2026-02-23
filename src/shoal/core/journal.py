"""Append-only session journals stored as flat markdown files.

Each session gets a ``<session_id>.md`` file under ``state_dir() / "journals"``.
Entries follow the format::

    ## <ISO timestamp> [<source>]

    <content>

    ---
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from shoal.core.config import state_dir


@dataclass(frozen=True)
class JournalEntry:
    """A single journal entry."""

    timestamp: datetime
    source: str
    content: str


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


def append_entry(session_id: str, content: str, source: str = "") -> Path:
    """Append a new entry to a session journal. Creates the file if needed."""
    path = journal_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(tz=UTC).isoformat()
    block = f"## {timestamp} [{source}]\n\n{content}\n\n---\n\n"

    with open(path, "a") as f:
        f.write(block)

    return path


def _parse_journal(text: str) -> list[JournalEntry]:
    """Parse journal markdown into a list of entries."""
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
