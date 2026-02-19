"""Session management commands: new, ls, attach, detach, fork, kill, status, popup."""

from __future__ import annotations

import asyncio
import re
import shlex
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from shoal.core import git, tmux
from shoal.core.config import config_dir, ensure_dirs, load_config, load_template, load_tool_config
from shoal.core.db import with_db
from shoal.core.state import (
    build_tmux_session_name,
    _get_tool_icon,
    _resolve_session_interactive_impl,
    create_session,
    delete_session,
    find_by_name,
    is_shoal_tmux_session_name,
    get_session,
    get_status_style,
    list_sessions,
    touch_session,
    update_session,
)
from shoal.core.theme import (
    Colors,
    Icons,
    Symbols,
    create_panel,
    create_table,
    get_status_icon,
)
from shoal.models.state import SessionStatus

console = Console()

ALLOWED_BRANCH_CATEGORIES = ("feat", "fix", "bug", "chore", "docs", "refactor", "test")


def _infer_branch_name(worktree_name: str) -> str:
    """Infer branch name from worktree name.

    If the worktree name contains a '/', use it as-is (assumes it has a prefix like fix/, feat/, chore/).
    Otherwise, prepend 'feat/' as the default prefix.

    Examples:
        fix/tmux-status -> fix/tmux-status
        chore/cleanup -> chore/cleanup
        tmux-status -> feat/tmux-status
        my-feature -> feat/my-feature
    """
    if "/" in worktree_name:
        return worktree_name
    return f"feat/{worktree_name}"


def _validate_category_slug_branch(branch_name: str) -> None:
    categories = "|".join(ALLOWED_BRANCH_CATEGORIES)
    pattern = rf"^({categories})/[a-z0-9][a-z0-9-]*$"
    if re.match(pattern, branch_name):
        return
    allowed = ", ".join(ALLOWED_BRANCH_CATEGORIES)
    raise ValueError(
        "Branch name must follow category/slug (for example: feat/my-change) "
        f"with category in: {allowed}"
    )


def _branch_name_for_worktree(worktree_name: str) -> str:
    branch_name = _infer_branch_name(worktree_name)
    _validate_category_slug_branch(branch_name)
    return branch_name


def add(
    path: Annotated[str | None, typer.Argument(help="Project directory")] = None,
    tool: Annotated[str | None, typer.Option("-t", "--tool", help="AI tool to use")] = None,
    template: Annotated[
        str | None, typer.Option("--template", help="Session template name")
    ] = None,
    worktree: Annotated[
        str | None, typer.Option("-w", "--worktree", help="Create a git worktree")
    ] = None,
    branch: Annotated[bool, typer.Option("-b", "--branch", help="Create a new branch")] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview without creating session")
    ] = False,
    name: Annotated[str | None, typer.Option("-n", "--name", help="Session name")] = None,
) -> None:
    """Create a new session."""
    asyncio.run(with_db(_add_impl(path, tool, template, worktree, branch, dry_run, name)))


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
            console.print(
                f"[yellow]Warning: Skipping startup command with missing variable {e}: {cmd}[/yellow]"
            )
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
    template,
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
    template,
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


