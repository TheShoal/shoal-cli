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

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shoal.core.config import data_dir
from shoal.core.conversations import (
    ConversationEvent,
    journal_entry_to_event,
    qmd_turn_to_event,
    render_event_as_journal_content,
    summary_to_event,
)

logger = logging.getLogger("shoal.qmd")


def conversation_artifacts_dir() -> Path:
    """Return Shoal's canonical QMD artifact directory."""
    return data_dir() / "conversations"


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
    prompt_tokens: int | None = None
    response_tokens: int | None = None
    cost_usd: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json_record(self) -> dict[str, Any]:
        """Convert to QMD TurnRecord JSON format.

        Returns:
            Dict matching QMD TurnRecord schema.
        """
        structured_keys = {
            "schema_version",
            "session_name",
            "source",
            "kind",
            "correlation_id",
            "tool",
            "branch",
            "worktree",
            "summary",
            "tags",
        }
        omitted_keys = {
            "content_markdown",
            "thinking",
            "prompt_summary",
            "response_summary",
            "thinking_summary",
        }
        custom_metadata = {
            key: value
            for key, value in self.metadata.items()
            if key not in structured_keys and key not in omitted_keys
        }

        record: dict[str, Any] = {
            "id": self.id,
            "schema_version": int(self.metadata.get("schema_version", 1)),
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "event_id": self.event_id,
            "model": self.model,
        }

        for key in structured_keys:
            if key in self.metadata:
                record[key] = self.metadata[key]

        if self.tokens is not None:
            record["tokens"] = self.tokens

        if self.prompt_tokens is not None:
            record["prompt_tokens"] = self.prompt_tokens

        if self.response_tokens is not None:
            record["response_tokens"] = self.response_tokens

        if self.cost_usd is not None:
            record["cost_usd"] = self.cost_usd

        if custom_metadata:
            record["metadata"] = custom_metadata

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

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        metadata = dict(record.get("metadata", {}))
        for key in (
            "schema_version",
            "session_name",
            "source",
            "kind",
            "correlation_id",
            "tool",
            "branch",
            "worktree",
            "summary",
            "tags",
            "prompt_summary",
            "response_summary",
            "thinking_summary",
        ):
            if key in record:
                metadata[key] = record[key]

        return cls(
            id=str(record.get("id", "")),
            timestamp=timestamp,
            session_id=str(record.get("session_id", "")),
            event_id=str(record.get("event_id", "")),
            prompt=str(record.get("prompt", "")),
            response=str(record.get("response", "")),
            model=str(record.get("model", "")),
            tokens=int(record["tokens"]) if "tokens" in record else None,
            prompt_tokens=int(record["prompt_tokens"]) if "prompt_tokens" in record else None,
            response_tokens=int(record["response_tokens"]) if "response_tokens" in record else None,
            cost_usd=float(record["cost_usd"]) if "cost_usd" in record else None,
            metadata=metadata,
        )

    def to_markdown(self) -> str:
        """Convert to QMD markdown format with YAML frontmatter.

        Returns:
            Markdown string with YAML frontmatter.
        """
        schema_version = int(self.metadata.get("schema_version", 1))
        frontmatter = [
            "---",
            f"id: {self.id}",
            f"schema_version: {schema_version}",
            f"timestamp: {self.timestamp.isoformat()}",
            f"session_id: {self.session_id}",
        ]
        for key in (
            "session_name",
            "source",
            "kind",
            "correlation_id",
            "tool",
            "branch",
            "worktree",
        ):
            value = self.metadata.get(key)
            if value not in (None, ""):
                frontmatter.append(f"{key}: {value}")

        if self.model:
            frontmatter.append(f"model: {self.model}")
        if self.metadata.get("summary") not in (None, ""):
            frontmatter.append(
                f"summary: {json.dumps(self.metadata['summary'], ensure_ascii=False)}"
            )
        if self.metadata.get("tags"):
            frontmatter.append(f"tags: {json.dumps(self.metadata['tags'], ensure_ascii=False)}")
        frontmatter.append("---")
        frontmatter.append("")

        kind = str(self.metadata.get("kind") or ("chat_turn" if self.response else "journal_entry"))
        if kind == "chat_turn":
            body_lines = ["## Prompt", "", self.prompt, "", "## Response", "", self.response]
            thinking = self.metadata.get("thinking")
            if thinking:
                body_lines.extend(["", "## Thinking", "", str(thinking)])
        else:
            content_markdown = str(self.metadata.get("content_markdown") or self.prompt)
            body_lines = ["## Content", "", content_markdown]

        return "\n".join(frontmatter + body_lines) + "\n"


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


def _decode_frontmatter_value(raw: str) -> Any:
    if raw.startswith(("[", "{", '"')):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    if raw in {"true", "false", "null"}:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


def _parse_markdown_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text

    end_index = text.find("\n---\n", 4)
    if end_index == -1:
        return {}, text

    block = text[4:end_index]
    body = text[end_index + 5 :]
    frontmatter: dict[str, Any] = {}
    for line in block.splitlines():
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        frontmatter[key.strip()] = _decode_frontmatter_value(value.strip())
    return frontmatter, body


