# Implementation Plan: Implement Finishes Its Tasks

**Branch**: `spec/123-implement-task-completion` | **Date**: 2026-11-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/123-implement-task-completion/spec.md`

## Summary

Implement cycles stop after one slice, tasks no cycle can finish hold the loop open, and folded review findings consume the cap. The plan extends the one existing home for tasks.md classification (`count-tasks-checkboxes.sh`, spec 117) with two new line classes (deterministically-unbuildable tasks, folded review findings), threads the resulting "buildable" count through the one stop rule (`decide-implement-outcome.sh`), finalize and the lifecycle review gate, adds a "keep building" instruction to the implement prompt, records a per-cycle outcome line, and ships a one-time migration for lifecycles already stranded at `review`. Lever (b) (low-progress escalation) is deferred per the spec.

## Technical Context

**Language/Version**: Bash + awk + jq (shared scripts under `.github/actions/_shared/`), GitHub Actions YAML, Python 3 for `verify-*.py` gates

**Primary Dependencies**: `gh` CLI, `git`, existing composites (`wing-commander-tasks-checkbox-count`, `wing-commander-implement-outcome`, `wing-commander-remaining-work`, `wing-commander-write-boundary`, `wing-commander-spec-meta`)

**Storage**: `tasks.md`, `spec-meta.json` (git), lifecycle issue comments/labels

**Testing**: checked-in fixtures under `.github/scripts/fixtures/123-implement-task-completion/` driven by `verify-*.py` gates; `python .github/scripts/run-local-gates.py`

**Target Platform**: GitHub Actions runners (and consuming repos via the published composite)

**Project Type**: CI pipeline / shared-script library

**Performance Goals**: N/A (SC-001/SC-002 are post-merge outcome measures)

**Constraints**: One home for classification (FR-017); deterministic code decides convergence (constitution IX); published composite output meanings change must be announced (constitution VII); every agent step keeps explicit model and turn budget (II); no writes under `.claude/` by agents (V)

**Scale/Scope**: ~5 shared scripts/composites, 3 workflows (implement, finalize, lifecycle-review-gate), 1 migration script, fixtures + gates

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1.*

| Principle | Assessment |
|---|---|
| I Guide | Built through the pipeline; PR cites spec 123 / #1111. PASS |
| II Model tiering | No new agent step; no model change; lever (b) deferred so no escalation. PASS |
| III GitHub-native | Outcomes reported on the lifecycle issue; resume by label/dispatch. PASS |
| IV Automation-first | Removes manual restarts for unbuildable-task stalls. PASS |
| V Security | Classification only reads tasks.md as data; `.claude/` writes routed to maintainer. PASS |
| VI Portability | Consumer-owned artifacts untouched; migration touches only this repo's lifecycles. PASS |
| VII Two interfaces | Composite `wing-commander-tasks-checkbox-count` output meanings change; contract amended and announced (see contracts/). PASS with obligation |
| VIII Green means what it says | Fixtures per failure branch (FR-017); "single home" check added to an existing gate. PASS |
| IX Deterministic judgment | Classification, counting, cap outcome, finalize/gate wait all in shell, not agent. PASS |
| X Bounded autonomy | Hand-off at cap stays human-gated; no new self-dispatch. PASS |

Post-design re-check: unchanged; no violations, Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/123-implement-task-completion/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── buildable-classification.md
└── tasks.md             # produced by the tasks stage
```

### Source Code (repository root)

```text
.github/actions/_shared/
├── count-tasks-checkboxes.sh          # extend: unbuildable + fold classes, buildable-* outputs
├── classify-out-of-boundary-tasks.sh  # reused for the write-boundary class (extend only if needed)
├── decide-implement-outcome.sh        # cap/blocker hand-off keyed on buildable count; fold-aware convergence
├── render-remaining-work.sh           # list buildable + maintainer-only at hand-off
└── migrate-stranded-review-lifecycles.sh   # new: FR-018 one-time, idempotent
.github/actions/
├── wing-commander-tasks-checkbox-count/action.yml   # new outputs
├── wing-commander-implement-outcome/action.yml      # pass new inputs, emit cycle-outcome line
└── wing-commander-remaining-work/action.yml
.github/workflows/
├── implement.yml     # prompt "keep building"; cycle outcome record; lift stage:stalled on resumed cycle
├── finalize.yml      # refuse final PR while buildable tasks remain
└── lifecycle-review-gate.yml   # skip a final PR with unchecked buildable tasks
.github/scripts/
├── verify-buildable-classification.py          # new gate
├── verify-finalize-buildable-wait.py           # new gate (or folded into one)
└── fixtures/123-implement-task-completion/
specs/117-implement-stall-handoff/contracts/shared-scripts.md   # live contract, amended
```

**Structure Decision**: No new top-level layout. All classification stays in `count-tasks-checkboxes.sh`; the other readers consume its outputs through the composite (research D1).

## Complexity Tracking

No violations.
