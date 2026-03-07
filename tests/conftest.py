"""Shared fixtures with isolated temp directories for testing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    """Create a temporary config directory with tool configs."""
    config = tmp_path / "config" / "shoal"
    config.mkdir(parents=True)

    # Main config
    (config / "config.toml").write_text(
        """
[general]
default_tool = "opencode"

[tmux]
session_prefix = "_"

[notifications]
enabled = false

[robo]
default_tool = "opencode"
session_prefix = "__"
"""
    )

    # Tool configs
    tools = config / "tools"
    tools.mkdir()

    (tools / "claude.toml").write_text(
        """
[tool]
name = "claude"
command = "claude"
icon = "🤖"
status_provider = "regex"

[detection]
busy_patterns = ["⠋", "thinking"]
waiting_patterns = ["❯", "Yes/No", "Allow"]
error_patterns = ["Error:", "ERROR"]
idle_patterns = ["$"]

[mcp]
config_cmd = "claude mcp add"
"""
    )

    (tools / "opencode.toml").write_text(
        """
[tool]
name = "opencode"
command = "opencode"
icon = "🌐"
status_provider = "opencode_compat"

[detection]
busy_patterns = ["working", "thinking"]
waiting_patterns = ["│ >", "permission"]
error_patterns = ["error", "Error"]
idle_patterns = ["│ >"]
"""
    )

    (tools / "codex.toml").write_text(
        """
[tool]
name = "codex"
command = "codex"
icon = "⚙️"
status_provider = "regex"

[detection]
busy_patterns = ["thinking", "analyzing", "running"]
waiting_patterns = ["approve", "allow", "yes/no"]
error_patterns = ["Error:", "error:", "failed"]
idle_patterns = ["❯", "$"]

[mcp]
config_cmd = ""
config_file = ""
socket_env = ""
"""
    )

    (tools / "pi.toml").write_text(
        """
[tool]
name = "pi"
command = "pi"
icon = "🥧"
status_provider = "pi"

[detection]
busy_patterns = ["thinking", "generating", "executing", "reading", "writing", "editing"]
waiting_patterns = ["permission", "confirm", "approve", "y/n"]
error_patterns = ["Error:", "error:", "ERROR", "FAILED"]

[mcp]
config_cmd = ""
config_file = ""
socket_env = ""
"""
    )

    # Robo profile
    robo = config / "robo"
    robo.mkdir()
    (robo / "default.toml").write_text(
        """
[robo]
name = "default"
tool = "opencode"
auto_approve = false

[monitoring]
poll_interval = 10
waiting_timeout = 300

[escalation]
notify = true
auto_respond = false

[tasks]
log_file = "task-log.md"
"""
    )

    return config


@pytest.fixture
def tmp_state(tmp_path: Path) -> Path:
    """Create a temporary state directory."""
    state = tmp_path / "state" / "shoal"
    for subdir in ("sessions", "mcp-pool/pids", "mcp-pool/sockets", "robo", "remote"):
        (state / subdir).mkdir(parents=True)
    return state


@pytest.fixture
def tmp_runtime(tmp_path: Path) -> Path:
    """Create a temporary runtime directory."""
    runtime = tmp_path / "runtime" / "shoal"
    for subdir in ("logs",):
        (runtime / subdir).mkdir(parents=True)
    return runtime


@pytest.fixture
def mock_dirs(tmp_config: Path, tmp_state: Path, tmp_runtime: Path):
    """Patch config_dir(), data_dir(), and state_dir() to use temp directories."""
    from shoal.core.config import load_config
    from shoal.core.db import ShoalDB

    load_config.cache_clear()

    # Reset DB singleton before test
    import asyncio

    asyncio.run(ShoalDB.reset_instance())

    config_patch = patch("shoal.core.config.config_dir", return_value=tmp_config)
    data_dir_patch = patch("shoal.core.config.data_dir", return_value=tmp_state)
    state_dir_patch = patch("shoal.core.config.state_dir", return_value=tmp_runtime)

    with (
        config_patch,
        data_dir_patch,
        state_dir_patch,
        # Patch imported references in all modules that import these
        patch("shoal.cli.session_create.config_dir", return_value=tmp_config),
        patch("shoal.cli.mcp.data_dir", return_value=tmp_state),
        patch("shoal.cli.robo.config_dir", return_value=tmp_config),
        patch("shoal.cli.robo.data_dir", return_value=tmp_state),
        patch("shoal.cli.robo.state_dir", return_value=tmp_runtime),
        patch("shoal.cli.watcher.state_dir", return_value=tmp_runtime),
        patch("shoal.services.mcp_pool.data_dir", return_value=tmp_state),
        patch("shoal.services.mcp_proxy.data_dir", return_value=tmp_state),
    ):
        yield tmp_config, tmp_state
        load_config.cache_clear()
        # Reset DB singleton after test
        asyncio.run(ShoalDB.reset_instance())


@pytest.fixture
async def async_client(mock_dirs):
    """Async test client for the Shoal API."""
    from shoal.api.server import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
