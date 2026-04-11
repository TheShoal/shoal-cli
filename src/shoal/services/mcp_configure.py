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

    # Check if this server uses HTTP transport
    from shoal.core.config import load_mcp_registry_full
    from shoal.services.mcp_pool import get_transport, read_port

    transport = get_transport(mcp_name)
    if transport == "http":
        # Prefer the registry URL (e.g. from hermes config) over port-derived fallback
        registry = load_mcp_registry_full()
        reg_entry = registry.get(mcp_name, {})
        registry_url = reg_entry.get("url", "")
        if registry_url:
            return _configure_http_for_tool_url(tool, mcp_name, work_dir, registry_url, mcp_cfg)
        port = read_port(mcp_name) or 8390
        return _configure_http_for_tool(tool, mcp_name, work_dir, port, mcp_cfg)

    # Strategy 1: Run a config command (e.g. "claude mcp add")
    if mcp_cfg.config_cmd:
        return _configure_via_command(mcp_cfg.config_cmd, mcp_name, work_dir)

    # Strategy 2: Merge into a config file (e.g. ".opencode.json")
    if mcp_cfg.config_file:
        return _configure_via_file(mcp_cfg.config_file, mcp_name, work_dir)

    # No auto-config method available
    return None


def _configure_http_for_tool_url(
    tool: str,
    mcp_name: str,
    work_dir: str,
    url: str,
    mcp_cfg: Any,
) -> str | None:
    """Configure a tool to use an HTTP-mode MCP server with an explicit URL."""
    if mcp_cfg.config_file:
        path = Path(work_dir) / mcp_cfg.config_file
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _read_config_file(path)

        mcp_servers = data.setdefault("mcpServers", {})
        mcp_servers[mcp_name] = {"url": url}

        _write_config_file(path, data)
        return f"Configured HTTP URL in {path}"

    return f"HTTP server at {url}"

def _configure_http_for_tool(
    tool: str,
    mcp_name: str,
    work_dir: str,
    port: int,
    mcp_cfg: Any,
) -> str | None:
    """Configure a tool to use an HTTP-mode MCP server."""
    url = f"http://localhost:{port}/mcp/"

    if mcp_cfg.config_file:
        path = Path(work_dir) / mcp_cfg.config_file
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _read_config_file(path)

        mcp_servers = data.setdefault("mcpServers", {})
        mcp_servers[mcp_name] = {"url": url}

        _write_config_file(path, data)
        return f"Configured HTTP URL in {path}"

    # No file config — just report the URL
    return f"HTTP server at {url}"


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


def _is_yaml_config(path: Path) -> bool:
    """Return True if the config file uses YAML format."""
    return path.suffix.lower() in {".yml", ".yaml"}


