# Quickstart: validating sync-from-main

Contracts: `contracts/sync-method-input.md`. State: `data-model.md`.

## Local gates (no Actions needed)

```bash
python .github/scripts/run-local-gates.py
python .github/scripts/verify-sync-from-main.py
python .github/scripts/verify-rebase-discover-selection.py   # unchanged behaviour under rebase
```

`verify-sync-from-main.py` builds a throwaway origin and clone per case and
must report each of: unknown method rejected; already-current → no commit;
clean merge → one two-parent commit, old tip an ancestor; same-tree merge →
still a commit; in-scope conflict resolution passes; resolution touching an
extra path refused; leftover conflict marker refused; wrong parents refused;
remote moved before publish → push rejected, remote unchanged; `+`/force
refspec refused. Its mutation cases (each guard reverted) must make it fail.

## Scenario 1 — history preserved (US1, SC-001/002)

1. Set repository variable `WING_COMMANDER_SPEC_BRANCH_SYNC=merge`.
2. Record `spec/NNN-…` head `H`. Push an unrelated commit to `main`.
3. After the sync run: `git merge-base --is-ancestor H origin/spec/NNN-…`
   succeeds; the new head's parents are `H` and the new `main` tip; the run log
   shows a plain push, not force-with-lease.

## Scenario 2 — default unchanged (US2, SC-004)

Unset the variable; push to `main`. The leg is named `rebase (…)` and the
branch is force-pushed with lease exactly as before. Set it to `squash`: the
`discover` job fails naming `squash` and the accepted values; no leg runs.

## Scenario 3 — conflict (US3, SC-005)

Edit the same line on the spec branch and on `main`. Merge mode: the agent
resolves, `verify-scope` passes, one sync commit is published. Variation: make
the agent's tree differ on a non-conflicting file (fixture) — nothing is
published and the lifecycle issue gets the `rebase:blocked` callout whose remedy
says to merge `main` into the branch.

## Scenario 4 — consumers (US4, SC-003/006)

With a lifecycle that has two recorded review rounds and a `main` push between
them under merge mode, `wc_convergence.py` reports share and churn as values;
finalize's fold-log range resolves and the log grows. Under rebase, the same
report shows `n/a — rebase rewrites history; merge sync avoids it`.

## Prove after merge

Re-drive one run with `gh workflow run wing-commander-rebase.yml` on a
repository with the variable set to `merge` and record the evidence
(`prove-after-merge` skill).
