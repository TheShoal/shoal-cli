"""A2A gRPC bridge — translates proto messages to/from Pydantic and patches LobsterClient.

All gRPC-touching code is guarded behind ``try/except ImportError`` so this module
is safely importable when grpcio is not installed.
"""

from __future__ import annotations

from typing import Any

from shoal.models.config.agent_card import (
    AgentCapabilities,
    AgentCard,
    AgentProvider,
    AgentSkill,
)

# ---------------------------------------------------------------------------
# Optional gRPC imports
# ---------------------------------------------------------------------------

try:
    import grpc as _grpc  # noqa: I001 — load order preserved for descriptor pool

    from shoal.core.lobster_client import LobsterClient as _LobsterClient

    # Load a2a_core_pb2 first — a2a_claw_pb2 depends on a2a_core.proto
    from shoal.core.proto import (
        a2a_core_pb2 as _a2a_core_pb2,
    )
    from shoal.core.proto import (
        a2a_claw_pb2_grpc as _a2a_claw_grpc,
    )

    GRPC_AVAILABLE = True
except (ImportError, TypeError):
    GRPC_AVAILABLE = False
    _LobsterClient = None  # type: ignore


# ---------------------------------------------------------------------------
# Public helpers — importable regardless of grpcio
# ---------------------------------------------------------------------------


