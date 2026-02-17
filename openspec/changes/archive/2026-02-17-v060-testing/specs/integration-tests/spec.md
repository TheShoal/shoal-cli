## ADDED Requirements

### Requirement: Session lifecycle integration test
The system SHALL have integration tests that exercise the full session lifecycle through the application layer: create session → verify state → fork session → verify fork → kill both → verify cleanup. Tests SHALL mock at system boundaries (tmux, git, subprocess) but exercise all application logic.

#### Scenario: Create and kill workflow
- **WHEN** a session is created via `create_session()`, then killed via `delete_session()`
- **THEN** the database SHALL reflect the session as created, then removed, with proper status transitions

#### Scenario: Fork workflow
- **WHEN** a session is created, then forked via the fork logic
- **THEN** the forked session SHALL inherit the parent's path and tool, with a unique name and tmux session

#### Scenario: Multi-session status aggregation
- **WHEN** multiple sessions exist in different statuses
- **THEN** the status endpoint SHALL correctly aggregate counts across all sessions

### Requirement: Integration test marker
Integration tests SHALL use the `@pytest.mark.integration` marker already defined in `pyproject.toml` so they can be run selectively.

#### Scenario: Selective test execution
- **WHEN** `pytest -m integration` is run
- **THEN** only integration tests SHALL execute
