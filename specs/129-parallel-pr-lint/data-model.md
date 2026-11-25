# Data Model: Parallel PR Lint

No stored data. The entities are derived from `.github/workflows/lint-workflows.yml`.

| Entity | Identity | Fields | Rules |
|---|---|---|---|
| Gate | unique step name | job (its unit), `run:` script + args, optional self-test pair | exactly one unit; names unique across PR-time jobs (FR-007, Key Entities) |
| Unit | job id | `lint-shard-1..8`, `harness-tests`; `if: github.event_name == 'pull_request'` | listed in the aggregate's `needs`; every non-checkout step guarded `!cancelled()` (FR-009) |
| Aggregate | job id `lint`, name `lint`, workflow `lint · workflows` | `needs` = all units, `if: always() && pull_request` | only job named `lint`; fails unless every need is `success`; not a gate, not a unit |
| Verdict reader | script / branch protection | matches check-run name `lint`, workflow name containing "workflow" | unchanged |

State transitions of the aggregate on a PR head: in progress (not green) → success (all needs success) | failure (any need failure, cancelled or skipped). On push/schedule/dispatch: skipped, run conclusion unaffected.
