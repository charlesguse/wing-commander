# Contract: The Ordinary Prove Path's Own Concurrency Group

This is this feature's own working draft of the changes FR-005/FR-021
require folding into
`specs/060-self-redrive-concurrency/contracts/concurrency-groups.md` and
`specs/057-autonomous-board-loop/contracts/board-loop-workflow.md` during
implementation (research.md D9) — it is **not** a second canonical source.
Gate 101 (`verify-concurrency-guarantee-statement.py`) reads its canonical
guarantee sentence from `concurrency-groups.md` alone, unchanged by this
feature; this file exists so implementation has no ambiguity about the
target text to move there.

## The guarantee (FR-016, as amended by FR-005)

Supersedes `concurrency-groups.md`'s current "## The guarantee" text:

> One board item is in flight repository-wide. A directed proof run and a
> merged item's own prove run — neither of which selects a board item or
> opens a fix PR — are the only runs permitted to overlap an ordinary
> board-loop run, or each other when they prove distinct merged items.
> Every other pair of `board-loop.yml` runs queues rather than races or
> cancels.

Must appear, verbatim or gate-verified-equivalent, in the same three kinds
of site Gate 101 already checks (8 per-job `concurrency:` comments,
`board-loop-workflow.md`'s "Concurrency" section, this feature's
equivalent of `concurrency-groups.md`).

## Groups, per job (supersedes `concurrency-groups.md`'s `prove-gate`/`prove` row)

| Job | Group (ordinary trigger) | Group (`directed-stage != ''`) | `cancel-in-progress` |
|---|---|---|---|
| `prove-gate`, `prove` | `wing-commander-board-loop-prove-{github.event.pull_request.number}` (was: `wing-commander-board-loop`) | `wing-commander-board-loop-directed-proof` (unchanged) | `false` |

Every other row (`select` through `readiness`) is unchanged by this
feature.

## What changes from `concurrency-groups.md`'s "What does not change"

That section's bullet —

> the hourly schedule tick can still displace a queued `pull_request:
> closed` run's pending slot … this feature does not change whether it can
> happen

— becomes false the moment the table above ships and MUST be removed
(FR-005 names this sentence specifically). Nothing else in that section is
affected: the directed group's own sharing-across-dispatches semantics, and
a future external dispatchable target's own group, are both untouched.

## The gate (FR-018)

`verify-prove-path-concurrency.py` (next free gate number at
implementation time — 118 as of this tree's HEAD) asserts, against the
real `board-loop.yml`, using `board_prove.read_job_concurrency_group()`
(research.md D8, a small extraction from the existing
`joins_directed_group()`):

1. Each job's whole group expression, evaluated the way GitHub resolves
   it (`wc_gha_expr`) for a `pull_request` event, renders two distinct PR
   numbers to two distinct group names, neither of them
   `wing-commander-board-loop` or
   `wing-commander-board-loop-directed-proof` — the per-merge key FR-004
   requires.
2. The same expression resolves a scheduled run and an ordinary
   dispatch to `wing-commander-board-loop`, and a directed dispatch to
   `wing-commander-board-loop-directed-proof` — the canonical "Groups, per
   job" table in
   `specs/060-self-redrive-concurrency/contracts/concurrency-groups.md`.
3. `prove-gate` and `prove` resolve to identical raw group text (both
   branches), so the two jobs chained by `needs:` can never desync into
   different groups.

The expression is evaluated, never pattern-matched: a per-merge arm whose
text is intact but which can never win (shadowed by an earlier `||`
literal, or `&&`-ed with a false clause) still matches any pattern for
that arm (code review of #893).

Reachable through the gate registry the same way every other gate is
(`.github/scripts/wc_gate_registry.py`'s filename convention plus a
`lint-workflows.yml` wiring pair), run the same way locally
(`python .github/scripts/run-local-gates.py`) and in CI (Principle VIII).

Fixtures (FR-020), both directions:

- **Pass**: the shipped `board-loop.yml`.
- **Fail (1)**: the `pull_request` branch reverted to
  `'wing-commander-board-loop'` — the exact regression this feature exists
  to make loud (spec.md "A rule with no gate behind it").
- **Fail (2)**: the `pull_request` branch templated with a fixed string
  instead of `github.event.pull_request.number` (e.g.
  `'wing-commander-board-loop-prove'`) — the "group key shared by all
  merges" edge case.
- **Fail (3)**: `prove-gate` and `prove`'s group text diverges (one keyed
  by PR number, the other left on the shared group).
- **Fail (4)**: the per-merge arm intact but unreachable — after the
  ordinary literal, or `&&`-ed with a clause a `pull_request` run never
  meets — and the directed-proof arm left unguarded, so a scheduled run
  joins it.

## Acceptance mapping

- User Story 1, Acceptance Scenarios 1 and 2 — satisfied by the group
  table above: a scheduled run never joins `wing-commander-board-loop-prove-{N}`,
  and two merges' own prove runs never share a group.
- User Story 1, Acceptance Scenario 6 (undisplaced behaviour unchanged) —
  the `if:` conditions on both jobs are untouched; only the group name a
  `pull_request` event resolves to changes, which is invisible to the
  job's own logic.
- User Story 3 — the gate above, entirely.
