# Coding Agent Setup — Maximalist Configuration

**Audience:** You are an AI coding agent (Claude Code, OMP, opencode, Codex, Gemini, or similar) reading this page to configure Shoal on your host machine. Follow every step to unlock every feature: MCP orchestration, session fleet management, Robo supervision, cross-agent skills, auto-commit, git identity isolation, session journals, handoff packets, fish shell integration, and the live dashboard.

Skim nothing. Each section activates a distinct capability.

---

## 1. Prerequisites

Confirm these tools are present before proceeding:

```bash
tmux -V          # 3.2+
git --version    # 2.30+
fish --version   # 3.6+ (optional but required for shell integration)
fzf --version    # any (required for shoal popup / shoal attach)
uv --version     # any (required for Python-based install)
```

If `fish` is absent, install it first (`brew install fish` / `apt install fish`). The status bar and key bindings are unavailable without it.

---

## 2. Install — with all extras

```bash
uv tool install "shoal-cli[mcp]"
```

The `[mcp]` extra activates the `shoal-orchestrator` FastMCP server. Without it the MCP tools (`list_sessions`, `send_keys`, `capture_pane`, etc.) are unavailable to any agent that tries to connect.

Verify the install:

```bash
shoal --version
shoal check       # dependency health check
```

---

## 3. Initialize the control plane

```bash
shoal init                  # scaffold XDG dirs, install bundled tool profiles + templates
shoal setup fish            # install fish completions, key bindings, status bar, helpers
```

`shoal init` writes defaults to `~/.config/shoal/` and `~/.local/state/shoal/`. It also downloads the latest bundled tool profiles. Re-run with `--refresh-tools` after a major Shoal upgrade to pull in new profiles.

`shoal setup fish` installs into `~/.config/fish/`:

| File | Purpose |
|------|---------|
| `completions/shoal.fish` | Tab-complete all commands and live session names |
| `conf.d/shoal.fish` | Auto-loads integration on shell start |
| `functions/shoal-quick-attach.fish` | `Ctrl-F` → fuzzy attach |
| `functions/shoal-dashboard.fish` | `Prefix+S` → popup dashboard |
| `functions/shoal-remote.fish` | Remote host picker |

Source immediately without restarting:

```fish
source ~/.config/fish/conf.d/shoal.fish
```

---

## 4. Global config — `~/.config/shoal/config.toml`

Write this file to enable every global feature:

```toml
[general]
default_tool     = "claude"          # change to your own binary name
worktree_dir     = ".worktrees"      # where git worktrees live, relative to repo root
use_nerd_fonts   = true              # requires a Nerd Font in your terminal
auto_commit      = true              # stage + commit all changes before session kill

[tmux]
session_prefix   = "_"              # sessions appear as _<name> in tmux ls
popup_width      = "90%"
popup_height     = "90%"
popup_key        = "S"              # Prefix+S opens the live dashboard

[status_bar]
max_display      = 8                # sessions shown in fish prompt
separator        = "  "
flash_waiting    = true             # blink indicator when a session needs input

[notifications]
enabled          = true             # macOS osascript alerts for waiting sessions
timeout_seconds  = 120              # fire after 2 minutes of waiting (default is 5)

[robo]
default_tool     = "claude"         # tool the robo supervisor session uses
default_profile  = "default"
session_prefix   = "__"             # robo sessions appear as __<name>
```

`auto_commit = true` is the most important setting for unattended operation: Shoal stages everything in the worktree and creates a conventional commit before tearing down a session, so work is never lost.

---

## 5. Verify your tool profile

`shoal init` installs bundled profiles. Confirm yours is present and correct:

```bash
shoal template ls          # lists tool profiles alongside templates
cat ~/.config/shoal/tools/claude.toml   # or omp.toml / opencode.toml / etc.
```

The fields that matter most for maximalist operation:

| Field | Recommended value | Why |
|-------|-------------------|-----|
| `input_mode` | `"arg"` (Claude/OMP) or `"flag"` (opencode) | Eliminates TUI startup race on prompt delivery |
| `status_provider` | `"pi"` (OMP/Pi), `"opencode_compat"`, or `"regex"` | Accurate status detection without false idle readings |
| `send_keys_delay` | `0.05` | Prevents dropped keystrokes in TUI render window |
| `mcp.config_cmd` | `"claude mcp add"` (Claude), `""` (OMP/file-based) | Enables `shoal mcp attach` automation |

