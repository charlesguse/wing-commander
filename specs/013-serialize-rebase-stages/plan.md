# Implementation Plan: Keep Auto-Rebase From Force-Pushing a Spec Branch Out From Under an In-Flight Stage

**Branch**: `plan/013-serialize-rebase-stages` | **Date**: 2026-07-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/013-serialize-rebase-stages/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

The auto-rebase stage (`rebase.yml`) and the four per-spec stages
(`plan.yml`, `tasks.yml`, `implement.yml`, `finalize.yml`) already each
serialize *themselves* per specification via a job-level
`concurrency:` group — but every stage family uses its own group-name
prefix (`wing-commander-rebase-<slug>`, `wing-commander-plan-<slug>`,
`wing-commander-tasks-<slug>`, and the pair `implement`/`finalize` already
share, `wing-commander-<spec-dir>`). Five disjoint prefixes for the same
specification mean GitHub Actions never orders a rebase against a stage —
that's the entire root cause (research.md D1).

The fix converges all six job instances across the five workflow files
onto one shared group per specification —
`wing-commander-<spec-dir>` (e.g.
`wing-commander-specs/013-serialize-rebase-stages`), which is
`implement.yml`/`finalize.yml`'s *existing* string, unchanged
(research.md D2):

1. `rebase.yml`: one-line change — the `rebase` matrix job's group moves
   from `matrix.slug`-keyed to `matrix.spec_dir`-keyed (`discover` already
   emits `spec_dir` per candidate branch; nothing new to compute).
2. `plan.yml` / `tasks.yml`: these only receive a `head-ref` (prefixed:
   `spec-draft/`, `plan/`, or `tasks/`) or a bare `slug`, and derive the
   canonical slug in a same-job step today — too late, since a job's
   `concurrency:` block is evaluated before its own steps run. Each file
   gains one small new `resolve-spec` job (no checkout, no secrets, pure
   string derivation) that the real job now `needs:`, and whose
   `spec-dir` output feeds the concurrency group (research.md D3). The
   existing per-job slug-validation step moves into `resolve-spec` rather
   than being duplicated.
3. `implement.yml` / `finalize.yml`: **no change** — they already receive
   `spec-dir` directly and already use the canonical string.

`cancel-in-progress: false` (already true everywhere) means a request for
a held group queues rather than being cancelled or dropped, which is what
gives FR-004's currency guarantee without any new "deferred rebase"
bookkeeping (research.md D4) — the nightly `schedule` trigger and every
subsequent default-branch push remain the backstop for the rare case where
a queued request is itself superseded by a newer one for the same group.
`intake.yml` (no slug yet) and `clarify.yml` (keyed to the issue, not the
branch) are explicitly untouched per FR-005; `cleanup.yml` is explicitly
out of scope per research.md D5 (it runs only after a spec's terminal
stage and only ever deletes the branch, never publishes over it).

## Technical Context

**Language/Version**: YAML (GitHub Actions workflow definitions), Bash
(`run:` steps) — same as every other pipeline stage; no new language or
runtime.

**Primary Dependencies**: GitHub Actions' own job-level `concurrency:`
primitive (the entire mechanism this feature relies on — no new library,
action, or reusable workflow input). No changes to
`.github/actions/wing-commander-context` or any other composite action.

