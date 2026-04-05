# ADR: Keep Lobster/A2A federation out of Shoal core

**Date**: 2026-04-05  
**Status**: Accepted

## Context

Shoal's core value is local orchestration: worktree-backed sessions, tmux runtime management, SQLite state,
journals, and MCP control-plane access.

A Track B audit of the current repo found that the old Lobster/A2A integration is no longer part of the live
core:

- the runtime provider registry only wires `tmux` today
- packaging exposes `mcp` as an optional extra, but no `lobster` extra
- user-facing Lobster CLI docs had drifted and were removed during the audit
- the remaining durable conversation artifact format (`qmd.py`) is still active and is used by conversation
  indexing and summarization flows
- session approval flows remain active core functionality through the Agent Bus and MCP action tools

This leaves a clear architectural boundary question: if remote federation or Lobster-style agent-to-agent
transport returns, should it live inside Shoal core again?

## Decision

Shoal core will remain focused on local orchestration and generic control-plane primitives.

Remote federation concerns, including any future Lobster or A2A transport, should live outside core as a
separate plugin or package, tentatively `shoal-lobster`.

## What stays in core

These capabilities are part of Shoal's core architecture and should remain in-tree:

- session lifecycle orchestration
- worktree management and branch isolation
- tmux runtime provider support
- SQLite state, journals, and workflow lineage
- MCP server and control-plane tools
- session action approval flows (`request_session_action`, `list_pending_session_actions`,
  `approve_session_action`, `deny_session_action`)
- QMD conversation artifacts and indexing
- generic extension seams such as the runtime-provider interface

## What moves out of core

These capabilities should not be reintroduced into the main Shoal package:

- Lobster-specific or A2A-specific transport clients
- gRPC or protocol-generated stubs for remote agent communication
- Lobster-specific CLI groups and config sections
- optional dependency bundles dedicated to remote federation
- remote agent discovery models that exist only for a federation transport
- integration tests that require live remote federation endpoints unless they live with that plugin

## Rationale

### 1. Preserve Shoal's system boundary

Shoal already has a strong layering model: it owns orchestration, while lower or adjacent layers own execution,
transport, or sandboxing. Remote federation is a different concern from local session control.

### 2. Reduce dormant surface area

Previous Lobster/A2A work added code, packaging, tests, and docs that were not part of the default local user
path. Keeping that concern outside core avoids carrying dead or lightly exercised surface area.

### 3. Keep core verification predictable

Shoal's core test and docs pipeline should validate features that ship by default. Remote federation typically
adds optional dependencies, external endpoint assumptions, and integration-only failure modes.

### 4. Preserve useful generic primitives

The audit confirmed that not everything touched by the old integration is Lobster-specific. Session approvals
and QMD artifacts are still broadly useful and should stay in core because they support local orchestration,
auditing, and agent workflows independent of any specific remote protocol.

## Consequences

### Positive

- smaller and clearer core surface area
- fewer stale docs and unused optional dependencies
- cleaner ownership boundary for future federation work
- easier CI expectations for the default package

### Negative

- a future federation integration will need its own package, docs, and release discipline
- cross-package compatibility will need to be managed at the seam level rather than by direct in-core coupling

## Plugin contract expectations

If `shoal-lobster` is built later, it should:

- depend on Shoal's public seams rather than private internals
- integrate through MCP and/or the runtime-provider boundary
- own its transport models, config, and tests
- document its own auth, endpoint, and operational expectations
- keep Shoal core free of plugin-only generated protocol code

## Migration guidance

When evaluating future federation work, prefer this order:

1. express the workflow with Shoal MCP tools first
2. add plugin-local transport/client code second
3. promote new abstractions into Shoal core only if they are protocol-agnostic and clearly useful without Lobster

## Current repository evidence

At the time of this decision:

- runtime providers are tmux-only in `src/shoal/services/runtime_provider.py`
- optional dependencies list no Lobster extra in `pyproject.toml`
- QMD indexing remains active in `src/shoal/core/conversation_index.py` and `src/shoal/core/qmd.py`
- action approval tools remain active in `src/shoal/services/mcp_shoal_server.py`

That evidence supports keeping the remaining generic primitives in core while treating Lobster/A2A federation as
an external concern.