For Claude Code specifically, the bundled `claude.toml` is correct out of the box. Do not modify `status_provider` — `regex` is the only supported mode for Claude Code because it emits no structured status events.

---

## 6. The maximalist session template

Create (or replace) `~/.config/shoal/templates/claude-maximalist.toml`:

```toml
# Maximalist Claude template — all features active.
# Adapt tool = / CLAUDE_MODEL / git fields for your context.

[template]
name        = "claude-maximalist"
description = "All-features Claude session: MCP orchestrator + memory, git identity, test window"
extends     = "base-dev"
tool        = "claude"
# Union-merged with parent MCP list.
# shoal-orchestrator: gives this session the full fleet management tool surface.
# mcp-memory: persistent key/value memory across sessions.
mcp         = ["shoal-orchestrator", "mcp-memory"]
# Mixins appended after extends resolution.
# with-tests: adds a third tmux window pre-configured as a test runner.
# git-identity: stamps agent commits with a distinct author.
# uv-dev: runs `uv sync --extra dev` before agent launch (Python projects).
mixins      = ["with-tests", "git-identity", "uv-dev"]

[template.env]
CLAUDE_MODEL              = "opus"       # override per-session: sonnet / haiku
SHOAL_AGENT               = "1"         # disables pre-commit hooks inside the worktree
CLAUDE_CODE_USE_BEDROCK   = "0"         # set to "1" to route via AWS Bedrock

[template.git]
user_name        = "Shoal Agent"
user_email       = "agent@shoal.local"
branch_prefix    = "feat/"              # shoal new -b → feat/<session-name>

# setup_commands run (via send-keys) in the initial pane before agent launch.
# Use this to hydrate the environment before the agent sees the workspace.
[template]
setup_commands = [
    "git fetch --quiet origin",
    "uv sync --extra dev --quiet",
]

[[windows]]
name  = "agent"
focus = true

[[windows.panes]]
split   = "root"
size    = "65%"
title   = "agent"
command = "{tool_command}"

[[windows.panes]]
split   = "right"
size    = "35%"
title   = "terminal"
command = "echo 'Terminal ready'"

[[windows]]
name = "monitor"

[[windows.panes]]
split   = "root"
title   = "git-log"
command = "git log --oneline --graph --decorate --all"
```

!!! tip "Adapting for other tools"
    Replace `tool = "claude"` with `"omp"`, `"opencode"`, `"codex"`, or `"gemini"`. Remove `CLAUDE_MODEL` and `CLAUDE_CODE_USE_BEDROCK` from `[template.env]`. Everything else carries over unchanged.

---

## 7. Connect the Shoal orchestrator MCP to your own client

For you (the agent) to call Shoal MCP tools — `list_sessions`, `send_keys`, `create_session`, `capture_pane`, etc. — your client must have the orchestrator server registered.

### Claude Code

```bash
# HTTP transport (recommended — no per-session process)
claude mcp add --scope user shoal-orchestrator \
  --transport http http://localhost:8390/mcp/
```

Or add directly to `~/.claude/mcp.json` / `.mcp.json` at the project root:

```json
{
  "mcpServers": {
    "shoal-orchestrator": {
      "type": "http",
      "url": "http://localhost:8390/mcp/"
    }
  }
}
```

Start the server before connecting:

```bash
shoal api start          # launches the FastAPI + MCP server on :8390
```

Or keep it persistent:

```bash
shoal api start --daemon
```

### OMP (oh-my-pi)

Add to `.omp/config.yml` (project-level) or `~/.omp/agent/config.yml` (user-level):

```yaml
mcpServers:
  shoal-orchestrator:
    type: http
    url: http://localhost:8390/mcp/
```

### opencode

Add to `.opencode/config.json`:

```json
{
  "mcpServers": {
    "shoal-orchestrator": {
      "type": "http",
      "url": "http://localhost:8390/mcp/"
    }
  }
}
```

### Verify the connection

```bash
shoal mcp ls          # should list running pool servers
```

From within your agent session, call `list_sessions` via the MCP tool surface to confirm connectivity.

---

## 8. Start the Shoal API server

The MCP orchestrator and the REST API share the same process:

```bash
shoal api start --daemon   # background; writes PID to ~/.local/state/shoal/api.pid
shoal diag                 # confirm all components healthy
```

