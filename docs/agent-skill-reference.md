# Agent Skill Reference

Quick-reference landing page for AI agents operating inside Shoal sessions. Covers every major subcommand group, config schema, and common workflow pattern.

For narrative introduction see [Getting Started](getting-started.md). For full CLI syntax see [CLI Reference](cli-reference.md).

---

## Core Concepts

### Sessions

A **session** is a tmux session + optional git worktree + optional MCP servers, tracked in SQLite. Sessions can be in states: `running`, `waiting`, `error`, `idle`, `stopped`, `completed`.

### Worktrees

Sessions optionally create **git worktrees** (`.worktrees/<name>`) for isolated branch development. Worktrees are auto-cleaned up on session finish and support branch creation.

### Templates

**Templates** define the full session layout: tool, windows/panes, environment variables, MCP servers, and startup commands. Templates support `extends` (inheritance) and `mixins` (additive composition).

### MCP Pool

**MCP servers** run in a shared asyncio pool via Unix sockets. One listener per server type; each connection spawns a fresh process. Servers can be attached to sessions on demand.

### Status Detection

Sessions poll their tmux pane every 5s to detect status (Thinking/Waiting/Error/Idle). OMP sessions use the `omp_compat` provider; legacy Pi sessions used explicit event contracts. Other tools fall back to regex patterns from tool TOML profiles.

---

## Session Lifecycle

```bash
shoal new [name] [-t tool] [--template tmpl] [-w worktree] [-b]
shoal new --mode <mode>   # feature-lane | author-review | remote-batch | planner | implementer | reviewer

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
shoal fork <source-session> <new-name>
shoal fork <source-session> <new-name> --no-worktree   # Share parent's git state
shoal fork <source-session> <new-name> --mcp github,memory
```

### Session Aliases (`shoal session`)

Ergonomic aliases for common operations:

```bash
shoal session list        # = shoal ls
shoal session info <name> # = shoal info
shoal session status      # = shoal status
shoal session attach <name>
shoal session detach
shoal session kill <name>
shoal session prune
shoal session logs <name> # Show session journal log
```

---

## Operating Modes

Modes set sensible defaults for template, worktree prefix, and branch when creating a session:

```bash
shoal mode ls
shoal new --mode feature-lane    # Feature development
shoal new --mode author-review   # Review cycle
shoal new --mode remote-batch    # Batch operations on remote hosts
shoal new --mode planner         # Scope and plan
shoal new --mode implementer     # Execute from plan
shoal new --mode reviewer        # Pre-merge review
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

## Templates

```bash
shoal template ls               # List all available templates
shoal template show <name>      # Show resolved template as JSON
shoal template show <name> --raw
shoal template validate [name]  # Validate one or all templates
shoal template mixins           # List available mixins
```

### Template Structure

```toml
[template]
name = "my-dev"
description = "My development template"
extends = "base-dev"      # Single parent inheritance
mixins = ["mcp-memory"]   # Additive: env, mcp, windows
tool = "omp"

[template.env]
MY_VAR = "value"

[template.worktree]
name = "feat/{session_name}"
create_branch = true
prefix = "feat"

[template.git]
branch_prefix = "feat"

[[windows]]
name = "editor"
focus = true

[[windows.panes]]
split = "root"
size = "65%"
title = "omp-agent"
command = "{tool_command}"

