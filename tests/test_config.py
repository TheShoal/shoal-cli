"""Tests for core/config.py — TOML loading and path helpers."""

import pytest

from shoal.core.config import (
    available_templates,
    available_tools,
    load_robo_profile,
    load_config,
    load_template,
    load_tool_config,
)


class TestLoadConfig:
    def test_loads_config(self, mock_dirs):
        cfg = load_config()
        assert cfg.general.default_tool == "opencode"
        assert cfg.notifications.enabled is False

    def test_default_when_missing(self, tmp_path, monkeypatch):
        from shoal.core import config as config_mod

        load_config.cache_clear()
        monkeypatch.setattr(config_mod, "config_dir", lambda: tmp_path / "nonexistent")
        cfg = load_config()
        assert cfg.general.default_tool == "opencode"
        load_config.cache_clear()


class TestLoadToolConfig:
    def test_loads_claude(self, mock_dirs):
        cfg = load_tool_config("claude")
        assert cfg.name == "claude"
        assert cfg.command == "claude"
        assert cfg.icon == "🤖"
        assert "thinking" in cfg.detection.busy_patterns
        assert "Error:" in cfg.detection.error_patterns

    def test_loads_opencode(self, mock_dirs):
        cfg = load_tool_config("opencode")
        assert cfg.name == "opencode"
        assert cfg.command == "opencode"

    def test_missing_tool(self, mock_dirs):
        with pytest.raises(FileNotFoundError):
            load_tool_config("nonexistent")


class TestLoadRoboProfile:
    def test_loads_default(self, mock_dirs):
        profile = load_robo_profile("default")
        assert profile.name == "default"
        assert profile.tool == "opencode"
        assert profile.monitoring.poll_interval == 10
        assert profile.escalation.notify is True

    def test_missing_profile(self, mock_dirs):
        with pytest.raises(FileNotFoundError):
            load_robo_profile("nonexistent")


class TestAvailableTools:
    def test_lists_tools(self, mock_dirs):
        tools = available_tools()
        assert "claude" in tools
        assert "opencode" in tools


class TestTemplates:
    def test_available_templates_empty(self, mock_dirs):
        assert available_templates() == []

    def test_available_templates(self, mock_dirs):
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "feature-dev.toml").write_text(
            """
[template]
name = "feature-dev"
tool = "opencode"

[[windows]]
name = "main"

[[windows.panes]]
split = "root"
command = "opencode"
"""
        )

        assert available_templates() == ["feature-dev"]

    def test_load_template(self, mock_dirs):
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "feature-dev.toml").write_text(
            """
[template]
name = "feature-dev"
description = "Feature workflow"
tool = "opencode"

[template.worktree]
name = "feat/{slug}"
create_branch = true

[template.env]
FOO = "bar"

[[windows]]
name = "dev"
focus = true

[[windows.panes]]
split = "root"
command = "nvim ."
"""
        )

        template = load_template("feature-dev")
        assert template.name == "feature-dev"
        assert template.tool == "opencode"
        assert template.worktree.create_branch is True
        assert template.env["FOO"] == "bar"
        assert len(template.windows) == 1
        assert template.windows[0].panes[0].command == "nvim ."

    def test_load_template_missing(self, mock_dirs):
        with pytest.raises(FileNotFoundError):
            load_template("nonexistent")

    def test_load_template_invalid(self, mock_dirs):
        from pydantic import ValidationError

        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "broken.toml").write_text(
            """
[template]
name = "broken"

[[windows]]
name = "dev"

[[windows.panes]]
split = "root"
"""
        )

        with pytest.raises(ValidationError):
            load_template("broken")
