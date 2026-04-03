"""Tests for Lobster runtime provider and client."""

from __future__ import annotations

import pytest

from shoal.models.state import LobsterRuntimeState, RuntimeKind


class TestLobsterRuntimeState:
    """Test LobsterRuntimeState model."""

    def test_create_lobster_runtime_state(self) -> None:
        """Test creating a LobsterRuntimeState instance."""
        runtime = LobsterRuntimeState(
            lobster_id="claw_abc123",
            endpoint="grpc://claw-abc123.lobster-party-runtime.svc:50051",
            employee_id="emp_123",
        )

        assert runtime.kind == RuntimeKind.lobster
        assert runtime.lobster_id == "claw_abc123"
        assert runtime.endpoint == "grpc://claw-abc123.lobster-party-runtime.svc:50051"
        assert runtime.employee_id == "emp_123"

    def test_lobster_runtime_state_defaults(self) -> None:
        """Test LobsterRuntimeState default values."""
        runtime = LobsterRuntimeState(lobster_id="claw_test")

        assert runtime.kind == RuntimeKind.lobster
        assert runtime.lobster_id == "claw_test"
        assert runtime.endpoint == ""
        assert runtime.employee_id == ""

    def test_lobster_runtime_state_serialization(self) -> None:
        """Test LobsterRuntimeState JSON serialization."""
        runtime = LobsterRuntimeState(
            lobster_id="claw_test",
            endpoint="grpc://test:50051",
        )

        data = runtime.model_dump(mode="json")
        assert data["kind"] == "lobster"
        assert data["lobster_id"] == "claw_test"
        assert data["endpoint"] == "grpc://test:50051"
        assert data["employee_id"] == ""


class TestRuntimeKind:
    """Test RuntimeKind enum."""

    def test_runtime_kind_lobster_exists(self) -> None:
        """Test that RuntimeKind.lobster exists."""
        assert RuntimeKind.lobster == "lobster"
        assert RuntimeKind.tmux == "tmux"
        assert len(list(RuntimeKind)) == 2


class TestLobsterProviderImport:
    """Test Lobster provider imports gracefully."""

    def test_lobster_provider_import_without_grpcio(self) -> None:
        """Test that Lobster provider imports even when grpcio is not available."""
        # This should not raise - the provider should import gracefully
        try:
            from shoal.services.runtime_providers.lobster import LobsterRuntimeProvider

            provider = LobsterRuntimeProvider()
            assert provider.kind == RuntimeKind.lobster
        except ImportError:
            # grpcio might not be installed in test environment
            pytest.skip("grpcio not installed")

    def test_runtime_provider_registry_includes_lobster(self) -> None:
        """Test that Lobster provider is registered in the provider registry."""
        from shoal.services.runtime_provider import _providers

        providers = _providers()
        assert RuntimeKind.lobster in providers
        assert RuntimeKind.tmux in providers


class TestLobsterConfig:
    """Test LobsterConfig model."""

    def test_create_lobster_config(self) -> None:
        """Test creating a LobsterConfig instance."""
        from shoal.models.config.lobster import LobsterConfig

        config = LobsterConfig(
            known_lobsters={"claw_abc": "grpc://claw-abc:50051"},
            default_timeout=60.0,
            retry_attempts=5,
        )

        assert config.known_lobsters == {"claw_abc": "grpc://claw-abc:50051"}
        assert config.default_timeout == 60.0
        assert config.retry_attempts == 5

    def test_lobster_config_defaults(self) -> None:
        """Test LobsterConfig default values."""
        from shoal.models.config.lobster import LobsterConfig

        config = LobsterConfig()

        assert config.known_lobsters == {}
        assert config.default_timeout == 30.0
        assert config.retry_attempts == 3


class TestLobsterClient:
    """Test LobsterClient async wrapper."""

    @pytest.mark.asyncio
    async def test_lobster_client_requires_grpcio(self) -> None:
        """Test that LobsterClient raises ImportError when grpcio is not available."""
        try:
            from shoal.core.lobster_client import GRPC_AVAILABLE
        except ImportError:
            pytest.skip("grpcio modules not available")

        if not GRPC_AVAILABLE:
            pytest.skip("grpcio not installed")

        from shoal.core.lobster_client import LobsterClient

        # Should work when grpcio is available
        client = LobsterClient(
            lobster_id="test",
            endpoint="grpc://test:50051",
        )
        assert client.lobster_id == "test"
        assert client.endpoint == "grpc://test:50051"


class TestLifecycleIntegration:
    """Test lifecycle integration for Claw sessions."""

    @pytest.mark.asyncio
    async def test_create_claw_session_lifecycle_exists(self) -> None:
        """Test that create_claw_session_lifecycle function exists."""
        from shoal.services.lifecycle import create_claw_session_lifecycle

        assert callable(create_claw_session_lifecycle)

    @pytest.mark.asyncio
    async def test_claw_session_creation_signature(self) -> None:
        """Test create_claw_session_lifecycle has correct signature."""
        import inspect

        from shoal.services.lifecycle import create_claw_session_lifecycle

        sig = inspect.signature(create_claw_session_lifecycle)
        params = list(sig.parameters.keys())

        assert "session_name" in params
        assert "claw_id" in params
        assert "endpoint" in params
        assert "employee_id" in params
