"""Tests for demo command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shoal.cli.demo import create_demo_project
from shoal.cli.demo.start_stop import _demo_start_impl, _demo_stop_impl
from shoal.cli.demo.tour import _demo_tour_impl


def test_create_demo_project(tmp_path):
    """Test demo project creation."""
    demo_dir = tmp_path / "demo"

    with patch("shoal.cli.demo.subprocess.run") as mock_run:
        create_demo_project(demo_dir)

        # Should create directory
        assert demo_dir.exists()
        assert demo_dir.is_dir()

        # Should create files
        assert (demo_dir / "README.md").exists()
        assert (demo_dir / "pyproject.toml").exists()
        assert (demo_dir / "main.py").exists()
        assert (demo_dir / "utils.py").exists()
        assert (demo_dir / "api.py").exists()
        assert (demo_dir / "tests" / "test_utils.py").exists()

        # Should init git repo
        mock_run.assert_any_call(["git", "init"], cwd=demo_dir, check=True, capture_output=True)

        # Should create initial commit
        git_add_call = [c for c in mock_run.call_args_list if c[0][0][:2] == ["git", "add"]]
        assert len(git_add_call) > 0


def test_create_demo_project_content(tmp_path):
    """Test demo project file contents are well-formed."""
    demo_dir = tmp_path / "demo"

    with patch("shoal.cli.demo.subprocess.run"):
        create_demo_project(demo_dir)

    # pyproject.toml has valid content
    pyproject = (demo_dir / "pyproject.toml").read_text()
    assert "shoal-demo" in pyproject
    assert "requires-python" in pyproject

    # api.py has valid content
    api_content = (demo_dir / "api.py").read_text()
    assert "FastAPI" in api_content
    assert "health" in api_content

    # utils.py has both functions
    utils_content = (demo_dir / "utils.py").read_text()
    assert "def greet" in utils_content
    assert "def add" in utils_content

    # test file tests both functions
    test_content = (demo_dir / "tests" / "test_utils.py").read_text()
    assert "test_greet" in test_content
    assert "test_add" in test_content


@pytest.mark.asyncio
async def test_demo_start_happy_path(tmp_path, mock_dirs):
    """Test demo start command happy path."""
    demo_dir = tmp_path / "demo-test"

    def mock_wt_add(root, path, **kwargs):
        Path(path).mkdir(parents=True, exist_ok=True)

    with (
        patch("shoal.cli.demo.start_stop.shutil.which") as mock_which,
        patch("shoal.cli.demo.subprocess.run") as mock_run,
        patch("shoal.cli.demo.start_stop.tmux.has_session", return_value=False),
        patch("shoal.cli.demo.start_stop.tmux.new_session") as mock_new_session,
        patch("shoal.cli.demo.start_stop.tmux.run_command") as mock_run_command,
        patch("shoal.cli.demo.start_stop.tmux.send_keys") as mock_send_keys,
        patch(
            "shoal.cli.demo.start_stop.git.worktree_add", side_effect=mock_wt_add
        ) as mock_worktree_add,
        patch("shoal.cli.demo.start_stop.git.current_branch", return_value="main"),
        patch("shoal.cli.demo.start_stop.console.print"),
        patch("shoal.cli.demo.start_stop.demo_dir", return_value=demo_dir),
    ):
        # Mock tool availability
        mock_which.return_value = "/usr/bin/tmux"

        # Mock subprocess for git operations
        mock_run.return_value = MagicMock(returncode=0)

        # Run demo start
        await _demo_start_impl(None)

        # Verify tmux sessions were created (4 sessions)
        assert mock_new_session.call_count == 4

        # Demo sessions should use stable names (no global prefix)
        created_names = {call.args[0] for call in mock_new_session.call_args_list}
        assert created_names == {"demo-main", "demo-feature", "demo-bugfix", "demo-robo"}

        # Each session has 2 panes: tool + info script
        assert mock_send_keys.call_count == 8

        # Verify pane split commands were issued
        split_commands = [call.args[0] for call in mock_run_command.call_args_list]
        assert sum("split-window" in cmd for cmd in split_commands) == 4

        # Verify worktrees were created (feature + bugfix)
        assert mock_worktree_add.call_count == 2

        # Verify marker file was created
        marker_file = demo_dir / ".shoal-demo"
        assert marker_file.exists()
        session_ids = marker_file.read_text().strip().split("\n")
        assert len(session_ids) == 4


@pytest.mark.asyncio
async def test_demo_start_varied_statuses(tmp_path, mock_dirs):
    """Test demo start sets varied statuses on sessions."""
    demo_dir = tmp_path / "demo-test"

    def mock_wt_add(root, path, **kwargs):
        Path(path).mkdir(parents=True, exist_ok=True)

    with (
        patch("shoal.cli.demo.start_stop.shutil.which", return_value="/usr/bin/tmux"),
        patch("shoal.cli.demo.subprocess.run", return_value=MagicMock(returncode=0)),
        patch("shoal.cli.demo.start_stop.tmux.has_session", return_value=False),
        patch("shoal.cli.demo.start_stop.tmux.new_session"),
        patch("shoal.cli.demo.start_stop.tmux.run_command"),
        patch("shoal.cli.demo.start_stop.tmux.send_keys"),
        patch("shoal.cli.demo.start_stop.git.worktree_add", side_effect=mock_wt_add),
        patch("shoal.cli.demo.start_stop.git.current_branch", return_value="main"),
        patch("shoal.cli.demo.start_stop.demo_dir", return_value=demo_dir),
    ):
        await _demo_start_impl(None)

    # Read session IDs and verify their statuses
    from shoal.core.state import get_session

    marker_file = demo_dir / ".shoal-demo"
    session_ids = marker_file.read_text().strip().split("\n")

    s1 = await get_session(session_ids[0])
    s2 = await get_session(session_ids[1])
    s3 = await get_session(session_ids[2])
    s4 = await get_session(session_ids[3])

    assert s1.status.value == "running"  # demo-main
    assert s2.status.value == "idle"  # demo-feature
    assert s3.status.value == "waiting"  # demo-bugfix
    assert s4.status.value == "running"  # demo-robo


@pytest.mark.asyncio
async def test_demo_start_custom_dir(tmp_path, mock_dirs):
    """Test demo start with custom directory."""
    custom_dir = tmp_path / "my custom demo"

    def mock_wt_add(root, path, **kwargs):
        Path(path).mkdir(parents=True, exist_ok=True)

    with (
        patch("shoal.cli.demo.start_stop.shutil.which") as mock_which,
        patch("shoal.cli.demo.subprocess.run") as mock_run,
        patch("shoal.cli.demo.start_stop.tmux.has_session", return_value=False),
        patch("shoal.cli.demo.start_stop.tmux.new_session") as mock_new_session,
        patch("shoal.cli.demo.start_stop.tmux.run_command") as mock_run_command,
        patch("shoal.cli.demo.start_stop.tmux.send_keys") as mock_send_keys,
        patch("shoal.cli.demo.start_stop.git.worktree_add", side_effect=mock_wt_add),
        patch("shoal.cli.demo.start_stop.git.current_branch", return_value="main"),
    ):
        mock_which.return_value = "/usr/bin/tmux"
        mock_run.return_value = MagicMock(returncode=0)

        await _demo_start_impl(str(custom_dir))

        # Verify custom directory was used
        assert custom_dir.exists()
        assert (custom_dir / ".shoal-demo").exists()

        # Verify pane render commands are sent through Typer/Rich command path
        actual_commands = [call.args[1] for call in mock_send_keys.call_args_list]
        pane_commands = [cmd for cmd in actual_commands if "shoal demo pane" in cmd]
        assert len(pane_commands) == 4
        assert any("--session-name demo-main" in cmd for cmd in pane_commands)
        assert any("--session-name demo-feature" in cmd for cmd in pane_commands)
        assert any("--session-name demo-bugfix" in cmd for cmd in pane_commands)
        assert any("--session-name demo-robo" in cmd for cmd in pane_commands)
        assert any("--worktree-note" in cmd for cmd in pane_commands)
        assert any("--robo" in cmd for cmd in pane_commands)
        # Verify feature flags
        assert any("--feature sessions" in cmd for cmd in pane_commands)
        assert any("--feature worktrees" in cmd for cmd in pane_commands)
        assert any("--feature detection" in cmd for cmd in pane_commands)
        assert mock_new_session.call_count == 4
        assert mock_run_command.call_count >= 4


@pytest.mark.asyncio
async def test_demo_start_marker_exists(tmp_path, mock_dirs):
    """Test demo start exits when marker file exists."""
    demo_dir = tmp_path / "demo-test"
    demo_dir.mkdir(parents=True)
    (demo_dir / ".shoal-demo").write_text("existing")

    with (
        patch("shoal.cli.demo.start_stop.shutil.which", return_value="/usr/bin/tmux"),
        patch("shoal.cli.demo.start_stop.console.print") as mock_print,
        patch("shoal.cli.demo.start_stop.demo_dir", return_value=demo_dir),
        patch("shoal.cli.demo.start_stop.create_demo_project") as mock_create,
    ):
        from typer import Exit

        with pytest.raises(Exit) as exc:
            await _demo_start_impl(None)

        assert exc.value.exit_code == 1
        mock_create.assert_not_called()
        error_calls = [str(c) for c in mock_print.call_args_list]
        assert any("demo already running" in str(c).lower() for c in error_calls)


@pytest.mark.asyncio
async def test_demo_start_missing_tmux(tmp_path, mock_dirs):
    """Test demo start fails when tmux is missing."""
    demo_dir = tmp_path / "demo-test"

    with (
        patch("shoal.cli.demo.start_stop.shutil.which", return_value=None),
        patch("shoal.cli.demo.start_stop.console.print") as mock_print,
        patch("shoal.cli.demo.start_stop.demo_dir", return_value=demo_dir),
        patch("shoal.cli.demo.start_stop.create_demo_project") as mock_create,
    ):
        from typer import Exit

        with pytest.raises(Exit) as exc:
            await _demo_start_impl(None)

        assert exc.value.exit_code == 1
        mock_create.assert_not_called()
        error_calls = [str(c) for c in mock_print.call_args_list]
        assert any("tmux not found" in str(c).lower() for c in error_calls)


@pytest.mark.asyncio
async def test_demo_start_missing_git(tmp_path, mock_dirs):
    """Test demo start fails when git is missing."""
    demo_dir = tmp_path / "demo-test"

    with (
        patch("shoal.cli.demo.start_stop.shutil.which", side_effect=["/usr/bin/tmux", None]),
        patch("shoal.cli.demo.start_stop.console.print") as mock_print,
        patch("shoal.cli.demo.start_stop.demo_dir", return_value=demo_dir),
        patch("shoal.cli.demo.start_stop.create_demo_project") as mock_create,
    ):
        from typer import Exit

        with pytest.raises(Exit) as exc:
            await _demo_start_impl(None)

        assert exc.value.exit_code == 1
        mock_create.assert_not_called()
        error_calls = [str(c) for c in mock_print.call_args_list]
        assert any("git not found" in str(c).lower() for c in error_calls)


@pytest.mark.asyncio
async def test_demo_stop_no_marker(tmp_path, mock_dirs):
    """Test demo stop when no marker file exists."""
    demo_dir = tmp_path / "demo-test"

    with (
        patch("shoal.cli.demo.start_stop.console.print") as mock_print,
        patch("shoal.cli.demo.start_stop.demo_dir", return_value=demo_dir),
    ):
        # Should raise exit
        from typer import Exit

        with pytest.raises(Exit) as exc:
            await _demo_stop_impl(None)

        assert exc.value.exit_code == 0

        # Should print error about no demo running
        error_calls = [str(c) for c in mock_print.call_args_list]
        assert any(
            "no demo found" in str(c).lower() or "nothing to clean up" in str(c).lower()
            for c in error_calls
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
        patch("shoal.cli.demo.start_stop.tmux.has_session") as mock_has_session,
        patch("shoal.cli.demo.start_stop.tmux.kill_session") as mock_kill_session,
        patch("shoal.cli.demo.start_stop.shutil.rmtree") as mock_rmtree,
        patch("shoal.cli.demo.start_stop.console.print"),
    ):
        mock_has_session.return_value = True

        # Should not raise exception
        await _demo_stop_impl(demo_dir)

        # Should still clean up what exists
        assert mock_kill_session.call_count == 2
        mock_rmtree.assert_called_once()


@pytest.mark.asyncio
async def test_demo_stop_without_tmux_sessions(tmp_path, mock_dirs):
    """Test demo stop still deletes sessions when tmux sessions are missing."""
    demo_dir = tmp_path / "demo-test"
    marker_file = demo_dir / ".shoal-demo"
    demo_dir.mkdir(parents=True)

    from shoal.core.state import create_session, get_session

    s1 = await create_session("demo-main", "claude", str(demo_dir))
    s2 = await create_session("demo-feature", "opencode", str(demo_dir))

    marker_file.write_text(f"{s1.id}\n{s2.id}")

    with (
        patch("shoal.cli.demo.start_stop.tmux.has_session", return_value=False),
        patch("shoal.cli.demo.start_stop.tmux.kill_session") as mock_kill_session,
        patch("shoal.cli.demo.start_stop.shutil.rmtree") as mock_rmtree,
    ):
        await _demo_stop_impl(demo_dir)

        assert mock_kill_session.call_count == 0
        mock_rmtree.assert_called_once()

        assert await get_session(s1.id) is None
        assert await get_session(s2.id) is None


# ============================================================================
# Demo tour tests
# ============================================================================


@pytest.mark.asyncio
async def test_demo_tour_all_pass(mock_dirs):
    """Test demo tour runs and all feature checks pass."""
    with patch("shoal.cli.demo.tour.console.print") as mock_print:
        await _demo_tour_impl()

    all_output = " ".join(str(c) for c in mock_print.call_args_list)
    # All 7 pass when fastmcp is installed; 6 pass + 1 skipped otherwise
    assert (
        "All 7 feature areas passed" in all_output
        or "6 feature areas passed, 1 skipped" in all_output
    )


@pytest.mark.asyncio
async def test_demo_tour_step_detection(mock_dirs):
    """Test tour's detection step exercises real detect_status()."""
    from shoal.cli.demo.tour import step_status_detection

    result = await step_status_detection()
    assert result.passed
    assert result.label == "Status Detection"


