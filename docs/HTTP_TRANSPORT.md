# HTTP Transport for MCP Servers

Shoal's MCP server (`shoal-orchestrator`) supports **HTTP transport** via FastMCP's streamable-http mode. This is the default transport for the orchestrator, replacing the Unix socket byte bridge with a standard HTTP endpoint.

---

## Quick Start

### Start the orchestrator (HTTP is the default)

```bash
shoal mcp start shoal-orchestrator
```

This automatically starts the server in HTTP mode on port 8390. No extra flags needed — Shoal's registry knows `shoal-orchestrator` defaults to HTTP.

### Verify it's running

```bash
shoal mcp doctor
```

The doctor probes HTTP servers using FastMCP's `StreamableHttpTransport` and reports protocol, tool count, version, and latency:

```
┌────────────────────┬──────────┬──────┬─────────┬─────────┐
│ NAME               │ PROTOCOL │ TOOLS│ VERSION │ LATENCY │
├────────────────────┼──────────┼──────┼─────────┼─────────┤
│ shoal-orchestrator │ http     │ 8    │ 0.17.0  │ 12ms    │
└────────────────────┴──────────┴──────┴─────────┴─────────┘
```

---

## How It Works

### Server-side

The `shoal-mcp-server` binary supports two transport modes:

| Mode | Flag | Default Port | Protocol |
|------|------|-------------|----------|
| stdio | *(none)* | — | JSON-RPC over stdin/stdout |
| HTTP | `--http` | 8390 | FastMCP streamable-http |

```bash
# Stdio mode (for direct MCP client connections)
shoal-mcp-server

# HTTP mode on default port
shoal-mcp-server --http

# HTTP mode on custom port
shoal-mcp-server --http 8391
```

In HTTP mode, the server listens at `http://localhost:<port>/mcp/`.

### Transport auto-detection

When you run `shoal mcp start <name>`, Shoal checks the transport for that server:

1. User registry (`~/.config/shoal/mcp-servers.toml`) — explicit `transport` field
2. Built-in defaults — `shoal-orchestrator` defaults to `"http"`
3. Fallback — all other servers default to `"socket"`

The `shoal-orchestrator` is the only built-in server that defaults to HTTP. All other servers (`memory`, `filesystem`, `github`, `fetch`) continue using Unix socket transport.

---

## Registry Configuration

### View the registry

```bash
shoal mcp registry
```

Shows all known servers with their transport mode:

```
┌────────────────────┬──────────┬───────────┬────────────────────────────────────────┐
│ NAME               │ SOURCE   │ TRANSPORT │ COMMAND                                │
├────────────────────┼──────────┼───────────┼────────────────────────────────────────┤
│ memory             │ built-in │ socket    │ npx -y @modelcontextprotocol/server-…  │
│ shoal-orchestrator │ built-in │ http      │ shoal-mcp-server                       │
└────────────────────┴──────────┴───────────┴────────────────────────────────────────┘
```

### Override transport in user config

```toml
# ~/.config/shoal/mcp-servers.toml

# Force a server to use HTTP
[my-custom-server]
command = "my-mcp-server"
transport = "http"

# Or force socket for the orchestrator
[shoal-orchestrator]
command = "shoal-mcp-server"
transport = "socket"
```

---

## Tool Integration

AI tools that support MCP over HTTP can connect directly to the orchestrator endpoint:

```
http://localhost:8390/mcp/
```

For tools that only support stdio MCP, use `shoal-mcp-proxy` to bridge:

```bash
shoal-mcp-proxy shoal-orchestrator
```

The proxy detects the server's transport mode and connects via HTTP or socket accordingly.

---

## Diagnostics

### Health check

```bash
shoal mcp doctor
```

For HTTP servers, the doctor:
1. Reads the port from `~/.local/share/shoal/mcp-pool/ports/<name>.port`
2. Connects via `FastMCP Client` with `StreamableHttpTransport`
3. Reports server name, version, tool count, and round-trip latency

### Clean up stale servers

```bash
shoal mcp doctor --cleanup
```

Removes stale PID and port files for servers that are no longer running.

### View server logs

```bash
shoal mcp logs shoal-orchestrator
```

---

## Why HTTP?

The [transport evaluation spike](transport-spike.md) compared Unix socket byte bridging with FastMCP HTTP transport:

- **Compatibility**: HTTP works with remote sessions via SSH tunnels — no Unix socket forwarding needed
- **Tooling**: Standard HTTP endpoints are easier to debug (`curl`, browser, etc.)
- **FastMCP native**: Uses FastMCP's built-in streamable-http transport with no custom bridging code

Socket transport remains the default for stateless MCP servers (`memory`, `filesystem`, etc.) where the byte bridge overhead is minimal and no remote access is needed.

---

## Further Reading

- [Transport Spike](transport-spike.md) — Benchmark data comparing UDS vs HTTP
- [Robo Supervisor Guide](ROBO_GUIDE.md) — Using the orchestrator with robo workflows
- [Shoal Overview](index.md) — Overview of Shoal
