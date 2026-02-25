"""Session lifecycle commands: new, fork, kill."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from shoal.core import git
from shoal.core.config import (
    ConfigLoadError,
    config_dir,
    ensure_dirs,
    load_config,
    load_template,
    load_tool_config,
)
from shoal.core.db import with_db
from shoal.core.state import (
    _get_tool_icon,
    _resolve_session_interactive_impl,
    build_tmux_session_name,
    find_by_name,
    get_session,
)
from shoal.services.lifecycle import (
    SessionExistsError,
    StartupCommandError,
    TmuxSetupError,
    _preview_default_startup_commands,
    _preview_template_startup,
    create_session_lifecycle,
    fork_session_lifecycle,
    kill_session_lifecycle,
)

console = Console()

ALLOWED_BRANCH_CATEGORIES = ("feat", "fix", "bug", "chore", "docs", "refactor", "test")


def _infer_branch_name(worktree_name: str) -> str:
    """Infer branch name from worktree name.

    If the worktree name contains a '/', use it as-is
    (assumes it has a prefix like fix/, feat/, chore/).
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
    mcp: Annotated[
        str | None,
        typer.Option("--mcp", help="MCP servers to provision (comma-separated)"),
    ] = None,
) -> None:
    """Create a new session."""
    mcp_list = [s.strip() for s in mcp.split(",") if s.strip()] if mcp else []
    asyncio.run(with_db(_add_impl(path, tool, template, worktree, branch, dry_run, name, mcp_list)))


async def _add_impl(
    path: str | None,
    tool: str | None,
    template: str | None,
    worktree: str | None,
    branch: bool,
    dry_run: bool,
    name: str | None,
    mcp_servers: list[str] | None = None,
) -> None:
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
        except ConfigLoadError as e:
            console.print(f"[red]{e}[/red]")
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
                    "[dim]Use --worktree for dynamic names or only"
                    " {template_name} in template.worktree.name[/dim]"
                )
                raise typer.Exit(1) from None

        if template_cfg.worktree.create_branch:
            branch = True

        # Merge template MCP declarations with --mcp flag (union, deduped)
        if template_cfg.mcp:
            merged = set(mcp_servers or []) | set(template_cfg.mcp)
            mcp_servers = sorted(merged)

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

    # Delegate to lifecycle service
    try:
        session = await create_session_lifecycle(
            session_name=session_name,
            tool=tool,
            git_root=root,
            wt_path=wt_path,
            work_dir=work_dir,
            branch_name=branch_name,
            tool_command=tool_cfg.command,
            startup_commands=cfg.tmux.startup_commands,
            template_cfg=template_cfg,
            worktree_name=worktree or "",
            mcp_servers=mcp_servers or None,
        )
    except SessionExistsError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None
    except TmuxSetupError as e:
        console.print("[red]Error: Failed to create tmux session[/red]")
        console.print(f"[dim]{e}[/dim]")
        console.print()
        console.print("[yellow]Troubleshooting:[/yellow]")
        console.print("  • Check if tmux is installed: which tmux")
        console.print("  • Check if tmux server is responsive: tmux ls")
        console.print(f"  • Verify working directory exists: ls {work_dir}")
        raise typer.Exit(1) from None
    except StartupCommandError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None
    except ValueError as e:
        console.print(f"[red]Invalid session name: {e}[/red]")
        raise typer.Exit(1) from None

    console.print(
        f"{tool_cfg.icon} Session '{session_name}' created (id: {session.id}, tool: {tool})"
    )
    if worktree:
        console.print(f"  Worktree: {work_dir}")
        console.print(f"  Branch: {branch_name}")
    if template_cfg:
        console.print(f"  Template: {template_cfg.name}")
    if session.mcp_servers:
        console.print(f"  MCP: {', '.join(session.mcp_servers)}")
    console.print(f"  Tmux: {session.tmux_session}")
    console.print()
    console.print(f"Attach with: shoal attach {session_name}")


def fork(
    session: Annotated[str | None, typer.Argument(help="Session to fork")] = None,
    name: Annotated[str | None, typer.Option("--name", "-n", help="New session name")] = None,
    no_worktree: Annotated[
        bool, typer.Option("--no-worktree", help="Fork without creating a worktree")
    ] = False,
    mcp: Annotated[
        str | None,
        typer.Option("--mcp", help="MCP servers to provision (comma-separated)"),
    ] = None,
) -> None:
    """Fork a session into a new worktree (or standalone session with --no-worktree)."""
    mcp_list = [s.strip() for s in mcp.split(",") if s.strip()] if mcp else []
    asyncio.run(with_db(_fork_impl(session, name, no_worktree, mcp_list)))


async def _fork_impl(
    session: str | None, name: str | None, no_worktree: bool, mcp_servers: list[str] | None = None
) -> None:
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

    # Delegate to lifecycle service
    try:
        new_session = await fork_session_lifecycle(
            session_name=new_name,
            source_tool=source.tool,
            source_path=source.path,
            source_branch=source.branch,
            wt_path=wt_path,
            work_dir=work_dir,
            new_branch=new_branch,
            tool_command=tool_cfg.command,
            startup_commands=cfg.tmux.startup_commands,
            mcp_servers=mcp_servers or None,
            parent_id=source.id,
        )
    except SessionExistsError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None
    except TmuxSetupError as e:
        console.print("[red]Error: Failed to create tmux session[/red]")
        console.print(f"[dim]{e}[/dim]")
        raise typer.Exit(1) from None
    except StartupCommandError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None
    except ValueError as e:
        console.print(f"[red]Invalid session name: {e}[/red]")
        raise typer.Exit(1) from None

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
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Force kill even with dirty worktree")
    ] = False,
) -> None:
    """Kill a session."""
    asyncio.run(with_db(_kill_impl(session, worktree, force)))


async def _kill_impl(session: str | None, worktree: bool, force: bool) -> None:
    from shoal.services.lifecycle import DirtyWorktreeError

    ensure_dirs()
    sid = await _resolve_session_interactive_impl(session)
    s = await get_session(sid)
    if not s:
        raise typer.Exit(1)

    icon = _get_tool_icon(s.tool)

    try:
        summary = await kill_session_lifecycle(
            session_id=s.id,
            tmux_session=s.tmux_session,
            worktree=s.worktree,
            git_root=s.path,
            branch=s.branch,
            remove_worktree=worktree,
            force=force,
        )
    except DirtyWorktreeError as exc:
        console.print(f"[red]Worktree has uncommitted changes:[/red] {s.worktree}")
        if exc.dirty_files:
            for line in exc.dirty_files.splitlines()[:10]:
                console.print(f"  {line}")
        console.print("\n[yellow]Use --force to remove anyway[/yellow]")
        raise typer.Exit(1) from None

    if summary["tmux_killed"]:
        console.print(f"{icon} Killed tmux session: {s.tmux_session}")
    if summary["worktree_removed"]:
        console.print(f"  Removed worktree: {s.worktree}")
    if summary["branch_deleted"]:
        console.print(f"  Deleted branch: {s.branch}")
    if summary["journal_archived"]:
        console.print(f"  Archived journal: {s.id}.md")
    console.print(f"Session '{s.name}' ({sid}) removed")
