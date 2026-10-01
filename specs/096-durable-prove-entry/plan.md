# Implementation Plan: A Merged Fix Reaches Prove — The Prove Entry Survives a Displaced Queue Slot

**Branch**: `spec/096-durable-prove-entry` | **Date**: 2026-09-30 | **Spec**: [specs/096-durable-prove-entry/spec.md](./spec.md)

**Input**: Feature specification from `/specs/096-durable-prove-entry/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

`board-loop.yml`'s `prove-gate`/`prove` jobs join the same
`wing-commander-board-loop` group every other ordinary job uses, so a
`pull_request: closed` run's pending slot in that group can be — and today
regularly is — evicted by the next scheduled tick before `prove-gate` ever
starts (spec.md "The deadlock"). Spec 060 already shipped detection of this
("prove run displaced") and a directed-dispatch entry into `prove-gate`/
`prove` for a different purpose (self-redriving the prove step's own
Actions-only behaviour). This feature closes the remaining gap with two
independent mechanisms the owner's Q2 answer chose: **prevention** — the
ordinary `pull_request: closed` prove path moves to its own concurrency
group keyed by the merged PR's number
(`wing-commander-board-loop-prove-{PR#}`), so no scheduled tick and no
other merge's prove run can ever displace it again (research.md D1) — and
**bounded recovery** — a new step in `select` finds at most one already
merged-but-unproven item per run whose recorded reason is exactly the
displacement itself or `uncorrelated` (Q3), and drives it to prove through
spec 060's existing directed-dispatch entry, never a second implementation
of the actions-only decision, redrive, wait, or close (research.md D3).
Both mechanisms reuse machinery this repository already ships: the
directed-proof concurrency group, the marker mechanism (extended with two
additive fields, research.md D4), and the resume step's existing
step-resolution chain (research.md D7, fixing the one place a merged fix
was still routed to a fresh triage). Every new judgment — which item is
recoverable, which group a job joins, which outcome to record — is
deterministic Python in one new sibling module,
`board_prove_recovery.py`, following the same fixture-and-real-tree-gate
pattern spec 060's own `board_prove.py`/`board_prove_displacement.py`
already established (Principle IX, Principle VIII).

## Technical Context

**Language/Version**: Python 3.11 (`.github/scripts/board_prove.py`,
`board_prove_displacement.py`, the new `board_prove_recovery.py`,
`board_item_marker.py`), Bash (workflow `run:` steps), YAML
(`board-loop.yml`) — the same three languages specs 057 and 060 already
used; this feature adds no new one.

**Primary Dependencies**: `PyYAML` (already a `board_prove.py` dependency),
the `gh` CLI (already `board_stand_down.py`'s and the displacement step's
dependency for `gh run list`/`gh pr list`/`gh workflow run`), GitHub
Actions' own `concurrency:` and `workflow_dispatch` primitives. No new
external package.

**Storage**: N/A — GitHub Issues/PRs/Actions runs remain the only durable
state (constitution: every durable action re-derives from live state). The
two new marker fields (research.md D4) live in the same
`<!-- wing-commander-board-item: {...} -->` HTML-comment JSON payload every
other marker field already lives in; no new store.

**Testing**: This repo's own gate registry
(`.github/scripts/run-local-gates.py`, `.github/workflows/lint-workflows.yml`),
invoked identically locally and in CI (Principle VIII). The new gate
(FR-018) follows `verify-spec-branch-push-concurrency.py`'s
real-tree-plus-fixtures pattern; the new module
(`board_prove_recovery.py`) follows `verify-board-prove.py`'s/
`verify-board-prove-displacement.py`'s inline-fixture pattern (FR-020).

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), this
repository's own consuming-instrument layer (`board-loop.yml` carries no
`workflow_call` trigger, so nothing here touches the published stage
contract, Principle VII).

**Project Type**: CI-native automation (a GitHub Actions workflow plus its
supporting Python scripts) — not an application with a runtime server or a
UI.

**Performance Goals**: SC-001 — a contended merge reaches `prove-gate`/
`prove` in the same run its `pull_request: closed` event fires, not on a
later, undetermined tick. SC-008 — a permanently unobservable proof is
retried at most once, ever, per merged PR; the recovery step's own
candidate scan and dispatch add at most one `gh workflow run` call and one
marker write to `select`'s existing run time, never a synchronous wait for
the dispatched run's own conclusion (research.md D3).

