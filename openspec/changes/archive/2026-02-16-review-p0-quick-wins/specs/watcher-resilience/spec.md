## ADDED Requirements

### Requirement: Watcher poll loop SHALL survive transient errors
The watcher's main loop SHALL catch exceptions from `_poll_cycle()` and continue to the next cycle instead of crashing.

#### Scenario: Poll cycle raises an exception
- **WHEN** `_poll_cycle()` raises any `Exception` (e.g., DB locked, malformed data, tmux error)
- **THEN** the exception is logged with full traceback and the watcher continues to the next poll cycle

#### Scenario: Poll cycle succeeds
- **WHEN** `_poll_cycle()` completes without error
- **THEN** the watcher proceeds normally to sleep and poll again

### Requirement: Watcher SHALL log poll failures at error level
When a poll cycle fails, the watcher MUST log the exception using `logger.exception()` to capture the full traceback for diagnosis.

#### Scenario: Repeated poll failures are all logged
- **WHEN** multiple consecutive `_poll_cycle()` calls raise exceptions
- **THEN** each failure is logged individually with its full traceback

### Requirement: Watcher SHALL NOT catch BaseException subclasses
The watcher's error handling MUST only catch `Exception`, not `BaseException`. `SystemExit`, `KeyboardInterrupt`, and other `BaseException` subclasses MUST propagate normally.

#### Scenario: KeyboardInterrupt during poll cycle
- **WHEN** a `KeyboardInterrupt` is raised during `_poll_cycle()`
- **THEN** the interrupt propagates and the watcher shuts down via the existing signal handling
