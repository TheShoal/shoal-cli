"""Session lifecycle orchestration — shared by CLI and API.

Centralises create / fork / kill / reconcile logic so that both
``cli/session.py`` and ``api/server.py`` share a single rollback
sequence and startup-command execution path.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
import subprocess
from collections import defaultdict
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shoal.models.config import DreamerConfig, ProjectHookEntry

from shoal.core import git, tmux
from shoal.core.config import load_config
from shoal.core.state import (
    build_nvim_socket_path,
    create_session,
    delete_session,
    get_session,
    list_sessions,
    update_session,
)
from shoal.models.config import (
    CoordinatorConfig,
    DreamerConfig,
    ProjectHookEntry,
    SessionTemplateConfig,
)
from shoal.models.state import LifecycleEvent, SessionState, SessionStatus, TmuxRuntimeState
from shoal.services.runtime_provider import provider_for_session

logger = logging.getLogger("shoal.lifecycle")

# ---------------------------------------------------------------------------
# Lifecycle hook registry
# ---------------------------------------------------------------------------

# Callback type: async fn(event, **kwargs) -> None
HookCallback = Callable[..., Awaitable[None]]

_hooks: dict[LifecycleEvent, list[HookCallback]] = defaultdict(list)
_registered: set[str] = set()  # idempotency keys; cleared alongside _hooks


def on(event: LifecycleEvent, callback: HookCallback) -> None:
    """Register an async callback for a lifecycle event."""
    _hooks[event].append(callback)


async def emit(event: LifecycleEvent, **kwargs: Any) -> None:
    """Fire all registered callbacks for an event.

    Exceptions in individual hooks are logged but do not propagate,
    so a broken hook never blocks the lifecycle operation.
    """
    for cb in _hooks.get(event, []):
        try:
            await cb(event, **kwargs)
        except Exception:
            logger.exception("Hook error for %s: %s", event, cb)


def clear_hooks() -> None:
    """Remove all registered hooks.  Intended for testing."""
    _hooks.clear()
    _registered.clear()


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class LifecycleError(Exception):
    """Base exception for lifecycle operations."""

    def __init__(self, message: str, *, session_id: str = "", operation: str = "") -> None:
        self.session_id = session_id
        self.operation = operation
        super().__init__(message)


class TmuxSetupError(LifecycleError):
    """``tmux new-session`` (or related setup step) failed."""


class StartupCommandError(LifecycleError):
    """Startup command interpolation or execution failed."""


class SessionExistsError(LifecycleError):
    """Session name collision."""


class DirtyWorktreeError(LifecycleError):
    """Worktree has uncommitted changes."""

    def __init__(self, message: str, *, session_id: str = "", dirty_files: str = "") -> None:
        self.dirty_files = dirty_files
        super().__init__(message, session_id=session_id, operation="kill")


class SessionNotFoundError(LifecycleError):
    """Session not found."""


# ---------------------------------------------------------------------------
# Skill sync — transpile .shoal/skills/ into tool-native format
# ---------------------------------------------------------------------------


def _sync_skills_to_worktree(git_root: str, wt_path: str, tool: str) -> None:
    """Symlink .shoal/skills/ into the worktree's tool-native skill path.

    Currently supports Claude Code (.claude/skills/).  Other tools get skills
    via the cross-agent skill sync script (post_worktree_create hook).
    """
    skills_src = Path(git_root) / ".shoal" / "skills"
    if not skills_src.is_dir():
        return

    wt = Path(wt_path)

    # Claude Code: symlink each skill directory
    if tool in ("claude", "claude-yolo"):
        dest = wt / ".claude" / "skills"
        dest.mkdir(parents=True, exist_ok=True)
        for skill_dir in skills_src.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                link = dest / skill_dir.name
                if not link.exists():
                    try:
                        link.symlink_to(skill_dir)
                    except OSError:
                        logger.debug("Failed to symlink skill %s", skill_dir.name)


# ---------------------------------------------------------------------------
# Post-worktree hook
# ---------------------------------------------------------------------------


def _run_post_worktree_hook(
    template_cfg: SessionTemplateConfig | None,
    wt_path: str,
    git_root: str,
) -> None:
    """Execute post_worktree_create script synchronously, if configured.

    Errors are logged as warnings and do not propagate — a misconfigured or
    failing hook must not abort session creation.
    """
    if not template_cfg or not template_cfg.worktree.post_worktree_create:
        return
    script_raw = template_cfg.worktree.post_worktree_create
    # Resolve relative paths against the git root so scripts can live in the repo.
    script_path = (
        Path(script_raw) if Path(script_raw).is_absolute() else Path(git_root) / script_raw
    )
    if not script_path.exists():
        logger.warning(
            "post_worktree_create script not found: %s (resolved from %s)",
            script_path,
            script_raw,
        )
        return
    try:
        result = subprocess.run(
            [str(script_path), wt_path],
            check=False,
        )
        if result.returncode != 0:
            logger.warning(
                "post_worktree_create script exited %d: %s",
                result.returncode,
                script_path,
            )
    except Exception:
        logger.warning(
            "post_worktree_create script raised an exception: %s", script_path, exc_info=True
        )


# ---------------------------------------------------------------------------
# Rollback helper
# ---------------------------------------------------------------------------


def _rollback(
    *,
    session_id: str = "",
    tmux_name: str = "",
    wt_path: str = "",
    git_root: str = "",
) -> list[str]:
    """Best-effort rollback of partially-created resources.

    Each step is independently try/excepted so one failure does not
    prevent cleanup of remaining resources.  Returns a list of warning
    messages (empty on clean rollback).
    """
    warnings: list[str] = []

    # 1. Delete DB row
    if session_id:
        try:
            import asyncio

            # We may be called from both sync and async contexts.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # Already inside an async context — schedule as a task.
                # The caller is responsible for awaiting rollback in that case,
                # so this branch is handled by _rollback_async instead.
                pass
            else:
                asyncio.run(delete_session(session_id))
        except Exception as exc:
            msg = f"Rollback: failed to delete DB row {session_id}: {exc}"
            logger.warning(msg)
            warnings.append(msg)

    # 2. Kill tmux session
    if tmux_name:
        try:
            tmux.kill_session(tmux_name)
        except Exception as exc:
            msg = f"Rollback: failed to kill tmux session {tmux_name}: {exc}"
            logger.warning(msg)
            warnings.append(msg)

    # 3. Remove worktree
    if wt_path and Path(wt_path).exists():
        try:
            root = git_root or ""
            if root:
                git.worktree_remove(root, wt_path, force=True)
        except Exception as exc:
            msg = f"Rollback: failed to remove worktree {wt_path}: {exc}"
            logger.warning(msg)
            warnings.append(msg)

    return warnings


async def _rollback_async(
    *,
    session_id: str = "",
    tmux_name: str = "",
    wt_path: str = "",
    git_root: str = "",
) -> list[str]:
    """Async variant of :func:`_rollback` — use when already on an event loop."""
    warnings: list[str] = []

    if session_id:
        try:
            await delete_session(session_id)
        except Exception as exc:
            msg = f"Rollback: failed to delete DB row {session_id}: {exc}"
            logger.warning(msg)
            warnings.append(msg)

    if tmux_name:
        try:
            await tmux.async_kill_session(tmux_name)
        except Exception as exc:
            msg = f"Rollback: failed to kill tmux session {tmux_name}: {exc}"
            logger.warning(msg)
            warnings.append(msg)

    wt_exists = bool(wt_path and await asyncio.to_thread(lambda: Path(wt_path).exists()))
    if wt_exists:
        try:
            root = git_root or ""
            if root:
                await git.async_worktree_remove(root, wt_path, force=True)
        except Exception as exc:
            msg = f"Rollback: failed to remove worktree {wt_path}: {exc}"
            logger.warning(msg)
            warnings.append(msg)

    return warnings


async def _run_default_startup_commands_async(
    startup_commands: list[str],
    *,
    tool_command: str,
    work_dir: str,
    session_name: str,
    tmux_session: str,
) -> None:
    """Async variant of :func:`_run_default_startup_commands`."""
    for cmd in startup_commands:
        try:
            interpolated = cmd.format(
                tool_command=tool_command,
                work_dir=work_dir,
                session_name=session_name,
                tmux_session=tmux_session,
            )
        except KeyError as e:
            logger.warning("Skipping startup command with missing variable %s: %s", e, cmd)
            continue
        await tmux.async_run_command(interpolated)


async def _run_template_startup_async(
    template: SessionTemplateConfig,
    *,
    tool_command: str,
    work_dir: str,
    root: str,
    branch_name: str,
    session_name: str,
    tmux_session: str,
    worktree_name: str,
) -> None:
    """Async variant of :func:`_run_template_startup`."""
    if not template.windows:
        return

    context = {
        "tool_command": tool_command,
        "work_dir": work_dir,
        "git_root": root,
        "session_name": session_name,
        "tmux_session": tmux_session,
        "branch_name": branch_name,
        "worktree": worktree_name,
        "template_name": template.name,
    }

    focus_window_target = ""

    _wi_base, _pi_base = await tmux.async_server_base_indices()

    for window_index, window in enumerate(template.windows):
        window_target = f"{tmux_session}:{window_index + _wi_base}"
        window_name = _format_value(window.name, context, "window name") if window.name else ""
        window_cwd = work_dir
        if window.cwd:
            window_cwd = _format_value(window.cwd, context, "window cwd")

        if window_index == 0:
            if window_name:
                await tmux.async_run_command(
                    f"rename-window -t {window_target} {shlex.quote(window_name)}"
                )
        else:
            cmd = f"new-window -t {tmux_session}"
            if window_name:
                cmd += f" -n {shlex.quote(window_name)}"
            cmd += f" -c {shlex.quote(window_cwd)}"
            await tmux.async_run_command(cmd)

        if window.focus and not focus_window_target:
            focus_window_target = window_target

        for pane_index, pane in enumerate(window.panes):
            pane_target = f"{window_target}.{pane_index + _pi_base}"

            if pane_index == 0:
                if window_cwd and window_cwd != work_dir:
                    await tmux.async_send_keys(pane_target, f"cd {shlex.quote(window_cwd)}")
            else:
                split_type = pane.split
                if split_type == "root":
                    split_type = "down"

                split_flag = "-h" if split_type == "right" else "-v"
                cmd = f"split-window -t {window_target} {split_flag}"
                percent = _split_percentage(pane.size)
                if percent is not None:
                    cmd += f" -p {percent}"
                cmd += f" -c {shlex.quote(window_cwd)}"
                await tmux.async_run_command(cmd)

            pane_command = _format_value(pane.command, context, "pane command")
            await tmux.async_send_keys(pane_target, pane_command)

            if pane.title:
                pane_title = _format_value(pane.title, context, "pane title")
                await tmux.async_set_pane_title(pane_target, pane_title)

        if window.layout:
            layout = _format_value(window.layout, context, "window layout")
            await tmux.async_run_command(f"select-layout -t {window_target} {shlex.quote(layout)}")

    if focus_window_target:
        await tmux.async_run_command(f"select-window -t {focus_window_target}")


# ---------------------------------------------------------------------------
# Startup command helpers (moved from cli/session.py)
# ---------------------------------------------------------------------------


def _split_percentage(size: str) -> int | None:
    value = size.strip()
    if not value:
        return None
    if value.endswith("%"):
        value = value[:-1]
    if not value.isdigit():
        return None
    parsed = int(value)
    if 1 <= parsed <= 99:
        return parsed
    return None


def _format_value(raw: str, context: dict[str, str], field_name: str) -> str:
    try:
        return raw.format(**context)
    except KeyError as e:
        raise ValueError(f"Missing template variable {e} in {field_name}: {raw}") from None


def _run_default_startup_commands(
    startup_commands: list[str],
    *,
    tool_command: str,
    work_dir: str,
    session_name: str,
    tmux_session: str,
) -> None:
    for cmd in startup_commands:
        try:
            interpolated = cmd.format(
                tool_command=tool_command,
                work_dir=work_dir,
                session_name=session_name,
                tmux_session=tmux_session,
            )
        except KeyError as e:
            logger.warning("Skipping startup command with missing variable %s: %s", e, cmd)
            continue
        tmux.run_command(interpolated)


def _preview_default_startup_commands(
    startup_commands: list[str],
    *,
    tool_command: str,
    work_dir: str,
    session_name: str,
    tmux_session: str,
) -> list[str]:
    preview: list[str] = []
    for cmd in startup_commands:
        try:
            interpolated = cmd.format(
                tool_command=tool_command,
                work_dir=work_dir,
                session_name=session_name,
                tmux_session=tmux_session,
            )
        except KeyError as e:
            raise ValueError(f"Missing startup command variable {e} in: {cmd}") from None
        preview.append(interpolated)
    return preview


def _run_template_startup(
    template: SessionTemplateConfig,
    *,
    tool_command: str,
    work_dir: str,
    root: str,
    branch_name: str,
    session_name: str,
    tmux_session: str,
    worktree_name: str,
) -> None:
    if not template.windows:
        return

    context = {
        "tool_command": tool_command,
        "work_dir": work_dir,
        "git_root": root,
        "session_name": session_name,
        "tmux_session": tmux_session,
        "branch_name": branch_name,
        "worktree": worktree_name,
        "template_name": template.name,
    }

    focus_window_target = ""

    _wi_base, _pi_base = tmux.server_base_indices()

    for window_index, window in enumerate(template.windows):
        window_target = f"{tmux_session}:{window_index + _wi_base}"
        window_name = _format_value(window.name, context, "window name") if window.name else ""
        window_cwd = work_dir
        if window.cwd:
            window_cwd = _format_value(window.cwd, context, "window cwd")

        if window_index == 0:
            if window_name:
                tmux.run_command(f"rename-window -t {window_target} {shlex.quote(window_name)}")
        else:
            cmd = f"new-window -t {tmux_session}"
            if window_name:
                cmd += f" -n {shlex.quote(window_name)}"
            cmd += f" -c {shlex.quote(window_cwd)}"
            tmux.run_command(cmd)

        if window.focus and not focus_window_target:
            focus_window_target = window_target

        for pane_index, pane in enumerate(window.panes):
            pane_target = f"{window_target}.{pane_index + _pi_base}"

            if pane_index == 0:
                if window_cwd and window_cwd != work_dir:
                    tmux.send_keys(pane_target, f"cd {shlex.quote(window_cwd)}")
            else:
                split_type = pane.split
                if split_type == "root":
                    split_type = "down"

                split_flag = "-h" if split_type == "right" else "-v"
                cmd = f"split-window -t {window_target} {split_flag}"
                percent = _split_percentage(pane.size)
                if percent is not None:
                    cmd += f" -p {percent}"
                cmd += f" -c {shlex.quote(window_cwd)}"
                tmux.run_command(cmd)

            pane_command = _format_value(pane.command, context, "pane command")
            tmux.send_keys(pane_target, pane_command)

            if pane.title:
                pane_title = _format_value(pane.title, context, "pane title")
                tmux.set_pane_title(pane_target, pane_title)

        if window.layout:
            layout = _format_value(window.layout, context, "window layout")
            tmux.run_command(f"select-layout -t {window_target} {shlex.quote(layout)}")

    if focus_window_target:
        tmux.run_command(f"select-window -t {focus_window_target}")


def _preview_template_startup(
    template: SessionTemplateConfig,
    *,
    tool_command: str,
    work_dir: str,
    root: str,
    branch_name: str,
    session_name: str,
    tmux_session: str,
    worktree_name: str,
) -> list[str]:
    preview: list[str] = []
    if not template.windows:
        return preview

    context = {
        "tool_command": tool_command,
        "work_dir": work_dir,
        "git_root": root,
        "session_name": session_name,
        "tmux_session": tmux_session,
        "branch_name": branch_name,
        "worktree": worktree_name,
        "template_name": template.name,
    }

    focus_window_target = ""

    for window_index, window in enumerate(template.windows):
        window_target = f"{tmux_session}:{window_index}"
        window_name = _format_value(window.name, context, "window name") if window.name else ""
        window_cwd = work_dir
        if window.cwd:
            window_cwd = _format_value(window.cwd, context, "window cwd")

        if window_index == 0:
            if window_name:
                preview.append(f"rename-window -t {window_target} {shlex.quote(window_name)}")
        else:
            cmd = f"new-window -t {tmux_session}"
            if window_name:
                cmd += f" -n {shlex.quote(window_name)}"
            cmd += f" -c {shlex.quote(window_cwd)}"
            preview.append(cmd)

        if window.focus and not focus_window_target:
            focus_window_target = window_target

        for pane_index, pane in enumerate(window.panes):
            pane_target = f"{window_target}.{pane_index}"

            if pane_index == 0:
                if window_cwd and window_cwd != work_dir:
                    preview.append(f"send-keys -t {pane_target} cd {shlex.quote(window_cwd)} Enter")
            else:
                split_type = pane.split
                if split_type == "root":
                    split_type = "down"
                split_flag = "-h" if split_type == "right" else "-v"
                cmd = f"split-window -t {window_target} {split_flag}"
                percent = _split_percentage(pane.size)
                if percent is not None:
                    cmd += f" -p {percent}"
                cmd += f" -c {shlex.quote(window_cwd)}"
                preview.append(cmd)

            pane_command = _format_value(pane.command, context, "pane command")
            preview.append(f"send-keys -t {pane_target} {shlex.quote(pane_command)} Enter")

            if pane.title:
                pane_title = _format_value(pane.title, context, "pane title")
                preview.append(f"select-pane -t {pane_target} -T {shlex.quote(pane_title)}")

        if window.layout:
            layout = _format_value(window.layout, context, "window layout")
            preview.append(f"select-layout -t {window_target} {shlex.quote(layout)}")

    if focus_window_target:
        preview.append(f"select-window -t {focus_window_target}")

    return preview


# ---------------------------------------------------------------------------
# MCP provisioning helper
# ---------------------------------------------------------------------------


async def _provision_mcp_servers(
    mcp_names: list[str],
    session_id: str,
    tool: str,
    work_dir: str,
) -> list[str]:
    """Best-effort MCP provisioning.  Failures warn but don't block.

    For each server name:
    1. Start it if not already running (via registry lookup).
    2. Add it to the session's MCP list.
    3. Auto-configure the tool (if supported).

    Returns the list of successfully provisioned server names.
    """
    from shoal.core.config import load_mcp_registry
    from shoal.services.mcp_configure import McpConfigureError, configure_mcp_for_tool
    from shoal.services.mcp_pool import is_mcp_running, start_mcp_server

    registry = load_mcp_registry()
    provisioned: list[str] = []

    for name in mcp_names:
        try:
            # Start if not running
            if not is_mcp_running(name):
                command = registry.get(name)
                if not command:
                    logger.warning("[%s] mcp: skipping '%s' — not in registry", session_id, name)
                    continue
                start_mcp_server(name, command)

            # Attach to session
            from shoal.core.state import add_mcp_to_session

            await add_mcp_to_session(session_id, name)

            # Auto-configure tool
            try:
                configure_mcp_for_tool(tool, name, work_dir)
            except McpConfigureError as e:
                logger.warning("[%s] mcp: configure '%s' failed: %s", session_id, name, e)

            provisioned.append(name)
        except Exception as e:
            logger.warning("[%s] mcp: failed to provision '%s': %s", session_id, name, e)

    return provisioned


def _mcp_socket_env_injection(provisioned: list[str], tool: str) -> dict[str, str]:
    """Return env vars to inject when a tool receives MCP sockets via an env var.

    When ``mcp.socket_env`` is set on the tool config (e.g. ``PISCES_MCP_SOCKETS``),
    returns a single-entry dict mapping that var to a colon-delimited list of the
    Unix socket paths for every provisioned server.  Returns an empty dict when
    ``socket_env`` is unset or the tool config is missing.
    """
    from shoal.core.config import load_tool_config
    from shoal.services.mcp_pool import mcp_socket

    try:
        tool_cfg = load_tool_config(tool)
    except FileNotFoundError:
        return {}
    env_var = tool_cfg.mcp.socket_env
    if not env_var:
        return {}
    socket_paths = [str(mcp_socket(name)) for name in provisioned]
    return {env_var: ":".join(socket_paths)}


async def _inject_mcp_socket_env_async(
    sock_env: dict[str, str],
    tmux_session: str,
    session_id: str,
) -> None:
    """Push MCP socket env vars into a running tmux session.

    Sets each var in the tmux session environment (inherited by future windows)
    and sends a ``set -gx`` command to every shell pane so running processes
    pick it up immediately.
    """
    if not sock_env:
        return
    for key, value in sock_env.items():
        await tmux.async_set_environment(tmux_session, key, value)
    _SHELL_COMMANDS = {"fish", "zsh", "bash", "sh", "dash"}
    # Panes may still be initializing when MCP provisioning completes.
    # Poll briefly until at least one shell pane is ready (max ~5 s).
    shell_panes: list[str] = []
    for _ in range(20):
        panes = await tmux.async_list_panes(tmux_session)
        shell_panes = [p["id"] for p in panes if p.get("command", "") in _SHELL_COMMANDS]
        if shell_panes:
            break
        await asyncio.sleep(0.25)
    for pane in shell_panes:
        for key, value in sock_env.items():
            await tmux.async_send_keys(
                pane,
                f"set -gx {shlex.quote(key)} {shlex.quote(value)}",
                enter=True,
            )
    logger.debug(
        "[%s] injected MCP socket env %s into %d shell pane(s)",
        session_id,
        list(sock_env),
        len(shell_panes),
    )


async def _symlink_pre_commit_config(src: str, work_dir: str) -> None:
    """Symlink a shared pre-commit config into the session worktree.

    Creates ``<work_dir>/.pre-commit-config.yaml -> <src>`` so that
    ``pre-commit`` picks up the shared config automatically.
    Silently no-ops if *src* does not exist.  If a symlink already exists at
    the target it is replaced (idempotent for re-used worktrees).
    The path expansion and filesystem operations are run in a thread to
    stay async-safe.
    """

    def _do_symlink() -> None:
        src_path = Path(src).expanduser().resolve()
        if not src_path.exists():
            return
        dest = Path(work_dir) / ".pre-commit-config.yaml"
        if dest.is_symlink():
            dest.unlink()
        dest.symlink_to(src_path)

    await asyncio.to_thread(_do_symlink)


async def _apply_template_git_config_async(
    template_cfg: SessionTemplateConfig,
    tmux_session: str,
    work_dir: str,
) -> None:
    """Apply [template.git] identity fields to the session's git worktree.

    Emits ``git config --local`` commands into the initial tmux pane so the
    config is scoped to the worktree and does not leak into the global gitconfig.
    Also exports ``GIT_AUTHOR_*`` and ``GIT_COMMITTER_*`` as env vars so
    subprocess git calls inherit the identity even when cwd differs.
    """
    git_cfg = template_cfg.git
    if git_cfg is None:
        return
    if not (
        git_cfg.user_name
        or git_cfg.user_email
        or git_cfg.commit_template
        or git_cfg.pre_commit_config
    ):
        return

    initial_pane = await tmux.async_first_pane(tmux_session)

    if git_cfg.user_name:
        name_q = shlex.quote(git_cfg.user_name)
        work_q = shlex.quote(work_dir)
        await tmux.async_send_keys(
            initial_pane,
            f"git -C {work_q} config --local user.name {name_q}",
            enter=True,
        )
        await tmux.async_send_keys(
            initial_pane,
            f"set -gx GIT_AUTHOR_NAME {name_q}",
            enter=True,
        )
        await tmux.async_send_keys(
            initial_pane,
            f"set -gx GIT_COMMITTER_NAME {name_q}",
            enter=True,
        )

    if git_cfg.user_email:
        email_q = shlex.quote(git_cfg.user_email)
        work_q = shlex.quote(work_dir)
        await tmux.async_send_keys(
            initial_pane,
            f"git -C {work_q} config --local user.email {email_q}",
            enter=True,
        )
        await tmux.async_send_keys(
            initial_pane,
            f"set -gx GIT_AUTHOR_EMAIL {email_q}",
            enter=True,
        )
        await tmux.async_send_keys(
            initial_pane,
            f"set -gx GIT_COMMITTER_EMAIL {email_q}",
            enter=True,
        )

    if git_cfg.commit_template:
        tmpl_q = shlex.quote(git_cfg.commit_template)
        work_q = shlex.quote(work_dir)
        await tmux.async_send_keys(
            initial_pane,
            f"git -C {work_q} config --local commit.template {tmpl_q}",
            enter=True,
        )

    if git_cfg.pre_commit_config:
        await _symlink_pre_commit_config(git_cfg.pre_commit_config, work_dir)


# ---------------------------------------------------------------------------
# Lifecycle operations
# ---------------------------------------------------------------------------


def _inject_model_arg(command: str, model: str | None) -> str:
    """Inject ``--model`` into a tool command string if not already present.

    Uses :func:`shlex.quote` to prevent shell injection when the model
    string is eventually typed into a tmux pane via ``send_keys``.

    If *command* already contains ``--model`` as a standalone flag, the
    explicit *model* parameter is **not** appended and a warning is logged
    so that template-baked models take precedence without silent overrides.

    Args:
        command: The tool command string (e.g. ``"pisces"``).
        model: Model identifier to inject (e.g. ``"z-ai/glm-5"``).

    Returns:
        The command with ``--model`` appended, or *command* unchanged.
    """
    if not model:
        return command
    # Check for --model as a standalone flag (not part of a longer flag like --model-path)
    if re.search(r"(?:^|\s)--model(?:=|\s|$)", command):
        logger.warning(
            "tool_command already contains --model; skipping injection of model=%s", model
        )
        return command
    return f"{command} --model {shlex.quote(model)}"


async def create_session_lifecycle(
    *,
    session_name: str,
    tool: str,
    git_root: str,
    wt_path: str,
    work_dir: str,
    branch_name: str,
    tool_command: str,
    startup_commands: list[str],
    template_cfg: SessionTemplateConfig | None = None,
    worktree_name: str = "",
    mcp_servers: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    tags: list[str] | None = None,
    dreamer_config: DreamerConfig | None = None,
    coordinator_config: CoordinatorConfig | None = None,
    model: str | None = None,
) -> SessionState:
    """Create a session with full rollback on failure.

    This is the canonical create path shared by CLI and API.

    Returns the created :class:`SessionState`.

    Raises:
        SessionExistsError: name collision (DB or tmux).
        TmuxSetupError: tmux new-session failed.
        StartupCommandError: startup command interpolation/execution failed.
        ValueError: invalid session name.
    """
    template_name = template_cfg.name if template_cfg else ""
    logger.info("[%s] create: starting (tool=%s, model=%s)", session_name, tool, model or "default")

    # Inject --model flag into tool_command when model is specified
    tool_command = _inject_model_arg(tool_command, model)

    # 1. Create DB row
    try:
        session = await create_session(
            session_name,
            tool,
            git_root,
            wt_path,
            branch_name,
            tags=tags or [],
            template_name=template_name,
            model=model or "",
        )
    except ValueError as exc:
        if "already exists" in str(exc) or "collides" in str(exc):
            raise SessionExistsError(str(exc), session_id="", operation="create") from exc
        raise

    from shoal.core.context import set_session_id

    set_session_id(session.id)

    tmux_session = session.tmux_runtime.session_name
    logger.info("[%s] create: DB row created (id=%s)", session_name, session.id)

    # 2. Create tmux session
    try:
        await tmux.async_new_session(tmux_session, cwd=work_dir)
    except Exception as exc:
        logger.warning("[%s] create: tmux.new_session failed: %s", session.id, exc)
        await _rollback_async(
            session_id=session.id,
            wt_path=wt_path,
            git_root=git_root,
        )
        raise TmuxSetupError(
            f"Failed to create tmux session: {exc}",
            session_id=session.id,
            operation="create",
        ) from exc

    # 3. Set environment variables (precedence: project < template < extra/CLI)
    await tmux.async_set_environment(tmux_session, "SHOAL_SESSION_ID", session.id)
    await tmux.async_set_environment(tmux_session, "SHOAL_SESSION_NAME", session_name)

    # Extract secure environment variables (API keys, tokens, secrets) for delegation proxy
    secure_env: dict[str, str] = {}
    session_env: dict[str, str] = {}

    # Helper to identify secure env vars
    def _is_secure_key(key: str) -> bool:
        return any(
            key.endswith(suffix)
            for suffix in ("_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_CREDENTIAL")
        )

    try:
        from shoal.core.config import load_project_config

        project_cfg = load_project_config(git_root)
        if project_cfg and project_cfg.env:
            for k, v in project_cfg.env.items():
                if _is_secure_key(k):
                    secure_env[k] = v
                else:
                    session_env[k] = v
    except Exception:
        logger.debug("Failed to load project config", exc_info=True)

    if template_cfg:
        for k, v in template_cfg.env.items():
            if _is_secure_key(k):
                secure_env[k] = v
            else:
                session_env[k] = v

    if extra_env:
        for k, v in extra_env.items():
            if _is_secure_key(k):
                secure_env[k] = v
            else:
                session_env[k] = v

    if coordinator_config and coordinator_config.context_injection:
        session_env.update(coordinator_config.context_injection)

    if session_env:
        for key, value in session_env.items():
            await tmux.async_set_environment(tmux_session, key, value)
        # Apply env to the initial pane via fish set (tmux set-environment only affects new panes)
        initial_pane = await tmux.async_first_pane(tmux_session)
        for key, value in session_env.items():
            await tmux.async_send_keys(
                initial_pane,
                f"set -gx {shlex.quote(key)} {shlex.quote(value)}",
                enter=True,
            )

    # 3.4. Apply template git identity config
    if template_cfg:
        await _apply_template_git_config_async(template_cfg, tmux_session, work_dir)

    # 3.5. Run template setup_commands in initial pane
    if template_cfg and template_cfg.setup_commands:
        initial_pane = await tmux.async_first_pane(tmux_session)
        for cmd in template_cfg.setup_commands:
            await tmux.async_send_keys(initial_pane, cmd, enter=True)

    # 4. Run startup commands
    try:
        if template_cfg and template_cfg.windows:
            await _run_template_startup_async(
                template_cfg,
                tool_command=tool_command,
                work_dir=work_dir,
                root=git_root,
                branch_name=branch_name,
                session_name=session_name,
                tmux_session=tmux_session,
                worktree_name=worktree_name,
            )
        else:
            await _run_default_startup_commands_async(
                startup_commands,
                tool_command=tool_command,
                work_dir=work_dir,
                session_name=session_name,
                tmux_session=tmux_session,
            )
    except (ValueError, subprocess.CalledProcessError, TimeoutError) as exc:
        logger.warning("[%s] create: startup command failed: %s", session.id, exc)
        await _rollback_async(
            session_id=session.id,
            tmux_name=tmux_session,
            wt_path=wt_path,
            git_root=git_root,
        )
        raise StartupCommandError(
            f"Startup command failed: {exc}",
            session_id=session.id,
            operation="create",
        ) from exc

    # 4.5. Provision MCP servers (failures warn, don't block)
    if mcp_servers:
        provisioned = await _provision_mcp_servers(mcp_servers, session.id, tool, work_dir)
        if provisioned:
            logger.info("[%s] create: MCP provisioned: %s", session.id, provisioned)
            await _inject_mcp_socket_env_async(
                _mcp_socket_env_injection(provisioned, tool),
                tmux_session,
                session.id,
            )

    # 4.6. Sync skills into worktree (best-effort)
    if wt_path:
        await asyncio.to_thread(_sync_skills_to_worktree, git_root, wt_path, tool)

    # 5. Set pane title on the agent pane (first pane), not the active pane
    agent_pane = await tmux.async_first_pane(tmux_session)
    await tmux.async_set_pane_title(agent_pane, f"shoal:{session.id}")

    # 5.5. Spawn dreamer pane if enabled
    dreamer_pane_id = ""
    if dreamer_config and dreamer_config.enabled:
        try:
            # Split horizontally, detached, named 'dreamer'
            dreamer_cmd = (
                f"split-window -t {tmux_session} -h -d -n dreamer -c {shlex.quote(work_dir)}"
            )
            await tmux.async_run_command(dreamer_cmd)
            # Get the new dreamer pane ID
            panes = await tmux.async_list_panes(tmux_session)
            for pane in panes:
                if pane.get("title") == "dreamer":
                    dreamer_pane_id = pane.get("id", "")
                    break
            if dreamer_pane_id:
                await tmux.async_set_pane_title(
                    f"{tmux_session}:{dreamer_pane_id}", f"dreamer:{session.id}"
                )
                logger.info(
                    "[%s] create: dreamer pane spawned (id=%s)", session.id, dreamer_pane_id
                )
        except Exception as exc:
            logger.warning("[%s] create: failed to spawn dreamer pane: %s", session.id, exc)

    # 6. Capture PID + tmux coordinates + nvim socket

    updates: dict[str, object] = {"status": SessionStatus.running}

    pane_target = agent_pane
    pid = await tmux.async_pane_pid(pane_target)
    if pid:
        updates["pid"] = pid

    updated_runtime = session.runtime
    coordinates = await tmux.async_pane_coordinates(pane_target)
    if coordinates:
        tmux_session_id, tmux_window_id = coordinates
        updated_runtime = TmuxRuntimeState(
            session_name=tmux_session,
            session_id=tmux_session_id,
            window_id=tmux_window_id,
            nvim_socket=build_nvim_socket_path(tmux_session_id, tmux_window_id),
        )
    if updated_runtime != session.runtime:
        updates["runtime"] = updated_runtime

    if dreamer_pane_id:
        updates["dreamer_pane_id"] = dreamer_pane_id

    await update_session(session.id, **updates)

    logger.info("[%s] create: complete (tmux=%s)", session.id, tmux_session)

    # Re-fetch to return fully-updated state
    result = await get_session(session.id)
    assert result is not None

    await emit(LifecycleEvent.session_created, session=result)

    return result


async def fork_session_lifecycle(
    *,
    session_name: str,
    source_tool: str,
    source_path: str,
    source_branch: str,
    wt_path: str,
    work_dir: str,
    new_branch: str,
    tool_command: str,
    startup_commands: list[str],
    template_cfg: SessionTemplateConfig | None = None,
    worktree_name: str = "",
    mcp_servers: list[str] | None = None,
    parent_id: str = "",
    model: str | None = None,
) -> SessionState:
    """Fork a session with full rollback on failure.

    Same pattern as :func:`create_session_lifecycle` but for forks.
    Fixes the missing startup-command rollback in the previous fork path.

    Args:
        session_name: Name for the new session.
        source_tool: Tool identifier from the source session.
        source_path: Git root of the source session.
        source_branch: Branch name in the source session.
        wt_path: Path to the new git worktree.
        work_dir: Working directory inside the worktree.
        new_branch: Branch name for the fork.
        tool_command: Command to launch the tool (e.g. ``"pisces"``).
        startup_commands: Extra shell commands to run after tool launch.
        template_cfg: Optional template configuration to apply.
        worktree_name: Display name for the worktree.
        mcp_servers: MCP servers to provision.
        parent_id: ID of the parent session.
        model: Model to inject into the tool command (e.g. ``"z-ai/glm-5"``).

    Raises:
        SessionExistsError, TmuxSetupError, StartupCommandError, ValueError.
    """
    logger.info(
        "[%s] fork: starting (tool=%s, model=%s)", session_name, source_tool, model or "default"
    )

    # Inject --model flag into tool_command when model is specified
    tool_command = _inject_model_arg(tool_command, model)

    # 1. Create DB row
    try:
        session = await create_session(
            session_name,
            source_tool,
            source_path,
            wt_path,
            new_branch,
            parent_id=parent_id,
        )
    except ValueError as exc:
        if "already exists" in str(exc) or "collides" in str(exc):
            raise SessionExistsError(str(exc), session_id="", operation="fork") from exc
        raise

    from shoal.core.context import set_session_id

    set_session_id(session.id)

    tmux_session = session.tmux_runtime.session_name
    logger.info("[%s] fork: DB row created (id=%s)", session_name, session.id)

    # 2. Create tmux session
    try:
        await tmux.async_new_session(tmux_session, cwd=work_dir)
    except Exception as exc:
        logger.warning("[%s] fork: tmux.new_session failed: %s", session.id, exc)
        await _rollback_async(
            session_id=session.id,
            wt_path=wt_path,
            git_root=source_path,
        )
        raise TmuxSetupError(
            f"Failed to create tmux session: {exc}",
            session_id=session.id,
            operation="fork",
        ) from exc

    # 3. Set environment
    await tmux.async_set_environment(tmux_session, "SHOAL_SESSION_ID", session.id)
    await tmux.async_set_environment(tmux_session, "SHOAL_SESSION_NAME", session_name)
    if template_cfg:
        for key, value in template_cfg.env.items():
            await tmux.async_set_environment(tmux_session, key, value)
        # Apply env to the initial pane via fish set (tmux set-environment only affects new panes)
        if template_cfg.env:
            initial_pane = await tmux.async_first_pane(tmux_session)
            for key, value in template_cfg.env.items():
                await tmux.async_send_keys(
                    initial_pane,
                    f"set -gx {shlex.quote(key)} {shlex.quote(value)}",
                    enter=True,
                )

    # 3.4. Apply template git identity config
    if template_cfg:
        await _apply_template_git_config_async(template_cfg, tmux_session, work_dir)

    # 3.5. Run template setup_commands in initial pane
    # 3.5. Run template setup_commands in initial pane
    if template_cfg and template_cfg.setup_commands:
        initial_pane = await tmux.async_first_pane(tmux_session)
        for cmd in template_cfg.setup_commands:
            await tmux.async_send_keys(initial_pane, cmd, enter=True)

    # 4. Run startup commands — full rollback on failure (fixes previous gap)
    try:
        if template_cfg and template_cfg.windows:
            await _run_template_startup_async(
                template_cfg,
                tool_command=tool_command,
                work_dir=work_dir,
                root=source_path,
                branch_name=new_branch,
                session_name=session_name,
                tmux_session=tmux_session,
                worktree_name=worktree_name,
            )
        else:
            await _run_default_startup_commands_async(
                startup_commands,
                tool_command=tool_command,
                work_dir=work_dir,
                session_name=session_name,
                tmux_session=tmux_session,
            )
    except (ValueError, subprocess.CalledProcessError, TimeoutError) as exc:
        logger.warning("[%s] fork: startup command failed: %s", session.id, exc)
        await _rollback_async(
            session_id=session.id,
            tmux_name=tmux_session,
            wt_path=wt_path,
            git_root=source_path,
        )
        raise StartupCommandError(
            f"Startup command failed: {exc}",
            session_id=session.id,
            operation="fork",
        ) from exc

    # 4.5. Provision MCP servers (failures warn, don't block)
    if mcp_servers:
        provisioned = await _provision_mcp_servers(mcp_servers, session.id, source_tool, work_dir)
        if provisioned:
            logger.info("[%s] fork: MCP provisioned: %s", session.id, provisioned)
            await _inject_mcp_socket_env_async(
                _mcp_socket_env_injection(provisioned, source_tool),
                tmux_session,
                session.id,
            )

    # 5. Set pane title on the agent pane (first pane)
    fork_agent_pane = await tmux.async_first_pane(tmux_session)
    await tmux.async_set_pane_title(fork_agent_pane, f"shoal:{session.id}")

    # 6. Capture coordinates
    updates: dict[str, object] = {"status": SessionStatus.running}

    pane_target = fork_agent_pane
    pid = await tmux.async_pane_pid(pane_target)
    if pid:
        updates["pid"] = pid

    updated_runtime = session.runtime
    coordinates = await tmux.async_pane_coordinates(pane_target)
    if coordinates:
        tmux_session_id, tmux_window_id = coordinates
        updated_runtime = TmuxRuntimeState(
            session_name=tmux_session,
            session_id=tmux_session_id,
            window_id=tmux_window_id,
            nvim_socket=build_nvim_socket_path(tmux_session_id, tmux_window_id),
        )
    if updated_runtime != session.runtime:
        updates["runtime"] = updated_runtime

    await update_session(session.id, **updates)

    logger.info("[%s] fork: complete (tmux=%s)", session.id, tmux_session)
    result = await get_session(session.id)
    assert result is not None

    await emit(LifecycleEvent.session_forked, session=result)

    return result


async def kill_session_lifecycle(
    *,
    session_id: str,
    tmux_session: str,
    worktree: str = "",
    git_root: str = "",
    branch: str = "",
    remove_worktree: bool = False,
    force: bool = False,
) -> dict[str, bool]:
    """Kill a session and optionally remove its worktree.

    After killing the session, checks if any MCP servers used by this
    session have no remaining users and stops them.

    Returns a summary dict with keys: tmux_killed, worktree_removed,
    branch_deleted, db_deleted, mcp_stopped.

    Raises DirtyWorktreeError if worktree has uncommitted changes and
    force is False.
    """
    from shoal.core.context import set_session_id

    set_session_id(session_id)

    logger.info("[%s] kill: starting", session_id)
    summary: dict[str, bool] = {
        "tmux_killed": False,
        "worktree_removed": False,
        "branch_deleted": False,
        "db_deleted": False,
        "handoff_generated": False,
        "journal_archived": False,
        "mcp_stopped": False,
        "auto_committed": False,
    }

    # Snapshot MCP servers before deleting the session
    session = await get_session(session_id)
    mcp_names = list(session.mcp_servers) if session else []

    # 1. Kill runtime
    if session is not None:
        if await provider_for_session(session).async_kill(session):
            summary["tmux_killed"] = True
            logger.info("[%s] kill: runtime session killed", session_id)
    elif await tmux.async_has_session(tmux_session):
        await tmux.async_kill_session(tmux_session)
        summary["tmux_killed"] = True
        logger.info("[%s] kill: tmux session killed", session_id)

    # 1.5. Auto-commit dirty worktree if configured
    if session is not None and session.worktree:
        _ac_wt = session.worktree
        _wt_exists = await asyncio.to_thread(lambda: Path(_ac_wt).is_dir())
        _ac_on = _wt_exists and load_config().general.auto_commit
        if _ac_on and await git.async_worktree_is_dirty(_ac_wt):
            _commit_msg = (
                f"chore: auto-commit worktree for shoal session '{session.name}'\n\n"
                f"Branch: {session.branch}\nTool: {session.tool}"
            )
            try:
                await git.async_stage_all(_ac_wt)
                await git.async_commit(_ac_wt, _commit_msg)
                summary["auto_committed"] = True
                logger.info("[%s] kill: auto-committed worktree", session_id)
            except Exception:
                logger.warning("[%s] kill: auto-commit failed", session_id, exc_info=True)
    # 2. Optionally remove worktree + branch
    if remove_worktree and worktree and await asyncio.to_thread(lambda: Path(worktree).is_dir()):
        # Check for dirty worktree
        if await git.async_worktree_has_tracked_changes(worktree):
            if not force:
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "status", "--porcelain"],
                    cwd=worktree,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                dirty_output = result.stdout.strip()
                raise DirtyWorktreeError(
                    f"Worktree has uncommitted changes: {worktree}",
                    session_id=session_id,
                    dirty_files=dirty_output,
                )
            logger.warning("[%s] kill: forcing removal of dirty worktree", session_id)

        if await git.async_worktree_remove(git_root, worktree, force=True):
            summary["worktree_removed"] = True
            logger.info("[%s] kill: worktree removed", session_id)

        if (
            branch
            and branch not in ("main", "master")
            and await git.async_branch_delete(git_root, branch)
        ):
            summary["branch_deleted"] = True
            logger.info("[%s] kill: branch deleted", session_id)

    # 2.5. Emit kill event before DB deletion (session still available)
    if session:
        await emit(LifecycleEvent.session_killed, session=session)

    # 3. Generate handoff artifact (before DB deletion — needs transitions)
    if session:
        try:
            from shoal.core.db import get_db
            from shoal.core.journal import (
                generate_handoff,
                read_journal,
                write_handoff_artifact,
            )

            entries = await asyncio.to_thread(read_journal, session_id)
            handoff_db = await get_db()
            transitions = await handoff_db.get_status_transitions(session_id, limit=5)

            # Pull structured summaries from index when available.
            dreamer_summary = ""
            workflow_summary = ""
            try:
                from shoal.core.conversation_index import get_index

                idx = await get_index()
                ds = await idx.latest_summary(session_id, kind="summary")
                if ds and ds.get("summary"):
                    dreamer_summary = ds["summary"]
                ws = await idx.latest_summary(session_id, kind="workflow_summary")
                if ws and ws.get("summary"):
                    workflow_summary = ws["summary"]
            except Exception:  # noqa: S110
                pass  # index unavailable; proceed without structured summaries

            artifact = await asyncio.to_thread(
                generate_handoff,
                session,
                entries,
                transitions,
                dreamer_summary=dreamer_summary,
                workflow_summary=workflow_summary,
            )
            await asyncio.to_thread(write_handoff_artifact, session_id, artifact)
            summary["handoff_generated"] = True
            logger.info("[%s] kill: handoff artifact generated", session_id)
        except Exception:
            logger.warning("[%s] kill: failed to generate handoff", session_id, exc_info=True)

    # 4. Delete DB row
    await delete_session(session_id)
    summary["db_deleted"] = True
    logger.info("[%s] kill: DB row deleted", session_id)

    # 4.5. Archive journal (best-effort)
    try:
        from shoal.core.journal import archive_journal

        archived = await asyncio.to_thread(archive_journal, session_id)
        if archived:
            summary["journal_archived"] = True
            logger.info("[%s] kill: journal archived", session_id)
    except OSError:
        logger.warning("[%s] kill: failed to archive journal", session_id, exc_info=True)

    # 4. Stop orphaned MCP servers (no remaining sessions using them)
    if mcp_names:
        stopped = await _cleanup_orphaned_mcp_servers(mcp_names, session_id)
        if stopped:
            summary["mcp_stopped"] = True
            logger.info("[%s] kill: stopped orphaned MCP servers: %s", session_id, stopped)

    return summary


async def _cleanup_orphaned_mcp_servers(mcp_names: list[str], killed_session_id: str) -> list[str]:
    """Stop MCP servers that have no remaining sessions using them."""
    from shoal.services.mcp_pool import is_mcp_running, stop_mcp_server

    remaining_sessions = await list_sessions()
    stopped: list[str] = []

    for name in mcp_names:
        # Check if any remaining session still uses this MCP
        still_used = any(
            name in s.mcp_servers for s in remaining_sessions if s.id != killed_session_id
        )

        if not still_used and is_mcp_running(name):
            try:
                stop_mcp_server(name)
                stopped.append(name)
            except Exception as e:
                logger.warning("Failed to stop orphaned MCP '%s': %s", name, e)

    return stopped


async def reconcile_sessions() -> list[tuple[str, str, str]]:
    """Boot-time stale-DB reconciliation.

    1. Iterates non-stopped sessions and marks any whose tmux session has
       disappeared as stopped.
    2. Scans MCP pool sockets for dead processes and cleans up stale
       socket/PID files.

    Returns a list of ``(session_id, name, action)`` tuples for each
    reconciled session.
    """
    reconciled: list[tuple[str, str, str]] = []
    sessions = await list_sessions()

    for session in sessions:
        if session.status.value == "stopped":
            continue

        if not await provider_for_session(session).async_exists(session):
            from datetime import UTC, datetime

            await update_session(
                session.id,
                status=SessionStatus.stopped,
                last_activity=datetime.now(UTC),
            )
            action = f"marked stopped (was {session.status.value})"
            logger.info(
                "[%s] reconcile: %s — runtime gone",
                session.id,
                action,
            )
            reconciled.append((session.id, session.name, action))

    # Reconcile MCP pool — clean dead sockets/PIDs
    cleaned = reconcile_mcp_pool()
    reconciled.extend(("mcp", name, "cleaned dead MCP socket/PID") for name in cleaned)

    return reconciled


def reconcile_mcp_pool() -> list[str]:
    """Scan MCP pool for dead processes and clean up stale files."""
    from shoal.services.mcp_pool import is_mcp_running, mcp_pid_file, mcp_socket, read_pid

    # Use mcp_socket to get the socket dir (consistent with mcp_pool's data_dir)
    socket_dir = mcp_socket("").parent
    if not socket_dir.exists():
        return []

    cleaned: list[str] = []
    for sock_path in socket_dir.glob("*.sock"):
        name = sock_path.stem
        pid = read_pid(name)

        if pid is not None and not is_mcp_running(name):
            # Process is dead — clean up
            sock_path.unlink(missing_ok=True)
            mcp_pid_file(name).unlink(missing_ok=True)
            cleaned.append(name)
            logger.info("reconcile: cleaned dead MCP '%s' (pid: %d)", name, pid)
        elif pid is None:
            # Orphaned socket with no PID file
            sock_path.unlink(missing_ok=True)
            cleaned.append(name)
            logger.info("reconcile: cleaned orphaned MCP socket '%s'", name)

    return cleaned


async def complete_session(name: str, summary: str = "") -> SessionState:
    """Mark a session as complete.

    Sets completed_at, appends a journal entry, optionally auto-commits the
    worktree, emits the session_completed event, and returns the updated state.

    Raises:
        SessionNotFoundError: Session not found.
    """
    from datetime import UTC, datetime

    from shoal.core.db import get_db
    from shoal.core.journal import append_entry
    from shoal.core.state import find_by_name, get_session

    session_id = await find_by_name(name)
    if session_id is None:
        raise SessionNotFoundError(
            f"Session not found: {name}", session_id="", operation="complete"
        )

    state = await get_session(session_id)
    if state is None:
        raise SessionNotFoundError(
            f"Session not found: {name}", session_id=session_id, operation="complete"
        )

    state.completed_at = datetime.now(UTC)

    db = await get_db()
    await db.save_session(state)

    journal_body = (
        f"## Completion\n{summary}" if summary else "## Completion\nSession marked complete."
    )
    await asyncio.to_thread(append_entry, state.id, journal_body, source="lifecycle")

    # Auto-commit dirty worktree if configured (same pattern as kill_session_lifecycle)
    if state.worktree:
        _ac_wt = state.worktree
        _wt_exists = await asyncio.to_thread(lambda: Path(_ac_wt).is_dir())
        _ac_on = _wt_exists and load_config().general.auto_commit
        if _ac_on and await git.async_worktree_is_dirty(_ac_wt):
            _commit_msg = (
                f"chore: auto-commit worktree for shoal session '{state.name}'\n\n"
                f"Branch: {state.branch}\nTool: {state.tool}"
            )
            try:
                await git.async_stage_all(_ac_wt)
                await git.async_commit(_ac_wt, _commit_msg)
                logger.info("[%s] complete: auto-committed worktree", state.id)
            except Exception:
                logger.warning("[%s] complete: auto-commit failed", state.id, exc_info=True)

    await emit(LifecycleEvent.session_completed, session=state)
    return state


# ---------------------------------------------------------------------------
# Built-in hooks
# ---------------------------------------------------------------------------


async def _hook_journal_on_create(event: LifecycleEvent, **kwargs: Any) -> None:
    """Write an initial journal entry when a session is created."""
    session: SessionState | None = kwargs.get("session")
    if session is None:
        return
    from shoal.core.journal import append_entry, build_journal_metadata

    metadata = build_journal_metadata(session)
    await asyncio.to_thread(
        append_entry,
        session.id,
        f"Session **{session.name}** created (tool={session.tool})",
        source="lifecycle",
        metadata=metadata,
    )


async def _hook_fish_event(event: LifecycleEvent, **kwargs: Any) -> None:
    """Emit a fish shell event so users can react in their fish config.

    Fires ``emit shoal_<event> <session_name> [extra...]`` via fish -c.
    Best-effort — failures are logged and swallowed.
    """
    session: SessionState | None = kwargs.get("session")
    if session is None:
        return

    parts = ["emit", f"shoal_{event.value}", session.name]

    if event == LifecycleEvent.status_changed:
        old: SessionStatus | None = kwargs.get("old_status")
        new: SessionStatus | None = kwargs.get("new_status")
        if old is not None:
            parts.append(old.value)
        if new is not None:
            parts.append(new.value)

    fish_cmd = " ".join(parts)
    try:
        await asyncio.to_thread(
            subprocess.run,
            ["fish", "-c", fish_cmd],
            capture_output=True,
            check=False,
            timeout=5,
        )
    except FileNotFoundError:
        logger.debug("fish not found, skipping event emission")
    except Exception:
        logger.debug("fish event emission failed", exc_info=True)


async def _hook_record_status_transition(event: LifecycleEvent, **kwargs: Any) -> None:
    """Record a status transition in the database."""
    session: SessionState | None = kwargs.get("session")
    old_status: SessionStatus | None = kwargs.get("old_status")
    new_status: SessionStatus | None = kwargs.get("new_status")
    if session is None or old_status is None or new_status is None:
        return
    from shoal.core.db import get_db

    db = await get_db()
    await db.save_status_transition(
        session_id=session.id,
        from_status=old_status.value,
        to_status=new_status.value,
    )


async def _hook_journal_on_status_change(event: LifecycleEvent, **kwargs: Any) -> None:
    """Write a journal entry on status change."""
    session: SessionState | None = kwargs.get("session")
    old_status: SessionStatus | None = kwargs.get("old_status")
    new_status: SessionStatus | None = kwargs.get("new_status")
    if session is None or old_status is None or new_status is None:
        return
    from shoal.core.journal import append_entry

    await asyncio.to_thread(
        append_entry,
        session.id,
        f"Status: {old_status.value} → {new_status.value}",
        source="lifecycle",
    )


def _init_linear_hooks() -> None:
    """Register Linear integration hook if API key is available (idempotent)."""
    if "linear" in _registered:
        return
    _registered.add("linear")
    from shoal.services.linear_bridge import hook_linear_on_complete

    on(LifecycleEvent.session_completed, hook_linear_on_complete)


def _init_proactive_hooks() -> None:
    """Initialise the FsWatcher and ProactiveSupervisor if enabled (idempotent)."""
    if "proactive" in _registered:
        return
    _registered.add("proactive")
    from shoal.core.config import load_config

    cfg = load_config()
    if not cfg.proactive.enabled:
        return

    # Ensure singleton exists (started lazily on first add_path).
    from shoal.services.fs_watcher import get_fs_watcher, init_fs_watcher

    if get_fs_watcher() is None:
        init_fs_watcher()

    # Register per-session path hooks.
    on(LifecycleEvent.session_created, _hook_fs_watch_add)
    on(LifecycleEvent.session_forked, _hook_fs_watch_add)
    on(LifecycleEvent.session_killed, _hook_fs_watch_remove)

    # Register proactive supervisor.
    from shoal.core.config import load_robo_profile
    from shoal.services.proactive_supervisor import (
        get_proactive_supervisor,
        init_proactive_supervisor,
        register_proactive_hook,
    )

    supervisor = get_proactive_supervisor()
    if supervisor is None:
        robo_profile = load_robo_profile(cfg.robo.default_profile)
        supervisor = init_proactive_supervisor(robo_profile.proactive)
    register_proactive_hook(supervisor)


async def _hook_fs_watch_add(event: LifecycleEvent, **kwargs: Any) -> None:
    """Register the session worktree with the FsWatcher on session create."""
    from shoal.services.fs_watcher import get_fs_watcher

    watcher = get_fs_watcher()
    if watcher is None:
        return
    session = kwargs.get("session")
    if session is None:
        return
    from shoal.models.state import SessionState

    if not isinstance(session, SessionState):
        return

    # Lazily start the watcher loop on first session registration.
    if not watcher._running:
        await watcher.start()

    if session.worktree:
        from pathlib import Path

        wt_path = str(Path(session.path) / ".worktrees" / session.worktree)
        await watcher.add_path(wt_path, session.id, session.name)
    else:
        await watcher.add_path(session.path, session.id, session.name)


async def _hook_fs_watch_remove(event: LifecycleEvent, **kwargs: Any) -> None:
    """Deregister the session from the FsWatcher on kill."""
    from shoal.services.fs_watcher import get_fs_watcher

    watcher = get_fs_watcher()
    if watcher is None:
        return
    session = kwargs.get("session")
    if session is None:
        return
    from shoal.models.state import SessionState

    if not isinstance(session, SessionState):
        return
    await watcher.remove_path(session.id)


async def _hook_coordinator_on_complete(event: LifecycleEvent, **kwargs: Any) -> None:
    """Notify the parent (coordinator) session when a worker session completes."""
    session: SessionState | None = kwargs.get("session")
    if session is None or not session.parent_id:
        return
    from shoal.core.message_bus import send_message
    from shoal.core.state import get_session

    parent = await get_session(session.parent_id)
    if parent is None:
        return
    try:
        await send_message(
            from_session=session.name,
            to_session=parent.name,
            topic="worker_completed",
            payload=session.name,
            kind="event",
        )
    except Exception:
        logger.debug("coordinator notification failed (non-fatal)", exc_info=True)


def register_builtin_hooks() -> None:
    """Register the default set of lifecycle hooks (idempotent)."""
    if "builtin" in _registered:
        return
    _registered.add("builtin")
    on(LifecycleEvent.session_created, _hook_journal_on_create)
    on(LifecycleEvent.session_forked, _hook_journal_on_create)
    on(LifecycleEvent.status_changed, _hook_record_status_transition)
    on(LifecycleEvent.status_changed, _hook_journal_on_status_change)
    on(LifecycleEvent.session_completed, _hook_coordinator_on_complete)
    _init_linear_hooks()
    for evt in LifecycleEvent:
        on(evt, _hook_fish_event)
    _init_proactive_hooks()


def register_project_hooks() -> None:
    """Register project-local lifecycle hooks from ``.shoal/hooks.toml`` (idempotent)."""
    from shoal.core.config import load_project_hooks

    for entry in load_project_hooks():
        _register_one_project_hook(entry)


def _register_one_project_hook(entry: ProjectHookEntry) -> None:
    """Build and register one async callback for a ProjectHookEntry."""
    import subprocess as _sp

    key = f"project:{entry.event}:{entry.when_status}:{entry.command}"
    if key in _registered:
        return
    _registered.add(key)

    event = LifecycleEvent(entry.event)
    when_status: str = entry.when_status
    command: str = entry.command

    async def _project_hook(evt: LifecycleEvent, **kwargs: Any) -> None:
        session = kwargs.get("session")
        new_status = kwargs.get("new_status")
        old_status = kwargs.get("old_status")

        # Apply when_status filter for status_changed events.
        if (
            when_status
            and evt == LifecycleEvent.status_changed
            and (new_status is None or str(new_status.value) != when_status)
        ):
            return

        env = dict(os.environ)
        env["SHOAL_EVENT"] = evt.value
        if session is not None:
            env["SHOAL_SESSION_ID"] = getattr(session, "id", "")
            env["SHOAL_SESSION_NAME"] = getattr(session, "name", "")
        if old_status is not None:
            env["SHOAL_OLD_STATUS"] = str(old_status.value)
        if new_status is not None:
            env["SHOAL_NEW_STATUS"] = str(new_status.value)

        try:
            await asyncio.to_thread(  # noqa: S604 — shell=True is intentional; command is user-authored
                _sp.run,
                command,
                shell=True,  # nosec B604 — user-authored hook command; intentional
                env=env,
                timeout=30,
            )
        except Exception:
            logger.exception("Project hook failed for event %s: %s", evt, command)

    on(event, _project_hook)
