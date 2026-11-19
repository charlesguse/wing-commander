# Data Model: Prompt Metrics Records for Pipeline-Dispatched Runs

No new persisted schema. The record schema (spec 043
`contracts/metrics-record-schema.md`) and `records.jsonl` are unchanged; the
only data-shaped changes are two stage inputs, one stage output and one
rollup line.

## Entities

### Metrics record (unchanged)
Identified by `run.record_key = <workflow_run_id>:<job_id>:<step_index>`
(`job_id` resolved at persist time from the jobs listing; emission-time form
`run_id:job_key:step_index` when unresolved). Idempotence key for FR-004. Open
risk R6: stability of `job_id` across re-run attempts.

### Persisting job (new, workflow construct)
| Field | Value |
|---|---|
| Location | `wing-commander-5-implement.yml`, `wing-commander-6-finalize.yml` |
| Calls | `./.github/workflows/metrics-persist.yml` |
| `needs` | stage call job (implement also `resolve-model`) |
| `if` | `always()` + kill switch + started-signal + stage result != skipped |
| `run-id` | `github.run_id` (its own run) |
| Secrets | `pipeline-repo-token`, registry creds only; no App secrets |
| Concurrency | none |
| Stage inputs | `run-in-cancelled-run: true`, `tolerate-failure: true` |

### Stage input / output deltas (published surface, VII)
| Name | Kind | Type | Default | Effect |
|---|---|---|---|---|
| `run-in-cancelled-run` | input | boolean | `false` | `persist` gates on `always()`; the image check keeps its Gate 22-pinned `if` and is skipped in a cancelled run |
| `tolerate-failure` | input | boolean | `false` | `continue-on-error` on both jobs; warning step on failure |
| `started` (finalize.yml) | output | string | n/a | `'true'` once an early record-free job ran (R2); only if the drill requires it |

All additive and optional; existing callers (workflow_run job, sweep job,
adopters) unchanged.

### Rollup comment (one line added)
"Last daily sweep: `<high_water_mark | unknown>` — runs completed since then may
be missing from the total." Source: `sweep-state.json` on the destination branch.

### Readers of an in-progress implement run (audit table, R7)
| Reader | Behaviour with a longer-lived run | Disposition |
|---|---|---|
| pr-conversation `stop` | may cancel during persisting job | records to sweep; label covers |
| fold-cycle guard | classifies cancellations by started jobs | persisting job gated off when nothing started (R2) |
| fold-dispatch / fold queue | keyed on the stage concurrency group | unaffected (job outside group) |
| lifecycle-review-gate | dispatches the implement wrapper by file name (`implement-workflow: wing-commander-5-implement.yml`, L1428-1442); does not read the run's duration | unaffected; the added job runs after `implement`, outside the stage's concurrency group |
| `wing-commander-9b-fold-cycle-guard.yml` / `fold-cycle-guard.yml` | reacts to the implement run's `workflow_run` completion (9b L13) and dispatches by file name (L255) | unaffected in kind: completion now follows the persisting job, a bounded delay (the job is tolerant, FR-007); a cancelled-before-start run gates the job off (R2) |
| `wing-commander-fold-dispatch` | dispatches the wrapper with `fold_queue_token` (action.yml L242) | unaffected; keyed on the dispatch, not the run's end |
| `board-loop.yml` | no reference to the implement wrapper in the audit grep | no dependency found |
| `auto-release.yml` | maps the wrapper file to its stage (L1144); reads no run status of an in-progress implement run | no dependency found |

Proof limit: this audit is a read of the referencing lines (grep of each
reader for the wrapper's name), not a live run; the post-merge drills
(T024, T025) are what prove the delayed `completed` event is harmless.

## State transitions

Persisting job per run: `skipped` (paused / nothing started / stage skipped) →
`running` → `success` (persisted N ≥ 0 records; N=0 is the FR-021 no-op) or
`success` with warning (tolerated failure; sweep backstop). It never yields a
failed run conclusion (FR-007).
