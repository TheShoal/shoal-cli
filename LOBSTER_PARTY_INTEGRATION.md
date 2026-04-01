# Shoal + Lobster Party Integration Specifications

A document detailing the requirements for combining Shoal agents together with Lobster Party features.

## Workstream 1: AgentCard & A2A Bridge
**Target Files:**
- `src/shoal/core/proto/a2a_claw.proto` (and generated pb2/grpc.py models)
- `src/shoal/core/proto/a2a_core.proto` 
- `src/shoal/core/claw_client.py`
- *Net new:* `src/shoal/integrations/lobster/a2a_bridge.py`

**Change:**
- Implement data models and server bridge translations for `AgentCard` and `mcp-lobster-a2a`, exposing the appropriate GetAgentCard and A2A connectivity over gRPC using `claw_client.py`.

## Workstream 2: Delegation Wrapper
**Target Files:**
- `src/shoal/core/proto/delegation.proto` (and generated pb2/grpc.py models)
- *Net new:* `src/shoal/integrations/lobster/delegation_wrapper.py`
- `src/shoal/cli/session.py`

**Change:**
- Implement the Delegation Wrapper over `lobster.party.delegation.v1.DelegationService` that replaces environment variable injection.
- Ensure API keys are shielded from the agent sandbox. Provide proxy/injection stubs in `session.py` without overlapping with other streams.

## Workstream 3: QMD Sync, Remote Connect & Handoff
**Target Files:**
- `src/shoal/core/claw_conversations.py`
- `src/shoal/cli/handoff.py`
- `src/shoal/cli/remote.py`
- *Net new:* `src/shoal/integrations/lobster/clawplexer_sync.py`

**Change:**
- Implement the QMD Sync loop integrating `ClawTurn` and mapping Claw records to journal entries via `claw_conversations.py`.
- Connect the handoff and remote command pipelines to the new `clawplexer_sync.py` to enable Git Workspace Handoff over Remote Claws.

## Avoid Conflicts
- The Typer routing logic in `src/shoal/cli/remote.py` and `src/shoal/cli/handoff.py` is reserved exclusively for **Workstream 3**.
- `session.py` modifications are strictly scoped to **Workstream 2** environment configuration.
- `claw_client.py` modifications are strictly scoped to **Workstream 1** AgentCard endpoints.
