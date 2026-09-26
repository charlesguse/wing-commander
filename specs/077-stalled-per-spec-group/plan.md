# Implementation Plan: The Stall Mark Waits Its Turn — pr-conversation's Survivor Job Joins the Per-Spec Concurrency Group

**Branch**: `077-stalled-per-spec-group` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/077-stalled-per-spec-group/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

`pr-conversation.yml`'s `stalled` job pushes a stall mark onto `spec/NNN-slug`
through `wing-commander-chain-stop-notice`, but it cannot join the canonical
`wing-commander-<spec-dir>` group the way `plan.yml`/`tasks.yml`'s survivor
jobs already do (#397), because the spec directory is resolved *inside* the
job whose own start this survivor job exists to detect — a job-level
`concurrency.group` cannot read a step output of the job it belongs to, and
the job that publishes `spec-dir` today (`classify-and-announce`) is by
construction the one that did not run.

This plan gives `pr-conversation.yml` the prerequisite-job shape `plan.yml`
and `tasks.yml` already ship, adapted for the one respect in which this
stage's inputs differ: it receives only `pr-number`, so the new job must ask
the GitHub API for the head ref before it can derive anything, where
`plan.yml`'s equivalent job is pure string manipulation over a declared
input.

1. **New job `resolve-identity`** — no checkout, no secrets,
   `permissions: {pull-requests: read, contents: read}` — runs before both
   `classify-and-announce` and `stalled`. It is today's
   "Resolve PR identity and check qualification" step, relocated verbatim:
   it resolves the default branch and the PR's base/head ref, fails loudly
   (`::error::` + `exit 1`) when either API read comes back empty, and
   otherwise stays green and emits `qualifies`/`slug`/`spec-dir`/
   `default-branch` — `qualifies: false` and an empty `spec-dir` for a
   legitimately non-qualifying head ref is not a failure (FR-007), exactly
   as the step already behaves today.

2. **`classify-and-announce` consumes it instead of deriving it twice.** The
   job's own `identity` step (and its now-orphaned "identity-resolution
   refusal" callout, which could only ever fire from that step) is deleted;
   every reference to `steps.identity.outputs.*` — in this job's own `if:`
   conditions, its job-level outputs, and the classify agent's prompt —
   becomes `needs.resolve-identity.outputs.*`. The job gains
   `needs.resolve-identity.result != 'failure'` in its own `if:`, mirroring
   the existing `verify-image-prerequisites` toleration clause, so that a
   failed API read in `resolve-identity` skips this job outright rather than
   letting it read empty outputs as "this PR does not qualify" (the failure
   mode FR-011 forbids). The job's per-PR concurrency group is unchanged —
   it never pushes to `spec/<slug>` itself, only `act` does, through its own
   group (research.md D1).

3. **`stalled` reads identity from `resolve-identity` instead of
   re-deriving it a second time.** Its own "Resolve PR identity
   independently" step — the second `gh pr view` lookup FR-016 says must go
   — is deleted. The job's `needs` gains `resolve-identity`; its `if:` gains
   an explicit `needs.resolve-identity.result == 'failure'` arm (FR-005) so
   the admission decision does not rely solely on `classify-and-announce`'s
   derived skip; its `concurrency.group` becomes the canonical per-spec
   group with an explicit per-PR fallback for the empty-`spec-dir` case
   (research.md D2); and its lifecycle-issue lookup — the one piece of
   identity resolution that stays in this job (Assumptions) — now keys off
   `needs.resolve-identity.outputs.slug`/`spec-dir` and is skipped outright
   when `spec-dir` is empty.

4. **Two small cross-cutting consequences**, both already scoped by the
   spec: Gate 80 (`verify-spec-branch-push-concurrency.py`) learns the exact
   fallback group spelling FR-008 requires as a fourth accepted spelling
   (research.md D3), and `specs/041-implement-stall-notice`'s D6 table gains
   a row describing this derivation-only-prerequisite shape in place of the
   independent re-derivation it describes today (research.md D4).

No `workflow_call` input, output, or secret of `pr-conversation.yml` changes
(FR-017); no other stage file is touched.

See [research.md](./research.md) for the full decision record,
[data-model.md](./data-model.md) for the exact before/after wiring tables,
and [contracts/](./contracts/) for the new job's contract, the widened
`stalled` job's contract, and Gate 80's new accepted spelling.

## Technical Context

**Language/Version**: Bash (`run:` steps, matching every existing job in
this workflow), YAML (the job/`if:`/`concurrency:` graph itself), Python 3
(`.github/scripts/verify-spec-branch-push-concurrency.py`, matching every
existing gate script) — no new language introduced.

**Primary Dependencies**: `gh` CLI (the two read-only calls `resolve-identity`
inherits verbatim: `gh repo view --json defaultBranchRef` and
`gh pr view --json baseRefName,headRefName`), matching what
`classify-and-announce`'s identity step already calls. No new tool.

**Storage**: `spec-meta.json` on the specification's `spec/NNN-slug` branch
(existing mechanism, existing schema, unchanged) — this feature changes
*when* the survivor job is allowed to write it (ordered against other
writers), never its shape.

**Testing**: `.github/scripts/verify-spec-branch-push-concurrency.py`'s
existing self-test gains cases for the new accepted spelling (a job
declaring it passes; a near-miss — a different `needs.*` job name in the two
halves, or a literal near-miss of the fallback text — still fails), per this
repository's `verify-*.py` self-contained-script convention (Constitution
VIII).

