"""Incident workflow commands: ingest, ls, show."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Annotated, cast

import typer
from rich.console import Console

from shoal.core.db import with_db
from shoal.core.theme import Icons, Symbols, create_panel, create_table
from shoal.models.incident import (
    ClaudeHookEventName,
    IncidentHookEnvelope,
    IncidentIngestRequest,
    IncidentRole,
    IncidentSpawnRequest,
    IncidentStatus,
)
from shoal.services.incident import (
    get_incident_record,
    ingest_incident,
    list_incident_records,
    load_alert_payload,
    resolve_incident,
    spawn_incident_lane,
)
from shoal.services.incident_hooks import record_claude_hook_event, scaffold_claude_hook_files

console = Console()
app = typer.Typer(
    name="incident",
    help="Incident supervision workflow.",
    no_args_is_help=False,
    invoke_without_command=True,
)

_SEVERITY_STYLE = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "cyan",
    "info": "dim",
}


@app.callback(invoke_without_command=True)
def incident_default(ctx: typer.Context) -> None:
    """Incident workflow (default: ls)."""
    if ctx.invoked_subcommand is None:
        incident_ls()


@app.command("ingest")
def incident_ingest(
    payload: Annotated[str, typer.Argument(help="JSON string, file path, or '-' for stdin")],
    path: Annotated[
        str | None, typer.Option("--path", help="Repo path for the incident context")
    ] = None,
    tool: Annotated[
        str | None,
        typer.Option("--tool", help="Preferred supervisor tool (used when spawning lanes)"),
    ] = None,
    template: Annotated[
        str | None,
        typer.Option("--template", help="Preferred supervisor template (used when spawning lanes)"),
    ] = None,
    no_supervisor: Annotated[
        bool,
        typer.Option("--no-supervisor", help="Ingest only; do not auto-spawn a supervisor lane"),
    ] = False,
) -> None:
    """Ingest a canonical alert payload into Shoal incident state."""
    try:
        alert = load_alert_payload(payload)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from None

    request = IncidentIngestRequest(
        alert=alert,
        path=path or ".",
        spawn_supervisor=not no_supervisor,
        tool=tool,
        template=template,
    )
    incident = asyncio.run(with_db(ingest_incident(request)))

    severity_style = _SEVERITY_STYLE[incident.alert.severity.value]
    table = create_table(padding=(0, 1))
    table.add_column("Field", style="bold cyan", width=14)
    table.add_column("Value", overflow="fold")
    table.add_row("Incident", f"[bold]{incident.id}[/bold] ({incident.slug})")
    table.add_row(
        "Severity",
        f"[{severity_style}]{incident.alert.severity.value}[/{severity_style}]",
    )
    table.add_row("Title", incident.alert.title)
    table.add_row("Source", incident.alert.source)
    table.add_row("Received", incident.alert.received_at.isoformat())
    if incident.git_root:
        table.add_row("Git root", incident.git_root)
    if incident.supervisor_session_id:
        table.add_row("Supervisor", incident.supervisor_session_id)

    console.print(
        create_panel(
            table,
            title=f"[bold blue]{Icons.STATUS} Incident ingested[/bold blue]",
            title_align="left",
            primary=True,
            padding=(0, 1),
        )
    )


@app.command("ls")
def incident_ls(
    status: Annotated[
        str | None,
        typer.Option("--status", help="Filter by status: active, monitoring, resolved"),
    ] = None,
) -> None:
    """List incident records."""
    try:
        parsed_status = IncidentStatus(status) if status else None
    except ValueError:
        console.print("[red]Error:[/red] Invalid incident status")
        raise typer.Exit(1) from None

    incidents = asyncio.run(with_db(list_incident_records(status=parsed_status)))
    if not incidents:
        console.print("[yellow]No incidents found[/yellow]")
        return

    table = create_table(padding=(0, 1))
    table.add_column("ID", width=12)
    table.add_column("SEV", width=8)
    table.add_column("STATUS", width=12)
    table.add_column("TITLE", min_width=24, ratio=3, overflow="fold")
    table.add_column("SOURCE", min_width=16, ratio=2, overflow="fold")
    table.add_column("LANES", width=7, justify="right")
    table.add_column("UPDATED", min_width=20)

    for incident in incidents:
        severity_style = _SEVERITY_STYLE[incident.alert.severity.value]
        table.add_row(
            incident.id,
            f"[{severity_style}]{incident.alert.severity.value}[/{severity_style}]",
            incident.status.value,
            incident.alert.title,
            incident.alert.source,
            str(len(incident.lanes)),
            incident.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        )

    console.print(
        create_panel(
            table,
            title=f"[bold blue]{Icons.STATUS} Active incidents[/bold blue]",
            title_align="left",
            primary=True,
            padding=(0, 1),
        )
    )


@app.command("spawn")
def incident_spawn(
    incident: Annotated[str, typer.Argument(help="Incident ID or slug")],
    role: Annotated[
        IncidentRole,
        typer.Option(
            "--role",
            help=(
                "Lane role: incident-supervisor, incident-investigator, incident-repro, "
                "incident-comms, incident-reviewer"
            ),
        ),
    ],
    tool: Annotated[
        str | None,
        typer.Option("--tool", help="Worker tool override (claude, omp, opencode, etc.)"),
    ] = None,
    template: Annotated[
        str | None,
        typer.Option("--template", help="Template override for this lane"),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option("--name", help="Explicit session name override"),
    ] = None,
    summary: Annotated[
        str,
        typer.Option("--summary", help="Additional operator direction for this lane"),
    ] = "",
) -> None:
    """Spawn an incident worker lane."""
    try:
        session = asyncio.run(
            with_db(
                spawn_incident_lane(
                    incident,
                    IncidentSpawnRequest(
                        role=role,
                        tool=tool,
                        template=template,
                        name=name,
                        summary=summary,
                    ),
                )
            )
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from None

    table = create_table(padding=(0, 1))
    table.add_column("Field", style="bold cyan", width=14)
    table.add_column("Value", overflow="fold")
    table.add_row("Session", f"[bold]{session.name}[/bold] ({session.id})")
    table.add_row("Role", role.value)
    table.add_row("Tool", session.tool)
    if session.branch:
        table.add_row("Branch", session.branch)
    if session.worktree:
        table.add_row("Worktree", session.worktree)

    console.print(
        create_panel(
            table,
            title=f"[bold blue]{Icons.SESSION} Incident lane created[/bold blue]",
            title_align="left",
            primary=True,
            padding=(0, 1),
        )
    )


@app.command("show")
def incident_show(
    incident: Annotated[str, typer.Argument(help="Incident ID or slug")],
) -> None:
    """Show detailed incident state."""
    record = asyncio.run(with_db(get_incident_record(incident)))
    if record is None:
        console.print(f"[red]Incident not found:[/red] {incident}")
        raise typer.Exit(1)

    summary = create_table(padding=(0, 1))
    summary.add_column("Field", style="bold cyan", width=16)
    summary.add_column("Value", overflow="fold")
    severity_style = _SEVERITY_STYLE[record.alert.severity.value]
    summary.add_row("Incident", f"[bold]{record.id}[/bold] ({record.slug})")
    summary.add_row("Status", record.status.value)
    summary.add_row(
        "Severity",
        f"[{severity_style}]{record.alert.severity.value}[/{severity_style}]",
    )
    summary.add_row("Title", record.alert.title)
    summary.add_row("Source", record.alert.source)
    summary.add_row("Reason", record.alert.reason)
    if record.alert.url:
        summary.add_row("URL", record.alert.url)
    if record.git_root:
        summary.add_row("Git root", record.git_root)
    if record.supervisor_session_id:
        summary.add_row("Supervisor", record.supervisor_session_id)

    console.print(
        create_panel(
            summary,
            title=f"[bold blue]{Icons.STATUS} Incident detail[/bold blue]",
            title_align="left",
            primary=True,
            padding=(0, 1),
        )
    )

    lanes = create_table(padding=(0, 1))
    lanes.add_column("ROLE", min_width=24, overflow="fold")
    lanes.add_column("SESSION", min_width=24, ratio=2, overflow="fold")
    lanes.add_column("TOOL", width=12)
    lanes.add_column("TEMPLATE", min_width=16, overflow="fold")
    if record.lanes:
        for lane in record.lanes:
            lanes.add_row(
                lane.role.value,
                f"{lane.session_name} [dim]({lane.session_id})[/dim]",
                lane.tool,
                lane.template_name or "-",
            )
    else:
        lanes.add_row("[dim]-[/dim]", "[dim]No worker lanes yet[/dim]", "-", "-")
    console.print(create_panel(lanes, title="[bold]Worker lanes[/bold]", title_align="left"))

    events = create_table(padding=(0, 1))
    events.add_column("AT", width=20)
    events.add_column("KIND", min_width=22, overflow="fold")
    events.add_column("SOURCE", width=14)
    events.add_column("MESSAGE", min_width=32, ratio=3, overflow="fold")
    if record.events:
        for event in record.events[-10:]:
            events.add_row(
                event.at.strftime("%Y-%m-%d %H:%M:%S"),
                event.kind,
                event.source,
                event.message,
            )
    else:
        events.add_row("-", "-", "-", "No timeline events")
    console.print(create_panel(events, title="[bold]Recent timeline[/bold]", title_align="left"))

    if record.alert.metadata:
        console.print(f"[bold]{Symbols.BULLET_FILLED} Metadata[/bold]")
        for key, value in sorted(record.alert.metadata.items()):
            console.print(f"  [cyan]{key}[/cyan]: {value}")


@app.command("resolve")
def incident_resolve(
    incident: Annotated[str, typer.Argument(help="Incident ID or slug")],
    note: Annotated[
        str,
        typer.Option("--note", help="Optional resolution note appended to the timeline"),
    ] = "",
) -> None:
    """Mark an incident resolved."""
    try:
        record = asyncio.run(with_db(resolve_incident(incident, note=note)))
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from None

    table = create_table(padding=(0, 1))
    table.add_column("Field", style="bold cyan", width=14)
    table.add_column("Value", overflow="fold")
    table.add_row("Incident", f"[bold]{record.id}[/bold] ({record.slug})")
    table.add_row("Status", record.status.value)
    if note.strip():
        table.add_row("Note", note.strip())

    console.print(
        create_panel(
            table,
            title=f"[bold blue]{Icons.STATUS} Incident resolved[/bold blue]",
            title_align="left",
            primary=True,
            padding=(0, 1),
        )
    )


@app.command("hook-scaffold")
def incident_hook_scaffold(
    output_dir: Annotated[
        str,
        typer.Option(
            "--output-dir",
            help="Directory where example Claude hook files should be written",
        ),
    ] = ".shoal/claude-hooks",
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite existing scaffold files in the output dir"),
    ] = False,
) -> None:
    """Generate example Claude hook files for manual opt-in incident reporting."""
    resolved_dir = Path(output_dir).expanduser().resolve()
    try:
        paths = scaffold_claude_hook_files(resolved_dir, force=force)
    except FileExistsError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from None

    table = create_table(padding=(0, 1))
    table.add_column("Artifact", style="bold cyan", width=12)
    table.add_column("Path", overflow="fold")
    table.add_row("Script", str(paths["script"]))
    table.add_row("Settings", str(paths["settings"]))

    console.print(
        create_panel(
            table,
            title=f"[bold blue]{Icons.STATUS} Claude hook scaffold[/bold blue]",
            title_align="left",
            primary=True,
            padding=(0, 1),
        )
    )
    console.print(
        "[dim]Manual opt-in:[/dim] copy the generated hooks stanza into .claude/settings.json "
        + "or .claude/settings.local.json yourself."
    )


@app.command("hook-report", hidden=True)
def incident_hook_report(
    event_name: Annotated[ClaudeHookEventName, typer.Argument(help="Claude hook event name")],
    session: Annotated[
        str | None,
        typer.Option("--session", help="Shoal session ID; defaults to SHOAL_SESSION_ID"),
    ] = None,
    incident: Annotated[
        str | None,
        typer.Option("--incident", help="Incident ID; defaults to SHOAL_INCIDENT_ID"),
    ] = None,
) -> None:
    """Internal hook ingestion entrypoint used by generated Claude hook scripts."""
    resolved_session = session or os.environ.get("SHOAL_SESSION_ID")
    if not resolved_session:
        return

    resolved_incident = incident or os.environ.get("SHOAL_INCIDENT_ID")
    payload_text = sys.stdin.read().strip()
    payload: dict[str, object] = {}
    if payload_text:
        try:
            raw_payload = cast(object, json.loads(payload_text))
        except json.JSONDecodeError:
            raw_payload = {"raw": payload_text}
        if isinstance(raw_payload, dict):
            normalized_payload: dict[str, object] = {}
            raw_payload_dict = cast(dict[object, object], raw_payload)
            for key_obj, value_obj in raw_payload_dict.items():
                normalized_payload[str(key_obj)] = value_obj
            payload = normalized_payload
        else:
            payload = {"raw": raw_payload}

    _ = asyncio.run(
        with_db(
            record_claude_hook_event(
                IncidentHookEnvelope(
                    event_name=event_name,
                    session_id=resolved_session,
                    incident_id=resolved_incident,
                    payload=payload,
                )
            )
        )
    )
