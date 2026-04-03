# Project-Local Templates

Shoal supports **project-local templates** stored in your repository alongside global templates. Local templates let you share session configurations with collaborators and tailor templates to specific projects without polluting your global config.

---

## Quick Start

### 1. Create the directory

```bash
mkdir -p .shoal/templates
```

This directory lives at your git root, next to `.git/`.

### 2. Add a template

```toml
# .shoal/templates/my-project.toml
[template]
name = "my-project"
tool = "claude"
description = "Claude session for my-project with memory MCP"
mcp = ["memory"]

[[template.windows]]
name = "tests"
command = "just test --watch"
```

### 3. Use it

```bash
shoal new my-feature --template my-project
```

---

## Search Path

Shoal checks for templates in this order:

1. **`<git-root>/.shoal/templates/<name>.toml`** — project-local (takes priority)
2. **`~/.config/shoal/templates/<name>.toml`** — global

If a template with the same name exists in both locations, the **local version wins**.

### Listing templates

```bash
shoal template ls
```

The `SOURCE` column shows where each template was found:

```
┌──────────────┬────────┬──────────┬─────────┬─────┐
│ NAME         │ TOOL   │ SOURCE   │ EXTENDS │ MIX │
├──────────────┼────────┼──────────┼─────────┼─────┤
│ my-project   │ claude │ local    │         │     │
│ base-dev     │ …      │ global   │         │     │
│ claude-dev   │ claude │ global   │ base-dev│     │
└──────────────┴────────┴──────────┴─────────┴─────┘
```

---

## Local Mixins

Mixins also support the local search path. Place them in:

```
.shoal/templates/mixins/<name>.toml
```

```toml
# .shoal/templates/mixins/project-mcp.toml
[mixin]
name = "project-mcp"
mcp = ["memory", "filesystem"]

[mixin.env]
PROJECT_NAME = "my-project"
```

Use them from any template (local or global):

```toml
# .shoal/templates/my-project.toml
[template]
name = "my-project"
tool = "opencode"
mixins = ["project-mcp"]
```

The mixin search path mirrors templates: local first, then global.

---

## Inheritance with Local Templates

Local templates can `extend` global templates and vice versa. The `extends` and `mixins` fields resolve across both search paths:

```toml
# .shoal/templates/my-claude.toml
[template]
name = "my-claude"
extends = "base-dev"          # resolves from global
mixins = ["project-mcp"]     # resolves from local
tool = "claude"
description = "Claude for this project, inheriting base-dev layout"
```

Resolution order remains: `extends` chain first, then `mixins`, then CLI flags.

---

## Tags & Mode Fields

Templates can declare `tags` and `mode` to auto-configure sessions:

```toml
[template]
name = "haiku-reviewer"
extends = "base-dev"
tool = "claude"
mode = "reviewer"
tags = ["dogfood", "haiku", "reviewer"]

[template.env]
CLAUDE_MODEL = "haiku"
```

- **`tags`**: Applied to the session at creation. Union-merged with parent during inheritance.
- **`mode`**: Declares which operating mode this template serves. Child wins if set.

Tags affect urgency tiers: sessions tagged `review-ready` are promoted to the **review** urgency tier in `shoal status` output.

See [Handoffs & Modes](handoffs-and-modes.md) for the full operating modes reference.

---

## Per-Session Git Identity

The `[template.git]` block configures a scoped git identity for the session's worktree. When set, Shoal emits `git config --local` commands into the worktree and exports `GIT_AUTHOR_NAME`, `GIT_COMMITTER_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_EMAIL` as fish global env vars so all subprocess git calls inherit the identity automatically.

### Fields

| Field | Description |
|-------|-------------|
| `user_name` | `git config --local user.name` for this worktree |
| `user_email` | `git config --local user.email` for this worktree |
| `commit_template` | Path to a commit message template (`git config --local commit.template`) |
| `branch_prefix` | Default branch category prefix used by `shoal new -b` (e.g. `"fix"`, `"chore"`) |

All fields are optional. The block is a no-op when all four are empty.

### Example

```toml
# ~/.config/shoal/templates/my-template.toml
[template]
name = "my-template"
tool = "pi"

[template.git]
user_name  = "Robo Coder"
user_email = "robo@myorg.com"
commit_template = "~/.gitmessage"
branch_prefix = "fix"

[[windows]]
name = "editor"
[[windows.panes]]
split = "root"
command = "{tool_command}"
```

### `branch_prefix` behaviour

`branch_prefix` is a hint used when running `shoal new -w <name> -b`. If the worktree name contains no `/`, Shoal prepends `branch_prefix/` to form the branch name (e.g. `fix/my-feature`). If the worktree name already contains a `/`, it passes through unchanged — the explicit form always wins.

