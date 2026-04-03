"""Lobster runtime provider - gRPC-based remote agent runtime."""

from __future__ import annotations

import asyncio
import importlib
import logging
from typing import TYPE_CHECKING, Any, cast

from shoal.models.config import ToolConfig
from shoal.models.state import LobsterRuntimeState, RuntimeKind, RuntimeState, SessionState
from shoal.services.runtime_models import RuntimeObservation

if TYPE_CHECKING:
    from shoal.core.lobster_client import LobsterClient

RuntimeLobsterClient: type[LobsterClient] | None

logger = logging.getLogger("shoal.lobster_provider")

# Optional gRPC imports - guarded since grpcio is an optional dependency
try:
    from shoal.core.lobster_client import LobsterClient as RuntimeLobsterClient
except ImportError:
    RuntimeLobsterClient = None
    grpc_available = False
    logger.debug("grpcio not installed - Lobster provider disabled")
else:
    grpc_available = True


class LobsterRuntimeProvider:
    """Runtime provider for Lobster gRPC-based remote agents.

    This provider implements the RuntimeProvider protocol for Lobster runtimes,
    which are remote gRPC-based agents managed by the Lobster Party system.

    Unlike tmux sessions (local process-based), Lobsters are remote services
    accessed via gRPC. Many operations that make sense for local processes
    (attach, capture_output, send_input) are not applicable or require
    different semantics for remote agents.

    All gRPC imports are optional - the provider gracefully degrades when
    grpcio is not installed.
    """

    kind: RuntimeKind = RuntimeKind.lobster

    def _get_client(self, session: SessionState) -> LobsterClient:
        """Get a Lobster client for the session.

        Args:
            session: The session state.

        Returns:
            A LobsterClient instance for communicating with the Lobster.

        Raises:
            RuntimeError: If grpcio is not installed.
            ValueError: If session runtime is not LobsterRuntimeState.
        """
        if not grpc_available or RuntimeLobsterClient is None:
            raise RuntimeError(
                "grpcio is required for Lobster provider. "
                "Install with: pip install grpcio grpcio-tools"
            )

        if not isinstance(session.runtime, LobsterRuntimeState):
            raise ValueError(f"Expected LobsterRuntimeState, got {type(session.runtime)}")

        return RuntimeLobsterClient(
            lobster_id=session.runtime.lobster_id,
            endpoint=session.runtime.endpoint,
            employee_id=session.runtime.employee_id,
        )

    def _ensure_a2a_bridge(self) -> None:
        """Load the A2A bridge so LobsterClient gets patched helper methods."""
        _ = importlib.import_module("shoal.integrations.lobster.a2a_bridge")

    @staticmethod
    def _render_task_line(task: dict[str, object]) -> str:
        """Render one task row for dashboard- and CLI-friendly output."""
        task_id = str(task.get("id", "")) or "-"
        state = str(task.get("state", "")) or "-"
        context_id = str(task.get("context_id", ""))
        status_message = str(task.get("status_message", ""))
        parts = [task_id, state]
        if context_id:
            parts.append(f"context={context_id}")
        if status_message:
            parts.append(status_message)
        return " | ".join(parts)

    def _render_output_text(
        self,
        session: SessionState,
        *,
        health: dict[str, object] | None,
        tasks: list[dict[str, object]],
    ) -> str:
        """Build a plain-text status summary for Lobster sessions."""
        assert isinstance(session.runtime, LobsterRuntimeState)
        lines = [f"Lobster: {session.runtime.lobster_id}"]
        if session.runtime.endpoint:
            lines.append(f"Endpoint: {session.runtime.endpoint}")

        if health is not None:
            health_parts = ["healthy" if bool(health.get("healthy", False)) else "unhealthy"]
            status = str(health.get("status", "")).strip()
            state = str(health.get("state", "")).strip()
            if status:
                health_parts.append(status)
            if state:
                health_parts.append(f"state={state}")
            lines.append(f"Health: {' | '.join(health_parts)}")

            raw_issues = health.get("issues")
            issues: list[str] = []
            if isinstance(raw_issues, list):
                issues = [str(issue).strip() for issue in raw_issues if str(issue).strip()]
            if issues:
                lines.append(f"Issues: {', '.join(issues)}")

        if tasks:
            lines.append("Tasks:")
            lines.extend(f"- {self._render_task_line(task)}" for task in tasks)
        else:
            lines.append("Tasks: none")

        return "\n".join(lines)

    def payload(self, runtime: RuntimeState) -> dict[str, object]:
        """Get runtime payload for serialization.

        Args:
            runtime: The runtime state to serialize.

        Returns:
            Dictionary representation of the runtime state.
        """
        if not isinstance(runtime, LobsterRuntimeState):
            raise ValueError(f"Expected LobsterRuntimeState, got {type(runtime)}")

        return runtime.model_dump(mode="json")

    def summary(self, runtime: RuntimeState) -> dict[str, str]:
        """Get runtime summary for display.

        Args:
            runtime: The runtime state.

        Returns:
            Dictionary with key runtime information.
        """
        if not isinstance(runtime, LobsterRuntimeState):
            raise ValueError(f"Expected LobsterRuntimeState, got {type(runtime)}")

        return {
            "lobster_id": runtime.lobster_id,
            "endpoint": runtime.endpoint or "",
            "employee_id": runtime.employee_id or "",
        }

    def exists(self, session: SessionState) -> bool:
        """Check if Lobster exists (synchronous).

        For Lobster runtimes, this checks if the Lobster is registered and reachable.

        Args:
            session: The session to check.

        Returns:
            True if the Lobster exists and is reachable.

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
                logger.debug("Lobster %s does not exist: %s", session.id, exc)
                return False

    async def async_exists(self, session: SessionState) -> bool:
        """Check if Lobster exists (async).

        For Lobster runtimes, this performs a health check to verify
        the Lobster is registered and reachable.

        Args:
            session: The session to check.

        Returns:
            True if the Lobster exists and is healthy.
        """
        try:
            async with self._get_client(session) as client:
                health = await client.health()
                return bool(health.get("healthy", False))
        except Exception as exc:
            logger.debug("Lobster %s health check failed: %s", session.id, exc)
            return False

    def attach(self, session: SessionState) -> None:
        """Attach to a Lobster session.

        Note:
            Lobster runtimes are remote gRPC services - direct attachment
            is not supported. This is a no-op for Lobster sessions.

        Args:
            session: The session to attach to.
        """
        logger.warning("attach() is not supported for Lobster runtimes")

    def capture_output(
        self,
        session: SessionState,
        *,
        lines: int,
        include_ansi: bool = False,
    ) -> str:
        """Capture synthesized status output from a Lobster session."""
        _ = include_ansi
        try:
            _ = asyncio.get_running_loop()
            logger.warning("capture_output() called in async context - use async_capture_output()")
            return ""
        except RuntimeError:
            try:
                return asyncio.run(self.async_capture_output(session, lines=lines))
            except Exception as exc:
                logger.debug("Lobster %s capture failed: %s", session.id, exc)
                return ""

    async def async_capture_output(
        self,
        session: SessionState,
        *,
        lines: int,
        include_ansi: bool = False,
    ) -> str:
        """Capture synthesized status output from a Lobster session (async)."""
        _ = include_ansi
        health: dict[str, object] | None = None
        tasks: list[dict[str, object]] = []

        try:
            self._ensure_a2a_bridge()
            client = self._get_client(session)
        except Exception as exc:
            logger.debug("Lobster %s capture setup failed: %s", session.id, exc)
            return ""

        async with client:
            try:
                health = await client.health()
            except Exception as exc:
                logger.debug("Lobster %s health lookup failed during capture: %s", session.id, exc)

            try:
                list_tasks = cast(Any, client).list_tasks
                tasks = cast(
                    list[dict[str, object]],
                    await list_tasks(page_size=max(1, min(lines, 50))),
                )
            except Exception as exc:
                logger.debug("Lobster %s task lookup failed during capture: %s", session.id, exc)

        if health is None and not tasks:
            return ""

        rendered = self._render_output_text(session, health=health, tasks=tasks)
        rendered_lines = rendered.splitlines()
        if lines > 0 and len(rendered_lines) > lines:
            return "\n".join(rendered_lines[-lines:])
        return rendered

    async def async_send_input(
        self,
        session: SessionState,
        text: str,
        *,
        enter: bool = True,
        delay: float = 0.0,
    ) -> None:
        """Send a text message to a Lobster session via the A2A bridge."""
        del enter, delay
        if not text.strip():
            logger.debug("Ignoring empty Lobster input for %s", session.id)
            return

        self._ensure_a2a_bridge()
        async with self._get_client(session) as client:
            result = cast(
                dict[str, object],
                await cast(Any, client).send_message(message=text),
            )

        logger.info(
            "Lobster %s accepted input (task_id=%s, state=%s)",
            session.id,
            result.get("task_id", ""),
            result.get("state", ""),
        )

    async def async_wait_for_ready(
        self,
        session: SessionState,
        tool_config: ToolConfig,
        *,
        ready_timeout: float,
    ) -> None:
        """Wait for Lobster to be ready.

        For Lobster runtimes, this polls the health endpoint until the Lobster
        reports healthy or the timeout expires.

        Args:
            session: The session to wait for.
            tool_config: Tool configuration (ignored for Lobster).
            ready_timeout: Maximum time to wait in seconds.

        Raises:
            TimeoutError: If the Lobster does not become ready within the timeout.
        """
        import asyncio

        start = asyncio.get_event_loop().time()
        while True:
            try:
                async with self._get_client(session) as client:
                    health = await client.health()
                    if health.get("healthy", False):
                        logger.info("Lobster %s is ready", session.id)
                        return
            except Exception as exc:
                logger.debug("Lobster %s health check pending: %s", session.id, exc)

            elapsed = asyncio.get_event_loop().time() - start
            if elapsed >= ready_timeout:
                raise TimeoutError(
                    f"Lobster {session.id} did not become ready within {ready_timeout}s"
                )

            await asyncio.sleep(0.5)

    async def async_rename(
        self,
        session: SessionState,
        new_name: str,
    ) -> LobsterRuntimeState:
        """Rename a Lobster session.

        Note:
            Lobster runtimes have fixed identifiers (lobster_id) that cannot be
            renamed. This returns the existing runtime state unchanged.

        Args:
            session: The session to rename.
            new_name: The new name (ignored for Lobster runtimes).

        Returns:
            The unchanged runtime state.
        """
        logger.warning("async_rename() is not supported for Lobster runtimes")
        assert isinstance(session.runtime, LobsterRuntimeState)
        return session.runtime

    async def async_kill(self, session: SessionState) -> bool:
        """Kill a Lobster session.

        Note:
            Lobster lifecycle is managed by the Lobster Party Clawplexer,
            not by individual clients. This is a no-op.

        Args:
            session: The session to kill.

        Returns:
            False (operation not supported).
        """
        logger.warning("async_kill() is not supported for Lobster runtimes")
        return False

    async def async_observe(
        self,
        session: SessionState,
        tool_config: ToolConfig,
        *,
        lines: int,
    ) -> RuntimeObservation:
        """Observe a Lobster session.

        For Lobster runtimes, this checks health and returns runtime state.

        Args:
            session: The session to observe.
            tool_config: Tool configuration (ignored for Lobster).
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
            logger.debug("Lobster %s observe failed: %s", session.id, exc)
            return RuntimeObservation(
                alive=False,
                runtime=session.runtime,
            )
