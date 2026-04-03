# Lobster Party Quick Reference

## Configuration

Configure Shoal to connect to one or more Lobster runtimes by adding the `[lobster]` block in
your Shoal configuration file (`~/.config/shoal/config.toml`):

```toml
[lobster]
known_lobsters = { "prod" = "grpc://localhost:50051", "staging" = "grpc://..." }
grpc_addr = ""  # fallback for single-Lobster setups
employee_id = "default"
```

## Commands

### Discovery

Fetch a Lobster's AgentCard to verify connectivity:

```bash
shoal lobster ping <lobster-id>
shoal lobster ping prod --json
```

### Send a message

```bash
shoal lobster send <lobster-id> "your message"
shoal lobster send prod "summarise recent activity" --task-id my-task-1
```

### List tasks

```bash
shoal lobster tasks <lobster-id>
shoal lobster tasks prod --status working
shoal lobster tasks prod --context ctx-abc123
```

## Conversation synchronisation

Import QMD conversation history from a Lobster into the Shoal journal:

```bash
shoal handoff --sync-claw ~/conversations
```

Conversations are stored in **QMD format** (Markdown + JSON sidecar) organised into
weekly-bucketed directories (e.g., `2025-W03/`). They are imported into the session journal
and indexed by `ConversationIndex` for fast handoff retrieval.

## Implementation notes

- **`LobsterClient` (`src/shoal/core/lobster_client.py`)**: Async gRPC client wrapping
  `LobsterLoopStub`. Manages channel lifecycle with `async with LobsterClient(...) as client:`.
- **`LobsterRuntimeState`**: Session runtime state model for Lobster sessions
  (`lobster_id`, `endpoint`, `employee_id`).
- **A2A bridge (`src/shoal/integrations/lobster/a2a_bridge.py`)**: Agent-to-agent protocol
  bridge; exposes `get_agent_card`, `send_message`, `list_tasks` via `LobsterA2AClient`.
- **State streaming**: The client subscribes to real-time events from the Lobster runtime
  using server-streaming RPCs to keep local Shoal state synchronised without polling.