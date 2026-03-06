"""Tests for core/config.py — TOML loading and path helpers."""

from pathlib import Path
from unittest.mock import patch

import pytest

from shoal.core.config import (
    ConfigLoadError,
    _examples_dir,
    available_templates,
    available_tools,
    load_config,
    load_mcp_registry,
    load_mcp_registry_full,
    load_mixin,
    load_robo_profile,
    load_template,
    load_tool_config,
    scaffold_defaults,
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
        assert cfg.general.default_tool == "pi"
        load_config.cache_clear()

    def test_use_nerd_fonts_default(self, mock_dirs):
        cfg = load_config()
        assert cfg.general.use_nerd_fonts is True

    def test_use_nerd_fonts_override(self, mock_dirs):
        tmp_config, _ = mock_dirs
        load_config.cache_clear()
        (tmp_config / "config.toml").write_text(
            """
[general]
use_nerd_fonts = false

[notifications]
enabled = false
"""
        )
        cfg = load_config()
        assert cfg.general.use_nerd_fonts is False
        load_config.cache_clear()


class TestLoadToolConfig:
    def test_loads_claude(self, mock_dirs):
        cfg = load_tool_config("claude")
        assert cfg.name == "claude"
        assert cfg.command == "claude"
        assert cfg.icon == "🤖"
        assert cfg.status_provider == "regex"
        assert "thinking" in cfg.detection.busy_patterns
        assert "Error:" in cfg.detection.error_patterns

    def test_loads_opencode(self, mock_dirs):
        cfg = load_tool_config("opencode")
        assert cfg.name == "opencode"
        assert cfg.command == "opencode"
        assert cfg.status_provider == "opencode_compat"

    def test_loads_codex(self, mock_dirs):
        cfg = load_tool_config("codex")
        assert cfg.name == "codex"
        assert cfg.command == "codex"
        assert cfg.status_provider == "regex"

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
        assert "codex" in tools
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
        from shoal.core.config import ConfigLoadError

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

        with pytest.raises(ConfigLoadError):
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


class TestExamplesDir:
    def test_examples_dir_exists(self):
        """Bundled examples directory should exist in the source tree."""
        assert _examples_dir().is_dir()

    def test_examples_dir_has_config_toml(self):
        assert (_examples_dir() / "config.toml").is_file()

    def test_examples_dir_has_tool_configs(self):
        tools = _examples_dir() / "tools"
        assert (tools / "claude.toml").is_file()
        assert (tools / "codex.toml").is_file()
        assert (tools / "opencode.toml").is_file()


class TestScaffoldDefaults:
    def test_scaffolds_all_files_on_empty_dir(self, tmp_path: Path) -> None:
        """On an empty config dir, all example files should be copied."""
        cfg = tmp_path / "config" / "shoal"
        cfg.mkdir(parents=True)
        with patch("shoal.core.config.config_dir", return_value=cfg):
            created = scaffold_defaults()
        assert len(created) > 0
        assert "config.toml" in created
        assert "tools/claude.toml" in created
        assert "tools/codex.toml" in created
        assert "tools/opencode.toml" in created
        # Verify files actually exist
        assert (cfg / "config.toml").is_file()
        assert (cfg / "tools" / "claude.toml").is_file()

    def test_skips_existing_files(self, tmp_path: Path) -> None:
        """Existing files should not be overwritten."""
        cfg = tmp_path / "config" / "shoal"
        cfg.mkdir(parents=True)
        # Pre-create config.toml with custom content
        (cfg / "config.toml").write_text("# my custom config\n")
        with patch("shoal.core.config.config_dir", return_value=cfg):
            created = scaffold_defaults()
        assert "config.toml" not in created
        # Original content preserved
        assert (cfg / "config.toml").read_text() == "# my custom config\n"
        # Other files still created
        assert "tools/claude.toml" in created

    def test_returns_empty_when_all_exist(self, tmp_path: Path) -> None:
        """When all files already exist, nothing is created."""
        cfg = tmp_path / "config" / "shoal"
        cfg.mkdir(parents=True)
        # First pass: scaffold everything
        with patch("shoal.core.config.config_dir", return_value=cfg):
            first = scaffold_defaults()
        assert len(first) > 0
        # Second pass: nothing new
        with patch("shoal.core.config.config_dir", return_value=cfg):
            second = scaffold_defaults()
        assert second == []

    def test_creates_subdirectories(self, tmp_path: Path) -> None:
        """Scaffold creates tools/, templates/, etc. subdirectories."""
        cfg = tmp_path / "config" / "shoal"
        cfg.mkdir(parents=True)
        with patch("shoal.core.config.config_dir", return_value=cfg):
            scaffold_defaults()
        assert (cfg / "tools").is_dir()
        assert (cfg / "templates").is_dir()
        assert (cfg / "templates" / "mixins").is_dir()

    def test_handles_missing_examples_dir(self, tmp_path: Path) -> None:
        """Returns empty list when bundled examples are not found."""
        cfg = tmp_path / "config" / "shoal"
        cfg.mkdir(parents=True)
        with (
            patch("shoal.core.config.config_dir", return_value=cfg),
            patch("shoal.core.config._examples_dir", return_value=tmp_path / "nonexistent"),
        ):
            created = scaffold_defaults()
        assert created == []


class TestLoadMcpRegistryFull:
    def test_defaults_present(self, mock_dirs: tuple[Path, Path]) -> None:
        """Built-in defaults are returned even without a user file."""
        registry = load_mcp_registry_full()
        assert "memory" in registry
        assert "filesystem" in registry
        assert "github" in registry
        assert "command" in registry["memory"]

    def test_user_overrides(self, mock_dirs: tuple[Path, Path]) -> None:
        """User file overrides built-in entries."""
        tmp_config, _ = mock_dirs
        (tmp_config / "mcp-servers.toml").write_text(
            """
[memory]
command = "custom-memory"
transport = "http"
"""
        )
        registry = load_mcp_registry_full()
        assert registry["memory"]["command"] == "custom-memory"
        assert registry["memory"]["transport"] == "http"
        # Other defaults still present
        assert "filesystem" in registry

    def test_user_adds_new_servers(self, mock_dirs: tuple[Path, Path]) -> None:
        """User file can add new servers not in defaults."""
        tmp_config, _ = mock_dirs
        (tmp_config / "mcp-servers.toml").write_text(
            """
[my-rag]
command = "/usr/local/bin/rag-server"
"""
        )
        registry = load_mcp_registry_full()
        assert "my-rag" in registry
        assert registry["my-rag"]["command"] == "/usr/local/bin/rag-server"
        # Defaults still present
        assert "memory" in registry


class TestMalformedToml:
    def test_malformed_config_toml(self, mock_dirs: tuple[Path, Path]) -> None:
        """Malformed config.toml raises ConfigLoadError."""
        tmp_config, _ = mock_dirs
        load_config.cache_clear()
        (tmp_config / "config.toml").write_text("invalid toml {{{{")
        with pytest.raises(ConfigLoadError, match="malformed TOML"):
            load_config()
        load_config.cache_clear()

    def test_malformed_tool_toml(self, mock_dirs: tuple[Path, Path]) -> None:
        """Malformed tool config raises ConfigLoadError."""
        tmp_config, _ = mock_dirs
        tools = tmp_config / "tools"
        (tools / "bad-tool.toml").write_text("not valid [[[")
        with pytest.raises(ConfigLoadError, match="malformed TOML"):
            load_tool_config("bad-tool")

    def test_malformed_template_toml(self, mock_dirs: tuple[Path, Path]) -> None:
        """Malformed template TOML raises ConfigLoadError."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "bad.toml").write_text("{{not toml}}")
        with pytest.raises(ConfigLoadError, match="malformed TOML"):
            load_template("bad")

    def test_malformed_mixin_toml(self, mock_dirs: tuple[Path, Path]) -> None:
        """Malformed mixin TOML raises ConfigLoadError."""
        tmp_config, _ = mock_dirs
        mixins = tmp_config / "templates" / "mixins"
        mixins.mkdir(parents=True, exist_ok=True)
        (mixins / "bad.toml").write_text("{{broken}}")
        with pytest.raises(ConfigLoadError, match="malformed TOML"):
            load_mixin("bad")

    def test_malformed_mcp_servers_toml(self, mock_dirs: tuple[Path, Path]) -> None:
        """Malformed mcp-servers.toml raises ConfigLoadError."""
        tmp_config, _ = mock_dirs
        (tmp_config / "mcp-servers.toml").write_text("invalid [[[toml")
        with pytest.raises(ConfigLoadError, match="malformed TOML"):
            load_mcp_registry()

    def test_malformed_robo_profile(self, mock_dirs: tuple[Path, Path]) -> None:
        """Malformed robo profile raises ConfigLoadError."""
        tmp_config, _ = mock_dirs
        robo = tmp_config / "robo"
        (robo / "bad.toml").write_text("not valid {{")
        with pytest.raises(ConfigLoadError, match="malformed TOML"):
            load_robo_profile("bad")


class TestExtraFieldsRejected:
    def test_unknown_field_in_general(self, mock_dirs: tuple[Path, Path]) -> None:
        """Unknown field in [general] raises ConfigLoadError."""
        tmp_config, _ = mock_dirs
        load_config.cache_clear()
        (tmp_config / "config.toml").write_text(
            """
[general]
default_tool = "opencode"
state_dir = "~/.local/share/shoal"
"""
        )
        with pytest.raises(ConfigLoadError, match="invalid config"):
            load_config()
        load_config.cache_clear()

    def test_unknown_top_level_section(self, mock_dirs: tuple[Path, Path]) -> None:
        """Unknown top-level section raises ConfigLoadError."""
        tmp_config, _ = mock_dirs
        load_config.cache_clear()
        (tmp_config / "config.toml").write_text(
            """
[general]
default_tool = "opencode"

[bogus_section]
foo = "bar"
"""
        )
        with pytest.raises(ConfigLoadError, match="invalid config"):
            load_config()
        load_config.cache_clear()

    def test_unknown_field_in_tool_detection(self, mock_dirs: tuple[Path, Path]) -> None:
        """Unknown field in [detection] section raises ConfigLoadError."""
        tmp_config, _ = mock_dirs
        tools = tmp_config / "tools"
        (tools / "bad.toml").write_text(
            """
[tool]
name = "bad"
command = "bad"

[detection]
busy_patterns = ["thinking"]
unknown_field = "oops"
"""
        )
        with pytest.raises(ConfigLoadError, match="invalid tool config"):
            load_tool_config("bad")

    def test_unknown_field_in_template(self, mock_dirs: tuple[Path, Path]) -> None:
        """Unknown field in template pane raises ConfigLoadError."""
        tmp_config, _ = mock_dirs
        templates = tmp_config / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "bad.toml").write_text(
            """
[template]
name = "bad"
tool = "opencode"

[[windows]]
name = "main"
bogus = "field"

[[windows.panes]]
split = "root"
command = "opencode"
"""
        )
        with pytest.raises(ConfigLoadError, match="invalid template"):
            load_template("bad")
