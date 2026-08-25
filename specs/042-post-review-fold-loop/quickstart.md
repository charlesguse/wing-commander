# Quickstart: Validating The Post-Review Fold Loop

Prerequisites: a checkout of this repository, Python 3, `bash`, `jq`, `git`
on `PATH` — the same prerequisites every existing shell-harness gate
documents. Every scenario below is mechanically verifiable **locally**,
without a live triggered `pr-conversation`/`finalize` run — this feature's
coverage strategy (research.md D13) is built on `wc_shell_harness.py`
driving the shipped `run:` blocks of both workflows against synthetic
inputs and, where a real commit/push side effect matters, a real local git
repository with a bare remote.

## Scenario 1 — One review, three in-scope items, exactly one implementation dispatch (US1; FR-001–FR-004, SC-001, SC-013)

```
python3 .github/scripts/verify-fold-dispatch-once.py
```

Runs Gate 34's scenario 1: three in-scope legs, each folding cleanly.
Confirm the script reports exactly one computed `gh workflow run`
invocation and that `report-fold-outcomes` posts nothing for this
scenario.

**Expected**: SC-001 holds — down from one implementation dispatch per
item to exactly one per review, with zero legs cancelled by contention
with the run their own review started (the #240 shape).

## Scenario 2 — A review arriving mid-cycle waits, then folds and dispatches once (US1 AS7, Edge Cases; FR-004a, FR-004b, SC-013)

```
python3 .github/scripts/verify-fold-dispatch-once.py
```

Same command, scenario 2: an in-flight implementation cycle is modelled
as already holding `act`'s concurrency group. Confirm the harness shows no
fold and no dispatch until the modelled cycle "finishes," and that the
wait itself is not misreported as a terminated leg by
`report-fold-outcomes`.

**Expected**: SC-013 holds — zero implementation cycles discarded because a
review arrived while one was running; every dispatched cycle starts
against a task list no fold is still writing.

## Scenario 3 — A leg that dies before folding says so on the PR thread (US2; FR-006, FR-006a, SC-002, SC-003)

```
python3 .github/scripts/verify-fold-dispatch-once.py -v
```

Inspect scenarios 3 and 4: a leg cancelled with zero fold evidence
("not folded") and a leg whose fold commit landed but whose job did not
conclude successfully ("partly folded"). Confirm the two produce visibly
different report text, and that scenario 7 (every leg healthy) produces no
report at all.

**Expected**: SC-002/SC-003 hold — the number of review items announced
but never folded and never reported falls to zero, and every announced
leg has an observable outcome, healthy or failed.

## Scenario 4 — A held leg's bounded wait does not block the rest of the review (US1 AS5, Edge Cases; FR-005, FR-005a)

```
python3 .github/scripts/verify-fold-dispatch-once.py
```

Scenario 5: a held leg whose `confirm-timeout-minutes` bound expires
alongside ready legs that fold immediately. Confirm the ready legs'
dispatch happens without waiting for the held leg, and that the held
item's eventual timeout is reported per FR-005a rather than silently
dropped.

```
grep -n "confirm-timeout-minutes" .github/workflows/pr-conversation.yml
```

Confirm the new input exists with a default of `1440` and is wired to the
`act` job's `timeout-minutes:`.

## Scenario 5 — A folded PR comes back and asks for re-review (US3; FR-008–FR-010e, SC-004–SC-008)

```
python3 .github/scripts/verify-finalize-refresh.py
```

Runs Gate 35's scenario 1: an existing open final PR, one prior fold-log
entry, a new fold since. Confirm: the metadata commit reads
`stage: review`; `stage:review` is present on the lifecycle issue and any
`stage:implement` label is gone; a re-review is requested from the login
recorded in `pending_re_review_from`; the PR body's state block is fully
regenerated; prose the fixture placed outside the delimiters survives
unchanged; exactly one new fold-log entry is appended and the prior entry
is untouched.

**Expected**: SC-004/SC-005/SC-006 hold — the lifecycle record reads
`review`, not `implement`, after a converged fold; the final PR describes
the folded branch and asks the triggering reviewer(s) for another look;
the maintainer learns this without polling, via the lifecycle-issue
comment.

## Scenario 6 — A merged or closed final PR is left alone (Edge Cases; FR-009, FR-009a, SC-007)

```
python3 .github/scripts/verify-finalize-refresh.py -v
```

Inspect scenarios 2 and 3: a merged PR and a closed-not-merged PR.
Confirm neither produces a PR edit, a metadata commit, a label change, or
a re-review request, and that the lifecycle-issue comment in each case
names the correct state ("merged" vs. "closed") — distinct wording per
FR-009a.

**Expected**: SC-007 holds — a merged or deliberately closed final PR
receives no refresh, ever.

## Scenario 7 — Repeated finalize runs are quiet (Edge Cases "nothing has changed"; FR-010a, SC-008)

```
python3 .github/scripts/verify-finalize-refresh.py -v
```

Scenario 5: the same open PR refreshed twice with no intervening fold.
Confirm the second run appends no new fold-log entry, requests no second
re-review, and posts no duplicate lifecycle-issue comment.

**Expected**: SC-008 holds — exactly one final PR, no duplicate comments or
re-review requests, across any number of finalize runs.

## Scenario 8 — A re-review request that fails does not fail the refresh (Edge Cases; FR-010b)

```
python3 .github/scripts/verify-finalize-refresh.py -v
```

Scenario 4: a stubbed `gh pr edit --add-reviewer` failure. Confirm the
metadata commit, label restore, and body regeneration still occur, the
job's own exit is still 0, and the failure is stated on the lifecycle
issue rather than silently absorbed.

## Scenario 9 — The create path is untouched (FR-017, SC-012)

```
python3 .github/scripts/verify-finalize-refresh.py
```

Scenario 6: no existing PR. Confirm the create path's outputs match what
a checkout from before this feature would have produced for the same
synthetic history (`git show main:.github/workflows/finalize.yml`, piped
through the same harness), byte-for-byte, and that the machine-owned
region is written fresh with an empty fold log.

**Expected**: SC-012 holds — a first finalize is unchanged in what reaches
the PR and the lifecycle issue.

## Scenario 10 — A folded deletion completes, no manual-work note (US4; FR-011–FR-015, SC-009)

```
grep -n "git rm" .github/workflows/implement.yml
grep -n "git rm" specs/010-reusable-pipeline/contracts/stage-interfaces.md
python3 .github/scripts/verify-stage-tool-lists.py
```

Confirm `Bash(git rm:*)` is present at both `implement.yml` call sites
(`implement.cycle`, `implement.retry`) and in both corresponding
`stage-interfaces.md` rows, and that Gate 27 (`verify-stage-tool-lists.py`)
exits 0 — proving the contract and the call sites agree.

**Expected**: SC-009 holds — a task that removes a tracked file completes
within the implementation cycle, with zero "remaining manual work" reports
attributable to the missing capability.

## Scenario 11 — Reintroducing any of the three defects fails a check (US5; FR-018–FR-021, SC-010)

```
git stash
# apply one mutation at a time from contracts/gate-coverage-042.md's
# "Required mutations" tables, and separately, remove Bash(git rm:*)
# from only one of the two implement.yml call sites without touching
# stage-interfaces.md
python3 .github/scripts/verify-fold-dispatch-once.py; echo "exit: $?"
python3 .github/scripts/verify-finalize-refresh.py; echo "exit: $?"
python3 .github/scripts/verify-stage-tool-lists.py; echo "exit: $?"
git checkout -- .github/workflows .specify specs/010-reusable-pipeline
git stash pop
```

**Expected**: a non-zero exit for every mutation listed in
`contracts/gate-coverage-042.md` and for the deliberately-diverged
call-site edit, and exit 0 once each is reverted — the same checks Gates
34, 35, and 27 run automatically in `lint-workflows.yml` on every PR.
Confirm separately that all three gate names appear in `lint-workflows.yml`'s
job output when the full `lint · workflows` job runs (SC-010's "disabling
the new coverage fails a check," via Gate 10's existing wiring assertion).

## Scenario 12 — Re-running the measured #240 shape end to end

The acceptance bar spec.md names directly: one review, three in-scope
items plus a question and a note, against a live `pr-conversation`
dispatch. This scenario is not part of the local gate suite (it requires
a live PR and a live review) — it is the manual confirmation to run once,
post-merge, against a scratch adopter repository or this repository's own
next qualifying review, per constitution I ("the repo is its own first
example"). Confirm: all three in-scope items appear in `tasks.md`; exactly
one implementation cycle is dispatched; zero legs or cycles belonging to
that review are cancelled; the question and note legs behave exactly as
they do today; and, once that cycle converges, `finalize` refreshes the
existing PR and requests re-review from the reviewer who filed it.
