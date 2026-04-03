"""FastMCP server bridge for Lobster Party A2A protocol.

This module translates local MCP tool calls to remote A2A gRPC requests,
enabling AI agents to discover and interact with Claw runtimes via the
Agent2Agent (A2A) protocol.

The bridge exposes MCP tools that wrap the ClawClient gRPC client,
providing agent discovery (GetAgentCard) and task submission capabilities.

Spec: https://a2a-protocol.org/latest/specification/
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import ValidationError

if TYPE_CHECKING:
    from shoal.core.lobster_client import LobsterClient
    from shoal.models.config import ShoalConfig

logger = logging.getLogger("shoal.lobster_a2a")

# Guard gRPC imports - these are optional dependencies
try:
    import shoal.integrations.lobster.a2a_bridge  # noqa: F401 — activates LobsterClient A2A extensions
    from shoal.core.lobster_client import LobsterClient

    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False
    logger.debug("grpcio not installed - A2A bridge disabled")

# ---------------------------------------------------------------------------
# MCP Server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="lobster-a2a-bridge",
    instructions=(
        "Lobster Party A2A protocol bridge. Use these tools to discover "
        "Claw runtimes via AgentCard and submit tasks via A2A gRPC. "
        "All Claw communication requires grpcio optional dependency."
    ),
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _get_lobster_endpoint(config: ShoalConfig, lobster_id: str) -> str:
    """Get endpoint URL for a Lobster from config.

    Args:
        config: Shoal configuration with known_lobsters mapping.
        lobster_id: The Lobster identifier to lookup.

    Returns:
        The gRPC endpoint URL for the Lobster.

    Raises:
        ToolError: If Lobster is not found in known_lobsters.
    """
    endpoint = config.lobster.known_lobsters.get(lobster_id)
    if not endpoint:
        raise ToolError(f"Lobster '{lobster_id}' not found in known_lobsters configuration")
    return endpoint


# ---------------------------------------------------------------------------
# Tool: get_agent_card
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_agent_card",
    description=(
        "Get a Claw runtime's AgentCard for agent discovery. "
        "Returns metadata about the Claw's capabilities, skills, and endpoint. "
        "Requires grpcio optional dependency."
    ),
    annotations={"readOnlyHint": True},
)
async def get_agent_card_tool(lobster_id: str) -> dict[str, str | bool | list[dict[str, str]]]:
    """Get AgentCard from a Lobster runtime.

    This tool queries a Lobster runtime's GetAgentCard RPC to retrieve
    its capabilities and identity metadata. This is the primary A2A
    agent discovery mechanism.

    Args:
        lobster_id: The Lobster identifier to query.

    Returns:
        Dictionary containing the AgentCard with fields:
        - name: Agent name
        - version: Agent version
        - provider: Organization info {organization, url}
        - capabilities: {streaming, push_notifications, state_transition_reports}
        - skills: List of {id, name, description, tags}
        - endpoint: gRPC endpoint URL
        - description: Human-readable description
        - metadata: Additional key-value pairs

    Raises:
        ToolError: If grpcio is not installed or Lobster is not configured.
        RuntimeError: If gRPC call fails.
    """
    if not GRPC_AVAILABLE:
        raise ToolError("Claw A2A bridge requires grpcio. Install with: pip install shoal[claw]")

    from shoal.core.config import load_config

    config = load_config()
    endpoint = _get_lobster_endpoint(config, lobster_id)

    client: LobsterClient | None = None
    try:
        client = LobsterClient(
            lobster_id=lobster_id,
            endpoint=endpoint,
            employee_id=config.lobster.employee_id,
            config=config.lobster,
        )

        agent_card = await client.get_agent_card()  # type: ignore[attr-defined]
        return agent_card.model_dump()  # type: ignore[no-any-return]

    except ValidationError as exc:
        logger.error("AgentCard validation failed for Lobster %s: %s", lobster_id, exc)
        raise ToolError(f"Invalid AgentCard from Lobster {lobster_id}: {exc}") from exc
    except RuntimeError as exc:
        logger.error("Lobster %s AgentCard RPC failed: %s", lobster_id, exc)
        raise ToolError(f"Failed to get AgentCard from {lobster_id}: {exc}") from exc
    finally:
        if client:
            await client.close()


# ---------------------------------------------------------------------------
# Tool: send_a2a_message
# ---------------------------------------------------------------------------


@mcp.tool(
    name="send_a2a_message",
    description=(
        "Send a message to a Claw runtime via A2A protocol. "
        "Submits work to the Claw and returns the response. "
        "Requires grpcio optional dependency."
    ),
    annotations={"destructiveHint": True},
)
async def send_a2a_message_tool(
    lobster_id: str,
    message: str,
    task_id: str | None = None,
    employee_id: str | None = None,
) -> dict[str, object]:
    """Send a message to a Lobster runtime via A2A SendMessage RPC.

    This tool submits work to a Lobster runtime using the A2A protocol's
    SendMessage operation. It replaces the legacy Turn RPC.

    Args:
        lobster_id: The Lobster identifier to send work to.
        message: The message/work payload to process.
        task_id: Optional task ID for idempotency (generated if not provided).
        employee_id: Optional employee ID for audit trail (uses config default if not provided).

    Returns:
        Dictionary containing:
        - task_id: The task identifier
        - response: The Lobster's response text
        - state: Current Lobster state after processing

    Raises:
        ToolError: If grpcio is not installed or Lobster is not configured.
        RuntimeError: If gRPC call fails.
    """
    if not GRPC_AVAILABLE:
        raise ToolError("Claw A2A bridge requires grpcio. Install with: pip install shoal[claw]")

    from shoal.core.config import load_config

    config = load_config()
    endpoint = _get_lobster_endpoint(config, lobster_id)
    emp_id = employee_id or config.lobster.employee_id

    client: LobsterClient | None = None
    try:
        client = LobsterClient(
            lobster_id=lobster_id,
            endpoint=endpoint,
            employee_id=emp_id,
            config=config.lobster,
        )

        return cast(
            dict[str, object],
            await client.send_message(  # type: ignore[attr-defined]
                message=message,
                task_id=task_id,
            ),
        )

    except RuntimeError as exc:
        logger.error("Lobster %s A2A message failed: %s", lobster_id, exc)
        raise ToolError(f"Failed to send message to {lobster_id}: {exc}") from exc
    finally:
        if client:
            await client.close()


# ---------------------------------------------------------------------------
# Tool: list_a2a_tasks
# ---------------------------------------------------------------------------


@mcp.tool(
    name="list_a2a_tasks",
    description=(
        "List tasks for a Claw runtime via A2A protocol. "
        "Returns tasks with optional filtering by context or status. "
        "Requires grpcio optional dependency."
    ),
    annotations={"readOnlyHint": True},
)
async def list_a2a_tasks_tool(
    lobster_id: str,
    context_id: str | None = None,
    status: str | None = None,
) -> dict[str, list[dict[str, str]] | str]:
    """List tasks from a Lobster runtime via A2A ListTasks RPC.

    Args:
        lobster_id: The Lobster identifier to query.
        context_id: Optional context ID to filter tasks by.
        status: Optional task state to filter by (e.g., "working", "completed").

    Returns:
        Dictionary containing list of tasks with their states and metadata.

    Raises:
        ToolError: If grpcio is not installed or Lobster is not configured.
        RuntimeError: If gRPC call fails.
    """
    if not GRPC_AVAILABLE:
        raise ToolError("Claw A2A bridge requires grpcio. Install with: pip install shoal[claw]")

    from shoal.core.config import load_config

    config = load_config()
    endpoint = _get_lobster_endpoint(config, lobster_id)

    client: LobsterClient | None = None
    try:
        client = LobsterClient(
            lobster_id=lobster_id,
            endpoint=endpoint,
            employee_id=config.lobster.employee_id,
            config=config.lobster,
        )

        tasks = await client.list_tasks(  # type: ignore[attr-defined]
            context_id=context_id,
            status=status,
        )
        return {
            "tasks": tasks,
            "lobster_id": lobster_id,
        }

    except RuntimeError as exc:
        logger.error("Lobster %s ListTasks RPC failed: %s", lobster_id, exc)
        raise ToolError(f"Failed to list tasks from {lobster_id}: {exc}") from exc
    finally:
        if client:
            await client.close()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the A2A bridge MCP server."""
    if not GRPC_AVAILABLE:
        logger.error("grpcio not installed - cannot start A2A bridge server")
        raise SystemExit(1)

    mcp.run()


if __name__ == "__main__":
    main()
