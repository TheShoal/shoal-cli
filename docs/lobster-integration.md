# Lobster Party Integration

Lobster Party is the remote gRPC-based agent runtime system for Claw environments. It enables Shoal to orchestrate and monitor agents running on remote, specialized infrastructure (Claws) just as easily as local tmux sessions.

## Architecture overview

Instead of executing agents locally, Shoal communicates with a centralized "Clawplexer" which manages the lifecycle of remote Claw runtimes. This architecture allows for horizontally scalable agent fleets.

### Shoal Integration

Shoal integrates with Lobster Party through several key components:

1. **Claw Client (`src/shoal/core/claw_client.py`)**: The primary interface for communicating with the Clawplexer. It manages the gRPC connection lifecycle.
2. **gRPC Stubs (`lobster_loop_pb2`)**: The generated protocol buffer code that defines the API boundary between Shoal and the Lobster Party ecosystem.
3. **Claw Runtime Provider (`services/runtime_providers/claw.py`)**: This implements Shoal's runtime interface for Claws. Unlike `tmux` runtimes where Shoal directly manages process execution, the `claw` runtime provider delegates lifecycle management to the remote Clawplexer via `grpc://` endpoints.

### Conversation Synchronization

Lobster Party uses a unique format for storing and syncing conversation history.

Conversations are stored in **QMD format** (a specialized Markdown dialect) and are organized into **weekly-bucketed files** (e.g., `2024-W42.qmd`). By default, these are synced to and from `~/conversations` on the local machine. This allows for rich, human-readable history that is easily version-controlled and searchable, while remaining efficiently structured for agent context windows.