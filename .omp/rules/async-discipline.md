---
description: Async-first I/O discipline — all I/O must use async/await, blocking calls must use asyncio.to_thread().
---

## Rule

All I/O operations in shoal MUST use `async/await`. Never block the event loop.

## Blocking calls that MUST use `asyncio.to_thread()`

- `subprocess.run()`, `subprocess.call()`, `subprocess.check_output()`
- `shutil.copy()`, `shutil.rmtree()`, and other filesystem operations that may block
- Any third-party library call that performs synchronous I/O

## Never use in async contexts

- `time.sleep()` — use `asyncio.sleep()` instead
- `open()` for file I/O in hot paths — use `aiofiles` or `asyncio.to_thread()`
- Bare `subprocess.run()` — wrap with `asyncio.to_thread(subprocess.run, ...)`

## Pattern: wrapping blocking subprocess calls

```python
async def async_some_operation(arg: str) -> str:
    result = await asyncio.to_thread(
        subprocess.run,
        ["command", arg],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()
```

## Pattern: existing async wrappers

Shoal provides `async_*` prefixed wrappers in `core/tmux.py` and `core/git.py` for common operations. Use these instead of writing new wrappers:

- `async_send_keys()`, `async_capture_pane()`, `async_wait_for_ready()`
- `async_create_worktree()`, `async_remove_worktree()`
- `async_diff_stat()`, `async_commit_count_since_main()`

## Why

SQLite via `aiosqlite`, FastAPI, and the status watcher all share one event loop. A single blocking call stalls everything — status detection, API responses, and CLI commands.
