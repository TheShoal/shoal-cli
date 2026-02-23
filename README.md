<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=0:11111b,30:1e1e2e,70:45475a,100:94e2d5&height=200&section=header&text=Shoal&fontSize=72&fontColor=cdd6f4&animation=fadeIn&fontAlignY=32&desc=Terminal-first%20orchestration%20for%20parallel%20AI%20coding%20agents&descSize=16&descColor=89b4fa&descAlignY=52" alt="Shoal banner" width="100%">
</p>

<p align="center">
  <img src="assets/robo-fish.svg" width="280" alt="Shoal robo-fish mascot">
</p>

<!-- Badges -->
<p align="center">
  <img src="https://img.shields.io/badge/v0.16.0-beta-EED49F?style=flat-square" alt="v0.16.0 beta">
  <img src="https://img.shields.io/badge/python-3.12+-8AADF4?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/license-Proprietary-ED8796?style=flat-square" alt="License: Proprietary">
</p>

<!-- Row 2 — Stack -->
<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/SQLite_WAL-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite WAL">
  <img src="https://img.shields.io/badge/tmux-1BB91F?style=flat-square&logo=tmux&logoColor=white" alt="tmux">
  <img src="https://img.shields.io/badge/Fish_Shell-4AAE46?style=flat-square&logo=gnubash&logoColor=white" alt="Fish Shell">
  <img src="https://img.shields.io/badge/Pydantic_v2-E92063?style=flat-square&logo=pydantic&logoColor=white" alt="Pydantic v2">
  <img src="https://img.shields.io/badge/Ruff-D7FF64?style=flat-square&logo=ruff&logoColor=black" alt="Ruff">
</p>

<!-- Row 3 — Quality -->
<p align="center">
  <img src="https://img.shields.io/badge/tests-589_passing-A6DA95?style=flat-square" alt="Tests: 589 passing">
  <img src="https://img.shields.io/badge/coverage-81%25-8BD5CA?style=flat-square" alt="Coverage: 81%">
  <img src="https://img.shields.io/badge/pre--commit-enabled-C6A0F6?style=flat-square&logo=pre-commit&logoColor=white" alt="pre-commit enabled">
</p>

<p align="center">
  <em>Run multiple AI agents in isolated worktrees, coordinate them through a shared control plane, and never context-switch again.</em>
</p>

<p align="center">
  <img src="assets/status-pulse.svg" width="600" alt="Agent status indicators">
</p>

---

## TL;DR

You're an engineer running AI coding agents — Claude, Pi, Gemini, OpenCode. You want them working in parallel without stomping on each other's files. You need to know when they're thinking, when they're waiting for approval, and when they've errored out.

**Shoal is `docker-compose` for AI coding agents.** You declare sessions, Shoal gives each one a git worktree, a tmux session, and a shared pool of MCP servers. One command to start. One dashboard to monitor. One CLI to control them all.

---

## See It in Action

<p align="center">
  <img src="assets/terminal-demo.svg" width="700" alt="Shoal terminal workflow demo">
</p>

---

## What You Get

**Parallel agent loops** let you run multiple coding agents simultaneously. Each agent works in its own tmux session with its own context — no shared terminal, no conflicts.

**Worktree isolation** gives every session a dedicated git worktree. Agents work on separate branches in separate directories. Your main branch stays clean.

**MCP server pool** provides shared infrastructure for MCP servers via Unix socket proxying. Each agent connection spawns a fresh MCP process — no duplicate listener overhead.

**Real-time status detection** watches tmux pane output and reports each agent's state: Thinking, Waiting, Error, or Idle. You always know who needs attention.

**Session templates** define window layouts, pane splits, and tool configs in TOML. Templates support inheritance (`extends`) and composition (`mixins`) to eliminate duplication across workflows.

**Robo supervisor mode** gives a coordinating agent access to the Shoal CLI. It monitors the fleet, sends keystrokes, approves actions, and routes tasks — your agents managing agents.

