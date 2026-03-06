"""Fish shell integration installer."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from rich.console import Console

from shoal.core.theme import Icons, Symbols, create_panel, create_table


def get_template_dir() -> Path:
    """Get the directory containing fish template files."""
    return Path(__file__).parent / "templates"


def get_fish_config_dir() -> Path | None:
    """Get the user's fish configuration directory.

    Respects XDG_CONFIG_HOME if set, falling back to ~/.config/fish.
    """
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    fish_config = Path(xdg_config) / "fish" if xdg_config else Path.home() / ".config" / "fish"
    return fish_config if fish_config.exists() or fish_config.parent.exists() else None


def expected_fish_config_dir() -> Path:
    """Return the fish config directory implied by the current XDG environment."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg_config) / "fish" if xdg_config else Path.home() / ".config" / "fish"


def is_fish_installed() -> bool:
    """Check if fish shell is installed."""
    return shutil.which("fish") is not None


def install_fish_integration(force: bool = False) -> bool:
    """
    Install fish shell integration files.

    Args:
        force: If True, overwrite existing files

    Returns:
        True if installation succeeded, False otherwise
    """
    console = Console()

    # Check if fish is installed
    if not is_fish_installed():
        console.print(
            create_panel(
                "[red]Fish shell not found![/red]\n\n"
                "Fish shell integration requires fish to be installed.\n"
                "Install fish using your package manager:\n\n"
                "  • macOS: [cyan]brew install fish[/cyan]\n"
                "  • Ubuntu: [cyan]sudo apt install fish[/cyan]\n"
                "  • Fedora: [cyan]sudo dnf install fish[/cyan]",
                title=f"[bold red]{Icons.ERROR} Installation Failed[/bold red]",
                title_align="left",
            )
        )
        return False

    # Get fish config directory
    fish_config = get_fish_config_dir()
    if not fish_config:
        console.print(
            create_panel(
                "[red]Could not locate fish configuration directory![/red]\n\n"
                f"Expected location: [cyan]{expected_fish_config_dir()}[/cyan]",
                title=f"[bold red]{Icons.ERROR} Installation Failed[/bold red]",
                title_align="left",
            )
        )
        return False

    # Create fish config directories if they don't exist
    fish_config.mkdir(parents=True, exist_ok=True)
    completions_dir = fish_config / "completions"
    conf_d_dir = fish_config / "conf.d"
    functions_dir = fish_config / "functions"

    completions_dir.mkdir(exist_ok=True)
    conf_d_dir.mkdir(exist_ok=True)
    functions_dir.mkdir(exist_ok=True)

    # Template files to install
    template_dir = get_template_dir()
    installations = [
        (template_dir / "completions.fish", completions_dir / "shoal.fish", "Completions"),
        (template_dir / "bootstrap.fish", conf_d_dir / "shoal.fish", "Bootstrap"),
        (
            template_dir / "quick-attach.fish",
            functions_dir / "shoal-quick-attach.fish",
            "Quick Attach",
        ),
        (template_dir / "dashboard.fish", functions_dir / "shoal-dashboard.fish", "Dashboard"),
        (template_dir / "remote.fish", functions_dir / "shoal-remote.fish", "Remote"),
        (template_dir / "hooks.fish", conf_d_dir / "shoal-hooks.fish", "Hooks"),
    ]

    # Track installation results
    results = []

    for src, dest, name in installations:
        if not src.exists():
            results.append((name, dest, "error", "Template not found"))
            continue

        # Check if file already exists
        if dest.exists() and not force:
            results.append((name, dest, "skipped", "Already exists"))
            continue

        # Copy the file
        try:
            shutil.copy2(src, dest)
            results.append((name, dest, "success", "Installed"))
        except Exception as e:
            results.append((name, dest, "error", str(e)))

    # Display results
    table = create_table(padding=(0, 2))
    table.add_column("Component", width=20)
    table.add_column("Status", width=12)
    table.add_column("Location")

    for name, dest, status, message in results:
        if status == "success":
            marker = f"[green]{Symbols.CHECK}[/green]"
            status_text = f"{marker} {message}"
            location = f"[dim]{dest}[/dim]"
        elif status == "skipped":
            marker = f"[yellow]{Symbols.INFO}[/yellow]"
            status_text = f"{marker} {message}"
            location = f"[dim]{dest}[/dim]"
        else:  # error
            marker = f"[red]{Symbols.CROSS}[/red]"
            status_text = f"{marker} {message}"
            location = f"[dim]{dest}[/dim]"

        table.add_row(name, status_text, location)

    console.print(
        create_panel(
            table,
            title=f"[bold blue]{Icons.FISH} Fish Shell Integration[/bold blue]",
            title_align="left",
        )
    )

    # Check if any files were skipped
    skipped = [r for r in results if r[2] == "skipped"]
    if skipped and not force:
        console.print(
            "\n[yellow]Tip:[/yellow] Use [cyan]shoal setup fish --force[/cyan]"
            " to overwrite existing files."
        )

    # Success message
    errors = [r for r in results if r[2] == "error"]
    if not errors:
        source_path = conf_d_dir / "shoal.fish"
        console.print(
            "\n[green]Fish integration installed successfully![/green]\n\n"
            f"Restart your fish shell or run: [cyan]source {source_path}[/cyan]\n"
            "to start using the integration."
        )
        return True
    console.print(f"\n[red]Installation completed with {len(errors)} error(s).[/red]")
    return False


def uninstall_fish_integration() -> bool:
    """Remove fish shell integration files installed by shoal.

    Returns:
        True if uninstall succeeded, False otherwise.
    """
    console = Console()

    fish_config = get_fish_config_dir()
    if not fish_config:
        console.print("[yellow]No fish configuration directory found. Nothing to remove.[/yellow]")
        return True

    # These are the exact files the installer creates
    targets = [
        (fish_config / "completions" / "shoal.fish", "Completions"),
        (fish_config / "conf.d" / "shoal.fish", "Bootstrap"),
        (fish_config / "functions" / "shoal-quick-attach.fish", "Quick Attach"),
        (fish_config / "functions" / "shoal-dashboard.fish", "Dashboard"),
        (fish_config / "functions" / "shoal-remote.fish", "Remote"),
        (fish_config / "conf.d" / "shoal-hooks.fish", "Hooks"),
    ]

    removed = 0
    for path, name in targets:
        if path.exists():
            path.unlink()
            console.print(f"  {Symbols.CHECK} Removed {name}: [dim]{path}[/dim]")
            removed += 1
        else:
            console.print(f"  [dim]{Symbols.INFO} Not found: {path}[/dim]")

    if removed:
        console.print(f"\n[green]Removed {removed} fish integration file(s).[/green]")
    else:
        console.print("\n[yellow]No shoal fish integration files found to remove.[/yellow]")

    return True
