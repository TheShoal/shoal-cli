# CLI Reference

Shoal is a Typer-based CLI with a small set of top-level session commands and feature-specific
subcommand groups.

## Top-level commands

| Command | Purpose |
| ------- | ------- |
|| `shoal new` | Create a new session, optionally with a worktree and branch (branch category uses `template.git.branch_prefix` when set). Supports `--model <<idid>` to override the tool default. |
| `shoal ls` | List sessions, with filters like `--tree` and `--tag` |
| `shoal info` | Show detailed metadata for one session |
| `shoal attach` | Jump into a session |
| `shoal detach` | Detach from the current session |
| `shoal rename` | Rename an existing session |
| `shoal logs` | Read recent terminal output |
| `shoal status` | Show a quick fleet summary |
| `shoal popup` | Open the fzf dashboard (`ctrl-y` approve, `ctrl-g` fork, `ctrl-w` filter waiting, `ctrl-r` reload) |
| `shoal history` | Show status transition history |
| `shoal journal` | Read or append to a session journal |
| `shoal handoff` | Generate a structured handoff summary for a session (`--json`, `--save`) |
| `shoal handoff-ls` | List saved handoff artifacts |
| `shoal done` | Mark a session as completed |
| `shoal diag` | Check component health |
| `shoal init` | Scaffold config and state directories (`--refresh-tools` to re-copy bundled profiles) |
| `shoal check` | Re-run dependency and environment checks |
| `shoal serve` | Start the FastAPI server for HTTP access |
| `shoal team` | Show configured team mappings loaded from `.shoal/workspace.toml` |
| `shoal ticket` | Bind Linear issues to Shoal sessions and track active ticket/session links |
| `shoal report` | Generate PM-readable session, team, and sprint summaries; optionally post sprint updates to Linear |

Hidden aliases exist for speed, including `a` for `attach`, `rm` for `kill`, and `pop` for `popup`.

## Session lifecycle

```bash
shoal new -t claude -w auth -b
shoal fork auth review-auth
shoal rename review-auth review-api
shoal kill review-api
shoal prune
```

Use `new` when you are starting fresh, `fork` when you need lineage from an existing session,
and `prune` to clear stopped sessions from the database after cleanup.

## Worktrees

| Command | Purpose |
| ------- | ------- |
| `shoal wt ls` | List Shoal-managed worktrees |
| `shoal wt finish` | Merge, optionally open a PR, and clean up a worktree |
| `shoal wt cleanup` | Remove stale Shoal worktrees |

## Linear and PM workflows

| Command | Purpose |
| ------- | ------- |
| `shoal team ls` | List configured teams, their Linear keys, templates, worktree dirs, and report targets |
| `shoal ticket ls --team <slug>` | Query Linear for issues in a configured team |
| `shoal ticket start <ISSUE-ID>` | Create a session from a Linear issue and tag it for status sync |
| `shoal ticket done [ISSUE-ID]` | Generate a handoff, update Linear, and finish the linked session workflow |
| `shoal ticket status` | Show active Linear-to-session bindings from session tags |
| `shoal report session <name>` | Summarize one session using journals, handoff context, and Dreamer summaries |
| `shoal report team --team <slug>` | Summarize active work across a configured team |
| `shoal report sprint --team <slug>` | Build a sprint summary from session state and Linear issue data |
| `shoal report sprint --team <slug> --post` | Publish the sprint report to the team's configured Linear project or initiative |

`shoal ticket` and `shoal report` both resolve team metadata from `[teams.<slug>]` blocks in `.shoal/workspace.toml`. To enable `--post`, add a `[teams.<slug>.report]` block with `type = "project" | "initiative"` and exactly one selector: `id`, `slug`, or `name`.
## MCP pool

| Command | Purpose |
| ------- | ------- |
| `shoal mcp ls` | List configured MCP servers |
| `shoal mcp start` | Start the shared MCP pool |
| `shoal mcp stop` | Stop pool processes |
| `shoal mcp attach` | Attach a server to a session |
| `shoal mcp status` | Inspect runtime state |
| `shoal mcp logs` | Read server logs |
| `shoal mcp doctor` | Run protocol-level diagnostics |
| `shoal mcp registry` | Inspect transport and registry data |

## Robo automation

| Command | Purpose |
| ------- | ------- |
| `shoal robo setup` | Create or update robo profile scaffolding |
| `shoal robo start` | Start a robo worker session |
| `shoal robo stop` | Stop a robo worker |
| `shoal robo send` | Send instructions to robo |
| `shoal robo approve` | Approve a pending action |
| `shoal robo status` | Inspect a robo worker |
| `shoal robo ls` | List robo workers |
| `shoal robo watch` | Start supervision loop |
| `shoal robo watch-stop` | Stop watcher mode |
| `shoal robo watch-status` | Check watcher health |

For patterns and safety rules, read [Robo Supervisor](ROBO_GUIDE.md).

## Remote control

| Command | Purpose |
| ------- | ------- |
| `shoal remote connect` | Open an SSH tunnel to a remote host |
| `shoal remote disconnect` | Tear down the tunnel |
| `shoal remote status` | Inspect the remote control-plane state |
| `shoal remote sessions` | List sessions on a remote host |
| `shoal remote send` | Send keys to a remote session |
| `shoal remote attach` | Attach to a remote session |

See [Remote Sessions](REMOTE_GUIDE.md) for config and tunnel setup.

## Web dashboard

```bash
shoal serve
```

Starts the FastAPI server (default: `http://localhost:8080`). Navigate to `http://localhost:8080/ui` for the fleet dashboard with live WebSocket updates, session detail, pane capture, and urgency-tier color coding.

## Proactive supervision

