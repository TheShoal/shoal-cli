# Shoal

**S.H.O.A.L. — SHell Orchestration for Agentic Loops**

AI agent orchestration for terminal-first workflows.

Shoal manages multiple AI coding agents (Claude Code, OpenCode, Gemini) running in parallel via tmux sessions, with git worktree integration, MCP server pooling, and a conductor (supervisory agent) mode.

## Prerequisites

- Python 3.12+
- [tmux](https://github.com/tmux/tmux)
- [git](https://git-scm.com/)
- [fzf](https://github.com/junegunn/fzf) (for interactive session picker and dashboard)
- [socat](http://www.dest-unreach.org/socat/) (for MCP server pooling)
- [gh](https://cli.github.com/) (optional, for `wt finish --pr`)
- [nvr](https://github.com/mhinz/neovim-remote) (optional, for neovim integration)

## Installation

```bash
# From source
git clone https://github.com/yourusername/shoal.git
cd shoal
pip install .

# Or with uv
uv pip install .

# Editable install for development
pip install -e ".[dev]"
```

After installation, three commands are available:

| Command | Purpose |
|---------|---------|
| `shoal` | Main CLI |
| `shoal-mcp-proxy` | MCP stdio-to-socket bridge (used in tool configs) |
| `shoal-status` | Tmux status bar segment (used in `tmux.conf`) |

## Configuration

Shoal reads TOML config files from `~/.config/shoal/`. Copy the examples to get started:

```bash
cp -r examples/config/ ~/.config/shoal/
```

### File layout

```
~/.config/shoal/
├── config.toml              # Global settings
├── tools/
│   ├── claude.toml          # Claude Code tool definition
│   ├── opencode.toml        # OpenCode tool definition
│   └── gemini.toml          # Gemini tool definition
└── conductor/
    └── default.toml         # Default conductor profile
```

### Tool config (`tools/<name>.toml`)

Each tool config defines how to launch the AI agent and how to detect its status from tmux pane output:

```toml
[tool]
name = "claude"
command = "claude"
icon = "🤖"

[detection]
busy_patterns = ["⠋", "⠙", "thinking"]
waiting_patterns = ["❯", "Yes/No", "Allow", "Deny"]
error_patterns = ["Error:", "ERROR"]
idle_patterns = ["$", "❯"]

[mcp]
config_cmd = "claude mcp add"
```

### Runtime state

Session state is stored as JSON files in `~/.local/share/shoal/sessions/`. These are managed automatically — you don't need to edit them.

## Quick Start

```bash
# Create a session in the current git repo
shoal add -t claude

# Create a session with a dedicated worktree and branch
shoal add -t claude -w my-feature -b

# List sessions
shoal ls

# Attach to a session (switches tmux client)
shoal attach my-feature

# Detach (from inside a shoal tmux session)
shoal detach

# Kill a session and its worktree
shoal kill my-feature --worktree

# Quick status overview
shoal status

# Interactive dashboard (tmux popup)
shoal popup
```

## Command Reference

### Session Management

| Command | Description |
|---------|-------------|
| `shoal add [PATH] -t TOOL -w NAME -b -n NAME` | Create a new session |
| `shoal ls` | List all sessions |
| `shoal attach [SESSION]` | Attach to a session (fzf picker if no arg) |
| `shoal detach` | Detach from current shoal session |
| `shoal fork [SESSION] --name NAME` | Fork a session into a new worktree |
| `shoal kill [SESSION] --worktree` | Kill a session, optionally remove worktree |
| `shoal status` | Summary of all session statuses |
| `shoal popup` | Interactive fzf dashboard in tmux popup |
| `shoal version` | Print version |

**Aliases:** `new`=add, `a`=attach, `d`=detach, `rm`=kill, `st`=status, `pop`=popup

### Worktree Management (`shoal wt`)

| Command | Description |
|---------|-------------|
| `shoal wt ls` | List worktrees managed by shoal |
| `shoal wt finish [SESSION] --pr --no-merge` | Merge branch, remove worktree, clean up |
| `shoal wt cleanup` | Find and remove orphaned worktrees |

**Alias:** `worktree`=wt

### MCP Server Pool (`shoal mcp`)

Shoal can run shared MCP servers as Unix socket proxies via socat. Multiple AI agents can connect to the same MCP server through `shoal-mcp-proxy`.

| Command | Description |
|---------|-------------|
| `shoal mcp ls` | List pooled MCP servers |
| `shoal mcp start NAME [--command CMD]` | Start an MCP server |
| `shoal mcp stop NAME` | Stop an MCP server |
| `shoal mcp attach SESSION MCP` | Associate an MCP server with a session |
| `shoal mcp status` | Pool health check |

Known servers (no `--command` needed): `memory`, `filesystem`, `github`, `fetch`.

```bash
# Start a shared memory server
shoal mcp start memory

# Connect it to a session's tool
shoal mcp attach my-session memory
# Then in Claude Code:
#   claude mcp add memory -- shoal-mcp-proxy memory
```

### Conductor (`shoal conductor`)

A conductor is a supervisory AI agent that monitors other sessions.

| Command | Description |
|---------|-------------|
| `shoal conductor setup [NAME] -t TOOL` | Create a conductor profile + AGENTS.md |
| `shoal conductor start [NAME]` | Start a conductor session |
| `shoal conductor stop [NAME]` | Stop a conductor |
| `shoal conductor status` | Conductor health check |
| `shoal conductor ls` | List conductor profiles |

**Alias:** `cond`=conductor

### Neovim Integration (`shoal nvim`)

Requires [neovim-remote](https://github.com/mhinz/neovim-remote) (`nvr`).

| Command | Description |
|---------|-------------|
| `shoal nvim send SESSION CMD` | Send an ex command to a session's nvim |
| `shoal nvim diagnostics SESSION` | Get LSP diagnostics from a session's nvim |

### Background Watcher (`shoal watcher`)

Polls tmux panes to detect agent status changes and sends macOS notifications when a session enters the "waiting" state.

| Command | Description |
|---------|-------------|
| `shoal watcher start [--foreground]` | Start the watcher daemon |
| `shoal watcher stop` | Stop the watcher |
| `shoal watcher status` | Check if the watcher is running |

### Tmux Status Bar

Add to your `tmux.conf`:

```tmux
set -g status-right "#(shoal-status)"
```

This shows active sessions with tool icons, color-coded status, and an active count.

## Architecture

```
src/shoal/
├── cli/            # Typer commands (one file per command group)
├── core/           # Pure logic + subprocess wrappers
│   ├── config.py   # TOML loading, XDG paths
│   ├── state.py    # Session CRUD (JSON via Pydantic)
│   ├── tmux.py     # Tmux subprocess wrappers
│   ├── git.py      # Git subprocess wrappers
│   ├── detection.py# Status detection (pure function)
│   └── notify.py   # macOS notifications
├── models/         # Pydantic models for config + state
├── services/       # Background processes + entry points
│   ├── watcher.py  # Asyncio polling daemon
│   ├── mcp_pool.py # MCP server lifecycle
│   ├── mcp_proxy.py# stdio-to-socket bridge
│   └── status_bar.py# Tmux status segment
└── dashboard/      # fzf popup integration
```

Key design decisions:

- **Pydantic for all I/O** — config (TOML) and state (JSON) go through typed models. No `jq` dependency.
- **Pure detection function** — `detect_status(pane_text, tool_config) -> SessionStatus` has no side effects, making it trivially testable.
- **Subprocess wrappers** — `core/tmux.py` and `core/git.py` isolate all subprocess calls, keeping CLI handlers focused on orchestration logic.
- **XDG layout** — config in `~/.config/shoal/`, state in `~/.local/share/shoal/`.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

## License

MIT
