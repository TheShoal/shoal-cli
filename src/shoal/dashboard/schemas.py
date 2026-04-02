"""Pydantic schemas for the Shoal web dashboard JSON API.

These schemas provide structured JSON responses for the dashboard partial
endpoints when ``?format=json`` is requested, enabling integration with
external tools like Pisces and Lobster Party.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SessionCardResponse(BaseModel):
    """JSON representation of a session card in the fleet grid."""

    id: str
    name: str
    tool: str
    tool_icon: str
    status: str
    status_label: str
    tier_css: str
    tier_name: str
    branch: str = ""
    worktree: str = ""
    mcp_servers: list[str] = Field(default_factory=list)
    last_activity: str
    created_at: str
    parent_id: str = ""
    tags: list[str] = Field(default_factory=list)
    template_name: str = ""


class FleetCountsResponse(BaseModel):
    """Aggregate session counts returned with fleet responses."""

    total: int = 0
    running: int = 0
    waiting: int = 0
    error: int = 0
    idle: int = 0
    stopped: int = 0
    unknown: int = 0
    attention: int = 0


class FleetResponse(BaseModel):
    """JSON response for fleet board partials."""

    session_cards: list[SessionCardResponse] = Field(default_factory=list)
    counts: FleetCountsResponse = Field(default_factory=FleetCountsResponse)


class SessionDetailResponse(BaseModel):
    """JSON representation of a session detail page."""

    id: str
    name: str
    tool: str
    tool_icon: str
    status: str
    status_label: str
    tier_css: str
    tier_name: str
    branch: str = ""
    worktree: str = ""
    path: str = ""
    mcp_servers: list[str] = Field(default_factory=list)
    parent_id: str = ""
    tags: list[str] = Field(default_factory=list)
    template_name: str = ""
    pid: int | None = None
    runtime_kind: str = "unknown"
    runtime_detail: dict[str, str] = Field(default_factory=dict)
    created_at_iso: str
    created_at: str
    last_activity_iso: str
    last_activity: str
    status_since_iso: str
    status_since: str
    completed_at: str | None = None


class JournalEntryResponse(BaseModel):
    """JSON representation of a journal entry."""

    timestamp_iso: str
    timestamp_rel: str
    source: str
    source_icon: str
    content_html: str
    content_raw: str


class PaneResponse(BaseModel):
    """JSON response for terminal pane capture."""

    session_id: str
    pane_text: str = ""
