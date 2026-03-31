"""Session viewing commands: ls, status, info, logs."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from shoal.cli._console import get_console
from shoal.core.config import ensure_dirs, load_config, load_tool_config
from shoal.core.db import with_db
from shoal.core.state import _get_tool_icon, get_session, list_sessions
from shoal.core.status_provider import describe_status_provider
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
from shoal.services.runtime_provider import provider_for_session, runtime_summary


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
            get_console().print(session.name)
        return

    if not sessions:
        get_console().print("No sessions")
        return

    if tree:
        _render_fork_tree(sessions)
        return

    use_nerd = load_config().general.use_nerd_fonts
    show_tags = any(s.tags for s in sessions)
    session_icon = Icons.SESSION if use_nerd else Symbols.BULLET_FILLED
    home = str(Path.home())

    # Group sessions by project root, then render each group as a compact table.
    from collections import defaultdict

    groups = defaultdict(list)
    for s in sessions:
        groups[s.path].append(s)

    sorted_paths = sorted(groups.keys())

    for index, path in enumerate(sorted_paths):
        group_sessions = sorted(groups[path], key=lambda x: x.name)
        display_project = path.replace(home, "~")

        table = create_table(
            padding=(0, 1),
            collapse_padding=True,
            expand=True,
            pad_edge=False,
        )
        table.add_column("SESSION", min_width=24, ratio=3, overflow="fold")
        table.add_column("STATE", min_width=16, ratio=2, overflow="fold")
        table.add_column("LOCATION", min_width=28, ratio=4, overflow="fold")
        if show_tags:
            table.add_column("TAGS", min_width=14, ratio=2, overflow="fold")

        for s in group_sessions:
            icon = _get_tool_icon(s.tool)

            is_ghost = False
            if s.status.value != "stopped" and not provider_for_session(s).exists(s):
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

            location_path = (
                s.worktree.replace(path, ".").replace(home, "~")
                if s.worktree
                else "[dim](root)[/dim]"
            )

            row: list[str] = [
                f"{icon} [bold]{s.name}[/bold]\n[dim]{s.id}[/dim]",
                f"{status_text}\n[dim]{s.tool}[/dim]",
                f"[cyan]{s.branch or '-'}[/cyan]\n{location_path}",
            ]
            if show_tags:
                row.append(", ".join(s.tags) if s.tags else "[dim]-[/dim]")

            table.add_row(*row)

        if index:
            get_console().print()
        get_console().rule(
            f"[bold blue]{session_icon} {display_project}[/bold blue]",
            style=Colors.PANEL_BORDER_PRIMARY,
            align="left",
        )
        get_console().print(table)


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
        get_console().print(
            f"{prefix}{connector}[bold]{s.name}[/bold] "
            f"[dim]({s.id})[/dim] {s.status.value}{_fmt_tags(s.tags)}"
        )
        child_prefix = prefix + ("    " if is_last else "│   ")
        kids = children.get(s.id, [])
        for i, child in enumerate(kids):
            _print_node(child, child_prefix, i == len(kids) - 1)

    get_console().print()
    for _i, root in enumerate(roots):
        get_console().print(
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
    from datetime import UTC, datetime

    from shoal.core.urgency import UrgencyTier, derive_urgency

    ensure_dirs()
    sessions = await list_sessions()
    if not sessions:
        if format == "plain":
            return
        get_console().print("[yellow]No active sessions[/yellow]")
        get_console().print("Create one with: [bold]shoal new[/bold]")
        return

    cfg = load_config()
    blocked_after = cfg.operator.blocked_after_minutes
    stale_after = cfg.operator.stale_after_minutes
    now = datetime.now(UTC)

    # Annotate every session with its urgency tier and label.
    annotated = [
        (
            s,
            *derive_urgency(
                s, now=now, blocked_after_minutes=blocked_after, stale_after_minutes=stale_after
            ),
        )
        for s in sessions
    ]
    annotated.sort(key=lambda x: (int(x[1]), x[0].name))

    # Plain format for shell completions / scripting — keep it terse.
    if format == "plain":
        from collections import Counter

        tier_counts: Counter[str] = Counter(label for _, _, label in annotated)
        parts = [f"{n} {lbl}" for lbl, n in tier_counts.most_common()]
        get_console().print(f"Total: {len(sessions)} | {', '.join(parts)}")
        return

    # Group into attention / active / ready / background.
    attention = [
        (s, lbl)
        for s, tier, lbl in annotated
        if tier in (UrgencyTier.error, UrgencyTier.blocked, UrgencyTier.waiting)
    ]
    review = [(s, lbl) for s, tier, lbl in annotated if tier == UrgencyTier.review]
    active = [(s, lbl) for s, tier, lbl in annotated if tier == UrgencyTier.running]
    background = [
        (s, lbl)
        for s, tier, lbl in annotated
        if tier in (UrgencyTier.stale, UrgencyTier.idle, UrgencyTier.stopped, UrgencyTier.unknown)
    ]

    arrow = Symbols.ARROW
    get_console().print()

    if attention:
        get_console().print(f"[bold red]Needs attention ({len(attention)})[/bold red]")
        for s, lbl in attention:
            icon = _get_tool_icon(s.tool)
            tier_style = "red" if s.status.value == "error" else "yellow"
            get_console().print(
                f"  {icon} [bold]{s.name}[/bold]  "
                f"[{tier_style}]{lbl}[/{tier_style}]  "
                f"[dim]{arrow} shoal attach {s.name}[/dim]"
            )
        get_console().print()

    if review:
        get_console().print(f"[bold cyan]Ready for review ({len(review)})[/bold cyan]")
        for s, lbl in review:
            icon = _get_tool_icon(s.tool)
            get_console().print(
                f"  {icon} [bold]{s.name}[/bold]  [cyan]{lbl}[/cyan]  "
                f"[dim]{arrow} shoal attach {s.name}[/dim]"
            )
        get_console().print()

    if active:
        get_console().print(f"[bold green]Active ({len(active)})[/bold green]")
        for s, lbl in active:
            icon = _get_tool_icon(s.tool)
            get_console().print(f"  {icon} [bold]{s.name}[/bold]  [green]{lbl}[/green]")
        get_console().print()

    if background:
        get_console().print(f"[dim]Background ({len(background)})[/dim]")
        for s, lbl in background:
            icon = _get_tool_icon(s.tool)
            tier_style = "yellow" if "stale" in lbl else "dim"
            get_console().print(
                f"  {icon} [bold]{s.name}[/bold]  [{tier_style}]{lbl}[/{tier_style}]"
            )
        get_console().print()

    total = len(sessions)
    n_attention = len(attention)
    summary_parts = [f"[bold]{total} sessions[/bold]"]
    if n_attention:
        summary_parts.append(f"[red]{n_attention} need attention[/red]")
    if review:
        summary_parts.append(f"[cyan]{len(review)} review-ready[/cyan]")
    get_console().print("[dim]" + "  ·  ".join(summary_parts) + "[/dim]")
    get_console().print("[dim]shoal ls for full list  ·  shoal popup for dashboard[/dim]")


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
    from rich.console import Console
    from rich.table import Table

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
    if tool_cfg:
        details.add_row("Detection", describe_status_provider(tool_cfg))
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
    runtime.add_row(f"{Icons.STATUS} Runtime", s.runtime.kind.value)
    for label, value in runtime_summary(s.runtime).items():
        display_value = value or "[dim](none)[/dim]"
        runtime.add_row(" ", f"[dim]{label}:[/dim] {display_value}")
    runtime.add_row(f"{Icons.PID} PID", str(s.pid) if s.pid else "[dim]N/A[/dim]")
    runtime.add_row(
        f"{Icons.MCP} MCP", ", ".join(s.mcp_servers) if s.mcp_servers else "[dim](none)[/dim]"
    )

    if color_setting == "always":
        info_console = Console(force_terminal=True, color_system="truecolor")
    elif color_setting == "never":
        info_console = Console(no_color=True)
    else:
        info_console = get_console()

    info_console.print()
    info_console.print(
        create_panel(
            Columns([details, paths, runtime], expand=True),
            title=f"[bold blue]{Icons.SESSION} Session: {s.name}[/bold blue]",
            title_align="left",
            padding=(1, 2),
        )
    )

    provider = provider_for_session(s)
    if provider.exists(s):
        info_console.print(f"\n[bold]{Icons.OUTPUT} Recent Output:[/bold]")
        include_ansi = color_setting == "always"
        preview_lines = 15
        skip_lines = 10
        capture_lines = preview_lines * 6 if include_ansi else 20
        content = provider.capture_output(s, lines=capture_lines, include_ansi=include_ansi)
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

    provider = provider_for_session(s)
    if not provider.exists(s):
        get_console().print(f"[red]Runtime session not found: {s.runtime.session_name}[/red]")
        raise typer.Exit(1)

    if color_setting == "always":
        from rich.console import Console

        logs_console = Console(force_terminal=True, color_system="truecolor")
    elif color_setting == "never":
        from rich.console import Console

        logs_console = Console(no_color=True)
    else:
        logs_console = get_console()

    include_ansi = color_setting == "always"

    if not tail:
        content = provider.capture_output(s, lines=lines, include_ansi=include_ansi)
        if include_ansi:
            from rich.text import Text

            logs_console.print(Text.from_ansi(content))
        else:
            logs_console.print(content)
    else:
        last_content = ""
        try:
            while True:
                content = provider.capture_output(s, lines=lines, include_ansi=include_ansi)
                if content != last_content:
                    if last_content:
                        new_lines = content.splitlines()
                        old_lines = last_content.splitlines()
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
