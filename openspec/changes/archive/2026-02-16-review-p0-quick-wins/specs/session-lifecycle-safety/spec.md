## ADDED Requirements

### Requirement: Fork SHALL clean up DB record on tmux failure
When `_fork_impl` fails to create a tmux session, it MUST delete the session record from the database to prevent orphaned records.

#### Scenario: Tmux session creation fails during fork
- **WHEN** `tmux.new_session()` raises an exception during `_fork_impl`
- **THEN** the session record created in DB is deleted via `delete_session()`
- **AND** an error message is displayed to the user
- **AND** `typer.Exit(1)` is raised

#### Scenario: Tmux session creation succeeds during fork
- **WHEN** `tmux.new_session()` succeeds during `_fork_impl`
- **THEN** the session record remains in the DB and the fork proceeds normally

### Requirement: Session creation SHALL detect tmux name collisions
Before creating a new tmux session, the system MUST check whether the sanitized tmux session name already exists and fail with a clear error if a collision is detected.

#### Scenario: Two session names sanitize to the same tmux name
- **WHEN** a user creates session `my.project` and `my-project` already exists (both sanitize to `shoal_my-project`)
- **THEN** the system rejects the second session with an error explaining the collision

#### Scenario: Tmux session name is unique
- **WHEN** a user creates a session whose sanitized tmux name does not collide with any existing tmux session
- **THEN** the session is created normally

### Requirement: Collision detection SHALL apply to both CLI and API paths
The tmux name collision check MUST be performed in the shared `create_session()` function in `core/state.py`, not in individual CLI or API handlers.

#### Scenario: CLI session creation triggers collision check
- **WHEN** a session is created via the CLI
- **THEN** the collision check runs before `tmux.new_session()`

#### Scenario: API session creation triggers collision check
- **WHEN** a session is created via the API
- **THEN** the collision check runs before `tmux.new_session()`