**Target Platform**: GitHub Actions, `ubuntu-latest` runner (or whatever
`inputs.runner`/`inputs.container-image` the calling wrapper configures —
`resolve-identity` follows the same runner/container passthrough every
other job in this stage already does).

**Project Type**: Single project — a GitHub Actions reusable-workflow
pipeline component; no application `src`/`tests` split applies.

**Performance Goals**: One additional job on every `pr-conversation` run
(`resolve-identity`), costing one `gh repo view` and one `gh pr view` call —
work that `classify-and-announce`'s identity step already performs today, so
this is a relocation, not new API traffic. `stalled` itself gains no new
work when it does not run (unchanged trigger surface, User Story 3).

**Constraints**:
- FR-017/Constitution VII: no `workflow_call` input, output, or secret of
  `pr-conversation.yml` changes; no adopter wrapper needs editing.
- FR-009/FR-010: the qualification verdict and every existing downstream
  reference to the entry job's identity outputs must resolve identically —
  this plan only moves *where* the computation happens, never *what* it
  computes (research.md D1).
- FR-005/FR-007: `resolve-identity` fails loudly on an unreadable API
  response and stays green with `qualifies: false` for an ordinary
  non-qualifying head ref — the same two branches the step it replaces
  already implements, unchanged.
- FR-008/FR-018: the survivor job's group must never degenerate to the
  bare `wing-commander-` constant; Gate 80's widened acceptance must not
  admit any string that isn't this exact fallback spelling.
- FR-012: the slug-from-head-ref derivation exists in exactly one place
  (`resolve-identity`) once this change lands — down from three occurrences
  (data-model.md).

