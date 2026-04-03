# Shoal Journal / QMD / Memory Improvement Plan

## Purpose

This plan captures the recommended improvement path for Shoal's journal, QMD sync, Dreamer summaries, and memory/retrieval features so a later session can pick up implementation cleanly.

The central conclusion from the investigation is:

- Shoal should borrow Lobster Party's **two-plane architecture**:
  - human-readable markdown artifacts for durable full text
  - machine-readable structured metadata for indexing, summaries, and retrieval
- Shoal should **not** copy Lobster Party's runtime-specific Majordomo / delegated host execution model.
- Dreamer and related summarizers should become **summary producers over a canonical event store**, not the memory system itself.

## Investigation summary

### Current Shoal state

Shoal already has several pieces of a memory system, but they are split across overlapping paths:

- `src/shoal/core/journal.py`
  - append-only markdown session journal
  - frontmatter metadata
  - journal archive + handoff helpers
  - linear substring search over journals
- `src/shoal/core/qmd.py`
  - generic QMD import/export/sync helpers
- `src/shoal/core/claw_conversations.py`
  - Lobster Party / Claw-specific QMD import/export helpers
- `src/shoal/cli/session.py`
  - `sync` command, currently wired through the Claw-specific path
- `src/shoal/services/dreamer.py`
  - periodic live session summaries
  - summaries stored in memory and mirrored into the journal
- `src/shoal/services/claw_bootstrap.py`
  - periodic journal summaries and workflow summaries
- `src/shoal/services/status_bar.py`
  - reads Dreamer summaries from in-process state first, then from the journal
- `src/shoal/services/mcp_shoal_server.py`
  - `session_summary` MCP tool with the same Dreamer -> journal fallback logic

### Key Shoal problems identified

1. **Duplicate sync/export paths**
   - `src/shoal/core/qmd.py`
   - `src/shoal/core/claw_conversations.py`
   - `src/shoal/core/journal.py` wrappers
   - `src/shoal/cli/session.py` routing

2. **Current memory is weakly structured**
   - Dreamer stores `summary_history` in memory and only mirrors text into the journal.
   - Claw journal summary appends prose into the journal.
   - Workflow summary is sent on the bus but not stored in a canonical memory plane.

3. **QMD sidecars are not yet a true machine plane**
   - `src/shoal/core/qmd.py` currently duplicates full prompt/response into both JSON and markdown.

4. **Search is still primitive**
   - `search_journals()` in `src/shoal/core/journal.py` is a linear scan over markdown journals.

5. **There is at least one correctness bug in current sync code**
   - `append_entry()` expects `session_id: str`
   - `import_claw_turns()` currently passes a session record instead of the session id

### Relevant Lobster Party ideas worth borrowing

From `../../../patron/lobster-party`:

1. **Immutable per-turn markdown + JSON pair**
   - durable file artifacts
   - weekly bucketing
   - stable ids

2. **True dual-plane architecture**
   - markdown remains the full text/search corpus
   - JSON sidecars hold structured metadata and summaries

3. **Derived SQLite metadata/index layer**
   - secondary plane for aggregation, retrieval, enrichment, and analytics
   - does not replace the file artifacts as source of truth

4. **Search + enrichment retrieval pattern**
   - text search or candidate retrieval first
   - canonical metadata enrichment second

### Lobster Party ideas to avoid

1. Majordomo / delegated `qmd.query` execution model
2. Sandbox/host-specific command gating and runtime assumptions
3. Directly importing Lobster's identity model as Shoal's primary abstraction
   - Lobster is conversation/thread/channel centric
   - Shoal is session/worktree/workflow centric

## Product goal

Give Shoal a coherent memory architecture that supports:

- durable session and workflow context
- structured summaries from Dreamer and other producers
- fast retrieval for status, MCP, handoff, and operator workflows
- Lobster/Claw interoperability without forcing Shoal's internals to be Lobster-shaped

## Non-goals

- replacing Shoal's session journal UX
- importing Majordomo runtime behavior
- making QMD mandatory for all Shoal usage immediately
- redesigning the message bus or coordinator beyond what memory integration requires
- building a full semantic retrieval system in the first pass

## Design principles

1. **One canonical event model**
   - all summary, journal-export, and import workflows must converge on one internal schema

2. **Markdown remains operator-facing**
   - journals and markdown artifacts remain readable and durable

