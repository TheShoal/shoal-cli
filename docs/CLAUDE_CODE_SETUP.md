# Claude Code Setup for Shoal Development

This guide covers the Claude Code configuration that ships with the shoal repository. These tools automate quality checks, provide project context, and make Claude more effective at writing production-level shoal code.

---

## What's Included

```
.claude/
├── settings.json              # Shared hooks (auto-format, compact recovery)
├── settings.local.json        # Personal permissions (gitignored)
├── agents/
│   └── shoal-test-runner.md   # Haiku-based test runner subagent
└── skills/
    ├── shoal-verify/
    │   └── SKILL.md           # /shoal-verify slash command
    └── shoal-handoff/
        └── SKILL.md           # /shoal-handoff slash command

CLAUDE.md                      # Project context (conventions, commands, architecture)
.mcp.json                      # MCP server configuration (scaffold)
```

---

## CLAUDE.md — Project Context

The root `CLAUDE.md` gives Claude essential project knowledge on every session start:

- **Build commands**: `just ci`, `just test`, `just lint`, etc.
- **Code style**: 100-char lines, mandatory type hints, ruff lint rules
- **Module layout**: One-line description of each top-level package
- **Architectural invariants**: SQLite WAL mode, lifecycle service pattern, MCP pooling
- **Gotchas**: Fish template validation, hatchling build backend, MCP pool semantics

It also uses `@imports` to pull in `ARCHITECTURE.md` and `COMMIT_GUIDELINES.md` when Claude needs deeper context.

**Maintenance**: If Claude keeps making the same mistake, add a rule to `CLAUDE.md`. If a rule isn't preventing mistakes, remove it. Keep it under 100 lines.

---

## Hooks

Hooks are defined in `.claude/settings.json` and run automatically at specific lifecycle points.

### Auto-Format (PostToolUse)

**Trigger**: After every `Edit` or `Write` tool call on a `.py` file.

**What it does**: Runs `ruff format` and `ruff check --fix` on the edited file. This means:
- Code is always formatted before you see it
- Simple lint issues (unused imports, import ordering) are fixed automatically
- Pre-commit hooks won't fail on formatting issues

You don't need to do anything — this runs silently in the background.

### Compact Recovery (SessionStart)

**Trigger**: After Claude's context window compacts (long sessions).

**What it does**: Re-injects a reminder that this is the shoal project with key commands and conventions. Without this, Claude can "forget" project context after compaction and start guessing at conventions.

---

## /shoal-verify — CI Pipeline Skill

Run the full CI pipeline or targeted checks from within Claude Code.

### Usage

```
/shoal-verify              # Full pipeline: lint → typecheck → test → fish-check
/shoal-verify lint         # Ruff lint only
/shoal-verify typecheck    # mypy --strict only
/shoal-verify test         # Unit tests only (excludes integration)
/shoal-verify test-all     # All tests including integration
/shoal-verify cov          # Tests with coverage report
/shoal-verify fish         # Fish template syntax validation
```

### When to Use

- After finishing a feature or fix, before committing
- When you want Claude to run checks and interpret the results (not just raw output)
- As a quick sanity check mid-session

---

## /shoal-handoff — Session Continuity Skill

Pick up where the last session left off, or record what you did for the next session.

### Usage

```
/shoal-handoff             # Read the latest handoff and upcoming work
/shoal-handoff update      # Write a new handoff entry for this session
```

### How It Works

The handoff section lives at the bottom of `ROADMAP.md`. Each Claude Code session that does significant work should write a handoff entry before ending. The next session starts with `/shoal-handoff` to understand context without re-reading the entire codebase.

Each entry records:
- **What we did**: Concrete accomplishments (commits, features, test counts)
- **What to do next**: Prioritized action items for the next session

---

## shoal-test-runner — Subagent

A lightweight test runner that Claude delegates to automatically after code changes.

### How It Works

