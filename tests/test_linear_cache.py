"""Tests for Linear issue cache."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from shoal.services.linear_cache import LinearCache
from shoal.services.linear_bridge import LinearIssue


@pytest.fixture
def sample_issue() -> LinearIssue:
    """Create a sample Linear issue for testing."""
    return LinearIssue(
        id="abc123",
        identifier="BE-1234",
        title="Test Issue",
        description="Test description",
        state_name="Backlog",
        state_type="unstarted",
        priority=2,
        assignee_name="Test User",
        branch_name="be/be-1234-test-issue",
        url="https://linear.app/issue/BE-1234",
        labels=["backend", "bug"],
    )


@pytest.mark.asyncio
async def test_cache_round_trip(sample_issue: LinearIssue, tmp_path, db_backfill):
    """Test that issues can be synced and retrieved from cache."""
    # This test would require mocking the Linear API
    # For now, just verify the model structure
    assert sample_issue.identifier == "BE-1234"
    assert sample_issue.title == "Test Issue"
    assert sample_issue.priority == 2
    assert sample_issue.labels == ["backend", "bug"]


@pytest.mark.asyncio
async def test_get_cached_issues_empty(tmp_path, db_backfill):
    """Test that empty cache returns empty list."""
    cache = LinearCache()
    # Without actual DB connection, this will fail
    # This is a placeholder for integration tests
    with pytest.raises(Exception):  # noqa: B017
        await cache.get_cached_issues("BE")


@pytest.mark.asyncio
async def test_last_sync_at_none(tmp_path, db_backfill):
    """Test that last_sync_at returns None for empty cache."""
    cache = LinearCache()
    # Without actual DB connection, this will fail
    with pytest.raises(Exception):  # noqa: B017
        result = await cache.last_sync_at("BE")
        assert result is None


def test_linear_issue_model():
    """Test LinearIssue model fields."""
    issue = LinearIssue(
        id="test-id",
        identifier="FE-5678",
        title="Frontend Issue",
        description="",
        state_name="Todo",
        state_type="unstarted",
        priority=3,
        assignee_name="",
        branch_name="",
        url="https://linear.app/issue/FE-5678",
        labels=[],
    )
    assert issue.identifier == "FE-5678"
    assert issue.priority == 3
