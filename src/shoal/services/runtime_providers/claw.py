"""Claw runtime provider - gRPC-based remote agent runtime."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from shoal.models.config import ToolConfig
from shoal.models.state import ClawRuntimeState, RuntimeKind, RuntimeState, SessionState
from shoal.services.runtime_models import RuntimeObservation

if TYPE_CHECKING:
    from shoal.core.claw_client import ClawClient

logger = logging.getLogger("shoal.claw_provider")

# Optional gRPC imports - guarded since grpcio is an optional dependency
try:
    from shoal.core.claw_client import ClawClient

    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False
    logger.debug("grpcio not installed - Claw provider disabled")


class ClawRuntimeProvider:
    """Runtime provider for Claw gRPC-based remote agents.

    This provider implements the RuntimeProvider protocol for Claw runtimes,
    which are remote gRPC-based agents managed by the Lobster Party system.

    Unlike tmux sessions (local process-based), Claws are remote services
    accessed via gRPC. Many operations that make sense for local processes
    (attach, capture_output, send_input) are not applicable or require
    different semantics for remote agents.

    All gRPC imports are optional - the provider gracefully degrades when
    grpcio is not installed.
    """

    kind: RuntimeKind = RuntimeKind.claw

    def _get_client(self, session: SessionState) -> ClawClient:
        """Get a Claw client for the session.

        Args:
            session: The session state.

        Returns:
            A ClawClient instance for communicating with the Claw.

        Raises:
            RuntimeError: If grpcio is not installed.
            ValueError: If session runtime is not ClawRuntimeState.
        """
        if not GRPC_AVAILABLE:
            raise RuntimeError(
                "grpcio is required for Claw provider. "
                "Install with: pip install grpcio grpcio-tools"
            )

        if not isinstance(session.runtime, ClawRuntimeState):
            raise ValueError(f"Expected ClawRuntimeState, got {type(session.runtime)}")

        return ClawClient(
            claw_id=session.runtime.claw_id,
            endpoint=session.runtime.endpoint,
            employee_id=session.runtime.employee_id,
        )

    def payload(self, runtime: RuntimeState) -> dict[str, object]:
        """Get runtime payload for serialization.

        Args:
            runtime: The runtime state to serialize.

        Returns:
            Dictionary representation of the runtime state.
        """
        if not isinstance(runtime, ClawRuntimeState):
            raise ValueError(f"Expected ClawRuntimeState, got {type(runtime)}")

        return runtime.model_dump(mode="json")

    def summary(self, runtime: RuntimeState) -> dict[str, str]:
        """Get runtime summary for display.

        Args:
            runtime: The runtime state.

        Returns:
            Dictionary with key runtime information.
        """
        if not isinstance(runtime, ClawRuntimeState):
            raise ValueError(f"Expected ClawRuntimeState, got {type(runtime)}")

        return {
            "claw_id": runtime.claw_id,
            "endpoint": runtime.endpoint or "",
            "employee_id": runtime.employee_id or "",
        }

    def exists(self, session: SessionState) -> bool:
        """Check if Claw exists (synchronous).

        For Claw runtimes, this checks if the Claw is registered and reachable.

        Args:
            session: The session to check.

        Returns:
            True if the Claw exists and is reachable.

        Note:
            This is a sync wrapper - prefer async_exists for async contexts.
        """
        import asyncio

        try:
            _ = asyncio.get_running_loop()
            # We're in an async context - can't use asyncio.run
            logger.warning("exists() called in async context - use async_exists()")
            return False
        except RuntimeError:
            # No running loop - safe to use asyncio.run
            try:
                return asyncio.run(self.async_exists(session))
            except Exception as exc:
                logger.debug("Claw %s does not exist: %s", session.id, exc)
                return False

    async def async_exists(self, session: SessionState) -> bool:
        """Check if Claw exists (async).

        For Claw runtimes, this performs a health check to verify
        the Claw is registered and reachable.

        Args:
            session: The session to check.

        Returns:
            True if the Claw exists and is healthy.
        """
        try:
            async with self._get_client(session) as client:
                health = await client.health()
                return bool(health.get("healthy", False))
        except Exception as exc:
            logger.debug("Claw %s health check failed: %s", session.id, exc)
            return False

    def attach(self, session: SessionState) -> None:
        """Attach to a Claw session.

        Note:
            Claw runtimes are remote gRPC services - direct attachment
            is not supported. This is a no-op for Claw sessions.

        Args:
            session: The session to attach to.
        """
        logger.warning("attach() is not supported for Claw runtimes")

    def capture_output(
        self,
        session: SessionState,
        *,
        lines: int,
        include_ansi: bool = False,
    ) -> str:
        """Capture output from a Claw session.

        Note:
            Claw runtimes are remote agents - they don't expose raw terminal
            output like tmux sessions. This returns an empty string.

        Args:
            session: The session to capture from.
            lines: Number of lines to capture.
            include_ansi: Whether to include ANSI escape codes.

        Returns:
            Empty string (not applicable for Claw runtimes).
        """
        logger.warning("capture_output() is not supported for Claw runtimes")
        return ""

    async def async_capture_output(
        self,
        session: SessionState,
        *,
        lines: int,
        include_ansi: bool = False,
    ) -> str:
        """Capture output from a Claw session (async).

        Note:
            Claw runtimes are remote agents - they don't expose raw terminal
            output like tmux sessions. This returns an empty string.

        Args:
            session: The session to capture from.
            lines: Number of lines to capture.
            include_ansi: Whether to include ANSI escape codes.

        Returns:
            Empty string (not applicable for Claw runtimes).
        """
        logger.warning("async_capture_output() is not supported for Claw runtimes")
        return ""

    async def async_send_input(
        self,
        session: SessionState,
        text: str,
        *,
        enter: bool = True,
        delay: float = 0.0,
    ) -> None:
        """Send input to a Claw session.

        Note:
            Claw runtimes are remote agents that receive structured work
            payloads via gRPC, not raw terminal input. This is a no-op.

        Args:
            session: The session to send input to.
            text: The text to send.
            enter: Whether to send an enter key (ignored).
            delay: Delay before sending (ignored).
        """
        logger.warning("async_send_input() is not supported for Claw runtimes")

    async def async_wait_for_ready(
        self,
        session: SessionState,
        tool_config: ToolConfig,
        *,
        ready_timeout: float,
    ) -> None:
        """Wait for Claw to be ready.

        For Claw runtimes, this polls the health endpoint until the Claw
        reports healthy or the timeout expires.

        Args:
            session: The session to wait for.
            tool_config: Tool configuration (ignored for Claw).
            ready_timeout: Maximum time to wait in seconds.

        Raises:
            TimeoutError: If the Claw does not become ready within the timeout.
        """
        import asyncio

        start = asyncio.get_event_loop().time()
        while True:
            try:
                async with self._get_client(session) as client:
                    health = await client.health()
                    if health.get("healthy", False):
                        logger.info("Claw %s is ready", session.id)
                        return
            except Exception as exc:
                logger.debug("Claw %s health check pending: %s", session.id, exc)

            elapsed = asyncio.get_event_loop().time() - start
            if elapsed >= ready_timeout:
                raise TimeoutError(
                    f"Claw {session.id} did not become ready within {ready_timeout}s"
                )

            await asyncio.sleep(0.5)

    async def async_rename(
        self,
        session: SessionState,
        new_name: str,
    ) -> ClawRuntimeState:
        """Rename a Claw session.

        Note:
            Claw runtimes have fixed identifiers (claw_id) that cannot be
            renamed. This returns the existing runtime state unchanged.

        Args:
            session: The session to rename.
            new_name: The new name (ignored for Claw runtimes).

        Returns:
            The unchanged runtime state.
        """
        logger.warning("async_rename() is not supported for Claw runtimes")
        assert isinstance(session.runtime, ClawRuntimeState)
        return session.runtime

    async def async_kill(self, session: SessionState) -> bool:
        """Kill a Claw session.

        Note:
            Claw lifecycle is managed by the Lobster Party Clawplexer,
            not by individual clients. This is a no-op.

        Args:
            session: The session to kill.

        Returns:
            False (operation not supported).
        """
        logger.warning("async_kill() is not supported for Claw runtimes")
        return False

    async def async_observe(
        self,
        session: SessionState,
        tool_config: ToolConfig,
        *,
        lines: int,
    ) -> RuntimeObservation:
        """Observe a Claw session.

        For Claw runtimes, this checks health and returns runtime state.

        Args:
            session: The session to observe.
            tool_config: Tool configuration (ignored for Claw).
            lines: Number of output lines to capture (ignored).

        Returns:
            RuntimeObservation with health status and runtime state.
        """
        try:
            async with self._get_client(session) as client:
                health = await client.health()
                alive = bool(health.get("healthy", False))

                return RuntimeObservation(
                    alive=alive,
                    runtime=session.runtime,
                )
        except Exception as exc:
            logger.debug("Claw %s observe failed: %s", session.id, exc)
            return RuntimeObservation(
                alive=False,
                runtime=session.runtime,
            )
