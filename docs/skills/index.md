# Skills

> A lightweight, open format for extending Shoal agents with domain-specific knowledge and workflows.

Skills are `.md` files with YAML frontmatter that agents read to understand project conventions, team workflows, and domain rules. Shoal sessions discover skills at startup and make them available to whatever agent tool is running.

---

## What are skills?

A skill is a focused, self-contained set of instructions for a specific task:

- **When to use it** — described in the `description` field
- **What to do** — written in the body as step-by-step guidance
- **What tools to use** — optionally restricted via `allowed-tools`

Skills are the primary mechanism for giving agents context that isn't in the codebase: team conventions, review criteria, ticket workflow, handoff format, release process.

---

## Supported tools

Shoal skills work across every agent tool Shoal supports:

| Tool | Discovery path | Format |
|------|--------------|--------|
| Claude Code | `.claude/skills/<name>/SKILL.md` | Markdown + YAML frontmatter |
| omp | `.omp/skills/<name>/SKILL.md` | Markdown + YAML frontmatter |
| OpenCode | `.opencode/agents/<name>.md` | Markdown |
| pi | `.pi/skills/<name>/SKILL.md` | Markdown + YAML frontmatter |

Shoal handles the format differences automatically. See [Cross-Tool Skills](cross-tool.md) for how sharing works.

---

## Shoal's role

Shoal manages the **skill lifecycle** within a session:

- **Discovery** — Shoal scans `.shoal/skills/`, `~/.config/shoal/skills/`, and tool-native paths at session startup
- **Sync** — Shoal symlinks skills into tool-native directories on worktree creation
- **List** — `shoal skill ls` shows all discovered skills with their paths
- **Validation** — `shoal skill validate <name>` checks frontmatter and file structure

---

## Page index

- [Quickstart](quickstart.md) — create and install your first skill in 5 steps
- [Reference](reference.md) — full skill format specification with Shoal-specific behaviour
- [Cross-Tool Skills](cross-tool.md) — share skills across multiple agent tools

---

## Built-in skills

Shoal ships with skills for its own workflows:

| Skill | Purpose |
|-------|---------|
| `shoal-setup` | Bootstrap `.shoal/` config for a new repo |
| `shoal-verify` | Run `just ci` and surface the result |
| `shoal-handoff` | Pack session context for a follow-up agent |
| `shoal-scaffold` | Generate new modules, commands, or services |
| `shoal-review` | Structured code review (Critical → Important → Nice-to-have) |
| `shoal-release` | Cut a release: bump, changelog, commit, tag |
| `shoal-changelog` | Generate CHANGELOG entries from git history |
| `shoal-roadmap` | Add items to the ROADMAP backlog |
| `shoal-coverage` | Run tests with coverage and surface gaps |
| `shoal-deps` | Audit dependencies for updates and security |
| `shoal-arch-check` | Validate architectural invariants |

See [Reference](reference.md) for how to write your own.
