# Data Model: Implement Finishes Its Tasks

## tasks.md line classes (unchecked and checked, first match wins)

| Order | Class | Recognised by | Counts in `buildable-*` | Counts in `impl-*` | Listed as |
|---|---|---|---|---|---|
| 1 | Standing instruction | spec 117 `is_standing` | no | no | nothing |
| 2 | Folded review finding | text after id/tags starts `Review finding:` or `Recurring review finding:` | no | yes | fold item |
| 3 | Maintainer (tag) | `[maintainer]` in the lead tag run | no | no | human work |
| 4 | Deterministic-unbuildable | post-merge proof / drill pattern; write-boundary classifier hit; gate-suite run when `GATE_SUITE_READY=false` | no | no | human work |
| 5 | Buildable | everything else (ambiguity included) | yes | yes | remaining work |

## Cycle outcome (per implement cycle)

| Field | Source |
|---|---|
| `buildable_ticked` | `buildable-checked-count` tip minus base |
| `buildable_remaining` | `buildable-unchecked-count` at tip (+ dropped ids) |
| `turns_used` / `turn_budget` | run execution record / configured budget |

Written to the lifecycle issue comment and the metrics record; never taken from the agent's report.

## Lifecycle states touched

`spec-meta.json.stage`: `implement` → (cap or validated blocker with buildable left) `stalled` + label `stage:stalled`; resumed cycle (iteration recorded+1) removes the label. Migration sets `review` → `stalled`, iteration unchanged. `dropped_task_ids` semantics (spec 117, decision C on #992) unchanged.

## Transitions of the stop rule

- unchecked `impl` = 0 → converged.
- else cap/blocker and `buildable-unchecked` + dropped > 0 → hand-off (no finalize, no PR).
- else cap and only folds/maintainer-only remain → proceed to finalize (converged when only maintainer-only remain).
