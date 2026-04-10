# Dogfood bugs: `shoal ticket start` (2026-04-09)

Found while launching 5 parallel SDK sessions (AIA-469 through AIA-473) on `ai-sdk` using `shoal ticket start AIA-XXX -t claude-bedrock-sonnet`.

## Bug 1: `issueFilter` GraphQL query returns 400

**File:** `src/shoal/services/linear_bridge.py:72`

The `_QUERY_ISSUE` uses `issueFilter(filters: { identifier: { eq: $identifier } })` which is not a valid Linear API top-level query. Linear returns HTTP 400.

**Fix:** Replace with `issue(id: $identifier)` — Linear's `issue()` query accepts identifiers like `"AIA-469"` directly.

```diff
-query Issue($identifier: String!) {
-  issueFilter(filters: { identifier: { eq: $identifier } }) {
+query Issue($identifier: String!) {
+  issue(id: $identifier) {
     id
     identifier
     title
     description
     url
     priority
     branchName
-    teamId
+    team { id }
     state { name type }
     assignee { name }
     labels { nodes { name } }
   }
 }
```

Also update `_parse_issue` (line 317) and `get_issue` (line 368):

```diff
-node: dict[str, Any] | None = data.get("issueFilter")
+node: dict[str, Any] | None = data.get("issue")
```

```diff
-team_id=node.get("teamId") or "",
+team_id=(node.get("team") or {}).get("id") or node.get("teamId") or "",
```

The `teamId` fallback keeps backward compat with the team issues queries that may still return it as a flat field.

---

## Bug 2: Branch name validation rejects Linear's `branchName`

**File:** `src/shoal/cli/session_create.py` (branch validation logic)

Linear returns branch names like:
```
ricardoroche/aia-469-sdk-resilienttool-base-class-for-3rd-party-api-circuit
```

Shoal's branch validator requires `category/slug` where category must be one of: `feat, fix, bug, chore, docs, refactor, test, plan, impl, review, batch, ops`.

`ticket start` passes `issue.branch_name` directly to session creation, which then fails validation.

**Options:**
1. Normalize the branch name in `ticket start` — e.g., `feat/{identifier_lower}` as fallback when `branchName` doesn't match the pattern
2. Relax validation for `ticket start` since the branch is auto-generated from a known source
3. Add a `--branch-name` override flag to `ticket start`

Recommendation: option 1 — `ticket start` should construct `feat/aia-469-resilient-tool` (slugified title) as default, falling back to Linear's `branchName` only if it passes validation.

---

## Bug 3: `worktree_is_dirty` blocks on untracked files

**File:** `src/shoal/cli/session_create.py:372` / `src/shoal/core/git.py:159`

`session_create.py` calls `git.worktree_is_dirty()` before creating a worktree. This function uses `git status --porcelain` which includes untracked files (`??` lines). A repo with untracked files (common — `.shoal/`, scratch files, generated code) is blocked from creating worktrees.

There's already a `worktree_has_tracked_changes()` function (line 168) that filters out `??` lines.

**Fix:** Use `worktree_has_tracked_changes()` instead of `worktree_is_dirty()` at line 372:

```diff
-if git.worktree_is_dirty(str(resolved_path)):
+if git.worktree_has_tracked_changes(str(resolved_path)):
```

Untracked files don't affect `git worktree add` — only staged/unstaged changes to tracked files matter for HEAD consistency.

---

## Workaround used

Bypassed `ticket start` entirely and used `shoal new` directly:

```bash
# Stash untracked files to satisfy dirty check
git stash -u

# Launch sessions manually
shoal new -t claude-bedrock-sonnet -w feat/aia-469-resilient-tool -b -n aia-469-resilient-tool /path/to/ai-sdk

# Pop stash, copy prompts to worktrees, inject via tmux
git stash pop
cp .shoal/prompts/AIA-469-resilient-tool.md .worktrees/feat-aia-469-resilient-tool/.shoal/prompts/
tmux send-keys -t '%0' 'Implement the feature described in this file. Read it first, then implement everything in the plan: @.shoal/prompts/AIA-469-resilient-tool.md' Enter
```

---

## Scope

All three bugs affect the `shoal ticket start` happy path. Bug 1 is a complete blocker (HTTP 400). Bugs 2 and 3 are hit sequentially after fixing bug 1.

Fix priority: 1 > 3 > 2 (bug 1 is a hard crash, bug 3 is an unnecessary blocker, bug 2 needs a design decision).
