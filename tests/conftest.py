"""Shared fixtures with isolated temp directories for testing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    """Create a temporary config directory with tool configs."""
    config = tmp_path / "config" / "shoal"
    config.mkdir(parents=True)

    # Main config
    (config / "config.toml").write_text(
        """
[general]
default_tool = "claude"

[tmux]
session_prefix = "shoal"

[notifications]
enabled = false

[conductor]
default_tool = "opencode"
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

[detection]
busy_patterns = ["working", "thinking"]
waiting_patterns = ["│ >", "permission"]
error_patterns = ["error", "Error"]
idle_patterns = ["│ >"]
"""
    )

    # Conductor profile
    conductor = config / "conductor"
    conductor.mkdir()
    (conductor / "default.toml").write_text(
        """
[conductor]
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
    for subdir in ("sessions", "mcp-pool/pids", "mcp-pool/sockets", "conductor"):
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
    """Patch config_dir(), state_dir(), and runtime_dir() to use temp directories."""
    from shoal.core.config import load_config

    load_config.cache_clear()

    config_patch = patch("shoal.core.config.config_dir", return_value=tmp_config)
    state_dir_patch = patch("shoal.core.config.state_dir", return_value=tmp_state)
    runtime_dir_patch = patch("shoal.core.config.runtime_dir", return_value=tmp_runtime)

    with (
        config_patch,
        state_dir_patch,
        runtime_dir_patch,
        # Patch imported references in all modules that import these
        patch("shoal.core.state.state_dir", return_value=tmp_state),
        patch("shoal.core.state.ensure_dirs"),
        patch("shoal.cli.session.config_dir", return_value=tmp_config),
        patch("shoal.cli.session.ensure_dirs"),
        patch("shoal.cli.mcp.ensure_dirs"),
        patch("shoal.cli.mcp.state_dir", return_value=tmp_state),
        patch("shoal.cli.worktree.ensure_dirs"),
        patch("shoal.cli.conductor.config_dir", return_value=tmp_config),
        patch("shoal.cli.conductor.state_dir", return_value=tmp_state),
        patch("shoal.cli.conductor.ensure_dirs"),
        patch("shoal.cli.watcher.runtime_dir", return_value=tmp_runtime),
        patch("shoal.cli.watcher.ensure_dirs"),
        patch("shoal.cli.nvim.ensure_dirs"),
        patch("shoal.services.status_bar.state_dir", return_value=tmp_state),
    ):
        yield tmp_config, tmp_state
        load_config.cache_clear()
