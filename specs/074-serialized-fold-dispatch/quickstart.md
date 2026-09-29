# Quickstart: Validating One Fold Queue Per PR

## Prerequisites

- A checkout of this repository with the implementation applied (the
  composites under `.github/actions/wing-commander-fold-queue-*`,
  `.github/actions/_shared/fold-queue-ledger.sh` and
  `fold-queue-await.sh`, the edited `pr-conversation.yml`/`implement.yml`,
  `fold-cycle-guard.yml` and its wrapper, and Gate 126 registered in
  `lint-workflows.yml`).
- `gh` authenticated against the disposable end-to-end test repository
  this pipeline already uses for live drills (spec 055's fixture
  environment), so this drill does not touch the real Wing Commander
  repository's own issues/PRs.
- Local gate suite runnable: `python .github/scripts/run-local-gates.py`
  (per CLAUDE.md's pre-push requirement).

## Drill 1 — local gate suite (fast, no network)

```
python .github/scripts/run-local-gates.py "fold-queue"
```

Expect Gate 126 to pass against the shipped workflows (12 scenarios) and
to report `MUTATION SURVIVED` as a failure it deliberately produced and
recovered from for each of its nine mutations (contracts/gates.md) — i.e.,
the gate script's own self-check, not the suite overall, should show each
mutation breaking and the unmodified subject passing.

## Drill 2 — composite-level fixtures (fast, no network)

```
bash .github/actions/wing-commander-fold-queue-admit/tests/run.sh
bash .github/actions/wing-commander-fold-queue-release/tests/run.sh
bash .github/actions/wing-commander-fold-queue-claim-dispatch/tests/run.sh
bash .github/actions/wing-commander-fold-queue-ledger/tests/run.sh
```

Each uses an injectable `git`/`gh` shim (no live network), exercising: a
clean grant, a queued-then-granted sequence, an idempotent double-release,
one stale-ticket reclaim, and (2026-09-29 reconciliation with spec 075)
two scenarios proving the implement-kind stale-reclaim check resolves
liveness through the round's correlated real run rather than the
ticket's own (dispatching-run) `run_id` — the `wing-commander-fold-queue-admit`
suite. The `wing-commander-fold-queue-claim-dispatch` suite covers: a
decline for no own folds (even against an empty, unclaimed round), a
requeue-then-win once the outstanding `act`-kind ticket clears (with the
winning `folded-items` naming both contributing runs), a win against an
already-empty round, and a decline against an already-claimed round.

## Drill 3 — the reproduced two-run scenario (post-merge, live — FR-023/SC-008)

This is the scenario SC-001/SC-002/SC-003/SC-008 require reproducing
against a real dispatched run, mirroring PR #414's own timeline:

1. Open a throwaway implementation PR against a disposable spec branch in
   the e2e test repository.
2. Post a review with nine fold-route comments, triggering `pr-conversation.yml`
   ("review run"). Let its `classify-and-announce`/`fold-turn-act` reach
   the point where `act` is folding item 5 or 6 (watch the run's job list
   for `act (leg-N)` reaching `in_progress`).
3. While the review run's `act` is still mid-matrix, post a follow-up
   comment with two more fold-route items, starting a second
   `pr-conversation.yml` run ("follow-up run").
4. Watch both runs to completion. Confirm:
   - Neither run's `act` job (nor its `fold-turn-act` prerequisite) shows
     a `cancelled` conclusion for a leg that was merely pending (SC-002).
   - The union of both runs' `report-fold-outcomes` comments accounts for
     all eleven items — folded or explicitly not-folded — with none
     silently absent (SC-001).
   - Exactly one "Implementation cycle N dispatched" reply appears on the
     PR/lifecycle issue for the pair, not two (SC-003) — check which run's
     `dispatch-once` posted it; the other run's `dispatch-once` should show
     `should-dispatch: false` in its own job log with no reply posted.
   - The dispatched `implement.yml` run reaches a non-`cancelled`
     conclusion (SC-002's implement-side half).
5. Record the run URLs (both `pr-conversation.yml` runs, the one
   `implement.yml` run) on the PR or the lifecycle issue, per FR-023.

### Drill 3b — a folding run and a no-fold run (2026-09-29 reconciliation with spec 075)

Reproduces spec.md's acceptance scenario 6 (User Story 2): one run folds,
the other folds nothing of its own, in the same round.

1. Open a throwaway implementation PR against a disposable spec branch in
   the e2e test repository.
2. Post a review with one fold-route comment, triggering `pr-conversation.yml`
   ("folding run"). Let its `act` fold that item.
3. While the folding run's `dispatch-once` is still waiting on its
   `fold-turn-dispatch` ticket (or immediately after, if it already
   cleared), post a follow-up comment whose classification produces a
   fold-route leg that ultimately holds/fails/questions without folding
   anything ("no-fold run") — starting a second `pr-conversation.yml` run
   on the same PR.
4. Watch both runs to completion. Confirm:
   - The no-fold run's `dispatch-once` posts the declined-dispatch notice
     ("This run folded nothing of its own...") and shows
     `should-dispatch: false` / `outcome: declined` in its own job log.
   - The folding run's `dispatch-once` dispatches exactly one implement
     cycle, and its reply's "Folded in this review" list names only the
     folding run's own fold — the no-fold run contributed nothing to the
     round's `folded-items` (FR-011).
   - No second "Implementation cycle N dispatched" reply appears anywhere
     for this round (SC-003).
5. Record both run URLs and the one dispatched `implement.yml` run's URL
   on the PR or the lifecycle issue.

## Drill 4 — forcing a lost cycle (post-merge, live — US3's independent test)

1. Bypass the ticket queue deliberately: manually `gh workflow run` the
   implement wrapper directly (no `fold-queue-token`) at the same moment a
   `pr-conversation.yml` run's `act` ticket is granted and running, so the
   manual dispatch's `implement` job and the ticketed `act` job both
   attempt the same `wing-commander-<spec-dir>` GitHub concurrency group —
   reproducing the one residual collision this design does not eliminate
   by construction (research.md D6's rare path).
2. Confirm the manually-dispatched run is evicted while pending.
3. Confirm `fold-cycle-guard.yml`'s wrapper run fires on that run's
   completion, posts the FR-012 notice, and re-dispatches once.
4. Repeat steps 1–3 once more against the *re-dispatched* run to force a
   second loss; confirm the second notice reports the loss and explicitly
   states that a maintainer's re-drive is the remaining step, with no
   third automatic dispatch (FR-016a).
5. Separately, manually cancel an `implement.yml` run from the Actions UI
   while it is already `in_progress` (not pending); confirm no notice is
   posted at all (FR-013, US3 AC2/AC6 — today's existing silence).

## Expected outcomes summary

| Check | Success criterion |
|---|---|
| Local gates | Gate 126 green (12 scenarios); suite's own mutation self-check shows all nine mutations caught |
| Composite fixtures | All pass, including the idempotent-release, stale-reclaim, and requeue-then-win cases |
| Two-run live drill | 11/11 items terminal, 0 cancelled-while-pending, exactly one dispatch reply, implement run non-cancelled |
| Folding + no-fold live drill (3b) | No-fold run declines and posts spec 075's notice; folding run dispatches once naming only its own fold(s) |
| Lost-cycle live drill | Notice posted only for the never-started+correlated case; re-dispatch fires exactly once per round; manual in-progress cancel stays silent |
