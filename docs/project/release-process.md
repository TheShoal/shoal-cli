# Release Process

Shoal follows a straightforward single-maintainer release process built on conventional commits and automated PyPI publishing.

## Steps

### 1. Commit (conventional format required)

All commits must follow [Conventional Commits](https://www.conventionalcommits.org/). The `gitlint` pre-commit hook enforces this. See [Commit Guidelines](commit-guidelines.md).

### 2. Bump version

Version is declared in `src/shoal/__init__.py` as `__version__`. Update it before tagging:

```python
# src/shoal/__init__.py
__version__ = "0.38.0"
```

`pyproject.toml` reads this via `hatch.version` dynamic versioning — no dual update required.

### 3. Update CHANGELOG.md

Add a `## [X.Y.Z] - YYYY-MM-DD` section with **Added / Changed / Fixed** subsections.

### 4. Tag and push

```bash
git tag vX.Y.Z
git push origin main
git push origin vX.Y.Z
```

### 5. Create a GitHub Release

Navigate to **Releases → Draft a new release**, select the tag, paste in the changelog section, and publish.

The GitHub Actions [`release.yml`](https://github.com/TheShoal/shoal-cli/blob/main/.github/workflows/release.yml) workflow triggers on release publication and:

1. Builds the distribution (`uv build`)
2. Publishes to PyPI via OIDC trusted publisher (`pypa/gh-action-pypi-publish`) — no token required

## CI gate

All merges to `main` run the full CI matrix before publishing is allowed:

| Job | Command |
|-----|---------|
| Lint | `just lint` |
| Typecheck | `just typecheck` |
| Test | `just test` |
| Fish check | `just fish-check` |
| Security | `just security` |

Run `just ci` locally before tagging to catch issues early.

## PyPI package

Package name: **`shoal-cli`**

```bash
uv tool install shoal-cli          # latest
uv tool install shoal-cli==0.37.2  # pinned
```

Optional extras: `shoal-cli[mcp]`
