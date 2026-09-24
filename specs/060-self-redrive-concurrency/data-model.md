# Data Model: The Proof Run Can Actually Start

This feature adds no persistent storage — every entity below is either a
value computed by `board_prove.py` from the checked-out tree and the
Actions API, or state that already lives on a GitHub issue (comments, the
`<!-- wing-commander-board-item: {...} -->` marker) or in a workflow run
(its `displayTitle`, `status`, `conclusion`). Fields marked **new** are
introduced by this feature; fields marked **existing** extend spec
057-autonomous-board-loop's data-model.md entities of the same name.

## Re-drive Target (extends spec 057)

| Field | Type | Source | Notes |
|---|---|---|---|
| `workflow` | string \| null | `redrive_target()` | existing: the workflow basename, or `null` |
| `reason` | string | `redrive_target()` | existing |
| `directed_stage` | string \| null | **new**: `directed_stage()` (research.md D1) | job name inside `workflow`, or `null` when `workflow` isn't `board-loop.yml`, or the change reaches no aimable job |
| `can_start` | bool | **new**: `joins_directed_group()` (D4, FR-001) | whether dispatching would join a group the caller already holds; determined statically, before dispatch |

## Directed Proof Run (new)

The run this feature's mechanism dispatches. Distinct from an ordinary
board-loop run in three structural ways, all enforced by construction
(D2/D3), not by an agent's restraint:

| Field | Type | Notes |
|---|---|---|
| `stage` | enum: `triage` \| `review` \| `readiness` \| `prove` | the aimable job it runs (research.md D2); never `select`/`route`/`fix` |
| `issue` | int | supplied via the `directed-issue` `workflow_dispatch` input, never chosen by `select()` |
| `pr` | int \| null | supplied via `directed-pr`; only set when `stage == "prove"` |
| `attempt_token` | string | unchanged correlation token, `${{ github.run_id }}-${{ github.run_attempt }}` of the *dispatching* run |
| `concurrency_group` | string | always `wing-commander-board-loop-directed-proof` (D3) |
| `selects_item` | bool (invariant: always `false`) | checked by D7's structural assertion, never merely asserted in prose |
| `opens_fix_pr` | bool (invariant: always `false`) | same |

## Job-Uses-Graph (new)

Per-job extension of spec 057/060's existing `uses_graph` (which maps a
*workflow* to what it references). Computed by `scan_job_uses_graph()`
(research.md D1), consumed only by `directed_stage()`.

| Field | Type | Notes |
|---|---|---|
| `job` | string | a job name inside `board-loop.yml` |
| `referenced` | set[string] | repo-relative paths the job's own steps reference — `.github/workflows/*.yml`, `.github/actions/**`, and (D5) resolved `.github/scripts/board_*.py` module imports, transitively closed over helper-imports-helper |

## Proof Record (extends spec 057)

Spec 057's fields (`actions_only`, `run_url`, `outcome`, `reason`) are
unchanged. This feature widens `outcome`'s enum and adds `outcome_reason`
(research.md D6):

| Field | Type | Notes |
|---|---|---|
| `actions_only` | bool | existing |
| `run_url` | string \| null | existing |
| `outcome` | enum: `success` \| `failure` \| `not_dispatched` \| `not_required` | existing (spec 057) |
| `outcome_reason` | **new** enum: `group-busy` \| `not-started` \| `unfinished` \| `displaced` \| `uncorrelated` \| `no-target` \| `nothing-reaches` \| `success` \| `failure` | the SC-003 taxonomy; every non-`success`/`failure` value implies `outcome == not_dispatched` and the issue stays open (FR-008) |
| `directed` | bool | **new**: whether this proof record came from a directed proof run (vs. today's whole-workflow re-drive of an external target, FR-004) |

## Proof-Group Occupancy Check (new, FR-001a)

Not stored — computed fresh before every dispatch attempt.

| Field | Type | Notes |
|---|---|---|
| `run_list_json` | JSON | `gh run list --workflow=board-loop.yml --json databaseId,displayTitle,status -L 20` |
| `busy` | bool | `directed_proof_group_busy(run_list_json)` (D4): any non-`completed` row whose `displayTitle` contains `[directed:` |

## Displaced-Prove Detection Record (new, FR-010b)

Computed by `board_prove_displacement.find_undetected_merges()` (research.md
D8), run as a step inside `select`.

| Field | Type | Notes |
|---|---|---|
| `issue` | int | an issue whose most recently merged, loop-labeled fix PR left no later `prove`/`proven` marker and no proof-outcome comment |
| `merged_pr` | int | the PR that should have triggered a `prove-gate`/`prove` run |
| `recorded_reason` | literal `"prove run displaced"` | distinct from every FR-006/FR-007 `outcome_reason` value (FR-010b) |

## Concurrency Guarantee (extends spec 057's FR-048 statement)

Not a data entity so much as the sentence FR-016/SC-006 require be
identical across three places — tracked here so each place can be diffed
against it:

| Location | What it must say |
|---|---|
| `board-loop.yml`'s per-job `concurrency:` comments (research.md D3) | one board item in flight repository-wide; a directed proof run, which takes no item, is the only run permitted to overlap |
| `specs/057-autonomous-board-loop/contracts/board-loop-workflow.md` "Concurrency" section (edited during implementation, research.md D9) | same sentence |
| `specs/060-self-redrive-concurrency/contracts/concurrency-groups.md` (this spec, below) | same sentence, canonical source the gate (SC-006) diffs the other two against |

## Configuration Constants (new)

| Name | Value | Home | Notes |
|---|---|---|---|
| `aimable_jobs` | `{"triage", "review", "readiness", "prove"}` | `board_prove.py` | research.md D2; read by the new gate (D7) rather than restated |
| `wing-commander-board-loop-directed-proof` | concurrency group literal | `board-loop.yml` per-job `concurrency:` blocks | research.md D3 |
