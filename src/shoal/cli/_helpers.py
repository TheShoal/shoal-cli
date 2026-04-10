"""Shared CLI helper utilities to reduce duplication across commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

import typer

from shoal.cli._console import get_console
from shoal.core import git
from shoal.core.config import load_workspace_config

if TYPE_CHECKING:
    from shoal.models.config.workspace import TeamConfig


T = TypeVar("T")


def resolve_team_config(team_slug: str) -> tuple[str, TeamConfig]:
    """Look up a team by slug from workspace config.

    Args:
        team_slug: Team identifier to look up

    Returns:
        Tuple of (git_root, TeamConfig)

    Raises:
        typer.Exit: If workspace config or team is not found
    """
    console = get_console()
    root = git.git_root(".")
    ws_cfg = load_workspace_config(root)
    if not ws_cfg or not ws_cfg.teams:
        console.print("[red]No teams configured in .shoal/workspace.toml[/red]")
        raise typer.Exit(1)

    team = ws_cfg.teams.get(team_slug)
    if team is None:
        available = ", ".join(sorted(ws_cfg.teams.keys()))
        console.print(f"[red]Unknown team '{team_slug}'. Available: {available}[/red]")
        raise typer.Exit(1)
    return root, team


def init_bridge(factory_fn: type[T]) -> T:
    """Initialize a bridge with standard error handling.

    Args:
        factory_fn: Bridge factory function (e.g., get_linear_bridge)

    Returns:
        Initialized bridge instance

    Raises:
        typer.Exit: If bridge initialization fails
    """
    console = get_console()
    try:
        return factory_fn()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
