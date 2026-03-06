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

## When to Use Local vs Global

| Use case | Location |
|----------|----------|
| Shared base layouts (`base-dev`) | Global (`~/.config/shoal/templates/`) |
| Tool-specific defaults (`claude-dev`, `codex-dev`, `pi-dev`) | Global |
| Project-specific sessions | Local (`.shoal/templates/`) |
| Project-specific MCP sets | Local mixins (`.shoal/templates/mixins/`) |

---

## Further Reading

- [Template Inheritance](architecture.md#template-inheritance-and-composition) — Merge semantics for `extends` and `mixins`
- [Shoal Overview](index.md) — Overview of Shoal
