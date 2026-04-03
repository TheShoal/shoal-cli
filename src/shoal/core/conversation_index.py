"""Derived SQLite index for canonical Shoal conversation/event artifacts.

The index is a *secondary* plane derived from the canonical markdown+JSON
artifact pairs written by ``src/shoal/core/qmd.py``.  It never replaces
those artifacts as the source of truth — it is always rebuildable from disk.

Usage::

    from shoal.core.conversation_index import get_index

    idx = await get_index()
    await idx.ingest(event, md_path, json_path)
    summaries = await idx.recent_events(session_id="sess-1", kind="summary")
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger("shoal.conversation_index")

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS conversation_events (
    id              TEXT PRIMARY KEY,
    schema_version  INTEGER NOT NULL DEFAULT 1,
    timestamp       TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    session_name    TEXT NOT NULL DEFAULT '',
    source          TEXT NOT NULL DEFAULT '',
    kind            TEXT NOT NULL DEFAULT '',
    event_id        TEXT,
    correlation_id  TEXT,
    tool            TEXT,
    branch          TEXT,
    worktree        TEXT,
    model           TEXT,
    summary         TEXT,
    tokens          INTEGER,
    cost_usd        REAL,
    json_path       TEXT,
    markdown_path   TEXT
)
"""

_CREATE_TAGS = """
CREATE TABLE IF NOT EXISTS conversation_tags (
    event_id  TEXT NOT NULL REFERENCES conversation_events(id) ON DELETE CASCADE,
    tag       TEXT NOT NULL,
    PRIMARY KEY (event_id, tag)
)
"""

