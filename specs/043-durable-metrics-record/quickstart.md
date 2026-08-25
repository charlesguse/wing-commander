# Quickstart: Validating Durable Agent Run Metrics

Prerequisites: a checkout of this repository with the feature branch's
changes, `gh` authenticated against a test repository (or this one, with
write access), `jq`, `git`. All scenarios below are the Independent
Tests from spec.md's five user stories, made runnable.

## Story 1 — Emission produces a record alongside the transcript

1. Trigger any stage that invokes `wing-commander-metrics-summary` (e.g.
   push a no-op commit to a `spec-draft/*` branch to trigger `intake`, or
   `gh workflow run` a stage directly with `workflow_dispatch` if it
   supports manual dispatch for testing).
2. After the run completes, `gh run download <run-id> -p 'metrics-record*'`.
3. `jq . <downloaded-file>` and confirm the shape matches
   contracts/metrics-record-schema.md — `schema_version: 1`, every field
   listed there present, `per_model` has at least one entry.
4. Compare the record's `cost_usd`/`turns.counted`/`model` against the
   same run's `$GITHUB_STEP_SUMMARY` table — they must be numerically
   identical (FR-004).
5. Re-run the same stage with a deliberately corrupted transcript
   (contracts/metrics-record-schema.md's "Degraded record" fixture, or
   drive `verify-metrics-record-schema`'s fixture harness locally) and
   confirm the step still succeeds and the record's
   `record_available`/`*_available` fields are all `false`.

## Story 2 — The record outlives the artifact

1. Configure `WING_COMMANDER_METRICS_BRANCH`/`_PATH` repository variables
   (or accept the wrapper's defaults, `metrics`/`records.jsonl`).
2. Trigger 2-3 concurrent pipeline runs (e.g. push to two different spec
   branches at once, or manually dispatch the same stage twice back to
   back).
3. Once each concludes, either wait for `wing-commander-metrics-persist.yml`'s
   `workflow_run` trigger or dispatch it manually with each run's id
   (`gh workflow run wing-commander-metrics-persist.yml -f run-id=<id>`).
4. `git fetch origin metrics && git show origin/metrics:records.jsonl | wc -l`
   — confirm one line per agent run across all triggered runs, with no
   line lost (compare `record_key`s against what each run's own artifact
   listed).
5. Confirm no other branch changed:
   `git log --oneline main..origin/metrics` should show only
   metrics-branch-local history (the orphan root plus append commits),
   and `git status` on any spec branch untouched by this exercise shows
   no unexpected commits.
6. Re-dispatch `wing-commander-metrics-persist.yml` a second time for the
   same `run-id` and confirm `records.jsonl`'s line count is unchanged
   (FR-018 idempotency).
7. To exercise contention directly rather than by chance: run
   `verify-metrics-persist-retry`'s local-git-fixture harness
   (contracts/gate-coverage-043.md) — it races two writers against one
   bare repo and asserts both survive.

## Story 3 — A spec's cumulative spend is legible from its issue

1. Take one specification through at least two stages that both persist
   successfully (Story 2).
2. Open the spec's lifecycle issue. Confirm:
   - Each stage's own status comment carries a compact cost line
     (data-model.md "Rollup — per-run cost line").
   - Exactly one comment contains the
     `<!-- wing-commander-metrics-rollup:begin -->` region, showing a
     total that equals the sum of every persisted record for that
     `spec_dir`.
3. Complete a third stage and confirm the same rollup comment (same
   comment id, `gh api .../comments` before/after) is edited in place —
   not a new comment — and its total increased by exactly that stage's
   cost.
4. Re-dispatch persistence for a run already reflected in the rollup and
   confirm the region's per-run history list and total are unchanged
   (FR-031b).
5. Manually craft (or use the schema-conformance fixture for) a record
   with an unavailable cost field, persist it, and confirm the rollup
   region's "Incomplete" notice appears and names the gap (FR-030)
   rather than silently under-reporting.

## Story 4 — Transcript uploads declare retention

1. `grep -A3 'name: claude-execution-output' .github/workflows/*.yml`
   (or run `verify-transcript-retention-declared` directly) and confirm
   every discovered site includes `retention-days: 90`.
2. Add a new `upload-artifact` step uploading a file named like the
   transcript pattern, without `retention-days`, to a scratch branch;
   confirm `verify-transcript-retention-declared` fails and names the
   new site; remove the scratch change.

## Story 5 — Checks fail on regression, not just on review

Run each new gate locally exactly as CI does
(`python3 .github/scripts/run-local-gates.py`, or the individual
`verify-*.py` invocations from contracts/gate-coverage-043.md) against:

1. The correct tree — all five new gates pass.
2. Each gate's own negative fixture in turn (ambient state in a new
   composite; a malformed record; an unknown schema version dropped
   instead of retained; a contention fixture engineered to exhaust
   retries; a transcript upload with no retention) — confirm each turns
   that specific gate red, and that disabling or removing the gate's
   `run:` line from `lint-workflows.yml` is itself caught by the
   existing `verify-gate-wiring.py`.

## Cleanup

Scenarios that create real branches/comments in a shared repository
(Stories 2-4) should be run against a disposable test repository or
reverted afterward — deleting the `metrics` branch and the rollup
comments created during the exercise before merging this feature's own
implementation PR.
