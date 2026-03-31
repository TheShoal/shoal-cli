---
description: Read ROADMAP.md handoff section and upcoming milestones to understand session context, or write a new handoff entry.
---

Pick up where the last session left off, or record what you did for the next session.

## Reading (default)

1. Read `ROADMAP.md` — focus on the **Handoff** section at the bottom and the first upcoming milestone.
2. If needed, read `CHANGELOG.md` for historical release context.
3. Summarize:
   - What the last session accomplished (from the most recent handoff entry)
   - What the next session should work on
   - Current milestone status (what's done, what remains)

## Writing (when asked to "update" or "write")

1. Ask the user to confirm what was accomplished this session.
2. Append a new handoff entry to the **Handoff** section in `ROADMAP.md`:

```
### Session: YYYY-MM-DD — brief title

**What we did:**
- bullet points of accomplishments

**Current state:**
- Branch, CI status, test counts

**What to do next:**
- bullet points of next steps
```

3. Update milestone checkboxes in `ROADMAP.md` if any items were completed.
4. Update `CHANGELOG.md` under `[Unreleased]` if new features/fixes were shipped.

## Rules

- Keep entries concise — 5-10 bullets max per section.
- Include concrete numbers (test counts, commit counts, file counts).
- Reference specific files/functions when relevant.
- When writing a new entry, prune the handoff section to keep only the last 2-3 entries. Older session history is preserved in CHANGELOG.md.
