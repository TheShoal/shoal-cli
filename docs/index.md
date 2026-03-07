---
hide:
  - toc
---

# Shoal

<div class="shoal-hero">
  <div>
    <p class="shoal-eyebrow">Terminal-first orchestration for parallel AI coding agents</p>
    <h1>Design a terminal workflow where multiple agents stay legible, fast, and enjoyable to supervise.</h1>
    <p class="shoal-lede">
      Shoal gives each agent its own worktree, tmux session, state tracking, and shared MCP
      infrastructure so you can operate a fleet from one CLI without losing the human loop. The
      point is not raw autonomy. The point is sustained developer flow.
    </p>
    <div class="shoal-actions">
      <a class="md-button md-button--primary" href="getting-started/">Get Started</a>
      <a class="md-button" href="flow-state-workflows/">Run Better Workflows</a>
    </div>
  </div>
  <div class="shoal-hero-art">
    <img src="assets/robo-fish.svg" alt="Shoal robo-fish mascot">
  </div>
</div>

<div class="shoal-demo-frame">
  <img src="assets/terminal-demo.svg" alt="Shoal terminal workflow demo">
</div>

## Why Shoal exists

Shoal is built for the point where "open another terminal" stops scaling.

- You want multiple AI agents working at the same time.
- You need each agent isolated from the others at the filesystem and branch level.
- You still need one place to monitor status, approvals, errors, and MCP connectivity.
- You want automation hooks instead of copy-pasting the same setup into each session.

## What Shoal is really designing

Shoal is a terminal interaction system for human-AI collaboration.

- Templates reduce setup friction before work starts.
- Tmux topology keeps multiple sessions visible and recoverable.
- Robo handles waiting-state pressure without hiding approvals.
- Journals preserve narrative memory so interruptions are cheap.
- Naming conventions turn session lists into a readable operations board.

## What you get

<div class="shoal-card-grid">
  <a class="shoal-card" href="getting-started/">
    <strong>Fast start</strong>
    <span>Install Shoal, scaffold config, and launch a first session in minutes.</span>
  </a>
  <a class="shoal-card" href="cli-reference/">
    <strong>CLI map</strong>
    <span>See the top-level commands, subcommands, and the workflows they support.</span>
  </a>
  <a class="shoal-card" href="architecture/">
    <strong>System model</strong>
    <span>Understand how tmux, SQLite, FastAPI, and the MCP pool fit together.</span>
  </a>
  <a class="shoal-card" href="terminal-interaction-design/">
    <strong>Interaction design</strong>
    <span>See how Shoal turns naming, topology, visibility, and approvals into a usable human loop.</span>
  </a>
  <a class="shoal-card" href="ROBO_GUIDE/">
    <strong>Robo supervision</strong>
    <span>Automate approvals, routing, and escalation with a supervisor session.</span>
  </a>
  <a class="shoal-card" href="flow-state-workflows/">
    <strong>Flow-state patterns</strong>
    <span>Design session topology, supervision loops, and shell ergonomics for momentum.</span>
  </a>
  <a class="shoal-card" href="operator-playbooks/">
    <strong>Operator playbooks</strong>
    <span>Adopt concrete daily patterns for triage, feature work, remote execution, and release control.</span>
  </a>
  <a class="shoal-card" href="REMOTE_GUIDE/">
    <strong>Remote fleets</strong>
    <span>Control sessions on other machines over SSH tunnels without changing the UX.</span>
  </a>
  <a class="shoal-card" href="reference/python-api/">
    <strong>Python API</strong>
    <span>Browse the current configuration, state, and MCP server internals.</span>
  </a>
</div>

## Sixty-second workflow

```bash
shoal init
shoal setup fish

shoal new -t claude -w auth -b
shoal new -t codex -w api-refactor -b
shoal new -t gemini -w docs-refresh -b

shoal status
shoal popup
shoal attach auth
```

## Operating principles

<div class="shoal-principles">
  <div class="shoal-principle">
    <strong>Bias toward defaulted starts</strong>
    <span>Sessions should open faster than you can second-guess the setup.</span>
  </div>
  <div class="shoal-principle">
    <strong>Keep state visible</strong>
    <span>Status, waiting prompts, and handoff context should stay one gesture away.</span>
  </div>
  <div class="shoal-principle">
    <strong>Name work like an operator</strong>
    <span>Readable session names turn the fleet into a working board instead of a pile of panes.</span>
  </div>
  <div class="shoal-principle">
    <strong>Make interruption cheap</strong>
    <span>Journals, templates, and role-separated sessions should preserve narrative continuity.</span>
  </div>
  <div class="shoal-principle">
    <strong>Keep authority human</strong>
    <span>Agents should increase throughput, not silently absorb judgment calls.</span>
  </div>
</div>

## Signature operating modes

<div class="shoal-band">
  <div>
    <p class="shoal-eyebrow">Mode 01</p>
    <h3>Author, reviewer, supervisor</h3>
    <p>One agent writes, one critiques, and robo keeps the approval loop short.</p>
  </div>
  <div>
    <p class="shoal-eyebrow">Mode 02</p>
    <h3>Planner, implementer, closer</h3>
    <p>Use this when orchestration and decision sequencing matter more than raw code throughput.</p>
  </div>
  <div>
    <p class="shoal-eyebrow">Mode 03</p>
    <h3>Local control, remote execution</h3>
    <p>Keep one operator surface while sending long-running work to remote boxes and batch lanes.</p>
  </div>
</div>

## Documentation map

### Start here

- [Getting Started](getting-started.md) for installation, initialization, and the first real session.
- [CLI Reference](cli-reference.md) for command groups and high-signal examples.

### Operate Shoal

- [Flow-State Workflows](flow-state-workflows.md) for high-leverage setups, templates, and supervision loops.
- [Operator Playbooks](operator-playbooks.md) for concrete day-to-day operating patterns.
- [Robo Supervisor](ROBO_GUIDE.md) for automation patterns and escalation rules.
- [Remote Sessions](REMOTE_GUIDE.md) for SSH-backed control of remote fleets.
- [Fish Integration](FISH_INTEGRATION.md) for completions, bindings, and helper functions.
- [Local Templates](LOCAL_TEMPLATES.md) for project-scoped templates and mixins.
- [Journals](JOURNALS.md) for append-only session logs and frontmatter.
- [HTTP Transport](HTTP_TRANSPORT.md) for orchestrator transport details.
- [Troubleshooting](TROUBLESHOOTING.md) for failure recovery and environment fixes.

### Design the loop

- [Terminal Interaction Design](terminal-interaction-design.md) for the operating philosophy behind
  naming, topology, approvals, and interruption recovery.
- [Architecture](architecture.md) for the control-plane model and design boundaries.
- [Implementation Audit](implementation-audit.md) for a code-versus-claims review of the current product surface.

### Reference

- [Python API Reference](reference/python-api.md) for rendered module docs.
- [Extensions](EXTENSIONS.md) and [Extensions Review](EXTENSIONS_REVIEW.md) for fin boundaries and gaps.

### Project records

- [Contributing](project/contributing.md) for development workflow and standards.
- [Roadmap](project/roadmap.md), [Release Process](project/release-process.md), and [Changelog](project/changelog.md) for project planning and release history.
- [Architecture Guide](project/architecture-guide.md), [Worktree Environment Init](WORKTREE_ENV_INIT.md),
  [Composition Gateway](composition-gateway.md), and [Transport Spike](transport-spike.md) for deeper design investigations.

## Build the docs site locally

```bash
just docs-serve
just docs-build
```
