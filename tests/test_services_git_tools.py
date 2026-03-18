"""Tests for services/git_tools.py."""

from __future__ import annotations

import subprocess
from unittest.mock import AsyncMock, patch

import pytest

from shoal.services.git_tools import branch_status, merge_branch


def _proc(
    stdout: str = "", stderr: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# branch_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_branch_status_happy_path() -> None:
    procs = [
        _proc("main\n"),  # branch
        _proc("2\n"),  # ahead
        _proc("1\n"),  # behind
        _proc(""),  # porcelain (clean)
        _proc("abc123\n"),  # sha
        _proc("fix: something\n"),  # msg
    ]
    with patch(
        "shoal.services.git_tools.asyncio.gather", new_callable=AsyncMock, return_value=procs
    ):
        result = await branch_status("/repo")

    assert result == {
        "branch": "main",
        "ahead": 2,
        "behind": 1,
        "dirty": False,
        "last_commit_sha": "abc123",
        "last_commit_msg": "fix: something",
    }


@pytest.mark.asyncio
async def test_branch_status_dirty_worktree() -> None:
    procs = [
        _proc("main\n"),
        _proc("0\n"),
        _proc("0\n"),
        _proc(" M src/foo.py\n"),  # non-empty = dirty
        _proc("abc\n"),
        _proc("msg\n"),
    ]
    with patch(
        "shoal.services.git_tools.asyncio.gather", new_callable=AsyncMock, return_value=procs
    ):
        result = await branch_status("/repo")

    assert result["dirty"] is True


@pytest.mark.asyncio
async def test_branch_status_subprocess_failure_returns_defaults() -> None:
    procs = [
        _proc("", returncode=128),  # branch fails
        _proc("", returncode=128),  # ahead fails (no upstream)
        _proc("", returncode=128),  # behind fails
        _proc(""),  # porcelain clean
        _proc("", returncode=128),  # sha fails
        _proc("", returncode=128),  # msg fails
    ]
    with patch(
        "shoal.services.git_tools.asyncio.gather", new_callable=AsyncMock, return_value=procs
    ):
        result = await branch_status("/repo")

    assert result["branch"] == ""
    assert result["ahead"] == 0
    assert result["behind"] == 0
    assert result["last_commit_sha"] == ""


@pytest.mark.asyncio
async def test_branch_status_non_integer_ahead_defaults_to_zero() -> None:
    procs = [
        _proc("main\n"),
        _proc("not-a-number\n"),  # bad ahead output
        _proc("0\n"),
        _proc(""),
        _proc("abc\n"),
        _proc("msg\n"),
    ]
    with patch(
        "shoal.services.git_tools.asyncio.gather", new_callable=AsyncMock, return_value=procs
    ):
        result = await branch_status("/repo")

    assert result["ahead"] == 0


# ---------------------------------------------------------------------------
# merge_branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_branch_dirty_worktree_refuses() -> None:
    with patch("shoal.services.git_tools._run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = _proc(" M file.py\n")  # dirty
        result = await merge_branch("/repo", "main")

    assert result["success"] is False
    assert result["conflicts"] is False
    assert "uncommitted" in result["error"]  # type: ignore[operator]


@pytest.mark.asyncio
async def test_merge_branch_success() -> None:
    responses = [
        _proc(""),  # porcelain clean
        _proc("feat/x\n"),  # current branch
        _proc(""),  # checkout target OK
        _proc(""),  # merge OK
        _proc("deadbeef\n"),  # sha
    ]
    with patch("shoal.services.git_tools._run", new_callable=AsyncMock, side_effect=responses):
        result = await merge_branch("/repo", "main", strategy="merge")

    assert result["success"] is True
    assert result["conflicts"] is False
    assert result["merge_commit_sha"] == "deadbeef"


@pytest.mark.asyncio
async def test_merge_branch_conflict() -> None:
    responses = [
        _proc(""),  # clean
        _proc("feat/x\n"),  # branch
        _proc(""),  # checkout OK
        _proc("CONFLICT", returncode=1),  # merge fails
        _proc(""),  # abort (best effort)
    ]
    with patch("shoal.services.git_tools._run", new_callable=AsyncMock, side_effect=responses):
        result = await merge_branch("/repo", "main")

    assert result["success"] is False
    assert result["conflicts"] is True


@pytest.mark.asyncio
async def test_merge_branch_checkout_failure() -> None:
    responses = [
        _proc(""),  # clean
        _proc("feat/x\n"),  # branch
        _proc("error: branch not found", returncode=1),  # checkout fails
    ]
    with patch("shoal.services.git_tools._run", new_callable=AsyncMock, side_effect=responses):
        result = await merge_branch("/repo", "nonexistent")

    assert result["success"] is False
    assert result["conflicts"] is False


@pytest.mark.asyncio
async def test_merge_branch_squash_strategy() -> None:
    calls: list[list[str]] = []

    async def mock_run(cmd: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return _proc("")

    # Override sha call at the end
    sha_response = _proc("squashsha\n")
    call_count = 0

    async def mock_run_with_sha(cmd: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
        nonlocal call_count
        call_count += 1
        calls.append(cmd)
        if call_count == 6:  # sha call
            return sha_response
        return _proc("")

    with patch("shoal.services.git_tools._run", side_effect=mock_run_with_sha):
        result = await merge_branch("/repo", "main", strategy="squash")

    merge_cmd = next(c for c in calls if "merge" in c and "--squash" in c)
    assert "--squash" in merge_cmd
    assert result["success"] is True
