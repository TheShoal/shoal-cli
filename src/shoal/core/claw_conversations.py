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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("shoal.claw_conversations")


@dataclass
class ClawTurn:
    """A single turn from a Claw conversation.

    Attributes:
        id: Unique turn identifier.
        timestamp: When the turn occurred (UTC).
        claw_id: The Claw runtime that processed this turn.
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
    cost_usd: float | None = None

    @classmethod
    def from_json_record(cls, record: dict[str, object]) -> ClawTurn:
        """Create a ClawTurn from a QMD JSON TurnRecord.

        Args:
            record: Dict with QMD TurnRecord fields.

        Returns:
            ClawTurn instance with mapped fields.
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
        tokens = record.get("tokens")
        if tokens is None:
            prompt_tokens = int(record.get("prompt_tokens", 0) or 0)
            response_tokens = int(record.get("response_tokens", 0) or 0)
            if prompt_tokens or response_tokens:
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
            tokens=int(tokens) if tokens is not None else None,
            cost_usd=float(cost_usd) if cost_usd is not None else None,
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
) -> list[ClawTurn]:
    """Read all QMD turn records from a conversations directory.

    Scans weekly subdirectories (YYYY-Www format) for .json turn files,
    loads and parses them into ClawTurn objects.

    Args:
        conversations_dir: Path to the conversations root directory.
        since: Optional cutoff - only return turns after this timestamp.

    Returns:
        List of ClawTurn objects, sorted by timestamp (oldest first).
    """
    if not conversations_dir.exists():
        logger.debug("Conversations directory does not exist: %s", conversations_dir)
        return []

    turns: list[ClawTurn] = []

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
                turn = ClawTurn.from_json_record(record_data)

                # Filter by timestamp if since is provided
                if since is not None and turn.timestamp <= since:
                    continue

                turns.append(turn)
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning("Failed to parse turn file %s: %s", json_file, e)

    # Sort by timestamp (oldest first)
    turns.sort(key=lambda t: t.timestamp)
    return turns


def turns_to_journal_entries(turns: list[ClawTurn]) -> str:
    """Convert a list of ClawTurns into journal entry markdown.

    Each turn becomes a journal entry with this format:
        ## {timestamp} — claw-sync

        **[claw:{claw_id} turn:{event_id}]** {prompt_summary}
        > {response_summary}
        ({tokens} tokens, ${cost_usd})

    Args:
        turns: List of ClawTurn objects to convert.

    Returns:
        Markdown string with all entries concatenated.
    """
    entries: list[str] = []

    for turn in turns:
        ts = turn.timestamp.isoformat()

        # Create summaries from prompt/response (first 200 chars)
        prompt_summary = turn.prompt[:200].replace("\n", " ").strip()
        if len(turn.prompt) > 200:
            prompt_summary += "..."

        response_summary = turn.response[:200].replace("\n", " ").strip()
        if len(turn.response) > 200:
            response_summary += "..."

        # Build metadata line
        meta_parts: list[str] = []
        if turn.tokens is not None:
            meta_parts.append(f"{turn.tokens} tokens")
        if turn.cost_usd is not None:
            meta_parts.append(f"${turn.cost_usd:.4f}")

        metadata = f"({', '.join(meta_parts)})" if meta_parts else ""

        entry = f"""## {ts} — claw-sync

**[claw:{turn.claw_id} turn:{turn.event_id}]** {prompt_summary}
> {response_summary}
{metadata}

---

"""
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

    for i, entry in enumerate(claw_entries):
        # Generate turn ID from timestamp and index
        turn_id = f"{entry.timestamp.strftime('%Y%m%d%H%M%S')}-{i:03d}"
        week_dir_name = _get_iso_week_dir(entry.timestamp)
        week_path = output_dir / week_dir_name
        week_path.mkdir(parents=True, exist_ok=True)

        # Parse entry content to extract claw_id, event_id, etc.
        # Format: **[claw:{claw_id} turn:{event_id}]** {prompt}
        claw_id = session_name
        event_id = turn_id
        prompt = entry.content
        response = ""

        # Try to parse the header line
        header_match = re.search(
            r"\*\*\[claw:([^\s]+)\s+turn:([^\]]+)\]\*\*\s*(.*)",
            entry.content,
            re.DOTALL,
        )
        if header_match:
            claw_id = header_match.group(1)
            event_id = header_match.group(2)
            rest = header_match.group(3).strip()
            # Response is after the > marker
            response_match = re.search(r">\s*(.*)", rest, re.DOTALL)
            if response_match:
                response = response_match.group(1).strip()
                prompt = rest[: response_match.start()].strip()
            else:
                prompt = rest

        # Create TurnRecord JSON
        record: dict[str, object] = {
            "id": turn_id,
            "timestamp": entry.timestamp.isoformat(),
            "claw_id": claw_id,
            "event_id": event_id,
            "prompt": prompt,
            "response": response,
            "thinking": "",
            "prompt_summary": prompt[:100],
            "response_summary": response[:100],
            "model": "unknown",
            "prompt_tokens": 0,
            "response_tokens": 0,
            "cost_usd": 0.0,
            "metadata": {"source": "shoal-journal-export"},
        }

        # Write JSON file
        json_file = week_path / f"{turn_id}.json"
        json_file.write_text(json.dumps(record, indent=2))

        # Write markdown file with frontmatter
        md_content = f"""---
turn_id: {turn_id}
timestamp: {entry.timestamp.isoformat()}
claw_id: {claw_id}
event_id: {event_id}
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
