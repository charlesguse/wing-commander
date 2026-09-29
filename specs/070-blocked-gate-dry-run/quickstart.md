# Quickstart: Validating "A never-unblocking merge gate is named"

This is a runbook for proving the feature works, per the spec's own
Independent Test: "drive the merge-gate decision and the poll loop's
handling of it with fixtures... No live run is required." Every scenario
below is a local fixture/gate run — no dispatch of `auto-release.yml`
against the live test repository is needed to validate this feature (unlike
spec 055's own quickstart, which does require live dispatches for its
identity/containment scenarios).

## Prerequisites

None beyond what spec 055 already requires to run the two gates this
feature extends: a `bash`/`jq` environment (`wc_shell_harness.py`'s
`ensure_jq`/`resolve_bash` already handle discovery) and Python 3. No new
secret, credential, or repository variable is introduced.

## Scenario 1 — a gate blocked with nothing resolved, inside the allowance, is still waited on (Acceptance Scenario 1's precondition; FR-002)

1. Run `python .github/scripts/verify-auto-release-e2e-gate-decisions.py`.
2. Confirm the merge-decision suite's "BLOCKED, no check has registered yet"
   and "BLOCKED, a check still running" scenarios now expect
   `blocked-pending` (not `wait`) from
   `auto-release-e2e-merge-decision.sh` (research.md D1,
   contracts/gate-allowance-decision.md).
3. Confirm the new allowance suite's `start` and `wait` scenarios pass: a
   first `blocked-pending` observation (`blocked_since=""`) yields `start`;
   a later one with `now - blocked_since < 1200` yields `wait`.

**Pass condition**: the decision layer distinguishes "blocked, nothing
resolved yet, still within the allowance" from every stall, and never
declares it stalled early (FR-002, Acceptance Scenario 3).

## Scenario 2 — the allowance exhausted ends the attempt as a named gate stall (Acceptance Scenario 1; FR-003, FR-004)

1. In the same suite, confirm the allowance scenario with
   `now - blocked_since >= 1200` yields `stall`.
2. Run `python .github/scripts/verify-auto-release-report.py` and confirm
   the new `GATE_STALL_*` fixture (using this feature's exact `expected`/
   `observed` strings from contracts/gate-allowance-decision.md) renders a
   durable-issue body containing "gate stall", the gate's name, and
   "required checks never reported a result", and excludes "pipeline
   defect" / "infrastructure" (mirroring the existing three
   `GATE_STALL_*` fixtures' `body_excludes` assertions).

**Pass condition**: SC-001 and Acceptance Scenario 1/5 hold — the verdict
names the gate, names the PR, states the required checks never reported,
and reads "gate stall" in the failure report, never "pipeline defect,"
"infrastructure," or a timeout.

## Scenario 3 — a gate that resolves to a pass inside the allowance still merges (Acceptance Scenario 2)

1. In the allowance suite, confirm a `merge` (or any non-`blocked-pending`)
   decision with a previously-set `blocked_since` yields `clear`.
2. Confirm the corresponding merge-decision scenario (a PR that starts
   `BLOCKED` with an empty rollup and, on a later fetch, resolves to
   `mergeable == "MERGEABLE"` / `mergeStateStatus` in `CLEAN`/`UNSTABLE`/
   `HAS_HOOKS`) still yields `merge\n<number>` from the merge-decision
   script, unaffected by the `blocked-pending` rename.

**Pass condition**: FR-005's reset condition holds, and Acceptance Scenario
2 ("the gate merges it and no stall is reported") is exercised without a
live PR.

## Scenario 4 — the allowance resets only on observable progress, never on shape alone (Edge Case: "flips between nothing reported and something still running")

1. Confirm the allowance suite has no scenario in which two consecutive
   `blocked-pending` decisions (regardless of whether the underlying
   rollup shape differed) produce anything but `wait`/`start` — the
   allowance script never sees rollup shape at all, only the token
   (research.md D3's invariant).
2. Confirm a `wait` decision (e.g. `isDraft`, `UNKNOWN`, `BEHIND`) with a
   previously-set `blocked_since` yields `clear` — proving a gate that
   temporarily looks like ordinary waiting for an unrelated reason still
   resets the timer, per FR-005's "leaves the blocked-with-unresolved-
   checks state."

**Pass condition**: the Edge Case holds — a flapping rollup shape cannot
reset the clock forever, and only merging or leaving the specific
blocked-with-unresolved-checks state does.

## Scenario 5 — the generic timeout is unaffected (Acceptance Scenario 4; FR-007, SC-003)

1. Confirm the allowance suite's scenario for an ordinary `wait` (draft PR,
   or `UNKNOWN`/`BEHIND`) always yields `clear`, never `stall` — the new
   logic has no path to fire when no gate is `blocked-pending`.
2. Diff `auto-release.yml` lines 1083-1089 (the generic-timeout write) and
   lines 1790-1794 (the three-way classification `case`) against this
   branch's base — both must be byte-identical, since neither needs to
   change for this feature (data-model.md's Failure report classification
   table).

**Pass condition**: SC-003 holds — every outcome this feature does not
touch (pass, the four existing gate-stall reasons, infrastructure,
pipeline-defect, and the generic timeout) is unchanged.

## Running everything together

`python .github/scripts/run-local-gates.py` runs both extended gates (66
and 52) alongside the rest of the PR-time suite, per CLAUDE.md. A clean run
of that command, plus the five scenarios above, is the complete evidence
this feature's SC-001/SC-002/SC-003 pass — no dispatch of `auto-release.yml`
against the live test repository is part of this feature's own validation,
consistent with its Independent Test.
