# Implementation Plan: Surface Per-Run Agent Metrics for Pipeline Tuning (Tier 1)

**Branch**: `plan/009-agent-metrics` | **Date**: 2026-07-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/009-agent-metrics/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Every agent-invoking pipeline stage already writes its full execution
transcript to `${{ runner.temp }}/claude-execution-output.json` and uploads
it as the `claude-execution-output` artifact, but reading it today means
downloading that artifact and parsing JSON by hand. This feature's
committed scope is tier 1 only (FR-012): a new composite action,
`.github/actions/speckit-metrics-summary`, invoked once immediately after
every existing `claude-code-action` step across all nine call sites in
eight workflow files (`speckit-1` through `speckit-7`, plus
`speckit-rebase.yml`). It reads that same transcript file — already sitting
in the runner's temp directory, no download needed — and appends a
concise Markdown block to `$GITHUB_STEP_SUMMARY`: model, turns used against
the run's configured `--max-turns` budget, duration, tokens, and cost, with
a visible warning when a run consumed at or above 80% of its turn budget
(FR-004). No agent call is needed for this (research.md D1) — it's pure
`bash`/`jq` over already-produced JSON, so it costs nothing and can never
change a stage's own outcome (FR-011). A missing or unparseable transcript
degrades to a plain "metrics unavailable" line rather than failing the
stage (FR-009). Tiers 2 (lifecycle-issue rollup) and 3 (durable trend
record) are explicitly deferred — this plan builds neither, only the
per-run extraction they would eventually share.

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps), YAML (workflow
and composite-action definitions), `jq` — same toolchain as every other
pipeline stage; no new language or runtime.

**Primary Dependencies**: GitHub Actions, `jq` (preinstalled on
`ubuntu-latest`), `actions/upload-artifact@v4` (already present at every
call site, unchanged by this feature). No new external dependency, no SDK,
no agent invocation of any kind for this feature's own logic (research.md
D1).

**Storage**: None persisted. This feature only *reads* the already-produced
`claude-execution-output.json` from the runner's own temp directory
(ephemeral, job-scoped) and only *writes* to `$GITHUB_STEP_SUMMARY`
(ephemeral, run-scoped, GitHub-native). It never touches `spec-meta.json`,
never commits anything, and never creates a new artifact — tiers 2/3, which
would need durable storage, are out of scope (FR-012).

**Testing**: No automated test suite exists for any pipeline stage in this
repository; this feature is validated the same way stages 1–8 were —
`quickstart.md`'s scenarios run against a real scratch workflow dispatch
for the happy path, and the composite action invoked directly against
hand-crafted fixture transcripts for the missing/malformed/partial-field
edge cases (research.md D9).

**Target Platform**: GitHub Actions (`ubuntu-latest` runners) — added as one
additional step inside each of the nine existing agent-invoking steps
across `speckit-1-intake.yml`, `speckit-2-clarify.yml`,
`speckit-3-plan.yml`, `speckit-4-tasks.yml` (two mutually-exclusive
invocations, one call site), `speckit-5-implement.yml` (three
invocations — cycle, retry, progress comment), `speckit-6-finalize.yml`,
`speckit-7-cleanup.yml`, and `speckit-rebase.yml`.

**Project Type**: Single project — CI/CD automation under
`.github/workflows/` and a new `.github/actions/` composite action, mirroring
the shape of the existing `speckit-context` composite. No frontend/backend
split.

**Performance Goals**: N/A (a single `jq` parse of an already-in-memory
file, sub-second per invocation). Adds no measurable wall-clock cost to any
stage.

**Constraints**: MUST NOT alter any stage's own behavior, outcome, or exit
code (FR-011) — the new step is purely additive and, on the fixed
`claude-code-action` failure/timeout path, still runs (`if: always()`) so a
failed run still gets a metrics line. MUST NOT invoke or wait on any agent
(FR-011, research.md D1). MUST run once per agent invocation and, for jobs
with more than one invocation, before the next invocation overwrites the
shared temp file at the same fixed path (research.md D3/D4 — this is the
one genuinely fragile ordering constraint in the whole feature, and it
already has a working precedent in `speckit-5-implement.yml`'s existing
per-invocation artifact-upload placement). MUST degrade per-field rather
than all-or-nothing when the transcript's result record is present but
incomplete (spec.md edge case). MUST remain entirely GitHub-native — no
external dashboard, service, or dependency (FR-010, SC-006).

