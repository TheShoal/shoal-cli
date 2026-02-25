"""Fin extension commands: inspect, validate, run."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from shoal.services.fin_runtime import FinRuntimeError, inspect_fin, run_fin, validate_fin

app = typer.Typer(no_args_is_help=True)


@app.command("inspect")
def fin_inspect(
    fin_path: Annotated[str, typer.Argument(help="Path to fin root or fin.toml")],
) -> None:
    """Inspect fin metadata and resolved entrypoints."""
    try:
        data = inspect_fin(fin_path)
    except FinRuntimeError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1) from None

    typer.echo(json.dumps(data, indent=2))


@app.command("validate")
def fin_validate(
    fin_path: Annotated[str, typer.Argument(help="Path to fin root or fin.toml")],
    strict: Annotated[bool, typer.Option("--strict", help="Enable strict validation mode")] = False,
) -> None:
    """Validate fin manifest and execute fin validate lifecycle."""
    try:
        result = validate_fin(fin_path, strict=strict)
    except FinRuntimeError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1) from None

    if result.stdout:
        typer.echo(result.stdout, nl=False)
    if result.stderr:
        typer.echo(result.stderr, err=True, nl=False)

    if result.exit_code != 0:
        raise typer.Exit(result.exit_code)


@app.command("run")
def fin_run(
    fin_path: Annotated[str, typer.Argument(help="Path to fin root or fin.toml")],
    config: Annotated[
        str | None,
        typer.Option("--config", help="Optional path to fin config file"),
    ] = None,
    output: Annotated[
        str,
        typer.Option("--output", help="Output format for fin env (text|json)"),
    ] = "text",
    args: Annotated[
        list[str] | None, typer.Argument(help="Arguments passed to fin run entrypoint")
    ] = None,
) -> None:
    """Run a fin with raw argument passthrough after --."""
    if output not in {"text", "json"}:
        raise typer.BadParameter("Output must be one of: text, json")

    try:
        result = run_fin(
            fin_path,
            config_path=config,
            output_format=output,
            args=args or [],
        )
    except FinRuntimeError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1) from None

    if result.stdout:
        typer.echo(result.stdout, nl=False)
    if result.stderr:
        typer.echo(result.stderr, err=True, nl=False)

    if result.exit_code != 0:
        raise typer.Exit(result.exit_code)
