# Shoal MCP Dogfooding Issues - 2026-04-07

Session: Hermes via Discord reviewing zendesk-pipeline fixes

## Issue 1: No model override in create_session

**Problem:** `mcp_shoal_orchestrator_create_session` has no `model` parameter to specify which LLM to use.

**Impact:** Cannot configure per-session model overrides (e.g., `z-ai/glm-5` via OpenRouter).

**Workaround:** None currently - pisces uses its default model configuration.

**Suggested Fix:** Add optional `model` field to `CreateSessionParams` that gets passed to the tool profile or environment.

---

## Issue 2: Prompt parsing fails with special characters in fish shell

**Problem:** When passing prompts via `create_session(prompt=...)` or `send_keys`, special characters like `?` and `&&` are interpreted by fish shell, causing errors:

```
fish: command substitutions not allowed in command position. Try var=(your-cmd) $var ...
```

**Impact:** Complex prompts with questions or multi-command sequences fail to execute.

**Workaround:** Use simple prompts without `?`, `&&`, `()`, or other shell-special characters.

**Suggested Fix:** 
1. Escape prompts properly before sending to fish
2. Consider using a heredoc or file-based prompt passing
3. Add prompt sanitization in the MCP tool

---

## Issue 3: Long prompts get mangled in tmux

**Problem:** Long prompts passed to `create_session` appear concatenated without spaces in the tmux pane, making them unreadable.

**Impact:** Agent receives garbled prompt text.

**Workaround:** Keep prompts short and send additional instructions via `send_keys` after session starts.

**Suggested Fix:** Investigate how prompts are being passed to tmux - may need to use a different mechanism for long text.

---

## Session Info

- Shoal version: v0.39.0
- Shell: fish 4.6.0
- Terminal: tmux 3.6a
- Sessions tested: `review-prefetch-fix`, `review-dlq-alerting`
