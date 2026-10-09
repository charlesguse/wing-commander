# Data Model: The Prove Entry Survives a Displaced Queue Slot

This feature adds no persistent storage — every entity below is either a
value computed by a `.github/scripts/board_*.py` module from the
checked-out tree and the Actions/Issues API, or state that already lives
on a GitHub issue (comments, the
`<!-- wing-commander-board-item: {...} -->` marker) or in a workflow run
(its `displayTitle`, `status`, `conclusion`). Fields marked **new** are
introduced by this feature; fields marked **existing** extend
specs/057-autonomous-board-loop's and specs/060-self-redrive-concurrency's
data-model.md entities of the same name.

## Board Item Marker (extends specs/057, specs/060)

| Field | Type | Source | Notes |
|---|---|---|---|
| `step` | string | existing | unchanged vocabulary (`board_eligibility.py`'s step sets); `"prove"` is pre-existing, not introduced here |
| `round` | int | existing | unchanged |
| `pr` | int \| null | existing | unchanged; a `"prove"`-step marker still carries `null` (research.md D3: the PR is re-derived live, never read off the marker, FR-010) |
| `branch` | string \| null | existing | unchanged |
| `base_sha` | string \| null | existing | unchanged |
| `outcome_reason` | string \| null | **new** (research.md D4) | either `board_prove_displacement.RECORDED_REASON` ("prove run displaced"), one of `board_prove.OUTCOME_REASONS`, or `null` on any marker written before this feature or by a non-prove step |
| `recovery_attempted` | bool | **new** (research.md D4) | `true` once a `gh workflow run` dispatch for this item's recovery has been made (FR-011a); a dispatch skipped for `group-busy` MUST NOT set this |

## Recoverable Item (new, FR-011/FR-011a/FR-011b)

Computed fresh every `select` run by `board_prove_recovery.find_recoverable_items()`
(research.md D3/D5); never stored beyond the marker fields above.

| Field | Type | Source | Notes |
|---|---|---|---|
| `issue` | int | `board-recent-merges-by-issue.json` (displacement step's own fetch, reused) | must also be in this run's open-issues list |
| `merged_pr` | int | same | the PR whose merge left this issue unproven |
| `marker_created_at` | string (ISO 8601) | `board_item_marker.read_marker_with_timestamp()` | tie-break key, oldest first (FR-011b fairness) |
| `outcome_reason` | string | the issue's own marker | one of the two recoverable literals only — `is_recoverable()` (research.md D5) excludes every other value including `null` |

## Recovery Dispatch (new, FR-011/FR-002)

The `workflow_dispatch` this feature's recovery step performs. Distinct
from an ordinary directed proof run (specs/060 "Directed Proof Run" entity)
in exactly one field; every other property (selects no board item, opens
no fix PR, joins `wing-commander-board-loop-directed-proof`) is inherited
unchanged because it *is* a directed proof run of `stage == "prove"`.

| Field | Type | Notes |
|---|---|---|
| `stage` | literal `"prove"` | never another aimable job — recovery only ever recovers a proof |
| `issue` | int | the recoverable item's issue |
| `pr` | int | the recoverable item's merged PR |
| `recovery` | bool (**new** `directed-recovery` input, research.md D6) | `true`; the one field distinguishing this from any other directed `prove` dispatch (e.g., the pre-existing self-redrive-of-the-prove-step-itself case) |
| `group_busy_checked` | bool | `board_prove.directed_proof_group_busy()` was called and returned `false` before this dispatch was made |

## Prove-Path Concurrency Group (extends specs/060 "Concurrency group")

| Field | Type | Notes |
|---|---|---|
| `ordinary_group` (directed branch, unchanged) | string | `wing-commander-board-loop-directed-proof` |
| `ordinary_group` (`pull_request` branch, **changed**, research.md D1) | string, templated | `wing-commander-board-loop-prove-{github.event.pull_request.number}` — was the shared `wing-commander-board-loop` |
| `key_source` | GitHub Actions context expression | `github.event.pull_request.number`, available directly in a job-level `concurrency.group:` expression on this event, no pre-step needed |

## Concurrency Guarantee (extends specs/060's same-named entity)

Not a data entity so much as the sentence FR-016/FR-005 require be
identical across three places — tracked here so implementation can diff
each place against it (research.md D2 states the new text in full).

| Location | Edited by |
|---|---|
| `board-loop.yml`'s 8 per-job `concurrency:` comments | this feature, implementation (FR-005) |
| `specs/057-autonomous-board-loop/contracts/board-loop-workflow.md` "Concurrency" section | this feature, implementation (FR-005, research.md D9) |
| `specs/060-self-redrive-concurrency/contracts/concurrency-groups.md` "## The guarantee" (canonical source Gate 101 diffs the other two against) | this feature, implementation (FR-005, research.md D9) |

## Resume Step Resolution (extends specs/057's "Board Item Marker" resolution chain)

| Marker shape | `pr_state` | Resolved `step` (existing/changed) |
|---|---|---|
| `awaiting-merge` (or any `FIX_OR_LATER_STEPS`) with a resolvable `pr` | `OPEN` | unchanged: stays `marker_step` (clause 5) |
| `awaiting-merge` (or any `FIX_OR_LATER_STEPS`) with a resolvable `pr` | `MERGED` | **changed** (research.md D7): `prove`, fields cleared — was `triage`, fields cleared |
| `awaiting-merge` (or any `FIX_OR_LATER_STEPS`) with a resolvable `pr` | `CLOSED` (unmerged) | unchanged: `triage`, fields cleared (FR-008) |
| `awaiting-merge` with an unresolvable `pr` | n/a | unchanged: held via `_awaiting_merge_holds()`'s fail-safe (FR-008) |
| `prove` with no `pr` field | n/a | unchanged: stays `prove` (clause 1) |

## Configuration Constants (new)

| Name | Value | Home | Notes |
|---|---|---|---|
| `RECOVERY_DIRECTED_INPUT` | `"directed-recovery"` | `board_prove_recovery.py` | research.md D5/D6 — the one spelling of the new `workflow_dispatch` input name |
| `wing-commander-board-loop-prove-{N}` | concurrency group template | `board-loop.yml` `prove-gate`/`prove` `concurrency:` blocks | research.md D1 |
