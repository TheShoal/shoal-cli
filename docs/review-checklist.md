<div class="shoal-page-head" data-icon="review">
  <p class="shoal-eyebrow">Operate Shoal</p>
  <p class="shoal-page-lede">
    Use this checklist when a reviewer lane needs a clear contract: what to inspect first, what to
    ignore until later, and what must be escalated before merge.
  </p>
</div>

# Review Checklist

!!! note
    The point of review is risk reduction, not aesthetic commentary. Style polish comes after
    behavioral confidence.

<div class="shoal-step-grid shoal-step-grid--plain">
  <div class="shoal-step">
    <strong>Behavior first</strong>
    <p>Start with runtime regressions and user-facing contract drift before you spend energy on polish.</p>
  </div>
  <div class="shoal-step">
    <strong>Config and tests</strong>
    <p>Check environment movement, deployment risk, and whether the risky path is covered instead of only the happy path.</p>
  </div>
  <div class="shoal-step">
    <strong>Docs alignment</strong>
    <p>Compare the code against setup flow, examples, and operator guidance so the docs do not silently drift.</p>
  </div>
  <div class="shoal-step">
    <strong>Escalate early</strong>
    <p>Pull a human in quickly when release semantics, destructive operations, or approval automation are involved.</p>
  </div>
</div>

## Default review order

1. Behavioral regressions.
2. Configuration and deployment risk.
3. Test coverage gaps.
4. Contract drift against the docs.
5. Hidden coupling and rollback difficulty.
6. Code clarity and maintainability.

If time is tight, cut the bottom of the list, not the top.

## Checklist for author and reviewer lanes

| Area | Reviewer question | Escalate when |
| --- | --- | --- |
| Behavior | Did runtime behavior change in ways the author did not claim? | A user-facing contract changed unexpectedly |
| Config | Did env vars, config defaults, or storage paths move? | Docs or installer output are now wrong |
| Tests | Are the risky paths covered, or only the happy path? | Failure modes are untested |
| Docs | Do docs still match the implementation and setup flow? | A guide now over-promises or misroutes users |
| Recovery | Is rollback or mitigation obvious if this fails? | The change is hard to reverse safely |

## Fast pass

Use this when you need a fast but serious first-pass review.

- read the stated goal,
- diff the risky files first,
- run or inspect the most targeted tests,
- compare behavior against any user-facing docs,
- write the blocker or confidence summary immediately.

## Deep pass

Use this when the change touches infra, release logic, state handling, or automation.

- read the implementation path end to end,
- inspect adjacent config and installer behavior,
- look for contract drift in docs and examples,
- examine rollback paths,
- verify any automation still leaves a human decision point where it should.

## Review notes format

Use notes that another operator can act on immediately.

```text
Severity:
Surface:
Observed behavior:
Why it matters:
Suggested fix or next check:
```

## What not to optimize for

Avoid reviews that spend all their energy on:

- naming nits with no behavior impact,
- personal style preferences,
- speculative rewrites,
- broad architecture debates unrelated to the task.

Those can wait until the correctness questions are closed.

## Escalation triggers

!!! warning
    Escalate immediately if a change affects destructive operations, merge policy, release
    semantics, remote transport, approval automation, or user setup instructions.

## Closing question

Before you clear a change, ask:

> Would I still be comfortable merging this if I had to debug it at 2 a.m. tomorrow?

If the honest answer is no, the review is not finished.
