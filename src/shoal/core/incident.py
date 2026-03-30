"""Core incident state helpers backed by SQLite."""

from __future__ import annotations

from datetime import UTC, datetime

from shoal.core.db import get_db
from shoal.core.state import generate_id
from shoal.models.incident import (
    AlertPayload,
    IncidentEvent,
    IncidentLane,
    IncidentRecord,
    IncidentStatus,
    slugify_title,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def _unique_slug(base_slug: str) -> str:
    """Return a slug that is unique across incident records."""
    db = await get_db()
    slug = base_slug
    counter = 2
    while await db.find_incident_by_slug(slug):
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


async def create_incident(alert: AlertPayload, *, git_root: str = "") -> IncidentRecord:
    """Persist a new incident record from an alert payload."""
    db = await get_db()
    incident_id = f"inc-{generate_id()}"
    slug = await _unique_slug(slugify_title(alert.title))
    created_at = _utcnow()
    incident = IncidentRecord(
        id=incident_id,
        slug=slug,
        git_root=git_root,
        alert=alert,
        events=[
            IncidentEvent(
                kind="incident.ingested",
                source=alert.source,
                message=f"{alert.severity.value.upper()} alert ingested: {alert.title}",
                data={"source": alert.source},
            )
        ],
        created_at=created_at,
        updated_at=created_at,
    )
    await db.save_incident(incident)
    return incident


async def get_incident(incident_id_or_slug: str) -> IncidentRecord | None:
    """Resolve an incident by ID first, then by slug."""
    db = await get_db()
    incident = await db.get_incident(incident_id_or_slug)
    if incident is not None:
        return incident
    return await db.find_incident_by_slug(incident_id_or_slug)


async def list_incidents(*, status: IncidentStatus | None = None) -> list[IncidentRecord]:
    """List incidents ordered by most recent activity."""
    db = await get_db()
    return await db.list_incidents(status.value if status else None)


async def update_incident_status(
    incident_id: str,
    status: IncidentStatus,
    *,
    source: str = "shoal",
    message: str | None = None,
) -> IncidentRecord | None:
    """Update status and append a status-change event."""
    incident = await get_incident(incident_id)
    if incident is None:
        return None

    event_message = message or f"Incident status changed to {status.value}"
    events = [
        *incident.events,
        IncidentEvent(
            kind="incident.status_changed",
            source=source,
            message=event_message,
            data={"status": status.value},
        ),
    ]
    db = await get_db()
    return await db.update_incident(
        incident.id,
        status=status,
        events=events,
    )


async def attach_lane(
    incident_id: str,
    lane: IncidentLane,
    *,
    set_supervisor: bool = False,
    source: str = "shoal",
) -> IncidentRecord | None:
    """Attach a worker lane to an incident and append a timeline event."""
    incident = await get_incident(incident_id)
    if incident is None:
        return None

    events = [
        *incident.events,
        IncidentEvent(
            kind="incident.lane_added",
            source=source,
            message=f"Attached {lane.role.value} lane '{lane.session_name}' using {lane.tool}",
            data={
                "session_id": lane.session_id,
                "session_name": lane.session_name,
                "role": lane.role.value,
                "tool": lane.tool,
            },
        ),
    ]
    fields: dict[str, object] = {
        "lanes": [*incident.lanes, lane],
        "events": events,
    }
    if set_supervisor:
        fields["supervisor_session_id"] = lane.session_id

    db = await get_db()
    return await db.update_incident(incident.id, **fields)


async def append_incident_event(incident_id: str, event: IncidentEvent) -> IncidentRecord | None:
    """Append a timeline event to an incident."""
    incident = await get_incident(incident_id)
    if incident is None:
        return None

    db = await get_db()
    return await db.update_incident(incident.id, events=[*incident.events, event])


async def delete_incident(incident_id: str) -> bool:
    """Delete an incident record if it exists."""
    db = await get_db()
    incident = await db.get_incident(incident_id)
    if incident is None:
        return False
    await db.delete_incident(incident_id)
    return True
