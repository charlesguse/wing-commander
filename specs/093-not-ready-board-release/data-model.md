# Data Model: A Not-Ready PR Releases the Board

This feature adds no new storage layer (research.md D1). Every entity
below is either an extension of the existing Board Item Marker (spec 057
`contracts/board-item-marker.md`, `data-model.md` "Board Item Marker") or
a value derived at read time from it plus live GitHub state — never a
persisted record of its own.

## Board Item Marker (extended)

The existing JSON payload gains three optional fields, meaningful only as
described:

| Field | Type | Present when | Meaning |
|---|---|---|---|
| `step` | str | always (unchanged) | Unchanged vocabulary; a not-ready outcome keeps `step: "readiness"` (research.md D1). |
| `round` | int | always (unchanged) | No longer dropped to 0 on a converged-review marker write (research.md D6) — carries the fix→review round budget across a moved-head re-admission. |
| `pr` | int\|null | always (unchanged) | Unchanged, **except** this feature's own `stalled` handover marker (FR-008), which — uniquely among stall sites — records the PR the threshold was reached on rather than `null` (research.md D7). |
| `branch` | str\|null | always (unchanged) | Unchanged. |
| `base_sha` | str\|null | always (unchanged) | Unchanged. |
| `nr_count` | int | a `readiness` marker that has recorded at least one not-ready outcome since the last reset; carried unchanged through intervening `review` markers for the same PR | The running count of not-ready outcomes for this PR since the last reset (FR-004(a)). Absent means 0 — this PR has never been not-ready, or was reset by a `board:stalled` removal (Edge Cases). |
| `nr_head_sha` | str | a not-ready `readiness` marker; also this feature's own `stalled` handover marker | The PR head SHA the not-ready (or handover-triggering) decision was measured against (FR-002). |
| `nr_class` | `"self-clearing"` \| `"durable"` | a not-ready `readiness` marker | FR-005's classification of the unmet condition that produced this record, as `board_readiness.evaluate_from_snapshot()` computed it (research.md D2) — never re-derived by the reader. |

A marker with `step: "readiness"` and none of `nr_count`/`nr_head_sha`/
`nr_class` set is the ordinary "just entered readiness from a converged
review, not yet evaluated" shape that exists today — it carries no
not-ready record and is never held.

## Not-Ready Record (logical entity)

The durable, machine-readable record of one not-ready readiness outcome
(spec.md Key Entities). Not a new structure — it is the projection of the
marker's `pr`, `nr_head_sha`, `nr_class` and `nr_count` fields, read only
from the issue's single newest qualifying marker
(`board_item_marker.read_marker_with_timestamp()`), never from prose or a
value captured earlier in the same run (spec.md: "never the issue's
prose, never a comment's text, never a value captured earlier in the same
run").

**Validation rules**:
- Unparsable, missing, or (per `contracts/board-item-marker.md`'s Author
  rule) posted by anyone other than the loop's own App → no record (`None`),
  which `_not_ready_holds()` treats as the FR-011 fail-safe (pass over,
  never admit) whenever the PR head cannot otherwise be resolved either.
- `nr_class` absent or not one of the two known values → treated as no
  record (fail-safe), never as a silent default to either class.

## Hold

The derived state of an item that has a **durable** Not-Ready Record and
whose PR's current head SHA equals `nr_head_sha` (research.md D3). Not a
disposition, not a label, not stored anywhere — recomputed by
`board_eligibility._not_ready_holds()` on every run from the marker plus
the same live PR lookup the select job already performs
(`pr_head_sha_by_number`, research.md D4). Ends by itself the moment the
head moves; never requires a human action (contrast: Handover, below,
which does).

## Re-admission

The event of a Hold ending because the PR's current head SHA no longer
equals `nr_head_sha`. Two independent paths reach it:

1. **Automatic** (FR-001/FR-007, US3): the item was never removed from
   selection eligibility by anything but the Hold itself; once the head
   moves, `_not_ready_holds()` returns `False` on the very next run and
   the item is the in-flight candidate again. Resolves to `review`
   (never `readiness`) because a human's new commits have not been
   through an independent review. `nr_count` is **carried forward
   unchanged** (research.md D5) — re-admission continues the threshold,
   it does not reset it.
2. **Manual** (FR-008's own handover only; research.md D7): a maintainer
   removes `board:stalled` from an item this feature itself stalled. The
   new resume-recovery clause (research.md D7) compares the recovered
   PR's current head against the handover marker's own `nr_head_sha`:
   equal → resolves `readiness` (already reviewed, do not re-review);
   different → resolves `review`. Either way `nr_count` resets to absent
   (0) — the Edge Case's "a label removal is a human's explicit reset of
   the not-ready count."

## Handover

The terminal state of an item whose `nr_count` reached
`board_eligibility.NOT_READY_THRESHOLD` (3, spec.md Assumptions).
Expressed only through spec 057 FR-030's existing mechanism
(`board_item_marker.add_stalled_label()` then a `stalled` marker) — never
a second label, never a second notice shape (FR-008, FR-012). This
feature's own handover marker is the one exception to "a `stalled` marker
always carries `pr: null`" (research.md D7), recording `pr` and
`nr_head_sha` so a later label-removal re-admission can tell whether the
head has moved since the handover.

## Unmet Condition Class

`self-clearing` or `durable` (research.md D2), a field of the
`ReadinessDecision` `board_readiness.evaluate_from_snapshot()` already
returns, extended with one more key (`unmet_class`). Computed once, per
run, from the same fresh `statusCheckRollup` every other readiness
condition already reads — never recomputed from the marker (the marker
only ever *carries forward* a class this module already decided).

## State flow (marker `step` transitions this feature touches)

```text
review (converged) --> readiness [nr_count carried, no not-ready fields yet]
readiness --ready--> awaiting-merge                         [unchanged]
readiness --not ready, self-clearing--> readiness [nr_count+1, nr_class=self-clearing, nr_head_sha=this head]
                                          (item stays in-flight; re-evaluated next run)
readiness --not ready, durable, nr_count+1 < 3--> readiness [nr_count+1, nr_class=durable, nr_head_sha=this head]
                                          (item HELD until head moves)
   held item, head moves --> review [nr_count carried unchanged, round carried unchanged]
readiness --not ready, durable, nr_count+1 >= 3--> stalled [pr, nr_head_sha recorded; board:stalled applied first]
   stalled (this feature's own), board:stalled removed, head unchanged --> readiness [nr_count reset]
   stalled (this feature's own), board:stalled removed, head moved     --> review    [nr_count reset]
   stalled (any other stall site), board:stalled removed               --> review    [unchanged, FR-015]
```
