# Quickstart: Validating Board Loop Self-Merge

## Prerequisites

- A checkout of this branch.
- For the live steps, the repository variables `WING_COMMANDER_BOARD_AUTO_MERGE` and `WING_COMMANDER_BOARD_LOOP_PAUSED`.

## 1. Offline: the gate and the suite

```text
python .github/scripts/verify-board-merge.py
python .github/scripts/run-local-gates.py
```

Expected: every fixture's `may_merge` and `unmet_reason` match its recorded expectation. That covers one case per name in `CONDITIONS_FIX`, `CONDITIONS_BUMP` and `REFUSAL_CLASSES`, plus the moved-head and no-checks cases. The full gate suite passes. Contract: [contracts/board-merge.md](contracts/board-merge.md).

## 2. Switch off is unchanged (SC-006)

Leave `WING_COMMANDER_BOARD_AUTO_MERGE` unset and drive a fix item to readiness. Expect the "Awaiting a human merge" report and the `awaiting-merge` marker, with no `merge` job in the run.

## 3. Fix class, live (US1)

Set the switch to `true`. Drive one fix-shaped issue to readiness. Expect a squash commit on `main` whose SHA is the merged head, plus an announcement on the PR and the issue naming each condition.

## 4. Refusal (US3)

Bring a ready PR that touches a workflow file to the merge step. Expect no change on `main`, a handover that quotes GitHub's reason, and the `handed-over` marker.

## 5. Bump class (US2)

Let the auto-update stage open an upgrade PR whose verification passes, with a `wc-bump-verification` marker at the head SHA. Expect a squash merge with the verification quoted in the announcement. A PR from another author, or one with a human commit on top, is not merged.

## 6. Kill switch and prove (US4)

Set `WING_COMMANDER_BOARD_LOOP_PAUSED` to `true` before the merge step: no merge. After an Actions-only merge, expect a prove entry and its evidence on the PR.
