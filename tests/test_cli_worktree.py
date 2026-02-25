"""Tests for cli/worktree.py."""

import asyncio
from unittest.mock import patch

from typer.testing import CliRunner

from shoal.cli.worktree import app
from shoal.core.db import with_db
from shoal.core.state import create_session, update_session

runner = CliRunner()


def test_wt_finish_no_worktree(mock_dirs):
    """Test wt finish on a session with no worktree."""

    async def setup():
        await create_session("no-wt", "claude", "/tmp")

    asyncio.run(with_db(setup()))

    result = runner.invoke(app, ["finish", "no-wt"])
    assert result.exit_code == 1
    assert "has no worktree to finish" in result.stdout


def test_wt_finish_success(mock_dirs):
    """Test wt finish success path (merge)."""

    async def setup():
        s = await create_session(
            "wt-fin", "claude", "/tmp/repo", worktree="/tmp/repo/.worktrees/wt"
        )
        await update_session(s.id, branch="feat/test")

    asyncio.run(with_db(setup()))

    with (
        patch("shoal.core.tmux.has_session", return_value=True),
        patch("shoal.core.tmux.kill_session") as mock_kill,
        patch("shoal.core.git.main_branch", return_value="main"),
        patch("shoal.core.git.checkout"),
        patch("shoal.core.git.merge", return_value=True) as mock_merge,
        patch("shoal.core.git.worktree_remove", return_value=True) as mock_wt_remove,
        patch("shoal.core.git.branch_delete", return_value=True),
        patch("pathlib.Path.is_dir", return_value=True),
    ):
        result = runner.invoke(app, ["finish", "wt-fin"])
        assert result.exit_code == 0
        assert "Merged successfully" in result.stdout
        assert "Removed worktree" in result.stdout
        mock_kill.assert_called_once()
        mock_merge.assert_called_once()
        mock_wt_remove.assert_called_once()


def test_wt_cleanup_no_orphans(mock_dirs):
    """Test wt cleanup with no orphans."""
    result = runner.invoke(app, ["cleanup"])
    assert result.exit_code == 0
    assert "No orphaned worktrees found" in result.stdout


def test_wt_cleanup_with_orphans(mock_dirs, tmp_path):
    """Test wt cleanup finds orphans."""
    repo_path = tmp_path / "repo"
    wt_base = repo_path / ".worktrees"
    wt_base.mkdir(parents=True)
    orphan_wt = wt_base / "orphan"
    orphan_wt.mkdir()

    async def setup():
        # Create a session so we have a repo path to check
        await create_session("s1", "claude", str(repo_path))

    asyncio.run(with_db(setup()))

    with (
        patch("shoal.core.tmux.has_session", return_value=True),
        patch("typer.confirm", return_value=True),
        patch("shoal.core.git.worktree_remove", return_value=True) as mock_remove,
        patch("shoal.core.git.git_root", return_value=str(repo_path)),
    ):
        result = runner.invoke(app, ["cleanup"])
        assert result.exit_code == 0
        assert "Orphaned worktrees" in result.stdout
        assert "orphan" in result.stdout
        mock_remove.assert_called_once()
