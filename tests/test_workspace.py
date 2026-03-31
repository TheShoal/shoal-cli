"""Tests for workspace manifest loading and sub-repo routing."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from shoal.core.config import ConfigLoadError, load_workspace_config
from shoal.core.git import apply_workspace_routing, resolve_workspace_repo
from shoal.models.config import WorkspaceConfig

# ---------------------------------------------------------------------------
# WorkspaceConfig model
# ---------------------------------------------------------------------------


class TestWorkspaceConfig:
    def test_valid_config(self) -> None:
        cfg = WorkspaceConfig(
            name="smorgasbord",
            repos={"emailservice": "backend/emailservice", "web-app": "frontend/web-app"},
        )
        assert cfg.name == "smorgasbord"
        assert cfg.repos["emailservice"] == "backend/emailservice"

    def test_defaults(self) -> None:
        cfg = WorkspaceConfig()
        assert cfg.name == ""
        assert cfg.repos == {}

    def test_empty_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty key and path"):
            WorkspaceConfig(repos={"": "backend/svc"})

    def test_empty_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty key and path"):
            WorkspaceConfig(repos={"svc": ""})

    def test_extra_fields_rejected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            WorkspaceConfig(name="test", repos={}, bogus="nope")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# load_workspace_config
# ---------------------------------------------------------------------------


class TestLoadWorkspaceConfig:
    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        assert load_workspace_config(str(tmp_path)) is None

    def test_loads_valid_manifest(self, tmp_path: Path) -> None:
        shoal_dir = tmp_path / ".shoal"
        shoal_dir.mkdir()
        (shoal_dir / "workspace.toml").write_text(
            '[workspace]\nname = "meta"\n\n[workspace.repos]\nsvc = "backend/svc"\n'
        )
        cfg = load_workspace_config(str(tmp_path))
        assert cfg is not None
        assert cfg.name == "meta"
        assert cfg.repos == {"svc": "backend/svc"}

    def test_raises_on_bad_toml(self, tmp_path: Path) -> None:
        shoal_dir = tmp_path / ".shoal"
        shoal_dir.mkdir()
        (shoal_dir / "workspace.toml").write_text("not valid [[[toml")
        with pytest.raises(ConfigLoadError, match="TOML parse error"):
            load_workspace_config(str(tmp_path))

    def test_raises_on_invalid_schema(self, tmp_path: Path) -> None:
        shoal_dir = tmp_path / ".shoal"
        shoal_dir.mkdir()
        (shoal_dir / "workspace.toml").write_text('[workspace]\nname = "meta"\nbogus = true\n')
        with pytest.raises(ConfigLoadError, match="validation error"):
            load_workspace_config(str(tmp_path))

    def test_empty_workspace_section(self, tmp_path: Path) -> None:
        shoal_dir = tmp_path / ".shoal"
        shoal_dir.mkdir()
        (shoal_dir / "workspace.toml").write_text("[workspace]\n")
        cfg = load_workspace_config(str(tmp_path))
        assert cfg is not None
        assert cfg.repos == {}


# ---------------------------------------------------------------------------
# resolve_workspace_repo
# ---------------------------------------------------------------------------


class TestResolveWorkspaceRepo:
    @pytest.fixture()
    def repos(self) -> dict[str, str]:
        return {
            "emailservice": "backend/emailservice",
            "user-service": "backend/user-service",
            "web-app": "frontend/web-app",
        }

    def test_explicit_repo_key(self, tmp_path: Path, repos: dict[str, str]) -> None:
        result = resolve_workspace_repo(str(tmp_path), repos, repo_key="emailservice")
        assert result == str(tmp_path / "backend" / "emailservice")

    def test_explicit_repo_key_not_found(self, tmp_path: Path, repos: dict[str, str]) -> None:
        with pytest.raises(ValueError, match="not found"):
            resolve_workspace_repo(str(tmp_path), repos, repo_key="nope")

    def test_worktree_hint_exact_match(self, tmp_path: Path, repos: dict[str, str]) -> None:
        result = resolve_workspace_repo(str(tmp_path), repos, worktree_hint="emailservice")
        assert result == str(tmp_path / "backend" / "emailservice")

    def test_worktree_hint_no_match(self, tmp_path: Path, repos: dict[str, str]) -> None:
        result = resolve_workspace_repo(str(tmp_path), repos, worktree_hint="feat/my-thing")
        assert result is None

    def test_path_prefix_match(self, tmp_path: Path, repos: dict[str, str]) -> None:
        # Create the directory so resolve() works
        sub = tmp_path / "backend" / "emailservice" / "src"
        sub.mkdir(parents=True)
        result = resolve_workspace_repo(str(tmp_path), repos, resolved_path=str(sub))
        assert result == str(tmp_path / "backend" / "emailservice")

    def test_no_match_returns_none(self, tmp_path: Path, repos: dict[str, str]) -> None:
        result = resolve_workspace_repo(str(tmp_path), repos)
        assert result is None

    def test_repo_key_takes_priority_over_hint(self, tmp_path: Path, repos: dict[str, str]) -> None:
        result = resolve_workspace_repo(
            str(tmp_path),
            repos,
            repo_key="user-service",
            worktree_hint="emailservice",
        )
        assert result == str(tmp_path / "backend" / "user-service")

    def test_hint_takes_priority_over_path(self, tmp_path: Path, repos: dict[str, str]) -> None:
        sub = tmp_path / "frontend" / "web-app"
        sub.mkdir(parents=True)
        result = resolve_workspace_repo(
            str(tmp_path),
            repos,
            worktree_hint="emailservice",
            resolved_path=str(sub),
        )
        assert result == str(tmp_path / "backend" / "emailservice")

    def test_error_message_lists_available_repos(
        self, tmp_path: Path, repos: dict[str, str]
    ) -> None:
        with pytest.raises(ValueError, match="emailservice") as exc_info:
            resolve_workspace_repo(str(tmp_path), repos, repo_key="nope")
        assert "user-service" in str(exc_info.value)
        assert "web-app" in str(exc_info.value)


# ---------------------------------------------------------------------------
# WorkspaceConfig path traversal validation
# ---------------------------------------------------------------------------


class TestWorkspaceConfigPathTraversal:
    def test_dotdot_rejected(self) -> None:
        with pytest.raises(ValueError, match="relative without"):
            WorkspaceConfig(repos={"evil": "../../etc"})

    def test_absolute_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="relative without"):
            WorkspaceConfig(repos={"evil": "/etc/passwd"})

    def test_dotdot_in_middle_rejected(self) -> None:
        with pytest.raises(ValueError, match="relative without"):
            WorkspaceConfig(repos={"evil": "backend/../../../etc"})

    def test_dotdot_as_substring_allowed(self) -> None:
        cfg = WorkspaceConfig(repos={"ok": "backend/my..svc"})
        assert cfg.repos["ok"] == "backend/my..svc"


# ---------------------------------------------------------------------------
# apply_workspace_routing
# ---------------------------------------------------------------------------


class TestApplyWorkspaceRouting:
    @pytest.fixture()
    def repos(self) -> dict[str, str]:
        return {"svc": "backend/svc"}

    def test_routes_to_sub_repo(self, tmp_path: Path, repos: dict[str, str]) -> None:
        sub = tmp_path / "backend" / "svc"
        sub.mkdir(parents=True)

        with patch("shoal.core.git.git_root", return_value=str(sub)):
            new_root, _new_path = apply_workspace_routing(
                str(tmp_path), str(tmp_path), repo="svc", repos=repos
            )
        assert new_root == str(sub)

    def test_no_match_returns_original(self, tmp_path: Path, repos: dict[str, str]) -> None:
        root = str(tmp_path)
        new_root, new_path = apply_workspace_routing(root, root, repos=repos)
        assert new_root == root
        assert new_path == root

    def test_not_a_git_repo_raises(self, tmp_path: Path, repos: dict[str, str]) -> None:
        with patch(
            "shoal.core.git.git_root",
            side_effect=subprocess.CalledProcessError(128, "git"),
        ):
            with pytest.raises(ValueError, match="Not a git repo"):
                apply_workspace_routing(str(tmp_path), str(tmp_path), repo="svc", repos=repos)
