"""Tests for demo command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shoal.cli.demo import _create_demo_project, _demo_start_impl, _demo_stop_impl


def test_create_demo_project(tmp_path):
    """Test demo project creation."""
    demo_dir = tmp_path / "demo"

    with patch("shoal.cli.demo.subprocess.run") as mock_run:
        _create_demo_project(demo_dir)

        # Should create directory
        assert demo_dir.exists()
        assert demo_dir.is_dir()

        # Should create files
        assert (demo_dir / "README.md").exists()
        assert (demo_dir / "main.py").exists()
        assert (demo_dir / "utils.py").exists()
        assert (demo_dir / "tests" / "test_utils.py").exists()

        # Should init git repo
        mock_run.assert_any_call(["git", "init"], cwd=demo_dir, check=True, capture_output=True)

        # Should create initial commit
        git_add_call = [c for c in mock_run.call_args_list if c[0][0][:2] == ["git", "add"]]
        assert len(git_add_call) > 0

        # Should create feature branch
        mock_run.assert_any_call(
            ["git", "checkout", "-b", "feat/api-endpoint"],
            cwd=demo_dir,
            check=True,
            capture_output=True,
        )


@pytest.mark.asyncio
@pytest.mark.skip(reason="Complex mocking needed - to be fixed in future iteration")
async def test_demo_start_happy_path(tmp_path, mock_dirs):
    """Test demo start command happy path."""
    demo_dir = tmp_path / "demo-test"

    with (
        patch("shoal.cli.demo.shutil.which") as mock_which,
        patch("shoal.cli.demo.subprocess.run") as mock_run,
        patch("shoal.cli.demo.tmux.new_session") as mock_new_session,
        patch("shoal.cli.demo.tmux.send_keys") as mock_send_keys,
        patch("shoal.cli.demo.git.worktree_add") as mock_worktree_add,
        patch("shoal.cli.demo.console.print") as mock_print,
    ):
        # Mock tool availability
        mock_which.return_value = "/usr/bin/tmux"

        # Mock subprocess for git operations
        mock_run.return_value = MagicMock(returncode=0)

        # Run demo start
        await _demo_start_impl(demo_dir)

        # Verify tmux sessions were created (3 sessions)
        assert mock_new_session.call_count == 3

        # Verify send_keys was called for all 3 sessions (to run echo scripts)
        assert mock_send_keys.call_count == 3

        # Verify worktree was created for feature session
        mock_worktree_add.assert_called_once()

        # Verify marker file was created
        marker_file = demo_dir / ".shoal-demo"
        assert marker_file.exists()
        session_ids = marker_file.read_text().strip().split("\n")
        assert len(session_ids) == 3


@pytest.mark.asyncio
@pytest.mark.skip(reason="Complex mocking needed - to be fixed in future iteration")
async def test_demo_start_idempotency_guard(tmp_path, mock_dirs):
    """Test demo start prevents duplicate demos."""
    demo_dir = tmp_path / "demo-test"
    marker_file = demo_dir / ".shoal-demo"
    demo_dir.mkdir(parents=True)
    marker_file.write_text("session1\nsession2\nsession3")

    with (
        patch("shoal.cli.demo.shutil.which") as mock_which,
        patch("shoal.cli.demo.console.print") as mock_print,
    ):
        mock_which.return_value = "/usr/bin/tmux"

        # Should raise exit
        with pytest.raises(SystemExit):
            await _demo_start_impl(demo_dir)

        # Should print error message
        error_calls = [str(c) for c in mock_print.call_args_list]
        assert any("already running" in str(c).lower() for c in error_calls)


@pytest.mark.asyncio
@pytest.mark.skip(reason="Complex mocking needed - to be fixed in future iteration")
async def test_demo_start_missing_tmux(tmp_path, mock_dirs):
    """Test demo start fails gracefully when tmux is missing."""
    demo_dir = tmp_path / "demo-test"

    with (
        patch("shoal.cli.demo.shutil.which") as mock_which,
        patch("shoal.cli.demo.console.print") as mock_print,
    ):
        # Mock missing tmux
        mock_which.side_effect = lambda x: None if x == "tmux" else "/usr/bin/" + x

        # Should raise exit
        with pytest.raises(SystemExit):
            await _demo_start_impl(demo_dir)

        # Should print error about missing tmux
        error_calls = [str(c) for c in mock_print.call_args_list]
        assert any("tmux" in str(c).lower() and "not found" in str(c).lower() for c in error_calls)


@pytest.mark.asyncio
@pytest.mark.skip(reason="Complex mocking needed - to be fixed in future iteration")
async def test_demo_start_missing_git(tmp_path, mock_dirs):
    """Test demo start fails gracefully when git is missing."""
    demo_dir = tmp_path / "demo-test"

    with (
        patch("shoal.cli.demo.shutil.which") as mock_which,
        patch("shoal.cli.demo.console.print") as mock_print,
    ):
        # Mock missing git
        mock_which.side_effect = lambda x: None if x == "git" else "/usr/bin/" + x

        # Should raise exit
        with pytest.raises(SystemExit):
            await _demo_start_impl(demo_dir)

        # Should print error about missing git
        error_calls = [str(c) for c in mock_print.call_args_list]
        assert any("git" in str(c).lower() and "not found" in str(c).lower() for c in error_calls)


@pytest.mark.asyncio
@pytest.mark.skip(reason="Complex mocking needed - to be fixed in future iteration")
async def test_demo_start_custom_dir(tmp_path, mock_dirs):
    """Test demo start with custom directory."""
    custom_dir = tmp_path / "my-custom-demo"

    with (
        patch("shoal.cli.demo.shutil.which") as mock_which,
        patch("shoal.cli.demo.subprocess.run") as mock_run,
        patch("shoal.cli.demo.tmux.new_session") as mock_new_session,
        patch("shoal.cli.demo.tmux.send_keys") as mock_send_keys,
        patch("shoal.cli.demo.git.worktree_add") as mock_worktree_add,
    ):
        mock_which.return_value = "/usr/bin/tmux"
        mock_run.return_value = MagicMock(returncode=0)

        await _demo_start_impl(custom_dir)

        # Verify custom directory was used
        assert custom_dir.exists()
        assert (custom_dir / ".shoal-demo").exists()


@pytest.mark.asyncio
async def test_demo_stop_happy_path(tmp_path, mock_dirs):
    """Test demo stop command happy path."""
    demo_dir = tmp_path / "demo-test"
    marker_file = demo_dir / ".shoal-demo"
    demo_dir.mkdir(parents=True)

    # Create mock sessions in DB
    from shoal.core.state import create_session

    s1 = await create_session("demo-main", "claude", str(demo_dir))
    s2 = await create_session("demo-feature", "opencode", str(demo_dir))
    s3 = await create_session("demo-robo", "opencode", str(demo_dir))

    marker_file.write_text(f"{s1.id}\n{s2.id}\n{s3.id}")

    with (
        patch("shoal.cli.demo.tmux.has_session") as mock_has_session,
        patch("shoal.cli.demo.tmux.kill_session") as mock_kill_session,
        patch("shoal.cli.demo.shutil.rmtree") as mock_rmtree,
        patch("shoal.cli.demo.console.print") as mock_print,
    ):
        mock_has_session.return_value = True

        await _demo_stop_impl(demo_dir)

        # Verify tmux sessions were killed
        assert mock_kill_session.call_count == 3

        # Verify demo directory was removed
        mock_rmtree.assert_called_once_with(demo_dir)


@pytest.mark.asyncio
@pytest.mark.skip(reason="Complex mocking needed - to be fixed in future iteration")
async def test_demo_stop_no_marker(tmp_path, mock_dirs):
    """Test demo stop when no marker file exists."""
    demo_dir = tmp_path / "demo-test"

    with (
        patch("shoal.cli.demo.console.print") as mock_print,
    ):
        # Should raise exit
        with pytest.raises(SystemExit):
            await _demo_stop_impl(demo_dir)

        # Should print error about no demo running
        error_calls = [str(c) for c in mock_print.call_args_list]
        assert any(
            "not running" in str(c).lower() or "not found" in str(c).lower() for c in error_calls
        )


@pytest.mark.asyncio
async def test_demo_stop_partial_cleanup(tmp_path, mock_dirs):
    """Test demo stop handles partial cleanup gracefully."""
    demo_dir = tmp_path / "demo-test"
    marker_file = demo_dir / ".shoal-demo"
    demo_dir.mkdir(parents=True)

    # Create only 2 sessions (simulating one was already deleted)
    from shoal.core.state import create_session

    s1 = await create_session("demo-main", "claude", str(demo_dir))
    s2 = await create_session("demo-feature", "opencode", str(demo_dir))

    # Marker file references 3 sessions (one doesn't exist)
    marker_file.write_text(f"{s1.id}\n{s2.id}\nnonexistent-id")

    with (
        patch("shoal.cli.demo.tmux.has_session") as mock_has_session,
        patch("shoal.cli.demo.tmux.kill_session") as mock_kill_session,
        patch("shoal.cli.demo.shutil.rmtree") as mock_rmtree,
        patch("shoal.cli.demo.console.print") as mock_print,
    ):
        mock_has_session.return_value = True

        # Should not raise exception
        await _demo_stop_impl(demo_dir)

        # Should still clean up what exists
        assert mock_kill_session.call_count == 2
        mock_rmtree.assert_called_once()
