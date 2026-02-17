# Shoal Code Review — v0.5.0 (`feature-fish-integration`)

## 1. Architecture Summary

```
User
  │
  ├── CLI (typer)                    ─── src/shoal/cli/
  │     ├── session.py  (new/ls/attach/fork/kill/status/logs/rename/info)
  │     ├── robo.py     (supervisor agent management)
  │     ├── mcp.py      (MCP server pool commands)
  │     ├── worktree.py (git worktree lifecycle)
  │     ├── watcher.py  (start/stop background daemon)
  │     ├── demo.py     (demo environment)
  │     ├── nvim.py     (neovim integration)
  │     └── setup.py    (fish shell installer)
  │
  ├── API (FastAPI)                  ─── src/shoal/api/server.py
  │     ├── REST endpoints (CRUD sessions, MCP pool, status)
  │     └── WebSocket (real-time status broadcast)
  │
  ├── Dashboard (fzf popup)          ─── src/shoal/dashboard/popup.py
  │
  └── Fish Shell Integration         ─── src/shoal/integrations/fish/
        ├── installer.py (copies templates to ~/.config/fish/)
        └── templates/ (bootstrap, completions, dashboard, quick-attach)

                          ┌──────────────────────┐
                          │    Core Layer         │
                          │  ┌────────────────┐   │
                          │  │ state.py       │   │  Session CRUD + validation
                          │  │ db.py          │   │  Async SQLite (WAL mode)
                          │  │ config.py      │   │  TOML config loading
                          │  │ tmux.py        │   │  Subprocess wrappers
                          │  │ git.py         │   │  Subprocess wrappers
                          │  │ detection.py   │   │  Pure pane → status function
                          │  │ notify.py      │   │  macOS osascript
                          │  │ theme.py       │   │  Rich/tmux styling
                          │  └────────────────┘   │
                          └──────────────────────┘

Services:
  watcher.py    ── polls tmux panes, updates status in DB, sends notifications
  mcp_pool.py   ── socat-based MCP server lifecycle (start/stop/health)
  mcp_proxy.py  ── stdio-to-unix-socket bridge via socat execvp
  status_bar.py ── tmux status bar generator

Source of truth: SQLite DB (~/.local/state/shoal/shoal.db)
  - Sessions stored as JSON blobs with id/name index
  - Robo states in separate table
  - WAL mode for concurrent read access
  - Single-writer with no locking (read-modify-write pattern)

Control flow: CLI + API are parallel entry points into the same core layer.
Both call state.py functions which hit db.py. Tmux/git wrappers are sync
subprocess calls. The watcher is a separate process polling the same DB.
```

**Observations:**
- Fish scripts are thin (good) -- just abbreviations, keybindings, and fzf wrappers
- tmux commands are centralized in `core/tmux.py` (good)
- CLI and API duplicate session creation logic (lines 73-221 in `session.py` vs 265-353 in `server.py`) -- this is a maintenance risk
- No single "controller" layer -- CLI and API both directly import and orchestrate core functions

---

## 2. Top 10 Issues (Ranked by Severity)

### 1. Unauthenticated API with RCE capabilities — `server.py:196-202,422-428,592`

The API binds to `0.0.0.0:8080` with `allow_origins=["*"]`, no authentication, and exposes `POST /sessions/{id}/send` which sends arbitrary keystrokes to tmux panes. This is a remote code execution vector.

```python
# server.py:422-428 — anyone on the network can type into your agents
@app.post("/sessions/{session_id}/send")
async def send_keys_api(session_id: str, body: SendKeysRequest):
    s = await get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    tmux.send_keys(s.tmux_session, body.keys)  # arbitrary keystrokes
    return {"message": "Keys sent"}
```

### 2. Command injection via socat `EXEC:` — `mcp_pool.py:84-88`

User-supplied `command` from `POST /mcp` is passed to socat's `EXEC:` which shell-evaluates it. An attacker can execute arbitrary shell commands.

```python
# mcp_pool.py:84-88
proc = subprocess.Popen(
    ["socat", f"UNIX-LISTEN:{socket},fork,reuseaddr",
     f"EXEC:{command},pipes"],  # shell-evaluated by socat
    ...
)
```

