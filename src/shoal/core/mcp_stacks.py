"""MCP server stacks: config-defined and template-derived."""

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

logger = logging.getLogger("shoal.mcp_stacks")


class McpStack(BaseModel):
    """A named stack of MCP servers."""

    name: str
    description: str = ""
    servers: list[str] = Field(default_factory=list)
    source: Literal["config", "template"]


def load_mcp_stacks() -> dict[str, McpStack]:
    """Load MCP stacks from config file and available templates.

    Config-defined stacks take precedence over template-derived stacks
    when names conflict.

    Returns:
        Dict of stack name to McpStack, sorted by name.

    Raises:
        ConfigLoadError: If mcp-stacks.toml exists but is malformed.
    """
    stacks: dict[str, McpStack] = {}

    # Template-derived stacks (lower priority, loaded first).
    for tpl_name in available_templates():
        try:
            tpl = resolve_template(tpl_name)
        except Exception:
            logger.warning("Skipping broken template: %s", tpl_name)
            continue
        if tpl.mcp:
            stacks[tpl_name] = McpStack(
                name=tpl_name,
                description=f"From template: {tpl_name}",
                servers=list(tpl.mcp),
                source="template",
            )

    # Config-defined stacks (higher priority, overwrite template entries).
    config_path = config_dir() / "mcp-stacks.toml"
    if config_path.exists():
        try:
            raw = config_path.read_text(encoding="utf-8")
            data = tomllib.loads(raw)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigLoadError(config_path, f"Malformed TOML: {exc}") from exc

        for name, section in data.get("stacks", {}).items():
            if not isinstance(section, dict):
                raise ConfigLoadError(
                    config_path,
                    f"stacks.{name} must be a table",
                )
            stacks[name] = McpStack(
                name=name,
                description=section.get("description", ""),
                servers=section.get("servers", []),
                source="config",
            )

    return dict(sorted(stacks.items()))


def available_mcp_servers() -> list[str]:
    """Return sorted list of all registered MCP server names."""
    return sorted(load_mcp_registry())
