# Shoal plan: capitalize on the NemoClaw release

## Executive summary

NemoClaw changes the conversation more than the competitive landscape.

The direct announcement is NVIDIA's release of **NemoClaw**, an **OpenClaw-specific plugin** for **OpenShell**, and the more important underlying move is **OpenShell**: a secure runtime for autonomous agents with policy-controlled filesystem, network, process, and inference access. That is not Shoal's current layer.

Shoal is already positioned as the **control plane for parallel coding agents**: worktree isolation, tmux-based supervision, status/history, journals, remote control, robo loops, and MCP-based orchestration. The risk is not that NemoClaw replaces Shoal tomorrow. The risk is that NVIDIA resets user expectations around **safe agent operations**, and Shoal looks incomplete if it does not explain where runtime safety comes from.

The right response is:

1. **Clarify the stack**: Shoal orchestrates the fleet; OpenShell secures each worker.
2. **Integrate thinly**: add optional OpenShell-backed workflows using existing Shoal seams.
3. **Double down on Shoal's moat**: handoffs, role/mode templates, remote fleet operations, and human supervision.
4. **Do not chase the wrong layer**: no Shoal-native sandbox, privacy router, or policy engine.

## What the research says

### About NemoClaw / OpenShell

- NVIDIA positions NemoClaw as: "Run any agent safely. Control its access not capabilities, and keep inference private." Source: https://build.nvidia.com/nemoclaw
- NemoClaw is explicitly an **alpha** and "not yet... production-ready." Sources:
  - https://raw.githubusercontent.com/NVIDIA/NemoClaw/main/README.md
  - https://docs.nvidia.com/nemoclaw/latest/index.html
- NemoClaw is not a general fleet manager. It is the **OpenClaw plugin for NVIDIA OpenShell** with a TypeScript plugin + versioned Python blueprint model. Source: https://docs.nvidia.com/nemoclaw/latest/reference/architecture.html
- OpenShell is the broader runtime story: sandboxed execution, declarative policy, privacy routing, and enforceable controls across filesystem/network/process/inference. Sources:
  - https://docs.nvidia.com/openshell/latest/about/overview.html
  - https://developer.nvidia.com/blog/run-autonomous-self-evolving-agents-more-safely-with-nvidia-openshell/
  - https://raw.githubusercontent.com/NVIDIA/OpenShell/main/README.md
- OpenShell already supports Claude Code, OpenCode, and Codex to varying degrees, which makes it more relevant to Shoal than NemoClaw itself. Source: https://docs.nvidia.com/openshell/latest/about/supported-agents.html
- NVIDIA is teaching the market to expect:
  - policy-enforced egress approval
  - runtime-level auditability
  - remote deployment and long-running agent operation
  - operator-facing TUI monitoring
  Sources:
  - https://docs.nvidia.com/nemoclaw/latest/network-policy/approve-network-requests.html
  - https://docs.nvidia.com/nemoclaw/latest/deployment/deploy-to-remote-gpu.html
  - https://developer.nvidia.com/blog/run-autonomous-self-evolving-agents-more-safely-with-nvidia-openshell/
- The distribution advantage is real: Build, NeMo Agent Toolkit, Nemotron/NIM, DGX/Brev, and NVIDIA media reach. Sources:
  - https://build.nvidia.com/nemoclaw
  - https://techcrunch.com/2026/03/16/nvidias-version-of-openclaw-could-solve-its-biggest-problem-security/

### About Shoal today

- Shoal already positions itself as the **layer above the agent interface**: `README.md`, `docs/index.md`.
- Shoal's strongest current wedges are already shipped:
  - worktree isolation
  - session/status/history/journal state
  - remote sessions
  - robo supervision
  - MCP orchestration tools
  - terminal-first operator UX
  Evidence:
  - `README.md`
  - `docs/index.md`
  - `ROADMAP.md`
- Shoal's visible strategic gaps are also already named in-repo:
  - structured handoff packets
  - role/mode templates
  - flagship demo workflow
  - broader fin ecosystem story
  Evidence:
  - `ROADMAP.md`
  - `docs/EXTENSIONS.md`
- Shoal does **not** currently have a hard runtime trust boundary; even the extensions docs call out that sandboxing is not implemented. Evidence:
  - `docs/EXTENSIONS.md`
  - `ARCHITECTURE.md`

## Strategic diagnosis

### What this means

NemoClaw is **not** Shoal's immediate product substitute.

The more accurate stack comparison is:

| Layer | What it does | Relevant product |
| --- | --- | --- |
| Agent runtime / sandbox | Controls what a worker can access | OpenShell |
| Agent-specific secure bootstrap | Makes one runtime/agent combination easy to launch | NemoClaw |
| Multi-agent operator control plane | Orchestrates many workers, roles, handoffs, approvals, and remote fleets | Shoal |

