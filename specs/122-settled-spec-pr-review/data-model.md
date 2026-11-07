# Data Model: Settled Spec PR Review

All entities are transient JSON passed between workflow steps and the
decision module, or are already stored on GitHub. No new persistent store.

## SpecPrSnapshot (input to selection/eligibility)

| Field | Source | Notes |
|---|---|---|
| `pr` | PR number | open, base `main` |
| `head_ref`, `head_repo` | PR | must start `spec-draft/` and be this repository (FR-001) |
| `head_sha`, `head_committed_at` | PR/commit | re-fetched before each write |
| `issues` | linked lifecycle issues | exactly one required |
| `stage_labels` | issue labels | `stage:spec` and not `stage:clarify` |
| `open_marker` | marker-scan result at head | boolean (FR-002b) |
| `announcements[]` | issue comments | `{author, created_at, body_marker_present}`; only App-authored count |
| `rounds[]` | App's own PR reviews | `{round, sha, verdict, record}` (spec 116 round records) |
| `failed_attempts[head_sha]` | issue notes | integer, FR-028 |
| `dispatch` | optional | `{actor_type, association}` (FR-027) |
| `pause` | variable | kill switch |

## Settledness (derived)

`settled = stage_ok ∧ ¬open_marker ∧ announced_by_app ∧ head_not_newer_than_announcement`, or, for a valid maintainer dispatch, `open ∧ spec-draft ∧ stage:spec ∧ ¬open_marker`.
Result: `{settled: bool, reason: <enum>}`.

## EligibilityDecision

`{eligible: bool, reason}` where reason ∈ `ok`, `paused`, `not-spec-pr`, `fork`, `no-issue`, `multiple-issues`, `unsettled:<why>`, `already-reviewed`, `budget-exhausted`, `convergence-stop`, `failed-cap`.

## Finding

Existing review-finding shape (title, what, evidence{file_paths, detail?}, fingerprint_basis) plus:

| Field | Values |
|---|---|
| `class` | `unambiguous-error` \| `owner-decision` |
| `precedent` | `{kind: default-branch\|head\|issue-comment, ref}` (required for unambiguous-error to be pushed) |
| `fix` | optional unified diff hunk set (spec-dir paths only) |
| `question` | for owner-decision: `{options[≥2], recommendation, precedent?}` |

## ReviewRound

`{round, head_sha, verdict ∈ {"ready for the owner","not ready"}, outcome ∈ {reviewed, failed, budget-exhausted, convergence-stop, stood-down}, findings[], fix_commits[], marker_push, label_moved, announcement_posted}`.
Verdict is `not ready` iff `findings` is non-empty (FR-013).

## ActionPlan (output of `plan_actions`)

`{push_fixes: bool, push_markers: bool, move_label: bool, post_announcement: bool, status: success|failure, issue_line, handoff?}` with the invariants:

- `move_label` only if `push_markers` succeeded (FR-015c).
- `post_announcement` only if all findings were unambiguous errors and every fix pushed (FR-015d).
- Nothing is pushed or relabelled on a stale or closed PR.

## State transitions

`stage:spec` --(owner decisions + markers pushed)--> `stage:clarify` --(clarify folds, announces)--> `stage:spec` (new head, new round). A pushed-fix-only round re-announces on its own head, so the next selection reviews it as a new round counting against the budget.