3. **Structured metadata must be first-class**
   - summaries, workflow ids, session metadata, tool metadata, and tags must not live only in prose

4. **Derived index, not alternate source of truth**
   - SQLite index is derived from canonical artifacts and can be rebuilt

5. **Dreamer is a producer, not the store**
   - Dreamer writes structured summaries
   - Dreamer does not own memory semantics

6. **Backward compatibility during migration**
   - existing Shoal journals
   - current QMD exports
   - Lobster QMD fixtures/imports
   should remain readable during transition

---

# Target architecture

## Canonical layers

### Layer 1: Session journal

Keep the current append-only journal in `src/shoal/core/journal.py` for:

- operator log
- human-readable history
- handoff evidence
- compatibility with existing features

This remains useful, but should stop being the only durable memory substrate.

### Layer 2: Canonical conversation/event artifacts

Introduce one Shoal-native event model for all persisted memory/search artifacts.

Recommended module split:

- `src/shoal/core/conversations.py`
  - canonical event schema
  - id generation
  - conversion helpers
- `src/shoal/core/qmd.py`
  - serialization / deserialization to markdown + JSON sidecars
- `src/shoal/core/claw_conversations.py`
  - Lobster/Claw compatibility adapter only

### Layer 3: Derived SQLite conversation index

Add a derived index that ingests the canonical JSON sidecars and supports:

- recent memory
- session summaries
- workflow summaries
- structured filters
- enrichment for search results

Recommended module:

- `src/shoal/core/conversation_index.py`

### Layer 4: Retrieval consumers

Consumers should read structured memory via Shoal-native APIs:

- status bar
- MCP `session_summary`
- handoff generation
- future memory search / recall tools

---

# Proposed canonical schema

Use a Shoal-native event model rather than forcing everything into a prompt/response turn.

## Core fields

- `id: str`
- `schema_version: int`
- `timestamp: datetime`
- `session_id: str`
- `session_name: str`
- `source: str`
- `kind: str`
- `event_id: str | None`
- `correlation_id: str | None`
- `tool: str | None`
- `branch: str | None`
- `worktree: str | None`
- `model: str | None`
- `summary: str | None`
- `tags: list[str]`
- `metadata: dict[str, Any]`

## Optional full-text fields

For generic Shoal events:

- `content_markdown: str | None`

For imported chat-turn style records:

- `prompt: str | None`
- `response: str | None`
- `thinking: str | None`
- `prompt_summary: str | None`
- `response_summary: str | None`
- `thinking_summary: str | None`

## Optional usage/cost fields

- `tokens: int | None`
- `prompt_tokens: int | None`
- `response_tokens: int | None`
- `cost_usd: float | None`

## Recommended `kind` values

Initial set:

- `journal_entry`
- `chat_turn`
- `summary`
- `workflow_summary`
- `handoff_snapshot`
- `status_transition`

This lets Shoal represent its own event model cleanly while still supporting Lobster-style turns.

---

# Storage model

## Markdown artifact

Markdown holds the full text and remains the durable human-readable plane.

For a generic Shoal event, use frontmatter plus body, e.g.:

```md
---
id: evt-...
schema_version: 2
timestamp: 2026-04-03T12:34:56+00:00
session_id: sess-123
session_name: feature-auth
source: dreamer
kind: summary
event_id: dreamer-...
correlation_id: wf_...
tool: omp
branch: feat/auth
worktree: /path/to/worktree
model: amazon.nova-lite-v1:0
summary: Session is implementing auth middleware and fixing failing tests.
tags: [shoal, summary, dreamer, feature-auth]
---

## Content

Full summary or source content here.
```

For imported chat turns, the markdown body can still use sections:

```md
## Prompt
...

## Response
...

## Thinking
...
```

## JSON sidecar

JSON should hold structured machine-useful fields only.

Important: do **not** duplicate full prompt/response or body text in JSON unless there is a very strong reason.

JSON should include:

- ids and timestamps
- source/kind
- session/workflow metadata
- model
- summaries
- usage/cost fields
- tags
- metadata
- optionally a reference to the markdown body by basename/path

This is the core Lobster-inspired improvement.

---

# Dreamer and related features

## Role of Dreamer

Dreamer should become the **live session summarization producer** over the canonical event plane.

