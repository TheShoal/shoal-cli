# Shoal Troubleshooting Guide

This guide covers common issues you might encounter while using Shoal and provides steps to resolve them.

## 1. Using Debug Logging

If you encounter an error or unexpected behavior, the first step is to enable verbose logging.

```fish
shoal --debug <command>
```

This will output DEBUG-level logs to stderr, which can help identify where a process is failing or what commands are being executed.

## 2. Watcher Issues

### Symptom: Session status doesn't update (remains 'running' or 'idle' incorrectly)

**Causes:**
- Watcher daemon is not running.
- Pattern matching in tool config doesn't match the output in the tmux pane.

**Solutions:**
1. Check if the watcher is running: `shoal watcher status`
2. Start it if needed: `shoal watcher start`
3. Verify tool configuration in `~/.config/shoal/tools/<tool>.toml`. Ensure the `busy_patterns`, `waiting_patterns`, and `error_patterns` match the actual text output by your tool.
4. Run `shoal logs <session>` to see what the watcher is seeing in the pane.

## 3. Database Issues

### Symptom: `sqlite3.OperationalError: database is locked`

**Causes:**
- Multiple processes trying to write to the database simultaneously without WAL mode enabled.
- A stale process holding a connection.

**Solutions:**
- Shoal uses WAL (Write-Ahead Logging) mode by default to prevent this. If you see this error, it may mean a process hung while holding a transaction.
- Check for Shoal processes: `ps aux | grep shoal`
- Ensure you are running the latest version which handles the DB lifecycle correctly.

## 4. Tmux Issues

### Symptom: `Tmux session '_...' not found`

**Causes:**
- The tmux session was killed manually outside of Shoal.
- The terminal multiplexer server crashed.

**Solutions:**
1. Run `shoal ls` to see if the session is marked as a **ghost**.
2. Use `shoal prune` to remove stale records for dead tmux sessions.
3. Use `shoal kill <session>` to clean up the DB record.

### Symptom: Session status does not change even though tmux output changed

**Cause:**
- The active pane is no longer running the tool command configured for that session.

**Solution:**
1. Run `shoal info <session>` and check the session's configured tool.
2. In tmux, restart the matching tool command in that session pane (for example, `opencode`).
3. Run `shoal status` again. The tmux status segment always stays visible, even when all counts are zero.

## 5. MCP Connection Problems

### Symptom: `Attached MCP '...' to session '...' but tool can't connect`

**Causes:**
- The MCP server process died.
- The tool is not configured to use the proxy.
- Stale sockets/PIDs from a previous crash.

**Solutions:**
1. Run deep diagnostics: `shoal mcp doctor`
   - Shows PID liveness, protocol health, tool count, and latency per server
2. Check MCP pool status: `shoal mcp status`
3. Restart the MCP server: `shoal mcp stop <name> && shoal mcp start <name>`
4. Clean stale sockets: `shoal init` (auto-reconciles on startup)
5. Verify the tool's MCP configuration. For Claude Code:
   ```fish
   claude mcp add <name> -- shoal-mcp-proxy <name>
   ```
6. Check server logs: `shoal mcp logs <name>`

## 6. Remote Session Issues

### Symptom: `shoal remote ls` fails or times out

**Causes:**
- SSH tunnel is not connected.
- The remote Shoal API server is not running.
- Port conflict or firewall blocking the tunnel.

**Solutions:**
1. Connect the tunnel: `shoal remote connect <host>`
2. Check tunnel status: `shoal remote status <host>`
3. Verify the remote API is running: `ssh <host> "shoal serve"` in a separate terminal
4. If the tunnel disconnects, reconnect: `shoal remote disconnect <host> && shoal remote connect <host>`
5. Configure remote hosts in `~/.config/shoal/config.toml`:
   ```toml
   [remote.myserver]
   host = "user@myserver.example.com"
   port = 22
   ```

## 7. Diagnostics

### Using `shoal diag`

The diagnostics command checks all core subsystems:

```fish
shoal diag          # Rich-formatted output
shoal diag --json   # Machine-readable JSON
```

Checks performed:
- **DB**: SQLite connectivity and WAL mode
- **Watcher**: Background status watcher PID liveness
- **Tmux**: tmux server reachability

### Structured Logging

For deeper debugging, use the logging flags:

```fish
shoal --log-level DEBUG <command>    # Verbose logs to stderr
shoal --log-file /tmp/shoal.log <command>  # Log to file
shoal --json-logs <command>          # JSON-lines format (for log aggregators)
```

These flags work with any command and can be combined.

## 8. Neovim Integration

### Symptom: `nvr not found` or `No nvim socket`

**Causes:**
- `neovim-remote` is not installed.
- Neovim is not running in the session or was started without a socket.

**Solutions:**
1. Install `neovim-remote`: `pip install neovim-remote`
2. Ensure you are using a tool that launches Neovim correctly within the Shoal environment.
3. Check `shoal info <session>` to see if an `nvim_socket` path is assigned.
