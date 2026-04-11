"""
PantheonGraph: Knowledge graph layer for Shoal sessions using LadybugDB.

This module wraps the real_ladybug Python SDK to provide a structured
knowledge graph for tracking sessions, tasks, Linear issues, GitHub PRs,
and findings across the Pantheon stack.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import ladybug as lb

logger = logging.getLogger(__name__)

# Default path for the Pantheon knowledge graph
DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "shoal" / "pantheon_kg.ladybug"


class PantheonGraph:
    """
    Knowledge graph wrapper for LadybugDB.

    Provides structured methods for upserting sessions, linking to Linear/GitHub,
    and querying work and findings.
    """

    def __init__(self, db_path: str | Path | None = None):
        """
        Initialize the PantheonGraph.

        Args:
            db_path: Path to the LadybugDB database.
                Defaults to ~/.local/share/shoal/pantheon_kg.ladybug
        """
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._db = lb.Database(str(self.db_path))
        self._conn: lb.Connection | None = None
        self._initialized = False

    def _get_connection(self) -> lb.Connection:
        """Get or create a database connection."""
        if self._conn is None:
            self._conn = lb.Connection(self._db)
        return self._conn

    async def initialize(self) -> None:
        """
        Initialize the database schema.

        Creates nodes: Session, Task, LinearIssue, GitHubPR, GitHubIssue, File, Finding
        Creates relationships: RAN, WORKED_ON, CREATED_PR, PRODUCED, FOUND
        """
        if self._initialized:
            return

        conn = self._get_connection()

        # Create node types using Cypher
        node_creates = [
            (
                "CREATE NODE TABLE Session (id STRING PRIMARY KEY, name STRING, "
                "planet STRING, status STRING, created_at STRING)"
            ),
            (
                "CREATE NODE TABLE Task (id STRING PRIMARY KEY, title STRING, "
                "status STRING, priority STRING)"
            ),
            (
                "CREATE NODE TABLE LinearIssue (id STRING PRIMARY KEY, identifier STRING, "
                "title STRING, state STRING, url STRING)"
            ),
            (
                "CREATE NODE TABLE GitHubPR (id STRING PRIMARY KEY, number INT64, "
                "title STRING, state STRING, url STRING)"
            ),
            (
                "CREATE NODE TABLE GitHubIssue (id STRING PRIMARY KEY, number INT64, "
                "title STRING, state STRING, url STRING)"
            ),
            "CREATE NODE TABLE File (path STRING PRIMARY KEY, content_hash STRING)",
            (
                "CREATE NODE TABLE Finding (id STRING PRIMARY KEY, type STRING, "
                "description STRING, severity STRING, session_id STRING)"
            ),
        ]

        rel_creates = [
            "CREATE REL TABLE RAN (FROM Session TO Task)",
            "CREATE REL TABLE WORKED_ON (FROM Session TO LinearIssue)",
            "CREATE REL TABLE CREATED_PR (FROM Session TO GitHubPR)",
            "CREATE REL TABLE PRODUCED (FROM Session TO File)",
            "CREATE REL TABLE FOUND (FROM Session TO Finding)",
        ]

        try:
            for stmt in node_creates + rel_creates:
                conn.execute(stmt)
            self._initialized = True
            logger.info("PantheonGraph schema initialized at %s", self.db_path)
        except Exception as e:
            # Schema might already exist (idempotent)
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                self._initialized = True
                logger.info("PantheonGraph schema already exists")
            else:
                raise

    async def upsert_session(self, session_data: dict) -> None:
        """
        Upsert a session node.

        Args:
            session_data: Dict with keys: id, name, planet, status, created_at
        """
        await self.initialize()
        conn = self._get_connection()

        query = """
        MERGE (s:Session {id: $id})
        SET s.name = $name, s.planet = $planet, s.status = $status, s.created_at = $created_at
        """
        conn.execute(
            query,
            parameters={
                "id": session_data.get("id"),
                "name": session_data.get("name"),
                "planet": session_data.get("planet"),
                "status": session_data.get("status"),
                "created_at": session_data.get("created_at"),
            },
        )

    async def link_session_to_linear(self, session_id: str, linear_issue: dict) -> None:
        """
        Link a session to a Linear issue via WORKED_ON relationship.

        Args:
            session_id: The session ID
            linear_issue: Dict with keys: id, identifier, title, state, url
        """
        await self.initialize()
        conn = self._get_connection()

        # Upsert LinearIssue
        issue_query = """
        MERGE (l:LinearIssue {id: $id})
        SET l.identifier = $identifier, l.title = $title, l.state = $state, l.url = $url
        """
        conn.execute(
            issue_query,
            parameters={
                "id": linear_issue.get("id"),
                "identifier": linear_issue.get("identifier"),
                "title": linear_issue.get("title"),
                "state": linear_issue.get("state"),
                "url": linear_issue.get("url"),
            },
        )

        # Create relationship
        rel_query = """
        MATCH (s:Session {id: $session_id}), (l:LinearIssue {id: $issue_id})
        CREATE (s)-[r:WORKED_ON]->(l)
        """
        conn.execute(
            rel_query,
            parameters={
                "session_id": session_id,
                "issue_id": linear_issue.get("id"),
            },
        )

    async def link_session_to_github_pr(self, session_id: str, pr_data: dict) -> None:
        """
        Link a session to a GitHub PR via CREATED_PR relationship.

        Args:
            session_id: The session ID
            pr_data: Dict with keys: id, number, title, state, url
        """
        await self.initialize()
        conn = self._get_connection()

        # Upsert GitHubPR
        pr_query = """
        MERGE (p:GitHubPR {id: $id})
        SET p.number = $number, p.title = $title, p.state = $state, p.url = $url
        """
        conn.execute(
            pr_query,
            parameters={
                "id": pr_data.get("id"),
                "number": pr_data.get("number"),
                "title": pr_data.get("title"),
                "state": pr_data.get("state"),
                "url": pr_data.get("url"),
            },
        )

        # Create relationship
        rel_query = """
        MATCH (s:Session {id: $session_id}), (p:GitHubPR {id: $pr_id})
        CREATE (s)-[r:CREATED_PR]->(p)
        """
        conn.execute(
            rel_query,
            parameters={
                "session_id": session_id,
                "pr_id": pr_data.get("id"),
            },
        )

    async def write_findings(self, session_id: str, findings: list[str]) -> None:
        """
        Write findings linked to a session via FOUND relationship.

        Args:
            session_id: The session ID
            findings: List of finding descriptions (creates Finding nodes)
        """
        await self.initialize()
        conn = self._get_connection()

        for idx, description in enumerate(findings):
            finding_id = f"{session_id}-finding-{idx}"
            finding_type = "observation"  # Default type

            # Determine severity based on keywords
            severity = "low"
            if any(kw in description.lower() for kw in ["bug", "error", "critical", "security"]):
                severity = "high"
            elif any(kw in description.lower() for kw in ["warning", "deprecation", "tech-debt"]):
                severity = "medium"

            # Create Finding node
            finding_query = """
            MERGE (f:Finding {id: $id})
            SET f.type = $type, f.description = $description,
                f.severity = $severity, f.session_id = $session_id
            """
            conn.execute(
                finding_query,
                parameters={
                    "id": finding_id,
                    "type": finding_type,
                    "description": description,
                    "severity": severity,
                    "session_id": session_id,
                },
            )

            # Link to session
            link_query = """
            MATCH (s:Session {id: $session_id}), (f:Finding {id: $finding_id})
            CREATE (s)-[r:FOUND]->(f)
            """
            conn.execute(
                link_query,
                parameters={
                    "session_id": session_id,
                    "finding_id": finding_id,
                },
            )

    async def query_session_work(self, session_id: str) -> list[dict]:
        """
        Query all work associated with a session.

        Returns Linear issues and GitHub PRs linked via WORKED_ON and CREATED_PR.

        Args:
            session_id: The session ID to query

        Returns:
            List of dicts with work items and their types
        """
        await self.initialize()
        conn = self._get_connection()

        results = []

        # Query Linear issues
        linear_query = """
        MATCH (s:Session {id: $session_id})-[r:WORKED_ON]->(l:LinearIssue)
        RETURN l.id as id, l.identifier as identifier, l.title as title,
               l.state as state, l.url as url, 'linear' as source
        """
        result = conn.execute(linear_query, parameters={"session_id": session_id})
        results.extend(dict(row) if isinstance(row, dict) else row for row in result.get_all())

        # Query GitHub PRs
        pr_query = """
        MATCH (s:Session {id: $session_id})-[r:CREATED_PR]->(p:GitHubPR)
        RETURN p.id as id, p.number as number, p.title as title,
               p.state as state, p.url as url, 'github_pr' as source
        """
        result = conn.execute(pr_query, parameters={"session_id": session_id})
        results.extend(dict(row) if isinstance(row, dict) else row for row in result.get_all())

        return results

    async def query_findings(self, entity_name: str) -> list[dict]:
        """
        Query findings for a specific entity type.

        Args:
            entity_name: The type of findings to query (e.g., 'high', 'medium', 'low')

        Returns:
            List of finding dicts
        """
        await self.initialize()
        conn = self._get_connection()

        query = """
        MATCH (f:Finding)
        WHERE f.severity = $severity OR $severity = 'all'
        RETURN f.id as id, f.type as type, f.description as description,
               f.severity as severity, f.session_id as session_id
        """
        result = conn.execute(
            query, parameters={"severity": entity_name if entity_name != "all" else "all"}
        )

        return [dict(row) if isinstance(row, dict) else row for row in result.get_all()]


async def _run_integration_test():
    """Quick integration test for PantheonGraph."""
    import tempfile

    # Use a temporary database for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_pantheon_kg.ladybug"
        graph = PantheonGraph(db_path)

        print("1. Testing initialize...")
        await graph.initialize()
        print("   Schema initialized successfully")

        print("2. Testing upsert_session...")
        await graph.upsert_session(
            {
                "id": "test-session-001",
                "name": "AIA-123-fix",
                "planet": "mars",
                "status": "in_progress",
                "created_at": "2026-04-09T12:00:00Z",
            }
        )
        print("   Session upserted successfully")

        print("3. Testing link_session_to_linear...")
        await graph.link_session_to_linear(
            "test-session-001",
            {
                "id": "lin-123",
                "identifier": "AIA-123",
                "title": "Fix critical bug",
                "state": "in_progress",
                "url": "https://linear.app/usmobile/issue/AIA-123",
            },
        )
        print("   Session linked to Linear issue")

        print("4. Testing link_session_to_github_pr...")
        await graph.link_session_to_github_pr(
            "test-session-001",
            {
                "id": "pr-456",
                "number": 789,
                "title": "feat: fix critical bug",
                "state": "open",
                "url": "https://github.com/usmobile/smorgasbord/pull/789",
            },
        )
        print("   Session linked to GitHub PR")

        print("5. Testing write_findings...")
        await graph.write_findings(
            "test-session-001",
            [
                "Found that the config was missing a required field",
                "WARNING: deprecated API in use",
                "Security: hardcoded token found in config.yaml",
            ],
        )
        print("   Findings written successfully")

        print("6. Testing query_session_work...")
        work = await graph.query_session_work("test-session-001")
        print(f"   Found {len(work)} work items: {work}")

        print("7. Testing query_findings...")
        findings = await graph.query_findings("high")
        print(f"   Found {len(findings)} high-severity findings")

        print("\nAll tests passed!")


if __name__ == "__main__":
    print("Running PantheonGraph integration test...\n")
    asyncio.run(_run_integration_test())