Current behavior in `src/shoal/services/dreamer.py`:

- tail logs
- accumulate recent output
- summarize periodically
- keep `summary_history` in memory
- mirror `[dreamer] ...` text into the journal

Target behavior:

- continue live summarization
- emit a canonical `summary` event artifact
- optionally continue mirroring the summary into the journal for operator UX

## Role of claw `summarize_journal`

This should become the **periodic consolidation summarizer**.

Current behavior in `src/shoal/services/claw_bootstrap.py`:

- summarize recent journal entries
- append `[claw-summary] ...` to the journal

Target behavior:

- emit a canonical `summary` event with `source="claw"`
- optionally mirror to the journal
- support larger horizon summaries than Dreamer

## Role of claw `summarize_workflow`

This should become the **workflow memory producer**.

Current behavior:

- summarize messages by `correlation_id`
- emit a `workflow_summary` event on the message bus

Target behavior:

- continue bus emission if useful
- also persist a canonical `workflow_summary` artifact/index entry

## Role of handoff generation

Handoff should become a consumer of memory, not only a reconstruction pass over recent journal entries.

Current handoff logic in `src/shoal/core/journal.py` uses:

- status urgency
- transitions
- recent journal entries
- git diff stat
- commit count

Future handoff should also incorporate:

- latest Dreamer summary
- latest claw consolidation summary
- latest workflow summary if available
- relevant recent journal excerpts as evidence

---

# Detailed implementation phases

## Phase 0 — repair current seam

### Goal

Fix correctness issues and reduce duplicate sync routing before introducing new architecture.

### Files

- `src/shoal/core/journal.py`
- `src/shoal/core/qmd.py`
- `src/shoal/core/claw_conversations.py`
- `src/shoal/cli/session.py`
- `src/shoal/integrations/lobster/clawplexer_sync.py`
- `tests/test_journal.py`
- `tests/test_claw_conversations.py`
- `tests/test_clawplexer_sync.py`

### Work

1. Fix `import_claw_turns()` to pass `session_rec.id` into `append_entry()`.
2. Decide which sync path is canonical.
   - recommendation: make `src/shoal/core/qmd.py` the canonical path
3. Re-route CLI sync to the canonical path.
4. Keep `claw_conversations.py` only for Lobster-specific compatibility helpers.
5. Add or update tests to prove the routing works through a single authoritative sync surface.

### Exit criteria

- current sync works correctly
- no ambiguous primary implementation
- tests cover the repaired seam

## Phase 1 — add canonical event model

### Goal

Create one Shoal-native schema used by all imports, exports, summaries, and retrieval.

### Files

- new `src/shoal/core/conversations.py`
- `src/shoal/core/qmd.py`
- `src/shoal/core/claw_conversations.py`
- `tests/test_claw_conversations.py`
- new `tests/test_qmd.py` or `tests/test_conversations.py`

### Work

1. Add canonical event dataclass/model.
2. Add deterministic id generation helpers.
3. Add conversion helpers:
   - journal entry -> canonical event
   - Lobster turn -> canonical event
   - summary output -> canonical event
4. Keep importers tolerant of old formats during migration.

### Exit criteria

- all producers can convert into one event schema
- Lobster fixtures still parse
- Shoal-native journal entries convert cleanly without fake prompt/response fields

## Phase 2 — make QMD a true dual plane

### Goal

Turn markdown + JSON sidecars into a real full-text + machine-metadata split.

### Files

- `src/shoal/core/qmd.py`
- `src/shoal/core/conversations.py`
- tests for serialization/deserialization

### Work

1. Redesign JSON sidecar output to store structured metadata + summaries only.
2. Keep full text in markdown.
3. Add `schema_version` to new artifacts.
4. Keep backward-compatible readers for existing Shoal exports and Lobster fixtures.

### Exit criteria

- markdown is the durable text plane
- JSON is the durable structured plane
- full body text is not unnecessarily duplicated in JSON

## Phase 3 — promote summaries to first-class structured artifacts

### Goal

Make Dreamer, claw journal summaries, and workflow summaries persist into canonical structured memory.

### Files

- `src/shoal/services/dreamer.py`
- `src/shoal/services/claw_bootstrap.py`
- `src/shoal/core/conversations.py`
- `src/shoal/core/qmd.py`
- tests for summary persistence

### Work

