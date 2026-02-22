"""Session lifecycle orchestration — shared by CLI and API.

Centralises create / fork / kill / reconcile logic so that both
``cli/session.py`` and ``api/server.py`` share a single rollback
sequence and startup-command execution path.
"""

from __future__ import annotations

import logging
import shlex
import subprocess
from pathlib import Path

from shoal.core import git, tmux
from shoal.core.state import (
    build_nvim_socket_path,
    create_session,
    delete_session,
    get_session,
    list_sessions,
    update_session,
)
from shoal.models.config import SessionTemplateConfig
from shoal.models.state import SessionState, SessionStatus

logger = logging.getLogger("shoal.lifecycle")


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

    if wt_path and Path(wt_path).exists():
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

    for window_index, window in enumerate(template.windows):
        window_target = f"{tmux_session}:{window_index}"
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
            pane_target = f"{window_target}.{pane_index}"

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

    for window_index, window in enumerate(template.windows):
        window_target = f"{tmux_session}:{window_index}"
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
            pane_target = f"{window_target}.{pane_index}"

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


# ---------------------------------------------------------------------------
# Lifecycle operations
# ---------------------------------------------------------------------------


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
    logger.info("[%s] create: starting (tool=%s)", session_name, tool)

    # 1. Create DB row
    try:
        session = await create_session(session_name, tool, git_root, wt_path, branch_name)
    except ValueError as exc:
        if "already exists" in str(exc) or "collides" in str(exc):
            raise SessionExistsError(str(exc), session_id="", operation="create") from exc
        raise

    tmux_session = session.tmux_session
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

    # 3. Set environment variables
    await tmux.async_set_environment(tmux_session, "SHOAL_SESSION_ID", session.id)
    await tmux.async_set_environment(tmux_session, "SHOAL_SESSION_NAME", session_name)

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

    # 5. Set pane title
    await tmux.async_set_pane_title(tmux_session, f"shoal:{session.id}")

    # 6. Capture PID + tmux coordinates + nvim socket
    updates: dict[str, object] = {"status": SessionStatus.running}

    pane_target = await tmux.async_preferred_pane(tmux_session, f"shoal:{session.id}")
    pid = await tmux.async_pane_pid(pane_target)
    if pid:
        updates["pid"] = pid

    coordinates = await tmux.async_pane_coordinates(pane_target)
    if coordinates:
        tmux_session_id, tmux_window_id = coordinates
        updates["tmux_session_id"] = tmux_session_id
        updates["tmux_window"] = tmux_window_id
        updates["nvim_socket"] = build_nvim_socket_path(tmux_session_id, tmux_window_id)

    await update_session(session.id, **updates)

    logger.info("[%s] create: complete (tmux=%s)", session.id, tmux_session)

    # Re-fetch to return fully-updated state
    result = await get_session(session.id)
    assert result is not None
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
) -> SessionState:
    """Fork a session with full rollback on failure.

    Same pattern as :func:`create_session_lifecycle` but for forks.
    Fixes the missing startup-command rollback in the previous fork path.

    Raises:
        SessionExistsError, TmuxSetupError, StartupCommandError, ValueError.
    """
    logger.info("[%s] fork: starting (tool=%s)", session_name, source_tool)

    # 1. Create DB row
    try:
        session = await create_session(
            session_name,
            source_tool,
            source_path,
            wt_path,
            new_branch,
        )
    except ValueError as exc:
        if "already exists" in str(exc) or "collides" in str(exc):
            raise SessionExistsError(str(exc), session_id="", operation="fork") from exc
        raise

    tmux_session = session.tmux_session
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

    # 5. Set pane title
    await tmux.async_set_pane_title(tmux_session, f"shoal:{session.id}")

    # 6. Capture coordinates
    updates: dict[str, object] = {"status": SessionStatus.running}

    pane_target = await tmux.async_preferred_pane(tmux_session, f"shoal:{session.id}")
    pid = await tmux.async_pane_pid(pane_target)
    if pid:
        updates["pid"] = pid

    coordinates = await tmux.async_pane_coordinates(pane_target)
    if coordinates:
        tmux_session_id, tmux_window_id = coordinates
        updates["tmux_session_id"] = tmux_session_id
        updates["tmux_window"] = tmux_window_id
        updates["nvim_socket"] = build_nvim_socket_path(tmux_session_id, tmux_window_id)

    await update_session(session.id, **updates)

    logger.info("[%s] fork: complete (tmux=%s)", session.id, tmux_session)
    result = await get_session(session.id)
    assert result is not None
    return result


async def kill_session_lifecycle(
    *,
    session_id: str,
    tmux_session: str,
    worktree: str = "",
    git_root: str = "",
    branch: str = "",
    remove_worktree: bool = False,
) -> dict[str, bool]:
    """Kill a session and optionally remove its worktree.

    After killing the session, checks if any MCP servers used by this
    session have no remaining users and stops them.

    Returns a summary dict with keys: tmux_killed, worktree_removed,
    branch_deleted, db_deleted, mcp_stopped.
    """
    logger.info("[%s] kill: starting", session_id)
    summary: dict[str, bool] = {
        "tmux_killed": False,
        "worktree_removed": False,
        "branch_deleted": False,
        "db_deleted": False,
        "mcp_stopped": False,
    }

    # Snapshot MCP servers before deleting the session
    session = await get_session(session_id)
    mcp_names = list(session.mcp_servers) if session else []

    # 1. Kill tmux
    if await tmux.async_has_session(tmux_session):
        await tmux.async_kill_session(tmux_session)
        summary["tmux_killed"] = True
        logger.info("[%s] kill: tmux session killed", session_id)

    # 2. Optionally remove worktree + branch
    if remove_worktree and worktree and Path(worktree).is_dir():
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

    # 3. Delete DB row
    await delete_session(session_id)
    summary["db_deleted"] = True
    logger.info("[%s] kill: DB row deleted", session_id)

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

        if not await tmux.async_has_session(session.tmux_session):
            from datetime import UTC, datetime

            await update_session(
                session.id,
                status=SessionStatus.stopped,
                last_activity=datetime.now(UTC),
            )
            action = f"marked stopped (was {session.status.value})"
            logger.info(
                "[%s] reconcile: %s — tmux session gone",
                session.id,
                action,
            )
            reconciled.append((session.id, session.name, action))

    # Reconcile MCP pool — clean dead sockets/PIDs
    cleaned = _reconcile_mcp_pool()
    for name in cleaned:
        reconciled.append(("mcp", name, "cleaned dead MCP socket/PID"))

    return reconciled


def _reconcile_mcp_pool() -> list[str]:
    """Scan MCP pool for dead processes and clean up stale files."""
    from shoal.services.mcp_pool import is_mcp_running, mcp_pid_file, mcp_socket, read_pid

    # Use mcp_socket to get the socket dir (consistent with mcp_pool's state_dir)
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
