# Contract: Lifecycle Gate Call Sites (FR-004 audit)

This is the per-entry-point migration/audit contract for spec 022 — every
comment-/label-/PR-merge-/dispatch-triggered entry point FR-004 covers, its
existing who/what gate, and the new `wing-commander-lifecycle-gate` call
site and downstream `if:` guards it needs. `contracts/wing-commander-
lifecycle-gate.md` defines the composite; this file defines *where* it is
invoked, in what job, and which existing steps must gain the
`is-open == 'true'` guard.

| # | Workflow (reusable) | Existing who/what gate (unchanged) | New gate step position | Steps that gain `if: is-open == 'true'` |
|---|---|---|---|---|
| 1 | `clarify.yml` | Wrapper `wing-commander-2-clarify.yml:22-27` — non-bot commenter is maintainer-or-author, issue carries `spec:`/`stage:spec`\|`stage:clarify` labels | Immediately after "Checkout pipeline repository," before "Preflight" | Preflight, Bedrock config, Fetch issue labels, Wing Commander context, Verify spec identity, Checkout draft spec branch as bot, React to comment, all remaining agent/commit/PR-edit/callout steps |
| 2 | `intake.yml` | Wrapper `wing-commander-1-intake.yml:20` — `spec-request` label present (maintainer-applied label is the gate) | Immediately after "Checkout pipeline repository," before "Preflight" | Preflight, Wing Commander context, Resolve default branch, Re-checkout default branch as bot, Allocate feature number, Report run started, Create spec from issue (agent step), and every step after it |
| 3 | `tasks.yml` (`tasks-approved` job) | `wing-commander-4-tasks.yml`'s `pull_request: closed` + `merged == true` + head-ref prefix check; `tasks.yml`'s own `if: inputs.mode == 'approved'` | After "Checkout spec branch as wing-commander-bot," before "Verify stage and dispatch implement stage" (issue number is only known once `spec-meta.json` is readable from that branch — research.md R3) | "Verify stage and dispatch implement stage" only (the sole write step in this job) |
| 4 | `finalize.yml` | Dispatched only by `implement.yml`'s own internal "Dispatch finalize stage" step — no external comment/label reaches it directly; gated here defensively per FR-004's explicit naming (research.md R1) | Immediately after "Checkout pipeline repository," before "Preflight" | Preflight and every step after it (diff summary, PR open, remaining-work comment, lifecycle-issue report) |
| 5 | `implement.yml` | Self-dispatching `workflow_call` chain (`self-workflow`/`next-workflow` inputs); no external comment/label — gated defensively per FR-004's naming (research.md R1) | Immediately after "Checkout pipeline repository," before "Preflight" | Preflight and every step after it (agent attempt, escalation retry, converge check, progress comment, next-cycle/finalize dispatch) |

**Contract clauses**:

- Every row's new gate step MUST run before any step capable of a write
  (branch checkout-as-bot, commit, push, PR edit, `gh workflow run`
  dispatch, or an `action`/agent-authored comment) and before any agent
  step (FR-002). Row 3 is the one case where the gate cannot also precede
  the read-only "checkout an existing long-lived branch" step, because the
  issue number is not known until that branch's `spec-meta.json` is read —
  this is documented, not an oversight (research.md R3's placement table).
- Row 1–2's who/what gate stays in the **wrapper** file exactly as it is
  today; only the new state gate moves into the **reusable workflow**,
  consistent with those workflows already being event-agnostic (fetching
  labels/issue data themselves rather than trusting the wrapper's event
  payload).
- No row changes an existing label mutation, an existing `kind: action`
  callout, or any agent prompt's content — the state gate only adds a new
  step and `if:` guards; it does not touch what happens on the *open*
  path (FR-006).
- Every row MUST use the identical decline note
  (`contracts/wing-commander-lifecycle-gate.md`'s `kind: info` template,
  `"This lifecycle issue is closed — no action was taken."`) — one
  recognizable format across every entry point, mirroring how
  `specs/019-next-step-callouts/` already unified the `action`-kind
  callouts.
- **Explicitly not in this table** (research.md R1/R2, scope boundaries):
  `wing-commander-3-plan.yml`'s PR-merge trigger (named nowhere in FR-004);
  `wing-commander-7-cleanup.yml` (the pipeline's own teardown mechanism —
  must keep running on a closing PR merge to actually close/torn-down the
  lifecycle in the first place); `claude.yml` (disabled, `if: false`, dead
  code). Grep-auditable after implementation:
  `grep -rLn "wing-commander-lifecycle-gate" .github/workflows/{plan,cleanup,claude}.yml`
  should list all three, confirming no unintended expansion crept in, and
  `grep -rln "wing-commander-lifecycle-gate" .github/workflows/{clarify,intake,tasks,finalize,implement}.yml`
  should list exactly those five, confirming SC-003 (zero ungated named
  entry points).
