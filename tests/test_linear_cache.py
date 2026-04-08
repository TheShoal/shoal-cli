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


def test_sample_issue_fixture(sample_issue):
    """Test sample_issue fixture produces valid model."""
    assert sample_issue.id == "abc123"
    assert sample_issue.identifier == "BE-1234"
    assert sample_issue.title == "Test Issue"
    assert sample_issue.description == "Test description"
    assert sample_issue.state_name == "Backlog"
    assert sample_issue.state_type == "unstarted"
    assert sample_issue.priority == 2
    assert sample_issue.assignee_name == "Test User"
    assert sample_issue.branch_name == "be/be-1234-test-issue"
    assert sample_issue.url == "https://linear.app/issue/BE-1234"
    assert sample_issue.labels == ["backend", "bug"]


def test_linear_issue_optional_fields():
    """Test LinearIssue with empty optional fields."""
    issue = LinearIssue(
        id="opt-id",
        identifier="BE-0001",
        title="Minimal Issue",
        description="",
        state_name="",
        state_type="",
        priority=0,
        assignee_name="",
        branch_name="",
        url="",
        labels=[],
    )
    assert issue.description == ""
    assert issue.assignee_name == ""
    assert issue.branch_name == ""
    assert issue.labels == []