---

## How It Works

<p align="center">
  <img src="assets/architecture-flow.svg" width="700" alt="Shoal architecture diagram">
</p>

1. **You run `shoal new`** — Shoal creates a tmux session, optionally provisions a git worktree and branch, and launches your chosen AI tool inside it.

2. **Each agent gets isolation** — Separate worktree, separate branch, separate tmux session. Agents cannot interfere with each other's files.

3. **MCP servers are pooled** — Instead of each agent spawning its own MCP servers, Shoal runs a shared pool. Agents connect through `shoal-mcp-proxy` for shared infrastructure (each connection spawns a fresh MCP process).

4. **Status is tracked continuously** — A background monitor reads tmux pane output, matches patterns against tool-specific configs, and writes state to a SQLite WAL database. The FastAPI server exposes this via a local API.

5. **You control everything from one CLI** — `shoal status` shows all agents. `shoal popup` opens a TUI dashboard. `shoal attach` jumps into any session. `shoal robo` launches a supervisor to automate the whole fleet.

---

## Quick Start

### Install

```bash
# Recommended
uv tool install .

# From source (dev)
git clone git@github.com:usm-ricardoroche/shoal.git
cd shoal && uv pip install -e ".[dev]"
just setup  # install pre-commit + commit-msg hooks
```

### Try the Demo

```bash
shoal demo start   # guided demo environment
shoal demo stop    # tear down when done
```

### 60-Second Workflow

```bash
# Create 3 parallel agents, each in its own worktree
shoal new -t claude -w auth -b
shoal new -t pi -w api-refactor -b
shoal new -t gemini -w docs -b

# Check on everyone
shoal status

# Open the dashboard
shoal popup

# Attach to a session
shoal attach auth

# When done, merge and clean up
shoal wt finish auth --pr
```

`shoal new` defaults to your configured `default_tool`. Pass `-t/--tool` to override.

---

## Use Cases

<details>
<summary><strong>Parallel Feature Development</strong></summary>

Work on frontend, backend, and docs simultaneously:

```bash
shoal new -t claude -w feature-ui -b
shoal new -t pi -w feature-api -b --template pi-dev
shoal new -t gemini -w feature-docs -b
```

Each agent works in its own worktree with pooled MCP server infrastructure.

</details>

<details>
<summary><strong>Code Review Automation</strong></summary>

Have one agent write code, another review it:

```bash
shoal new -t claude -w implement-auth -b
shoal new -t pi -w review-auth -b
# Reviewer accesses implementer's worktree via shared filesystem MCP
```

</details>

<details>
<summary><strong>Overnight Batch Processing</strong></summary>

Set up agents with a robo supervisor to route tasks:

```bash
shoal robo setup batch --tool opencode
shoal robo start batch
# Robo monitors agents and assigns tasks from a backlog
```

See [docs/ROBO_GUIDE.md](docs/ROBO_GUIDE.md) for detailed patterns.

</details>

---

## Commands

### Session Management

| Command        | Alias | Description                                       |
| -------------- | ----- | ------------------------------------------------- |
| `shoal new`    | `add` | Create a new session (optionally with a worktree) |
| `shoal ls`     |       | List sessions grouped by project                  |
| `shoal attach` | `a`   | Attach to a session (fzf picker if no name)       |
| `shoal kill`   | `rm`  | Stop a session and clean up worktrees             |
| `shoal popup`  | `pop` | Open the interactive TUI dashboard                |

### Worktrees (`shoal wt`)

| Command   | Description                               |
| --------- | ----------------------------------------- |
| `ls`      | List managed worktrees                    |
| `finish`  | Merge, delete branch, and remove worktree |
| `cleanup` | Remove orphaned worktrees                 |

### MCP Pool (`shoal mcp`)

| Command      | Description                          |
| ------------ | ------------------------------------ |
| `start/stop` | Manage pooled servers                |
| `attach`     | Connect a session to a pooled server |

### Templates (`shoal template`)

