## ADDED Requirements

### Requirement: Popup single DB lifecycle
The `run_popup()` function SHALL use at most one `with_db()` invocation per call. The current pattern of opening separate DB connections for listing and for post-selection lookup SHALL be consolidated.

#### Scenario: Popup with session selection
- **WHEN** `run_popup()` is called and a user selects a session from fzf
- **THEN** the session details SHALL be resolved from pre-fetched data without opening a second DB connection

#### Scenario: Popup list building
- **WHEN** `_build_entries()` is called
- **THEN** it SHALL return session data including enough information to resolve the selected session without a second DB query

### Requirement: Connection pooling evaluation
The system SHALL document findings from API load testing regarding whether connection pooling is needed. This evaluation SHALL be captured as comments or documentation, not as implementation.

#### Scenario: Load test findings documented
- **WHEN** API load tests complete
- **THEN** the results SHALL inform whether connection pooling is recommended for v0.7.0
