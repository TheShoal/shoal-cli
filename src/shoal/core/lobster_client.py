"""Async gRPC client wrapper for Lobster runtime communication."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger("shoal.lobster_client")

# Optional gRPC imports - guarded since grpcio is an optional dependency
if TYPE_CHECKING:
    import grpc
    from grpc.aio import Channel

    from shoal.core.proto import (
        lobster_loop_pb2,
        lobster_loop_pb2_grpc,
    )
    from shoal.models.config.lobster import LobsterConfig

# Runtime imports - these will fail gracefully if grpcio is not installed
try:
    import grpc
    from grpc.aio import insecure_channel, secure_channel

    from shoal.core.proto import lobster_loop_pb2, lobster_loop_pb2_grpc

    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False
    logger.debug("grpcio not installed - Lobster client disabled")


class LobsterClient:
    """Async gRPC client for communicating with Lobster runtimes.

    This client provides a high-level async interface to the Lobster gRPC services,
    handling connection management, retries, and error translation.

    All gRPC imports are optional - the client gracefully degrades when grpcio
    is not installed.

    Attributes:
        lobster_id: The Lobster identifier this client communicates with.
        endpoint: The gRPC endpoint URL for the Lobster.
        employee_id: The employee ID for audit/auth purposes.
        config: Optional configuration for timeouts and retries.
    """

    def __init__(
        self,
        lobster_id: str,
        endpoint: str,
        employee_id: str = "",
        config: LobsterConfig | None = None,
    ) -> None:
        """Initialize a Lobster client.

        Args:
            lobster_id: The Lobster identifier.
            endpoint: gRPC endpoint URL (e.g., "grpc://host:port").
            employee_id: Employee ID for audit trail.
            config: Optional configuration for timeouts and retries.

        Raises:
            ImportError: If grpcio is not installed and client is instantiated.
        """
        if not GRPC_AVAILABLE:
            raise ImportError(
                "grpcio is required for Lobster client. Install with: uv add grpcio grpcio-tools"
            )

        self.lobster_id = lobster_id
        self.endpoint = endpoint
        self.employee_id = employee_id
        self.config = config

        self._channel: Channel | None = None
        self._stub: lobster_loop_pb2_grpc.LobsterLoopStub | None = None
        self._lock = asyncio.Lock()

    async def _ensure_channel(self) -> None:
        """Ensure gRPC channel is open."""
        if self._channel is not None:
            return

        async with self._lock:
            if self._channel is not None:
                return

            # Determine if we need secure or insecure channel
            if self.endpoint.startswith("grpcs://"):
                self._channel = secure_channel(
                    self.endpoint[8:],
                    credentials=grpc.ssl_channel_credentials(),
                )
            else:
                # Strip grpc:// prefix if present
                target = self.endpoint[7:] if self.endpoint.startswith("grpc://") else self.endpoint
                self._channel = insecure_channel(target)

            self._stub = lobster_loop_pb2_grpc.LobsterLoopStub(self._channel)  # type: ignore[no-untyped-call]

    async def close(self) -> None:
        """Close the gRPC channel."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None

    async def __aenter__(self) -> LobsterClient:
        """Async context manager entry."""
        await self._ensure_channel()
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Async context manager exit."""
        await self.close()

    async def status(self) -> dict[str, Any]:
        """Get Lobster status.

        Returns:
            Dictionary with Lobster state and resource usage.

        Raises:
            RuntimeError: If gRPC call fails.
        """
        await self._ensure_channel()
        assert self._stub is not None

        try:
            request = lobster_loop_pb2.StatusRequest(claw_id=self.lobster_id)  # type: ignore[attr-defined]
            response = await self._stub.Status(request)

            return {
                "claw_id": response.claw_id,
                "state": response.state,
                "runtime_class": response.runtime_class,
                "started_at": response.started_at,
                "last_activity_at": response.last_activity_at,
                "usage": {
                    "cpu_usage_millicores": response.usage.cpu_usage_millicores,
                    "memory_usage_bytes": response.usage.memory_usage_bytes,
                    "ephemeral_storage_bytes": response.usage.ephemeral_storage_bytes,
                }
                if response.usage
                else {},
            }
        except grpc.aio.AioRpcError as exc:
            logger.error("Lobster %s status RPC failed: %s", self.lobster_id, exc)
            raise RuntimeError(f"Lobster status failed: {exc.details()}") from exc

    async def health(self) -> dict[str, Any]:
        """Get Lobster health status.

        Returns:
            Dictionary with health status and any issues.

        Raises:
            RuntimeError: If gRPC call fails.
        """
        await self._ensure_channel()
        assert self._stub is not None

        try:
            request = lobster_loop_pb2.HealthRequest(claw_id=self.lobster_id)  # type: ignore[attr-defined]
            response = await self._stub.Health(request)

            return {
                "healthy": response.healthy,
                "status": response.status,
                "issues": list(response.issues),
                "state": response.state,
            }
        except grpc.aio.AioRpcError as exc:
            logger.error("Lobster %s health RPC failed: %s", self.lobster_id, exc)
            raise RuntimeError(f"Lobster health failed: {exc.details()}") from exc

    async def execute(
        self,
        payload: bytes,
        event_id: str,
        metadata: dict[str, str] | None = None,
    ) -> tuple[bool, str, bytes]:
        """Execute a turn on the Lobster.

        Args:
            payload: The work payload to execute.
            event_id: Idempotency key for the turn.
            metadata: Optional additional context.

        Returns:
            Tuple of (success, message, result_bytes).

        Raises:
            RuntimeError: If gRPC call fails.
        """
        await self._ensure_channel()
        assert self._stub is not None

        try:
            request = lobster_loop_pb2.TurnRequest(  # type: ignore[attr-defined]
                claw_id=self.lobster_id,
                employee_id=self.employee_id,
                payload=payload,
                event_id=event_id,
                metadata=metadata or {},
            )

            # Stream response - collect typing events and final response
            success = False
            message = ""
            result = b""

            async for item in self._stub.Turn(request):
                if item.HasField("typing"):
                    # Typing indicator - just log it
                    logger.debug("Lobster %s sending typing indicator", self.lobster_id)
                elif item.HasField("response"):
                    success = item.response.success
                    message = item.response.message
                    result = item.response.result

            return success, message, result
        except grpc.aio.AioRpcError as exc:
            logger.error("Lobster %s turn RPC failed: %s", self.lobster_id, exc)
            raise RuntimeError(f"Lobster turn failed: {exc.details()}") from exc

    async def subscribe(
        self,
        event_types: list[str] | None = None,
    ) -> Any:
        """Subscribe to Lobster events.

        Args:
            event_types: Optional list of event types to filter.

        Yields:
            Event dictionaries as they arrive.

        Raises:
            RuntimeError: If gRPC call fails.
        """
        await self._ensure_channel()
        assert self._stub is not None

        try:
            request = lobster_loop_pb2.SubscribeRequest(  # type: ignore[attr-defined]
                claw_id=self.lobster_id,
                event_types=event_types or [],
            )

            # This is a streaming RPC - caller should iterate
            async for event in self._stub.Subscribe(request):
                yield {
                    "event_id": event.event_id,
                    "claw_id": event.claw_id,
                    "type": event.type,
                    "state": event.state,
                    "timestamp": event.timestamp,
                }
        except grpc.aio.AioRpcError as exc:
            logger.error("Lobster %s subscribe RPC failed: %s", self.lobster_id, exc)
            raise RuntimeError(f"Lobster subscribe failed: {exc.details()}") from exc

    async def inter_claw(
        self,
        target_lobster_id: str,
        action: str,
        payload: bytes,
        event_id: str,
        metadata: dict[str, str] | None = None,
    ) -> tuple[bool, str, bytes]:
        """Send an InterClaw request to another Lobster.

        Args:
            target_lobster_id: The target Lobster identifier.
            action: What action to request.
            payload: The request payload.
            event_id: Idempotency key for the request.
            metadata: Optional additional context.

        Returns:
            Tuple of (success, message, result_bytes).

        Raises:
            RuntimeError: If gRPC call fails.
        """
        await self._ensure_channel()
        assert self._stub is not None

        try:
            request = lobster_loop_pb2.InterClawRequest(  # type: ignore[attr-defined]
                source_claw_id=self.lobster_id,
                target_claw_id=target_lobster_id,
                action=action,
                payload=payload,
                event_id=event_id,
                metadata=metadata or {},
            )

            response = await self._stub.InterClaw(request)
            return response.success, response.message, response.result
        except grpc.aio.AioRpcError as exc:
            logger.error("InterClaw RPC failed: %s", exc)
            raise RuntimeError(f"InterClaw failed: {exc.details()}") from exc
