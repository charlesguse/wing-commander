# Implementation Plan: The Stop Decision Answers Both Questions — One Home for "Stand Down" and "Cancel What"

**Branch**: `085-stop-request-cancel-contract` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/085-stop-request-cancel-contract/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

`board_stop_check.find_stop_request()` collapses two independent facts — *must
this job stand down?* and *is there an earlier run worth cancelling?* — into
one returned run id, forcing every caller to re-derive the distinction in
shell (the self-cancel guard) and forcing the composite that owns the only
call site to reimplement the module's own CLI inline instead of piping
through it. This plan replaces the single collapsed value with a two-fact
`StopDecision(stand_down, cancel_run_id)` returned by the decision function
and emitted as one line of JSON by `board_stop_check.py`'s existing `main()`
entry point; repoints `wing-commander-board-stop-check/action.yml`'s `check`
step at that CLI (removing the inline `sys.path`/import bootstrap); keeps the
composite's own "target is not this run" comparison as documented,
belt-and-braces defence in depth (FR-004); and reworks Gate 60's
`board-stop-check` check to reason structurally about each job's resolved
step list (following `check_token_mint()`) instead of three literal
fragments, one of which this change deletes. Gate 87 gains the mutation that
proves the no-self-cancel rule is load-bearing at the decision-function layer,
independent of the composite's unreadable-run and workflow-path guards. All
three defects ship as one unit (FR-013); no new gate is added.

## Technical Context

**Language/Version**: Python 3 (`.github/scripts/*.py`, stdlib only — `json`,
`re`, `sys`; the gate scripts additionally use `yaml`, already a dependency),
Bash (the composite's `check` step, run under Actions' `bash --noprofile
--norc -eo pipefail`), YAML (the composite's `action.yml`)

**Primary Dependencies**: None new. `board_item_marker.is_loop_marker_author`
(existing), PyYAML (existing, used by `verify-single-home-idioms.py` and
`verify-board-stop-check.py`), `jq` and `bash` (existing, resolved via
`wc_shell_harness.resolve_bash`)

**Storage**: N/A — no persisted state; comments are read live from the GitHub
API on every check

**Testing**: The repository's own gate scripts, run directly and via
`python .github/scripts/run-local-gates.py`: Gate 87
(`verify-board-stop-check.py` — checked-in JSON fixtures under
`.github/scripts/tests/board-stop-check/`, a mutation self-test over the
decision function, and a subprocess harness that extracts the composite's
`check` step and runs it under `bash -eo pipefail` against a stub `gh`) and
Gate 60 (`verify-single-home-idioms.py --self-test` — synthetic tempdir
fixtures)

**Target Platform**: GitHub Actions runners (`ubuntu-latest`) executing this
repository's own board loop (`.github/workflows/board-loop.yml`); the gate
scripts also run unmodified on a contributor's local Linux/macOS checkout

**Project Type**: Single repository — CI/pipeline tooling (composite actions,
Python decision/gate scripts, GitHub Actions workflows), not an application
with a src/ tree

**Performance Goals**: N/A — one decision per job re-check against a
paginated comment list already bounded by GitHub's own page size; no
measurable latency requirement beyond "does not add a second network round
trip"

**Constraints**: FR-008 fixes the composite's published surface (input names
and defaults, the `paused` output's name and meaning, the App-token/
cancel-token split, the `completed`-status check, the workflow-path and
repository target guards) — this is a Principle VII compatibility surface,
not merely a convenience. FR-013 requires the two-fact contract, the CLI
reuse, and the Gate 60 rework to land in one change. No new gate (Out of
Scope).

**Scale/Scope**: One module (`board_stop_check.py`), one composite
(`wing-commander-board-stop-check/action.yml`), two existing gates
(`verify-board-stop-check.py` / Gate 87, `verify-single-home-idioms.py` /
Gate 60) and their fixtures, one consuming workflow
(`board-loop.yml`, unchanged) with six call sites of the composite.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself worked through the pipeline from
  lifecycle issue #612 — no exception needed.
- **II. Cost-Conscious Model Tiering**: No new Claude invocation is added by
  this feature; it changes only deterministic Python/Bash/YAML. N/A.
- **III. Simple, GitHub-Native Interaction**: No user-facing interaction
  changes; the board loop's own comment thread and `paused` behaviour are
  unchanged (FR-008). Pass.
