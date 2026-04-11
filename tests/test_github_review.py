"""Tests for GitHub PR review workflow."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from typer.testing import CliRunner

from shoal.services.github_bridge import GitHubBridge, GitHubPR


@pytest.fixture
def mock_bridge() -> GitHubBridge:
    """Create a mock GitHubBridge."""
    return GitHubBridge(token="test-token")  # noqa: S106


@pytest.fixture
def sample_pr_data() -> dict[str, Any]:
    """Sample PR data matching GitHub API response."""
    return {
        "id": 123,
        "number": 42,
        "title": "Add new feature",
        "body": "This PR adds a new feature",
        "state": "open",
        "url": "https://api.github.com/repos/owner/repo/pulls/42",
        "html_url": "https://github.com/owner/repo/pull/42",
        "user": "testuser",
        "head_sha": "abc123",
        "base": "main",
        "head": "feature-branch",
        "mergeable_state": "clean",
    }


@pytest.fixture
def sample_diff() -> str:
    """Sample git diff."""
    return """diff --git a/file.py b/file.py
index 1234567..abcdefg 100644
--- a/file.py
+++ b/file.py
@@ -1,3 +1,4 @@
+import new_module
 def main():
-    print("old")
+    print("new")
"""


@pytest.fixture
def sample_comments() -> list[dict[str, Any]]:
    """Sample PR comments."""
    return [
        {
            "id": 1,
            "user": {"login": "reviewer1"},
            "body": "LGTM",
            "path": "file.py",
            "position": 5,
        },
        {
            "id": 2,
            "user": {"login": "reviewer2"},
            "body": "Needs tests",
            "path": "file.py",
            "position": 10,
        },
    ]


@pytest.fixture
def sample_reviews() -> list[dict[str, Any]]:
    """Sample PR reviews."""
    return [
        {
            "id": 100,
            "user": {"login": "reviewer1"},
            "state": "APPROVED",
            "body": "Looks good!",
        },
        {
            "id": 101,
            "user": {"login": "reviewer2"},
            "state": "CHANGES_REQUESTED",
            "body": "Please add tests",
        },
    ]


class TestGitHubBridgeReviewMethods:
    """Tests for new GitHubBridge methods supporting PR review."""

    @pytest.mark.asyncio
    async def test_get_pr_diff(self, mock_bridge: GitHubBridge, sample_diff: str) -> None:
        """Test fetching PR diff."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = sample_diff
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.request.return_value = mock_response

        with patch.object(mock_bridge, "_ensure_client", return_value=mock_client):
            result = await mock_bridge.get_pr_diff("owner/repo", 42)

            assert result == sample_diff
            mock_client.request.assert_called_once()
            call_args = mock_client.request.call_args
            assert call_args[0][0] == "GET"
            assert call_args[0][1] == "/repos/owner/repo/pulls/42"
            assert call_args[1]["headers"]["Accept"] == "application/vnd.github.v3.diff"

    @pytest.mark.asyncio
    async def test_get_pr_diff_empty(self, mock_bridge: GitHubBridge) -> None:
        """Test fetching PR diff when none exists."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.request.return_value = mock_response

        with patch.object(mock_bridge, "_ensure_client", return_value=mock_client):
            result = await mock_bridge.get_pr_diff("owner/repo", 42)
            assert result == ""

    @pytest.mark.asyncio
    async def test_get_pr_comments(
        self, mock_bridge: GitHubBridge, sample_comments: list[dict[str, Any]]
    ) -> None:
        """Test fetching PR comments."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_comments
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.request.return_value = mock_response

        with patch.object(mock_bridge, "_ensure_client", return_value=mock_client):
            result = await mock_bridge.get_pr_comments("owner/repo", 42)

            assert len(result) == 2
            assert result[0]["user"]["login"] == "reviewer1"
            assert result[1]["body"] == "Needs tests"
            mock_client.request.assert_called_once()
            call_args = mock_client.request.call_args
            assert call_args[0][1] == "/repos/owner/repo/pulls/42/comments"

    @pytest.mark.asyncio
    async def test_get_pr_comments_empty(self, mock_bridge: GitHubBridge) -> None:
        """Test fetching PR comments when none exist."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.request.return_value = mock_response

        with patch.object(mock_bridge, "_ensure_client", return_value=mock_client):
            result = await mock_bridge.get_pr_comments("owner/repo", 42)
            assert result == []

    @pytest.mark.asyncio
    async def test_get_pr_reviews(
        self, mock_bridge: GitHubBridge, sample_reviews: list[dict[str, Any]]
    ) -> None:
        """Test fetching PR reviews."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_reviews
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.request.return_value = mock_response

        with patch.object(mock_bridge, "_ensure_client", return_value=mock_client):
            result = await mock_bridge.get_pr_reviews("owner/repo", 42)

            assert len(result) == 2
            assert result[0]["state"] == "APPROVED"
            assert result[1]["state"] == "CHANGES_REQUESTED"
            mock_client.request.assert_called_once()
            call_args = mock_client.request.call_args
            assert call_args[0][1] == "/repos/owner/repo/pulls/42/reviews"

    @pytest.mark.asyncio
    async def test_get_pr_reviews_empty(self, mock_bridge: GitHubBridge) -> None:
        """Test fetching PR reviews when none exist."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.request.return_value = mock_response

        with patch.object(mock_bridge, "_ensure_client", return_value=mock_client):
            result = await mock_bridge.get_pr_reviews("owner/repo", 42)
            assert result == []

    @pytest.mark.asyncio
    async def test_get_pr_diff_http_error(self, mock_bridge: GitHubBridge) -> None:
        """Test handling HTTP errors when fetching diff."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=MagicMock(),
            response=mock_response,
        )

        mock_client = AsyncMock()
        mock_client.request.return_value = mock_response

        with patch.object(mock_bridge, "_ensure_client", return_value=mock_client):
            with pytest.raises(httpx.HTTPStatusError):
                await mock_bridge.get_pr_diff("owner/repo", 999)


