"""Session viewing commands: ls, status, info, logs."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from shoal.core import tmux
from shoal.core.config import ensure_dirs, load_config, load_tool_config
from shoal.core.db import with_db
from shoal.core.state import (
    _get_tool_icon,
    get_session,
    list_sessions,
)
from shoal.core.theme import (
    Colors,
    Icons,
    Symbols,
    create_panel,
    create_table,
    get_status_icon,
    get_status_style,
)
from shoal.models.state import SessionState

console = Console()


def ls(
    format: Annotated[
        str | None,
        typer.Option(
            "--format",
            "-f",
            help="Output format: default (rich table) or plain (names only for completions)",
        ),
    ] = None,
    tag: Annotated[
        str | None,
        typer.Option("--tag", help="Filter sessions by tag"),
    ] = None,
    tree: Annotated[
        bool,
        typer.Option("--tree", help="Display fork relationships as a tree"),
    ] = False,
) -> None:
    """List all sessions."""
    asyncio.run(with_db(_ls_impl(format, tag=tag, tree=tree)))


async def _ls_impl(format: str | None, *, tag: str | None = None, tree: bool = False) -> None:
    ensure_dirs()
    sessions = await list_sessions()

    # Filter by tag
    if tag:
        sessions = [s for s in sessions if tag in s.tags]

    if format == "plain":
        for session in sessions:
            console.print(session.name)
        return

    if not sessions:
        console.print("No sessions")
        return

    if tree:
        _render_fork_tree(sessions)
        return

    use_nerd = load_config().general.use_nerd_fonts
    show_tags = any(s.tags for s in sessions)

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
        if show_tags:
            table.add_column("TAGS", width=20)

        # Sort sessions within group by name
        for s in sorted(group_sessions, key=lambda x: x.name):
            icon = _get_tool_icon(s.tool)

            # Check if it's a ghost session
            is_ghost = False
            if s.status.value != "stopped" and not tmux.has_session(s.tmux_session):
                is_ghost = True

            status_icon = get_status_icon(s.status.value, use_nerd=use_nerd)
            status_style = get_status_style(s.status.value)

            status_text = (
                f"[{status_style}]{status_icon} {s.status.value}[/{status_style}]"
                if status_style
                else s.status.value
            )

            if is_ghost:
                ghost_icon = Icons.GHOST if use_nerd else Symbols.CROSS
                status_text = (
                    f"[bold red]{ghost_icon} ghost[/bold red] [dim](was {s.status.value})[/dim]"
                )

            wt_display = ""
            if s.worktree:
                wt_display = s.worktree.replace(path, ".").replace(str(Path.home()), "~")
            else:
                wt_display = "[dim](root)[/dim]"

            row: list[str] = [
                s.id,
                f"{icon} [bold]{s.name}[/bold]",
                s.tool,
                status_text,
                f"[cyan]{s.branch or '-'}[/cyan]",
                wt_display,
            ]
            if show_tags:
                row.append(", ".join(s.tags) if s.tags else "[dim]-[/dim]")

            table.add_row(*row)

        session_icon = Icons.SESSION if use_nerd else Symbols.BULLET_FILLED
        console.print()
        console.print(
            create_panel(
                table,
                title=f"[bold blue]{session_icon} {display_project}[/bold blue]",
                primary=True,
                title_align="left",
                padding=(0, 1),
            )
        )


def _render_fork_tree(sessions: list[SessionState]) -> None:
    """Render sessions as a fork-relationship tree."""

    # Build parent -> children map
    by_id: dict[str, SessionState] = {s.id: s for s in sessions}
    children: dict[str, list[SessionState]] = {}
    roots: list[SessionState] = []

    for s in sessions:
        if s.parent_id and s.parent_id in by_id:
            children.setdefault(s.parent_id, []).append(s)
        else:
            roots.append(s)

    # Sort
    roots.sort(key=lambda x: x.name)
    for clist in children.values():
        clist.sort(key=lambda x: x.name)

    def _fmt_tags(tags: list[str]) -> str:
        if not tags:
            return ""
        return f" \\[{', '.join(tags)}]"

    def _print_node(s: SessionState, prefix: str, is_last: bool) -> None:
        connector = "└── " if is_last else "├── "
        console.print(
            f"{prefix}{connector}[bold]{s.name}[/bold] "
            f"[dim]({s.id})[/dim] {s.status.value}{_fmt_tags(s.tags)}"
        )
        child_prefix = prefix + ("    " if is_last else "│   ")
        kids = children.get(s.id, [])
        for i, child in enumerate(kids):
            _print_node(child, child_prefix, i == len(kids) - 1)

    console.print()
    for _i, root in enumerate(roots):
        console.print(
            f"[bold]{root.name}[/bold] "
            f"[dim]({root.id})[/dim] {root.status.value}{_fmt_tags(root.tags)}"
        )
        kids = children.get(root.id, [])
        for j, child in enumerate(kids):
            _print_node(child, "", j == len(kids) - 1)


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


async def _status_impl(format: str | None) -> None:
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

    use_nerd = load_config().general.use_nerd_fonts

    total = len(sessions)
    from rich.text import Text

    status_line = Text()
    status_line.append(f"Total Sessions: {total}", style="bold")

    parts = []
    if counts["running"]:
        ri = get_status_icon("running", use_nerd=use_nerd)
        parts.append(f"[green]{ri} {counts['running']} running[/green]")
    if counts["waiting"]:
        wi = get_status_icon("waiting", use_nerd=use_nerd)
        parts.append(f"[yellow]{wi} {counts['waiting']} waiting[/yellow]")
    if counts["error"]:
        ei = get_status_icon("error", use_nerd=use_nerd)
        parts.append(f"[red]{ei} {counts['error']} error[/red]")
    if counts["idle"]:
        ii = get_status_icon("idle", use_nerd=use_nerd)
        parts.append(f"{ii} {counts['idle']} idle")
    if counts["stopped"]:
        si = get_status_icon("stopped", use_nerd=use_nerd)
        parts.append(f"[dim]{si} {counts['stopped']} stopped[/dim]")
    if counts["unknown"]:
        parts.append(f"[dim]? {counts['unknown']} unknown[/dim]")

    console.print()
    console.print(
        create_panel(Text.from_markup("  |  ".join(parts)), title="Shoal Status", expand=False)
    )

    # Sessions needing attention
    if counts["waiting"]:
        status_icon = Icons.STATUS if use_nerd else Symbols.INFO
        console.print(f"\n[bold yellow]{status_icon} Waiting for input:[/bold yellow]")
        for s in sessions:
            if s.status.value == "waiting":
                icon = _get_tool_icon(s.tool)
                arrow = Symbols.ARROW
                console.print(
                    f"  {icon} [bold]{s.name}[/bold] [dim]{arrow} shoal attach {s.name}[/dim]"
                )

    if counts["error"]:
        error_icon = Icons.ERROR_ICON if use_nerd else Symbols.CROSS
        console.print(f"\n[bold red]{error_icon} Errors detected:[/bold red]")
        for s in sessions:
            if s.status.value == "error":
                icon = _get_tool_icon(s.tool)
                arrow = Symbols.ARROW
                console.print(
                    f"  {icon} [bold]{s.name}[/bold] [dim]{arrow} shoal attach {s.name}[/dim]"
                )

    console.print("\n[dim]Use 'shoal ls' for a full list or 'shoal info <name>' for details.[/dim]")


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


async def _info_impl(session_name_or_id: str | None, color_setting: str) -> None:
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
    if s.template_name:
        details.add_row(f"{Symbols.ARROW} Template", s.template_name)
    if s.parent_id:
        parent = await get_session(s.parent_id)
        parent_display = f"{parent.name} [dim]({s.parent_id})[/dim]" if parent else s.parent_id
        details.add_row(f"{Symbols.ARROW} Parent", parent_display)
    if s.tags:
        details.add_row(f"{Symbols.BULLET_FILLED} Tags", ", ".join(s.tags))
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

    info_console.print()
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
            preview_renderable: str | Text
            if include_ansi:
                from rich.text import Text

                preview_renderable = Text.from_ansi(preview)
            else:
                preview_renderable = preview
            info_console.print(create_panel(preview_renderable, padding=(0, 1)))
        else:
            info_console.print("  [dim](no output captured)[/dim]")


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


async def _logs_impl(
    session_name_or_id: str | None, lines: int, tail: bool, color_setting: str
) -> None:
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
