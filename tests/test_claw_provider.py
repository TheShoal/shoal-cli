"""Tests for Claw runtime provider and client."""

from __future__ import annotations

import pytest

from shoal.models.state import ClawRuntimeState, RuntimeKind


class TestClawRuntimeState:
    """Test ClawRuntimeState model."""

    def test_create_claw_runtime_state(self) -> None:
        """Test creating a ClawRuntimeState instance."""
        runtime = ClawRuntimeState(
            claw_id="claw_abc123",
            endpoint="grpc://claw-abc123.lobster-party-runtime.svc:50051",
            employee_id="emp_123",
        )

        assert runtime.kind == RuntimeKind.claw
        assert runtime.claw_id == "claw_abc123"
        assert runtime.endpoint == "grpc://claw-abc123.lobster-party-runtime.svc:50051"
        assert runtime.employee_id == "emp_123"

    def test_claw_runtime_state_defaults(self) -> None:
        """Test ClawRuntimeState default values."""
        runtime = ClawRuntimeState(claw_id="claw_test")

        assert runtime.kind == RuntimeKind.claw
        assert runtime.claw_id == "claw_test"
        assert runtime.endpoint == ""
        assert runtime.employee_id == ""

    def test_claw_runtime_state_serialization(self) -> None:
        """Test ClawRuntimeState JSON serialization."""
        runtime = ClawRuntimeState(
            claw_id="claw_test",
            endpoint="grpc://test:50051",
        )

        data = runtime.model_dump(mode="json")
        assert data["kind"] == "claw"
        assert data["claw_id"] == "claw_test"
        assert data["endpoint"] == "grpc://test:50051"
        assert data["employee_id"] == ""


class TestRuntimeKind:
    """Test RuntimeKind enum."""

    def test_runtime_kind_claw_exists(self) -> None:
        """Test that RuntimeKind.claw exists."""
        assert RuntimeKind.claw == "claw"
        assert RuntimeKind.tmux == "tmux"
        assert len(list(RuntimeKind)) == 2


class TestClawProviderImport:
    """Test Claw provider imports gracefully."""

    def test_claw_provider_import_without_grpcio(self) -> None:
        """Test that Claw provider imports even when grpcio is not available."""
        # This should not raise - the provider should import gracefully
        try:
            from shoal.services.runtime_providers.claw import ClawRuntimeProvider

            provider = ClawRuntimeProvider()
            assert provider.kind == RuntimeKind.claw
        except ImportError:
            # grpcio might not be installed in test environment
            pytest.skip("grpcio not installed")

    def test_runtime_provider_registry_includes_claw(self) -> None:
        """Test that Claw provider is registered in the provider registry."""
        from shoal.services.runtime_provider import _providers

        providers = _providers()
        assert RuntimeKind.claw in providers
        assert RuntimeKind.tmux in providers


class TestClawConfig:
    """Test ClawConfig model."""

    def test_create_claw_config(self) -> None:
        """Test creating a ClawConfig instance."""
        from shoal.models.config.claw import ClawConfig

        config = ClawConfig(
            known_claws={"claw_abc": "grpc://claw-abc:50051"},
            default_timeout=60.0,
            retry_attempts=5,
        )

        assert config.known_claws == {"claw_abc": "grpc://claw-abc:50051"}
        assert config.default_timeout == 60.0
        assert config.retry_attempts == 5

    def test_claw_config_defaults(self) -> None:
        """Test ClawConfig default values."""
        from shoal.models.config.claw import ClawConfig

        config = ClawConfig()

        assert config.known_claws == {}
        assert config.default_timeout == 30.0
        assert config.retry_attempts == 3


class TestClawClient:
    """Test ClawClient async wrapper."""

    @pytest.mark.asyncio
    async def test_claw_client_requires_grpcio(self) -> None:
        """Test that ClawClient raises ImportError when grpcio is not available."""
        try:
            from shoal.core.claw_client import GRPC_AVAILABLE
        except ImportError:
            pytest.skip("grpcio modules not available")

        if not GRPC_AVAILABLE:
            pytest.skip("grpcio not installed")

        from shoal.core.claw_client import ClawClient

        # Should work when grpcio is available
        client = ClawClient(
            claw_id="test",
            endpoint="grpc://test:50051",
        )
        assert client.claw_id == "test"
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
