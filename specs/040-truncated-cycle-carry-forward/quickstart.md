# Quickstart: Validating a Turn-Exhausted Cycle Is Carried Forward, Not Redone

Prerequisites: a checkout of this repository, Python 3, `bash`, `jq` on
`PATH` (the same prerequisites `wc_shell_harness.py` documents for every
existing shell-harness gate). Every scenario below is mechanically
verifiable **locally**, without a live triggered workflow run — this
feature's whole coverage strategy (research.md D8) is built on
`wc_shell_harness.py` driving `implement.yml`'s own shipped `run:` blocks
against synthetic git history, exactly what `python3 .github/scripts/
verify-truncated-cycle-carry-forward.py` does in CI as Gate 30.

## Scenario 1 — A truncated cycle with progress carries forward, no cold Opus redo (US1; FR-001, FR-002, FR-006, FR-007, SC-001, SC-002)

```
python3 .github/scripts/verify-truncated-cycle-carry-forward.py
```

Runs every scenario in `contracts/truncated-cycle-coverage.md`'s table,
including scenario 1: an `exhausted` verdict, the lifecycle record
advanced, a task newly ticked in `tasks.md`. Confirm exit code 0 and that
the script reports `ok=true`, `truncated=true` for that scenario, and that
the retry step's gate condition (unchanged text, `steps.outcome.outputs.ok
== 'false'`) would evaluate false against those outputs — i.e. no
escalated retry fires.

**Expected**: SC-001/SC-002 hold — a turn-exhausted cycle with pushed work
advances to the next iteration at the same tier instead of a cold
escalated redo.

## Scenario 2 — An unfinished feature is never handed to finalize as converged (US2; FR-005, SC-003)

Same command as Scenario 1. Inspect scenario 1's and scenario 2's
`converged` output specifically:

- Scenario 1 (truncated, no `converge:` commit): `converged=false` — the
  absence of the commit is not read as evidence of convergence.
- Scenario 6 (a normal successful cycle) still computes `converged` from
  the existing converge-commit scan, unchanged.

**Expected**: SC-003 holds — zero truncated-and-cut-off runs are ever
reported converged, across the coverage.

## Scenario 3 — A cycle that achieved nothing still escalates (US3; FR-004, SC-004)

Same command. Inspect scenario 2 (`exhausted` verdict, only the
lifecycle-record-advance commit landed — no task ticked, no file changed
outside the spec directory): confirm `ok=false`, `truncated=false` — the
same failed path as today, so the existing retry gate fires exactly as it
does now.

**Expected**: SC-004 holds — a no-progress truncated cycle still escalates
on its first occurrence rather than being carried forward to burn the
whole iteration budget.

## Scenario 4 — A truncated top-tier cycle no longer strands its work (US4; FR-009, SC-005)

```
grep -n "final-ok" .github/workflows/implement.yml
```

Confirm the `stalled` job's condition (`needs.implement.outputs.final-ok
== 'false'`) is unchanged text, then re-run Scenario 1's assertion:
`final.outputs.truncated=='true'` cycles always resolve `ok=true` at
"Consolidate final outcome" regardless of `inputs.model` vs.
`inputs.escalation-model` — the retry step's own gate
(`inputs.model != inputs.escalation-model`) is irrelevant here because
retry never fires for a truncated cycle in the first place (Scenario 1).

**Expected**: SC-005 holds — a truncated cycle already on the escalation
tier is carried forward like any other, never marked stalled.

## Scenario 5 — Repeated truncation is counted and reported (US5; FR-011, FR-012, FR-013, SC-007)

```
python3 .github/scripts/verify-truncated-cycle-carry-forward.py -v
```

(or read the script's own assertions on the counter and reporting checks
described in `contracts/truncated-cycle-coverage.md`'s "Additional
assertions"). Confirm:

- A `spec-meta.json` starting at `truncated_count: 1`, run through a
  second truncated scenario, ends at `2`.
- The same starting state, run through the ordinary-failure or
  normal-success scenario instead, resets to `0`.
- "Dispatch next step"'s composed body for a truncated, below-cap cycle
  contains the consecutive-truncation count and does not contain the word
  "failed."
- The at-cap truncated body states the last cycle ran out of turns before
  assessing what remained, and contains no empty remaining-work fence
  (FR-014).

**Expected**: SC-007/SC-008 hold — a reader of the lifecycle issue alone
can tell a truncated cycle from a failed one and from a normally
unconverged one, and see the consecutive-truncation count, without
opening a run log.

## Scenario 6 — The classification is proven against recorded runs, not merely shipped (US6; FR-018, FR-019, FR-020, SC-009)

```
git stash
# apply one of the mutations research.md D8 / contracts/
# truncated-cycle-coverage.md describe by hand to implement.yml, e.g.
# remove the forced converged=false on the truncated path
python3 .github/scripts/verify-truncated-cycle-carry-forward.py; echo "exit: $?"
git checkout -- .github/workflows/implement.yml
git stash pop
```

**Expected**: a non-zero exit for each of the six required mutations
(contracts/truncated-cycle-coverage.md's "Required mutations" table), and
exit 0 once the mutation is reverted. This is the same check Gate 30
performs automatically in `lint-workflows.yml` on every PR — this
scenario just runs it by hand to build confidence before pushing. Confirm
separately that `Gate 30` appears in `lint-workflows.yml`'s job output
when the full `lint · workflows` job runs, satisfying SC-009's "disabling
or removing the new coverage fails a check."

## Scenario 7 — Every non-truncated path is unchanged (FR-017, SC-006)

Same command as Scenario 1. Confirm scenario 5 (ordinary failure) and
scenario 6 (normal successful cycle) in the coverage output match exactly
what the same synthetic history would have produced against the
pre-feature step text — i.e. diff a run of the unmutated coverage script
against a checkout from before this feature
(`git show main:.github/workflows/implement.yml`, piped through the same
harness) for those two scenarios specifically, and confirm the `ok`/
`converged`/`remaining` outputs are byte-for-byte identical.

**Expected**: SC-006 holds — cycles that fail for any reason other than
turn exhaustion behave identically before and after this feature.