async def _add_impl(path, tool, template, worktree, branch, dry_run, name):
    ensure_dirs()
    cfg = load_config()
    template_cfg = None

    if template:
        try:
            template_cfg = load_template(template)
        except FileNotFoundError:
            console.print(f"[red]Error: Template '{template}' not found[/red]")
            templates_dir = config_dir() / "templates"
            console.print(f"[dim]Expected config at: {templates_dir / f'{template}.toml'}[/dim]")
            raise typer.Exit(1) from None
        except ValueError as e:
            console.print(f"[red]Error: Invalid template '{template}'[/red]")
            console.print(f"[dim]{e}[/dim]")
            raise typer.Exit(1) from None

        if not tool and template_cfg.tool:
            tool = template_cfg.tool

        if not worktree and template_cfg.worktree.name:
            try:
                worktree = template_cfg.worktree.name.format(template_name=template_cfg.name)
            except KeyError as e:
                console.print(f"[red]Error: Template worktree has unsupported variable {e}[/red]")
                console.print(
                    "[dim]Use --worktree for dynamic names or only {template_name} in template.worktree.name[/dim]"
                )
                raise typer.Exit(1) from None

        if template_cfg.worktree.create_branch:
            branch = True

    resolved_path = Path(path).resolve() if path else Path.cwd().resolve()

    if not tool:
        tool = cfg.general.default_tool

    # Validate tool config
    tool_config_path = config_dir() / "tools" / f"{tool}.toml"
    if not tool_config_path.exists():
        console.print(f"[red]Error: Unknown tool '{tool}'[/red]")
        console.print(f"[dim]Expected config at: {tool_config_path}[/dim]")
        console.print()
        console.print("[yellow]Available tools:[/yellow]")
        tools_dir = config_dir() / "tools"
        if tools_dir.exists():
            for f in sorted(tools_dir.glob("*.toml")):
                console.print(f"  • {f.stem}")
        else:
            console.print("  [dim](none configured)[/dim]")
        console.print()
        console.print("[yellow]To create a tool config:[/yellow]")
        console.print(f"  mkdir -p {tools_dir}")
        console.print(f"  cat > {tool_config_path} <<EOF")
        console.print("  [tool]")
        console.print(f'  name = "{tool}"')
        console.print(f'  command = "{tool}"  # or full path')
        console.print("  EOF")
        raise typer.Exit(1)

    # Validate git repo
    if not git.is_git_repo(str(resolved_path)):
        console.print("[red]Error: Not a git repository[/red]")
        console.print(f"[dim]Path: {resolved_path}[/dim]")
        console.print()
        console.print("[yellow]Shoal requires a git repository to track sessions.[/yellow]")
        console.print("Run one of the following:")
        console.print(f"  cd {resolved_path} && git init")
        console.print("  shoal new <path-to-git-repo>")
        raise typer.Exit(1)

    root = git.git_root(str(resolved_path))
    work_dir = str(resolved_path)
    branch_name = ""

    wt_path = ""
    if worktree:
        wt_dir_name = worktree.replace("/", "-")
        wt_path = str(Path(root) / ".worktrees" / wt_dir_name)

        if Path(wt_path).exists():
            console.print("[red]Error: Worktree already exists[/red]")
            console.print(f"[dim]Path: {wt_path}[/dim]")
            console.print()
            console.print("[yellow]Options:[/yellow]")
            console.print("  • Attach to existing worktree: shoal attach")
            console.print(f"  • Use a different worktree name: shoal new -w {worktree}-v2")
            console.print(f"  • Remove existing worktree: rm -rf {wt_path}")
            raise typer.Exit(1)

        if branch:
            try:
                branch_name = _branch_name_for_worktree(worktree)
            except ValueError as e:
                console.print(f"[red]Error: {e}[/red]")
                raise typer.Exit(1) from None
        else:
            branch_name = git.current_branch(str(resolved_path))

        work_dir = wt_path
    else:
        branch_name = git.current_branch(str(resolved_path))

    # Session name
    session_name = name
    if not session_name:
        project_name = Path(root).name
        if worktree:
            wt_label = worktree.replace("/", "-")
            session_name = f"{project_name}/{wt_label}"
        else:
            session_name = project_name

    # Check name collision
    if await find_by_name(session_name):
        console.print(f"[red]Error: Session '{session_name}' already exists[/red]")
        console.print()
        console.print("[yellow]Actionable suggestions:[/yellow]")
        console.print(f"  • Attach to existing: [bold]shoal attach {session_name}[/bold]")
        console.print(f"  • Use unique name:    [bold]shoal new -n {session_name}-v2[/bold]")
        console.print(f"  • Kill existing:      [bold]shoal kill {session_name}[/bold]")
        raise typer.Exit(1)

    tool_cfg = load_tool_config(tool)
    tmux_session = build_tmux_session_name(session_name)

    if dry_run:
        console.print("[bold cyan]Dry run: no changes applied[/bold cyan]")
        console.print(f"  Session: {session_name}")
        console.print(f"  Tool: {tool}")
        console.print(f"  Branch: {branch_name}")
        if worktree:
            console.print(f"  Worktree: {work_dir}")
            console.print(f"  Worktree dir name: {worktree.replace('/', '-')}")
        else:
            console.print(f"  Directory: {work_dir}")
        console.print(f"  Tmux: {tmux_session}")
        if template_cfg:
            console.print(f"  Template: {template_cfg.name}")

        try:
            if template_cfg and template_cfg.windows:
                startup_preview = _preview_template_startup(
                    template_cfg,
                    tool_command=tool_cfg.command,
                    work_dir=work_dir,
                    root=root,
                    branch_name=branch_name,
                    session_name=session_name,
                    tmux_session=tmux_session,
                    worktree_name=worktree or "",
                )
            else:
                startup_preview = _preview_default_startup_commands(
                    cfg.tmux.startup_commands,
                    tool_command=tool_cfg.command,
                    work_dir=work_dir,
                    session_name=session_name,
                    tmux_session=tmux_session,
                )
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1) from None

        console.print()
        console.print("[bold]Planned tmux actions:[/bold]")
        if startup_preview:
            for cmd in startup_preview:
                console.print(f"  - tmux {cmd}")
        else:
            console.print("  - [dim](none)[/dim]")
        return

    if worktree:
        Path(root, ".worktrees").mkdir(parents=True, exist_ok=True)
        if branch:
            git.worktree_add(root, wt_path, branch=branch_name)
        else:
            git.worktree_add(root, wt_path)
            branch_name = git.current_branch(wt_path)

    # Create session state
    try:
        session = await create_session(session_name, tool, root, work_dir, branch_name)
    except ValueError as e:
        console.print(f"[red]Invalid session name: {e}[/red]")
        raise typer.Exit(1) from None

    tmux_session = session.tmux_session

    # Create tmux session
    try:
        tmux.new_session(tmux_session, cwd=work_dir)
    except Exception as e:
        console.print("[red]Error: Failed to create tmux session[/red]")
        console.print(f"[dim]{e}[/dim]")
        console.print()
        console.print("[yellow]Troubleshooting:[/yellow]")
        console.print("  • Check if tmux is installed: which tmux")
        console.print("  • Check if tmux server is responsive: tmux ls")
        console.print(f"  • Verify working directory exists: ls {work_dir}")
        await delete_session(session.id)
        raise typer.Exit(1) from None

    tmux.set_environment(tmux_session, "SHOAL_SESSION_ID", session.id)
    tmux.set_environment(tmux_session, "SHOAL_SESSION_NAME", session_name)

    # Run startup commands
    try:
        if template_cfg and template_cfg.windows:
            _run_template_startup(
                template_cfg,
                tool_command=tool_cfg.command,
                work_dir=work_dir,
                root=root,
                branch_name=branch_name,
                session_name=session_name,
                tmux_session=tmux_session,
                worktree_name=worktree or "",
            )
        else:
            _run_default_startup_commands(
                cfg.tmux.startup_commands,
                tool_command=tool_cfg.command,
                work_dir=work_dir,
                session_name=session_name,
                tmux_session=tmux_session,
            )
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        await delete_session(session.id)
        tmux.kill_session(tmux_session)
        raise typer.Exit(1) from None

    tmux.set_pane_title(tmux_session, f"shoal:{session.id}")

    # Update state
    await update_session(session.id, status=SessionStatus.running)

    pane = tmux.pane_pid(tmux.preferred_pane(tmux_session, f"shoal:{session.id}"))
    if pane:
        await update_session(session.id, pid=pane)

    console.print(
        f"{tool_cfg.icon} Session '{session_name}' created (id: {session.id}, tool: {tool})"
    )
    if worktree:
        console.print(f"  Worktree: {work_dir}")
        console.print(f"  Branch: {branch_name}")
    if template_cfg:
        console.print(f"  Template: {template_cfg.name}")
    console.print(f"  Tmux: {tmux_session}")
    console.print()
    console.print(f"Attach with: shoal attach {session_name}")