[[windows.panes]]
split = "right"
size = "35%"
title = "terminal"
command = "echo 'Terminal ready'"
```

### Inheritance and Mixin Merge Rules

| Field | `extends` | `mixins` |
|-------|-----------|----------|
| `env` | Merge (child wins) | Merge (mixin wins) |
| `mcp` | Union, deduped | Union, deduped |
| `windows` | Child replaces entirely | Appended |
| `setup_commands` | Child replaces | Appended |

---

## MCP Server Pool

```bash
shoal mcp ls                     # List running MCP servers
shoal mcp start <name>           # Start a pooled server
shoal mcp start <name> --http    # Start with HTTP transport
shoal mcp start <name> --port 8391
shoal mcp stop <name>
shoal mcp status                 # Pool health check
shoal mcp attach <session> <server>   # Auto-start + attach to session
shoal mcp registry               # Show full server registry with transport/url
```

### MCP Stacks

MCP stacks are presets for common server groups (`~/.config/shoal/mcp-stacks.toml`):

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

`shoal-orchestrator` is implicitly added to every new session at creation time — no manual `shoal mcp attach` required.

---

## Ticket Workflows (Linear)

```bash
shoal ticket sync                          # Sync Linear issues to local SQLite cache
shoal ticket pick                          # Interactive fzf picker across teams
shoal ticket pick --json                   # Output selection as JSON
shoal ticket start <identifier>            # Create session from issue (e.g. AIA-469)
shoal ticket decompose <identifier>        # Split parent into child sub-issues (dry-run)
shoal ticket decompose <identifier> --commit  # Create sub-issues in Linear
```

Session names and branch slugs are auto-derived from issue identifier + title and normalized to `feat/<identifier>-<title-slug>` format.

---

## GitHub PR Workflows

```bash
shoal github review-pr <pr-number>    # Spawn review session with full PR context
shoal github post-review <session>    # Post session findings as PR comment
```

---

## Reports

```bash
shoal report session <session>        # Summary for a single session
shoal report team [--team <name>]     # Aggregate sessions by team
shoal report weekly                   # Weekly digest (sessions + Linear + GitHub PRs)
shoal report weekly --week 2026-W15   # Specific ISO week
shoal report weekly --post            # Post sprint update to Linear
```

---

## Worktree Management

```bash
shoal wt ls                          # List managed worktrees
shoal wt finish <session>            # Merge branch + cleanup worktree
shoal wt finish <session> --pr       # Open PR via gh
shoal wt cleanup                     # Remove orphaned worktrees
```

### Git Worktrees

Shoal creates worktrees in `.worktrees/<name>/`. Branch names follow `<category>/<slug>` format.

Allowed categories: `feat`, `fix`, `bug`, `chore`, `docs`, `refactor`, `test`, `plan`, `impl`, `review`, `batch`, `ops`

Lock file auto-install runs on worktree creation for: `bun.lock`, `pnpm-lock.yaml`, `yarn.lock`, `package-lock.json`, `uv.lock`, `Pipfile.lock`, `poetry.lock`

---

## Robo Supervisor

```bash
shoal robo setup <name>              # Create a robo profile
shoal robo setup <name> -t omp       # With specific tool
shoal robo start <name>
shoal robo stop <name>
shoal robo ls
shoal robo status
shoal robo watch
shoal robo approve <session>         # Approve + continue a waiting agent
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
notify = true
auto_respond = false
escalation_session = ""       # Session name to escalate to (optional)
escalation_timeout = 300

[tasks]
log_file = "task-log.md"

[proactive]
auto_enqueue = false          # Spawn implementer session on command failure
failure_ttl_seconds = 3600    # How long to retain failure context packets
trigger_topics = ["command_failed"]
```

---

## Proactive Monitoring

```bash
shoal proactive fs-watch start               # Watch session worktrees for file changes
shoal proactive fs-watch status
shoal proactive message send <session> <msg> # Send a message to a session's Agent Bus
shoal proactive message list <session>       # List unconsumed messages
```

`command_failed` lifecycle events are captured by the Scout supervisor when `proactive.auto_enqueue = true` in the robo profile. Failure context is retrievable via the `get_failure_context` MCP tool.

---

## Batch Operations (MCP)

```python
# Preferred — use MCP tools from within an agent:
spawn_team(workers=[{"name": "worker-1", "prompt": "..."}, ...])
wait_for_team(sessions=["worker-1", "worker-2"])
capture_pane(session="worker-1")

# CLI scripting alternative:
for name in feature-1 feature-2 feature-3; do
  shoal new $name -t omp -w feat/$name -b &
done
wait
```

---

## Skills

See [Skills](skills/index.md) for the full guide covering format, authoring, and cross-tool sharing.

---

## Workspace Routing

For monorepos with `.shoal/workspace.toml`:

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
shoal new --repo backend
shoal new --repo frontend -w feat/my-feature
```

---

## Dashboard

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

Web dashboard at `http://localhost:8080/ui` — MCP Matrix at `/ui/mcp-matrix`.

---

## Configuration

```bash
shoal config paths            # Show resolved XDG directories
shoal config show             # Dump effective config (TOML)
shoal config show --format json
```

### Main Config (`~/.config/shoal/config.toml`)