**Constraints**: Principle IX (every new judgment — recoverability,
which group a job joins, the outcome label — is deterministic Python,
never an agent's judgment or a workflow's own shell conditional);
Principle VIII (the new gate is reachable through the registry, runs the
same subject locally as in CI, and fails loudly on a broken tree); FR-006
(specs 057's/060's `spec.md` files are not edited — only their live
`contracts/`); FR-002/CLAUDE.md's single-home rule (the recovery's entry
into `prove-gate`/`prove` is spec 060's existing directed dispatch, never a
parallel implementation of the actions-only decision, the redrive, the
wait, or the close); Out of Scope (no re-detection of displacement, no
change to what `board_prove.py` decides is Actions-only or which workflow
it targets, no change to the merge gate itself).

**Scale/Scope**: One workflow (`board-loop.yml`, ~4600 lines, 9 jobs) gains
one new `workflow_dispatch` input (`directed-recovery`), one new step in
`select` ("Recover a stranded prove"), a widened `concurrency.group:`
expression on `prove-gate`/`prove` (research.md D1), and small additions to
the resume step (research.md D7) and the prove job's outcome-recording/
metrics-label steps (research.md D6). One existing module
(`board_item_marker.py`) gains two keyword parameters and two CLI flags.
One new sibling module, `board_prove_recovery.py`. One existing gate
(`verify-board-prove.py` or `verify-board-prove-displacement.py`, whichever
`tasks.md` judges the cleaner single home) gains fixtures for the new
module's functions; one new gate, `verify-prove-path-concurrency.py`
(FR-018), is added. Gate 101 is unmodified — only the prose it diffs
changes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: PASS. Specified, planned, and implemented through this
  repository's own pipeline; lifecycle issue #723.
- **II. Cost-Conscious Model Tiering**: PASS (N/A). No new Claude
  invocation — every new branch is deterministic Python/Bash (FR-016). The
  plan stage itself runs on the sonnet tier per this repository's own
  tiering.
- **III. Simple, GitHub-Native Interaction**: PASS. Every new outcome
  (recovery dispatched, recovery succeeded/failed) is posted to the
  originating issue as a comment; nothing requires a dashboard (SC-003).
- **IV. Automation-First**: PASS. No new manual step. Recovery dispatches
  automatically from `select`; a human never invokes it directly except to
  reproduce a scenario locally (quickstart.md).
- **V. Security**: PASS. `directed-recovery` is a `workflow_dispatch`
  input gated the same way `directed-stage`/`directed-issue`/`directed-pr`
  already are; `prove-gate`'s directed path re-derives `MERGED`/marker
  state and ownership live from `gh pr view`/issue comments rather than
  trusting any dispatch input, exactly as today — no new untrusted-content
  surface. Issue/PR bodies remain data, never instructions (FR-017).
- **VI. Portability**: PASS. All changes stay inside this repository's own
  `board-loop.yml` wrapper and its `.github/scripts/` helpers, never a
  published `workflow_call` stage.
- **VII. Two Interfaces**: PASS. `board-loop.yml` carries no
  `workflow_call` trigger today and gains none.
  `wing-commander-dispatch-and-wait` is not modified or newly invoked by
  the recovery path (research.md D3: the recovery dispatch uses a plain
  `gh workflow run`, not the wait composite, since it does not
  synchronously wait).
- **VIII. A Green Check Means What It Says**: PASS, and directly on point —
  FR-018/FR-020/SC-005 require the new concurrency arrangement be asserted
  against the real tree, reachable through the registry, and exercised in
  both directions by fixtures — exactly the discipline spec.md's own "A
  rule with no gate behind it" section calls for.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: PASS, and the organizing constraint of this plan — recoverability
  (`is_recoverable()`), the group a job joins, and the outcome/label text
  are all pure Python or structural YAML, never left to an agent, and
  `directed-recovery` is a plain fact about how a run started, not an
  inference from mutable state (research.md D6).
- **X. Bounded Autonomy — The Pipeline Works Its Own Board**: PASS. This
  feature *is* Principle X's own "prove" step, strengthened: "a fix to
  behaviour that only runs in Actions is proven after merge by re-driving
  one run" now holds even when a scheduled tick contends for the loop's
  group, without widening any merge class or changing who merges.