| Command           | Description                             |
| ----------------- | --------------------------------------- |
| `ls`              | List available session templates        |
| `show <name>`     | Display a template's resolved config    |
| `show --raw`      | Display unresolved template (pre-merge) |
| `validate <name>` | Validate a template against the schema  |
| `mixins`          | List available template mixins          |

### Demo (`shoal demo`)

| Command | Description                                           |
| ------- | ----------------------------------------------------- |
| `start` | Spin up a full demo environment with example sessions |
| `stop`  | Tear down the demo environment                        |

### Robo Supervisor (`shoal robo`)

| Command   | Description                            |
| --------- | -------------------------------------- |
| `start`   | Launch the supervisor agent            |
| `approve` | Send "Enter" to a waiting agent        |
| `send`    | Send arbitrary keys to a child session |

### Remote Sessions (`shoal remote`)

| Command      | Description                           |
| ------------ | ------------------------------------- |
| `ls`         | List configured remote hosts          |
| `connect`    | Open SSH tunnel to remote API         |
| `disconnect` | Close SSH tunnel                      |
| `status`     | Show remote session status summary    |
| `sessions`   | List sessions on remote host          |
| `send`       | Send keystrokes to remote session     |
| `attach`     | Attach to remote tmux session via SSH |

---

## Fish Shell Integration

```fish
shoal setup fish
```

Installs tab completions, key bindings (`Ctrl+S` popup, `Alt+A` attach), abbreviations (`sa`, `sl`, `ss`, `sp`), and helper functions. See [Fish Integration Guide](docs/FISH_INTEGRATION.md) for details.

For completions only:

```fish
shoal --install-completion fish
```

---

## Supported Tools

| Tool        | Command    | Status    |
| ----------- | ---------- | --------- |
| OpenCode    | `opencode` | Primary   |
| Claude Code | `claude`   | Supported |
| Pi          | `pi`       | Supported |
| Gemini      | `gemini`   | Supported |

Tool configs live in `~/.config/shoal/tools/<name>.toml` with per-tool detection patterns.

---

## Status

| Milestone   | Focus                                 | Status   |
| ----------- | ------------------------------------- | -------- |
| **v0.16.0** | Remote sessions via SSH tunnel        | Current  |
| **v0.15.0** | FastMCP integration, Shoal MCP server | Complete |
| **v0.14.0** | Template inheritance and mixins       | Complete |

See [ROADMAP.md](ROADMAP.md) for the full plan.

---

## Development

```bash
just ci          # all CI checks (lint, typecheck, test, fish-check)
just lint        # lint with ruff
just fmt         # auto-format with ruff
just test        # tests (exclude integration)
just cov         # tests with coverage report
just setup       # install pre-commit hooks
```

**589 tests** | **81% coverage** | **pre-commit enforced** | **conventional commits**

See [CONTRIBUTING.md](CONTRIBUTING.md) for full setup instructions.

---

## Documentation

- [docs/REMOTE_GUIDE.md](docs/REMOTE_GUIDE.md) — Remote session management guide
- [docs/ROBO_GUIDE.md](docs/ROBO_GUIDE.md) — Robo supervisor patterns and workflows
- [docs/FISH_INTEGRATION.md](docs/FISH_INTEGRATION.md) — Fish shell integration guide
- [ARCHITECTURE.md](ARCHITECTURE.md) — System design and concepts
- [CONTRIBUTING.md](CONTRIBUTING.md) — Development setup and guidelines
- [ROADMAP.md](ROADMAP.md) — Upcoming features and milestones
- [RELEASE_PROCESS.md](RELEASE_PROCESS.md) — Versioning and release workflow
- [SECURITY.md](SECURITY.md) — Security policy and vulnerability reporting

---

## License

Proprietary. Copyright (c) 2026 US Mobile.

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=0:94e2d5,30:45475a,70:1e1e2e,100:11111b&height=120&section=footer" alt="footer" width="100%">
</p>
