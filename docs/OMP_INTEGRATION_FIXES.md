# OMP Integration Fixes for Shoal CLI

**Date:** 2026-03-31  
**Author:** AI Agent (via shoal session)  
**Status:** Draft — Requires Review

## Problem Statement

During OMP (oh-my-pi) agent configuration setup for smorgasbord, a critical workflow issue was discovered: **Shoal sessions created with `--tool omp` don't actually use the `omp` executable** — they default to `pi` and lack proper OMP awareness.

This document outlines the fixes needed in shoal-cli to properly support OMP as a first-class tool.

---

## Root Cause Analysis

### What Happened

1. User requested OMP agent setup in smorgasbord
2. Agent ran: `shoal new --name "omp-agent-setup" --tool pi`
3. Session was created successfully
4. Agent then worked in the **current session** instead of attaching to the shoal session
5. Work was completed outside shoal orchestration

### Why It Happened

**Three interconnected issues:**

1. **Tool default bias**: Shoal defaults to `pi` everywhere — in mode presets, help text, and fallback logic
2. **No OMP tool config**: No `.shoal/tools/omp.toml` exists in the default configuration
3. **Workflow confusion**: The agent didn't understand that shoal sessions should be attached to, not created and ignored

### Evidence from Code

**`src/shoal/cli/mode_presets.py`:**
```python
MODE_REGISTRY: dict[str, ModeSpec] = {
    "feature-lane": ModeSpec(
        fallback_tool="codex",  # OK
        ...
    ),
    "planner": ModeSpec(
        fallback_tool="pi",  # ← pi hardcoded
        ...
    ),
    "implementer": ModeSpec(
        fallback_tool="pi",  # ← pi hardcoded
        ...
    ),
}
```

**`src/shoal/cli/session_create.py` (line 62):**
```python
typer.Option(
    "-t", "--tool",
    help="AI tool to use (pi recommended; opencode status is best-effort)",
    # ← Help text mentions pi and opencode, not omp
)
```

**`src/shoal/cli/robo.py`:**
```python
tool = tool or "pi"  # ← Hardcoded default
```

---

## Required Fixes

### 1. Add OMP Tool Configuration

**File:** `.shoal/tools/omp.toml` (bundle with shoal-cli)

```toml
[tool]
name = "omp"
command = "omp"
description = "Oh My Pi — AI coding agent for the terminal"

[tool.session]
# OMP uses the same tmux-based session model as pi
startup_command = "omp"

[tool.status]
# OMP has similar output patterns to pi
provider = "pi"  # Reuse pi's status provider initially
# TODO: Create omp-specific status provider if output differs

[tool.capabilities]
supports_worktrees = true
supports_mcp = true
supports_branching = true
```

**Action:** Add to `src/shoal/integrations/tools/` or bundle in default config scaffolding.

---

### 2. Update Mode Presets

**File:** `src/shoal/cli/mode_presets.py`

**Current:**
```python
"planner": ModeSpec(
    fallback_tool="pi",
    ...
),
"implementer": ModeSpec(
    fallback_tool="pi",
    ...
),
```

**Proposed:**
```python
"planner": ModeSpec(
    fallback_tool="omp",  # Changed from pi
    ...
),
"implementer": ModeSpec(
    fallback_tool="omp",  # Changed from pi
    ...
),
```

**Rationale:** OMP is the actively maintained fork of pi with better extension support, skills system, and shoal integration.

---

### 3. Update Help Text

**File:** `src/shoal/cli/session_create.py`

**Current (line 62):**
```python
help="AI tool to use (pi recommended; opencode status is best-effort)",
```

**Proposed:**
```python
help="AI tool to use (omp recommended; pi/codex/claude/opencode also supported)",
```

**Also update:** `src/shoal/cli/robo.py` help text similarly.

---

### 4. Add Default Tool Configuration

**File:** `src/shoal/core/config.py` or default config scaffold

**Current:**
```python
default_tool: str = "pi"
```

**Proposed:**
```python
default_tool: str = "omp"
```

**Migration path:**
- New installations default to `omp`
- Existing configs preserve `pi` via user's `config.toml`
- Add migration note in CHANGELOG

---

### 5. Create OMP Status Provider (Optional but Recommended)

**File:** `src/shoal/core/status_provider.py` or new `src/shoal/integrations/omp/`

**Why:** OMP may have different output patterns than pi. A dedicated status provider ensures accurate detection.

**Implementation:**
```python
class OmpStatusProvider(ToolStatusProvider):
    """Status detection for OMP (oh-my-pi) sessions."""
    
    def parse_status(self, output: str) -> SessionStatus:
        # OMP-specific patterns
        if "Thinking..." in output or "Processing..." in output:
            return SessionStatus.THINKING
        if "Waiting for" in output or "Confirm:" in output:
            return SessionStatus.WAITING
        if "Error:" in output or "Failed:" in output:
            return SessionStatus.ERROR
        return SessionStatus.IDLE
```

**Register in:** `src/shoal/core/config.py` tool loading logic.

---

### 6. Update Documentation

**Files to update:**
- `README.md` — Update quickstart examples to use `omp`
- `docs/tools.md` — Add OMP tool documentation
- `docs/getting-started.md` — Update installation steps
- `CLAUDE.md` — Update tool references
- `DOGFOOD.md` — Update dogfooding examples

