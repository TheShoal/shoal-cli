"""Tests for HTTP transport default for shoal-orchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from shoal.services.mcp_pool import _DEFAULT_TRANSPORTS, get_transport


class TestTransportDetection:
    """Test transport auto-detection logic."""

    def test_shoal_orchestrator_defaults_http(self) -> None:
        assert _DEFAULT_TRANSPORTS.get("shoal-orchestrator") == "http"

    def test_get_transport_default_http(self) -> None:
        with patch("shoal.core.config.load_mcp_registry_full", return_value={}):
            assert get_transport("shoal-orchestrator") == "http"

    def test_get_transport_default_socket(self) -> None:
        with patch("shoal.core.config.load_mcp_registry_full", return_value={}):
            assert get_transport("memory") == "socket"

    def test_get_transport_user_override(self) -> None:
        registry = {"memory": {"command": "some-cmd", "transport": "http"}}
        with patch("shoal.core.config.load_mcp_registry_full", return_value=registry):
            assert get_transport("memory") == "http"

    def test_get_transport_user_override_socket(self) -> None:
        registry = {"shoal-orchestrator": {"command": "cmd", "transport": "socket"}}
        with patch("shoal.core.config.load_mcp_registry_full", return_value=registry):
            assert get_transport("shoal-orchestrator") == "socket"


class TestAutoStartHTTP:
    """Test that mcp_start auto-detects HTTP for known servers."""

    def test_auto_http_for_shoal_orchestrator(self) -> None:
        """Verify get_transport returns http for shoal-orchestrator."""
        with patch("shoal.core.config.load_mcp_registry_full", return_value={}):
            transport = get_transport("shoal-orchestrator")
        assert transport == "http"


class TestHTTPConfigGeneration:
    """Test HTTP URL config generation for tools."""

    def test_configure_http_for_tool_with_config_file(self, tmp_path: Path) -> None:
        from shoal.models.config import MCPToolConfig
        from shoal.services.mcp_configure import _configure_http_for_tool

        mcp_cfg = MCPToolConfig(config_file=".opencode.json")
        result = _configure_http_for_tool(
            "opencode", "shoal-orchestrator", str(tmp_path), 8390, mcp_cfg
        )
        assert result is not None
        assert "HTTP URL" in result

        import json

        config_file = Path(tmp_path) / ".opencode.json"
        config = json.loads(config_file.read_text())
        assert "shoal-orchestrator" in config["mcpServers"]
        expected_url = "http://localhost:8390/mcp/"
        assert config["mcpServers"]["shoal-orchestrator"]["url"] == expected_url

    def test_configure_http_no_config_file(self) -> None:
        from shoal.models.config import MCPToolConfig
        from shoal.services.mcp_configure import _configure_http_for_tool

        mcp_cfg = MCPToolConfig()
        result = _configure_http_for_tool("opencode", "shoal-orchestrator", "/tmp", 8390, mcp_cfg)
        assert result is not None
        assert "http://localhost:8390" in result
