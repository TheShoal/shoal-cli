"""QMD conversation formatting for syncing logs inspired by Lobster Party QMD.

This module provides conversion between Shoal journal entries and the QMD (Conversation
Markdown) format used by Lobster Party for storing AI conversations.

QMD stores conversations as weekly-bucketed pairs:
    conversations/{year}-W{week}/{turn_id}.md    # YAML frontmatter + markdown
    conversations/{year}-W{week}/{turn_id}.json  # TurnRecord fields

References:
    - Lobster Party QMD spec: https://github.com/lobster-party/qmd
    - Shoal journal format: shoal.core.journal
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("shoal.qmd")


@dataclass(frozen=True)
class QmdTurn:
    """A single turn in QMD format.

    Attributes:
        id: Unique turn identifier (UUID or hash-based).
        timestamp: When the turn occurred (UTC).
        session_id: The session this turn belongs to.
        event_id: Optional event/correlation ID for tracing.
        prompt: The user's prompt text.
        response: The model's response text.
        model: Model identifier (e.g., "claude-sonnet-4-20250514").
        tokens: Total token count (prompt + response), if available.
        cost_usd: Cost in USD, if available.
        metadata: Additional key-value pairs for extensibility.
    """

    id: str
    timestamp: datetime
    session_id: str
    event_id: str
    prompt: str
    response: str
    model: str
    tokens: int | None = None
    cost_usd: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json_record(self) -> dict[str, Any]:
        """Convert to QMD TurnRecord JSON format.

        Returns:
            Dict matching QMD TurnRecord schema.
        """
        record: dict[str, Any] = {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "event_id": self.event_id,
            "prompt": self.prompt,
            "response": self.response,
            "model": self.model,
        }

        if self.tokens is not None:
            record["tokens"] = self.tokens

        if self.cost_usd is not None:
            record["cost_usd"] = self.cost_usd

        if self.metadata:
            record["metadata"] = self.metadata

        return record

    @classmethod
    def from_json_record(cls, record: dict[str, Any]) -> QmdTurn:
        """Create a QmdTurn from a QMD JSON TurnRecord.

        Args:
            record: Dict with QMD TurnRecord fields.

        Returns:
            QmdTurn instance with mapped fields.
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

        return cls(
            id=str(record.get("id", "")),
            timestamp=timestamp,
            session_id=str(record.get("session_id", "")),
            event_id=str(record.get("event_id", "")),
            prompt=str(record.get("prompt", "")),
            response=str(record.get("response", "")),
            model=str(record.get("model", "")),
            tokens=int(record["tokens"]) if "tokens" in record else None,
            cost_usd=float(record["cost_usd"]) if "cost_usd" in record else None,
            metadata=dict(record.get("metadata", {})),
        )

    def to_markdown(self) -> str:
        """Convert to QMD markdown format with YAML frontmatter.

        Returns:
            Markdown string with YAML frontmatter.
        """
        frontmatter = [
            "---",
            f"id: {self.id}",
            f"timestamp: {self.timestamp.isoformat()}",
            f"session_id: {self.session_id}",
            f"event_id: {self.event_id}",
            f"model: {self.model}",
        ]

        if self.tokens is not None:
            frontmatter.append(f"tokens: {self.tokens}")

        if self.cost_usd is not None:
            frontmatter.append(f"cost_usd: {self.cost_usd}")

        for key, value in sorted(self.metadata.items()):
            frontmatter.append(f"{key}: {json.dumps(value)}")

        frontmatter.append("---")
        frontmatter.append("")

        body_lines = [
            "## Prompt",
            "",
            self.prompt,
            "",
            "## Response",
            "",
            self.response,
        ]

        return "\n".join(frontmatter + body_lines) + "\n"


def _generate_turn_id(timestamp: datetime, session_id: str, content: str) -> str:
    """Generate a deterministic turn ID from timestamp and content.

    Args:
        timestamp: When the turn occurred.
        session_id: The session this turn belongs to.
        content: Prompt + response content for hashing.

    Returns:
        Short hash-based turn ID (first 12 chars of SHA256).
    """
    data = f"{timestamp.isoformat()}:{session_id}:{content}"
    return hashlib.sha256(data.encode()).hexdigest()[:12]


def _get_iso_week_dir(timestamp: datetime) -> str:
    """Get the ISO week directory name for a timestamp.

    Args:
        timestamp: Datetime to convert.

    Returns:
        Directory name in YYYY-Www format.
    """
    iso_cal = timestamp.isocalendar()
    return f"{iso_cal.year}-W{iso_cal.week:02d}"


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
    session_id: str | None = None,
) -> list[QmdTurn]:
    """Read all QMD turn records from a conversations directory.

    Scans weekly subdirectories (YYYY-Www format) for .json turn files,
    loads and parses them into QmdTurn objects.

    Args:
        conversations_dir: Path to the conversations root directory.
        since: Optional cutoff - only return turns after this timestamp.
        session_id: Optional filter - only return turns for this session.

    Returns:
        List of QmdTurn objects, sorted by timestamp (oldest first).
    """
    if not conversations_dir.exists():
        logger.debug("Conversations directory does not exist: %s", conversations_dir)
        return []

    turns: list[QmdTurn] = []

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
                turn = QmdTurn.from_json_record(record_data)

                # Filter by timestamp if since is provided
                if since is not None and turn.timestamp <= since:
                    continue

                # Filter by session_id if provided
                if session_id is not None and turn.session_id != session_id:
                    continue

                turns.append(turn)
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning("Failed to parse turn file %s: %s", json_file, e)

    # Sort by timestamp (oldest first)
    turns.sort(key=lambda t: t.timestamp)
    return turns


