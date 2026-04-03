"""Import/export conversations between Shoal journals and Lobster Party QMD format.

Lobster Party stores conversations as weekly-bucketed pairs:
    conversations/{year}-W{week}/{turn_id}.md    # YAML frontmatter + markdown
    conversations/{year}-W{week}/{turn_id}.json  # TurnRecord fields

This module provides bidirectional conversion between QMD turns and Shoal journal entries.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from shoal.core.conversations import (
    claw_turn_to_event,
    journal_entry_to_event,
    render_event_as_journal_content,
)

logger = logging.getLogger("shoal.lobster_conversations")


@dataclass
class LobsterTurn:
    """A single turn from a Lobster conversation.

    Attributes:
        id: Unique turn identifier.
        timestamp: When the turn occurred (UTC).
        claw_id: The Lobster runtime that processed this turn.
        event_id: Optional event/correlation ID.
        prompt: The user's prompt text.
        response: The model's response text.
        model: Model identifier (e.g., "claude-sonnet-4-20250514").
        tokens: Total token count (prompt + response), if available.
        cost_usd: Cost in USD, if available.
    """

    id: str
    timestamp: datetime
    claw_id: str
    event_id: str
    prompt: str
    response: str
    model: str
    tokens: int | None = None
    prompt_tokens: int | None = None
    response_tokens: int | None = None
    cost_usd: float | None = None
    thinking: str | None = None
    prompt_summary: str | None = None
    response_summary: str | None = None
    thinking_summary: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json_record(cls, record: dict[str, object]) -> LobsterTurn:
        """Create a LobsterTurn from a QMD JSON TurnRecord.

        Args:
            record: Dict with QMD TurnRecord fields.

        Returns:
            LobsterTurn instance with mapped fields.
        """
        # Parse timestamp - handle both ISO format and Unix timestamp
        ts_raw = record.get("timestamp", "")
        if isinstance(ts_raw, (int, float)):
            timestamp = datetime.fromtimestamp(ts_raw, tz=UTC)
        else:
            ts_str = str(ts_raw).replace("Z", "+00:00")
            timestamp = datetime.fromisoformat(ts_str)

        # Normalize timezone to UTC
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        # Calculate total tokens if separate counts provided
        prompt_tokens = cast(int, record.get("prompt_tokens", 0) or 0)
        response_tokens = cast(int, record.get("response_tokens", 0) or 0)
        tokens = record.get("tokens")
        if tokens is None and (prompt_tokens or response_tokens):
            tokens = prompt_tokens + response_tokens

        cost_usd = record.get("cost_usd")

        return cls(
            id=str(record.get("id", "")),
            timestamp=timestamp,
            claw_id=str(record.get("claw_id", "")),
            event_id=str(record.get("event_id", "")),
            prompt=str(record.get("prompt", "")),
            response=str(record.get("response", "")),
            model=str(record.get("model", "")),
            tokens=cast(int, tokens) if tokens is not None else None,
            prompt_tokens=prompt_tokens or None,
            response_tokens=response_tokens or None,
            cost_usd=cast(float, cost_usd) if cost_usd is not None else None,
            thinking=str(record.get("thinking", "")) or None,
            prompt_summary=str(record.get("prompt_summary", "")) or None,
            response_summary=str(record.get("response_summary", "")) or None,
            thinking_summary=str(record.get("thinking_summary", "")) or None,
            metadata=cast("dict[str, Any]", record.get("metadata") or {}),
        )


def _parse_iso_week_dir(dir_name: str) -> tuple[int, int] | None:
    """Parse year and week number from directory name like '2025-W03'.

    Args:
        dir_name: Directory name in YYYY-Www format.

    Returns:
        Tuple of (year, week_number) or None if invalid format.
    """
    match = re.match(r"(\d{4})-W(\d{2})", dir_name)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def read_qmd_turns(
    conversations_dir: Path,
    since: datetime | None = None,
) -> list[LobsterTurn]:
    """Read all QMD turn records from a conversations directory.

    Scans weekly subdirectories (YYYY-Www format) for .json turn files,
    loads and parses them into LobsterTurn objects.

    Args:
        conversations_dir: Path to the conversations root directory.
        since: Optional cutoff - only return turns after this timestamp.

    Returns:
        List of LobsterTurn objects, sorted by timestamp (oldest first).
    """
    if not conversations_dir.exists():
        logger.debug("Conversations directory does not exist: %s", conversations_dir)
        return []

    turns: list[LobsterTurn] = []

    # Scan weekly subdirectories
    for week_dir in sorted(conversations_dir.iterdir()):
        if not week_dir.is_dir():
            continue

        week_info = _parse_iso_week_dir(week_dir.name)
        if week_info is None:
            logger.debug("Skipping non-week directory: %s", week_dir.name)
            continue

        # Load all .json turn files in this week
        for json_file in sorted(week_dir.glob("*.json")):
            try:
                record_data = json.loads(json_file.read_text())
                turn = LobsterTurn.from_json_record(record_data)

                # Filter by timestamp if since is provided
                if since is not None and turn.timestamp <= since:
                    continue

                turns.append(turn)
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning("Failed to parse turn file %s: %s", json_file, e)

    # Sort by timestamp (oldest first)
    turns.sort(key=lambda t: t.timestamp)
    return turns


def turns_to_journal_entries(turns: list[LobsterTurn]) -> str:
    """Convert a list of LobsterTurns into journal entry markdown."""
    entries: list[str] = []

    for turn in turns:
        event = claw_turn_to_event(turn, session_name=turn.claw_id)
        entry = (
            f"## {turn.timestamp.isoformat()} — claw-sync\n\n"
            f"{render_event_as_journal_content(event, actor=turn.claw_id)}\n\n"
            "---\n"
        )
        entries.append(entry)

    return "\n".join(entries)


def _get_iso_week_dir(timestamp: datetime) -> str:
    """Get the ISO week directory name for a timestamp.

    Args:
        timestamp: Datetime to convert.

    Returns:
        Directory name in YYYY-Www format.
    """
    iso_cal = timestamp.isocalendar()
    return f"{iso_cal.year}-W{iso_cal.week:02d}"


def export_journal_to_qmd(
    journal_path: Path,
    output_dir: Path,
    session_name: str,
) -> int:
    """Write journal entries as QMD-compatible markdown+JSON pairs.

    Parses journal entries and writes them as QMD turn files:
        {output_dir}/{year}-W{week}/{turn_id}.md
        {output_dir}/{year}-W{week}/{turn_id}.json

    Args:
        journal_path: Path to the Shoal journal file.
        output_dir: Root directory for QMD conversations output.
        session_name: Session name to use in claw_id field.

    Returns:
        Number of turns exported.
    """
    from shoal.core.journal import _parse_journal

    if not journal_path.exists():
        logger.debug("Journal file does not exist: %s", journal_path)
        return 0

    text = journal_path.read_text()
    entries = _parse_journal(text)

    # Filter to only claw-sync entries
    claw_entries = [e for e in entries if "claw-sync" in e.source.lower()]

    if not claw_entries:
        logger.debug("No claw-sync entries found in journal")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    exported = 0

    for entry in claw_entries:
        event = journal_entry_to_event(entry, session_name, session_name)
        turn_id = event.id
        week_dir_name = _get_iso_week_dir(event.timestamp)
        week_path = output_dir / week_dir_name
        week_path.mkdir(parents=True, exist_ok=True)

        claw_id = str(event.metadata.get("claw_id") or session_name)
        prompt = event.prompt or event.content_markdown or event.summary or ""
        response = event.response or ""
        prompt_summary = event.prompt_summary or prompt[:100]
        response_summary = event.response_summary or response[:100]

        record: dict[str, object] = {
            "id": turn_id,
            "timestamp": event.timestamp.isoformat(),
            "claw_id": claw_id,
            "event_id": event.event_id or turn_id,
            "prompt": prompt,
            "response": response,
            "thinking": event.thinking or "",
            "prompt_summary": prompt_summary,
            "response_summary": response_summary,
            "model": event.model or "unknown",
            "prompt_tokens": event.prompt_tokens or 0,
            "response_tokens": event.response_tokens or 0,
            "cost_usd": event.cost_usd or 0.0,
            "metadata": {**event.metadata, "source": "shoal-journal-export"},
        }

        json_file = week_path / f"{turn_id}.json"
        json_file.write_text(json.dumps(record, indent=2))

        md_content = f"""---
turn_id: {turn_id}
timestamp: {event.timestamp.isoformat()}
claw_id: {claw_id}
event_id: {event.event_id or turn_id}
---

# Turn {turn_id}

**Prompt:**

{prompt}

**Response:**

{response}
"""
        md_file = week_path / f"{turn_id}.md"
        md_file.write_text(md_content)

        exported += 1

    return exported
