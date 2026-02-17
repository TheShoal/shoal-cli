## ADDED Requirements

### Requirement: Unit tests for notify module
The system SHALL have unit tests for `core/notify.py` covering the `notify()` function and `_escape_applescript_string()` helper. Tests MUST mock `subprocess.run` and `sys.platform` to avoid triggering real OS notifications.

#### Scenario: Notification on macOS
- **WHEN** `notify()` is called on a macOS platform
- **THEN** `subprocess.run` SHALL be called with an osascript command containing the escaped title and message

#### Scenario: Notification on non-macOS
- **WHEN** `notify()` is called on a non-macOS platform
- **THEN** the function SHALL return without calling subprocess

#### Scenario: AppleScript string escaping
- **WHEN** `_escape_applescript_string()` is called with a string containing backslashes and quotes
- **THEN** the output SHALL have backslashes and quotes properly escaped

### Requirement: Unit tests for theme module
The system SHALL have unit tests for `core/theme.py` covering icon constants, status style definitions, `tmux_status_segment()`, `create_panel()`, and `create_table()` factory functions.

#### Scenario: tmux status segment formatting
- **WHEN** `tmux_status_segment()` is called with icon, count, and color
- **THEN** it SHALL return a properly formatted tmux status string with the color code

#### Scenario: Panel factory produces Rich Panel
- **WHEN** `create_panel()` is called with content and title
- **THEN** it SHALL return a `rich.panel.Panel` instance with the specified styling

#### Scenario: Table factory produces Rich Table
- **WHEN** `create_table()` is called
- **THEN** it SHALL return a `rich.table.Table` instance with default shoal styling

#### Scenario: Status styles completeness
- **WHEN** the STATUS_STYLES dictionary is accessed
- **THEN** it SHALL contain entries for all SessionStatus values (running, idle, waiting, error, stopped, unknown)

### Requirement: Unit tests for popup module
The system SHALL have unit tests for `dashboard/popup.py` covering `_build_entries()` and `print_popup_list()`. Tests MUST mock session data and verify output format.

#### Scenario: Build entries with sessions
- **WHEN** `_build_entries()` is called with existing sessions in the database
- **THEN** it SHALL return a list of tab-delimited strings containing session ID, icon, name, tool, status, branch, and last activity

#### Scenario: Build entries with no sessions
- **WHEN** `_build_entries()` is called with an empty database
- **THEN** it SHALL return an empty list

### Requirement: Unit tests for CLI nvim commands
The system SHALL have unit tests for `cli/nvim.py` covering `nvim send` and `nvim diagnostics` commands via the CLI test runner with mocked nvr and session resolution.

#### Scenario: nvim send with valid session
- **WHEN** `nvim send` is invoked with a valid session name and command
- **THEN** the system SHALL resolve the nvim socket and send the command via nvr

#### Scenario: nvim send with invalid session
- **WHEN** `nvim send` is invoked with a non-existent session
- **THEN** the system SHALL display an error message

### Requirement: Unit tests for CLI setup commands
The system SHALL have unit tests for `cli/setup.py` covering the `setup fish` command dispatch.

#### Scenario: Setup fish invocation
- **WHEN** `setup fish` is invoked via CLI runner
- **THEN** it SHALL delegate to the fish installer module

### Requirement: Expanded CLI session tests
The system SHALL have tests for `kill`, `logs` (success path), `attach` (error paths), and `info` edge cases in `cli/session.py`.

#### Scenario: Kill existing session
- **WHEN** `kill` is invoked with a valid session ID
- **THEN** the session SHALL be deleted and tmux session killed (mocked)

#### Scenario: Logs for existing session
- **WHEN** `logs` is invoked for a session with a log file
- **THEN** the system SHALL display the log contents

### Requirement: Expanded CLI mcp tests
The system SHALL have tests for `mcp start`, `mcp stop`, `mcp attach`, and `mcp detach` commands with mocked MCP pool operations.

#### Scenario: MCP start with known server
- **WHEN** `mcp start` is invoked with a known server name
- **THEN** the MCP server SHALL be started and confirmation displayed

### Requirement: Expanded CLI watcher tests
The system SHALL have tests for `watcher start` in both foreground and background modes with mocked Watcher class and subprocess.

#### Scenario: Watcher start foreground
- **WHEN** `watcher start --foreground` is invoked
- **THEN** the watcher SHALL run directly in the current process (mocked)

### Requirement: Expanded CLI robo tests
The system SHALL have tests for `robo setup`, `robo start`, `robo stop`, and `robo status` commands.

#### Scenario: Robo setup creates profile
- **WHEN** `robo setup` is invoked with a profile name
- **THEN** a new robo profile configuration SHALL be created

### Requirement: Expanded CLI worktree tests
The system SHALL have tests for `wt finish` and `wt cleanup` commands with mocked git operations.

#### Scenario: Worktree finish with merge
- **WHEN** `wt finish` is invoked for a worktree session
- **THEN** the system SHALL merge the branch and clean up the worktree (mocked)

### Requirement: Unskip fixable tests
The system SHALL unskip tests in `test_demo.py` and `test_mcp_pool.py` that can be made to work with proper mocking. Tests that genuinely require real system resources SHALL remain skipped with documentation.

#### Scenario: Demo start test unskipped
- **WHEN** the `test_demo_start` test is run with proper tmux/git mocks
- **THEN** it SHALL pass without requiring real tmux or git

### Requirement: Status bar edge case tests
The system SHALL have additional tests for status bar edge cases including all sessions in one status and large session counts.

#### Scenario: All sessions running
- **WHEN** all sessions have status "running"
- **THEN** the status bar SHALL show only the running count with no other status segments

#### Scenario: Large session count
- **WHEN** there are 100+ sessions
- **THEN** the status bar SHALL correctly aggregate and display counts without truncation

### Requirement: Fish uninstall test
The system SHALL have tests for `uninstall_fish_integration()` covering file removal and error handling.

#### Scenario: Successful uninstall
- **WHEN** `uninstall_fish_integration()` is called with existing integration files
- **THEN** all shoal fish files SHALL be removed and confirmation displayed

### Requirement: Coverage threshold at 70%
The system SHALL enforce a minimum 70% test coverage threshold in `pyproject.toml`.

#### Scenario: Coverage gate enforcement
- **WHEN** `pytest --cov` is run
- **THEN** the test suite SHALL fail if coverage drops below 70%
