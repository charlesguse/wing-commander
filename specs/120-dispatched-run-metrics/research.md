# Research: Prompt Metrics Records for Pipeline-Dispatched Runs

No `[NEEDS CLARIFICATION]` markers remained in spec.md. The spec's own
"the plan MUST ..." items are resolved below; where the answer can only be
observed on a live run, the decision names the drill that settles it
(quickstart.md) and the fallback.

## R1 — Where the persisting job lives and what it `needs`

**Decision**: one new job, `persist-metrics`, in each of
`wing-commander-5-implement.yml` and `wing-commander-6-finalize.yml`, a
`uses: ./.github/workflows/metrics-persist.yml` call with
`needs: [<the stage call job>]` (`implement` / `finalize`; implement's also
`resolve-model`). The wrapper's stage job is a reusable-workflow call, so its
result is the result of the whole of implement.yml / finalize.yml
(`verify-image-prerequisites`, `fold-turn-implement`, the gate suite,
`implement`, `stalled`, `fold-turn-release`, ...). `needs: implement` therefore
covers every record-emitting job in the callee; no per-job enumeration is
needed or possible from the wrapper.

**Rationale**: constitution VII puts destination choice (branch, path, kill
switch) in the wrapper, and `wing-commander-metrics-persist.yml` already shows
the exact call shape. FR-002 forbids pasting persistence logic.

**Alternatives**: a job inside implement.yml/finalize.yml (rejected: stages own
no destination or `vars.*`, and it would sit inside the per-spec concurrency
chain); a workflow_run listener (rejected: the whole problem).

## R2 — Status gating (`review-step-gating`)

**Decision** (implement wrapper):
`if: always() && vars.WING_COMMANDER_METRICS_PAUSED != 'true' &&
needs.resolve-model.result == 'success' && needs.implement.result != 'skipped'`.
`resolve-model` is the wrapper's first job and emits no record; if it did not
succeed no stage job ever started, so a run cancelled while queued never
starts the persisting job (FR-002 third bullet, FR-011). `always()` rather
than `!cancelled()` because `!cancelled()` would skip exactly the
cancelled-mid-cycle runs that User Story 3 requires to persist. A `skipped`
stage result may still start it as a zero-record no-op; the gate excludes it
anyway to save the job-minute.

**Finalize** has no resolve job; its call result `cancelled` is ambiguous.
Decision: gate on a stage output that an early, record-free job in finalize.yml
publishes on success (`started`), because outputs of jobs that completed before
the cancellation remain readable from the call even when a later job is
cancelled. Spec FR-002 requires this readability to be shown first: drill D2
in quickstart.md proves it on a live cancelled run; the fallback if it does not
hold is `always() && needs.finalize.result != 'skipped'` with the persisting
stage's zero-record no-op (spec 043 FR-021) absorbing the queued-cancel case,
and the finalize wrapper then records that fallback as a measured exception to
FR-011 in its comment. Adding a `started` output is a new optional stage
output (compatible, VII).

## R3 — Reusing the stage in a cancelled run and tolerating its failure

Today's `metrics-persist.yml`: `verify-image-prerequisites` has an implicit
`success()`; `persist` is `!cancelled() && image != failure`; failures are fatal
by design. Two declared, optional `workflow_call` inputs, defaults preserving
today's behaviour for every existing caller and the sweep:

- `run-in-cancelled-run` (boolean, default `false`): when true the image check
  and `persist` use `always()` in place of the implicit/`!cancelled()` gate.
- `tolerate-failure` (boolean, default `false`): when true, both jobs set
  `continue-on-error: ${{ inputs.tolerate-failure }}` and `persist` gains a
  final `if: failure()` step emitting `::warning::` and a step-summary line
  naming the sweep as the backstop (FR-007).

A callee job's `continue-on-error` makes its result `success` to the caller, so
the persisting job never turns a green stage red as seen by the run conclusion.
Image-check coverage is included (FR-007 "its image check included").

**Alternative**: wrapper-level `continue-on-error` — impossible on a `uses:`
job (spec says so). Rejected a second reusable workflow: duplicates the stage.

## R4 — Credentials and concurrency

