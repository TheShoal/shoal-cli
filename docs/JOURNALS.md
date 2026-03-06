# Session Journals

**Journals** are append-only markdown logs attached to Shoal sessions. Each session gets one journal file that captures decisions, progress notes, and context — from the CLI, MCP tools, or the robo supervisor.

---

## Quick Start

### View a session's journal

```bash
shoal journal my-session
```

### Append an entry

```bash
shoal journal my-session --append "Implemented the auth endpoint"
```

### Append with a source tag

```bash
shoal journal my-session -a "Fixed cache invalidation" --source robo
```

---

## How It Works

Journals are created lazily on first write. Each entry is a markdown section:

```markdown
## 2026-02-24T10:15:32+00:00 [cli]

Implemented the auth endpoint

---
```

The `[source]` tag identifies where the entry came from: `cli`, `mcp`, `robo`, or any custom string.

### Storage

| Path | Purpose |
|------|---------|
| `~/.local/share/shoal/journals/<session_id>.md` | Active journal |
| `~/.local/share/shoal/journals/archive/<session_id>.md` | Archived (after `shoal kill`) |

### YAML Frontmatter

On first write, Shoal writes Obsidian-compatible YAML frontmatter:

```yaml
---
session_id: a1b2c3d4-...
title: my-session
aliases: [my-session]
tool: opencode
branch: feat/auth
worktree: /repo/.worktrees/my-session
git_root: /repo
created: 2026-02-24T10:00:00+00:00
tags: [shoal, my-session, opencode]
hostname: my-machine
platform: Darwin
python: 3.12.3
shoal_version: 0.17.0
---
```

This makes journal files directly browsable in Obsidian or any markdown tool that reads frontmatter.

---

## CLI Reference

```bash
# View all entries
shoal journal <session>

# View last N entries
shoal journal <session> --limit 5
shoal journal <session> -n 5

# Append an entry
shoal journal <session> --append "your note here"
shoal journal <session> -a "your note here"

# Append with custom source tag
shoal journal <session> -a "note" --source robo
```

---

## MCP Tools

Two journal tools are exposed via the `shoal-orchestrator` MCP server, making journals accessible to any MCP-connected agent.

### `append_journal`

Append an entry to a session's journal. Creates the journal (with frontmatter) if it doesn't exist.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | string | required | Session name or ID |
| `entry` | string | required | Entry content |
| `source` | string | `"mcp"` | Source tag |

### `read_journal`

Read entries from a session's journal, newest last.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | string | required | Session name or ID |
| `limit` | int | `10` | Number of recent entries to return |

Returns a list of `{"timestamp": "...", "source": "...", "content": "..."}` objects.

---

## Lifecycle

1. **Created** on first `append_entry()` — from CLI (`--append`), MCP tool, or programmatically
2. **Frontmatter written once** at creation time with session metadata
3. **Appended** throughout the session's life
4. **Archived** automatically when the session is killed (`shoal kill`)

The archived journal moves from `journals/<id>.md` to `journals/archive/<id>.md`. The `kill_session` MCP tool returns `journal_archived: true` on success.

### Size Warning

Journals have an advisory 1 MB size threshold. When a write pushes the file past this limit, Shoal logs a warning but does not block the write. If you see journals growing large, consider starting a fresh session.

---

## Robo Integration

Journals are particularly useful with the [Robo Supervisor](ROBO_GUIDE.md). A robo agent can use the MCP tools to:

- Log decisions and approvals to worker journals
- Read worker journals to understand context before sending commands
- Build a persistent record of multi-agent coordination

Example robo instruction:

```markdown
Before approving any session, read its journal with `read_journal` to
understand what it has been working on. After approving, append a note
with `append_journal` explaining your reasoning.
```

---

## Further Reading

- [Robo Supervisor Guide](ROBO_GUIDE.md) — Coordination patterns using journals
- [Shoal Overview](index.md) — Overview of Shoal
