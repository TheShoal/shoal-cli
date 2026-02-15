"""Status detection — pure function, no subprocess calls."""

from __future__ import annotations

from shoal.models.config import ToolConfig
from shoal.models.state import SessionStatus


def detect_status(pane_content: str, tool_config: ToolConfig) -> SessionStatus:
    """Detect agent status from pane content using tool-specific patterns.

    Checks in priority order: error > waiting > busy > idle.
    """
    if not pane_content.strip():
        return SessionStatus.idle

    patterns = tool_config.detection

    for pattern in patterns.error_patterns:
        if pattern in pane_content:
            return SessionStatus.error

    for pattern in patterns.waiting_patterns:
        if pattern in pane_content:
            return SessionStatus.waiting

    for pattern in patterns.busy_patterns:
        if pattern in pane_content:
            return SessionStatus.running

    return SessionStatus.idle
