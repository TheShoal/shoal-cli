"""Session template commands: ls, show, validate, mixins."""

from __future__ import annotations

from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console

from shoal.core.config import (
    _load_template_raw,
    available_mixins,
    available_templates,
    load_mixin,
    load_template,
    mixins_dir,
    template_source,
    templates_dir,
)
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

    table = create_table(padding=(0, 1))
    table.add_column("NAME", style="bold")
    table.add_column("SOURCE")
    table.add_column("EXTENDS")
    table.add_column("MIX", justify="right")
    table.add_column("TOOL")
    table.add_column("WIN", justify="right")
    table.add_column("PANES", justify="right")
    table.add_column("DESCRIPTION", no_wrap=False)

    for name in names:
        source = template_source(name)
        try:
            raw = _load_template_raw(name)
            raw_tmpl = raw.get("template", {})
            extends_name = raw_tmpl.get("extends", "")
            mixins_list = raw_tmpl.get("mixins", [])
            template = load_template(name)
        except (ValidationError, ValueError, TypeError, FileNotFoundError):
            table.add_row(
                name,
                source,
                "-",
                "-",
                "-",
                "-",
                "-",
                "[red]invalid template[/red]",
            )
            continue

        pane_count = sum(len(w.panes) for w in template.windows)
        table.add_row(
            template.name,
            source,
            extends_name or "[dim]-[/dim]",
            str(len(mixins_list)) if mixins_list else "[dim]-[/dim]",
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
    raw: Annotated[bool, typer.Option("--raw", help="Show unresolved template")] = False,
) -> None:
    """Show a template as JSON (resolved by default)."""
    try:
        if raw:
            from shoal.core.config import _parse_template_data

            raw_data = _load_template_raw(name)
            template = _parse_template_data(raw_data, name)
        else:
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
            extends_info = ""
            try:
                raw = _load_template_raw(template_name)
                extends_name = raw.get("template", {}).get("extends")
                if extends_name:
                    extends_info = f" [dim](extends {extends_name})[/dim]"
            except FileNotFoundError:
                pass
            console.print(f"[green]OK[/green] {template_name}{extends_info}")
        except FileNotFoundError:
            console.print(f"[red]MISSING[/red] {template_name}")
            errors += 1
        except (ValidationError, ValueError, TypeError) as exc:
            console.print(f"[red]INVALID[/red] {template_name}")
            console.print(f"[dim]{exc}[/dim]")
            errors += 1

    if errors:
        raise typer.Exit(1)


@app.command("mixins")
def template_mixins_cmd() -> None:
    """List available template mixins."""
    names = available_mixins()
    if not names:
        console.print("[yellow]No mixins found[/yellow]")
        console.print(f"[dim]Directory: {mixins_dir()}[/dim]")
        return

    table = create_table(padding=(0, 2))
    table.add_column("NAME", style="bold")
    table.add_column("MCP", width=20)
    table.add_column("WINDOWS", width=8, justify="right")
    table.add_column("DESCRIPTION")

    for name in names:
        try:
            m = load_mixin(name)
        except (ValidationError, ValueError, TypeError, FileNotFoundError):
            table.add_row(name, "-", "-", "[red]invalid mixin[/red]")
            continue

        table.add_row(
            m.name,
            ", ".join(m.mcp) if m.mcp else "[dim]-[/dim]",
            str(len(m.windows)) if m.windows else "[dim]-[/dim]",
            m.description or "[dim]-[/dim]",
        )

    console.print()
    console.print(table)
