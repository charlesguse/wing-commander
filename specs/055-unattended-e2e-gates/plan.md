# Implementation Plan: Unattended Passage of the Pipeline's Human Gates in End-to-End Release Verification

**Branch**: `spec/055-unattended-e2e-gates` | **Date**: 2026-09-19 | **Spec**: [specs/055-unattended-e2e-gates/spec.md](./spec.md)

**Input**: Feature specification from `/specs/055-unattended-e2e-gates/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

`auto-release.yml`'s `verify-e2e` job has never reached a verdict
unattended — it stops at the first of four points where the published
pipeline stages wait for a human (a clarification reply, and three PR
merges: spec, plan, finalize). This plan drives all four from inside the
job's existing `poll` loop, using a dedicated real GitHub user account
(never a bot) whose classic PAT is contained to the disposable test
repository alone by the account's own memberships plus a runtime
containment check (not by token scoping — a fine-grained PAT cannot be
issued for a repository the account only collaborates on, research.md
D1), so the pipeline's own actor gates accept it exactly as they accept a
maintainer today. The clarification reply and every merge
decision are deterministic — a fixed pre-authored answer, and a merge
attempted only once GitHub reports the PR mergeable — never an agent's
judgment call (Constitution IX). A new outcome class, `fail-gate-stall`,
lets a stalled gate surface immediately and be classified distinctly from
both a generic poll timeout and a genuine pipeline defect, reusing the
existing verdict shape and durable one-report-per-head mechanics
unchanged. No published stage workflow changes; the only files touched are
this repository's own wrapper (`auto-release.yml`), two new pure decision
scripts under `.github/actions/_shared/`, the existing verdict/report
plumbing, and docs.

## Technical Context

**Language/Version**: Bash (POSIX-ish, matching the rest of `auto-release.yml`) driven from GitHub Actions YAML; `jq` for JSON construction/inspection.

**Primary Dependencies**: GitHub CLI (`gh`) against the test repository's REST/GraphQL surface (`gh issue view`, `gh pr list`, `gh pr merge`, `gh issue comment`); the existing `_shared/auto-release-verdict.sh` and `_shared/durable-failure-issue` composite; no new external dependency.

**Storage**: N/A — all state is GitHub-native (issue comments, PR merge state, labels) in the disposable test repository; nothing is persisted to this repository's own tree beyond the workflow/script/doc changes themselves.

**Testing**: Python fixture-style unit tests under `.github/scripts/`, following the existing `verify-auto-release-report.py` pattern (Constitution VIII: every gate runs the same subject/args locally as in CI); the two new decision scripts (contracts/gate-decision-scripts.md) are pure functions of already-fetched JSON, so they are testable with checked-in fixtures with no live network call, and `run-local-gates.py` picks them up automatically once wired into `lint-workflows.yml`'s existing gate registry.

**Target Platform**: GitHub Actions hosted runner (`ubuntu-latest`), inside the existing `verify-e2e` job of `auto-release.yml` — schedule/`workflow_dispatch`-only, unchanged.

**Project Type**: Single project — this is a CI/CD workflow feature (GitHub Actions YAML + shell), not an application with a src/tests split.

**Performance Goals**: N/A (not a request-serving system); the relevant budget is wall-clock and dollar cost per attempt (see Constraints).

**Constraints**: No modification to any published stage workflow (`.github/workflows/{intake,clarify,plan,tasks,implement,converge,finalize,cleanup,watchdog}.yml`) or to the documented wrapper set `docs/adoption.md` names (FR-004); every gate-driving decision must be deterministic code, never an agent's judgment (Constitution IX, FR-005); the new credential must be provably scoped to the test repository alone and read by no other job (FR-011, FR-003a); the poll budget (`POLL_BUDGET_SECONDS`) and the job's own `timeout-minutes` must agree on which fires first (research.md D13); a stalled gate must be classified as `fail-gate-stall` and surfaced before the full poll budget elapses, not just relabeled after the fact.

**Scale/Scope**: One job (`verify-e2e`) in one workflow; two new files under `.github/actions/_shared/`; edits to `auto-release.yml`'s `poll` and `report` jobs, `.github/scripts/verify-auto-release-report.py`'s fixtures, and `docs/setup.md`'s prerequisite list. No new jobs, no new workflows, no new composite actions resolved by any published stage.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Guide — repo is its own first example | This feature is itself specified, planned, and implemented through the pipeline (spec/plan/tasks/implement on issue #386). No violation. |
| II. Cost-Conscious Model Tiering | No new Claude/agent invocation is introduced — every gate-driving decision is deterministic shell (research.md D5/D6, Constitution IX), not a model call. N/A, not a violation. |
| III. Simple, GitHub-Native Interaction | Unaffected — this feature changes only an internal verification job's own behavior, not how a requester interacts with the pipeline. |
| IV. Automation-First | Directly advances this principle for the verification path itself: the four remaining manual acts in `verify-e2e` become automated, with the machine identity's every act reported (FR-015, FR-019), not silently assumed. |
| V. Security — untrusted content is never instructions; humans merge to `main`; the bot never merges to `main` | The fixture maintainer identity merges PRs only inside the disposable, force-reset test repository (research.md D1) — never this repository, never any adopter's `main`. The spec's own Assumptions section states Principle V governs this repository and the published product, and that the test repository's disposability is precisely why an unattended merge there is discussable at all; FR-011–FR-015 are this feature's containment obligations under that reading. This is not a widening of what an adopter's pipeline can do to their own `main` — the published stage workflows' actor and merge gates are unchanged (FR-012), verified by Scenario 4 in quickstart.md. Reviewed, no violation; not logged in Complexity Tracking because the spec itself pre-justifies the exception rather than this plan introducing a new one. |
| VI. Portability | Unaffected — nothing here is read from or resolved into a consuming repository; this is entirely this repository's own wrapper-level verification. |
| VII. Two Interfaces | The only files touched are the consuming instrument (`auto-release.yml`, a `wing-commander-*`-pattern-adjacent internal wrapper with no `workflow_call` trigger) and two new `_shared/` scripts, matching the existing `auto-release-verdict.sh` precedent (single-workflow shared logic, not published-contract composites; research.md D5). No published `workflow_call` stage or `.github/actions/**` composite resolved by one changes. FR-004 is satisfied by construction. |
| VIII. A Green Check Means What It Says | Central to this feature's own Requirements (FR-016–FR-020): every driven gate gets a positive, machine-observable assertion (data-model.md's Lifecycle gate table), a stalled gate fails loudly as `fail-gate-stall` rather than reporting a pass it didn't earn, and every new failure branch ships with a checked-in fixture (contracts/gate-decision-scripts.md, contracts/verdict-extension.md). The two new decision scripts are deliberately pure (fetch stays in the workflow step) so they can run the same subject with the same arguments locally as in CI. |
| IX. Judgment That Gates a Durable Action Belongs in Deterministic Code | FR-005 requires this explicitly, and the spec cites the principle by name. The clarification reply is a fixed literal (research.md D8); the merge decision is a deterministic function of GitHub's own `mergeable`/`mergeStateStatus` fields (research.md D6/D9) — no agent ever decides whether to answer or merge. |

No entries required in Complexity Tracking — no principle is violated; the
one principle (V) whose scope needed reasoning through is addressed above
with the spec's own pre-existing justification, not a new exception this
plan is introducing.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
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
│   └── auto-release.yml                          # MODIFIED: verify-e2e's poll loop gains gate-driving;
│                                                   #   token/reachable steps gain the new credential check;
│                                                   #   report job's classification step becomes three-way
├── actions/
│   └── _shared/
│       ├── auto-release-verdict.sh                # UNCHANGED — new outcome value, no schema change
│       ├── auto-release-e2e-clarify-decision.sh   # NEW — contracts/gate-decision-scripts.md
│       └── auto-release-e2e-merge-decision.sh     # NEW — contracts/gate-decision-scripts.md
└── scripts/
    └── verify-auto-release-report.py              # MODIFIED: new fixtures for fail-gate-stall,
                                                     #   the three-way classification, and the two new
                                                     #   decision scripts' branches

docs/
└── setup.md                                        # MODIFIED: new secret prerequisite row +
                                                       #   resume-condition prose (research.md D14)

specs/055-unattended-e2e-gates/
├── plan.md              # This file
├── research.md           # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
└── contracts/            # Phase 1 output
    ├── gate-decision-scripts.md
    └── verdict-extension.md
```

**Structure Decision**: Single project — this feature has no application
source tree, only workflow/script/doc edits inside the paths above.
Nothing under `.github/workflows/<stage>.yml` (the published contract) or
`docs/adoption.md` (the adopter-facing surface) changes, per FR-004 and
Constitution Principle VII; every touched path is either this repository's
own consuming-instrument wrapper, single-workflow shared logic already
living in `_shared/` (research.md D5), or this-repository-only
documentation.

## Complexity Tracking

*No entries — the Constitution Check above found no violation requiring
justification.*
