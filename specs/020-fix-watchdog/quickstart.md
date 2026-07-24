# Quickstart: Validating the Watchdog Fix

Prerequisites: maintainer access to this repository's Actions tab, and
`gh` CLI access equivalent to the repo's own automation (no special setup
beyond what every other stage's verification already needs). All scenarios
below are run against real triggered workflow runs — this repo dogfoods
itself (constitution I) and has no separate unit-test harness for workflow
YAML.

## Scenario 1 — Automatic per-stage trigger reaches a verdict (US1, US2; FR-001–FR-003)

1. Let any lightweight stage complete on a real branch (e.g. push a trivial
   commit that triggers `Rebase`, or wait for the next `5 - Implement` run to
   finish).
2. Confirm `8 - Watchdog` fires automatically (`workflow_run` trigger) and
   completes green.
3. Confirm exactly one verdict comment appears on that spec's lifecycle
   issue: "run passed inspection," a finding block, or a "could not inspect"
   message — never silence.

**Expected**: SC-001, SC-002 hold — one verdict, visible on the lifecycle
issue, no raw log reading required.

## Scenario 2 — Fault injection proves the safety net (FR-002, FR-007, FR-008)

1. Temporarily and deliberately break one of the `collect` job's non-
   collector steps in a throwaway branch/PR (e.g. point `run-id` at a
   plausible-looking but invalid value, or otherwise force "Fetch inspected
   run metadata" to fail) — do **not** do this against `.github/workflows/
   watchdog.yml` on `main`.
2. Trigger the watchdog against that broken configuration (manual
   `workflow_dispatch` is easiest to control).
3. Confirm: `collect` fails as expected, `diagnose`/`triage`/`act` are
   skipped (unchanged Actions semantics), but `report-unhandled-failure`
   still runs (`if: always()`) and posts "could not inspect this run: the
   collect job ended failure unexpectedly" with a link to the job's logs —
   to the lifecycle issue if one resolves, else the run summary.
4. Revert the deliberate breakage.

**Expected**: SC-004 holds — a human-legible reason is present; the run
never ends silently, matching US3's acceptance scenarios.

## Scenario 3 — Reproducing the originally reported failure (FR-005)

1. Because the run linked from issue #96 may have expired past artifact/log
   retention by the time this is verified (spec.md's Assumptions), reproduce
   the same *class* of failure identified in research.md R1 (a hard failure
   in one of `collect`'s pre-collector steps) rather than depending on that
   exact run still being inspectable.
2. Confirm the reproduction, before the fix, exhibits the same "job failed,
   no verdict anywhere" symptom; after the fix, confirm it now yields a
   valid verdict (either the corrected happy path, or, if the underlying
   flakiness is only intermittent, the new "could not inspect: job failed"
   report from Scenario 2).

**Expected**: SC-003 holds.

## Scenario 4 — No regression in the other invocation contexts (FR-006)

1. Re-run the watchdog via manual `workflow_dispatch` against a recent
   completed run. Confirm it still resolves `run-name` via `gh run view` and
   reaches a verdict exactly as before.
2. Let (or force) a watchdog run itself complete, so `8 - Watchdog`
   triggers on `8 - Watchdog` (self-inspection, US4 in
   `specs/015-pipeline-watchdog/`). Confirm self-dispatch-cap and pause
   behavior are unaffected, and a verdict is still reached.

**Expected**: SC-005 holds — every acceptance scenario from
`specs/015-pipeline-watchdog/` that passed before this fix still passes.

## Scenario 5 — Timing (SC-006)

Across Scenarios 1 and 4, note the wall-clock time from the inspected stage's
run completing to the verdict comment appearing. Confirm the median stays
under 10 minutes, consistent with `specs/015-pipeline-watchdog/`'s original
service level — the new safety-net job is a short deterministic job with no
LLM call, so it should not materially add latency on the common (no-failure)
path, where it runs its `if:` check and immediately no-ops.
