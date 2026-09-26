# Contract: Gate 99 — `verify-fold-queue-admission.py`

(Working number — the tasks stage confirms the actual next-available gate
number against `lint-workflows.yml` at implementation time, per
plan.md's Testing note.)

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
4. **Dispatch claim while a fold is still outstanding** — asserts
   `should-dispatch` resolves `false` for a claim attempted while another
   run's `act` ticket remains queued (FR-007).
5. **Dispatch claim after the round empties** — asserts exactly one of two
   simulated concurrent claimants resolves `true` (FR-009/SC-003).
6. **`stop`-only run alongside a mutating run** — asserts the stop run's
   jobs never enqueue a ticket at all and never appear in the simulated
   ledger (FR-005/FR-017a).
7. **`fold-cycle-guard` never-started + correlated entrant** →
   `notice-and-redispatch`; **never-started + no correlated entrant** →
   `none`; **ran steps then cancelled** → `none` (FR-012/FR-013).
8. **Re-dispatch bound** — a round with `redispatch_count: 1` already set
   → asserts the guard's expression resolves to "report only, no further
   dispatch" (FR-016a).

## Mutations (`MUTATIONS`, each proven to break the gate — FR-022)

- `mut_drop_fold_turn_needs` — strips `fold-turn-act`/`fold-turn-dispatch`/
  `fold-turn-implement` out of the downstream job's `needs:` list
  (reintroducing bare concurrency-group contention, defect #1 from
  spec.md's Context section). Must fail scenario 2/3.
- `mut_unconditional_dispatch` — removes the round-emptiness check from
  the claim expression (reintroducing "dispatch-once is once per run, not
  once per PR", defect #2). Must fail scenario 4/5.
- `mut_collapse_manual_and_replaced` — removes the correlated-entrant
  check from the guard's detection expression (reintroducing "a
  concurrency-replaced cancel is invisible" in its collapsed form — every
  cancel gets a notice, including a manual one, defect #3 restated).
  Must fail scenario 7.
- `mut_unbounded_redispatch` — removes the `redispatch_count` check from
  the guard's re-dispatch expression. Must fail scenario 8.

`main()` runs `suite()` against the untouched subject (must be 0
failures) and then, for each mutation, re-runs `suite()` and requires a
failure — `MUTATION SURVIVED` is a hard error, identical to Gate 70's own
`main()` shape.

## Wiring

Registered in `lint-workflows.yml` immediately after Gate 98 (or whichever
gate is last at implementation time), `if: "!cancelled()"`, no new
`paths:` entry (research.md D8 confirms the existing globs already cover
every file this feature touches).
