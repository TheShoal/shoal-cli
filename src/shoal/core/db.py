"""Async SQLite database for Shoal session and robo state."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import aiosqlite

from shoal.models.incident import IncidentRecord
from shoal.models.state import RoboState, SessionState

logger = logging.getLogger("shoal.db")

SQLITE_MAX_VARIABLES = 900


def _chunked(items: list[str], chunk_size: int | None = None) -> list[list[str]]:
    size = chunk_size or SQLITE_MAX_VARIABLES
    return [items[index : index + size] for index in range(0, len(items), size)]


class ShoalDB:
    """Database manager with persistent singleton connection.

    Uses a single aiosqlite connection (not a pool) with WAL mode enabled
    for concurrent read access. The connection is managed as a singleton
    via get_instance() and can be reset for testing with reset_instance().

    The connection lifecycle:
    - get_instance(): Returns or creates the singleton
    - connect(): Establishes connection and initializes schema with WAL mode
    - close(): Closes the connection
    - reset_instance(): Closes and clears the singleton (tests only)
    """

    _instance: "ShoalDB | None" = None
    _initialized: bool = False

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._update_lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls, db_path: Path | None = None) -> "ShoalDB":
        """Get or create the singleton database instance."""
        if cls._instance is None:
            if db_path is None:
                from shoal.core.config import data_dir, ensure_dirs

                ensure_dirs()
                db_path = data_dir() / "shoal.db"
            cls._instance = cls(db_path)
        return cls._instance

    @classmethod
    async def reset_instance(cls) -> None:
        """Reset singleton instance (primarily for testing)."""
        if cls._instance is not None:
            await cls._instance.close()
            cls._instance = None
            cls._initialized = False

    async def connect(self) -> None:
        """Establish database connection and initialize schema."""
        if self._conn is not None:
            return

        logger.debug("Connecting to database: %s", self.db_path)
        self._conn = await aiosqlite.connect(self.db_path)

        # Enable WAL mode once at connection time
        if not self._initialized:
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._initialize_schema()
            self._initialized = True

    async def _initialize_schema(self) -> None:
        """Create tables if they don't exist."""
        if self._conn is None:
            raise RuntimeError("Database not connected")

        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                data TEXT NOT NULL
            )
        """)
        # Add index on name for faster lookups
        await self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_name ON sessions(name)
        """)
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS conductors (
                name TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        """)
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL,
                status TEXT NOT NULL,
                git_root TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                data TEXT NOT NULL
            )
        """)
        await self._conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_incidents_slug
            ON incidents(slug)
        """)
        await self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_incidents_status_updated
            ON incidents(status, updated_at DESC)
        """)
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS status_transitions (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                from_status TEXT NOT NULL,
                to_status TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                pane_snapshot TEXT
            )
        """)
        await self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_st_session
            ON status_transitions(session_id)
        """)
        await self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_st_timestamp
            ON status_transitions(timestamp)
        """)
        # Agent Bus: session-to-session message queue.
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_session TEXT NOT NULL,
                to_session TEXT NOT NULL,
                topic TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                consumed_at TEXT
            )
        """)
        await self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_to_session
            ON messages(to_session, consumed_at, created_at)
        """)
        # Failure context packets for proactive supervisor.
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS failure_contexts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                session_name TEXT NOT NULL,
                pane_snapshot TEXT NOT NULL,
                old_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                consumed_at TEXT
            )
        """)
        await self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_fc_session
            ON failure_contexts(session_id, consumed_at)
        """)
        # Backfill status_since for existing sessions that predate the field.
        # For each session whose serialised JSON lacks status_since, set it to
        # the timestamp of the most recent status_transitions row, or to
        # last_activity if no transition history exists.
        await self._backfill_status_since()
        await self._backfill_runtime_state()
        await self._conn.commit()

    async def _backfill_status_since(self) -> None:
        """Backfill status_since for sessions created before the field existed."""
        from datetime import UTC, datetime

        if self._conn is None:
            return

        async with self._conn.execute("SELECT id, data FROM sessions") as cursor:
            rows = cast(list[tuple[str, str]], list(await cursor.fetchall()))

        migrated = 0
        for session_id, data_json in rows:
            data = json.loads(data_json)
            if "status_since" in data:
                continue  # already has the field

            # Best estimate: most recent transition into current status.
            async with self._conn.execute(
                "SELECT timestamp FROM status_transitions"
                " WHERE session_id = ? ORDER BY timestamp DESC LIMIT 1",
                (session_id,),
            ) as cur:
                row = await cur.fetchone()

            if row:
                data["status_since"] = row[0]
            else:
                # No transition history — use last_activity as a safe fallback.
                data["status_since"] = data.get("last_activity", datetime.now(UTC).isoformat())

            await self._conn.execute(
                "UPDATE sessions SET data = ? WHERE id = ?",
                (json.dumps(data), session_id),
            )
            migrated += 1
        logger.debug("_backfill_status_since: migrated %d session(s)", migrated)

    async def _backfill_runtime_state(self) -> None:
        """Rewrite legacy tmux fields into the nested runtime payload."""
        if self._conn is None:
            return

        async with self._conn.execute("SELECT id, data FROM sessions") as cursor:
            rows = cast(list[tuple[str, str]], list(await cursor.fetchall()))

        migrated = 0
        for session_id, data_json in rows:
            data = json.loads(data_json)
            if "runtime" in data or "tmux_session" not in data:
                continue

            session = SessionState.model_validate(data)
            await self._conn.execute(
                "UPDATE sessions SET data = ? WHERE id = ?",
                (session.model_dump_json(), session_id),
            )
            migrated += 1
        logger.debug("_backfill_runtime_state: migrated %d session(s)", migrated)

    async def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            logger.debug("Closing database connection")
            await self._conn.close()
            self._conn = None
            self._initialized = False

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Get database connection, ensuring it's initialized."""
        await self.connect()
        if self._conn is None:
            raise RuntimeError("Failed to establish database connection")
        yield self._conn

    async def save_session(self, session: SessionState) -> None:
        """Save or update a session."""
        t0 = time.monotonic()
        async with self._connection() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO sessions (id, name, data) VALUES (?, ?, ?)",
                (session.id, session.name, session.model_dump_json()),
            )
            await conn.commit()
        logger.debug(
            "save_session: %s (%s) (%.1fms)",
            session.id,
            session.name,
            (time.monotonic() - t0) * 1000,
        )

    async def get_session(self, session_id: str) -> SessionState | None:
        """Get a session by ID."""
        t0 = time.monotonic()
        async with (
            self._connection() as conn,
            conn.execute("SELECT data FROM sessions WHERE id = ?", (session_id,)) as cursor,
        ):
            row = await cursor.fetchone()
            logger.debug("get_session: %s (%.1fms)", session_id, (time.monotonic() - t0) * 1000)
            if row:
                return SessionState.model_validate_json(row[0])
        return None

    async def get_sessions(self, session_ids: list[str]) -> dict[str, SessionState]:
        """Get multiple sessions by ID."""
        ids = list(dict.fromkeys(session_ids))
        if not ids:
            return {}

        t0 = time.monotonic()
        result: dict[str, SessionState] = {}
        async with self._connection() as conn:
            for chunk in _chunked(ids):
                placeholders = ", ".join("?" for _ in chunk)
                query = f"SELECT data FROM sessions WHERE id IN ({placeholders})"  # noqa: S608
                async with conn.execute(query, chunk) as cursor:
                    rows = await cursor.fetchall()
                sessions = [SessionState.model_validate_json(row[0]) for row in rows]
                result.update({session.id: session for session in sessions})

        logger.debug(
            "get_sessions: %d requested, %d found (%.1fms)",
            len(ids),
            len(result),
            (time.monotonic() - t0) * 1000,
        )
        return result

    async def list_sessions(self) -> list[SessionState]:
        """List all sessions."""
        t0 = time.monotonic()
        async with self._connection() as conn, conn.execute("SELECT data FROM sessions") as cursor:
            rows = await cursor.fetchall()
            result = [SessionState.model_validate_json(row[0]) for row in rows]
            logger.debug(
                "list_sessions: %d rows (%.1fms)", len(result), (time.monotonic() - t0) * 1000
            )
            return result

    async def find_session_by_name(self, name: str) -> SessionState | None:
        """Find a session by name (indexed lookup)."""
        async with (
            self._connection() as conn,
            conn.execute("SELECT data FROM sessions WHERE name = ?", (name,)) as cursor,
        ):
            row = await cursor.fetchone()
            if row:
                return SessionState.model_validate_json(row[0])
        return None

    async def find_sessions_by_names(self, names: list[str]) -> dict[str, SessionState]:
        """Find multiple sessions by name."""
        unique_names = list(dict.fromkeys(names))
        if not unique_names:
            return {}

        result: dict[str, SessionState] = {}
        async with self._connection() as conn:
            for chunk in _chunked(unique_names):
                placeholders = ", ".join("?" for _ in chunk)
                query = f"SELECT data FROM sessions WHERE name IN ({placeholders})"  # noqa: S608
                async with conn.execute(query, chunk) as cursor:
                    rows = await cursor.fetchall()
                sessions = [SessionState.model_validate_json(row[0]) for row in rows]
                result.update({session.name: session for session in sessions})
        return result

    async def update_session(self, session_id: str, **fields: Any) -> SessionState | None:
        """Update specific fields of a session.

        Uses a lock to prevent concurrent read-modify-write races
        (e.g. watcher vs API on the same event loop).

        Automatically sets ``status_since`` to the current UTC time whenever
        ``status`` is included in the update fields and has actually changed.
        """
        from datetime import UTC, datetime

        t0 = time.monotonic()
        async with self._update_lock:
            session = await self.get_session(session_id)
            if not session:
                return None

            # Auto-advance status_since when status transitions.
            if "status" in fields and fields["status"] != session.status:
                fields.setdefault("status_since", datetime.now(UTC))

            updated = session.model_copy(update=fields)
            await self.save_session(updated)
            logger.debug(
                "update_session: %s fields=%s (%.1fms)",
                session_id,
                list(fields.keys()),
                (time.monotonic() - t0) * 1000,
            )
            return updated

    async def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        t0 = time.monotonic()
        async with self._connection() as conn:
            await conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await conn.commit()
        logger.debug("delete_session: %s (%.1fms)", session_id, (time.monotonic() - t0) * 1000)

    async def save_incident(self, incident: IncidentRecord) -> None:
        """Save or update an incident record."""
        t0 = time.monotonic()
        async with self._connection() as conn:
            await conn.execute(
                "INSERT INTO incidents"
                " (id, slug, status, git_root, created_at, updated_at, data)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    incident.id,
                    incident.slug,
                    incident.status.value,
                    incident.git_root,
                    incident.created_at.isoformat(),
                    incident.updated_at.isoformat(),
                    incident.model_dump_json(),
                ),
            )
            await conn.commit()
        logger.debug(
            "save_incident: %s (%s) (%.1fms)",
            incident.id,
            incident.slug,
            (time.monotonic() - t0) * 1000,
        )

    async def get_incident(self, incident_id: str) -> IncidentRecord | None:
        """Get an incident by ID."""
        t0 = time.monotonic()
        async with (
            self._connection() as conn,
            conn.execute("SELECT data FROM incidents WHERE id = ?", (incident_id,)) as cursor,
        ):
            row = await cursor.fetchone()
            logger.debug("get_incident: %s (%.1fms)", incident_id, (time.monotonic() - t0) * 1000)
            if row:
                return IncidentRecord.model_validate_json(row[0])
        return None

    async def find_incident_by_slug(self, slug: str) -> IncidentRecord | None:
        """Find an incident by slug."""
        async with (
            self._connection() as conn,
            conn.execute("SELECT data FROM incidents WHERE slug = ?", (slug,)) as cursor,
        ):
            row = await cursor.fetchone()
            if row:
                return IncidentRecord.model_validate_json(row[0])
        return None

    async def list_incidents(self, status: str | None = None) -> list[IncidentRecord]:
        """List incident records, optionally filtered by status."""
        t0 = time.monotonic()
        query = "SELECT data FROM incidents"
        params: tuple[object, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY updated_at DESC, created_at DESC"
        async with self._connection() as conn, conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            result = [IncidentRecord.model_validate_json(row[0]) for row in rows]
            logger.debug(
                "list_incidents: %d rows status=%s (%.1fms)",
                len(result),
                status,
                (time.monotonic() - t0) * 1000,
            )
            return result

    async def update_incident(self, incident_id: str, **fields: Any) -> IncidentRecord | None:
        """Update specific fields of an incident."""
        from datetime import UTC, datetime

        t0 = time.monotonic()
        async with self._update_lock:
            incident = await self.get_incident(incident_id)
            if not incident:
                return None

            fields.setdefault("updated_at", datetime.now(UTC))
            updated = incident.model_copy(update=fields)
            async with self._connection() as conn:
                await conn.execute(
                    "UPDATE incidents SET slug = ?, status = ?, git_root = ?, created_at = ?, "
                    "updated_at = ?, data = ? WHERE id = ?",
                    (
                        updated.slug,
                        updated.status.value,
                        updated.git_root,
                        updated.created_at.isoformat(),
                        updated.updated_at.isoformat(),
                        updated.model_dump_json(),
                        updated.id,
                    ),
                )
                await conn.commit()
            logger.debug(
                "update_incident: %s fields=%s (%.1fms)",
                incident_id,
                list(fields.keys()),
                (time.monotonic() - t0) * 1000,
            )
            return updated

    async def delete_incident(self, incident_id: str) -> None:
        """Delete an incident."""
        t0 = time.monotonic()
        async with self._connection() as conn:
            await conn.execute("DELETE FROM incidents WHERE id = ?", (incident_id,))
            await conn.commit()
        logger.debug("delete_incident: %s (%.1fms)", incident_id, (time.monotonic() - t0) * 1000)

    async def save_robo(self, state: RoboState) -> None:
        """Save or update robo state."""
        async with self._connection() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO conductors (name, data) VALUES (?, ?)",
                (state.name, state.model_dump_json()),
            )
            await conn.commit()

    async def get_robo(self, name: str) -> RoboState | None:
        """Get robo state by name."""
        async with (
            self._connection() as conn,
            conn.execute("SELECT data FROM conductors WHERE name = ?", (name,)) as cursor,
        ):
            row = await cursor.fetchone()
            if row:
                return RoboState.model_validate_json(row[0])
        return None

    async def list_robos(self) -> list[RoboState]:
        """List all robos."""
        async with (
            self._connection() as conn,
            conn.execute("SELECT data FROM conductors") as cursor,
        ):
            rows = await cursor.fetchall()
            return [RoboState.model_validate_json(row[0]) for row in rows]

    async def save_status_transition(
        self,
        session_id: str,
        from_status: str,
        to_status: str,
        pane_snapshot: str | None = None,
    ) -> str:
        """Record a status transition. Returns the generated transition ID."""
        import uuid
        from datetime import UTC, datetime

        t0 = time.monotonic()
        transition_id = str(uuid.uuid4())
        timestamp = datetime.now(UTC).isoformat()
        async with self._connection() as conn:
            await conn.execute(
                "INSERT INTO status_transitions"
                " (id, session_id, from_status, to_status, timestamp, pane_snapshot)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (transition_id, session_id, from_status, to_status, timestamp, pane_snapshot),
            )
            await conn.commit()
        logger.debug(
            "save_status_transition: %s %s→%s (%.1fms)",
            session_id,
            from_status,
            to_status,
            (time.monotonic() - t0) * 1000,
        )
        return transition_id

    async def get_status_transitions(
        self, session_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get status transitions for a session, ordered by timestamp descending."""
        t0 = time.monotonic()
        async with (
            self._connection() as conn,
            conn.execute(
                "SELECT id, session_id, from_status, to_status, timestamp, pane_snapshot"
                " FROM status_transitions WHERE session_id = ?"
                " ORDER BY timestamp DESC LIMIT ?",
                (session_id, limit),
            ) as cursor,
        ):
            rows = await cursor.fetchall()
            result = [
                {
                    "id": row[0],
                    "session_id": row[1],
                    "from_status": row[2],
                    "to_status": row[3],
                    "timestamp": row[4],
                    "pane_snapshot": row[5],
                }
                for row in rows
            ]
            logger.debug(
                "get_status_transitions: %s %d rows (%.1fms)",
                session_id,
                len(result),
                (time.monotonic() - t0) * 1000,
            )
            return result

    # -----------------------------------------------------------------------
    # Agent Bus: session-to-session message queue
    # -----------------------------------------------------------------------

    async def send_message(
        self,
        from_session: str,
        to_session: str,
        topic: str,
        payload: str,
    ) -> int:
        """Insert a message and return its auto-assigned ID."""
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        async with self._connection() as conn:
            cursor = await conn.execute(
                "INSERT INTO messages (from_session, to_session, topic, payload, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (from_session, to_session, topic, payload, now),
            )
            await conn.commit()
        return cursor.lastrowid or 0

    async def receive_messages(
        self,
        to_session: str,
        topic: str | None = None,
        *,
        unconsumed_only: bool = True,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        """Fetch messages addressed to a session."""
        parts = ["SELECT id, from_session, to_session, topic, payload, created_at, consumed_at"]
        parts.append("FROM messages WHERE to_session = ?")
        params: list[object] = [to_session]
        if unconsumed_only:
            parts.append("AND consumed_at IS NULL")
        if topic is not None:
            parts.append("AND topic = ?")
            params.append(topic)
        parts.append("ORDER BY created_at ASC LIMIT ?")
        params.append(limit)
        sql = " ".join(parts)

        async with (
            self._connection() as conn,
            conn.execute(sql, params) as cursor,
        ):
            rows = await cursor.fetchall()
        return [
            {
                "id": row[0],
                "from_session": row[1],
                "to_session": row[2],
                "topic": row[3],
                "payload": row[4],
                "created_at": row[5],
                "consumed_at": row[6],
            }
            for row in rows
        ]

    async def mark_message_consumed(self, message_id: int) -> None:
        """Mark a message as consumed."""
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        async with self._connection() as conn:
            await conn.execute(
                "UPDATE messages SET consumed_at = ? WHERE id = ?",
                (now, message_id),
            )
            await conn.commit()

    async def purge_old_messages(self, older_than_seconds: int = 86_400) -> int:
        """Delete consumed messages older than ``older_than_seconds``."""
        from datetime import UTC, datetime, timedelta

        cutoff = (datetime.now(UTC) - timedelta(seconds=older_than_seconds)).isoformat()
        async with self._connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM messages WHERE consumed_at IS NOT NULL AND consumed_at < ?",
                (cutoff,),
            )
            await conn.commit()
        return cursor.rowcount or 0

    # -----------------------------------------------------------------------
    # Proactive Supervisor: failure context packets
    # -----------------------------------------------------------------------

    async def save_failure_context(
        self,
        session_id: str,
        session_name: str,
        pane_snapshot: str,
        old_status: str,
    ) -> int:
        """Insert a failure context packet and return its ID."""
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        async with self._connection() as conn:
            cursor = await conn.execute(
                "INSERT INTO failure_contexts"
                " (session_id, session_name, pane_snapshot, old_status, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (session_id, session_name, pane_snapshot, old_status, now),
            )
            await conn.commit()
        return cursor.lastrowid or 0

    async def get_failure_context(
        self,
        session_id: str,
        *,
        unconsumed_only: bool = True,
    ) -> dict[str, object] | None:
        """Return the most recent failure context packet for a session."""
        # Build query using fixed clauses — no user input in the SQL skeleton.
        params: list[object] = [session_id]
        sql = (
            "SELECT id, session_id, session_name, pane_snapshot, old_status, created_at"
            " FROM failure_contexts WHERE session_id = ?"
        )
        if unconsumed_only:
            sql += " AND consumed_at IS NULL"
        sql += " ORDER BY created_at DESC LIMIT 1"
        async with (
            self._connection() as conn,
            conn.execute(sql, params) as cursor,
        ):
            row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "session_id": row[1],
            "session_name": row[2],
            "pane_snapshot": row[3],
            "old_status": row[4],
            "created_at": row[5],
        }

    async def consume_failure_context(self, context_id: int) -> None:
        """Mark a failure context packet as consumed."""
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        async with self._connection() as conn:
            await conn.execute(
                "UPDATE failure_contexts SET consumed_at = ? WHERE id = ?",
                (now, context_id),
            )
            await conn.commit()

    async def expire_old_failure_contexts(self, session_id: str, ttl_seconds: int = 3600) -> None:
        """Expire unconsumed failure contexts older than ttl_seconds."""
        from datetime import UTC, datetime, timedelta

        cutoff = (datetime.now(UTC) - timedelta(seconds=ttl_seconds)).isoformat()
        now = datetime.now(UTC).isoformat()
        async with self._connection() as conn:
            await conn.execute(
                "UPDATE failure_contexts SET consumed_at = ?"
                " WHERE session_id = ? AND consumed_at IS NULL AND created_at < ?",
                (now, session_id, cutoff),
            )
            await conn.commit()


async def get_db() -> ShoalDB:
    """Get the global database instance."""
    return await ShoalDB.get_instance()


async def with_db[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine and close the DB connection afterward.

    Use this to wrap coroutines passed to asyncio.run() in CLI
    entry points so the aiosqlite background thread is properly
    stopped and the process can exit cleanly.

    Example:
        asyncio.run(with_db(_ls_impl(format)))
    """
    try:
        return await coro
    finally:
        await ShoalDB.reset_instance()