### 3. Command injection via fzf `--preview` — `quick-attach.fish:6`

fzf's `{}` placeholder is shell-evaluated. If a session name contained metacharacters (currently mitigated by `validate_session_name`), it would be RCE. The defense is implicit, not explicit.

```fish
# quick-attach.fish:6 — fzf shell-evaluates {}
--preview="shoal info {}"
```

### 4. Read-modify-write race in DB — `db.py:139-147`

`update_session` reads the full JSON blob, modifies it in Python, and writes it back. Concurrent updates (watcher + CLI, or two API requests) silently lose data. No row-level locking.

```python
# db.py:139-147
async def update_session(self, session_id: str, **fields):
    session = await self.get_session(session_id)  # read
    updated = session.model_copy(update=fields)   # modify in Python
    await self.save_session(updated)               # overwrite entire blob
```

### 5. Lossy tmux name sanitization causes silent collisions — `state.py:56-61`

Two distinct session names like `my.project` and `my-project` both produce `shoal_my-project`. The second `tmux.new_session` will fail or collide with no detection.

```python
# state.py:56-61
def _sanitize_tmux_name(name: str) -> str:
    return name.replace(".", "-").replace(":", "-").replace("/", "-")  # lossy
```

### 6. No subprocess timeouts anywhere — `tmux.py`, `git.py`

Every `subprocess.run` call blocks indefinitely. A hung tmux server, unresponsive git remote, or credential prompt hangs the entire process (CLI, API server, or watcher).

```python
# tmux.py:27-32 — no timeout parameter
return subprocess.run(["tmux", *args], capture_output=capture, text=True, check=check)
```

### 7. Startup command template injection — `models/config.py:20`, `session.py:197-204`

The default startup command `"send-keys -t {tmux_session} '{tool_command}' Enter"` embeds `tool_command` inside single quotes. If `tool_command` contains `'`, the tmux command breaks/injects. Additionally, `cmd.format()` with user-controlled values has no `KeyError` handling for undefined template variables.

### 8. Orphaned session state on fork tmux failure — `session.py:412-421`

In `_fork_impl`, the session is created in DB (line 413-414) before `tmux.new_session` (line 421). If tmux fails, the DB session is never cleaned up (unlike `_add_impl` which has a try/except on lines 180-191).

### 9. Watcher crash on single poll failure — `watcher.py:47-50`

The main loop has no per-cycle exception handling. If `_poll_cycle` throws (e.g., DB locked, malformed TOML, or unexpected exception type), the watcher exits entirely. All status detection stops.

```python
# watcher.py:47-50
while self._running:
    await self._poll_cycle()    # if this throws, watcher dies
    await asyncio.sleep(self.poll_interval)
```

### 10. Duplicate session creation logic — `session.py:73-221` vs `server.py:265-353`

The CLI's `_add_impl` and the API's `create_session_api` duplicate the entire session creation flow (~100 lines each): git validation, worktree setup, name generation, tmux session creation, startup commands. They will inevitably diverge. The API version already has subtle differences (e.g., different worktree path inference, no `_infer_branch_name` call).

---

## 3. Reliability Hardening Plan

### P0 — Do before sharing with other users