### Inheritance semantics

**`extends`** — The child `[template.git]` block replaces the parent's entire block. If the child omits a field that the parent set, that field reverts to empty.

**`mixins`** — Field-level merge. A non-empty mixin field wins, but unset mixin fields do not clear the template's own values. This lets a shared mixin supply only `user_name`/`user_email` without disrupting a template's `commit_template` or `branch_prefix`.

Mixin example:

```toml
# ~/.config/shoal/templates/mixins/git-identity.toml
[mixin]
name = "git-identity"
description = "Per-session git authorship for automated commits"

[mixin.git]
user_name  = "Robo Coder"
user_email = "robo@myorg.com"
```

Apply to any template with:

```toml
[template]
name = "my-project"
tool = "pi"
mixins = ["git-identity"]
```

---

## Directory Layout

A typical project using local templates:

```
my-repo/
├── .shoal/
│   └── templates/
│       ├── my-project.toml
│       ├── review.toml
│       └── mixins/
│           └── project-mcp.toml
├── src/
├── tests/
└── ...
```

Commit `.shoal/templates/` to version control so collaborators inherit the same session configurations.

---

## Bundled Mixins

These mixins are installed globally by `shoal init` into `~/.config/shoal/templates/mixins/`:

| Mixin | Effect |
|-------|--------|
| `uv-dev` | Runs `uv sync --extra dev` in the initial pane before agent launch |
| `with-tests` | Appends a test-runner window to the session layout |
| `shoal-orchestrator` | Attaches the Shoal orchestrator MCP server to the session |
| `mcp-memory` | Attaches the memory MCP server to the session |
| `git-identity` | Sets `user_name`, `user_email` for automated commits in the worktree |

### `uv-dev` — dev-dependency bootstrap

Use this mixin in any worktree-based template to ensure dev tools (ruff, mypy, pytest)
are installed before the agent starts:

```toml
# ~/.config/shoal/templates/my-project.toml
[template]
name = "my-project"
tool = "pi"
mixins = ["uv-dev"]

[[windows]]
name = "editor"
[[windows.panes]]
split = "root"
command = "{tool_command}"
```

To install additional extras (e.g. `mcp`), copy `uv-dev.toml` to your project's
`.shoal/templates/mixins/` and adjust the command:

```toml
# .shoal/templates/mixins/uv-dev.toml
[mixin]
name = "uv-dev"
description = "Bootstrap dev + mcp extras"
setup_commands = ["uv sync --extra dev --extra mcp"]
```

The local version shadows the global one — no other files need changing.

---

## When to Use Local vs Global

| Use case | Location |
|----------|----------|
| Shared base layouts (`base-dev`) | Global (`~/.config/shoal/templates/`) |
| Tool-specific defaults (`claude-dev`, `codex-dev`, `pi-dev`) | Global |
| Project-specific sessions | Local (`.shoal/templates/`) |
| Project-specific MCP sets | Local mixins (`.shoal/templates/mixins/`) |
| Per-session git author/commit config | `[template.git]` or `git-identity` mixin |

---

## Workspace Manifest (Meta-Repos)

For meta-repos containing multiple sub-repositories (like Smorgasbord), add a `.shoal/workspace.toml` to map logical names to sub-repo paths:

```toml
# .shoal/workspace.toml
[workspace]
name = "smorgasbord"

[workspace.repos]
emailservice = "backend/emailservice"
order = "backend/order"
web-app = "frontend/web-app"
```

Teams can also live in the same file and drive `shoal team`, `shoal ticket`, and `shoal report`:

```toml
[teams.be]
name = "Backend Engineering"
linear_slug = "BE"
default_template = "be-agent"
worktree_dir = "backend"

[teams.be.report]
type = "project"
slug = "backend-roadmap"
```

Then from the meta-repo root:

```bash
# Route worktree to the emailservice sub-repo
shoal new --repo emailservice -w feat/my-feature -b

# Auto-match by path when already inside a sub-repo
cd backend/emailservice && shoal new -w feat/my-feature -b
```

See [Handoffs & Modes](handoffs-and-modes.md) for the full workspace routing reference.

---

## Further Reading

- [Template Inheritance](architecture.md#template-inheritance-and-composition) — Merge semantics for `extends` and `mixins`
- [Architecture — Template Git Config](architecture.md#template-git-config) — Merge semantics for [template.git]
- [Handoffs & Modes](handoffs-and-modes.md) — Handoff packets, operating modes, template tags
- [Shoal Overview](index.md) — Overview of Shoal
