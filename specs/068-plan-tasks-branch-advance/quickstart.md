# Quickstart: Validating Plan/Tasks Branch-Advance Recording

Prerequisites: a checkout of this repository, Python 3, `bash`, `jq`,
`git` on `PATH`. Every scenario below is mechanically verifiable
**locally**, without a live triggered `plan`/`tasks`/`watchdog` run — the
same fixture-and-harness strategy `specs/050-branch-drift-sha-baseline`
established (research.md, this feature's own contracts/gate-
coverage-068.md).

## Scenario 1 — A plan or tasks run that pushed nothing is caught (US1; FR-001–FR-006, SC-001, SC-002)

```
python .github/scripts/run-local-gates.py gate-53
```

(or `python3 .github/scripts/verify-branch-drift-sha-baseline.py -v`
directly). Confirms this feature's new cases: a synthetic plan-run
record and a synthetic tasks-run record, each with `branch_advance
.available: true` and equal `before_sha`/`after_sha`, each produce a
`lost-progress` signal naming the stage's own branch (`plan/<slug>` or
`tasks/<slug>`), both SHAs, and the recorded commit count.

**Expected**: SC-002 holds for both new stages — a pushed-nothing plan
run and a pushed-nothing tasks run are each reported, where before this
feature both were silently skipped (spec.md's Overview).

## Scenario 2 — A healthy plan/tasks run is never flagged, regardless of inspection timing (US2; FR-013, SC-003, SC-004)

```
python3 .github/scripts/verify-branch-drift-sha-baseline.py -v
```

Confirms the same two new cases with `before_sha != after_sha` produce
no signal, and that this holds independent of the local git fixture's
*current* branch state (simulating an intervening force-push or a later
run's push) — the exact-sha arm never reads live branch state for its
verdict, for any of the three stages now, not only implement.

**Expected**: SC-003/SC-004 hold for plan and tasks the same way
specs/050 already proved them for implement.

## Scenario 3 — A run with no usable evidence degrades visibly, with no false fallback (US4; FR-016–FR-018)

```
python3 .github/scripts/verify-branch-drift-sha-baseline.py -v
```

Confirms a plan run and a tasks run whose downloaded artifact set
carries no `branch_advance.available: true` record produce **no
signal**, and — the assertion unique to this feature — that the
since-created fallback is **not** attempted for either (unlike
implement's own no-evidence case, which still falls back). The step
summary text is asserted to name "no recorded branch-advance
evidence... skipping."

**Expected**: FR-016/FR-018 hold — no false lost-progress signal, and
the collector's own outcome for this run stays `"ok"` (trustworthy),
never `"failed"`.

## Scenario 4 — The record schema covers both review modes and the branch-creation case (SC-005)

```
python .github/scripts/run-local-gates.py gate-39
```

Confirms the three new fixtures — a branch-creation `before` point, a
persistent-spec-branch name, a review-branch name — validate, alongside
the eight fixtures specs/050 already shipped for every other
`branch_advance` state.

**Expected**: SC-005 holds — FR-020's fixture list (a branch-creation
run, a persistent-branch record, a review-branch record) is satisfied
by name, not only by incidental fixture content.

## Scenario 5 — The real composite emits a conforming record for plan, tasks, and (unchanged) implement (SC-001, SC-006)

```
python .github/scripts/run-local-gates.py gate-43
```

Confirms: (a) `implement.yml`'s refactored branch-advance call site
(now routed through `wing-commander-branch-advance`) still emits the
same `branch_advance` values it did before the refactor, for the same
inputs (FR-011's regression proof); (b) `plan.yml`'s and `tasks.yml`'s
new call sites each emit a conforming record for both an `auto`-mode and
a `pr`-mode `branch` value.

**Expected**: SC-006 holds — the capture is exactly one home, and
moving it changed no already-shipped stage's recorded values.

## Scenario 6 — The capture has exactly one home (US3; FR-011, FR-012, SC-006)

```
python .github/scripts/run-local-gates.py gate-60
```

Confirms Gate 60's new `branch-advance-capture` check: the clean tree
(capture logic living solely in `wing-commander-branch-advance`) passes,
and a synthetic third paste of the refspec-fetch + `..`-range
`rev-list --count` fragments into an unrelated workflow fails, naming
the declared home.

**Expected**: SC-006 holds structurally, not only by inspection — a
future re-paste is caught by this gate, not rediscovered by accident
(constitution VIII).

## Scenario 7 — No agent invocation was added (FR-007, SC-007)

```
python3 .github/scripts/verify-actions-layer-invariants.py
```

(specs/043's existing gate, unchanged — confirms no scanned `action.yml`
under `.github/actions/**`, including the new
`wing-commander-branch-advance`, invokes `claude-code-action`.) A
`grep -c "uses: anthropics/claude-code-action" .github/workflows/
plan.yml` and the same for `tasks.yml`, before and after this feature's
diff, should each report the same count as today (one) — the new
branch-advance steps in both files are not agent steps.

## Full local gate run

```
python .github/scripts/run-local-gates.py
```

Runs the complete PR-time gate suite, matching what CI runs
(`lint-workflows.yml`), including every gate this feature extends.
