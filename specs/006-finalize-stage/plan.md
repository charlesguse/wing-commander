# Implementation Plan: Finalize Stage — Final Pull Request & Manual-Task Report

**Branch**: `plan/006-finalize-stage` | **Date**: 2026-07-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-finalize-stage/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Implement the pipeline's fifth stage: turn the stub
`.github/workflows/speckit-6-finalize.yml` (`workflow_dispatch` inputs
`spec_dir`, `issue`, `converged`, already correct per
`docs/architecture.md` §Stage 5) into the finalize-and-hand-to-review flow.
A dispatched run resolves and validates the hand-off (FR-014), checks
whether a final pull request for this specification already exists and, if
so, stops there (FR-012 idempotency), checks whether the spec branch
actually differs from `main` and, if not, reports the anomaly instead of
opening an empty PR (FR-013), then runs a single read-only
`claude-haiku-4-5` step that writes two plain-text artifacts — a
human-readable change summary and the remaining-manual-work list extracted
from `tasks.md` — to known temp-file paths. Everything after that is
deterministic bash: assemble the final PR body from those two files plus
git-computed "how to see it" facts (a compare link and the changed-file
list) and, when `converged=false`, a prominent ⚠️ not-fully-converged
banner; open the PR `spec/NNN-slug → main` with `gh pr create`; verify it
was actually created (FR-015); only then commit `spec-meta.json`
(`stage: "review"`) directly onto `spec/NNN-slug` (no separate work branch —
same direct-commit pattern the implement/converge stage already uses) and
post the *same* remaining-manual-work file's content verbatim as an issue
comment, guaranteeing the PR and the issue never disagree (SC-003) without
relying on an agent repeating itself. The label flips to `stage:review`
last, only once every step before it has verifiably succeeded. This mirrors
the plan/tasks stages' precedent of "agent proposes, deterministic step
verifies and advances state," reserving the LLM turn for the two things
that actually need judgment (narrative summary, classifying which task-list
items are human-only) and keeping every state transition and GitHub write
in this stage's own deterministic bash, per `docs/architecture.md`'s Stage 5
sketch ("Haiku step summarizes ... Plain `gh pr create` ... Comment the
same manual-task list").

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps), YAML (workflow definitions) — same as every other pipeline stage.

**Primary Dependencies**: GitHub Actions, `gh` CLI, `jq`, `anthropics/claude-code-action@v1`, the repo's own `.github/actions/speckit-context` composite action. Unlike the plan/tasks/implement stages, this stage does not invoke a `/speckit-*` skill — its behavior (diff summary, PR body assembly, issue report, stage advance) is pipeline orchestration with no corresponding spec-kit template, matching `docs/architecture.md`'s Stage 5 design, which names plain steps and a Haiku summary, not a skill. This stage is a terminal hand-off point: it is dispatched only by the implement/converge stage (`speckit-5-implement.yml`, already implemented) and dispatches nothing further itself — the next stage (cleanup) is triggered by a human merging the final PR, an event this stage does not fire.

**Storage**: `specs/NNN-slug/spec-meta.json` (durable lifecycle record, JSON, this stage advances `stage` to `"review"`) and the existing `spec/NNN-slug` branch (this stage's only write to it is that one metadata commit) — no database. Two throwaway plain-text files under `${{ runner.temp }}` (change-summary and remaining-manual-work) are the hand-off between the Haiku step and the deterministic steps that follow it within the same job; nothing under `${{ runner.temp }}` is committed or persisted past the run.

**Testing**: No automated test suite exists for any pipeline stage (1–4 are all validated manually); this stage is validated the same way, per `quickstart.md`'s `workflow_dispatch` scenarios against a scratch spec (including a forced no-diff spec, a forced missing-artifact spec, a duplicate dispatch, and both `converged=true`/`converged=false`), plus conformance against `docs/architecture.md`'s Stage 5 design and the constitution.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), triggered exclusively by `workflow_dispatch` (`spec_dir`, `issue`, `converged`) — this stage has no natural GitHub PR/issue event of its own, matching the stub's existing trigger and `docs/architecture.md`'s Stage 5 trigger.

**Project Type**: Single project — CI/CD automation living entirely under `.github/workflows/`, reusing the existing `.github/actions/speckit-context` composite action. No frontend/backend split.

**Performance Goals**: N/A (event-driven CI job, not a latency-sensitive service). The one agent step is read-only summarization with a modest `--max-turns` per constitution II (no code is written or committed by it).

