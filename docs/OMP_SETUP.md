# OMP (Oh My Pi) Setup for Shoal Development

This guide covers the OMP configuration that ships with the shoal repository. These tools automate quality checks, provide project context, and make OMP more effective at writing production-level shoal code.

---

## What's Included

```
.omp/
├── AGENTS.md                           # Project context (conventions, architecture, gotchas)
├── config.yml                          # MCP server configuration
├── commands/
│   ├── fin-scaffold.md                 # Scaffold a new shoal fin
│   ├── handoff.md                      # Session continuity (read/write ROADMAP.md handoff)
│   ├── session-template.md             # Create a new session template
│   ├── shoal-status.md                 # Full status snapshot with attention triage
│   └── verify.md                       # CI pipeline runner
├── extensions/
│   └── shoal-dev/
│       └── index.ts                    # Quality gate extension (ruff, mypy, pip block)
├── rules/
│   ├── async-discipline.md             # Async-first I/O rules
│   ├── conventional-commits.md         # Commit format spec
│   ├── fin-contract.md                 # Fin contract-v1 reference
│   └── session-lifecycle.md            # Session lifecycle, pane identity, status detection
└── skills/
    ├── shoal-context/
    │   └── SKILL.md                    # Current project state (version, recent releases)
    ├── shoal-handoff/
    │   └── SKILL.md                    # Session handoff skill
    ├── shoal-roadmap/
    │   └── SKILL.md                    # Add items to ROADMAP.md
    ├── shoal-scaffold/
    │   └── SKILL.md                    # Scaffold new components
    └── shoal-verify/
        └── SKILL.md                    # CI pipeline skill
```

---

## AGENTS.md — Project Context

The `.omp/AGENTS.md` file gives OMP essential project knowledge on every session start:

- **Build commands**: `just ci`, `just test`, `just lint`, etc.
- **Code style**: 100-char lines, mandatory type hints, ruff lint rules
- **Module layout**: One-line description of each top-level package
- **Architectural invariants**: SQLite WAL mode, lifecycle service pattern, MCP pooling
- **Gotchas**: Fish template validation, hatchling build backend, MCP pool semantics
- **Tool discipline**: When to use `write` vs `edit`, verification shortcuts

**Maintenance**: If OMP keeps making the same mistake, add a rule to `AGENTS.md`. If a rule isn't preventing mistakes, remove it.

---

## Extension: shoal-dev

Defined in `.omp/extensions/shoal-dev/index.ts`. Runs automatically alongside OMP's global devtools extension.

### Auto-Lint (PostToolUse)

**Trigger**: After every `edit` or `write` tool call on a `.py` file.

**What it does**: Runs `ruff check --fix` on the edited file. This layers on top of the global devtools `ruff format` — so you get both formatting and lint auto-fix.

### Type Check (PostToolUse)

**Trigger**: After every `edit` or `write` on a `.py` file under `src/shoal/`.

**What it does**: Runs `mypy --strict` on the edited file. Reports the first 8 errors for immediate feedback.

### pip Block (PreToolUse)

**Trigger**: Before any `bash` command containing `pip install` (without `uv pip` prefix).

**What it does**: Blocks the command with a message to use `uv add` or `uv sync` instead.

---

## Rules

Rules in `.omp/rules/` provide always-on context that OMP consults during code generation.

| Rule | Purpose |
|------|---------|
| `session-lifecycle.md` | Pane identity, status detection guarantees, cleanup protocol, fork semantics |
| `fin-contract.md` | Fin contract-v1 schema, exit codes, env vars, breaking change rules |
| `conventional-commits.md` | Commit format spec — types, scopes, description rules |
| `async-discipline.md` | Async-first I/O rules — `asyncio.to_thread()`, no `time.sleep()` |

---

## Commands

Commands in `.omp/commands/` are invocable via OMP's command interface.

### `/verify` — CI Pipeline

Run the full CI pipeline or targeted checks.

```
/verify              # Full pipeline: lint → typecheck → test → fish-check → security
/verify lint         # Ruff lint only
/verify typecheck    # mypy --strict only
/verify test         # Unit tests only
/verify cov          # Tests with coverage report
```

### `/handoff` — Session Continuity

Pick up where the last session left off, or record what you did.

```
/handoff             # Read latest handoff and upcoming work
/handoff update      # Write a new handoff entry for this session
```

### `/shoal-status` — Status Snapshot

Full status snapshot of all shoal sessions with attention triage. Runs `shoal status`, `shoal ls`, `shoal diag`, and inspects waiting/error sessions.

### `/session-template` — Template Creator

Interactive template generator — asks questions about the workflow, then generates a valid TOML template.

### `/fin-scaffold` — Fin Generator

Scaffolds a complete fin following the contract-v1 shape. Generates `fin.toml`, all four entrypoint scripts, config, and README.

---

## Skills

Skills in `.omp/skills/` provide deeper context that OMP can reference when relevant.

| Skill | Purpose |
|-------|---------|
| `shoal-context` | Current project state — version, recent releases, live docs |
| `shoal-verify` | CI pipeline execution and result interpretation |
| `shoal-handoff` | Session handoff reading and writing |
| `shoal-scaffold` | Component scaffolding with project pattern enforcement |
| `shoal-roadmap` | Add items to ROADMAP.md backlog or milestones |

---

## MCP Configuration

The `.omp/config.yml` configures the Shoal MCP orchestrator server:

```yaml
mcpServers:
  shoal-orchestrator:
    url: http://localhost:8390/mcp/
```

This gives OMP access to all 18 Shoal orchestration tools including `list_sessions`, `send_keys`, `capture_pane`, `read_worktree_file`, `list_worktree_files`, `mark_complete`, and more.

---

## Cross-Agent Compatibility

Shoal keeps tool-specific automation separated:

| Directory | Tool | Purpose |
|-----------|------|---------|
| `.omp/` | OMP / Oh My Pi | Extensions, commands, rules, skills |
| `.claude/` | Claude Code | Hooks, skills, agents |
| `.opencode/` | OpenCode | Agent configuration |

Shared orchestration lives in tool profiles (`examples/config/tools/`) and session templates (`examples/config/templates/`). This lets each tool have optimized DX without locking the project to a single vendor.

---

## Adding to This Configuration

### New command

Create `.omp/commands/<name>.md` with YAML frontmatter:

```yaml
---
description: One-line description of what this command does.
---
```

The body contains the instructions OMP follows when the command is invoked.

### New skill

```bash
mkdir -p .omp/skills/<name>
# Write SKILL.md with YAML frontmatter (name, description)
```

### New rule

Create `.omp/rules/<name>.md` with YAML frontmatter:

```yaml
---
description: One-line description of when this rule applies.
---
```

Rules are always-on — OMP consults them automatically when relevant.

### New extension

Create `.omp/extensions/<name>/index.ts`. Extensions hook into OMP's event system (`tool_call`, `tool_result`) to automate quality gates and workflows.
