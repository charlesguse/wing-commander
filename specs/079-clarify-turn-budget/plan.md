# Implementation Plan: Clarify's Turn Budget Reflects the Work Clarify Actually Does

**Branch**: `spec/079-clarify-turn-budget` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/079-clarify-turn-budget/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

The watchdog's `turn-budget-trend` collector correctly reported that
clarify's declared turn budget (`40`) no longer describes clarify's real
work: three recorded runs finished at 39, 45 and 61 counted turns, and
61/100 (the ceiling `wing-commander-turn-ceiling` derives at ×2.5) is a
`0.61` consumed-ceiling-fraction, at/over the `0.6` climb threshold that
produces the `elevated` band. This plan re-bases the single value that
carries clarify's budget — `clarify.yml`'s `workflow_call.inputs.max-turns.default`
— from `40` to `65` (research.md R1), derived from the observed range
(39-61) with working margin, so the heaviest recorded run is not flagged
over budget while a genuinely runaway run still is. Because the
fleet-wide ×2.5 multiplier stays fixed, the change states its own
consequence: the runaway ceiling rises from `100` to `163`, recorded in
the same commit (FR-003). Everywhere else — every other stage's budget,
ceiling, over-budget determination and reported metrics, the watchdog's
band arithmetic, signal identity, and suppression mechanism (spec 046) —
is left exactly as it is (FR-002/FR-009/FR-015), and no repository
variable or new workflow input is added (FR-008, Q2). Two durable
artifacts complete the response: a written, evidence-based procedure in
`docs/architecture.md` for the next `turn-budget-trend` on any stage
(FR-013, demonstrated against clarify's own numbers per FR-014), and a
new deterministic gate, `verify-stage-turn-budget-docs.py`, that fails
loudly if a stage's declared budget and its `docs/adoption.md` row ever
disagree again (FR-017/FR-018).

## Technical Context

**Language/Version**: YAML (the `workflow_call` input default in
`clarify.yml`), Markdown (`docs/adoption.md`, `docs/architecture.md`),
Python 3 (the new gate script, following the existing
docs-vs-source-consistency gate shape — `verify-versioning-refs.py` is
the closest prior art: WHY/WHAT-IT-CHECKS/WHAT-IT-DOES-NOT-CHECK
docstring, `--self-test` over checked-in fixtures). No new language, no
new toolchain — identical to every other gate in this repository.

**Primary Dependencies**: None new. The feature reads and edits
mechanism spec 037 (`wing-commander-turn-ceiling`'s ×2.5 formula) and
spec 046 (the watchdog's `collect-turn-budget` band arithmetic) already
ship; both are read-only dependencies here (research.md R2/R3) — neither
is modified.

**Storage**: N/A. The recorded run history this plan's R1 decision reads
lives in the existing `metrics` orphan branch (spec 043), untouched by
this feature; the re-based budget itself lives in `clarify.yml`, not a
data store.

**Testing**: This repository's existing gate-registry convention
(`.github/scripts/verify-*.py`/`.sh`, wired into `lint-workflows.yml`,
runnable via `python .github/scripts/run-local-gates.py`). One new gate
is added with a checked-in fixture per failure branch
(contracts/gate-coverage-079.md); zero existing gates are amended —
Gates 22/23 already cover clarify's ceiling/verdict wiring generically
and need no clarify-specific fixture change (research.md R3).

**Target Platform**: GitHub Actions runners, any repository adopting the
published `clarify.yml` stage (constitution VI/VII) — the change is
purely a default-value move on an already-published, typed input; no
platform or runner change.

**Project Type**: GitHub Actions reusable-workflow pipeline (no
`src`/`tests` split) — this feature edits one workflow's declared
default, one docs table row, adds one docs subsection, and adds one gate
script plus its fixtures and registration line.

**Performance Goals**: N/A in the usual sense; the operative "outcome" is
observability quieting down, stated as SC-001/SC-002 (replaying {39, 45,
61} against the new configuration produces zero trend signals and zero
over-budget notes) and SC-003 (the new worst-case turn count, `163`, is a
single stated number, not an emergent side effect).

**Constraints**: FR-002/FR-009/SC-005 — every stage other than clarify
must show byte-identical declared budget, ceiling, over-budget
determination, reported metrics and spend before and after. FR-008/SC-004
— zero new inputs, repository variables, or knobs. FR-003 — the ×2.5
multiplier is fixed; only clarify's `max-turns` moves. FR-011 — the
existing invalid-budget guard (empty/zero/negative/non-numeric -> loud
failure) must not weaken, and is not touched (research.md R3). FR-015 —
the watchdog's band computation, signal identity, fingerprinting, and
dedup/suppression mechanism (spec 046) is out of scope and untouched.

**Scale/Scope**: One `workflow_call` input default (`clarify.yml`), one
inline comment recording the reasoning beside it, one `docs/adoption.md`
table cell, one new `docs/architecture.md` subsection (the written
procedure, FR-013/FR-014), one new gate script plus its fixtures and its
`lint-workflows.yml` registration line (number assigned at
implementation time, following spec 058's identical precedent). No
workflow gains or loses a job; no other of the eight remaining
budget-carrying stages (intake, plan, tasks, implement, finalize,
cleanup, rebase, pr-conversation) is touched.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | This feature responds to a real watchdog finding against this repository's own clarify stage, worked through intake -> plan (this stage) -> tasks -> implement, the same pipeline it tunes. | Pass |
| II. Cost-Conscious Model Tiering | This plan runs at the planning tier (`claude-sonnet-5`). The feature changes a turn count, never a model tier (FR-016) — no tiering decision is implicated. Every clarify invocation keeps its explicit model and now-larger-but-still-bounded ceiling (FR-004). | Pass |
| III. Simple, GitHub-Native Interaction | The re-based budget, its reasoning, and the written procedure are all visible from the workflow file, the docs, and (per the completion comment) the lifecycle issue — no dashboard or external surface introduced. | Pass |
| IV. Automation-First | No new manual step. The pipeline continues to post over-budget/warning lines automatically; the one manual action this feature's Assumptions section names (closing the currently-open `pipeline-defect` as accepted once this change lands) is a pre-existing board-loop/triage action, not a new one this feature adds. | Pass |
| V. Security — untrusted content is never instructions | No issue/comment body is read as an instruction anywhere in this change; the re-based value is a workflow default, and the new gate reads only workflow YAML and docs Markdown, both trusted repository content. | Pass |
| VI. Portability — consuming repo owns its artifacts | The changed default lives in the published stage workflow itself; an adopter who already pins their own `max-turns` keeps it (FR-010) — nothing here reads or assumes adopter-specific state. | Pass |
| VII. Two Interfaces | `max-turns` is already a declared, typed `workflow_call` input; only its literal default moves — the published contract's shape (name, type, required-ness) is unchanged, so this is not a widening (FR-008/SC-004). `docs/adoption.md`/`docs/architecture.md` are this repository's own consuming-instrument documentation, updated in the same change per FR-017. | Pass |
| VIII. A Green Check Means What It Says | The new gate is reachable through the gate registry, runs the same subject (workflow default + docs cell) locally and in CI, is triggered by changes to either file, fails loudly when it cannot find a stage's subject rather than skipping it, and ships one checked-in fixture per failure branch (contracts/gate-coverage-079.md) — no manual-only demonstration. | Pass |
| IX. Judgment That Gates a Durable Action Belongs in Deterministic Code | The docs-vs-workflow-default comparison the new gate performs is pure string/YAML comparison — no model judges whether they "look" consistent. The re-based number itself (R1) is a plan-time human/agent decision recorded in research.md and the issue comment, not a durable gate outcome a model computes at run time. | Pass |
| X. Bounded Autonomy — The Pipeline Works Its Own Board | Not implicated — this issue was already routed `spec-request` and is worked through the ordinary feature lifecycle (intake already ran; this is the plan stage), not the board loop. | N/A |

No violations. Complexity Tracking below is empty.

## Project Structure

### Documentation (this feature)

```text
specs/079-clarify-turn-budget/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   ├── clarify-turn-budget-delta.md
│   └── gate-coverage-079.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This repository has no `src`/`tests` split — it is a GitHub Actions
pipeline. This feature's concrete changes:

```text
.github/
├── workflows/
│   ├── clarify.yml            # max-turns default 40 -> 65; inline comment
│   │                          # records accepted range (39-61), source
│   │                          # (issue #587), and resulting ceiling (163)
│   │                          # (contracts/clarify-turn-budget-delta.md)
│   └── lint-workflows.yml     # registers the new gate (number assigned
│                              # at implementation time)
└── scripts/
    ├── verify-stage-turn-budget-docs.py   # new (contracts/gate-coverage-079.md)
    └── fixtures/
        └── stage-turn-budget-docs/
            ├── all-agree/
            ├── workflow-drifted/
            ├── docs-drifted/
            ├── docs-missing-cell/
            └── no-subjects/

docs/
├── adoption.md      # ### clarify row: max-turns 40 -> 65
└── architecture.md  # new subsection: the written turn-budget-trend
                      # response procedure (FR-013/FR-014), placed
                      # immediately after the existing turn/ceiling
                      # explanation (data-model.md's "Written procedure"
                      # table)

specs/079-clarify-turn-budget/
├── plan.md, research.md, data-model.md, quickstart.md   # this plan
├── contracts/
│   ├── clarify-turn-budget-delta.md
│   └── gate-coverage-079.md
└── tasks.md                            # /speckit-tasks output — not produced here
```

**Structure Decision**: One change, landed as a single unit rather than
sub-problems (unlike spec 058's A/B/C split) — every piece here (the
value move, its recorded reasoning, the docs update, the written
procedure, and the new gate) is small, touches non-overlapping files, and
has no independent value on its own: a re-based budget with no gate
behind FR-017 would drift again exactly as CLAUDE.md's own cost-line
example warns, and a written procedure with no worked re-basing to point
at would be asserted rather than demonstrated (FR-014). No new stage
workflow, no new composite action, and no amendment to any existing gate
is introduced — every change is either a literal-value move on an
existing published input, a docs update, or one wholly new, narrowly
scoped gate.

## Complexity Tracking

*No Constitution Check violations — this section intentionally left empty.*
