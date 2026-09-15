# Contract: Four new `collect-*` steps in `watchdog.yml`

This contract describes the interface each new collector must satisfy —
its scope guard, its signal/outcome shape, and the configuration it
reads — so that it is indistinguishable, from `Aggregate signals` onward,
from the five collectors already in the `collect` job. It does not
restate the shared downstream contract (evidence-validity gate,
fingerprint, dedup) — that is unchanged (FR-032) and already documented
in `specs/015-pipeline-watchdog/contracts/watchdog-workflow.md` and
`specs/024-watchdog-precision-hardening/data-model.md`.

## Shared obligations (FR-001–FR-009), restated per collector below

Every collector in this contract:

1. Runs as one `id: collect-<name>` step inside the existing `collect`
   job, `shell: bash`, `continue-on-error: true`.
2. Appends to the same `$RUNNER_TEMP/signals.json` and
   `$RUNNER_TEMP/collector-outcomes.json` the five existing collectors
   already write.
3. Checks the attribution invariant before emitting anything: the scope
   the signal is about did not conclude `skipped`/`cancelled`, and the
   artifact read belongs to the inspected run itself.
4. Emits `"outcome": "ok"` whenever its source produced nothing
   applicable to this run — only a genuine read failure is `"failed"`
   (data-model.md's outcome table).
5. Treats every artifact it reads (PR bodies, issue comments, task
   files, `records.jsonl` lines) as untrusted data.
6. Runs only within its declared scope (below) and emits no signal
   outside it.

## `collect-turn-budget`

- **Scope**: any inspected run whose stage declares a turn budget (i.e.
  its metrics record — store or per-run artifact — carries
  `turns.available: true`).
- **Reads**: the inspected run's own metrics record (research.md R3);
  the spec-043 `records.jsonl` on the metrics branch, filtered to the
  inspected run's `stage`, most recent `WING_COMMANDER_TURN_BUDGET_HISTORY_WINDOW`
  entries; `gh issue list --label pipeline-defect --label "🐕 · turn-budget-trend"
  --state closed --json body` (research.md R4's suppression pre-check,
  only when a cross-run trigger would otherwise fire).
- **Config**: `vars.WING_COMMANDER_TURN_BUDGET_HISTORY_WINDOW` (default
  `10`), `vars.WING_COMMANDER_TURN_BUDGET_CONSECUTIVE_TRIGGER` (default
  `3`), `vars.WING_COMMANDER_TURN_BUDGET_CLIMB_FRACTION` (default `0.6`).
- **Emits**: zero or one `turn-budget` (per-run, `class-hint: null`)
  signal; zero or one `turn-budget-trend` (cross-run, `class-hint:
  "turn-budget-trend"`) signal. Full shapes: data-model.md.
- **No cross-run history available** (adopter has not wired
  `metrics-persist.yml`, or the metrics branch does not exist): the
  per-run signal still emits normally (it needs no history); the
  cross-run half emits nothing and the collector still reports `"ok"`
  (spec.md Assumptions: "the cross-run half... reports that it could not
  inspect, and the per-run half continues to work").

## `collect-cost-report`

- **Scope**: any inspected run that is a cost-bearing stage run, per its
  own metrics record's `cost_available` field (true or false — a run
  with `cost_available: false` is still in scope, it simply produces no
  signal per FR-019; a run with no metrics record at all, e.g. a
  deterministic-only job with no agent step, is out of scope and
  produces no signal).
- **Reads**: the inspected run's metrics record (`cost_available`); the
  lifecycle issue's comments attributable to this run (the same
  attribution convention `collect-branch-drift`'s coexistence check
  already uses to find the lifecycle issue from `spec-meta.json`).
- **Config**: none new — the expected-presentation pattern (research.md
  R8) is a literal in the collector, not a tunable, matching FR-018's
  "single explicit, machine-checkable form."
- **Emits**: zero, one, or two of `cost-line-missing` /
  `cost-line-malformed` (data-model.md's Cost-line claim shapes).

## `collect-final-pr-claims`

- **Scope**: finalize-stage runs only (the inspected run's resolved
  stage, the same resolution `collect-spec-meta` already performs, equals
  `"finalize"`).
- **Reads**: the final PR's body (via `gh pr view`); `tasks.md` at the
  PR's head ref; the commit range between the PR's recorded base and head
  SHAs; the diff's added file list filtered to `*/fixtures/*` (research.md
  R7).
- **Config**: none new.
- **Emits**: zero to three `narrative-drift` signals, one per mismatched
  claim shape (`tasks`/`commits`/`tests`) — never for a claim shape the
  parser cannot match (FR-023), never for a claim that matches ground
  truth (FR-024).
- **Issue-filing**: `narrative-drift` Findings are routed by
  `contracts/turn-budget-trend.md`'s sibling mechanism — see
  `Determine issue-filing eligibility` in that contract's neighbor
  section below — to skip `Ensure pipeline-defect issue` entirely
  (FR-025).

## `collect-spec-collision`

- **Scope**: intake-completion runs only, and only when the inspected
  run's own newly allocated spec number is one of the colliding
  claimants (FR-004's attribution invariant applied to this class: the
  run "owns" the number it itself allocated, not an unrelated pair of
  PRs it happens to observe).
- **Reads**: `gh pr list --state open --json number,headRefName` (the
  same call `intake.yml` already makes for its own labeling step, made
  unfiltered here); `ls -d specs/[0-9][0-9][0-9]-*` on the default
  branch; the configured `spec-draft`/`spec` branch prefixes (the same
  `vars.WING_COMMANDER_SPEC_DRAFT_PREFIX`/`_SPEC_PREFIX` `watchdog.yml`
  already reads at its existing branch-prefix lines).
- **Config**: none new — reuses the existing branch-prefix vars.
- **Emits**: zero or one `spec-number-collision` signal per contested
  number this run's own claim participates in.

## `Stamp signal ids` — four additive rows

The existing source→kind map (watchdog.yml's `Stamp signal ids` step)
gains exactly the four rows in research.md R11 / data-model.md's per-entity
"Signal-id identity" notes. No existing row changes. A signal whose
`source` does not match any row (existing or new) still falls into the
existing `"unmapped"` + warning failure path — this is unchanged and is
not a valid resting state for any signal this feature ships.
