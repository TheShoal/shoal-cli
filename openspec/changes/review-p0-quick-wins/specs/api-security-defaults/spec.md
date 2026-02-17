## ADDED Requirements

### Requirement: API server SHALL bind to localhost by default
The API server MUST bind to `127.0.0.1` by default instead of `0.0.0.0` to prevent unintended network exposure.

#### Scenario: API server started with default settings
- **WHEN** the API server is started without specifying a host
- **THEN** it binds to `127.0.0.1` and is only accessible from the local machine

#### Scenario: API server started with explicit host override
- **WHEN** the API server is started with `--host 0.0.0.0`
- **THEN** it binds to all interfaces and is network-accessible

### Requirement: CLI serve command SHALL default to localhost
The `shoal serve` CLI command MUST use `127.0.0.1` as the default value for the `--host` parameter.

#### Scenario: CLI serve with no host flag
- **WHEN** `shoal serve` is run without `--host`
- **THEN** the API server binds to `127.0.0.1`
