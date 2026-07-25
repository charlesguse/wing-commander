# Phase 0 Research: A Closed Lifecycle Is Inert

spec.md carries no literal `[NEEDS CLARIFICATION]` markers — the three that
existed during `/speckit-clarify` were already resolved on issue #109
(checklists/requirements.md Notes). Phase 0 research below is about the
*technical* unknowns planning still had to resolve: which entry points in
the actual codebase FR-004's named list corresponds to, where to insert the
gate so it is genuinely "before any command can run," and what the watchdog
collector can actually source a denial count from today.

## R1 — Mapping FR-004's named entry points onto the real codebase

**Decision**: Enumerate what actually exists rather than assume FR-004's
prose maps one-to-one onto distinct raw comment/label triggers. A repo-wide
audit (`grep -rn "issue_comment"` and every workflow's `on:` block) finds:

| FR-004 name | Real entry point | Trigger shape |
|---|---|---|
| "the clarify stage" | `wing-commander-2-clarify.yml` → `clarify.yml` | `issue_comment: [created]` — real comment trigger |
| "intake's `labeled` trigger" | `wing-commander-1-intake.yml` → `intake.yml` | `issues: [labeled]` — real label trigger |
| "the tasks-approval trigger" | `wing-commander-4-tasks.yml`'s `tasks-approved` job → `tasks.yml` | `pull_request: [closed]` (merged `tasks/**` PR) — a PR-merge hand-off, not a raw comment/label event, but named explicitly by FR-004 |
| "the finalize... comment path" | `wing-commander-6-finalize.yml` → `finalize.yml` | `workflow_dispatch` only, dispatched internally by `implement.yml` — **no comment trigger exists** |
| "...and converge comment paths" | `implement.yml`'s self-dispatch loop | `workflow_call`/`workflow_dispatch` chain — **no comment trigger exists** |

`claude.yml` also declares `issue_comment` but is fully disabled
(`if: false`) — dead code, not a real entry point, excluded from scope.
`wing-commander-3-plan.yml` and `wing-commander-7-cleanup.yml` are also
`pull_request: [closed]`-triggered but are **not named by FR-004** and are
not comment/label events either; `cleanup.yml` is specifically the
pipeline's own teardown mechanism (it is *how* the issue gets closed) and
must keep running on a closing PR merge regardless of the resulting issue
state, so it is explicitly out of scope, not merely unaudited.

**Rationale**: FR-004 says "at minimum this covers" the five named items,
then separately requires auditing "any other comment-/label-triggered
wrapper." Read literally, "tasks-approval" and "finalize/converge" are
explicitly in scope by name even though two of them are not comment/label
events at all — the spec's intent (Overview, US2) is that no ordinary
GitHub activity advancing a lifecycle should act on a closed issue, and a PR
merge or a chained dispatch that only happens *because* an earlier
comment/label advanced the lifecycle is exactly that kind of activity. This
plan treats FR-004's five named items as authoritative regardless of their
underlying GitHub event shape, and treats the "audit every other wrapper"
clause as scoped to true comment/label triggers only (which the audit above
shows are already fully covered by the two that exist). `wing-commander-3-
plan.yml`'s PR-merge trigger is a structurally identical case to
tasks-approval that FR-004 does not name; it is left out of this feature's
scope as a documented boundary, not an oversight — see R2.

**Alternatives considered**:
- *Refuse to plan until the spec is corrected to match the code* — rejected
  per this run's standing instruction to make a documented decision and
  continue rather than block, and because FR-004's intent is clear even
  where its event-shape description isn't literally accurate.
- *Gate only the two entry points that are literally comment/label events*
  — rejected: it would silently narrow FR-004's explicit "at minimum"
  list, leaving the tasks-approval hand-off (a real, if PR-merge-shaped, way
  a closed lifecycle could still be advanced) ungated.

## R2 — Scope boundary: `wing-commander-3-plan.yml`'s PR-merge trigger

**Decision**: Out of scope for this feature. Its `pull_request: [closed]`
trigger (merged `spec-draft/**` or `plan/**` PR) is structurally identical
to tasks-approval's, but FR-004 does not name it, and FR-004's audit clause
is textually scoped to "comment-/label-triggered wrapper," not
PR-merge-triggered ones. Flagged here as a candidate for the same gate
pattern if a future spec extends this feature's scope to PR-merge triggers
generally — the composite this plan adds (contracts/wing-commander-
lifecycle-gate.md) would apply to it with no redesign.

**Rationale**: Keeping scope to what FR-004 actually enumerates (R1) avoids
silently expanding an already-large, cross-cutting audit feature beyond what
was accepted. The risk profile is also lower: a merged plan PR's stage
advance touches the spec branch, not a torn-down draft branch, and does not
reproduce the reported zombie-run symptom (branch resurrection, closed-PR
edits) the way tasks-approval's dispatch-and-comment step could.

## R3 — Where the gate must run: extending the "event-agnostic reusable workflow" pattern, not `wing-commander-preflight`

**Decision**: Add one new composite, `wing-commander-lifecycle-gate`
(contracts/wing-commander-lifecycle-gate.md), called as the first billable
step of each affected reusable workflow's job — immediately after
"Checkout pipeline repository" and before `wing-commander-preflight` — using
a fresh `gh issue view "$ISSUE" --json state` call, never the calling
event's cached payload. Every step from `wing-commander-preflight` onward
gets `if: steps.lifecycle-gate.outputs.is-open == 'true'` (ANDed with any
existing `if:`); when closed, the job instead calls the existing
`wing-commander-callout` composite once with `kind: info` (FR-012) and ends.

Two design choices this decision makes, both already precedented in this
codebase:

1. **Re-fetch state, don't trust the wrapper's event payload.** `clarify.yml`
   already documents itself as event-agnostic (research.md D2 in that
   stage's own history — see "Fetch issue labels" fetching labels itself
   rather than trusting `github.event.issue.labels`) precisely so a reusable
   workflow's behavior does not depend on which event shape called it. The
   same reasoning applies to state: `tasks-approved` and `finalize`/
   `implement` have no `issue_comment`/`issues.labeled` payload to read
   `.issue.state` from at all, so a uniform "always re-fetch via API"
   design is the only one that covers every entry point with one composite,
   and it also correctly handles the "race at close time" edge case (the
   gate reads state at the moment it runs, not at whatever moment the
   original webhook fired).
2. **Do not fold this into `wing-commander-preflight`.** That composite's
   own header states it is deliberately "Pure shell — no agent, **no
   network**" so it can never itself incur cost or a transient-failure
   surface. A `gh issue view` call is a network call; adding it there would
   violate that documented invariant for every one of preflight's existing
   callers, including entry points this feature does not touch. A sibling
   composite keeps `wing-commander-preflight`'s contract intact and keeps
   the new gate independently testable/removable.

**Placement per entry point**:

| Workflow | Gate step position | Why here |
|---|---|---|
| `clarify.yml`, `intake.yml`, `finalize.yml`, `implement.yml` | Immediately after "Checkout pipeline repository," before `wing-commander-preflight` | Each already declares `issue-number` as a direct required `workflow_call` input (verified: `clarify.yml` inputs, `intake.yml:17-20`, `finalize.yml:17-20`, `implement.yml:27-30`) — no lookup needed, so the gate can be the very first thing that runs |
| `tasks.yml` (`tasks-approved` job) | After "Checkout spec branch as wing-commander-bot," before "Verify stage and dispatch" | This job derives its issue number from `spec-meta.json` on the long-lived `spec/<slug>` branch (`jq -r '.issue' "$SPEC_DIR/spec-meta.json"`, `tasks.yml:751`) — it is not a `workflow_call` input here, so it isn't known until that branch is checked out. Checking out an *existing, already-long-lived* branch is not itself the resurrection risk the spec is concerned with (FR-003's forbidden writes are branch **creation/re-push**, commit, push, PR edit, and actionable comment); the write this job can produce — `gh workflow run` dispatch plus an issue comment — happens only in "Verify stage and dispatch," which is exactly where the gate is inserted, so no forbidden side effect can occur before it runs |

