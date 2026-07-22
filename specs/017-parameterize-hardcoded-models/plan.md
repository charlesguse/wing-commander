# Implementation Plan: Parameterize Hardcoded Models

**Branch**: `spec/017-parameterize-hardcoded-models` | **Date**: 2026-07-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/017-parameterize-hardcoded-models/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Seven executable model selections in `implement.yml` (the retry/escalation branch and the
progress-comment summary step) are literal `claude-opus-4-8` / `claude-haiku-4-5` strings
with no `workflow_call` input behind them — the one gap spec 016 left in an otherwise
fully-parameterized reusable-stage surface. In addition, three of the four illustrative
task tiers (`spec/clarify`, `plan/tasks`, `triage/summary`) have a `workflow_call` input
with a correct default, but **no repository-variable knob** wired into this repo's own
wrapper workflows — unlike the `implement` tier, which already exposes
`WING_COMMANDER_IMPLEMENT_MODEL`. FR-003 requires every tier to be settable "the same
[repository-variable] mechanism already used for the implement-tier model," so closing
the gap means both (a) turning the 7 literals into declared inputs and (b) wiring a repo
variable for every tier, not just fixing the literals.

The approach adds two new `workflow_call` inputs to `implement.yml`
(`escalation-model`, default `claude-opus-4-8`; `summary-model`, default
`claude-haiku-4-5`) to replace the 7 literals, and introduces four new repository
variables — `WING_COMMANDER_SPEC_MODEL`, `WING_COMMANDER_PLAN_MODEL`,
`WING_COMMANDER_SUMMARY_MODEL`, `WING_COMMANDER_IMPLEMENT_ESCALATION_MODEL` — wired
through the existing wrapper-side `${{ vars.X || 'default' }}` pattern (or, for
`watchdog.yml`, its existing direct-`vars.*`-read exception). No reusable stage
workflow's default value changes, so every existing consumer sees identical model
selections with zero configuration (FR-005, User Story 2).

## Technical Context

**Language/Version**: GitHub Actions workflow YAML (`workflow_call` reusable
workflows) + POSIX `bash` steps; no application language — this is CI/CD
infrastructure, matching every other spec in this repo.

**Primary Dependencies**: `anthropics/claude-code-action` (agent invocation),
`gh` CLI (issue/label reads), `actionlint` (CI lint gate in `release.yml`).

**Storage**: N/A — configuration lives in GitHub repository Variables
(`vars.*`) and `workflow_call` input defaults; no database or file-based store.

**Testing**: This repo has no unit-test suite for workflows; correctness is
validated by (a) `actionlint` + the grep-based "published-stage invariant"
gate in `release.yml` (Gate 1b), and (b) dogfooded live runs of the pipeline
against its own issues (constitution I). This feature adds no new automated
test tooling; `quickstart.md` documents the manual/CI validation scenarios
that stand in for tests here, consistent with how spec 016 was validated.

**Target Platform**: GitHub Actions (ubuntu-latest runners), consumed both by
this repo (dogfooded, local `uses: ./...` paths) and by adopting repositories
(pinned `uses: owner/repo/.github/workflows/*.yml@ref`).

**Project Type**: Single project — reusable GitHub Actions workflow library
plus this repo's own thin wrapper workflows that dogfood it (constitution I,
VI). No frontend/backend split.

**Performance Goals**: N/A — no latency/throughput target; the change is a
routing/configuration change, not a hot path.

**Constraints**: Must not change any default model selection (FR-005); must
not introduce a `vars.*` read inside the 8 CI-gated reusable stage workflows
(`intake`, `clarify`, `plan`, `tasks`, `implement`, `finalize`, `cleanup`,
`rebase` — `release.yml`'s Gate 1b greps these and fails the build on any
`vars\.` match); every agent step must keep declaring `--model` and
`--max-turns` explicitly (constitution II, same gate).

**Scale/Scope**: 7 hardcoded literals across 1 reusable workflow file
(`implement.yml`); 4 new repository variables; wiring touches up to 8 wrapper
workflow files (`wing-commander-{1-intake,2-clarify,3-plan,4-tasks,5-implement,6-finalize,7-cleanup,rebase}.yml`)
and `watchdog.yml` itself (documented `vars.*` exception). Full location list
and current defaults are in `research.md`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: Satisfied — this feature is itself a spec (017) flowing through the
  pipeline's own stages, and its change is entirely to this repo's own workflow
  files (the worked example other adopters copy).
