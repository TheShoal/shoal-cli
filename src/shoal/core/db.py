"""Async SQLite database for Shoal session and conductor state."""

import aiosqlite
from pathlib import Path
from typing import Any
from shoal.models.state import SessionState, ConductorState

class ShoalDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    async def initialize(self):
        """Create tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    data TEXT NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS conductors (
                    name TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                )
            """)
            await db.commit()

    async def save_session(self, session: SessionState):
        """Save or update a session."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO sessions (id, name, data) VALUES (?, ?, ?)",
                (session.id, session.name, session.model_dump_json())
            )
            await db.commit()

    async def get_session(self, session_id: str) -> SessionState | None:
        """Get a session by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT data FROM sessions WHERE id = ?", (session_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return SessionState.model_validate_json(row[0])
        return None

    async def list_sessions(self) -> list[SessionState]:
        """List all sessions."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT data FROM sessions") as cursor:
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
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await db.commit()

    async def save_conductor(self, state: ConductorState):
        """Save or update conductor state."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO conductors (name, data) VALUES (?, ?)",
                (state.name, state.model_dump_json())
            )
            await db.commit()

    async def get_conductor(self, name: str) -> ConductorState | None:
        """Get conductor state by name."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT data FROM conductors WHERE name = ?", (name,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return ConductorState.model_validate_json(row[0])
        return None

    async def list_conductors(self) -> list[ConductorState]:
        """List all conductors."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT data FROM conductors") as cursor:
                rows = await cursor.fetchall()
                return [ConductorState.model_validate_json(row[0]) for row in rows]

async def get_db() -> ShoalDB:
    """Get the global database instance."""
    from shoal.core.config import state_dir, ensure_dirs
    ensure_dirs()
    db_path = state_dir() / "shoal.db"
    db = ShoalDB(db_path)
    await db.initialize()
    return db
