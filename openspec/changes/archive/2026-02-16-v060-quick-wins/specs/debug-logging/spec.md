## ADDED Requirements

### Requirement: Global debug flag
The CLI SHALL accept a `--debug` global flag that enables verbose logging (DEBUG level) for all commands. When not set, the default logging level SHALL remain at WARNING or higher.

#### Scenario: Debug flag enables verbose output
- **WHEN** user runs `shoal --debug session list`
- **THEN** the command produces DEBUG-level log output to stderr in addition to normal output

#### Scenario: No debug flag uses default logging
- **WHEN** user runs `shoal session list` without `--debug`
- **THEN** only WARNING and above messages appear, and DEBUG messages are suppressed

#### Scenario: Debug flag works with all commands
- **WHEN** user passes `--debug` before any subcommand
- **THEN** verbose logging is active for that command's entire execution
