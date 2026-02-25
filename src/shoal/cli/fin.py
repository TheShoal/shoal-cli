"""Fin extension commands: inspect, validate, run."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from shoal.services.fin_runtime import (
    FinRuntimeError,
    configure_fin,
    inspect_fin,
    install_fin,
    list_fins,
    run_fin,
    validate_fin,
)

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


@app.command("install")
def fin_install(
    fin_path: Annotated[str, typer.Argument(help="Path to fin root or fin.toml")],
) -> None:
    """Install a fin by executing its install entrypoint."""
    try:
        result = install_fin(fin_path)
    except FinRuntimeError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1) from None

    if result.stdout:
        typer.echo(result.stdout, nl=False)
    if result.stderr:
        typer.echo(result.stderr, err=True, nl=False)

    if result.exit_code != 0:
        raise typer.Exit(result.exit_code)


@app.command("configure")
def fin_configure(
    fin_path: Annotated[str, typer.Argument(help="Path to fin root or fin.toml")],
    config: Annotated[
        str | None,
        typer.Option("--config", help="Optional path to fin config file"),
    ] = None,
) -> None:
    """Configure a fin by executing its configure entrypoint."""
    try:
        result = configure_fin(fin_path, config_path=config)
    except FinRuntimeError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1) from None

    if result.stdout:
        typer.echo(result.stdout, nl=False)
    if result.stderr:
        typer.echo(result.stderr, err=True, nl=False)

    if result.exit_code != 0:
        raise typer.Exit(result.exit_code)


@app.command("ls")
def fin_ls(
    path: Annotated[
        str,
        typer.Option("--path", help="Directory or fin.toml path for discovery"),
    ] = ".",
) -> None:
    """List path-based fin candidates and manifest validity."""
    try:
        rows = list_fins(path)
    except FinRuntimeError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1) from None

    if not rows:
        typer.echo("No fin candidates found.")
        return

    for row in rows:
        if row.status == "valid":
            typer.echo(
                "\t".join(
                    [
                        "valid",
                        row.root,
                        row.name or "",
                        row.version or "",
                        row.capability or "",
                    ]
                )
            )
        else:
            typer.echo("\t".join(["invalid", row.root, row.error or "unknown error"]))


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
