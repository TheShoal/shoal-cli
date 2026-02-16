"""Async SQLite database for Shoal session and conductor state."""

import aiosqlite
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator
from shoal.models.state import SessionState, ConductorState


class ShoalDB:
    """Database manager with persistent connection pool."""

    _instance: "ShoalDB | None" = None
    _initialized: bool = False

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    @classmethod
    async def get_instance(cls, db_path: Path | None = None) -> "ShoalDB":
        """Get or create the singleton database instance."""
        if cls._instance is None:
            if db_path is None:
                from shoal.core.config import state_dir, ensure_dirs

                ensure_dirs()
                db_path = state_dir() / "shoal.db"
            cls._instance = cls(db_path)
        return cls._instance

    @classmethod
    async def reset_instance(cls):
        """Reset singleton instance (primarily for testing)."""
        if cls._instance is not None:
            await cls._instance.close()
            cls._instance = None
            cls._initialized = False

    async def connect(self):
        """Establish database connection and initialize schema."""
        if self._conn is not None:
            return

        self._conn = await aiosqlite.connect(self.db_path)

        # Enable WAL mode once at connection time
        if not self._initialized:
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._initialize_schema()
            self._initialized = True

    async def _initialize_schema(self):
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
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS conductors (
                name TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        """)
        await self._conn.commit()

    async def close(self):
        """Close database connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Get database connection, ensuring it's initialized."""
        await self.connect()
        if self._conn is None:
            raise RuntimeError("Failed to establish database connection")
        yield self._conn

    async def save_session(self, session: SessionState):
        """Save or update a session."""
        async with self._connection() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO sessions (id, name, data) VALUES (?, ?, ?)",
                (session.id, session.name, session.model_dump_json()),
            )
            await conn.commit()

    async def get_session(self, session_id: str) -> SessionState | None:
        """Get a session by ID."""
        async with self._connection() as conn:
            async with conn.execute(
                "SELECT data FROM sessions WHERE id = ?", (session_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return SessionState.model_validate_json(row[0])
        return None

    async def list_sessions(self) -> list[SessionState]:
        """List all sessions."""
        async with self._connection() as conn:
            async with conn.execute("SELECT data FROM sessions") as cursor:
                rows = await cursor.fetchall()
                return [SessionState.model_validate_json(row[0]) for row in rows]

    async def update_session(self, session_id: str, **fields: Any) -> SessionState | None:
        """Update specific fields of a session."""
        session = await self.get_session(session_id)
        if not session:
            return None

        updated = session.model_copy(update=fields)
        await self.save_session(updated)
        return updated

    async def delete_session(self, session_id: str):
        """Delete a session."""
        async with self._connection() as conn:
            await conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await conn.commit()

    async def save_conductor(self, state: ConductorState):
        """Save or update conductor state."""
        async with self._connection() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO conductors (name, data) VALUES (?, ?)",
                (state.name, state.model_dump_json()),
            )
            await conn.commit()

    async def get_conductor(self, name: str) -> ConductorState | None:
        """Get conductor state by name."""
        async with self._connection() as conn:
            async with conn.execute(
                "SELECT data FROM conductors WHERE name = ?", (name,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return ConductorState.model_validate_json(row[0])
        return None

    async def list_conductors(self) -> list[ConductorState]:
        """List all conductors."""
        async with self._connection() as conn:
            async with conn.execute("SELECT data FROM conductors") as cursor:
                rows = await cursor.fetchall()
                return [ConductorState.model_validate_json(row[0]) for row in rows]


async def get_db() -> ShoalDB:
    """Get the global database instance."""
    return await ShoalDB.get_instance()
