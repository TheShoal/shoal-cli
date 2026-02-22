"""Auto-configure MCP servers for AI coding tools.

Handles the tool-specific configuration step so that after attaching an
MCP server to a session, the tool can actually use it without manual
setup.
"""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class McpConfigureError(Exception):
    """Raised when auto-configuration fails."""


def configure_mcp_for_tool(
    tool: str,
    mcp_name: str,
    work_dir: str,
) -> str | None:
    """Auto-configure a tool to use an MCP server.

    Looks up the tool's MCP configuration method (``config_cmd`` or
    ``config_file``) and applies it.

    Returns:
        A human-readable summary of what was configured, or ``None`` if
        no auto-config method is available for this tool.

    Raises:
        McpConfigureError: if configuration was attempted but failed.
    """
    from shoal.core.config import load_tool_config

    try:
        tool_cfg = load_tool_config(tool)
    except FileNotFoundError:
        return None

    mcp_cfg = tool_cfg.mcp

    # Strategy 1: Run a config command (e.g. "claude mcp add")
    if mcp_cfg.config_cmd:
        return _configure_via_command(mcp_cfg.config_cmd, mcp_name, work_dir)

    # Strategy 2: Merge into a config file (e.g. ".opencode.json")
    if mcp_cfg.config_file:
        return _configure_via_file(mcp_cfg.config_file, mcp_name, work_dir)

    # No auto-config method available
    return None


def _configure_via_command(config_cmd: str, mcp_name: str, work_dir: str) -> str:
    """Run a tool's config command to register the MCP proxy."""
    cmd = [*shlex.split(config_cmd), mcp_name, "--", "shoal-mcp-proxy", mcp_name]
    cmd_display = " ".join(cmd)
    try:
        subprocess.run(
            cmd,
            shell=False,
            check=True,
            capture_output=True,
            text=True,
            cwd=work_dir,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise McpConfigureError(f"Config command not found: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise McpConfigureError(
            f"Config command failed (exit {exc.returncode}): {cmd_display}\n{exc.stderr}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise McpConfigureError(f"Config command timed out: {cmd_display}") from exc

    return f"Configured via command: {cmd_display}"


def _configure_via_file(config_file: str, mcp_name: str, work_dir: str) -> str:
    """Merge an MCP entry into a tool's JSON config file."""
    path = Path(work_dir) / config_file
    data: dict[str, Any] = {}

    if path.exists():
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            raise McpConfigureError(f"Failed to parse existing config file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise McpConfigureError(f"Config file {path} is not a JSON object")

    # Ensure mcpServers section exists and add our entry
    mcp_servers = data.setdefault("mcpServers", {})
    mcp_servers[mcp_name] = {
        "command": "shoal-mcp-proxy",
        "args": [mcp_name],
    }

    try:
        path.write_text(json.dumps(data, indent=2) + "\n")
    except OSError as exc:
        raise McpConfigureError(f"Failed to write config file {path}: {exc}") from exc

    return f"Configured via file: {path}"
