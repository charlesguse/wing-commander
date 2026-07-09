# Quickstart: Validating Per-Run Agent Metrics (Tier 1)

Prerequisites: a repo checkout with `gh` authenticated, and either (a) a
scratch specification you can push through one or more pipeline stages, or
(b) for the fixture-driven edge cases, a local shell with `jq` (matches
`ubuntu-latest`'s preinstalled toolchain) and the ability to invoke
`.github/actions/speckit-metrics-summary`'s `run:` steps directly against a
hand-crafted `claude-execution-output.json`. See
`contracts/speckit-metrics-summary-action.md` for the action's inputs and
`contracts/step-summary-format.md` for the exact expected output shape.

## Scenario 1 — Normal run: full metrics visible (US1 Acceptance Scenario 1, SC-001)

1. Trigger any single-agent-invocation stage to completion (e.g. dispatch
   `speckit-3-plan.yml` for a scratch spec that's past intake).
2. Open that workflow run's summary page (no artifact download).
3. Expected: a metrics block per `contracts/step-summary-format.md`'s
   "Normal case," showing the model, `turns_used / turn_budget` (e.g.
   `36 / 80`), duration, tokens, and cost — all without opening
   `claude-execution-output.json`.

## Scenario 2 — Turn budget warning fires at/above threshold (US1 Acceptance Scenario 2, SC-002)

1. Craft a fixture transcript (a JSON array whose last entry is
   `{"type": "result", "num_turns": 65, ...}`) and invoke the composite
   action with `max-turns: 80`, `warn-fraction: 0.8` (65/80 = 81.25%).
2. Expected: the rendered block includes the ⚠️ turn-budget warning line
   (contracts/step-summary-format.md), with the run's actual used/budgeted
   numbers and percentage.

## Scenario 3 — No warning under the threshold (US1 Acceptance Scenario 3)

1. Same as Scenario 2 but `num_turns: 40` against `max-turns: 80` (50%).
2. Expected: no warning line appears at all — not a "you're fine" message,
   just its absence (contracts/step-summary-format.md's silence rule).

## Scenario 4 — Missing/unparseable transcript (US1 Acceptance Scenario 4, FR-009, SC-005)

1. Invoke the composite action with `transcript-path` pointing at a
   nonexistent file (missing case), an empty file (empty case), and a file
   containing `not valid json` (unparseable case) — three separate runs.
2. Expected, for all three: the "Unavailable case" block renders
   (contracts/step-summary-format.md), the step itself exits 0, and no
   other step in the job is affected.

## Scenario 5 — Partial result record: some fields present, some missing (spec.md edge case)

1. Craft a fixture whose `result` record has `num_turns` and
   `total_cost_usd` but omits token usage and any per-model breakdown.
2. Expected: the rendered table shows real values for turns and cost, and
   `unavailable` specifically in the tokens cell — the whole block still
   renders (not the all-or-nothing unavailable case).

## Scenario 6 — No discoverable turn budget (spec.md edge case, FR-005)

1. Invoke the composite action without the `max-turns` input at all,
   against a normal fixture transcript.
2. Expected: the Turns cell shows only `turns_used` (no `/ budget`, no
   dash placeholder), and no turn-budget warning line appears regardless of
   how many turns were used.

## Scenario 7 — Multiple invocations in one job, each gets its own block (US1 edge case, FR-008)

1. Dispatch `speckit-5-implement.yml` for a scratch spec on an iteration
   where the primary attempt fails and the opus retry runs (or simulate by
   invoking the composite action three times locally with three distinct
   fixtures and `run-label` values `cycle`, `retry`, `progress comment`).
2. Expected: the job's step summary contains three distinct metrics
   blocks, each headed with its own `run-label`, in invocation order — not
   one block reflecting only the last invocation.

## Scenario 8 — Deterministic-only stage: no summary expected (spec.md edge case)

1. Inspect the step summary of a stage run that invokes no agent at all
   (e.g. `speckit-7-cleanup.yml`'s `teardown-rejected` job, which is pure
   `gh`/`git`).
2. Expected: no metrics block appears anywhere in that job's summary — its
   absence is not an error and nothing should be added to a job that never
   calls the composite action.

## Scenario 9 — Read-only: metrics extraction never changes stage outcome (FR-011)

1. Take any stage run from Scenario 1 and compare its actual outcome (PR
   opened, label flipped, commit pushed — whatever that stage does) against
   an equivalent run from before this feature existed.
2. Expected: identical outcome and identical artifacts besides the new
   step-summary block — the metrics step adds a summary and nothing else
   (no new commit, no new file in the repo, no altered exit code on an
   otherwise-successful run).

See `contracts/speckit-metrics-summary-action.md` for the action's full
input/behavioral contract and `data-model.md` for the field-by-field
availability rules each scenario above exercises.
