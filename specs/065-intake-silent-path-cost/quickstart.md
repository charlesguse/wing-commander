# Quickstart: validating "A Run That Spent Money Says So"

This feature ships entirely as workflow YAML, one composite action, and
three gate-script extensions — there is no service to boot. Validation is
the PR-time gate suite plus a manual read of the shipped scenario table.

## Prerequisites

- A checkout of this repository with the feature's changes applied.
- Python 3 and the repository's existing local-gate tooling (no extra
  dependencies beyond what `run-local-gates.py` already requires).

## 1. Run the full PR-time gate suite

```text
python .github/scripts/run-local-gates.py
```

This is the same gate set CI runs (per CLAUDE.md's "Before pushing"
section) and includes all three gates this feature touches:
`verify-clarification-gating.py`, `verify-metrics-summary-record-emission.py`,
and `verify-plan-tasks-cost-line.py`.

Expected outcome: all gates pass, including the new/extended assertions
described in `contracts/gate-extensions.md`.

## 2. Prove each failure branch fails loudly (FR-010, FR-010a, Constitution VIII)

Each of the following is a checked-in fixture inside the extended gate
scripts' own self-test mode — no manual file editing should be required to
reproduce them, but the fixture's intent can be spot-checked by reading
the mutation it applies:

```text
python .github/scripts/verify-clarification-gating.py --self-test
python .github/scripts/verify-metrics-summary-record-emission.py --self-test
python .github/scripts/verify-plan-tasks-cost-line.py --self-test
```

Expected outcome: each self-test run reports that every mutated (broken)
variant was correctly rejected by the gate's normal-mode logic.

## 3. Walk the outcome-path table by hand

Read the extended `INTAKE_SCENARIOS` table in
`verify-clarification-gating.py` (or the restated version in
`data-model.md`'s Silent Outcome Path section) and confirm, for each of
the four historically-silent scenarios plus at least one non-silent one:

- Exactly one of {outcome callout carries cost, uniform report posts}
  is true.
- The two veto scenarios (readiness veto, contradiction veto) still show
  a cost report despite the run's conclusion being red.
- The "agent never ran" and "cancelled" cases show no cost report.

This is SC-001/SC-005's independent test, reproduced from the checked-in
scenario table rather than a live run.

## 4. Confirm the single-home properties (SC-006, SC-007)

```text
grep -rn "Report cost of a reply that answered nothing" .github/
grep -rn "Report cost of an auto-mode hand-off" .github/
```

Expected outcome: no matches outside historical git history — both
retired step names are gone from the shipped workflows.

```text
grep -rln "wing-commander-cost-report" .github/workflows/
```

Expected outcome: exactly `intake.yml`, `clarify.yml`, `plan.yml`,
`tasks.yml`.

## 5. Post-merge proof (per CLAUDE.md, for behavior that only runs in Actions)

Once merged, re-drive one intake run against a thin issue (no discernible
feature request) via the dispatchable wrapper workflow and confirm the
lifecycle issue carries exactly one cost statement alongside the agent's
own explanatory comment — this is US1's Independent Test, and the evidence
belongs on the PR or the tracking issue per CLAUDE.md's "Working the issue
board."
