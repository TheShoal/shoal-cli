"""Git + worktree subprocess wrappers."""

from __future__ import annotations

import subprocess


def _run(
    args: list[str], *, cwd: str | None = None, check: bool = True, timeout: int = 30
) -> subprocess.CompletedProcess[str]:
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
