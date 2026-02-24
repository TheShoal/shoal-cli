# Server Composition Gateway Spike: FastMCP `mount()`

**Date**: 2026-02-24
**Version**: v0.18.0 Phase 2
**Status**: Complete

## Summary

Evaluated FastMCP 3.x `mount()` for per-session MCP server aggregation — a single gateway endpoint that composes `shoal-orchestrator` with each session's configured MCP servers (memory, github, filesystem, etc.).

**Recommendation**: No-go for now. The composition gateway adds process overhead and latency without solving a problem Shoal actually has today. The existing pool + proxy architecture is simpler and already works. Revisit when agent clients support multi-server configs natively or when Shoal needs cross-server tool orchestration.

---

## 1. What `mount()` Does in FastMCP 3.x

FastMCP 3.x provides `mount()` for composing multiple MCP servers into a single unified endpoint. A parent server mounts child servers, exposing all their tools, resources, and prompts through one connection.

**API**:

```python
def mount(
    self,
    server: FastMCP,
    namespace: str | None = None,      # prefix for tool names
    tool_names: dict[str, str] | None = None,  # custom name overrides
) -> None
```

**Namespacing**: When `namespace="memory"` is provided, tool `create` becomes `memory_create`. An underscore separator is auto-inserted — never include a trailing underscore in the namespace string (known gotcha, [GitHub #1308](https://github.com/jlowin/fastmcp/issues/1308)).

**Dynamic link**: Unlike `import_server()` (one-time static copy), `mount()` creates a live connection — tools added to the child after mounting are immediately accessible through the parent.

**Remote servers via `create_proxy()`**: Third-party MCP servers can be mounted by first wrapping them in a proxy:

```python
from fastmcp import FastMCP
from fastmcp.server import create_proxy

gateway = FastMCP("Session Gateway")

# Mount shoal-orchestrator in-process (zero overhead)
gateway.mount(shoal_mcp, namespace="shoal")

# Mount third-party stdio server via proxy
config = {"mcpServers": {"default": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-memory"]
}}}
gateway.mount(create_proxy(config), namespace="memory")
```

**Supported transports**: stdio, HTTP (streamable-http), SSE, in-memory. **No Unix domain socket transport** — FastMCP cannot connect to Shoal's existing UDS pool sockets.

## 2. Architecture Options

### Option A: Gateway-per-session

Each session gets its own gateway process that mounts the session's configured MCP servers.

```
Session "feature-ui" (mcp: [memory, github])
  └─ Gateway (HTTP :8391)
       ├─ shoal-orchestrator (in-process, namespace="shoal")
       ├─ memory (stdio proxy, namespace="memory")
       └─ github (stdio proxy, namespace="github")

Session "feature-api" (mcp: [memory])
  └─ Gateway (HTTP :8392)
       ├─ shoal-orchestrator (in-process, namespace="shoal")
       └─ memory (stdio proxy, namespace="memory")
```

| Aspect | Assessment |
|--------|------------|
| Per-session tool surface | Each agent sees only its configured servers |
| Process overhead | 1 gateway process + N proxied subprocesses per session |
| Memory | ~90 MB per gateway (Python + uvicorn + FastMCP) |
| Port allocation | Needs dynamic port management per session |
| Lifecycle | Must start/stop gateway with session create/kill |

### Option B: Shared gateway

Single gateway mounts all registered MCP servers. All sessions connect to the same endpoint.

```
Shared Gateway (HTTP :8390)
  ├─ shoal-orchestrator (in-process, namespace="shoal")
  ├─ memory (stdio proxy, namespace="memory")
  ├─ github (stdio proxy, namespace="github")
  └─ filesystem (stdio proxy, namespace="fs")
```

| Aspect | Assessment |
|--------|------------|
| Per-session tool surface | All agents see all servers (no session-level filtering) |
| Process overhead | 1 gateway + N proxied subprocesses (shared) |
| Memory | ~90 MB total |
| Port allocation | Single well-known port |
| Lifecycle | Starts once, survives session churn |

**Which fits Shoal?** Neither is a clear win. Option A is architecturally cleaner (session isolation) but expensive — 90 MB per gateway is steep when sessions already have their own tmux panes, worktrees, and agent processes. Option B is simpler but violates Shoal's per-session MCP configuration model (sessions declare which MCP servers they need).

## 3. Integration with Existing Architecture

### Current flow (pool + proxy)

```
Agent → shoal-mcp-proxy (stdio→UDS bridge) → mcp_pool.py (UDS listener) → spawned MCP process
```

- `mcp_pool.py`: asyncio Unix socket listener per MCP type. Each client connection spawns a fresh MCP command and bridges I/O.
- `mcp_proxy.py`: stdio-to-UDS bridge binary. Agent's MCP client config points `command` to `shoal-mcp-proxy <name>`.
- `shoal-orchestrator`: Already a FastMCP server, runs via HTTP (port 8390) or stdio.

### What a gateway would change

The gateway would **replace** the proxy + pool path for mounted servers, using `create_proxy()` to manage subprocess spawning instead of `mcp_pool.py`:

```
Agent → Gateway (HTTP) → create_proxy() → spawned MCP process
```

**Integration points**:

1. **`shoal-orchestrator`**: Can be mounted in-process (`gateway.mount(mcp, namespace="shoal")`). This is the cleanest part — zero overhead, no serialization.
2. **Third-party stdio servers**: Must use `create_proxy()` with MCPConfig dicts. This **duplicates** what `mcp_pool.py` already does (spawn + bridge) but through FastMCP's proxy layer instead of raw asyncio.
3. **Session lifecycle**: `create_session_lifecycle()` would need to start a gateway per session (Option A) or register with a shared gateway (Option B). Either requires new lifecycle code.
4. **Agent config**: Agents currently get per-server entries in their MCP config. A gateway collapses these to one endpoint. This works if the agent client supports HTTP transport — Claude Code and OpenCode do.

### What stays unchanged

- Tool configs (`~/.config/shoal/tools/*.toml`) — unchanged
- Session templates — still declare `mcp: [memory, github]`
- `mcp-servers.toml` registry — still defines available servers
- Status detection, journals, lifecycle hooks — all orthogonal

## 4. Known Limitations

### No UDS transport

FastMCP does not support Unix domain sockets. The gateway cannot connect to Shoal's existing pool sockets. A gateway must manage its own subprocess spawning via `create_proxy()`, meaning the pool and gateway are parallel systems, not layered.

### No shared state in spawn-per-connection model

`create_proxy()` with stdio targets spawns a fresh process per client session by default. This matches Shoal's current pool behavior — MCP memory written by one agent is not readable by another. A connected `Client` object can share state, but FastMCP warns about "context mixing in concurrent scenarios."

### Proxy latency overhead

| Operation | Local (in-process) | Proxied (stdio subprocess) |
|-----------|-------------------|---------------------------|
| `list_tools()` | 1-2ms | 300-400ms |
| `call_tool()` | 1-2ms | 200-500ms |

This compounds across mounted servers. A gateway mounting 3 proxied servers adds 300-400ms to tool discovery. Not catastrophic for AI agents (they call tools infrequently relative to thinking time), but measurable.

### Tool namespace collisions

Without namespacing, the most recently mounted server wins on name conflicts. With namespacing, tool names become longer (`memory_create` vs `create`), consuming more of the agent's context window. Minor issue in practice.

### Tool count overload

Mounting many servers exposes many tools to the LLM. Claude Code and OpenCode handle this well today, but it's a known concern in the MCP ecosystem. The [fastmcp-gateway](https://github.com/jlowin/fastmcp) project addresses this with "progressive discovery" meta-tools.

### Namespace gotcha

The auto-inserted underscore separator means `namespace="f1_"` produces `f1__add` (double underscore). Always omit trailing underscores.

## 5. Decision

### No-go (defer to backlog)

| Factor | Assessment |
|--------|------------|
| **Problem severity** | Low — agents already connect to multiple MCP servers via per-server config entries. No user pain reported. |
| **Architecture fit** | Poor — duplicates pool subprocess management. No UDS support means gateway and pool are parallel systems. |
| **Complexity** | High — per-session gateway requires lifecycle management, port allocation, memory overhead. Shared gateway breaks session-level MCP isolation. |
| **Benefit** | Marginal — single endpoint per session vs N endpoints. Agents handle multiple endpoints fine today. |
| **Latency** | 300-400ms proxy overhead per mounted server, compounding. Acceptable but not free. |
| **Dependency risk** | FastMCP 3.x is new (2026-02). `mount()` and `create_proxy()` APIs are stabilizing but have open issues (#1308, #2802). |

### Rationale

The composition gateway solves a problem Shoal doesn't have yet. Today's architecture — where each agent gets per-server MCP config entries pointing to the pool proxy — works correctly, is battle-tested, and adds no extra processes.

A gateway becomes valuable when:

1. **Cross-server orchestration** is needed (e.g., a tool that reads from memory and writes to github in one operation)
2. **Agent clients** stop supporting multi-server configs (unlikely — the trend is toward more MCP support)
3. **Robo supervisor** needs a unified tool surface across all session MCP servers (possible in Phase 4)

### Follow-up

- Move "Server Composition Gateway" from Phase 2 to backlog in ROADMAP.md
- Revisit if robo supervisor (Phase 4) needs unified cross-session MCP access
- Monitor FastMCP UDS transport support — if added, the gateway becomes cheaper to integrate
- Consider `import_server()` (static copy, no proxy overhead) if a lightweight variant is needed

## 6. References

- [FastMCP Server Composition](https://gofastmcp.com/servers/composition)
- [FastMCP Proxy Servers](https://gofastmcp.com/servers/proxy)
- [FastMCP Server API Reference](https://gofastmcp.com/python-sdk/fastmcp-server-server)
- [Introducing FastMCP 3.0](https://www.jlowin.dev/blog/fastmcp-3)
- [What's New in FastMCP 3.0](https://www.jlowin.dev/blog/fastmcp-3-whats-new)
- [GitHub #1308: prefix parameter namespace issue](https://github.com/jlowin/fastmcp/issues/1308)
- [Shoal Transport Spike (v0.15.0)](transport-spike.md) — prior art on FastMCP transport evaluation
