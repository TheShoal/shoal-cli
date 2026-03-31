"""Skill discovery and listing commands."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from shoal.core import git
from shoal.core.config import discover_skills

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command("ls")
def skill_ls() -> None:
    """List discovered skills from project-local and global paths."""
    try:
        root = git.git_root(".")
    except Exception:
        root = None

    skills = discover_skills(root)
    if not skills:
        console.print("[dim]No skills found.[/dim]")
        console.print("[dim]Add skills to .shoal/skills/<name>/SKILL.md[/dim]")
        return

    table = Table(show_header=True)
    table.add_column("Skill", style="bold cyan")
    table.add_column("Description")
    table.add_column("Tools", style="dim")
    table.add_column("Path", style="dim")

    for s in skills:
        tools = ", ".join(s.allowed_tools) if s.allowed_tools else "-"
        # Shorten path for display
        path = s.path
        if root and path.startswith(root):
            path = path[len(root) :].lstrip("/")
        table.add_row(s.name, s.description, tools, path)

    console.print(table)
