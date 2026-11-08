# Contract: buildable classification (amends specs/117 shared-scripts.md)

Live contract; fixed like code. Consumers: implement (`wing-commander-implement-outcome`), finalize, lifecycle-review-gate, `wing-commander-remaining-work`.

## `count-tasks-checkboxes.sh <ref> <path>` (env: `GATE_SUITE_READY`, default `true`; `NO_WRITE_PATHS`, default `.claude/,.git/`)

Existing outputs keep names. Changed meaning, announced as a change in the published composite (constitution VII):

- `maintainer-items` additionally includes deterministic-unbuildable lines.
- `impl-*` = buildable + folded review findings (unchanged for a tasks.md with neither class).

New outputs:

| Output | Meaning |
|---|---|
| `buildable-checked-count` / `buildable-unchecked-count` | class 5 only |
| `buildable-unchecked-ids` | space-separated T###/M### ids of unchecked class 5 lines |
| `buildable-unchecked-items` | heredoc, literal lines |
| `fold-unchecked-count` / `fold-unchecked-items` | class 2, unchecked |

Failure mode unchanged: an unreadable ref:path exits non-zero, stdout empty.

## `decide-implement-outcome.sh`

New env: `BUILDABLE_UNCHECKED_TIP`, `BUILDABLE_CHECKED_BASE`, `BUILDABLE_CHECKED_TIP`. `converged` still requires `IMPL_UNCHECKED_TIP`=0 (folds included). `handoff` for cap/blocker requires buildable unchecked (plus dropped ids) > 0. `progressed` uses the buildable checked delta.

## finalize / review gate

Read `buildable-unchecked-count` from the composite at the spec-branch tip / PR head. > 0 → finalize opens no PR and comments the list; the gate skips with a logged reason. No override input.

## Migration

`migrate-stranded-review-lifecycles.sh`: inputs `repo`, optional `dry-run`; idempotent; touches only open lifecycle issues whose spec-meta stage is `review` and `buildable-unchecked-count` > 0.
