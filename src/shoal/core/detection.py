"""Compatibility wrapper for status detection."""

import logging

from shoal.core.status_provider import detect_status as _detect_status
from shoal.models.config import ToolConfig
from shoal.models.state import SessionStatus

logger = logging.getLogger("shoal.detection")


def detect_status(pane_content: str, tool_config: ToolConfig) -> SessionStatus:
    """Detect status through the configured provider abstraction."""
    logger.debug("detect_status: tool=%s content_len=%d", tool_config.name, len(pane_content))
    return _detect_status(pane_content, tool_config)


__all__ = ["detect_status"]
