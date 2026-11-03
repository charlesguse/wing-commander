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
| `run-in-cancelled-run` | input | boolean | `false` | image check and `persist` gate on `always()` |
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
| lifecycle-review-gate, board-loop, auto-release | read run status/head refs | audited in tasks; table completed there |

## State transitions

Persisting job per run: `skipped` (paused / nothing started / stage skipped) →
`running` → `success` (persisted N ≥ 0 records; N=0 is the FR-021 no-op) or
`success` with warning (tolerated failure; sweep backstop). It never yields a
failed run conclusion (FR-007).