def ls(
    format: Annotated[
        str | None,
        typer.Option(
            "--format",
            "-f",
            help="Output format: default (rich table) or plain (names only for completions)",
        ),
    ] = None,
) -> None:
    """List all sessions."""
    asyncio.run(with_db(_ls_impl(format)))


async def _ls_impl(format):
    ensure_dirs()
    sessions = await list_sessions()

    if format == "plain":
        for session in sessions:
            console.print(session.name)
        return

    if not sessions:
        console.print("No sessions")
        return

    # Group sessions by path

    from collections import defaultdict

    groups = defaultdict(list)
    for s in sessions:
        groups[s.path].append(s)

    # Sort paths alphabetically
    sorted_paths = sorted(groups.keys())

    for path in sorted_paths:
        group_sessions = groups[path]
        display_project = path.replace(str(Path.home()), "~")

        table = create_table(padding=(0, 1), collapse_padding=True)
        table.add_column("ID", style="dim", width=8)
        table.add_column("NAME", width=25)
        table.add_column("TOOL", width=12)
        table.add_column("STATUS", width=20)
        table.add_column("BRANCH", width=30)
        table.add_column("WORKTREE")

        # Sort sessions within group by name
        for s in sorted(group_sessions, key=lambda x: x.name):
            icon = _get_tool_icon(s.tool)

            # Check if it's a ghost session
            is_ghost = False
            if s.status.value != "stopped" and not tmux.has_session(s.tmux_session):
                is_ghost = True

            status_style = get_status_style(s.status.value)

            status_text = (
                f"[{status_style}]{s.status.value}[/{status_style}]"
                if status_style
                else s.status.value
            )

            if is_ghost:
                status_text = (
                    f"[bold red]{Icons.GHOST} ghost[/bold red] [dim]({s.status.value})[/dim]"
                )

            wt_display = ""
            if s.worktree:
                wt_display = s.worktree.replace(path, ".").replace(str(Path.home()), "~")
            else:
                wt_display = "[dim](root)[/dim]"

            table.add_row(
                s.id,
                f"{icon} [bold]{s.name}[/bold]",
                s.tool,
                status_text,
                f"[cyan]{s.branch or '-'}[/cyan]",
                wt_display,
            )

        console.print(
            create_panel(
                table,
                title=f"[bold blue]{Icons.SESSION} {display_project}[/bold blue]",
                primary=True,
                title_align="left",
                padding=(0, 1),
            )
        )


