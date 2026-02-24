---
name: shoal-changelog
description: Generate or update CHANGELOG.md entries from git history since the last release. Use before cutting a release or to keep the changelog current during development.
argument-hint: [preview|write|diff]
disable-model-invocation: true
allowed-tools: Bash, Read, Edit, Grep, Glob
---

# Shoal Changelog Generator

Analyze git history since the last release and generate properly categorized CHANGELOG.md entries following the Keep a Changelog format.

## Subcommands

### `preview` (default) — Show What Would Be Added

1. Find the last release tag: `git describe --tags --abbrev=0`
2. Get all commits since that tag: `git log <tag>..HEAD --oneline --no-merges`
3. For each commit, categorize by conventional commit type:
   - `feat:` → **Added**
   - `fix:` → **Fixed**
   - `docs:` → (skip — documentation changes don't go in changelog)
   - `refactor:` → **Changed**
   - `perf:` → **Changed** (with performance note)
   - `test:` → (skip — test-only changes)
   - `chore:` → (skip — unless it's a dependency or build change worth noting)
   - `style:` → (skip)
4. For meaningful commits, read the full commit message (`git log <hash> -1`) to get the body for detail
5. For `feat` and `fix` commits, also check `git diff <hash>~1..<hash> --stat` to understand scope
6. Present the draft entries:

```
## [Unreleased] — Draft Entries

### Added
- **Feature name**: Brief description of what it does and why
  - Sub-bullet for implementation detail if notable

### Changed
- **What changed**: Brief description of the change

### Fixed
- **Bug description**: What was broken and how it was fixed

### Stats
- N commits analyzed, M changelog-worthy entries generated
- Test count: (run `uv run pytest --co -q | tail -1` to get current count)
```

### `write` — Write Entries to CHANGELOG.md

1. Run the `preview` analysis
2. Read current `CHANGELOG.md`
3. Merge new entries under `## [Unreleased]`:
   - Group by category (Added, Changed, Fixed, Removed)
   - Deduplicate — skip entries that already exist (fuzzy match on key phrases)
   - Preserve existing unreleased entries
4. Write the updated CHANGELOG.md
5. Show the diff of what was added

### `diff` — Show Raw Git Diff for Manual Review

1. Find last release tag
2. Show: `git diff <tag>..HEAD --stat` for file-level overview
3. Show: `git log <tag>..HEAD --oneline --no-merges` for commit list
4. Highlight files with the most changes (potential changelog-worthy work)

## Changelog Style Guide (from existing entries)

Read the existing CHANGELOG.md to match the established voice:

- **Bold lead**: Each entry starts with `**Feature name**:` in bold
- **Active voice**: "Added", "Fixed", "Replaced" — not "We added" or "This was fixed"
- **Implementation detail in sub-bullets**: Keep the top-level entry user-facing, put technical details as sub-bullets
- **Cross-references**: Link to relevant docs where applicable
- **Stats section**: End each release with test count and other metrics
- **No commit hashes**: The changelog is for users, not git archeology
- **No trivial entries**: Skip reformatting, comment changes, test-only changes

## Rules

- Always read the existing CHANGELOG.md first to match style
- Never remove existing entries — only add or merge
- Group related commits into single entries (e.g., 5 commits for "template inheritance" = 1 entry)
- Include the test count stat by actually running `uv run pytest --co -q | tail -1`
- If the `[Unreleased]` section already has substantial entries, show them alongside new ones for dedup review
