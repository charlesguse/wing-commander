# Implementation Plan: Maintainer Commands and Spec Kit Routing Through PR Conversation

**Branch**: `033-pr-conversation-commands` | **Date**: 2026-08-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/033-pr-conversation-commands/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Today, a maintainer's review comment on an implementation (finalize) PR is
invisible to the pipeline — every re-drive of implement ⟲ converge, every
spin-off issue or PR, and every clarifying question is a manual human step.
This feature adds a tenth published stage, `pr-conversation.yml`, plus a new
thin wrapper `wing-commander-9-pr-conversation.yml` that is the first in
this repository to listen to `pull_request_review` and
`pull_request_review_comment` events (alongside `issue_comment` filtered to
PR comments) — no existing wrapper covers this trigger shape (research.md
D1). The stage classifies each maintainer request into one of eight
categories (FR-003), announces its classification, planned action, and a
run link before mutating anything (FR-023), and then routes: in-scope
requests are folded into `tasks.md` on `spec/<slug>` and re-dispatch the
*existing* `wing-commander-5-implement.yml` wrapper unchanged (research.md
D5 — no change to `implement.yml` or `/speckit-converge` is needed);
new-functionality requests are folded into the current spec or spun off as
a new lifecycle issue via the *existing* `spec-request`-labeled intake
entry point (research.md D7); very small unrelated changes become a
separate PR to the default branch; manual-step/permission requests are
performed or become a permission-request PR; ambiguous or
constitution-conflicting requests get a clarifying question or a reasoned
decline; questions are answered with no mutation; and stop requests cancel
the run named in the stage's own most recent intent-announcement comment
(research.md D10 — no new storage, the PR thread itself is the state).
Every artifact created outside the PR is recorded on the lifecycle issue as
an outstanding task item (FR-008/FR-013). Per-action-category
propose-and-confirm autonomy (FR-020) reuses the existing deployment
-environment binding mechanism (`specs/031-stage-environment-binding`)
rather than inventing a new wait/poll primitive (research.md D9). Per-spec
serialization (FR-015) joins the existing `wing-commander-<spec-dir>`
concurrency group (`specs/013-serialize-rebase-stages`) rather than
inventing a new lock.

## Technical Context

**Language/Version**: Bash (POSIX-ish, matching every existing composite
action and workflow `run:` step) + GitHub Actions YAML (`workflow_call`
reusable workflow + `workflow_dispatch`-chained wrapper); the
classification/drafting half is a Claude Code prompt with structured
(`--json-schema`) output, the same invocation shape `clarify.yml` already
uses (`anthropics/claude-code-action@v1`) — no new application language or
runtime.

**Primary Dependencies**: GitHub Actions (`workflow_call`, `workflow_dispatch`,
job-level `environment:` binding), `gh` CLI (`gh api` for
`pull_request_review`/`pull_request_review_comment`/issue-comment reads,
`gh pr comment`/`gh issue comment` for replies, `gh pr create`/`gh issue
create` for spin-off artifacts, `gh run list`/`gh run cancel` for the stop
mechanism, `gh workflow run` for re-dispatching
`wing-commander-5-implement.yml`), `jq`, `anthropics/claude-code-action@v1`,
the existing composite actions (`wing-commander-lifecycle-gate`,
`wing-commander-context`, `wing-commander-callout`, `wing-commander-preflight`,
`wing-commander-tool-args`, `wing-commander-metrics-summary`,
`wing-commander-bedrock-credentials`) reused as-is (research.md D3), and the
`spec-request`-labeled intake entry point reused as-is for the
new-lifecycle-issue spin-off (research.md D7).

**Storage**: N/A — no new persisted schema. State that already exists is
reused: `spec-meta.json` on `spec/<slug>` (`stage`/`iteration`, read and,
for in-scope requests, advanced back to `"implement"` before re-dispatch —
research.md D5), `tasks.md` on the same branch (gains a maintainer-feedback
task section, the actual "converge input" fold-in), and the PR's own
comment thread (the stop mechanism's only state store — research.md D10).
No new file, table, or cache is introduced.

**Testing**: `actionlint` + `yamllint` (already CI-gated per spec
025-lint-composite-actions) for the two new workflow files;
`lint-workflows.yml` Gate 7 for the `environment:`/`environment-deployment:`
binding shape (spec 031); standalone shell invocation of the new
deterministic steps (actor-gate expression, implementation-PR identity
check, environment-name resolution, stop-target extraction) against
representative `gh api` fixture JSON, asserting `$GITHUB_OUTPUT` values
(`quickstart.md` "Static validation"); end-to-end dogfood runs via
`wing-commander-9-pr-conversation.yml` against real test implementation PRs
in this repository (constitution I), one per user story
(`quickstart.md`).

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), consumed by
any repository that references `pr-conversation.yml` (constitution VI); no
new platform surface.