| Command | Purpose |
| ------- | ------- |
| `shoal proactive fs-watch start` | Start the FsWatcher — emits `file_changed` events per session worktree |
| `shoal proactive fs-watch status` | Check watcher state |
| `shoal proactive message send <src> <dst> <text>` | Send a message via the Agent Bus |
| `shoal proactive message list <session>` | List messages for a session |

!!! note "Enable Scout"
    Proactive supervision requires `[proactive] enabled = true` in `~/.config/shoal/config.toml` and a robo profile with `[robo.proactive] auto_enqueue = true`.

## Operating modes

| Command | Purpose |
| ------- | ------- |
| `shoal mode ls` | List available operating modes with templates, prefixes, and auto-tags |

Modes are single-session presets for `shoal new --mode <name>`. See [Handoffs & Modes](handoffs-and-modes.md) for details.

## Incidents

| Command | Purpose |
| ------- | ------- |
| `shoal incident ingest` | Ingest an alert JSON payload and create an incident record |
| `shoal incident ls` | List incidents |
| `shoal incident show` | Show incident details |
| `shoal incident spawn` | Spawn a worker lane for an incident |
| `shoal incident resolve` | Resolve an incident |
| `shoal incident hook-scaffold` | Scaffold example Claude hook files to a directory |

## Skills

| Command | Purpose |
| ------- | ------- |
| `shoal skill ls` | List discovered skills from project-local and global paths |

Skills in `.shoal/skills/<name>/SKILL.md` are auto-symlinked into `.claude/skills/` for Claude Code sessions. See [Cross-Agent Skills](cross-agent-skills.md) for details.

## Templates, tags, and config

| Command | Purpose |
| ------- | ------- |
| `shoal template ls` | List available templates |
| `shoal template show` | Render an expanded template |
| `shoal template validate` | Validate a template file |
| `shoal template mixins` | List mixins available to templates |
| `shoal tag add` | Add a tag to a session |
| `shoal tag remove` | Remove a tag from a session |
| `shoal tag ls` | List tags for sessions |
| `shoal config show` | Render merged configuration |
| `shoal config paths` | Show config, state, and runtime paths |


### Template git config

Templates can declare a `[template.git]` block that Shoal applies to the worktree at session creation:

| Field | Effect |
|---|---|
| `user_name` | Scopes `git config --local user.name`; exports `GIT_AUTHOR_NAME` / `GIT_COMMITTER_NAME` |
| `user_email` | Scopes `git config --local user.email`; exports `GIT_AUTHOR_EMAIL` / `GIT_COMMITTER_EMAIL` |
| `commit_template` | Scopes `git config --local commit.template` |
| `branch_prefix` | Default branch category for `-b` (e.g. `"fix"` → `fix/<worktree>`). Explicit `/` in worktree name always wins. |

See [Local Templates — Per-Session Git Identity](LOCAL_TEMPLATES.md#per-session-git-identity).

## MCP Tools reference

Key tools exposed by `shoal-orchestrator` beyond what `shoal mcp ls` shows:

| Tool | Category | Notes |
|------|----------|-------|
| `create_session` | lifecycle | Respects `branch_prefix` from template |
| `fork_session` | lifecycle | Agents can self-spawn worker sessions |
| `spawn_team` | teams | Fan-out N workers with shared `correlation_id` |
| `wait_for_team` | teams | Block until all team workers complete |
| `send_keys` | lifecycle | Auto-appends Enter for Claude Code tool profile |
| `capture_pane` | lifecycle | Read last N lines of terminal output |
| `session_snapshot` | lifecycle | Status + last 50 pane lines |
| `mark_complete` | completion | Signal task done from within a session |
| `wait_for_completion` | completion | Block until `completed` status |
| `read_history` | observability | Status transition timeline |
| `read_worktree_file` | files | Path-traversal-protected file read |
| `list_worktree_files` | files | Enumerate worktree |
| `merge_branch` | git | Merge session branch into main |
| `branch_status` | git | Branch, ahead/behind, dirty state |
| `session_summary` | dreamer | Dreamer LLM summary |
| `get_failure_context` | proactive | Scout failure context packet (`consume` flag) |
| `send_session_message` | messaging | Agent Bus send |
| `receive_session_messages` | messaging | Poll unread messages |
| `get_workflow_messages` | messaging | Trace by `correlation_id` |
| `request_session_action` | actions | Request approval |
| `approve_session_action` | actions | Approve pending action |
| `deny_session_action` | actions | Deny pending action |

## Extensions and integrations

| Command | Purpose |
| ------- | ------- |
| `shoal fin inspect` | Inspect a fin manifest |
| `shoal fin validate` | Validate a fin package |
| `shoal fin install` | Install a fin and register it locally (use `--no-register` to skip registration) |
| `shoal fin configure` | Run fin configure entrypoint |
| `shoal fin ls` | List registered fins (default) or discover from a path with `--path` |
| `shoal fin run` | Execute a fin |
| `shoal nvim send` | Send content to Neovim |
| `shoal nvim diagnostics` | Inspect Neovim integration |
| `shoal watcher start` | Start background status watcher |
| `shoal watcher stop` | Stop watcher |
| `shoal watcher status` | Check watcher status |
| `shoal demo ...` | Launch or step through the guided demo |

## Setup

| Command | Purpose |
| ------- | ------- |
| `shoal setup fish` | Install fish shell integration |

## Recommended operator flow

1. Run `shoal init` on a fresh machine. Use `shoal init --refresh-tools` after upgrading to pick up revised tool profiles.
2. Use `shoal new` or `shoal fork` to create isolated sessions.
3. Monitor the fleet with `shoal status` or `shoal popup`.
4. Add `shoal mcp`, `shoal robo`, or `shoal remote` only when the base loop is stable.