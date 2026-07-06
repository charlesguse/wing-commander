# Implementation Plan: Tasks Stage — Plan to Task List

**Branch**: `plan/003-tasks-stage` | **Date**: 2026-07-05 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-tasks-stage/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Implement the pipeline's third stage: when a plan pull request merges into a
specification's persistent `spec/NNN-slug` branch, run `/speckit-tasks` to
derive `tasks.md` from the accepted plan, then hand off to implementation.
The repo-level variable `SPECKIT_TASKS_REVIEW` (default `auto`) chooses
between committing `tasks.md` directly and auto-dispatching
`speckit-5-implement.yml`, or opening a `tasks/NNN-slug` review PR whose
merge performs the same dispatch. Either path updates `spec-meta.json`
(`stage: "tasks"`), flips the lifecycle issue's `stage:*` label, and posts a
task summary comment. This turns the existing stub workflow
`.github/workflows/speckit-4-tasks.yml` into a full implementation, following
the same shape as the already-implemented plan stage
(`.github/workflows/speckit-3-plan.yml`, `specs/002-plan-stage/`).

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps), YAML (workflow definitions) — same as every other pipeline stage.

**Primary Dependencies**: GitHub Actions, `gh` CLI, `jq`, `anthropics/claude-code-action@v1`, the repo's own `.github/actions/speckit-context` composite action, and the `/speckit-tasks` skill (`.claude/skills/speckit-tasks/SKILL.md`, unmodified).

**Storage**: `specs/NNN-slug/spec-meta.json` (durable lifecycle record, JSON) and git branches (`spec/NNN-slug`, `plan/NNN-slug`, `tasks/NNN-slug`) — no database.

**Testing**: No automated test suite exists for these workflows (none exists for stages 1–2 either); validated per `quickstart.md` via manual `workflow_dispatch` / synthetic PR-merge runs against a scratch spec, plus conformance against `docs/architecture.md`'s Stage 3 design and the constitution.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), triggered by repository `pull_request` events and `workflow_dispatch`.

**Project Type**: Single project — CI/CD automation living entirely under `.github/workflows/` and `.github/actions/`, reusing existing `.specify/` and `.claude/` assets. No frontend/backend split.

**Performance Goals**: N/A (event-driven CI jobs, not a latency-sensitive service). Bounded by `--max-turns` on the agent step per constitution II.

**Constraints**: Idempotent under duplicate `pull_request: closed` notifications (FR-011); never merges or approves its own PRs (FR-010); least-privilege `--allowedTools`/`permissions:` per constitution V; no PAT — GitHub App installation token via `speckit-context`; no web tools in this agent step; only trusted refs checked out.

**Scale/Scope**: One workflow file (`speckit-4-tasks.yml`) plus one new job clause for the stalled path; concurrent specs run independently (`concurrency: speckit-tasks-<slug>`), matching the plan stage's concurrency model.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself built through the pipeline (issue #8 → this spec → this plan → tasks → implementation), and turns a documented stub (`docs/architecture.md` §Stage 3) into a working example other stages can point to. **Pass.**
- **II. Cost-Conscious Model Tiering**: Task generation runs on `claude-sonnet-5` (constitution: "specification, clarification, planning, and task generation" → sonnet), with an explicit `--max-turns` budget, matching the plan stage's agent step. No haiku step is introduced since no new triage/labeling/summarization task exists beyond what the sonnet agent itself produces (see research.md decision on the issue-comment summary). **Pass.**
- **III. Simple, GitHub-Native Interaction**: Status is visible entirely via the lifecycle issue (label + comment); review-required mode course-corrects via ordinary PR review/merge. **Pass.**
- **IV. Automation-First**: Default path (`auto`) requires zero manual steps between plan-merge and implementation dispatch; the one manual step that can exist (`pr` mode's human merge) is explicitly configured, reported to the issue, and is the same shape as the plan stage's own human gate. **Pass.**
- **V. Security**: Issue/spec content is treated as data, never interpolated as instructions; commenter/actor trust boundaries aren't touched by this stage (it's PR-merge triggered, not comment triggered) but the composite action and App-token pattern are reused unchanged; web tools disabled; only `spec/**`/`plan/**`/`tasks/**` repo-local branches are checked out, never fork heads; humans merge every PR, the bot never approves. **Pass.**

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/003-tasks-stage/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── tasks-workflow.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   └── speckit-4-tasks.yml     # Stub → full implementation (this feature's primary artifact)
└── actions/
    └── speckit-context/        # Reused unchanged (App token + label-based spec resolution)

.claude/
└── skills/
    └── speckit-tasks/
        └── SKILL.md            # Reused unchanged (already generic spec-kit skill)

.specify/
├── scripts/bash/
│   ├── setup-tasks.sh          # Reused unchanged
│   └── common.sh               # Reused unchanged
└── templates/
    └── tasks-template.md       # Reused unchanged

docs/
└── architecture.md             # Stage 3 section already documents the target design;
                                 # no changes expected, cross-checked during planning
```

**Structure Decision**: This is a single-project CI/CD feature — there is no
`src/`/`tests/` split to choose between. The only production artifact is
`.github/workflows/speckit-4-tasks.yml` (going from the current stub to a
full implementation with a `tasks` job and a `stalled` job, mirroring
`speckit-3-plan.yml`'s two-job shape). All other referenced paths
(`speckit-context`, the `/speckit-tasks` skill, `setup-tasks.sh`,
`tasks-template.md`) already exist and are consumed as-is.

## Complexity Tracking

> Not applicable — no Constitution Check violations.
