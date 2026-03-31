# Handoff Packets & Operating Modes

Shoal generates structured handoff artifacts when sessions end and supports named operating modes that wire up templates, tags, and worktree conventions automatically.

---

## Handoff Packets

A **handoff packet** is a structured summary of a session's state, recent activity, git context, and suggested next action. Handoffs bridge the gap between one session ending and the next operator (human or agent) picking up the work.

### When handoffs are generated

- **Automatically on kill**: Every `shoal kill` generates a handoff artifact before archiving the journal.
- **On demand**: `shoal handoff <session>` generates a live handoff for a running session.

### CLI commands

```bash
# Generate and display a handoff summary
shoal handoff my-session

# Output as JSON (for programmatic consumption)
shoal handoff my-session --json

# Save artifact to disk without displaying
shoal handoff my-session --save

# List all saved handoff artifacts
shoal handoff-ls
```

### What's in a handoff

| Field | Source |
|-------|--------|
| Session name, tool, branch | Session state |
| Status + urgency label | Urgency derivation (error > blocked > waiting > review > running > stale > idle) |
| Time in status | `status_since` field |
| Worktree path | Session worktree |
| Git diff summary | `git diff --stat HEAD` in worktree |
| Commit count | Commits since diverging from main |
| Recent transitions | Last 5 status changes from DB |
| Recent journal entries | Last 5 journal entries |
| Suggested next action | Based on urgency tier |

### Storage

Handoff artifacts are saved as markdown files:

```
~/.local/share/shoal/journals/handoffs/<session_id>.md
```

The `shoal journal <session> --handoff` flag also generates handoffs (backward-compatible alias).

---

## Operating Modes

Modes are named presets that configure template, tool, worktree prefix, and auto-tags for common workflows. They reduce boilerplate when creating sessions.

### Available modes

```bash
shoal mode ls
```

| Mode | Description | Prefix | Auto-tags |
|------|-------------|--------|-----------|
| `feature-lane` | Default feature development | `feat/` | — |
| `author-review` | Author-review cycle | `review/` | `review-ready` |
| `remote-batch` | Batch operations on remote hosts | `batch/` | — |
| `planner` | Scope and plan work | `plan/` | `planner` |
| `implementer` | Execute implementation from a plan | `impl/` | `implementer` |
| `reviewer` | Review changes before merge | `review/` | `reviewer`, `review-ready` |

### Usage

```bash
# Create a planner session with auto-tags and worktree prefix
shoal new --mode planner -w plan/auth-redesign -b

# Combine with a specific template
shoal new --mode reviewer --template haiku-reviewer -w review/pr-42 -b

# Modes only fill in defaults — explicit flags always win
shoal new --mode feature-lane --tool pi -w feat/custom -b
```

### Auto-tagging

When a mode or template specifies tags, they are automatically applied to the session at creation time:

1. **Template tags** from `template.tags` (e.g., `["dogfood", "haiku"]`)
2. **Mode auto-tags** from the mode spec (e.g., `["reviewer", "review-ready"]`)
3. Merged, deduplicated, applied to the session

Tags affect urgency: sessions tagged `review-ready` are promoted to the **review** urgency tier.

---

## Template Tags & Mode Field

Templates can declare `tags` and `mode` fields:

```toml
[template]
name = "haiku-reviewer"
description = "Claude Haiku reviewer"
extends = "base-dev"
tool = "claude"
mode = "reviewer"
tags = ["dogfood", "haiku", "reviewer", "review-ready"]

[template.env]
CLAUDE_MODEL = "haiku"
```

### Inheritance behavior

- **`tags`**: Union-merged with parent template tags, sorted.
- **`mode`**: Child wins if explicitly set; otherwise inherits from parent.
- Both fields follow the same inheritance rules as `env` and `mcp`.

### Unattended sessions with Bedrock

For cheap, unattended dogfooding with Claude Haiku via AWS Bedrock:

```toml
[template]
name = "haiku-bedrock-dev"
extends = "base-dev"
tool = "claude"
tags = ["dogfood", "haiku", "bedrock"]

[template.env]
CLAUDE_MODEL = "haiku"
CLAUDE_CODE_USE_BEDROCK = "1"
```

Pair with a tool profile that skips permissions:

```toml
# ~/.config/shoal/tools/claude-yolo.toml
[tool]
name = "claude-yolo"
command = "claude --dangerously-skip-permissions"
input_mode = "arg"
send_keys_delay = 0.05
```
