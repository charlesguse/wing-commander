# Contract: Fold Queue Ledger

**Internal infrastructure — not a published `workflow_call` surface.**
This document is the contract the shared shell library
(`.github/actions/_shared/fold-queue-ledger.sh`) and every composite that
sources it must satisfy; it is not itself adopter-facing (Constitution
VII's `_shared/` carve-out).

## Storage

- Branch: `wing-commander-fold-queue` (created on first write via the
  existing `orphan-branch-reset`-style idiom if it does not yet exist).
- File: `fold-queue.json` at the branch root, shape per data-model.md.

## Write contract (every mutation: enqueue, release, claim, reclaim)

Every write is a **CAS transaction**: fetch the branch's current tip,
parse the current JSON (or start from `{"specs": {}}` if the branch or key
is absent), apply exactly one named transform (`enqueue`, `release`,
`claim-dispatch`, `reclaim-stale`), commit, and push. On a non-fast-forward
push rejection, discard the local commit, re-fetch, and retry — capped at
8 attempts with the same 1s/2s/3s/4s/5s/5s/5s backoff
`wing-commander-metrics-persist` already uses
(`.github/actions/wing-commander-metrics-persist/action.yml:373-509`).
Exhausting the retry budget is a hard failure (`::error::`), never a
silent no-op — Principle VIII's "fail loudly rather than report a pass it
did not earn" applies to a ledger write exactly as it does to a gate.

Every transform is **idempotent under retry**: re-applying `enqueue` for a
token already present is a no-op (not a duplicate entry); re-applying
`release` for a token already absent is a no-op (not an error); a retried
`claim-dispatch` observes its own prior write on the re-fetched tip and
returns the same result it would have returned had the first attempt's
push succeeded.

## Read contract (polling)

A poll is a plain `git fetch` + read of the branch tip — no lock, no
side effect. Callers MUST NOT cache a read across poll iterations; each
iteration re-fetches, so a concurrent writer's update is visible on the
very next poll.

## Transforms

- **`enqueue(spec_dir, kind, run_id)`**: appends
  `{token: "run-<run_id>-<kind>", kind, run_id, enqueued_at: now, granted_at: null}`
  to `specs[spec_dir].queue` unless a ticket with that token already
  exists. If `specs[spec_dir].queue` was empty before this append,
  increments `specs[spec_dir].round` and initializes a fresh
  `specs[spec_dir].rounds[<new round>]` record (data-model.md).
- **`release(spec_dir, token, outcome, commit_sha?, leg_id?)`**: removes
  the ticket matching `token` from `queue` (only valid when it is at index
  0 — a release request for a non-head ticket is a caller error, surfaced
  as `::error::`, since a ticket only performs real work once granted).
  Appends a completion record to the current round's `folded_items` (when
  `commit_sha` is present) or `not_folded_items` (otherwise).
- **`claim-dispatch(spec_dir, round, implement_workflow)`**: only valid
  when the calling ticket (`kind: dispatch`) is at the head. Succeeds
  (returns `should-dispatch: true`) only if `queue` contains no other
  `act`-kind ticket for this spec_dir and `rounds[round].dispatch_claimed_by`
  is `null`; in the same write, sets `dispatch_claimed_by`, reads
  `spec-meta.json`'s `iteration` (fresh checkout, not cached), sets
  `rounds[round].iteration`, and enqueues an `implement`-kind ticket at the
  new queue head. Any other outcome (an `act` ticket still present, or the
  round already claimed) returns `should-dispatch: false` and mutates
  nothing.
- **`reclaim-stale(spec_dir, stale_token)`**: only valid when
  `stale_token` is at index 0 and its `granted_at` is older than
  `stale-after-minutes` and the caller has independently confirmed (via
  `gh api`, outside this transform) that `stale_token`'s owning run is no
  longer active. Removes it from `queue` with no completion record (its
  outcome is unknown by construction — the whole point of reclaim is that
  its owner never got to report one).

## Guarantees

1. At most one ticket per `(spec_dir, kind, run_id)` triple ever exists
   in `queue` at once.
2. `queue[0]`, once granted, is the only entry any caller may act on;
   every other entry's caller is still polling.
3. A round's `dispatch_claimed_by` is set at most once — verified by Gate
   99's mutation coverage (contracts/gates.md).
4. No transform ever blocks on I/O other than `git`/`gh` calls already
   bounded by the composite's own timeout inputs — the ledger itself
   never introduces an unbounded wait (research.md D6 covers the one
   residual wait, which is bounded and self-resolving).
