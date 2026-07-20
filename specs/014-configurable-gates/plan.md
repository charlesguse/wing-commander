# Implementation Plan: Configurable Human Review Gates

**Branch**: `plan/014-configurable-gates` | **Date**: 2026-07-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/014-configurable-gates/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Make the plan review gate (Gate 3) configurable, following the exact pattern
the tasks stage already established for its own review step. A new
repository variable, `WING_COMMANDER_PLAN_REVIEW` (`pr` default \| `auto`),
is read by the plan stage's wrapper (`wing-commander-3-plan.yml`) into a new
`plan-review` input on the reusable `plan.yml` workflow. `pr` keeps today's
behavior (open a `plan/NNN-slug` PR, wait for a human merge). `auto` commits
the plan artifacts directly to `spec/NNN-slug` and dispatches the tasks
stage (`wing-commander-4-tasks.yml`) immediately via a new `next-workflow`
input — mirroring `tasks.yml`'s own existing `tasks-review`/`next-workflow`
mechanism verbatim. Invalid configuration values fall back to `pr` (the
enabled default) and are surfaced via a workflow annotation, step summary,
and a lifecycle-issue note, rather than silently weakening the gate. Gates 1,
2, and 4 are untouched — no code in this feature makes them configurable,
per the constitution's NON-NEGOTIABLE Principle V and this spec's FR-011.

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps), YAML (workflow definitions) — same as every other pipeline stage.

**Primary Dependencies**: GitHub Actions (`workflow_call`, `workflow_dispatch`), `gh` CLI, `jq`, `anthropics/claude-code-action@v1`, the repo's own `.github/actions/wing-commander-context` and `.github/actions/wing-commander-preflight` composite actions, and the `/speckit-plan` skill (`.claude/skills/speckit-plan/SKILL.md`, unmodified).

**Storage**: `specs/NNN-slug/spec-meta.json` (durable lifecycle record, JSON), one repository variable (`WING_COMMANDER_PLAN_REVIEW`), and git branches (`spec/NNN-slug`, conditionally `plan/NNN-slug`) — no database.

**Testing**: No automated test suite exists for these workflows; `lint-workflows.yml` (YAML parse + `bash -n` on every embedded script) is the only CI-enforced check and must continue to pass. Feature validation is manual, per `quickstart.md`, via `workflow_dispatch` / synthetic PR-merge runs against a scratch spec, cross-checked against `docs/architecture.md`'s Stage 2 design and the constitution — the same validation approach every prior wing-commander stage feature has used (e.g. `specs/003-tasks-stage/plan.md`).

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), triggered by repository `pull_request` events and `workflow_dispatch`.

**Project Type**: Single project — CI/CD automation living entirely under `.github/workflows/`, reusing existing `.specify/` and `.claude/` assets. No frontend/backend split.

**Performance Goals**: N/A (event-driven CI jobs, not a latency-sensitive service). The `auto` path adds exactly one deterministic verification step and one `gh workflow run` dispatch — negligible added runtime, no additional agent turns.

**Constraints**: Gate configuration MUST be trusted maintainer input, never derived from issue/comment content (FR-010, constitution V) — satisfied by using a repository variable, which only a maintainer with repo-settings access can set. Invalid configuration MUST fall back to enabled and be surfaced, never silently weaken a gate (FR-008). A bypassed gate MUST NOT let a failed/empty artifact cascade into the next stage (FR-007) — enforced by a deterministic verification step before any dispatch. Least-privilege permissions per constitution V: the only new grant is `actions: write` on the `plan` job, needed solely for the `auto`-mode dispatch.