**Scale/Scope**: One new composite action
(`.github/actions/speckit-metrics-summary`) plus one new step wired into
each of the nine existing agent-invocation sites across eight workflow
files. No workflow's triggers, permissions, concurrency groups, or
existing steps change — this feature only adds steps, it never removes or
reorders anything that exists today (beyond inserting the new step
immediately after each agent step).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: Built through the pipeline itself (issue #16 → this spec →
  this plan → tasks → implementation); once shipped, every subsequent
  pipeline stage's own workflow runs — including this very plan stage's
  own `speckit-3-plan.yml` run — will carry the metrics summary this
  feature adds, making it its own first example. **Pass.**
- **II. Cost-Conscious Model Tiering**: This feature adds **zero** agent
  invocations (research.md D1) — the metrics step is deterministic
  `bash`/`jq`, the cheapest possible outcome, and it doesn't touch any
  existing step's `--model`/`--max-turns` declaration. **Pass.**
- **III. Simple, GitHub-Native Interaction**: The only new surface is
  `$GITHUB_STEP_SUMMARY` on the run a maintainer is already looking at —
  no new dashboard, no external service, no new issue-comment noise (tier
  2 is explicitly deferred, FR-012). **Pass.**
- **IV. Automation-First**: Removes a manual step (downloading an artifact
  and parsing JSON by hand) with no new manual step introduced anywhere.
  **Pass.**
- **V. Security**: The new composite action takes no secrets, mints no
  tokens, and makes no GitHub API or network calls — it only reads a local
  file already sitting in the runner's temp directory and writes to
  `$GITHUB_STEP_SUMMARY`. It carries no elevated permissions beyond what
  the step it rides alongside already has, and — because it never invokes
  an agent (II above) — none of constitution V's untrusted-content/
  commenter-trust rules apply to it; it doesn't read issue/comment bodies
  at all. **Pass.**
- **VI. Portability**: The new composite action lives under this
  repository's own `.github/actions/`, the same location
  `speckit-context` already establishes as the pattern for pipeline-internal
  shared logic — nothing about it is speckit-action-specific or hardcodes
  this repository's name/owner; every path it touches is relative to the
  checkout. **Pass.**

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/009-agent-metrics/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/             # Phase 1 output (/speckit-plan command)
│   ├── speckit-metrics-summary-action.md
│   └── step-summary-format.md
└── tasks.md               # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── actions/
│   ├── speckit-context/               # Existing composite, unchanged
│   └── speckit-metrics-summary/       # NEW — this feature's only new file besides workflow edits
│       └── action.yml
└── workflows/
    ├── speckit-1-intake.yml           # +1 metrics step after its agent step
    ├── speckit-2-clarify.yml          # +1 metrics step after its agent step
    ├── speckit-3-plan.yml             # +1 metrics step after its agent step
    ├── speckit-4-tasks.yml            # +1 metrics step (shared across the two mutually-exclusive agent steps)
    ├── speckit-5-implement.yml        # +3 metrics steps (cycle, retry, progress comment)
    ├── speckit-6-finalize.yml         # +1 metrics step after its agent step
    ├── speckit-7-cleanup.yml          # +1 metrics step after its agent step
    └── speckit-rebase.yml             # +1 metrics step after its per-matrix-entry agent step
```

**Structure Decision**: Single-project CI/CD feature, no `src/`/`tests/`
split. The entire feature is one new composite action plus additive steps
in eight existing workflow files — no existing step, trigger, permission,
or concurrency group is removed or restructured; this is purely additive,
matching FR-011's read-only requirement at the structural level as well as
the behavioral one.

## Complexity Tracking

> Not applicable — no Constitution Check violations.
