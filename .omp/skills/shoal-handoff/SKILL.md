---
name: shoal-handoff
description: Read ROADMAP.md handoff section and upcoming milestones to understand session context. Use at session start or when picking up work.
---

# Shoal Handoff

Read the project roadmap and handoff notes to establish session context.

## Steps

1. Read `ROADMAP.md` — focus on the **Handoff** section at the bottom and the first upcoming milestone
2. If needed, read `CHANGELOG.md` for historical release context (completed milestones live there, not in ROADMAP)
3. Summarize to the user:
   - What the last session accomplished (from the most recent handoff entry)
   - What the next session should work on
   - Current milestone status (what's done, what remains)
4. If asked to "update" or "write":
   - Ask the user to confirm what was accomplished this session
   - Append a new handoff entry to the **Handoff** section in `ROADMAP.md` following the existing format
   - Update milestone checkboxes if any items were completed
   - Update `CHANGELOG.md` under `[Unreleased]` if new features/fixes were shipped

## Format

Each handoff entry uses this template:
- **Session date and title**: `### Session: YYYY-MM-DD — brief description`
- **What we did**: Concrete accomplishments (commits, features, fixes, test counts)
- **Current state**: Branch, CI status, test counts
- **What to do next**: Actionable items for the next session, ordered by priority

## Rules

- Keep entries concise — 5-10 bullets max per section
- Include concrete numbers (test counts, commit counts, file counts)
- Reference specific files/functions when relevant
- Don't duplicate the full ROADMAP — just link to the milestone
- The handoff section lives at the bottom of ROADMAP.md
- **Trim old handoffs**: When writing a new entry, prune the handoff section to keep only the last 2-3 entries. Older session history is preserved in CHANGELOG.md.
