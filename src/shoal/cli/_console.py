"""Shared lazy console for CLI modules."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console


@lru_cache(maxsize=1)
def get_console() -> Console:
    from rich.console import Console

    return Console()
