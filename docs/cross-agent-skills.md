# Cross-Agent Skills

Shoal supports sharing skill definitions across different AI coding tools (Claude Code, OpenCode, omp) via a tool-agnostic skill format stored in `.shoal/skills/`.

---

## The Problem

Each coding agent has its own skill/command registration format:

| Tool | Skill Path | Format | Discovery |
|------|-----------|--------|-----------|
| Claude Code | `.claude/skills/<name>/SKILL.md` | Markdown + YAML frontmatter | Auto (directory scan) |
| OpenCode | `~/.config/opencode/skills/` | Plugin-based | User global only |
| omp | — | No formal skill system | Prompt injection via `@file` |

If you write a skill for Claude Code, it doesn't exist when you switch to an OpenCode or omp session. Each agent gets a different experience.

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

Skills are concatenated into a context file and injected via omp's `@file` prompt prefix:

```
# Injected at session start as @.shoal/context/skills.md
```

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