The persisting job passes `pipeline-repo-token`/registry secrets exactly as the
existing wrapper does and **no** `speckit-app-*` secrets. Permissions are the
set the workflow_run path's job holds (`contents: write, issues: write,
actions: read, id-token: write`); the wrapper's `actions: write` is on the stage
job only. No `concurrency:` key on the new job.

**The `stalled` exception (spec edge case)**: `needs: implement` also waits for
`stalled`, which is in the per-spec group and can queue behind the next cycle
the failed stage already dispatched. The wrapper cannot depend on a callee job
selectively. Decision: state it as a measured exception to SC-001, not a
design goal: it requires a stage-job failure *after* the next-cycle dispatch,
the sweep is the backstop, and FR-006's label covers the window. The
measurement is taken in the post-merge proof (quickstart.md, P3).

## R5 — Artifacts and job ids of an in-progress run

Assumption (spec): artifacts uploaded by finished jobs are listable while the
run is in progress, and job ids resolve from the jobs listing. The composite
reads `jobs.json` and `actions/runs/<id>/artifacts`; both are available mid-run
(the job list includes the running persisting job, which has no artifact and is
ignored by the `job_key` match). Verified for real by drill D1. The one record
class at risk is the final step of the *stage's own* last job if it uploads
after `needs` completes — impossible, `needs` waits for job end.

## R6 — Re-run key stability

`record_key` is rewritten at persist time to `run_id:job_id:step_index` using
the id from the *current* jobs listing (action.yml ~L336-343). A re-run (or
re-run of failed jobs) allocates new job ids for the re-run jobs, so a record
persisted on attempt 1 and the same job's record re-derived on attempt 2 may
differ — a duplicate. Decision: this is verified by a fixture-driven check
first (a task writes a failing test with two `jobs.json` snapshots, one per
attempt); if the keys differ, the fix is in the existing derivation
(e.g. key the id of the job's *first* attempt, or include `run_attempt` and
de-dup on `run_id:job_key:step_index`), in the composite, per FR-004 — never a
workaround in the persisting job. This is the highest-risk item; it is
sequenced before the wrapper edits.

## R7 — In-progress readers of the implement run (FR-002/SC-003)

Longer-lived runs affect readers of in-progress implement runs. Found by
search of references to the implement wrapper: `wing-commander-9-pr-conversation.yml`
(the `stop` procedure that cancels the in-progress run),
`lifecycle-review-gate.yml`, `fold-cycle-guard.yml` /
`wing-commander-9b-fold-cycle-guard.yml`, `.github/actions/wing-commander-fold-dispatch`,
`board-loop.yml` (stand-down / head refs), `auto-release.yml`. Each is
audited in a task and recorded in data-model.md "Readers". Expected findings:
a `stop` landing during the persisting job cancels it (records left to the
sweep, FR-006); fold-dispatch/queue keyed on the stage's concurrency group is
unaffected because the persisting job is outside it; the guard's
never-started classification is addressed by R2. Any reader that treats
"implement run in progress" as "stage busy" is fixed or listed with proof it is
unchanged. Not resolved by reading alone; the audit is task work with a
checked-in table.

## R8 — FR-006 rollup label

The rollup renderer (composite, ~L542-600) appends one line: "Last daily sweep:
<high_water_mark from sweep-state.json on the destination branch, or 'unknown'>;
runs completed since then may be missing (sweep-only run kinds, and runs whose
persisting job failed or never ran)." Single home: the composite; no wrapper
copy. Gate 47 pointer rules apply if prose repeats.

## R9 — Gate

**Decision**: extend Gate 79 (`verify-metrics-wrapper-trigger-drops-watchdog.py`;
it already owns the metrics wrapper's record-owner and trigger/sweep shape) with
a "persisting job" section and fixtures for each failure branch (VIII): missing
job in either wrapper; gating that excludes `failure` or mid-run `cancelled`
(textual check of the status function: `always()` present, no bare `success()`
/ `!cancelled()` alone); missing `needs` on the stage job; job not calling
`metrics-persist.yml`; any `speckit-app-*`/`APP_TOKEN` secret handed to it; a
`concurrency:` key; both new stage inputs present with `false` defaults in
`metrics-persist.yml`. Also: an existing-caller check that the sweep and
workflow_run jobs pass neither input. A "single home" assertion: no discovery
/ append / rollup shell appears in the two wrappers.

Rejected a new gate: spec directs extension of an existing one and Gate 79
already holds the same subject file.

## R10 — Contract updates (live, done in implement)

- `specs/058-per-job-minute-floor/contracts/metrics-persist-sweep-delta.md`:
  implement/finalize completion-triggered path restated per FR-008.
- `specs/043-durable-metrics-record/contracts/persist-workflow.md`: "runs only
  after the origin run has concluded" amended; new inputs documented.
- `specs/043-durable-metrics-record/contracts/wrapper-contract.md`: persisting
  job in the wrapper contract.
- docs: `docs/` page describing the trigger model, if one states it (task
  greps).

## Decisions made without clarification

- Finalize's started-signal approach and its fallback (R2).
- Re-run key stability handled as test-first, fix-in-derivation (R6).
- `stalled` queueing recorded as a measured SC-001 exception (R4).
- Extending Gate 79 rather than adding a gate (R9).
