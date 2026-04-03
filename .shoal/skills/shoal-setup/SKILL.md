---
name: shoal-setup
description: Configure Shoal for a repository — infer stack/roles from the codebase, confirm with the user, write .shoal/ config.
allowed-tools: Read, Glob, Grep, Bash, Write, Edit
---

# Shoal Repository Setup

Configure Shoal for the current repository. Read the codebase, infer the right
templates and roles, confirm with the user, then write `.shoal/` config files.

---

## Phase 1 — Reconnaissance

Gather facts about the repo before asking anything.

```bash
# Understand the repo shape
git rev-parse --show-toplevel        # confirm git root
ls -1                                 # top-level layout
cat README.md 2>/dev/null | head -60  # stated purpose
```

Look for:

**Stack signals** (infer setup commands and tool defaults):
- `pyproject.toml` / `uv.lock` → Python; setup command: `uv sync`
- `package.json` → Node/TS; setup command: `npm install` or `pnpm install`
- `go.mod` → Go; setup command: `go mod download`
- `Cargo.toml` → Rust; setup command: `cargo fetch`
- `Makefile` / `justfile` → check for `ci`, `test`, `lint` targets
- `Dockerfile` / `docker-compose.yml` → containerized; note for infra role
- `.github/workflows/` → CI pipeline; read it to find test/lint commands

**Monorepo signals** (infer workspace entries):
- Multiple `package.json` files across subdirectories
- `packages/`, `apps/`, `services/`, `libs/` directories
- Turborepo / Nx / Lerna config
- Different language roots at subdirectory level

**Team shape signals** (infer which roles are useful):
- `frontend/`, `web/`, `ui/`, `client/` → frontend role worth adding
- `backend/`, `server/`, `api/` → backend role
- `infra/`, `terraform/`, `k8s/`, `.github/workflows/` → infra role
- `tests/`, `e2e/`, `cypress/`, `playwright/` → QA role
- `SECURITY.md`, `audit/`, security-related CI steps → security role
- `docs/`, `spec/`, design files → planner or supervisor role

**Existing Shoal config** (avoid overwriting):
```bash
ls .shoal/ 2>/dev/null
cat .shoal.toml 2>/dev/null
```

If `.shoal/` already exists with templates, **stop and tell the user** what's
already there before proceeding. Offer to extend it, not replace it.

---

## Phase 2 — Confirm with the User

Present findings concisely, then ask only what you can't infer.

### Confirmation block format

```
Here's what I found:

**Stack**: Python (uv), pytest for tests, ruff for lint
**Structure**: Monorepo — packages/api, packages/web, packages/shared
**CI**: GitHub Actions (.github/workflows/ci.yml) — lint → typecheck → test

**Roles I'd create templates for:**
- supervisor     — interactive planner/supervisor session for team coordination
- planner        — scope features, write specs (cheap model)
- implementer    — write code (powerful model, one per subdomain)
  - api-impl     — packages/api context
  - web-impl     — packages/web context (TypeScript)
- reviewer       — review diffs, check behavioral regressions

**Workspace entries** (for --repo routing):
  api  → packages/api
  web  → packages/web

**Default tool**: [TOOL] (from your current environment)

Does this look right? Anything to add, remove, or rename?
Also: which AI tool do you use? (claude / pisces / omp / opencode)
```

Keep the confirmation block short. Don't list every TOML field — just the
roles, structure, and tool. Let the user correct at a high level.

