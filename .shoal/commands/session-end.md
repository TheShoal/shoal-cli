---
description: Capture session outcome before ending — record what worked, what failed, lessons learned
---

Before ending this session:

1. Run `git log --oneline -5` to review commits made
2. Run `git diff HEAD~1..HEAD --stat` to confirm changes
3. Call the `capture_session_outcome` MCP tool with:
   - goal: what you were asked to implement
   - commands_failed: any commands that didn't work (with brief reason)
   - commands_worked: key commands that succeeded
   - root_causes: any bugs or blockers you hit
   - fixes_applied: how you resolved them
   - lessons: what future agents should know about this codebase area
4. Run `shoal status` one final time to confirm no blocking collisions
5. Optionally call `generate_weekly_synthesis` if this is the last session of the day
   to get a prompt for reviewing the day's work holistically

Then exit cleanly.
