"""Pydantic models for the A2A AgentCard protocol.

Mirrors the AgentCard message hierarchy defined in
``src/shoal/core/proto/a2a_core.proto``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentProvider(BaseModel):
    """Organization providing this agent."""

    organization: str
    url: str


class AgentCapabilities(BaseModel):
    """Capability flags for this agent."""

    streaming: bool = False
    push_notifications: bool = False
    state_transition_reports: bool = False


class AgentSkill(BaseModel):
    """A skill this agent can perform."""

    id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class AgentCard(BaseModel):
    """Metadata document describing a Claw runtime's capabilities.

    Returned by the GetAgentCard RPC and used for agent discovery.
    """

    name: str
    version: str
    provider: AgentProvider
    capabilities: AgentCapabilities
    skills: list[AgentSkill] = Field(default_factory=list)
    endpoint: str = ""
    description: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)
