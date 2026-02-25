"""Tests for demo tutorial command."""

from unittest.mock import patch

import pytest

from shoal.cli.demo.tutorial import (
    TutorialContext,
    _cleanup,
    _demo_tutorial_impl,
    _step_check_status,
    _step_create_session,
    _step_write_journal,
)


@pytest.mark.asyncio
async def test_tutorial_missing_tmux(mock_dirs):
    """Test tutorial exits when tmux is missing."""
    from typer import Exit

    with (
        patch("shoal.cli.demo.tutorial.shutil.which", return_value=None),
        patch("shoal.cli.demo.tutorial.console.print"),
    ):
        with pytest.raises(Exit) as exc:
            await _demo_tutorial_impl()

        assert exc.value.exit_code == 1


@pytest.mark.asyncio
async def test_tutorial_stale_marker(tmp_path, mock_dirs):
    """Test tutorial exits when stale marker exists."""
    from typer import Exit

    with (
        patch("shoal.cli.demo.tutorial.shutil.which", return_value="/usr/bin/tmux"),
        patch("shoal.cli.demo.tutorial.tutorial_dir", return_value=tmp_path),
        patch("shoal.cli.demo.tutorial.console.print"),
    ):
        # Create stale marker
        (tmp_path / ".shoal-tutorial").write_text("")

        with pytest.raises(Exit) as exc:
            await _demo_tutorial_impl()

        assert exc.value.exit_code == 1


@pytest.mark.asyncio
async def test_step_create_session(tmp_path, mock_dirs):
    """Test step 1 creates a session in the DB."""
    from shoal.core.state import get_session

    ctx = TutorialContext(tutorial_path=tmp_path, step=1)

    with patch("shoal.cli.demo.tutorial.git.current_branch", return_value="main"):
        await _step_create_session(ctx)

    assert len(ctx.session_ids) == 1
    assert ctx.session_names == ["tutorial-main"]

    s = await get_session(ctx.session_ids[0])
    assert s is not None
    assert s.name == "tutorial-main"
    assert s.tool == "claude"


@pytest.mark.asyncio
async def test_step_check_status(tmp_path, mock_dirs):
    """Test step 2 lists sessions without error."""
    from shoal.core.state import create_session

    s = await create_session("tutorial-main", "claude", str(tmp_path))
    ctx = TutorialContext(tutorial_path=tmp_path, session_ids=[s.id], step=2)

    with patch("shoal.cli.demo.tutorial.console.print"):
        await _step_check_status(ctx)


@pytest.mark.asyncio
async def test_step_write_journal(tmp_path, mock_dirs):
    """Test step 4 writes and reads a journal entry."""
    from shoal.core.journal import read_journal
    from shoal.core.state import create_session

    s = await create_session("tutorial-main", "claude", str(tmp_path))
    ctx = TutorialContext(
        tutorial_path=tmp_path,
        session_ids=[s.id],
        session_names=["tutorial-main"],
        step=4,
    )

    with patch("shoal.cli.demo.tutorial.console.print"):
        await _step_write_journal(ctx)

    entries = read_journal(s.id)
    assert len(entries) == 1
    assert "Tutorial journal entry" in entries[0].content
    assert entries[0].source == "tutorial"


@pytest.mark.asyncio
async def test_cleanup_idempotent(tmp_path, mock_dirs):
    """Test cleanup works when no resources exist."""
    with patch("shoal.cli.demo.tutorial.console.print"):
        await _cleanup(tmp_path)


@pytest.mark.asyncio
async def test_cleanup_kills_sessions(tmp_path, mock_dirs):
    """Test cleanup removes tutorial sessions from DB."""
    from shoal.core.state import create_session, get_session

    s = await create_session("tutorial-main", "claude", str(tmp_path))
    marker = tmp_path / ".shoal-tutorial"
    marker.write_text(s.id)

    with (
        patch("shoal.cli.demo.tutorial.tmux.has_session", return_value=False),
        patch("shoal.cli.demo.tutorial.console.print"),
    ):
        await _cleanup(tmp_path)

    assert await get_session(s.id) is None
    assert not tmp_path.exists()