- **Model**: Haiku (fast and cheap — won't burn through your token budget)
- **Trigger**: Claude invokes it proactively when you modify Python files
- **Behavior**: Maps changed source files to their test files and runs targeted tests

### File-to-Test Mapping

| Source | Test |
|--------|------|
| `src/shoal/services/lifecycle.py` | `tests/test_lifecycle.py` |
| `src/shoal/services/mcp_pool.py` | `tests/test_mcp_pool.py` |
| `src/shoal/services/mcp_proxy.py` | `tests/test_mcp_proxy.py` |
| `src/shoal/services/mcp_configure.py` | `tests/test_mcp_configure.py` |
| `src/shoal/api/server.py` | `tests/test_api.py` |
| `src/shoal/cli/*.py` | `tests/test_cli_mcp.py` |
| `src/shoal/core/config.py` | `tests/test_config.py` |

### What You See

After code changes, Claude may say something like:

> Running tests for lifecycle changes...
> All 45 tests passed in test_lifecycle.py.

Or if something breaks:

> 2/45 tests failed in test_lifecycle.py — `test_create_session_rollback` and `test_fork_worktree_cleanup` failing due to missing await on the new helper.

You don't need to invoke this manually — Claude handles it. If you want to force a test run, use `/shoal-verify test` instead.

---

## Permissions

Permissions in `.claude/settings.local.json` control which Bash commands Claude can run without asking. The shoal config pre-approves:

| Permission | Why |
|------------|-----|
| `just:*` | All justfile targets (ci, test, lint, fmt, etc.) |
| `uv run:*` | Python tool execution via uv |
| `ruff check:*` / `ruff format:*` | Lint and format (also used by auto-format hook) |
| `mypy:*` | Type checking |
| `fish -n:*` | Fish template syntax validation |
| `git:*` | All git operations |
| `pre-commit run:*` | Pre-commit hook execution |
| `python3:*` | Direct Python execution |

These are in `settings.local.json` (gitignored) because permission preferences are personal. If Claude asks permission for something you think should be pre-approved, add it here.

---

## MCP Configuration

The `.mcp.json` file at the project root is a scaffold for MCP server definitions. Shoal itself is an MCP orchestrator, so during development you may want to add servers here for testing:

```json
{
  "mcpServers": {
    "memory": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    }
  }
}
```

Add servers with `claude mcp add --scope project <name>` to keep them in `.mcp.json` and shared across sessions.

---

## Global Configuration

These live outside the repo in `~/.claude/` and apply to all projects.

### Agent Progress Hook (SubagentStop)

When a subagent completes significant work (commits, file writes, deployments), a markdown report is written to `~/.inbox/`. Shoal sessions are tagged with `project: shoal` so you can filter them.

Lightweight agents (Explore, Bash, haiku lookups) are silently skipped to avoid inbox noise.

### Usage Tracking Hook (SessionStart)

Maintains a token usage cache at `~/.claude/stats-cache.json`. Updates every 4 hours. Useful for monitoring consumption on the Max plan.

---

## Adding to This Configuration

### New skill

```bash
mkdir -p .claude/skills/my-skill
# Write SKILL.md with YAML frontmatter (name, description, allowed-tools)
```

Or use the global `/create-skill` command which scaffolds the full directory structure.

### New agent

Create `.claude/agents/my-agent.md` with YAML frontmatter. Key fields:
- `model`: haiku (cheap/fast), sonnet (balanced), opus (complex reasoning)
- `tools`: Tool allowlist
- `description`: Include "use proactively" if Claude should auto-delegate

### New hook

Add to the appropriate event in `.claude/settings.json`:
- `PreToolUse` — block dangerous operations (exit code 2 to block)
- `PostToolUse` — auto-fix after edits (formatting, linting)
- `SessionStart` — inject context (use `"matcher": "compact"` for post-compaction)
- `Stop` — verification gates before Claude finishes

### Project vs personal

| Location | Scope | Git |
|----------|-------|-----|
| `.claude/settings.json` | Shared conventions (hooks, deny rules) | Committed |
| `.claude/settings.local.json` | Personal preferences (allow rules) | Gitignored |
| `.claude/skills/`, `.claude/agents/` | Project-specific tools | Committed |
| `~/.claude/skills/`, `~/.claude/agents/` | Personal tools (all projects) | Via dotfiles |