**Rationale**: This keeps the change mechanical and repeatable — one new
step plus `if:` guards, no reordering of existing steps' secrets/tokens,
and it satisfies FR-002 ("before any agent is launched and before any
command can run") under the reading that "any command" means any command
capable of a write or of starting the agent step; the gate step's own
read-only `gh issue view` call is, like `wing-commander-preflight`'s own
checks, deliberately allowed to run first since it produces no side effect.

**Alternatives considered**:
- *Wrapper-level `if:` addition* (e.g. `&& github.event.issue.state ==
  'open'` on `wing-commander-2-clarify.yml`'s existing gate) — considered
  for clarify/intake since their raw events do carry `.issue.state`
  cheaply. Rejected as the *only* mechanism: it cannot cover
  `tasks-approved` (a `pull_request` payload has no `.issue` at all) or
  `finalize`/`implement` (`workflow_dispatch`/`workflow_call`, no event
  issue payload), and using the event's payload snapshot rather than a live
  re-fetch is weaker against the "race at close time" edge case than a
  fresh API read. One composite covering every entry point uniformly was
  chosen over two different mechanisms for the same requirement.
- *A single top-level `if:` on the whole job* — GitHub Actions has no
  "stop the rest of this job" primitive short of failing it (which would
  misreport a decline as an error) or conditioning every subsequent step
  individually. The per-step `if:` guard is the only faithful mechanism;
  it is mechanical and auditable (`contracts/lifecycle-gate-points.md`
  enumerates every gated step per workflow for the tasks stage to verify
  against).

## R4 — Watchdog collector: no `permission_denials` field exists to source from

**Decision**: Confirmed (Claude Code SDK/CLI documentation check) that the
terminal `{"type":"result", ...}` record emitted by `claude -p
--output-format json` carries no `permission_denials`-shaped field today —
only `num_turns`, `duration_ms`, `total_cost_usd`, `usage`, `modelUsage`,
`is_error`, `subtype`, `result`. This repository's own
`wing-commander-metrics-summary` composite, which already extracts fields
from this exact record, corroborates the same field list. FR-009's
"source from the terminal result record when present" branch therefore has
no live case to exercise today; the collector's **only** real path is
FR-009's fallback (log-scan), which this feature must make accurate and
must label as non-authoritative — not the record-sourced branch, which
this plan implements as forward-compatible but currently dead code (it
naturally becomes live if a future Claude Code SDK version adds such a
field, with no further change needed here).

The log-scan fix itself (`contracts/denied-tool-collector-delta.md`): the
current filter groups denial-shaped `tool_result` entries by tool name and
**drops any group of size 1** (`map(select(length > 1))`), which both
silently discards genuine single-tool denials and produces a `denials`
count (`length` of the surviving group) that is disconnected from the
actual number of individually-occurring denial events reported elsewhere.
The fix removes that grouping-based drop/count and instead counts every
denial-shaped `tool_result` entry directly, one `facts` entry per denial
occurrence (or per tool, with an accurate `denials` count that is the true
occurrence count, not a post-filter group length). The per-entry position
field, currently named `turn` and populated with `to_entries[] | .key` —
the zero-based index into the *raw interleaved SDK message array*, not a
conversation turn (a single turn commonly spans several array entries) — is
renamed to `record-index`, and the fallback output is explicitly labeled
non-authoritative (FR-009's third clause), so a reader can never again see
an impossible "turn" number exceeding the run's own `num_turns`.

**Rationale**: This is a documented decision made without further
clarification, consistent with this run's standing instruction: the
precise original root cause behind the "3 denials, turns 28/116/118 vs. 2
denials, 20 turns" report (issues #105/#106) cannot be re-derived from this
sandboxed planning session (no live `gh run view`/log access — same class
of constraint `specs/020-fix-watchdog/research.md` R3 already documents for
this environment), but the *defect* FR-008/009/010 describe — overcounting
via a grouping heuristic, and labeling array indexes as turns — is fully
visible and fixable from the checked-in `jq` filter alone (`watchdog.yml`
lines ~314-357), which is sufficient to design and implement the fix
without depending on that specific historical run remaining inspectable.

**Alternatives considered**:
- *Block until `gh run view` access to the original run is available* —
  rejected for the same reason `specs/020-fix-watchdog/` already rejected
  it: the fix is correct regardless of which exact array entries the
  original run contained, since it corrects the counting/labeling
  mechanism generally rather than patching one run's numbers.
- *Derive genuine turn numbers instead of renaming the field* — explicitly
  rejected by FR-010 itself ("Deriving and reporting genuine turn numbers
  is explicitly not required; the minimal, accurate-naming fix is the
  chosen approach") and by the maintainer's own Decision A on this
  question (checklists/requirements.md Notes).

## R5 — The orphaned `spec-draft/021-rebase-discover-stall` branch (FR-011)

**Decision**: The branch FR-011/SC-007 describe is
`origin/spec-draft/021-rebase-discover-stall` (tip `cffb04f "spec: resolve
clarifications from #102"`, parent `a85ac72`). `git merge-base
origin/main origin/spec-draft/021-rebase-discover-stall` returns no common
ancestor — a genuinely torn-down-then-resurrected history, sitting well
behind current `main`. Its `spec-meta.json` (read via `git show`) records
lifecycle issue **#102** (spec 021, "rebase discover stall"), not #105/#106
— those two issue numbers are the watchdog's own *finding* issues that
triggered this feature's post-mortem, not the lifecycle issue the zombie
run acted on; #102's lifecycle issue is the one whose closing comment
resurrected this branch. `specs/021-rebase-discover-stall/` does not exist
in the current tracked tree, confirming spec 021 was never merged and its
draft was already torn down by cleanup before the defect resurrected it.

**Remediation**: `git push origin --delete spec-draft/021-rebase-discover-
stall` (or the maintainer-facing equivalent) restores the state cleanup had
already established. This is **not performed by this plan** — deleting a
remote branch is a destructive, hard-to-reverse action outside what a plan
stage may do (it edits only files under `specs/022-gate-closed-lifecycle/`
and commits only to `spec/022-gate-closed-lifecycle`); it is recorded here
as a task for the implement stage (running with the App's write
credentials, as every branch-mutating stage already does) or for a
maintainer to perform directly, and is carried into tasks.md as an explicit
task rather than silently assumed done.

**Rationale**: Confirming the exact branch and its provenance before
tasks.md is generated avoids a vague "delete the orphaned branch" task that
a future implementer would have to re-investigate from scratch; the
investigation is done once, here, and the answer is unambiguous (only two
`spec-draft/*` refs exist on `origin` — this orphan and the current
in-flight `spec-draft/022-gate-closed-lifecycle`).

**Alternatives considered**: Deleting the branch during planning — rejected
per this session's explicit constraint against destructive/out-of-scope
git operations during the plan stage, and because branch deletion is more
naturally a task the implement stage executes and reports on the lifecycle
issue like any other automated step (constitution IV).
