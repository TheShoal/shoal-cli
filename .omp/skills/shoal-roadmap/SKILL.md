---
name: shoal-roadmap
description: Add items to the Shoal ROADMAP.md backlog or milestone. Use when noting ideas, feature requests, or future work.
---

# Shoal Roadmap

Add items to ROADMAP.md — either to the **Backlog** section or to a specific milestone.

## Steps

1. Read `ROADMAP.md` to understand current structure
2. Determine:
   - The item description
   - Target section (backlog by default, or a specific milestone like `v0.28.0`)
3. Format the item matching existing style:
   - Backlog: `- **Short title**: Description with context and rationale`
   - Milestone: `- [ ] Description` (checkbox format)
4. Add the item to the appropriate section in `ROADMAP.md`
5. Confirm what was added and where

## Format

Backlog items:
```markdown
- **Feature Name**: One-line description — context on why, what it enables, any blockers or dependencies
```

Milestone items:
```markdown
- [ ] Feature description
```

## Rules

- Keep descriptions concise but include enough context for a future session to understand
- Note dependencies or blockers inline (e.g., "blocked by X", "requires Y")
- Don't create new milestones — only add to existing ones or to Backlog
- If the item relates to an existing backlog entry, update it rather than duplicating
- Preserve grouping within sections (related items together)