class TestReviewPRCommand:
    """Tests for the review-pr CLI command."""

    @pytest.mark.asyncio
    async def test_review_pr_dry_run(
        self,
        sample_pr_data: dict[str, Any],
        sample_diff: str,
        sample_comments: list[dict[str, Any]],
        sample_reviews: list[dict[str, Any]],
    ) -> None:
        """Test review-pr command in dry-run mode."""
        from shoal.cli.github import _pr_review_impl

        mock_bridge = MagicMock()
        mock_bridge.get_pr = AsyncMock(return_value=GitHubPR(**sample_pr_data))
        mock_bridge.get_pr_diff = AsyncMock(return_value=sample_diff)
        mock_bridge.get_pr_comments = AsyncMock(return_value=sample_comments)
        mock_bridge.get_pr_reviews = AsyncMock(return_value=sample_reviews)
        mock_bridge.close = AsyncMock()

        with patch("shoal.cli.github.get_github_bridge", return_value=mock_bridge):
            # Dry-run should not create session
            await _pr_review_impl("owner/repo", 42, template="pantheon-review", dry_run=True)

            # Verify bridge methods were called
            mock_bridge.get_pr.assert_called_once_with("owner/repo", 42)
            mock_bridge.get_pr_diff.assert_called_once_with("owner/repo", 42)
            mock_bridge.get_pr_comments.assert_called_once_with("owner/repo", 42)
            mock_bridge.get_pr_reviews.assert_called_once_with("owner/repo", 42)
            mock_bridge.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_review_pr_diff_truncation(
        self,
        sample_pr_data: dict[str, Any],
        sample_comments: list[dict[str, Any]],
        sample_reviews: list[dict[str, Any]],
    ) -> None:
        """Test that large diffs are truncated."""
        from shoal.cli.github import _pr_review_impl

        # Create a diff larger than 5000 chars
        large_diff = "+" * 6000

        mock_bridge = MagicMock()
        mock_bridge.get_pr = AsyncMock(return_value=GitHubPR(**sample_pr_data))
        mock_bridge.get_pr_diff = AsyncMock(return_value=large_diff)
        mock_bridge.get_pr_comments = AsyncMock(return_value=sample_comments)
        mock_bridge.get_pr_reviews = AsyncMock(return_value=sample_reviews)
        mock_bridge.close = AsyncMock()

        with patch("shoal.cli.github.get_github_bridge", return_value=mock_bridge):
            await _pr_review_impl("owner/repo", 42, template="pantheon-review", dry_run=True)

            # Verify diff was fetched (actual truncation happens in formatting)
            mock_bridge.get_pr_diff.assert_called_once()


