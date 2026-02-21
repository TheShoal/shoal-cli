# Branch Summary: feat/pi-agent-integration

## Overview

This branch adds Pi coding agent support to Shoal and implements the v0.8.0
roadmap items (template validation, failure compensation, safety improvements).

## Changes

### Pi Coding Agent Integration

**New files:**
- `examples/config/tools/pi.toml` — Tool config with detection patterns for Pi's
  TUI output (busy: thinking/generating/executing; waiting: permission/confirm/approve;
  error: Error:/FAILED)
- `examples/config/templates/pi-dev.toml` — Two-window session template for pi-tmux
  workflows (65/35 editor+terminal split, plus a tools window)

**Modified:**
- `tests/conftest.py` — Added `pi.toml` to test fixtures so Pi is available in all
  test suites
- `src/shoal/integrations/fish/templates/completions.fish` — Added:
  - `__shoal_tools` and `__shoal_templates` helper functions for dynamic completions
  - `--tool`, `--template`, `--dry-run` flag completions for `shoal new`
  - `template` subcommand group with ls/show/validate completions

### v0.8.0: Template Schema Validation

**Modified:** `src/shoal/models/config.py`
- `SessionTemplateConfig.validate_name()` — Enforces alphanumeric+dash+underscore
- `SessionTemplateConfig.validate_has_windows()` — Requires at least one window
- `TemplateWindowConfig.validate_first_pane_is_root()` — First pane must be split="root"
- `TemplatePaneConfig.validate_size()` — Pane size must be 1-99%

### v0.8.0: MCP Name Validation

**New function:** `validate_mcp_name()` in `src/shoal/services/mcp_pool.py`
- Regex: `^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$`
- Blocks empty, shell metacharacters, dots, slashes, leading dashes, >64 chars

**Enforced at all entry points:**
- `src/shoal/services/mcp_pool.py` — `start_mcp_server()`, `stop_mcp_server()`
- `src/shoal/cli/mcp.py` — `mcp_start()`, `_mcp_attach_impl()`
- `src/shoal/api/server.py` — `McpCreate` model validator, `attach_mcp_to_session()`

### v0.8.0: Failure Compensation (Rollback)

**Modified:** `src/shoal/cli/session.py`
- `_add_impl()` — On tmux creation or startup command failure, rolls back:
  DB session row + worktree (if created)
- `_fork_impl()` — Same rollback on tmux creation failure

**Modified:** `src/shoal/api/server.py`
- `create_session_api()` — On tmux or startup failure, rolls back:
  DB session row + worktree + tmux session
- Startup command failures now caught and handled (previously uncaught KeyError
  would leave orphaned resources)

### v0.8.0: Nvim Diagnostics Safety

**Modified:** `src/shoal/cli/nvim.py`
- Replaced inline `luaeval('...')` string composition with `_DIAGNOSTICS_LUA` constant
- Lua script written to temp file, invoked via `dofile()` path reference
- Eliminates shell quoting issues with single-quote nesting in nvr commands
- Temp file cleaned up in `finally` block
- Added 10-second timeout to subprocess call

### v0.8.0: Startup Contract Unification

**Modified:** `src/shoal/api/server.py`
- API `create_session_api()` now handles `KeyError` in startup command interpolation
  (matching CLI behavior)
- Failure triggers full rollback (DB + tmux + worktree) instead of leaving orphans

### Tests

**New file:** `tests/test_v080_features.py` — 35 tests covering:
- Pi tool config loading and detection patterns (12 tests)
- Template schema validation edge cases (12 tests)
- MCP name validation (9 tests)
- Nvim Lua script safety assertions (2 tests)

### Documentation

**Modified:** `ROADMAP.md`
- Marked v0.7.1 as released with Pi agent and fish enhancement items
- Marked v0.8.0 as released with all checklist items checked

## Test Results

```
292 passed, 1 skipped, 0 failures
```

## Files Changed

| File | Type | Summary |
|------|------|---------|
| `examples/config/tools/pi.toml` | New | Pi tool config |
| `examples/config/templates/pi-dev.toml` | New | Pi dev template |
| `tests/test_v080_features.py` | New | 35 tests for v0.8.0 |
| `src/shoal/models/config.py` | Modified | Template schema validators |
| `src/shoal/services/mcp_pool.py` | Modified | MCP name validation |
| `src/shoal/cli/mcp.py` | Modified | MCP validation at CLI layer |
| `src/shoal/cli/nvim.py` | Modified | Safe Lua diagnostics |
| `src/shoal/cli/session.py` | Modified | Failure rollback |
| `src/shoal/api/server.py` | Modified | Failure rollback + startup contract |
| `src/shoal/integrations/fish/templates/completions.fish` | Modified | Tool/template completions |
| `tests/conftest.py` | Modified | Pi test fixture |
| `ROADMAP.md` | Modified | v0.7.1 + v0.8.0 marked complete |
