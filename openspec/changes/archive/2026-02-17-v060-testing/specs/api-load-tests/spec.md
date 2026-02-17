## ADDED Requirements

### Requirement: Concurrent API request handling
The system SHALL have load tests verifying the API server handles concurrent requests correctly. Tests SHALL use `asyncio.gather` with `httpx.AsyncClient` via `ASGITransport` for in-process testing.

#### Scenario: Concurrent session listing
- **WHEN** 20 concurrent GET /sessions requests are made
- **THEN** all requests SHALL return 200 with consistent data and no errors

#### Scenario: Concurrent status polling
- **WHEN** 20 concurrent GET /status requests are made while sessions exist
- **THEN** all requests SHALL return correct aggregate counts

#### Scenario: Concurrent mixed operations
- **WHEN** concurrent reads and writes (GET /sessions + POST /sessions) are interleaved
- **THEN** all operations SHALL complete without data corruption or deadlocks

### Requirement: Load test does not enforce performance thresholds
Load tests SHALL assert correctness (all requests succeed, data integrity) rather than performance timing thresholds to avoid flaky tests.

#### Scenario: No timing assertions
- **WHEN** load tests are run
- **THEN** assertions SHALL validate response status codes and data correctness, not response times
