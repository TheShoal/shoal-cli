# Shoal Refocus Plan

## Purpose
This document serves as a persistent handoff plan and source of truth for the Shoal project. It aligns the technical implementation with the finalized product positioning and outlines the remaining steps to reach the v0.8.0 milestone.

## Product Positioning
- **Personal-First**: Optimized for a single-maintainer, high-velocity AI coding workflow.
- **Fish-Only**: Primary support for Fish shell. Bash and Zsh are explicitly out of scope for integration features (completions, keybindings, abbreviations).
- **Core Stack**: Python (Typer/Pydantic), tmux, Fish, Neovim, and OpenCode (primary agent).

## Finalized Decisions
- **Global Templates Only**: Templates are managed globally; no per-project template complexity for now.
- **Arbitrary Shell Commands**: Templates support running any shell command in windows/panes.
- **OpenCode Default**: `shoal new` and other agent commands default to OpenCode.
- **Flexible UI**: Neovim panes are optional and template-driven, not mandatory for every session.
- **Branch Naming**: Strict `category/slug` convention (e.g., `feat/my-feature`, `fix/bug-name`).
- **Tmux Sanitization**: Session/worktree tmux names replace `/` with `-` (e.g., `feat/task` -> `feat-task`) to ensure tmux compatibility.

## Phased Plan

### Phase 0: Scope Alignment (Completed)
- [x] Reset documentation scope in `README.md`, `ROADMAP.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`, and `docs/TROUBLESHOOTING.md`.
- [x] Remove outdated bash/zsh support claims.

### Phase 1: Template Infrastructure (Completed)
- [x] Define Pydantic schema for session templates (windows, panes, commands).
- [x] Implement template loader and registry.
- [x] Add CLI commands: `shoal template ls`, `shoal template show`, `shoal template validate`.

### Phase 2: Template Execution (Completed)
- [x] Update `shoal new --template <name>` to parse and execute template definitions.
- [x] Implement tmux window and pane creation logic based on templates.
- [x] Add comprehensive tests for template configuration, CLI, and startup behavior.

### Phase 3: Refinement & Validation (Completed)
- [x] **Dry-run Support**: Add `--dry-run` to `shoal new` to preview tmux commands without execution.
- [x] **Naming Enforcement**: Implement stricter validation for the `category/slug` branch naming policy.
- [x] **Demo Cleanup**: Remove hardcoded bash dependency paths from `shoal demo` code.

### Phase 4: Release & Handoff (Upcoming)
- [ ] Final v0.8.0 release tagging.
- [x] Update `docs/ROBO_GUIDE.md` with template-based supervisor patterns.

## Current Implementation Map
- `src/shoal/models/config.py`: Template schema models (`SessionTemplateConfig` and related models).
- `src/shoal/cli/template.py`: Template management CLI commands.
- `src/shoal/cli/session.py`: `shoal new --template <name>` execution and tmux layout orchestration.
- `src/shoal/core/config.py`: Global template pathing + loading (`templates_dir`, `available_templates`, `load_template`).
- `src/shoal/cli/__init__.py`: `template` command group wiring.
- `tests/test_config.py`: Template loading/discovery validation tests.
- `tests/test_cli.py`: Template CLI tests.
- `tests/test_tmux_startup.py`: Template startup layout tests for `shoal new`.

## Verification Commands
```bash
# Validate template system
shoal template ls
shoal template validate

# Test template-based session creation
shoal new -w feat/example --template feature-dev

# Run targeted tests for refocus work
uv run pytest tests/test_config.py tests/test_cli.py tests/test_tmux_startup.py -k "template or startup"
```

## Next-Session Kickoff Checklist
1. Verify `shoal template ls` shows expected global templates from `~/.config/shoal/templates`.
2. Implement `shoal new --dry-run` in `src/shoal/cli/session.py` to preview tmux actions.
3. Add explicit `category/slug` branch naming enforcement in `src/shoal/cli/session.py`.
4. Remove remaining bash-dependent demo paths in `src/shoal/cli/demo.py`.