Add this to your shell's session init (e.g., `.config/fish/conf.d/shoal-autostart.fish`) if you want it always running:

```fish
if not shoal api status --quiet 2>/dev/null
    shoal api start --daemon
end
```

---

## 9. Launch a maximalist session

```bash
shoal new auth-impl \
  --template claude-maximalist \
  --branch \
  --prompt "Implement JWT authentication following the spec in ROADMAP.md"
```

Flags:
- `--branch` / `-b`: create a dedicated `feat/auth-impl` branch in the worktree
- `--prompt`: delivered as a positional arg at launch (`input_mode = "arg"`) — no `send_keys` race

Check it started correctly:

```bash
shoal info auth-impl     # shows: tool, worktree, branch, MCP servers, detection mode
shoal status             # fleet-wide summary
```

---

## 10. Robo supervisor — the fleet manager

The Robo is a dedicated AI session that monitors all worker sessions, approves safe steps, routes tasks, and escalates to you only when judgment is required.

### Setup

```bash
shoal robo setup default --tool claude
shoal robo start default
```

This creates `~/.config/shoal/robo/default.toml` and launches `__default` in tmux with the robo AGENTS.md pre-loaded.

### Attach

```bash
tmux attach -t __default
# or via picker:
shoal attach
```

### What the Robo does

| Event | Robo action |
|-------|-------------|
| Session enters `waiting` | Reads context, approves if safe, escalates if risky |
| Session enters `error` | Inspects pane, decides retry vs. escalate |
| Session goes `idle` | Routes the next task from the backlog |
| Worktree has new commits | Triggers review or merge workflow |

The robo uses the same MCP tools you have — `capture_pane`, `send_keys`, `read_worktree_file`, `append_journal` — to act without attaching to each pane manually.

---

## 11. Cross-agent skills — `.shoal/skills/`

Skills defined once in `.shoal/skills/<name>/SKILL.md` are transpiled into each tool's native format at session creation time. This is the shared source of truth for commands like `/verify`, `/handoff`, and `/scaffold`.

```
your-project/
├── .shoal/
│   └── skills/
│       ├── verify/
│       │   └── SKILL.md
│       └── handoff/
│           └── SKILL.md
├── .claude/
│   └── skills/         ← auto-populated from .shoal/skills/
```

SKILL.md format (same as Claude Code native):

```markdown
---
name: verify
description: Run the full CI pipeline (lint, typecheck, test)
allowed-tools: [Bash]
---

# Verify

Run `just ci` and report the first failing stage.
```

Wire the sync into your template's `setup_commands` or a `post_worktree_create` hook:

```toml
[template]
setup_commands = [
    "mkdir -p .claude/skills && cp -r $(git rev-parse --show-toplevel)/.shoal/skills/* .claude/skills/ 2>/dev/null || true",
]
```

---

## 12. Journals and handoff packets

Every session gets an append-only markdown journal. Use it to track decisions, record progress, and bridge sessions.

### Write from the CLI

```bash
shoal journal auth-impl --append "Implemented refresh token rotation"
shoal journal auth-impl --append "Blocked on rate limiter config" --source robo
```

### Write from within a session via MCP

Call `append_journal` with your session name and the entry text. The source tag defaults to `mcp`.

### Read a journal

```bash
shoal journal auth-impl        # pretty-prints the full journal
```

### Generate a handoff packet

```bash
shoal handoff auth-impl        # structured summary: status, git diff, recent entries, next action
shoal handoff auth-impl --json # machine-readable for programmatic handoff chains
```

Handoff packets are also generated automatically on `shoal kill`. They persist at:

```
~/.local/share/shoal/journals/handoffs/<session_id>.md
```

### Signal completion (from within a session)

When you finish your task, call the `mark_complete` MCP tool with an optional summary. This sets `completed_at`, appends a journal entry, and fires the `session_completed` lifecycle event for supervisors polling `wait_for_completion`.

---

## 13. Fan-out orchestration pattern

When you are acting as the orchestrator (not a worker), use this pattern to run parallel workstreams:

```bash
# Create N workers from the same template
shoal new auth-impl   --template claude-maximalist --branch \
  --prompt "Implement JWT auth — see ROADMAP.md §auth"
shoal new auth-tests  --template claude-maximalist --branch \
  --prompt "Write pytest tests for the JWT auth module once auth-impl lands"

# Poll status
shoal status

# Attach to a specific pane when intervention is needed
shoal attach auth-impl

# Collect results via MCP
# → capture_pane: {session: "auth-impl", lines: 100}
# → read_worktree_file: {session: "auth-impl", path: "src/auth/jwt.py"}

# Kill + auto-commit when done
shoal kill auth-impl
shoal kill auth-tests
```

