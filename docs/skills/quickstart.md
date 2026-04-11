# Quickstart

> Create your first skill and have it running in a Shoal session in under 5 minutes.

---

## 1. Create the skill directory

```bash
mkdir -p .shoal/skills/my-first-skill
```

The directory name must match the `name` field in frontmatter. Use lowercase letters and hyphens only.

---

## 2. Write `SKILL.md`

```markdown
---
name: my-first-skill
description: Add a two-line summary of what this skill does and when to use it.
---

# My First Skill

Step-by-step instructions for the agent when this skill is activated.

## Steps

1. Read the relevant files
2. Make the change
3. Verify the change works
```

Required frontmatter fields:

| Field | Rules |
|-------|-------|
| `name` | Lowercase, hyphens only, matches directory name |
| `description` | 1–1024 characters. Include keywords agents use to match tasks |

Optional:

| Field | Purpose |
|-------|---------|
| `allowed-tools` | Restrict which tools the agent may use |
| `metadata` | Arbitrary key-value pairs |
| `license` | License name or path to bundled LICENSE file |

---

## 3. Verify the skill

```bash
shoal skill ls
```

Output lists all discovered skills and their source paths. Your new skill should appear under `.shoal/skills/`.

For strict validation:

```bash
shoal skill validate my-first-skill
```

---

## 4. Test it in a session

Start a session and invoke the skill by name:

- **Claude Code / omp**: `/my-first-skill`
- **OpenCode**: invoke via skill name in prompt

The agent loads the full `SKILL.md` body when it activates the skill.

---

## 5. Share it across tools (optional)

If your repo uses multiple agent tools, Shoal can keep a single `.shoal/skills/` source of truth.

See [Cross-Tool Skills](cross-tool.md) for setup options (symlinks, transpilation, or `setup_commands`).

---

## What's next

- **[Reference](reference.md)** — full frontmatter schema, body structure, and Shoal-specific behaviour
- **[Cross-Tool Skills](cross-tool.md)** — share skills with OpenCode, omp, and Claude Code simultaneously
