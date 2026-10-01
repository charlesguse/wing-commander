# Implementation Plan: A Stall Holds Until a Maintainer Re-Admits It — and a Stop Halts Readiness's Filing

**Branch**: `100-stalled-item-re-admission` | **Date**: 2026-09-30 | **Spec**: `specs/100-stalled-item-re-admission/spec.md`

**Input**: Feature specification from `specs/100-stalled-item-re-admission/spec.md` (lifecycle issue #752)

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Two of the three defects this spec describes (label-before-marker at every
stall site, readiness's per-write stand-down gating) already landed on
`main` via #782, before this plan ran; they are preserved invariants, not
new work (research.md D1). What remains live is FR-006 through FR-011: the
loop must state, as one gated rule rather than an emergent side effect of
clause ordering, what a re-admitted stalled item resumes at — the resume
step's existing `board:owned` fallback (`board-loop.yml`'s `select` job,
clause 2), refined per spec 093's owner-chosen invariant so an open PR whose
head no review has covered yet resumes at `review`, but one whose head is
unchanged since the last *converged* review resumes at `readiness` instead
of a second, wasted review round. That refinement rests on one shared "has
the head moved since the last review" determination (FR-006b) that this
feature builds from live state — the PR's live head SHA compared against
the head SHA the loop's own most recent *converged* review-round comment
recorded for that PR; a budget-spent or any other inconclusive verdict
never establishes a reviewed head and always resolves to `review` with a
fresh round budget, regardless of head movement (maintainer review of
#885) — with no new marker field and no change to how review posts its
findings. The technical approach is
a three-way split of one existing `elif` clause, one new small live-state
lookup function, one new fixture-driven gate, and run-summary lines at the
resume step and at stall-site retries recording what fired and why. FR-016-
018 (readiness's own duplicate-spec-request lookup) are explicitly deferred
to #701/spec 092 and are not built here.

## Technical Context

**Language/Version**: Python 3.11 (matches every existing `.github/scripts/*.py` and the `run:` heredoc in `board-loop.yml`'s `select` job), embedded in GitHub Actions YAML (`.github/workflows/board-loop.yml`).

**Primary Dependencies**: `gh` CLI (PR/issue reads — no new API surface beyond what `resume-recovery.md` and readiness's snapshot already use), `board_eligibility.py`, `board_item_marker.py` (both already imported by the resume step's heredoc).

**Storage**: None. No new marker field, no new comment convention, no database. The reviewed-head determination reads existing GitHub state (PR commits, existing bot comments) live each run.

**Testing**: The repository's existing `verify-*.py` gate-script pattern (fixture directories under `.github/scripts/tests/`, run via `python .github/scripts/run-local-gates.py`, registered as a numbered `Gate N` step in `lint-workflows.yml`). No new testing framework.

**Target Platform**: GitHub Actions (ubuntu runners), same as the rest of `board-loop.yml`.

**Project Type**: Single project — this is a consuming-instrument automation change (Constitution VII), not a library/service/mobile app. No frontend/backend split applies.

**Performance Goals**: N/A (a scheduled/dispatched Actions job; no latency budget beyond board-loop's existing per-run turn/cost ceilings, which this feature does not change).

**Constraints**: FR-021 — no published `workflow_call` interface or composite-action interface may change (Constitution VII). FR-019 — no marker schema extension. FR-016-018 — no new or duplicated `spec-request` duplicate-check. FR-010 — no additional agent invocation on a retry.

**Scale/Scope**: One workflow file (`board-loop.yml`), one clause inside its `select` job's resume step, one new small Python function (the reviewed-head determination — module TBD at task-breakdown time, most naturally alongside `board_item_marker.py` or as its own small module since it is consumed by a future feature (spec 093) as well as this one), one new gate script plus its fixture directory, and small additions to two live contracts (`resume-recovery.md`'s clause 2, `labels-and-cross-links.md`'s `board:stalled` row).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design below.*

- **I. Guide**: This feature is itself built through the pipeline (spec → plan → tasks → implement), from lifecycle issue #752. Pass.
- **II. Cost-Conscious Model Tiering**: No new automated Claude invocation is introduced — this feature changes deterministic gating code and a gate script, not an agent step or its model choice. N/A, no violation.
- **III. Simple, GitHub-Native Interaction**: All new run-summary lines (FR-011) post to the run summary and, where a stall/re-admission already comments on the issue, to that issue — no new external surface. Pass.
- **IV. Automation-First**: Re-admission continues to require zero requester action beyond removing a label (unchanged); the loop states and records the rule automatically. Pass.
- **V. Security**: No new comment-triggered or issue-body-driven logic. The reviewed-head determination reads GitHub-authored metadata (timestamps, the loop's own past comments) as data, never as instructions. Pass.
- **VI. Portability**: All changes stay inside this repository's own `.github/workflows/board-loop.yml` and `.github/scripts/`, both already repository-owned. Pass.
- **VII. Two Interfaces**: FR-021 explicitly holds the published surface fixed; verified in research.md D2/D8 that no stage workflow or composite action interface is touched. Pass.
- **VIII. A Green Check Means What It Says**: The new gate (research.md D8) is fixture-driven, must be reachable through the gate registry (`run-local-gates.py` / `lint-workflows.yml`), and FR-006's own failure mode (reverting clause 2 to unconditional `review`) is a required checked-in fixture (mirrors FR-005's existing style for the stall-site check). Pass, by design — verified again after Phase 1.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic Code**: The reviewed-head determination and the three-way clause-2 split are both deterministic Python, not a prompt; no agent judgment gates the `review`/`readiness`/`breach` choice. Pass.
- **X. Bounded Autonomy**: This is a fix-shaped change to the board loop's own gating code (a corrected/extended `verify-*` gate plus a plumbing fix to an existing clause) with an owner-decided trade-off already resolved via the spec's Q1/Q2/Q3 clarifications — appropriately routed through the full spec→plan→tasks pipeline rather than as a bare fix PR, consistent with "spans several stages / benefited from the clarify stage's questions." Pass.

No violations requiring Complexity Tracking. This section is re-affirmed unchanged after Phase 1 design below — Phase 1 introduced no new dependency, storage, or interface that would change any answer above.

## Project Structure

### Documentation (this feature)

```text
specs/100-stalled-item-re-admission/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   ├── resume-recovery-readmission.md
│   ├── reviewed-head-determination.md
│   └── stall-and-readmission-invariants.md
└── tasks.md               # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This is a single-project GitHub Actions automation repository — no
frontend/backend or mobile split applies. The concrete files this feature
touches:

```text
.github/
├── workflows/
│   └── board-loop.yml                       # select job's resume step, clause 2 (FR-006); run-summary lines (FR-011)
├── scripts/
│   ├── board_item_marker.py                  # unchanged (no schema extension, FR-019); may host the new reviewed-head function
│   ├── board_eligibility.py                  # unchanged (PRE_FIX_STEPS/FIX_OR_LATER_STEPS/TERMINAL_STEPS/select/in_flight_candidate all preserved)
│   ├── verify-board-loop-resume-gating.py    # unchanged (Gate 97 — resume reachability, a distinct concern from clause correctness)
│   ├── verify-board-loop-readmission.py      # NEW (research.md D8) — the re-admission clause's own gate
│   └── tests/
│       └── board-loop-readmission/           # NEW — fixture cases for the new gate
└── workflows/lint-workflows.yml              # registers the new gate as a "Gate N -- ..." step (FR-003)

specs/
├── 061-marker-owned-in-flight/contracts/resume-recovery.md      # amended: clause 2 (live contract, FR-019)
└── 057-autonomous-board-loop/contracts/labels-and-cross-links.md # amended: board:stalled row's "Cleared by" cell (live contract, FR-019/FR-020)
```

**Structure Decision**: Single project, automation-only. No `src/`/`tests/`
top-level split exists or is introduced — this repository's convention for
workflow automation is `.github/workflows/` + `.github/scripts/` (+
`.github/scripts/tests/` fixtures), which every prior board-loop spec
(057, 061) already used and which this feature follows without deviation.

## Complexity Tracking

*No entries — Constitution Check reported no violations requiring justification.*
