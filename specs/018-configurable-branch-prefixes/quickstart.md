# Quickstart: Validating Configurable Branch Prefixes

Validation scenarios for spec 018, cross-referenced to the acceptance
scenarios in `spec.md` and the contract in
`contracts/branch-prefix-override-points.md`. This repo has no unit-test
harness for workflow YAML (`plan.md` Technical Context); validation is a mix
of the existing CI gate (`release.yml` Gate 1b, unchanged by this feature)
and manual/dogfooded checks, the same validation style specs 016/017/014
used.

## Prerequisites

- A checkout of this repository (or a fork/adopting repo with its own
  `specify init` output) on a branch containing this feature's changes.
- `gh` CLI authenticated with repo scope, for setting repository variables
  and inspecting workflow runs.
- (Optional, for full end-to-end scenarios) A test issue with the
  `spec-request` label to drive a real pipeline run — expensive in agent
  cost, so most scenarios below are static/contract checks instead.

## Scenario 1 — No overrides: identical default behavior (User Story 2, FR-005, SC-003)

**Setup**: Ensure none of the five `WING_COMMANDER_*_PREFIX` variables are
set in the repository (or run against a fresh fork with no variables
configured).

**Steps**:
```bash
grep -A2 "spec-draft-prefix:" .github/workflows/intake.yml
grep -A2 "spec-prefix:\|plan-prefix:" .github/workflows/plan.yml
grep -A2 "tasks-prefix:" .github/workflows/tasks.yml
```

**Expected**: Every new input's `default:` matches
`contracts/branch-prefix-override-points.md` Layer 1 exactly
(`spec-draft/`, `spec/`, `plan/`, `tasks/`, `impl/`). Run (or dogfood) the
pipeline end to end on a throwaway issue and confirm the created branches,
PR heads, and labels are byte-for-byte identical to a pre-018 run.

## Scenario 2 — Full override: a custom naming scheme end to end (User Story 1, FR-001, FR-003, SC-001, SC-002)

**Setup**: Set all five repository variables to a coherent alternate scheme:

```bash
gh variable set WING_COMMANDER_SPEC_DRAFT_PREFIX --body "draft/"
gh variable set WING_COMMANDER_SPEC_PREFIX --body "spec/"
gh variable set WING_COMMANDER_PLAN_PREFIX --body "planning/"
gh variable set WING_COMMANDER_TASKS_PREFIX --body "tasks/"
gh variable set WING_COMMANDER_IMPL_PREFIX --body "build/"
```

