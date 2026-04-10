"""Multi-agent workflow reference implementation using the Agent Bus.

This script demonstrates a complete planner-worker-reviewer coordination
pattern using typed messages, correlation IDs, and the Agent Bus primitives.

Flow:
1. Planner sends typed requests to 2 workers with shared correlation_id
2. Workers execute tasks and send handoff messages back to planner
3. Planner aggregates results using get_workflow_messages()
4. Planner forwards aggregated context to reviewer
5. Reviewer posts approval decision back

Run this script directly:
    python examples/multi_agent_workflow.py

Or import and adapt for your own workflows.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime

from shoal.core.db import ShoalDB
from shoal.core.message_bus import (
    get_workflow_messages,
    mark_consumed,
    receive_messages,
    send_message,
    watch_messages,
)


async def simulate_planner(correlation_id: str) -> None:
    """Planner session: coordinates work across multiple workers.

    The planner is responsible for:
    - Decomposing work into parallel tasks
    - Sending typed requests to worker sessions
    - Aggregating results from workers
    - Forwarding context to the reviewer
    """
    print("=== PLANNER: Starting workflow ===")

    # Step 1: Send parallel requests to two workers
    # Using kind="request" signals this is an actionable work item
    task_a_payload = json.dumps(
        {
            "task": "validate_api_endpoints",
            "files": ["src/api/auth.py", "src/api/users.py"],
        }
    )
    await send_message(
        from_session="planner",
        to_session="worker-a",
        topic="code-review",
        payload=task_a_payload,
        kind="request",
        correlation_id=correlation_id,
        priority=2,  # 1=highest, 5=lowest
        requires_ack=True,
    )
    print("  → Sent request to worker-a (task: validate_api_endpoints)")

    task_b_payload = json.dumps(
        {
            "task": "check_test_coverage",
            "files": ["tests/test_api.py"],
        }
    )
    await send_message(
        from_session="planner",
        to_session="worker-b",
        topic="code-review",
        payload=task_b_payload,
        kind="request",
        correlation_id=correlation_id,
        priority=2,
        requires_ack=True,
    )
    print("  → Sent request to worker-b (task: check_test_coverage)")

    # Step 2: Wait for handoff responses from both workers
    # Using kind="handoff" to filter for completion messages
    print("\n  ⏳ Waiting for workers to complete...")
    handoffs = await watch_messages(
        session="planner",
        kind="handoff",
        correlation_id=correlation_id,
        timeout_seconds=10.0,
        poll_interval=0.5,
    )

    if len(handoffs) < 2:
        print(f"  ⚠️  Only received {len(handoffs)}/2 handoffs (timeout)")
        # In production: handle partial completion, retry, or escalate
        return

    print(f"  ✓ Received {len(handoffs)} handoffs from workers")
    for msg in handoffs:
        await mark_consumed(msg["id"])  # type: ignore[arg-type]
        result = json.loads(msg["payload"])  # type: ignore[arg-type]
        print(f"    - {msg['from_session']}: {result.get('status', 'unknown')}")

    # Step 3: Aggregate full workflow context
    # get_workflow_messages retrieves ALL messages with this correlation_id,
    # regardless of session boundaries — perfect for building context
    all_messages = await get_workflow_messages(correlation_id)
    print(f"\n  📊 Aggregated {len(all_messages)} messages across workflow")

    # Step 4: Forward aggregated context to reviewer
    review_payload = json.dumps(
        {
            "workflow_id": correlation_id,
            "worker_results": [
                json.loads(msg["payload"])  # type: ignore[arg-type]
                for msg in all_messages
                if msg["kind"] == "handoff"
            ],
            "summary": "API validation and test coverage review completed",
        }
    )
    await send_message(
        from_session="planner",
        to_session="reviewer",
        topic="approval",
        payload=review_payload,
        kind="approval_request",
        correlation_id=correlation_id,
        requires_ack=True,
    )
    print("  → Forwarded aggregated context to reviewer")

    # Step 5: Wait for reviewer approval
    print("\n  ⏳ Waiting for reviewer approval...")
    approval = await watch_messages(
        session="planner",
        kind="approval_decision",
        correlation_id=correlation_id,
        timeout_seconds=10.0,
    )

    if approval:
        decision = json.loads(approval[0]["payload"])  # type: ignore[arg-type]
        await mark_consumed(approval[0]["id"])  # type: ignore[arg-type]
        if decision.get("approved"):
            print("  ✅ Workflow approved by reviewer")
        else:
            print(f"  ❌ Workflow rejected: {decision.get('reason', 'no reason')}")
    else:
        print("  ⚠️  Reviewer approval timeout")

    print("\n=== PLANNER: Workflow complete ===")


async def simulate_worker(worker_id: str, correlation_id: str) -> None:
    """Worker session: executes assigned tasks and reports back.

    Workers are responsible for:
    - Polling for requests addressed to them
    - Executing the requested work
    - Sending handoff messages with results
    """
    print(f"\n=== WORKER-{worker_id.upper()}: Starting ===")

    # Small delay to ensure planner messages are committed
    await asyncio.sleep(0.1)

    # Poll for incoming requests
    # unconsumed_only=True ensures we don't reprocess messages
    messages = await receive_messages(
        session=f"worker-{worker_id}",
        kind="request",
        correlation_id=correlation_id,
        unconsumed_only=True,
    )

    if not messages:
        print(f"  ⚠️  No work assigned to worker-{worker_id}")
        return

    for msg in messages:
        task = json.loads(msg["payload"])  # type: ignore[arg-type]
        print(f"  📋 Received task: {task['task']}")

        # Mark message as consumed to prevent duplicate processing
        await mark_consumed(msg["id"])  # type: ignore[arg-type]

        # Simulate work execution
        await asyncio.sleep(0.5)
        print(f"     Processing {len(task.get('files', []))} files...")
        await asyncio.sleep(0.5)

        # Send handoff with results back to planner
        result_payload = json.dumps(
            {
                "task": task["task"],
                "status": "completed",
                "findings": f"All checks passed for {task['task']}",
                "files_processed": len(task.get("files", [])),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        await send_message(
            from_session=f"worker-{worker_id}",
            to_session="planner",
            topic="task-complete",
            payload=result_payload,
            kind="handoff",
            correlation_id=correlation_id,
            reply_to_message_id=msg["id"],  # type: ignore[arg-type]
        )
        print("  ✓ Sent handoff to planner")

    print(f"=== WORKER-{worker_id.upper()}: Complete ===")


async def simulate_reviewer(correlation_id: str) -> None:
    """Reviewer session: validates aggregated work and approves/rejects.

    Reviewers are responsible for:
    - Receiving approval requests with aggregated context
    - Validating the work meets quality standards
    - Posting approval_decision messages
    """
    print("\n=== REVIEWER: Starting ===")

    # Wait for approval request from planner using watch_messages
    # This ensures we wait for the message to arrive
    requests = await watch_messages(
        session="reviewer",
        kind="approval_request",
        correlation_id=correlation_id,
        timeout_seconds=5.0,
        poll_interval=0.2,
    )

    if not requests:
        print("  ⚠️  No approval requests received")
        return

    for msg in requests:
        review_data = json.loads(msg["payload"])  # type: ignore[arg-type]
        print("  📋 Received approval request")
        print(f"     Workflow: {review_data['workflow_id']}")
        print(f"     Workers: {len(review_data['worker_results'])} completed")

        await mark_consumed(msg["id"])  # type: ignore[arg-type]

        # Simulate review process
        await asyncio.sleep(0.5)
        print("     Reviewing worker results...")
        await asyncio.sleep(0.5)

        # Make approval decision
        all_passed = all(r.get("status") == "completed" for r in review_data["worker_results"])

        decision_payload = json.dumps(
            {
                "approved": all_passed,
                "reason": "All workers completed successfully"
                if all_passed
                else "Some tasks failed",
                "reviewed_at": datetime.now(UTC).isoformat(),
            }
        )
        await send_message(
            from_session="reviewer",
            to_session="planner",
            topic="review-decision",
            payload=decision_payload,
            kind="approval_decision",
            correlation_id=correlation_id,
            reply_to_message_id=msg["id"],  # type: ignore[arg-type]
        )
        print(f"  ✅ Posted approval decision: {'APPROVED' if all_passed else 'REJECTED'}")

    print("=== REVIEWER: Complete ===")


async def main() -> None:
    """Run the complete multi-agent workflow demonstration."""
    # Generate unique correlation ID for this workflow
    correlation_id = f"wf_{uuid.uuid4().hex[:12]}"

    print("Multi-Agent Workflow Demo")
    print(f"Correlation ID: {correlation_id}")
    print("=" * 50)

    # Initialize database connection
    # In production, this is typically handled by the Shoal harness
    db = await ShoalDB.get_instance()
    await db.connect()

    # Run all agents concurrently
    # In production, each would be a separate Shoal session
    await asyncio.gather(
        simulate_planner(correlation_id),
        simulate_worker("a", correlation_id),
        simulate_worker("b", correlation_id),
        simulate_reviewer(correlation_id),
    )

    print("\n" + "=" * 50)
    print("✅ Workflow demonstration complete!")
    print("\nKey takeaways:")
    print(f"  • Used correlation_id '{correlation_id}' to track workflow")
    print("  • Typed messages (request/handoff/approval_decision) for clarity")
    print("  • get_workflow_messages() aggregated cross-session context")
    print("  • watch_messages() provided event-driven coordination")
    print("  • mark_consumed() prevented duplicate processing")


if __name__ == "__main__":
    asyncio.run(main())