Cost routing heuristic:

| Task type | Where to run |
|-----------|-------------|
| File edits, grep, refactors with a clear spec | Worker session (free TUI) |
| Architecture decisions, multi-file coordination | Orchestrating agent |
| Commit messages, summaries, trivial Q&A | Orchestrating agent with a smol model |

---

## 14. Unattended operation (fully autonomous)

For sessions that must run without any human at the terminal:

```bash
# Claude Code: skip all permission prompts
shoal new robo-worker --template claude-maximalist \
  --env SHOAL_AGENT=1 \
  --prompt "Refactor the auth module per ARCHITECTURE.md"
```

`SHOAL_AGENT=1` disables pre-commit hooks in the worktree. Pair with `--dangerously-skip-permissions` in the tool command for zero-interruption sessions.

To bake this into your template permanently:

```toml
[template.env]
SHOAL_AGENT = "1"
```

And in `~/.config/shoal/tools/claude.toml`:

```toml
[tool]
command = "claude --dangerously-skip-permissions"
```

!!! warning "Sandbox first"
    `--dangerously-skip-permissions` bypasses all Claude Code safety prompts, including file deletion and shell execution. Run unattended sessions in git worktrees (Shoal's default) so every change is version-controlled and reversible.

---

## 15. Feature checklist

Use this to verify your setup is complete:

| Feature | How to verify |
|---------|--------------|
| Install + MCP extra | `shoal check` reports all green |
| Global config loaded | `shoal diag` shows config path + values |
| Tool profile correct | `cat ~/.config/shoal/tools/<your-tool>.toml` |
| Maximalist template | `shoal template show claude-maximalist` |
| MCP orchestrator registered | `claude mcp list` (or tool equivalent) shows `shoal-orchestrator` |
| API server running | `shoal api status` or `curl http://localhost:8390/health` |
| Fish integration | `shoal status` renders in your fish prompt |
| Robo supervisor | `shoal ls` shows `__default` session |
| Auto-commit | `[general] auto_commit = true` in config.toml |
| Git identity isolated | `git log --format="%ae"` in a worktree shows `agent@shoal.local` |
| Cross-agent skills | `.shoal/skills/` exists; `.claude/skills/` symlinks present |
| Journals active | `shoal journal <session>` prints entries |
| Handoff on kill | `~/.local/share/shoal/journals/handoffs/` populates after `shoal kill` |

---

## Quick reference

```bash
# Session lifecycle
shoal new <name> -t <template> -b --prompt "..."    # create
shoal ls                                             # list all sessions
shoal info <name>                                    # deep session detail
shoal status                                         # fleet summary
shoal popup                                          # interactive dashboard (fzf)
shoal attach <name>                                  # drop into pane
shoal send <name> "some text"                        # send keys to agent
shoal kill <name>                                    # kill + auto-commit + handoff

# Templates
shoal template ls                                    # list global + local templates
shoal template show <name>                           # inspect resolved (merged) template

# Journals + handoffs
shoal journal <name>                                 # read
shoal journal <name> --append "note"                 # write
shoal handoff <name>                                 # generate handoff packet
shoal handoff-ls                                     # list saved artifacts

# Robo
shoal robo setup default --tool claude
shoal robo start default
shoal robo approve <session>

# Diagnostics
shoal diag
shoal check
shoal history <name>
```

---

## Further reading

- [Local Templates](LOCAL_TEMPLATES.md) — per-project template overrides and mixin composition
- [Agent Reference](AGENTS.md) — prompt delivery mechanics, session continuity, and MCP wiring per tool
- [Robo Supervisor Guide](ROBO_GUIDE.md) — full robo workflow patterns
- [Handoffs and Modes](handoffs-and-modes.md) — handoff packet schema and operating modes
- [Cross-Agent Skills](cross-agent-skills.md) — transpilation and `.shoal/skills/` setup
- [Journals](JOURNALS.md) — journal schema, frontmatter, and Obsidian compatibility
- [Fish Integration](FISH_INTEGRATION.md) — key bindings, abbreviations, and status bar config