def _read_config_file(path: Path) -> dict[str, Any]:
    """Read a config file, auto-detecting JSON or YAML format."""
    if not path.exists():
        return {}

    content = path.read_text()
    if not content.strip():
        return {}

    if _is_yaml_config(path):
        try:
            import yaml
        except ImportError:
            raise McpConfigureError("PyYAML not installed, cannot read YAML config") from None
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise McpConfigureError(f"Failed to parse YAML config {path}: {exc}") from exc
    else:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise McpConfigureError(f"Failed to parse JSON config {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise McpConfigureError(f"Config file {path} is not an object")
    return data


def _write_config_file(path: Path, data: dict[str, Any]) -> None:
    """Write a config file, auto-detecting JSON or YAML format."""
    if _is_yaml_config(path):
        try:
            import yaml
        except ImportError:
            raise McpConfigureError("PyYAML not installed, cannot write YAML config") from None
        content = yaml.dump(data, default_flow_style=False, sort_keys=False)
    else:
        content = json.dumps(data, indent=2) + "\n"
    try:
        path.write_text(content)
    except OSError as exc:
        raise McpConfigureError(f"Failed to write config file {path}: {exc}") from exc


def _configure_via_file(config_file: str, mcp_name: str, work_dir: str) -> str:
    """Merge an MCP entry into a tool's config file (JSON or YAML)."""
    path = Path(work_dir) / config_file
    path.parent.mkdir(parents=True, exist_ok=True)

    data = _read_config_file(path)

    # Ensure mcpServers section exists and add our entry
    mcp_servers = data.setdefault("mcpServers", {})
    mcp_servers[mcp_name] = {
        "command": "shoal-mcp-proxy",
        "args": [mcp_name],
    }

    _write_config_file(path, data)
    return f"Configured via file: {path}"



# ---------------------------------------------------------------------------
# OMP (oh-my-pi) configuration
# ---------------------------------------------------------------------------

OMP_CONFIG_PATH = Path.home() / ".omp" / "agent" / "config.yml"


def configure_omp_mcp(mcp_name: str) -> str | None:
    """Add an MCP server to OMP's mcpServers configuration.

    Reads the OMP config, determines the server transport (HTTP or stdio),
    and adds the appropriate configuration entry.

    Returns:
        A human-readable summary of what was configured, or ``None`` if OMP
        config doesn't exist.

    Raises:
        McpConfigureError: if configuration was attempted but failed.
    """
    if not OMP_CONFIG_PATH.exists():
        logger.debug("OMP config not found at %s", OMP_CONFIG_PATH)
        return None

    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML not installed, cannot configure OMP")
        return None

    # Load existing config
    try:
        data = yaml.safe_load(OMP_CONFIG_PATH.read_text())
    except (yaml.YAMLError, OSError) as exc:
        raise McpConfigureError(f"Failed to parse OMP config: {exc}") from exc

    if not isinstance(data, dict):
        data = {}

    # Determine server configuration
    from shoal.core.config import load_mcp_registry_full
    from shoal.services.mcp_pool import get_transport, read_port

    transport = get_transport(mcp_name)
    mcp_servers = data.setdefault("mcpServers", {})

    if transport == "http":
        # Prefer the registry URL (e.g. from hermes config) over port-derived fallback
        registry = load_mcp_registry_full()
        reg_url = registry.get(mcp_name, {}).get("url", "")
        url = reg_url or f"http://127.0.0.1:{read_port(mcp_name) or 8390}/mcp"
        mcp_servers[mcp_name] = {
            "type": "http",
            "url": url,
        }
    else:
        # stdio transport via proxy
        mcp_servers[mcp_name] = {
            "type": "stdio",
            "command": "shoal-mcp-proxy",
            "args": [mcp_name],
        }

    # Write back
    try:
        OMP_CONFIG_PATH.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    except OSError as exc:
        raise McpConfigureError(f"Failed to write OMP config: {exc}") from exc

    return f"Configured {mcp_name} in OMP ({transport})"


def remove_omp_mcp(mcp_name: str) -> str | None:
    """Remove an MCP server from OMP's mcpServers configuration.

    Returns:
        A human-readable summary if the server was removed, ``None`` if not found.

    Raises:
        McpConfigureError: if configuration was attempted but failed.
    """
    if not OMP_CONFIG_PATH.exists():
        return None

    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML not installed, cannot configure OMP")
        return None

    # Load existing config
    try:
        data = yaml.safe_load(OMP_CONFIG_PATH.read_text())
    except (yaml.YAMLError, OSError) as exc:
        raise McpConfigureError(f"Failed to parse OMP config: {exc}") from exc

    if not isinstance(data, dict):
        return None

    mcp_servers = data.get("mcpServers", {})
    if mcp_name not in mcp_servers:
        return None

    del mcp_servers[mcp_name]

    # Clean up empty mcpServers section
    if not mcp_servers:
        data.pop("mcpServers", None)

    # Write back
    try:
        OMP_CONFIG_PATH.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    except OSError as exc:
        raise McpConfigureError(f"Failed to write OMP config: {exc}") from exc

    return f"Removed {mcp_name} from OMP config"