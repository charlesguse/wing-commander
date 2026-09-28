# Implementation Plan: A Run That Spent Money Says So — Intake's Silent Outcome Paths Report Their Cost

**Branch**: `065-intake-silent-path-cost` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/065-intake-silent-path-cost/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Every cost-bearing stage (intake, clarify, plan, tasks) already computes a
per-run cost line from `wing-commander-metrics-summary`'s `cost-line` output,
but today that line only reaches the lifecycle issue as a passenger on an
outcome-announcing callout. Four intake paths announce no outcome and so
report no cost; clarify and plan/tasks each carry a bespoke, independently
authored cost-report step (#366, #377) that repeats the same shape.

The technical approach: add one new composite action,
`wing-commander-cost-report`, as the single home for *posting* a stage's
cost line to the lifecycle issue, independent of whatever outcome that
stage decided (or decided not) to announce. Each of the four stage
workflows calls it exactly once per run, gated only on "the agent step
ran" and "the run was not cancelled" — never on which outcome branch was
taken — so it fires on every live path a stage can take, including the two
veto paths that fail the run. Every outcome callout in every stage sheds
its embedded cost line (FR-002a), because the callout is no longer the
line's only ride. The clarify early-STOP report (#366) and the plan/tasks
auto-mode hand-off reports (#377) are retired in favor of calling the new
composite, folding three bespoke copies and this request into one
mechanism (US3). Two existing gates are extended rather than a new one
invented from scratch: `verify-clarification-gating.py`'s scenario harness
(already executing intake's real run-blocks against synthetic agent
outputs) gains an assertion that the new report fires exactly once per
scenario, and `verify-metrics-summary-record-emission.py`'s single-home
scan gains a sibling check that the retired bespoke patterns, and any
inline duplicate of the new composite's posting logic, cannot reappear in
a workflow.

## Technical Context

**Language/Version**: GitHub Actions workflow YAML; Bash + `jq` inside
composite `run:` steps; Python 3 for the PR-time gate scripts under
`.github/scripts/`.

**Primary Dependencies**: `gh` CLI (issue commenting), existing composites
`wing-commander-metrics-summary` (cost-line formatter, unchanged) and
`wing-commander-callout` (the single existing comment-posting primitive,
reused as the new composite's own posting mechanism).

**Storage**: N/A — the lifecycle issue's comment thread is the durable
record, as it already is for every existing callout.

**Testing**: The PR-time gate suite (`python .github/scripts/run-local-gates.py`),
specifically the extended `verify-clarification-gating.py` and
`verify-metrics-summary-record-emission.py`, plus `verify-plan-tasks-cost-line.py`
(Gate 63), which must move from checking the retired plan/tasks bespoke
steps to checking their replacement call sites. Each new failure branch
ships with a checked-in fixture per Constitution VIII.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), this
repository's own pipeline.

**Project Type**: CI/CD pipeline infrastructure (reusable workflows +
composite actions + Python gate scripts) — not application code.

**Performance Goals**: N/A (no runtime performance surface; the change
adds at most one more `gh issue comment` call per stage run).

**Constraints**:
- FR-004: no second place may format or round a cost figure — the new
  composite only ever forwards the value it is given.
- FR-008: no outcome callout's announced-outcome decision or wording may
  change beyond the cost line's removal.
- FR-012a: the new report step must not be strandable by a failing step
  above it (the readiness veto, the contradiction veto) — its own `if:`
  must survive both, which is exactly what `review-step-gating` (per
  CLAUDE.md) will be asked to check before this ships.
- FR-013: a run that never invoked its agent, and a cancelled run, must
  post no report.

**Scale/Scope**: One new composite action; four stage workflows each gain
one new step and lose the cost line from their existing callout bodies;
three bespoke report steps retired; two gate scripts extended, one gate
script (`verify-plan-tasks-cost-line.py`) re-pointed at the new call sites.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide** — PASS. The fix ships through the pipeline's own stages
  (intake authored this spec, plan authors this document) on this
  repository's own workflows.
- **II. Cost-Conscious Model Tiering** — N/A. No new Claude invocation is
  introduced; this is workflow/gate plumbing around an existing agent
  step's already-computed cost.
- **III. Simple, GitHub-Native Interaction** — PASS, and directly served:
  the fix's entire purpose is making the lifecycle issue tell the whole
  story of a run, spend included, without requiring anyone to open the
  run.
- **IV. Automation-First** — PASS. Reporting cost is itself automation
  that was previously silently skipped on four paths; this closes that
  gap without adding a manual step.
- **V. Security** — PASS, unaffected. No change to authorization,
  tool allowlists, or merge actors. The new composite posts with the same
  GitHub App identity every existing callout already uses.
- **VI. Portability** — PASS. Nothing repo-specific is hardcoded; the new
  composite takes issue number and token as inputs like its siblings.
- **VII. Two Interfaces** — NOTE, not a violation. The new composite,
  `.github/actions/wing-commander-cost-report`, is called directly by
  four published `workflow_call` stage workflows, so it joins the
  published contract rather than living under `_shared/`. This is a
  deliberate, additive widening of the surface (a new composite alongside
  `wing-commander-callout`), not a breaking change — no existing input,
  secret, or output is removed or renamed. Record this explicitly in the
  PR description per VII's "deliberate act rather than a convenience."
- **VIII. A Green Check Means What It Says** — directly governs FR-010/
  FR-010a: the extended gates must stay reachable through the gate
  registry, run the same subject locally and in CI (they already do, via
  `run-local-gates.py`), fail loudly if their subject is unreachable, and
  ship a checked-in fixture for every new failure branch (report absent,
  ungated, mis-gated, empty body; a pasted duplicate). Planned as part of
  Phase 1 below.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code** — PASS. Whether a report posts is a deterministic `if:` over
  `steps.agent.outcome` and the job's cancellation state, never a model
  judgment call.
- **X. Bounded Autonomy** — N/A. This is a spec-lifecycle change, not a
  board-loop fix-shaped change.

No violations requiring Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/065-intake-silent-path-cost/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── cost-report-action.md
│   └── gate-extensions.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── actions/
│   ├── wing-commander-cost-report/   # NEW — single home for posting the
│   │                                  # uniform per-stage cost report
│   ├── wing-commander-metrics-summary/  # unchanged: cost-line formatter stays here
│   └── wing-commander-callout/       # unchanged: reused internally by the new action
├── workflows/
│   ├── intake.yml     # gains one report step; both outcome callouts drop the cost line
│   ├── clarify.yml     # early-STOP bespoke report (#366) retired -> calls new action;
│   │                    # its other outcome callout(s) drop the cost line
│   ├── plan.yml        # auto-mode bespoke report (#377) retired -> calls new action
│   └── tasks.yml       # auto-mode bespoke report (#377) retired -> calls new action
└── scripts/
    ├── verify-clarification-gating.py       # extended: assert the report fires
    │                                          # exactly once per intake scenario
    ├── verify-metrics-summary-record-emission.py  # extended: single-home scan also
    │                                          # rejects a pasted report duplicate
    └── verify-plan-tasks-cost-line.py        # re-pointed: checks the new call sites
                                               # in plan.yml/tasks.yml instead of the
                                               # retired bespoke steps
```

**Structure Decision**: This is infrastructure work inside the existing
`.github/{workflows,actions,scripts}` layout — no `src/`/`tests/` split
applies. One new composite action is added; four existing stage workflows
and up to three existing gate scripts are modified in place. No new
top-level directories.

## Complexity Tracking

*No Constitution Check violations — this section is not needed.*