def attach(
    session: Annotated[str | None, typer.Argument(help="Session name or ID")] = None,
) -> None:
    """Attach to a session."""
    asyncio.run(with_db(_attach_impl(session)))


async def _attach_impl(session_name_or_id):
    ensure_dirs()
    sid = await _resolve_session_interactive_impl(session_name_or_id)
    s = await get_session(sid)
    if not s:
        raise typer.Exit(1)

    if not tmux.has_session(s.tmux_session):
        console.print(
            f"[red]Tmux session '{s.tmux_session}' not found (session may have died)[/red]"
        )
        await update_session(sid, status=SessionStatus.stopped)
        raise typer.Exit(1)

    await touch_session(sid)

    if tmux.is_inside_tmux():
        tmux.switch_client(s.tmux_session)
    else:
        tmux.attach_session(s.tmux_session)


def detach() -> None:
    """Detach from current session."""
    if not tmux.is_inside_tmux():
        console.print("[red]Not inside a tmux session[/red]")
        raise typer.Exit(1)

    current = tmux.current_session_name()
    if not is_shoal_tmux_session_name(current):
        console.print(f"[red]Not inside a shoal session (current: {current})[/red]")
        raise typer.Exit(1)

    tmux.detach_client()


def fork(
    session: Annotated[str | None, typer.Argument(help="Session to fork")] = None,
    name: Annotated[str | None, typer.Option("--name", "-n", help="New session name")] = None,
    no_worktree: Annotated[
        bool, typer.Option("--no-worktree", help="Fork without creating a worktree")
    ] = False,
) -> None:
    """Fork a session into a new worktree (or standalone session with --no-worktree)."""
    asyncio.run(with_db(_fork_impl(session, name, no_worktree)))


