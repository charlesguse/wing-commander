# Implementation Plan: Review Loops That Notice They Aren't Converging, and an Analyze Check Before Folded Review Tasks Reach Implement

**Branch**: `spec/116-review-convergence-analyze` | **Date**: 2026-10-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/116-review-convergence-analyze/spec.md`

## Summary

Three deterministic additions, built in dependency order:

1. **Recurrence** (Story 1, FR-001..003). The lifecycle gate's `disposition` partition step stops dropping a finding whose fingerprint an earlier round already folded; it classifies it `recurrence`, keeps the round non-clean, and names it. The board loop gets the same ledger for fixed findings.
2. **Convergence signals and the `not-converging` stop** (Stories 2, 4, FR-004..010, FR-018, FR-019). The arithmetic in `.claude/skills/review-until-clean/scripts/thrash_signals.py` moves to one module under `.github/scripts/` (`wc_convergence.py`), gains a pure decision function (`decide(history) -> signals + tripped rules`) and a thresholds table that is the only place the FR-006 numbers appear. Both loops and the skill call it. Reviewer schemas gain an optional `line`; the module validates it at the reviewed head. A new gate fails if a second copy of the arithmetic appears.
3. **Fold-time analyze check** (Story 3, FR-011..017). A new composite `wing-commander-fold-analyze` runs between `wing-commander-fold-commit` and `wing-commander-fold-dispatch` (both callers: `pr-conversation.yml` `act` path and `lifecycle-review-gate.yml` `disposition`). It runs the vendored `/speckit-analyze` read-only on `claude-sonnet-5-5`, with a bounded `--max-turns`, schema-constrained output. Deterministic code (a script in the composite) decides hold vs dispatch: hold only on a constitution conflict, or on an analyze step failure (FR-013). Hold posts an owner question; the owner's answer releases it.

Story 5 / part 3 is out of scope (FR-020): no reviewer prompt or published contract change for it.

## Technical Context

**Language/Version**: Python 3.11+ for scripts and gates (matches `.github/scripts/`); Bash inside composite `run:` steps; GitHub Actions YAML.

**Primary Dependencies**: git (blame, diff, merge-base), `jq`, `gh`, `anthropics/claude-code-action` (already used by stage workflows), vendored `/speckit-analyze` (used as-is).

**Storage**: Per-PR state in existing GitHub artifacts: the lifecycle gate's round record comments/markers (already carry `folded_fingerprints`/`filed_fingerprints`), extended with per-round head SHA, finding lines and counts. No new datastore. See [data-model.md](data-model.md).

**Testing**: Python fixture tests beside each new `verify-*.py` (checked-in failure-branch fixtures, constitution VIII); `thrash_signals.py --self-test` logic ported into a unit-test module for `wc_convergence`; replay fixtures built from #954/#969 histories (SC-002) and #833's recurrence (SC-001); composite fixture tests in the style of `wing-commander-fold-queue-*-tests/run-tests.sh`. Full gate suite: `python .github/scripts/run-local-gates.py`.

**Target Platform**: GitHub Actions ubuntu runners, including caller-supplied container jobs (so any new `run:` step in a container job sets `shell: bash`; see `container-shell-safety`).

**Project Type**: CI/CD pipeline repository (workflows, composite actions, scripts, gates).

**Performance Goals**: Signal computation is O(findings + changed hunks) per round; one extra agent invocation per non-empty fold (bounded `--max-turns`).

**Constraints**: 5-round budget unchanged (FR-009); no edits under `.claude/skills/speckit-*`; agents never write `.claude/` (Constitution V) — the `review-until-clean` skill edit is made by the implement stage's deterministic path only if permitted, otherwise see research D9; published-contract surface widened only deliberately (FR-016).

**Scale/Scope**: ~1 new script module, 1 new composite, 2 gates, edits to 3 workflows (`lifecycle-review-gate.yml`, `board-loop.yml`, `pr-conversation.yml`), 2 composites (`fold-commit` outputs, `fold-dispatch` hold input), 1 skill script.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1.*

| Principle | Assessment |
|---|---|
| I Guide | Built through the pipeline; the spec is the worked example. PASS |
| II Model tiering | Analyze step declares `claude-sonnet-5-5` and `--max-turns` (FR-016). No other new agent. PASS |
| III GitHub-native | Hold is an owner question on the lifecycle issue; answered by an ordinary comment. PASS |
| IV Automation-first | Only a constitution conflict or a failed check adds an owner touchpoint (FR-012/013); reported explicitly. PASS |
| V Security | Analyze agent is read-only with least-privilege tools, no web, no writes under `.claude/`; fold section text and findings treated as data. Hold-release comment authorization reuses the maintainer check. PASS |
| VI Portability | Reads the project folder's own constitution/spec via spec-dir; no hardcoded repo names. PASS |
| VII Two interfaces | New composite inputs/outputs are deliberate, additive and optional (backward-compatible); `_shared/` used for cross-composite shell. Wrapper-owned: thresholds env, kill switch. PASS (see Complexity: additive surface) |
| VIII Green means green | Two new gates (single-home arithmetic; analyze wiring/decision) each with fixtures for every failure branch; analyze failure never reads as a pass. PASS |
| IX Deterministic judgment | Hold/dispatch, recurrence, thresholds and stop all in code; agent only proposes findings. PASS |
| X Bounded autonomy | `not-converging` reuses the budget-exhaustion hand-off; PR never merged by a stopped loop (SC-006). PASS |

Post-design re-check: PASS, no violations. The only Complexity item is the additive published-contract surface.

## Project Structure

### Documentation (this feature)

```text
specs/116-review-convergence-analyze/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── convergence-signals.md   # module API, thresholds, hand-off marker (consuming instrument + _shared)
│   └── fold-analyze.md          # new composite interface + hold protocol (published contract)
└── tasks.md                     # /speckit-tasks output
```

### Source Code (repository root)

```text
.github/
├── scripts/
│   ├── wc_convergence.py                       # NEW: single home — attribution, churn, growth, recurrence, thresholds, decide()
│   ├── wc_convergence_tests/                   # NEW: unit tests + #954/#969/#833 replay fixtures
│   ├── verify-convergence-single-home.py       # NEW gate (FR-019) + fixtures dir
│   ├── verify-fold-analyze-wiring.py           # NEW gate: composite sits between fold-commit and fold-dispatch in both callers; model/max-turns declared
│   └── (existing verify-fold-*.py updated for the new step)
├── actions/
│   ├── wing-commander-fold-analyze/action.yml  # NEW composite (published contract, additive)
│   ├── wing-commander-fold-commit/action.yml   # outputs: fold-section range for scoping (additive)
│   └── wing-commander-fold-dispatch/action.yml # optional input hold-released / skip when held (additive)
└── workflows/
    ├── lifecycle-review-gate.yml               # recurrence class, signals, not-converging, analyze step
    ├── board-loop.yml                          # signals + not-converging for review rounds
    └── pr-conversation.yml                     # analyze step on the `act` path
.claude/skills/review-until-clean/
├── SKILL.md                                    # call the shared module
└── scripts/thrash_signals.py                   # becomes a thin caller of wc_convergence
```

**Structure Decision**: Single repository, script-and-composite layout following existing conventions; shared arithmetic under `.github/scripts/`, shared shell (if any) under `.github/actions/_shared/` (CLAUDE.md "one home").

## Complexity Tracking

| Item | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| New published-contract composite `wing-commander-fold-analyze` plus additive optional inputs/outputs on fold composites | The single insertion point must serve both fold callers (spec 062 FR-017) | Inlining in each caller duplicates logic across two workflows (violates "one home") |
