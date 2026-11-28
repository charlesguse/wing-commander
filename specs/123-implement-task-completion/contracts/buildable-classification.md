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

One lifecycle per run. `migrate-stranded-review-lifecycles.yml` is dispatched by hand with inputs `issue` (the lifecycle issue number), `branch` (its `spec/*` branch; anything else stops the run before any read or write), `spec-dir` (its `specs/NNN-slug` directory) and `dry-run` (default `true`: report the verdict, change nothing). The decision has one home, `.github/actions/_shared/migrate-stranded-review-lifecycles.sh decide <issue-state> <spec-meta-stage> <handoff-marker-present> <buildable-unchecked-count>`, which prints one of:

- `decision=migrate`: the issue is open, no hand-off marker comment exists, spec-meta's stage is `review` and `buildable-unchecked-count` > 0. The workflow sets spec-meta's stage to `stalled`, moves the label from `stage:review` to `stage:stalled` and posts the marker comment last.
- `decision=comment-only`: stage is already `stalled` but the marker comment is missing (a partial earlier run); only the label move and the comment are redone.
- `decision=skip reason=<why>`: `issue-not-open`, `already-migrated` (the marker comment exists), `not-at-review`, `count-unreadable` or `no-buildable-left`.

Idempotent: the marker comment is the last write, so a finished hand-off is never repeated. A spec-meta.json that fails the self-identity check decides nothing.
