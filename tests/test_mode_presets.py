"""Tests for single-session mode defaults on `shoal new`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from shoal.cli import app
from shoal.cli.mode_presets import resolve_mode_defaults

runner = CliRunner()


class TestResolveModeDefaults:
    def test_feature_lane_uses_template_when_available(self) -> None:
        with patch("shoal.cli.mode_presets.available_templates", return_value=["codex-dev"]):
            resolved = resolve_mode_defaults(
                "feature-lane",
                name="payment-retry",
                template=None,
                tool=None,
                worktree=None,
                branch=False,
                project_name="shoal-cli",
            )

        assert resolved.template == "codex-dev"
        assert resolved.tool is None
        assert resolved.worktree == "feat/payment-retry"
        assert resolved.branch is True

    def test_author_review_falls_back_to_claude_tool(self) -> None:
        with patch("shoal.cli.mode_presets.available_templates", return_value=[]):
            resolved = resolve_mode_defaults(
                "author-review",
                name="auth-review",
                template=None,
                tool=None,
                worktree=None,
                branch=False,
                project_name="shoal-cli",
            )

        assert resolved.template is None
        assert resolved.tool == "claude"
        assert resolved.worktree == "review/auth-review"
        assert resolved.branch is True

    def test_explicit_values_win(self) -> None:
        with patch("shoal.cli.mode_presets.available_templates", return_value=["codex-dev"]):
            resolved = resolve_mode_defaults(
                "feature-lane",
                name="custom",
                template="pi-dev",
                tool="pi",
                worktree="docs/custom",
                branch=False,
                project_name="shoal-cli",
            )

        assert resolved.template == "pi-dev"
        assert resolved.tool == "pi"
        assert resolved.worktree == "docs/custom"
        assert resolved.branch is True


class TestNewModeDryRun:
    def test_new_dry_run_shows_resolved_mode(self, mock_dirs: object, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()

        with (
            patch("shoal.cli.session_create.git.is_git_repo", return_value=True),
            patch("shoal.cli.session_create.git.git_root", return_value=str(repo)),
        ):
            result = runner.invoke(app, ["new", str(repo), "--mode", "feature-lane", "--dry-run"])

        assert result.exit_code == 0
        assert "Mode: feature-lane" in result.output
        assert "Tool: codex" in result.output
        assert "Branch: feat/repo" in result.output
        assert "Worktree dir name: feat-repo" in result.output


class TestModeRegistry:
    def test_all_original_modes_present(self) -> None:
        from shoal.cli.mode_presets import MODE_REGISTRY

        assert "feature-lane" in MODE_REGISTRY
        assert "author-review" in MODE_REGISTRY
        assert "remote-batch" in MODE_REGISTRY

    def test_new_modes_present(self) -> None:
        from shoal.cli.mode_presets import MODE_REGISTRY

        assert "planner" in MODE_REGISTRY
        assert "implementer" in MODE_REGISTRY
        assert "reviewer" in MODE_REGISTRY

    def test_reviewer_has_review_ready_tag(self) -> None:
        from shoal.cli.mode_presets import MODE_REGISTRY

        assert "review-ready" in MODE_REGISTRY["reviewer"].auto_tags

    def test_planner_has_planner_tag(self) -> None:
        from shoal.cli.mode_presets import MODE_REGISTRY

        assert "planner" in MODE_REGISTRY["planner"].auto_tags

    def test_resolve_returns_auto_tags(self) -> None:
        with patch("shoal.cli.mode_presets.available_templates", return_value=[]):
            resolved = resolve_mode_defaults(
                "reviewer",
                name="code-review",
                template=None,
                tool=None,
                worktree=None,
                branch=False,
                project_name="myproj",
            )
        assert "reviewer" in resolved.auto_tags
        assert "review-ready" in resolved.auto_tags
        assert resolved.worktree == "review/code-review"

    def test_unknown_mode_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="Unknown mode"):
            resolve_mode_defaults(
                "nonexistent",
                name=None,
                template=None,
                tool=None,
                worktree=None,
                branch=False,
                project_name="p",
            )


class TestModeListCli:
    def test_mode_ls(self) -> None:
        result = runner.invoke(app, ["mode", "ls"])
        assert result.exit_code == 0
        assert "feature-lane" in result.output
        assert "planner" in result.output
        assert "reviewer" in result.output
