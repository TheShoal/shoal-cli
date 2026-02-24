---
name: shoal-help
description: Show a quick reference of all shoal-specific Claude Code skills, agents, hooks, and configuration. Use for re-orientation after time away.
disable-model-invocation: true
allowed-tools: Read
---

# Shoal Claude Code Quick Reference

Print the reference card below directly to the user. Do not paraphrase or summarize — output it as-is. If `$ARGUMENTS` contains a section name (skills, agents, hooks, permissions, keybindings, mcp), show only that section.

---

## Skills (invoke with `/name`)

| Skill | What it does |
|-------|-------------|
| `/shoal-verify [target]` | Run CI pipeline. Targets: `lint`, `typecheck`, `test`, `test-all`, `fish`, `cov`. Empty = full `just ci`. |
| `/shoal-release <version>` | Cut a release: verify clean tree → `just ci` → bump `pyproject.toml` + `__init__.py` → update CHANGELOG → commit → tag → confirm before push. |
| `/shoal-coverage [module]` | Run tests with coverage. Shows files below 80% gate, cross-references with recent git changes. Optional per-module targeting. |
| `/shoal-handoff [update]` | Read ROADMAP.md handoff section for session context. Pass `update` to write a new handoff entry. |
| `/shoal-scaffold <type> <name>` | Scaffold modules, CLI commands, services, models, MCP tools, templates with tests. Types: `cli`, `service`, `core`, `model`, `mcp-tool`, `template`, `integration`. |
| `/shoal-parallel [plan\|launch\|status\|collect]` | Orchestrate parallel Shoal sessions for independent workstreams. Uses Shoal's own MCP tools to spin up, monitor, and merge parallel dev sessions. |
| `/shoal-arch-check [target]` | Validate architectural invariants: async correctness, lifecycle delegation, module boundaries, detection patterns, DB/MCP patterns. Targets: `async`, `lifecycle`, `boundaries`, `detection`, `db`, `mcp`, `all`. |
| `/shoal-dogfood [area]` | Test Shoal features by actually using them via MCP tools and CLI. Areas: `sessions`, `mcp`, `templates`, `cli`, `detection`. |
| `/shoal-changelog [preview\|write\|diff]` | Generate CHANGELOG.md entries from git history since last release. Categorizes by conventional commit type. |
| `/shoal-deps [check]` | Audit dependencies: updates, unused, optional boundary validation, security. Checks: `updates`, `unused`, `boundaries`, `security`, `tree`, `audit`. |
| `/shoal-help [section]` | This reference card. |

## Agents (invoked automatically via Task tool)

| Agent | Model | Purpose |
|-------|-------|---------|
| `shoal-test-runner` | haiku | Run targeted tests after code changes. Maps source files to test files. Auto-invoked after writing Python code. |
| `shoal-diff-reviewer` | sonnet | Review staged changes for: missing type hints, async violations, missing tests, ruff/mypy issues. Use before committing. |
| `shoal-lint-checker` | haiku | Fast ruff + mypy --strict check (no tests). Quick type safety validation. |

## Hooks (fire automatically)

| Hook | Trigger | What it does |
|------|---------|-------------|
| **ruff format + check** | PostToolUse `Edit\|Write` | Auto-formats and auto-fixes Python files after every edit. 10s timeout. |
| **mypy --strict** | PostToolUse `Edit\|Write` | Type-checks edited Python files. Shows first 5 errors. 15s timeout. |
| **test-reminder** | PostToolUse `Edit\|Write` | Injects "run tests" context when editing `src/shoal/*.py` files. Non-blocking. |
| **git-guard** | PreToolUse `Bash` | Blocks destructive git commands: `push --force`, `reset --hard`, `branch -D`, `clean -f`, `checkout .`, `restore .`. Allows `--force-with-lease`. |
| **SessionStart** | Every session start | Injects project context reminder (Python 3.12+, just ci, mypy --strict, 618 tests, 80% coverage gate). |

## MCP Servers

| Server | Registration |
|--------|-------------|
| `shoal-orchestrator` | Registered in `.mcp.json`. Entry point: `shoal-mcp-server` (stdio). Exposes 8 tools: `list_sessions`, `session_status`, `session_info`, `send_keys`, `create_session`, `kill_session`, `append_journal`, `read_journal`. |

## Project Permissions (`.claude/settings.local.json`)

Auto-allowed: `git`, `just`, `uv run`, `python3`, `ruff check`, `ruff format`, `mypy`, `fish -n`, `pre-commit run`, `head`, `tail`, `gh`, `wc`, `diff`.

## Key Commands

```
just ci            # Full pipeline: lint → typecheck → test → fish-check
just test          # Unit tests only
just test-all      # Including integration tests (needs tmux)
just cov           # Tests with coverage
just lint          # Ruff lint
just fmt           # Ruff format
just typecheck     # mypy --strict
just fish-check    # Fish template syntax
```

## Keybindings

| Chord | Action |
|-------|--------|
| `Ctrl+K Ctrl+I` | Stash current chat |
| `Ctrl+K Ctrl+T` | Toggle todo list |

## File Locations

```
.mcp.json                              # MCP server registration
.claude/settings.json                  # Hooks (committed)
.claude/settings.local.json            # Permissions (gitignored, per-machine)
.claude/hooks/git-guard.sh             # Destructive git command blocker
.claude/hooks/test-reminder.sh         # Test reminder injector
.claude/skills/shoal-*/SKILL.md        # Project skills
.claude/agents/shoal-*.md              # Project agents
```