async def _fork_impl(session, name, no_worktree):
    ensure_dirs()
    cfg = load_config()
    source_id = await _resolve_session_interactive_impl(session)
    source = await get_session(source_id)
    if not source:
        raise typer.Exit(1)

    new_name = name or f"{source.name}-fork"

    if await find_by_name(new_name):
        console.print(f"[red]Session with name '{new_name}' already exists[/red]")
        raise typer.Exit(1)

    tool_cfg = load_tool_config(source.tool)
    work_dir = source.worktree or source.path
    wt_path = ""
    new_branch = source.branch

    if no_worktree:
        # Fork as a standalone session in the same directory
        pass
    else:
        # Create new worktree
        wt_dir_name = new_name.replace("/", "-")
        wt_path = str(Path(source.path) / ".worktrees" / wt_dir_name)
        try:
            new_branch = _branch_name_for_worktree(new_name)
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1) from None

        Path(source.path, ".worktrees").mkdir(parents=True, exist_ok=True)
        try:
            git.worktree_add(source.path, wt_path, branch=new_branch, start_point=source.branch)
        except Exception:
            console.print("[red]Failed to create worktree for fork[/red]")
            raise typer.Exit(1) from None
        work_dir = wt_path

    # Create new session
    try:
        new_session = await create_session(new_name, source.tool, source.path, wt_path, new_branch)
    except ValueError as e:
        console.print(f"[red]Invalid session name: {e}[/red]")
        raise typer.Exit(1)

    tmux_session = new_session.tmux_session

    try:
        tmux.new_session(tmux_session, cwd=work_dir)
    except Exception as e:
        console.print("[red]Error: Failed to create tmux session[/red]")
        console.print(f"[dim]{e}[/dim]")
        console.print()
        console.print("[yellow]Troubleshooting:[/yellow]")
        console.print("  • Check if tmux is installed: which tmux")
        console.print("  • Check if tmux server is responsive: tmux ls")
        console.print(f"  • Verify working directory exists: ls {work_dir}")
        await delete_session(new_session.id)
        raise typer.Exit(1) from None

    tmux.set_environment(tmux_session, "SHOAL_SESSION_ID", new_session.id)
    tmux.set_environment(tmux_session, "SHOAL_SESSION_NAME", new_name)

    # Run startup commands
    for cmd in cfg.tmux.startup_commands:
        try:
            interpolated = cmd.format(
                tool_command=tool_cfg.command,
                work_dir=work_dir,
                session_name=new_name,
                tmux_session=tmux_session,
            )
        except KeyError as e:
            console.print(
                f"[yellow]Warning: Skipping startup command with missing variable {e}: {cmd}[/yellow]"
            )
            continue
        tmux.run_command(interpolated)

    tmux.set_pane_title(tmux_session, f"shoal:{new_session.id}")

    await update_session(new_session.id, status=SessionStatus.running)

    console.print(f"{tool_cfg.icon} Forked '{source.name}' → '{new_name}' (id: {new_session.id})")
    if wt_path:
        console.print(f"  Worktree: {wt_path}")
        console.print(f"  Branch: {new_branch} (from {source.branch})")
    else:
        console.print(f"  Directory: {work_dir}")
    console.print()
    console.print(f"Attach with: shoal attach {new_name}")


def kill(
    session: Annotated[str | None, typer.Argument(help="Session to kill")] = None,
    worktree: Annotated[
        bool, typer.Option("--worktree", help="Also remove the git worktree")
    ] = False,
) -> None:
    """Kill a session."""
    asyncio.run(with_db(_kill_impl(session, worktree)))


async def _kill_impl(session, worktree):
    ensure_dirs()
    sid = await _resolve_session_interactive_impl(session)
    s = await get_session(sid)
    if not s:
        raise typer.Exit(1)

    icon = _get_tool_icon(s.tool)

    # Kill tmux session
    if tmux.has_session(s.tmux_session):
        tmux.kill_session(s.tmux_session)
        console.print(f"{icon} Killed tmux session: {s.tmux_session}")

    # Optionally remove worktree
    if worktree and s.worktree and Path(s.worktree).is_dir():
        if git.worktree_remove(s.path, s.worktree, force=True):
            console.print(f"  Removed worktree: {s.worktree}")
        else:
            console.print(f"  [yellow]Warning: Failed to remove worktree: {s.worktree}[/yellow]")

        if s.branch and s.branch not in ("main", "master") and git.branch_delete(s.path, s.branch):
            console.print(f"  Deleted branch: {s.branch}")

    await delete_session(sid)
    console.print(f"Session '{s.name}' ({sid}) removed")


def prune(
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Do not ask for confirmation")
    ] = False,
) -> None:
    """Remove all sessions marked as stopped."""
    asyncio.run(with_db(_prune_impl(force)))


async def _prune_impl(force):
    ensure_dirs()
    sessions = await list_sessions()
    stopped = [s for s in sessions if s.status.value == "stopped"]

    if not stopped:
        console.print("No stopped sessions to prune")
        return

    if not force:
        console.print(f"Found {len(stopped)} stopped sessions:")
        for s in stopped:
            console.print(f"  - {s.name} ({s.id})")
        if not typer.confirm("Are you sure you want to remove these?"):
            raise typer.Abort()

    for s in stopped:
        await delete_session(s.id)
        console.print(f"Removed session '{s.name}' ({s.id})")


