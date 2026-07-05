# Implementation Plan: Plan Stage — Spec to Implementation Plan

**Branch**: `plan/002-plan-stage` | **Date**: 2026-07-05 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-plan-stage/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

When a draft specification pull request merges into `main`, this stage creates
the specification's persistent `spec/NNN-slug` integration branch (if it
doesn't already exist), runs `/speckit-plan` against the specification to
generate an implementation plan and its supporting design artifacts, opens a
pull request containing that plan targeting the persistent branch (never
`main`), updates the durable `spec-meta.json` lifecycle record, and reports
progress on the specification's lifecycle issue — creating that issue first
if the specification arrived hand-submitted. The stage is a single new
GitHub Actions workflow (`speckit-3-plan.yml`) that reuses the existing
`speckit-context` composite action and the generic `/speckit-plan` skill;
duplicate merge notifications and re-runs are made idempotent by checking for
the existence of `spec/NNN-slug` and `plan/NNN-slug` before acting, and a plan
PR closed without merging is handled by a second job that marks the
specification `stalled` rather than leaving it silently "in planning."

## Technical Context

**Language/Version**: GitHub Actions workflow YAML + POSIX/Bash (runner default `bash`, matching stage 1's intake workflow); no application language — this feature is pipeline automation, not a deployed service.

**Primary Dependencies**: `anthropics/claude-code-action@v1` (runs `/speckit-plan`, model `claude-sonnet-5` per constitution II), `actions/checkout@v4`, `actions/create-github-app-token@v1` (via the existing `./.github/actions/speckit-context` composite action), `actions/upload-artifact@v4`, GitHub CLI (`gh`), `jq`, and the existing spec-kit v0.12.4 scripts under `.specify/scripts/bash/` (`setup-plan.sh`, `check-prerequisites.sh`, `update-agent-context.sh`).

**Storage**: None beyond git itself and GitHub's own state (branches, PRs, issues, labels). The durable lifecycle record is `specs/NNN-slug/spec-meta.json`, committed to the persistent `spec/NNN-slug` branch.

**Testing**: No unit/integration test harness — matching the precedent set by stage 1 (intake). Validated by dogfooding: running the real workflow against this repository's own specs (see `quickstart.md`) and inspecting the resulting branches, PR, labels, and issue comment.

**Target Platform**: GitHub Actions (`ubuntu-latest`), acting against the GitHub REST API through `gh` and the `speckit-bot` GitHub App installation token.

**Project Type**: Single project — repository CI/CD automation (a workflow file + reused composite action + reused skill), not an application with its own runtime.

**Performance Goals**: N/A (event-driven, human-paced; bounded by the `--max-turns 80` budget on the planning agent step and the Actions job's own timeout, not a throughput target).

**Constraints**: No PAT anywhere (App token only, constitution V); the bot must never merge or approve a PR; each job requests only the permissions it needs; only trusted refs are checked out (`main`, `spec/*`, never a fork PR head); one planning attempt per spec (idempotent under duplicate `pull_request: closed` deliveries); stages of the same spec serialize via a `speckit-plan-<slug>` concurrency group while different specs run in parallel.

**Scale/Scope**: One new workflow file (`speckit-3-plan.yml`) with two jobs (`plan`, `stalled`); reuses `speckit-context` and `/speckit-plan` unmodified. Handles arbitrarily many concurrent specifications, one planning attempt at a time per specification.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — dogfooded | This very feature is planned by having `/speckit-plan` run against `specs/002-plan-stage/spec.md`, and the resulting workflow is what will plan every future spec, including its own. | PASS |
| II. Cost-conscious model tiering | The generative step declares `--model claude-sonnet-5` (planning tier) and `--max-turns 80`; no untiered or unbounded agent step is introduced. | PASS |
| III. Simple, GitHub-native interaction | All state changes are ordinary GitHub objects (branches, a PR, issue labels, an issue comment) — no external dashboard or bespoke CLI. | PASS |
| IV. Automation-First | Branch creation, plan generation, PR creation, lifecycle-record update, and issue reporting are all automatic; the only manual step (reviewing/merging the plan PR) is inherent to the stage's human gate and is reported via the PR itself. | PASS |
| V. Security | Uses the `speckit-bot` App token (no PAT); prompt interpolates only the validated slug and an integer issue number, framing spec content as data; `--disallowedTools "WebSearch,WebFetch"`; least-privilege `permissions:` block per job; only `main` and `spec/*`/`plan/*` refs are checked out, never a fork head; the bot never merges or approves. | PASS |

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/002-plan-stage/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   └── speckit-3-plan.yml      # This feature: the plan-stage workflow (jobs: plan, stalled)
└── actions/
    └── speckit-context/        # Existing composite action, reused unmodified
        └── action.yml

.claude/
└── skills/
    └── speckit-plan/           # Existing generic plan skill, invoked unmodified
        └── SKILL.md

.specify/
├── scripts/bash/                # Existing spec-kit scripts, invoked unmodified
│   ├── setup-plan.sh
│   ├── check-prerequisites.sh
│   └── update-agent-context.sh
└── templates/
    └── plan-template.md         # Existing template, filled per-feature

docs/
└── architecture.md              # Updated to document Stage 2 as implemented
```

**Structure Decision**: Single project (repository automation). This feature
adds exactly one new workflow file, `.github/workflows/speckit-3-plan.yml`,
and reuses the existing `speckit-context` composite action and
`/speckit-plan` skill without modification — matching the pattern
established by stage 1 (intake). No `src/`/`tests/` application tree applies;
the "source" is the workflow YAML plus the bash it inlines.

## Complexity Tracking

*No violations — table intentionally omitted.*
