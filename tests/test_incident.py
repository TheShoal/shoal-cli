"""Tests for incident supervision models, services, and CLI commands."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from shoal.cli import app
from shoal.core.db import with_db
from shoal.core.incident import get_incident
from shoal.core.journal import read_journal
from shoal.core.state import create_session
from shoal.models.incident import (
    AlertPayload,
    AlertSeverity,
    ClaudeHookEventName,
    IncidentHookEnvelope,
    IncidentIngestRequest,
    IncidentRole,
    IncidentSpawnRequest,
)
from shoal.models.state import SessionState, TmuxRuntimeState
from shoal.services.incident import incident_tag, list_incident_records, spawn_incident_lane
from shoal.services.incident_hooks import record_claude_hook_event, scaffold_claude_hook_files

runner = CliRunner()


def _alert_payload() -> AlertPayload:
    return AlertPayload(
        severity=AlertSeverity.critical,
        title="API outage in payments",
        source="pagerduty",
        reason="Checkout requests are timing out for multiple customers",
        score=97.3,
        url="https://status.example.com/incidents/123",
        metadata={"service": "payments", "customer_impact": "high"},
    )


@pytest.mark.asyncio
async def test_ingest_incident_persists_alert(mock_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    _ = mock_dirs
    from shoal.services.incident import ingest_incident

    incident = await ingest_incident(
        IncidentIngestRequest(
            alert=_alert_payload(),
            path=str(tmp_path),
            spawn_supervisor=False,
        )
    )

    reloaded = await get_incident(incident.id)
    assert reloaded is not None
    assert reloaded.alert.title == "API outage in payments"
    assert reloaded.events[0].kind == "incident.ingested"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["claude", "omp", "opencode"])
async def test_spawn_incident_lane_supports_worker_tools(
    mock_dirs: tuple[Path, Path],
    tmp_path: Path,
    tool_name: str,
) -> None:
    _ = mock_dirs
    from shoal.services.incident import ingest_incident

    incident = await ingest_incident(
        IncidentIngestRequest(
            alert=_alert_payload(),
            path=str(tmp_path),
            spawn_supervisor=False,
        )
    )

    async def _fake_create_session_lifecycle(**kwargs: object) -> SessionState:
        raw_tags = cast(list[str], kwargs.get("tags", []))
        return SessionState(
            id=f"sess-{tool_name}",
            name=str(kwargs["session_name"]),
            tool=str(kwargs["tool"]),
            path=str(tmp_path),
            branch=str(kwargs["branch_name"]),
            runtime=TmuxRuntimeState(session_name=f"shoal-{tool_name}"),
            tags=raw_tags,
        )

    with (
        patch("shoal.services.incident.git.current_branch", return_value="main"),
        patch(
            "shoal.services.incident.create_session_lifecycle",
            new=AsyncMock(side_effect=_fake_create_session_lifecycle),
        ) as mock_create,
    ):
        session = await spawn_incident_lane(
            incident.id,
            IncidentSpawnRequest(role=IncidentRole.investigator, tool=tool_name),
        )

    assert session.tool == tool_name
    assert mock_create.await_args is not None
    kwargs = mock_create.await_args.kwargs
    assert kwargs["extra_env"]["SHOAL_INCIDENT_ID"] == incident.id
    assert incident_tag(incident.id) in cast(list[str], kwargs["tags"])

    updated = await get_incident(incident.id)
    assert updated is not None
    assert updated.lanes[-1].tool == tool_name
    assert updated.lanes[-1].role == IncidentRole.investigator


@pytest.mark.asyncio
async def test_record_claude_hook_event_uses_session_incident_tag(
    mock_dirs: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    _ = mock_dirs
    from shoal.services.incident import ingest_incident

    incident = await ingest_incident(
        IncidentIngestRequest(
            alert=_alert_payload(),
            path=str(tmp_path),
            spawn_supervisor=False,
        )
    )
    session = await create_session(
        "incident-worker",
        "claude",
        str(tmp_path),
        tags=[incident_tag(incident.id)],
    )

    updated = await record_claude_hook_event(
        IncidentHookEnvelope(
            event_name=ClaudeHookEventName.task_completed,
            session_id=session.id,
            payload={"summary": "triage notes captured"},
        )
    )

    assert updated is not None
    assert updated.events[-1].kind == "claude.task_completed"
    entries = read_journal(session.id)
    assert entries[-1].source == "claude-hook"
    assert "TaskCompleted" in entries[-1].content


def test_scaffold_claude_hook_files_writes_examples(tmp_path: Path) -> None:
    paths = scaffold_claude_hook_files(tmp_path)

    assert paths["script"].exists()
    assert paths["settings"].exists()
    assert "TaskCreated" in paths["settings"].read_text()
    assert "TaskCompleted" in paths["settings"].read_text()
    assert "StopFailure" in paths["settings"].read_text()


def test_incident_cli_ingest_and_show(mock_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    _ = mock_dirs
    payload_path = tmp_path / "alert.json"
    _ = payload_path.write_text(
        json.dumps(
            {
                "severity": "critical",
                "title": "API outage in payments",
                "source": "pagerduty",
                "reason": "Checkout requests are timing out for multiple customers",
                "score": 97.3,
                "url": "https://status.example.com/incidents/123",
            }
        )
    )

    result = runner.invoke(
        app,
        [
            "incident",
            "ingest",
            str(payload_path),
            "--path",
            str(tmp_path),
            "--no-supervisor",
        ],
    )
    assert result.exit_code == 0
    assert "Incident ingested" in result.stdout

    incidents = asyncio.run(with_db(list_incident_records()))
    assert len(incidents) == 1

    show = runner.invoke(app, ["incident", "show", incidents[0].id])
    assert show.exit_code == 0
    assert "API outage in payments" in show.stdout


@pytest.mark.asyncio
async def test_resolve_incident_updates_status(mock_dirs: tuple[Path, Path]) -> None:
    _ = mock_dirs
    from shoal.services.incident import ingest_incident, resolve_incident

    request = IncidentIngestRequest(alert=_alert_payload(), spawn_supervisor=False)
    record = await with_db(ingest_incident(request))

    resolved = await with_db(resolve_incident(record.id, note="Root cause patched."))
    assert resolved.status.value == "resolved"
    # Timeline should contain the resolution event
    events = [e.kind for e in resolved.events]
    assert any("status" in k for k in events), f"No status event found in {events}"


def test_incident_cli_resolve(mock_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    _ = mock_dirs
    payload_path = tmp_path / "alert.json"
    _ = payload_path.write_text(
        json.dumps(
            {
                "severity": "high",
                "title": "Email delivery degraded",
                "source": "datadog",
                "reason": "SMTP queue depth exceeded threshold",
            }
        )
    )

    ingest = runner.invoke(
        app,
        ["incident", "ingest", str(payload_path), "--path", str(tmp_path), "--no-supervisor"],
    )
    assert ingest.exit_code == 0

    incidents = asyncio.run(with_db(list_incident_records()))
    assert len(incidents) == 1
    inc_id = incidents[0].id

    result = runner.invoke(app, ["incident", "resolve", inc_id, "--note", "Queue drained."])
    assert result.exit_code == 0, result.stdout
    assert "Incident resolved" in result.stdout

    updated = asyncio.run(with_db(list_incident_records()))
    assert updated[0].status.value == "resolved"
