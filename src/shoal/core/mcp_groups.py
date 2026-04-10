"""MCP server grouping: config-defined and template-derived."""

from __future__ import annotations

import logging
import tomllib
from typing import Literal

from pydantic import BaseModel, Field

from shoal.core.config import (
    ConfigLoadError,
    available_templates,
    config_dir,
    load_mcp_registry,
    resolve_template,
)

logger = logging.getLogger("shoal.mcp_groups")


class McpGroup(BaseModel):
    """A named group of MCP servers."""

    name: str
    description: str = ""
    servers: list[str] = Field(default_factory=list)
    source: Literal["config", "template"]


def load_mcp_groups() -> dict[str, McpGroup]:
    """Load MCP groups from config file and available templates.

    Config-defined groups take precedence over template-derived groups
    when names conflict.

    Returns:
        Dict of group name to McpGroup, sorted by name.

    Raises:
        ConfigLoadError: If mcp-groups.toml exists but is malformed.
    """
    groups: dict[str, McpGroup] = {}

    # Template-derived groups (lower priority, loaded first).
    for tpl_name in available_templates():
        try:
            tpl = resolve_template(tpl_name)
        except Exception:
            logger.warning("Skipping broken template: %s", tpl_name)
            continue
        if tpl.mcp:
            groups[tpl_name] = McpGroup(
                name=tpl_name,
                description=f"From template: {tpl_name}",
                servers=list(tpl.mcp),
                source="template",
            )

    # Config-defined groups (higher priority, overwrite template entries).
    config_path = config_dir() / "mcp-groups.toml"
    if config_path.exists():
        try:
            raw = config_path.read_text(encoding="utf-8")
            data = tomllib.loads(raw)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigLoadError(config_path, f"Malformed TOML: {exc}") from exc

        for name, section in data.get("groups", {}).items():
            if not isinstance(section, dict):
                raise ConfigLoadError(
                    config_path,
                    f"groups.{name} must be a table",
                )
            groups[name] = McpGroup(
                name=name,
                description=section.get("description", ""),
                servers=section.get("servers", []),
                source="config",
            )

    return dict(sorted(groups.items()))


def available_mcp_servers() -> list[str]:
    """Return sorted list of all registered MCP server names."""
    return sorted(load_mcp_registry())
