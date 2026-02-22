---
name: shoal-handoff
description: Read ROADMAP.md handoff section and upcoming milestones to understand session context. Use at session start or when picking up work.
allowed-tools: Read, Glob, Grep
---

# Shoal Handoff

Read the project roadmap and handoff notes to establish session context.

## Steps

1. Read `ROADMAP.md` — focus on the **Handoff** section at the bottom and the first **Upcoming** milestone
2. Summarize to the user:
   - What the last session accomplished (from the most recent handoff entry)
   - What the next session should work on
   - Current milestone status (what's done, what remains)
3. If `$ARGUMENTS` is "update" or "write":
   - Ask the user to confirm what was accomplished this session
   - Append a new handoff entry to the **Handoff** section in `ROADMAP.md` following the existing format:
     ```
     ### Session: YYYY-MM-DD — brief title

     **What we did:**
     - bullet points of accomplishments

     **What to do next:**
     - bullet points of next steps
     ```
   - Update milestone checkboxes if any items were completed

## Format

Each handoff entry uses this template:
- **Session date and title**: `### Session: YYYY-MM-DD — brief description`
- **What we did**: Concrete accomplishments (commits, features, fixes, test counts)
- **What to do next**: Actionable items for the next session, ordered by priority

## Rules

- Keep entries concise — 5-10 bullets max per section
- Include concrete numbers (test counts, commit counts, file counts)
- Reference specific files/functions when relevant
- Don't duplicate the full ROADMAP — just link to the milestone
- The handoff section lives at the bottom of ROADMAP.md, after "Future Considerations"
