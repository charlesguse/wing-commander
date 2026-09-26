# Phase 1 Data Model: Plan and Tasks Stages Record Their Own Branch Advance

No new record shape. Every entity below is either the new populator
surface for the `branch_advance` group `specs/050-branch-drift-sha-
baseline` already defined (`specs/043-durable-metrics-record/contracts/
metrics-record-schema.md`), or a new composite's own inputs/outputs.
This is spec.md's Key Entities section made concrete against
research.md's decisions.

## `branch_advance` (no shape change — two new populators)

Unchanged shape (data-model.md of specs/050 has the full field table):
`available`, `branch`, `before_sha`, `before_available`, `after_sha`,
`after_available`, `commits`, `commits_available`. This feature adds two
new call sites that populate it — `plan.yml` and `tasks.yml`'s own new
"Record branch advance (after agent)" steps (research.md R3) — alongside
`implement.yml`'s existing one (now routed through the shared composite,
research.md R1, with unchanged values). Every other call site (the
per-agent-step records in all three stages) continues to omit the group
or carry it `available: false`, exactly as before.

| Populator | `branch_advance.branch` | Review mode it fires in |
|---|---|---|
| `implement.yml` "Record branch advance (cycle)" (existing, refactored) | `${spec-prefix}${slug}` | N/A — implement has no review mode |
| `plan.yml` "Record branch advance (after agent)" (**new**) | `${spec-prefix}${slug}` (`auto`) or `${plan-prefix}${slug}` (`pr`) | Both — FR-004 |
| `tasks.yml` "Record branch advance (after agent)" (**new**) | `${spec-prefix}${slug}` (`auto`) or `${tasks-prefix}${slug}` (`pr`) | Both — FR-004 |

**Compatibility**: Still purely additive (FR-009) — the group's shape,
its `*_available` convention, and the base contract's four compatibility
rules are all unchanged. A record from a `plan`/`tasks` run predating
this feature simply lacks a `branch_advance` key, read identically to
`{available: false, ...}` by every consumer, exactly as any pre-spec-050
record already is.

## New composite: `wing-commander-branch-advance`

Not a schema entity — the shared "after"/"commits" computation
(research.md R1). Consumed by `implement.yml` (refactored) and the two
new `plan.yml`/`tasks.yml` call sites.

| Input | Type | Notes |
|---|---|---|
| `branch` | string | The branch to measure — passed through unchanged to the caller's own `wing-commander-metrics-summary` call as `branch` (FR-004: recorded literally by the caller, never touched by this composite). |
| `before-sha` | string, may be empty | The caller's already-resolved "before" point (implement: `steps.base.outputs.base-sha`; plan/tasks: the new `git rev-parse HEAD` capture, research.md R2). |
| `before-sha-available` | `'true'`\|`'false'` | The caller's own availability determination for `before-sha`. |

| Output | Type | Notes |
|---|---|---|
| `after-sha` | string, may be empty | `git rev-parse refs/remotes/origin/<branch>` after a fresh `git fetch origin "+refs/heads/<branch>:refs/remotes/origin/<branch>"`. Empty when the fetch or rev-parse fails (including "no such branch," e.g. a `pr`-mode run whose agent never created its review branch). |
| `after-sha-available` | `'true'`\|`'false'` | `'false'` only when the fetch/rev-parse itself failed — best-effort, never fails the calling step (`continue-on-error: true` at the call site, matching implement's existing convention). |
| `commits` | string (integer), may be empty | `git rev-list --count "<before-sha>..<after-sha>"`, computed only when both `before-sha-available` and the freshly-resolved `after-sha-available` are `'true'`. |
| `commits-available` | `'true'`\|`'false'` | `'false'` when either SHA is unavailable, or the range fails to resolve for a reason other than "0 commits." |

**Invariant**: Byte-identical git plumbing to `implement.yml`'s
pre-refactor inline step (research.md R1) — Gate 43's extension
(contracts/gate-coverage-068.md) proves implement's own recorded values
are unchanged by the extraction (FR-011).

## New workflow step: "Record branch tip before agent" (`plan.yml`, `tasks.yml`)

Not a schema entity — a plain `run:` step, one per file, producing two
step outputs consumed by the "after" capture later in the same job
(research.md R2):

| Output | Source |
|---|---|
| `branch` | `steps.mode.outputs.mode == 'auto'` ? `${spec-prefix}${slug}` : `${plan-prefix}${slug}` (or `${tasks-prefix}${slug}` in `tasks.yml`) |
| `before-sha` | `git rev-parse HEAD` immediately after "Checkout spec branch as wing-commander-bot" |
| `before-sha-available` | `'true'` unless the rev-parse fails |

## Branch-drift signal — baseline-selection table, updated

Replaces specs/050 data-model.md's own table (which named only
implement's two arms) with the three-stage version this feature ships:

| Condition | Baseline | Verdict rule |
|---|---|---|
| Run's head branch == the branch the stage pushes to (`plan`/`tasks` in some future trigger shape, or any stage whose head already is its own target) | `head-sha` (unchanged) | `HEAD_SHA..after_sha` commit count == 0 |
| Any of plan/tasks/implement, inspected record's `branch_advance.available == true` with both points present | `exact-sha` (**widened** — was implement-only) | `before_sha == after_sha`; `measure_branch` is always the record's own `branch_advance.branch` (research.md R5) |
| Dispatched implement run, no record with `branch_advance.available == true` | `since-created` (unchanged fallback, **implement-only**) | `git rev-list --count --since=<createdAt> after_sha` == 0 |
| Plan/tasks run, no record with `branch_advance.available == true` | (skipped — **no fallback**, research.md R5) | no signal |
| Not a push-expected stage / no spec slug resolved / run skipped or cancelled | (skipped, unchanged) | no signal |

**Step summary addition (FR-016)**: the plan/tasks no-evidence case
states "no recorded branch-advance evidence on this `<plan|tasks>`
run — skipping" (research.md R5), textually distinct from implement's
own no-evidence message ("...measuring `<branch>` for commits since the
run was created at `<timestamp>`") so a reader cannot mistake one
stage's outcome for the other's.

## Gate fixtures (not runtime entities, but checked-in test data)

| Fixture | Used by |
|---|---|
| `branch_advance`: `before_sha`/`before_available:true` is a branch-creation commit (schema-identical to an existing both-present-different fixture, added under its own name) | Gate 39 (FR-020, positive) |
| `branch_advance` naming a persistent spec branch (`spec/<slug>`) | Gate 39 (FR-020, positive) |
| `branch_advance` naming a review branch (`plan/<slug>` or `tasks/<slug>`) | Gate 39 (FR-020, positive) |
| A plan run's downloaded record: `branch_advance.available:true`, `branch:"plan/..."`, SHAs equal | Gate 53 (US1, this feature's case 1) |
| A tasks run, SHAs differ | Gate 53 (US1, this feature's case 2) |
| A plan run with no usable record in the downloaded set | Gate 53 (US3/FR-016, this feature's case 3 — asserts NO since-created fallback fires) |
| A tasks run, same as above | Gate 53 (US3/FR-016, this feature's case 4) |
| A workflow/composite pasting the refspec-fetch + `..`-range `rev-list --count` fragments outside the declared home | Gate 60 (FR-012, negative — `branch-advance-capture` check) |
