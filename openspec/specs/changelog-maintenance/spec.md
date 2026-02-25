## ADDED Requirements

### Requirement: CHANGELOG v0.5.0 entry
The CHANGELOG.md SHALL contain a v0.5.0 release entry documenting fish shell integration, P0 quick wins, and CI hardening changes. The entry SHALL follow the existing changelog format.

#### Scenario: CHANGELOG includes v0.5.0
- **WHEN** a developer reads CHANGELOG.md
- **THEN** there is a v0.5.0 section listing fish integration, subprocess timeouts, watcher resilience, tmux name collision detection, fork cleanup, ConnectionManager fixes, API localhost binding, fish template fixes, and CI hardening

#### Scenario: CHANGELOG format consistency
- **WHEN** the v0.5.0 entry is compared to prior entries
- **THEN** it follows the same heading level, date format, and bullet style as existing entries