**Scale/Scope**: Two new `workflow_call` inputs (`plan-review`, `next-workflow`) and a handful of new steps on one existing workflow file (`plan.yml`), one new line in its wrapper (`wing-commander-3-plan.yml`), and documentation updates (`docs/setup.md`, `docs/adoption.md`, `docs/architecture.md`, `specs/010-reusable-pipeline/contracts/stage-interfaces.md`). No new workflow files. Concurrent specs remain independent — `plan.yml`'s existing `concurrency: { group: wing-commander-<spec-dir> }` is unchanged and already serializes only within one spec.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself built through the pipeline (issue #74 → this spec → this plan → tasks → implementation), and turns a documented, fixed Stage 2 design (`docs/architecture.md`) into a configurable one other stages (and adopters) can point to as the worked example for "how to add a bypassable gate." **Pass.**
- **II. Cost-Conscious Model Tiering**: No new agent invocation is introduced. The existing plan agent step keeps `claude-sonnet-5` with an explicit `--max-turns` budget; the new verification and dispatch steps are deterministic (no model call at all), consistent with how `tasks.yml`'s own `auto`-mode verification and dispatch already work. **Pass.**
- **III. Simple, GitHub-Native Interaction**: Gate state lives in a repository variable (Settings → Variables, no external dashboard) and its effect is legible entirely from the lifecycle issue (comment states whether the gate was bypassed) and ordinary PR review (`pr` mode is unchanged). **Pass.**
- **IV. Automation-First**: The whole point of this feature is removing a manual step (merging the plan PR) when a maintainer opts in; the one manual step that can still exist (`pr` mode's human merge) is explicitly configured, reported to the issue, and is the same shape as the tasks stage's own existing human gate. **Pass.**
- **V. Security (NON-NEGOTIABLE)**: Gate configuration is a repository variable — trusted maintainer input, never derived from issue/comment content (FR-010). Gates 1, 2, and 4 (label-gated entry, and the two merges into `main`) are untouched and remain mandatory — no constitution amendment needed (FR-011). The bot still never merges or approves a PR (the `auto` path commits directly to the spec branch instead of merging one). The only new permission is `actions: write`, scoped to workflow dispatch, on the same job that already holds `contents: write`/`pull-requests: write`/`issues: write`. **Pass.**
- **VI. Portability**: No new dependency on anything outside the consuming repository's own checkout; the new repository variable is read the same way `WING_COMMANDER_TASKS_REVIEW` already is, from the consuming repo's own `vars.*`, never hardcoded or bundled with wing-commander itself. **Pass.**

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/014-configurable-gates/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   └── plan-workflow.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
└── workflows/
    ├── plan.yml                    # Gains `plan-review` + `next-workflow` inputs,
    │                                 a mode-resolution step (with FR-008 surfacing),
    │                                 an `auto`-mode direct-commit path, a deterministic
    │                                 post-commit verification step (FR-007), and an
    │                                 `auto`-mode dispatch step. `actions: write` added
    │                                 to the `plan` job's permissions.
    └── wing-commander-3-plan.yml   # One new line wiring
                                      vars.WING_COMMANDER_PLAN_REVIEW → plan-review,
                                      and next-workflow: wing-commander-4-tasks.yml

docs/
├── setup.md                        # New row in the repository-variables table
├── adoption.md                     # `plan` section's Inputs row + wrapper example updated;
│                                     vars-mapping table unaffected (no rename, new variable)
└── architecture.md                 # Stage 2 section rewritten to describe both modes,
                                      mirroring the existing Stage 3 (tasks) prose

specs/010-reusable-pipeline/
└── contracts/
    └── stage-interfaces.md         # `reusable-plan.yml` row gains the two new inputs
```

Unmodified by this feature: `.github/workflows/intake.yml` (Gate 1),
`.github/workflows/finalize.yml` (Gate 4), `.github/workflows/tasks.yml` and
`wing-commander-4-tasks.yml` (already-configurable tasks step — read, not
changed), `.github/workflows/cleanup.yml` (its existing generic
`plan/*`-closed-unmerged stalled path already covers `pr` mode with no
changes needed, and `auto` mode never opens a PR for it to watch),
`.claude/skills/speckit-plan/SKILL.md`, and every `.specify/` script/template.

**Structure Decision**: This is a single-project CI/CD feature — there is no
`src/`/`tests/` split to choose between. The only production artifact is
`.github/workflows/plan.yml` (extended, not replaced) plus its wrapper's one
new line. Documentation updates keep the adoption docs and the stage-contract
reference truthful, following this repo's established practice of updating
those alongside any stage-behavior change (see `003-tasks-stage`'s and
`010-reusable-pipeline`'s plans for the same pattern).

## Complexity Tracking

> Not applicable — no Constitution Check violations.