**Scale/Scope**: One file changed (`.github/workflows/pr-conversation.yml`:
one new job, two jobs rewired), one waiver entry removed
(`.github/scripts/spec-branch-push-waivers.json`), one gate script amended
(`.github/scripts/verify-spec-branch-push-concurrency.py`), one existing
cross-spec contract amended (`specs/013-serialize-rebase-stages/contracts/concurrency-groups.md`),
one existing cross-spec decision record amended
(`specs/041-implement-stall-notice/research.md` D6). No new composite
action, no new gate.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | Built through the pipeline itself (issue #581 → this spec → this plan → tasks → implement), validated by the same gate-registry machinery the repository already checks itself with. | ✅ Pass |
| II. Cost-Conscious Model Tiering | This plan runs at `claude-sonnet-5` (planning-weight default, no clarification needed above). The feature adds no new agent invocation — `resolve-identity` is deterministic bash, matching every other identity-resolution step in this fleet. | ✅ Pass |
| III. Simple, GitHub-Native Interaction | No new interaction surface — the stall notice still lands via `gh issue comment` on the same target (the lifecycle issue, or the PR when identity is unresolved) it lands on today. | ✅ Pass |
| IV. Automation-First | No manual step is introduced or removed; this is a purely internal ordering fix. | ✅ Pass |
| V. Security — untrusted content is never instructions | No new untrusted-content path. `resolve-identity` reads only `gh`'s own structured JSON about the PR (`baseRefName`, `headRefName`) and the repository's default branch — the same two calls the step it replaces already makes, over the same declared `workflow_call` inputs. | ✅ Pass |
| VI. Portability — consuming repo owns its artifacts | No new artifact path; `resolve-identity` reads no repository-specific file (no checkout at all). | ✅ Pass |
| VII. Two Interfaces — published contract vs. consuming instrument | FR-017 checked explicitly: no `workflow_call` input/output/secret of `pr-conversation.yml` changes. `resolve-identity` is an internal job of the published stage, not itself a new contract surface — no adopter-facing name to pin. | ✅ Pass |
| VIII. A Green Check Means What It Says | Gate 80's widened acceptance is checked by new self-test fixtures (the accepted spelling passes; a near-miss — wrong job name, wrong literal text — still fails), not by "the repository currently passes" alone (SC-008). | ✅ Pass |
| IX. Judgment That Gates a Durable Action Belongs in Deterministic Code | The fallback-vs-canonical group choice is a plain YAML ternary evaluated by GitHub Actions itself, and Gate 80's acceptance of it is a regex match against the literal expression text — no model judgment gates the push. | ✅ Pass |

**Post-Phase-1 re-check**: Unchanged. Phase 1 design (data-model.md,
contracts/) confirms the only new compatibility-relevant surface is the
internal job graph of one already-published stage (no `workflow_call`
change) and a widened, exactly-matched acceptance rule in an existing gate
script.

## Project Structure

### Documentation (this feature)

```text
specs/077-stalled-per-spec-group/
├── plan.md                                  # This file (/speckit-plan command output)
├── research.md                              # Phase 0 output (/speckit-plan command)
├── data-model.md                            # Phase 1 output (/speckit-plan command)
├── quickstart.md                            # Phase 1 output (/speckit-plan command)
├── contracts/                               # Phase 1 output (/speckit-plan command)
│   ├── resolve-identity-job.md              # the new job's contract
│   ├── stalled-job-concurrency.md           # stalled's widened if:/concurrency, and the exact
│   │                                         #   amendment to specs/013's concurrency-groups.md
│   └── gate-80-fallback-spelling.md         # the new accepted regex + required self-test cases
├── checklists/
│   └── requirements.md                      # already present (intake stage output)
├── spec-meta.json
└── tasks.md                                 # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source code (repository root)

This repository is a GitHub Actions pipeline, not a conventional
library/service — there is no `src`/`tests` split. The real layout this
feature touches:

```text
.github/
├── workflows/
│   └── pr-conversation.yml                    # + resolve-identity job (new);
│                                               #   classify-and-announce: drops its own
│                                               #   identity step, reads needs.resolve-identity.*;
│                                               #   stalled: drops its independent re-derivation,
│                                               #   reads needs.resolve-identity.*, widened if:,
│                                               #   canonical + per-PR-fallback concurrency group
│   └── lint-workflows.yml                     # UNCHANGED — Gate 80 already registered;
│                                               #   only the script it invokes changes
└── scripts/
    ├── verify-spec-branch-push-concurrency.py # + fourth accepted group spelling (the per-PR
    │                                           #   fallback), + self-test cases (SC-008)
    └── spec-branch-push-waivers.json          # - the pr-conversation.yml/stalled waiver (FR-003)

specs/
├── 013-serialize-rebase-stages/contracts/
│   └── concurrency-groups.md                  # + stalled row in Members table (FR-004);
│                                               #   + resolve-identity job contract, alongside
│                                               #   the existing resolve-spec contract
└── 041-implement-stall-notice/research.md     # D6's pr-conversation row amended: derivation-only
                                                #   prerequisite job, not independent re-derivation
                                                #   (FR-019)
```

**Structure Decision**: One workflow file gains one job and two rewired
jobs; one gate script gains one accepted spelling; two other specs' existing
contract/decision documents gain a row each, both amendments already
required by this feature's own FR-004/FR-019 rather than incidental scope
creep. No new top-level directory, no new composite action, no change to
`pr-conversation.yml`'s declared `workflow_call` surface.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — table intentionally omitted.
