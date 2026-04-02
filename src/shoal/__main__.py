"""Support python -m shoal."""

from __future__ import annotations

import typer
from click.exceptions import (
    Abort,
    BadParameter,
    ClickException,
    UsageError,
)
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from shoal.cli import app


def _format_exception(exc: BaseException) -> None:
    """Format and print exceptions with consistent styling."""
    console = Console(stderr=True)

    if isinstance(exc, BadParameter):
        msg = str(exc.message) if hasattr(exc, "message") else str(exc)
        title = "Invalid Parameter"
    elif isinstance(exc, UsageError):
        msg = str(exc.message) if hasattr(exc, "message") else str(exc)
        title = "Usage Error"
    elif isinstance(exc, Abort):
        msg = "Operation aborted."
        title = "Aborted"
    elif isinstance(exc, ClickException):
        msg = str(exc)
        title = "Error"
    else:
        msg = str(exc)
        title = "Error"

    panel = Panel(
        Text(msg, style="bold red"),
        title=f"[bold red]{title}[/bold red]",
        border_style="red",
        box=box.ROUNDED,
    )
    console.print(panel)


def main() -> None:
    """Run the app with consistent error handling."""
    try:
        app()
    except (BadParameter, UsageError, Abort) as exc:
        _format_exception(exc)
        raise typer.Exit(1) from exc
    except ClickException as exc:
        _format_exception(exc)
        raise typer.Exit(exc.exit_code) from exc


if __name__ == "__main__":
    main()
