## Context

Shoal v0.5.0 shipped fish shell integration and applied all P0 quick wins from the initial code review. The codebase now has solid subprocess timeout handling, resilient watcher loops, and fixed fish templates. However, 10 additional quick wins were identified during the v0.5.0 review that remain unaddressed. These are all isolated, low-risk changes that collectively raise the security and reliability floor before v0.6.0's larger refactoring efforts.

The changes span 9 source files and 1 documentation file. None introduce new dependencies, change data models, or alter the public API surface beyond adding two CLI flags.

## Goals / Non-Goals

**Goals:**
- Eliminate the two remaining injection vectors (MCP proxy name, socat EXEC args)
- Fix the `unknown` status crash in session summary counts
- Make fish integration respect XDG conventions and be cleanly removable
- Wire dead fish completion helpers so tab completion actually works for MCP servers and robo profiles
- Reduce maintenance burden by deduplicating init/check logic
- Add defensive error handling for startup command template formatting
- Provide `--debug` flag for user-facing troubleshooting
- Document v0.5.0 in CHANGELOG.md

**Non-Goals:**
- Fixing the read-modify-write race in db.py (requires larger transactional refactor)
- Deduplicating session creation between CLI and API (architectural change for v0.6.0)
- Fixing CORS wildcard configuration (needs auth design discussion)
- Adding automated tests (covered separately in v0.6.0 testing plan)
- Refactoring `_initialized` class variable pattern in ShoalDB

## Decisions

### 1. MCP proxy name validation: regex allowlist
Validate `sys.argv[1]` in `mcp_proxy.py` against `^[a-zA-Z0-9_-]+$` before passing to `execvp`. This is the simplest defense — reject anything that isn't a plain identifier. Alternative: path-based lookup table — rejected as over-engineered for a proxy entry point.

### 2. Socat EXEC quoting: shlex.quote
Wrap each argument in the socat EXEC command string with `shlex.quote()` in `mcp_pool.py`. This prevents shell metacharacter injection through MCP server config values. Alternative: subprocess list form — rejected because socat EXEC requires a shell command string.

### 3. Fish config dir: os.environ.get with fallback
Change `get_fish_config_dir()` to check `XDG_CONFIG_HOME` env var first, falling back to `~/.config/fish`. This follows the XDG Base Directory spec that fish itself uses. No alternative needed — this is the standard approach.

### 4. Fish uninstall: reverse of install
Add `--uninstall` flag that removes the exact files the installer creates (bootstrap, completions, quick-attach, conf.d sourcer). Uses the same path resolution logic as install. Alternative: uninstall command — rejected to keep CLI surface small.

### 5. Debug logging: global Typer callback
Add `--debug` as a Typer global option that sets `logging.basicConfig(level=DEBUG)`. This affects all commands uniformly. Alternative: per-command flag — rejected as redundant and harder to maintain.

### 6. Init/check deduplication: extract shared helper
Move the common init/check logic from `cli/__init__.py` into a shared function in a new or existing module, then call from both places. This eliminates ~40 lines of duplication.

### 7. Startup command KeyError guard: try/except
Wrap `cmd.format(**context)` calls in try/except KeyError to log a warning instead of crashing the session. This is the minimal defensive fix.

## Risks / Trade-offs

- [MCP name regex too strict] → If legitimate server names use dots or other chars, the regex will reject them. Mitigation: start strict, widen if real names are rejected.
- [Fish uninstall deletes user modifications] → If users manually edited installed files, uninstall removes their changes. Mitigation: print each file being removed so the user sees what's happening.
- [Debug output too verbose] → `--debug` may produce overwhelming output. Mitigation: this is opt-in, and users who use it expect verbosity.
- [Deduplication changes import structure] → Moving init/check logic may affect CLI startup time or import order. Mitigation: keep the helper in an existing module to minimize import changes.
