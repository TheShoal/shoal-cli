"""Session template commands: ls, show, validate."""

from __future__ import annotations

from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console

from shoal.core.config import available_templates, load_template, templates_dir
from shoal.core.theme import create_table

console = Console()

app = typer.Typer(no_args_is_help=False, invoke_without_command=True)


@app.callback(invoke_without_command=True)
def template_default(ctx: typer.Context) -> None:
    """Template management (default: ls)."""
    if ctx.invoked_subcommand is None:
        template_ls()


@app.command("ls")
def template_ls() -> None:
    """List available global session templates."""
    names = available_templates()
    if not names:
        console.print("[yellow]No templates found[/yellow]")
        console.print(f"[dim]Directory: {templates_dir()}[/dim]")
        return

    table = create_table(padding=(0, 2))
    table.add_column("NAME", style="bold")
    table.add_column("TOOL", width=12)
    table.add_column("WINDOWS", width=8, justify="right")
    table.add_column("PANES", width=8, justify="right")
    table.add_column("DESCRIPTION")

    for name in names:
        try:
            template = load_template(name)
        except (ValidationError, ValueError, TypeError):
            table.add_row(name, "-", "-", "-", "[red]invalid template[/red]")
            continue

        pane_count = sum(len(w.panes) for w in template.windows)
        table.add_row(
            template.name,
            template.tool,
            str(len(template.windows)),
            str(pane_count),
            template.description or "[dim]-[/dim]",
        )

    console.print()
    console.print(table)


@app.command("show")
def template_show(
    name: Annotated[str, typer.Argument(help="Template name")],
) -> None:
    """Show a template as JSON."""
    try:
        template = load_template(name)
    except FileNotFoundError:
        console.print(f"[red]Template not found: {name}[/red]")
        available = available_templates()
        if available:
            console.print(f"[yellow]Available:[/yellow] {', '.join(available)}")
        raise typer.Exit(1) from None
    except (ValidationError, ValueError, TypeError) as exc:
        console.print(f"[red]Invalid template: {name}[/red]")
        console.print(f"[dim]{exc}[/dim]")
        raise typer.Exit(1) from None

    console.print_json(template.model_dump_json(indent=2))


@app.command("validate")
def template_validate(
    name: Annotated[str | None, typer.Argument(help="Template name", show_default=False)] = None,
) -> None:
    """Validate one template or all templates."""
    names = [name] if name else available_templates()
    if not names:
        console.print("[yellow]No templates found[/yellow]")
        console.print(f"[dim]Directory: {templates_dir()}[/dim]")
        return

    errors = 0
    for template_name in names:
        try:
            load_template(template_name)
            console.print(f"[green]OK[/green] {template_name}")
        except FileNotFoundError:
            console.print(f"[red]MISSING[/red] {template_name}")
            errors += 1
        except (ValidationError, ValueError, TypeError) as exc:
            console.print(f"[red]INVALID[/red] {template_name}")
            console.print(f"[dim]{exc}[/dim]")
            errors += 1

    if errors:
        raise typer.Exit(1)
