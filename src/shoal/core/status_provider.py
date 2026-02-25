"""Status provider abstraction for backend-specific status detection."""

from __future__ import annotations

import logging
from typing import Literal, Protocol

from shoal.models.config import ToolConfig
from shoal.models.state import SessionStatus

ProviderName = Literal["regex", "pi", "opencode_compat"]

logger = logging.getLogger("shoal.status_provider")


def default_status_provider_for_tool(tool_name: str) -> ProviderName:
    """Return the default status provider for a tool name."""
    lowered = tool_name.strip().lower()
    if lowered == "pi":
        return "pi"
    if lowered == "opencode":
        return "opencode_compat"
    return "regex"


class StatusProvider(Protocol):
    """Backend-specific status detector contract."""

    name: ProviderName
    compatibility_mode: bool

    def detect_status(self, pane_content: str, tool_config: ToolConfig) -> SessionStatus:
        """Detect status from pane content for a tool config."""


class RegexStatusProvider:
    """Regex-only provider using detection patterns from tool config."""

    name: ProviderName = "regex"
    compatibility_mode = False

    def detect_status(self, pane_content: str, tool_config: ToolConfig) -> SessionStatus:
        if not pane_content.strip():
            return SessionStatus.idle

        patterns = tool_config.detection

        for pattern in patterns._compiled_error:
            if pattern.search(pane_content):
                return SessionStatus.error

        for pattern in patterns._compiled_waiting:
            if pattern.search(pane_content):
                return SessionStatus.waiting

        for pattern in patterns._compiled_busy:
            if pattern.search(pane_content):
                return SessionStatus.running

        return SessionStatus.idle


class PiStatusProvider(RegexStatusProvider):
    """Pi-first provider (currently regex backed)."""

    name: ProviderName = "pi"


class OpenCodeCompatStatusProvider(RegexStatusProvider):
    """Compatibility provider for OpenCode status detection."""

    name: ProviderName = "opencode_compat"
    compatibility_mode = True


_PROVIDERS: dict[ProviderName, StatusProvider] = {
    "regex": RegexStatusProvider(),
    "pi": PiStatusProvider(),
    "opencode_compat": OpenCodeCompatStatusProvider(),
}


def provider_name_for_tool(tool_config: ToolConfig) -> ProviderName:
    """Resolve provider name with tool-aware defaults."""
    if tool_config.status_provider:
        return tool_config.status_provider
    return default_status_provider_for_tool(tool_config.name)


def resolve_status_provider(tool_config: ToolConfig) -> StatusProvider:
    """Resolve the provider implementation for a tool config."""
    provider_name = provider_name_for_tool(tool_config)
    return _PROVIDERS[provider_name]


def detect_status(pane_content: str, tool_config: ToolConfig) -> SessionStatus:
    """Detect status using the configured backend provider."""
    provider = resolve_status_provider(tool_config)
    logger.debug(
        "detect_status: tool=%s provider=%s content_len=%d",
        tool_config.name,
        provider.name,
        len(pane_content),
    )
    return provider.detect_status(pane_content, tool_config)


def describe_status_provider(tool_config: ToolConfig) -> str:
    """Return user-facing provider description."""
    provider = resolve_status_provider(tool_config)
    if provider.compatibility_mode:
        return f"{provider.name} (best effort)"
    return provider.name