def proto_to_agent_card(
    proto_card: Any,
    *,
    lobster_id: str,
    endpoint: str,
) -> AgentCard:
    """Translate a proto AgentCard message to the Pydantic model.

    Args:
        proto_card: A ``a2a_core_pb2.AgentCard`` proto message.
        lobster_id: Fallback name when the lobster's name field is empty.
        endpoint: Fallback endpoint when the proto card's endpoint field is empty.

    Returns:
        Populated :class:`AgentCard` instance.
    """
    name = proto_card.name or lobster_id
    version = proto_card.version or "1.0.0"
    ep = proto_card.endpoint or endpoint

    provider_org = (
        proto_card.provider.organization
        if proto_card.provider.organization
        else "us-mobile-lobster-party"
    )
    provider_url = proto_card.provider.url if proto_card.provider.url else "https://usmobile.com"
    provider = AgentProvider(organization=provider_org, url=provider_url)

    capabilities = AgentCapabilities(
        streaming=proto_card.capabilities.streaming,
        push_notifications=proto_card.capabilities.push_notifications,
        state_transition_reports=proto_card.capabilities.state_transition_reports,
    )

    skills = [
        AgentSkill(
            id=s.id,
            name=s.name,
            description=s.description,
            tags=list(s.tags),
        )
        for s in proto_card.skills
    ]

    # proto map field → plain dict
    metadata: dict[str, str] = dict(proto_card.metadata)

    return AgentCard(
        name=name,
        version=version,
        provider=provider,
        capabilities=capabilities,
        skills=skills,
        endpoint=ep,
        description=proto_card.description,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# LobsterClient method implementations (defined only when GRPC_AVAILABLE)
# ---------------------------------------------------------------------------

if GRPC_AVAILABLE:

    async def _get_agent_card_impl(self: Any) -> AgentCard:
        """Fetch this Lobster's AgentCard via the A2A GetAgentCard RPC.

        Returns:
            Populated :class:`AgentCard` describing the remote Lobster.

        Raises:
            RuntimeError: If the RPC call fails.
        """
        await self._ensure_channel()
        stub = _a2a_claw_grpc.AgentLoopStub(self._channel)  # type: ignore[no-untyped-call]
        call_meta = [("x-employee-id", self.employee_id)] if self.employee_id else []
        try:
            proto_card = await stub.GetAgentCard(
                _a2a_core_pb2.GetAgentCardRequest(),  # type: ignore[attr-defined]
                metadata=call_meta,
            )
        except _grpc.aio.AioRpcError as exc:
            raise RuntimeError(f"GetAgentCard RPC failed: {exc.details()}") from exc
        return proto_to_agent_card(proto_card, lobster_id=self.lobster_id, endpoint=self.endpoint)

    async def _send_message_impl(
        self: Any,
        message: str,
        task_id: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send a message to this Lobster via the A2A SendMessage RPC.

        Args:
            message: The text content to send.
            task_id: Optional task ID for idempotency; generated if not provided.
            metadata: Optional metadata key/value pairs attached to the request.

        Returns:
            Dict with keys ``task_id``, ``response``, and ``state``.

        Raises:
            RuntimeError: If the RPC call fails.
        """
        import time
        import uuid

        effective_task_id = task_id or str(uuid.uuid4())
        now = int(time.time())

        # Merge employee_id into proto-level metadata so the Claw service sees it
        # in the request payload, and pass it as gRPC call metadata for transport-level auth.
        effective_meta: dict[str, str] = dict(metadata or {})
        if self.employee_id:
            effective_meta.setdefault("employee_id", self.employee_id)
        call_meta = [("x-employee-id", self.employee_id)] if self.employee_id else []
        msg = _a2a_core_pb2.Message(  # type: ignore[attr-defined]
            id=str(uuid.uuid4()),
            role=_a2a_core_pb2.ROLE_USER,  # type: ignore[attr-defined]
            parts=[
                _a2a_core_pb2.Part(  # type: ignore[attr-defined]
                    text=_a2a_core_pb2.TextPart(text=message)  # type: ignore[attr-defined]
                )
            ],
            timestamp=now,
        )

        req = _a2a_core_pb2.SendMessageRequest(  # type: ignore[attr-defined]
            task_id=effective_task_id,
            message=msg,
            metadata=effective_meta,
        )

        await self._ensure_channel()
        stub = _a2a_claw_grpc.AgentLoopStub(self._channel)  # type: ignore[no-untyped-call]
        try:
            response = await stub.SendMessage(req, metadata=call_meta)
        except _grpc.aio.AioRpcError as exc:
            raise RuntimeError(f"SendMessage RPC failed: {exc.details()}") from exc

        # SendMessageResponse is a oneof{task, message}
        response_text = ""
        result_task_id = effective_task_id
        state = "unknown"

        which = response.WhichOneof("response")
        if which == "task":
            task = response.task
            result_task_id = task.id or effective_task_id
            if task.HasField("status"):
                state = _a2a_core_pb2.TaskState.Name(task.status.state)  # type: ignore[attr-defined]
            response_text = task.status.message if task.HasField("status") else ""
            # If no status message, try the last message in history
            if not response_text and task.history:
                last_msg = task.history[-1]
                response_text = " ".join(
                    part.text.text for part in last_msg.parts if part.HasField("text")
                )
        elif which == "message":
            resp_msg = response.message
            result_task_id = effective_task_id
            state = "completed"
            response_text = " ".join(
                part.text.text for part in resp_msg.parts if part.HasField("text")
            )

        return {
            "task_id": result_task_id,
            "response": response_text,
            "state": state,
        }

    async def _list_tasks_impl(
        self: Any,
        context_id: str | None = None,
        status: str | None = None,
        page_size: int = 50,
    ) -> list[dict[str, Any]]:
        """List tasks on this Lobster via the A2A ListTasks RPC.

        Args:
            context_id: Optional context ID filter.
            status: Optional status string filter — one of ``working``,
                ``input-required``, ``completed``, ``canceled``, ``failed``.
            page_size: Maximum number of tasks to return (default 50).

        Returns:
            List of dicts with keys ``id``, ``state``, ``context_id``,
            ``status_message``.

        Raises:
            RuntimeError: If the RPC call fails.
        """
        _STATUS_MAP: dict[str, int] = {
            "working": _a2a_core_pb2.TASK_STATE_WORKING,  # type: ignore[attr-defined]
            "input-required": _a2a_core_pb2.TASK_STATE_INPUT_REQUIRED,  # type: ignore[attr-defined]
            "completed": _a2a_core_pb2.TASK_STATE_COMPLETED,  # type: ignore[attr-defined]
            "canceled": _a2a_core_pb2.TASK_STATE_CANCELED,  # type: ignore[attr-defined]
            "failed": _a2a_core_pb2.TASK_STATE_FAILED,  # type: ignore[attr-defined]
        }

        state_filter = _STATUS_MAP.get(status, 0) if status else 0  # 0 = UNSPECIFIED

        req = _a2a_core_pb2.ListTasksRequest(  # type: ignore[attr-defined]
            context_id=context_id or "",
            status=state_filter,
            page_size=page_size,
        )

        await self._ensure_channel()
        stub = _a2a_claw_grpc.AgentLoopStub(self._channel)  # type: ignore[no-untyped-call]
        call_meta = [("x-employee-id", self.employee_id)] if self.employee_id else []
        try:
            response = await stub.ListTasks(req, metadata=call_meta)
        except _grpc.aio.AioRpcError as exc:
            raise RuntimeError(f"ListTasks RPC failed: {exc.details()}") from exc

        tasks: list[dict[str, Any]] = []
        for task in response.tasks:
            state_name = (
                _a2a_core_pb2.TaskState.Name(task.status.state)  # type: ignore[attr-defined]
                if task.HasField("status")
                else "TASK_STATE_UNSPECIFIED"
            )
            status_message = task.status.message if task.HasField("status") else ""
            tasks.append(
                {
                    "id": task.id,
                    "state": state_name,
                    "context_id": task.context_id,
                    "status_message": status_message,
                }
            )

        return tasks

    # Patch LobsterClient with the A2A methods
    _LobsterClient.get_agent_card = _get_agent_card_impl  # type: ignore[attr-defined]
    _LobsterClient.send_message = _send_message_impl  # type: ignore[attr-defined]
    _LobsterClient.list_tasks = _list_tasks_impl  # type: ignore[attr-defined]