**Project Type**: Infrastructure / reusable CI workflow library — not an
application; one new published stage file plus one new thin wrapper,
following the same nine-stage architecture already in place.

**Performance Goals**: N/A in the traditional sense — the classify+draft
agent step is bounded (`max-turns`, constitution II); the deterministic
steps (actor gate, PR-identity check, tasks.md fold-in, dispatch, stop-scan)
are a bounded number of `gh api`/`gh run list` calls, negligible relative to
the implement/converge cycle they may trigger.

**Constraints**: Zero reaction to spec-draft/plan/tasks PR conversation
(FR-018 — only the implementation/finalize PR, identified by base = default
branch and head = the configured `spec-prefix` branch, never `spec-draft-prefix`,
`plan-prefix`, or `tasks-prefix`); no requester carve-out in the actor gate,
unlike clarify/intake (FR-019); no `github.event.*`/`vars.*` read inside the
stage file itself (constitution VII); web tools disabled (FR-016); every
mutating action announced before it runs, with a run link, and abandoned on
a matching stop request (FR-023/FR-024); autonomy configuration is
trusted-input-only, never derived from PR conversation content (FR-020);
`implement.yml` and `/speckit-converge` receive **zero** changes (research.md
D5) — the fold-in is entirely a `tasks.md` + `spec-meta.json` edit the new
stage makes on its own before dispatching the existing implement wrapper.

**Scale/Scope**: 1 new published stage workflow (`pr-conversation.yml`,
likely 2 jobs: `classify-and-announce`, `act`); 1 new thin wrapper
(`wing-commander-9-pr-conversation.yml`); 0 new composite actions (research.md
D3 — `wing-commander-callout` is reused as-is, called against the PR number
and, when needed, again against the issue number, since `gh issue comment`
already accepts PR numbers); 0 changes to any other published stage; 2 new
repository variables (`WING_COMMANDER_PR_CONVERSATION_CONFIRM_CATEGORIES`,
`WING_COMMANDER_PR_CONVERSATION_CONFIRM_ENVIRONMENT`) plus reuse of the
existing `WING_COMMANDER_*_MODEL`/`model:opus`-label resolve-model pattern;
1 drafted addition to `specs/010-reusable-pipeline/contracts/stage-interfaces.md`
(`reusable-pr-conversation.yml` row + a new "Wrapper gate obligations"
bullet), carried over at implementation time, not edited by this plan
stage.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide — dogfooded**: PASS. This spec itself will flow through
  intake → plan → tasks → implement like every other feature, and once
  merged this repository's own maintainers become the first users of the
  stage it adds — a review comment on this feature's own eventual
  implementation PR is a real worked example, not a hypothetical one.
- **II. Cost-Conscious Model Tiering**: PASS. The classify+draft step gets
  an explicit model and `--max-turns`; it is not pure triage/classification
  (it also drafts issue bodies, decline reasoning, and small-change diffs
  and judges constitution conflicts), so it follows the same tier and
  opt-in pattern `implement.yml` already uses — `claude-sonnet-5` default,
  `claude-opus-5` via repo variable or `model:opus` label — rather than the
  haiku triage tier (research.md D2). The stop-scan and dispatch steps are
  pure shell, incurring no model cost at all, matching
  `wing-commander-lifecycle-gate`/`wing-commander-preflight`.
- **III. Simple, GitHub-Native Interaction**: PASS, and this is the
  feature's whole premise — the interaction surface is exactly "leave a
  review or comment on the PR," nothing external. The intent-announcement
  and stop mechanisms (research.md D9/D10) are both built from GitHub's own
  primitives (deployment environments, run cancellation, comment threads),
  not a bespoke dashboard or polling service.
