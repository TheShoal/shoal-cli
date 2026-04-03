# Shoal PM Brain — Simplified Plan

## Vision

Shoal becomes the bridge between **Linear (PM intent)** and **AI agent sessions (implementation)**. Three modules, no new dependencies, built on existing infrastructure.

Linear is the source of truth. Shoal wraps, doesn't replace.

---

## Core Insight: What Shoal Already Has

Before adding anything, recognize the existing pieces:

| Existing Capability | Relevant To |
|---|---|
| 34 MCP tools (session orchestration) | Agent coordination is solved |
| Lifecycle hooks (`.shoal/hooks.toml`) | Status sync triggers already work |
| Dreamer service (log tail + LLM summarization) | Report generation engine |
| Journal system (per-session structured log) | Execution history |
| Handoff system (`shoal handoff`) | Sprint review data source |
| Template inheritance + mixins | Team-specific agent configs |
| Workspace routing (`WorkspaceConfig`) | Meta-repo session creation |
| Robo supervisor (Scout) | Autonomous session management |
| Linear MCP server (external, 50+ tools) | Linear API access is already available |

The plan adds *composition* of these pieces, not new infrastructure.

---

## Module 1: `shoal ticket` — Linear-to-Session Bridge

The core value proposition. Binds Linear issues to shoal sessions.

### Commands

```bash
shoal ticket ls --team be             # Query Linear for team's ready issues
shoal ticket ls --team be --mine      # My assigned, ready to work
shoal ticket start BE-1234            # Create session + tag linear:BE-1234 + set Linear "In Progress"
shoal ticket done [BE-1234]           # Complete session + update Linear + generate handoff
shoal ticket status                   # Show all active ticket<>session bindings
```

### How It Works

**`shoal ticket ls`** queries Linear via the Linear MCP tools (already connected). Filters by team config's `linear_slug`, shows priority/status/assignee. No new API client needed.

**`shoal ticket start BE-1234`**:
1. Fetches issue details from Linear (title, description, labels)
2. Resolves team from issue's team prefix (BE- -> be team config)
3. Calls `shoal new` with team's `default_template`, branch name from Linear's suggested branch
4. Tags session with `linear:BE-1234`
5. Injects issue context into session journal (first entry)
6. Updates Linear issue status to "In Progress"

**`shoal ticket done`**:
1. Generates handoff (existing `shoal handoff` logic)
2. Posts handoff summary as Linear issue comment
3. Updates Linear status to "In Review" or "Done" (configurable)
4. If session has a PR, links it to the Linear issue

**`shoal ticket status`**: Reads session tags, cross-references with Linear to show a unified table.

### Implementation

- New CLI group: `src/shoal/cli/ticket.py`
- New service: `src/shoal/services/linear_bridge.py` — thin layer over Linear MCP calls
- Extend `SessionState` tags or metadata to store `linear_issue_id`
- Two lifecycle hooks:
  - `session_completed` -> update Linear status
  - `session_created` (when via ticket start) -> update Linear status

### What This Replaces

- `scripts/beads/pick-ticket` (issue selection)
- `scripts/beads/bd-worktree` (session creation from ticket)
- `scripts/beads/linear-status-update` (status sync)
- Manual Linear status management

---

## Module 2: `shoal report` — AI-Generated Summaries

Composes existing data (journals, Dreamer summaries, Linear queries) into PM-readable reports.

### Commands

```bash
shoal report session <name>           # Summary of one session's work
shoal report team --team be           # Current status across all active sessions
shoal report sprint --team be         # Sprint summary from Linear cycle data + session journals
shoal report sprint --team be --post  # Same, but post as Linear project update
```

### How It Works

**`shoal report session`**: Already 90% exists as `session_summary_tool` in MCP. CLI wrapper + better formatting.

**`shoal report team`**:
1. List active sessions tagged with team (from session DB)
2. Collect journal entries + Dreamer summaries for each
3. Query Linear for team's current cycle stats (via Linear MCP)
4. Feed to LLM with a report template prompt
5. Output formatted Markdown

**`shoal report sprint`**:
1. Query Linear for cycle's completed/in-progress/blocked issues
2. Pull session journals for completed sessions in this cycle
3. Aggregate: velocity, wins, blockers, risks
4. Generate Markdown report
5. Optional: post as Linear project status update (`--post`)

### Implementation

