# Cross-Tool Skills

> Share a single skill definition across Claude Code, omp, OpenCode, and pi.

Define skills once in `.shoal/skills/<name>/SKILL.md`. Shoal syncs them into each tool's native format at worktree creation time.

---

## Directory structure

```
my-project/
├── .shoal/
│   └── skills/
│       ├── review-code/
│       │   └── SKILL.md
│       └── run-tests/
│           └── SKILL.md
├── .claude/skills/        ← auto-populated from .shoal/skills/
├── .omp/skills/           ← auto-populated from .shoal/skills/
└── .opencode/agents/      ← injected as instructions
```

---

## How it works per tool

### Claude Code

Symlinked directly — no transformation needed.

```bash
ln -sfn .shoal/skills/review-code .claude/skills/review-code
```

Claude Code discovers skills by scanning `.claude/skills/` at startup.

### omp

Symlinked directly into omp's native discovery path.

```bash
ln -sfn .shoal/skills/review-code .omp/skills/review-code
```

Invoke with `/review-code` in an omp session.

### OpenCode

Skills are injected as instructions in `.opencode.json`:

```json
{
  "instructions": [
    ".shoal/skills/review-code/SKILL.md",
    ".shoal/skills/run-tests/SKILL.md"
  ]
}
```

OpenCode reads these files as context at session start.

---

## Setup options

### Option 1: `post_worktree_create` hook (recommended)

```toml
# ~/.config/shoal/templates/my-template.toml
[template.worktree]
post_worktree_create = "scripts/shoal-skill-sync.sh"
```

The script runs in every new worktree. Shoal ships a reference implementation at `.shoal/scripts/skill-sync.sh` — copy it into your repo and reference it in your template.

### Option 2: `setup_commands`

For simpler setups, copy skills as part of the agent startup sequence:

```toml
[template]
setup_commands = [
    "mkdir -p .claude/skills && cp -r $(git rev-parse --show-toplevel)/.shoal/skills/* .claude/skills/ 2>/dev/null || true",
]
```

### Option 3: Commit tool-native skills directly

If you only use one tool, skip the transpilation layer entirely. Commit `.claude/skills/` to your repo — Shoal worktrees inherit repo files, so skills are available in every session automatically.

---

## Shoal's built-in skill sync

Shoal's own templates use the `shoal-setup` skill to bootstrap `.shoal/` configuration in new repos. It also wires skill symlinks for whichever tools are present.

Run it from any Shoal session:

```bash
# In Claude Code or omp
/shoal-setup
```

The skill reads the repo, infers stack and conventions, then writes:
- `.shoal.toml` — project-level defaults
- `.shoal/templates/<role>.toml` — session templates per role
- `.shoal/workspace.toml` — monorepo team config

---

## Adding a new skill

1. Create `.shoal/skills/<name>/SKILL.md`
2. Run `shoal skill ls` to confirm discovery
3. Test in a session (`/<name>` or via tool's skill invocation)
4. Commit `.shoal/skills/` — derived directories (`.claude/skills/`, `.omp/skills/`) are generated artifacts; add them to `.gitignore`

For the full skill format, see [Reference](reference.md).
