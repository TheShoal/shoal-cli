# Lobster Party Quick Reference

## Configuration

Configure Shoal to connect to multiple Clawplexers by adding the `[runtime.claw]` block in your Shoal configuration file (`~/.config/shoal/config.toml`):

```toml
[runtime.claw]
endpoints={"claw-test": "grpc://localhost:50051", "prod-us-east": "grpc://..."}
```

## Commands

### Session Management

Start a new Shoal session using the `claw` runtime instead of `tmux`:

```bash
# Note: The `claw-id` must match a configured endpoint.
shoal new my-claw-session --kind claw --claw-id claw-test
```

### Synchronization

Synchronize QMD conversation history from the Clawplexer to your local filesystem:

```bash
# By default, this synchronizes to ~/conversations
shoal session claw-sync --dir ~/conversations
```

## Implementation Notes

*   **`LobsterLoopStub`**: The core gRPC interface defined in `lobster_loop_pb2_grpc.py`. It provides methods for launching agents, reading process stdout/stderr streams, and subscribing to status updates.
*   **State Streaming**: The Claw client subscribes to real-time events from the Clawplexer using server-streaming RPCs to keep local Shoal state synchronized with remote agent status without aggressive polling.