No violations; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/096-durable-prove-entry/
├── plan.md                                # This file
├── research.md                            # Phase 0: D1-D9 design decisions
├── data-model.md                          # Phase 1: entities (marker fields, recoverable item, recovery dispatch, etc.)
├── quickstart.md                          # Phase 1: validation scenarios per user story
├── contracts/
│   ├── prove-path-concurrency.md          # NEW — FR-004/FR-005/FR-018 target text and gate
│   └── recovery-and-resume.md             # NEW — FR-002/FR-007/FR-008/FR-010/FR-011* mechanism
└── spec-meta.json
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   └── board-loop.yml                     # EDIT — one new workflow_dispatch input (directed-recovery,
│                                           #   research.md D6); prove-gate/prove's concurrency.group:
│                                           #   gains a per-PR-keyed middle branch (FR-004, research.md D1);
│                                           #   8 per-job concurrency comments restate the amended
│                                           #   guarantee sentence (FR-005, research.md D2); new "Recover
│                                           #   a stranded prove" step in select, after the existing
│                                           #   displacement step (FR-011, research.md D3); resume step's
│                                           #   stale-marker clause splits on pr_state (FR-007,
│                                           #   research.md D7); prove job's outcome-recording and
│                                           #   metrics-label steps read directed-recovery (FR-014/015,
│                                           #   research.md D6)
├── scripts/
│   ├── board_prove.py                     # EDIT — read_job_concurrency_group() extracted from
│                                           #   joins_directed_group() (research.md D8), reused by the
│                                           #   new gate
│   ├── board_prove_displacement.py        # EDIT (imported, not modified in behaviour) — RECORDED_REASON
│                                           #   consumed by board_prove_recovery.py rather than re-typed
│   ├── board_prove_recovery.py            # NEW — is_recoverable(), find_recoverable_items(),
│                                           #   RECOVERY_DIRECTED_INPUT (research.md D5)
│   ├── board_item_marker.py               # EDIT — write_marker() gains outcome_reason/
│                                           #   recovery_attempted keyword params (backward-compatible
│                                           #   defaults); CLI gains --outcome-reason/--recovery-attempted
│                                           #   (research.md D4)
│   ├── verify-board-prove.py (or          # EDIT — fixtures for read_job_concurrency_group() and any
│   │   verify-board-prove-displacement.py,#   board_prove.py additions (FR-020); tasks.md decides the
│   │   tasks.md decides)                  #   single home
│   ├── verify-board-prove-recovery.py     # NEW (or folded into the above — tasks.md decides) —
│                                           #   is_recoverable()/find_recoverable_items() fixtures, both
│                                           #   directions (FR-020)
│   └── verify-prove-path-concurrency.py   # NEW — FR-018's real-tree-plus-fixtures gate (research.md D8)
└── actions/
    └── wing-commander-dispatch-and-wait/  # UNCHANGED — the recovery dispatch does not use it
                                            #   (research.md D3); no correlation/wait mechanism needed

specs/057-autonomous-board-loop/contracts/
├── prove-step.md                          # EDITED DURING IMPLEMENTATION (FR-021, research.md D9) —
│                                           #   folds in the recovery entry and the resume-step fix
└── board-item-marker.md                   # EDITED DURING IMPLEMENTATION — documents the two new
                                            #   marker fields

specs/060-self-redrive-concurrency/contracts/
├── concurrency-groups.md                  # EDITED DURING IMPLEMENTATION (FR-005/FR-021, research.md D9)
│                                           #   — amended guarantee sentence, prove-gate/prove group row,
│                                           #   removed "what does not change" bullet
├── directed-proof-run.md                  # EDITED DURING IMPLEMENTATION — notes the recovery dispatch
│                                           #   as a stage=="prove" directed run carrying directed-recovery
└── proof-outcome-taxonomy.md              # EDITED DURING IMPLEMENTATION — "Recording rule" section
                                            #   documents the new outcome_reason marker field (no new
                                            #   taxonomy value)
```

**Structure Decision**: This feature touches exactly one workflow
(`board-loop.yml`), two existing script modules it already owns
(`board_prove.py`, `board_item_marker.py`), one new sibling module scoped
to a single new concern (`board_prove_recovery.py`, matching the existing
one-`board_*.py`-module-per-concern convention alongside
`board_eligibility.py`/`board_stand_down.py`/`board_prove_displacement.py`),
and the gate(s) that check them. No new top-level directory or package;
`.github/scripts/tests/` already holds fixture directories available if
`tasks.md` chooses external fixtures over inline ones for any new gate.

## Complexity Tracking

*No violations — table intentionally empty.*
