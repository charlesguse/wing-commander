# Data Model: Implement Stall Hand-off

## Task line classes (derived, never stored)

Computed by `count-tasks-checkboxes.sh` for each `- [ ]`/`- [x]` line
outside fenced blocks.

| Class | Rule (first match wins) | Counted in loop? | Finalize list |
|---|---|---|---|
| Standing instruction | stripped text matches the closed pattern table (research D3) | no | omitted |
| Maintainer task | contains the literal `[maintainer]` token after the id | no | Maintainer steps |
| Implementation task | every other checkbox line | yes | Unfinished implementation |

## Script outputs added (additive)

`impl-checked-count`, `impl-unchecked-count`, `impl-unchecked-items`
(heredoc), `maintainer-items` (heredoc), `standing-count`.

## Blocker record (`$RUNNER_TEMP/implement-blocker.json`, agent-written)

| Field | Type | Validation |
|---|---|---|
| `task` | string `T\d+` | names an unchecked implementation task at the pushed tip |
| `kind` | enum | `missing-tool`, `missing-permission`, `contradictory-spec`, `external-dependency` |
| `detail` | string | 1-300 chars, single line |

Exactly these keys. Any violation (or a missing file) yields
`blocker_valid=false`.

## Cycle outcome (decide script)

Inputs: `ok`, `truncated`, `impl_checked_base`, `impl_checked_tip`,
`impl_unchecked_tip`, `converge_sha`, `iteration`, `max_iterations`,
`blocker_valid`, `blocker_text`, `impl_unchecked_ids_base`, `impl_ids_tip`,
`carried_dropped_ids`.
Outputs: `converged`, `progressed`, `handoff`, `stall-reason`,
`stall-comment`, `dropped-ids`.

Every id in `impl_unchecked_ids_base` or `carried_dropped_ids` that is not in
`impl_ids_tip` is a dropped id and adds one to `impl_unchecked_tip` before the
transitions below (owner decisions A and C on #992).

## Dropped task ids (`spec-meta.json` `dropped_task_ids`, pipeline-written)

| Field | Type | Written by | Read by |
|---|---|---|---|
| `dropped_task_ids` | array of task-id strings; absent when empty | implement.yml "Record truncated-cycle count", from the stop rule's `dropped-ids`, in the same commit as `truncated_count` / `truncated_tier` | `wing-commander-implement-outcome` at the next cycle's base (`meta-ref`), passed to the stop rule as `carried_dropped_ids` |

Rule: each cycle's persisted set is exactly that cycle's `dropped-ids`. An id
therefore stays until it is implementation work at a cycle's tip again
(checked or unchecked), and the agent's own edit of `spec-meta.json` is
overwritten. To accept a retag, a maintainer removes the id from
`dropped_task_ids` on the spec branch between cycles; the stall comment says
so. Left unchanged when no stop-rule decision ran.

State transitions for a healthy, non-truncated cycle:

- `impl_unchecked_tip == 0` -> converged (FR-003/FR-010b)
- else `impl_checked_tip > impl_checked_base` -> dispatch next (progressed)
- else converge commit present -> dispatch next
- else `blocker_valid` -> handoff, reason = quoted blocker
- else `iteration >= max_iterations` -> handoff, reason = iteration cap
- else dispatch next cycle (new behaviour)

## Re-entry

Remaining cycles = `max_iterations - recorded iteration`, floor 0; reported
on the lifecycle issue at re-entry start. No state is written.
