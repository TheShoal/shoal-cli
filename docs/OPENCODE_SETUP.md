# OpenCode Setup for Shoal Development

This guide covers the OpenCode configuration that ships with the shoal repository. These files provide project context, coding agents, and rules to make OpenCode effective at writing production-level shoal code.

---

## What's Included

```
.opencode/
├── instructions.md            # Project context (conventions, commands, architecture)
├── agents/
│   ├── test-runner.md         # Test runner agent
│   ├── lint-checker.md        # Lint + type check agent
│   ├── diff-reviewer.md       # Staged diff reviewer agent
│   ├── verify.md              # CI pipeline runner agent
│   ├── handoff.md             # Session continuity agent
│   ├── scaffold.md            # Component scaffolder agent
│   └── roadmap.md             # Roadmap manager agent
└── rules/
    ├── session-lifecycle.md   # Pane identity, status detection, cleanup protocol
    └── conventional-commits.md # Commit message format rules

opencode.json                  # OpenCode configuration (models, instructions ref)
```

---

## instructions.md — Project Context

The `.opencode/instructions.md` file gives OpenCode essential project knowledge:

- **Build commands**: `just ci`, `just test`, `just lint`, etc.
- **Code style**: 100-char lines, mandatory type hints, ruff lint rules
- **Module layout**: One-line description of each top-level package
- **Architectural invariants**: SQLite WAL mode, lifecycle service pattern, MCP pooling
- **Gotchas**: Fish template validation, hatchling build backend, MCP pool semantics

**Maintenance**: If OpenCode keeps making the same mistake, add a rule to `instructions.md` or create a new rule file in `.opencode/rules/`. Keep instructions under 100 lines.

---

## Rules

Rules in `.opencode/rules/` provide domain-specific constraints.

### session-lifecycle.md

Reference for shoal session lifecycle contracts:
- Pane identity (`shoal:<session_id>` titles)
- Status detection guarantees and limitations
- Status state machine (idle -> running -> waiting -> error -> stopped)
- Worktree cleanup protocol
- Fork semantics and MCP pool isolation

### conventional-commits.md

Commit message format enforced by gitlint:
- Type: `feat|fix|docs|style|refactor|perf|test|chore`
- Scope: optional (`session`, `mcp`, `cli`, `api`, etc.)
- Description: imperative, lowercase, no period, under 50 chars

---

## Agents

### test-runner — Test Execution

Maps changed source files to their test files and runs targeted tests.

| Source | Test |
|--------|------|
| `src/shoal/services/lifecycle.py` | `tests/test_lifecycle.py` |
| `src/shoal/services/mcp_pool.py` | `tests/test_mcp_pool.py` |
| `src/shoal/services/mcp_proxy.py` | `tests/test_mcp_proxy.py` |
| `src/shoal/services/mcp_configure.py` | `tests/test_mcp_configure.py` |
| `src/shoal/api/server.py` | `tests/test_api.py` |
| `src/shoal/cli/*.py` | `tests/test_cli_mcp.py` |
| `src/shoal/core/config.py` | `tests/test_config.py` |

### lint-checker — Quick Quality Check

Runs `uv run ruff check src/ tests/` and `uv run mypy --strict src/` without running the full test suite. Use for rapid type safety validation.

### diff-reviewer — Pre-Commit Review

Reviews staged changes for:
- Missing type hints on function signatures
- Async violations (blocking calls in async functions)
- Missing test files for new modules
- Ruff lint and mypy strict errors

### verify — CI Pipeline

Runs the full CI pipeline (`just ci`) or targeted checks. Equivalent to what CI runs on push.

### handoff — Session Continuity

Reads ROADMAP.md handoff section to establish context from the previous session, or writes a new handoff entry when ending a session.

### scaffold — Component Generator

Generates boilerplate for new Shoal modules following existing patterns. Supports: CLI commands, services, core modules, Pydantic models, MCP tools, session templates, and integration tests.

### roadmap — Backlog Manager

Adds items to ROADMAP.md backlog or milestone sections. Formats entries to match the existing style and prevents duplicates.

---

## opencode.json — Model Configuration

The `opencode.json` at the project root configures OpenCode's agent models:

| Agent | Model | Purpose |
|-------|-------|---------|
| build | claude-sonnet-4.6 | Code generation and implementation |
| plan | claude-opus-4.6 | Architecture and planning |
| scribe | claude-haiku-4.5 | Repository exploration and status tracking |

The `instructions` field points to `.opencode/instructions.md` for project context injection.

---

## Cross-Agent Compatibility

Shoal keeps tool-specific automation in separate directories:

| Directory | Tool |
|-----------|------|
| `.claude/` | Claude Code |
| `.omp/` | OMP / Pi |
| `.opencode/` | OpenCode |

Shared orchestration lives in Shoal tool profiles and session templates:
- Tool profiles: `examples/config/tools/` (`claude`, `codex`, `gemini`, `opencode`, `pi`)
- Session templates: `examples/config/templates/` (`base-dev` + tool-specific overlays)

This separation lets each tool have first-class support without locking the project to a single runtime.

---

## Adding to This Configuration

### New agent

Create `.opencode/agents/my-agent.md` with a title heading and task description. Include:
- Clear step-by-step instructions
- Expected output format
- File-to-file mapping if applicable

### New rule

Create `.opencode/rules/my-rule.md` with domain constraints. Rules are automatically loaded by OpenCode and applied during code generation.

### Project vs personal

| Location | Scope | Git |
|----------|-------|-----|
| `.opencode/instructions.md` | Shared project context | Committed |
| `.opencode/agents/` | Project-specific agents | Committed |
| `.opencode/rules/` | Project-specific rules | Committed |
| `opencode.json` | Model configuration | Committed |