def _parse_markdown_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    body = body.strip()
    matches = list(re.finditer(r"^## (?P<section>[^\n]+)\n\n", body, re.MULTILINE))
    if not matches:
        return sections

    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        section_name = match.group("section").strip()
        sections[section_name] = body[start:end].strip()
    return sections


def _hydrate_turn_from_markdown(turn: QmdTurn, markdown_text: str) -> QmdTurn:
    frontmatter, body = _parse_markdown_frontmatter(markdown_text)
    sections = _parse_markdown_sections(body)
    metadata = dict(turn.metadata)

    for key in (
        "schema_version",
        "session_name",
        "source",
        "kind",
        "correlation_id",
        "tool",
        "branch",
        "worktree",
        "summary",
        "tags",
    ):
        if key in frontmatter and key not in metadata:
            metadata[key] = frontmatter[key]

    prompt = turn.prompt
    response = turn.response
    if "Prompt" in sections:
        prompt = sections["Prompt"]
    if "Response" in sections:
        response = sections["Response"]
    if "Thinking" in sections and "thinking" not in metadata:
        metadata["thinking"] = sections["Thinking"]
    if "Content" in sections and "content_markdown" not in metadata:
        metadata["content_markdown"] = sections["Content"]
    elif (
        not sections and body and "content_markdown" not in metadata and not prompt and not response
    ):
        metadata["content_markdown"] = body.strip()

    session_id = turn.session_id or str(frontmatter.get("session_id", ""))
    event_id = turn.event_id or str(frontmatter.get("event_id", ""))
    model = turn.model or str(frontmatter.get("model", ""))

    return QmdTurn(
        id=turn.id or str(frontmatter.get("id", "")),
        timestamp=turn.timestamp,
        session_id=session_id,
        event_id=event_id,
        prompt=prompt,
        response=response,
        model=model,
        tokens=turn.tokens,
        prompt_tokens=turn.prompt_tokens,
        response_tokens=turn.response_tokens,
        cost_usd=turn.cost_usd,
        metadata=metadata,
    )


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

                markdown_file = json_file.with_suffix(".md")
                if markdown_file.exists():
                    turn = _hydrate_turn_from_markdown(turn, markdown_file.read_text())

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

    # Write markdown with full text plane
    md_path.write_text(turn.to_markdown())

    # Write JSON sidecar with structured metadata only
    json_record = turn.to_json_record()
    json_record["body_markdown"] = md_path.name
    json_path.write_text(json.dumps(json_record, indent=2))
    return md_path, json_path


