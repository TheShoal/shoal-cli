"""Tmux-backed runtime provider."""

from __future__ import annotations

import asyncio
import os
import shlex
import tempfile

from shoal.core import tmux
from shoal.core.session_names import build_tmux_session_name
from shoal.integrations.fish.prompt import escape_for_fish
from shoal.models.config import SessionTemplateConfig, ToolConfig
from shoal.models.state import RuntimeKind, RuntimeState, SessionState, TmuxRuntimeState
from shoal.services.runtime_models import RuntimeObservation


def _build_nvim_socket_path(session_id: str, window_id: str) -> str:
    base = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return f"{base}/nvim-{session_id}-{window_id}.sock"


def _runtime(session: SessionState) -> TmuxRuntimeState:
    return session.tmux_runtime


# Threshold for long prompt handling (characters)
# Above this length, use file-based delivery to avoid tmux mangling
LONG_PROMPT_THRESHOLD = 500


def _send_long_prompt_via_file(pane_target: str, text: str) -> None:
    """Send a long prompt via a temporary file to avoid tmux mangling.

    Writes the text to a temp file and sends a command to source/execute it.
    """
    # Write prompt to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write(text)
        temp_path = f.name

    try:
        # Send command to execute the file content
        # Using 'fish -c' to execute in fish shell context
        tmux.send_keys(pane_target, f"fish -c 'source {shlex.quote(temp_path)}'", enter=True)
    finally:
        # Clean up temp file asynchronously would be ideal,
        # but tmux send_keys is synchronous so we leave it for gc
        pass


def _tool_executable(tool_command: str) -> str:
    if not tool_command.strip():
        return ""

    try:
        parts = shlex.split(tool_command)
    except ValueError:
        parts = tool_command.strip().split()
    return os.path.basename(parts[0]) if parts else ""


def _find_session_tool_pane(
    panes: list[dict[str, str]],
    pane_title: str,
    tool_command: str,
) -> str | None:
    """Pick the pane tagged for this session, with safe fallbacks."""
    tool_exe = _tool_executable(tool_command)

    for pane in panes:
        if pane.get("title") == pane_title:
            return pane.get("id")

    if tool_exe:
        command_matches = [pane for pane in panes if pane.get("command") == tool_exe]
        if len(command_matches) == 1:
            return command_matches[0].get("id")
        for pane in command_matches:
            if pane.get("active") == "1":
                return pane.get("id")

    if len(panes) == 1:
        return panes[0].get("id")
    return None


