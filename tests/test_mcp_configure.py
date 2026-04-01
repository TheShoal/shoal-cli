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


class TestConfigureHttpForTool:
    def test_http_config_with_file_success(self, mock_dirs, tmp_path):
        from shoal.services.mcp_configure import _configure_http_for_tool

        class MockMcpCfg:
            config_file = "test_config.json"

        work_dir = tmp_path

        result = _configure_http_for_tool(
            "tool_name", "http_mcp", str(work_dir), 8080, MockMcpCfg()
        )

        config_path = work_dir / "test_config.json"

        assert result == f"Configured HTTP URL in {config_path}"
        assert config_path.exists()

        with open(config_path) as f:
            data = json.load(f)

        assert data == {"mcpServers": {"http_mcp": {"url": "http://localhost:8080/mcp/"}}}

    def test_http_config_with_existing_file(self, mock_dirs, tmp_path):
        from shoal.services.mcp_configure import _configure_http_for_tool

        class MockMcpCfg:
            config_file = "test_config.json"

        work_dir = tmp_path
        config_path = work_dir / "test_config.json"

        with open(config_path, "w") as f:
            json.dump({"existing": "value", "mcpServers": {"other": {"url": "http://other"}}}, f)

        _configure_http_for_tool("tool_name", "http_mcp", str(work_dir), 8080, MockMcpCfg())

        with open(config_path) as f:
            data = json.load(f)

        assert data["existing"] == "value"
        assert data["mcpServers"]["other"]["url"] == "http://other"
        assert data["mcpServers"]["http_mcp"]["url"] == "http://localhost:8080/mcp/"

    def test_http_config_no_file(self, mock_dirs, tmp_path):
        from shoal.services.mcp_configure import _configure_http_for_tool

        class MockMcpCfg:
            config_file = None

        work_dir = tmp_path

        result = _configure_http_for_tool(
            "tool_name", "http_mcp", str(work_dir), 8080, MockMcpCfg()
        )

        assert result == "HTTP server at http://localhost:8080/mcp/"

    def test_http_config_invalid_json_file(self, mock_dirs, tmp_path):
        from shoal.services.mcp_configure import McpConfigureError, _configure_http_for_tool

        class MockMcpCfg:
            config_file = "test_config.json"

        work_dir = tmp_path
        config_path = work_dir / "test_config.json"
        config_path.write_text("invalid json")

        with pytest.raises(McpConfigureError, match="Failed to parse config file"):
            _configure_http_for_tool("tool_name", "http_mcp", str(work_dir), 8080, MockMcpCfg())


class TestHttpTransportIntegration:
    def test_http_transport_routing(self, mock_dirs, tmp_path):
        from shoal.services.mcp_configure import configure_mcp_for_tool

        with (
            patch("shoal.core.config.load_tool_config") as mock_tool,
            patch("shoal.services.mcp_pool.get_transport") as mock_transport,
            patch("shoal.services.mcp_pool.read_port") as mock_port,
        ):
            from shoal.models.config import MCPToolConfig, ToolConfig

            mock_tool.return_value = ToolConfig(
                name="opencode",
                command="opencode",
                mcp=MCPToolConfig(config_file=".opencode.json"),
            )
            mock_transport.return_value = "http"
            mock_port.return_value = 8080

            result = configure_mcp_for_tool("opencode", "memory", str(tmp_path))

            assert "HTTP URL in" in result
