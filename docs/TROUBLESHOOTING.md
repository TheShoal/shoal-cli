# Shoal Troubleshooting Guide

This guide covers common issues you might encounter while using Shoal and provides steps to resolve them.

## 1. Using Debug Logging

If you encounter an error or unexpected behavior, the first step is to enable verbose logging.

```bash
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
- `socat` is not installed.
- The MCP server process died.
- The tool is not configured to use the proxy socket.

**Solutions:**
1. Ensure `socat` is installed: `shoal check`
2. Check MCP pool status: `shoal mcp status`
3. Restart the MCP server: `shoal mcp stop <name> && shoal mcp start <name>`
4. Verify the tool's MCP configuration. For Claude Code, it should look like:
   ```bash
   claude mcp add <name> -- socat STDIO UNIX-CONNECT:~/.local/state/shoal/mcp-pool/sockets/<name>.sock
   ```

## 6. Neovim Integration

### Symptom: `nvr not found` or `No nvim socket`

**Causes:**
- `neovim-remote` is not installed.
- Neovim is not running in the session or was started without a socket.

**Solutions:**
1. Install `neovim-remote`: `pip install neovim-remote`
2. Ensure you are using a tool that launches Neovim correctly within the Shoal environment.
3. Check `shoal info <session>` to see if an `nvim_socket` path is assigned.
