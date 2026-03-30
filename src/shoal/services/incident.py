"""Shared incident ingestion, lane spawning, and query services."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import cast

from shoal.core import git
from shoal.core.config import available_templates, load_config, load_template, load_tool_config
from shoal.core.incident import (
    append_incident_event,
    attach_lane,
    create_incident,
    get_incident,
    list_incidents,
)
from shoal.core.journal import append_entry, build_journal_metadata, journal_exists
from shoal.core.prompt_delivery import build_tool_command_with_prompt
from shoal.core.state import find_by_name
from shoal.models.config import SessionTemplateConfig, ToolConfig
from shoal.models.incident import (
    AlertPayload,
    IncidentEvent,
    IncidentIngestRequest,
    IncidentLane,
    IncidentRecord,
    IncidentRole,
    IncidentSpawnRequest,
    IncidentStatus,
    slugify_title,
)
from shoal.models.state import SessionState
from shoal.services.lifecycle import create_session_lifecycle
from shoal.services.runtime_provider import provider_for_session

INCIDENT_TAG_PREFIX = "incident:"
INCIDENT_ROLE_TAG_PREFIX = "incident-role:"
INCIDENT_SEVERITY_TAG_PREFIX = "incident-severity:"

_ROLE_FOCUS = {
    IncidentRole.supervisor: (
        "Coordinate the response, delegate lanes, and maintain a truthful triage log."
    ),
    IncidentRole.investigator: (
        "Investigate likely causes, narrow the blast radius, and report evidence."
    ),
    IncidentRole.repro: ("Reproduce the failure or isolate why it cannot be reproduced safely."),
    IncidentRole.comms: (
        "Draft operator and stakeholder updates with explicit uncertainty and next steps."
    ),
    IncidentRole.reviewer: (
        "Review candidate fixes for correctness, risk, and missing verification."
    ),
}


def incident_tag(incident_id: str) -> str:
    """Return the canonical tag used on sessions linked to an incident."""
    return f"{INCIDENT_TAG_PREFIX}{incident_id}"


def incident_role_tag(role: str) -> str:
    """Return the canonical role tag used on incident worker sessions."""
    return f"{INCIDENT_ROLE_TAG_PREFIX}{role}"


def incident_severity_tag(severity: str) -> str:
    """Return the canonical severity tag used on incident worker sessions."""
    return f"{INCIDENT_SEVERITY_TAG_PREFIX}{severity}"


def load_alert_payload(raw_source: str) -> AlertPayload:
    """Load an alert payload from JSON text, stdin, or a file path."""
    source = raw_source.strip()
    if not source:
        raise ValueError("Alert payload source must not be empty")

    if source == "-":
        payload_text = sys.stdin.read()
    else:
        source_path = Path(source).expanduser()
        payload_text = source_path.read_text() if source_path.exists() else source

    try:
        payload_obj = cast(object, json.loads(payload_text))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid alert payload JSON: {exc}") from exc
    return AlertPayload.model_validate(payload_obj)


async def ingest_incident(request: IncidentIngestRequest) -> IncidentRecord:
    """Create and persist an incident record from an ingest request."""
    git_root = ""
    if request.path:
        resolved_path = Path(request.path).expanduser().resolve()
        if git.is_git_repo(str(resolved_path)):
            git_root = git.git_root(str(resolved_path))
        else:
            git_root = str(resolved_path)

    incident = await create_incident(request.alert, git_root=git_root)
    if not request.spawn_supervisor:
        return incident

    try:
        _ = await spawn_incident_lane(
            incident.id,
            IncidentSpawnRequest(
                role=IncidentRole.supervisor,
                tool=request.tool,
                template=request.template,
            ),
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        _ = await append_incident_event(
            incident.id,
            IncidentEvent(
                kind="incident.supervisor_spawn_failed",
                source="shoal",
                message=str(exc),
            ),
        )

    updated = await get_incident(incident.id)
    return updated if updated is not None else incident


async def list_incident_records(*, status: IncidentStatus | None = None) -> list[IncidentRecord]:
    """Return incidents ordered by most recent activity."""
    return await list_incidents(status=status)


async def get_incident_record(incident_id_or_slug: str) -> IncidentRecord | None:
    """Resolve an incident for show/detail flows."""
    return await get_incident(incident_id_or_slug)


async def resolve_incident(
    incident_id_or_slug: str,
    *,
    note: str = "",
) -> IncidentRecord:
    """Mark an incident resolved and record a timeline event."""
    record = await get_incident(incident_id_or_slug)
    if record is None:
        raise ValueError(f"Incident not found: {incident_id_or_slug}")
    message = note.strip() or "Incident resolved."
    updated = await update_incident_status(
        record.id,
        IncidentStatus.resolved,
        source="cli",
        message=message,
    )
    return updated if updated is not None else record


async def spawn_incident_lane(
    incident_id: str,
    request: IncidentSpawnRequest,
) -> SessionState:
    """Create a worker session for an incident and record it as a lane."""
    incident = await get_incident(incident_id)
    if incident is None:
        raise ValueError(f"Incident not found: {incident_id}")
    if not incident.git_root:
        raise ValueError(
            "Incident has no git root. Re-ingest with --path or provide a repo-backed "
            "incident path first."
        )

    cfg = load_config()
    resolved_tool = request.tool or cfg.general.default_tool
    tool_cfg = load_tool_config(resolved_tool)
    template_cfg, resolved_template_name = _resolve_template_for_lane(
        resolved_tool,
        request.template,
    )
    if request.tool is None and template_cfg is not None and template_cfg.tool:
        resolved_tool = template_cfg.tool
        tool_cfg = load_tool_config(resolved_tool)

    mcp_servers = (
        sorted(set(template_cfg.mcp)) if template_cfg is not None and template_cfg.mcp else None
    )
    session_name = await _resolve_session_name(incident, request)
    prompt = _build_lane_prompt(incident, request)
    tool_command = _tool_command_for_prompt(tool_cfg, prompt, session_name)

    session = await create_session_lifecycle(
        session_name=session_name,
        tool=resolved_tool,
        git_root=incident.git_root,
        wt_path="",
        work_dir=incident.git_root,
        branch_name=git.current_branch(incident.git_root),
        tool_command=tool_command,
        startup_commands=cfg.tmux.startup_commands,
        template_cfg=template_cfg,
        mcp_servers=mcp_servers,
        extra_env={
            "SHOAL_INCIDENT_ID": incident.id,
            "SHOAL_INCIDENT_ROLE": request.role.value,
            "SHOAL_INCIDENT_SEVERITY": incident.alert.severity.value,
            "SHOAL_INCIDENT_TITLE": incident.alert.title,
        },
        tags=[
            incident_tag(incident.id),
            incident_role_tag(request.role.value),
            incident_severity_tag(incident.alert.severity.value),
        ],
    )

    if prompt and tool_cfg.input_mode == "keys":
        provider = provider_for_session(session)
        await provider.async_wait_for_ready(session, tool_cfg, ready_timeout=5.0)
        await provider.async_send_input(session, prompt, delay=tool_cfg.send_keys_delay)

    lane = IncidentLane(
        session_id=session.id,
        session_name=session.name,
        role=request.role,
        tool=session.tool,
        template_name=resolved_template_name,
    )
    updated = await attach_lane(
        incident.id,
        lane,
        set_supervisor=request.role is IncidentRole.supervisor,
    )
    if updated is None:
        raise RuntimeError(f"Failed to attach lane for incident {incident.id}")

    await asyncio.to_thread(_seed_session_journal, session, incident, request.role)
    return session


async def update_incident_status(
    incident_id: str,
    status: IncidentStatus,
    *,
    source: str = "shoal",
    message: str | None = None,
) -> IncidentRecord | None:
    """Update status and append a timeline event."""
    event_message = message or f"Incident status changed to {status.value}"
    _ = await append_incident_event(
        incident_id,
        IncidentEvent(
            kind="incident.status_changed",
            source=source,
            message=event_message,
            data={"status": status.value},
        ),
    )
    incident = await get_incident(incident_id)
    if incident is None:
        return None
    from shoal.core.db import get_db

    db = await get_db()
    return await db.update_incident(incident.id, status=status)


def _resolve_template_for_lane(
    tool: str,
    requested_template: str | None,
) -> tuple[SessionTemplateConfig | None, str]:
    if requested_template:
        template = load_template(requested_template)
        return template, template.name

    available = set(available_templates())
    preferred_templates = {
        "claude": ["claude-dev"],
        "omp": ["omp-dev", "base-dev"],
        "opencode": ["opencode-dev", "base-dev"],
    }
    for template_name in preferred_templates.get(tool, []):
        if template_name in available:
            template = load_template(template_name)
            return template, template.name
    return None, ""


async def _resolve_session_name(
    incident: IncidentRecord,
    request: IncidentSpawnRequest,
) -> str:
    if request.name:
        return request.name

    project = Path(incident.git_root).name if incident.git_root else "incident"
    role_slug = request.role.value.removeprefix("incident-")
    base_name = f"{project}/incident-{slugify_title(incident.alert.title)}-{role_slug}"
    candidate = base_name
    counter = 2
    while await find_by_name(candidate):
        candidate = f"{base_name}-{counter}"
        counter += 1
    return candidate


def _tool_command_for_prompt(tool_cfg: ToolConfig, prompt: str, session_key: str) -> str:
    if not prompt or tool_cfg.input_mode == "keys":
        return tool_cfg.command
    return build_tool_command_with_prompt(tool_cfg, prompt, session_key)


def _build_lane_prompt(incident: IncidentRecord, request: IncidentSpawnRequest) -> str:
    metadata_block = ""
    if incident.alert.metadata:
        metadata_json = json.dumps(incident.alert.metadata, indent=2, sort_keys=True)
        metadata_block = f"\nMetadata:\n```json\n{metadata_json}\n```\n"

    url_block = f"\nReference URL: {incident.alert.url}\n" if incident.alert.url else "\n"
    extra_summary = f"\nAdditional direction: {request.summary}\n" if request.summary else "\n"
    return (
        f"You are the {request.role.value} lane for Shoal incident {incident.id}.\n\n"
        f"Severity: {incident.alert.severity.value}\n"
        f"Title: {incident.alert.title}\n"
        f"Source: {incident.alert.source}\n"
        f"Reason: {incident.alert.reason}\n"
        f"Git root: {incident.git_root or '(not provided)'}\n"
        f"{url_block}"
        f"{metadata_block}"
        f"Role focus: {_ROLE_FOCUS[request.role]}\n"
        "Work inside Shoal's existing journal/handoff workflow. Be explicit about uncertainty,"
        " evidence, and next steps.\n"
        f"{extra_summary}"
    )


def _seed_session_journal(
    session: SessionState,
    incident: IncidentRecord,
    role: IncidentRole,
) -> None:
    if journal_exists(session.id):
        return

    metadata = build_journal_metadata(session)
    _ = append_entry(
        session.id,
        (
            f"Incident {incident.id} ({incident.alert.severity.value})\n\n"
            f"Title: {incident.alert.title}\n"
            f"Role: {role.value}\n"
            f"Source: {incident.alert.source}\n"
            f"Reason: {incident.alert.reason}\n"
        ),
        source="incident",
        metadata=metadata,
    )
