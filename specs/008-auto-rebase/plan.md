# Implementation Plan: Auto-Rebase — Keep In-Flight Spec Branches Current With the Main Line

**Branch**: `plan/008-auto-rebase` | **Date**: 2026-07-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-auto-rebase/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Turn the stub `.github/workflows/speckit-rebase.yml` (per
`docs/architecture.md` §Auto-rebase: `push: main` + nightly `schedule`,
already gated on `!endsWith(github.actor, '[bot]')`) into the pipeline's
maintenance stage: it keeps every in-flight specification's persistent
working branch (`spec/NNN-slug`) rebased onto current `main` without a
human ever running `git rebase` by hand.

Two jobs. `discover` (single run) lists `spec/*` branches
(`git ls-remote --heads origin 'spec/*'`), reads each one's **own tip**
copy of `specs/NNN-slug/spec-meta.json` (never `main`'s, which goes stale
the moment a spec leaves the `spec` stage — research.md D1) to exclude
`stalled` specs (FR-002) and specs already known-blocked against an
unchanged `(branch-sha, main-sha)` pair (FR-012, research.md D6), then
emits the survivors as a JSON matrix. `rebase` is a
`fail-fast: false` matrix job, one instance per branch
(`concurrency: speckit-rebase-<slug>`, giving FR-010's per-branch
isolation for free — research.md D2), that:

1. Checks out the branch, fetches only `main` (never re-fetching the
   working branch's own ref — this is what keeps the eventual
   `--force-with-lease` push meaningful, research.md D3), and runs
   `git rebase origin/main`.
2. **Clean, and the tip actually moved**: `git push --force-with-lease`
   (FR-004). If the tip didn't move, it's a no-op — nothing is published
   (Acceptance Scenario 1.3). If the lease is rejected because someone
   published to the branch in the meantime, the job logs it and exits
   silently — no comment (FR-011, edge case).
3. **Conflicts**: `anthropics/claude-code-action@v1`
   (`--model claude-sonnet-5`, matching the stub and constitution II's
   implementation tier) resolves the in-progress rebase only — tightly
   allowlisted tools (no arbitrary `Bash`, no push, no `gh`), then a
   deterministic post-step verifies scope by comparing each replayed
   commit's touched-file set against its pre-rebase original plus the
   files that were ever actually conflict-marked (research.md D4) before
   the same `--force-with-lease` publish runs (FR-005, FR-006).
4. **Still stuck** (outright rebase failure, agent failure/timeout, or a
   scope-check failure): `git rebase --abort`; nothing is ever pushed, so
   the branch is untouched by construction (FR-007, research.md D5); a
   comment goes to the lifecycle issue re-derived from the branch's own
   `spec-meta.json`, carrying an HTML-comment SHA marker so `discover`
   can dedup future runs against the same unchanged pair (FR-008, FR-012,
   FR-013, research.md D6) — or, if the issue itself can't be identified,
   the failure is only logged (no blind action), per spec.md's edge case.

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps), YAML (workflow
definitions) — same as every other pipeline stage.

**Primary Dependencies**: GitHub Actions, `gh` CLI, `jq`, `git`,
`anthropics/claude-code-action@v1` (one step, conflict-only, gated behind
the rebase actually stopping on conflicts), the repo's own
`.github/actions/speckit-context` composite action (App-token auth, reused
unchanged). This stage runs no `/speckit-*` skill — like the finalize and
cleanup stages, its behavior is pipeline orchestration with no
corresponding spec-kit template, matching `docs/architecture.md`'s
Auto-rebase sketch.

**Storage**: `specs/NNN-slug/spec-meta.json` is read (never written) by
this stage — from each candidate branch's own tip, not `main`
(research.md D1). This stage's only durable write on a successful rebase
is the branch's own history (a force-with-lease push, FR-004/FR-006); on
an abandoned rebase it writes nothing to any branch (FR-007) and instead
comments on the lifecycle issue with a machine-readable SHA marker
(research.md D6) plus a `rebase:blocked` label — the closest thing this
stage has to persisted state, deliberately kept off `spec-meta.json` to
preserve FR-007's byte-for-byte guarantee. No database.

**Testing**: No automated test suite exists for any pipeline stage; this
one is validated the same way stages 2–6 were — `quickstart.md`'s
scenarios run against scratch specifications and a scratch conflicting
commit on `main`, cross-checked against `docs/architecture.md`'s
Auto-rebase section and the constitution.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), triggered
by `push` to `main` and a nightly `schedule` — the stub's existing
triggers, unchanged (research.md D7).

**Project Type**: Single project — CI/CD automation under
`.github/workflows/`, reusing `.github/actions/speckit-context`. No
frontend/backend split.

**Performance Goals**: N/A (event-driven/scheduled CI job). The
conflict-resolution agent step is the only unbounded-feeling piece and
carries an explicit `--max-turns`; matrix parallelism (research.md D2)
keeps total wall-clock roughly flat as the number of in-flight specs
grows, since branches rebase concurrently rather than in a loop.

