"""Async SQLite database for Shoal session and robo state."""

import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

from shoal.models.state import RoboState, SessionState


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
                from shoal.core.config import ensure_dirs, state_dir

                ensure_dirs()
                db_path = state_dir() / "shoal.db"
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
        await self._conn.commit()

    async def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
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
        async with self._connection() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO sessions (id, name, data) VALUES (?, ?, ?)",
                (session.id, session.name, session.model_dump_json()),
            )
            await conn.commit()

    async def get_session(self, session_id: str) -> SessionState | None:
        """Get a session by ID."""
        async with (
            self._connection() as conn,
            conn.execute("SELECT data FROM sessions WHERE id = ?", (session_id,)) as cursor,
        ):
            row = await cursor.fetchone()
            if row:
                return SessionState.model_validate_json(row[0])
        return None

    async def list_sessions(self) -> list[SessionState]:
        """List all sessions."""
        async with self._connection() as conn, conn.execute("SELECT data FROM sessions") as cursor:
            rows = await cursor.fetchall()
            return [SessionState.model_validate_json(row[0]) for row in rows]

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
        async with self._update_lock:
            session = await self.get_session(session_id)
            if not session:
                return None

            updated = session.model_copy(update=fields)
            await self.save_session(updated)
            return updated

    async def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        async with self._connection() as conn:
            await conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await conn.commit()

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

    # Backward compatibility aliases
    save_conductor = save_robo
    get_conductor = get_robo
    list_conductors = list_robos


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
