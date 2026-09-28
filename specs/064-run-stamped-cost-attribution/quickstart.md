# Quickstart: Validating Run-Stamped Cost Attribution

Prerequisites: a checkout of this repository with the feature branch's
changes, `jq`, `bash`, `python3`. Every scenario below is runnable without
a live pipeline run — drive the relevant `verify-*` gate script directly
(`contracts/cost-attribution.md`, `contracts/run-stamp.md`), per
constitution VIII's "same subject, same arguments, locally and in CI."
`python3 .github/scripts/run-local-gates.py` runs the full suite this
feature touches in one pass.

## Story 1 — A run that posted no cost line is reported, even with a neighbour on the same issue

1. Seed the #369/#370 shape: two `Compute cost line`-style comments on one
   lifecycle issue, `createdAt` 8 seconds apart, windows overlapping, only
   one carrying a well-formed `**Cost**: ...` figure with a stamp naming
   run A. Drive `collect-cost-report`'s logic (via `verify-gate-19.py`'s
   `run_cost_one()` harness) once for run A, once for run B. Confirm: run
   A produces no signal; run B produces `cost-line-missing` naming run B
   (Acceptance Scenarios 1-2, SC-001, SC-002).
2. Malform run A's cost line in the same fixture. Confirm run B's verdict
   is unaffected — no `cost-line-malformed` charged to run B (Acceptance
   Scenario 3).
3. Give both runs a well-formed, stamped cost line. Confirm neither
   produces a signal and each reads its own amount
   (`contracts/cost-attribution.md`'s `own` partition; Acceptance
   Scenario 4).
4. Seed a single comment, no neighbour, unstamped (pre-stamp shape).
   Confirm the verdict matches today's pre-feature behavior (Acceptance
   Scenario 5).
5. Seed a window with one foreign-stamped comment and one unstamped,
   well-formed comment. Confirm the foreign-stamped one is excluded and
   the unstamped one is still accepted — no `cost-line-missing`
   (Acceptance Scenario 6, FR-008).
6. Seed two attempts of one workflow run (same `run_id`, `run_attempt`
   `1` and `2`), only attempt 2 posting. Confirm `cost-line-missing` is
   emitted for attempt 1 alone (Acceptance Scenario 7, FR-002, SC-008).

## Story 2 — Every cost-bearing comment names its run, from one place

1. Run `wing-commander-metrics-summary`'s composite locally (or its
   extracted jq/bash, per `verify-metrics-summary-record-emission.py`'s
   own harness) for a known `run_id`/`run_attempt`/`job`/`step-index`.
   Confirm the `cost-line` output's trailing text is a parseable stamp
   naming exactly that run (Acceptance Scenario 1;
   `contracts/run-stamp.md`).
2. Force the composite's internal metrics gathering to degrade (a missing
   or unparseable transcript, `verify-metrics-summary-record-emission.py`'s
   existing `case_missing_transcript_degrades`-style fixture). Confirm the
   resulting `**Cost**: ... unavailable` text still carries the stamp
   (Acceptance Scenario 2, FR-001).
3. Confirm the stamp does not appear in any rendered preview of the
   comment (an HTML comment renders as nothing) — inspect the raw posted
   body only (Acceptance Scenario 3, FR-004).
4. Add a second, literal reconstruction of the stamp marker to a workflow
   file outside `wing-commander-metrics-summary/action.yml`. Run
   `python3 .github/scripts/verify-metrics-summary-record-emission.py`
   and confirm `case_run_stamp_has_exactly_one_home` fails (Acceptance
   Scenario 4, FR-003). Revert, and confirm the real 12 call sites'
   `$RUN_STAMP` consumption passes the same gate.

## Story 3 — The attribution rule has a gate that can fail it

1. Run `python3 .github/scripts/run-local-gates.py` against the shipped
   collector and confirm every fixture in `data-model.md`'s "Gate
   fixtures" table passes, each run's verdict asserted independently for
   the overlapping-pair fixtures (Acceptance Scenario 1, FR-012).
2. Apply the "drop the stamp preference" mutation
   (`contracts/cost-attribution.md`'s coverage section) and confirm
   `verify-gate-19.py`'s `COST_MUTATIONS` loop reports the suite as
   passing where it should have failed — i.e., confirm the *unmutated*
   suite fails to catch this only if the new scenarios are absent, and
   passes (catches it) once they're present (Acceptance Scenario 2,
   SC-005).
3. Apply the "accept a foreign stamp" mutation and confirm the same
   (Acceptance Scenario 3).

## Cross-cutting: the widened record key holds everywhere it's composed

1. `grep` every production composition site
   (`wing-commander-metrics-summary/action.yml`,
   `wing-commander-metrics-persist/action.yml`) for the record-key literal
   and confirm each includes `run_attempt` (R1's grep-audit, informal —
   `verify-metrics-record-schema.py`'s new shape regex is the actual
   gate).
2. Feed a record whose `record_key` omits the attempt segment to
   `python3 .github/scripts/verify-metrics-record-schema.py` and confirm
   it fails (SC-009).
3. Re-run `python3 .github/scripts/run-local-gates.py` in full and confirm
   green — this is the same command CI's `lint-workflows.yml` derives its
   gate invocations from (CLAUDE.md).
