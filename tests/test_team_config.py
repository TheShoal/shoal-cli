"""Tests for TeamConfig with repos field."""

from __future__ import annotations

import pytest

from shoal.models.config.workspace import TeamConfig, TeamReportTargetConfig


def test_team_config_repos_default():
    """Test that repos defaults to empty list."""
    team = TeamConfig(linear_slug="BE")
    assert team.repos == []


def test_team_config_with_repos():
    """Test TeamConfig with repos configured."""
    team = TeamConfig(
        name="Backend",
        linear_slug="BE",
        repos=["backend/user-service", "backend/gateway", "backend/emailservice"],
    )
    assert team.repos == ["backend/user-service", "backend/gateway", "backend/emailservice"]
    assert team.linear_slug == "BE"


def test_team_config_repos_validation():
    """Test that repos accepts valid paths."""
    team = TeamConfig(
        linear_slug="FE",
        repos=["frontend/web-app", "frontend/ui-lib", "frontend/native-app"],
    )
    assert len(team.repos) == 3


def test_team_config_extra_forbidden():
    """Test that extra fields are rejected."""
    with pytest.raises(Exception):  # Pydantic ValidationError
        TeamConfig(linear_slug="BE", unknown_field="should_fail")  # type: ignore[call-arg]


def test_team_config_with_report():
    """Test TeamConfig with report target."""
    team = TeamConfig(
        name="Backend",
        linear_slug="BE",
        repos=["backend/core"],
        report=TeamReportTargetConfig(type="project", slug="be-sprint-reports"),
    )
    assert team.report is not None
    assert team.report.type == "project"
    assert team.report.slug == "be-sprint-reports"
