## ADDED Requirements

### Requirement: Tmux subprocess calls SHALL have a default timeout
The `tmux._run()` function SHALL accept a `timeout` parameter defaulting to 30 seconds. All tmux subprocess calls MUST complete within the specified timeout or raise an error.

#### Scenario: Normal tmux command completes within timeout
- **WHEN** a tmux command (e.g., `has_session`, `new_session`, `capture_pane`) is executed
- **THEN** the command completes normally and returns its result

#### Scenario: Tmux command exceeds timeout
- **WHEN** a tmux command does not complete within the timeout period
- **THEN** the subprocess is terminated and a `subprocess.TimeoutExpired` exception is raised

#### Scenario: Custom timeout is provided
- **WHEN** a caller passes a custom `timeout` value to `_run()`
- **THEN** that value is used instead of the 30-second default

### Requirement: Git subprocess calls SHALL have a default timeout
The `git._run()` function SHALL accept a `timeout` parameter defaulting to 30 seconds. All git subprocess calls MUST complete within the specified timeout or raise an error.

#### Scenario: Normal git command completes within timeout
- **WHEN** a git command (e.g., `is_git_repo`, `current_branch`, `worktree_add`) is executed
- **THEN** the command completes normally and returns its result

#### Scenario: Git command exceeds timeout
- **WHEN** a git command does not complete within the timeout period
- **THEN** the subprocess is terminated and a `subprocess.TimeoutExpired` exception is raised

### Requirement: Git push SHALL use an extended timeout
The `git.push()` function SHALL use a timeout of 120 seconds to accommodate network latency on remote pushes.

#### Scenario: Git push to remote completes within 120 seconds
- **WHEN** `git.push()` is called and the remote responds within 120 seconds
- **THEN** the push completes normally

#### Scenario: Git push exceeds 120-second timeout
- **WHEN** `git.push()` is called and the remote does not respond within 120 seconds
- **THEN** the subprocess is terminated and a `subprocess.TimeoutExpired` exception is raised

### Requirement: Timeout errors SHALL produce clear error messages
When a subprocess times out, the error message MUST identify the command that timed out and the timeout duration.

#### Scenario: Tmux timeout error message
- **WHEN** a tmux command times out after 30 seconds
- **THEN** the error message includes the tmux subcommand name and the timeout value