### What changed anyway

NVIDIA just made three things more urgent for Shoal:

1. **Explain the layer boundary clearly.** If Shoal stays silent, users will infer that it lacks a safety story rather than understanding that it operates above the runtime.
2. **Support secure-worker deployments.** If users want runtime-enforced workers, Shoal should be able to orchestrate them without fighting its own architecture.
3. **Win harder on operator workflow.** NVIDIA is strong on runtime trust. Shoal should get much stronger on multi-agent operations.

## Core strategic decision

**Position Shoal as the control plane above secure runtimes, starting with OpenShell.**

Do not respond by making Shoal a security runtime.

## Prioritized plan

## Phase 1 — 0 to 30 days

### Initiative 1: tighten positioning and comparison language

**Goal:** prevent category confusion and turn NVIDIA's launch into a framing win.

**Deliverables**
- Update top-level messaging so Shoal explicitly says it orchestrates agent fleets **above** runtime/security layers.
- Add a comparison section or page covering:
  - Shoal vs coding-agent UIs
  - Shoal vs runtime sandboxes
  - Shoal + OpenShell together
- Add a short "safe stack" diagram to docs and README.

**Repository targets**
- `README.md`
- `docs/index.md`
- `SHOAL.md`
- likely one new doc such as `docs/STACK_LAYERS.md` or `docs/OPENSHELL.md`

**Key message to earn**
- "Shoal manages the fleet. OpenShell constrains each worker."

**Acceptance criteria**
- A new reader can tell, from the first two docs surfaces, that Shoal is not claiming sandbox security itself.
- OpenShell appears as a compatible substrate, not a competitor to be ignored.

### Initiative 2: reprioritize roadmap around Shoal's actual moat

**Goal:** move roadmap effort toward operator features that runtime vendors are not solving.

**Change**
Promote these existing backlog items ahead of fin registry/distribution work:
- structured journal handoff packets (`ROADMAP.md` B2)
- role/mode templates (`ROADMAP.md` B3)
- flagship fleet demo (`ROADMAP.md` B6)

**Why**
Those are the features that turn Shoal from session launcher into operational system.

**Acceptance criteria**
- Roadmap sequencing reflects operator-control differentiation, not plugin-platform breadth.

## Phase 2 — 30 to 60 days

### Initiative 3: ship a thin OpenShell integration beta

**Goal:** let Shoal orchestrate secure workers without importing OpenShell's complexity into core Shoal.

**Principles**
- Optional only.
- No mandatory Docker/OpenShell dependency.
- Reuse existing seams: tool profiles, templates, setup commands, docs/playbooks.
- Prefer docs/templates first; core code only if workflow friction proves real.

**Scope**
Start with **generic OpenShell**, not NemoClaw:
- Claude Code in OpenShell
- OpenCode in OpenShell
- Codex in OpenShell

**Possible implementation shape**
- Add example tool profiles/templates for OpenShell-backed workers.
- Add operator guide for:
  - creating/opening sandboxes
  - launching Shoal sessions against those workers
  - using `openshell term` for network approvals while Shoal handles multi-session orchestration
- Add a design note answering one key architectural question:
  - Does Shoal own sandbox launch, or does it attach to pre-provisioned OpenShell workers?

**Repository targets**
- `examples/config/tools/`
- `examples/config/templates/`
- `docs/`
- maybe `src/shoal/cli/template.py` or config surfaces only if absolutely necessary

**Acceptance criteria**
- A user can follow documented steps to run at least one Shoal-supervised worker inside OpenShell.
- The path does not require new mandatory dependencies for standard Shoal users.

### Initiative 4: ship structured handoff packets

**Goal:** strengthen Shoal's recoverability story now that the market is moving toward always-on agents.

**Scope**
Implement a structured handoff artifact per session with at least:
- summary of work completed
- files touched
- assumptions made
- blockers / unresolved risks
- recommended next action
- reviewer brief

**Why this matters now**
NemoClaw/OpenShell make long-running autonomous work more plausible. Shoal should own the "what happened, what matters, and what to do next" layer.

**Acceptance criteria**
- `shoal journal handoff <session>` or equivalent produces a reusable artifact.
- A stopped or handed-off session has machine-readable + human-readable continuation context.

### Initiative 5: ship role/mode templates

**Goal:** turn Shoal's documented operating modes into concrete, reproducible workflows.

**Initial modes**
- author / reviewer / supervisor
- planner / implementer / closer
- local control / remote execution
- secure fleet (OpenShell-backed workers)

**Acceptance criteria**
- Users can start a named mode without hand-building topology every time.
- Docs/demo show how mode templates improve throughput and supervision quality.

## Phase 3 — 60 to 90 days

### Initiative 6: launch a flagship "secure fleet" demo

**Goal:** convert the NVIDIA moment into a more compelling Shoal story.

