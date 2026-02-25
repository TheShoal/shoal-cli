---
name: shoal-release
description: Cut a new shoal release. Bumps version, updates changelog, commits, and tags. Use when ready to release a new version.
argument-hint: <version>
disable-model-invocation: true
allowed-tools: Read, Edit, Bash, Grep, Glob
---

# Shoal Release

Cut a new release for the shoal project. `$ARGUMENTS` must be a semver version (e.g., `0.16.0`).

## Pre-flight

1. Verify clean working tree: `git status --porcelain` must be empty. Abort if dirty.
2. Verify on `main` branch. Abort if not.
3. Run `just ci` — abort if any check fails.

## Version Bump

4. Read `pyproject.toml` and update the `version = "..."` line to `$ARGUMENTS`.
5. Read `src/shoal/__init__.py` and update `__version__ = "..."` to `$ARGUMENTS`.
6. Verify both files now show the same version.

## Changelog

7. Read `CHANGELOG.md`. Replace `## [Unreleased]` with:
   ```
   ## [Unreleased]

   ## [$ARGUMENTS] - YYYY-MM-DD
   ```
   Use today's date. Preserve all existing content under the old Unreleased heading — it moves under the new version heading.

## Commit and Tag

8. Stage the 3 changed files: `pyproject.toml`, `src/shoal/__init__.py`, `CHANGELOG.md`
9. Commit: `chore: bump version to $ARGUMENTS`
10. Create annotated tag: `git tag -a v$ARGUMENTS -m "Release v$ARGUMENTS"`

## Confirm Before Push

11. Show the user a summary: version, changed files, commit hash, tag name.
12. Ask the user to confirm before pushing. Do NOT push automatically.
13. If confirmed: `git push origin main && git push origin v$ARGUMENTS`

## Rules

- Never skip `just ci`. A failing CI means no release.
- Always bump BOTH `pyproject.toml` and `__init__.py` — they must match.
- The `[Unreleased]` section must always exist after the release entry.
