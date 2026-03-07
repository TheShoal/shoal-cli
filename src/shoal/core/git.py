"""Git + worktree subprocess wrappers.

All core functions are synchronous (used by CLI directly).
``async_*`` variants wrap the sync functions via ``asyncio.to_thread()``
for use in async contexts (lifecycle service, API).
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess

logger = logging.getLogger("shoal.git")


def _run(
    args: list[str], *, cwd: str | None = None, check: bool = True, timeout: int = 30
) -> subprocess.CompletedProcess[str]:
    logger.debug("git %s (cwd=%s)", " ".join(args), cwd)
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        cmd_name = args[0] if args else "unknown"
        raise TimeoutError(f"git {cmd_name} timed out after {timeout}s") from None


def is_git_repo(path: str) -> bool:
    result = _run(["rev-parse", "--git-dir"], cwd=path, check=False)
    return result.returncode == 0


def git_root(path: str) -> str:
    result = _run(["rev-parse", "--show-toplevel"], cwd=path)
    return result.stdout.strip()


def current_branch(path: str) -> str:
    result = _run(["branch", "--show-current"], cwd=path, check=False)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return "detached"


def worktree_add(
    repo: str, path: str, *, branch: str | None = None, start_point: str | None = None
) -> None:
    args = ["worktree", "add", path]
    if branch:
        args.extend(["-b", branch])
    if start_point:
        args.append(start_point)
    _run(args, cwd=repo)


def worktree_remove(repo: str, path: str, *, force: bool = False) -> bool:
    args = ["worktree", "remove", path]
    if force:
        args.append("--force")
    result = _run(args, cwd=repo, check=False)
    return result.returncode == 0


def branch_delete(repo: str, branch: str, *, force: bool = False) -> bool:
    flag = "-D" if force else "-d"
    result = _run(["branch", flag, branch], cwd=repo, check=False)
    return result.returncode == 0


def checkout(repo: str, branch: str) -> bool:
    result = _run(["checkout", branch], cwd=repo, check=False)
    return result.returncode == 0


def merge(repo: str, branch: str) -> bool:
    result = _run(["merge", branch], cwd=repo, check=False)
    return result.returncode == 0


def push(repo: str, branch: str, *, set_upstream: bool = False) -> bool:
    args = ["push"]
    if set_upstream:
        args.extend(["-u", "origin", branch])
    else:
        args.extend(["origin", branch])
    result = _run(args, cwd=repo, check=False, timeout=120)
    return result.returncode == 0


def main_branch(repo: str) -> str:
    result = _run(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=repo, check=False)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().replace("refs/remotes/origin/", "")
    return "main"


# ---------------------------------------------------------------------------
# Async wrappers — for use in async contexts (lifecycle, API)
# ---------------------------------------------------------------------------


async def async_is_git_repo(path: str) -> bool:
    return await asyncio.to_thread(is_git_repo, path)


async def async_git_root(path: str) -> str:
    return await asyncio.to_thread(git_root, path)


async def async_current_branch(path: str) -> str:
    return await asyncio.to_thread(current_branch, path)


async def async_worktree_add(
    repo: str, path: str, *, branch: str | None = None, start_point: str | None = None
) -> None:
    await asyncio.to_thread(worktree_add, repo, path, branch=branch, start_point=start_point)


async def async_worktree_remove(repo: str, path: str, *, force: bool = False) -> bool:
    return await asyncio.to_thread(worktree_remove, repo, path, force=force)


async def async_branch_delete(repo: str, branch: str, *, force: bool = False) -> bool:
    return await asyncio.to_thread(branch_delete, repo, branch, force=force)


def worktree_is_dirty(path: str) -> bool:
    """Return True if the worktree at *path* has uncommitted changes."""
    result = _run(["status", "--porcelain"], cwd=path, check=False)
    return bool(result.stdout.strip())


async def async_worktree_is_dirty(path: str) -> bool:
    return await asyncio.to_thread(worktree_is_dirty, path)


# ---------------------------------------------------------------------------
# Branch naming utilities
# ---------------------------------------------------------------------------

ALLOWED_BRANCH_CATEGORIES: tuple[str, ...] = (
    "feat",
    "fix",
    "bug",
    "chore",
    "docs",
    "refactor",
    "test",
)


def infer_branch_name(worktree_name: str) -> str:
    """Infer a branch name from a worktree name.

    If the worktree name already contains a ``/``, it is returned as-is
    (assumed to carry a valid category prefix like ``fix/`` or ``feat/``).
    Otherwise ``feat/`` is prepended as the default category.

    Examples::

        fix/tmux-status  -> fix/tmux-status   (pass-through)
        feat/my-feature  -> feat/my-feature   (pass-through)
        tmux-status      -> feat/tmux-status  (default prefix)
        my-feature       -> feat/my-feature   (default prefix)
    """
    if "/" in worktree_name:
        return worktree_name
    return f"feat/{worktree_name}"


def validate_branch_name(branch_name: str) -> None:
    """Raise ``ValueError`` if *branch_name* does not follow ``category/slug``.

    Valid categories: feat, fix, bug, chore, docs, refactor, test.
    Slug must be lowercase alphanumeric with hyphens (``[a-z0-9][a-z0-9-]*``).
    """
    categories = "|".join(ALLOWED_BRANCH_CATEGORIES)
    pattern = rf"^({categories})/[a-z0-9][a-z0-9-]*$"
    if re.match(pattern, branch_name):
        return
    allowed = ", ".join(ALLOWED_BRANCH_CATEGORIES)
    raise ValueError(
        "Branch name must follow category/slug (for example: feat/my-change) "
        f"with category in: {allowed}"
    )