- [ ] **Add subprocess timeouts.** Add `timeout=30` to `tmux._run()` and git `_run()`. Use `timeout=120` for `git.push()`. Handle `subprocess.TimeoutExpired`.
- [ ] **Wrap watcher poll cycle in try/except.** In `watcher.py:48`, catch `Exception` around `_poll_cycle()`, log it, and continue.
- [ ] **Add tmux cleanup on fork failure.** In `session.py:421`, wrap `tmux.new_session` in try/except and `delete_session` on failure (mirror `_add_impl`'s pattern).
- [ ] **Detect tmux name collisions.** Before `tmux.new_session`, call `tmux.has_session(tmux_session)` and fail with a clear error if a collision is detected from lossy sanitization.
- [ ] **Fix `ConnectionManager.disconnect` crash.** Use `set` instead of `list` for `active_connections`, or wrap `.remove()` in try/except.
- [ ] **Fix `broadcast` to handle per-connection errors.** Catch exceptions per-connection so one broken WS doesn't block others.

### P1 — Do before scaling beyond a handful of sessions

- [ ] **Make `update_session` atomic.** Use `UPDATE sessions SET data = ? WHERE id = ?` with SQL-level field updates instead of read-modify-write. Or use `BEGIN IMMEDIATE` transactions.
- [ ] **Add `status is-interactive; or return` to `bootstrap.fish`.** Prevents errors in non-interactive fish contexts.
- [ ] **Change `set -U` to `set -g` in bootstrap.fish:38.** Universal variable writes on every command is a performance concern.
- [ ] **Add stale PID/socket cleanup on watcher/mcp startup.** Check for orphaned processes and clean up before starting.
- [ ] **Add PID file locking for watcher.** Use `fcntl.flock` to prevent duplicate watcher instances.

### P2 — Long-term reliability

- [ ] **Consolidate session creation into a single service function** called by both CLI and API.
- [ ] **Add structured logging** (JSON format option) with log rotation for watcher and API.
- [ ] **Add health check endpoint that verifies DB connectivity.**
- [ ] **Add graceful degradation** — if DB is inaccessible, CLI should show a clear error rather than a Python traceback.

---

## 4. Security Findings

### Finding 1: Unauthenticated RCE via API

**Impact:** Critical. Anyone on the same network can execute arbitrary commands in any tmux session.

**Fix (immediate):**
```python
# server.py — change default bind to localhost
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8080)  # was 0.0.0.0

# cli/__init__.py — change default host
def serve(host: str = "127.0.0.1", port: int = 8080):
```

**Fix (proper):** Add token-based auth. Generate a token on `shoal init`, store it in config, require it as a header.

### Finding 2: Command injection via MCP pool

**Impact:** High via API, low via CLI (CLI requires local access).

**Fix:**
```python
# mcp_pool.py — use shlex.quote or validate command against allowlist
import shlex

# Option A: Quote the command for socat's EXEC
safe_cmd = shlex.quote(command)
proc = subprocess.Popen(
    ["socat", f"UNIX-LISTEN:{socket},fork,reuseaddr",
     f"EXEC:{safe_cmd},pipes"],
    ...
)

# Option B (better): Only allow known servers, reject arbitrary commands from API
@app.post("/mcp", ...)
async def start_mcp_server_api(data: McpCreate):
    if data.command and data.name not in KNOWN_SERVERS:
        raise HTTPException(400, "Custom MCP commands not allowed via API")
```

### Finding 3: fzf preview command injection

**Impact:** Medium. Currently mitigated by `validate_session_name` restricting charset to `[a-zA-Z0-9_/.-]`, but the defense is implicit.

**Fix:**
```fish
# quick-attach.fish — use single quotes around {} to prevent word splitting
--preview='shoal info -- {}'
# Also add -- to prevent flag injection from names starting with -
```

### Finding 4: AppleScript injection (minor, already handled)

`notify.py` correctly escapes `"` and `\`. However, it doesn't handle other AppleScript control characters like `\r`, `\n`, or `\t`, which while not injection vectors, could corrupt the notification display. Low priority.

### Finding 5: Config directory permissions not validated

If `~/.config/shoal/` or `~/.local/state/shoal/` is world-writable, any local user could inject tool configs that execute arbitrary commands via startup commands.

**Fix:**
```python
# config.py — check permissions on ensure_dirs()
import stat

def ensure_dirs():
    for d in (config_dir(), state_dir(), runtime_dir()):
        d.mkdir(parents=True, exist_ok=True)
        mode = d.stat().st_mode
        if mode & (stat.S_IWGRP | stat.S_IWOTH):
            import warnings
            warnings.warn(f"Insecure permissions on {d}: {oct(mode)}")
```

### Finding 6: `curl | sh` in CI

`.github/workflows/ci.yml:16` pipes a remote script directly to `sh`.

**Fix:**
```yaml
# Replace with official GitHub Action
- uses: astral-sh/setup-uv@v5
  with:
    version: "0.5.11"
```

---

## 5. Refactors That Would Pay Off Most

### Small (< 1 day each)

1. **Extract session creation service.** Move the shared logic from `_add_impl` and `create_session_api` into a single `create_session_full()` function in `core/` or a new `services/session.py`. Both CLI and API call it. This eliminates the duplicate ~100 lines and prevents future divergence.

2. **Replace `_initialized` class variable with instance variable.** `ShoalDB._initialized` is a class variable but semantically belongs to the instance. If `reset_instance` is called and a new instance is created, the old class-variable state could leak. Move it to `__init__`.

3. **Consolidate `init` and `check` in `cli/__init__.py`.** Lines 85-214 are largely duplicated. Extract shared dependency/directory checks into a helper.

### Medium (1-3 days each)

4. **Make DB updates field-level atomic.** Instead of the current read-modify-write with `model_copy`, store session fields as SQL columns (or use `json_set()` in SQLite 3.38+). This eliminates the race condition entirely.

5. **Add a `ShoalError` hierarchy.** Currently errors are a mix of `ValueError`, `FileNotFoundError`, `RuntimeError`, `SystemExit`, and `typer.Exit`. A proper taxonomy (`SessionNotFoundError`, `ToolConfigError`, `TmuxError`) would make error handling consistent and testable.

6. **Add XDG support to fish installer.** Respect `$XDG_CONFIG_HOME` instead of hardcoding `~/.config/fish`.

### Large (> 3 days)

7. **Wrap all tmux operations in an async executor.** While the docstring in `tmux.py` acknowledges the sync-in-async tradeoff, as session counts grow this will become a bottleneck. Use `asyncio.to_thread()` wrappers.

8. **Add a proper event bus.** The current model of polling DB for changes (watcher + API poller) doesn't scale. An in-process event bus (or SQLite `UPDATE` triggers with notifications) would reduce polling and enable real-time reactivity. (I see you have an `openspec/changes/event-bus/` — this is the right direction.)

---

## 6. Testing Plan

### What to unit test (pure functions, no I/O)

| Module | Priority | Notes |
|--------|----------|-------|
| `detection.py` | Already good | Add case-sensitivity and regex-special-char tests |
| `notify.py._escape_applescript_string` | High | 0 tests currently. Test `'`, `"`, `\`, newlines, unicode |
| `state.validate_session_name` | Already good | Add leading/trailing slash, `../` path traversal |
| `state._sanitize_tmux_name` | High | Test collision detection (e.g., `a.b` vs `a-b`) |
| `models/` | Medium | Add invalid input tests, boundary values |
| `theme.py` | Low | Pure formatting, test `tmux_status_segment` edge cases |
| `_infer_branch_name` | Low | Already trivial |

### What to integration test (with mocking)

| Module | Priority | Notes |
|--------|----------|-------|
| Session creation (CLI) | High | Happy path. Currently only error cases tested |
| Session creation (API) | High | Currently **SKIPPED** |
| `kill` command | High | 0 tests |
| `fork` command | Medium | Only startup commands tested |
| `watcher._poll_cycle` | Medium | Add exception-during-poll and concurrent-update tests |
| `mcp_pool.start/stop` | High | 4 tests **SKIPPED** |
| Fish installer | Medium | Add missing-template and copy-failure paths |
| `demo start` | Medium | 5 tests **SKIPPED** |

### How to test tmux/fish

```python
# For tmux: mock subprocess.run at the tmux._run level
@patch("shoal.core.tmux._run")
def test_new_session_with_cwd(mock_run):
    tmux.new_session("test", cwd="/tmp")
    mock_run.assert_called_once_with(
        ["new-session", "-d", "-s", "test", "-c", "/tmp"]
    )

# For fish: use `fish -n` (no-execute) to syntax-check templates
def test_fish_templates_syntax():
    template_dir = Path(__file__).parent.parent / "src/shoal/integrations/fish/templates"
    for f in template_dir.glob("*.fish"):
        result = subprocess.run(["fish", "-n", str(f)], capture_output=True)
        assert result.returncode == 0, f"{f.name}: {result.stderr}"

# For integration tests (mark with @pytest.mark.integration):
# Require real tmux, real git, real fish
# Use unique session prefixes to avoid collisions with user sessions
# Clean up in teardown (kill all shoal_test_* sessions)
```

### Current gaps summary
- **8 skipped tests** across demo, MCP pool, and API
- **0 tests** for: `notify.py`, `theme.py`, `popup.py`, `nvim.py`, `setup.py` CLI, `kill`, `attach`, `fork` (full flow)
- Coverage floor is 57% (`pyproject.toml:67`) — reasonable for v0.5, but should be 70%+ before wider distribution

---

## 7. Quick Wins (< 2 hours each)

1. **Bind API to `127.0.0.1` by default.** Two lines changed in `server.py:592` and `cli/__init__.py`. Eliminates the most critical security issue immediately.

2. **Add `status is-interactive; or return` to `bootstrap.fish`.** One line at top. Prevents errors when fish sources this in non-interactive contexts.

3. **Change `set -U` to `set -g` in `bootstrap.fish:38`.** One character change. Eliminates filesystem write on every command.

4. **Add subprocess timeouts.** Add `timeout=30` parameter to `tmux._run()` and `git._run()`. Handle `subprocess.TimeoutExpired` with a clear error message. ~10 lines changed.

5. **Fix watcher crash on poll failure.** Wrap `_poll_cycle()` call in try/except in `watcher.py:49`. ~4 lines.

   ```python
   while self._running:
       try:
           await self._poll_cycle()
       except Exception:
           logger.exception("Poll cycle failed, continuing")
       await asyncio.sleep(self.poll_interval)
   ```

6. **Fix `ConnectionManager` bugs.** Use a `set` for connections and add per-connection error handling in broadcast. ~8 lines.

   ```python
   class ConnectionManager:
       def __init__(self):
           self.active_connections: set[WebSocket] = set()
   
       def disconnect(self, websocket: WebSocket):
           self.active_connections.discard(websocket)
   
       async def broadcast(self, message: dict):
           broken = []
           for conn in list(self.active_connections):
               try:
                   await conn.send_json(message)
               except Exception:
                   broken.append(conn)
           for conn in broken:
               self.active_connections.discard(conn)
   ```

7. **Add try/except around `tmux.new_session` in `_fork_impl`.** Mirror the pattern from `_add_impl`. ~6 lines.

8. **Fix CI to use `astral-sh/setup-uv@v5`.** Replace `curl | sh` with the official action. 2 lines in `ci.yml`.

9. **Remove unused imports in `installer.py`.** Delete `from rich.console import Panel` and `from rich.table import Table`. 2 lines.

10. **Add `fish -n` syntax check to CI.** Add a CI step that validates fish template syntax. ~5 lines in `ci.yml`.

---

## Fish Integration Specific Issues

### From `bootstrap.fish`

- **Line 1:** No `status is-interactive; or return` guard → errors in non-interactive contexts
- **Line 16:** `\cs` (Ctrl+S) conflicts with terminal flow control (XOFF signal) — users may think terminal froze
- **Line 38:** `set -U __shoal_last_session` writes to disk on every command → performance issue
- **No guard against re-sourcing** → duplicate event handlers could accumulate

### From `completions.fish`

- **Lines 13-20:** Dead helper functions (`__shoal_mcp_servers`, `__shoal_robo_profiles`) defined but never used
- **Line 29:** `detach` subcommand has no session-name completion
- **Missing:** `setup fish --force` flag completion

### From `quick-attach.fish`

- **Line 6:** `--preview="shoal info {}"` → shell injection via fzf's `{}` (currently mitigated by name validation, but defense is implicit)
- **Line 12:** `shoal attach $session` lacks `--` to prevent flag injection
- **No fzf availability check** in the function itself (only in keybinding)

### From `installer.py`

- **Line 24:** `get_fish_config_dir()` logic is broken — always returns a path (never `None`), making the error check on line 62 dead code
- **No XDG_CONFIG_HOME support** → installs to wrong directory if user has custom XDG config
- **Line 113:** Bare `except Exception` with unhelpful error messages
- **No uninstall mechanism**
- **Lines 10-11:** Unused imports (`Panel`, `Table`)

---

**Overall assessment:** The codebase has a clean architecture with good separation of concerns. The core abstractions (db.py, state.py, tmux.py) are well-designed. The main risks are: the unauthenticated API surface, the lack of subprocess timeouts, and the read-modify-write race in the DB. The fish integration is well-structured but needs the interactive guard and the fzf preview fix. The test suite has good bones but significant coverage gaps, especially around happy paths and the 8 skipped tests. Fixing the quick wins above would materially improve both security and reliability for v0.5.0 release.
