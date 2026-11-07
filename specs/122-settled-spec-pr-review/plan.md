# Implementation Plan: Review a Spec PR Automatically Once Clarification Has Settled It

**Branch**: `spec/122-settled-spec-pr-review` | **Date**: 2026-11-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/122-settled-spec-pr-review/spec.md`

## Summary

Add a consuming-instrument workflow, `spec-pr-review.yml` (wrapper, not a
published stage), that on a schedule and by maintainer dispatch selects open
`spec-draft/…` PRs that are *settled* (FR-002), runs one independent Opus
`code-review` round per head, and posts a `COMMENT` review with a
deterministically computed verdict, structured findings and spec 116's round
record. Unambiguous errors are pushed to the branch under a path/size/citation
backstop (FR-026); owner decisions are written as colon-form clarification
markers plus issue questions and move the issue to `stage:clarify`
(FR-015c). Bounds: round budget (5), spec 116 convergence check, failed-attempt
cap (2) and a `WING_COMMANDER_SPEC_REVIEW_PAUSED` kill switch.

All judgment that gates a durable action (settledness, eligibility, verdict,
fix checks, label move, announcement, caps) lives in one new Python module
with checked-in fixtures reachable through the gate registry (IX, VIII).
Selection, head bookkeeping, findings rendering, cost line, convergence and
the marker scan are consumed from their existing single homes (FR-023).

## Technical Context

**Language/Version**: Python 3 (gate/decision scripts under `.github/scripts/`), Bash in `run:` steps, GitHub Actions YAML

**Primary Dependencies**: `anthropics/claude-code-action` (as `lifecycle-review-gate.yml` uses it); existing composites `wing-commander-context`, `-tool-args`, `-turn-ceiling`, `-agent-verdict`, `-metrics-summary` (cost-line), `-post-review-comment`, `-clarification-marker`, `-size-path-backstop`, `-hardened-push`, `-refresh-remote`, `-callout`, `-stage-findings`; `wc_convergence.py`, `wc_review_finding_fingerprint.py`, `wc_lifecycle_review_marker.py`, `wc_gate_registry.py`, `git_read.py`

**Storage**: No new store. Round state is read back from the App's own PR reviews (spec 116 round records), the head-SHA bookkeeping spec 062 uses, and issue comments (announcements, failed-attempt notes)

**Testing**: `verify-spec-pr-review.py` (decision module fixtures) plus wiring/provenance verifiers modelled on `verify-lifecycle-review-gate-composite-provenance.py`; run via `python .github/scripts/run-local-gates.py`

**Target Platform**: GitHub Actions (ubuntu runners, caller container rules per `container-shell-safety`)

**Project Type**: CI pipeline / consuming-instrument workflow

**Performance Goals**: One Opus round per settled head; scheduled selection costs no agent turns when nothing is eligible

**Constraints**: App holds no `Actions: write` and no Commit statuses permission (status uses workflow token, job-level `statuses: write`); never check out fork heads; spec-dir-only pushes; reviewer never approves/requests changes/merges; no new stage in the published contract

**Scale/Scope**: A handful of open spec PRs at a time; ≤5 rounds per PR

## Constitution Check

*Gate: passes before Phase 0 and after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I Guide | Built through the pipeline; PR #-chain is the worked example. Pass |
| II Model tiering | Explicit `claude-opus-5-5`, `high`, bounded `--max-turns`, overridable by repo variable (FR-008). Pass |
| III GitHub-native | Result on PR; one-line outcome and questions on lifecycle issue. Pass |
| IV Automation-first | Removes the manual local review. Pass |
| V Security | Untrusted-data framing; App-authored announcement only; no fork heads; no approve/merge; bot-actor dispatch not a maintainer's; writes under `.claude/` impossible (path bound = spec dir). Pass |
| VII Two interfaces | Wrapper workflow + `_shared`/script logic; no published stage or input added (FR-022). Pass; verifier asserts it |
| VIII Green means green | Every decision branch has a fixture; gate registered; fail-loud on unreachable subject. Pass |
| IX Deterministic judgment | Verdict, settledness, fix-check, label move all in code; agent only proposes findings/classification. Pass |
| X Bounded autonomy | Does not touch the three merge classes; spec-dir fixes are bounded by size/path backstop in the same spirit. Pass |

No violations; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/122-settled-spec-pr-review/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── spec-pr-review-workflow.md
│   └── decision-module.md
└── tasks.md             # tasks stage
```

### Source Code (repository root)

```text
.github/workflows/spec-pr-review.yml            # schedule + workflow_dispatch(pr); select → review → act jobs
.github/scripts/spec_pr_review.py               # decision module: settled, eligible, verdict, fix checks, label/announce, caps
.github/scripts/verify-spec-pr-review.py        # fixtures for every decision branch (registered gate)
.github/scripts/verify-spec-pr-review-wiring.py # composite provenance, kill switch, no-approve/merge, no published-surface change
.github/scripts/spec-pr-review-fixtures/        # settled/unsettled/dispatch/fix-check/cap cases
docs/setup.md                                   # new variables + kill switch (documented surface)
```

**Structure Decision**: Mirror `lifecycle-review-gate.yml`'s select/review/act job split in a new wrapper workflow; new decision logic in one script that imports the existing convergence, fingerprint and marker helpers rather than copying them. Shared steps already in composites are reused unchanged.

## Complexity Tracking

None.
