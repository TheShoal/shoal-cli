# Shoal Fleet — shoal-cli

Operating doctrine and quick-reference for the shoal-cli agent fleet.

## Session namespace

| Pattern | Role | Template | Model |
|---|---|---|---|
| `impl/*` | Feature implementer | `shoal-impl` | omp slow (`claude-opus-4-6-thinking`) |
| `review/*` | Code reviewer | `shoal-reviewer` | omp smol (`gemini-3-flash-preview`) |
| `plan/*` | Planner / architect | `shoal-planner` | omp plan (`glm-5`) |
| `release/*` | Release cutter | `shoal-release` | omp commit (`claude-haiku-4.5`) |
| `ops/*` | Infrastructure / CI | `shoal-impl` | omp slow |
| `__shoal-dev` | Robo supervisor | robo profile | omp default (`claude-sonnet-4.6`) |

## Common workflows

### Feature implementation

```bash
shoal new impl/my-feature \
  --template shoal-impl \
  --branch \
  --prompt "Implement X — see ROADMAP.md backlog item '...'"
```

The `shoal-impl` template opens 3 windows: `agent` (omp, 65/35 split with terminal),
`tests` (just test runner), `monitor` (git log). `uv sync` and `git fetch` run at
session creation via `.shoal.toml` setup_commands.

### Code review

```bash
shoal new review/my-feature \
  --template shoal-reviewer \
  --branch \
  --prompt "/shoal-review — review feat/my-feature vs main"
```

The `shoal-review` skill (`.shoal/skills/shoal-review/SKILL.md`) drives the review.
Findings are grouped: Critical → Important → Nice-to-have.

### Release cut

```bash
shoal new release/v0.37.0 \
  --template shoal-release \
  --branch \
  --prompt "/shoal-release v0.37.0"
```

Uses the existing `shoal-release` and `shoal-changelog` skills from `.claude/skills/`.

### Milestone planning

```bash
shoal new plan/v0-38-scope \
  --template shoal-planner \
  --branch \
  --prompt "/shoal-handoff — then scope the next milestone and update ROADMAP.md"
```

### Parallel implementation fan-out

```bash
shoal new impl/branch-prefix-enforcement \
  --template shoal-impl --branch \
  --prompt "Implement branch_prefix enforcement in shoal new per ROADMAP.md"

shoal new impl/direnv-integration \
  --template shoal-impl --branch \
  --prompt "Implement direnv/mise integration per ROADMAP.md"

shoal robo start shoal-dev  # supervisor watches both
```

## Robo supervisor

Profile at `.shoal/robo/shoal-dev.toml`. The global robo profile (written by
`shoal robo setup shoal-dev --tool omp`) lives at
`~/.config/shoal/robo/shoal-dev.toml`. Runtime state (AGENTS.md, task-log.md)
is at `~/.local/share/shoal/robo/shoal-dev/`.

The repo-local `shoal-supervisor` template is separate: it is the interactive coordinator session you talk to inside this repo, while the robo profile above powers the standalone `shoal robo` flow.

```bash
shoal robo start shoal-dev    # start supervisor
shoal robo status shoal-dev   # check health
shoal robo stop shoal-dev     # stop
```

The robo AGENTS.md is augmented with shoal-cli–specific doctrine:
- AUTO-APPROVE: lint/test/typecheck prompts, uv sync, git fetch
- MUST ESCALATE: git push, merges, version bumps, tag creation, .github/ edits
- Task routing: idle impl sessions get next unchecked ROADMAP.md backlog item
- Review pairing: `mark_complete` triggers `shoal new review/<branch>`

## Review doctrine (priority order)

All review sessions follow this ordering. Style never outranks correctness.

1. **Behavioral regressions** — async invariants, lifecycle delegation, status detection
2. **Config/deployment risk** — config model changes, new MCP tools, CLI registration
3. **Test coverage** — new public functions without tests, async test markers
4. **Contract drift** — invariants in `ARCHITECTURE.md`, `CHANGELOG.md`/`ROADMAP.md` sync
5. **Type safety** — mypy --strict violations, unjustified `Any`
6. **Style** — only after all above are clear

## Template inheritance

All four templates extend `base-dev` and set `tool = "omp"`.
Model is selected via `OMP_LAUNCH_ARGS = "--model <id>"` in each template's `[env]`.

```
base-dev (global)
├── shoal-impl     extends=base-dev, tool=omp, slow model, mcp=[shoal-orchestrator,memory]
├── shoal-reviewer extends=base-dev, tool=omp, smol model, mcp=[shoal-orchestrator]
├── shoal-planner  extends=base-dev, tool=omp, plan model, mcp=[shoal-orchestrator,memory]
└── shoal-release  extends=base-dev, tool=omp, commit model, mcp=[shoal-orchestrator]
```

Mixins in use:
- `with-tests` (global): adds test runner window — applied to `shoal-impl` only

## Skills

Project-local skills live in `.shoal/skills/` (for cross-tool portability) and
tool-specific versions in `.claude/skills/` (11 existing skills).

| Skill | Location | Purpose |
|---|---|---|
| `shoal-review` | `.shoal/skills/shoal-review/SKILL.md` | Code review following project doctrine |
| `shoal-verify` | `.claude/skills/shoal-verify/SKILL.md` | Run CI pipeline and verify passes |
| `shoal-handoff` | `.claude/skills/shoal-handoff/SKILL.md` | Session context handoff |
| `shoal-scaffold` | `.claude/skills/shoal-scaffold/SKILL.md` | Scaffold new modules/commands |
| `shoal-release` | `.claude/skills/shoal-release/SKILL.md` | Cut a release |
| `shoal-changelog` | `.claude/skills/shoal-changelog/SKILL.md` | Generate CHANGELOG entries |
| `shoal-roadmap` | `.claude/skills/shoal-roadmap/SKILL.md` | Update ROADMAP backlog |
| `shoal-context` | `.claude/skills/shoal-context/SKILL.md` | Current project state |
| `shoal-coverage` | `.claude/skills/shoal-coverage/SKILL.md` | Coverage reporting |
| `shoal-deps` | `.claude/skills/shoal-deps/SKILL.md` | Dependency audit |
| `shoal-arch-check` | `.claude/skills/shoal-arch-check/SKILL.md` | Architecture invariant check |
