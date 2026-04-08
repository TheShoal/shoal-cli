"""Linear issue cache for fast local queries."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from shoal.core.db import ShoalDB
from shoal.services.linear_bridge import LinearIssue, get_linear_bridge

logger = logging.getLogger("shoal.linear_cache")


class LinearCache:
    """SQLite-backed cache for Linear issues.

    Stores issues locally for fast queries without hitting the Linear API.
    Sync is explicit - call sync_team_issues() to refresh the cache.
    """

    async def sync_team_issues(self, team_key: str) -> int:
        """Sync all issues for a team from Linear API to local cache.

        Returns:
            Number of issues synced.
        """
        bridge = get_linear_bridge()
        try:
            issues = await bridge.list_team_issues(team_key, ready_only=False)
            db = await ShoalDB.get_instance()
            await db.connect()
            now = datetime.now(UTC).isoformat()

            count = 0
            async with db._connection() as conn:
                for issue in issues:
                    await conn.execute(
                        """
                        INSERT OR REPLACE INTO linear_issues
                        (id, identifier, team_key, title, description, state_name,
                         state_type, priority, assignee_name, branch_name, url,
                         labels, synced_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            issue.id,
                            issue.identifier,
                            team_key.upper(),
                            issue.title,
                            issue.description or "",
                            issue.state_name,
                            issue.state_type,
                            issue.priority,
                            issue.assignee_name or "",
                            issue.branch_name or "",
                            issue.url,
                            json.dumps(issue.labels),
                            now,
                            None,  # updated_at not available from API
                        ),
                    )
                    count += 1

                await conn.commit()
            logger.info("sync_team_issues: synced %d issues for %s", count, team_key)
            return count
        finally:
            await bridge.close()

    async def get_cached_issues(
        self,
        team_key: str,
        *,
        ready_only: bool = False,
        mine_only: bool = False,
    ) -> list[LinearIssue]:
        """Get issues from local cache.

        Args:
            team_key: Team key (e.g. "BE")
            ready_only: Filter to unstarted issues
            mine_only: Filter to assigned issues (requires user matching)

        Returns:
            List of LinearIssue objects from cache.
        """
        db = await ShoalDB.get_instance()
        query = "SELECT * FROM linear_issues WHERE team_key = ?"
        params: list[str | int] = [team_key.upper()]

        if ready_only:
            query += " AND state_type = ?"
            params.append("unstarted")

        query += " ORDER BY priority, identifier"

        async with db._connection() as conn:
            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()

        issues: list[LinearIssue] = []
        for row in rows:
            issue = LinearIssue(
                id=row[0],
                identifier=row[1],
                title=row[3],
                description=row[4] or "",
                state_name=row[5] or "",
                state_type=row[6] or "",
                priority=row[7] or 0,
                assignee_name=row[8] or "",
                branch_name=row[9] or "",
                url=row[10] or "",
                labels=json.loads(row[11]) if row[11] else [],
            )
            # mine_only filter requires knowing current user - skip for now
            issues.append(issue)

        return issues

    async def get_issue(self, identifier: str) -> LinearIssue | None:
        """Get a single issue from cache by identifier.

        Args:
            identifier: Issue ID like "BE-1234"

        Returns:
            LinearIssue or None if not in cache.
        """
        db = await ShoalDB.get_instance()
        async with db._connection() as conn:
            async with conn.execute(
                "SELECT * FROM linear_issues WHERE identifier = ?",
                (identifier.upper(),),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        return LinearIssue(
            id=row[0],
            identifier=row[1],
            title=row[3],
            description=row[4] or "",
            state_name=row[5] or "",
            state_type=row[6] or "",
            priority=row[7] or 0,
            assignee_name=row[8] or "",
            branch_name=row[9] or "",
            url=row[10] or "",
            labels=json.loads(row[11]) if row[11] else [],
        )

    async def invalidate(self, team_key: str) -> None:
        """Clear cached issues for a team."""
        db = await ShoalDB.get_instance()
        async with db._connection() as conn:
            await conn.execute(
                "DELETE FROM linear_issues WHERE team_key = ?",
                (team_key.upper(),),
            )
            await conn.commit()
        logger.info("invalidate: cleared cache for %s", team_key)

    async def last_sync_at(self, team_key: str) -> datetime | None:
        """Get the timestamp of the last sync for a team."""
        db = await ShoalDB.get_instance()
        async with db._connection() as conn:
            async with conn.execute(
                "SELECT MAX(synced_at) FROM linear_issues WHERE team_key = ?",
                (team_key.upper(),),
            ) as cursor:
                row = await cursor.fetchone()

        if row and row[0]:
            return datetime.fromisoformat(row[0])
        return None


# Singleton instance
_cache: LinearCache | None = None


def get_linear_cache() -> LinearCache:
    """Get the singleton LinearCache instance."""
    global _cache
    if _cache is None:
        _cache = LinearCache()
    return _cache
