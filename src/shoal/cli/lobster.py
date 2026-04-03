"""Lobster runtime CLI commands: ping, send, tasks."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Annotated, cast

import typer

from shoal.cli._console import get_console
from shoal.core.theme import create_table

app = typer.Typer(
    name="lobster",
    help="Lobster runtime operations (requires shoal[claw]).",
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_grpc() -> None:
    """Abort with a clear message when grpcio is not installed."""
    try:
        import grpc as _grpc  # noqa: F401
    except ImportError as exc:
        typer.echo(
            "grpcio is not installed. Install with: pip install 'shoal[claw]'",
            err=True,
        )
        raise typer.Exit(1) from exc


def _resolve_endpoint(lobster_id: str) -> str:
    """Look up endpoint for *lobster_id* from config, aborting if not found."""
    from shoal.core.config import load_config

    cfg = load_config()
    endpoint = cfg.lobster.known_lobsters.get(lobster_id) or cfg.lobster.grpc_addr
    if not endpoint:
        typer.echo(
            f"Lobster '{lobster_id}' not found in known_lobsters and no grpc_addr fallback.",
            err=True,
        )
        raise typer.Exit(1)
    return endpoint


# ---------------------------------------------------------------------------
# Command: ping
# ---------------------------------------------------------------------------


@app.command("ping")
def lobster_ping(
    lobster_id: Annotated[str, typer.Argument(help="Lobster identifier to query")],
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON")] = False,
) -> None:
    """Fetch a Lobster's AgentCard (agent discovery smoke-test)."""
    _require_grpc()

    from shoal.core.config import load_config
    from shoal.core.lobster_client import LobsterClient
    from shoal.integrations.lobster import a2a_bridge as _bridge  # noqa: F401

    async def _run() -> dict[str, object]:
        cfg = load_config()
        endpoint = _resolve_endpoint(lobster_id)
        async with LobsterClient(
            claw_id=lobster_id,
            endpoint=endpoint,
            employee_id=cfg.lobster.employee_id,
            config=cfg.lobster,
        ) as client:
            card = await client.get_agent_card()  # type: ignore[attr-defined]
            result: dict[str, object] = card.model_dump()
            return result

    try:
        data = asyncio.run(_run())
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    if json_output:
        print(json.dumps(data, indent=2, default=str))
        return

    console = get_console()
    console.print(f"[bold]{data['name']}[/bold]  v{data['version']}")
    console.print(f"  endpoint:    {data['endpoint']}")
    console.print(f"  description: {data.get('description') or '\u2014'}")
    provider = cast(dict[str, str], data.get("provider") or {})
    console.print(f"  provider:    {provider.get('organization', '\u2014')}")

    caps = cast(dict[str, object], data.get("capabilities") or {})
    cap_parts = [k for k, v in caps.items() if v]
    console.print(f"  capabilities: {', '.join(cap_parts) or 'none'}")

    skills = cast(list[dict[str, str]], data.get("skills") or [])
    if skills:
        table = create_table(title=f"Skills on {lobster_id}")
        table.add_column("id")
        table.add_column("name")
        table.add_column("description")
        for s in skills:
            table.add_row(s.get("id", ""), s.get("name", ""), s.get("description", ""))
        console.print(table)


# ---------------------------------------------------------------------------
# Command: send
# ---------------------------------------------------------------------------


@app.command("send")
def lobster_send(
    lobster_id: Annotated[str, typer.Argument(help="Lobster identifier")],
    message: Annotated[str, typer.Argument(help="Message text to send")],
    task_id: Annotated[
        str | None, typer.Option("--task-id", help="Explicit task ID (idempotency key)")
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON")] = False,
) -> None:
    """Send a message to a Lobster and print the response."""
    _require_grpc()

    from shoal.core.config import load_config
    from shoal.core.lobster_client import LobsterClient
    from shoal.integrations.lobster import a2a_bridge as _bridge  # noqa: F401

    async def _run() -> dict[str, object]:
        cfg = load_config()
        endpoint = _resolve_endpoint(lobster_id)
        async with LobsterClient(
            claw_id=lobster_id,
            endpoint=endpoint,
            employee_id=cfg.lobster.employee_id,
            config=cfg.lobster,
        ) as client:
            result: dict[str, object] = await client.send_message(  # type: ignore[attr-defined]
                message=message,
                task_id=task_id,
            )
            return result

    try:
        data = asyncio.run(_run())
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    if json_output:
        print(json.dumps(data, indent=2, default=str))
        return

    console = get_console()
    console.print(f"[dim]task_id:[/dim] {data['task_id']}")
    console.print(f"[dim]state:  [/dim] {data['state']}")
    if data["response"]:
        console.print(f"\n{data['response']}")


# ---------------------------------------------------------------------------
# Command: tasks
# ---------------------------------------------------------------------------


@app.command("tasks")
def lobster_tasks(
    lobster_id: Annotated[str, typer.Argument(help="Lobster identifier")],
    context_id: Annotated[
        str | None, typer.Option("--context", help="Filter by context ID")
    ] = None,
    status: Annotated[
        str | None,
        typer.Option(
            "--status",
            help="Filter by state: working | input-required | completed | canceled | failed",
        ),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON")] = False,
) -> None:
    """List tasks on a Lobster runtime."""
    _require_grpc()

    from shoal.core.config import load_config
    from shoal.core.lobster_client import LobsterClient
    from shoal.integrations.lobster import a2a_bridge as _bridge  # noqa: F401

    async def _run() -> list[dict[str, object]]:
        cfg = load_config()
        endpoint = _resolve_endpoint(lobster_id)
        async with LobsterClient(
            claw_id=lobster_id,
            endpoint=endpoint,
            employee_id=cfg.lobster.employee_id,
            config=cfg.lobster,
        ) as client:
            tasks: list[dict[str, object]] = await client.list_tasks(  # type: ignore[attr-defined]
                context_id=context_id,
                status=status,
            )
            return tasks

    try:
        tasks = asyncio.run(_run())
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    if json_output:
        print(json.dumps(tasks, indent=2, default=str))
        return

    console = get_console()
    if not tasks:
        console.print(f"[dim]No tasks on {lobster_id}[/dim]")
        return

    table = create_table(title=f"Tasks on {lobster_id}")
    table.add_column("id")
    table.add_column("state")
    table.add_column("context_id")
    table.add_column("message")
    for t in tasks:
        table.add_row(
            str(t.get("id", "")),
            str(t.get("state", "")),
            str(t.get("context_id", "")),
            str(t.get("status_message", "")),
        )
    console.print(table)
    if sys.stdout.isatty():
        console.print(f"[dim]{len(tasks)} task(s)[/dim]")
