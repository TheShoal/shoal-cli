## ADDED Requirements

### Requirement: Troubleshooting documentation
The system SHALL provide a `docs/TROUBLESHOOTING.md` file covering common issues, their symptoms, causes, and solutions.

#### Scenario: Watcher not detecting status changes
- **WHEN** a user experiences the watcher not updating session statuses
- **THEN** the troubleshooting guide SHALL explain how to check watcher status, verify tool config patterns, and use `--debug` for verbose logging

#### Scenario: Database locked errors
- **WHEN** a user encounters SQLite "database is locked" errors
- **THEN** the troubleshooting guide SHALL explain WAL mode, single-connection architecture, and how to check for stale processes

#### Scenario: Tmux session not found
- **WHEN** a user gets "tmux session not found" errors
- **THEN** the troubleshooting guide SHALL explain session naming, how to list tmux sessions, and how to prune stale records

#### Scenario: MCP server connection issues
- **WHEN** a user cannot connect to an MCP server
- **THEN** the troubleshooting guide SHALL explain socket paths, socat requirements, and how to check server health

### Requirement: Debug flag documentation
The troubleshooting guide SHALL document the `--debug` flag and how to use it for diagnosing issues.

#### Scenario: Debug flag usage
- **WHEN** a user needs verbose logging
- **THEN** the guide SHALL show the `shoal --debug <command>` syntax and explain what additional output to expect

### Requirement: Error message improvement audit
Error messages across the CLI SHALL provide actionable suggestions where feasible, including relevant commands to try or documentation to consult.

#### Scenario: Improved error context
- **WHEN** a CLI command fails with a known recoverable error
- **THEN** the error message SHALL include a suggestion for how to resolve the issue
