# Implementation Plan: Include Follow-Up Comments in Intake Specification

**Branch**: `029-intake-issue-comments` | **Date**: 2026-08-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/029-intake-issue-comments/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Intake currently specifies an issue from its title and body alone; a
maintainer who applies the entry-gate label to a well-discussed issue
silently gets a spec built from the original, least-informed version of the
request, because every follow-up comment is invisible to the stage. This
feature makes intake read the issue's comment history and fold *qualifying*
comments — from OWNER/MEMBER/COLLABORATOR accounts or the original issue
author, never bots — into the feature description handed to
`/speckit-specify`, while keeping non-qualifying comment content fully
unreachable by the specification. The technical approach adds one new
deterministic (non-agent) step to `intake.yml` that fetches the issue
author and all comments via `gh api`, applies the same
association/author-id/bot rule `clarify.yml`'s wrapper already applies to
its single triggering comment, and stages only the qualifying comments —
ordered, verbatim, untrusted — to a data file the agent reads. A second new
deterministic step posts a visible notice on the lifecycle issue when
substantive (non-bot) comments existed but none qualified, so the maintainer
never silently believes unused discussion was incorporated. No new
`workflow_call` inputs, no tool-allowlist change, and no change to
`/speckit-specify` itself — this is a self-contained `intake.yml` change
(Assumptions: "existing permissions suffice … a prompt/behavior change, not
a permissions change").

## Technical Context

**Language/Version**: Bash (POSIX-ish, matching existing composite actions and workflow `run:` steps) + GitHub Actions YAML (`workflow_call`); the agent-facing half is a Claude Code prompt change (no new application language).

**Primary Dependencies**: GitHub Actions (`workflow_call`), `gh` CLI (`gh api` for issue + issue-comments REST reads — the same command family `clarify.yml` already uses for its single-comment fetch), `jq` (comment filtering/counting, already a dependency of `wing-commander-preflight`), `anthropics/claude-code-action@v1` (unchanged invocation shape — no new `claude_args`), `/speckit-specify` skill (consumed as-is, unchanged — research.md D6).

**Storage**: N/A — no persisted state. The staged comments file (`/tmp/wing-commander/intake-comments.md`) is runner-local and discarded with the job, matching `clarify.yml`'s existing `/tmp/wing-commander/` staging convention. Nothing new is written to `spec-meta.json`.

**Testing**: `actionlint` + `yamllint` (already CI-gated per spec 025-lint-composite-actions) for the changed `intake.yml`; standalone shell invocation of the new filter step's logic against representative `gh api` fixture JSON, asserting `$GITHUB_OUTPUT` counts and staged-file contents (`quickstart.md` "Static validation"); end-to-end dogfood runs via `wing-commander-1-intake.yml` against real test issues with controlled commenter identities (`quickstart.md` "End-to-end scenario checks").

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), consumed by any repository that references `intake.yml` (constitution VI — portability); no new platform surface.

**Project Type**: Infrastructure / reusable CI workflow library — not an application; single scope covering one existing published stage file (`.github/workflows/intake.yml`).

**Performance Goals**: N/A in the traditional sense — the new filter step is a bounded number of paginated `gh api` calls (one per ~100 comments) plus `jq` filtering; must add negligible wall-clock time relative to the agent step it precedes, and strictly less than the cost of the agent re-deriving the same data itself.

**Constraints**: Zero behavior change when an issue has no qualifying comments (FR-007, SC-004); non-qualifying/bot comment content must never become reachable by the agent through the new mechanism (FR-002/FR-003/FR-009, defense-in-depth per research.md D3); comment bodies must never be shell-interpolated or pasted into the agent prompt string (FR-004); the three-marker `[NEEDS CLARIFICATION]` cap still applies however large the discussion (Assumptions); no new `workflow_call` input, no tool-allowlist change (Assumptions: "existing permissions suffice").

**Scale/Scope**: 1 published stage workflow (`intake.yml`); 2 new deterministic steps (comment-trust-gate, excluded-comments notice); 1 extended agent prompt (feature-description assembly + an explicit "don't re-fetch comments yourself" constraint); 0 new composite actions (the existing `wing-commander-callout` covers the new notice); 0 new `workflow_call` inputs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide — dogfooded**: PASS. This spec itself flows through intake →
  plan → tasks → implement, the same stages it modifies; no bootstrap
  exception needed.
- **II. Cost-Conscious Model Tiering**: PASS / no change. No new agent
  invocation is introduced — the two new steps are pure shell (`gh api` +
  `jq` and a `wing-commander-callout` composite call), identical in kind to
  `wing-commander-lifecycle-gate`/`wing-commander-preflight`, so they "can
  never itself incur cost." Intake's existing agent step keeps its
  existing model (`claude-opus-4-8`, tier-appropriate for specification per
  Principle II) and `max-turns`; the feature description it receives is
  longer, not different in kind.
- **III. Simple, GitHub-Native Interaction**: PASS. No new interaction
  surface — a maintainer still just comments on the issue and applies the
  label; the only new user-visible artifact is one additional lifecycle-
  issue comment (the FR-008 notice, `contracts/notice-callout.md`), in the
  same `wing-commander-callout` format every other stage callout already
  uses.
- **IV. Automation-First**: PASS. Nothing new is manual; the trust decision
  and the notice-fire decision are both deterministic (research.md D1/D4,
  never left to agent judgment), and the notice itself is exactly the
  "manual step … reported explicitly to the lifecycle issue" this principle
  requires when the pipeline can't act further on its own (here: it can't
  know whether the excluded discussion should have been folded into the
  body, so it says so instead of guessing).
