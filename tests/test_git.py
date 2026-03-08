"""Tests for core.git module."""

from unittest.mock import MagicMock, patch

import pytest

from shoal.core import git


def test_is_git_repo_true(tmp_path):
    """Test is_git_repo returns True for git repository."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    with patch("shoal.core.git.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = git.is_git_repo(str(repo_path))

        assert result is True
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )


def test_is_git_repo_false(tmp_path):
    """Test is_git_repo returns False for non-git directory."""
    non_repo = tmp_path / "not-a-repo"
    non_repo.mkdir()

    with patch("shoal.core.git.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=128)

        result = git.is_git_repo(str(non_repo))

        assert result is False


def test_git_root(tmp_path):
    """Test git_root returns repository root."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    with patch("shoal.core.git.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=str(repo_path) + "\n",
        )

        result = git.git_root(str(repo_path))

        assert result == str(repo_path)
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )


def test_main_branch_main(tmp_path):
    """Test main_branch detects 'main' branch."""
    with patch("shoal.core.git.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="refs/remotes/origin/main\n",
        )

        result = git.main_branch(str(tmp_path))

        assert result == "main"
        mock_run.assert_called_once_with(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )


def test_main_branch_master(tmp_path):
    """Test main_branch falls back to 'main' when symbolic-ref fails."""
    with patch("shoal.core.git.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")

        result = git.main_branch(str(tmp_path))

        assert result == "main"


def test_worktree_add(tmp_path):
    """Test worktree_add creates a new worktree."""
    repo = tmp_path / "repo"
    worktree = tmp_path / "worktree"
    repo.mkdir()

    with patch("shoal.core.git.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = git.worktree_add(str(repo), str(worktree), branch="feature")
        assert result is None

        mock_run.assert_called_once_with(
            ["git", "worktree", "add", str(worktree), "-b", "feature"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )


def test_worktree_add_no_branch(tmp_path):
    """Test worktree_add without creating a new branch."""
    repo = tmp_path / "repo"
    worktree = tmp_path / "worktree"
    repo.mkdir()

    with patch("shoal.core.git.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = git.worktree_add(str(repo), str(worktree))
        assert result is None

        mock_run.assert_called_once_with(
            ["git", "worktree", "add", str(worktree)],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )


def test_worktree_remove(tmp_path):
    """Test worktree_remove deletes a worktree."""
    repo = tmp_path / "repo"
    worktree = tmp_path / "worktree"
    repo.mkdir()
    worktree.mkdir()

    with patch("shoal.core.git.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = git.worktree_remove(str(repo), str(worktree))

        assert result is True
        mock_run.assert_called_once_with(
            ["git", "worktree", "remove", str(worktree)],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )


def test_checkout(tmp_path):
    """Test checkout switches branches."""
    repo = tmp_path / "repo"
    repo.mkdir()

    with patch("shoal.core.git.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = git.checkout(str(repo), "feature-branch")

        assert result is True
        mock_run.assert_called_once_with(
            ["git", "checkout", "feature-branch"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )


def test_merge(tmp_path):
    """Test merge merges a branch."""
    repo = tmp_path / "repo"
    repo.mkdir()

    with patch("shoal.core.git.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = git.merge(str(repo), "feature-branch")

        assert result is True
        mock_run.assert_called_once_with(
            ["git", "merge", "feature-branch"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )


def test_push(tmp_path):
    """Test push pushes to remote."""
    repo = tmp_path / "repo"
    repo.mkdir()

    with patch("shoal.core.git.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = git.push(str(repo), "main")

        assert result is True
        mock_run.assert_called_once_with(
            ["git", "push", "origin", "main"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )


def test_branch_delete(tmp_path):
    """Test branch_delete removes a branch."""
    repo = tmp_path / "repo"
    repo.mkdir()

    with patch("shoal.core.git.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = git.branch_delete(str(repo), "old-feature", force=True)

        assert result is True
        mock_run.assert_called_once_with(
            ["git", "branch", "-D", "old-feature"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )


def test_stage_all(tmp_path):
    """stage_all runs git add -A in the given path."""
    repo = tmp_path / "repo"
    repo.mkdir()

    with patch("shoal.core.git.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        git.stage_all(str(repo))

        mock_run.assert_called_once_with(
            ["git", "add", "-A"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )


def test_commit(tmp_path):
    """commit runs git commit -m <message> in the given path."""
    repo = tmp_path / "repo"
    repo.mkdir()

    with patch("shoal.core.git.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        git.commit(str(repo), "chore: test commit")

        mock_run.assert_called_once_with(
            ["git", "commit", "-m", "chore: test commit"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )


def test_commit_propagates_error(tmp_path):
    """commit raises CalledProcessError when git exits non-zero."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()

    with patch("shoal.core.git.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "git commit")

        with pytest.raises(subprocess.CalledProcessError):
            git.commit(str(repo), "bad commit")
