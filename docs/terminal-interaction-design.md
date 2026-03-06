# Terminal Interaction Design

Shoal is most useful when you treat it as a human-AI interaction layer, not a pile of helper
commands.

The unit of design is not the individual agent. It is the loop between:

- your intent,
- the session topology,
- the approval path,
- the state you can see at a glance,
- the handoff artifacts that survive interruption.

## What Shoal should optimize

A good Shoal environment should reduce four kinds of drag:

1. Decision drag before work begins.
2. Attention drag while several agents are active.
3. Recovery drag after interruptions.
4. Approval drag when an agent blocks.

If a workflow increases those costs, it is probably over-configured.

## Design around visible state

The terminal is unforgiving when state is hidden. Shoal works because it makes several layers of
state explicit:

- `shoal status` exposes the current fleet.
- `shoal popup` compresses the supervision loop into one repeatable action.
- journals preserve the narrative of why a session exists and what changed.
- worktree names, branch names, and session names become routing metadata.

That means the CLI should not merely start agents. It should keep your operating picture legible.

## Defaults are a UX feature

Most friction in agent workflows comes from choices made too late.

Good defaults move those choices earlier:

```toml
[general]
default_tool = "codex"
worktree_dir = ".worktrees"
use_nerd_fonts = true

[tmux]
session_prefix = "_"
popup_key = "S"
popup_width = "92%"
popup_height = "88%"

[robo]
default_tool = "pi"
default_profile = "default"
session_prefix = "__"
```

This is not just convenience. It lowers the time between "I know what should happen" and "the
session exists and is usable."

## Name sessions like operators talk

The session namespace is part of the interface. Use names that reveal role, scope, and expected
handoff shape:

- `plan/release-cut`
- `feat/auth-api`
- `review/auth-api`
- `docs/auth-guide`
- `ops/devbox-recovery`

This improves:

- `shoal ls`
- status scanning
- robo escalation targeting
- journal review
- branch cleanup

## Design for interruption recovery

Shoal should make it cheap to stop and resume.

To get that effect:

- create journals at the start of meaningful work,
- record decisions before risky edits,
- keep templates stable across similar tasks,
- prefer a few durable workflows over many one-off commands,
- keep reviewer and implementer roles distinct.

The goal is for future-you to re-enter the system without reconstructing hidden context.

## Separate throughput from authority

Agents can produce throughput. They should not own authority.

Keep these human:

- task selection,
- approval of ambiguous actions,
- destructive operations,
- merge and release decisions,
- policy changes.

Let agents own:

- search,
- drafting,
- repetitive edits,
- test execution,
- first-pass review,
- summarization.

Shoal becomes safer and faster when those boundaries are explicit.

## Use topology to express intent

A single agent session is not a workflow. The topology is the workflow.

Common high-signal shapes:

- author + reviewer + supervisor
- planner + implementer + closer
- local implementers + remote batch workers
- foreground active work + background robo watch

You should be able to glance at the fleet and understand the current mode of operation.

## Developer enjoyment is operational, not decorative

Flow state is a system property. It comes from:

- low startup latency,
- clear visible state,
- quick handling of waiting prompts,
- minimal tab-hunting,
- reliable recovery after context loss.

Shoal should feel calm under load. When it feels ceremonial or noisy, simplify the loop.

## Questions to use when shaping a workflow

Before adding more automation, ask:

1. What decision is the human still making?
2. What state must be visible without opening three panes?
3. What happens when the agent blocks?
4. What survives if the operator disappears for an hour?
5. Does this make starting work faster tomorrow, or just more elaborate today?

Those questions keep the system aligned with actual developer flow instead of performative
complexity.
