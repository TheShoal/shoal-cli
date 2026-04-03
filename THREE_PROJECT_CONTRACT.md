# Three-Project Contract: Pisces, Shoal, and Lobster Party

## Purpose

This document defines the recommended ownership boundaries between the three related projects so they can evolve together without duplicating orchestration logic or coupling to each other's internals.

## Recommended stack

- **Pisces** = agent runtime and decomposition engine
- **Shoal** = local session orchestration substrate
- **Lobster Party** = remote/server control plane and federation layer

Short version:

- Pisces thinks.
- Shoal runs workers.
- Lobster coordinates systems.

## Why this split fits the current code

### Pisces already owns decomposition

Pisces already has a native task/subagent system:

- `README.md:159` describes the Task Tool as a subagent system with bundled agents, parallel execution, real-time artifact streaming, and isolation backends.
- `packages/coding-agent/src/task/executor.ts:432` shows recursive subagent execution and task-tool gating.

Pisces also already has Shoal-backed orchestration features:

- `packages/coding-agent/src/shoal/commands.ts:2` documents `/team` as Shoal-backed multi-agent team orchestration.
- `packages/coding-agent/src/shoal/orchestrator.ts:2` defines `ShoalOrchestrator` as a Shoal-backed multi-agent pipeline.
- `packages/coding-agent/src/shoal/session-lifecycle.ts:2` defines `ShoalMcpBridge` over `shoal-mcp-server`.

### Shoal already owns session substrate concerns

Shoal already provides the session/runtime layer:

- `src/shoal/services/runtime_providers/tmux.py:103` handles runtime input injection.
- `src/shoal/models/batch.py:54` models `send_keys` as terminal actuation, not messaging.
- `src/shoal/core/message_bus.py:1` defines the Agent Bus for session-to-session messaging.
- `src/shoal/core/db.py:142` stores message queue state in SQLite.
- `src/shoal/services/mcp_shoal_server.py:663` exposes session message MCP tools.

Shoal also documents that MCP pooled memory is not shared across sessions:

- `ARCHITECTURE.md:159` describes per-connection spawning for MCP servers.
- `ARCHITECTURE.md:180` states memory state is not shared between agents.

### Lobster Party already owns protocol-rich coordination

Lobster Party already has the strongest remote coordination model:

- `proto/a2a_claw.proto:41` describes A2A send/stream/subscribe operations.
- `proto/a2a_claw.proto:196` describes `AgentToAgent` / InterClaw relay semantics.
- `cmd/lobster-loop/src/grpc.rs:372` enforces delegated ownership/permission checks.
- `cmd/lobster-loop/src/conversation.rs:17` persists conversation/task metadata such as channel, conversation ID, session ID, thread ID, and employee ID.

## Ownership contract

## 1. Pisces

**Role:** agent runtime and decomposition engine.

### Pisces owns

- prompts and system behavior
- tool execution behavior
- model/tool selection policy
- in-session subagent decomposition via `task`
- agent personas and bundled agent definitions
- team planning logic if `/team` remains a Pisces-facing UX

### Pisces does not own

- tmux lifecycle
- git worktree lifecycle
- session registry
- cross-session message persistence semantics
- fleet-level approval workflows
- remote federation and cross-claw routing

### Rule of thumb

If the work fits inside one agent session, Pisces should own it.
If the work needs multiple long-lived isolated workers, Pisces should ask Shoal.

## 2. Shoal

**Role:** local orchestration substrate for agent sessions.

### Shoal owns

- session lifecycle
- worktree lifecycle
- runtime transport/control
- pane capture and readiness
- journals and handoffs
- inter-session Agent Bus
- approval/action gating
- local fleet supervision and observability

### Shoal does not own

- intra-session decomposition heuristics
- provider/model reasoning strategy
- agent persona definitions
- cloud federation or remote multi-claw routing

### Rule of thumb

If it is about starting, stopping, isolating, observing, or coordinating sessions, Shoal should own it.

## 3. Lobster Party

**Role:** remote/server control plane and federation layer.

### Lobster Party owns

- remote task submission
- A2A / InterClaw routing
- streaming subscriptions
- ACL and permission enforcement across claws
- durable remote conversation/task metadata
- cloud or service-hosted coordination

### Lobster Party does not own

- tmux details
- Shoal SQLite internals
- Pisces internal subagent execution

### Rule of thumb

If the coordination crosses machines, claws, users, or service boundaries, Lobster Party should own it.

## Integration hierarchy

Recommended hierarchy:

- Lobster Party sits above Shoal.
- Shoal sits beside/under Pisces as the multi-session substrate.
- Pisces sits inside each worker as the runtime.

In practice:

- Pisces runtime can call Shoal when it wants multiple isolated workers.
- Shoal can host Pisces workers as sessions.
- Lobster can orchestrate Shoal through a Shoal-facing adapter or contract.

