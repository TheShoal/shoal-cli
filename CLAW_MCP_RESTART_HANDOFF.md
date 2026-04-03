# Claw MCP Restart Handoff

## Context

The active `shoal-mcp-server` process appears stale with respect to Claw/gRPC support.

Evidence gathered in this repo:
- Active MCP server processes were launched as `uv run shoal-mcp-server`.
- A fresh repo interpreter reports `shoal.integrations.lobster.lobster_a2a.GRPC_AVAILABLE == True`.
- The live MCP tool path still returns a grpc-missing error for claw tools.

That combination strongly suggests the running MCP server needs to be restarted in a claw-enabled environment.

Module-mode restart is preferred based on `memory://root/memory_summary.md`, paired with the repo entrypoint at `src/shoal/services/mcp_shoal_server.py:1845`.

## Restart commands

Run these from the repo root:

```bash
cd /Users/ricardoroche/sanctum/opus/proprium/the-shoal/shoal-cli

# Optional: inspect current MCP server processes
ps -Ao pid,ppid,command | grep -E 'shoal-mcp-server' | grep -v grep

# Stop the current stdio MCP server(s)
pkill -f 'shoal-mcp-server'

# Start a fresh claw-enabled MCP server
uv run --extra claw python -m shoal.services.mcp_shoal_server
```

## If launched by config/supervisor

Update the command from:

```bash
uv run shoal-mcp-server
```

to:

```bash
uv run --extra claw python -m shoal.services.mcp_shoal_server
```

## Quick preflight check

Before or after restart, this should report that gRPC is available in a fresh interpreter:

```bash
cd /Users/ricardoroche/sanctum/opus/proprium/the-shoal/shoal-cli
.venv/bin/python - <<'PY'
from shoal.integrations.lobster import lobster_a2a
print('GRPC_AVAILABLE =', lobster_a2a.GRPC_AVAILABLE)
PY
```

Expected output:

```bash
GRPC_AVAILABLE = True
```

## Post-restart verification

Open a new ephemeral session that connects to the restarted MCP server and run:

1. `mcp_shoal_orchestrator_list_claws`
2. `mcp_shoal_orchestrator_claw_status` for one returned claw ID
3. If a live claw endpoint is configured:
   - `mcp_shoal_orchestrator_get_agent_card`
   - optionally `mcp_shoal_orchestrator_send_a_a_message`

## Expected result

After restart:
- The claw MCP tools should no longer fail with the import-gate error:

```text
grpcio is required for Claw client. Install with: pip install grpcio grpcio-tools
```

- If a claw is misconfigured or unreachable, errors should now be real config/network/RPC failures instead of grpc import failures.

## Current implementation status in repo

The local code changes needed for claw-aware API/UI behavior are already done and verified:
- Claw runtime provider can send messages and synthesize pane output
- dashboard session detail sends typed input correctly
- tmux-only approve actions are hidden for claw sessions
- API delete is claw-safe
- attach cleanly rejects non-tmux sessions

Validation already completed in this repo:

```bash
uv run ruff check src/shoal/services/runtime_providers/claw.py src/shoal/dashboard/context.py src/shoal/dashboard/routes.py src/shoal/api/server.py tests/test_api.py tests/test_dashboard_context.py
uv run mypy src/shoal/services/runtime_providers/claw.py src/shoal/dashboard/context.py src/shoal/dashboard/routes.py src/shoal/api/server.py
uv run pytest tests/test_api.py tests/test_dashboard_context.py -q
```

Result:
- `93 passed, 1 skipped`

## Resume point for next session

Once the MCP server has been restarted, continue with:
1. verify `claw_status` works through the live MCP connection
2. verify `get_agent_card` for a real configured claw
3. if available, send one harmless test message through `send_a_a_message`
4. report whether the live orchestrator path is fully claw-capable now