- **II. Cost-Conscious Model Tiering**: Directly reinforced, not violated — the
  feature's whole purpose is to make every tiered model selection explicit and
  overridable while preserving the constitution's tier→model defaults
  (haiku/triage, opus/spec+clarify, sonnet/plan+tasks, sonnet-default+opus-opt-in/implement).
  No new agent step is added; the two new `implement.yml` inputs
  (`escalation-model`, `summary-model`) replace literals on **existing** agent
  steps, which already declare `--model` and `--max-turns` — that invariant is
  preserved, only the value's source changes from literal to input.
- **III. Simple, GitHub-Native Interaction**: Satisfied — overrides are ordinary
  repository Variables (Settings → Variables), the same surface `WING_COMMANDER_IMPLEMENT_MODEL`
  already uses; no new dashboard or CLI.
- **IV. Automation-First**: Satisfied — no new manual step; existing automated
  wrapper-to-reusable-workflow wiring is extended, not replaced.
- **V. Security**: Satisfied — no change to trust boundaries, label gating, or
  checkout refs; model identifiers are configuration values, not executable
  content, and flow through the same `with:`/`vars.` paths already reviewed
  for the implement tier.
- **VI. Portability**: Satisfied — new inputs get defaults that reproduce
  current behavior, so an adopting repo's `.specify`/`specs/` and wrapper
  workflows keep working unmodified; repo variables remain something the
  *consuming* repository sets, never a value baked into the published
  reusable workflows.

**Result**: PASS. No violations to record in Complexity Tracking.

*Post-Phase-1 re-check*: PASS, unchanged — Phase 1 design (data-model.md,
contracts/model-override-points.md) introduces no new agent steps, no new
trust boundary, and no default-value change; it only names and documents the
override points designed above.

## Project Structure

### Documentation (this feature)

```text
specs/017-parameterize-hardcoded-models/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── model-override-points.md   # Phase 1 output (/speckit-plan command)
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   ├── implement.yml                     # + 2 new workflow_call inputs (escalation-model, summary-model); 7 literals replaced
│   ├── watchdog.yml                      # unchanged inputs; 2 existing inputs (diagnose-model, propose-fix-model) gain repo-variable defaults via its existing direct-vars.* exception
│   ├── intake.yml, clarify.yml           # unchanged (already parameterized) — wrapper-side wiring only
│   ├── plan.yml, tasks.yml, rebase.yml   # unchanged (already parameterized) — wrapper-side wiring only
│   ├── finalize.yml, cleanup.yml         # unchanged (already parameterized) — wrapper-side wiring only
│   ├── release.yml                       # Gate 1b unchanged — new vars.* reads land in wrapper files, outside its grep scope
│   ├── wing-commander-1-intake.yml       # + vars.WING_COMMANDER_SPEC_MODEL wiring
│   ├── wing-commander-2-clarify.yml      # + vars.WING_COMMANDER_SPEC_MODEL wiring
│   ├── wing-commander-3-plan.yml         # + vars.WING_COMMANDER_PLAN_MODEL wiring
│   ├── wing-commander-4-tasks.yml        # + vars.WING_COMMANDER_PLAN_MODEL wiring
│   ├── wing-commander-5-implement.yml    # extend resolve-model job: + escalation-model, summary-model outputs
│   ├── wing-commander-6-finalize.yml     # + vars.WING_COMMANDER_SUMMARY_MODEL wiring
│   ├── wing-commander-7-cleanup.yml      # + vars.WING_COMMANDER_SUMMARY_MODEL wiring
│   └── wing-commander-rebase.yml         # + vars.WING_COMMANDER_PLAN_MODEL wiring
docs/
└── setup.md                              # Repository variables table: + 4 new rows
```

**Structure Decision**: Single project, no new directories. Every change is a
targeted edit to existing `.github/workflows/*.yml` files (reusable stages
gain declared inputs; this repo's own thin wrappers gain `vars.*` wiring
mirroring the existing `WING_COMMANDER_IMPLEMENT_MODEL` / `WING_COMMANDER_PLAN_REVIEW`
pattern) plus a documentation update to `docs/setup.md`'s repository-variables
table (the configuration-discoverability surface FR-007/SC-005 require).

## Complexity Tracking

*No Constitution Check violations — table intentionally omitted.*
