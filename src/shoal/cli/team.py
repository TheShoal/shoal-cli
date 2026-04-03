"""CLI commands for team configuration."""

from __future__ import annotations

import typer
from rich.table import Table

from shoal.cli._console import get_console
from shoal.core import git
from shoal.core.config import load_workspace_config
from shoal.models.config.workspace import TeamConfig

app = typer.Typer(no_args_is_help=True)


def _format_report_target(team: TeamConfig) -> str:
    """Render a configured report target for CLI output."""
    if team.report is None:
        return "[dim]--[/dim]"
    selector = team.report.id or team.report.slug or team.report.name
    return f"{team.report.type}:{selector}"


@app.command("ls")
def team_ls() -> None:
    """List configured teams from .shoal/workspace.toml."""
    console = get_console()

    root = git.git_root(".")
    ws_cfg = load_workspace_config(root)
    if not ws_cfg or not ws_cfg.teams:
        console.print("[dim]No teams configured.[/dim]")
        console.print("[dim]Add [teams.<slug>] sections to .shoal/workspace.toml[/dim]")
        raise typer.Exit(0)

    table = Table(title="Configured Teams")
    table.add_column("Slug", style="bold")
    table.add_column("Name")
    table.add_column("Linear")
    table.add_column("Template")
    table.add_column("Worktree Dir")
    table.add_column("Report")

    for slug, team in sorted(ws_cfg.teams.items()):
        table.add_row(
            slug,
            team.name or "[dim]--[/dim]",
            team.linear_slug,
            team.default_template or "[dim]--[/dim]",
            team.worktree_dir or "[dim]--[/dim]",
            _format_report_target(team),
        )

    console.print(table)