@pytest.mark.asyncio
async def test_demo_tour_step_journals(mock_dirs):
    """Test tour's journal step creates, reads, and cleans up."""
    from shoal.cli.demo.tour import step_journals

    result = await step_journals()
    assert result.passed
    assert result.label == "Journals"


@pytest.mark.asyncio
async def test_demo_tour_step_templates(mock_dirs):
    """Test tour's template step verifies inheritance and mixins."""
    from shoal.cli.demo.tour import step_templates_and_inheritance

    result = await step_templates_and_inheritance()
    assert result.passed
    assert result.label == "Templates & Inheritance"


@pytest.mark.asyncio
async def test_demo_tour_with_sessions(mock_dirs):
    """Test tour displays session data when sessions exist."""
    from shoal.core.state import create_session

    with patch("shoal.cli.demo.start_stop.tmux.has_session", return_value=False):
        await create_session("test-session", "claude", "/tmp/test")

    with patch("shoal.cli.demo.tour.console.print") as mock_print:
        await _demo_tour_impl()

    all_output = " ".join(str(c) for c in mock_print.call_args_list)
    assert (
        "All 7 feature areas passed" in all_output
        or "6 feature areas passed, 1 skipped" in all_output
    )
    # Verify session count is shown (1 session + tour-journal-test briefly)
    assert "1 sessions" in all_output


@pytest.mark.asyncio
async def test_demo_tour_no_failures(mock_dirs):
    """Test that no tour checks produce failures."""
    with patch("shoal.cli.demo.tour.console.print") as mock_print:
        await _demo_tour_impl()

    all_output = " ".join(str(c) for c in mock_print.call_args_list)
    assert (
        "All 7 feature areas passed" in all_output
        or "6 feature areas passed, 1 skipped" in all_output
    )
    # Should not contain failure indicators
    assert "failed" not in all_output.lower() or "0 failed" in all_output.lower()
