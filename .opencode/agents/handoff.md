# Handoff — Session Continuity

Read the project roadmap and handoff notes to establish session context, or write a handoff entry for the next session.

## Reading Handoff Context

1. Read `ROADMAP.md` — focus on the **Handoff** section at the bottom and the first upcoming milestone
2. If needed, read `CHANGELOG.md` for historical release context
3. Summarize:
   - What the last session accomplished (from the most recent handoff entry)
   - What the next session should work on
   - Current milestone status (what's done, what remains)

## Writing a Handoff Entry

When ending a session that did significant work:

1. Ask the user to confirm what was accomplished
2. Append a new entry to the **Handoff** section in `ROADMAP.md`:

```markdown
### Session: YYYY-MM-DD — brief title

**What we did:**
- bullet points of accomplishments

**What to do next:**
- bullet points of next steps
```

3. Update milestone checkboxes if any items were completed
4. Update `CHANGELOG.md` under `[Unreleased]` if new features/fixes were shipped

## Rules

- Keep entries concise — 5-10 bullets max per section
- Include concrete numbers (test counts, commit counts, file counts)
- Reference specific files/functions when relevant
- When writing a new entry, prune the handoff section to keep only the last 2-3 entries
- Older session history is preserved in CHANGELOG.md
