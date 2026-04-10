You are reviewing Shoal's MkDocs documentation for specificity and cohesion.

Goal
- Make docs explicitly clear about where Shoal is opinionated.
- Clarify how new functionality (especially Linear + GitHub bridges) is used in real workflows.
- Show how features tie together end-to-end, not as isolated commands.

Scope
- mkdocs.yml
- docs/index.md
- docs/features.md
- docs/cli-reference.md
- docs/ticket-decompose.md
- docs/github-workflows.md
- docs/patterns/multi-agent-coordination.md

What to audit (be concrete)
1) Opinionated behavior that should be called out explicitly:
   - Branch/worktree naming conventions and validation constraints
   - Template inheritance and resolution order
   - Status detection contracts and pane assumptions
   - Prompt delivery model (arg/flag/keys) and why OMP/Pi defaults matter
   - Session lifecycle assumptions (clean tracked changes vs untracked files)

2) Bridge-specific flows:
   - Linear: sync/pick/start/done/decompose/report lifecycle and expected state transitions
   - GitHub: ls-prs/start-pr/review-pr/post-review/done-pr lifecycle
   - How Linear and GitHub flows connect to session tags, reports, and handoffs

3) Cohesion gaps:
   - Places where docs mention a feature but not when to use it
   - Missing cross-links between CLI reference, feature docs, and workflow guides
   - Any stale or vague text that hides operational constraints

Output format (required)
A) Findings table with columns:
   - Severity (High/Medium/Low)
   - File:line
   - Gap
   - Why it matters operationally
   - Recommended doc change (1-3 sentences)

B) Proposed structure tweaks:
   - Exact headings to add/rename
   - Exact files to move content between (if needed)

C) Draft copy blocks:
   - 2-4 short drop-in doc sections we can paste directly
   - At least one section titled: "Shoal Opinionated Defaults"
   - At least one section titled: "Linear + GitHub End-to-End Workflow"

D) Implementation plan:
   - Ordered, minimal set of doc edits
   - Include estimated risk and reviewer checklist

Constraints
- Be specific and operational; no generic doc advice.
- Use file:line references for every finding.
- Favor minimal edits over broad rewrites.
- Do NOT run full test/build; this is a documentation review task.