def status(
    format: Annotated[
        str | None,
        typer.Option(
            "--format",
            "-f",
            help="Output format: default (rich panel) or plain (simple text for completions)",
        ),
    ] = None,
) -> None:
    """Quick status summary."""
    asyncio.run(with_db(_status_impl(format)))


async def _status_impl(format):
    ensure_dirs()
    sessions = await list_sessions()
    if not sessions:
        if format == "plain":
            return
        console.print("[yellow]No active sessions[/yellow]")
        console.print("Create one with: [bold]shoal new[/bold]")
        return

    counts: dict[str, int] = {
        "running": 0,
        "waiting": 0,
        "error": 0,
        "idle": 0,
        "stopped": 0,
        "unknown": 0,
    }
    for s in sessions:
        key = s.status.value if s.status.value in counts else "unknown"
        counts[key] += 1

    # Plain format for shell completions
    if format == "plain":
        total = len(sessions)
        status_parts = []
        if counts["running"]:
            status_parts.append(f"{counts['running']} running")
        if counts["waiting"]:
            status_parts.append(f"{counts['waiting']} waiting")
        if counts["error"]:
            status_parts.append(f"{counts['error']} error")
        if counts["idle"]:
            status_parts.append(f"{counts['idle']} idle")
        if counts["stopped"]:
            status_parts.append(f"{counts['stopped']} stopped")
        if counts["unknown"]:
            status_parts.append(f"{counts['unknown']} unknown")
        console.print(f"Total: {total} | {', '.join(status_parts)}")
        return

    total = len(sessions)
    from rich.text import Text

    status_line = Text()
    status_line.append(f"Total Sessions: {total}", style="bold")

    parts = []
    if counts["running"]:
        parts.append(f"[green]{get_status_icon('running')} {counts['running']} running[/green]")
    if counts["waiting"]:
        parts.append(f"[yellow]{get_status_icon('waiting')} {counts['waiting']} waiting[/yellow]")
    if counts["error"]:
        parts.append(f"[red]{get_status_icon('error')} {counts['error']} error[/red]")
    if counts["idle"]:
        parts.append(f"{get_status_icon('idle')} {counts['idle']} idle")
    if counts["stopped"]:
        parts.append(f"[dim]{get_status_icon('stopped')} {counts['stopped']} stopped[/dim]")
    if counts["unknown"]:
        parts.append(f"[dim]? {counts['unknown']} unknown[/dim]")

    console.print(
        create_panel(Text.from_markup("  |  ".join(parts)), title="Shoal Status", expand=False)
    )

    # Sessions needing attention
    if counts["waiting"]:
        console.print(f"\n[bold yellow]{Icons.STATUS} Waiting for input:[/bold yellow]")
        for s in sessions:
            if s.status.value == "waiting":
                icon = _get_tool_icon(s.tool)
                console.print(
                    f"  {icon} [bold]{s.name}[/bold] [dim]{Symbols.ARROW} shoal attach {s.name}[/dim]"
                )

    if counts["error"]:
        console.print(f"\n[bold red]{Icons.ERROR_ICON} Errors detected:[/bold red]")
        for s in sessions:
            if s.status.value == "error":
                icon = _get_tool_icon(s.tool)
                console.print(
                    f"  {icon} [bold]{s.name}[/bold] [dim]{Symbols.ARROW} shoal attach {s.name}[/dim]"
                )

    console.print("\n[dim]Use 'shoal ls' for a full list or 'shoal info <name>' for details.[/dim]")


def popup() -> None:
    """Open tmux popup dashboard."""
    ensure_dirs()
    if tmux.is_inside_tmux():
        # Launch the dashboard in a tmux popup
        tmux.popup("shoal _popup-inner")
    else:
        _popup_inner_impl()


def info(
    session: Annotated[str | None, typer.Argument(help="Session name or ID")] = None,
    color: Annotated[
        str,
        typer.Option(
            "--color",
            help="Color output: auto, always, never",
        ),
    ] = "auto",
) -> None:
    """Show detailed information about a session."""
    color_setting = color.lower()
    if color_setting not in {"auto", "always", "never"}:
        raise typer.BadParameter("Color must be one of: auto, always, never")
    asyncio.run(with_db(_info_impl(session, color_setting)))


