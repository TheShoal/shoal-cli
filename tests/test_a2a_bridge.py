"""Tests for the lobster A2A bridge."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from shoal.integrations.lobster.a2a_bridge import GRPC_AVAILABLE, proto_to_agent_card
from shoal.models.config.agent_card import AgentCard

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_proto_card(
    *,
    name: str = "claw-abc",
    version: str = "2.0.0",
    endpoint: str = "grpc://host:50051",
    description: str = "Test Claw",
    org: str = "test-org",
    url: str = "https://test.com",
    streaming: bool = True,
    push_notifications: bool = False,
    state_transition_reports: bool = True,
    skills: list[object] | None = None,
    metadata: dict[str, str] | None = None,
) -> SimpleNamespace:
    """Build a minimal proto-like namespace for use with proto_to_agent_card."""
    return SimpleNamespace(
        name=name,
        version=version,
        endpoint=endpoint,
        description=description,
        provider=SimpleNamespace(organization=org, url=url),
        capabilities=SimpleNamespace(
            streaming=streaming,
            push_notifications=push_notifications,
            state_transition_reports=state_transition_reports,
        ),
        skills=skills or [],
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# GRPC Availability
# ---------------------------------------------------------------------------


@pytest.mark.skipif(GRPC_AVAILABLE, reason="grpcio is installed in this environment")
def test_grpc_available_false_without_grpcio() -> None:
    """GRPC_AVAILABLE is False when grpcio is not installed in dev env."""
    assert GRPC_AVAILABLE is False


# ---------------------------------------------------------------------------
# proto_to_agent_card
# ---------------------------------------------------------------------------


def test_proto_to_agent_card_basic() -> None:
    """Basic translation from proto namespace to AgentCard."""
    proto_card = _make_proto_card()
    result = proto_to_agent_card(proto_card, lobster_id="claw-abc", endpoint="grpc://host:50051")

    assert isinstance(result, AgentCard)
    assert result.name == "claw-abc"
    assert result.version == "2.0.0"
    assert result.endpoint == "grpc://host:50051"
    assert result.description == "Test Claw"
    assert result.provider.organization == "test-org"
    assert result.provider.url == "https://test.com"
    assert result.capabilities.streaming is True
    assert result.capabilities.push_notifications is False
    assert result.skills == []
    assert result.metadata == {}


def test_proto_to_agent_card_empty_name_uses_claw_id() -> None:
    """Falls back to claw_id when proto name is empty."""
    proto_card = _make_proto_card(name="")
    result = proto_to_agent_card(
        proto_card, lobster_id="fallback-claw", endpoint="grpc://host:50051"
    )
    assert result.name == "fallback-claw"


def test_proto_to_agent_card_empty_provider_uses_defaults() -> None:
    """Falls back to default provider values when proto provider fields are empty."""
    proto_card = _make_proto_card(org="", url="")
    result = proto_to_agent_card(proto_card, lobster_id="claw", endpoint="grpc://host")
    assert result.provider.organization == "us-mobile-lobster-party"
    assert result.provider.url == "https://usmobile.com"


def test_proto_to_agent_card_empty_endpoint_uses_fallback() -> None:
    """Falls back to endpoint arg when proto endpoint is empty."""
    proto_card = _make_proto_card(endpoint="")
    result = proto_to_agent_card(proto_card, lobster_id="claw", endpoint="grpc://fallback:9999")
    assert result.endpoint == "grpc://fallback:9999"


def test_proto_to_agent_card_with_skills() -> None:
    """Skills list is correctly translated."""
    skill1 = SimpleNamespace(id="s1", name="S1", description="desc1", tags=["tag1", "tag2"])
    skill2 = SimpleNamespace(id="s2", name="S2", description="", tags=[])
    proto_card = _make_proto_card(skills=[skill1, skill2])

    result = proto_to_agent_card(proto_card, lobster_id="claw", endpoint="grpc://host")

    assert len(result.skills) == 2
    assert result.skills[0].id == "s1"
    assert result.skills[0].name == "S1"
    assert result.skills[0].tags == ["tag1", "tag2"]
    assert result.skills[1].id == "s2"
    assert result.skills[1].tags == []


def test_proto_to_agent_card_with_metadata() -> None:
    """Metadata map is copied to result."""
    proto_card = _make_proto_card(metadata={"env": "prod", "region": "us-east-1"})
    result = proto_to_agent_card(proto_card, lobster_id="claw", endpoint="grpc://host")
    assert result.metadata == {"env": "prod", "region": "us-east-1"}
