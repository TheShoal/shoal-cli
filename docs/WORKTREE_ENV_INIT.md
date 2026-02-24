# Worktree Environment Initialization — Design Document

> **Status**: Planning / Not yet implemented
> **Related milestone**: Backlog (post v0.18.0)

## Current State (The Bug)

`SessionTemplateConfig.env` (`models/config.py:227`) is fully parsed and merged but never
applied. Both lifecycle functions (create: lines 667-669, fork: lines 805-807) set only:

```python
await tmux.async_set_environment(tmux_session, "SHOAL_SESSION_ID", session.id)
await tmux.async_set_environment(tmux_session, "SHOAL_SESSION_NAME", session_name)
# <- template_cfg.env never looped here
```

### Why `tmux set-environment` alone is insufficient

`set-environment` affects only NEW panes (new-window/split-window), not the initial pane
created by `new-session`. The agent runs in that initial pane via `send-keys`
(`lifecycle.py:298-299`). Its shell won't see vars set after it started.

The fix requires two mechanisms:
- **Initial pane**: fish `set -gx KEY VALUE` via `send-keys` before agent command
- **Subsequent panes**: `tmux set-environment` (created after, so they inherit correctly)

---

## Approach 1 — Fix the Existing Gap (Bug Fix)

After the SHOAL_SESSION_ID/NAME lines in both create and fork:

```python
if template_cfg and template_cfg.env:
    for key, value in template_cfg.env.items():
        await tmux.async_set_environment(tmux_session, key, value)
    initial_pane = f"{tmux_session}:0.0"
    for key, value in template_cfg.env.items():
        await tmux.async_send_keys(
            initial_pane, f"set -gx {shlex.quote(key)} {shlex.quote(value)}"
        )
```

**Pros**: ~10 lines, no schema changes, fixes declared-but-ignored contract immediately.
**Cons**: Fish-specific `set -gx` (low priority given fish-first scope).
**Impact on backlog worker**: Transparent (goes through `create_session_lifecycle`).
**Recommendation**: **Ship as a bug fix. One iteration, no schema impact.**

---

## Approach 2 — Template `setup_commands` (HIGH VALUE)

New `setup_commands: list[str]` field on `SessionTemplateConfig` and `TemplateMixinConfig`.
Commands run via `send-keys` in the initial pane BEFORE the agent launches.

```toml
[template]
name = "python-dev"
setup_commands = [
  "uv sync --quiet",
  "source .venv/bin/activate.fish",
]
```

**Variable interpolation**: reuse existing `context` dict (work_dir, git_root, session_name,
branch_name, worktree, template_name).

**Template inheritance**:
- `extends`: child's `setup_commands` replaces parent's (same semantics as `windows`)
- `mixins`: appended after resolved base (additive, same as `windows` in mixins)

**Implementation** (in `_run_template_startup_async`, before pane commands):
```python
if template.setup_commands:
    initial_pane = f"{tmux_session}:0.0"
    for cmd in template.setup_commands:
        await tmux.async_send_keys(initial_pane, _format_value(cmd, context, "setup command"))
```

**Failure handling**: `send-keys` has no exit code capture — warn-and-continue default.
Add `setup_strict = true` flag later for hard failures.

**Pros**: Declarative, template-driven, inherits through extends/mixins, covers venv/sync.
**Cons**: Slow commands block session creation; fish-first only; exit code opacity.
**Impact on backlog worker**: Transparent.
**Recommendation**: **HIGH VALUE — canonical venv activation answer.**
**Files**: `models/config.py`, `services/lifecycle.py`, `docs/LOCAL_TEMPLATES.md`

---

## Approach 3 — Project-Level `.shoal.toml` (MEDIUM)

`.shoal.toml` at project root (committed to git), loaded when `work_dir` is in that git tree.

```toml
[env]
PYTHONDONTWRITEBYTECODE = "1"

[setup]
commands = ["uv sync --quiet", "source .venv/bin/activate.fish"]
```

**Discovery**: `Path(git_root) / ".shoal.toml"` — git_root already known at session creation.
Worktrees get it for free (file lives in the git tree).

**Precedence**: `.shoal.toml env` < `template.env` < CLI flags

**Pros**: Travels with repo, zero per-user setup, team-shareable.
**Cons**: Third config layer; new file format.
**Recommendation**: **Medium priority — implement after `setup_commands`.**

---

## Approach 4 — Per-Project in `~/.config/shoal/config.toml` (LOW)

```toml
[projects."/home/user/work/myproject"]
env = { PYTHONDONTWRITEBYTECODE = "1" }
setup_commands = ["uv sync"]
```

**Pros**: Single config file, user-private.
**Cons**: Machine-specific paths, not portable, doesn't travel with repo.
**Recommendation**: **Low priority — Approach 3 is strictly better.**

---

## Approach 5 — direnv / mise Integration (DEFERRED, OPT-IN ONLY)

New `env_manager = "mise" | "direnv" | "none"` field on `SessionTemplateConfig`.

- **mise**: sends `mise trust --quiet && mise install --quiet` before agent
- **direnv**: sends `direnv allow .` — activates via fish hook thereafter

**CRITICAL**: Auto-detection of `.envrc`/`mise.toml` must NEVER happen without opt-in.
`direnv allow .` is a trust grant; `mise install` makes network calls.

**Impact on backlog worker**: Needs explicit invocation (non-interactive shell).
**Recommendation**: **Explicit opt-in only. Implement after `setup_commands` is stable.**

---

## Interaction Matrix

| Approach | Template inheritance | Portability | backlog-run | Code delta | Schema delta |
|---|---|---|---|---|---|
| 1. Fix env gap | Works (resolved pre-lifecycle) | N/A | Transparent | ~10 lines | None |
| 2. setup_commands | extends=replace, mixins=append | Via template | Transparent | ~30 lines | +1 field |
| 3. .shoal.toml | Lifecycle layer, lower precedence | Travels with repo | Transparent | ~50 lines | New file format |
| 4. Per-project cfg | Lifecycle layer, lower precedence | User-local | Transparent | ~30 lines | +section |
| 5. direnv/mise | New env_manager field | Tool-dependent | Explicit invoke | ~60 lines | +1 field |

---

## Recommended Sequencing

**Iteration 1** (bug fix): Fix silent env drop in lifecycle.py create + fork.
Files: `src/shoal/services/lifecycle.py`

**Iteration 2** (feature): Add `setup_commands` to models + lifecycle + docs.
Files: `models/config.py`, `services/lifecycle.py`, `docs/LOCAL_TEMPLATES.md`

**Iteration 3** (feature, lower priority): `.shoal.toml` project-level config loading.
Files: `core/config.py`, `services/lifecycle.py`

**Iteration 4** (deferred): `env_manager` opt-in for direnv/mise.

---

## Open Questions

1. **Shell portability**: Fish only for now (fish-first scope).
2. **Failure handling**: Warn-and-continue default; `setup_strict = true` flag later.
3. **direnv trust**: NEVER automatic — require explicit `env_manager = "direnv"`.
4. **Backlog worker venv (immediate)**: After Iteration 2, add `setup_commands` to the
   backlog template: `["uv sync --quiet", "source .venv/bin/activate.fish"]`.
