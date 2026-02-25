# Transport Evaluation Spike: UDS vs HTTP

**Date**: 2026-02-23
**Version**: v0.15.0 Phase 3
**Status**: Complete

## Summary

Evaluated whether FastMCP transports can replace Shoal's custom byte bridge (`mcp_pool.py` + `mcp_proxy.py`). Benchmarked stdio (direct spawn) and HTTP (streamable-http) transport paths for `shoal-orchestrator`.

**Recommendation**: Go — adopt HTTP transport for `shoal-orchestrator` alongside the existing byte bridge. Do not replace the byte bridge for third-party stdio MCP servers.

---

## 1. UDS Transport Investigation

**Finding**: FastMCP 3.0.2 does **not** provide native Unix Domain Socket (UDS) transport.

Available transports:
- `StdioTransport` — spawns subprocess, communicates via stdin/stdout
- `StreamableHttpTransport` — HTTP-based MCP protocol
- `SSETransport` — Server-Sent Events over HTTP
- No UDS transport exists or is planned upstream

This means FastMCP cannot directly replace the asyncio `start_unix_server()` pattern used in `mcp_pool.py`.

## 2. Benchmark Results

**Environment**: Python 3.13.11, Linux 6.18, FastMCP 3.0.2

| Metric | stdio (direct) | HTTP (streamable) |
|--------|---------------|-------------------|
| **Startup** | ~8,800ms (process spawn) | ~65ms (connect to running server) |
| **Call p50** | 19.6ms | 53.1ms |
| **Call p95** | 40.4ms | 83.0ms |
| **Call p99** | 70.8ms | 179.8ms |
| **Call mean** | 21.3ms | 57.4ms |
| **Concurrent mean (5 clients)** | n/a | 305.0ms |
| **Server RSS** | n/a (ephemeral process) | ~90 MB |

**Key observations**:

1. **Startup**: HTTP wins decisively. Stdio spawns a new Python process per connection (~2-9 seconds depending on system load). HTTP connects to a running server in ~65ms.

2. **Per-call latency**: Stdio is ~2.7x faster per call (21ms vs 57ms). This is expected — stdio is direct in-process communication vs HTTP request/response cycle.

3. **Memory**: HTTP server holds ~90 MB RSS (Python process + uvicorn + FastMCP). The byte bridge pool process is comparable but spawns ephemeral children.

4. **Concurrency**: HTTP handles 5 concurrent clients naturally through the ASGI server. The stdio/pool path spawns a separate process per client connection.

### UDS Pool Path

The UDS pool path (proxy → socket → spawned process) could not be benchmarked due to a Python 3.13 compatibility issue in `mcp_proxy.py`. The `StreamWriter` constructed with `asyncio.BaseProtocol` for stdout bridging fails because `BaseProtocol` lacks `_drain_helper` on Python 3.13. This is a pre-existing maintenance burden that supports the case for adopting FastMCP transports.

## 3. Architecture Implications

### What can move to HTTP

**`shoal-orchestrator`** (the Shoal MCP server) is a FastMCP-native server. It can run in HTTP mode with zero changes to its tool implementations — just `mcp.run(transport="streamable-http", port=PORT)`.

Benefits:
- **Remote sessions (v0.16.0)**: HTTP tunnels over SSH trivially. An HTTP server on the remote machine can be accessed via `ssh -L PORT:localhost:PORT`.
- **Persistent server**: No per-connection process spawning. One server handles all clients.
- **Protocol awareness**: Full MCP protocol with error handling, tool introspection, health checks.
- **No proxy needed**: Clients connect directly via HTTP, eliminating the stdio→UDS bridge.

### What stays on the byte bridge

**Third-party MCP servers** (memory, filesystem, github, fetch) are stdio-based CLI tools (`npx -y @modelcontextprotocol/server-memory`). They don't speak HTTP natively. The pool's per-connection spawning pattern remains necessary for these.

The byte bridge (`mcp_pool.py` + `mcp_proxy.py`) should be maintained for third-party servers but is not needed for `shoal-orchestrator`.

### Hybrid architecture

```
shoal-orchestrator:  Agent → StreamableHttpTransport → HTTP server (port 8390)
third-party servers: Agent → shoal-mcp-proxy → UDS pool → spawned process
```

This is a clean split: Shoal's own server uses modern HTTP transport while third-party stdio servers continue through the existing pool.

## 4. Proxy Maintenance Issue

The `mcp_proxy.py` stdio-to-socket bridge constructs an `asyncio.StreamWriter` with `asyncio.BaseProtocol` for stdout bridging (line 52-60). On Python 3.13, `StreamWriter.drain()` expects the protocol to have a `_drain_helper` method, which `BaseProtocol` does not provide.

This is fixable (use `StreamReaderProtocol` instead), but it highlights the maintenance cost of the custom byte bridge — compatibility with each Python release requires manual attention.

## 5. Decision

### Go: HTTP for shoal-orchestrator

- Add HTTP as the **default transport** for `shoal-orchestrator` in a future release
- Keep the byte bridge for third-party stdio MCP servers
- The ~35ms per-call overhead is acceptable for orchestration operations (session management is not latency-critical)
- HTTP directly enables v0.16.0 remote sessions via SSH tunneling

### Follow-up work

1. **Production HTTP server**: Add proper `shoal mcp start shoal-orchestrator --http` CLI support
2. **Fix proxy Python 3.13 bug**: Replace `BaseProtocol` with `StreamReaderProtocol` in `mcp_proxy.py`
3. **Remote sessions**: Use HTTP transport as the foundation for `shoal remote` commands
4. **Server composition**: Evaluate FastMCP `mount()` for per-session MCP aggregation gateway

## 6. How to reproduce

```bash
uv run python benchmarks/transport_spike.py --calls 50 --concurrency 5
```
