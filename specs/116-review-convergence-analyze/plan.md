# Implementation Plan: Review Loops That Notice They Aren't Converging, and an Analyze Check Before Folded Review Tasks Reach Implement

**Branch**: `spec/116-review-convergence-analyze` | **Date**: 2026-10-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/116-review-convergence-analyze/spec.md`

**Scope split (2026-10-19)**: Story 3 (FR-011..017, the fold-time analyze check and its holds) moved to proposal #1066. The plan below keeps its Story 3 items only as pointers to #1066.

## Summary

Two deterministic additions, built in dependency order (a third, the fold-time analyze check, moved to #1066):

1. **Recurrence** (Story 1, FR-001..003). The lifecycle gate's `disposition` partition step stops dropping a finding whose fingerprint an earlier round already folded; it classifies it `recurrence`, keeps the round non-clean, and names it. The board loop gets the same ledger for fixed findings.
2. **Convergence signals and the `not-converging` stop** (Stories 2, 4, FR-004..010, FR-018, FR-019). The arithmetic in `.claude/skills/review-until-clean/scripts/thrash_signals.py` moves to one module under `.github/scripts/` (`wc_convergence.py`), gains a pure decision function (`decide(history) -> signals + tripped rules`) and a thresholds table that is the only place the FR-006 numbers appear. Both loops and the skill call it. Reviewer schemas gain an optional `line`; the module validates it at the reviewed head. A new gate fails if a second copy of the arithmetic appears.
3. **Fold-time analyze check** (Story 3, FR-011..017): moved to #1066.

Story 5 / part 3 is out of scope (FR-020): no reviewer prompt or published contract change for it.

## Technical Context

**Language/Version**: Python 3.11+ for scripts and gates (matches `.github/scripts/`); Bash inside composite `run:` steps; GitHub Actions YAML.

**Primary Dependencies**: git (blame, diff, merge-base), `jq`, `gh`.

**Storage**: Per-PR state in existing GitHub artifacts: the lifecycle gate's round record comments/markers (already carry `folded_fingerprints`/`filed_fingerprints`), extended with per-round head SHA, finding lines and counts. No new datastore. See [data-model.md](data-model.md).

**Testing**: Python fixture tests beside each new `verify-*.py` (checked-in failure-branch fixtures, constitution VIII); `thrash_signals.py --self-test` logic ported into a unit-test module for `wc_convergence`; replay fixtures built from #954/#969 histories (SC-002) and #833's recurrence (SC-001). Full gate suite: `python .github/scripts/run-local-gates.py`.

**Target Platform**: GitHub Actions ubuntu runners, including caller-supplied container jobs (so any new `run:` step in a container job sets `shell: bash`; see `container-shell-safety`).

**Project Type**: CI/CD pipeline repository (workflows, composite actions, scripts, gates).

**Performance Goals**: Signal computation is O(findings + changed hunks) per round; no new agent invocation.

**Constraints**: 5-round budget unchanged (FR-009); no edits under `.claude/skills/speckit-*`; agents never write `.claude/` (Constitution V) — the `review-until-clean` skill edit is made by the implement stage's deterministic path only if permitted, otherwise see research D9.

**Scale/Scope**: ~1 new script module, 1 gate, edits to 2 workflows (`lifecycle-review-gate.yml`, `board-loop.yml`), 1 skill script.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1.*

| Principle | Assessment |
|---|---|
| I Guide | Built through the pipeline; the spec is the worked example. PASS |
| II Model tiering | No new agent (the analyze step moved to #1066). PASS |
| III GitHub-native | The hand-off is posted on the lifecycle issue or PR, as the budget hand-off is. PASS |
| IV Automation-first | No new owner touchpoint beyond the existing budget hand-off, now also reached by `not-converging`. PASS |
| V Security | Reviewer text (titles, paths) reaches markers and the hand-off only escaped; signals are computed from git, never agent-supplied. PASS |
| VI Portability | Reads the PR's own reviews and spec-dir; no hardcoded repo names. PASS |
| VII Two interfaces | No published composite input or output changes; the reviewer's `line` is optional. PASS |
| VIII Green means green | One new gate (single-home arithmetic) with fixtures for every failure branch. PASS |
| IX Deterministic judgment | Recurrence, thresholds and stop all in code; the reviewer only proposes findings. PASS |
| X Bounded autonomy | `not-converging` reuses the budget-exhaustion hand-off; PR never merged by a stopped loop (SC-006). PASS |

Post-design re-check: PASS, no violations.

## Project Structure

### Documentation (this feature)

```text
specs/116-review-convergence-analyze/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── convergence-signals.md   # module API, thresholds, hand-off marker (consuming instrument + _shared)
└── tasks.md                     # /speckit-tasks output
```

### Source Code (repository root)

```text
.github/
├── scripts/
│   ├── wc_convergence.py                       # NEW: single home — attribution, churn, growth, recurrence, thresholds, decide()
│   ├── wc_convergence_tests/                   # NEW: unit tests + #954/#969/#833 replay fixtures
│   └── verify-convergence-single-home.py       # NEW gate (FR-019) + fixtures dir
└── workflows/
    ├── lifecycle-review-gate.yml               # recurrence class, signals, not-converging
    └── board-loop.yml                          # signals + not-converging for review rounds
.claude/skills/review-until-clean/
├── SKILL.md                                    # call the shared module
└── scripts/thrash_signals.py                   # becomes a thin caller of wc_convergence
```

**Structure Decision**: Single repository, script-and-composite layout following existing conventions; shared arithmetic under `.github/scripts/`, shared shell (if any) under `.github/actions/_shared/` (CLAUDE.md "one home").

## Complexity Tracking

None. (The additive published-contract surface of the fold-analyze composite moved to #1066 with Story 3.)