**Demo narrative**
1. Planner scopes work.
2. Implementer runs in an OpenShell-backed sandbox.
3. Reviewer checks the result in a separate lane.
4. Supervisor handles approvals/escalations.
5. Remote worker runs overnight.
6. Next morning Shoal surfaces status + handoff packet + what needs attention.

**Deliverables**
- scripted demo flow
- docs page
- likely `shoal demo` scenario
- screenshots / GIFs / terminal recording for docs/social

**Acceptance criteria**
- The demo makes the division of responsibility legible: runtime safety below, multi-agent control plane above.

### Initiative 7: add lightweight runtime awareness, not runtime ownership

**Goal:** improve operator visibility for secure workers without absorbing OpenShell internals.

**Possible scope**
- session metadata field for runtime type (native vs openshell)
- optional sandbox/gateway notes in `shoal info`
- links or commands surfaced in docs/output for `openshell term`, policy inspection, or sandbox status

**Non-goal**
- Shoal does not reimplement policy display, approval logic, or runtime monitoring internals.

**Acceptance criteria**
- Operators can correlate a Shoal session with its runtime context quickly.
- No runtime policy engine logic is duplicated in Shoal.

## Phase 4 — later / conditional

### Initiative 8: decide whether NemoClaw deserves first-class playbooks

**Decision rule**
Only invest in NemoClaw-specific support if real user demand appears for OpenClaw inside Shoal.

**If demand appears**
- publish a NemoClaw operator playbook
- add a niche template/profile for OpenClaw workers
- keep it clearly separate from generic OpenShell support

**If demand does not appear**
- keep NemoClaw as a documented example under the broader OpenShell story

## Anti-goals

These are attractive but strategically wrong:

1. **Do not build a Shoal-native sandbox or policy engine.** That is a different product layer.
2. **Do not make OpenShell mandatory.** Shoal's low-friction terminal orchestration is part of its advantage.
3. **Do not pivot to OpenClaw-first positioning.** NemoClaw is narrower than Shoal's actual market.
4. **Do not answer NVIDIA by accelerating fin marketplace work.** That does not solve the expectation shift.
5. **Do not market Shoal as "secure" by implication.** Be explicit about where enforcement comes from.

## Recommended roadmap changes

### Move up
- Structured handoff packets
- Role/mode templates
- Flagship fleet demo
- OpenShell integration docs/templates

### Hold or de-emphasize for now
- Fin registry/distribution marketplace work
- deeper plugin ecosystem packaging
- any sandbox/security-runtime ambitions

## Risks and mitigations

### Risk: OpenShell is alpha and moving fast
**Mitigation:** start with docs/templates/playbooks, not deep core coupling.

### Risk: category confusion makes Shoal look unsafe or incomplete
**Mitigation:** update messaging immediately and show the layered stack.

### Risk: reacting at the wrong layer burns roadmap time
**Mitigation:** require every proposed response to answer: "Does this strengthen Shoal's operator-control-plane wedge?"

## Success criteria

Within one release cycle, Shoal should be able to truthfully say:

- It is the operator control plane for heterogeneous coding-agent fleets.
- It can orchestrate workers running inside secure runtimes such as OpenShell.
- It provides better handoff, supervision, and role-based workflow management than runtime vendors do.
- It does not pretend to be the runtime security layer itself.

## Recommended immediate next actions

1. Approve a short docs/positioning pass.
2. Approve a thin OpenShell integration design spike.
3. Reorder the roadmap around handoffs, modes, and the secure-fleet demo.
4. Delay any fin-registry push until after the operator moat work lands.

## Sources

### Primary
- https://build.nvidia.com/nemoclaw
- https://developer.nvidia.com/blog/run-autonomous-self-evolving-agents-more-safely-with-nvidia-openshell/
- https://docs.nvidia.com/nemoclaw/latest/index.html
- https://docs.nvidia.com/nemoclaw/latest/reference/architecture.html
- https://docs.nvidia.com/nemoclaw/latest/reference/commands.html
- https://docs.nvidia.com/nemoclaw/latest/network-policy/approve-network-requests.html
- https://docs.nvidia.com/nemoclaw/latest/deployment/deploy-to-remote-gpu.html
- https://docs.nvidia.com/openshell/latest/about/overview.html
- https://docs.nvidia.com/openshell/latest/about/supported-agents.html
- https://docs.nvidia.com/openshell/latest/reference/support-matrix.html
- https://raw.githubusercontent.com/NVIDIA/NemoClaw/main/README.md
- https://raw.githubusercontent.com/NVIDIA/OpenShell/main/README.md

### Shoal repo evidence
- `README.md`
- `docs/index.md`
- `SHOAL.md`
- `ARCHITECTURE.md`
- `ROADMAP.md`
- `docs/EXTENSIONS.md`
