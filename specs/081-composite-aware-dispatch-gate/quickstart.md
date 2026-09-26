# Quickstart: validating spec 081

These are the checks a reviewer or CI runs to confirm the feature's
acceptance scenarios and success criteria actually hold, once
implementation lands. No implementation code here — see contracts/ for
interfaces and data-model.md for shapes.

## Prerequisites

- Repository root.
- `.github/scripts/verify-correlated-release-dispatch.py` amended per
  `contracts/resolving-gate.md`.
- `.github/actions/wing-commander-dispatch-and-wait/action.yml` widened
  per `contracts/dispatch-and-wait-outputs.md`.
- `.github/scripts/verify-auto-release-tag-state-runtime.py` exists
  (User Story 3).

## 1. The gate suite passes on the final tree (SC-007)

```
python .github/scripts/run-local-gates.py
```
Expected: every gate passes, including Gate 59 and its `--self-test`,
Gate 88 and its widened cases, and the new Gate 99, with no gate
skipped, waived, or newly excluded.

## 2. The gate follows the idiom into a composite (User Story 1, SC-001, SC-003, SC-004)

```
python .github/scripts/verify-correlated-release-dispatch.py --self-test
```
Expected: PASS, including — per `contracts/resolving-gate.md`'s
ten-case fixture matrix —
- the fixture that relocates checks 3 and 5's shell into a composite the
  job calls (passes, and the plain-run pass message names the composite
  as the satisfying location, FR-005);
- one fixture per check (3, 4, 5) mutated in each arrangement it can
  occur in, each failing and naming only its own clause (SC-003) — check
  4 has only the inline arrangement (FR-027), plus the fixture that
  relocates check 4's shell into a composite, which fails naming the
  tag-state clause (User Story 1 scenario 7);
- the fixture naming a composite path that does not exist, failing
  loudly with that path named, never a pass (SC-004);
- the two-levels-deep fixture, failing loudly naming the unresolved
  second reference.

Manual confirmation (not required for CI, useful for a reviewer): on a
scratch branch, move `auto-release.yml`'s correlation-and-wait shell
into a throwaway composite the `dispatch-release` job calls, run
```
python .github/scripts/verify-correlated-release-dispatch.py
```
confirm it passes and names the throwaway composite; revert.

## 3. The shared composite carries the full dispatch outcome (User Story 2, SC-010)

```
bash .github/scripts/dispatch-and-wait-tests/run-tests.sh
```
Expected: PASS for every scenario in
`contracts/dispatch-and-wait-outputs.md`'s table, including the two new
ones (`dispatch-rejected`, uncorrelated-wait honored) — each asserting
every declared output for that case, not just `run-url`/`conclusion`.

Mutation check (SC-010): temporarily break one invariant in the
composite's own shipped shell (e.g. drop the attempt-token match from
the correlation loop) and confirm the corresponding harness case fails;
revert.

## 4. auto-release.yml reaches the idiom through its one home (User Story 3, SC-005, SC-006)

```
python .github/scripts/run-local-gates.py
python .github/scripts/verify-auto-release-tag-state-runtime.py
```
Expected: both pass. Then:
- `git grep -n "dispatch-and-wait" .github/scripts/single-home-waivers.json`
  — expected: no match (the waiver is gone, FR-020).
- `python .github/scripts/verify-single-home-idioms.py` — expected: pass
  with no waiver needed for `auto-release.yml`.
- Side-by-side report text: for each of released / branch-advanced /
  dispatch-failed / version-collision, diff the `report` job's rendered
  summary before and after the repoint using the same fixed inputs —
  expected: zero differences (FR-018, SC-005).

## 5. The single-home register holds exactly one copy (SC-006)

```
git grep -rn "gh workflow run" .github/workflows .github/actions
```
Expected: `wing-commander-dispatch-and-wait/action.yml` is the only hit
whose surrounding shell also matches the `gh run list --workflow=` +
`displayTitle` + `[attempt:` co-occurrence Gate 60's
`check_dispatch_and_wait` keys on — confirmed by that gate passing with
zero `dispatch-and-wait` waivers.

## 6. Provenance describes the tree that shipped (FR-023)

- `specs/057-autonomous-board-loop/tasks.md`: T054 and T056 are checked
  off, each pointing at `specs/081-composite-aware-dispatch-gate`.
- `specs/048-correlated-release-dispatch/contracts/regression-gate.md`:
  states that checks 3 and 5 now resolve through a called composite and
  points at `resolving-gate.md`.

## 7. Post-merge proof (FR-022, SC-008)

After merge:
```
gh workflow run auto-release.yml
```
Record the resulting run's URL and outcome on the PR or lifecycle issue
#595.