**Example README update:**
```bash
# Before
shoal new --name "my-feature" --tool pi

# After
shoal new --name "my-feature" --tool omp
```

---

### 7. Add OMP to Robo Supervisor

**File:** `src/shoal/cli/robo.py`

**Current:**
```python
tool = tool or "pi"
```

**Proposed:**
```python
tool = tool or cfg.general.default_tool  # Use config default
```

**Also:** Update robo brief templates to mention OMP.

---

### 8. Update Shell Completions

**File:** `src/shoal/integrations/fish/templates/completions.fish`

**Add:**
```fish
complete -c shoal -n '__shoal_has_subcommand new' -l tool -r -f -a "omp pi codex claude opencode"
```

---

### 9. Add Migration Guide

**File:** `docs/migration/pi-to-omp.md`

**Content:**
```markdown
# Migrating from Pi to OMP

## Why Migrate?

OMP (oh-my-pi) is the actively maintained fork of pi-coding-agent with:
- Better extension system (TypeScript-based)
- Skills system (file-backed capability packs)
- Improved shoal integration
- Active development and community

## Migration Steps

1. Install OMP:
   ```bash
   npm install -g @oh-my-pi/pi-coding-agent
   ```

2. Update shoal config:
   ```bash
   shoal config set default-tool omp
   ```

3. Migrate existing sessions:
   - Pi sessions continue to work
   - New sessions default to OMP
   - No breaking changes

## Compatibility Notes

- Pi tool configs remain valid
- Session formats unchanged
- MCP servers compatible
```

---

### 10. Add OMP to Tool Discovery

**File:** `src/shoal/cli/config_cmd.py` (or wherever `shoal config show` lists tools)

**Ensure:** OMP appears in the list of available tools when running `shoal config show`.

---

## Implementation Priority

### Phase 1: Critical (Blocks OMP Usage)
1. ✅ Add OMP tool config (`omp.toml`)
2. ✅ Update help text to mention OMP
3. ✅ Update mode presets to use OMP as default

### Phase 2: Important (Improves UX)
4. Update default tool config
5. Add OMP status provider
6. Update documentation

### Phase 3: Nice-to-Have
7. Add migration guide
8. Update shell completions
9. Robo supervisor updates

---

## Testing Plan

### Unit Tests
- [ ] Test OMP tool config loads correctly
- [ ] Test mode presets return `omp` as default
- [ ] Test help text includes OMP

### Integration Tests
- [ ] Create session with `--tool omp`
- [ ] Verify OMP executable launches
- [ ] Verify status detection works
- [ ] Verify worktree creation works with OMP

### Manual Testing
```bash
# Test 1: Basic session creation
shoal new --name "omp-test" --tool omp

# Test 2: Verify OMP is running
shoal attach omp-test
# Should see OMP prompt, not pi

# Test 3: Mode defaults
shoal new --mode implementer --name "test"
# Should use OMP, not pi

# Test 4: Robo supervisor
shoal robo watch --tool omp
# Should use OMP for supervision
```

---

## Acceptance Criteria

- [ ] `shoal new --tool omp` launches OMP executable
- [ ] `shoal new --mode implementer` defaults to OMP
- [ ] Help text mentions OMP as recommended tool
- [ ] Documentation updated with OMP examples
- [ ] All existing tests pass
- [ ] New tests added for OMP integration
- [ ] Migration guide published

---

## Related Files

### To Create
- `.shoal/tools/omp.toml`
- `docs/migration/pi-to-omp.md`
- `src/shoal/integrations/omp/status_provider.py` (optional)

### To Modify
- `src/shoal/cli/mode_presets.py`
- `src/shoal/cli/session_create.py`
- `src/shoal/cli/robo.py`
- `src/shoal/core/config.py`
- `README.md`
- `docs/tools.md`
- `docs/getting-started.md`
- `CLAUDE.md`
- `DOGFOOD.md`
- `src/shoal/integrations/fish/templates/completions.fish`

---

## Notes

### Why OMP Over Pi?

1. **Active Development**: Pi is no longer actively maintained; OMP is the active fork
2. **Better Extension System**: TypeScript extensions vs. pi's limited hooks
3. **Skills System**: File-backed capability packs with `skill://` protocol
4. **Shoal Awareness**: OMP has better understanding of session orchestration
5. **Community**: Growing community around OMP with plugins and extensions

### Backward Compatibility

All changes are backward compatible:
- Existing `pi` configs continue to work
- Users can explicitly choose `--tool pi`
- Default changes only affect new installations

### Future Considerations

- Add OMP-specific MCP servers
- Create OMP template presets
- Integrate OMP's extension system with shoal hooks
- Support OMP's task tool for subagent orchestration

---

## Next Steps

1. **Review this document** with shoal maintainers
2. **Create GitHub issue** in the-shoal/shoal-cli repo
3. **Implement Phase 1 fixes** (critical path)
4. **Test with smorgasbord** OMP configuration
5. **Document in CHANGELOG**
6. **Release** with migration notes

---

**References:**
- OMP Repository: https://github.com/can1357/oh-my-pi
- Shoal CLI Repository: https://github.com/the-shoal/shoal-cli
- Smorgasbord PR: https://github.com/US-Mobile/smorgasbord/pull/new/feat/omp-agent-config