## Critical boundary rules

## Boundary rule 1: Pisces may use Shoal, but only via a stable contract

Good:

- Pisces calls Shoal MCP/API/CLI wrappers.
- Pisces creates sessions through Shoal.
- Pisces watches status through Shoal.
- Pisces exchanges cross-session messages through Shoal.

Bad:

- Pisces treats Shoal SQLite as a durable public API.

Current caveat:

- `packages/coding-agent/src/shoal/awareness.ts:4` states Pisces reads the Shoal SQLite DB directly.

That is acceptable as a bootstrap optimization, but not as the long-term integration boundary.

## Boundary rule 2: one decomposition model, one session model

Pisces currently has two parallelism modes:

1. native `task` subagents
2. Shoal-backed `/team` orchestration

This is acceptable only if the scopes are explicit.

### Use `task` when

- delegation stays inside one runtime/session
- separate worktrees are unnecessary
- workers do not need long-lived session identity
- outputs can stay local to the parent session

### Use Shoal-backed `/team` when

- you want separate worktrees
- you want separately inspectable sessions
- you want fleet-level status and supervision
- you want handoffs/journals/session artifacts
- you need cross-session messaging or approvals

## Boundary rule 3: Lobster should talk to Shoal, not to tmux or SQLite

Lobster Party should never directly depend on:

- Shoal tmux internals
- Shoal DB schema
- Pisces internal task state

It should talk through a stable Shoal-facing adapter:

- MCP tools
- a dedicated Shoal API
- or a Shoal claw wrapper over those tools

That adapter is where translation happens between:

- Lobster task/thread/event semantics
- and Shoal session/message/action semantics

## Feature ownership matrix

| Capability | Pisces | Shoal | Lobster Party |
|---|---|---|---|
| In-session subagents | Primary owner | No | No |
| Session lifecycle | No | Primary owner | No |
| Worktrees | No | Primary owner | No |
| Session messaging | Consumer | Primary owner | Consumer via adapter |
| Session approvals | Consumer | Primary owner | Consumer via adapter |
| Local supervision | Consumer | Primary owner | No |
| Remote federation | No | Adapter target | Primary owner |
| Cross-claw ACLs | No | Local hooks only | Primary owner |
| Conversation/thread metadata | Local only | Workflow metadata only | Primary owner |

## What to standardize next

### A. Shoal as the public orchestration substrate

The stable public surface should include:

- `create_session`
- `kill_session`
- `list_sessions`
- `session_info`
- `wait_for_completion`
- `mark_complete`
- `capture_pane`
- `session_snapshot`
- `read_journal`
- `append_journal`
- `send_session_message`
- `receive_session_messages`
- `mark_session_message_consumed`

Future additions:

- `request_session_action`
- `approve_session_action`
- `deny_session_action`

### B. A richer Shoal message envelope

Current message shape in Shoal is minimal:

- `from_session`
- `to_session`
- `topic`
- `payload`
- timestamps and consumed state

Recommended additions:

- `kind`
- `correlation_id`
- `reply_to_message_id`
- `priority`
- `requires_ack`
- `metadata_json`
- optional `expires_at`

Suggested `kind` values:

- `request`
- `response`
- `event`
- `handoff`
- `approval_request`
- `approval_decision`
- `error`

### C. A standard Pisces execution decision

Pisces should explicitly choose between:

- `task` for in-session decomposition
- Shoal for inter-session execution

### D. A standard Lobster mapping

Lobster concepts should map onto Shoal concepts:

- Lobster `task_id` -> Shoal `correlation_id`
- Lobster `thread/conversation` -> Shoal workflow/session metadata
- Lobster `AgentToAgent` -> Shoal session message or action request
- Lobster subscriptions -> Shoal watch/event surfaces

## Current overlap to untangle

### 1. Pisces direct DB awareness

Current:

- Pisces reads Shoal SQLite directly in `packages/coding-agent/src/shoal/awareness.ts:4`.

Recommendation:

- keep it only for lightweight contextual awareness if necessary
- do not build critical orchestration behavior on it
- replace it over time with a stable Shoal surface

### 2. Pisces `/team` versus Pisces `task`

Current:

- both exist
- both imply multi-agent operation

Recommendation:

- document them as two different scopes:
  - `task` = in-session
  - `/team` = Shoal-backed multi-session

### 3. Lobster/Shoal boundary

Current Shoal already has claw-related integration points:

- `src/shoal/cli/claw.py`
- `src/shoal/core/claw_client.py`
- `src/shoal/core/claw_conversations.py`

Recommendation:

- formalize this as an adapter boundary
- avoid turning Shoal into a partial Lobster clone
- avoid turning Lobster into a remote tmux wrapper

## Next planning outputs

This contract should be converted into:

1. a repo-by-repo backlog
2. a Shoal API/schema proposal
3. a Pisces migration plan away from Shoal internals
