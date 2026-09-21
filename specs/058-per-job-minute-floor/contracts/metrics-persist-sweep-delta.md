# Contract Delta: Metrics Persistence — Sweep Mode and the Dropped Watchdog Trigger

This is a delta against `specs/043-durable-metrics-record/contracts/
persist-workflow.md` (the published `metrics-persist.yml` stage) and
`specs/043-durable-metrics-record/contracts/wrapper-contract.md` (the
consuming `wing-commander-metrics-persist.yml` wrapper). Both remain the
base contract for the discover→retrieve→validate→append-with-retry
pipeline, the `record_key` idempotence scheme, and the isolation
guarantees (FR-015/019/019a of spec 043) — none of that changes here.

## `metrics-persist.yml` — new optional `since` input

**Current contract**: `run-id` (string, required) names the single run
to collect. `destination-branch`/`destination-path` (both required, no
default — spec 043 FR-013).

**Amended contract**: a new optional input, `since` (string, ISO-8601
timestamp, default `''`). When empty, behavior is unchanged — process
`run-id` alone. When set, the stage instead lists every run concluded at
or after `since` minus a one-hour overlap (research.md R-C3), and runs
the existing pipeline once per discovered run, batching every record
into one append-with-retry commit (research.md R-C1) rather than one
push per run. `run-id` is ignored when `since` is set. This is additive
and non-breaking per `contracts/versioning.md`.

## `metrics-persist.yml` — two new durable files on the destination branch, sweep runs only

**Current contract**: the destination branch holds exactly one file,
`records.jsonl`.

**Amended contract**: a sweep-mode run (non-empty `since`) also
maintains, in the same commit as any `records.jsonl` append:

- `sweep-state.json` — `{"high_water_mark": "<ISO-8601>"}`, the latest
  concluded-run timestamp the last sweep fully accounted for (research.md
  R-C2). Read by the next sweep to compute its own `since`.
- `unpersisted.jsonl` — one line per discovered run whose metrics
  artifacts had already expired before the sweep reached them:
  `{"run_id", "workflow", "reason": "artifact_expired",
  "discovered_at"}` (FR-028, research.md R-C4). The high-water mark
  still advances past such a run — it is accounted for, not retried.

A completion-triggered run (empty `since`, the unchanged nine-stage
path) writes neither file.

## Wrapper — sweep trigger added, watchdog removed from the completion trigger

**Current contract**:
```yaml
on:
  workflow_run:
    workflows:
      - "Wing Commander · 1 intake"
      - "Wing Commander · 2 clarify"
      - "Wing Commander · 3 plan"
      - "Wing Commander · 4 tasks"
      - "Wing Commander · 5 implement"
      - "Wing Commander · 6 finalize"
      - "Wing Commander · 7 cleanup"
      - "Wing Commander · rebase"
      - "Wing Commander · 8 watchdog"
      - "Wing Commander · 9 pr conversation"
    types: [completed]
  workflow_dispatch:
    inputs:
      run-id: { required: true }
```

**Amended contract**:
```yaml
on:
  workflow_run:
    workflows:
      - "Wing Commander · 1 intake"
      - "Wing Commander · 2 clarify"
      - "Wing Commander · 3 plan"
      - "Wing Commander · 4 tasks"
      - "Wing Commander · 5 implement"
      - "Wing Commander · 6 finalize"
      - "Wing Commander · 7 cleanup"
      - "Wing Commander · rebase"
      - "Wing Commander · 9 pr conversation"
      # "Wing Commander · 8 watchdog" REMOVED (FR-030(b)) — after FR-031
      # a healthy inspection emits no record, and a signal-bearing one
      # is reached by the sweep below, not this trigger.
    types: [completed]
  schedule:
    - cron: "37 6 * * *"   # daily sweep (FR-030(c)); minute/hour chosen
                            # only to avoid colliding with this repo's
                            # other scheduled wrappers (research.md R-C6)
  workflow_dispatch:
    inputs:
      run-id:
        description: "An already-concluded workflow run to collect metrics for"
        required: false
      since:
        description: "ISO-8601 timestamp — sweep mode; overrides run-id when set"
        required: false
```

`persist`'s existing job is unchanged for the `workflow_run`/manual
single-run `workflow_dispatch` path. A new `sweep` job, gated
`if: github.event_name == 'schedule' || (github.event_name ==
'workflow_dispatch' && inputs.since != '')`, calls the same
`metrics-persist.yml` with `since: ${{ inputs.since ||
<computed-high-water-mark-minus-overlap> }}` — the wrapper reads
`sweep-state.json` itself (a plain `git show`/`gh api` read, no checkout
of the pipeline repo needed for this one field) to compute the default
when `schedule:` fired with no explicit `since`. No `concurrency:` group
gates either job against the other (FR-030(d), research.md R-C7,
explicit non-decision).

## What does not change

- `record_key` derivation and idempotence (spec 043).
- The append-with-retry contention loop's bound (8 attempts) and
  backoff shape — reused, not re-typed, for the batched sweep commit.
- The hand-driven single-run re-drive (`run-id` on `workflow_dispatch`) —
  preserved, and safe to use while a sweep is in flight (FR-024,
  idempotence is the only safety mechanism needed, unchanged).
- Isolation guarantees: no branch but the destination is ever touched;
  a persistence failure fails only itself (FR-025, unchanged).
- Persistence stays a separate workflow from the watchdog run it may
  collect from (FR-026, unchanged — sweep mode does not fold persistence
  into `watchdog.yml`).

## Versioning

Additive and non-breaking: `since` is a new optional stage input; the
wrapper's trigger surface (a consuming-instrument file, not part of the
adopter-pinned published contract per constitution VII) gains a
`schedule:` entry and loses one `workflow_run` list item — an adopter
who forked this wrapper chooses independently whether to make the same
change. Per `contracts/versioning.md`, the stage-side `since` input
ships as part of this feature's overall minor release.
