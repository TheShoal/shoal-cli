"""Mode subcommand group."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from shoal.cli.mode_presets import MODE_REGISTRY

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command("ls")
def mode_ls() -> None:
    """List available operating modes."""
    table = Table(show_header=True)
    table.add_column("Mode", style="bold cyan")
    table.add_column("Description")
    table.add_column("Template", style="dim")
    table.add_column("Prefix", style="dim")
    table.add_column("Tags", style="dim")

    for spec in MODE_REGISTRY.values():
        tags = ", ".join(spec.auto_tags) if spec.auto_tags else "-"
        table.add_row(
            spec.name,
            spec.description,
            spec.preferred_template,
            spec.worktree_prefix,
            tags,
        )

    console.print(table)
