# Contract: `board-loop.yml` Concurrency Groups

Supersedes, for implementation purposes, the single workflow-level block
`specs/057-autonomous-board-loop/contracts/board-loop-workflow.md`
documents today (its "Concurrency" section, lines 21-30 of that file).
During implementation that section is edited to restate the sentence below
(FR-019/research.md D9); this file is the canonical source the new gate
(SC-006) diffs both `board-loop-workflow.md` and `board-loop.yml`'s own
comments against.

## The guarantee (FR-016, as amended by specs/096-durable-prove-entry FR-005)

> One board item is in flight repository-wide. A directed proof run and a
> merged item's own prove run — neither of which selects a board item or
> opens a fix PR — are the only runs permitted to overlap an ordinary
> board-loop run, or each other when they prove distinct merged items.
> Every other pair of `board-loop.yml` runs queues rather than races or
> cancels.

This sentence must appear, verbatim or gate-verified-equivalent, in:

1. `board-loop.yml`'s per-job `concurrency:` block comments (the
   `wing-commander-board-loop` blocks, the per-merge
   `wing-commander-board-loop-prove-{N}` blocks, and the
   `wing-commander-board-loop-directed-proof` block).
2. `specs/057-autonomous-board-loop/contracts/board-loop-workflow.md`'s
   "Concurrency" section.
3. This file.

## Groups, per job

| Job | Group (ordinary trigger) | Group (`pull_request: closed`) | Group (`directed-stage != ''`) | `cancel-in-progress` |
|---|---|---|---|---|
| `select` | `wing-commander-board-loop` | n/a | n/a — job is skipped for a directed dispatch | `false` |
| `triage`, `route`, `fix`, `review`, `readiness` | `wing-commander-board-loop` | n/a | `wing-commander-board-loop` when directed-reachable (`triage`/`review`/`readiness` only, contracts/directed-proof-run.md) | `false` |
| `prove-gate`, `prove` | `wing-commander-board-loop` | `wing-commander-board-loop-prove-` (suffixed with the merged PR's own number; specs/096-durable-prove-entry replaced the old unconditional `wing-commander-board-loop` membership on this trigger) | `wing-commander-board-loop-directed-proof` | `false` |

The directed group is shared across every directed dispatch (not
per-attempt-token), so two merges proven close together contend for it
rather than each getting an unshared slot — this is what makes FR-001a's
busy-check meaningful (research.md D3's "Alternatives considered").

## Pre-dispatch checks

- **FR-001 (static)**: `board_prove.joins_directed_group(target_workflow,
  target_job)` reads the target's own `concurrency:` group expression off
  the checked-out tree and confirms it differs from the caller's own group
  before ever considering a dispatch. For the self-target case (target is
  `board-loop.yml`) this is true by construction once the groups above
  ship; the check exists so a future edit narrowing or removing the split
  fails loudly rather than silently reintroducing the deadlock.
- **FR-001a (dynamic)**: `board_prove.directed_proof_group_busy(run_list_json,
  own_run_id)` reads `gh run list --workflow=board-loop.yml --json
  databaseId,displayTitle,status -L 20` and reports whether any row OTHER
  THAN `own_run_id` (the calling run's own `GITHUB_RUN_ID`) is
  non-`completed` and carries the `[directed:` marker `board-loop.yml`'s
  `run-name:` expression embeds for a directed dispatch — excluding the
  caller's own row so a directed run never sees its own in-progress
  marker and reports the group busy against itself (PR #490 review,
  2026-09-28). `True` → record `outcome_reason: group-busy` (never
  dispatch); `False` → proceed to dispatch.

## What does not change

- The `wing-commander-board-loop` group's membership and semantics for
  every job that already joins it today (`select` through `readiness`) —
  including the "Related surface" behaviour spec.md documents and leaves
  unchanged: a non-board PR's close event still creates a run that queues
  in this group. `prove-gate`/`prove` on the `pull_request: closed` path no
  longer join this group at all (specs/096-durable-prove-entry FR-004/
  FR-005) — see that feature's own contracts/prove-path-concurrency.md.
- A future external dispatchable target's own concurrency group (FR-004):
  untouched by this feature, continues to be dispatched and waited on
  exactly as today, since it was never a member of either
  `wing-commander-board-loop*` group in the first place.
