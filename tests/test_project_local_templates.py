"""Tests for project-local template search path (.shoal/templates/)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from shoal.core.config import (
    _load_template_raw,
    available_mixins,
    available_templates,
    load_mixin,
    project_templates_dir,
    template_source,
)


@pytest.fixture()
def local_templates(tmp_path: Path) -> Path:
    """Create a project-local .shoal/templates/ directory."""
    tpl_dir = tmp_path / ".shoal" / "templates"
    tpl_dir.mkdir(parents=True)
    return tpl_dir


@pytest.fixture()
def local_mixins(local_templates: Path) -> Path:
    """Create a project-local .shoal/templates/mixins/ directory."""
    mixin_dir = local_templates / "mixins"
    mixin_dir.mkdir(parents=True)
    return mixin_dir


def _write_template(directory: Path, name: str, tool: str = "opencode") -> Path:
    """Write a minimal template TOML to a directory."""
    path = directory / f"{name}.toml"
    path.write_text(f'[template]\nname = "{name}"\ntool = "{tool}"\ndescription = "test {name}"\n')
    return path


def _write_mixin(directory: Path, name: str) -> Path:
    """Write a minimal mixin TOML to a directory."""
    path = directory / f"{name}.toml"
    path.write_text(f'[mixin]\nname = "{name}"\ndescription = "mixin {name}"\n')
    return path


class TestProjectTemplatesDir:
    """Test project_templates_dir() detection."""

    def test_returns_path_when_in_git_repo(self, tmp_path: Path) -> None:
        local_dir = tmp_path / ".shoal" / "templates"
        local_dir.mkdir(parents=True)
        with patch("shoal.core.git.git_root", return_value=str(tmp_path)):
            result = project_templates_dir()
        assert result == local_dir

    def test_returns_none_when_no_git_repo(self) -> None:
        import subprocess

        with patch(
            "shoal.core.git.git_root",
            side_effect=subprocess.CalledProcessError(128, "git"),
        ):
            assert project_templates_dir() is None

    def test_returns_none_when_dir_missing(self, tmp_path: Path) -> None:
        with patch("shoal.core.git.git_root", return_value=str(tmp_path)):
            assert project_templates_dir() is None


class TestLocalTemplateLoading:
    """Test that local templates shadow global ones."""

    def test_local_template_found(
        self, local_templates: Path, tmp_path: Path, mock_dirs: object
    ) -> None:
        _write_template(local_templates, "my-local", tool="claude")
        with patch("shoal.core.config.project_templates_dir", return_value=local_templates):
            raw = _load_template_raw("my-local")
        assert raw["template"]["tool"] == "claude"

    def test_local_shadows_global(
        self, local_templates: Path, mock_dirs: tuple[Path, Path]
    ) -> None:
        config_dir, _ = mock_dirs
        global_dir = config_dir / "templates"
        global_dir.mkdir(parents=True, exist_ok=True)
        _write_template(global_dir, "shared", tool="opencode")
        _write_template(local_templates, "shared", tool="claude")

        with patch("shoal.core.config.project_templates_dir", return_value=local_templates):
            raw = _load_template_raw("shared")
        assert raw["template"]["tool"] == "claude"

    def test_falls_back_to_global(
        self, local_templates: Path, mock_dirs: tuple[Path, Path]
    ) -> None:
        config_dir, _ = mock_dirs
        global_dir = config_dir / "templates"
        global_dir.mkdir(parents=True, exist_ok=True)
        _write_template(global_dir, "global-only", tool="opencode")

        with patch("shoal.core.config.project_templates_dir", return_value=local_templates):
            raw = _load_template_raw("global-only")
        assert raw["template"]["tool"] == "opencode"

    def test_no_git_falls_back_to_global(self, mock_dirs: tuple[Path, Path]) -> None:
        config_dir, _ = mock_dirs
        global_dir = config_dir / "templates"
        global_dir.mkdir(parents=True, exist_ok=True)
        _write_template(global_dir, "global-only", tool="opencode")

        with patch("shoal.core.config.project_templates_dir", return_value=None):
            raw = _load_template_raw("global-only")
        assert raw["template"]["tool"] == "opencode"


class TestMergedListing:
    """Test that available_templates() merges local and global."""

    def test_merged_listing(self, local_templates: Path, mock_dirs: tuple[Path, Path]) -> None:
        config_dir, _ = mock_dirs
        global_dir = config_dir / "templates"
        global_dir.mkdir(parents=True, exist_ok=True)
        _write_template(global_dir, "global-tmpl")
        _write_template(local_templates, "local-tmpl")

        with patch("shoal.core.config.project_templates_dir", return_value=local_templates):
            names = available_templates()
        assert "global-tmpl" in names
        assert "local-tmpl" in names

    def test_deduplicated(self, local_templates: Path, mock_dirs: tuple[Path, Path]) -> None:
        config_dir, _ = mock_dirs
        global_dir = config_dir / "templates"
        global_dir.mkdir(parents=True, exist_ok=True)
        _write_template(global_dir, "shared")
        _write_template(local_templates, "shared")

        with patch("shoal.core.config.project_templates_dir", return_value=local_templates):
            names = available_templates()
        assert names.count("shared") == 1


class TestTemplateSource:
    """Test template_source() returns correct origin."""

    def test_local_source(self, local_templates: Path) -> None:
        _write_template(local_templates, "my-tmpl")
        with patch("shoal.core.config.project_templates_dir", return_value=local_templates):
            assert template_source("my-tmpl") == "local"

    def test_global_source(self) -> None:
        with patch("shoal.core.config.project_templates_dir", return_value=None):
            assert template_source("any") == "global"


class TestLocalMixins:
    """Test project-local mixins."""

    def test_local_mixin_found(self, local_mixins: Path, mock_dirs: object) -> None:
        _write_mixin(local_mixins, "my-mixin")
        with patch(
            "shoal.core.config.project_templates_dir",
            return_value=local_mixins.parent,
        ):
            mixin = load_mixin("my-mixin")
        assert mixin.name == "my-mixin"

    def test_available_mixins_merged(
        self, local_mixins: Path, mock_dirs: tuple[Path, Path]
    ) -> None:
        config_dir, _ = mock_dirs
        global_mixins = config_dir / "templates" / "mixins"
        global_mixins.mkdir(parents=True, exist_ok=True)
        _write_mixin(global_mixins, "global-mix")
        _write_mixin(local_mixins, "local-mix")

        with patch(
            "shoal.core.config.project_templates_dir",
            return_value=local_mixins.parent,
        ):
            names = available_mixins()
        assert "global-mix" in names
        assert "local-mix" in names