**Storage**: None. This feature reads no new file and writes no new file;
`spec-meta.json`'s shape, the `rebase:blocked` label/marker, and every
stage's existing comments are untouched. The only "state" this feature
introduces is an ephemeral job output (`resolve-spec`'s `slug`/`spec-dir`)
that exists for the lifetime of a single workflow run.

**Testing**: No automated test suite exists for any pipeline stage in this
repository; validated the same way stages 2–8 were —
`quickstart.md`'s scenarios run by hand against scratch specifications,
timed to force the two collision directions (User Story 1 and User Story
2), observed via the Actions UI's run/job queue state.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners) — the five
workflow files already run there; this feature changes none of their
triggers (`rebase.yml` keeps its `push`/`schedule`; `plan.yml`/`tasks.yml`/
`implement.yml`/`finalize.yml` keep `workflow_call` only).

**Project Type**: Single project — CI/CD automation under
`.github/workflows/`. No frontend/backend split, no new project.

**Performance Goals**: N/A (event-driven CI). FR-006 requires the
uncontended path to add no delay — the new `resolve-spec` job in
`plan.yml`/`tasks.yml` is a small, checkout-free job (pure string handling)
whose runner-provisioning overhead is the same fixed cost every job in
this pipeline already pays for its own preliminary steps (e.g.
`wing-commander-5-implement.yml`'s existing `resolve-model` job); it adds
no proportional or unbounded delay as specs or stages scale.

**Constraints**: Never widens what any stage or auto-rebase is allowed to
*do* — this feature only changes when a job is allowed to *start*
(FR-007, contracts/concurrency-groups.md's "Non-goals"). Never serializes
across specifications (FR-005) — every group string is per-`spec-dir`.
Never introduces a new persisted "contention" flag, label, or
`spec-meta.json` field — currency is achieved entirely through GitHub
Actions' native queuing plus the rebase stage's existing nightly/push
triggers (research.md D4). Never folds `cleanup.yml` into the shared group
(research.md D5). Applies to the reusable pipeline stages only, so
external adopters inherit the fix identically (constitution VI).

**Scale/Scope**: Five workflow files change
(`rebase.yml`, `plan.yml`, `tasks.yml`, and — for completeness of the
contract, though their content is unchanged — `implement.yml`/
`finalize.yml` are reviewed but not edited); two of those five gain one new
job each (`resolve-spec`); `rebase.yml` gains a one-line group-string
change; no other workflow file, composite action, or spec-kit script
changes. `specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s
existing (already-slightly-inaccurate) claim about shared per-spec
serialization becomes accurate once this ships — updating that file's
wording is implementation-phase follow-up, outside this plan's edit scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: Built through the pipeline itself (issue #53 → this spec →
  this plan → tasks → implementation); this specification's own working
  branch (`spec/013-serialize-rebase-stages`) is exactly the kind of
  branch this fix protects, and every specification that follows it
  benefits identically. **Pass.**
- **II. Cost-Conscious Model Tiering**: This feature runs no agent step at
  all — it is pure CI wiring (YAML/Bash) across five workflow files. No
  model-tiering decision applies. **Pass** (not applicable).
- **III. Simple, GitHub-Native Interaction**: The only user-visible
  surface is the Actions UI's existing run/job list, where a queued job
  now legitimately waits instead of racing — no new dashboard, comment
  type, or label. A maintainer who previously had to notice a failed,
  non-fast-forward stage run and manually re-dispatch it now sees fewer
  such failures; nothing new to read or configure. **Pass.**
- **IV. Automation-First**: Removes exactly the kind of manual step
  constitution IV singles out — spec.md's whole premise is "a manual
  re-dispatch recovers cleanly, but until then the lifecycle is stalled";
  this fix removes the need for that manual re-dispatch in the
  rebase-vs-stage collision (SC-002). **Pass.**
- **V. Security**: No change to any stage's `--allowedTools`, model,
  credential handling, or trust boundary — this feature touches only
  `concurrency:` blocks and one new checkout-free, secret-free
  `resolve-spec` job per file (least-privilege: `permissions: {}`, no
  token, no API call). No agent step is added or modified. **Pass.**
- **VI. Portability**: The change lives entirely in the reusable stage
  files (`rebase.yml`, `plan.yml`, `tasks.yml`) that publish to adopting
  repositories, per spec.md's own Assumptions ("the fix applies to the
  reusable pipeline stages, so external adopters... inherit the corrected
  behavior identically"). No repository name, owner, or project-specific
  content is introduced. **Pass.**

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/013-serialize-rebase-stages/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   └── concurrency-groups.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
└── workflows/
    ├── rebase.yml        # `rebase` matrix job: concurrency group keyed to matrix.spec_dir (was matrix.slug)
    ├── plan.yml           # New `resolve-spec` job; `plan` job needs it, groups on its spec-dir output
    ├── tasks.yml          # New `resolve-spec` job (mode-aware); `tasks`/`tasks-approved` need it
    ├── implement.yml      # Reviewed, unchanged — already the canonical group shape
    └── finalize.yml       # Reviewed, unchanged — already the canonical group shape

specs/
└── 010-reusable-pipeline/
    └── contracts/
        └── stage-interfaces.md   # Follow-up wording correction (implementation-phase task,
                                   # not a planning-time edit — outside this plan's scope)
```

**Structure Decision**: Single-project CI/CD feature, no `src/`/`tests/`
split — identical shape to specs 008/010. Unlike spec 007 (cleanup stage
consolidation), no workflow file is removed or replaced wholesale; three
files (`rebase.yml`, `plan.yml`, `tasks.yml`) get targeted, additive
changes to their existing `concurrency:` wiring, and two (`implement.yml`,
`finalize.yml`) are confirmed to already match the target shape and are
left alone.

## Complexity Tracking

> Not applicable — no Constitution Check violations.