- **IV. Automation-First**: No manual step is introduced or removed. Pass.
- **V. Security**: Out of Scope explicitly excludes changing what counts as a
  stop command, who may issue one, or how the baseline is computed — this
  feature only reshapes the return value and the call convention around an
  unchanged authorization rule. Pass.
- **VI. Portability**: All touched files already live under this
  repository's own `.github/scripts/` and `.github/actions/` — no
  Wing-Commander-bundled resolution is introduced. Pass.
- **VII. Two Interfaces**: `wing-commander-board-stop-check` is a
  non-underscore-prefixed composite action, part of the published,
  adopter-pinned surface. FR-008 is this plan's explicit compatibility gate:
  the composite's inputs, defaults, and `paused` output are held fixed while
  its internal implementation changes. `board_stop_check.py` itself is not
  part of that published surface (Assumptions: it is reached only through
  this repository's own self-checkout), so its return-shape change is not a
  Principle VII breaking change. Pass, with the FR-008 constraint carried
  into every design decision below.
- **VIII. A Green Check Means What It Says**: This feature's User Story 3 and
  the "gate gap" section exist because of this principle — Gate 60's
  fragment-keyed check would go blind the moment this change deletes the
  fragment it keys on, and Gate 87's composite-shell mutation coverage does
  not yet prove the self-cancel guard is load-bearing. Both are corrected in
  this same change (FR-009–FR-011); no gate is weakened or bypassed to ship
  it (SC-006). Pass, and this principle is the primary design driver for
  Phase 1.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic Code**:
  The no-self-cancel invariant already lives in deterministic code (a Python
  function and a shell comparison), never a prompt; this feature makes that
  code's contract more precise and proves it with a mutation rather than
  moving any judgment into an agent. Pass.
- **X. Bounded Autonomy**: Not directly engaged — this PR is produced by the
  spec-driven pipeline (issue #612 was routed to `spec-request`, per
  CLAUDE.md, because the return-contract redesign needed a maintainer's
  clarification on scope, not because it is board-loop runtime behaviour
  itself). N/A to this plan's own gate.

No violations. Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/085-stop-request-cancel-contract/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── decision-function.md
│   ├── composite-invocation.md
│   ├── gate-60-structural-check.md
│   └── gate-87-coverage.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This feature touches only existing files in this repository's own CI
tooling tree — there is no `src/`/`tests/` application layout to choose
between; the "Source Code" layout below names the real, already-existing
paths this plan's Phase 1 design changes or reasons about.

```text
.github/
├── scripts/
│   ├── board_stop_check.py          # find_stop_request() returns a two-fact
│   │                                 # StopDecision; main()'s stdout contract
│   │                                 # changes; docstrings updated (FR-001,
│   │                                 # FR-003, FR-005)
│   ├── board_item_marker.py         # unchanged (is_loop_marker_author, the
│   │                                 # marker-author predicate this module
│   │                                 # already imports)
│   ├── verify-board-stop-check.py   # Gate 87 — fixtures/mutation updated to
│   │                                 # the two-fact shape; gains the
│   │                                 # self-cancel mutation-proof (FR-011)
│   ├── verify-single-home-idioms.py # Gate 60 — check_board_stop_check()
│   │                                 # reworked to a structural, per-step-list
│   │                                 # scan (FR-009); DECLARED_HOMES comment,
│   │                                 # clean-tree fixture and self-test
│   │                                 # updated (FR-010)
│   └── tests/board-stop-check/      # Gate 87's checked-in fixtures — shape
│                                     # changes from a bare `expected_run_id`
│                                     # to the two-fact decision; no fixture
│                                     # is deleted (FR-012/SC-003)
└── actions/
    └── wing-commander-board-stop-check/
        └── action.yml                # `check` step's Python block replaced
                                       # by a pipe into board_stop_check.py's
                                       # CLI (FR-006); the redundant
                                       # "target is not this run" comparison
                                       # stays, re-commented per FR-004;
                                       # inputs/outputs unchanged (FR-008)

.github/workflows/board-loop.yml      # consumer of the composite's `paused`
                                       # output across six jobs — not
                                       # modified; FR-008 compliance is
                                       # verified against it, not edited
```

**Structure Decision**: Single-repository CI tooling change confined to the
paths above. No new files are added except the plan's own documentation
artifacts under `specs/085-stop-request-cancel-contract/` — the two gates and
the one composite already exist and are corrected in place (Out of Scope:
"Adding a new gate").

## Complexity Tracking

*No entries — the Constitution Check above recorded no violations.*
