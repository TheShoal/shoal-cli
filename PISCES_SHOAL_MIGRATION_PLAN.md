# Pisces -> Shoal Migration Plan

## Purpose

This plan keeps Pisces using Shoal as its inter-session orchestration substrate while reducing architectural risk from direct reliance on Shoal internals.

The target state is:

- Pisces continues to own runtime behavior and decomposition logic
- Shoal owns session lifecycle, worktrees, messaging, and approvals
- Pisces consumes Shoal through a stable contract instead of private storage details

## Current state

Pisces already has a meaningful Shoal integration layer:

- `packages/coding-agent/src/shoal/commands.ts:2` describes Shoal-backed `/team` orchestration.
- `packages/coding-agent/src/shoal/orchestrator.ts:2` implements a Shoal-backed multi-agent pipeline.
- `packages/coding-agent/src/shoal/session-lifecycle.ts:2` wraps `shoal-mcp-server` as `ShoalMcpBridge`.

Pisces also currently reads Shoal's SQLite database directly for awareness/context:

- `packages/coding-agent/src/shoal/awareness.ts:2`
- `packages/coding-agent/src/shoal/awareness.ts:4`

That direct DB read is the main migration concern.

## Migration principles

### Principle 1: keep Shoal as the inter-session substrate

This migration does **not** remove Shoal from Pisces.
It formalizes Shoal as the stable session substrate.

### Principle 2: preserve current user-facing value

Do not break:

- Shoal-backed `/team` workflows
- session-aware prompt context where it is useful
- the ability to inspect or manage Shoal workers from Pisces

### Principle 3: move critical paths first

The first code paths to migrate are the ones that affect orchestration correctness:

- session creation
- session observation
- completion tracking
- cross-session messaging

Awareness/context injection can lag behind if needed.

### Principle 4: distinguish awareness from orchestration

It is acceptable to keep a temporary direct DB read for passive awareness.
It is not acceptable for critical orchestration behavior to depend on private Shoal schema.

## Target Pisces architecture

### Pisces keeps owning

- agent runtime behavior
- prompts and system behavior
- model/tool selection
- task/subagent decomposition
- deciding when to use `task` versus Shoal-backed `/team`

### Pisces delegates to Shoal

- create worker sessions
- manage worktrees
- wait for completion
- read session state
- exchange inter-session messages
- handle action/approval flows
- read/write durable handoff state

## Migration scope

## In scope

- reducing direct Shoal SQLite dependence
- routing Shoal-backed orchestration through stable wrappers
- introducing correlation-aware workflow metadata where needed
- clarifying `task` versus `/team` behavior

## Out of scope

- replacing Shoal with a Pisces-native session substrate
- removing Pisces `/team`
- redesigning Pisces `task` runtime
- adding room/chat abstractions

## Migration phases

## Phase 0: document the split

### Goal

Make the product model understandable before changing behavior.

### Work

1. Document the two parallelism modes:
   - `task` = in-session subagents
   - Shoal-backed `/team` = multi-session orchestration

2. Document Shoal's role explicitly:
   - Shoal is the inter-session substrate
   - not just an optional helper

3. Mark current direct DB awareness as transitional/private in code comments and docs.

### Exit criteria

- developers can explain when to use `task` versus `/team`
- developers understand that Shoal is the session substrate

## Phase 1: isolate Shoal integration behind one Pisces boundary

### Goal

Ensure all Shoal interactions go through a small set of Pisces-owned integration modules.

### Work

1. Treat these modules as the only approved Shoal integration seam:
   - `packages/coding-agent/src/shoal/session-lifecycle.ts`
   - `packages/coding-agent/src/shoal/orchestrator.ts`
   - `packages/coding-agent/src/shoal/commands.ts`
   - `packages/coding-agent/src/shoal/awareness.ts`

2. Audit current callers and remove any direct Shoal coupling outside those modules.

3. Define integration categories inside Pisces:
   - **public substrate calls**: MCP/API/CLI-backed
   - **temporary awareness hooks**: clearly marked direct DB reads

### Exit criteria

- all Shoal usage is centralized in the Pisces Shoal integration package
- there are no ad hoc Shoal calls spread across unrelated Pisces modules

## Phase 2: migrate critical orchestration paths to stable Shoal contract

### Goal

Make the `/team` orchestration path independent of Shoal internals.

### Work

1. Ensure `ShoalOrchestrator` uses only stable Shoal operations for:
   - session creation
   - status/snapshot reads
   - completion waits
   - session cleanup
   - message exchange

2. Add support for workflow correlation IDs in Pisces team runs.

3. Pass correlation/workflow metadata through the Shoal bridge instead of embedding bespoke conventions only in prompts or file names.

4. Update status/rendering logic to prefer structured workflow/session state over implicit assumptions.

### Exit criteria

- `/team` runs do not require direct Shoal SQLite reads to function correctly
- workflow identity is visible and stable across a team run

