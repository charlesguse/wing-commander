# Contract: `wing-commander-fold-queue-claim-dispatch` (composite action)

**Published surface.** New in this feature.

## Purpose

Called once by `fold-turn-dispatch`, after its own `dispatch`-kind ticket
has been granted (via `wing-commander-fold-queue-admit`), to decide — via
one or more atomic ledger transactions — whether *this* run is the one
that dispatches the round's implement cycle (research.md D4). Per the
maintainer's 2026-09-29 reconciliation with spec 075 (spec.md
Clarifications), this composite internalizes the requeue-and-reawait loop
described below: a caller invokes it once and receives one of `declined`,
`requeued`-then-resolved, or `won` — it never returns a bare `requeued`
state to its caller for the caller itself to loop on, since a GitHub
Actions job's static step list cannot express an unbounded retry across
separate `uses:` steps. Internally it reuses the exact same poll/stale-
reclaim primitive `wing-commander-fold-queue-admit` uses (factored into
`_shared/fold-queue-await.sh`, single-homed per CLAUDE.md), never a
restated copy.

**T045 (maintainer review of #821):** this call, and the post-fold tip
read / fold-evidence computation / own-folds count feeding it, used to
live in `dispatch-once` itself. `dispatch-once` holds the
`wing-commander-<spec-dir>` GitHub concurrency group, so this composite's
own internal requeue-reawait loop, run there, could wait on another run's
`act`-kind ticket clearing — which requires that other run's `act` job to
actually start, and it cannot start while `dispatch-once` is occupying the
very group it needs to join. That was a real deadlock (guarantee 6 below
did not hold for the shape that shipped originally): the claim would time
out after `max-wait-minutes` with nothing ever dispatched, and the
requeued ticket's own release step would then error ("not at queue head").
The call now lives in `fold-turn-dispatch`, which carries no concurrency
group of its own, so its wait never blocks the run it is waiting on;
`dispatch-once` receives the result through this job's own outputs.

## Inputs

| Name | Required | Default | Description |
|---|---|---|---|
| `spec-dir` | yes | — | |
| `round` | yes | — | The round this run's `act` phase (if any) and `dispatch` ticket belong to. |
| `dispatch-token` | yes | — | This run's own granted `dispatch`-kind ticket — proves the caller is entitled to attempt the claim. |
| `own-folds` | yes | — | The count of THIS run's own fold-route items folded in this round (`wing-commander-fold-evidence`'s `folded-json` length) — spec 075 FR-014's own-evidence gate, now enforced inside the ledger's `claim-dispatch` transform rather than only in `wing-commander-fold-dispatch`. |
| `implement-configured` | no | `"true"` | `"true"` when the caller's `implement-workflow` input is non-empty. `"false"` (T046) means a winning claim still claims the round (a sibling's claim still declines) but enqueues no `implement`-kind ticket and returns an empty `implement-token` — no `implement.yml` run will ever be dispatched to await/release one, so one is never created rather than left to wedge every later admission for this spec-dir. |
| `max-wait-minutes` / `poll-interval-seconds` / `stale-after-minutes` | no | same defaults as `wing-commander-fold-queue-admit` | Passed straight through to the internal requeue-reawait loop; irrelevant when the first claim attempt resolves `declined` or `won`. |

## Outputs

| Name | Description |
|---|---|
| `should-dispatch` | `'true'` only for the single winning run; `'false'` for every other run whose round the claim resolved without dispatching (whether it declined for having no folds of its own, or another run already won). |
| `outcome` | `declined` \| `won` — never `requeued` (internalized, see Purpose). |
| `folded-items` | JSON array of every `{run_id, leg_id, summary, commit_sha}` the round accumulated (empty array if none — the "no-op, nothing folded" case), present only when `should-dispatch: true`. Spans every contributing run's entries, not only the caller's own (the one deliberate widening the 2026-09-29 reconciliation makes). |
| `not-folded-items` | JSON array of every `{run_id, leg_id, outcome}` the round accumulated, present only when `should-dispatch: true` — this is what the single aggregate PR reply's negative list is built from, replacing each individual run's own `report-fold-outcomes` warning for the folded-cycle-dispatch reply specifically (each run's own `report-fold-outcomes` job is unaffected and keeps reporting its own legs per FR-006). |
| `iteration` | The computed next iteration number, present only when `should-dispatch: true`. |
| `implement-token` | The `implement`-kind ticket token this same transaction enqueued, to be passed to `implement.yml` as its `fold-queue-token` input (research.md D5), present only when `should-dispatch: true`. |

## Behavioral guarantees

1. **Exactly one winner per round** (FR-009, SC-003): calling this
   composite from every stage-9 run that contributed to a round produces
   `should-dispatch: true` from exactly one of them, `false` from every
   other — enforced by the ledger's single-write CAS transaction
   (`fold-queue-ledger-schema.md`'s `claim-dispatch` transform), never by
   caller-side coordination.
2. **Never dispatches into an unfinished round** (FR-007): a claim
   attempted while any `act`-kind ticket for this spec-dir remains in the
   queue never resolves `should-dispatch: true` on that attempt — it
   requeues (own-folds > 0) or declines (own-folds == 0) instead.
3. **A run with no folds of its own never wins** (spec 075 FR-014,
   reconciled): `own-folds == 0` resolves `outcome: declined` immediately,
   regardless of the round's emptiness or claim state — this run posts
   spec 075's declined-dispatch notice and takes no further part.
4. **A `false` result requires no further action from its caller** beyond
   releasing its own `dispatch` ticket — no aggregate-round reply is
   posted; a `declined` result's caller posts spec 075's own
   run-scoped declined-dispatch notice instead, matching today's shape.
5. **The `implement`-kind ticket is inserted atomically with the winning
   claim** (research.md D5) — no caller-visible gap exists in which a
   later round's ticket could queue ahead of it.
6. **No deadlock** (FR-018): the internal requeue-reawait loop is bounded
   by the same `max-wait-minutes` ceiling and stale-reclaim safety net
   `wing-commander-fold-queue-admit` already provides, applied to this
   ticket's own (unchanged) token each time it is requeued — never a
   second, independent wait mechanism. This guarantee depends on the
   caller carrying no `concurrency:` block of its own (T045): a caller
   that does can block the very run its own wait depends on from ever
   starting.
7. **Idempotent under retry** (T050): a retried call carrying the SAME
   `dispatch-token` as a call that already won resolves `outcome: won`
   again, reusing the SAME `implement-token` the original win enqueued
   (or `""` if `implement-configured` was `"false"` then too) — never
   `declined`, which would contradict `fold-queue-ledger.sh`'s own header
   ("every transform is idempotent under retry").
