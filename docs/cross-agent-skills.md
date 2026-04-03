# Cross-Agent Skills

Shoal supports sharing skill definitions across different AI coding tools (Claude Code, OpenCode, omp) via a tool-agnostic skill format stored in `.shoal/skills/`.

---

## The Problem

Each coding agent has its own skill/command registration format:

| Tool | Skill Path | Format | Discovery | Setup Guide |
|------|-----------|--------|-----------|-------------|
| Claude Code | `.claude/skills/<name>/SKILL.md` | Markdown + YAML frontmatter | Auto (directory scan) | `docs/CLAUDE_CODE_SETUP.md` |
| OpenCode | `.opencode/agents/<name>.md` | Markdown agents | Auto (directory scan) | `docs/OPENCODE_SETUP.md` |
| omp | `.omp/skills/<name>/SKILL.md` + `.omp/commands/<name>.md` | Markdown + YAML frontmatter | Auto (directory scan) | `docs/OMP_SETUP.md` |

All three tools now have native skill equivalents in this repo (verify, handoff, scaffold, roadmap). The `.shoal/skills/` transpilation layer is for projects that want a single source of truth.

## The Solution: `.shoal/skills/`

Define skills once in `.shoal/skills/<name>/SKILL.md` using a tool-agnostic markdown format. Shoal transpiles them into each tool's native format at session creation time.

### Skill format

```markdown
---
name: my-skill
description: One-line description shown in skill listings
allowed-tools: [Read, Glob, Grep, Bash]
---

# My Skill

Instructions for the agent when this skill is invoked.

## Steps

1. Do this first
2. Then do this
3. Finally do this
```

This is the same format as Claude Code's SKILL.md — it works natively with Claude Code and is transpiled for other tools.

### Directory structure

```
my-project/
├── .shoal/
│   ├── skills/
│   │   ├── review-code/
│   │   │   └── SKILL.md
│   │   ├── run-tests/
│   │   │   └── SKILL.md
│   │   └── update-changelog/
│   │       └── SKILL.md
│   ├── templates/
│   └── workspace.toml
├── .claude/
│   └── skills/        ← auto-populated from .shoal/skills/
├── src/
└── tests/
```

## Transpilation

### Claude Code

Skills are symlinked directly — `.shoal/skills/<name>/SKILL.md` maps 1:1 to `.claude/skills/<name>/SKILL.md`. No transformation needed.

### OpenCode

Skill descriptions are injected as instructions in the project-level `.opencode.json`:

```json
{
  "instructions": [
    ".shoal/skills/review-code/SKILL.md",
    ".shoal/skills/run-tests/SKILL.md"
  ]
}
```

OpenCode reads these as context at session start.

### omp (oh-my-pi)

Skills are symlinked directly into `.omp/skills/<name>/SKILL.md`, matching omp's
native project-local discovery path. No concatenated context file is required.

## Setting Up Skill Sync

### Option 1: `post_worktree_create` hook (recommended)

Add a sync script that runs after worktree creation:

```bash
#!/usr/bin/env bash
# scripts/shoal-skill-sync.sh — called with worktree path as $1
set -euo pipefail
WT="$1"
SKILLS_SRC="$(git rev-parse --show-toplevel)/.shoal/skills"

[ -d "$SKILLS_SRC" ] || exit 0

# Claude Code: symlink skills into worktree
mkdir -p "$WT/.claude/skills"
for skill_dir in "$SKILLS_SRC"/*/; do
    name="$(basename "$skill_dir")"
    ln -sfn "$skill_dir" "$WT/.claude/skills/$name"
done

# OpenCode: inject as instructions
if [ -f "$WT/.opencode.json" ]; then
    # Merge with existing config (requires jq)
    :
else
    instructions=""
    for skill_dir in "$SKILLS_SRC"/*/; do
        name="$(basename "$skill_dir")"
        instructions="$instructions\".shoal/skills/$name/SKILL.md\","
    done
    echo "{\"instructions\": [${instructions%,}]}" > "$WT/.opencode.json"
fi
```

Reference it in your template:

```toml
[template.worktree]
post_worktree_create = "scripts/shoal-skill-sync.sh"
```

If `.shoal/skills/` is your source of truth, treat `.claude/skills/`, `.pisces/skills/`, `.omp/skills/`, and any generated `.shoal/context/` files as derived artifacts and ignore them in `.gitignore`.

### Option 2: `setup_commands` in template

For simpler cases, use `setup_commands` to copy skills before the agent starts:

```toml
[template]
setup_commands = [
    "mkdir -p .claude/skills && cp -r $(git rev-parse --show-toplevel)/.shoal/skills/* .claude/skills/ 2>/dev/null || true",
]
```

### Option 3: Commit `.claude/skills/` directly

If you only use Claude Code, skip transpilation entirely — just commit `.claude/skills/` to your repo. Shoal worktrees inherit the repo's files, so skills are available in every session automatically.

## Setting Up Shoal for a New Repository

Rather than writing templates and config by hand, use the **`shoal-setup` skill**.
It reads the repo, infers the right roles and templates, confirms with you, then
writes the entire `.shoal/` configuration.

### Using `shoal-setup`

Invoke it from any Claude Code session in the target repo:

```
/shoal-setup
```

Or from pisces / omp:

```
/shoal-setup
```

The skill will:

1. **Read the repo** — detect stack (Python/Node/Go/Rust), monorepo structure, CI commands, existing Shoal config
2. **Present a summary** — show what it found and what roles it plans to create (supervisor, planner, implementer, reviewer)
3. **Ask targeted questions** — only for genuinely ambiguous choices (tool, supervisor template, branch convention)
4. **Write config** — `.shoal.toml`, `.shoal/templates/<role>.toml`, `.shoal/workspace.toml` (monorepos only)
5. **Wire symlinks** — runs the appropriate symlink/transpile step for whichever tools are in PATH

If you also want Shoal's standalone background robo supervisor, configure that separately
with `shoal robo setup <name>` — it is related to, but distinct from, a repo-local
`*-supervisor` template.

The skill is discoverable in this repo at `.shoal/skills/shoal-setup/SKILL.md` and symlinked to `.claude/skills/shoal-setup/`.

---

## Writing Good Skills

1. **Keep skills focused** — one task per skill, clear entry/exit criteria
2. **Use `allowed-tools`** — restrict what the agent can do (e.g., read-only skills shouldn't allow `Bash`)
3. **Include examples** — show the expected output format
4. **Reference project conventions** — link to COMMIT_GUIDELINES.md, CLAUDE.md, etc.
5. **Test with multiple tools** — verify the skill works with Claude Code, OpenCode, and omp

## Example: Shared Review Skill

```markdown
---
name: code-review
description: Review staged changes for quality, security, and test coverage
allowed-tools: [Read, Glob, Grep, Bash]
---

# Code Review

Review the current staged changes (or recent commits) for quality issues.

## Steps

1. Run `git diff --staged --stat` (or `git log --oneline -3` if nothing staged)
2. Read each changed file
3. Check for:
   - Type safety issues (missing type hints, `Any` usage)
   - Security concerns (SQL injection, command injection, hardcoded secrets)
   - Missing test coverage for new functions
   - Stale imports or dead code
4. Write findings as a markdown summary, categorized by severity

## Output Format

- **Critical**: Must fix before merge
- **Important**: Should fix, creates tech debt if skipped
- **Nice-to-have**: Cleanup opportunities
```

This skill works identically whether invoked as `/code-review` in Claude Code, as an instruction context in OpenCode, or via `@file` in omp.
