# Lobster Party Integration

Lobster Party is the remote gRPC-based agent runtime system for Lobster environments. It enables Shoal to orchestrate and monitor agents running on remote, specialized infrastructure (Lobster runtimes) just as easily as local tmux sessions.

## Architecture overview

Instead of executing agents locally, Shoal communicates with a centralized "Lobster orchestrator" which manages the lifecycle of remote Lobster runtimes. This architecture allows for horizontally scalable agent fleets.

### Shoal Integration

Shoal integrates with Lobster Party through several key components:

1. **Lobster Client (`src/shoal/core/lobster_client.py`)**: The primary interface for communicating with the Lobster orchestrator. It manages the gRPC connection lifecycle.
2. **gRPC Stubs (`lobster_loop_pb2`)**: The generated protocol buffer code that defines the API boundary between Shoal and the Lobster Party ecosystem.
3. **Lobster Runtime Provider (`src/shoal/integrations/lobster/`)**: This implements Shoal's runtime interface for Lobster runtimes. Unlike `tmux` runtimes where Shoal directly manages process execution, the `lobster` runtime provider delegates lifecycle management to the remote Lobster orchestrator via `grpc://` endpoints.

### Conversation Synchronization

Lobster Party uses a unique format for storing and syncing conversation history.

Conversations are stored in **QMD format** (a specialized Markdown dialect) and are organized into **weekly-bucketed files** (e.g., `2024-W42.qmd`). By default, these are synced to and from `~/conversations` on the local machine. This allows for rich, human-readable history that is easily version-controlled and searchable, while remaining efficiently structured for agent context windows.