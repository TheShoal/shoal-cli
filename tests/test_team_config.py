"""Tests for TeamConfig model and workspace config loading."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from shoal.models.config.workspace import (
    TeamConfig,
    TeamReportTargetConfig,
    WorkspaceConfig,
)


class TestTeamReportTargetConfig:
    def test_slug_selector(self) -> None:
        cfg = TeamReportTargetConfig(type="project", slug="backend-platform")
        assert cfg.type == "project"
        assert cfg.slug == "backend-platform"

    def test_requires_exactly_one_selector(self) -> None:
        with pytest.raises(ValidationError, match="exactly one of id, slug, or name"):
            TeamReportTargetConfig(type="project")

        with pytest.raises(ValidationError, match="exactly one of id, slug, or name"):
            TeamReportTargetConfig(type="project", id="proj-1", slug="backend")


class TestTeamConfig:
    def test_minimal(self) -> None:
        cfg = TeamConfig(linear_slug="BE")
        assert cfg.linear_slug == "BE"
        assert cfg.name == ""
        assert cfg.default_template == ""
        assert cfg.worktree_dir == ""
        assert cfg.report is None

    def test_full(self) -> None:
        cfg = TeamConfig(
            name="Backend Engineering",
            linear_slug="BE",
            default_template="usm-be-agent",
            worktree_dir="backend",
            report=TeamReportTargetConfig(type="project", slug="backend-platform"),
        )
        assert cfg.name == "Backend Engineering"
        assert cfg.linear_slug == "BE"
        assert cfg.default_template == "usm-be-agent"
        assert cfg.worktree_dir == "backend"
        assert cfg.report is not None
        assert cfg.report.slug == "backend-platform"

    def test_missing_linear_slug_raises(self) -> None:
        with pytest.raises(ValidationError, match="linear_slug"):
            TeamConfig()  # type: ignore[call-arg]

    def test_extra_field_raises(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            TeamConfig(linear_slug="BE", slack_channel="#be")  # type: ignore[call-arg]


class TestWorkspaceConfigTeams:
    def test_default_empty_teams(self) -> None:
        ws = WorkspaceConfig()
        assert ws.teams == {}

    def test_teams_field(self) -> None:
        ws = WorkspaceConfig(
            name="test",
            teams={"be": TeamConfig(linear_slug="BE", name="Backend")},
        )
        assert "be" in ws.teams
        assert ws.teams["be"].linear_slug == "BE"

    def test_teams_and_repos_coexist(self) -> None:
        ws = WorkspaceConfig(
            name="test",
            repos={"email": "backend/email"},
            teams={"be": TeamConfig(linear_slug="BE")},
        )
        assert ws.repos == {"email": "backend/email"}
        assert ws.teams["be"].linear_slug == "BE"


class TestLoadWorkspaceConfigTeams:
    def test_loads_teams_from_toml(self, tmp_path: Path) -> None:
        """Teams are parsed from [teams.*] top-level sections in workspace.toml."""
        from shoal.core.config import load_workspace_config

        shoal_dir = tmp_path / ".shoal"
        shoal_dir.mkdir()
        workspace_toml = shoal_dir / "workspace.toml"
        workspace_toml.write_text(
            textwrap.dedent("""\
                [workspace]
                name = "test"

                [workspace.repos]
                email = "backend/email"

                [teams.be]
                name = "Backend"
                linear_slug = "BE"
                default_template = "usm-be-agent"
                worktree_dir = "backend"

                [teams.be.report]
                type = "project"
                slug = "backend-platform"

                [teams.fe]
                linear_slug = "FE"
            """)
        )

        ws = load_workspace_config(str(tmp_path))
        assert ws is not None
        assert len(ws.teams) == 2
        assert ws.teams["be"].name == "Backend"
        assert ws.teams["be"].linear_slug == "BE"
        assert ws.teams["be"].default_template == "usm-be-agent"
        assert ws.teams["be"].report is not None
        assert ws.teams["be"].report.slug == "backend-platform"
        assert ws.teams["fe"].linear_slug == "FE"
        assert ws.teams["fe"].name == ""

    def test_no_teams_section(self, tmp_path: Path) -> None:
        """Workspace without [teams] section loads fine with empty dict."""
        from shoal.core.config import load_workspace_config

        shoal_dir = tmp_path / ".shoal"
        shoal_dir.mkdir()
        workspace_toml = shoal_dir / "workspace.toml"
        workspace_toml.write_text(
            textwrap.dedent("""\
                [workspace]
                name = "test"
            """)
        )

        ws = load_workspace_config(str(tmp_path))
        assert ws is not None
        assert ws.teams == {}

    def test_backward_compat(self, tmp_path: Path) -> None:
        """Existing workspace.toml files without teams field still work."""
        from shoal.core.config import load_workspace_config

        shoal_dir = tmp_path / ".shoal"
        shoal_dir.mkdir()
        workspace_toml = shoal_dir / "workspace.toml"
        workspace_toml.write_text(
            textwrap.dedent("""\
                [workspace]
                name = "smorgasbord"

                [workspace.repos]
                emailservice = "backend/emailservice"
                ecommerce = "backend/ecommerce-service"
            """)
        )

        ws = load_workspace_config(str(tmp_path))
        assert ws is not None
        assert ws.teams == {}
        assert "emailservice" in ws.repos
