# Quickstart: Validating Reliable Watchdog Diagnosis

Prerequisites: maintainer access to this repository's Actions tab, and `gh`
CLI access equivalent to the repo's own automation (no special setup beyond
what every other stage's verification already needs). All scenarios below
run against real triggered workflow runs — this repo dogfoods itself
(constitution I) and has no separate unit-test harness for workflow YAML.

## Scenario 1 — Normal run is unaffected (FR-008; the healthy path)

1. Let any lightweight stage complete on a real branch, so `8 - Watchdog`
   fires automatically.
2. Confirm the `diagnose` job completes in a single attempt (`Diagnose
   (retry)` step shows `skipped`), reaches `outcome: passed-inspection` or
   `outcome: findings` exactly as before this feature, and posts the
   unchanged report text to the lifecycle issue.
3. Confirm `verify-watchdog-run.sh` (stage 8b) still passes for this run.

**Expected**: SC-004 holds — no behavior change on the common path, no new
`pipeline-defect` issue.

## Scenario 2 — Fault-injecting each classified shape proves the retry gate (FR-010; research.md R2)

On a throwaway branch/PR (never against `.github/workflows/watchdog.yml` on
`main`):

1. **Retryable shape**: force the `Diagnose` step to produce a genuine
   terminal `result` record with `is_error: true` or a non-`success`
   `subtype` on its first attempt (e.g. temporarily point `--max-turns` at a
   value that guarantees `error_max_turns` for the injected signal set, or
   simulate the equivalent execution-layer error). Trigger the watchdog
   (`workflow_dispatch` is easiest to control). Confirm: `Classify diagnose
   attempt` outputs `retryable=true`; `Diagnose (retry)` runs (not
   `skipped`); if the retry succeeds, the run reports `passed-inspection`/
   `findings` with `retried=true` recorded internally but the report text
   unchanged (data-model.md); if the retry also fails, the run reports
   "diagnose failed after 2 attempts."
2. **Non-retryable shape**: force the `Diagnose` step to fail before
   producing any terminal `result` record (e.g. temporarily break the
   `--json-schema` argument so the CLI rejects it outright, reproducing the
   `json-schema is not valid JSON` signature). Trigger the watchdog. Confirm:
   `Classify diagnose attempt` outputs `retryable=false`; `Diagnose (retry)`
   is `skipped`; the run reports "diagnose failed" (single-attempt wording)
   immediately, with no added latency from a pointless retry.
3. Revert both deliberate breakages.

**Expected**: SC-001, SC-002, SC-005 hold for both shapes — a masked pass
never occurs either way, and a maintainer reading the lifecycle issue alone
can tell which shape occurred and how many attempts were made.

## Scenario 3 — Reproducing (or confirming) the issue-#117 signature specifically (FR-005)

1. Attempt to fetch run 30161188955's diagnose job log directly (`gh api
   repos/<owner>/<repo>/actions/jobs/<diagnose-job-id>/logs`) to identify
   which of the four known crash signatures fired, per research.md R3's
   decision tree. If the run has aged out of log retention, reproduce the
   most plausible signature from that table instead (e.g. an actor outside
   `allowed_bots`, or the schema-string regression) on a throwaway branch.
2. Apply the targeted fix R3's decision tree indicates for the confirmed
   signature.
3. Re-run (or re-inject) the same signature after the fix. Confirm it either
   no longer occurs, or — if it was classified retryable — the run now
   recovers via Scenario 2's retryable path instead of ending in a bare
   failure.

**Expected**: SC-003 holds — the issue-#117 signature does not recur across
a representative sample of stage 8 runs after the fix.

## Scenario 4 — The verifier itself is unmodified (FR-007)

1. Diff `.github/scripts/verify-watchdog-run.sh` before and after this
   feature's implementation. Confirm zero changes.
2. Re-run Scenario 2's non-retryable case and confirm `verify-watchdog-run.sh`
   still fails that run exactly as it does today (a masked crash must still
   fail verification) — retry does not weaken detection of a genuine,
   unrecovered failure.

**Expected**: FR-007 holds by construction (contracts/
watchdog-diagnose-retry-delta.md's "Unchanged" section), confirmed here by a
literal diff.

## Scenario 5 — Timing stays within the new job budget (research.md R4)

Across Scenario 1 (no retry) and Scenario 2 (one retry each), note the
`diagnose` job's own wall-clock duration. Confirm the no-retry case stays
close to today's baseline (well under 75s per `verify-watchdog-run.sh`'s own
check), the one-retry case stays comfortably inside the new 35-minute job
timeout, and neither case trips `verify-watchdog-run.sh`'s run-level
duration-anomaly band (its ceiling is derived from this workflow's own
recent history, so it adapts automatically as retried runs become part of
that history).

**Expected**: No new `pipeline-defect` issue is filed for timing reasons on
either a healthy or a legitimately-recovered run.
