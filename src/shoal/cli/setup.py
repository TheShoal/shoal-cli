"""Setup commands for shell integrations."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="setup",
    help="Setup shell integrations.",
    no_args_is_help=True,
)


@app.command()
def fish(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing files"),
) -> None:
    """Install fish shell integration."""
    from shoal.integrations.fish.installer import install_fish_integration

    success = install_fish_integration(force=force)
    if not success:
        raise typer.Exit(code=1)
