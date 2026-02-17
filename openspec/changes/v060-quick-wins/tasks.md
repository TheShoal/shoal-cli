## 1. Input Validation & Security

- [x] 1.1 Add regex validation (`^[a-zA-Z0-9_-]+$`) on `sys.argv[1]` in `src/shoal/services/mcp_proxy.py`, exiting with error on mismatch or missing arg
- [x] 1.2 Add `shlex.quote()` to socat EXEC command arguments in `src/shoal/services/mcp_pool.py`
- [x] 1.3 Add `KeyError` guard (try/except) around `cmd.format()` in startup command logic in `src/shoal/core/state.py`

## 2. Correctness Fixes

- [x] 2.1 Add `"unknown": 0` to status counts dict in `src/shoal/cli/session.py` summary logic
- [x] 2.2 Fix `get_fish_config_dir()` in `src/shoal/integrations/fish/installer.py` to check `XDG_CONFIG_HOME` env var with fallback to `~/.config/fish`
- [x] 2.3 Update `get_fish_config_dir()` callers in `src/shoal/core/config.py` if needed

## 3. Fish Integration Improvements

- [x] 3.1 Wire `__shoal_mcp_servers` helper to MCP-related `complete` commands in `src/shoal/integrations/fish/templates/completions.fish`
- [x] 3.2 Wire `__shoal_robo_profiles` helper to robo-profile-related `complete` commands in `src/shoal/integrations/fish/templates/completions.fish`
- [x] 3.3 Add `--uninstall` flag to `shoal setup fish` in `src/shoal/integrations/fish/installer.py` that removes all installed fish files

## 4. CLI Ergonomics

- [x] 4.1 Extract shared init/check logic from `src/shoal/cli/__init__.py` and `src/shoal/cli/session.py` into a shared helper function
- [x] 4.2 Update both call sites to use the shared helper
- [x] 4.3 Add `--debug` global flag to Typer app in `src/shoal/cli/__init__.py` that sets `logging.basicConfig(level=DEBUG)`

## 5. Documentation

- [x] 5.1 Add v0.5.0 entry to `CHANGELOG.md` covering fish integration, P0 quick wins, and CI hardening