**Constraints**: Idempotent under duplicate/out-of-order dispatch for the same specification — an already-existing final PR is reused, never duplicated, and no duplicate remaining-manual-work comment is posted (FR-012). Never opens an empty PR when the spec branch has no diff against `main` (FR-013); never guesses which specification to finalize when the hand-off doesn't match a valid one (FR-014); surfaces its own failures (summarization or PR creation) on the lifecycle issue rather than dropping the specification silently (FR-015). Never approves or merges the final PR — that is reserved for a human (FR-011). Least-privilege `--allowedTools`/`permissions:` per constitution V; no PAT — GitHub App installation token via `speckit-context`; no web tools; only `spec/NNN-slug` and `main` are checked out/fetched, never a fork head.

**Scale/Scope**: One workflow file (`speckit-6-finalize.yml`) going from stub to a single-job implementation (no separate failure-path job is needed — an own-work failure is reported inline in the same job, since unlike the implement stage there is no retry-at-a-higher-tier ladder to run: the one agent step here is a fixed-tier summarization, not code generation). Concurrent specs run independently (`concurrency: speckit-<spec_dir>`, already present in the stub and shared with the implement stage's group so the two never overlap for the same spec).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself built through the pipeline (issue #21 → this spec → this plan → tasks → implementation), and turns a documented stub (`docs/architecture.md` §Stage 5) into a working example — the same stage that will, in turn, open this very repository's *own* first finalize PR once implemented and dispatched. **Pass.**
- **II. Cost-Conscious Model Tiering**: The sole agent step (change summary + remaining-manual-work extraction) runs on `claude-haiku-4-5`, matching the constitution's tiering table entry for "diff summaries" exactly — there is no code-writing agent step in this stage at all, so no higher tier is ever needed. The step declares `--max-turns`. **Pass.**
- **III. Simple, GitHub-Native Interaction**: The final PR and the mirrored lifecycle-issue comment are the only two surfaces this stage produces; both are ordinary GitHub objects (a PR, an issue comment, a label) requiring no external dashboard. A maintainer following only the lifecycle issue sees the remaining manual work and the stage advance without opening the PR (SC-004). **Pass.**
- **IV. Automation-First**: Summarizing the diff, extracting remaining manual work, opening the final PR, mirroring the report to the issue, and advancing the lifecycle stage are all automatic (SC-001–SC-004); the one manual step that must survive — a human reviewing and merging the final PR — is explicit by design (FR-011) and is exactly the "review the final implementation PR" step constitution IV reserves for the requester. **Pass.**
- **V. Security**: `spec.md`/`tasks.md` content is treated as data the Haiku step reads, never as instructions (framed identically to every other stage's agent prompt); this stage is `workflow_dispatch`-only, so the comment-author/commenter trust checks constitution V requires for issue/comment-triggered stages don't apply, but the App-token pattern, least-privilege `--allowedTools`, and no-web-tools rules are reused unchanged. Only `spec/NNN-slug` and `main` are checked out/fetched — never a fork head. The bot opens the final PR but never approves or merges it (FR-011); a human merge is what the (out-of-scope) cleanup stage reacts to. **Pass.**
- **VI. Portability**: No new project-specific concept is introduced beyond what stages 1–4 already established (`spec-meta.json`, `spec/NNN-slug`, the lifecycle issue); this stage's only artifact (`speckit-6-finalize.yml`) resolves every path relative to the checkout and does not hardcode the repository name (uses `${{ github.repository }}` where a repo-qualified link is needed). **Pass.**

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/006-finalize-stage/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── finalize-workflow.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   └── speckit-6-finalize.yml   # Stub → full implementation (this feature's sole artifact)
└── actions/
    └── speckit-context/         # Reused unchanged (App token + label-based spec resolution)

.specify/
└── scripts/bash/
    └── common.sh                 # Not invoked by this stage (no /speckit-* skill runs here);
                                   # listed only because other stages share this directory

docs/
├── architecture.md              # Stage 5 section already documents the target design;
│                                 # no changes expected, cross-checked during planning
└── setup.md                     # Already documents the stage:review label this stage sets
```

**Structure Decision**: This is a single-project CI/CD feature — there is no
`src/`/`tests/` split to choose between. The only production artifact is
`.github/workflows/speckit-6-finalize.yml` (going from the current stub to a
single-job implementation — unlike the implement stage's two-job
implement/stalled shape, this stage has no retry ladder that needs a
separate failure-path job; an own-work failure is reported inline in the
same job's steps). The only other path this feature touches is
`.github/actions/speckit-context`, reused as-is exactly like every prior
stage.

## Complexity Tracking

> Not applicable — no Constitution Check violations.
