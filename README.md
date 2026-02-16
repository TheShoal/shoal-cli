# Shoal

Terminal-first orchestration for parallel AI coding agents.

Shoal manages multiple AI coding agents (Claude Code, OpenCode, Gemini) in persistent, branch-aware tmux sessions. It provides a unified control plane with shared MCP servers, automated status detection, and a supervisor "conductor" workflow.

![Status: Beta](https://img.shields.io/badge/status-beta-yellow)
![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey)
![License: Proprietary](https://img.shields.io/badge/license-Proprietary-red)
![Python: 3.12+](https://img.shields.io/badge/python-3.12+-blue)

## The Analogy: A Robo-Fish in the Shoal

In nature, a shoal of fish moves as a single, self-directing unit. In your terminal, **Shoal** is the orchestrator—the "robo-fish" that leads a group of independent agent sessions.

- **The Conductor**: A supervisory agent that monitors the group, approves actions, and ensures the "shoal" stays on track.
- **The Sessions**: Parallel agents (the fish) working in dedicated git worktrees, synchronized by a shared state and MCP pool.

---

## Features

- 🔄 **Parallel Agent Loops**: Run multiple coding agents simultaneously without context switching.
- 🌿 **Worktree-Native**: Automatically manages git worktrees for every session—keep your main branch clean.
- 🔌 **MCP Pooling**: Shared MCP servers (Memory, Filesystem, GitHub) via a socket proxy—no more duplicate server overhead.
- 🕵️ **Status Detection**: Real-time monitoring of agent states (Thinking, Waiting, Error, Idle) from tmux pane output.
- 🔔 **macOS Notifications**: Get notified the second an agent needs your approval.
- 🎮 **Conductor Mode**: A supervisor agent that can "send keys" and "approve" tasks across your entire fleet of agents.
- 🏠 **Environment-First**: Built for tmux. SSH in from your phone, attach to a session inside VS Code, or live in the terminal.

## Demo

> [!TIP]
> **Insert VHS/Screenshot here**: Showing `shoal popup` and the tmux status bar in action.

---

## Status

Shoal is currently in **Beta**. It is the standard orchestration tool for terminal-first AI workflows at US Mobile.
- **Target Platform**: macOS + tmux 3.3+.
- **Stability**: CLI surface is stabilizing; config keys may change until v1.0.

---

## Install

### Recommended (uv)
```bash
uv tool install .
```

### From source (dev)
```bash
git clone git@github.com:usmobile/shoal.git
cd shoal
pip install -e ".[dev]"
```

## Shell Completions

Shoal supports tab-completion for Bash, Zsh, and Fish.

### Zsh
```bash
shoal --install-completion zsh
```

### Bash
```bash
shoal --install-completion bash
```

### Fish
```bash
shoal --install-completion fish
```

---

## Concepts

### Sessions & Worktrees
A **Session** is a tmux session tied to a specific tool and directory. If a **Worktree** name is provided, Shoal manages the git worktree and branch lifecycle for you, ensuring that parallel agents never stomp on each other's files.

### MCP Pooling
Instead of every agent starting its own instance of an MCP server, Shoal runs them in a **Pool**. Agents connect via `shoal-mcp-proxy`, allowing them to share state (like a shared Memory server) and reduce resource usage.

### Conductor Mode
The **Conductor** is a "super-session." It runs an agent with a specialized prompt (`AGENTS.md`) and access to the Shoal CLI. It can monitor the status of all other agents and interact with them directly.

---

## Quick Start

```bash
# Start a new agent session in a dedicated worktree
shoal add -t claude -w feature-api -b

# Open the interactive dashboard (tmux popup)
shoal popup

# Check the status of all running agents
shoal status

# Merge a worktree and clean up when done
shoal wt finish feature-api --pr
```

---

## Command Reference

### Session Management
| Command | Alias | Description |
|---------|-------|-------------|
| `shoal add` | `new` | Create a new session (optionally with a worktree) |
| `shoal ls` | | List sessions grouped by project |
| `shoal attach` | `a` | Attach to a session (fzf picker if no name) |
| `shoal kill` | `rm` | Stop a session and clean up worktrees |
| `shoal popup` | `pop` | Open the interactive TUI dashboard |

### Worktrees (`shoal wt`)
- `ls`: List managed worktrees.
- `finish`: Merge, delete branch, and remove worktree.
- `cleanup`: Remove orphaned worktrees.

### MCP Pool (`shoal mcp`)
- `start/stop`: Manage pooled servers.
- `attach`: Connect a session to a pooled server.

### Conductor (`shoal conductor`)
- `start`: Launch the supervisor agent.
- `approve`: Send "Enter" to a waiting agent.
- `send`: Send arbitrary keys to a child session.

---

## Architecture

Shoal is built on a modern async Python stack:
- **FastAPI/Uvicorn**: Provides a local API for state monitoring.
- **SQLite (WAL)**: Concurrent, persistent state management.
- **Typer**: Type-safe CLI interface.
- **Pydantic**: Strict data modeling for configs and state.

---

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions and [ROADMAP.md](ROADMAP.md) for what's coming next.

## License

Proprietary. Copyright (c) 2026 US Mobile.
