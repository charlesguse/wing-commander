# Quickstart: Validating the Prove Entry Survives a Displaced Queue Slot

This feature ships no user-facing command — it changes `board-loop.yml`'s
own behaviour. Validation is: run the gate suite locally (it is the same
set CI runs, CLAUDE.md "Before pushing"), then exercise the real workflow
in Actions per each user story's independent test.

## Prerequisites

- A checkout of this repository with `.github/scripts/board_prove.py`,
  `.github/scripts/board_prove_displacement.py`,
  `.github/scripts/board_prove_recovery.py`,
  `.github/scripts/board_item_marker.py`,
  `.github/scripts/board_eligibility.py`, and `.github/workflows/board-loop.yml`
  at the versions this feature ships.
- `python3`, `gh` (authenticated, for the live-run scenarios only), and
  this repo's usual local gate dependencies (`pyyaml`, etc.).

## 1. Local gate suite (every user story, fixture-level)

```
python .github/scripts/run-local-gates.py
```

Expect green, including:

- Gate 101 (`verify-concurrency-guarantee-statement.py`), unmodified by
  this feature but now diffing the amended sentence
  (contracts/prove-path-concurrency.md) across all ten sites.
- The new gate covering FR-018 (`verify-prove-path-concurrency.py`,
  contracts/prove-path-concurrency.md) — both directions: the real tree
  passes, and each of its three fixture mutations (shared-group revert,
  fixed-string key, `prove-gate`/`prove` divergence) fails naming the
  broken property.
- `board_prove_recovery.py`'s own fixture gate — `is_recoverable()` and
  `find_recoverable_items()` exercised for every marker shape in
  data-model.md's "Resume Step Resolution" and "Board Item Marker" tables,
  both a recoverable and a non-recoverable case per shape (FR-020):
  no-`outcome_reason` (pre-feature marker), `failure`, `unfinished`,
  `group-busy`, `no-target`, `nothing-reaches`, `displaced` (all
  non-recoverable), `"prove run displaced"` and `"uncorrelated"` (both
  recoverable, unless `recovery_attempted` is already true).
- `board_item_marker.py`'s existing gate, extended with round-trip fixtures
  for the two new fields (write with each, read back, and a marker missing
  them reads as `None`/`False`).
- The resume-step clause split (research.md D7) covered by whichever gate
  already fixtures the resume step's chain (per FR-020, both `MERGED` and
  `CLOSED` outcomes from an identical starting marker).

Each new failure branch MUST also be run with the mutation it exists to
catch (Principle VIII, FR-020) — e.g. temporarily revert `prove-gate`'s
group back to the shared literal and confirm the new gate fails; feed
`find_recoverable_items()` a `failure`-reason marker and confirm it is
excluded.

## 2. User Story 1 — a contended merge still reaches prove (Independent Test)

1. Start a scheduled board run that will hold `wing-commander-board-loop`
   for several minutes (any item with an agent-bearing step).
2. While it runs, merge a second, unrelated board fix PR. Its `pull_request:
   closed` run's `prove-gate`/`prove` jobs join
   `wing-commander-board-loop-prove-{PR#}`, not `wing-commander-board-loop`
   — confirm in the Actions tab that this job starts and completes without
   waiting on the scheduled run at all.
3. Merge a third board fix PR whose issue differs from the second's, close
   enough in time that both `prove-gate` jobs are pending at once. Confirm
   both run to completion — their two groups (`...-prove-{PR#A}`,
   `...-prove-{PR#B}`) never collide.

## 3. User Story 1 (recovery half) — a previously stranded item gets proven

1. Construct an issue carrying a `prove` marker with
   `outcome_reason: "prove run displaced"` (or `"uncorrelated"`) and no
   `recovery_attempted` — either by waiting for a genuine displacement
   under the pre-this-feature tree, or by posting the marker comment
   directly via `gh issue comment` for a rehearsal issue.
2. Run `select` (schedule tick or manual `gh workflow run board-loop.yml`,
   no `directed-stage`). Confirm the "Recover a stranded prove" step finds
   the item, checks the directed-proof group is not busy, and dispatches
   `gh workflow run board-loop.yml -f directed-stage=prove -f
   directed-issue=<N> -f directed-pr=<M> -f directed-recovery=true`.
3. Confirm the issue immediately gets a "recovery dispatched" comment and
   its marker gains `recovery_attempted: true`, without waiting for the
   dispatched run.
4. Confirm the dispatched run reaches `prove-gate`/`prove`, performs the
   same actions-only decision/redrive/wait/close logic as any other
   directed `prove` run, and its own comment states both the original
   displacement/uncorrelated condition and that it was recovered
   (contracts/recovery-and-resume.md).
5. On success: the issue closes citing the recovery run's own URL and
   conclusion. On failure/unfinished: the issue stays open, and a second
   `select` run over the same issue does **not** dispatch again
   (`recovery_attempted` already true).

## 4. User Story 2 — a merged fix is never re-triaged (Independent Test)

1. Take an issue with an `awaiting-merge` marker whose PR is genuinely
   `MERGED` (issue still open, no later proof marker).
2. Run the resume step's resolution against this live-shaped state
   (directly via the gate's fixture harness, or by letting a real `select`
   tick reach it). Confirm the resolved step is `prove`, not `triage`, and
   that no `pr`/`branch`/`round`/`base_sha` from the merged attempt appears
   on whatever the item resolves to next.
3. Repeat for the three neighbouring states — PR still `OPEN` (passed
   over), PR `CLOSED` unmerged (falls to `triage`), PR state unresolvable
   (skipped, `_awaiting_merge_holds()`'s existing fail-safe) — confirm each
   is byte-identical to today's behaviour.

## 5. User Story 3 — the arrangement is gated, not just commented (Independent Test)

Run `python .github/scripts/run-local-gates.py` against the real tree (it
passes), then against each of the three fixtures described in
contracts/prove-path-concurrency.md's "The gate" section (each fails,
naming the broken property) — this is the same rehearsal step 1 above
already runs; this section is the independent, story-scoped read of it.

## 6. User Story 4 — the recovery is legible and costed (Independent Test)

After step 3's recovery run completes, read the issue alone (no run log):
it should be possible to tell, in one read, that the proof was displaced
(or uncorrelated), that it was recovered, and what the outcome was. Confirm
the recovery run's own cost line and metrics record (searchable by its
distinct `"proof (recovered): ..."` label) are present via this
repository's existing `wing-commander-metrics-summary` mechanism.
