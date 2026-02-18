"""Tests for tmux startup commands configuration."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from typer.testing import CliRunner
from shoal.cli import app
from shoal.models.config import ShoalConfig

runner = CliRunner()


@pytest.fixture
def mock_git_repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    return repo_dir


def test_add_session_executes_startup_commands(mock_dirs, mock_git_repo):
    config_dir, _ = mock_dirs

    # Create a dummy tool config
    tools_dir = config_dir / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    (tools_dir / "claude.toml").write_text('[tool]\nname="claude"\ncommand="claude-cmd"\nicon="C"')

    # Custom tmux config with startup commands
    custom_config = ShoalConfig()
    custom_config.tmux.startup_commands = [
        "send-keys -t {tmux_session} 'echo {session_name}' Enter",
        "new-window -t {tmux_session} -n test '{tool_command}'",
    ]

    with (
        patch("shoal.cli.session.load_config", return_value=custom_config),
        patch("shoal.core.git.is_git_repo", return_value=True),
        patch("shoal.core.git.git_root", return_value=str(mock_git_repo)),
        patch("shoal.core.git.current_branch", return_value="main"),
        patch("shoal.core.tmux.new_session") as mock_new_session,
        patch("shoal.core.tmux.set_environment") as mock_set_env,
        patch("shoal.core.tmux.run_command") as mock_run_command,
        patch("shoal.core.tmux.pane_pid", return_value=123),
    ):
        result = runner.invoke(
            app,
            ["new", str(mock_git_repo), "--name", "test-session", "--tool", "claude"],
        )

        assert result.exit_code == 0

        # Verify tmux.new_session was called
        mock_new_session.assert_called_once()

        # Verify startup commands were run with correct interpolation
        expected_tmux_session = "_test-session"

        assert mock_run_command.call_count == 2

        # Check first command
        call1 = mock_run_command.call_args_list[0]
        assert f"send-keys -t {expected_tmux_session} 'echo test-session' Enter" == call1[0][0]

        # Check second command
        call2 = mock_run_command.call_args_list[1]
        assert f"new-window -t {expected_tmux_session} -n test 'claude-cmd'" == call2[0][0]


def test_fork_session_executes_startup_commands(mock_dirs, mock_git_repo):
    config_dir, _ = mock_dirs

    # Create a dummy tool config
    tools_dir = config_dir / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    (tools_dir / "claude.toml").write_text('[tool]\nname="claude"\ncommand="claude-cmd"\nicon="C"')

    # Create a source session in DB
    from shoal.core.state import create_session
    import asyncio

    source_session = asyncio.run(create_session("source", "claude", str(mock_git_repo)))

    # Custom tmux config
    custom_config = ShoalConfig()
    custom_config.tmux.startup_commands = [
        "send-keys -t {tmux_session} 'forked {session_name}' Enter"
    ]

    with (
        patch("shoal.cli.session.load_config", return_value=custom_config),
        patch(
            "shoal.cli.session._resolve_session_interactive_impl",
            new=AsyncMock(return_value=source_session.id),
        ),
        patch("shoal.core.tmux.new_session") as mock_new_session,
        patch("shoal.core.tmux.set_environment") as mock_set_env,
        patch("shoal.core.tmux.run_command") as mock_run_command,
        patch("shoal.core.tmux.pane_pid", return_value=123),
    ):
        result = runner.invoke(app, ["fork", "source", "--name", "forked-session", "--no-worktree"])

        assert result.exit_code == 0

        # Verify startup commands
        expected_tmux_session = "_forked-session"
        mock_run_command.assert_called_once_with(
            f"send-keys -t {expected_tmux_session} 'forked forked-session' Enter"
        )
