"""Async SQLite database for Shoal session and robo state."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

from shoal.models.state import RoboState, SessionState

logger = logging.getLogger("shoal.db")


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
        await self._conn.commit()

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

    async def update_session(self, session_id: str, **fields: Any) -> SessionState | None:
        """Update specific fields of a session.

        Uses a lock to prevent concurrent read-modify-write races
        (e.g. watcher vs API on the same event loop).
        """
        t0 = time.monotonic()
        async with self._update_lock:
            session = await self.get_session(session_id)
            if not session:
                return None

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
