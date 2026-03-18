"""Async git helpers for worktree introspection and branch merging."""

from __future__ import annotations

import asyncio
import subprocess
from typing import Literal


async def _run(cmd: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    """Run a git command in a thread, cwd=worktree. Never raises on non-zero exit."""
    return await asyncio.to_thread(
        subprocess.run,
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


async def branch_status(worktree: str) -> dict[str, object]:
    """Return git status for the given worktree path.

    All fields are best-effort: if a subprocess call fails the field is set to
    its zero value (``""`` or ``0`` or ``False``) rather than raising.

    Returns:
        A dict with keys: branch, ahead, behind, dirty, last_commit_sha,
        last_commit_msg.
    """
    branch_proc, ahead_proc, behind_proc, porcelain_proc, sha_proc, msg_proc = (
        await asyncio.gather(
            _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], worktree),
            _run(
                ["git", "rev-list", "--count", "@{u}..HEAD"],
                worktree,
            ),
            _run(
                ["git", "rev-list", "--count", "HEAD..@{u}"],
                worktree,
            ),
            _run(["git", "status", "--porcelain"], worktree),
            _run(["git", "log", "-1", "--format=%H"], worktree),
            _run(["git", "log", "-1", "--format=%s"], worktree),
        )
    )

    branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else ""

    ahead_raw = ahead_proc.stdout.strip() if ahead_proc.returncode == 0 else ""
    try:
        ahead = int(ahead_raw)
    except ValueError:
        ahead = 0

    behind_raw = behind_proc.stdout.strip() if behind_proc.returncode == 0 else ""
    try:
        behind = int(behind_raw)
    except ValueError:
        behind = 0

    dirty = bool(porcelain_proc.stdout.strip())

    last_commit_sha = sha_proc.stdout.strip() if sha_proc.returncode == 0 else ""
    last_commit_msg = msg_proc.stdout.strip() if msg_proc.returncode == 0 else ""

    return {
        "branch": branch,
        "ahead": ahead,
        "behind": behind,
        "dirty": dirty,
        "last_commit_sha": last_commit_sha,
        "last_commit_msg": last_commit_msg,
    }


async def merge_branch(
    worktree: str,
    target: str,
    strategy: Literal["merge", "squash"] = "merge",
) -> dict[str, object]:
    """Merge the worktree's current branch into target.

    Refuses to operate on a dirty worktree.  On conflict, aborts the merge
    (best-effort) and reports ``conflicts=True``.

    Args:
        worktree: Absolute path to the git worktree.
        target: Branch to merge into (e.g. "main").
        strategy: "merge" (default, --ff) or "squash".

    Returns:
        On success: ``{"success": True, "conflicts": False, "merge_commit_sha": str}``
        On failure: ``{"success": False, "error": str, "conflicts": bool, "merge_commit_sha": None}``
    """
    # Refuse dirty worktree upfront.
    porcelain = await _run(["git", "status", "--porcelain"], worktree)
    if porcelain.stdout.strip():
        return {
            "success": False,
            "error": "worktree has uncommitted changes",
            "conflicts": False,
            "merge_commit_sha": None,
        }

    # Record current branch so we can merge it into target.
    branch_proc = await _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], worktree)
    source_branch = branch_proc.stdout.strip()

    # Checkout target.
    checkout = await _run(["git", "checkout", target], worktree)
    if checkout.returncode != 0:
        return {
            "success": False,
            "error": checkout.stderr.strip(),
            "conflicts": False,
            "merge_commit_sha": None,
        }

    # Perform merge according to strategy.
    if strategy == "squash":
        merge_proc = await _run(["git", "merge", "--squash", source_branch], worktree)
    else:
        merge_proc = await _run(["git", "merge", "--ff", source_branch], worktree)

    if merge_proc.returncode != 0:
        # Attempt to abort so the worktree is left clean.
        await _run(["git", "merge", "--abort"], worktree)
        return {
            "success": False,
            "error": merge_proc.stderr.strip(),
            "conflicts": True,
            "merge_commit_sha": None,
        }

    # Squash merge stages changes but does not commit; commit now.
    if strategy == "squash":
        commit_proc = await _run(
            ["git", "commit", "-m", f"squash merge {source_branch}"],
            worktree,
        )
        if commit_proc.returncode != 0:
            return {
                "success": False,
                "error": commit_proc.stderr.strip() or commit_proc.stdout.strip(),
                "conflicts": False,
                "merge_commit_sha": None,
            }

    sha_proc = await _run(["git", "log", "-1", "--format=%H"], worktree)
    sha = sha_proc.stdout.strip() if sha_proc.returncode == 0 else ""

    return {
        "success": True,
        "conflicts": False,
        "merge_commit_sha": sha,
    }