- New CLI group: `src/shoal/cli/report.py`
- New service: `src/shoal/services/report.py` — data collection + LLM composition
- Uses existing `ai_client` (Dreamer's LLM infrastructure) for generation
- Report templates as prompt constants in `src/shoal/services/report_prompts.py`

### What This Replaces

- Manual sprint review preparation
- Manual status update writing
- Slack copy-paste workflows

---

## Module 3: `shoal team` — Team Configuration

Minimal config extension. Maps team slugs to Linear IDs, templates, and workspace paths.

### Config

```toml
# In .shoal/workspace.toml or ~/.config/shoal/config.toml

[teams.be]
name = "Backend Engineering"
linear_slug = "BE"
default_template = "usm-be-agent"
worktree_dir = "backend"

[teams.fe]
name = "Frontend"
linear_slug = "FE"
default_template = "usm-fe-agent"
worktree_dir = "frontend"

[teams.aia]
name = "AI/Agents"
linear_slug = "AIA"
default_template = "usm-be-agent"
worktree_dir = "ai-monorepo"
```

### Commands

```bash
shoal team ls                         # Show configured teams + Linear connection status
```

That's it. No interactive wizards, no `team add`. Edit the TOML directly.

### Implementation

- New model: `TeamConfig` in `src/shoal/models/config/workspace.py` (extend existing file)
- Parse from `[teams.*]` section in workspace config
- Used by `shoal ticket` and `shoal report` for routing

---

## Not Modules — Just Templates

### PM Agent

```toml
# .shoal/templates/pm-agent.toml
[template]
name = "pm-agent"
description = "AI PM agent with Linear + Shoal context"
tool = "omp"
mode = "planner"

[template.mcp]
servers = ["linear", "shoal-orchestrator"]

[template.env]
SHOAL_ROLE = "pm"
```

Usage: `shoal new -t pm-agent` — no `shoal pm` command needed.

### Incident Supervisor (already exists)

`shoal incident` already handles multi-lane orchestration. The PM brain doesn't need to reinvent this.

---

## What We're NOT Building

| Dropped | Why |
|---|---|
| `shoal linear` (full CLI) | Linear MCP already covers all API operations |
| `shoal sync` (beads bidirectional sync) | Beads is external with its own Dolt DB; shoal sessions + journals + tags replace the need |
| `shoal sprint` (ceremony orchestration) | `shoal report sprint` covers the data; ceremonies happen in meetings |
| `shoal spec` (OpenSpec lifecycle) | Document management is out of scope; stays in smorgasbord |
| `shoal pm` (dedicated command) | It's a template, not a command |
| Slack integration | Belongs in hooks or external scripts, not core CLI |
| Beads dependency | Shoal sessions ARE the fine-grained units; no third tracking system |

---

## Implementation Phases

### Phase 1: `shoal ticket` + Team Config (v0.39.0)

Target: Linear issues bind to shoal sessions. Status flows both directions.

- [ ] `TeamConfig` model (extend `WorkspaceConfig`)
- [ ] `shoal team ls` command
- [ ] `src/shoal/services/linear_bridge.py` — Linear MCP query wrapper
- [ ] `shoal ticket ls --team <slug>` — list ready issues
- [ ] `shoal ticket start <issue-id>` — create session from Linear issue
- [ ] `shoal ticket done [<issue-id>]` — complete + update Linear
- [ ] `shoal ticket status` — active bindings table
- [ ] Lifecycle hook: `session_completed` -> Linear status update
- [ ] Tests for linear_bridge, ticket CLI, team config

### Phase 2: `shoal report` (v0.40.0)

Target: AI-generated reports from existing data sources.

- [ ] `shoal report session <name>` — single session summary (CLI wrap of existing MCP tool)
- [ ] `shoal report team --team <slug>` — cross-session team status
- [ ] `shoal report sprint --team <slug>` — cycle summary from Linear + journals
- [ ] `--post` flag to publish as Linear project status update
- [ ] Report prompt templates
- [ ] Tests for report generation

### Phase 3: Autonomous Dispatch (v0.41.0+)

Target: Robo supervisor auto-spawns sessions from Linear ticket queue.

- [ ] Scout polls `shoal ticket ls --ready` for configured teams
- [ ] Auto-creates sessions for high-priority unblocked issues
- [ ] Respects concurrency limits per team
- [ ] Surfaces in dashboard as "auto-dispatched" sessions

---

## Dependency Map

```
Phase 1                    Phase 2                    Phase 3
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│ TeamConfig model │─────>│ shoal report     │      │ Scout dispatch  │
│ linear_bridge    │─────>│  (uses bridge +  │      │  (uses ticket ls │
│ shoal ticket     │      │   journals +     │      │   + shoal new)   │
│ lifecycle hooks  │      │   Dreamer)       │      │                  │
└──────────────────┘      └──────────────────┘      └──────────────────┘
        │                         │                         │
        v                         v                         v
  [Linear MCP]             [AI Client]              [Robo Supervisor]
  [Session DB]             [Linear MCP]              [Linear MCP]
  [Lifecycle]              [Journal DB]              [Lifecycle]
```

Each phase is independently shippable. Phase 3 is the payoff but Phase 1 alone is useful.