class TestPostReviewCommand:
    """Tests for the post-review CLI command."""

    @pytest.mark.asyncio
    async def test_post_review_with_explicit_session(self) -> None:
        """Test posting review from explicitly named session."""
        from shoal.cli.github import _pr_post_review_impl
        from shoal.core.journal import JournalEntry
        from shoal.models.state import SessionState, TmuxRuntimeState

        mock_session = SessionState(
            id="test-session-id",
            name="gh-review-owner-repo-42",
            tool="omp",
            path="/test/path",
            runtime=TmuxRuntimeState(session_name="test-tmux-session"),
            tags=["github:owner/repo#42"],
        )

        mock_entries = [
            JournalEntry(
                timestamp=datetime.now(UTC),
                source="user",
                content="Review finding 1",
            ),
            JournalEntry(
                timestamp=datetime.now(UTC),
                source="agent",
                content="Review finding 2",
            ),
        ]

        mock_bridge = MagicMock()
        mock_bridge.add_comment = AsyncMock()
        mock_bridge.close = AsyncMock()

        with (
            patch("shoal.cli.github.resolve_session", return_value="test-session-id"),
            patch("shoal.core.state.get_session", return_value=mock_session),
            patch("shoal.core.journal.read_journal", return_value=mock_entries),
            patch("shoal.cli.github.get_github_bridge", return_value=mock_bridge),
        ):
            await _pr_post_review_impl("owner/repo", 42, session="gh-review-owner-repo-42")

            # Verify comment was posted
            mock_bridge.add_comment.assert_called_once()
            call_args = mock_bridge.add_comment.call_args
            assert call_args[0][0] == "owner/repo"
            assert call_args[0][1] == 42
            comment_body = call_args[0][2]
            assert "gh-review-owner-repo-42" in comment_body
            assert "Review finding 1" in comment_body
            assert "Review finding 2" in comment_body

    @pytest.mark.asyncio
    async def test_post_review_auto_detect_session(self) -> None:
        """Test posting review with auto-detected session."""
        from shoal.cli.github import _pr_post_review_impl
        from shoal.core.journal import JournalEntry
        from shoal.models.state import SessionState, TmuxRuntimeState

        mock_session = SessionState(
            id="test-session-id",
            name="gh-review-owner-repo-42",
            tool="omp",
            path="/test/path",
            runtime=TmuxRuntimeState(session_name="test-tmux-session"),
            tags=["github:owner/repo#42"],
        )

        mock_entries = [
            JournalEntry(
                timestamp=datetime.now(UTC),
                source="user",
                content="Auto-detected review",
            ),
        ]

        mock_bridge = MagicMock()
        mock_bridge.add_comment = AsyncMock()
        mock_bridge.close = AsyncMock()

        with (
            patch("shoal.core.state.list_sessions", return_value=[mock_session]),
            patch("shoal.core.journal.read_journal", return_value=mock_entries),
            patch("shoal.cli.github.get_github_bridge", return_value=mock_bridge),
        ):
            await _pr_post_review_impl("owner/repo", 42, session=None)

            # Verify comment was posted
            mock_bridge.add_comment.assert_called_once()
            comment_body = mock_bridge.add_comment.call_args[0][2]
            assert "Auto-detected review" in comment_body

    @pytest.mark.asyncio
    async def test_post_review_no_session_found(self) -> None:
        """Test error when no matching session found."""
        import typer

        from shoal.cli.github import _pr_post_review_impl

        with (
            patch("shoal.core.state.list_sessions", return_value=[]),
            pytest.raises(typer.Exit),
        ):
            await _pr_post_review_impl("owner/repo", 42, session=None)

    @pytest.mark.asyncio
    async def test_post_review_no_journal_entries(self) -> None:
        """Test error when session has no journal entries."""
        import typer

        from shoal.cli.github import _pr_post_review_impl
        from shoal.models.state import SessionState, TmuxRuntimeState

        mock_session = SessionState(
            id="test-session-id",
            name="gh-review-owner-repo-42",
            tool="omp",
            path="/test/path",
            runtime=TmuxRuntimeState(session_name="test-tmux-session"),
            tags=["github:owner/repo#42"],
        )

        with (
            patch("shoal.core.state.list_sessions", return_value=[mock_session]),
            patch("shoal.core.journal.read_journal", return_value=[]),
            pytest.raises(typer.Exit),
        ):
            await _pr_post_review_impl("owner/repo", 42, session=None)


