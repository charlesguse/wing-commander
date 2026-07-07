# Implementation Plan: Cleanup Stage — Lifecycle Teardown on Final Merge or Draft Rejection

**Branch**: `plan/007-cleanup-stage` | **Date**: 2026-07-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-cleanup-stage/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Turn the stub `.github/workflows/speckit-7-cleanup.yml` (repo-wide
`pull_request: closed`, currently gated only on a head-ref prefix guard,
per `docs/architecture.md` §Stage 6) into the pipeline's terminal stage.
The stage self-selects three, and only three, outcomes from any closed
pull request, disambiguated deterministically from the event payload
itself (head ref prefix + base ref + `merged`) — never guessed (FR-009):

1. **Final merge** (`spec/NNN-slug → main`, merged): delete every
   remaining pipeline branch for that specification, close the lifecycle
   issue with a Haiku-written completion summary, flip its label to
   `stage:done` (FR-002–FR-005).
2. **Draft rejection** (`spec-draft/NNN-slug → main`, closed unmerged):
   delete the draft branch, strip both the stage and identity labels,
   comment that the specification was rejected, and leave the issue
   **open** for revision (FR-006–FR-008, FR-014).
3. **Stalled** (`spec/NNN-slug → main` closed unmerged — built work
   rejected — **or** a non-final `plan/*`/`tasks/*`/`impl/*` pipeline PR
   closed unmerged): advance the stage label to `stage:stalled`, leave
   every branch intact, and comment a rejection notice that includes a
   manual full-teardown runbook (FR-012, FR-013, FR-015).

Everything else — an ordinary PR, a pipeline-shaped head ref merging
somewhere other than `main`/its own `spec/NNN-slug`, or a non-final PR
that *merges* (already handled by that stage's own trigger) — is a
deliberate no-op (FR-010, User Story 3 Scenario 4). A key finding from
research (below) is that FR-013 makes this stage the sole owner of
"non-final pipeline PR closed unmerged" handling: the `stalled` jobs
already living in `speckit-3-plan.yml` (reacting to `plan/*`) and
`speckit-4-tasks.yml` (reacting to `tasks/*`) must be retired in the same
change that lands this stage, or the same close event fires two
independent, differently-worded "stalled" comments. There is no
equivalent job to retire for `impl/*` — the implemented Stage 4
(`specs/005-implement-converge/`) commits directly to `spec/NNN-slug` and
never opens an `impl/*` PR, so that arm of FR-013 is a defensive no-op in
the current system, exercised only if that design changes later.

Every GitHub write (branch deletion, label flips, issue close/comment) is
plain deterministic bash, gated on an identity/ownership refusal check
that runs first in every job — the one place an LLM turn is spent is the
single read-only completion-summary step on the merged path, mirroring
the finalize stage's "agent proposes prose, deterministic steps own every
GitHub write" shape.

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps), YAML (workflow
definitions) — same as every other pipeline stage.

**Primary Dependencies**: GitHub Actions, `gh` CLI, `jq`, `git`,
`anthropics/claude-code-action@v1` (one read-only step), the repo's own
`.github/actions/speckit-context` composite action. This stage runs no
`/speckit-*` skill — like the finalize stage, its behavior (event
disambiguation, branch deletion, label/issue writes) is pipeline
orchestration with no corresponding spec-kit template, matching
`docs/architecture.md`'s Stage 6 sketch. This stage dispatches nothing
further — it is the pipeline's terminal stage, triggered only by a human
closing or merging a pull request.

**Storage**: `specs/NNN-slug/spec-meta.json` is always read first (to
resolve/validate the lifecycle issue and confirm the hand-off is genuine).
Whether it is also **written** depends on which of the three outcomes
applies, because only the stalled outcome leaves a branch alive to commit
to: on the **stalled** path, `spec-meta.json` (`stage: "stalled"`) is
committed directly onto the still-intact `spec/NNN-slug` branch — the
same write the two retired per-stage `stalled` jobs used to make, now
made here instead (FR-013's consolidation; restart logic in
`speckit-4-tasks.yml` etc. reads this field, so it must keep advancing).
On the **done** and **draft-rejected** paths, the branch that would have
received the write (`spec/NNN-slug` or `spec-draft/NNN-slug`) is deleted
in the same job, and this stage never commits to `main` directly (only
humans merge into `main`, constitution V) — so `specs/NNN-slug/spec-meta.json`
as it last read on `main`/before deletion is left as the final historical
record; nothing re-reads it afterward (research.md). GitHub branches,
labels, and the lifecycle issue are the only other persisted state this
stage mutates. No database.

**Testing**: No automated test suite exists for any pipeline stage; this
one is validated the same way stage 5 was — `quickstart.md`'s scenarios
run against scratch specifications and pull requests, exercising all
three outcomes plus the ownership/idempotency edge cases, cross-checked
against `docs/architecture.md`'s Stage 6 design and the constitution.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), triggered
by `pull_request: closed` repo-wide (self-selecting, not path-filtered —
the stub's existing trigger, extended per research.md to also recognize
`tasks/*` head refs it currently misses).

**Project Type**: Single project — CI/CD automation under
`.github/workflows/`, reusing `.github/actions/speckit-context`. No
frontend/backend split.

**Performance Goals**: N/A (event-driven CI job). The one agent step
(completion summary) is read-only summarization with a bounded
`--max-turns`, run only on the merged-final-PR path.

