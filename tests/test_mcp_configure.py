"""Tests for services/mcp_configure.py — auto-configure MCP for tools."""

import json
from unittest.mock import patch

import pytest

from shoal.services.mcp_configure import (
    McpConfigureError,
    configure_mcp_for_tool,
)


class TestConfigureViaCommand:
    def test_command_success(self, mock_dirs):
        """Tool with config_cmd should run the command."""
        with patch("shoal.services.mcp_configure.subprocess.run") as mock_run:
            result = configure_mcp_for_tool("claude", "memory", "/tmp/work")

        assert result is not None
        assert "Configured via command" in result
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd_list = call_args[0][0]
        assert isinstance(cmd_list, list)
        assert cmd_list == ["claude", "mcp", "add", "memory", "--", "shoal-mcp-proxy", "memory"]
        assert call_args[1]["shell"] is False
        assert call_args[1]["cwd"] == "/tmp/work"

    def test_shell_metacharacters_safe(self, mock_dirs):
        """Shell metacharacters in names should not cause injection."""
        with patch("shoal.services.mcp_configure.subprocess.run") as mock_run:
            configure_mcp_for_tool("claude", "test$(whoami)", "/tmp/work")

        call_args = mock_run.call_args
        cmd_list = call_args[0][0]
        # The name is passed as a single list element, not interpreted by shell
        assert "test$(whoami)" in cmd_list
        assert call_args[1]["shell"] is False

    def test_command_not_found(self, mock_dirs):
        """Should raise McpConfigureError when config command is not found."""

        with (
            patch(
                "shoal.services.mcp_configure.subprocess.run",
                side_effect=FileNotFoundError("not found"),
            ),
            pytest.raises(McpConfigureError, match="not found"),
        ):
            configure_mcp_for_tool("claude", "memory", "/tmp/work")

    def test_command_failure(self, mock_dirs):
        """Should raise McpConfigureError when command exits non-zero."""
        import subprocess

        with (
            patch(
                "shoal.services.mcp_configure.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "cmd", stderr="oops"),
            ),
            pytest.raises(McpConfigureError, match="failed"),
        ):
            configure_mcp_for_tool("claude", "memory", "/tmp/work")


class TestConfigureViaFile:
    def test_file_create(self, mock_dirs, tmp_path):
        """Tool with config_file should create config JSON if missing."""
        with patch("shoal.core.config.load_tool_config") as mock_tool:
            from shoal.models.config import MCPToolConfig, ToolConfig

            mock_tool.return_value = ToolConfig(
                name="opencode",
                command="opencode",
                mcp=MCPToolConfig(config_file=".opencode.json"),
            )

            result = configure_mcp_for_tool("opencode", "memory", str(tmp_path))

        assert result is not None
        assert "Configured via file" in result

        config_path = tmp_path / ".opencode.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert data["mcpServers"]["memory"]["command"] == "shoal-mcp-proxy"
        assert data["mcpServers"]["memory"]["args"] == ["memory"]

    def test_file_merge(self, mock_dirs, tmp_path):
        """Tool with config_file should merge into existing config."""
        config_path = tmp_path / ".opencode.json"
        config_path.write_text(
            json.dumps({"setting": "value", "mcpServers": {"existing": {}}}) + "\n"
        )

        with patch("shoal.core.config.load_tool_config") as mock_tool:
            from shoal.models.config import MCPToolConfig, ToolConfig

            mock_tool.return_value = ToolConfig(
                name="opencode",
                command="opencode",
                mcp=MCPToolConfig(config_file=".opencode.json"),
            )

            result = configure_mcp_for_tool("opencode", "github", str(tmp_path))

        assert result is not None
        data = json.loads(config_path.read_text())
        # Existing data preserved
        assert data["setting"] == "value"
        assert "existing" in data["mcpServers"]
        # New entry added
        assert "github" in data["mcpServers"]

    def test_invalid_json(self, mock_dirs, tmp_path):
        """Should raise when existing config file is invalid JSON."""
        (tmp_path / ".opencode.json").write_text("not json {{{")

        with patch("shoal.core.config.load_tool_config") as mock_tool:
            from shoal.models.config import MCPToolConfig, ToolConfig

            mock_tool.return_value = ToolConfig(
                name="opencode",
                command="opencode",
                mcp=MCPToolConfig(config_file=".opencode.json"),
            )

            with pytest.raises(McpConfigureError, match="parse"):
                configure_mcp_for_tool("opencode", "memory", str(tmp_path))


class TestNoConfig:
    def test_no_config_available(self, mock_dirs):
        """Tool with neither config_cmd nor config_file returns None."""
        result = configure_mcp_for_tool("pi", "memory", "/tmp/work")
        assert result is None

    def test_tool_not_found(self, mock_dirs):
        """Unknown tool returns None."""
        result = configure_mcp_for_tool("nonexistent-tool", "memory", "/tmp/work")
        assert result is None
