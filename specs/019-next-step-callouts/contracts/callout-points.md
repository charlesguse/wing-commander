# Contract: Callout Call Sites

This is the per-stage migration contract for spec 019 — every existing
comment site FR-011 covers, its current behavior, and its new
`wing-commander-callout` invocation shape. `contracts/callout-format.md`
defines the rendering; this file defines *where* each rendering is invoked
and with what deterministic condition selects `kind`.

| # | Workflow | Site (current) | Deterministic `kind` condition | New invocation |
|---|---|---|---|---|
| 1 | `intake.yml` | Step 7, agent-authored "post a comment linking the PR and stating the spec is ready for review" | Always `action` when reached (this branch of step 7 only runs when no `[NEEDS CLARIFICATION]` markers remain) | `kind: action`, `summary: "Review the spec PR"`, `pr-url:` the draft PR URL (from the `gh pr create` step already run in step 6), `pr-label: "the spec PR"` |
| 2 | `intake.yml` | Step 7, agent-authored clarification-needed comment (`"## 🔍 Clarification needed"` heading) | Always `action` when reached (spec.md still has markers) | `kind: action`, `summary: "Answer the open clarification questions"`, `body-file:` the agent-written questions file, no `pr-url` |
| 3 | `clarify.yml` | Step 6, agent-authored "restate ONLY the still-open questions" | New deterministic step after the agent step: `grep -q '\[NEEDS CLARIFICATION\]' spec.md` | `kind: action`, `summary: "Answer the remaining clarification questions"`, `body-file:` agent-written restatement, no `pr-url` (same template as #2) |
| 4 | `clarify.yml` | Step 6, agent-authored "say the spec is ready for review and link the PR" | Same deterministic grep, negated | `kind: action`, `summary: "Review the spec PR"`, `pr-url:` the draft PR URL (via `gh pr list --head <branch>`, already computed by the existing "Update the draft PR description" step), `pr-label: "the spec PR"` (same template as #1 — Acceptance Scenario 2) |
| 5 | `finalize.yml` | *(none today)* — "Open the final pull request" step opens the PR with no issue comment | New step, always `action`, gated on `steps.diff.outputs.skip != 'true'` and `steps.verify-pr` succeeding | `kind: action`, `summary: "Review the implementation PR"`, `pr-url:` `steps.verify-pr`'s resolved PR number/URL, `pr-label: "the implementation PR"` — **the core fix for User Story 1** |
| 6 | `finalize.yml` | "Comment remaining manual work on the lifecycle issue" step, posts `finalize-remaining.md` verbatim or `"No manual work remains."` | `[ -s finalize-remaining.md ] && [ -n "$(tr -d '[:space:]' < finalize-remaining.md)" ]` (existing condition, unchanged) | Non-empty: `kind: action`, `summary: "Complete the remaining manual work"`, `body-file: finalize-remaining.md`, `timing: "after this PR merges"`. Empty: `kind: info`, `summary: "No manual work remains."` |
| 7a | `finalize.yml` | `"⚠️ **Finalize anomaly**"` (empty-diff case) | Always `action` when reached | `kind: action`, `summary:` the existing anomaly text, no `pr-url` |
| 7b | `finalize.yml` | `"❌ **Finalize failed**"` (×2 sites) | Always `action` when reached | `kind: action`, `summary:` the existing failure text, no `pr-url` |
| 8 | `implement.yml` | "Report stalled on lifecycle issue" — banner + reason + collapsible transcript + restart runbook | Always `action` when reached (this job only runs on exhausted retries) | `kind: action`, `summary: "Restart the implement stage"`, `body-file:` the existing assembled `/tmp/stall-comment.md` content (banner/reason/transcript/runbook unchanged), no `pr-url` |
| 9 | `rebase.yml` | Blocked-escalation comment with `<!-- wing-commander-rebase: blocked ... -->` dedup marker | Always `action` when reached (skip-if-unchanged dedup already gates whether this step runs at all) | `kind: action`, `summary: "Manually rebase this branch"`, `body-file:` existing comment content including the unchanged dedup marker, no `pr-url` |
| 10 | `cleanup.yml` | `"🚫 **Draft rejected**"` teardown-rejected comment | Always `action` when reached | `kind: action`, `summary: "Decide whether to revise and resubmit"`, `body-file` or `body:` existing rejection text, no `pr-url` (the draft PR is already closed) |
| 11 | `intake.yml` | *(none before specs/029-intake-issue-comments)* — new "Post excluded-comments notice" step, posted before the agent step runs | `qualifying-count == 0 AND excluded-human-count > 0` (specs/029-intake-issue-comments/contracts/notice-callout.md) | `kind: action`, `summary: "Confirm the issue body reflects the discussion before relying on this spec"`, `body:` fixed text interpolating only the integer `excluded-human-count` (never a commenter's name or comment content), no `pr-url` |

**Contract clauses**:

- Every row's `summary` MUST be a plain-language statement of the action, not
  a status label — e.g. `"Review the implementation PR"`, not `"PR opened"`
  (FR-001).
- Rows 1 and 4 MUST use the identical `pr-label` value (`"the spec PR"`) and
  row 5 MUST use `"the implementation PR"` — this is what makes both review
  gates read as "the same recognizable format" (Acceptance Scenario 2,
  FR-003).
- Row 5's callout MUST be posted only after `steps.verify-pr` confirms the
  final PR exists (not merely after `gh pr create` is attempted) — mirrors
  the existing ordering discipline `finalize.yml` already applies to its
  metadata commit (verify before writing anything else).
- Rows 3/4's deterministic grep MUST run against the *post-edit* `spec.md`
  (after the agent's step 3 edits), matching the same marker-presence check
  `intake.yml` already performs for rows 1/2 — one shared condition shape
  across both workflows.
- No row in this table changes an existing label mutation
  (`stage:review`, `stage:stalled`, `rebase:blocked`, label removal in
  `cleanup.yml`) — those stay exactly as they are today, in their own
  existing steps; `wing-commander-callout` only adds the comment.
- Sites explicitly **not** in this table (`plan.yml`'s gate-mode-fallback
  warning, all `watchdog.yml` comments, every purely informational
  stage-started/converged/summary comment) are unchanged by this feature
  (research.md scope decision) — grep-auditable after implementation via:
  `grep -rLn "wing-commander-callout" .github/workflows/{plan,tasks,watchdog}.yml`
  should list all three, confirming no unintended migration crept in.
