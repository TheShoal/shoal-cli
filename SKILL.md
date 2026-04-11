# Shoal CLI — Agent Landing Page

Shoal is a terminal-first orchestration layer for parallel AI coding agent sessions. It manages git worktrees, tmux sessions, MCP server pools, and delivers prompts reliably across Claude Code, OMP, and OpenCode.

**Repo**: `tools/shoal-cli/`
**Entry point**: `shoal` CLI, `shoal-mcp-server` (FastMCP), `shoal-mcp-proxy` (stdio bridge)

---

## Core Concepts

### Sessions

A **session** is a tmux session + optional git worktree + optional MCP servers, tracked in SQLite. Sessions can be in states: `running`, `waiting`, `error`, `idle`, `stopped`.

### Worktrees

Sessions optionally create **git worktrees** (`.worktrees/<name>`) for isolated branch development. Worktrees are auto-cleaned up on session finish and support branch creation.

### Templates

**Templates** define the full session layout: tool, windows/panes, environment variables, MCP servers, and startup commands. Templates support `extends` (inheritance) and `mixins` (additive composition).

### MCP Pool

**MCP servers** run in a shared asyncio pool via Unix sockets. One listener per server type; each connection spawns a fresh process. Servers can be attached to sessions on demand.

### Status Detection

Sessions poll their tmux pane every 5s to detect status (Thinking/Waiting/Error/Idle). OMP sessions use the `omp_compat` provider; legacy Pi sessions used explicit event contracts. Other tools fall back to regex patterns from tool TOML profiles.

---

## Quick Start

### Create a Session

```bash
# Basic session in current directory
shoal new

# Named session with specific tool
shoal new my-feature -t omp

# Session with worktree + branch
shoal new my-feature -w feat/my-feature -b

# Dry-run to preview what would be created
shoal new my-feature -w feat/my-feature -b --dry-run
```

### Session Lifecycle

```bash
shoal ls                        # List all sessions
shoal status                    # Quick status summary (grouped by urgency)
shoal info <session>            # Detailed session info
shoal attach <session>          # Attach to tmux session
shoal detach                    # Detach from current session

shoal kill <session>            # Kill session
shoal kill <session> --worktree # Kill + remove worktree
shoal prune                     # Remove all stopped sessions
```

### Fork a Session

```bash
# Fork into new worktree
shoal fork <source-session> <new-name>

# Fork without worktree (shares parent's git state)
shoal fork <source-session> <new-name> --no-worktree

# Fork with additional MCP servers
shoal fork <source-session> <new-name> --mcp github,memory
```

---

## Templates

### List and Inspect Templates

```bash
shoal template ls               # List all available templates
shoal template show <name>       # Show resolved template as JSON
shoal template show <name> --raw # Show raw (unresolved) template
shoal template validate          # Validate all templates
shoal template validate <name>   # Validate specific template
shoal template mixins            # List available mixins
```

### Use a Template

```bash
shoal new --template pi-dev
shoal new --template claude-dev -t claude
shoal new --template omp-dev --mcp memory,github
```

### Template Structure

```toml
[template]
name = "my-dev"
description = "My development template"
extends = "base-dev"      # Single parent inheritance
mixins = ["mcp-memory"]   # Additive: env, mcp, windows

tool = "pi"               # Required: which AI tool

[template.env]
MY_VAR = "value"          # Environment variables
ANOTHER = "override"       # Overrides parent/mixin values

[template.worktree]
name = "feat/{session_name}"  # Worktree name pattern
create_branch = true          # Auto-create branch
prefix = "feat"              # Branch name prefix

[template.git]
branch_prefix = "feat"        # Normalize branch names

[[windows]]                   # Window definitions
name = "editor"
focus = true

[[windows.panes]]
split = "root"
size = "65%"
title = "pi-agent"
command = "{tool_command}"

[[windows.panes]]
split = "right"
size = "35%"
title = "terminal"
command = "echo 'Terminal ready'"
```

### Template Inheritance

| Field | `extends` behavior | `mixins` behavior |
|-------|-------------------|-------------------|
| `env` | Merge (child wins) | Merge (mixin wins) |
| `mcp` | Union, deduped | Union, deduped |
| `windows` | Child replaces entirely | Appended |
| `setup_commands` | Child replaces | Appended |

---

## Operating Modes

Modes provide sensible defaults for common workflows:

