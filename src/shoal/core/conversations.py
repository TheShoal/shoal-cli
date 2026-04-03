"""Canonical Shoal conversation/event model and conversion helpers."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

SCHEMA_VERSION = 1

_CHAT_TURN_RE = re.compile(
    r"\*\*\[claw:(?P<actor>[^\s]+)\s+turn:(?P<event_id>[^\]]+)\]\*\*\s*(?P<body>.*)",
    re.DOTALL,
)
_USAGE_TOKENS_RE = re.compile(r"(?P<tokens>\d+)\s+tokens")
_USAGE_COST_RE = re.compile(r"\$(?P<cost>\d+(?:\.\d+)?)")


class JournalEntryLike(Protocol):
    """Structural type for journal entries."""

    @property
    def timestamp(self) -> datetime: ...

    @property
    def source(self) -> str: ...

    @property
    def content(self) -> str: ...


class QmdTurnLike(Protocol):
    """Structural type for Shoal-native QMD turns."""

    @property
    def id(self) -> str: ...

    @property
    def timestamp(self) -> datetime: ...

    @property
    def session_id(self) -> str: ...

    @property
    def event_id(self) -> str: ...

    @property
    def prompt(self) -> str: ...

    @property
    def response(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def tokens(self) -> int | None: ...

    @property
    def prompt_tokens(self) -> int | None: ...

    @property
    def response_tokens(self) -> int | None: ...

    @property
    def cost_usd(self) -> float | None: ...

    @property
    def metadata(self) -> dict[str, Any]: ...


class LobsterTurnLike(Protocol):
    """Structural type for Lobster/Claw-compatible QMD turns."""

    @property
    def id(self) -> str: ...

    @property
    def timestamp(self) -> datetime: ...

    @property
    def claw_id(self) -> str: ...

    @property
    def event_id(self) -> str: ...

    @property
    def prompt(self) -> str: ...

    @property
    def response(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def tokens(self) -> int | None: ...

    @property
    def prompt_tokens(self) -> int | None: ...

    @property
    def response_tokens(self) -> int | None: ...

    @property
    def cost_usd(self) -> float | None: ...

    @property
    def thinking(self) -> str | None: ...

    @property
    def prompt_summary(self) -> str | None: ...

    @property
    def response_summary(self) -> str | None: ...

    @property
    def thinking_summary(self) -> str | None: ...

    @property
    def metadata(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ConversationEvent:
    """Canonical Shoal-native event persisted across conversation artifacts."""

    id: str
    timestamp: datetime
    session_id: str
    session_name: str
    source: str
    kind: str
    schema_version: int = SCHEMA_VERSION
    event_id: str | None = None
    correlation_id: str | None = None
    tool: str | None = None
    branch: str | None = None
    worktree: str | None = None
    model: str | None = None
    summary: str | None = None
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    content_markdown: str | None = None
    prompt: str | None = None
    response: str | None = None
    thinking: str | None = None
    prompt_summary: str | None = None
    response_summary: str | None = None
    thinking_summary: str | None = None
    tokens: int | None = None
    prompt_tokens: int | None = None
    response_tokens: int | None = None
    cost_usd: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", _normalize_timestamp(self.timestamp))
        object.__setattr__(self, "tags", _normalize_tags(self.tags))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ParsedChatTurn:
    """Parsed prompt/response form embedded inside a journal entry."""

    actor: str
    event_id: str
    prompt: str
    response: str
    tokens: int | None
    cost_usd: float | None


def _normalize_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def _normalize_tags(tags: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw_tag in tags:
        tag = raw_tag.strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)
    return tuple(normalized)


def _coerce_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    return None


def _coerce_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    return None


def _coerce_tags(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return _normalize_tags([str(item) for item in value if str(item).strip()])
    return ()


def generate_event_id(
    *,
    kind: str,
    timestamp: datetime,
    session_id: str,
    source: str,
    event_id: str | None = None,
    correlation_id: str | None = None,
    content_markdown: str | None = None,
    prompt: str | None = None,
    response: str | None = None,
    summary: str | None = None,
) -> str:
    """Generate a deterministic event id from stable event content."""
    normalized_ts = _normalize_timestamp(timestamp)
    payload = {
        "kind": kind,
        "timestamp": normalized_ts.isoformat(),
        "session_id": session_id,
        "source": source,
        "event_id": event_id,
        "correlation_id": correlation_id,
        "content_markdown": content_markdown,
        "prompt": prompt,
        "response": response,
        "summary": summary,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()[:12]
    return f"{normalized_ts.strftime('%Y%m%d%H%M%S')}-{digest}"


def summarize_text(text: str, limit: int = 200) -> str:
    """Collapse whitespace and truncate text for operator-facing journal snippets."""
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."


def parse_chat_turn_content(content: str) -> ParsedChatTurn | None:
    """Parse a QMD-style chat turn embedded inside journal markdown."""
    match = _CHAT_TURN_RE.match(content.strip())
    if match is None:
        return None

    body = match.group("body").strip()
    tokens: int | None = None
    cost_usd: float | None = None

    metadata_match = re.search(r"\n\n(?P<meta>\([^\n]+\))\s*$", body)
    if metadata_match is not None:
        metadata_line = metadata_match.group("meta")
        body = body[: metadata_match.start()].strip()

        tokens_match = _USAGE_TOKENS_RE.search(metadata_line)
        if tokens_match is not None:
            tokens = int(tokens_match.group("tokens"))

        cost_match = _USAGE_COST_RE.search(metadata_line)
        if cost_match is not None:
            cost_usd = float(cost_match.group("cost"))

    prompt = body
    response = ""
    response_match = re.search(r"\n\n>\s*(?P<response>.*)$", body, re.DOTALL)
    if response_match is not None:
        prompt = body[: response_match.start()].strip()
        response = response_match.group("response").strip()

    return ParsedChatTurn(
        actor=match.group("actor"),
        event_id=match.group("event_id"),
        prompt=prompt,
        response=response,
        tokens=tokens,
        cost_usd=cost_usd,
    )


def journal_entry_to_event(
    entry: JournalEntryLike,
    session_id: str,
    session_name: str,
) -> ConversationEvent:
    """Convert a journal entry into the canonical event model."""
    source = entry.source or "journal"
    content = entry.content.strip()

    if content.startswith("[dreamer]"):
        summary = content.removeprefix("[dreamer]").strip()
        return ConversationEvent(
            id=generate_event_id(
                kind="summary",
                timestamp=entry.timestamp,
                session_id=session_id,
                source=source,
                summary=summary,
            ),
            timestamp=entry.timestamp,
            session_id=session_id,
            session_name=session_name,
            source=source,
            kind="summary",
            summary=summary,
            tags=("summary", "dreamer"),
            content_markdown=content,
        )

    if content.startswith("[claw-summary]"):
        summary = content.removeprefix("[claw-summary]").strip()
        return ConversationEvent(
            id=generate_event_id(
                kind="summary",
                timestamp=entry.timestamp,
                session_id=session_id,
                source=source,
                summary=summary,
            ),
            timestamp=entry.timestamp,
            session_id=session_id,
            session_name=session_name,
            source=source,
            kind="summary",
            summary=summary,
            tags=("summary", "claw"),
            content_markdown=content,
        )

    parsed_turn = parse_chat_turn_content(content)
    if parsed_turn is not None:
        event_metadata: dict[str, Any] = {}
        model: str | None = parsed_turn.actor
        if source.lower() == "claw-sync":
            event_metadata["claw_id"] = parsed_turn.actor
            model = None

        return ConversationEvent(
            id=generate_event_id(
                kind="chat_turn",
                timestamp=entry.timestamp,
                session_id=session_id,
                source=source,
                event_id=parsed_turn.event_id,
                prompt=parsed_turn.prompt,
                response=parsed_turn.response,
            ),
            timestamp=entry.timestamp,
            session_id=session_id,
            session_name=session_name,
            source=source,
            kind="chat_turn",
            event_id=parsed_turn.event_id,
            model=model,
            tags=("chat",),
            metadata=event_metadata,
            prompt=parsed_turn.prompt,
            response=parsed_turn.response,
            prompt_summary=summarize_text(parsed_turn.prompt),
            response_summary=summarize_text(parsed_turn.response) if parsed_turn.response else None,
            tokens=parsed_turn.tokens,
            cost_usd=parsed_turn.cost_usd,
        )

    return ConversationEvent(
        id=generate_event_id(
            kind="journal_entry",
            timestamp=entry.timestamp,
            session_id=session_id,
            source=source,
            content_markdown=content,
        ),
        timestamp=entry.timestamp,
        session_id=session_id,
        session_name=session_name,
        source=source,
        kind="journal_entry",
        tags=("journal",),
        content_markdown=content,
    )


def qmd_turn_to_event(turn: QmdTurnLike, session_name: str | None = None) -> ConversationEvent:
    """Convert a Shoal-native QMD turn into the canonical event model."""
    metadata = dict(turn.metadata)
    kind = _coerce_str(metadata.get("kind")) or ("chat_turn" if turn.response else "journal_entry")
    resolved_content = _coerce_str(metadata.get("content_markdown"))
    resolved_summary = _coerce_str(metadata.get("summary"))
    return ConversationEvent(
        id=turn.id
        or generate_event_id(
            kind=kind,
            timestamp=turn.timestamp,
            session_id=turn.session_id,
            source=_coerce_str(metadata.get("source")) or "qmd",
            event_id=_coerce_str(turn.event_id),
            correlation_id=_coerce_str(metadata.get("correlation_id")),
            content_markdown=resolved_content,
            prompt=turn.prompt,
            response=turn.response,
            summary=resolved_summary,
        ),
        timestamp=turn.timestamp,
        session_id=turn.session_id,
        session_name=session_name or _coerce_str(metadata.get("session_name")) or "",
        source=_coerce_str(metadata.get("source")) or "qmd",
        kind=kind,
        event_id=_coerce_str(turn.event_id),
        correlation_id=_coerce_str(metadata.get("correlation_id")),
        tool=_coerce_str(metadata.get("tool")),
        branch=_coerce_str(metadata.get("branch")),
        worktree=_coerce_str(metadata.get("worktree")),
        model=_coerce_str(turn.model),
        summary=resolved_summary,
        tags=_coerce_tags(metadata.get("tags")),
        metadata=metadata,
        content_markdown=resolved_content,
        prompt=turn.prompt if kind == "chat_turn" else None,
        response=turn.response if kind == "chat_turn" else None,
        thinking=_coerce_str(metadata.get("thinking")),
        prompt_summary=_coerce_str(metadata.get("prompt_summary")),
        response_summary=_coerce_str(metadata.get("response_summary")),
        thinking_summary=_coerce_str(metadata.get("thinking_summary")),
        tokens=turn.tokens,
        prompt_tokens=turn.prompt_tokens or _coerce_int(metadata.get("prompt_tokens")),
        response_tokens=turn.response_tokens or _coerce_int(metadata.get("response_tokens")),
        cost_usd=turn.cost_usd,
    )


def claw_turn_to_event(
    turn: LobsterTurnLike,
    *,
    session_id: str = "",
    session_name: str = "",
) -> ConversationEvent:
    """Convert a Lobster/Claw-compatible turn into the canonical event model."""
    metadata = dict(turn.metadata)
    return ConversationEvent(
        id=turn.id
        or generate_event_id(
            kind="chat_turn",
            timestamp=turn.timestamp,
            session_id=session_id,
            source=_coerce_str(metadata.get("source")) or "claw-qmd",
            event_id=_coerce_str(turn.event_id),
            prompt=turn.prompt,
            response=turn.response,
        ),
        timestamp=turn.timestamp,
        session_id=session_id,
        session_name=session_name,
        source=_coerce_str(metadata.get("source")) or "claw-qmd",
        kind="chat_turn",
        event_id=_coerce_str(turn.event_id),
        correlation_id=_coerce_str(metadata.get("correlation_id")),
        model=_coerce_str(turn.model),
        tags=("chat", "claw"),
        metadata={**metadata, "claw_id": turn.claw_id},
        prompt=turn.prompt,
        response=turn.response,
        thinking=turn.thinking,
        prompt_summary=turn.prompt_summary or summarize_text(turn.prompt),
        response_summary=turn.response_summary or summarize_text(turn.response),
        thinking_summary=turn.thinking_summary,
        tokens=turn.tokens,
        prompt_tokens=turn.prompt_tokens,
        response_tokens=turn.response_tokens,
        cost_usd=turn.cost_usd,
    )


def summary_to_event(
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
    content_markdown: str | None = None,
) -> ConversationEvent:
    """Build a canonical summary-style event."""
    resolved_timestamp = _normalize_timestamp(timestamp or datetime.now(tz=UTC))
    return ConversationEvent(
        id=generate_event_id(
            kind=kind,
            timestamp=resolved_timestamp,
            session_id=session_id,
            source=source,
            correlation_id=correlation_id,
            summary=summary,
        ),
        timestamp=resolved_timestamp,
        session_id=session_id,
        session_name=session_name,
        source=source,
        kind=kind,
        correlation_id=correlation_id,
        summary=summary,
        tags=_normalize_tags(tags),
        metadata=metadata or {},
        content_markdown=content_markdown,
    )


def render_event_as_journal_content(event: ConversationEvent, *, actor: str | None = None) -> str:
    """Render a canonical event back into operator-facing journal content."""
    if event.kind == "chat_turn":
        header_actor = (
            actor or event.model or _coerce_str(event.metadata.get("claw_id")) or "unknown"
        )
        prompt_text = event.prompt_summary or summarize_text(event.prompt or "")
        response_text = event.response_summary or summarize_text(event.response or "")

        parts = [f"**[claw:{header_actor} turn:{event.event_id or event.id}]** {prompt_text}"]
        if response_text:
            parts.extend(["", f"> {response_text}"])

        metadata_parts: list[str] = []
        if event.tokens is not None:
            metadata_parts.append(f"{event.tokens} tokens")
        if event.cost_usd is not None:
            metadata_parts.append(f"${event.cost_usd:.4f}")
        if metadata_parts:
            parts.extend(["", f"({', '.join(metadata_parts)})"])

        return "\n".join(parts)

    if event.content_markdown is not None:
        return event.content_markdown
    if event.summary is not None:
        return event.summary
    return ""
