## ADDED Requirements

### Requirement: ConnectionManager SHALL use a set for connection tracking
The `ConnectionManager` class MUST use a `set[WebSocket]` instead of `list[WebSocket]` for `active_connections` to prevent `ValueError` on disconnect.

#### Scenario: Disconnect called for an already-removed connection
- **WHEN** `disconnect()` is called with a WebSocket that is not in `active_connections`
- **THEN** the call completes without raising an exception

#### Scenario: Normal connect and disconnect cycle
- **WHEN** a WebSocket connects and later disconnects
- **THEN** the connection is added on connect and removed on disconnect without errors

### Requirement: Broadcast SHALL handle per-connection errors
The `broadcast()` method MUST catch exceptions from individual `send_json()` calls so that one broken connection does not prevent delivery to other connections.

#### Scenario: One connection fails during broadcast
- **WHEN** `broadcast()` is called and one connection's `send_json()` raises an exception
- **THEN** the message is still delivered to all other healthy connections
- **AND** the broken connection is removed from `active_connections`

#### Scenario: All connections are healthy during broadcast
- **WHEN** `broadcast()` is called and all connections succeed
- **THEN** all connections receive the message and remain in `active_connections`

#### Scenario: Multiple connections fail during broadcast
- **WHEN** `broadcast()` is called and multiple connections fail
- **THEN** all broken connections are removed and all healthy connections receive the message
