"""Runtime-provider registry and helpers for session backends."""

from __future__ import annotations

from typing import Protocol

from shoal.models.config import ToolConfig
from shoal.models.state import RuntimeKind, RuntimeState, SessionState
from shoal.services.runtime_models import RuntimeObservation


class RuntimeProvider(Protocol):
    """Provider contract for runtime-specific session operations."""

    kind: RuntimeKind

    def payload(self, runtime: RuntimeState) -> dict[str, object]: ...

    def summary(self, runtime: RuntimeState) -> dict[str, str]: ...

    def exists(self, session: SessionState) -> bool: ...

    async def async_exists(self, session: SessionState) -> bool: ...

    def attach(self, session: SessionState) -> None: ...

    def capture_output(
        self, session: SessionState, *, lines: int, include_ansi: bool = False
    ) -> str: ...

    async def async_capture_output(
        self, session: SessionState, *, lines: int, include_ansi: bool = False
    ) -> str: ...

    async def async_send_input(
        self,
        session: SessionState,
        text: str,
        *,
        enter: bool = True,
        delay: float = 0.0,
    ) -> None: ...

    async def async_wait_for_ready(
        self, session: SessionState, tool_config: ToolConfig, *, ready_timeout: float
    ) -> None: ...

    async def async_rename(self, session: SessionState, new_name: str) -> RuntimeState: ...

    async def async_kill(self, session: SessionState) -> bool: ...

    async def async_observe(
        self, session: SessionState, tool_config: ToolConfig, *, lines: int
    ) -> RuntimeObservation: ...


def _providers() -> dict[RuntimeKind, RuntimeProvider]:
    from shoal.services.runtime_providers.tmux import TmuxRuntimeProvider

    return {RuntimeKind.tmux: TmuxRuntimeProvider()}


def provider_for_runtime(runtime: RuntimeState) -> RuntimeProvider:
    return _providers()[runtime.kind]


def provider_for_session(session: SessionState) -> RuntimeProvider:
    return provider_for_runtime(session.runtime)


def runtime_payload(runtime: RuntimeState) -> dict[str, object]:
    return provider_for_runtime(runtime).payload(runtime)


def runtime_summary(runtime: RuntimeState) -> dict[str, str]:
    return provider_for_runtime(runtime).summary(runtime)
