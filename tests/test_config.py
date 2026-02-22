"""Tests for core/config.py — TOML loading and path helpers."""

import pytest

from shoal.core.config import (
    available_templates,
    available_tools,
    load_config,
    load_mcp_registry,
    load_robo_profile,
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

    def test_load_template_with_mcp(self, mock_dirs):
        """Template with mcp declarations loads correctly."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "ai-dev.toml").write_text(
            """
[template]
name = "ai-dev"
tool = "claude"
mcp = ["memory", "filesystem"]

[[windows]]
name = "editor"

[[windows.panes]]
split = "root"
command = "claude"
"""
        )
        template = load_template("ai-dev")
        assert template.mcp == ["memory", "filesystem"]

    def test_load_template_without_mcp(self, mock_dirs):
        """Template without mcp field defaults to empty list."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "basic.toml").write_text(
            """
[template]
name = "basic"
tool = "opencode"

[[windows]]
name = "main"

[[windows.panes]]
split = "root"
command = "opencode"
"""
        )
        template = load_template("basic")
        assert template.mcp == []

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


class TestLoadMcpRegistry:
    def test_load_mcp_registry_defaults(self, mock_dirs):
        """Registry returns built-in defaults when no user file exists."""
        registry = load_mcp_registry()
        assert "memory" in registry
        assert "filesystem" in registry
        assert "github" in registry
        assert "fetch" in registry
        assert "npx" in registry["memory"]

    def test_load_mcp_registry_custom(self, mock_dirs):
        """User file adds new servers to the registry."""
        tmp_config, _ = mock_dirs
        (tmp_config / "mcp-servers.toml").write_text(
            """
[my-rag]
command = "/usr/local/bin/my-rag-server"
"""
        )
        registry = load_mcp_registry()
        assert "my-rag" in registry
        assert registry["my-rag"] == "/usr/local/bin/my-rag-server"
        # Built-in defaults still present
        assert "memory" in registry

    def test_load_mcp_registry_override(self, mock_dirs):
        """User file can override built-in server commands."""
        tmp_config, _ = mock_dirs
        (tmp_config / "mcp-servers.toml").write_text(
            """
[memory]
command = "my-custom-memory-server"
"""
        )
        registry = load_mcp_registry()
        assert registry["memory"] == "my-custom-memory-server"
        # Other defaults still present
        assert "filesystem" in registry
