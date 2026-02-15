"""Tests for core/config.py — TOML loading and path helpers."""


from shoal.core.config import (
    available_tools,
    load_conductor_profile,
    load_config,
    load_tool_config,
)


class TestLoadConfig:
    def test_loads_config(self, mock_dirs):
        cfg = load_config()
        assert cfg.general.default_tool == "claude"
        assert cfg.notifications.enabled is False

    def test_default_when_missing(self, tmp_path, monkeypatch):
        from shoal.core import config as config_mod

        load_config.cache_clear()
        monkeypatch.setattr(config_mod, "config_dir", lambda: tmp_path / "nonexistent")
        cfg = load_config()
        assert cfg.general.default_tool == "claude"
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
        import pytest

        with pytest.raises(FileNotFoundError):
            load_tool_config("nonexistent")


class TestLoadConductorProfile:
    def test_loads_default(self, mock_dirs):
        profile = load_conductor_profile("default")
        assert profile.name == "default"
        assert profile.tool == "opencode"
        assert profile.monitoring.poll_interval == 10
        assert profile.escalation.notify is True

    def test_missing_profile(self, mock_dirs):
        import pytest

        with pytest.raises(FileNotFoundError):
            load_conductor_profile("nonexistent")


class TestAvailableTools:
    def test_lists_tools(self, mock_dirs):
        tools = available_tools()
        assert "claude" in tools
        assert "opencode" in tools
