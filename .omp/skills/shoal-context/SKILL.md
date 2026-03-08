---
name: shoal-context
description: Current shoal-cli project state — version, recent releases, active docs, and development context. Use when you need the current version, what changed recently, or where to find live state files.
---

# Shoal CLI — Current Project State

**Version**: 0.22.0
**Released**: 2026-03-07
**PyPI**: `shoal-cli` — install with `pipx install shoal-cli` or `uv tool install shoal-cli`

## Recent Releases (this sprint — all 2026-03-07)

### v0.22.0
- `shoal init --refresh-tools` — re-downloads built-in tool profiles without touching custom ones
- `general.auto_commit = true` — stages + conventional-commits worktree before session kill
- Dashboard fzf keybindings: `ctrl-y` approve, `ctrl-g` fork, `ctrl-w` filter waiting, `ctrl-r` reload
- `shoal fin install` now registers to `~/.config/shoal/fins/` by default (`--no-register` to skip)
- `shoal fin ls` defaults to installed fins; `--path` for path-based listing
- Fixed: tmux `base-index != 0` caused all startup commands to fail (now queries live server)
- Fixed: `shoal ls` ID column truncation in narrow terminals
- Fixed: kill guard fired on untracked-only worktrees (`??` lines now excluded)

### v0.21.0
- PyPI publish as `shoal-cli` (was unpublished). CLI binary remains `shoal`.
- OIDC trusted publisher GitHub Actions release workflow
- Pi documented as primary backend; OpenCode as compatibility mode

### v0.20.0
- `setup_commands: list[str]` on templates/mixins — run before agent launch
- Batch MCP ops: `capture_pane`, `send_keys`, `kill_session`, `session_status` accept `session: str | list[str]`
- `async_wait_for_ready` — polls pane every 100ms after session creation instead of fixed sleep

### v0.19.0
- Tool-native prompt delivery: `input_mode = arg | flag | keys` + `prompt_file_prefix`
- OMP/Pi sessions: `input_mode = "arg"`, `prompt_file_prefix = "@"` — file-based delivery, no TUI race
- Status provider abstraction: `pi`, `opencode_compat`, `regex` adapters; visible in `shoal info`
- `shoal fin install`, `shoal fin configure`, `shoal fin ls` — full fin lifecycle CLI
- `shoal fin validate`, `shoal fin inspect`, `shoal fin run`
- Pi-first defaults across config, robo, templates, demo

## Live Docs

| Doc | Purpose |
|-----|---------|
| `ROADMAP.md` | Milestone phases and task checklist |
| `CHANGELOG.md` | Full release history (v0.4.0–v0.22.0) |
| `SHOAL.md` | Ecosystem: Pi primary, OpenCode compat, Fins roadmap |
| `ARCHITECTURE.md` | Design decisions, data flow, component relationships |
| `CONTRIBUTING.md` | Dev setup, quality gates, commit conventions |

## Active Sessions

```bash
shoal ls        # all sessions
shoal status    # quick summary
```

## Quality Gates

```bash
just ci         # full pipeline (lint → typecheck → test → fish-check → security)
just test       # unit tests only
just typecheck  # mypy --strict
```
