"""Fish shell integration installer."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from shoal.core.theme import Colors, Icons, Symbols, create_panel, create_table


def get_template_dir() -> Path:
    """Get the directory containing fish template files."""
    return Path(__file__).parent / "templates"


def get_fish_config_dir() -> Optional[Path]:
    """Get the user's fish configuration directory."""
    fish_config = Path.home() / ".config" / "fish"
    return fish_config if fish_config.exists() or fish_config.parent.exists() else None


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
                "Expected location: [cyan]~/.config/fish[/cyan]",
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
            f"\n[yellow]Tip:[/yellow] Use [cyan]shoal setup fish --force[/cyan] to overwrite existing files."
        )

    # Success message
    errors = [r for r in results if r[2] == "error"]
    if not errors:
        console.print(
            "\n[green]Fish integration installed successfully![/green]\n\n"
            "Restart your fish shell or run: [cyan]source ~/.config/fish/conf.d/shoal.fish[/cyan]\n"
            "to start using the integration."
        )
        return True
    else:
        console.print(f"\n[red]Installation completed with {len(errors)} error(s).[/red]")
        return False