def write_qmd_event(
    event: ConversationEvent,
    output_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Persist a canonical event as a Shoal QMD artifact pair."""
    target_dir = output_dir or conversation_artifacts_dir()
    return write_qmd_turn(event_to_qmd_turn(event), target_dir)


def read_qmd_events(
    output_dir: Path | None = None,
    *,
    since: datetime | None = None,
    session_id: str | None = None,
    kind: str | None = None,
    correlation_id: str | None = None,
    source: str | None = None,
) -> list[ConversationEvent]:
    """Read canonical events from Shoal QMD artifacts with optional filters."""
    target_dir = output_dir or conversation_artifacts_dir()
    turns = read_qmd_turns(target_dir, since=since, session_id=session_id)
    events: list[ConversationEvent] = []

    for turn in turns:
        event = qmd_turn_to_event(turn)
        if kind is not None and event.kind != kind:
            continue
        if correlation_id is not None and event.correlation_id != correlation_id:
            continue
        if source is not None and event.source != source:
            continue
        events.append(event)

    return events


def latest_qmd_event(
    output_dir: Path | None = None,
    *,
    since: datetime | None = None,
    session_id: str | None = None,
    kind: str | None = None,
    correlation_id: str | None = None,
    source: str | None = None,
) -> ConversationEvent | None:
    """Return the newest matching canonical event from Shoal QMD artifacts."""
    events = read_qmd_events(
        output_dir,
        since=since,
        session_id=session_id,
        kind=kind,
        correlation_id=correlation_id,
        source=source,
    )
    if not events:
        return None
    return events[-1]


def persist_summary_event(
    *,
    session_id: str,
    session_name: str,
    source: str,
    summary: str,
    timestamp: datetime | None = None,
    kind: str = "summary",
    correlation_id: str | None = None,
    tags: tuple[str, ...] | list[str] = (),
    metadata: dict[str, Any] | None = None,
    output_dir: Path | None = None,
) -> tuple[ConversationEvent, tuple[Path, Path]]:
    """Create and persist a summary-style event in the canonical QMD artifact store."""
    event = summary_to_event(
        session_id=session_id,
        session_name=session_name,
        source=source,
        summary=summary,
        timestamp=timestamp,
        kind=kind,
        correlation_id=correlation_id,
        tags=tags,
        metadata=metadata,
    )
    return event, write_qmd_event(event, output_dir)


def event_to_qmd_turn(event: ConversationEvent) -> QmdTurn:
    """Convert a canonical conversation event into a Shoal-native QMD turn."""
    metadata = dict(event.metadata)
    metadata.setdefault("schema_version", event.schema_version)
    metadata.setdefault("kind", event.kind)
    metadata.setdefault("source", event.source)
    if event.session_name:
        metadata.setdefault("session_name", event.session_name)
    if event.correlation_id:
        metadata.setdefault("correlation_id", event.correlation_id)
    if event.tool:
        metadata.setdefault("tool", event.tool)
    if event.branch:
        metadata.setdefault("branch", event.branch)
    if event.worktree:
        metadata.setdefault("worktree", event.worktree)
    if event.summary is not None:
        metadata.setdefault("summary", event.summary)
    if event.tags:
        metadata.setdefault("tags", list(event.tags))
    if event.content_markdown is not None:
        metadata.setdefault("content_markdown", event.content_markdown)
    if event.prompt_summary is not None:
        metadata.setdefault("prompt_summary", event.prompt_summary)
    if event.response_summary is not None:
        metadata.setdefault("response_summary", event.response_summary)
    if event.thinking is not None:
        metadata.setdefault("thinking", event.thinking)
    if event.thinking_summary is not None:
        metadata.setdefault("thinking_summary", event.thinking_summary)

    model = event.model or str(event.metadata.get("claw_id") or "unknown")
    prompt = event.prompt or event.content_markdown or event.summary or ""
    response = event.response or ""

    return QmdTurn(
        id=event.id,
        timestamp=event.timestamp,
        session_id=event.session_id,
        event_id=event.event_id or event.id,
        prompt=prompt,
        response=response,
        model=model,
        tokens=event.tokens,
        prompt_tokens=event.prompt_tokens,
        response_tokens=event.response_tokens,
        cost_usd=event.cost_usd,
        metadata=metadata,
    )


def export_journal_to_qmd(
    journal_path: Path,
    output_dir: Path,
    session_id: str,
    session_name: str,
) -> int:
    """Write journal entries as QMD-compatible markdown+JSON pairs."""
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

    for entry in entries:
        event = journal_entry_to_event(entry, session_id, session_name)
        write_qmd_turn(event_to_qmd_turn(event), output_dir)
        exported += 1

    logger.info("Exported %d turns to QMD format in %s", exported, output_dir)
    return exported


def import_qmd_to_journal(
    conversations_dir: Path,
    journal_path: Path,
    session_id: str,
    since: datetime | None = None,
    *,
    allow_lobster_fallback: bool = True,
) -> int:
    """Import QMD turns into a Shoal journal.

    Reads generic Shoal QMD turn files first. If none match and fallback is enabled,
    also accepts Lobster-style Claw QMD records via the compatibility adapter.
    """
    from shoal.core.journal import append_entry

    turns = read_qmd_turns(conversations_dir, since=since, session_id=session_id)

    if turns:
        imported = 0
        for turn in turns:
            event = qmd_turn_to_event(turn)
            append_entry(
                session_id,
                render_event_as_journal_content(event, actor=event.model),
                source="qmd-sync",
            )
            imported += 1

        logger.info("Imported %d QMD turns to journal %s", imported, journal_path)
        return imported

    if not allow_lobster_fallback:
        logger.debug(
            "No Shoal QMD turns found for session %s in %s",
            session_id,
            conversations_dir,
        )
        return 0

    from shoal.core.lobster_conversations import read_qmd_turns as read_lobster_qmd_turns
    from shoal.core.lobster_conversations import turns_to_journal_entries

    claw_turns = read_lobster_qmd_turns(conversations_dir, since=since)
    if not claw_turns:
        logger.debug("No QMD turns found to import")
        return 0

    append_entry(
        session_id,
        turns_to_journal_entries(claw_turns),
        source="claw-sync",
    )
    logger.info(
        "Imported %d Lobster-compatible QMD turns to journal %s",
        len(claw_turns),
        journal_path,
    )
    return len(claw_turns)


def sync_journal_with_qmd(
    journal_path: Path,
    conversations_dir: Path,
    session_id: str,
    session_name: str,
    direction: str = "both",
    since: datetime | None = None,
) -> dict[str, int]:
    """Synchronize journal with QMD conversation files.

    Args:
        journal_path: Path to the Shoal journal file.
        conversations_dir: Path to the QMD conversations directory.
        session_id: Session ID for filtering.
        session_name: Session name for metadata.
        direction: Sync direction - "export", "import", or "both".
        since: Optional explicit import cutoff. When omitted, sync uses the newest
            journal entry timestamp to avoid duplicates.

    Returns:
        Dict with counts: {"exported": int, "imported": int}
    """
    result = {"exported": 0, "imported": 0}

    if direction in ("export", "both"):
        result["exported"] = export_journal_to_qmd(
            journal_path, conversations_dir, session_id, session_name
        )

    if direction in ("import", "both"):
        import_since = since
        if import_since is None:
            from shoal.core.journal import read_journal

            entries = read_journal(session_id, limit=1)
            import_since = entries[0].timestamp if entries else None

        result["imported"] = import_qmd_to_journal(
            conversations_dir,
            journal_path,
            session_id,
            since=import_since,
        )

    return result
