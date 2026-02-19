# Phase 2 Handoff for OpenCode Agent

## Objective

Align Shoal runtime metadata with the new tmux/fish Neovim socket contract now
implemented in `sigils`.

Contract in `sigils` now uses:

- socket key: tmux `session_id` + `window_id`
- socket path: `/tmp/nvim-<session_id>-<window_id>.sock`
- owner: interactive `nvim --listen` in the current tmux window
- tmux hook role: cleanup stale socket paths only (no headless nvim ownership)

## Why this handoff exists

`sigils` is updated, but Shoal still carries legacy assumptions (notably static
or default socket metadata, e.g. window `0`). This causes drift for `shoal nvim`
operations in non-default windows.

## Implement in Shoal (recommended minimal scope)

1. Replace static/default nvim socket persistence with dynamic resolution from
   current tmux coordinates.
2. Use tmux IDs, not names, for routing stability:
   - `#{session_id}`
   - `#{window_id}`
3. Keep persisted metadata as coordinates (session/window), not full derived
   socket string unless recomputed/validated at runtime.
4. Ensure any nvim send/open operation resolves socket at execution time.

## Candidate touchpoints in Shoal

- `src/shoal/core/state.py`
  - remove/avoid hardcoded default socket patterns tied to window `0`
- `src/shoal/cli/nvim.py`
  - resolve socket from active tmux context before `nvr` calls
- `src/shoal/cli/session.py`
  - if writing runtime metadata, persist tmux IDs and derive socket from them

## Validation checklist

1. In tmux window A, start `nvim --listen` path via wrapper and confirm `shoal nvim send` targets that instance.
2. In tmux window B (same session), confirm Shoal targets B's socket, not A.
3. Rename tmux session; verify routing still works (ID-based stability test).
4. Confirm stale socket removal does not break subsequent dynamic resolution.

## Non-goals

- Do not change `sigils` further in this task.
- Do not reintroduce headless background Neovim server ownership.

## Context note

In parallel, `sigils` also standardized OpenCode tmux integration to explicit
port launch: `opencode --port ${OPENCODE_PORT:-4096}` across Shoal/fish/tmux.