## Phase 3: downgrade direct DB reads to optional awareness only

### Goal

Keep the useful context injection behavior without making it a hard contract.

### Work

1. Keep `awareness.ts` read-only and best-effort.

2. Make failure semantics explicit:
   - if Shoal DB is absent or changed, awareness silently degrades
   - orchestration still works through the Shoal bridge

3. Constrain awareness fields to non-critical summary data only:
   - session name
   - status
   - tool
   - worktree overlap

4. Avoid using direct DB reads for:
   - workflow correctness
   - task completion
   - worker targeting
   - approval logic

### Exit criteria

- direct DB reads are optional context only
- losing awareness data does not break orchestration

## Phase 4: replace awareness DB reads with stable Shoal query surface

### Goal

Finish the migration away from Shoal internals once Shoal exposes the needed surface.

### Work

1. ~~Add a Shoal query surface for workspace/session awareness~~ **Done (Shoal-side).**
   `list_sessions` now accepts an optional `path` parameter (MCP tool + HTTP `GET /sessions?path=...`).
   Sessions whose git root matches the given path, or whose worktree falls under it, are returned.
   - `list_sessions` — already existed
   - `session_snapshot` — already existed
   - `path` filter on `list_sessions` — **shipped**

2. Update Pisces awareness to use the stable Shoal surface.

3. Remove or quarantine the direct SQLite path as legacy fallback only if still necessary.

### Exit criteria

- Pisces no longer depends on Shoal SQLite schema for awareness
- Shoal is consumed as a public substrate end to end

## Phase 5: align `/team` with future Shoal messaging/actions

### Goal

Prepare Pisces to use richer Shoal workflow primitives as they land.

### Work

1. Use enriched Shoal message envelopes when available:
   - `kind`
   - `correlation_id`
   - `reply_to_message_id`
   - `metadata`

2. Use Shoal request/reply semantics for planner-worker coordination where useful.

3. Route privileged operations through Shoal action/approval APIs instead of ad hoc conventions.

4. Keep Pisces task/subagent execution separate from Shoal session semantics.

### Exit criteria

- Shoal-backed `/team` uses Shoal-native workflow semantics
- Pisces `task` remains an in-session runtime concern only

## Recommended code changes by file area

## `packages/coding-agent/src/shoal/awareness.ts`

### Current role

- direct Shoal DB read for context injection

### Recommendation

- keep temporarily
- add comments making it explicit that this is best-effort awareness only
- later replace with stable Shoal query surface

## `packages/coding-agent/src/shoal/session-lifecycle.ts`

### Current role

- typed wrapper over `shoal-mcp-server`

### Recommendation

- grow this into the main Shoal integration contract for Pisces
- add typed support for richer message envelopes and action requests once Shoal exposes them

## `packages/coding-agent/src/shoal/orchestrator.ts`

### Current role

- Shoal-backed multi-agent pipeline

### Recommendation

- make this fully correlation-aware
- ensure it uses only stable Shoal bridge operations for correctness-critical orchestration
- avoid hidden assumptions based on Shoal internals

## `packages/coding-agent/src/shoal/commands.ts`

### Current role

- `/team` command and tools

### Recommendation

- clarify help text and docs around when `/team` should be used versus `task`
- expose workflow/correlation identifiers in user-facing status where possible

## Product rules Pisces should adopt

## Rule 1: `task` and `/team` are different scopes

### `task`

Use for:

- planning
- analysis
- short-lived decomposition
- child work that stays inside one parent session

### `/team`

Use for:

- separate worktrees
- inspectable worker sessions
- long-running or supervised execution
- cross-session collaboration
- workflows that may need durable handoffs or approvals

## Rule 2: Shoal is a substrate, not a bag of internals

Pisces can depend on Shoal behavior.
Pisces should not depend on Shoal implementation details.

## Rule 3: awareness may degrade, orchestration may not

If Shoal awareness data is unavailable:
- system prompt context may be less rich
- orchestration must still work

## Dependency order

### Can be done now

- document `task` versus `/team`
- centralize Shoal integration code
- mark DB awareness as transitional

### Depends on Shoal contract work

- migration off SQLite awareness
- correlation-aware workflow plumbing
- action/approval integration

## Risks

### Risk: breaking useful awareness too early

Mitigation:
- keep awareness best-effort until Shoal exposes a replacement surface

### Risk: doubling orchestration logic

Mitigation:
- keep session lifecycle in Shoal
- keep decomposition logic in Pisces
- do not rebuild session substrate semantics inside Pisces

### Risk: user confusion over two parallelism models

Mitigation:
- document and surface the distinction repeatedly in help text and docs

## Definition of done

This migration is successful when:

- Pisces still uses Shoal for inter-session orchestration
- `/team` no longer depends on private Shoal schema for correctness
- direct Shoal DB reads, if any remain, are passive and replaceable
- users understand when to use `task` versus Shoal-backed `/team`
