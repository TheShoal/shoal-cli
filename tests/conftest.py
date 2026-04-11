"""Shared fixtures with isolated temp directories for testing."""

from __future__ import annotations

import logging
import sqlite3
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
input_mode = "arg"

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
input_mode = "flag"
prompt_flag = "--prompt"

[detection]
busy_patterns = ["working", "thinking"]
waiting_patterns = ["│ >", "permission"]
error_patterns = ["error", "Error"]
idle_patterns = ["│ >"]
"""
    )

    (tools / "omp.toml").write_text(
        """
[tool]
name = "omp"
command = "omp"
icon = "🥧"
status_provider = "pi"
input_mode = "arg"
prompt_file_prefix = "@"

[detection]
busy_patterns = ["thinking", "generating", "executing"]
waiting_patterns = ["permission", "confirm", "approve", "y/n"]
error_patterns = ["Error:", "error:", "ERROR", "FAILED"]

[mcp]
config_cmd = ""
config_file = ".omp/config.yml"
socket_env = ""
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
def mock_dirs(tmp_config: Path, tmp_state: Path, tmp_runtime: Path) -> tuple[Path, Path]:
    """Patch config_dir(), data_dir(), and state_dir() to use temp directories.

    Also patches ``shoal.core.journal.data_dir`` directly since that module
    imports ``data_dir`` at module top-level (not via the ``config`` submodule
    reference), so the patch on ``shoal.core.config.data_dir`` alone does not
    redirect journal writes.
    """
    import asyncio

    from shoal.core.config import load_config
    from shoal.core.db import ShoalDB

    load_config.cache_clear()
    asyncio.run(ShoalDB.reset_instance())

    config_patch = patch("shoal.core.config.config_dir", return_value=tmp_config)
    data_dir_patch = patch("shoal.core.config.data_dir", return_value=tmp_state)
    state_dir_patch = patch("shoal.core.config.state_dir", return_value=tmp_runtime)
    # journal.py binds data_dir at module top-level; patch it directly
    journal_data_dir_patch = patch("shoal.core.journal.data_dir", return_value=tmp_state)

    with (
        config_patch,
        data_dir_patch,
        state_dir_patch,
        journal_data_dir_patch,
        # Patch imported references in all modules that import these
        patch("shoal.cli.session_create.config_dir", return_value=tmp_config),
        patch("shoal.cli.mcp.data_dir", return_value=tmp_state),
        patch("shoal.cli.robo.config_dir", return_value=tmp_config),
        patch("shoal.cli.robo.data_dir", return_value=tmp_state),
        patch("shoal.cli.robo.state_dir", return_value=tmp_runtime),
        patch("shoal.cli.watcher.state_dir", return_value=tmp_runtime),
        patch("shoal.services.mcp_pool.data_dir", return_value=tmp_state),
        patch("shoal.services.mcp_proxy.data_dir", return_value=tmp_state),
        patch("shoal.core.journal.data_dir", return_value=tmp_state),
        # project_templates_dir() calls git.git_root(".") which resolves to the real
        # repo root and leaks .shoal/templates/ into tests that expect a clean slate.
        patch("shoal.core.config.project_templates_dir", return_value=None),
    ):
        yield tmp_config, tmp_state
        load_config.cache_clear()
        asyncio.run(ShoalDB.reset_instance())

        # Safety net: purge any test-named sessions that escaped into the real DB.
        # Guards against tests that bypass mock_dirs via the MCP orchestrator.
        _cleanup_logger = logging.getLogger(__name__)
        try:
            import shoal.core.config as _cfg

            real_db = _cfg.data_dir() / "shoal.db"
            conn = sqlite3.connect(real_db)
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM sessions WHERE json_extract(data, '$.name') LIKE 'test%'",
            )
            conn.commit()
            conn.close()
        except Exception:  # pragma: no cover
            _cleanup_logger.debug("Could not clean up test sessions from DB")


@pytest.fixture
async def async_client(mock_dirs: tuple[Path, Path]) -> AsyncClient:
    """Async test client for the Shoal API."""
    from shoal.api.server import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


try:
    import fastmcp  # noqa: F401

    _HAS_FASTMCP = True
except ImportError:
    _HAS_FASTMCP = False