- **V. Security — Untrusted Content Is Never Instructions (NON-NEGOTIABLE)**:
  PASS, and this is the feature's core concern rather than an incidental
  gate. Comment bodies remain user data framed as such to the agent
  (extending intake's existing "SECURITY (non-negotiable)" prompt framing
  from body-only to body+comments); the author/bot gate is enforced
  deterministically, before the agent runs, using the identical two REST
  fields (`user.type`, `author_association`) the wrapper-level clarify gate
  already trusts (research.md D2) — not by asking the agent to judge
  commenter trustworthiness itself, which is exactly the naive approach
  User Story 2 exists to rule out. See research.md's "Constitutional
  considerations" note reconciling this principle's comment-*triggered*
  wording with intake's label-triggered-but-comment-*reading* shape, and
  D5's documented residual-risk mitigation for the pre-existing
  `Bash(gh issue view:*)` allowance (no tool-allowlist change is in scope,
  per Assumptions, so this is a prompt-level constraint, not a technical
  guarantee).
- **VI. Portability**: PASS. No new pipeline-specific state is introduced in
  the consuming repository beyond the existing `specs/`/`spec-meta.json`
  pattern; the new steps read only from the GitHub API of the repository
  the stage already runs against.
- **VII. Two Interfaces**: PASS, with the split explicitly reasoned through
  (research.md D1) rather than assumed: the wrapper (`wing-commander-1-
  intake.yml`) keeps owning its one trigger-time gate (the `spec-request`
  label); the new comment-trust filtering is stage-internal behavior
  (`intake.yml` itself), because there is no comment-*trigger* event for a
  wrapper to gate at dispatch time here — the stage is reading historical
  issue state mid-run, the same category of thing
  `wing-commander-lifecycle-gate` and `wing-commander-preflight` already do
  inside the stage. No new `workflow_call` input is added, so the
  published contract surface (`contracts/stage-interfaces.md`) gains no new
  compatibility commitment — only its prose "Behavior" cell for
  `reusable-intake.yml` needs updating at implementation time to mention
  comment intake, per constitution VII's "every document states which
  layer it describes."

No violations requiring justification; Complexity Tracking table is empty
(N/A) — both new steps are additive infrastructure of the same kind already
established (`wing-commander-lifecycle-gate`, the existing "Stage the
answer as a data file" step in `clarify.yml`), not a deviation from an
existing gate.

**Post-Phase-1 re-check**: unchanged — `data-model.md` and `contracts/`
introduce no new agent invocation, no new secret, no new external
dependency, no new `workflow_call` input, and preserve the FR-007/SC-004
zero-change-when-no-qualifying-comments invariant end-to-end (staged file
is written, and the notice fires, only when the deterministic conditions in
`contracts/comment-trust-gate.md`/`contracts/notice-callout.md` say so; the
agent prompt's added instructions are no-ops when `comments-file` is
empty). Gate still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/029-intake-issue-comments/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/             # Phase 1 output (/speckit-plan command)
│   ├── comment-trust-gate.md      # the new deterministic filter step's contract
│   ├── comment-staging-format.md  # the untrusted-data-to-file shape (extends clarify.yml's pattern to N comments)
│   └── notice-callout.md          # FR-008's visible-notice condition + wing-commander-callout invocation
└── tasks.md               # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This is an infrastructure feature with no `src/`/`tests/` application tree
— its "source" is GitHub Actions workflow YAML plus a Claude Code prompt,
which already exist at a fixed, well-known path in this repository. No new
top-level directories are introduced.

```text
.github/
└── workflows/
    └── intake.yml   # + 2 new deterministic steps (comment-trust-gate,
                      #   excluded-comments notice); agent prompt step 1/3
                      #   extended to read the staged comments file and
                      #   assemble the feature description from
                      #   title + body + qualifying comments (FR-005),
                      #   with an explicit "don't re-fetch comments
                      #   yourself" constraint (research.md D5)

specs/010-reusable-pipeline/contracts/
└── stage-interfaces.md   # reusable-intake.yml's "Behavior" cell gains a
                            # clause noting comment intake; edited at
                            # implementation time, not by this plan stage
                            # (same deferral 026-configurable-tool-lists
                            # used for its own stage-interfaces.md edit)

specs/019-next-step-callouts/contracts/
└── callout-points.md      # gains a new row for the FR-008 notice
                            # (this feature's own contracts/notice-callout.md
                            # is the source-of-truth draft, carried over
                            # verbatim at implementation time)
```

**Structure Decision**: No new project/module boundary and no new
composite action — the two new steps are additive edits inside the single
existing `intake.yml` job, calling the existing `wing-commander-callout`
composite action for the new notice exactly as intake's other two callout
points already do. Documentation additions land in the existing normative
contract docs (`specs/010-reusable-pipeline/contracts/stage-interfaces.md`,
`specs/019-next-step-callouts/contracts/callout-points.md`) rather than new
top-level docs, per constitution VI/VII (consumers already know to check
one contract doc per concern) — this plan stage only *drafts* that content
under `specs/029-intake-issue-comments/contracts/`; the actual edits to
those other specs' files happen during the implement stage.

## Complexity Tracking

*No entries — Constitution Check found no violations requiring
justification.*
