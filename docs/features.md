# Features Overview

Comprehensive reference for every major Shoal capability. For a narrative introduction see [Getting Started](getting-started.md). For CLI syntax see [CLI Reference](cli-reference.md).

---

## Session Management

### Create / Fork / Kill

| Command | Notes |
|---------|-------|
| `shoal new` | Create a new session. `-t <tool>`, `-w <worktree>`, `-b` (branch), `--template <name>`, `--mode <name>`, `--model <id>` |
| `shoal fork <src> <dst>` | Fork an existing session into a new worktree with lineage tracking |
| `shoal kill <name>` | Tear down a session, archive its journal, optionally clean its worktree |
| `shoal prune` | Remove stopped sessions from the database |

### Git Worktree Isolation

Each session with `-w` gets its own git worktree under `<repo>/.worktrees/<name>`, on its own branch. Agents can work fully in parallel with no file conflicts.

```bash
shoal new feat-auth -w feat-auth -b          # worktree + branch
shoal new feat-auth -w feat-auth -b --mode impl  # + mode preset
```

`shoal wt ls / finish / cleanup` — manage worktrees directly. See [Worktrees](#git-worktrees).

### Branch Naming

`infer_branch_name` derives the branch from the worktree name and `[template.git].branch_prefix`. Example: `branch_prefix = "fix"` + worktree `cache` → `fix/cache`. An explicit `/` in the worktree name always wins.

### Status Detection

Shoal scrapes tmux pane output to derive session status without modifying agent code. Three provider backends:

| Provider | Used for |
|----------|----------|
| `pi` | oh-my-pi (omp) primary backend |
| `omp_compat` | omp / pisces / opencode compatibility mode |
| `regex` | Generic regex patterns, configurable per tool profile |

Status values: `running`, `waiting`, `error`, `idle`, `stopped`, `completed`

### Urgency Tiers

Sessions are grouped into attention tiers for `shoal status` and `shoal popup`:

| Tier | Conditions |
|------|-----------|
| Needs attention | `error` or `waiting` longer than `blocked_after_minutes` (default 5m) |
| Ready for review | `waiting` within threshold |
| Active | `running` |
| Background | `idle`, `stale` (running > `stale_after_minutes`, default 30m), `stopped` |

Config in `~/.config/shoal/config.toml`:
```toml
[operator]
blocked_after_minutes = 5
stale_after_minutes = 30
```

### Session Graph (Tags, Modes, Parent Tracking)

```bash
shoal tag add <session> <tag>
shoal tag remove <session> <tag>
shoal ls --tag <tag>
shoal ls --tree          # show fork relationships
shoal mode ls            # list available mode presets
```

`parent_id` is recorded automatically on `shoal fork`. `template_name` and `tags` are set at creation and visible in `shoal info`.

---

## Templates & Configuration

### Session Templates

Templates are TOML files that encode tool, windows, MCP servers, env vars, and git config.

Search path (local wins):
1. `<git-root>/.shoal/templates/<name>.toml`
2. `~/.config/shoal/templates/<name>.toml`

```bash
shoal template ls
shoal template show <name>
shoal template validate <path>
shoal config show
```

See [Local Templates](LOCAL_TEMPLATES.md) for the full guide.

!!! note "Template search path"
    Local templates (`.shoal/templates/`) always take precedence over global templates (`~/.config/shoal/templates/`). If a template name exists in both locations, the local file wins.

### Template Inheritance

```toml
# claude-dev.toml
[template]
extends = "base-dev"
mixins = ["mcp-memory", "git-identity"]
tool = "claude"
```

| Mechanism | Behavior |
|-----------|----------|
| `extends` | Single parent; child scalars win, `env` merges, `mcp` unions, `windows` replaced if child sets any |
| `mixins` | Additive — `env` merges, `mcp` unions, `windows` appended |

!!! note "Merge behaviour for `[env]` and `[mcp]`"
    Both `extends` and `mixins` perform a **shallow merge** for `[env]`: child/mixin keys overwrite parent keys of the same name; keys unique to the parent are preserved. For `[mcp]`, entries are **unioned** (deduped by server name). `[windows]` from `extends` is **replaced** if the child defines any windows; for `mixins`, windows are **appended**.

Cycle detection is enforced. Resolution order: extends → mixins → CLI flags.

### `[template.git]` Section

Applied to the worktree at session creation time.

| Field | Effect |
|-------|--------|
| `user_name` | `git config --local user.name` + `GIT_AUTHOR_NAME` / `GIT_COMMITTER_NAME` |
| `user_email` | `git config --local user.email` + `GIT_AUTHOR_EMAIL` / `GIT_COMMITTER_EMAIL` |
| `commit_template` | `git config --local commit.template` |
| `branch_prefix` | Default branch category for `-b` |
| `pre_commit_config` | Path to `.pre-commit-config.yaml` to symlink into the worktree |

```toml
[template.git]
branch_prefix = "fix"
pre_commit_config = "~/.config/shoal/pre-commit-config.yaml"
```

!!! note
    `pre_commit_config` is silently skipped if the source file does not exist.

### `setup_commands`

Commands run via `send-keys` in the initial pane before the agent tool launches.

```toml
[template]
setup_commands = ["uv sync", "source .venv/bin/activate.fish"]
```

### Project-Level `.shoal.toml`

Committed config at the git root. Precedence: project < template < CLI flags.

```toml
# .shoal.toml
default_tool = "omp"
default_template = "base-dev"
setup_commands = ["uv sync"]

[env]
MYAPP_ENV = "dev"
```

---

## Shoal Opinionated Defaults

Shoal makes several choices that are not configurable per-session to keep multi-agent workflows predictable.

| Default | Value | Override |
|---------|-------|----------|
| Worktree base directory | `<repo>/.worktrees/<name>` | Not overridable; set by design |
| Branch naming | `<branch_prefix>/<worktree>` or worktree name | `branch_prefix` in `[template.git]`; explicit `/` in worktree name always wins |
| Status detection poll interval | 2 seconds | `[operator] poll_interval` in `config.toml` |
| Blocked threshold | 5 minutes in `waiting` | `[operator] blocked_after_minutes` |
| Stale threshold | 30 minutes in `running` | `[operator] stale_after_minutes` |

These defaults are designed around solo and small-team usage where session isolation matters more than flexibility.

## Linear ticket routing and PM reports

Shoal can treat Linear as the source of truth for team work while keeping execution inside Shoal sessions.
Team metadata lives in `.shoal/workspace.toml` and is shared by `shoal team`, `shoal ticket`, and `shoal report`.

```toml
[teams.be]
name = "Backend Engineering"
linear_slug = "BE"
default_template = "be-agent"
worktree_dir = "backend"

[teams.be.report]
type = "project"
slug = "backend-roadmap"
```

### Team config

+ Use `shoal team ls` to inspect configured teams, including the Linear key, default template, worktree dir, and report target.
+ `linear_slug` maps a Shoal team slug like `be` to a Linear team key like `BE`.
+ `default_template` and `worktree_dir` let `shoal ticket start` route work into the right template and repo path.
+ `[teams.<slug>.report]` configures where `shoal report sprint --post` publishes updates in Linear.

### Ticket workflow

```bash
shoal ticket ls --team be
shoal ticket start BE-1234
shoal ticket done BE-1234
shoal ticket status
```

`shoal ticket start` resolves the team from the issue prefix, creates a tagged session, and moves the Linear issue into active work. `shoal ticket done` reuses Shoal's handoff flow so the Linear issue gets a PM-readable completion note instead of a raw terminal transcript.

### PM-readable reports

```bash
shoal report session feat-auth
shoal report team --team be
shoal report sprint --team be
shoal report sprint --team be --post
```

Reports compose existing Shoal state instead of introducing a second tracking system: session journals, handoff artifacts, session summaries, and Linear issue data. When a report target is configured, `--post` publishes the rendered sprint summary as a Linear project or initiative update.

---

## MCP Orchestration (`shoal-orchestrator`)

The `shoal-orchestrator` MCP server exposes Shoal's full API to any MCP-capable agent.

```bash
shoal mcp start          # start the pool + orchestrator
shoal mcp stop           # stop all pool servers
shoal mcp status         # inspect running servers
shoal mcp doctor         # protocol-level health check
shoal mcp registry       # show registered servers and transport
```

!!! note "Experimental external autonomy"
    Hermes can drive Shoal over HTTP MCP as an external scheduler/supervisor.
    This path is documented and locally verified for read-only fleet-health
    cron runs, but it remains in development. Keep it local-only, use a
    strict tool whitelist, prefer `session_snapshot` for fleet reads, and
    treat Shoal as the execution control plane rather than the scheduler.


### MCP Tool Reference

#### Session lifecycle

| Tool | Description |
|------|-------------|
| `create_session` | Create a session (respects `branch_prefix` from template) |
| `fork_session` | Fork an existing session into a new worktree |
| `kill_session` | Tear down one or more sessions |
| `list_sessions` | List sessions; accepts `path` filter for git-root scoping |
| `session_info` | Full session metadata |
| `session_status` | Current status of one or more sessions |
| `session_snapshot` | Last N lines of terminal output + status |
| `send_keys` | Send keystrokes to a session |
| `capture_pane` | Read last N lines from a session's pane |

#### Completion & coordination

| Tool | Description |
|------|-------------|
| `mark_complete` | Signal task completion from within a session |
| `wait_for_completion` | Block until a session reaches `completed` |
| `spawn_team` | Fan-out N worker sessions with prompts and a shared `correlation_id` |
| `wait_for_team` | Wait for all workers in a team to complete |

#### Agent history & files

| Tool | Description |
|------|-------------|
| `read_history` | Status transition history for a session |
| `read_worktree_file` | Read a file from a session's worktree (path traversal protected) |
| `list_worktree_files` | Enumerate worktree contents |
| `session_summary` | LLM-generated summary from the session journal |

#### Git

| Tool | Description |
|------|-------------|
| `branch_status` | Current branch, ahead/behind, dirty state |
| `merge_branch` | Merge a session's branch into main |

#### Messaging & actions

| Tool | Description |
|------|-------------|
| `send_session_message` | Send a typed message to another session |
| `receive_session_messages` | Poll unread messages for a session |
| `mark_session_message_consumed` | Acknowledge a message |
| `mark_session_message_acked` | Ack a message that requires acknowledgment |
| `watch_session_messages` | Async generator for incoming messages |
| `get_workflow_messages` | Fetch all messages for a `correlation_id` |
| `request_session_action` | Request a human/robo approval action |
| `list_pending_session_actions` | List unapproved actions |
| `approve_session_action` | Approve an action |
| `deny_session_action` | Deny an action |
| `watch_session_actions` | Async generator for pending actions |

#### Proactive supervision

| Tool | Description |
|------|-------------|
| `get_failure_context` | Retrieve failure context packets stored by Scout; `consume=true` deletes after read |

See [Robo Supervisor](ROBO_GUIDE.md) for orchestration patterns.

---

## Agent Teams

Agents can self-spawn parallel worker sessions using MCP tools — no human required.

```
Supervisor session
 └── spawn_team(workers=["task-a", "task-b", "task-c"], correlation_id="batch-1")
       ├── fork_session → worker-task-a
       ├── fork_session → worker-task-b
       └── fork_session → worker-task-c

wait_for_team(correlation_id="batch-1")  # blocks until all complete
```

Workers signal completion via `mark_complete`. On completion a `worker_completed` message is sent back to the parent session.

!!! tip
    Use `correlation_id` to trace the full workflow across the Agent Bus with `get_workflow_messages`.

---

## Inter-Agent Messaging

The Agent Bus is a SQLite-backed message channel between sessions.

### Message Bus

```bash
shoal proactive message send <src> <dst> "<text>"
shoal proactive message list <session>
```

| MCP Tool | Description |
|----------|-------------|
| `send_session_message` | Send a typed message |
| `receive_session_messages` | Poll unread messages |
| `watch_session_messages` | Streaming poll |
| `get_workflow_messages` | Cross-session trace by `correlation_id` |

### Message kinds

`event`, `request`, `response`, `handoff`, `approval_request`, `approval_decision`, `error`

### Action Bus (approval lifecycle)

```
request_session_action  →  list_pending_session_actions  →  approve_session_action / deny_session_action
```

---

## Robo Supervisor

The Robo watches your fleet and autonomously approves safe waiting states.

```bash
shoal robo watch <profile>            # foreground
shoal robo watch <profile> --daemon   # background
shoal robo watch-stop <profile>
shoal robo watch-status <profile>
```

### Config (`~/.config/shoal/robo/<profile>.toml`)

```toml
[robo]
tool = "omp"
auto_approve = true
poll_interval = 30
waiting_timeout = 300

[escalation]
escalation_session = "robo-supervisor"
escalation_timeout = 120

[[safe_patterns]]
pattern = "Do you want to proceed"
action = "approve"
```

See [Robo Guide](ROBO_GUIDE.md) for full config reference and patterns.

---

## Proactive Supervision (Scout)

Scout listens for `command_failed` lifecycle events emitted by the Watcher and stores failure context packets that agents can query.

!!! note "Scout is opt-in"
    Scout does nothing unless `[proactive] enabled = true` is set in `~/.config/shoal/config.toml`. The config key is **not** created by `shoal init` — add it manually to activate.

### Enable

```toml
# ~/.config/shoal/config.toml
[proactive]
enabled = true
```

```toml
# ~/.config/shoal/robo/<profile>.toml — add to an existing robo profile
[robo.proactive]
auto_enqueue = true
failure_ttl_seconds = 3600   # how long to keep failure packets (default 1h)
trigger_topics = ["command_failed"]
```

### Usage

```bash
shoal proactive fs-watch start   # start watching session worktrees for file changes
shoal proactive fs-watch status  # check watcher state
shoal proactive message send <src> <dst> <text>   # send via Agent Bus
shoal proactive message list <session>            # read messages for a session
```

Agents query failure context via the `get_failure_context` MCP tool (`consume=true` deletes the packet after read).

```python
# Example agent workflow
ctx = get_failure_context(session="feat/auth", consume=True)
# ctx contains: pane_snapshot, old_status, timestamp, session metadata
```

---

## Observability

### Journals

Append-only Markdown files with YAML frontmatter (Obsidian-compatible).

```bash
shoal journal <session>                        # view
shoal journal <session> --append "note"        # append
shoal journal <session> --search <query>       # search all journals
shoal journal <session> --handoff              # generate handoff summary
```

See [Journals](JOURNALS.md).

### Status History

```bash
shoal history <session>
```

Every status transition is recorded in the `status_transitions` SQLite table with a pane snapshot.

### Handoff Packets

```bash
shoal handoff <session>             # print handoff artifact
shoal handoff <session> --json      # JSON output
shoal handoff <session> --save      # save to disk
shoal handoff-ls                    # list saved artifacts
```

Artifacts include: git diff stat, commit count since main, recent journal entries, and suggested next action.

### Dreamer LLM Summarizer

Generates natural-language session summaries using Bedrock or an HTTP AI gateway.

```toml
[dreamer]
[dreamer.ai]
provider = "bedrock"           # bedrock | http | stub
endpoint = ""                  # for http provider
model = "amazon.nova-lite-v1:0"
```

Query via `session_summary` MCP tool or `shoal-status --extended`.

### Web Dashboard

```bash
shoal serve     # start API + dashboard on http://localhost:8080
```

Navigate to `http://localhost:8080/ui` for:
- Fleet overview with live status bar and urgency-tier color coding
- Session detail with journal, terminal pane, and status history tabs
- Real-time WebSocket updates
- JSON API at `/ui/partials/*?format=json`

### FsWatcher

Emits `file_changed` lifecycle events when files in a session's worktree are modified.

```bash
shoal proactive fs-watch start
```

---

## Remote Sessions

Control agent sessions running on a remote machine via SSH tunnel.

```bash
shoal remote connect <host>
shoal remote disconnect <host>
shoal remote ls <host>
shoal remote status <host> <session>
shoal remote send <host> <session> <keys>
shoal remote attach <host> <session>
```

### Config (`~/.config/shoal/config.toml`)

```toml
[remote.myserver]
host = "user@myserver.example.com"
api_port = 8080
```

Remote status bar: `shoal-status --remote <name>` hits `GET /status` on the configured host.

---

## Git & Worktrees

### Worktree Commands

| Command | Purpose |
|---------|---------|
| `shoal wt ls` | List Shoal-managed worktrees |
| `shoal wt finish` | Merge, optionally open PR, clean up |
| `shoal wt cleanup` | Remove stale worktrees (detects orphans in `$CWD/.worktrees/`) |

### Auto-Commit on Kill

```toml
# ~/.config/shoal/config.toml
[general]
auto_commit = true
```

Stages all changes and creates a conventional commit before session teardown.

### Git MCP Tools

`branch_status` and `merge_branch` give robo supervisors git operations without raw `send_keys`.

---

## Skills & Extensions

### Skills

Skills are tool-agnostic `SKILL.md` files that Shoal auto-symlinks into the right location for each agent tool.

```bash
shoal skill ls
```

Search paths:
1. `<git-root>/.shoal/skills/`
2. `~/.config/shoal/skills/`

Auto-symlinked on session creation:
- Claude Code → `.claude/skills/`
- OpenCode → `.opencode/agents/`
- omp → `.omp/skills/`

See [Cross-Agent Skills](cross-agent-skills.md).

### Fins (Extensions)

Fins are self-contained extension packages with a `fin.toml` manifest.

```bash
shoal fin inspect <path>
shoal fin validate <path>
shoal fin install <path|url|fin:name>
shoal fin configure <name>
shoal fin ls
shoal fin run <name> [args]
```

See [Extensions](EXTENSIONS.md).

---

## Fish Integration

```bash
shoal setup fish    # install completions + lifecycle hook templates
```

After setup:
- `__shoal_on_status_changed` — dispatches to per-status handlers
- `__shoal_on_waiting`, `__shoal_on_error`, `__shoal_on_created`, `__shoal_on_killed` — customize in `~/.config/fish/conf.d/shoal-hooks.fish`
- `shoal popup` — fzf session switcher (`ctrl-y` approve, `ctrl-g` fork, `ctrl-w` filter waiting, `ctrl-r` reload)
- `shoal-status` — outputs JSON for Fish prompt status bar segments

See [Fish Integration](FISH_INTEGRATION.md).

---

## Lifecycle Hooks

### Built-in hooks (always active)

- Auto-journal entry on session create and status change
- Fish event emission: `emit shoal_status_changed <name> <status>`
- Status transition recorded to `status_transitions` table

### Project-local hooks (`.shoal/hooks.toml`)

```toml
[[hooks]]
event = "status_changed"
when_status = "waiting"
command = "ntfy publish my-topic 'Agent waiting: $SHOAL_SESSION_NAME'"
```

Env injected: `SHOAL_EVENT`, `SHOAL_SESSION_ID`, `SHOAL_SESSION_NAME`, `SHOAL_OLD_STATUS`, `SHOAL_NEW_STATUS`. Timeout: 30s.

---

## Incidents

Alert-driven multi-agent coordination.

```bash
shoal incident ingest <alert.json>
shoal incident ls
shoal incident show <id>
shoal incident spawn <id> --role investigator
shoal incident resolve <id>
shoal incident hook-scaffold <dir>
```

See [Operator Playbooks](operator-playbooks.md) for incident response patterns.
