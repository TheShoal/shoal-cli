# Release Process

This document outlines Shoal's release workflow using Semantic Versioning.

## Versioning Convention

Shoal follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html): `MAJOR.MINOR.PATCH`

- **MAJOR** (e.g., 1.0.0 → 2.0.0): Breaking changes to CLI commands, config format, or API.
- **MINOR** (e.g., 0.4.0 → 0.5.0): New features, non-breaking enhancements, or significant refactors.
- **PATCH** (e.g., 0.4.0 → 0.4.1): Bug fixes, docs updates, or minor polish.

### Pre-1.0 Flexibility
Before v1.0.0, MINOR versions may include breaking changes as we stabilize the API surface.

---

## Release Checklist

### 1. Pre-Release: Code Preparation
- [ ] All planned features/fixes are merged to `main`
- [ ] All tests pass: `pytest`
- [ ] Linting passes: `ruff check . && ruff format .`
- [ ] Type checking passes: `mypy src/`
- [ ] Manual testing of core workflows:
  - `shoal new`, `shoal ls`, `shoal popup`
  - `shoal demo start` (if applicable)
  - Robo supervisor workflow (if changed)

### 2. Update Documentation
- [ ] **CHANGELOG.md**: Move `[Unreleased]` items to `[X.Y.Z] - YYYY-MM-DD`
- [ ] **ROADMAP.md**: Mark completed items, update next milestone
- [ ] **README.md**: Update version badge, features, or examples if needed
- [ ] **pyproject.toml**: Bump `version = "X.Y.Z"`

### 3. Commit & Tag
```bash
# Commit version bump
git add pyproject.toml CHANGELOG.md ROADMAP.md README.md
git commit -m "chore: bump version to X.Y.Z"

# Create annotated tag
git tag -a vX.Y.Z -m "Release vX.Y.Z: <brief summary>"

# Push to remote
git push origin main --tags
```

### 4. GitHub Release
- Go to [Releases](https://github.com/usmobile/shoal/releases) → "Draft a new release"
- Select the tag `vX.Y.Z`
- Release title: `vX.Y.Z: <One-Liner Summary>`
- Description: Copy the relevant section from `CHANGELOG.md`
- Attach any demo videos, screenshots, or binary assets

### 5. Internal Announcement
- Notify the team in Slack/email
- Highlight key changes and migration steps (if any)

### 6. Post-Release: Prepare Next Version
- [ ] Add new `[Unreleased]` section to `CHANGELOG.md`:
  ```md
  ## [Unreleased]
  
  ### Added
  ### Changed
  ### Fixed
  ```
- [ ] Commit: `git commit -m "chore: prepare for next release"`

---

## Version Bump Decision Tree

**When should I create a new release?**

| Scenario | Version Type | Example |
|----------|--------------|---------|
| Breaking CLI command or config change | **MAJOR** | Remove `shoal add`, change `config.toml` schema |
| New feature or command | **MINOR** | Add `shoal export` command |
| Significant refactor (internal only) | **MINOR** | Migrate to async architecture |
| Bug fix, docs update, or polish | **PATCH** | Fix crash in `shoal status`, update README |

**When to release?**
- **PATCH**: As soon as a critical bug is fixed.
- **MINOR**: When a feature is complete, tested, and documented.
- **MAJOR**: Only after thorough testing and migration guide preparation (rare pre-1.0).

---

## Example Release Flow

**Scenario**: You've just finished adding a new `shoal export` command.

1. **Determine version**: New feature → **MINOR** bump → `0.4.0` → `0.5.0`
2. **Update docs**:
   - Add entry to `CHANGELOG.md` under `[0.5.0]`
   - Mark "export command" as completed in `ROADMAP.md`
   - Update `pyproject.toml` version
3. **Commit**: `git commit -m "chore: bump version to 0.5.0"`
4. **Tag**: `git tag -a v0.5.0 -m "Release v0.5.0: Export command"`
5. **Push**: `git push origin main --tags`
6. **GitHub**: Create release from tag, copy changelog
7. **Announce**: Post in Slack with usage example

---

## Emergency Hotfix Process

If a critical bug is discovered in production:

1. **Create hotfix branch** from the release tag:
   ```bash
   git checkout -b hotfix/v0.4.1 v0.4.0
   ```
2. **Fix the bug** and commit.
3. **Follow the release checklist** for a PATCH version.
4. **Merge back to main**:
   ```bash
   git checkout main
   git merge hotfix/v0.4.1
   git branch -d hotfix/v0.4.1
   ```

---

## FAQ

**Q: Should I version every commit?**  
No. Only create a release when you have a cohesive set of changes worth announcing.

**Q: What if I forgot to update the changelog?**  
Add a follow-up commit before tagging. If you already tagged, create a new PATCH release with the updated docs.

**Q: Can I delete a release?**  
GitHub releases can be deleted, but **git tags should not be deleted** once pushed. If you made a mistake, create a new PATCH release.

**Q: When do we hit v1.0.0?**  
When the CLI surface, config schema, and core workflows are stable enough for production use at US Mobile without frequent breaking changes.

---

## Tooling & Automation

Future improvements:
- [ ] Add `bump-version.sh` script to automate version updates
- [ ] CI/CD: Auto-publish GitHub releases on tag push
- [ ] Pre-commit hook to check for `[Unreleased]` section in CHANGELOG.md
