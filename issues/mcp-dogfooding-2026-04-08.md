# Shoal MCP Dogfooding Issues - 2026-04-08

Source: Dogfooding session fixing Pisces issues via Shoal + Gemma 4 31B
Related: `~/pantheon/tools/pisces/issues/mcp-dogfooding-2026-04-07.md`

---

## Issue S1: Worktrees don't get `node_modules` — need auto install

**Severity:** High
**Status:** Open

**Problem:** When Shoal creates a git worktree for branch isolation, the worktree has no `node_modules`. Bun/npm packages aren't tracked by git, so the worktree starts with zero dependencies. Pisces (and any Node/Bun tool) immediately crashes on launch:

```
error: Cannot find package 'handlebars'
```

**Repro:**
1. `shoal new -t pisces -n my-fix .` (creates worktree)
2. Pisces launches in the worktree → crash

**Expected:** Shoal should detect the package manager (bun.lock → `bun install`, package-lock.json → `npm install`, etc.) and auto-run install after creating the worktree. Could be a template config option like `post_create = "bun install"`.

**Workaround:** Manually `bun install` in each worktree before launching the tool.

---

## Issue S2: `shoal new` lacks `--model` flag

**Severity:** Medium
**Status:** Open

**Problem:** There's no way to pass a model to the spawned agent from the CLI. The only option is using a template with a hardcoded model (e.g., `gemma-test` template has `--model openrouter/google/gemma-4-31b-it:free`). But this requires creating a template for every model you want to use.

**Repro:**
1. `shoal new --help` — no `--model` flag listed
2. No way to say `shoal new -t pisces --model openrouter/google/gemma-4-31b-it .`

**Expected:** `shoal new --model <provider/model>` should pass the model to the tool's CLI command. Pisces supports `--model` on its CLI already.

**Workaround:** Use templates with hardcoded models, or send the command manually via `send_keys`.

---

## Issue S3: Template pane commands not always applied

**Severity:** Medium
**Status:** Open

**Problem:** The `gemma-test` template has `command = "{tool_command} --model openrouter/google/gemma-4-31b-it:free"` but the session launched with just `fish` as the command. The tool command wasn't applied to the tmux pane.

**Repro:**
1. Create session with `gemma-test` template via `shoal new -t pisces --template gemma-test`
2. Session starts with `fish` shell, not `pisces --model ...`

**Expected:** Template's command should be sent to the tmux pane after creation.

**Workaround:** Manually send the command via `send_keys`.

---

## Issue S4: Worktree creation on dirty/unmerged HEAD succeeds silently

**Severity:** Medium
**Status:** Open

**Problem:** The main checkout had an incomplete merge in progress. Shoal created worktrees from HEAD anyway, but HEAD was in an inconsistent state — some files existed on disk but weren't in the git tree (unmerged). This caused missing files in worktrees.

**Repro:**
1. Start a `git merge` with conflicts (don't resolve)
2. `shoal new -t pisces -n my-fix .` — worktree created from incomplete HEAD

**Expected:** Shoal should either refuse to create a worktree when the working tree is dirty/unmerged, or warn the user.

---

## Issue S5: Free-tier rate limits cause frequent model fallbacks

**Severity:** Low
**Status:** By design

**Problem:** Using `openrouter/google/gemma-4-31b-it:free` on OpenRouter's free tier hits rate limits quickly (429 errors). Pisces falls back through its model chain, ending up on `minimax/minimax-m2.7` or `google/gemma-4-26b-a4b-it` instead.

**Not a Shoal bug** — this is expected behavior for free-tier models. Documenting for awareness.

---

## Fix Session Summary

- **Session:** `fix-p1-model-enforce` using `gemma-test` template
- **Actual model used:** `google/gemma-4-26b-a4b-it` (fell back from `gemma-4-31b-it:free`)
- **Pisces fixes delivered:** 3 commits merged to `main`
- **Shoal issues found:** 5 (4 open, 1 by design)
- **Workaround burden:** Manual `bun install` + manual `send_keys` for each session = ~2 min overhead per session
