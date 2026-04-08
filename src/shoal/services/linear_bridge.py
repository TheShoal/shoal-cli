"""Linear GraphQL API bridge.

Provides async client for Linear REST/GraphQL operations used by the CLI.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "LinearBridge",
    "LinearIssue",
    "LinearNamedTarget",
    "LinearPostedUpdate",
    "get_linear_bridge",
]

_ENDPOINT = "https://api.linear.app/graphql"

LinearTargetKind = Literal["project", "initiative"]
LinearUpdateHealth = Literal["onTrack", "atRisk", "offTrack"]

_QUERY_TEAM_ISSUES = """
query TeamIssues($teamKey: String!, $first: Int) {
  issues(
    filter: { team: { key: { eq: $teamKey } } },
    first: $first
  ) {
    nodes {
      id
      identifier
      title
      description
      url
      priority
      branchName
      state { name type }
      assignee { name }
      labels { nodes { name } }
    }
  }
}
"""

_QUERY_TEAM_ISSUES_BY_STATE = """
query TeamIssuesByState($teamKey: String!, $first: Int, $stateType: String!) {
  issues(
    filter: { team: { key: { eq: $teamKey } }, state: { type: { eq: $stateType } } },
    first: $first
  ) {
    nodes {
      id
      identifier
      title
      description
      url
      priority
      branchName
      state { name type }
      assignee { name }
      labels { nodes { name } }
    }
  }
}
"""

_QUERY_ISSUE = """
query Issue($identifier: String!) {
  issueFilter(filters: { identifier: { eq: $identifier } }) {
    id
    identifier
    title
    description
    url
    priority
    branchName
    state { name type }
    assignee { name }
    labels { nodes { name } }
  }
}
"""

_QUERY_PROJECT_BY_ID = """
query Project($id: String!) {
  project(id: $id) {
    id
    name
    slugId
    url
  }
}
"""

_QUERY_PROJECTS_BY_SLUG = """
query ProjectsBySlug($slug: String!) {
  projects(filter: { slugId: { eq: $slug } }, first: 2) {
    nodes {
      id
      name
      slugId
      url
    }
  }
}
"""

_QUERY_PROJECTS_BY_NAME = """
query ProjectsByName($name: String!) {
  projects(filter: { name: { eq: $name } }, first: 2) {
    nodes {
      id
      name
      slugId
      url
    }
  }
}
"""

_QUERY_INITIATIVE_BY_ID = """
query Initiative($id: String!) {
  initiative(id: $id) {
    id
    name
    slugId
    url
  }
}
"""

_QUERY_INITIATIVES_BY_SLUG = """
query InitiativesBySlug($slug: String!) {
  initiatives(filter: { slugId: { eq: $slug } }, first: 2) {
    nodes {
      id
      name
      slugId
      url
    }
  }
}
"""

_QUERY_INITIATIVES_BY_NAME = """
query InitiativesByName($name: String!) {
  initiatives(filter: { name: { eq: $name } }, first: 2) {
    nodes {
      id
      name
      slugId
      url
    }
  }
}
"""

_MUTATION_UPDATE_STATE = """
mutation UpdateIssue($id: String!, $stateId: String!) {
  issueUpdate(id: $id, input: { stateId: $stateId }) {
    success
  }
}
"""

_MUTATION_ADD_COMMENT = """
mutation CreateComment($issueId: String!, $body: String!) {
  commentCreate(input: { issueId: $issueId, body: $body }) {
    success
  }
}
"""

_MUTATION_CREATE_PROJECT_UPDATE = """
mutation CreateProjectUpdate($input: ProjectUpdateCreateInput!) {
  projectUpdateCreate(input: $input) {
    success
    projectUpdate {
      id
      url
    }
  }
}
"""

_MUTATION_CREATE_INITIATIVE_UPDATE = """
mutation CreateInitiativeUpdate($input: InitiativeUpdateCreateInput!) {
  initiativeUpdateCreate(input: $input) {
    success
    initiativeUpdate {
      id
      url
    }
  }
}
"""


class LinearIssue(BaseModel):
    """Linear issue data extracted from GraphQL response."""

    model_config = ConfigDict(extra="forbid")

    id: str = ""
    identifier: str = ""
    title: str = ""
    description: str = ""
    state_name: str = ""
    state_type: str = ""
    priority: int = 0
    assignee_name: str = ""
    branch_name: str = ""
    url: str = ""
    labels: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class LinearNamedTarget:
    """Resolved Linear project/initiative target for status updates."""

    kind: LinearTargetKind
    id: str
    name: str
    slug: str
    url: str


@dataclass(frozen=True)
class LinearPostedUpdate:
    """Created Linear project/initiative status update."""

    kind: LinearTargetKind
    id: str
    url: str
    health: LinearUpdateHealth


class LinearBridge:
    """Async client for Linear GraphQL API.

    Handles authentication via API token and provides typed methods for
    common issue operations used by the Shoal CLI.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._api_key,
            "Content-Type": "application/json",
        }

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=_ENDPOINT,
                headers=self._headers(),
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _post(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Execute a GraphQL query and return the data or raise on errors."""
        client = await self._ensure_client()
        response = await client.post(
            "",
            json={"query": query, "variables": variables},
        )
        response.raise_for_status()
        payload = response.json()
        errors = payload.get("errors")
        if errors:
            msgs = "; ".join(e.get("message", str(e)) for e in errors)
            raise RuntimeError(f"Linear GraphQL error: {msgs}")
        data: dict[str, Any] = payload.get("data") or {}
        return data

    def _parse_issue(self, node: dict[str, Any]) -> LinearIssue:
        """Convert a GraphQL issue node into a LinearIssue."""
        state = node.get("state") or {}
        assignee = node.get("assignee") or {}
        labels_nodes = node.get("labels", {}).get("nodes") or []
        return LinearIssue(
            id=node.get("id") or "",
            identifier=node.get("identifier") or "",
            title=node.get("title") or "",
            description=node.get("description") or "",
            state_name=state.get("name") or "",
            state_type=state.get("type") or "",
            priority=node.get("priority") or 0,
            assignee_name=assignee.get("name") or "",
            branch_name=node.get("branchName") or "",
            url=node.get("url") or "",
            labels=[label.get("name") or "" for label in labels_nodes],
        )

    def _parse_named_target(
        self, node: dict[str, Any], *, kind: LinearTargetKind
    ) -> LinearNamedTarget:
        """Convert a GraphQL node into a named status-update target."""
        return LinearNamedTarget(
            kind=kind,
            id=node.get("id", ""),
            name=node.get("name", ""),
            slug=node.get("slugId", ""),
            url=node.get("url", ""),
        )

    async def list_team_issues(
        self,
        team_key: str,
        *,
        ready_only: bool = False,
        mine_only: bool = False,
    ) -> list[LinearIssue]:
        """List issues for a Linear team.

        Args:
            team_key: The team's short key (e.g. "BE").
            ready_only: If True, filter to unstarted issues (not yet started).
            mine_only: If True, filter to issues assigned to the current user.
                Note: requires the API token to belong to that user.
        """
        variables: dict[str, Any] = {"teamKey": team_key, "first": 50}
        if ready_only:
            query = _QUERY_TEAM_ISSUES_BY_STATE
            variables["stateType"] = "unstarted"
        else:
            query = _QUERY_TEAM_ISSUES
        data = await self._post(query, variables)
        nodes: list[dict[str, Any]] = data.get("issues", {}).get("nodes") or []
        return [self._parse_issue(n) for n in nodes]

    async def get_issue(self, identifier: str) -> LinearIssue | None:
        """Fetch a single issue by its identifier (e.g. "BE-1234")."""
        variables = {"identifier": identifier}
        data = await self._post(_QUERY_ISSUE, variables)
        node: dict[str, Any] | None = data.get("issueFilter")
        if not node:
            return None
        return self._parse_issue(node)

    async def update_issue_state(self, issue_id: str, state_name: str) -> None:
        """Update an issue's state by name.

        Args:
            issue_id: The Linear issue ID (UUID, not the identifier).
            state_name: The target state name (e.g. "In Progress", "Done").
        """
        issue = await self.get_issue_by_id(issue_id)
        if not issue:
            raise RuntimeError(f"Issue {issue_id} not found")
        state_id = await self._resolve_state_id(issue["teamId"], state_name)
        variables = {"id": issue_id, "stateId": state_id}
        await self._post(_MUTATION_UPDATE_STATE, variables)

    async def get_issue_by_id(self, issue_id: str) -> dict[str, Any] | None:
        """Fetch raw issue data by UUID."""
        query = """
        query IssueById($id: String!) {
          issue(id: $id) {
            id
            teamId
          }
        }
        """
        data = await self._post(query, {"id": issue_id})
        issue_data: dict[str, Any] | None = data.get("issue")
        return issue_data

    async def _resolve_state_id(self, team_id: str, state_name: str) -> str:
        """Look up a state's UUID given its team and name."""
        query = """
        query TeamWorkflow($teamId: String!) {
          team(id: $teamId) {
            states {
              nodes { id name }
            }
          }
        }
        """
        data = await self._post(query, {"teamId": team_id})
        states: list[dict[str, Any]] = data.get("team", {}).get("states", {}).get("nodes") or []
        for s in states:
            if s.get("name", "").lower() == state_name.lower():
                state_id_str: str = s["id"]
                return state_id_str
        available = [s["name"] for s in states]
        raise RuntimeError(
            f"State '{state_name}' not found in team workflow. Available states: {available}"
        )

    async def add_issue_comment(self, issue_id: str, body: str) -> None:
        """Add a comment to an issue.

        Args:
            issue_id: The Linear issue ID (UUID).
            body: Comment body as Markdown text.
        """
        variables = {"issueId": issue_id, "body": body}
        await self._post(_MUTATION_ADD_COMMENT, variables)

    async def resolve_target(
        self,
        *,
        kind: LinearTargetKind,
        id: str = "",
        slug: str = "",
        name: str = "",
    ) -> LinearNamedTarget:
        """Resolve a project/initiative target by id, slug, or exact name."""
        selectors = {
            "id": id.strip(),
            "slug": slug.strip(),
            "name": name.strip(),
        }
        provided = [selector_name for selector_name, value in selectors.items() if value]
        if len(provided) != 1:
            raise ValueError("Exactly one of id, slug, or name must be provided")

        selector_name = provided[0]
        selector_value = selectors[selector_name]
        if kind == "project":
            return await self._resolve_project_target(
                selector_name=selector_name,
                selector_value=selector_value,
            )
        return await self._resolve_initiative_target(
            selector_name=selector_name,
            selector_value=selector_value,
        )

    async def create_status_update(
        self,
        *,
        kind: LinearTargetKind,
        target_id: str,
        body: str,
        health: LinearUpdateHealth,
        is_diff_hidden: bool = False,
    ) -> LinearPostedUpdate:
        """Create a Linear project or initiative update."""
        input_data: dict[str, Any] = {
            "body": body,
            "health": health,
            "isDiffHidden": is_diff_hidden,
        }
        if kind == "project":
            input_data["projectId"] = target_id
            data = await self._post(_MUTATION_CREATE_PROJECT_UPDATE, {"input": input_data})
            payload = data.get("projectUpdateCreate") or {}
            node = payload.get("projectUpdate") or {}
        else:
            input_data["initiativeId"] = target_id
            data = await self._post(_MUTATION_CREATE_INITIATIVE_UPDATE, {"input": input_data})
            payload = data.get("initiativeUpdateCreate") or {}
            node = payload.get("initiativeUpdate") or {}

        if not payload.get("success"):
            raise RuntimeError(f"Failed to create Linear {kind} update")

        return LinearPostedUpdate(
            kind=kind,
            id=node.get("id", ""),
            url=node.get("url", ""),
            health=health,
        )

    async def _resolve_project_target(
        self, *, selector_name: str, selector_value: str
    ) -> LinearNamedTarget:
        """Resolve a project target using one selector."""
        if selector_name == "id":
            data = await self._post(_QUERY_PROJECT_BY_ID, {"id": selector_value})
            node = data.get("project")
            if not node:
                raise RuntimeError(f"Linear project not found for id '{selector_value}'")
            return self._parse_named_target(node, kind="project")

        if selector_name == "slug":
            data = await self._post(_QUERY_PROJECTS_BY_SLUG, {"slug": selector_value})
        else:
            data = await self._post(_QUERY_PROJECTS_BY_NAME, {"name": selector_value})

        nodes: list[dict[str, Any]] = data.get("projects", {}).get("nodes") or []
        if not nodes:
            raise RuntimeError(f"Linear project not found for {selector_name} '{selector_value}'")
        if len(nodes) > 1:
            raise RuntimeError(
                "Multiple Linear projects matched "
                f"{selector_name} '{selector_value}'. Use id instead."
            )
        return self._parse_named_target(nodes[0], kind="project")

    async def _resolve_initiative_target(
        self, *, selector_name: str, selector_value: str
    ) -> LinearNamedTarget:
        """Resolve an initiative target using one selector."""
        if selector_name == "id":
            data = await self._post(_QUERY_INITIATIVE_BY_ID, {"id": selector_value})
            node = data.get("initiative")
            if not node:
                raise RuntimeError(f"Linear initiative not found for id '{selector_value}'")
            return self._parse_named_target(node, kind="initiative")

        if selector_name == "slug":
            data = await self._post(_QUERY_INITIATIVES_BY_SLUG, {"slug": selector_value})
        else:
            data = await self._post(_QUERY_INITIATIVES_BY_NAME, {"name": selector_value})

        nodes: list[dict[str, Any]] = data.get("initiatives", {}).get("nodes") or []
        if not nodes:
            raise RuntimeError(
                f"Linear initiative not found for {selector_name} '{selector_value}'"
            )
        if len(nodes) > 1:
            raise RuntimeError(
                "Multiple Linear initiatives matched "
                f"{selector_name} '{selector_value}'. Use id instead."
            )
        return self._parse_named_target(nodes[0], kind="initiative")


def get_linear_bridge() -> LinearBridge:
    """Create a LinearBridge from environment config.

    Reads the API key from the ``SHOAL_LINEAR_API_KEY`` environment variable.

    Raises:
        RuntimeError: If the environment variable is not set.
    """
    api_key = os.environ.get("SHOAL_LINEAR_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "SHOAL_LINEAR_API_KEY is not set. "
            "Set it to your Linear personal API token to use ticket commands."
        )
    return LinearBridge(api_key)


async def hook_linear_on_complete(**kwargs: Any) -> None:
    """Lifecycle hook: update Linear issue status when a tagged session completes.

    Registered on ``session_completed``. Silently skips if no API key is configured
    or the session has no ``linear:`` tag.
    """
    import logging

    _logger = logging.getLogger("shoal.linear_bridge")
    session = kwargs.get("session")
    if session is None:
        return

    tags: list[str] = getattr(session, "tags", [])
    linear_ids = [t.removeprefix("linear:") for t in tags if t.startswith("linear:")]
    if not linear_ids:
        return

    api_key = os.environ.get("SHOAL_LINEAR_API_KEY", "").strip()
    if not api_key:
        return  # No key configured — silently skip

    bridge = LinearBridge(api_key)
    try:
        for identifier in linear_ids:
            issue = await bridge.get_issue(identifier)
            if issue:
                try:
                    await bridge.update_issue_state(issue.id, "Done")
                    _logger.info("Linear %s -> Done (session completed)", identifier)
                except RuntimeError as exc:
                    _logger.warning("Failed to update Linear %s: %s", identifier, exc)
    finally:
        await bridge.close()