def rename(
    old_name: Annotated[str, typer.Argument(help="Current session name or ID")],
    new_name: Annotated[str, typer.Argument(help="New name for the session")],
) -> None:
    """Rename a session."""
    asyncio.run(with_db(_rename_impl(old_name, new_name)))


def logs(
    session: Annotated[str | None, typer.Argument(help="Session name or ID")] = None,
    lines: Annotated[int, typer.Option("--lines", "-n", help="Number of lines to show")] = 20,
    tail: Annotated[bool, typer.Option("--tail", "-f", help="Follow the logs")] = False,
    color: Annotated[
        str,
        typer.Option(
            "--color",
            help="Color output: auto, always, never",
        ),
    ] = "auto",
) -> None:
    """Show recent output from a session."""
    color_setting = color.lower()
    if color_setting not in {"auto", "always", "never"}:
        raise typer.BadParameter("Color must be one of: auto, always, never")
    asyncio.run(with_db(_logs_impl(session, lines, tail, color_setting)))


async def _logs_impl(session_name_or_id, lines, tail, color_setting):
    ensure_dirs()
    from shoal.core.state import resolve_session

    sid = await resolve_session(session_name_or_id) if session_name_or_id else None
    if not sid:
        from shoal.core.state import _resolve_session_interactive_impl

        sid = await _resolve_session_interactive_impl(session_name_or_id)

    s = await get_session(sid)
    if not s:
        raise typer.Exit(1)

    if not tmux.has_session(s.tmux_session):
        console.print(f"[red]Tmux session '{s.tmux_session}' not found[/red]")
        raise typer.Exit(1)

    if color_setting == "always":
        logs_console = Console(force_terminal=True, color_system="truecolor")
    elif color_setting == "never":
        logs_console = Console(no_color=True)
    else:
        logs_console = console

    include_ansi = color_setting == "always"
    pane_target = tmux.preferred_pane(s.tmux_session, f"shoal:{s.id}")

    if not tail:
        content = tmux.capture_pane(pane_target, lines=lines, include_ansi=include_ansi)
        if include_ansi:
            from rich.text import Text

            logs_console.print(Text.from_ansi(content))
        else:
            logs_console.print(content)
    else:
        # Tailing tmux pane output is tricky without a dedicated tool,
        # but we can do a simple loop or use 'tmux pipe-pane'.
        # For simplicity, let's just use a loop for now.

        last_content = ""
        try:
            while True:
                content = tmux.capture_pane(
                    pane_target,
                    lines=lines,
                    include_ansi=include_ansi,
                )
                if content != last_content:
                    # Clear screen and show new content, or just show diff
                    # Simplest: just print it if it changed
                    if last_content:
                        new_lines = content.splitlines()
                        old_lines = last_content.splitlines()
                        # This is a very naive tail
                        for line in new_lines[len(old_lines) - 1 :]:
                            if line not in old_lines:
                                if include_ansi:
                                    from rich.text import Text

                                    logs_console.print(Text.from_ansi(line))
                                else:
                                    logs_console.print(line)
                    else:
                        if include_ansi:
                            from rich.text import Text

                            logs_console.print(Text.from_ansi(content))
                        else:
                            logs_console.print(content)
                    last_content = content
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass


async def _rename_impl(old_name, new_name):
    ensure_dirs()
    from shoal.core.state import resolve_session, validate_session_name

    # Validate new name
    try:
        validate_session_name(new_name)
    except ValueError as e:
        console.print(f"[red]Invalid session name: {e}[/red]")
        raise typer.Exit(1)

    sid = await resolve_session(old_name)
    if not sid:
        console.print(f"[red]Session not found: {old_name}[/red]")
        raise typer.Exit(1)

    s = await get_session(sid)
    if not s:
        raise typer.Exit(1)

    # Check if new name already exists
    if await find_by_name(new_name):
        console.print(f"[red]Session with name '{new_name}' already exists[/red]")
        raise typer.Exit(1)

    old_tmux = s.tmux_session
    new_tmux = build_tmux_session_name(new_name)

    # Rename tmux session if it exists
    if tmux.has_session(old_tmux):
        tmux.rename_session(old_tmux, new_tmux)
        console.print(f"Renamed tmux session: {old_tmux} → {new_tmux}")

    # Update DB
    await update_session(sid, name=new_name, tmux_session=new_tmux)
    console.print(f"Renamed session: {s.name} → {new_name}")


