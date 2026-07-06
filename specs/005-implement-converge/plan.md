# Implementation Plan: Implement/Converge Stage — Iterative Build to Convergence

**Branch**: `plan/005-implement-converge` | **Date**: 2026-07-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-implement-converge/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Implement the pipeline's fourth stage: turn the stub
`.github/workflows/speckit-5-implement.yml` (`workflow_dispatch` inputs
`spec_dir`, `issue`, `iteration`, already correct) into the build-and-reassess
loop `docs/architecture.md` designs. Each dispatch checks out the
specification's persistent `spec/NNN-slug` branch, runs `/speckit-implement`
then `/speckit-converge` in one agent step, and commits both directly to
that branch (no per-iteration branch or PR — see `research.md`). A
deterministic post-step reads the resulting commit history to decide,
without any agent turns, whether the cycle converged (no `converge:`-prefixed
commit landed) or not (one did): converged hands off to
`speckit-6-finalize.yml` with `converged=true`; not converged re-dispatches
this same workflow at `iteration + 1`, unless the repo-configured
`SPECKIT_MAX_ITERATIONS` cap (default 5) has been reached, in which case it
reports the remaining work on the lifecycle issue and hands off to finalize
with `converged=false`. A separate `claude-haiku-4-5` step posts a short
progress comment every cycle. The implementation model defaults to
`vars.SPECKIT_IMPLEMENT_MODEL` (`claude-sonnet-5`), escalating to
`claude-opus-4-8` via the `model:opus` issue label; an outright pass failure
(as opposed to completing without converging) auto-retries the same
iteration once on the next tier up, or marks the specification `stalled` if
already on the top tier or the retry also fails. This follows the same
two-job shape (main stage + a terminal failure path) as the already-implemented
plan and tasks stages (`specs/002-plan-stage/`, `specs/003-tasks-stage/`).

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps), YAML (workflow definitions) — same as every other pipeline stage.

**Primary Dependencies**: GitHub Actions, `gh` CLI, `jq`, `anthropics/claude-code-action@v1`, the repo's own `.github/actions/speckit-context` composite action, and the `/speckit-implement` and `/speckit-converge` skills (`.claude/skills/speckit-implement/SKILL.md`, `.claude/skills/speckit-converge/SKILL.md`, both unmodified). Dispatches `.github/workflows/speckit-6-finalize.yml` (remains a stub — out of scope for this feature, this stage only calls it) and re-dispatches itself.

**Storage**: `specs/NNN-slug/spec-meta.json` (durable lifecycle record, JSON) and one git branch per spec (`spec/NNN-slug` — no new branch kind introduced; see `research.md`'s branch decision) — no database.

**Testing**: No automated test suite exists for these workflows (none exists for stages 1–3 either); validated per `quickstart.md` via manual `workflow_dispatch` runs against a scratch spec (including a forced low `SPECKIT_MAX_ITERATIONS` and a forced-failure run), plus conformance against `docs/architecture.md`'s Stage 4 design and the constitution.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), triggered exclusively by `workflow_dispatch` — this stage has no natural GitHub PR/issue event of its own (chaining is explicit re-dispatch, per `docs/architecture.md`'s "State model" section).

**Project Type**: Single project — CI/CD automation living entirely under `.github/workflows/`, reusing existing `.specify/` and `.claude/` assets. No frontend/backend split.

**Performance Goals**: N/A (event-driven CI jobs, not a latency-sensitive service). Each cycle is bounded by `--max-turns` on its agent step per constitution II; the loop overall is bounded by `SPECKIT_MAX_ITERATIONS` (FR-005).

**Constraints**: Idempotent under duplicate/out-of-order dispatches for the same iteration (FR-011); never opens, approves, or merges a PR (FR-015); guarantees exactly one finalize hand-off per specification, converged or not (FR-007); least-privilege `--allowedTools`/`permissions:` per constitution V; no PAT — GitHub App installation token via `speckit-context`; no web tools; only the `spec/NNN-slug` ref is checked out, never a fork head.

