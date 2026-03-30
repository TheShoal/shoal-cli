"""Claude hook integration for incident worker sessions."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
from pathlib import Path

from shoal.core.incident import append_incident_event, get_incident
from shoal.core.journal import append_entry
from shoal.core.state import get_session
from shoal.models.incident import (
    ClaudeHookEventName,
    IncidentEvent,
    IncidentHookEnvelope,
    IncidentRecord,
)
from shoal.services.incident import incident_tag


def scaffold_claude_hook_files(output_dir: Path, *, force: bool = False) -> dict[str, Path]:
    """Write example Claude hook files without mutating user config automatically."""
    output_dir.mkdir(parents=True, exist_ok=True)
    script_path = output_dir / "report_hook.sh"
    settings_path = output_dir / "settings.json.example"

    files = {
        script_path: _build_hook_reporter_script(),
        settings_path: _build_claude_settings_example(script_path),
    }
    for path, content in files.items():
        if path.exists() and not force:
            raise FileExistsError(f"Refusing to overwrite existing file: {path}")
        _ = path.write_text(content)

    script_path.chmod(0o755)
    return {
        "script": script_path,
        "settings": settings_path,
    }


async def record_claude_hook_event(envelope: IncidentHookEnvelope) -> IncidentRecord | None:
    """Record a Claude hook event against the incident linked to the session."""
    session = await get_session(envelope.session_id)
    if session is None:
        raise ValueError(f"Session not found: {envelope.session_id}")

    resolved_incident_id = envelope.incident_id or _incident_id_from_session(session.tags)
    if not resolved_incident_id:
        return None

    incident = await get_incident(resolved_incident_id)
    if incident is None:
        return None

    event = IncidentEvent(
        kind=_event_kind(envelope.event_name),
        source="claude-hook",
        message=_event_message(envelope),
        data={
            "session_id": envelope.session_id,
            "session_name": session.name,
            "payload": envelope.payload,
        },
    )
    updated = await append_incident_event(incident.id, event)
    _ = await asyncio.to_thread(
        append_entry,
        session.id,
        _journal_message(envelope),
        "claude-hook",
    )
    return updated


def _incident_id_from_session(tags: list[str]) -> str:
    for tag in tags:
        if tag.startswith(f"{incident_tag('')}"):
            return tag.removeprefix(incident_tag(""))
    return ""


def _event_kind(event_name: ClaudeHookEventName) -> str:
    return {
        ClaudeHookEventName.task_created: "claude.task_created",
        ClaudeHookEventName.task_completed: "claude.task_completed",
        ClaudeHookEventName.stop_failure: "claude.stop_failure",
        ClaudeHookEventName.cwd_changed: "claude.cwd_changed",
        ClaudeHookEventName.file_changed: "claude.file_changed",
        ClaudeHookEventName.worktree_create: "claude.worktree_create",
        ClaudeHookEventName.worktree_remove: "claude.worktree_remove",
    }[event_name]


def _event_message(envelope: IncidentHookEnvelope) -> str:
    summary = _payload_summary(envelope)
    return (
        f"Claude hook {envelope.event_name.value}: {summary}"
        if summary
        else (f"Claude hook {envelope.event_name.value} received")
    )


def _payload_summary(envelope: IncidentHookEnvelope) -> str:
    if envelope.event_name is ClaudeHookEventName.task_created:
        return _first_string(envelope.payload, ["task", "description", "title"])
    if envelope.event_name is ClaudeHookEventName.task_completed:
        return _first_string(envelope.payload, ["task", "summary", "title"])
    if envelope.event_name is ClaudeHookEventName.stop_failure:
        return _first_string(envelope.payload, ["error", "message", "reason"])
    if envelope.event_name is ClaudeHookEventName.file_changed:
        return _first_string(envelope.payload, ["file", "path"])
    if envelope.event_name in {
        ClaudeHookEventName.cwd_changed,
        ClaudeHookEventName.worktree_create,
        ClaudeHookEventName.worktree_remove,
    }:
        return _first_string(envelope.payload, ["cwd", "path", "worktree"])
    return ""


def _first_string(payload: dict[str, object], keys: list[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _journal_message(envelope: IncidentHookEnvelope) -> str:
    payload_json = json.dumps(envelope.payload, indent=2, sort_keys=True)
    return (
        f"Claude hook event: {envelope.event_name.value}\n\n"
        f"Payload:\n```json\n{payload_json}\n```\n"
    )


def _build_hook_reporter_script() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail

EVENT_NAME=${1:?missing hook event name}
SESSION_ID=${SHOAL_SESSION_ID:-}
INCIDENT_ID=${SHOAL_INCIDENT_ID:-}

if [ -z \"$SESSION_ID\" ]; then
  exit 0
fi

if [ -n \"$INCIDENT_ID\" ]; then
  shoal incident hook-report \"$EVENT_NAME\" --session \"$SESSION_ID\" --incident \"$INCIDENT_ID\"
else
  shoal incident hook-report \"$EVENT_NAME\" --session \"$SESSION_ID\"
fi
"""


def _build_claude_settings_example(script_path: Path) -> str:
    quoted_script = shlex.quote(str(script_path))
    command = f"{quoted_script}"
    settings = {
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "hooks": {
            event: [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{command} {event}",
                            "timeout": 10,
                            "statusMessage": "Reporting Claude incident hook to Shoal",
                        }
                    ]
                }
            ]
            for event in ["TaskCreated", "TaskCompleted", "StopFailure"]
        },
    }
    return json.dumps(settings, indent=2) + os.linesep
