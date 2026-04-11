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
from pathlib import Path

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


def is_merging(path: str) -> bool:
    """Return True if the working tree has an in-progress merge."""
    git_dir = _run(["rev-parse", "--git-dir"], cwd=path, check=False).stdout.strip()
    if not git_dir:
        return False
    # git_dir may be relative or absolute; resolve it against the working tree
    gd = Path(git_dir)
    if not gd.is_absolute():
        gd = Path(path) / gd
    return (gd / "MERGE_HEAD").exists()


def is_rebasing(path: str) -> bool:
    """Return True if the working tree has an in-progress rebase."""
    git_dir = _run(["rev-parse", "--git-dir"], cwd=path, check=False).stdout.strip()
    if not git_dir:
        return False
    gd = Path(git_dir)
    return any((gd / f).exists() for f in ("rebase-merge", "rebase-apply"))


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


def worktree_has_tracked_changes(path: str) -> bool:
    """Return True if the worktree has changes to tracked files (ignores untracked).

    Uses ``--ignored`` so that gitignored entries (shown as ``!!``) are also
    excluded. This prevents directories that are themselves git repos or are
    gitignored from falsely blocking worktree creation in a meta-repo.
    """
    result = _run(["status", "--porcelain", "--ignored"], cwd=path, check=False)
    # XY filename  — XY != "??" (untracked) and XY != "!!" (ignored)
    return any(line[:2] not in ("??", "!!") and line.strip() for line in result.stdout.splitlines())


async def async_worktree_has_tracked_changes(path: str) -> bool:
    return await asyncio.to_thread(worktree_has_tracked_changes, path)


def stage_all(path: str) -> None:
    """Stage all changes in the working tree (git add -A)."""
    _run(["add", "-A"], cwd=path)


async def async_stage_all(path: str) -> None:
    await asyncio.to_thread(stage_all, path)


def commit(path: str, message: str) -> None:
    """Create a commit with *message* in the working tree at *path*.

    Raises ``subprocess.CalledProcessError`` if git commit exits non-zero
    (e.g. nothing to commit after staging).
    """
    _run(["commit", "-m", message], cwd=path)


async def async_commit(path: str, message: str) -> None:
    await asyncio.to_thread(commit, path, message)


def diff_stat(path: str) -> str:
    """Return a short ``--stat`` summary of uncommitted changes, or ``""``."""
    result = _run(["diff", "--stat", "HEAD"], cwd=path, check=False)
    if result.returncode != 0:
        return ""
    lines = result.stdout.strip().splitlines()
    return lines[-1].strip() if lines else ""


def commit_count_since_main(path: str) -> int:
    """Count commits on current branch since diverging from main/master."""
    main = main_branch(path)
    result = _run(["rev-list", "--count", f"{main}..HEAD"], cwd=path, check=False)
    if result.returncode != 0:
        return 0
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


async def async_diff_stat(path: str) -> str:
    return await asyncio.to_thread(diff_stat, path)


async def async_commit_count_since_main(path: str) -> int:
    return await asyncio.to_thread(commit_count_since_main, path)


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
    "plan",
    "impl",
    "review",
    "batch",
    "ops",
)


def infer_branch_name(worktree_name: str, branch_prefix: str = "") -> str:
    """Infer a branch name from a worktree name.

    If the worktree name already contains a ``/``, it is returned as-is
    (assumed to carry a valid category prefix like ``fix/`` or ``feat/``).
    Otherwise *branch_prefix* is prepended; if *branch_prefix* is empty,
    ``feat/`` is used as the default category.

    *branch_prefix* may include or omit a trailing ``/`` — it is normalised.

    Examples::

        fix/tmux-status  -> fix/tmux-status   (pass-through — explicit wins)
        feat/my-feature  -> feat/my-feature   (pass-through — explicit wins)
        tmux-status      -> feat/tmux-status  (default prefix, no template)
        my-feature       -> fix/my-feature    (branch_prefix="fix" or "fix/")
    """
    if "/" in worktree_name:
        return worktree_name
    prefix = branch_prefix.rstrip("/") if branch_prefix else "feat"
    return f"{prefix}/{worktree_name}"


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


# ---------------------------------------------------------------------------
# Workspace routing — meta-repo sub-repo resolution
# ---------------------------------------------------------------------------


def resolve_workspace_repo(
    meta_root: str,
    repos: dict[str, str],
    *,
    repo_key: str | None = None,
    worktree_hint: str | None = None,
    resolved_path: str | None = None,
) -> str | None:
    """Resolve a sub-repo git root from a workspace manifest.

    Matching order:

    1. **Explicit key** (``--repo`` flag): must exist in *repos*.
    2. **Worktree hint** (``-w`` value): exact key match against *repos*.
    3. **Path prefix**: if *resolved_path* starts with a repo path.
    4. No match → return ``None`` (fall through to meta-repo behaviour).

    Returns the **absolute path** to the sub-repo directory, or ``None``.
    The caller should run ``git_root()`` on the result to canonicalize.
    """
    if repo_key:
        rel = repos.get(repo_key)
        if rel is None:
            available = ", ".join(sorted(repos)) or "(none)"
            raise ValueError(f"Workspace repo '{repo_key}' not found. Available: {available}")
        return str(Path(meta_root) / rel)

    if worktree_hint:
        rel = repos.get(worktree_hint)
        if rel is not None:
            return str(Path(meta_root) / rel)

    if resolved_path:
        resolved = Path(resolved_path).resolve()
        meta = Path(meta_root).resolve()
        for rel in repos.values():
            candidate = meta / rel
            if resolved.is_relative_to(candidate):
                return str(candidate)

    return None


def apply_workspace_routing(
    root: str,
    resolved_path: str,
    *,
    repo: str | None = None,
    worktree: str | None = None,
    repos: dict[str, str],
) -> tuple[str, str]:
    """Re-target git root to a sub-repo based on workspace manifest.

    Returns ``(new_root, new_resolved_path)``.  Raises ``ValueError`` on
    user errors (unknown repo key, sub-path not a git repo).
    """
    sub_root = resolve_workspace_repo(
        root,
        repos,
        repo_key=repo,
        worktree_hint=worktree,
        resolved_path=resolved_path,
    )
    if sub_root is None:
        return root, resolved_path
    try:
        new_root = git_root(sub_root)
    except subprocess.CalledProcessError:
        raise ValueError(f"Not a git repo: {sub_root}") from None
    return new_root, str(Path(new_root).resolve())
