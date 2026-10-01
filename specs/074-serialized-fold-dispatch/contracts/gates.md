# Contract: Gate 128 — `verify-fold-queue-admission.py`

Renumbered from Gate 126 (T051, maintainer review of #821): five open
Finalize PRs all claimed Gate 126 at tasks time; the maintainer's
allocation gives this feature 128.

## Subject (loaded verbatim, never restated — Principle VIII)

- `pr-conversation.yml`: `fold-turn-act`'s `if:`/`needs:`, `act`'s
  `concurrency.group`/`needs:`, `fold-turn-dispatch`'s `if:`/`needs:`,
  `dispatch-once`'s `concurrency.group`/`needs:`.
- `implement.yml`: `fold-turn-implement`'s `if:`, `implement`'s
  `concurrency.group`/`needs:`, `stalled`'s `concurrency.group`/`if:`.
- `fold-cycle-guard.yml`: the never-started detection expression and the
  correlation-window expression (contracts/fold-cycle-guard.md).

Loaded via `yaml.safe_load` + the shared `find_job` helper
(`wc_shell_harness.py`), evaluated with the shared `wc_gha_expr.py`
interpreter — the same two modules Gate 70 and Gate 73 already share
(single home; a third gate reusing them is confirmation, not
duplication).

## Fixture scenarios (`suite(subject)`)

A cross-product covering, at minimum:

1. **Single run, no contention** — one `act` ticket, no other entrant;
   asserts the ticket is granted immediately and `act` runs without ever
   observing a second pending entrant (SC-006's latency guarantee, tested
   as "zero extra poll iterations" rather than measuring wall-clock).
2. **Two overlapping runs, both folding** — run A's `act` ticket granted
   and running; run B's `act` ticket enqueued; asserts B's `fold-turn-act`
   stays in `granted: false` until A's ticket is released, and that at no
   point does the *simulated* GitHub concurrency-group state show two
   pending entrants (the eviction precondition) for the `wing-commander-<spec-dir>`
   group.
3. **Three overlapping runs** — same as (2), extended by one more entrant,
   confirming the invariant holds for N, not just two (spec.md's own Edge
   Case).
4. **Dispatch claim while a fold is still outstanding** — a dispatch
   ticket with folds of its own (`own_folds > 0`) facing another run's
   outstanding `act` ticket resolves `should-dispatch: false`,
   `outcome: requeued` — never a silent step-aside (FR-007; 2026-09-29
   reconciliation with spec 075).
5. **Dispatch claim after the round empties** — asserts exactly one of two
   simulated concurrent claimants resolves `true` (FR-009/SC-003).
6. **A `stop`-only run** (every classified leg is `stop` — the stop
   procedure runs INSIDE `act`, so `legs` is never `[]` for this case;
   T054/B2) — asserts `fold-turn-act`'s/`fold-turn-dispatch`'s `if:`
   resolve false whenever classify-and-announce's `stop-only` output is
   `true` (their only `enqueue` step never runs), and that `act`/
   `dispatch-once` accept that skip only when `stop-only` agrees it was
   deliberate — never as a blanket substitute for a real ticket grant on a
   mutating run (FR-005/SC-009/FR-017a).
7. **`fold-cycle-guard` never-started + correlated entrant** →
   `notice-and-redispatch`; **never-started + no correlated entrant** →
   `none`; **ran steps then cancelled** → `none` (FR-012/FR-013).
8. **Re-dispatch bound** — a round with `redispatch_count: 1` already set
   → asserts the guard's expression resolves to "report only, no further
   dispatch" (FR-016a).
9. **Re-dispatch claim enqueues a fresh ticket atomically** (T038) — a
   winning `claim-redispatch` call enqueues an `implement`-kind ticket in
   the SAME write as the `redispatch_count` CAS and returns its token, and
   the `react` step threads that token onto its `gh workflow run`
   re-dispatch as `fold_queue_token`.
10. **No-own-folds never wins, in any queue order** (2026-09-29
    reconciliation with spec 075, spec 075 FR-014) — a claim with
    `own_folds == 0` declines against both an already-empty, unclaimed
    round and a round with an outstanding `act`-kind ticket; never
    `requeued`.
11. **A folding run requeues behind an outstanding act-kind ticket rather
    than stepping aside** (2026-09-29 reconciliation) — the ledger
    actually reorders the queue (proven via `peek`, not just the outcome
    label reported), and the same ticket wins once that `act`-kind ticket
    clears.
12. **The winning claim's `folded-items` names every contributing run in
    the round**, each attributed to its own `run_id` — not only the
    winning run's own evidence (2026-09-29 reconciliation, FR-011).
13. **Standalone mode never enqueues an implement-kind ticket** (T046) — a
    winning claim with `implement-configured: false` still claims the
    round (a sibling's claim still declines) but returns an empty
    `implement-token` and the ledger shows no ticket was ever enqueued.
14. **Idempotent win** (T050) — a retried claim carrying the SAME
    dispatch token as a call that already won resolves `outcome: won`
    again with the SAME `implement-token`, never `declined`.

## Mutations (`MUTATIONS`, each proven to break the gate — FR-022)

- `mut_drop_fold_turn_needs` — strips `fold-turn-act`/`fold-turn-dispatch`/
  `fold-turn-implement` out of the downstream job's `needs:` list
  (reintroducing bare concurrency-group contention, defect #1 from
  spec.md's Context section). Must fail scenario 2/3.
- `mut_unconditional_dispatch` — removes the round-emptiness check from
  the claim expression (a claim with own folds and an outstanding `act`
  ticket would win immediately instead of requeuing — reintroducing
  "dispatch-once is once per run, not once per PR", defect #2). Must fail
  scenario 4/5/11.
- `mut_collapse_manual_and_replaced` — removes the correlated-entrant
  check from the guard's detection expression (reintroducing "a
  concurrency-replaced cancel is invisible" in its collapsed form — every
  cancel gets a notice, including a manual one, defect #3 restated).
  Must fail scenario 7.
- `mut_unbounded_redispatch` — removes the `redispatch_count` check from
  the guard's re-dispatch expression. Must fail scenario 8.
- `mut_redispatch_no_enqueue` — reverts `claim-redispatch`'s jq filter to
  only flip `redispatch_count` without enqueueing the implement-kind
  ticket (the T038 defect restored). Must fail scenario 9.
- `mut_drop_redispatch_token_thread` — removes the `-f fold_queue_token=`
  argument from `react`'s `gh workflow run` call (the T038 defect
  restored). Must fail scenario 9.
- `mut_requeue_replaced_by_stepaside` — reverts the requeue branch to a
  plain decline with no queue mutation, so a folding run facing an
  outstanding `act`-kind ticket steps aside instead of requeuing. Must
  fail scenario 11 (and 12, which depends on the requeued ticket
  surviving to win).
- `mut_own_folds_check_dropped` — disables the own-folds gate so a
  no-fold run can fall through to win (spec 075 FR-014 regression). Must
  fail scenario 10.
- `mut_round_list_narrowed_to_claimant` — narrows the winning claim's
  `folded-items` back to the claimant's own `run_id`, dropping every
  other contributing run's folds from the reply. Must fail scenario 12.
- `mut_standalone_still_enqueues` — ignores `implement-configured` and
  always enqueues the implement-kind ticket (the T046 defect restored).
  Must fail scenario 13.
- `mut_win_retry_declines` — reverts the winning branch's idempotent-retry
  check to a plain decline (the T050 defect restored). Must fail
  scenario 14.
- `mut_drop_stop_only_handling` — reverts `fold-turn-act`/
  `fold-turn-dispatch` to admitting a ticket even for a stop-only run, and
  `act`/`dispatch-once` to requiring a bare `success` result from them
  (the T054/B2 defect restored: a stop-only run queues behind the very run
  it was asked to cancel). Must fail scenario 6.

`main()` runs `suite()` against the untouched subject (must be 0
failures) and then, for each mutation, re-runs `suite()` and requires a
failure — `MUTATION SURVIVED` is a hard error, identical to Gate 70's own
`main()` shape.

## Wiring

Registered in `lint-workflows.yml` (as Gate 128, immediately after
Gate 125), `if: "!cancelled()"`, no new `paths:` entry (research.md D8
confirms the existing globs already cover every file this feature
touches). The `fold-turn-dispatch`/`dispatch-once` expressions this gate
loads now come from `fold-turn-dispatch` alone (T045 moved the claim
there) plus `dispatch-once`'s own `concurrency.group`/`needs:`, unchanged
by that move.

The four composite fixture suites this feature's composites ship
(`wing-commander-fold-queue-{admit,release,claim-dispatch,ledger}-tests/
run-tests.sh`) live under `.github/scripts/` (T052, maintainer review of
#821) — not `.github/actions/<composite>/tests/`, a location Gate 119
(`verify-actions-no-gate-scripts.py`) forbids — so both CI and
`python .github/scripts/run-local-gates.py` run them, registered as
separate `run:` steps immediately after Gate 128 itself.