**Constraints**: Never publishes over a concurrently-updated branch
(FR-011, enforced by `--force-with-lease` plus disciplined fetching,
research.md D3) — a blocked publish is silent, no comment, no escalation.
Never leaves a working branch half-rebased (FR-007) — every failure path
runs `git rebase --abort` and simply never pushes. Never lets AI-assisted
conflict resolution touch a file it didn't need to for the conflicts
themselves (FR-005) — enforced by both tool allowlisting and a
deterministic post-step diff (research.md D4), not by trusting the
agent's own report. Never re-escalates the same unchanged stall
repeatedly (FR-012) — `discover` dedups against a marker embedded in the
prior escalation comment (research.md D6). Never acts on a main-line
advance that originated from the pipeline's own App-token pushes
(FR-009) — the stub's existing `!endsWith(github.actor, '[bot]')` gate,
unchanged (research.md D7). Never merges or approves anything, and never
touches `main` itself (constitution IV/V, spec.md Assumptions) — this
stage only ever updates `spec/NNN-slug` branches and, on failure, comments
on lifecycle issues. Least-privilege `--allowedTools` on the one agent
step; App-token auth via `speckit-context`; no web tools; only `main` and
each `spec/NNN-slug` under consideration are ever checked out.

**Scale/Scope**: One workflow file (`speckit-rebase.yml`) going from stub
(a single "not implemented" summary step) to two jobs (`discover`,
`rebase`), the latter matrixed over however many `spec/*` branches are
currently in flight and not already known-blocked. No other workflow file
changes — unlike stage 6's consolidation, no other stage owns any part of
"keep a working branch rebased," so there is nothing else to retire.
Concurrent specs rebase independently and in parallel
(`concurrency: speckit-rebase-<slug>` per matrix entry, the same
per-spec-group idiom every other stage uses); a nightly nudge and every
qualifying `main` push independently attempt the same idempotent
operation, so a run overlapping a still-running prior run for the same
spec serializes rather than corrupting it (same concurrency group).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: Built through the pipeline itself (issue #33 → this spec
  → this plan → tasks → implementation), turning a documented stub
  (`docs/architecture.md` §Auto-rebase) into a real stage — this very
  specification's own working branch (`spec/008-auto-rebase`) is exactly
  the kind of branch this stage will keep rebased once implemented, and
  will do so for every specification that follows it (Guide's "own first
  example"). **Pass.**
- **II. Cost-Conscious Model Tiering**: The one agent step (conflict
  resolution) runs on `claude-sonnet-5`, matching the constitution's
  tiering table's implementation row and `docs/architecture.md`'s own
  stub — this is code/prose conflict resolution, not a triage/summary
  (`haiku`) or spec-authoring (`opus`) task. It declares `--max-turns`.
  The clean-rebase path (the common case, User Story 1) runs no agent
  step at all — pure deterministic git/bash, the cheapest possible
  outcome. **Pass.**
- **III. Simple, GitHub-Native Interaction**: The only surfaces this
  stage touches are a branch's own history (force-with-lease push) and,
  on failure only, a lifecycle-issue comment plus a `rebase:blocked`
  label — a maintainer sees a stall exactly where they already watch
  everything else for a spec, with no new dashboard or state store
  (research.md D6 explicitly rejects a new persisted-state alternative
  on this ground). **Pass.**
- **IV. Automation-First**: This stage removes the pipeline's last
  manual step named in spec.md's own framing — the pre-merge rebase a
  maintainer used to have to do by hand. The one human action that
  survives (rebasing by hand after an escalation comment) is explicit,
  reported, and only reached when both the mechanical and AI-assisted
  paths have already failed. **Pass.**
- **V. Security**: This stage is `push`/`schedule`-triggered, never
  comment-triggered, so the commenter-trust checks constitution V
  requires for issue/comment-driven stages don't apply (same reasoning
  `speckit-7-cleanup.yml` already relies on for its `pull_request:
  closed` trigger) — but the App-token pattern, least-privilege
  `--allowedTools` on the one agent step, and no-web-tools rule are
  reused unchanged. The agent step never has `git push` or `gh` in its
  tool allowlist — every publish and every GitHub write stays in
  deterministic steps this stage's own bash owns, matching the shape of
  every previous stage's agent/deterministic-write split. Only `main`
  and the `spec/NNN-slug` branch currently being rebased are ever checked
  out — never a fork PR head, and never anything this stage itself just
  rejected via `--force-with-lease`. This stage never approves or merges
  anything. **Pass.**
- **VI. Portability**: No new project-specific concept beyond what
  stages 1–7 already established (`spec-meta.json`, `spec/NNN-slug`, the
  lifecycle issue, its labels); the new `rebase:blocked` label is exactly
  the same kind of stage-scoped label `stage:stalled`/`stage:done` already
  are. All paths resolve relative to the checkout; nothing hardcodes a
  repository name or owner. **Pass.**

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/008-auto-rebase/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   └── rebase-workflow.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   └── speckit-rebase.yml    # Stub → two-job implementation (this feature's only artifact)
└── actions/
    └── speckit-context/      # Reused unchanged (App token + push/comment identity)

docs/
└── architecture.md           # "Auto-rebase" section already documents the target design;
                               # cross-checked during planning, no changes expected beyond
                               # what research.md's SHA-marker/dedup mechanism adds as detail
```

**Structure Decision**: Single-project CI/CD feature, no `src/`/`tests/`
split. The entire feature is one workflow file
(`.github/workflows/speckit-rebase.yml`) going from a "not implemented"
stub to a `discover` → matrixed `rebase` pipeline. Unlike stage 6
(`specs/007-cleanup-stage/`), no other workflow file needs to change —
this is the first and only stage that keeps a working branch current
with `main`, so there is nothing elsewhere to retire or consolidate.

## Complexity Tracking

> Not applicable — no Constitution Check violations.
