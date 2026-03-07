"""Config inspection commands: show, paths."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console

from shoal.core.config import ConfigLoadError, config_dir, data_dir, load_config, state_dir

console = Console()

app = typer.Typer(no_args_is_help=True)


@app.command("show")
def config_show(
    fmt: Annotated[
        str, typer.Option("--format", "-f", help="Output format: toml or json")
    ] = "toml",
) -> None:
    """Dump effective (resolved) configuration."""
    try:
        cfg = load_config()
    except ConfigLoadError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    if fmt == "json":
        console.print_json(cfg.model_dump_json(indent=2))
    elif fmt == "toml":
        _print_toml_like(cfg.model_dump())
    else:
        console.print(f"[red]Unknown format: {fmt}[/red]")
        console.print("[dim]Use --format toml or --format json[/dim]")
        raise typer.Exit(1)


def _print_toml_like(data: dict[str, object], prefix: str = "") -> None:
    """Print a nested dict in a TOML-like format using Rich."""
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            console.print(f"\n[bold cyan]\\[{full_key}][/bold cyan]")
            _print_toml_like(value, full_key)
        elif isinstance(value, list):
            console.print(f"[green]{key}[/green] = {json.dumps(value)}")
        elif isinstance(value, bool):
            console.print(f"[green]{key}[/green] = {'true' if value else 'false'}")
        elif isinstance(value, str):
            console.print(f'[green]{key}[/green] = "{value}"')
        else:
            console.print(f"[green]{key}[/green] = {value}")


@app.command("paths")
def config_paths() -> None:
    """Show resolved XDG directory paths."""
    from rich.table import Table

    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan")
    table.add_column()
    table.add_column(style="dim")

    dirs = [
        ("Config", config_dir(), "XDG_CONFIG_HOME"),
        ("Data", data_dir(), "XDG_DATA_HOME"),
        ("State", state_dir(), "XDG_STATE_HOME"),
    ]

    for label, path, env_var in dirs:
        exists = "[green]exists[/green]" if path.exists() else "[yellow]not created[/yellow]"
        table.add_row(label, str(path), f"({exists}) [{env_var}]")

    console.print(table)
