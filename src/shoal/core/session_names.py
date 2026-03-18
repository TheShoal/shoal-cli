# SPDX-License-Identifier: MIT
"""Session naming helpers shared across models, CLI, and services."""

from __future__ import annotations

import re

from shoal.core.config import load_config


def validate_session_name(name: str) -> None:
    """Validate session name for security and compatibility.

    Session names are used in:
    - tmux session names (via ``build_tmux_session_name``)
    - file paths (tmux sockets, nvim sockets)
    - string interpolation for startup commands
    - database queries (safe via parameterization)

    Raises:
        ValueError: If validation fails with descriptive message.
    """
    if not name:
        raise ValueError("Session name cannot be empty")

    if len(name) > 100:
        raise ValueError("Session name too long (max 100 characters)")

    # Allow: alphanumeric, dash, underscore, slash, dot
    # Block: shell metacharacters, control chars, null bytes
    if not re.match(r"^[a-zA-Z0-9_/.-]+$", name):
        raise ValueError(
            "Session name must contain only: letters, numbers, dash, underscore, slash, dot"
        )

    # Block reserved names
    if name in (".", ".."):
        raise ValueError(f"Reserved name: {name}")


def _sanitize_tmux_name(name: str) -> str:
    """Sanitize a name for use in a tmux session name.

    Tmux does not allow '.' or ':' in session names.
    """
    return name.replace(".", "-").replace(":", "-").replace("/", "-")


def tmux_session_prefix() -> str:
    """Return configured tmux session prefix string."""
    cfg = load_config()
    return (cfg.tmux.session_prefix or "").strip()


def build_tmux_session_name(name: str) -> str:
    """Build a tmux session name from configured prefix + sanitized name."""
    sanitized_name = _sanitize_tmux_name(name)
    prefix = tmux_session_prefix()
    if not prefix:
        return sanitized_name
    if prefix.endswith("_"):
        return f"{prefix}{sanitized_name}"
    return f"{prefix}_{sanitized_name}"


def is_shoal_tmux_session_name(name: str | None) -> bool:
    """Check whether a tmux session name matches the configured Shoal prefix."""
    if not name:
        return False
    prefix = tmux_session_prefix()
    if not prefix:
        return True
    if prefix.endswith("_"):
        return name.startswith(prefix)
    return name.startswith(f"{prefix}_")
