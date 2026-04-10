"""CLI commands for PM-facing reports."""

from __future__ import annotations

import asyncio
import re
from datetime import date, timedelta
from typing import Annotated

import typer
from rich.markdown import Markdown

from shoal.cli._console import get_console
from shoal.cli._helpers import resolve_team_config
from shoal.core import git
from shoal.core.config import load_workspace_config
from shoal.core.db import with_db

app = typer.Typer(no_args_is_help=True)


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
    _root, team_cfg = resolve_team_config(team)
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
    _root, team_cfg = resolve_team_config(team)

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


def _parse_iso_week(week_str: str) -> tuple[date, date]:
    """Parse ISO week string (e.g., '2026-W15') to (start_date, end_date).

    Args:
        week_str: ISO week string in format YYYY-Www (e.g., '2026-W15')

    Returns:
        Tuple of (week_start_date, week_end_date) where start is Monday and end is Sunday.

    Raises:
        ValueError: If the week string format is invalid.
    """
    match = re.match(r"^(\d{4})-W(\d{2})$", week_str)
    if not match:
        raise ValueError(f"Invalid ISO week format: {week_str}. Expected format: YYYY-Www")

    year = int(match.group(1))
    week = int(match.group(2))

    if week < 1 or week > 53:
        raise ValueError(f"Invalid week number: {week}. Must be between 1 and 53")

    # ISO week 1 is the week with the year's first Thursday
    jan4 = date(year, 1, 4)
    week1_monday = jan4 - timedelta(days=jan4.weekday())
    target_monday = week1_monday + timedelta(weeks=week - 1)
    target_sunday = target_monday + timedelta(days=6)

    return target_monday, target_sunday


def _get_current_iso_week() -> str:
    """Get the current ISO week string (e.g., '2026-W15')."""
    from datetime import UTC, datetime

    today = datetime.now(UTC).date()
    iso_cal = today.isocalendar()
    return f"{iso_cal[0]}-W{iso_cal[1]:02d}"


@app.command("weekly")
def report_weekly(
    week: Annotated[
        str, typer.Option("--week", help="ISO week (e.g., 2026-W15), defaults to current week")
    ] = "",
    team: Annotated[str, typer.Option("--team", help="Team slug filter (e.g., be, fe)")] = "",
    model: str = typer.Option("amazon.nova-lite-v1:0", "--model", help="LLM model name"),
    post: bool = typer.Option(
        False, "--post", help="Publish to the team's configured Linear target"
    ),
) -> None:
    """Generate a weekly summary report."""
    asyncio.run(with_db(_report_weekly_impl(week=week, team=team, model=model, post=post)))


async def _report_weekly_impl(*, week: str, team: str, model: str, post: bool) -> None:
    from shoal.services.report import generate_weekly_summary

    console = get_console()

    # Parse or default the week
    if not week:
        week = _get_current_iso_week()

    try:
        week_start, week_end = _parse_iso_week(week)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None

    # Generate the report
    report = await generate_weekly_summary(
        week_start=week_start,
        week_end=week_end,
        team_slug=team if team else None,
        model=model,
    )

    console.print(Markdown(report))

    # TODO: Implement --post functionality for weekly reports
    if post:
        console.print("[yellow]Note: --post is not yet implemented for weekly reports[/yellow]")