```bash
shoal mode ls                           # List available modes
shoal new --mode feature-lane           # Feature development
shoal new --mode author-review          # Review cycle
shoal new --mode remote-batch           # Batch operations on remote hosts
shoal new --mode planner                # Scope and plan
shoal new --mode implementer            # Execute from plan
shoal new --mode reviewer               # Pre-merge review
```

| Mode | Template | Fallback Tool | Worktree Prefix | Auto-tags |
|------|----------|---------------|-----------------|-----------|
| `feature-lane` | codex-dev | codex | feat | — |
| `author-review` | claude-review | claude | review | review-ready |
| `remote-batch` | claude-dev | claude | batch | — |
| `planner` | omp-dev | omp | plan | planner |
| `implementer` | omp-dev | omp | impl | implementer |
| `reviewer` | claude-review | claude | review | reviewer, review-ready |

---

## MCP Server Pool

### Managing Servers

```bash
shoal mcp ls                    # List running MCP servers
shoal mcp start <name>          # Start a pooled server
shoal mcp start <name> --http   # Start with HTTP transport
shoal mcp start <name> --port 8391
shoal mcp stop <name>           # Stop a server
shoal mcp status                # Pool health check
```

### Attach Servers to Sessions

```bash
# Auto-start + attach
shoal mcp attach <session> <server>

# Examples
shoal mcp attach my-session memory
shoal mcp attach my-session github
shoal mcp attach my-session filesystem
```

### MCP Stacks

MCP stacks are presets for common server groups (defined in `~/.config/shoal/mcp-stacks.toml`):

```toml
[stacks.dev]
description = "Development essentials"
servers = ["filesystem", "github", "memory"]

[stacks.orchestration]
description = "Full orchestration stack"
servers = ["shoal-orchestrator", "memory"]
```

### MCP Registry

Register servers in `~/.config/shoal/mcp-servers.toml` for auto-discovery:

```toml
[memory]
command = "npx -y @modelcontextprotocol/server-memory"

[github]
command = "npx -y @modelcontextprotocol/server-github"

[filesystem]
command = "npx -y @modelcontextprotocol/server-filesystem"
```

---

## Dashboard

### Interactive Popup

```bash
shoal popup              # Open tmux popup dashboard (fzf-based)
# Inside tmux: Prefix+S also opens dashboard
```

| Key | Action |
|-----|--------|
| `Enter` | Attach to selected session |
| `Ctrl-x` | Kill session |
| `Ctrl-y` | Approve waiting agent (send Enter) |
| `Ctrl-g` | Fork session |
| `Ctrl-w` | Filter to attention-required only |
| `Ctrl-r` | Reload session list |
| `Esc` | Close |

### Quick Status

```bash
shoal status                 # Grouped by urgency (needs attention / active / background)
shoal status --format plain  # Terse output for scripts
```

---

## Worktree Management

```bash
shoal wt ls                  # List managed worktrees
shoal wt finish <session>     # Merge branch + cleanup worktree
shoal wt finish <session> --pr # Open PR via gh
shoal wt cleanup              # Remove orphaned worktrees
```

---

## Robo Supervisor

Robo sessions are supervisory agents that monitor the shoal and handle waiting agents.

### Setup and Run

```bash
shoal robo setup <name>           # Create a robo profile
shoal robo setup <name> -t omp     # With specific tool
shoal robo start <name>            # Start robo session
shoal robo stop <name>             # Stop robo session
shoal robo ls                      # List running robos
shoal robo status                  # Robo status
shoal robo watch                   # Watch robo activity
```

### Robo Profile (`~/.config/shoal/robo/<name>.toml`)

```toml
[robo]
name = "default"
tool = "omp"
auto_approve = false

[monitoring]
poll_interval = 10            # Seconds between status checks
waiting_timeout = 300         # Seconds before escalation

[escalation]
notify = true                 # Notify on escalation
auto_respond = false          # Auto-respond to common patterns
escalation_session = ""       # Session name to escalate to (optional)
escalation_timeout = 300      # Seconds before escalation fires

[tasks]
log_file = "task-log.md"

[proactive]
auto_enqueue = false          # Spawn implementer session on command failure
failure_ttl_seconds = 3600    # How long to retain failure context packets
trigger_topics = ["command_failed"]
```

### Approve Waiting Agents

```bash
shoal robo approve <session>   # Approve + continue
shoal send <session> ""         # Send Enter (same effect)
```

---

## Ticket Workflows (Linear)