**Constraints**: Never performs teardown on a pull request it does not
own (FR-010) — ownership is re-derived from the event payload in an
early refusal step, never assumed from the job-level `if:` prefix match
alone. Idempotent under re-delivered/out-of-order close events: an
already-absent branch, an already-closed issue, or a label already in
its target state are all treated as success, and no path posts a second
copy of its comment (FR-011). Never deletes a specification's branches
on the built-work-rejected or non-final-rejected paths — those mark
`stage:stalled` and preserve everything for revival (FR-012, FR-013).
Never closes the lifecycle issue on draft rejection (FR-014). Every
stalled comment carries a link and manual instructions for optional full
teardown (FR-015). Never merges or approves anything — this stage acts
only after a human has already closed or merged the pull request
(constitution IV/V, spec.md Assumptions). Least-privilege
`--allowedTools`/`permissions:`; App-token auth via `speckit-context`; no
web tools; no fork-head checkouts — only `main`, `spec/NNN-slug`, and
(for the draft path) `spec-draft/NNN-slug` are ever fetched, and only
because they still exist at the moment this stage runs.

**Scale/Scope**: One workflow file (`speckit-7-cleanup.yml`) going from
stub to a three-job implementation (`teardown-done`, `teardown-rejected`,
`mark-stalled`), each independently gated so exactly one runs per closed
PR. Two existing workflow files (`speckit-3-plan.yml`, `speckit-4-tasks.yml`)
lose their now-redundant `stalled` jobs, per FR-013's explicit
consolidation (research.md) — this is this feature's only change outside
its own workflow file, and is unavoidable: leaving them in place would
make two different stages independently comment "stalled" on the same
closed PR. Concurrent specs run independently
(`concurrency: speckit-cleanup-<slug>`, matching the existing
per-spec-group idiom used by every other stage).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself built through the pipeline (issue
  #28 → this spec → this plan → tasks → implementation), and turns a
  documented stub (`docs/architecture.md` §Stage 6) into the pipeline's
  first fully self-closing lifecycle — this very specification's own
  final PR merging will, once implemented, be the first pull request this
  stage ever tears down for real. **Pass.**
- **II. Cost-Conscious Model Tiering**: The one agent step (completion
  summary) runs on `claude-haiku-4-5`, matching the constitution's
  tiering table exactly ("summaries") and the spec's own Assumptions
  ("a lightweight model is sufficient"); it declares `--max-turns`. The
  draft-rejection and stalled paths run no agent step at all — pure
  deterministic bash. **Pass.**
- **III. Simple, GitHub-Native Interaction**: Branch deletion, label
  flips, issue closure, and comments are the only surfaces this stage
  touches, all ordinary GitHub objects. A maintainer following only the
  lifecycle issue sees it close itself with a completion summary (SC-002)
  or sees a clear rejected/stalled record, without inspecting the branch
  list or any PR. **Pass.**
- **IV. Automation-First**: This stage removes the last manual step in
  the pipeline (spec.md's own framing) — branch deletion, relabeling, and
  issue closure/commenting are all automatic; the one human action that
  survives (merging or closing the pull request) is the explicit,
  irreducible hand-off this stage reacts to, not a step it performs
  itself. **Pass.**
- **V. Security**: `spec.md`/`spec-meta.json` content is read as data,
  never as instructions, identical to every other stage. This stage is
  `pull_request: closed`-triggered (not comment-triggered), so the
  commenter-trust checks constitution V requires for issue/comment-driven
  stages don't apply, but the App-token pattern, least-privilege
  `--allowedTools`, and no-web-tools rules are reused unchanged. Only
  `main`, `spec/NNN-slug`, and `spec-draft/NNN-slug` are ever checked
  out — never a fork PR head, and never any ref this stage itself just
  deleted (deletion is always the last write in its job). This stage
  never approves or merges anything (FR — implicit throughout; it only
  ever reacts to a PR already closed by a human). **Pass.**
- **VI. Portability**: No new project-specific concept beyond what stages
  1–5 already established (`spec-meta.json`, `spec/NNN-slug`, the
  lifecycle issue, its labels); this stage's artifacts
  (`speckit-7-cleanup.yml`, plus the two retired `stalled` jobs) resolve
  every path relative to the checkout and use `${{ github.repository }}`
  wherever a repo-qualified link is needed. **Pass.**

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/007-cleanup-stage/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   └── cleanup-workflow.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   ├── speckit-7-cleanup.yml    # Stub → three-job implementation (this feature's primary artifact)
│   ├── speckit-3-plan.yml       # `stalled` job retired — ownership moves to speckit-7-cleanup.yml (FR-013)
│   └── speckit-4-tasks.yml      # `stalled` job retired — same consolidation (FR-013)
└── actions/
    └── speckit-context/         # Reused unchanged (App token + label-based spec resolution)

docs/
├── architecture.md              # Stage 6 section already documents the target design;
│                                 # cross-checked during planning, no changes expected beyond
│                                 # what the stalled-path consolidation already implies
└── setup.md                     # Documents stage:* labels; will need stage:done added
                                  # once this feature lands (tasks-phase concern, not this plan)
```

**Structure Decision**: Single-project CI/CD feature, no `src/`/`tests/`
split. The primary artifact is `.github/workflows/speckit-7-cleanup.yml`
(stub → three independently-gated jobs: `teardown-done`,
`teardown-rejected`, `mark-stalled` — no single job needs a
success/stalled split the way stages 2–4 do, since this stage's whole
purpose *is* to distinguish those outcomes). The only other files this
feature touches are the two existing workflows losing their now-redundant
`stalled` jobs (FR-013's consolidation, research.md) — an unusual but
unavoidable footprint for a stage whose entire point is to become the
single owner of "a pipeline PR closed unmerged."

## Complexity Tracking

> Not applicable — no Constitution Check violations.