```toml
[general]
default_tool = "omp"
worktree_dir = ".worktrees"
use_nerd_fonts = true

[tmux]
session_prefix = "_"
popup_width = "90%"
popup_height = "90%"
popup_key = "S"

[status_bar]
max_display = 5
flash_waiting = true

[notifications]
enabled = true
timeout_seconds = 300

[robo]
default_tool = "omp"
default_profile = "default"
session_prefix = "__"
```

---

## Tool Profiles

Tools are defined in `~/.config/shoal/tools/<tool>.toml`:

```toml
[tool]
name = "omp"
command = "omp"
icon = ""
status_provider = "omp_compat"  # omp_compat | pi | opencode_compat | regex
input_mode = "arg"              # arg | flag | keys
send_keys_delay = 0.05

[detection]
busy_patterns = ["thinking", "generating", "executing"]
waiting_patterns = ["permission", "confirm", "approve"]
error_patterns = ["Error:", "ERROR", "FAILED"]

[mcp]
config_cmd = ""
config_file = ""
socket_env = ""
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

## Error Reference

| Error | Cause | Resolution |
|-------|-------|------------|
| `Directory does not exist` | Invalid path | Check path or use `--name` for session name |
| `Not a git repository` | No git repo | `git init` or `cd` to git repo |
| `Worktree already exists` | Duplicate worktree | Use `--worktree <name>-v2` or `rm -rf .worktrees/<name>` |
| `Unknown tool 'x'` | Missing tool config | Create `~/.config/shoal/tools/x.toml` |
| `Session not found` | Wrong name/ID | `shoal ls` to find correct identifier |
| `MCP server not running` | Server not started | `shoal mcp start <name>` or `shoal mcp attach <session> <name>` |

---

## Files and Directories

| Path | Purpose |
|------|---------|
| `~/.config/shoal/` | User config |
| `~/.config/shoal/templates/` | Session templates |
| `~/.config/shoal/tools/` | Tool profiles |
| `~/.config/shoal/mcp-servers.toml` | MCP server registry |
| `~/.config/shoal/mcp-stacks.toml` | MCP server stack presets |
| `~/.local/share/shoal/` | Runtime data (SQLite DB) |
| `~/.local/state/shoal/` | State (journals, PIDs, sockets) |
| `.worktrees/<name>/` | Git worktrees |
| `.shoal/workspace.toml` | Workspace manifest |
| `.shoal/skills/` | Project-local skill definitions |

---

## Glossary

| Term | Definition |
|------|------------|
| **Session** | A tracked tmux session in Shoal, optionally paired with a git worktree and MCP servers. Identified by name or ID. |
| **Worktree** | A git worktree (`git worktree add`) giving a session its own working directory and branch. |
| **Template** | A TOML config defining the full session layout. Supports `extends` (inheritance) and `mixins` (additive composition). |
| **Mixin** | An additive template fragment contributing windows, env vars, or MCP servers. |
| **Tool** | The AI coding agent binary launched in a session (`omp`, `claude`, etc.). Defined in `~/.config/shoal/tools/<name>.toml`. |
| **MCP Pool** | Shoal's shared asyncio pool for MCP servers — one listener per server type. |
| **MCP Proxy** | `shoal-mcp-proxy` bridges stdio MCP clients to Unix socket servers in the pool. |
| **MCP Stack** | A named preset of MCP servers (e.g. `dev` = filesystem + github + memory). |
| **Status Detection** | Polling mechanism classifying pane output as `running`, `waiting`, `error`, `idle`, `stopped`, or `completed`. |
| **Robo** | A supervisory agent session that monitors the shoal, approves waiting agents, and escalates issues. |
| **Mode** | A named workflow preset setting defaults for template, worktree prefix, and branch. |
| **Fork** | A new session derived from an existing session, sharing tool config and optionally creating a new worktree. |
| **Skill** | A `SKILL.md` file in `.shoal/skills/` that agents read for project-specific conventions. |
| **Scout** | The proactive supervisor that captures `command_failed` events and stores failure context for agent retrieval. |
| **Agent Bus** | SQLite-backed session-to-session messaging, accessible via `shoal proactive message` and the `send_session_message` / `receive_session_messages` MCP tools. |
| **XDG** | XDG Base Directory Specification. Shoal uses `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME`. |