**Specific questions to ask only if genuinely ambiguous:**
- Which AI tool to default to (if you can't detect it from PATH or existing config)
- Whether they want an interactive supervisor template
- Branch naming convention (if no existing convention visible in git log)
- Whether to add a security reviewer (suggest only if security-sensitive code visible)

If they ask about `shoal robo`, clarify that it is separate from repo-local
supervisor templates: `shoal robo setup/start` manages the background robo
profile in user config, while a `*-supervisor` template is the interactive
session the human talks to inside the repo.

---

## Phase 3 — Write Config

Once confirmed, write files in this order:

### 3.1 `.shoal.toml` (project-level defaults)

```toml
# .shoal.toml — project-level Shoal defaults
# Inherited by all sessions in this repo.

default_tool = "<tool>"
default_template = "<default-template>"
setup_commands = ["<detected setup command>"]

[env]
# Add repo-specific env vars here
```

Only include `default_template` if one is clearly the best default. Only include
`setup_commands` if you detected one. Only include env vars if the repo clearly
needs them (e.g. `DATABASE_URL` in `.env.example`).

### 3.2 `.shoal/templates/<role>.toml` for each confirmed role

Use the appropriate base template depending on the role:

**Planner** (cheap, read-heavy, no writes):
```toml
[template]
name        = "<repo>-planner"
description = "Scope features, write specs and ROADMAP entries"
extends     = "base-dev"
tool        = "<tool>"
mcp         = ["shoal-orchestrator", "memory"]
mode        = "planner"
tags        = ["planner"]

[template.git]
branch_prefix = "plan/"
```

**Implementer** (powerful model, writes code):
```toml
[template]
name        = "<repo>-impl"
description = "<description of what this agent implements>"
extends     = "base-dev"
tool        = "<tool>"
mcp         = ["shoal-orchestrator", "memory"]
mode        = "implementer"
tags        = ["impl"]

[template.git]
branch_prefix = "feat/"
```

For monorepos, create one implementer template per subdomain with a
`[template.worktree]` `name` pointing to the relevant subdirectory.

**Reviewer** (fast, read-only, diff-focused):
```toml
[template]
name        = "<repo>-reviewer"
description = "Review diffs — behavioral regressions first, style last"
extends     = "base-dev"
tool        = "<tool>"
mcp         = ["shoal-orchestrator"]
mode        = "reviewer"
tags        = ["reviewer"]
```

**Interactive supervisor** (if requested):
```toml
[template]
name        = "<repo>-supervisor"
description = "Interactive supervisor — plans work, spawns fleet, supervises to completion"
extends     = "base-dev"
tool        = "<tool>"
mcp         = ["shoal-orchestrator", "memory"]
mixins      = ["shoal-orchestrator"]
mode        = "supervisor"
tags        = ["supervisor", "planner"]

[template.env]
SHOAL_ROBO = "1"
```

Prefer `branch_prefix` for interactive templates. Reserve `user_name` and
`user_email` for explicit automation roles where bot-authored commits are
intentional (for example a dedicated release template).

### 3.3 `.shoal/workspace.toml` (monorepos only)

Only write this if the repo is a confirmed monorepo:

```toml
# .shoal/workspace.toml — meta-repo workspace manifest
# Maps logical repo names to sub-directory paths.
# Used by --repo flag and auto-match in shoal new/fork.

[repos]
<name> = "<relative/path>"
```

### 3.4 Skill symlinks

After writing config, wire up the skill symlinks so agents pick them up:

**Claude Code** (if `claude` is in PATH):
```bash
mkdir -p .claude/skills
for dir in .shoal/skills/*/; do
  name=$(basename "$dir")
  ln -sfn "$(pwd)/$dir" ".claude/skills/$name"
done
echo "Claude Code skills linked."
```

**OpenCode** (if `opencode` is in PATH):
```bash
# Collect skill paths
skills=$(find .shoal/skills -name SKILL.md | sed 's|^|"|;s|$|"|' | paste -sd,)
if [ -f .opencode.json ]; then
  echo "Note: .opencode.json already exists — add instructions manually:"
  echo "  \"instructions\": [$skills]"
else
  echo "{\"instructions\": [$skills]}" > .opencode.json
  echo "OpenCode .opencode.json created."
fi
```

**pisces** (if `pisces` is in PATH):
```bash
# Requires pisces config set skills.customDirectories '[".pisces/skills"]'
mkdir -p .pisces/skills
for dir in .shoal/skills/*/; do
  name=$(basename "$dir")
  ln -sfn "$(pwd)/$dir" ".pisces/skills/$name"
done
echo "pisces skills linked."
```

**omp** (if `omp` is in PATH):
```bash
mkdir -p .omp/skills
for dir in .shoal/skills/*/; do
  name=$(basename "$dir")
  ln -sfn "$(pwd)/$dir" ".omp/skills/$name"
done
echo "omp skills linked."
```

Only run the blocks for tools that are present. Use `command -v <tool>` to check.
Also add generated paths like `.claude/skills/`, `.pisces/skills/`, `.omp/skills/`,
and `.shoal/context/` to `.gitignore` when `.shoal/skills/` is the source of
truth for shared skills.

---

## Phase 4 — Verify

After writing, confirm the config loads correctly:

```bash
shoal template ls          # confirm templates appear
shoal skill ls             # confirm skills are discoverable
```

If `shoal` is not in PATH, skip verification and tell the user to run
`shoal template ls` once Shoal is installed.

---

## Output after completion

```
## Shoal setup complete

**Written:**
- .shoal.toml              — project defaults (tool: <tool>, setup: <cmd>)
- .shoal/templates/
  - <role1>.toml
  - <role2>.toml
  ...
- .shoal/workspace.toml    — (if monorepo)

**Skills linked for:** claude / omp / opencode (whichever were present)

**To start a session:**
  shoal new feat/my-feature --template <repo>-impl
  shoal new review/my-feature --template <repo>-reviewer
  shoal new supervisor/my-feature --template <repo>-supervisor

**Background robo profile:**
  Use `shoal robo setup <name> --tool <tool>` if you also want the standalone robo supervisor.

Run `shoal template ls` to confirm everything loaded.
```

---

## Constraints

- **Never overwrite** existing `.shoal/` files without explicit user confirmation.
- **Never add roles** the user didn't confirm (e.g. don't add a security reviewer
  unless they said yes or the codebase is clearly security-sensitive).
- **Keep templates minimal** — only include fields that have real values. Don't
  emit commented-out placeholder blocks.
- **Don't create `.shoal.toml`** if no project-level defaults are needed.
- **Don't create workspace.toml** unless it's clearly a monorepo.
- The `extends = "base-dev"` line requires that `base-dev.toml` exists in the
  user's global templates (`~/.config/shoal/templates/`). If you're not sure,
  omit `extends` and write a self-contained template instead.