(`spec/` is left at its default deliberately, to also exercise "some
configured, some not" per Scenario 3.)

**Steps** (cheap, no agent cost — static contract check): confirm every
Layer-1 input in `contracts/branch-prefix-override-points.md` is reachable
from a Layer-2 variable by tracing the wrapper wiring:

```bash
grep -n "WING_COMMANDER_SPEC_DRAFT_PREFIX" .github/workflows/wing-commander-*.yml
grep -n "WING_COMMANDER_PLAN_PREFIX" .github/workflows/wing-commander-*.yml
grep -n "WING_COMMANDER_TASKS_PREFIX" .github/workflows/wing-commander-*.yml
grep -n "WING_COMMANDER_IMPL_PREFIX" .github/workflows/wing-commander-*.yml watchdog.yml
```

**Expected**: Every grep returns at least one match.

**Steps** (thorough, real run — do this at least once before merging):
Trigger a live pipeline run on a throwaway test issue through
`spec-request`, driving it through intake → clarify → plan → tasks →
implement → finalize → cleanup.

**Expected**: The draft PR's head branch starts with `draft/`; after merge,
the long-lived integration branch is `spec/NNN-slug` (default, unchanged);
the plan work branch is `planning/NNN-slug`; the tasks work branch is
`tasks/NNN-slug` (default); every stage that locates a branch created by an
earlier stage (plan.yml deriving the slug from the draft PR's head ref,
tasks.yml deriving it from the plan PR's head ref, finalize.yml opening the
final PR from `spec/NNN-slug`) succeeds with zero cross-stage handoff
failures. On teardown, `cleanup.yml` deletes `draft/NNN-slug`,
`spec/NNN-slug`, `planning/NNN-slug`, `tasks/NNN-slug`, and any
`build/NNN-slug-iterN` branches.

**Cleanup**: `gh variable delete WING_COMMANDER_SPEC_DRAFT_PREFIX` etc. for
all five (or four, given `spec/` was left default) — do not leave sentinel
values configured on a working repository.

## Scenario 3 — Partial override: independence (FR-004, SC-005, Edge Case "some configured, some not")

**Setup**: Set only `WING_COMMANDER_PLAN_PREFIX` to `planning/`; leave the
other four unset.

**Expected**: The plan stage creates `planning/NNN-slug` and `tasks.yml`
locates it via the same overridden value; every other branch type
(`spec-draft`, `spec`, `tasks`, `impl`) uses its documented default,
unaffected by the one variable being set.

**Cleanup**: `gh variable delete WING_COMMANDER_PLAN_PREFIX`.

## Scenario 4 — Blank override falls back to default (Edge Case "blank configuration")

**Setup**: `gh variable set WING_COMMANDER_SPEC_DRAFT_PREFIX --body ""`.

**Expected**: `intake.yml` still creates `spec-draft/NNN-slug` — not a branch
named `NNN-slug` with an empty prefix. Confirm by inspecting the resolved
`with: spec-draft-prefix:` value in the wrapper's job output.

**Cleanup**: `gh variable delete WING_COMMANDER_SPEC_DRAFT_PREFIX`.

## Scenario 5 — Invalid/colliding override fails closed before any branch is created (FR-010, Edge Case "invalid or colliding prefix")

**Setup A (invalid characters)**:
```bash
gh variable set WING_COMMANDER_PLAN_PREFIX --body "plan branch/"
```
Trigger `intake.yml` (or `plan.yml` directly via `workflow_dispatch`).

**Expected A**: The run fails at the `wing-commander-preflight` step with an
`::error::` naming the offending variable and value, *before* any
`git checkout -b`/push step runs. No `plan branch/NNN-slug` branch is
created. Inspect `$GITHUB_STEP_SUMMARY` for the same message.

**Setup B (collision)**:
```bash
gh variable set WING_COMMANDER_PLAN_PREFIX --body "spec/"
```
(colliding with the default `WING_COMMANDER_SPEC_PREFIX` value `spec/`.)
Trigger `plan.yml`.

**Expected B**: The run fails at `wing-commander-preflight` before either
the `spec/NNN-slug` or `plan/NNN-slug` (now `spec/NNN-slug`, colliding)
branch is created, naming both colliding prefixes and their variables.

**Cleanup**: `gh variable delete WING_COMMANDER_PLAN_PREFIX`.

## Scenario 6 — Configuration is discoverable without reading pipeline internals (FR-007, SC-004)

**Steps**: Starting only from `docs/setup.md`, with a 5-minute timer, list
every branch-prefix variable a run may use and its default.

**Expected**: All five variables from
`contracts/branch-prefix-override-points.md` Layer 2 are listed in
`docs/setup.md`'s "Repository variables" table, each with a default matching
the contract, reachable without opening any `.github/workflows/*.yml` file.

## Scenario 7 — Maintainer audit: no literal prefix remains (User Story 3, SC-001)

**Steps**:
```bash
grep -rn "spec-draft/\|\"plan/\|'plan/\|\"tasks/\|'tasks/\|\"impl/\|'impl/" \
  .github/workflows/{intake,clarify,plan,tasks,implement,finalize,cleanup,rebase,watchdog}.yml \
  | grep -v "default:"
```

**Expected**: Every remaining match is either a `default:` line (a
`workflow_call` input's documented fallback — allowed), the wrapper files'
`vars.X || 'default'` expressions, or a prose comment — zero matches where a
literal prefix is used directly in a `git checkout -b`, `git ls-remote`,
`gh pr list --head`, `${VAR#prefix}`, or `case prefix/*)` construct outside
of an input's own resolution.
