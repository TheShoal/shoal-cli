## Why

The v0.5.0 code review identified 10 low-effort, high-value improvements that harden security, fix correctness bugs, improve ergonomics, and reduce maintenance burden. These are all quick wins (5 min to 1 hour each) that should land before v0.6.0 to raise the quality floor before tackling larger refactors.

## What Changes

- Add regex validation on MCP proxy server names to prevent arbitrary command execution via `execvp`
- Add `unknown` to session status counts dict so unknown-status sessions don't crash the summary
- Fix `get_fish_config_dir()` to respect `XDG_CONFIG_HOME` instead of hardcoding `~/.config/fish`
- Wire dead fish completion helpers (`__shoal_mcp_servers`, `__shoal_robo_profiles`) to actual completions
- Deduplicate the `init`/`check` command logic shared between `cli/__init__.py` and `cli/session.py`
- Add `KeyError` guard on `cmd.format()` for startup commands to prevent crashes on malformed templates
- Add `shlex.quote()` to socat EXEC command arguments to prevent shell injection
- Add `--uninstall` flag to `shoal setup fish` to cleanly remove fish integration files
- Add `--debug` flag for verbose logging across CLI commands
- Update `CHANGELOG.md` with a v0.5.0 release entry

## Capabilities

### New Capabilities
- `input-validation`: Regex validation of MCP proxy names and shlex quoting of socat EXEC args
- `fish-uninstall`: `--uninstall` flag for `shoal setup fish` to remove fish integration files
- `debug-logging`: `--debug` global flag for verbose logging output
- `changelog-maintenance`: v0.5.0 CHANGELOG entry documenting fish integration and P0 fixes

### Modified Capabilities
<!-- No existing specs to modify -->

## Impact

- `src/shoal/services/mcp_proxy.py` — name validation added
- `src/shoal/services/mcp_pool.py` — shlex.quote on socat EXEC args
- `src/shoal/cli/session.py` — unknown status count, deduplicated init/check
- `src/shoal/cli/__init__.py` — deduplicated init/check, --debug flag
- `src/shoal/core/config.py` — XDG_CONFIG_HOME support for fish config dir
- `src/shoal/core/state.py` — KeyError guard on startup cmd.format()
- `src/shoal/integrations/fish/installer.py` — XDG fix, --uninstall support
- `src/shoal/integrations/fish/templates/completions.fish` — wire dead helpers
- `CHANGELOG.md` — new v0.5.0 entry
