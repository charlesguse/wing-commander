# Contract: `wing-commander-fold-queue-claim-dispatch` (composite action)

**Published surface.** New in this feature.

## Purpose

Called once by `dispatch-once`, after its own `dispatch`-kind ticket has
been granted (via `wing-commander-fold-queue-admit`), to decide — via a
single atomic ledger transaction — whether *this* run is the one that
dispatches the round's implement cycle (research.md D4).

## Inputs

| Name | Required | Default | Description |
|---|---|---|---|
| `spec-dir` | yes | — | |
| `round` | yes | — | The round this run's `act` phase (if any) and `dispatch` ticket belong to. |
| `dispatch-token` | yes | — | This run's own granted `dispatch`-kind ticket — proves the caller is entitled to attempt the claim. |

## Outputs

| Name | Description |
|---|---|
| `should-dispatch` | `'true'` only for the single winning run; `'false'` for every other run whose round the claim resolved without dispatching. |
| `folded-items` | JSON array of every `{run_id, leg_id, summary, commit_sha}` the round accumulated (empty array if none — the "no-op, nothing folded" case), present only when `should-dispatch: true`. |
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
   queue always returns `should-dispatch: false`.
3. **A `false` result requires no further action from its caller** beyond
   releasing its own `dispatch` ticket — no reply is posted, matching
   today's behavior when a run has nothing to report and preventing a
   duplicate "dispatched" or "nothing folded" reply per round.
4. **The `implement`-kind ticket is inserted atomically with the claim**
   (research.md D5) — no caller-visible gap exists in which a later
   round's ticket could queue ahead of it.
