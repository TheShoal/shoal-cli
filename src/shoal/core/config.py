"""Configuration loading and XDG path helpers."""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

from shoal.models.config import (
    DetectionPatterns,
    MCPToolConfig,
    RoboProfileConfig,
    SessionTemplateConfig,
    ShoalConfig,
    TemplateWorktreeConfig,
    ToolConfig,
)


def config_dir() -> Path:
    """Return ~/.config/shoal."""
    return Path.home() / ".config" / "shoal"


def state_dir() -> Path:
    """Return ~/.local/share/shoal (persistent data: sessions, robo state)."""
    return Path.home() / ".local" / "share" / "shoal"


def runtime_dir() -> Path:
    """Return ~/.local/state/shoal (transient runtime: PIDs, logs)."""
    return Path.home() / ".local" / "state" / "shoal"


def ensure_dirs() -> None:
    """Create all required state and runtime directories."""
    cfg = config_dir()
    for subdir in ("templates",):
        (cfg / subdir).mkdir(parents=True, exist_ok=True)

    base = state_dir()
    for subdir in ("sessions", "mcp-pool/pids", "mcp-pool/sockets", "robo"):
        (base / subdir).mkdir(parents=True, exist_ok=True)
    rt = runtime_dir()
    for subdir in ("logs",):
        (rt / subdir).mkdir(parents=True, exist_ok=True)


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


def load_robo_profile(name: str) -> RoboProfileConfig:
    """Load a robo profile TOML."""
    path = config_dir() / "robo" / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"No robo profile: {name}")
    with open(path, "rb") as f:
        data = tomllib.load(f)

    robo_section = data.get("robo", {})
    return RoboProfileConfig(
        name=robo_section.get("name", name),
        tool=robo_section.get("tool", "opencode"),
        auto_approve=robo_section.get("auto_approve", False),
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


def templates_dir() -> Path:
    """Return ~/.config/shoal/templates."""
    return config_dir() / "templates"


def available_templates() -> list[str]:
    """List available template names from config/templates/*.toml."""
    dir_path = templates_dir()
    if not dir_path.exists():
        return []
    return sorted(p.stem for p in dir_path.glob("*.toml"))


def load_mcp_registry() -> dict[str, str]:
    """Load MCP server registry: user file merged over built-in defaults.

    Reads ``~/.config/shoal/mcp-servers.toml``.  Each top-level key is a
    server name whose value is a table with a ``command`` key.  Built-in
    defaults are used as a fallback for servers not overridden by the user.

    Returns:
        Mapping of server name → command string.
    """
    from shoal.services.mcp_pool import _DEFAULT_SERVERS

    registry: dict[str, str] = dict(_DEFAULT_SERVERS)

    user_file = config_dir() / "mcp-servers.toml"
    if user_file.exists():
        with open(user_file, "rb") as f:
            data = tomllib.load(f)
        for name, entry in data.items():
            if isinstance(entry, dict) and "command" in entry:
                registry[name] = entry["command"]

    return registry


def load_template(name: str) -> SessionTemplateConfig:
    """Load a session template TOML.

    Expected shape:
      [template]
      name, description, tool
      [template.worktree]
      name, create_branch
      [template.env]
      ...
      [[windows]]
      [[windows.panes]]
    """
    path = templates_dir() / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"No template config: {path}")

    with open(path, "rb") as f:
        data = tomllib.load(f)

    template_section = data.get("template", {})
    worktree_section = template_section.get("worktree", {})
    env_section = template_section.get("env", {})
    mcp_section = template_section.get("mcp", [])
    windows_section = data.get("windows", [])

    return SessionTemplateConfig(
        name=template_section.get("name", name),
        description=template_section.get("description", ""),
        tool=template_section.get("tool", "opencode"),
        worktree=TemplateWorktreeConfig.model_validate(worktree_section),
        env=env_section,
        mcp=mcp_section,
        windows=windows_section,
    )
