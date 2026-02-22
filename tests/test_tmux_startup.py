"""Tests for tmux startup commands configuration."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
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
        patch("shoal.core.tmux.set_environment"),
        patch("shoal.core.tmux.set_pane_title"),
        patch("shoal.core.tmux.preferred_pane", return_value="_test-session"),
        patch("shoal.core.tmux.run_command") as mock_run_command,
        patch("shoal.core.tmux.pane_pid", return_value=123),
        patch("shoal.core.tmux.pane_coordinates", return_value=None),
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
        patch("shoal.core.tmux.new_session"),
        patch("shoal.core.tmux.set_environment"),
        patch("shoal.core.tmux.set_pane_title"),
        patch("shoal.core.tmux.preferred_pane", return_value="_forked-session"),
        patch("shoal.core.tmux.run_command") as mock_run_command,
        patch("shoal.core.tmux.pane_pid", return_value=123),
        patch("shoal.core.tmux.pane_coordinates", return_value=None),
    ):
        result = runner.invoke(app, ["fork", "source", "--name", "forked-session", "--no-worktree"])

        assert result.exit_code == 0

        # Verify startup commands
        expected_tmux_session = "_forked-session"
        mock_run_command.assert_called_once_with(
            f"send-keys -t {expected_tmux_session} 'forked forked-session' Enter"
        )


def test_add_session_uses_template_layout(mock_dirs, mock_git_repo):
    config_dir, _ = mock_dirs

    templates_dir = config_dir / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    (templates_dir / "feature-dev.toml").write_text(
        """
[template]
name = "feature-dev"
tool = "opencode"

[[windows]]
name = "dev"
focus = true

[[windows.panes]]
split = "root"
title = "primary"
command = "{tool_command}"

[[windows.panes]]
split = "right"
size = "40%"
title = "tests"
command = "pytest -q"
"""
    )

    custom_config = ShoalConfig()
    custom_config.tmux.startup_commands = ["display-message 'fallback-startup'"]

    with (
        patch("shoal.cli.session.load_config", return_value=custom_config),
        patch("shoal.core.git.is_git_repo", return_value=True),
        patch("shoal.core.git.git_root", return_value=str(mock_git_repo)),
        patch("shoal.core.git.current_branch", return_value="main"),
        patch("shoal.core.tmux.new_session") as mock_new_session,
        patch("shoal.core.tmux.set_environment"),
        patch("shoal.core.tmux.run_command") as mock_run_command,
        patch("shoal.core.tmux.send_keys") as mock_send_keys,
        patch("shoal.core.tmux.set_pane_title") as mock_set_pane_title,
        patch("shoal.core.tmux.preferred_pane", return_value="_templ-session"),
        patch("shoal.core.tmux.pane_pid", return_value=123),
        patch("shoal.core.tmux.pane_coordinates", return_value=None),
    ):
        result = runner.invoke(
            app,
            ["new", str(mock_git_repo), "--name", "templ-session", "--template", "feature-dev"],
        )

        assert result.exit_code == 0
        mock_new_session.assert_called_once()

        run_commands = [call[0][0] for call in mock_run_command.call_args_list]
        assert any(cmd.startswith("rename-window -t _templ-session:0") for cmd in run_commands)
        assert any(
            cmd.startswith("split-window -t _templ-session:0 -h -p 40") for cmd in run_commands
        )
        assert all("fallback-startup" not in cmd for cmd in run_commands)

        send_calls = [call.args for call in mock_send_keys.call_args_list]
        assert ("_templ-session:0.0", "opencode") in send_calls
        assert ("_templ-session:0.1", "pytest -q") in send_calls

        title_calls = [call.args for call in mock_set_pane_title.call_args_list]
        assert ("_templ-session:0.0", "primary") in title_calls
        assert ("_templ-session:0.1", "tests") in title_calls


def test_add_session_dry_run_has_no_side_effects(mock_dirs, mock_git_repo):
    custom_config = ShoalConfig()
    custom_config.tmux.startup_commands = [
        "send-keys -t {tmux_session} '{tool_command}' Enter",
    ]

    with (
        patch("shoal.cli.session.load_config", return_value=custom_config),
        patch("shoal.core.git.is_git_repo", return_value=True),
        patch("shoal.core.git.git_root", return_value=str(mock_git_repo)),
        patch("shoal.core.git.current_branch", return_value="main"),
        patch("shoal.core.git.worktree_add") as mock_worktree_add,
        patch("shoal.core.tmux.new_session") as mock_new_session,
    ):
        result = runner.invoke(
            app,
            [
                "new",
                str(mock_git_repo),
                "--name",
                "dry-run-session",
                "--worktree",
                "feat/dry-run",
                "--branch",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Dry run: no changes applied" in result.output
        assert "Planned tmux actions" in result.output
        mock_worktree_add.assert_not_called()
        mock_new_session.assert_not_called()


def test_add_session_invalid_branch_category_rejected(mock_dirs, mock_git_repo):
    custom_config = ShoalConfig()

    with (
        patch("shoal.cli.session.load_config", return_value=custom_config),
        patch("shoal.core.git.is_git_repo", return_value=True),
        patch("shoal.core.git.git_root", return_value=str(mock_git_repo)),
        patch("shoal.core.git.current_branch", return_value="main"),
        patch("shoal.core.git.worktree_add") as mock_worktree_add,
        patch("shoal.core.tmux.new_session") as mock_new_session,
    ):
        result = runner.invoke(
            app,
            [
                "new",
                str(mock_git_repo),
                "--name",
                "invalid-branch-session",
                "--worktree",
                "feature/not-allowed",
                "--branch",
            ],
        )

        assert result.exit_code == 1
        assert "category/slug" in result.output
        mock_worktree_add.assert_not_called()
        mock_new_session.assert_not_called()
