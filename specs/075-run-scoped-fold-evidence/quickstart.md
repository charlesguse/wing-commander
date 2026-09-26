# Quickstart: Validating Run-Scoped Fold Evidence

Prerequisites: a checkout of this repository, Python 3, `bash`, `jq`, `git`
on `PATH` — the same prerequisites Gate 34 already documents
(specs/042's quickstart.md). Every scenario below is mechanically
verifiable **locally**, without a live triggered `pr-conversation` run,
except Scenario 5, which is the post-merge "prove it in Actions" step
(SC-006, this repository's rule for behaviour that only runs in Actions).

## Scenario 1 — A lost item is still reported as lost when two runs overlap (US1; FR-001–FR-003, FR-006, FR-007, SC-001, SC-002)

```
python3 .github/scripts/verify-fold-dispatch-once.py -v
```

Inspect the new two-run scenarios (contracts/run-scoped-fold-evidence.md's
"New scenarios" 1–4). Confirm: a leg cancelled with no commit of its own
reports "not folded" even when a sibling run's same-id commit is present
in range; a leg that really did fold cleanly stays silent regardless of a
sibling's same-id commit; a leg that succeeded but folded nothing of its
own reports "partly folded"; and a commit carrying no
`Wing-Commander-Run-Id:` trailer at all is never counted as evidence for
any run.

**Expected**: SC-001/SC-002 hold — replaying PR #414's overlap as a
fixture, the cancelled leg's own run reports it as not folded 100% of the
time, and no scenario in the fixture set credits a leg with a commit
another run made.

## Scenario 2 — The maintainer's fold list and dispatch decision name this review's folds only (US2; FR-008, FR-014, FR-015, SC-005, SC-007)

```
python3 .github/scripts/verify-fold-dispatch-once.py -v
```

Inspect the new scenario 5 (this run folds nothing of its own while a
sibling run's fold commit is in range). Confirm `dispatch-once` computes
zero `gh workflow run` invocations and posts exactly one declined-dispatch
notice naming that this run folded nothing.

**Expected**: SC-005/SC-007 hold — a maintainer reading the fold list sees
only items this review folded, and a run with nothing of its own to
dispatch says so on the PR rather than staying silent or dispatching on
someone else's commit.

## Scenario 3 — The single-run baseline is unchanged (US1 AS4; FR-012, SC-004)

```
python3 .github/scripts/verify-fold-dispatch-once.py
```

Confirm the seven scenarios spec 042 already shipped (three-clean-legs,
mid-cycle wait, cancelled-no-evidence, partly-folded, missing-job,
zero-in-scope, held-leg-timeout) still pass byte-identically — none of
them involves a sibling run, so none of their expected outcomes changes.

**Expected**: SC-004 holds — every existing single-run fixture's report and
fold-list output is unchanged by this feature.

## Scenario 4 — Reintroducing the unscoped-range defect fails a gate (US3; FR-009–FR-011, SC-003)

```
git stash
# apply the mutation from contracts/run-scoped-fold-evidence.md's
# "New mutation" section: replace the wing-commander-fold-evidence call
# with the pre-fix inline git log --grep '^fold(' "$BASE_SHA..$TIP_SHA"
python3 .github/scripts/verify-fold-dispatch-once.py; echo "exit: $?"
git checkout -- .github/workflows .github/actions
git stash pop
```

**Expected**: a non-zero exit while the mutation is applied, and exit 0
once reverted. Confirm separately that "Gate 34" still appears in
`lint-workflows.yml`'s job output when the full `lint · workflows` job
runs (SC-003's "every branch named in FR-010 is covered, and the mutation
fails the suite").

## Scenario 5 — Prove it in Actions after merge (SC-006)

Not part of the local gate suite — it requires a live PR and a live
`pr-conversation` run. Re-drive one `pr-conversation` run
(`gh workflow run` on the wrapper that can dispatch it, or trigger it
through an ordinary review comment) against a spec branch with an
existing fold commit from a prior run already on it. Confirm: the new
run's own fold commit(s) carry a `Wing-Commander-Run-Id:` trailer matching
that run's `github.run_id`; `report-fold-outcomes` reads that trailer back
correctly for at least one leg; and the evidence is recorded on the PR or
the lifecycle issue per this repository's "prove it after merge" rule for
Actions-only behaviour.
