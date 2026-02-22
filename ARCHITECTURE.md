# Shoal Architecture Guide

**Why build Shoal this way?** This guide explains the technical design decisions, implementation architecture, and engineering philosophy behind a fish-first orchestration tool tailored to one maintainer's daily workflow.

---

## Table of Contents

1. [Why Shoal Exists](#why-shoal-exists)
2. [Core Architecture](#core-architecture)
3. [Design Principles](#design-principles)
4. [Key Implementation Decisions](#key-implementation-decisions)
5. [Why These Choices Matter](#why-these-choices-matter)
6. [Production Readiness](#production-readiness)
7. [Future-Proofing](#future-proofing)

Design Principles covers: Terminal-First, Async+SQLite, Git Worktrees, MCP Pool, Status Detection, Robo Supervisor, Template Inheritance.

---

## Why Shoal Exists

### Scope

- Shoal is intentionally optimized for a personal stack: **Fish + tmux + Neovim + OpenCode**.
- Claude and Gemini remain supported as secondary tool profiles.
- Bash/Zsh compatibility is out of scope for now to keep maintenance overhead low.

### The Problem

Modern AI coding agents (Claude Code, OpenCode, Gemini Code Assist) are powerful but inherently **single-threaded**. When you need to:

- Work on multiple features in parallel
- Have agents review each other's work
- Run overnight batch processing with supervision
- Coordinate complex multi-step workflows

...you hit fundamental limitations:

1. **Context Switching Hell**: Manually juggling multiple terminal windows, git branches, and agent states
2. **Resource Waste**: Each agent spinning up duplicate MCP servers (memory, filesystem, GitHub)
3. **No Coordination**: Agents can't communicate, share state, or be supervised programmatically
4. **State Management**: No persistent record of what agents are doing, what branches they're on, or their current status

### The Solution

Shoal is a **control plane** for AI agents that:

- Orchestrates parallel agent sessions with **zero manual context switching**
- Shares infrastructure (MCP servers, git state) to **minimize resource overhead**
- Provides **programmatic supervision** via the "robo" supervisor pattern
- Maintains **persistent state** in SQLite with real-time status detection

**Unlike simple shell scripts or tmux configs**, Shoal is a stateful orchestration system with lifecycle management, health monitoring, and inter-agent communication.

---

## Core Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────┐
│                         Shoal CLI                            │
│  (Typer-based CLI → Async Core → SQLite State)             │
└──────────────────┬──────────────────────────────────────────┘
                   │
      ┌────────────┴────────────┐
      │                         │
┌─────▼──────┐         ┌────────▼─────┐
│ Session    │         │ MCP Pool     │
│ Manager    │         │ (asyncio)    │
│            │         │              │
│ - Lifecycle│         │ - Shared     │
│ - Worktrees│         │   servers    │
│ - Status   │         │ - Socket     │
│   detection│         │   pooling    │
└─────┬──────┘         └──────────────┘
      │
┌─────▼──────────────────────────────┐
│  Tmux Session Layer                │
│  (tmux 3.3+ with status detection) │
└────────────────────────────────────┘
```

### Data Flow

1. **User Command** → CLI layer (Typer) or API layer (FastAPI)
2. **Lifecycle Orchestration** → `services/lifecycle.py` (create/fork/kill/reconcile with rollback)
3. **Business Logic** → Async core (`src/shoal/core/`)
4. **State Persistence** → SQLite (WAL mode, async via `aiosqlite`, update lock)
5. **Subprocess Ops** → Tmux/Git wrappers (sync for CLI, `async_*` for API/watcher)
6. **Monitoring** → Status detection via tmux pane capture + regex patterns

---

## Design Principles

### 1. **Terminal-First, Not GUI-First**

**Decision**: Build for tmux, SSH, and terminal workflows—not Electron or web UIs.

**Why**:
- Engineers already live in terminals
- SSH accessibility is critical for remote work
- Tmux provides battle-tested session persistence
- Lower resource footprint than Electron apps

**Trade-off**: Limited rich UI capabilities, but gained universal accessibility and reliability.

---

### 2. **Async-First with SQLite + WAL**

**Decision**: Use SQLite with Write-Ahead Logging (WAL mode) + `aiosqlite` for all state management.

**Why**:
- **No External Dependencies**: Zero setup friction (no Postgres, Redis, etc.)
- **ACID Guarantees**: Safe concurrent writes from CLI, API, and background watchers
- **WAL Mode**: Readers don't block writers, writers don't block readers
- **Async Throughout**: Natural async/await patterns for I/O operations

**Implementation**:
```python
# Single connection singleton with context manager lifecycle
async with get_db() as db:
    await db.execute("INSERT INTO sessions ...")
```

**Trade-off**: Not suitable for distributed deployments, but perfect for single-machine orchestration.

---

### 3. **Git Worktrees as Isolation Boundaries**

**Decision**: Use git worktrees (not branches) to isolate agent work.

**Why**:
- **Zero File Conflicts**: Each agent has a separate working directory
- **Parallel Checkouts**: Multiple agents can work on different branches simultaneously
- **Native Git Support**: No custom filesystem magic, just standard git commands
- **Branch Cleanup**: Automatically removes worktrees and branches when sessions end

**Example**:
```bash
# Agent 1 works in: /repo/.worktrees/feature-ui (branch: feature-ui)
# Agent 2 works in: /repo/.worktrees/feature-api (branch: feature-api)
# Main repo stays on: main
```

**Trade-off**: Requires users to understand worktrees, but provides rock-solid isolation.

---

### 4. **MCP Server Pool with Per-Connection Spawning**

**Decision**: Run a pool server per MCP type that listens on a Unix socket and spawns a fresh MCP command instance for each client connection.

**Why**:
- **Resource Efficiency**: One listener process per MCP type, shared socket infrastructure
- **Standard Protocol**: Works with any MCP-compatible client (Claude, OpenCode, etc.)
- **No External Dependencies**: Pure Python asyncio server, no socat required

**Implementation**:
```python
# Pool server listens on Unix socket:
#   ~/.local/state/shoal/mcp-pool/sockets/memory.sock
#
# Each client connection spawns:
#   npx -y @modelcontextprotocol/server-memory
#
# Client I/O is bridged to the spawned command's stdin/stdout.
# The shoal-mcp-proxy binary handles the stdio-to-socket bridge.
```

**Known limitation**: Because each connection spawns a fresh MCP process, memory state is **not shared** between agents. An agent writing to MCP memory cannot be read by another agent's session. True multiplexing with shared state is a future goal.

**Trade-off**: Simpler architecture and no runtime dependencies, but no cross-agent state sharing.

---

### 5. **Status Detection via Tmux Pane Scraping**

**Decision**: Detect agent status (Thinking, Waiting, Error, Idle) by parsing tmux pane output from the session-tagged tool pane.

**Why**:
- **No Agent Modifications**: Works with any agent (Claude, OpenCode, Gemini)
- **Stable Targeting**: Watcher follows pane title `shoal:<session_id>` so split panes and active-pane changes do not cause false routing
- **Real-Time**: Polls every 5 seconds via background watcher
- **Tool-Specific Patterns**: Configurable regex patterns per tool

**Implementation**:
```toml
# ~/.config/shoal/tools/claude.toml
[detection]
busy_patterns = ["⠋", "thinking"]
waiting_patterns = ["❯", "Yes/No", "Allow"]
error_patterns = ["Error:", "ERROR"]
idle_patterns = ["$"]
```

**Trade-off**: Requires tmux, limited to pattern matching, but universally compatible.

**Runtime Contract**:
- Session pane identity: `shoal:<session_id>` (tmux pane title)
- Neovim socket identity: `/tmp/nvim-<session_id>-<window_id>.sock`
- Socket ownership: interactive `nvim --listen` in the active tool pane
- Tmux cleanup role: stale socket cleanup only (no headless Neovim ownership)

---

### 6. **Robo Supervisor as Code**

**Decision**: The "robo" supervisor is just another agent session with Shoal CLI access.

**Why**:
- **Dogfooding**: Robo uses the same API as manual users
- **Programmable**: Can approve, send keys, monitor status—all via CLI
- **Emergent Behavior**: LLMs can orchestrate complex workflows without custom code

**Example Robo Prompt**:
```markdown
You are a robo-fish supervisor managing a shoal of AI agents.

Commands available:
- shoal status: See all agents
- shoal robo approve <session>: Approve an agent's action
- shoal send <session> <keys>: Send input to an agent

Your job: Monitor agents, approve when needed, escalate if stuck.
```

**Trade-off**: Requires LLM capability to use CLI, but provides unlimited flexibility.

---

### 7. **Template Inheritance and Composition**

**Decision**: Support single inheritance (`extends`) and additive composition (`mixins`) for session templates, with cycle detection and raw-TOML field presence checks.

**Why**:
- **DRY Templates**: Common layouts shared via a base template, specialized by child templates
- **Additive Composition**: Mixins add MCP servers, env vars, or windows without replacing base config
- **Safe Resolution**: Cycle detection via set-based tracking prevents infinite loops

**Merge Semantics** (`extends`):
- Scalars (tool, description): child wins only if explicitly set in TOML
- `env`: parent | child (child wins on conflict)
- `mcp`: union, deduplicated, sorted
- `windows`: child replaces all parent windows if child defines any; otherwise inherits
- `worktree`: child wins if `[template.worktree]` section present

**Mixin Semantics** (additive only):
- `env`: merged in (mixin wins on conflict)
- `mcp`: union, deduplicated, sorted
- `windows`: appended after existing windows

**Resolution order**: extends → mixins → CLI flags

**Implementation**:
```toml
# base-dev.toml — shared layout
[template]
name = "base-dev"
tool = "opencode"

# claude-dev.toml — inherits and specializes
[template]
name = "claude-dev"
extends = "base-dev"
mixins = ["mcp-memory"]
tool = "claude"
```

```python
# resolve_template() walks the extends chain with cycle detection,
# then applies each mixin additively. Raw TOML dict is checked for
# key presence to distinguish "not set" from "set to default".
resolved = resolve_template("claude-dev")
```

**Trade-off**: Adds complexity to template loading, but eliminates duplication across template libraries.

---

## Key Implementation Decisions

### Why Typer + Rich for CLI?

**Typer**: Type-safe, auto-generated help, built on Click  
**Rich**: Beautiful terminal output with colors, tables, panels

**Alternative Considered**: argparse, click  
**Decision**: Typer's type hints + Rich's styling = best developer experience

---

### Why FastAPI for the API Server?

**FastAPI**: Async-native, auto-docs (OpenAPI), Pydantic validation

**Alternative Considered**: Flask, Django  
**Decision**: Async support is critical for I/O-heavy operations (tmux, git, DB)

---

### Why Not a Traditional Database?

**SQLite**: Single file, zero configuration, ACID compliant

**Alternative Considered**: Postgres, MySQL  
**Decision**:
- No multi-machine deployments needed
- Setup friction must be zero
- WAL mode provides excellent concurrency for single-machine use

---

### Why Async Throughout?

**Decision**: `async/await` for all I/O operations (DB, subprocess, HTTP)

**Why**:
- Non-blocking concurrent operations (status polling + user commands)
- Natural fit for FastAPI server
- Better resource utilization than threading

**Trade-off**: More complex than sync code, but necessary for background tasks.

---

## Why These Choices Matter

### For Individual Engineers

- **Zero Setup**: `uv tool install shoal` and you're done—no Docker, no databases, no config files
- **Works Remotely**: SSH into any machine, attach to tmux, keep working
- **Terminal Native**: Integrates with your existing workflow (vim, fzf, lazygit)

### For Optional Collaborators and Forks

- **Resource Efficiency**: Shared MCP servers reduce duplicate process overhead
- **Reproducible Workflows**: Git worktrees preserve isolation and clean state
- **Extensible Foundation**: Tool profiles and tmux orchestration can be adapted per fork

---

## Production Readiness

### Current Status (v0.14.0)

- ✅ **589 Tests, 81% Coverage**: Comprehensive unit, CLI, and model tests with 80% coverage gate
- ✅ **Type Safety**: Full type hints, Pydantic v2 models, mypy --strict enforced
- ✅ **Error Handling**: Structured logging with session IDs, scoped exception hierarchy (`LifecycleError` → `TmuxSetupError`, `StartupCommandError`, `SessionExistsError`)
- ✅ **Database Lifecycle**: Single async SQLite connection with WAL mode, explicit lifecycle cleanup, and concurrent update guards (`asyncio.Lock`)
- ✅ **Lifecycle Service**: Shared `services/lifecycle.py` orchestrates create/fork/kill/reconcile with full rollback, used by both CLI and API
- ✅ **Async Correctness**: All tmux/git subprocess calls in async contexts use `asyncio.to_thread()` wrappers to avoid blocking the event loop
- ✅ **CI/CD Pipeline**: 5 concurrent CI jobs (lint, typecheck, test, fish-check, security), pre-commit hooks, conventional commits
- ✅ **Template Inheritance**: Single inheritance with cycle detection, additive mixins, full test coverage
- ✅ **Used Daily**: Built for sustained personal use in terminal-heavy AI workflows

### Known Limitations

- **Platform**: macOS only (tmux + Unix sockets required)
- **Concurrency**: Single machine only (SQLite limitation)
- **Status Detection**: Requires consistent tmux pane output patterns

### Roadmap to v1.0

- **v0.8.0**: Session template MVP release and final contract documentation ✅
- **v0.9.0**: Lifecycle hardening, async correctness, failure-path coverage ✅
- **v0.10.0**: Pure Python MCP bridge, server registry, auto-configure ✅
- **v0.11.0**: Pre-commit framework, CI pipeline, release automation ✅
- **v0.12.0**: Compiled regex detection, session CLI decomposition ✅
- **v0.13.0**: Ruff lint expansion, security consolidation ✅
- **v0.14.0**: Template inheritance and mixins ✅
- **v1.0.0**: Stable public surface for personal-first workflows

---

## Future-Proofing

### Extensibility Points

1. **Tool Configs**: Add new AI tools via TOML files (no code changes)
2. **MCP Servers**: Add new servers to the pool (filesystem, GitHub, custom)
3. **Status Patterns**: Customize detection patterns per tool
4. **Robo Profiles**: Multiple supervisor strategies (approver, reviewer, coordinator)
5. **Template Inheritance**: Build template libraries with `extends` and `mixins` composition

### Migration Path

- **To Distributed**: Replace SQLite with Postgres, add message queue
- **To Cloud**: Package as Docker container, add auth layer
- **To GUI**: FastAPI backend already exists, add React/Next.js frontend

---

## Why You Should Invest in Shoal

### Technical Excellence

- **Thoughtful Architecture**: Every design decision addresses a real pain point
- **Production-Tested**: Built and battle-tested at a high-growth company
- **Clean Codebase**: Type-safe, well-documented, 81% test coverage

### Practical Value

- **Immediate ROI**: Speeds up one developer's multi-agent workflow today
- **Low Maintenance**: SQLite + local-first = no infrastructure overhead
- **Composable Patterns**: Robo supervisor workflows remain available when needed

### Community Potential

- **Open Source Ready**: Clean abstractions, extensible design
- **Novel Approach**: First tool to treat AI agents as orchestratable processes
- **Growing Ecosystem**: MCP protocol adoption is accelerating

---

## Conclusion

Shoal isn't just a wrapper around tmux—it's a **control plane for the AI coding revolution**.

By choosing:
- **Terminal-first** over GUI bloat
- **SQLite + WAL** over complex databases
- **Git worktrees** over manual branch management
- **MCP pooling** over duplicate servers
- **Status detection** over agent API modifications
- **Robo supervisors** over hardcoded workflows

...we've built a system that is:
- ✅ **Simple to deploy** (zero dependencies)
- ✅ **Reliable in production** (ACID guarantees, WAL mode)
- ✅ **Extensible by design** (TOML configs, MCP protocol)
- ✅ **Future-proof** (async-first, event-ready)

**Invest in Shoal** because it solves today's AI orchestration problems while building a foundation for tomorrow's multi-agent workflows.

---

**Next Steps**:
- Read [docs/ROBO_GUIDE.md](docs/ROBO_GUIDE.md) for advanced patterns
- Try `shoal demo start` to see it in action
- Check [ROADMAP.md](ROADMAP.md) for upcoming features
- Review [CONTRIBUTING.md](CONTRIBUTING.md) to get involved
