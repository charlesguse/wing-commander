# Implementation Plan: Board Loop Merges Its Own Fix-Class and Dependency-Bump PRs

**Branch**: `spec/115-board-loop-self-merge` | **Date**: 2026-10-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/115-board-loop-self-merge/spec.md`

## Summary

Add one new job, `merge`, to `.github/workflows/board-loop.yml`, downstream of `readiness`. It runs only while `vars.WING_COMMANDER_BOARD_AUTO_MERGE == 'true'`. It re-derives every merge condition in deterministic Python (`board_merge.py`) from a fresh `gh pr view` snapshot of the exact head SHA. It then calls `gh pr merge --squash --match-head-commit <sha>`, announces the result or the refusal on the PR and the issue, and hands the item off. The fix class reuses `board_readiness.evaluate_from_snapshot`. The dependency-bump class is a second evaluator with no backstop; it is gated on a bot-authored verification record that the auto-update stage's act job writes on its PR. With the switch off, the readiness job is byte-for-byte today's behaviour. After an Actions-only merge, the existing prove-gate/prove path (spec 096) picks the merged item up.

## Technical Context

**Language/Version**: Python 3 (stdlib only, run with `python3 -I`), GitHub Actions YAML, bash

**Primary Dependencies**: `gh` CLI, existing `board_readiness.py`, `board_item_marker.py`, `lifecycle_merge_preconditions.py` (pattern only), composite `wing-commander-board-stop-check`

**Storage**: Hidden-marker comments on the issue and PR (existing marker pattern); no new files at runtime

**Testing**: A new gate `verify-board-merge.py` driving checked-in fixtures (FR-015); the full suite via `python .github/scripts/run-local-gates.py`

**Target Platform**: GitHub Actions (ubuntu-latest)

**Project Type**: CI pipeline / workflow tooling

**Performance Goals**: Merge within the same run that reaches readiness, or the next scheduled run (SC-001)

**Constraints**: One item at a time under the `wing-commander-board-loop` concurrency group; the App has no Workflows permission, so workflow-touching PRs end in a handover; never `--admin`, never approve, never enable auto-merge

**Scale/Scope**: One new job, two new scripts, one new marker kind, one record emission in the auto-update act job, one gate, fixtures

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Result |
|-----------|--------|
| III (findings posted on the PR) | Pass. The independent review is unchanged and the merge reads its converged outcome. |
| VII (published contract) | Pass. This adds a repo variable and workflow job and widens no consumer-facing contract. Gate parity checks are extended. |
| VIII (head with no checks is not green) | Pass. The evaluator reuses `_checks_green`, which treats an empty rollup as not green. |
| IX (durable action behind deterministic code) | Pass. `board_merge.py` decides; no agent judgment gates the merge. |
| X (bounded autonomy) | Pass. Both classes are authorized as worded at 2.5.0, with squash commits, a kill switch, a pinned SHA and prove after merge. |

No violations. Complexity Tracking is empty. Post-design re-check: still passes. The one new trust surface, the verification record, is bot-authored and SHA-bound, and `board_merge.py` reads it only from the bot's own login.

## Project Structure

### Documentation (this feature)

```text
specs/115-board-loop-self-merge/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── board-merge.md
└── tasks.md             # tasks stage
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   ├── board-loop.yml                 # new `merge` job; readiness gains outputs
│   └── auto-update-spec-kit.yml       # act job posts the verification record
├── scripts/
│   ├── board_merge.py                 # pure evaluators (fix, bump) + refusal classifier
│   ├── board_item_marker.py           # new merged / handed-over steps
│   ├── verify-board-merge.py          # new gate: fixtures per condition and refusal
│   ├── verify-board-readiness.py      # kept: switch-off text unchanged
│   ├── verify-constitution-merge-class-parity.py  # extended for the new variable
│   └── fixtures/board-merge/*.json
└── actions/_shared/                   # reuse resolve-pr-branch; no new composite expected
```

**Structure Decision**: Single home for the decision logic is `board_merge.py`, so neither the workflow nor the gate carries a copy. The merge step and announcement live only in the `merge` job. The readiness job keeps its report and marker, which still read "Awaiting a human merge" when the switch is off.

## Complexity Tracking

None.
