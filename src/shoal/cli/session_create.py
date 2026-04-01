"""Session lifecycle commands: new, fork, kill."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from shoal.cli._console import get_console
from shoal.cli.mode_presets import resolve_mode_defaults
from shoal.core import git
from shoal.core.config import (
    ConfigLoadError,
    config_dir,
    ensure_dirs,
    load_config,
    load_template,
    load_tool_config,
    load_workspace_config,
    template_source,
    templates_dir,
)
from shoal.core.db import with_db
from shoal.core.git import infer_branch_name, validate_branch_name
from shoal.core.session_names import build_tmux_session_name
from shoal.core.state import (
    _get_tool_icon,
    _resolve_session_interactive_impl,
    find_by_name,
    get_session,
)
from shoal.services.lifecycle import (
    SessionExistsError,
    StartupCommandError,
    TmuxSetupError,
    _preview_default_startup_commands,
    _preview_template_startup,
    _run_post_worktree_hook,
    create_session_lifecycle,
    fork_session_lifecycle,
    kill_session_lifecycle,
)


def _branch_name_for_worktree(worktree_name: str) -> str:
    branch_name = infer_branch_name(worktree_name)
    validate_branch_name(branch_name)
    return branch_name


def add(
    path: Annotated[str | None, typer.Argument(help="Project directory")] = None,
    tool: Annotated[
        str | None,
        typer.Option(
            "-t",
            "--tool",
            help="AI tool to use (pi recommended; opencode status is best-effort)",
        ),
    ] = None,
    template: Annotated[
        str | None, typer.Option("--template", help="Session template name")
    ] = None,
    mode: Annotated[
        str | None,
        typer.Option(
            "--mode",
            help="Single-session mode defaults: feature-lane, author-review, remote-batch",
        ),
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
    repo: Annotated[
        str | None,
        typer.Option("--repo", help="Target sub-repo from .shoal/workspace.toml"),
    ] = None,
) -> None:
    """Create a new session."""
    mcp_list = [s.strip() for s in mcp.split(",") if s.strip()] if mcp else []
    asyncio.run(
        with_db(
            _add_impl(path, tool, template, mode, worktree, branch, dry_run, name, mcp_list, repo)
        )
    )


async def _add_impl(
    path: str | None,
    tool: str | None,
    template: str | None,
    mode: str | None,
    worktree: str | None,
    branch: bool,
    dry_run: bool,
    name: str | None,
    mcp_servers: list[str] | None = None,
    repo: str | None = None,
) -> None:
    ensure_dirs()
    cfg = load_config()
    template_cfg = None
    resolved_mode: str | None = None
    resolved_path = Path(path).resolve() if path else Path.cwd().resolve()

    if not resolved_path.is_dir():
        get_console().print(f"[red]Error: Directory does not exist: {resolved_path}[/red]")
        if path and not path.startswith("-"):
            get_console().print(f"[dim]Did you mean: shoal new --name {path}[/dim]")
        raise typer.Exit(1)

    # Validate git repo before applying mode defaults that may synthesize worktrees.
    if not git.is_git_repo(str(resolved_path)):
        get_console().print("[red]Error: Not a git repository[/red]")
        get_console().print(f"[dim]Path: {resolved_path}[/dim]")
        get_console().print()
        get_console().print("[yellow]Shoal requires a git repository to track sessions.[/yellow]")
        get_console().print("Run one of the following:")
        get_console().print(f"  cd {resolved_path} && git init")
        get_console().print("  shoal new <path-to-git-repo>")
        raise typer.Exit(1)

    root = git.git_root(str(resolved_path))

    # --- Workspace routing: re-target to a sub-repo if inside a meta-repo ---
    ws_cfg = load_workspace_config(root)
    if repo and not ws_cfg:
        get_console().print("[red]Error: --repo requires .shoal/workspace.toml[/red]")
        get_console().print(
            f"[dim]No workspace manifest found at {root}/.shoal/workspace.toml[/dim]"
        )
        raise typer.Exit(1)
    if ws_cfg and ws_cfg.repos:
        try:
            old_root = root
            root, resolved_path_str = git.apply_workspace_routing(
                root, str(resolved_path), repo=repo, worktree=worktree, repos=ws_cfg.repos
            )
            resolved_path = Path(resolved_path_str)
            if root != old_root:
                get_console().print(f"[dim]Workspace routing: {old_root} → {root}[/dim]")
        except ValueError as e:
            get_console().print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1) from None
        except ConfigLoadError as e:
            get_console().print(f"[red]{e}[/red]")
            raise typer.Exit(1) from None

    if mode:
        try:
            mode_defaults = resolve_mode_defaults(
                mode,
                name=name,
                template=template,
                tool=tool,
                worktree=worktree,
                branch=branch,
                project_name=Path(root).name,
            )
        except ValueError as e:
            get_console().print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1) from None

        resolved_mode = mode_defaults.mode
        template = mode_defaults.template
        tool = mode_defaults.tool
        worktree = mode_defaults.worktree
        branch = mode_defaults.branch

    if template:
        try:
            template_cfg = load_template(template)
        except FileNotFoundError:
            template_path = templates_dir() / f"{template}.toml"
            source = template_source(template)
            get_console().print(f"[red]Error: Template '{template}' not found[/red]")
            get_console().print(f"[dim]Expected config at: {template_path} ({source})[/dim]")
            raise typer.Exit(1) from None
        except ConfigLoadError as e:
            get_console().print(f"[red]{e}[/red]")
            raise typer.Exit(1) from None
        except ValueError as e:
            get_console().print(f"[red]Error: Invalid template '{template}'[/red]")
            get_console().print(f"[dim]{e}[/dim]")
            raise typer.Exit(1) from None

        if not tool and template_cfg.tool:
            tool = template_cfg.tool

        if not worktree and template_cfg.worktree.name:
            try:
                worktree = template_cfg.worktree.name.format(template_name=template_cfg.name)
            except KeyError as e:
                get_console().print(
                    f"[red]Error: Template worktree has unsupported variable {e}[/red]"
                )
                get_console().print(
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

    if not tool:
        tool = cfg.general.default_tool
    tool_config_path = config_dir() / "tools" / f"{tool}.toml"
    if not tool_config_path.exists():
        get_console().print(f"[red]Error: Unknown tool '{tool}'[/red]")
        get_console().print(f"[dim]Expected config at: {tool_config_path}[/dim]")
        get_console().print()
        get_console().print("[yellow]Available tools:[/yellow]")
        tools_dir = config_dir() / "tools"
        if tools_dir.exists():
            for f in sorted(tools_dir.glob("*.toml")):
                get_console().print(f"  • {f.stem}")
        else:
            get_console().print("  [dim](none configured)[/dim]")
        get_console().print()
        get_console().print("[yellow]To create a tool config:[/yellow]")
        get_console().print(f"  mkdir -p {tools_dir}")
        get_console().print(f"  cat > {tool_config_path} <<EOF")
        get_console().print("  [tool]")
        get_console().print(f'  name = "{tool}"')
        get_console().print(f'  command = "{tool}"  # or full path')
        get_console().print("  EOF")
        raise typer.Exit(1)

    work_dir = str(resolved_path)
    branch_name = ""

    wt_path = ""
    if worktree:
        wt_dir_name = worktree.replace("/", "-")
        wt_path = str(Path(root) / ".worktrees" / wt_dir_name)

        if Path(wt_path).exists():
            get_console().print("[red]Error: Worktree already exists[/red]")
            get_console().print(f"[dim]Path: {wt_path}[/dim]")
            get_console().print()
            get_console().print("[yellow]Options:[/yellow]")
            get_console().print("  • Attach to existing worktree: shoal attach")
            get_console().print(f"  • Use a different worktree name: shoal new -w {worktree}-v2")
            get_console().print(f"  • Remove existing worktree: rm -rf {wt_path}")
            raise typer.Exit(1)

        if branch:
            try:
                branch_name = _branch_name_for_worktree(worktree)
            except ValueError as e:
                get_console().print(f"[red]Error: {e}[/red]")
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
        get_console().print(f"[red]Error: Session '{session_name}' already exists[/red]")
        get_console().print()
        get_console().print("[yellow]Actionable suggestions:[/yellow]")
        get_console().print(f"  • Attach to existing: [bold]shoal attach {session_name}[/bold]")
        get_console().print(f"  • Use unique name:    [bold]shoal new -n {session_name}-v2[/bold]")
        get_console().print(f"  • Kill existing:      [bold]shoal kill {session_name}[/bold]")
        raise typer.Exit(1)

    tool_cfg = load_tool_config(tool)
    tmux_session = build_tmux_session_name(session_name)

    if dry_run:
        get_console().print("[bold cyan]Dry run: no changes applied[/bold cyan]")
        get_console().print(f"  Session: {session_name}")
        get_console().print(f"  Tool: {tool}")
        get_console().print(f"  Branch: {branch_name}")
        if worktree:
            get_console().print(f"  Worktree: {work_dir}")
            get_console().print(f"  Worktree dir name: {worktree.replace('/', '-')}")
        else:
            get_console().print(f"  Directory: {work_dir}")
        get_console().print(f"  Tmux: {tmux_session}")
        if resolved_mode:
            get_console().print(f"  Mode: {resolved_mode}")
        if template_cfg:
            get_console().print(f"  Template: {template_cfg.name}")
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
            get_console().print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1) from None

        get_console().print()
        get_console().print("[bold]Planned tmux actions:[/bold]")
        if startup_preview:
            for cmd in startup_preview:
                get_console().print(f"  - tmux {cmd}")
        else:
            get_console().print("  - [dim](none)[/dim]")
        return

    if worktree:
        Path(root, ".worktrees").mkdir(parents=True, exist_ok=True)
        if branch:
            git.worktree_add(root, wt_path, branch=branch_name)
        else:
            git.worktree_add(root, wt_path)
            branch_name = git.current_branch(wt_path)
        await asyncio.to_thread(_run_post_worktree_hook, template_cfg, wt_path, root)

    # Collect auto-tags from mode + template
    auto_tags: list[str] = []
    if template_cfg and template_cfg.tags:
        auto_tags.extend(template_cfg.tags)
    if mode:
        auto_tags.extend(mode_defaults.auto_tags)
    # Dedupe preserving order
    auto_tags = list(dict.fromkeys(auto_tags))

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
            tags=auto_tags or None,
            dreamer_config=cfg.dreamer,
        )
    except SessionExistsError as e:
        get_console().print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None
    except TmuxSetupError as e:
        get_console().print("[red]Error: Failed to create tmux session[/red]")
        get_console().print(f"[dim]{e}[/dim]")
        get_console().print()
        get_console().print("[yellow]Troubleshooting:[/yellow]")
        get_console().print("  • Check if tmux is installed: which tmux")
        get_console().print("  • Check if tmux server is responsive: tmux ls")
        get_console().print(f"  • Verify working directory exists: ls {work_dir}")
        raise typer.Exit(1) from None
    except StartupCommandError as e:
        get_console().print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None
    except ValueError as e:
        get_console().print(f"[red]Invalid session name: {e}[/red]")
        raise typer.Exit(1) from None

    get_console().print(
        f"{tool_cfg.icon} Session '{session_name}' created (id: {session.id}, tool: {tool})"
    )
    if worktree:
        get_console().print(f"  Worktree: {work_dir}")
        get_console().print(f"  Branch: {branch_name}")
    if resolved_mode:
        get_console().print(f"  Mode: {resolved_mode}")
    if template_cfg:
        get_console().print(f"  Template: {template_cfg.name}")
    if session.mcp_servers:
        get_console().print(f"  MCP: {', '.join(session.mcp_servers)}")
    rt_kind = session.runtime.kind.value
    rt_name = session.tmux_runtime.session_name if rt_kind == "tmux" else ""
    get_console().print(f"  Runtime: {rt_kind} ({rt_name})")
    get_console().print()
    get_console().print(f"Attach with: shoal attach {session_name}")


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
        get_console().print(f"[red]Session with name '{new_name}' already exists[/red]")
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
            get_console().print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1) from None

        Path(source.path, ".worktrees").mkdir(parents=True, exist_ok=True)
        try:
            git.worktree_add(source.path, wt_path, branch=new_branch, start_point=source.branch)
        except Exception:
            get_console().print("[red]Failed to create worktree for fork[/red]")
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
        get_console().print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None
    except TmuxSetupError as e:
        get_console().print("[red]Error: Failed to create tmux session[/red]")
        get_console().print(f"[dim]{e}[/dim]")
        raise typer.Exit(1) from None
    except StartupCommandError as e:
        get_console().print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None
    except ValueError as e:
        get_console().print(f"[red]Invalid session name: {e}[/red]")
        raise typer.Exit(1) from None

    get_console().print(
        f"{tool_cfg.icon} Forked '{source.name}' → '{new_name}' (id: {new_session.id})"
    )
    if wt_path:
        get_console().print(f"  Worktree: {wt_path}")
        get_console().print(f"  Branch: {new_branch} (from {source.branch})")
    else:
        get_console().print(f"  Directory: {work_dir}")
    get_console().print()
    get_console().print(f"Attach with: shoal attach {new_name}")


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
            tmux_session=s.tmux_runtime.session_name,
            worktree=s.worktree,
            git_root=s.path,
            branch=s.branch,
            remove_worktree=worktree,
            force=force,
        )
    except DirtyWorktreeError as exc:
        get_console().print(f"[red]Worktree has uncommitted changes:[/red] {s.worktree}")
        if exc.dirty_files:
            for line in exc.dirty_files.splitlines()[:10]:
                get_console().print(f"  {line}")
        get_console().print("\n[yellow]Use --force to remove anyway[/yellow]")
        raise typer.Exit(1) from None

    if summary["tmux_killed"]:
        get_console().print(f"{icon} Killed runtime session: {s.tmux_runtime.session_name}")
    if summary["worktree_removed"]:
        get_console().print(f"  Removed worktree: {s.worktree}")
    if summary["branch_deleted"]:
        get_console().print(f"  Deleted branch: {s.branch}")
    if summary["journal_archived"]:
        get_console().print(f"  Archived journal: {s.id}.md")
    get_console().print(f"Session '{s.name}' ({sid}) removed")