_CREATE_INDEX_STATE = """
CREATE TABLE IF NOT EXISTS index_state (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
)
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ce_session   ON conversation_events(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_ce_kind      ON conversation_events(kind)",
    "CREATE INDEX IF NOT EXISTS idx_ce_corr      ON conversation_events(correlation_id)",
    "CREATE INDEX IF NOT EXISTS idx_ce_ts        ON conversation_events(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_ce_source    ON conversation_events(source)",
    "CREATE INDEX IF NOT EXISTS idx_ct_tag       ON conversation_tags(tag)",
]


# ---------------------------------------------------------------------------
# ConversationIndex
# ---------------------------------------------------------------------------


class ConversationIndex:
    """Async SQLite index over canonical QMD artifact pairs.

    Create via ``get_index()`` (singleton) or directly for tests.
    """

    _instance: ConversationIndex | None = None

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        self._initialized: bool = False

    # ------------------------------------------------------------------
    # Singleton lifecycle
    # ------------------------------------------------------------------

    @classmethod
    async def get_instance(cls, db_path: Path | None = None) -> ConversationIndex:
        """Return or create the process-level singleton index."""
        if cls._instance is None:
            if db_path is None:
                from shoal.core.config import data_dir, ensure_dirs

                ensure_dirs()
                db_path = data_dir() / "conversations.index.db"
            cls._instance = cls(db_path)
        return cls._instance

    @classmethod
    async def reset_instance(cls) -> None:
        """Close and clear the singleton (primarily for testing)."""
        if cls._instance is not None:
            await cls._instance.close()
            cls._instance = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the database connection and initialise the schema."""
        if self._conn is not None:
            return
        logger.debug("Connecting to conversation index: %s", self.db_path)
        self._conn = await aiosqlite.connect(self.db_path)
        if not self._initialized:
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA foreign_keys=ON")
            await self._initialize_schema()
            self._initialized = True

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _initialize_schema(self) -> None:
        if self._conn is None:
            raise RuntimeError("Database not connected")
        for ddl in (_CREATE_EVENTS, _CREATE_TAGS, _CREATE_INDEX_STATE, *_INDEXES):
            await self._conn.execute(ddl)
        await self._conn.commit()

    def _require_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("ConversationIndex not connected — call connect() first")
        return self._conn

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    async def ingest(
        self,
        event: Any,
        md_path: Path | None = None,
        json_path: Path | None = None,
    ) -> bool:
        """Upsert a single ConversationEvent into the index.

        Args:
            event: A ``ConversationEvent`` instance.
            md_path: Path to the markdown artifact (may be None).
            json_path: Path to the JSON sidecar artifact (may be None).

        Returns:
            True if the event was newly inserted; False if it already existed.
        """
        conn = self._require_conn()
        async with self._lock:
            # Check existence first so we can report insert vs. skip
            async with conn.execute(
                "SELECT 1 FROM conversation_events WHERE id = ?", (event.id,)
            ) as cur:
                row = await cur.fetchone()
            if row is not None:
                return False

            ts = (
                event.timestamp.isoformat()
                if hasattr(event.timestamp, "isoformat")
                else str(event.timestamp)
            )
            await conn.execute(
                """
                INSERT INTO conversation_events
                    (id, schema_version, timestamp, session_id, session_name,
                     source, kind, event_id, correlation_id, tool, branch,
                     worktree, model, summary, tokens, cost_usd,
                     json_path, markdown_path)
                VALUES (?,?,?,?,?, ?,?,?,?,?,?,?,?,?,?,?, ?,?)
                """,
                (
                    event.id,
                    event.schema_version,
                    ts,
                    event.session_id,
                    event.session_name or "",
                    event.source or "",
                    event.kind or "",
                    event.event_id,
                    event.correlation_id,
                    event.tool,
                    event.branch,
                    event.worktree,
                    event.model,
                    event.summary,
                    event.tokens,
                    event.cost_usd,
                    str(json_path) if json_path is not None else None,
                    str(md_path) if md_path is not None else None,
                ),
            )
            for tag in event.tags or ():
                await conn.execute(
                    "INSERT OR IGNORE INTO conversation_tags (event_id, tag) VALUES (?,?)",
                    (event.id, tag),
                )
            await conn.commit()
        return True

    async def ingest_from_disk(self, output_dir: Path | None = None) -> int:
        """Scan all JSON sidecars on disk and ingest any not yet indexed.

        This is idempotent — already-indexed events are silently skipped.

        Args:
            output_dir: Root QMD artifact directory.  Defaults to
                ``conversation_artifacts_dir()``.

        Returns:
            Number of newly ingested events.
        """
        from shoal.core.conversations import qmd_turn_to_event
        from shoal.core.qmd import conversation_artifacts_dir, read_qmd_turns

        root = output_dir or conversation_artifacts_dir()
        if not root.exists():
            return 0

        turns = read_qmd_turns(root)
        ingested = 0
        for turn in turns:
            try:
                event = qmd_turn_to_event(turn)
                json_path = _resolve_json_path(root, turn)
                md_path = json_path.with_suffix(".md") if json_path is not None else None
                inserted = await self.ingest(event, md_path=md_path, json_path=json_path)
                if inserted:
                    ingested += 1
            except Exception as exc:
                logger.warning("Failed to ingest turn %s: %s", turn.id, exc)

        if ingested:
            await self._set_checkpoint(root)
        logger.info("ingest_from_disk: %d new events from %s", ingested, root)
        return ingested

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    async def recent_events(
        self,
        session_id: str | None = None,
        *,
        kind: str | None = None,
        source: str | None = None,
        correlation_id: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return recent events, newest first, with optional filters.

        Args:
            session_id: Filter by session.
            kind: Filter by event kind.
            source: Filter by source.
            correlation_id: Filter by workflow correlation id.
            since: Only return events after this timestamp (UTC).
            limit: Maximum number of rows to return.

        Returns:
            List of raw row dicts ordered newest-first.
        """
        conn = self._require_conn()
        clauses: list[str] = []
        params: list[Any] = []

        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        if source is not None:
            clauses.append("source = ?")
            params.append(source)
        if correlation_id is not None:
            clauses.append("correlation_id = ?")
            params.append(correlation_id)
        if since is not None:
            clauses.append("timestamp > ?")
            params.append(since.astimezone(UTC).isoformat())

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)

        async with conn.execute(
            f"SELECT * FROM conversation_events {where} ORDER BY timestamp DESC LIMIT ?",  # noqa: S608
            params,
        ) as cur:
            cur.row_factory = aiosqlite.Row
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def latest_summary(
        self,
        session_id: str,
        *,
        kind: str = "summary",
    ) -> dict[str, Any] | None:
        """Return the most recent summary event for a session.

        Args:
            session_id: Session to query.
            kind: Event kind to match (default ``"summary"``).

        Returns:
            A raw row dict, or ``None`` if no matching event exists.
        """
        rows = await self.recent_events(session_id=session_id, kind=kind, limit=1)
        return rows[0] if rows else None

    async def workflow_events(
        self,
        correlation_id: str,
        *,
        kind: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return all events sharing a correlation id.

        Args:
            correlation_id: Workflow correlation id.
            kind: Optional kind filter.
            limit: Maximum rows to return.

        Returns:
            List of raw row dicts ordered newest-first.
        """
        return await self.recent_events(correlation_id=correlation_id, kind=kind, limit=limit)

    async def tags_for_event(self, event_id: str) -> list[str]:
        """Return all tags for a given event id.

        Args:
            event_id: The event's primary key.

        Returns:
            Sorted list of tag strings.
        """
        conn = self._require_conn()
        async with conn.execute(
            "SELECT tag FROM conversation_tags WHERE event_id = ? ORDER BY tag",
            (event_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [row[0] for row in rows]

    # ------------------------------------------------------------------
    # Index state helpers
    # ------------------------------------------------------------------

    async def _set_checkpoint(self, output_dir: Path) -> None:
        conn = self._require_conn()
        async with self._lock:
            await conn.execute(
                "INSERT OR REPLACE INTO index_state (key, value) VALUES (?,?)",
                (
                    f"checkpoint:{output_dir}",
                    json.dumps({"ingested_at": datetime.now(UTC).isoformat()}),
                ),
            )
            await conn.commit()

    async def get_checkpoint(self, output_dir: Path) -> dict[str, Any] | None:
        """Return the last ingestion checkpoint for an artifact directory.

        Args:
            output_dir: The QMD artifact root directory.

        Returns:
            Checkpoint dict or ``None`` if never ingested.
        """
        conn = self._require_conn()
        async with conn.execute(
            "SELECT value FROM index_state WHERE key = ?",
            (f"checkpoint:{output_dir}",),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return dict(json.loads(str(row[0])))


# ---------------------------------------------------------------------------
# Module-level singleton helpers
# ---------------------------------------------------------------------------


async def get_index(db_path: Path | None = None) -> ConversationIndex:
    """Return (and connect) the process-level ConversationIndex singleton.

    Args:
        db_path: Override DB path (useful for tests).

    Returns:
        A connected ``ConversationIndex`` instance.
    """
    idx = await ConversationIndex.get_instance(db_path)
    await idx.connect()
    return idx


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_json_path(root: Path, turn: Any) -> Path | None:
    """Best-effort reconstruction of a QMD JSON sidecar path.

    Walks the weekly bucket directory structure to find the .json file
    whose stem matches *turn.id*.
    """
    iso = turn.timestamp.isocalendar()
    week_dir = root / f"{iso.year}-W{iso.week:02d}"
    candidate = week_dir / f"{turn.id}.json"
    if candidate.exists():
        return candidate
    return None
