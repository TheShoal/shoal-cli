# Reference

> Complete format specification for Shoal skills. Based on the [Agent Skills](https://agentskills.io) open format.

For a quick start, see [Quickstart](quickstart.md). For cross-tool sharing, see [Cross-Tool Skills](cross-tool.md).

---

## Directory structure

A skill is a directory containing at minimum a `SKILL.md` file:

```
skill-name/
├── SKILL.md           # Required: metadata + instructions
├── scripts/           # Optional: executable helpers
├── references/        # Optional: supplementary docs
└── assets/            # Optional: templates, schemas, data
```

---

## `SKILL.md` format

YAML frontmatter followed by Markdown body.

### Frontmatter fields

| Field | Required | Constraints |
|-------|----------|-------------|
| `name` | Yes | 1–64 chars. Lowercase letters and hyphens only. Must match the directory name. |
| `description` | Yes | 1–1024 chars. Describe what the skill does and when to use it. Include keywords. |
| `allowed-tools` | No | Space-separated string of pre-approved tools (e.g. `Read Glob Bash`). |
| `license` | No | Short license name or path to bundled LICENSE file. |
| `metadata` | No | Arbitrary key-value map. Shoal does not consume this field. |

### Body content

The Markdown body is the skill's instructions. Write whatever helps the agent complete the task.

Recommended sections:

```markdown
## Steps
1. ...
2. ...

## Output Format
Describe the expected output.

## Edge Cases
...
```

Keep the body under 500 lines. Move detailed reference material to `references/REFERENCE.md` and load it on demand.

---

## Progressive disclosure

Shoal loads skill metadata at session startup (for discovery and matching) and the full body only when the agent activates the skill.

| Content | When loaded |
|---------|-------------|
| `name`, `description` | At session startup |
| Full `SKILL.md` body | On skill activation |
| `scripts/`, `references/`, `assets/` | On demand |

---

## File references

Use relative paths from the skill root:

```markdown
See [the reference guide](references/REFERENCE.md) for details.

Run the extraction script:
scripts/extract.py
```

Keep references one level deep from `SKILL.md`. Avoid deeply nested chains.

---

## Shoal-specific behaviour

### Discovery paths

Shoal scans these locations at session startup:

1. `<git-root>/.shoal/skills/<name>/SKILL.md`
2. `~/.config/shoal/skills/<name>/SKILL.md`

Local skills (`~/.shoal/skills/`) take precedence over global ones (`~/.config/shoal/skills/`).

### Sync on worktree creation

When Shoal creates a worktree, it can sync skills into tool-native paths:

```toml
[template.worktree]
post_worktree_create = "scripts/shoal-skill-sync.sh"
```

See [Cross-Tool Skills](cross-tool.md) for the sync script and `setup_commands` alternative.

### Validation

```bash
shoal skill validate my-skill
```

Validates:
- `name` matches the directory name
- `name` uses only lowercase + hyphens
- `description` is non-empty and under 1024 chars
- `SKILL.md` exists and has valid frontmatter

### Listing skills

```bash
shoal skill ls
```

Lists all discovered skills with source path and which sessions have them active.

---

## Example: Code review skill

```markdown
---
name: code-review
description: Review staged changes for quality, security, and test coverage.
  Use when asked to review, critique, or check changes before merge.
allowed-tools: Read Glob Grep Bash
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
- **Important**: Should fix; creates tech debt if skipped
- **Nice-to-have**: Cleanup opportunities
```
