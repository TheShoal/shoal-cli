"""Async gRPC client for Lobster Party Claw runtimes.

This module wraps the generated protobuf stubs to provide a clean Python API.
All imports from the generated module are guarded behind try/except since grpcio
is an optional dependency.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClawStatusResult:
    """Result from a Claw status RPC."""

    state: str
    employee_id: str = ""
    event_id: str = ""


@dataclass
class ClawHealthResult:
    """Result from a Claw health check RPC."""

    healthy: bool
    version: str = ""


class ClawClient:
    """Async gRPC client for interacting with Lobster Party Claws.

    All methods are async and use grpc.aio for non-blocking I/O.
    The client must be closed when done via the close() method.

    Attributes:
        grpc_addr: The gRPC address to connect to.
        jwt_secret: Secret for minting JWTs for authentication.
        tls: Whether to use TLS for the connection.
    """

    def __init__(
        self,
        addr: str = "localhost:50051",
        jwt_secret: str = "",
        tls: bool = False,
    ) -> None:
        """Initialize the Claw client.

        Args:
            addr: gRPC address (e.g., "localhost:50051").
            jwt_secret: Secret for minting JWTs. Empty string for no auth.
            tls: Whether to use TLS. Defaults to False.
        """
        self.grpc_addr: str = addr
        self.jwt_secret: str = jwt_secret
        self.tls: bool = tls
        self._channel: object | None = None
        self._stub: object | None = None

    async def turn(
        self,
        claw_id: str,
        employee_id: str,
        payload: str,
        event_id: str | None = None,
    ) -> str:
        """Send a turn to the Claw and get the response.

        Args:
            claw_id: The Claw identifier.
            employee_id: Employee/user identifier for the turn.
            payload: The message/prompt to send.
            event_id: Optional event ID for tracking.

        Returns:
            The Claw's response text.

        Raises:
            RuntimeError: If grpcio is not installed.
        """
        try:
            import grpc.aio

            from shoal.core.proto import (
                a2a_claw_pb2,
                a2a_claw_pb2_grpc,
            )
        except ImportError as e:
            raise RuntimeError("grpcio not installed. Install with: pip install shoal[claw]") from e

        if self._channel is None:
            self._channel = grpc.aio.insecure_channel(self.grpc_addr)
            self._stub = a2a_claw_pb2_grpc.ClawStub(self._channel)

        request = a2a_claw_pb2.TurnRequest(
            claw_id=claw_id,
            employee_id=employee_id,
            payload=payload,
            event_id=event_id or "",
        )

        response = await self._stub.Turn(request)
        return response.response

    async def status(self, claw_id: str) -> ClawStatusResult:
        """Get the current status of a Claw.

        Args:
            claw_id: The Claw identifier.

        Returns:
            ClawStatusResult with state and metadata.

        Raises:
            RuntimeError: If grpcio is not installed.
        """
        try:
            import grpc.aio

            from shoal.core.proto import (
                a2a_claw_pb2,
                a2a_claw_pb2_grpc,
            )
        except ImportError as e:
            raise RuntimeError("grpcio not installed. Install with: pip install shoal[claw]") from e

        if self._channel is None:
            self._channel = grpc.aio.insecure_channel(self.grpc_addr)
            self._stub = a2a_claw_pb2_grpc.ClawStub(self._channel)

        request = a2a_claw_pb2.StatusRequest(claw_id=claw_id)
        response = await self._stub.Status(request)

        return ClawStatusResult(
            state=response.state,
            employee_id=response.employee_id,
            event_id=response.event_id,
        )

    async def health(self, claw_id: str) -> ClawHealthResult:
        """Check the health of a Claw.

        Args:
            claw_id: The Claw identifier.

        Returns:
            ClawHealthResult with healthy flag and version.

        Raises:
            RuntimeError: If grpcio is not installed.
        """
        try:
            import grpc.aio

            from shoal.core.proto import (
                a2a_core_pb2,
                a2a_core_pb2_grpc,
            )
        except ImportError as e:
            raise RuntimeError("grpcio not installed. Install with: pip install shoal[claw]") from e

        if self._channel is None:
            self._channel = grpc.aio.insecure_channel(self.grpc_addr)
            self._stub = a2a_core_pb2_grpc.HealthStub(self._channel)

        request = a2a_core_pb2.HealthCheckRequest(service=claw_id)
        response = await self._stub.Check(request)

        return ClawHealthResult(
            healthy=response.status == a2a_core_pb2.HealthCheckResponse.SERVING,
            version=getattr(response, "version", ""),
        )

    async def close(self) -> None:
        """Close the gRPC channel.

        Should be called when the client is no longer needed.
        """
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._stub = None
