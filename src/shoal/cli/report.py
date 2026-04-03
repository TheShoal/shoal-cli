"""CLI commands for PM-facing reports."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.markdown import Markdown

from shoal.cli._console import get_console
from shoal.core import git
from shoal.core.config import load_workspace_config
from shoal.core.db import with_db
from shoal.models.config.workspace import TeamConfig

app = typer.Typer(no_args_is_help=True)


def _resolve_team_config(team_slug: str) -> TeamConfig:
    """Resolve a team config from workspace configuration."""
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
    return team


@app.command("session")
def report_session(
    session: Annotated[str, typer.Argument(help="Session name")],
    model: str = typer.Option("amazon.nova-lite-v1:0", "--model", help="LLM model name"),
) -> None:
    """Generate a report for one session."""
    asyncio.run(with_db(_report_session_impl(session, model=model)))


async def _report_session_impl(session: str, *, model: str) -> None:
    from shoal.services.report import generate_session_report

    console = get_console()
    try:
        report = await generate_session_report(session, model=model)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
    console.print(Markdown(report))


@app.command("team")
def report_team(
    team: Annotated[str, typer.Option("--team", help="Team slug (e.g. be, fe)")],
    model: str = typer.Option("amazon.nova-lite-v1:0", "--model", help="LLM model name"),
) -> None:
    """Generate a report across active sessions for a team."""
    asyncio.run(with_db(_report_team_impl(team, model=model)))


async def _report_team_impl(team: str, *, model: str) -> None:
    from shoal.services.report import generate_team_report

    console = get_console()
    team_cfg = _resolve_team_config(team)
    report = await generate_team_report(
        team_name=team_cfg.name or team,
        team_slug=team,
        linear_team_key=team_cfg.linear_slug,
        model=model,
    )
    console.print(Markdown(report))


@app.command("sprint")
def report_sprint(
    team: Annotated[str, typer.Option("--team", help="Team slug (e.g. be, fe)")],
    model: str = typer.Option("amazon.nova-lite-v1:0", "--model", help="LLM model name"),
    post: bool = typer.Option(
        False, "--post", help="Publish to the team's configured Linear target"
    ),
) -> None:
    """Generate a sprint report for a team."""
    asyncio.run(with_db(_report_sprint_impl(team, model=model, post=post)))


async def _report_sprint_impl(team: str, *, model: str, post: bool) -> None:
    from shoal.services.report import generate_sprint_report, post_sprint_report

    console = get_console()
    team_cfg = _resolve_team_config(team)

    if post:
        if team_cfg.report is None:
            console.print(
                f"Team '{team}' has no [teams.{team}.report] target configured",
                style="red",
                markup=False,
            )
            raise typer.Exit(1)
        try:
            posted = await post_sprint_report(
                team_name=team_cfg.name or team,
                team_slug=team,
                report_target=team_cfg.report,
                linear_team_key=team_cfg.linear_slug,
                model=model,
            )
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1) from None
        console.print(Markdown(posted.report))
        message = (
            f"[green]Posted {posted.target_kind} update ({posted.health}) to "
            + f"{posted.target_name}: {posted.update_url}[/green]"
        )
        console.print(message)
        return

    report = await generate_sprint_report(
        team_name=team_cfg.name or team,
        team_slug=team,
        linear_team_key=team_cfg.linear_slug,
        model=model,
    )
    console.print(Markdown(report))
