# Quickstart: validating prompt persistence for dispatched runs

## Local (before pushing)

    python .github/scripts/run-local-gates.py

Expect Gate 79 (extended) green, and its new fixtures red for each failure
branch listed in `contracts/persisting-job.md` section 3. Also run Gates 12,
45 (container-shell-safety), 47, and the `review-step-gating` skill on the
changed `if:`/`continue-on-error:` lines.

## Re-run key stability (R6, run first)

A fixture test feeds the composite two `jobs.json` snapshots for one run (attempt
1 and attempt 2, differing job ids) and the same record artifact; the records
file must hold one record. Fails today if the key is unstable.

## Post-merge drills (the `prove-after-merge` skill)

- **D1 — pipeline-dispatched implement**: let tasks (or a fold re-drive)
  dispatch an implement cycle. Expect the run's last job `persist-metrics`
  green, the record in `records.jsonl` on the metrics branch within 15 minutes,
  rollup updated, and no `Wing Commander · metrics-persist` workflow_run for it
  beyond the existing one (none for bot-dispatched). Repeat for finalize.
- **D2 — cancel mid-cycle**: start an implement run, cancel after the agent step
  emitted a record; expect `persist-metrics` to run and persist. Separately,
  cancel a run while queued (concurrency wait before any job): expect
  `persist-metrics` NOT to start. For finalize this proves the started-signal
  readability (research R2); if it fails, apply the documented fallback.
- **D3 — failed stage after next-cycle dispatch**: measure the `stalled`
  queueing delay; record it as the SC-001 exception evidence.
- **D4 — person dispatch**: `gh workflow run` the implement wrapper; expect both
  the persisting job and the later workflow_run job, and one copy of each
  record. Then re-run failed jobs and confirm no duplicate.
- **D5 — failure tolerance**: with the metrics branch unwritable (or a bad
  destination on a scratch run), the persisting job ends green with a warning;
  the run conclusion is unchanged and the next sweep picks the run up.
- **D6 — sweep**: after the daily sweep, `grep -c` each `record_key` in
  `records.jsonl` is 1 (SC-002).