def write_qmd_turn(turn: QmdTurn, output_dir: Path) -> tuple[Path, Path]:
    """Write a single QMD turn as markdown+JSON pair.

    Args:
        turn: QmdTurn object to write.
        output_dir: Root directory for QMD conversations output.

    Returns:
        Tuple of (markdown_path, json_path) for the written files.
    """
    week_dir_name = _get_iso_week_dir(turn.timestamp)
    week_path = output_dir / week_dir_name
    week_path.mkdir(parents=True, exist_ok=True)

    # Use turn ID as filename base
    base_name = turn.id

    md_path = week_path / f"{base_name}.md"
    json_path = week_path / f"{base_name}.json"

    # Write markdown with frontmatter
    md_path.write_text(turn.to_markdown())

    # Write JSON record
    json_path.write_text(json.dumps(turn.to_json_record(), indent=2))

    return md_path, json_path


def export_journal_to_qmd(
    journal_path: Path,
    output_dir: Path,
    session_id: str,
    session_name: str,
) -> int:
    """Write journal entries as QMD-compatible markdown+JSON pairs.

    Parses journal entries and writes them as QMD turn files:
        {output_dir}/{year}-W{week}/{turn_id}.md
        {output_dir}/{year}-W{week}/{turn_id}.json

    Args:
        journal_path: Path to the Shoal journal file.
        output_dir: Root directory for QMD conversations output.
        session_id: Session ID to use in session_id field.
        session_name: Session name to use in metadata.

    Returns:
        Number of turns exported.
    """
    from shoal.core.journal import _parse_journal

    if not journal_path.exists():
        logger.debug("Journal file does not exist: %s", journal_path)
        return 0

    text = journal_path.read_text()
    entries = _parse_journal(text)

    if not entries:
        logger.debug("No entries found in journal")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    exported = 0

    for i, entry in enumerate(entries):
        # Generate turn ID
        content_hash = hashlib.sha256(entry.content.encode()).hexdigest()[:12]
        turn_id = f"{entry.timestamp.strftime('%Y%m%d%H%M%S')}-{i:03d}-{content_hash}"

        # Parse entry to extract prompt/response if possible
        prompt = entry.content
        response = ""
        model = "unknown"

        # Try to parse QMD-style entries
        header_match = re.search(
            r"\*\*\[claw:([^\s]+)\s+turn:([^\]]+)\]\*\*\s*(.*)",
            entry.content,
            re.DOTALL,
        )
        if header_match:
            model = header_match.group(1)
            event_id = header_match.group(2)
            rest = header_match.group(3).strip()
            # Response is after the > marker
            response_match = re.search(r">\s*(.*)", rest, re.DOTALL)
            if response_match:
                response = response_match.group(1).strip()
                prompt = rest[: response_match.start()].strip()
            else:
                prompt = rest
        else:
            event_id = turn_id

        turn = QmdTurn(
            id=turn_id,
            timestamp=entry.timestamp,
            session_id=session_id,
            event_id=event_id,
            prompt=prompt,
            response=response,
            model=model,
            metadata={"source": entry.source, "session_name": session_name},
        )

        write_qmd_turn(turn, output_dir)
        exported += 1

    logger.info("Exported %d turns to QMD format in %s", exported, output_dir)
    return exported


def import_qmd_to_journal(
    conversations_dir: Path,
    journal_path: Path,
    session_id: str,
    since: datetime | None = None,
) -> int:
    """Import QMD turns into a Shoal journal.

    Reads QMD turn files and appends them as journal entries.

    Args:
        conversations_dir: Path to the QMD conversations directory.
        journal_path: Path to the Shoal journal file to append to.
        session_id: Session ID to filter turns (optional).
        since: Only import turns after this timestamp (optional).

    Returns:
        Number of turns imported.
    """
    from shoal.core.journal import append_entry

    turns = read_qmd_turns(conversations_dir, since=since, session_id=session_id)

    if not turns:
        logger.debug("No QMD turns found to import")
        return 0

    imported = 0
    for turn in turns:
        # Format as journal entry
        metadata_parts = []
        if turn.tokens is not None:
            metadata_parts.append(f"{turn.tokens} tokens")
        if turn.cost_usd is not None:
            metadata_parts.append(f"${turn.cost_usd:.4f}")

        metadata = f"({', '.join(metadata_parts)})" if metadata_parts else ""

        content = f"""**[claw:{turn.model} turn:{turn.event_id}]** {turn.prompt[:200]}

> {turn.response[:200]}

{metadata}
"""

        append_entry(
            session_id,
            content,
            source="qmd-sync",
        )
        imported += 1

    logger.info("Imported %d QMD turns to journal %s", imported, journal_path)
    return imported


def sync_journal_with_qmd(
    journal_path: Path,
    conversations_dir: Path,
    session_id: str,
    session_name: str,
    direction: str = "both",
) -> dict[str, int]:
    """Synchronize journal with QMD conversation files.

    Args:
        journal_path: Path to the Shoal journal file.
        conversations_dir: Path to the QMD conversations directory.
        session_id: Session ID for filtering.
        session_name: Session name for metadata.
        direction: Sync direction - "export", "import", or "both".

    Returns:
        Dict with counts: {"exported": int, "imported": int}
    """
    result = {"exported": 0, "imported": 0}

    if direction in ("export", "both"):
        result["exported"] = export_journal_to_qmd(
            journal_path, conversations_dir, session_id, session_name
        )

    if direction in ("import", "both"):
        # Get last journal entry timestamp to avoid duplicates
        from shoal.core.journal import read_journal

        entries = read_journal(session_id, limit=1)
        since = entries[0].timestamp if entries else None

        result["imported"] = import_qmd_to_journal(
            conversations_dir, journal_path, session_id, since=since
        )

    return result
