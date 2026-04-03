# Three-Project Backlog

This backlog turns `THREE_PROJECT_CONTRACT.md` into parallelizable work across:

- `shoal-cli`
- `pisces`
- `lobster-party`

The goal is to let all three repos move at once without duplicating ownership.

## Global sequencing rules

### Safe to parallelize immediately

- Shoal public contract design
- Pisces UX/documentation clarifying `task` vs Shoal-backed `/team`
- Lobster adapter design for Shoal integration

### Must sequence after Shoal contract stabilizes

- Pisces migration off Shoal SQLite internals
- Lobster implementation against the Shoal adapter
- any cross-repo shared correlation/message semantics

### Deferred

- room/chat abstractions
- shared MCP-memory assumptions
- direct Lobster control of tmux/runtime details

## Workstream 1: shoal-cli

**Owner:** Shoal
**Goal:** make Shoal the stable public orchestration substrate for both Pisces and Lobster.

### Shoal-P0: public contract stabilization

1. Document current public orchestration surface
   - `create_session`
   - `kill_session`
   - `session_info`
   - `session_snapshot`
   - `wait_for_completion`
   - `mark_complete`
   - `send_session_message`
   - `receive_session_messages`
   - `mark_session_message_consumed`

2. Enrich Agent Bus schema
   - add `kind`
   - add `correlation_id`
   - add `reply_to_message_id`
   - add `priority`
   - add `requires_ack`
   - add `metadata_json`
   - optionally add `expires_at`

3. Add request/reply semantics
   - codify message `kind` values
   - support correlation-driven request/response patterns
   - preserve backward compatibility with current minimal envelope

4. Distinguish message from action
   - define action request model separately from ordinary bus messages
   - reserve approval hooks for actions, not every message

### Shoal-P1: approval and watch surfaces

5. Add action request primitives
   - `request_session_action`
   - `approve_session_action`
   - `deny_session_action`

6. Add event/watch ergonomics
   - CLI watch UX
   - MCP watch/subscribe UX, even if backed by polling internally
   - correlation-centric status updates for workflows

7. Add workflow metadata surfaces
   - expose correlation/workflow metadata in session summaries or snapshots
   - support journal/handoff linkage to workflow IDs where useful

### Shoal-P2: adapter readiness for Lobster

8. Define a Shoal-facing adapter contract for Lobster
   - task correlation mapping
   - session targeting and identity
   - action approval hooks
   - event streaming/watch expectations

9. Reduce reliance on implementation details in consumers
   - explicitly mark Shoal SQLite schema as internal
   - ensure MCP/API/CLI wrappers cover required integration paths

### Shoal deliverables

- `SHOAL_ORCHESTRATION_API.md`
- enriched SQLite migrations
- MCP tool updates
- CLI/API docs for messaging and actions
- optional watch endpoint/tooling

## Workstream 2: pisces

**Owner:** Pisces
**Goal:** keep Pisces as the decomposition engine while using Shoal as the stable inter-session substrate.

### Pisces-P0: clarify product model

1. Document the two parallelism modes
   - `task` = in-session subagents
   - Shoal-backed `/team` = multi-session execution

2. Clarify execution decision rules
   - when to use `task`
   - when to use Shoal sessions
   - when to keep work inside one runtime

3. Make the Shoal dependency explicit but bounded
   - describe Shoal as the inter-session substrate
   - stop implying that Pisces itself owns session orchestration internals

### Pisces-P1: contract alignment

4. Refactor Shoal integrations toward a stable boundary
   - route orchestration through `ShoalMcpBridge` or equivalent public wrapper
   - minimize direct DB dependence outside awareness/bootstrap UX

5. Preserve lightweight workspace awareness separately
   - if direct DB reads stay temporarily, limit them to non-critical context injection
   - isolate that code so it can be swapped out later with a stable API call

6. Standardize cross-session workflow metadata
   - pass `correlation_id` / workflow metadata when creating Shoal-backed teams
   - consume Shoal message envelopes rather than bespoke payload conventions

### Pisces-P2: UX and runtime integration

7. Align `/team` with the contract
   - ensure team runs use Shoal public orchestration operations only
   - ensure status rendering can consume future watch/event surfaces

8. Keep task/subagent execution separate
   - no session-lifecycle logic inside task runtime
   - no worktree/session assumptions inside in-process subagents

### Pisces deliverables

- `PISCES_SHOAL_EXECUTION_MODEL.md`
- updated `/team` docs and help text
- reduced direct Shoal SQLite dependency
- correlation-aware Shoal team orchestration

## Workstream 3: lobster-party

**Owner:** Lobster Party
**Goal:** integrate with Shoal through a clean adapter while keeping Lobster responsible for remote federation and ACLs.

### Lobster-P0: adapter design

1. Define the Shoal claw contract
   - session discovery
   - session lifecycle hooks
   - workflow correlation
   - message send/receive
   - action approval path
   - journal/handoff read surfaces

2. Map Lobster semantics onto Shoal semantics
   - Lobster `task_id` -> Shoal `correlation_id`
   - Lobster thread/conversation metadata -> Shoal workflow metadata
   - Lobster `AgentToAgent` -> Shoal message or action request

3. Decide transport shape
   - direct MCP bridge
   - dedicated Shoal claw service
   - hybrid wrapper over MCP tools

### Lobster-P1: policy alignment

4. Define which actions require approval
   - file mutation requests
   - merge/release actions
   - cross-domain escalation
   - any request that crosses role boundaries

5. Reuse Lobster ACL semantics above Shoal, not inside Shoal
   - Lobster stays responsible for cross-claw trust and federation policy
   - Shoal only needs local action gating primitives and local role constraints

### Lobster-P2: runtime integration

6. Subscribe to Shoal workflow events
   - completion
   - failure
   - approval requested
   - approval decided
   - message response received

7. Persist mapped metadata
   - retain Lobster thread/task metadata while referencing Shoal session/workflow identities

### Lobster deliverables

- `SHOAL_CLAW_CONTRACT.md`
- correlation/identity mapping design
- approval policy matrix
- adapter implementation plan

## Cross-repo dependency map

### Can start now with no code dependency

- Shoal API/spec document
- Pisces execution-model document
- Lobster Shoal-claw contract document

### Depends on Shoal schema/API decisions

- Pisces migration off direct SQLite reads
- Pisces correlation-aware `/team` implementation
- Lobster adapter implementation
- Lobster event/watch integration

### Depends on Shoal action model

- Lobster approval routing
- Pisces action-request UX for team runs

## Suggested simultaneous execution plan

### Track A: Shoal foundation

- finalize public orchestration contract
- finalize message envelope
- finalize action/approval model

### Track B: Pisces alignment

- clarify `task` vs `/team`
- isolate direct Shoal DB reads
- prepare migration to Shoal public surfaces

### Track C: Lobster adapter design

- define Shoal claw boundary
- define mapping of task/thread/action semantics
- prepare implementation once Shoal contract lands

## Definition of done

### Shoal done when

- consumers no longer need Shoal SQLite schema knowledge for orchestration
- request/reply is first-class
- action approval is first-class
- message correlation is first-class

### Pisces done when

- users understand when to use `task` vs Shoal-backed `/team`
- critical orchestration no longer depends on direct Shoal DB reads
- Shoal-backed teams use the stable Shoal contract

### Lobster done when

- Lobster integrates with Shoal through an explicit adapter boundary
- cross-claw semantics map cleanly onto Shoal workflows
- remote orchestration does not depend on tmux or Shoal internals
