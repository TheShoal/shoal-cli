# Team Doctrine

Shoal gets better when a team agrees on a few operating rules instead of inventing a new ritual for
every task. This page is the minimal doctrine that keeps multi-agent work legible and reviewable.

## Standardize the namespace

Session names should encode role and scope immediately.

Good patterns:

- `feat/auth-api`
- `review/auth-api`
- `plan/release-cut`
- `docs/http-guide`
- `ops/devbox-recovery`

Avoid vague names like:

- `work`
- `test`
- `thing`
- `agent-2`

The point is not naming purity. The point is scanning `shoal ls` and understanding the fleet in a
single glance.

## Require review symmetry

If a task is risky enough to matter, it is risky enough to deserve an explicit reviewer lane.

Recommended pairings:

- `feat/<scope>` with `review/<scope>`
- `ops/<scope>` with `review/<scope>`
- `release/<scope>` with `review/<scope>`

If there is no reviewer session, there should be a clearly named human checkpoint in the journal.

## Make journals operational artifacts

Journals should answer four questions quickly:

1. What is this session trying to do?
2. What constraints matter?
3. What is blocked right now?
4. What decision is the human likely to make next?

A useful pattern:

```text
Goal:
Constraints:
Current blocker:
Next human decision:
```

Free-form notes are fine. Opaque notes are not.

## Keep authority with humans

Agents should accelerate throughput. They should not absorb responsibility for ambiguous judgment.

Human-owned decisions:

- destructive operations,
- merge approval,
- release approval,
- policy changes,
- escalation resolution.

Agent-owned work:

- repo search,
- repetitive edits,
- draft implementation,
- diagnostics,
- first-pass review,
- summarization.

If a team blurs this line, the workflow will feel fast until it fails.

## Use templates as contracts

Templates should express stable work modes, not every local preference.

Good shared templates:

- `codex-dev`
- `claude-review`
- `plan-release`
- `overnight-batch`

Bad shared templates:

- one-off templates for single tickets,
- templates that hide critical behavior,
- templates whose names do not reveal role.

When a template is shared, it becomes part of the team interface.

## Review doctrine

The reviewer lane should not be decorative. It should have a job.

Default review priorities:

1. Behavioral regressions.
2. Configuration and deployment risk.
3. Test coverage gaps.
4. Contract drift against docs.
5. Hidden coupling and rollback difficulty.

That ordering matters. Style cleanup should not outrank correctness risk.

## Escalation doctrine

Robo should narrow waiting time, not erase accountability.

Team defaults should define:

- which prompts can be auto-approved,
- when ambiguity escalates,
- who owns escalation sessions,
- how decisions are logged,
- which classes of work must page a human quickly.

If those rules are unclear, the automation layer will feel arbitrary.

## Remote doctrine

Remote execution should preserve the same operating shape as local execution.

Standardize:

- the same session names,
- the same review lane,
- the same journal format,
- the same escalation rules,
- the same template vocabulary.

Different machines are fine. Different semantics are not.

## Weekly hygiene

Teams using Shoal regularly should review:

- stale sessions,
- abandoned reviewer lanes,
- templates no one understands,
- journals that are too vague to resume from,
- automation rules that create surprise.

This is operational hygiene, not process theater.

## The short version

If the team remembers only five rules, use these:

1. Name sessions so the fleet is readable.
2. Pair meaningful work with a reviewer lane.
3. Write journals for interruption recovery, not memoir.
4. Keep authority human and throughput agent-driven.
5. Standardize a few stable workflows and reuse them aggressively.