async def _info_impl(session_name_or_id, color_setting):
    ensure_dirs()
    from shoal.core.state import resolve_session

    sid = await resolve_session(session_name_or_id) if session_name_or_id else None

    if not sid:
        # Fallback to interactive if no arg or not found
        from shoal.core.state import _resolve_session_interactive_impl

        sid = await _resolve_session_interactive_impl(session_name_or_id)

    s = await get_session(sid)
    if not s:
        raise typer.Exit(1)

    try:
        tool_cfg = load_tool_config(s.tool)
        icon = tool_cfg.icon
    except FileNotFoundError:
        icon = _get_tool_icon(s.tool)
        tool_cfg = None

    from rich.columns import Columns

    status_style = get_status_style(s.status.value)

    status_text = (
        f"[{status_style}]{s.status.value}[/{status_style}]" if status_style else s.status.value
    )

    details = Table.grid(padding=(0, 2))
    details.add_column(style=Colors.HEADER_PRIMARY)
    details.add_column()

    details.add_row(f"{Icons.SESSION} ID", s.id)
    details.add_row(f"{icon.strip()} Name", f"[bold]{s.name}[/bold]")
    details.add_row(f"{Icons.TOOL} Tool", s.tool)
    details.add_row(f"{Icons.STATUS} Status", status_text)
    details.add_row(f"{Icons.DATE} Created", s.created_at.strftime("%Y-%m-%d %H:%M:%S"))
    details.add_row(f"{Icons.ACTIVITY} Activity", s.last_activity.strftime("%Y-%m-%d %H:%M:%S"))

    paths = Table.grid(padding=(0, 2))
    paths.add_column(style=Colors.HEADER_SECONDARY)
    paths.add_column()
    paths.add_row(f"{Icons.GIT_ROOT} Git Root", s.path)
    paths.add_row(f"{Icons.WORKTREE} Worktree", s.worktree or "[dim](none)[/dim]")
    paths.add_row(f"{Icons.BRANCH} Branch", f"[magenta]{s.branch or '-'}[/magenta]")

    runtime = Table.grid(padding=(0, 2))
    runtime.add_column(style=Colors.HEADER_WARNING)
    runtime.add_column()
    runtime.add_row(f"{Icons.TMUX} Tmux", f"[dim]session:[/dim] {s.tmux_session}")
    runtime.add_row(" ", f"[dim]window:[/dim] {s.tmux_window}")
    runtime.add_row(f"{Icons.PID} PID", str(s.pid) if s.pid else "[dim]N/A[/dim]")
    runtime.add_row(
        f"{Icons.MCP} MCP", ", ".join(s.mcp_servers) if s.mcp_servers else "[dim](none)[/dim]"
    )

    if color_setting == "always":
        info_console = Console(force_terminal=True, color_system="truecolor")
    elif color_setting == "never":
        info_console = Console(no_color=True)
    else:
        info_console = console

    info_console.print(
        create_panel(
            Columns([details, paths, runtime], expand=True),
            title=f"[bold blue]{Icons.SESSION} Session: {s.name}[/bold blue]",
            title_align="left",
            padding=(1, 2),
        )
    )

    if tmux.has_session(s.tmux_session):
        info_console.print(f"\n[bold]{Icons.OUTPUT} Recent Output:[/bold]")
        include_ansi = color_setting == "always"
        preview_lines = 15
        skip_lines = 10
        capture_lines = preview_lines * 6 if include_ansi else 20
        pane_target = tmux.preferred_pane(s.tmux_session, f"shoal:{s.id}")
        content = tmux.capture_pane(
            pane_target,
            lines=capture_lines,
            include_ansi=include_ansi,
        )
        if content:
            lines = content.splitlines()
            while lines and not lines[-1].strip():
                lines.pop()
            if include_ansi and len(lines) > skip_lines:
                lines = lines[:-skip_lines]
            lines = lines[-preview_lines:]
            preview = "\n".join(lines)
            if include_ansi:
                from rich.text import Text

                preview_renderable = Text.from_ansi(preview)
            else:
                preview_renderable = preview
            info_console.print(create_panel(preview_renderable, padding=(0, 1)))
        else:
            info_console.print("  [dim](no output captured)[/dim]")


def _popup_inner_impl() -> None:
    """Inner popup implementation — called by the popup command."""
    from shoal.dashboard.popup import run_popup

    run_popup()