1. Change Dreamer `_summarize()` to emit a structured `summary` event artifact.
2. Keep journal mirroring for UX only.
3. Change `summarize_journal` to emit structured summary artifacts.
4. Change `summarize_workflow` to persist workflow summaries as structured artifacts as well as bus events if desired.

### Exit criteria

- summaries are queryable without scraping journal prose
- status/handoff consumers have a structured source available

## Phase 4 — add derived SQLite conversation index

### Goal

Support fast structured retrieval and enrichment.

### Files

- new `src/shoal/core/conversation_index.py`
- maybe new model module if Pydantic schemas are desired
- tests for indexing and query behavior

### Recommended tables

#### `conversation_events`

- `id`
- `schema_version`
- `timestamp`
- `session_id`
- `session_name`
- `source`
- `kind`
- `event_id`
- `correlation_id`
- `tool`
- `branch`
- `worktree`
- `model`
- `summary`
- `tokens`
- `cost_usd`
- `json_path`
- `markdown_path`

#### `conversation_tags`

- `event_id`
- `tag`

#### `index_state`

- ingestion checkpoint / high-water state

### Work

1. Build idempotent sidecar ingestion.
2. Support rebuildability from disk.
3. Expose query helpers for session/workflow/time-window retrieval.

### Exit criteria

- index is derived, deterministic, and rebuildable
- structured retrieval no longer depends on raw journal scans

## Phase 5 — move consumers onto the index

### Goal

Use structured memory for operator-facing features.

### Files

- `src/shoal/services/status_bar.py`
- `src/shoal/services/mcp_shoal_server.py`
- `src/shoal/core/journal.py`
- `src/shoal/cli/journal.py` or new memory CLI module
- handoff-related CLI files

### Work

1. Update status bar to prefer indexed summaries.
2. Update `session_summary` MCP tool to prefer indexed summaries.
3. Update handoff generation to pull latest summaries/workflow memory where available.
4. Keep journal fallback during migration.

### Exit criteria

- consumer features prefer structured memory
- journal fallback remains for resilience

## Phase 6 — optional retrieval enhancements

### Goal

Add richer memory/query behavior only after the foundations are stable.

### Possible additions

- synthetic tags/facets for date/session/workflow/tool/branch/worktree
- background watcher / incremental indexing loop
- memory search CLI / MCP endpoints
- optional QMD index integration for richer full-text retrieval

### Explicitly deferred until later

- semantic retrieval / embeddings
- Majordomo-like delegated query execution
- heavy background indexing automation before schema stabilizes

---

# Recommended file-by-file implementation order

## PR 1 — cleanup and seam repair

### Scope

- fix `import_claw_turns()` bug
- route sync through one canonical path
- keep behavior as close as possible to current behavior

### Files

- `src/shoal/core/journal.py`
- `src/shoal/cli/session.py`
- `src/shoal/core/claw_conversations.py`
- `tests/test_journal.py`
- `tests/test_clawplexer_sync.py`

## PR 2 — canonical event model

### Scope

- introduce canonical event schema
- refactor import/export around it
- keep backward-compatible readers

### Files

- new `src/shoal/core/conversations.py`
- `src/shoal/core/qmd.py`
- `src/shoal/core/claw_conversations.py`
- tests

## PR 3 — summary producers

### Scope

- Dreamer emits structured summaries
- claw summarizers emit structured summaries
- journal mirroring remains

### Files

- `src/shoal/services/dreamer.py`
- `src/shoal/services/claw_bootstrap.py`
- supporting schema/serialization files
- tests

## PR 4 — derived index

### Scope

- add SQLite memory/index layer
- add ingestion + query helpers

### Files

- new `src/shoal/core/conversation_index.py`
- tests

## PR 5 — consumers migrate

### Scope

- status bar
- MCP session summary
- handoff generation
- possibly journal search replacement path

### Files

- `src/shoal/services/status_bar.py`
- `src/shoal/services/mcp_shoal_server.py`
- `src/shoal/core/journal.py`
- CLI surfaces

---

# Testing strategy

## Existing tests to update

- `tests/test_journal.py`
- `tests/test_claw_conversations.py`
- `tests/test_clawplexer_sync.py`

## New tests to add

### `tests/test_conversations.py` or `tests/test_qmd.py`

Cover:

- canonical event creation
- deterministic id generation
- markdown serialization/deserialization
- JSON sidecar serialization/deserialization
- backward compatibility with old Shoal format
- compatibility with Lobster fixtures
- weekly bucketing

### `tests/test_conversation_index.py`

Cover:

- first ingest
- re-ingest idempotency
- session filter
- workflow filter
- summary retrieval
- tag retrieval
- index rebuild behavior

### Summary integration tests

Cover:

- Dreamer writes structured summary + journal mirror
- claw journal summary writes structured summary + journal mirror
- workflow summary persists and remains queryable
- status bar and MCP tools prefer indexed summary when available

## Verification commands

Use targeted commands first, then broaden:

```bash
uv run pytest tests/test_journal.py tests/test_claw_conversations.py tests/test_clawplexer_sync.py -q
just lint
just typecheck
just test
```

If Phase 3+ touches summary/index integration heavily, add the new targeted tests to the first command.

---

# Migration and compatibility strategy

## Backward compatibility window

For at least one or two releases, support reading:

- existing Shoal journals
- current Shoal QMD exports
- Lobster QMD fixtures/imports
- new Shoal canonical v2 artifacts

## Versioning

Add `schema_version` immediately to all new structured artifacts.

## Deletion strategy

Do not remove `src/shoal/core/claw_conversations.py` immediately.

Instead:

1. reduce it to a compatibility adapter
2. migrate all primary callers away from it
3. delete or further minimize it only after the new canonical path is stable

---

# Risks and hazards

## 1. Overfitting Shoal to chat-turn semantics

Risk:
- treating all memory as prompt/response pairs will distort Shoal's actual domain

Mitigation:
- use a generic event model with optional chat-turn fields

## 2. Keeping duplicate code paths alive too long

Risk:
- behavior drift, ambiguous ownership, tests split across multiple implementations

Mitigation:
- make one path canonical in Phase 0

## 3. Summary drift between in-memory and persisted forms

Risk:
- Dreamer / claw summaries diverge from stored memory

Mitigation:
- emit structured summary artifacts at production time
- keep journal mirroring secondary

## 4. SQLite index accidentally becoming source of truth

Risk:
- write paths start depending on the DB instead of canonical artifacts

Mitigation:
- derive the DB from sidecars only
- make rebuild behavior explicit

## 5. Breaking current sync / handoff flows during migration

Risk:
- Lobster sync or operator workflows regress

Mitigation:
- maintain compatibility readers and journal fallbacks during migration

---

# Open questions for implementation

These do not block the initial cleanup, but should be settled during schema work.

1. Should canonical event artifacts live under a Shoal-specific directory separate from Lobster sync directories?
   - recommended: yes
   - keep Shoal artifacts separate from imported Lobster conversation trees

2. Should summaries be append-only artifacts or updatable latest-state records?
   - recommended: append-only summary events, with the index resolving "latest"

3. Should handoff snapshots themselves be indexed as memory artifacts?
   - recommended: probably yes, as `kind = "handoff_snapshot"`

4. Should status transitions also feed the event plane?
   - recommended: maybe later; not required for the first pass

5. Should `search_journals()` eventually become a compatibility wrapper over indexed retrieval?
   - recommended: yes, but only after the index is stable

---

# Recommended first task for the next session

Start with **Phase 0 / PR 1**.

## Exact first steps

1. Inspect and fix the `import_claw_turns()` bug in `src/shoal/core/journal.py`.
2. Reconcile sync routing between:
   - `src/shoal/core/qmd.py`
   - `src/shoal/core/claw_conversations.py`
   - `src/shoal/cli/session.py`
3. Update tests to prove there is one authoritative sync surface.
4. Stop before schema redesign unless the cleanup is fully passing.

## Why this is the right start

Because every later memory improvement depends on having one stable sync/export seam.

---

# Executive summary

The improvement should be implemented as a shift from:

- flat journal prose
- duplicated QMD paths
- in-memory Dreamer summaries with journal fallback

into:

- one canonical Shoal event model
- markdown full-text artifacts + JSON metadata sidecars
- structured summary producers (Dreamer, claw journal summary, workflow summary)
- a derived SQLite index for retrieval and enrichment
- Shoal-native memory consumers for status, MCP, and handoff

The most important immediate move is not "build memory search." It is:

**normalize the data model and make summaries durable, structured, and queryable.**
