# TO-DO

## Now

- Fix this issue:

```
 ╰─λ shoal add grove-hub/
/Users/ricardoroche/.local/pipx/venvs/shoal/lib/python3.14/site-packages/pydantic/main.py:528: UserWarning: Pydantic serializer warnings:
  PydanticSerializationUnexpectedValue(Expected `enum` - serialized value may not be as expected [field_name='status', input_value='running', input_type=str])
  return self.__pydantic_serializer__.to_json(
🤖 Session 'grove-hub' created (id: s4vx65au, tool: claude)
  Tmux: shoal_s4vx65au

Attach with: shoal attach grove-hub
```

- Encountered this critical error while using the popup:

````
 ╰─λ shoal attach grove-hub
Tmux session 'shoal_s4vx65au' not found (session may have died)
/Users/ricardoroche/.local/pipx/venvs/shoal/lib/python3.14/site-packages/pydantic/main.py:528: UserWarning: Pydantic serializer warnings:
  PydanticSerializationUnexpectedValue(Expected `enum` - serialized value may not be as expected [field_name='status', input_value='stopped', input_type=str])
  return self.__pydantic_serializer__.to_json(```
````

- Change the name of the tmux session to the name of the project, not just "shoal" all the time
- Update architecture and README

- Session Groups (i.e. Projects?) -- I will often have more than one session per repo/project so these should get grouped together in some way

- Change default session name to project dir + worktree if worktree was supplied

- Encountered this issue while trying to fork off a session without a worktree:

```
 ╭─  …/shoal
 │ ( main) [?]                                                                         v3.12.8  v0.2.0
 ╰─λ shoal fork
Failed to create worktree for fork
```

- I opened a Shoal conductor session, but it looks like just any old OpenCode instance, so I'm not really sure what it's doing. It's just a TMUX session with an OpenCode window. Am I missing something? What is this window actually doing? How is it special at all?

- These should probably be moved to `~/.local/state` instead for UNIX/GNU consistency?

```
Background daemon process (pid stored in ~/.config/shoal/state/watcher.pid)
- Logs to ~/.config/shoal/state/logs/watcher.log
```

- Completions get messed up when tab completing after the command (shoal add) has been inputted:

```
╭─  ~/dev/laboratory                                                                               ↓60%
 │ (8m28s)
 ╰─λ shoal add ./shoal\n./grove-hub\n./openclaw-codehunter add
```

- Add a guide to the README on how to add stuff to tmux status bar and how to configure the popup

- Change the ctrl-k to kill shortcut in the popup to ctrl-x
