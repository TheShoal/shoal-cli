"""Action Bus — session action requests and approval lifecycle.

Actions are distinct from ordinary Agent Bus messages.  They represent
privileged operations that require explicit approval before execution.

Usage::

    from shoal.core.action_bus import request_action, approve_action, deny_action

    # Worker requests a privileged operation
    action_id = await request_action(
        requester_session="worker-a",
        action_type="merge_branch",
        payload_json=json.dumps({"branch": "feature/auth", "target": "main"}),
        target_session="supervisor",
        correlation_id="wf_01H...",
    )

    # Supervisor lists pending requests and approves
    pending = await list_pending_actions(target_session="supervisor")
    for action in pending:
        await approve_action(action.id, resolved_by="supervisor", reason="LGTM")
"""

from __future__ import annotations

import logging

from shoal.models.action import ActionStatus, SessionAction

logger = logging.getLogger("shoal.action_bus")


async def request_action(
    requester_session: str,
    action_type: str,
    payload_json: str,
    *,
    target_session: str | None = None,
    target_role: str | None = None,
    correlation_id: str | None = None,
    metadata_json: str | None = None,
) -> int:
    """Submit an action request requiring approval.

    Args:
        requester_session: Session requesting the action.
        action_type: Type of action (e.g. ``"merge_branch"``).
        payload_json: JSON string describing the action payload.
        target_session: Optional session that should approve.
        target_role: Optional role that should approve (alternative to
            target_session for role-routed approvals).
        correlation_id: Optional workflow correlation ID.
        metadata_json: Optional JSON metadata string.

    Returns:
        Auto-assigned action ID.
    """
    from shoal.core.db import get_db

    db = await get_db()
    action_id = await db.create_session_action(
        requester_session,
        action_type,
        payload_json,
        target_session=target_session,
        target_role=target_role,
        correlation_id=correlation_id,
        metadata_json=metadata_json,
    )
    logger.debug(
        "ActionBus: requested action %d  %s [%s] target=%s corr=%s",
        action_id,
        action_type,
        requester_session,
        target_session or target_role,
        correlation_id,
    )
    return action_id


async def get_action(action_id: int) -> SessionAction | None:
    """Retrieve an action by ID.

    Args:
        action_id: ID of the action.

    Returns:
        SessionAction if found, else None.
    """
    from shoal.core.db import get_db

    db = await get_db()
    return await db.get_session_action(action_id)


async def list_pending_actions(
    *,
    target_session: str | None = None,
    target_role: str | None = None,
    correlation_id: str | None = None,
    limit: int = 50,
) -> list[SessionAction]:
    """List pending action requests.

    Args:
        target_session: Optional filter by target session.
        target_role: Optional filter by target role.
        correlation_id: Optional filter by correlation ID.
        limit: Maximum number of actions to return.

    Returns:
        List of pending SessionAction objects, oldest-first.
    """
    from shoal.core.db import get_db

    db = await get_db()
    return await db.list_pending_session_actions(
        target_session=target_session,
        target_role=target_role,
        correlation_id=correlation_id,
        limit=limit,
    )


async def approve_action(
    action_id: int,
    resolved_by: str,
    reason: str | None = None,
) -> SessionAction | None:
    """Approve a pending action request.

    Args:
        action_id: ID of the action to approve.
        resolved_by: Identifier of the approving session or user.
        reason: Optional human-readable approval reason.

    Returns:
        Updated SessionAction with status=approved, or None if not found.
    """
    from shoal.core.db import get_db

    db = await get_db()
    action = await db.resolve_session_action(
        action_id,
        ActionStatus.approved,
        resolved_by,
        reason,
    )
    if action:
        logger.info(
            "ActionBus: approved action %d by %s  corr=%s",
            action_id,
            resolved_by,
            action.correlation_id,
        )
    return action


async def deny_action(
    action_id: int,
    resolved_by: str,
    reason: str | None = None,
) -> SessionAction | None:
    """Deny a pending action request.

    Args:
        action_id: ID of the action to deny.
        resolved_by: Identifier of the denying session or user.
        reason: Optional human-readable denial reason.

    Returns:
        Updated SessionAction with status=denied, or None if not found.
    """
    from shoal.core.db import get_db

    db = await get_db()
    action = await db.resolve_session_action(
        action_id,
        ActionStatus.denied,
        resolved_by,
        reason,
    )
    if action:
        logger.info(
            "ActionBus: denied action %d by %s  corr=%s",
            action_id,
            resolved_by,
            action.correlation_id,
        )
    return action