class TmuxRuntimeProvider:
    kind: RuntimeKind = RuntimeKind.tmux

    def payload(self, runtime: RuntimeState) -> dict[str, object]:
        return runtime.model_dump(mode="json")

    def summary(self, runtime: RuntimeState) -> dict[str, str]:
        return {
            "session": runtime.session_name,
            "window": runtime.window_id or "",
            "nvim_socket": runtime.nvim_socket or "",
        }

    def exists(self, session: SessionState) -> bool:
        runtime = _runtime(session)
        return tmux.has_session(runtime.session_name)

    async def async_exists(self, session: SessionState) -> bool:
        runtime = _runtime(session)
        return await tmux.async_has_session(runtime.session_name)

    def attach(self, session: SessionState) -> None:
        runtime = _runtime(session)
        if tmux.is_inside_tmux():
            tmux.switch_client(runtime.session_name)
        else:
            tmux.attach_session(runtime.session_name)

    def capture_output(
        self, session: SessionState, *, lines: int, include_ansi: bool = False
    ) -> str:
        runtime = _runtime(session)
        pane_target = tmux.preferred_pane(runtime.session_name, f"shoal:{session.id}")
        return tmux.capture_pane(pane_target, lines=lines, include_ansi=include_ansi)

    async def async_capture_output(
        self, session: SessionState, *, lines: int, include_ansi: bool = False
    ) -> str:
        runtime = _runtime(session)
        pane_target = await tmux.async_preferred_pane(runtime.session_name, f"shoal:{session.id}")
        return await tmux.async_capture_pane(pane_target, lines=lines, include_ansi=include_ansi)

    async def async_send_input(
        self,
        session: SessionState,
        text: str,
        *,
        enter: bool = True,
        delay: float = 0.0,
    ) -> None:
        runtime = _runtime(session)
        pane_target = await tmux.async_preferred_pane(runtime.session_name, f"shoal:{session.id}")

        # Detect shell type for proper escaping
        panes = await tmux.async_list_panes(runtime.session_name)
        pane_command = ""
        for pane in panes:
            if pane.get("id") == pane_target or pane.get("title") == f"shoal:{session.id}":
                pane_command = pane.get("command", "")
                break

        is_fish = "fish" in pane_command.lower()

        # Handle long prompts via file to avoid tmux mangling
        if len(text) > LONG_PROMPT_THRESHOLD:
            if is_fish:
                text = escape_for_fish(text)
            await asyncio.to_thread(_send_long_prompt_via_file, pane_target, text)
            if enter:
                await asyncio.to_thread(tmux.send_keys, pane_target, "Enter", enter=True)
            return

        # Apply fish escaping if needed
        if is_fish:
            text = escape_for_fish(text)

        await tmux.async_send_keys(pane_target, text, enter=enter, delay=delay)

    async def async_wait_for_ready(
        self, session: SessionState, tool_config: ToolConfig, *, ready_timeout: float
    ) -> None:
        runtime = _runtime(session)
        pane_target = await tmux.async_preferred_pane(runtime.session_name, f"shoal:{session.id}")
        _ = await tmux.async_wait_for_ready(pane_target, tool_config, timeout=ready_timeout)

    async def async_rename(self, session: SessionState, new_name: str) -> RuntimeState:
        runtime = _runtime(session)
        new_tmux_name = build_tmux_session_name(new_name)
        if tmux.has_session(runtime.session_name):
            await asyncio.to_thread(tmux.rename_session, runtime.session_name, new_tmux_name)
        return runtime.model_copy(update={"session_name": new_tmux_name})

    async def async_kill(self, session: SessionState) -> bool:
        runtime = _runtime(session)
        if not await tmux.async_has_session(runtime.session_name):
            return False
        await tmux.async_kill_session(runtime.session_name)
        return True

    async def async_observe(
        self, session: SessionState, tool_config: ToolConfig, *, lines: int
    ) -> RuntimeObservation:
        runtime = _runtime(session)
        if not await tmux.async_has_session(runtime.session_name):
            return RuntimeObservation(alive=False, runtime=runtime)

        panes = await tmux.async_list_panes(runtime.session_name)
        pane_target = _find_session_tool_pane(panes, f"shoal:{session.id}", tool_config.command)
        if not pane_target:
            return RuntimeObservation(alive=True, runtime=runtime)

        output = await tmux.async_capture_pane(pane_target, lines=lines)
        pid = await tmux.async_pane_pid(pane_target)
        updated_runtime = runtime
        coordinates = await tmux.async_pane_coordinates(pane_target)
        if coordinates:
            session_id, window_id = coordinates
            socket = _build_nvim_socket_path(session_id, window_id)
            updated_runtime = runtime.model_copy(
                update={
                    "session_id": session_id,
                    "window_id": window_id,
                    "nvim_socket": socket,
                }
            )

        return RuntimeObservation(
            alive=True,
            output=output,
            pid=pid,
            runtime=updated_runtime,
        )

    async def async_apply_template_startup(
        self,
        template: SessionTemplateConfig,
        *,
        tool_command: str,
        work_dir: str,
        root: str,
        branch_name: str,
        session_name: str,
        worktree_name: str,
        runtime: RuntimeState,
    ) -> None:
        if not template.windows:
            return

        context = {
            "tool_command": tool_command,
            "work_dir": work_dir,
            "git_root": root,
            "session_name": session_name,
            "tmux_session": runtime.session_name,
            "branch_name": branch_name,
            "worktree": worktree_name,
            "template_name": template.name,
        }
        focus_window_target = ""
        window_base, pane_base = await tmux.async_server_base_indices()

        for window_index, window in enumerate(template.windows):
            window_target = f"{runtime.session_name}:{window_index + window_base}"
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
                cmd = f"new-window -t {runtime.session_name}"
                if window_name:
                    cmd += f" -n {shlex.quote(window_name)}"
                cmd += f" -c {shlex.quote(window_cwd)}"
                await tmux.async_run_command(cmd)

            if window.focus and not focus_window_target:
                focus_window_target = window_target

            for pane_index, pane in enumerate(window.panes):
                pane_target = f"{window_target}.{pane_index + pane_base}"
                if pane_index == 0:
                    if window_cwd and window_cwd != work_dir:
                        await tmux.async_send_keys(pane_target, f"cd {shlex.quote(window_cwd)}")
                else:
                    split_type = "down" if pane.split == "root" else pane.split
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
                await tmux.async_run_command(
                    f"select-layout -t {window_target} {shlex.quote(layout)}"
                )

        if focus_window_target:
            await tmux.async_run_command(f"select-window -t {focus_window_target}")

    async def async_apply_default_startup(
        self,
        startup_commands: list[str],
        *,
        tool_command: str,
        work_dir: str,
        session_name: str,
        runtime: RuntimeState,
    ) -> None:
        for cmd in startup_commands:
            try:
                interpolated = cmd.format(
                    tool_command=tool_command,
                    work_dir=work_dir,
                    session_name=session_name,
                    tmux_session=runtime.session_name,
                )
            except KeyError:
                continue
            await tmux.async_run_command(interpolated)


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
    except KeyError as exc:
        raise ValueError(f"Missing template variable {exc} in {field_name}: {raw}") from None
