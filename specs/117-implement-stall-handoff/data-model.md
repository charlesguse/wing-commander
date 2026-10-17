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
`blocker_valid`, `blocker_text`.
Outputs: `converged`, `progressed`, `handoff`, `stall-reason`.

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