```bash
shoal ticket sync                        # Sync Linear issues to local SQLite cache
shoal ticket pick                        # Interactive fzf picker across teams
shoal ticket pick --json                 # Output selection as JSON
shoal ticket start <identifier>          # Create session from a Linear issue (e.g. AIA-469)
shoal ticket decompose <identifier>      # Split parent issue into child sub-issues (dry-run by default)
shoal ticket decompose <identifier> --commit  # Create sub-issues in Linear
```

Session names and branch slugs are auto-derived from issue identifier + title and normalized to `feat/<identifier>-<title-slug>` format.

---

## GitHub PR Workflows

```bash
shoal github review-pr <pr-number>       # Spawn a review session with full PR context (diff + comments)
shoal github post-review <session>       # Post session review findings as a PR comment
```

---

## Reports

```bash
shoal report session <session>           # Summary for a single session
shoal report team [--team <name>]        # Aggregate sessions by team
shoal report weekly                      # Weekly digest (sessions + Linear issues + GitHub PRs)
shoal report weekly --week 2026-W15      # Specific ISO week
shoal report weekly --post               # Post sprint update to Linear
```

---

## Proactive Monitoring

```bash
shoal proactive fs-watch start           # Watch session worktrees for file changes
shoal proactive fs-watch status          # Status of the file watcher
shoal proactive message send <session> <msg>   # Send a message to a session's Agent Bus
shoal proactive message list <session>   # List unconsumed messages for a session
```

`command_failed` lifecycle events are automatically captured by the Scout supervisor when `proactive.auto_enqueue = true` in the robo profile.

---

## Session Aliases (`shoal session`)

Ergonomic aliases for common session operations:

```bash
shoal session list                       # Alias for shoal ls
shoal session info <name>                # Alias for shoal info
shoal session status                     # Alias for shoal status
shoal session attach <name>              # Alias for shoal attach
shoal session detach                     # Alias for shoal detach
shoal session kill <name>                # Alias for shoal kill
shoal session prune                      # Alias for shoal prune
shoal session logs <name>                # Show session journal log
```

---

## Skills

Skills are project-local or global `.md` files that agents can read to understand domain-specific workflows.

### Discovery

```bash
shoal skill ls                 # List discovered skills
```

Skills are auto-discovered from:
- Project: `<git-root>/.shoal/skills/<name>/SKILL.md`
- Global: `~/.config/shoal/skills/<name>/SKILL.md`

### Skill Sync

On worktree creation, skills are synced to tool-native paths:
- Claude Code: `.claude/skills/` (symlinks)
- Others: via `post_worktree_create` hook

---

## Configuration

### Config Paths

```bash
shoal config paths            # Show resolved XDG directories
shoal config show             # Dump effective config (TOML)
shoal config show --format json
```

### Main Config (`~/.config/shoal/config.toml`)

```toml
[general]
default_tool = "omp"          # Default AI tool
worktree_dir = ".worktrees"   # Worktree base directory
use_nerd_fonts = true         # Nerd Font glyphs in output

[tmux]
session_prefix = "_"         # Tmux session name prefix
popup_width = "90%"
popup_height = "90%"
popup_key = "S"              # Prefix+S opens dashboard

[status_bar]
max_display = 5              # Sessions shown in fish status bar
flash_waiting = true          # Flash on waiting sessions

[notifications]
enabled = true
timeout_seconds = 300         # Wait before notifying

[robo]
default_tool = "omp"
default_profile = "default"
session_prefix = "__"         # Double underscore for robo tmux sessions
```

---

## Git Worktrees

Shoal creates worktrees in `.worktrees/<name>/`. Branch names follow `<category>/<slug>` format. Allowed categories: `feat`, `fix`, `bug`, `chore`, `docs`, `refactor`, `test`, `plan`, `impl`, `review`, `batch`, `ops`. Worktrees are:

- Created with `git worktree add`
- Auto-cleaned on `shoal wt finish`
- Auto-installed (deps detected from lock files)
- Branch-deleted on finish (unless PR mode)

### Lock File Detection

Auto-install runs on worktree creation for: `bun.lock`, `pnpm-lock.yaml`, `yarn.lock`, `package-lock.json`, `uv.lock`, `Pipfile.lock`, `poetry.lock`

---

## Tool Profiles

Tools are defined in `~/.config/shoal/tools/<tool>.toml`:

```toml
[tool]
name = "pi"
command = "pi"
icon = "pi"               # Or emoji
status_provider = "omp_compat"  # omp_compat | pi | opencode_compat | regex
input_mode = "arg"        # arg | flag | keys
send_keys_delay = 0.05    # Seconds between keystrokes

[detection]
busy_patterns = ["thinking", "generating", "executing"]
waiting_patterns = ["permission", "confirm", "approve"]
error_patterns = ["Error:", "ERROR", "FAILED"]

[mcp]
config_cmd = ""           # CLI command for MCP config
config_file = ""           # Config file path
socket_env = ""            # Environment variable for socket path
```

---

## Workspace Routing

For monorepos with `.shoal/workspace.toml`, route sessions to sub-repos:

```toml
[workspace]
name = "my-monorepo"

[[repos]]
name = "backend"
path = "services/api"
root = "services/api"

[[repos]]
name = "frontend"
path = "apps/web"
root = "apps/web"
```

```bash
# Route to sub-repo
shoal new --repo backend
shoal new --repo frontend -w feat/my-feature
```

---

## Diagnostics

```bash
shoal diag                 # Component health check
shoal check                # Dependency check
shoal init --refresh-tools # Re-download tool profiles
shoal history <session>    # Status transition history
```

---

## Batch Operations

For orchestrating multiple sessions:

```bash
# Via MCP tools (preferred):
spawn_team(workers=[{name: "...", prompt: "..."}])  # Fan-out to parallel worker sessions
wait_for_team(sessions=["worker-1", "worker-2"])    # Poll until all reach terminal state
capture_pane(session="...")                          # Inspect terminal output

# Via CLI (shell scripting):
for name in feature-1 feature-2 feature-3; do
  shoal new $name -t omp -w feat/$name -b &
done
wait
```

---

## Common Workflows

### Feature Development

```bash
# Create feature session
shoal new feature-auth -t omp -w feat/auth -b

# Work in tmux
shoal attach feature-auth
# ... do work ...

# Finish and merge
shoal wt finish feature-auth
```

### Parallel Review

```bash
# Create review sessions for multiple PRs
shoal new pr-123-review -t claude --template claude-review
shoal new pr-124-review -t claude --template claude-review

# Open dashboard to coordinate
shoal popup
```

### Multi-Agent Fan-out

```bash
# Spawn parallel workers for sub-tasks
shoal new auth-impl -t omp -w feat/auth -b
shoal new auth-tests -t claude -w feat/auth-tests -b

# Monitor status
shoal status

# When done, merge
shoal wt finish auth-impl
shoal wt finish auth-tests --pr
```

---

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `Directory does not exist` | Invalid path | Check path or use `--name` for session name |
| `Not a git repository` | No git repo | `git init` or `cd` to git repo |
| `Worktree already exists` | Duplicate worktree | Use `--worktree <name>-v2` or `rm -rf .worktrees/<name>` |
| `Unknown tool 'x'` | Missing tool config | Create `~/.config/shoal/tools/x.toml` |
| `Session not found` | Wrong name/ID | `shoal ls` to find correct identifier |
| `MCP server not running` | Server not started | `shoal mcp start <name>` or `shoal mcp attach <session> <name>` (auto-starts) |

---

## Files and Directories

| Path | Purpose |
|------|---------|
| `~/.config/shoal/` | User config |
| `~/.config/shoal/templates/` | Session templates |
| `~/.config/shoal/tools/` | Tool profiles |
| `~/.config/shoal/mcp-servers.toml` | MCP server registry |
| `~/.config/shoal/mcp-stacks.toml` | MCP server presets |
| `~/.local/share/shoal/` | Runtime data |
| `~/.local/state/shoal/` | State (journals, PIDs) |
| `.worktrees/<name>/` | Git worktrees |
| `.shoal/workspace.toml` | Workspace manifest |

---

## Quick Reference Card

```bash
# Create
shoal new [name] [-t tool] [--template tmpl] [-w worktree] [-b]
shoal new --mode <mode>       # feature-lane | author-review | remote-batch | planner | implementer | reviewer

# List / Status
shoal ls          # All sessions
shoal status      # By urgency
shoal info <name> # Details

# Attach / Detach
shoal attach <name>
shoal detach

# Fork / Kill
shoal fork <src> <dst>
shoal kill <name>

# MCP
shoal mcp ls
shoal mcp start <name>
shoal mcp attach <session> <name>

# Templates
shoal template ls
shoal new --template <tmpl>

# Dashboard
shoal popup

# Worktrees
shoal wt ls
shoal wt finish <session>
shoal wt finish <session> --pr

# Tickets & PRs
shoal ticket sync
shoal ticket pick
shoal ticket start <id>
shoal github review-pr <pr>

# Reports
shoal report weekly

# Proactive
shoal proactive fs-watch start
```

