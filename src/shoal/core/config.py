"""Configuration loading and XDG path helpers."""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

from shoal.models.config import (
    ConductorProfileConfig,
    DetectionPatterns,
    MCPToolConfig,
    ShoalConfig,
    ToolConfig,
)


def config_dir() -> Path:
    """Return ~/.config/shoal."""
    return Path.home() / ".config" / "shoal"


def state_dir() -> Path:
    """Return ~/.local/share/shoal."""
    return Path.home() / ".local" / "share" / "shoal"


def ensure_dirs() -> None:
    """Create all required state directories."""
    base = state_dir()
    for subdir in ("sessions", "mcp-pool/pids", "mcp-pool/sockets", "conductor", "logs"):
        (base / subdir).mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def load_config() -> ShoalConfig:
    """Load and cache the main config.toml."""
    path = config_dir() / "config.toml"
    if not path.exists():
        return ShoalConfig()
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return ShoalConfig.model_validate(data)


def load_tool_config(name: str) -> ToolConfig:
    """Load a tool config, flattening [tool] + [detection] + [mcp] sections."""
    path = config_dir() / "tools" / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"No tool config: {path}")
    with open(path, "rb") as f:
        data = tomllib.load(f)

    tool_section = data.get("tool", {})
    detection_section = data.get("detection", {})
    mcp_section = data.get("mcp", {})

    return ToolConfig(
        name=tool_section.get("name", name),
        command=tool_section.get("command", name),
        icon=tool_section.get("icon", "●"),
        detection=DetectionPatterns.model_validate(detection_section),
        mcp=MCPToolConfig.model_validate(mcp_section),
    )


def load_conductor_profile(name: str) -> ConductorProfileConfig:
    """Load a conductor profile TOML."""
    path = config_dir() / "conductor" / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"No conductor profile: {path}")
    with open(path, "rb") as f:
        data = tomllib.load(f)

    conductor_section = data.get("conductor", {})
    return ConductorProfileConfig(
        name=conductor_section.get("name", name),
        tool=conductor_section.get("tool", "opencode"),
        auto_approve=conductor_section.get("auto_approve", False),
        monitoring=data.get("monitoring", {}),
        escalation=data.get("escalation", {}),
        tasks=data.get("tasks", {}),
    )


def available_tools() -> list[str]:
    """List available tool names from config/tools/*.toml."""
    tools_dir = config_dir() / "tools"
    if not tools_dir.exists():
        return []
    return sorted(p.stem for p in tools_dir.glob("*.toml"))
