# TO-DO

## Done in v0.3.0

- [x] Fix Pydantic serialization warnings (pass `SessionStatus` enum instead of raw strings)
- [x] Change tmux session name to use session name (e.g., `shoal_grove-hub` instead of `shoal_s4vx65au`)
- [x] Change default session name to `{project}/{worktree}` when worktree is supplied
- [x] Fix `shoal fork` without worktree (added `--no-worktree` flag)
- [x] Move watcher PID/logs to `~/.local/state/shoal/` for XDG compliance
- [x] Change popup kill shortcut from ctrl-k to ctrl-x
- [x] Add tmux status bar and popup configuration guide to README
- [x] Update architecture docs and README
- [x] Conductor documentation: explain it's an AI agent running with AGENTS.md instructions

## Next

- Session Groups (i.e. Projects?) -- sessions for the same repo/project should get grouped together in some way (e.g., `shoal ls` could group by git root)

- Completions get messed up when tab completing after the command (shoal add) has been inputted:

```
╭─  ~/dev/laboratory                                                                               ↓60%
 │ (8m28s)
 ╰─λ shoal add ./shoal\n./grove-hub\n./openclaw-codehunter add
```

- Improve conductor: provide a way for the conductor to actually interact with child sessions (e.g., send keys, approve actions). Currently it just runs an AI tool with an AGENTS.md context file.
