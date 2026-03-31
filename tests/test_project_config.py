"""Tests for project-level .shoal.toml config."""

from __future__ import annotations

from pathlib import Path

import pytest

from shoal.core.config import ConfigLoadError, load_project_config
from shoal.models.config import ProjectConfig


class TestProjectConfig:
    def test_defaults(self) -> None:
        cfg = ProjectConfig()
        assert cfg.env == {}
        assert cfg.setup_commands == []
        assert cfg.default_tool == ""
        assert cfg.default_template == ""

    def test_full_config(self) -> None:
        cfg = ProjectConfig(
            env={"EDITOR": "nvim"},
            setup_commands=["uv sync"],
            default_tool="claude",
            default_template="claude-dev",
        )
        assert cfg.env["EDITOR"] == "nvim"
        assert cfg.setup_commands == ["uv sync"]

    def test_extra_fields_rejected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ProjectConfig(bogus="nope")  # type: ignore[call-arg]


class TestLoadProjectConfig:
    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        assert load_project_config(str(tmp_path)) is None

    def test_loads_valid_config(self, tmp_path: Path) -> None:
        (tmp_path / ".shoal.toml").write_text(
            'setup_commands = ["uv sync"]\ndefault_tool = "pi"\n\n[env]\nEDITOR = "nvim"\n'
        )
        cfg = load_project_config(str(tmp_path))
        assert cfg is not None
        assert cfg.env == {"EDITOR": "nvim"}
        assert cfg.setup_commands == ["uv sync"]
        assert cfg.default_tool == "pi"

    def test_raises_on_bad_toml(self, tmp_path: Path) -> None:
        (tmp_path / ".shoal.toml").write_text("not valid [[[toml")
        with pytest.raises(ConfigLoadError, match="TOML parse error"):
            load_project_config(str(tmp_path))

    def test_raises_on_invalid_schema(self, tmp_path: Path) -> None:
        (tmp_path / ".shoal.toml").write_text('bogus = "nope"\n')
        with pytest.raises(ConfigLoadError, match="validation error"):
            load_project_config(str(tmp_path))

    def test_empty_file(self, tmp_path: Path) -> None:
        (tmp_path / ".shoal.toml").write_text("")
        cfg = load_project_config(str(tmp_path))
        assert cfg is not None
        assert cfg.env == {}
