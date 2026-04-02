"""Shared lazy console for CLI modules."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console


# Console width for consistent panel formatting across help and error boxes
# Set this to a fixed width (e.g., 120) for consistent panel sizing
CONSOLE_WIDTH: int | None = None


@lru_cache(maxsize=1)
def get_console(*, width: int | None = None) -> Console:
    from rich.console import Console

    w = width if width is not None else CONSOLE_WIDTH
    if w is not None:
        return Console(width=w)
    return Console()


def get_stderr_console(*, width: int | None = None) -> Console:
    """Console that writes to stderr, used for error output."""
    from rich.console import Console

    w = width if width is not None else CONSOLE_WIDTH
    if w is not None:
        return Console(stderr=True, width=w)
    return Console(stderr=True)