- **IV. Automation-First**: PASS. The one surviving manual step this
  feature can't remove — an adopter must actually configure required
  reviewers on the confirm environment for propose-and-confirm to have
  teeth (research.md D9, mirroring spec 031's own documented caveat) — is
  explicitly a documentation obligation, not a silent gap.
- **V. Security — Untrusted Content Is Never Instructions (NON-NEGOTIABLE)**:
  PASS, and central to this feature. Review/comment bodies are staged to a
  file exactly as `clarify.yml` already does (never shell-interpolated,
  never pasted into the prompt string); the actor gate is deterministic,
  wrapper-owned, and — unlike clarify/intake — has **no** requester
  carve-out (FR-019, spec.md Assumptions); bot comments are ignored with no
  reply at all (FR-002); web tools are disabled (FR-016); only the trusted
  `spec/<slug>` branch is ever checked out, never a fork PR head
  (Assumptions).
- **VI. Portability**: PASS. All new state (the two repo variables, the
  confirm environment name) is consumer-owned configuration, resolved only
  in the new wrapper; the stage file itself reads no `vars.*`.
- **VII. Two Interfaces**: PASS, and this is the plan's central design
  question, resolved explicitly rather than assumed (research.md D1/D4):
  the new wrapper owns the `pull_request_review`/
  `pull_request_review_comment`/`issue_comment` triggers, the actor gate,
  and event→input extraction — ground with **zero** existing precedent in
  this repository (research confirmed no published stage or wrapper
  listens to either PR-review event today) — while the stage itself stays
  `workflow_call`-only and reads no ambient state. The new
  `contracts/reusable-pr-conversation.md` and `contracts/wrapper-gate.md`
  drafts in this plan are exactly the kind of registered, machine-checked
  interface constitution VII requires for a new stage/wrapper split, not a
  code-comment-only deviation.

No violations requiring justification; Complexity Tracking table is empty.
This is a new stage of the same shape as the other nine — one new
`workflow_call` file, one new thin wrapper, reusing every existing
composite action and configuration pattern (research.md D2–D9) rather than
introducing a new mechanism class, with the two genuine gaps (the
PR-review trigger shape, the stop mechanism) each resolved by extending an
existing GitHub-native primitive rather than building bespoke
infrastructure.

**Post-Phase-1 re-check**: unchanged — `data-model.md` and `contracts/`
introduce no new secret, no new external dependency, and no change to any
other stage's `workflow_call` interface; the one new `stage-interfaces.md`
addition is purely additive (a new stage row, a new wrapper-gate-obligation
bullet) and does not touch any existing row. Gate still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/033-pr-conversation-commands/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/             # Phase 1 output (/speckit-plan command)
│   ├── reusable-pr-conversation.md   # workflow_call contract, stage-interfaces.md row draft
│   ├── wrapper-gate.md               # trigger events, actor gate, event→input extraction
│   ├── classification-schema.md      # the classify+draft agent step's structured output
│   ├── converge-fold-in.md           # FR-004/FR-005: tasks.md + spec-meta.json + re-dispatch mechanics
│   ├── spinoff-routing.md            # FR-006/007/008/012: new-issue, small-PR, permission-PR, outstanding-task-item
│   └── autonomy-and-confirmation.md  # FR-020/023/024: config variables, environment gate, run link, stop
└── tasks.md               # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This is an infrastructure feature with no `src/`/`tests/` application
tree — its "source" is GitHub Actions workflow YAML plus a Claude Code
prompt, at the same well-known paths every other stage already uses. No new
top-level directories are introduced.

```text
.github/
└── workflows/
    ├── pr-conversation.yml            # NEW published stage (workflow_call only)
    └── wing-commander-9-pr-conversation.yml  # NEW thin wrapper (owns the trigger/actor gate)

specs/010-reusable-pipeline/contracts/
└── stage-interfaces.md   # gains a `reusable-pr-conversation.yml` row and a
                            # new "Wrapper gate obligations" bullet, edited at
                            # implementation time from this plan's
                            # contracts/reusable-pr-conversation.md and
                            # contracts/wrapper-gate.md drafts (same
                            # deferral 029-intake-issue-comments and
                            # 031-stage-environment-binding already used)

docs/
├── setup.md         # gains the two new WING_COMMANDER_PR_CONVERSATION_* variable rows
├── adoption.md       # gains the new wrapper's example + its workflow_dispatch-free trigger shape
└── architecture.md   # stage/wrapper counts and lists advance from nine to ten (constitution's
                        # own Sync Impact Report precedent for keeping these counts honest)
```

**Structure Decision**: No new project/module boundary. One new stage file
and one new wrapper file, at the same paths and following the same
`workflow_call`/thin-wrapper split every other stage already uses; zero new
composite actions (research.md D3); zero changes to any other stage file,
including `implement.yml` (research.md D5) — the fold-in and re-dispatch
are entirely new logic inside `pr-conversation.yml` calling the *existing*
`wing-commander-5-implement.yml` wrapper's already-published dispatch
contract (`specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s
"Chaining payload contract" table). Documentation additions land in the
existing normative contract doc
(`specs/010-reusable-pipeline/contracts/stage-interfaces.md`) rather than a
new one; this plan stage only *drafts* that content under this feature's
own `contracts/` — the actual edits happen during the implement stage.

## Complexity Tracking

*No entries — Constitution Check found no violations requiring
justification.*
