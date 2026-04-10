"""GitHub API bridge.

Provides async client for GitHub REST API operations used by the CLI.
"""

from __future__ import annotations

import os
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict

__all__ = [
    "GitHubBridge",
    "GitHubIssue",
    "GitHubPR",
    "get_github_bridge",
]

_API_BASE = "https://api.github.com"


class GitHubIssue(BaseModel):
    """GitHub issue data."""

    model_config = ConfigDict(extra="forbid")

    id: int = 0
    number: int = 0
    title: str = ""
    body: str = ""
    state: str = ""
    url: str = ""
    html_url: str = ""
    user: str = ""


class GitHubPR(GitHubIssue):
    """GitHub pull request data."""

    head_sha: str = ""
    base: str = ""
    head: str = ""
    mergeable_state: str = ""


class GitHubBridge:
    """Async client for GitHub REST API.

    Handles authentication via GITHUB_TOKEN env var and provides typed methods for
    common PR and issue operations used by the Shoal CLI.
    """

    def __init__(self, token: str) -> None:
        self._token = token
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"token {self._token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "shoal-cli",
        }

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=_API_BASE,
                headers=self._headers(),
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: Literal["GET", "POST", "PATCH"],
        path: str,
        json_data: dict[str, Any] | None = None,
        accept_header: str | None = None,
    ) -> Any:
        """Execute a GitHub API request."""
        client = await self._ensure_client()
        headers = {}
        if accept_header:
            headers["Accept"] = accept_header
        response = await client.request(
            method,
            path,
            json=json_data,
            headers=headers if headers else None,
        )
        response.raise_for_status()
        if response.status_code == 204:
            return None
        # Handle text responses (like diff format)
        if accept_header and "diff" in accept_header:
            return response.text
        return response.json()

    async def list_prs(self, repo: str, state: str = "open") -> list[GitHubPR]:
        """List pull requests for a repository."""
        data = await self._request("GET", f"/repos/{repo}/pulls", json_data=None)
        # GitHub returns a list directly
        return [GitHubPR(**item) for item in data] if isinstance(data, list) else []

    async def get_pr(self, repo: str, number: int) -> GitHubPR:
        """Get a specific pull request."""
        data = await self._request("GET", f"/repos/{repo}/pulls/{number}", json_data=None)
        return GitHubPR(**data)

    async def create_pr(self, repo: str, title: str, body: str, head: str, base: str) -> GitHubPR:
        """Create a new pull request."""
        payload = {
            "title": title,
            "body": body,
            "head": head,
            "base": base,
        }
        data = await self._request("POST", f"/repos/{repo}/pulls", json_data=payload)
        return GitHubPR(**data)

    async def list_issues(self, repo: str, state: str = "open") -> list[GitHubIssue]:
        """List issues for a repository."""
        # GitHub's /issues endpoint also includes PRs. To get only issues, we might need to filter
        # or use search. For a bridge, we'll use the standard list.
        params = {"state": state}
        client = await self._ensure_client()
        response = await client.get(f"/repos/{repo}/issues", params=params)
        response.raise_for_status()
        data = response.json()
        return [GitHubIssue(**item) for item in data] if isinstance(data, list) else []

    async def get_issue(self, repo: str, number: int) -> GitHubIssue:
        """Get a specific issue."""
        data = await self._request("GET", f"/repos/{repo}/issues/{number}", json_data=None)
        return GitHubIssue(**data)

    async def add_comment(self, repo: str, issue_number: int, body: str) -> None:
        """Add a comment to an issue or PR."""
        payload = {"body": body}
        await self._request(
            "POST", f"/repos/{repo}/issues/{issue_number}/comments", json_data=payload
        )

    async def close_pr(self, repo: str, number: int) -> None:
        """Close a pull request."""
        payload = {"state": "closed"}
        await self._request("PATCH", f"/repos/{repo}/pulls/{number}", json_data=payload)

    async def get_pr_diff(self, repo: str, number: int) -> str:
        """Get the diff for a pull request."""
        result = await self._request(
            "GET",
            f"/repos/{repo}/pulls/{number}",
            accept_header="application/vnd.github.v3.diff",
        )
        return str(result) if result else ""

    async def get_pr_comments(self, repo: str, number: int) -> list[dict[str, Any]]:
        """Get review comments for a pull request."""
        data = await self._request("GET", f"/repos/{repo}/pulls/{number}/comments")
        return data if isinstance(data, list) else []

    async def get_pr_reviews(self, repo: str, number: int) -> list[dict[str, Any]]:
        """Get reviews for a pull request."""
        data = await self._request("GET", f"/repos/{repo}/pulls/{number}/reviews")
        return data if isinstance(data, list) else []


def get_github_bridge() -> GitHubBridge:
    """Get a singleton-like instance of the GitHubBridge using environment auth."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN environment variable not set")
    return GitHubBridge(token)