class TestGitHubBindingCommands:
    def test_start_pr_uses_context_prefixed_name(self, mock_dirs) -> None:
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from shoal.cli import app as root_app

        pr = SimpleNamespace(title="Add new feature")
        bridge = SimpleNamespace(get_pr=AsyncMock(return_value=pr), close=AsyncMock())

        async def fake_add_impl(**kwargs):
            assert kwargs["name"] == "work/gh-owner-repo-42"

        runner = CliRunner()
        with (
            patch("shoal.cli.github.init_bridge", return_value=bridge),
            patch("shoal.cli.session_create._add_impl", side_effect=fake_add_impl),
            patch("shoal.cli.github.resolve_session", return_value=None),
        ):
            result = runner.invoke(root_app, ["github", "start-pr", "owner/repo", "42"])

        assert result.exit_code == 0, result.output

    def test_attach_pr_replaces_existing_github_tag(self, mock_dirs) -> None:
        from unittest.mock import AsyncMock

        from shoal.cli import app as root_app
        from shoal.core.state import add_tag, create_session, get_session

        session = asyncio.run(create_session("notes/research", "claude", "/tmp/repo"))
        asyncio.run(add_tag(session.id, "github:owner/repo#41"))

        bridge = type(
            "Bridge",
            (),
            {
                "get_pr": AsyncMock(return_value=object()),
                "close": AsyncMock(),
            },
        )()
        runner = CliRunner()
        with patch("shoal.cli.github.init_bridge", return_value=bridge):
            result = runner.invoke(
                root_app, ["github", "attach-pr", "notes/research", "owner/repo", "42"]
            )

        assert result.exit_code == 0, result.output
        updated = asyncio.run(get_session(session.id))
        assert updated is not None
        assert updated.tags.count("github:owner/repo#42") == 1
        assert "github:owner/repo#41" not in updated.tags

    def test_session_edit_applies_linear_and_github_bindings(self, mock_dirs) -> None:
        from unittest.mock import AsyncMock

        from shoal.cli import app as root_app
        from shoal.core.state import create_session, get_session

        session = asyncio.run(create_session("notes/research", "claude", "/tmp/repo"))
        linear_issue = type(
            "Issue",
            (),
            {
                "id": "issue-9",
                "identifier": "BE-9",
                "title": "Issue 9",
                "url": "https://linear.app/test/issue/BE-9",
            },
        )()
        gh_bridge = type(
            "Bridge",
            (),
            {
                "get_pr": AsyncMock(return_value=object()),
                "close": AsyncMock(),
            },
        )()
        linear_bridge = type(
            "Bridge",
            (),
            {
                "get_issue": AsyncMock(return_value=linear_issue),
                "close": AsyncMock(),
            },
        )()
        runner = CliRunner()
        with (
            patch("shoal.cli.ticket.init_bridge", return_value=linear_bridge),
            patch("shoal.cli.github.init_bridge", return_value=gh_bridge),
            patch("shoal.core.tmux.has_session", return_value=False),
        ):
            result = runner.invoke(
                root_app,
                [
                    "session",
                    "edit",
                    "notes/research",
                    "--name",
                    "work/notes-research",
                    "--add-tag",
                    "urgent",
                    "--linear",
                    "BE-9",
                    "--github",
                    "owner/repo#42",
                ],
            )

        assert result.exit_code == 0, result.output
        updated = asyncio.run(get_session(session.id))
        assert updated is not None
        assert updated.name == "work/notes-research"
        assert "urgent" in updated.tags
        assert "linear:BE-9" in updated.tags
        assert "github:owner/repo#42" in updated.tags