**Scale/Scope**: One workflow file (`speckit-5-implement.yml`) going from stub to a two-job implementation (`implement` main loop job + a `stalled` job for the exhausted-retry failure path); concurrent specs run independently (`concurrency: speckit-<spec_dir>`, already present in the stub and shared with the finalize stage's stub group so the two never overlap for the same spec).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself built through the pipeline (issue #15 → this spec → this plan → tasks → implementation — which will, notably, be the *first* specification actually built by running through this very stage once it exists), and turns a documented stub (`docs/architecture.md` §Stage 4) into a working example. **Pass.**
- **II. Cost-Conscious Model Tiering**: Implement/converge cycles run on `vars.SPECKIT_IMPLEMENT_MODEL` (default `claude-sonnet-5`) or `claude-opus-4-8` via the `model:opus` label, matching the constitution's tiering table exactly; the per-cycle progress comment runs on `claude-haiku-4-5`, matching "diff summaries" in the same table (research.md). Every agent step declares `--max-turns`. The FR-013 failure-retry ladder is the same two rungs (sonnet → opus) rather than introducing an undocumented Haiku code-writing tier (research.md). **Pass.**
- **III. Simple, GitHub-Native Interaction**: All progress (per-cycle updates, cap-reached remaining work, stalled failures) is visible on the lifecycle issue alone (SC-004); no external dashard or new interaction surface is introduced. **Pass.**
- **IV. Automation-First**: The entire build-and-reassess loop — implementation, convergence reassessment, cycle repetition, and the finalize hand-off (converged or not) — runs with zero manual steps (SC-001); the sole manual step that can arise (a `stalled` specification after an exhausted retry) is explicitly reported to the lifecycle issue with restart instructions, never silently assumed. **Pass.**
- **V. Security**: Spec/plan/tasks content is treated as data the agent reads, never as instructions (framed identically to the plan/tasks stages' prompts); this stage is `workflow_dispatch`-only, so the comment-author/commenter trust-boundary checks constitution V requires for issue/comment-triggered stages don't apply here, but the App-token pattern, least-privilege `--allowedTools`, and no-web-tools rules are reused unchanged; only `spec/NNN-slug` is checked out, never a fork head; the bot never opens, approves, or merges any PR (FR-015) — it only commits to the spec branch and dispatches the next workflow. **Pass.**

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/005-implement-converge/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── implement-workflow.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   ├── speckit-5-implement.yml  # Stub → full implementation (this feature's primary artifact)
│   └── speckit-6-finalize.yml   # Reused unchanged as a dispatch target (still a stub; out of scope)
└── actions/
    └── speckit-context/         # Reused unchanged (App token + label-based spec resolution)

.claude/
└── skills/
    ├── speckit-implement/
    │   └── SKILL.md             # Reused unchanged
    └── speckit-converge/
        └── SKILL.md             # Reused unchanged (append-only contract this stage's loop condition relies on)

.specify/
└── scripts/bash/
    ├── check-prerequisites.sh   # Reused unchanged (invoked by both skills)
    └── common.sh                # Reused unchanged

docs/
├── architecture.md              # Stage 4 section already documents the target design;
│                                 # no changes expected, cross-checked during planning
└── setup.md                     # Already documents SPECKIT_IMPLEMENT_MODEL,
                                  # SPECKIT_MAX_ITERATIONS, and the stage:implement /
                                  # stage:review / model:opus labels this stage consumes
```

**Structure Decision**: This is a single-project CI/CD feature — there is no
`src/`/`tests/` split to choose between. The only production artifact is
`.github/workflows/speckit-5-implement.yml` (going from the current stub to a
full implementation with an `implement` job and a `stalled` job, mirroring
the plan/tasks stages' two-job shape, re-keyed to this stage's own failure
mode — an exhausted retry rather than a closed-unmerged PR). All other
referenced paths (`speckit-context`, the `/speckit-implement` and
`/speckit-converge` skills, `speckit-6-finalize.yml`) already exist and are
consumed as-is; this feature does not modify `speckit-6-finalize.yml`
beyond calling it with the inputs it already declares.

## Complexity Tracking

> Not applicable — no Constitution Check violations.
