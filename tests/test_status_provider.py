"""Tests for status provider selection and descriptions."""

from shoal.core.status_provider import describe_status_provider, provider_name_for_tool
from shoal.models.config import ToolConfig


class TestStatusProviders:
    def test_provider_defaults_from_tool_name(self):
        pi = ToolConfig(name="pi", command="pi")
        opencode = ToolConfig(name="opencode", command="opencode")
        claude = ToolConfig(name="claude", command="claude")

        assert provider_name_for_tool(pi) == "pi"
        assert provider_name_for_tool(opencode) == "opencode_compat"
        assert provider_name_for_tool(claude) == "regex"

    def test_explicit_provider_override(self):
        cfg = ToolConfig(name="pi", command="pi", status_provider="regex")
        assert provider_name_for_tool(cfg) == "regex"

    def test_description_marks_compatibility_mode(self):
        cfg = ToolConfig(name="opencode", command="opencode", status_provider="opencode_compat")
        assert describe_status_provider(cfg) == "opencode_compat (best effort)"
