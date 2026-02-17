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
    uninstall: bool = typer.Option(False, "--uninstall", help="Remove fish integration files"),
) -> None:
    """Install fish shell integration."""
    if uninstall:
        from shoal.integrations.fish.installer import uninstall_fish_integration

        success = uninstall_fish_integration()
    else:
        from shoal.integrations.fish.installer import install_fish_integration

        success = install_fish_integration(force=force)
    if not success:
        raise typer.Exit(code=1)