---

## Glossary

| Term | Definition |
|------|------------|
| **Session** | A tracked tmux session in Shoal, optionally paired with a git worktree and MCP servers. Identified by name or ID. |
| **Worktree** | A git worktree (`git worktree add`) that gives a session its own working directory and branch. Isolates parallel work. |
| **Template** | A TOML config that defines the full session layout: tool, windows/panes, env vars, MCP servers, and startup commands. Supports inheritance via `extends` and additive composition via `mixins`. |
| **Mixin** | An additive template fragment that contributes windows, env vars, or MCP servers. Multiple mixins can be applied to a base template. |
| **Tool** | The AI coding agent binary launched in a session (e.g., `claude`, `omp`). Defined in `~/.config/shoal/tools/<name>.toml`. |
| **MCP** | Model Context Protocol. A stdio-based communication protocol for extending AI tools with external capabilities (filesystem, github, memory, etc.). |
| **MCP Pool** | Shoal's shared asyncio pool for MCP servers. One listener per server type; each connection spawns a fresh process. |
| **MCP Proxy** | `shoal-mcp-proxy` bridges stdio-based MCP clients to Unix socket servers in the pool. |
| **MCP Server** | A long-running process that implements the MCP spec and serves tool capabilities to connected clients. |
| **MCP Stack** | A named preset of MCP servers (e.g., `dev` = filesystem + github + memory). |
| **MCP Registry** | `~/.config/shoal/mcp-servers.toml` mapping server names to launch commands for auto-discovery. |
| **Status Detection** | Shoal's polling mechanism that classifies a session's pane output as `running`, `waiting`, `error`, `idle`, or `stopped`. |
| **Robo** | A supervisory AI agent session that monitors the shoal, approves waiting agents, and escalates issues. Configured via `~/.config/shoal/robo/<name>.toml`. |
| **Mode** | A named workflow preset (`feature-lane`, `author-review`, `planner`, etc.) that sets sensible defaults for template, worktree, and branch. |
| **Branch Prefix** | Normalized prefix applied to generated branch names (e.g., `feat/`, `fix/`, `review/`). Enforced by Shoal's naming contract. |
| **Fork** | A new session derived from an existing session, sharing the same tool and optionally creating a new worktree. |
| **Session ID** | UUID assigned to each session at creation. Unique, stable across renames. |
| **Tmux Runtime** | Shoal's mapping of a session to an actual tmux session/window/pane. Used by providers (tmux, etc.) for attach/send/detect operations. |
| **Skill** | A `SKILL.md` file in `.shoal/skills/` that agents read to understand project-specific conventions. |
| **Fish** | The fish shell. Shoal uses fish for its shell integration (prompt, events, completions). |
| **XDG** | XDG Base Directory Specification. Shoal uses `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME` for its config/data/state directories. |

---

## See Also

### Internal References

- [Pantheon AGENTS.md](../../notes/AGENTS.md) — The seven spheres, Mercury routing, session templates by planet
- [Pantheon SCHEMA.md](../../notes/SCHEMA.md) — Note taxonomy, tagging conventions, vault structure
- [Pantheon .shoal/workspace.toml](../../notes/.shoal/workspace.toml) — Workspace manifest for monorepo routing
- [Pantheon skills](../../notes/.shoal/skills/) — Project-local skills for domain-specific conventions

### Shoal CLI Internals

- [CLAUDE.md](./CLAUDE.md) — Developer reference: architecture, module layout, code style, quality gates
- [ARCHITECTURE.md](./ARCHITECTURE.md) — Design decisions, data flow, component relationships
- [CHANGELOG.md](./CHANGELOG.md) — Release history
- [ROADMAP.md](./ROADMAP.md) — Upcoming milestones and session handoff notes

### External

- [MCP Spec](https://modelcontextprotocol.io/) — Model Context Protocol specification
- [tmux(1)](https://man.openbsd.org/tmux.1) — tmux manual
- [git-worktree(1)](https://git-scm.com/docs/git-worktree) — Git worktree documentation
- [Oh My Pi (OMP)](https://github.com/rrii/oh-my-pi) — OMP agent backend
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — Anthropic's AI coding agent
- [OpenCode](https://github.com/opencode-ai/opencode) — OpenAI's coding agent
