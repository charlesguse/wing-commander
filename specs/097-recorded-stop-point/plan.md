# Implementation Plan: An Honoured Stop Records Its Stop Point — One Stop Halts One Item, Not the Board

**Branch**: `spec/097-recorded-stop-point` | **Date**: 2026-09-30 | **Spec**: [specs/097-recorded-stop-point/spec.md](./spec.md)

**Input**: Feature specification from `/specs/097-recorded-stop-point/spec.md`, lifecycle issue #724

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

When `wing-commander-board-stop-check` honours a maintainer's stop request,
it currently returns a single `paused=true` boolean and writes nothing
durable — the item is re-selected and re-stood-down on every later run,
wedging the whole board behind it (one item in flight repository-wide).
This plan gives the composite one additive change — a new `stop-cause`
output distinguishing a stop request from the kill switch from a closed
issue — and has it, and only it, write the stop's durable consequence: the
existing `stalled` marker shape plus the `board:stalled` label plus a
human-legible comment naming the cause, the specific stop comment, and the
release condition. Reusing existing primitives throughout
(`add_stalled_label()`, `write_marker()`, `fenced_section()`,
`is_excluded()`) means no new selection mechanism, no new label, and no
change to the frozen `find_stop_request()` decision function — only its
consequence is new. A new PR-time gate proves the regression this fixes
cannot silently return, and a small metrics/cost-line addition lets an
auditor distinguish the three stand-down causes from durable records alone.

## Technical Context

**Language/Version**: Python 3.11 (`.github/scripts/*.py`), Bash (GitHub
Actions `run:` steps), YAML (workflow/composite-action definitions) — no
new language or runtime.

**Primary Dependencies**: GitHub CLI (`gh`), `jq`; existing repository
modules `board_stop_check.py`, `board_item_marker.py`, `board_eligibility.py`,
`board_spec_request_body.py` (for `fenced_section()`); existing composites
`wing-commander-board-stop-check`, `wing-commander-metrics-summary`,
`wing-commander-lifecycle-gate`. No new third-party dependency.

**Storage**: N/A — durable state is entirely the target issue's own labels
and comments on GitHub (the "board item marker" convention); no database,
no new file format.

**Testing**: `.github/scripts/run-local-gates.py` (the full PR-time gate
suite, per CLAUDE.md's "Before pushing" section); the new Gate 128
(`verify-stop-point-recording.py`, contracts/gate-128-stop-point-
recording.md) plus its `--self-test`; Gate 87's existing mutation-tested
fixture corpus for `find_stop_request()`, extended with new fixtures for
FR-016/FR-009; `board_eligibility.py`'s existing fixture-driven tests,
reused (not modified) to prove SC-001.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), this
repository's own `board-loop.yml` workflow (Principle X's board loop).

**Project Type**: CI/automation pipeline component — a GitHub composite
action plus a calling workflow plus Python helper scripts. Not a
library/CLI/web-service in the template's usual sense; "Project Structure"
below is adapted accordingly.

**Performance Goals**: N/A in the throughput sense. The relevant bound is
FR-017/Assumptions' "round budgets and turn ceilings are unaffected": a run
that stands down and records a stop spends no additional agent turns beyond
those already spent before the stop check, and the new work is at most one
additional `gh issue view` (labels), one comment post, and one metrics
accounting call per stood-down job — all deterministic, non-agent steps.

**Constraints**:
- Must not alter `find_stop_request()`'s existing two-fact `StopDecision`
  contract or the cancel-run path (spec 097 Dependencies; research.md D1).
- Must not write anything durable for a kill-switch-only or closed-issue-
  only stand-down (FR-011/FR-013).
- At most one stop-point record per run (FR-007), even under a future job
  graph where more than one job could reach the same item's stop check in
  one run (research.md D6).
- The composite's `run:` body must resolve `board_stop_check.py` and the
  new label/marker write from the trusted pristine snapshot, not the
  workspace (FR-018; spec 095 FR-011/FR-012, not yet merged but
  independently required here).
- `wing-commander-board-stop-check` is part of the published, adopter-
  pinned contract (Principle VII); any change to it must be additive/
  backward-compatible, recorded as a deliberate widening.

**Scale/Scope**: One composite action (`wing-commander-board-stop-check`),
one Python module extended additively (`board_stop_check.py`, two new pure
functions), six call sites in one workflow (`board-loop.yml`: triage,
route, fix, review, readiness, prove), one new PR-time gate plus its
fixtures, one small metrics/cost-line addition (six new `always()`
accounting steps reusing an existing composite). No new workflow file, no
new composite action, no new script file beyond the one gate script.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself worked through the pipeline (spec
  #097, lifecycle issue #724) — compliant, no exception needed.
- **II. Cost-Conscious Model Tiering**: No new Claude/agent invocation is
  added. The new metrics-accounting steps (research.md D11) deliberately
  use the existing no-agent-cost shape (`model: ''`, placeholder
  transcript) `select` already established, spending nothing new. Compliant.
- **III. Simple, GitHub-Native Interaction**: The stop-point record is an
  issue comment plus a label, read and released by ordinary GitHub actions
  (comment to stop, remove a label to resume) — no new interaction surface.
  Compliant.
- **IV. Automation-First**: No new manual step is introduced; the fix
  automates a currently-missing durable consequence. Compliant.
- **V. Security**: The maintainer's stop-command authorization check
  (`MAINTAINER_ASSOCIATIONS`) is unchanged (FR-020). The stop request's own
  reason text is untrusted content; contracts/stop-point-record.md requires
  it be rendered only through the existing `fenced_section()` inert-quoting
  helper — never as instructions, mentions, or live links (FR-005).
  Compliant.
- **VI. Portability**: All changes are within this repository's own
  `.github/actions/`, `.github/scripts/`, and `.github/workflows/board-
  loop.yml` — the board loop is this repository's own operational
  mechanism (Principle X), not bundled generic pipeline code. Compliant.
- **VII. Two Interfaces**: `wing-commander-board-stop-check` is part of the
  published composite-action surface. This plan **widens** it (two new
  optional inputs, one new output) — a deliberate act, justified in
  research.md D3/D4, additive and backward-compatible (no rename, no
  removal, no changed default/meaning of any existing input or output).
  Flagged here explicitly per Principle VII's own requirement that widening
  be deliberate rather than incidental.
- **VIII. A Green Check Means What It Says**: The new Gate 128 is
  registered through the standard `lint-workflows.yml` wiring, runs
  identically locally via `run-local-gates.py`, is triggered by changes to
  the files it checks, and ships a `--self-test` proving it can fail its
  own subject on the exact pre-fix shape (SC-009). Compliant by design;
  verified at gate-authoring time in the tasks/implement stage.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: Every new decision (`stop-cause`'s priority order, which comment
  won, whether to write the record, the idempotency short-circuit) is
  deterministic Python/bash — no agent judgment is introduced anywhere on
  this path. Compliant.
- **X. Bounded Autonomy**: This is a fix-shaped change per CLAUDE.md's
  routing rule (deterministic, gate-shaped, carries the size-and-path
  backstop, no design trade-off left open — every open question in spec.md
  was already resolved by the owner or a merged sibling spec). Consistent
  with the lifecycle issue already being worked as a direct fix rather than
  a new `spec-request`.

No violations requiring the Complexity Tracking table below to be filled;
it is left empty per the template's own instruction.

## Project Structure

### Documentation (this feature)

```text
specs/097-recorded-stop-point/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   ├── stop-check-composite.md
│   ├── stop-point-record.md
│   ├── metrics-classification.md
│   └── gate-128-stop-point-recording.md
├── checklists/
│   └── requirements.md   # (from the intake stage)
└── tasks.md              # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

This feature is a targeted change to an existing GitHub Actions pipeline,
not a new application — none of the template's generic Option 1/2/3 trees
apply. The concrete files this feature touches:

```text
.github/
├── actions/
│   └── wing-commander-board-stop-check/
│       └── action.yml                 # new inputs/output, new recording steps, provenance fix
├── scripts/
│   ├── board_stop_check.py            # additive: find_stop_command_comment(), stop_command_reason()
│   ├── board_item_marker.py           # unchanged — reused (add_stalled_label(), write_marker())
│   ├── board_spec_request_body.py     # unchanged — reused (fenced_section())
│   ├── board_eligibility.py           # unchanged — relied upon (is_excluded(), in_flight_candidate())
│   ├── verify-stop-point-recording.py # NEW — Gate 128 + --self-test
│   └── tests/
│       └── board-stop-check/          # NEW fixtures for Gate 128 (and Gate 87 corpus extension)
└── workflows/
    ├── board-loop.yml                 # six call sites: new inputs, stop-cause reads, reworded
    │                                   # stand-down messages, six new always() metrics steps
    └── lint-workflows.yml             # Gate 128 + self-test step registration
```

**Structure Decision**: No new top-level directory. This feature is scoped
entirely to extending one existing composite action, one existing Python
module (additively), the six existing call sites in one existing workflow,
and adding one new gate script plus its fixtures and lint-workflows wiring
— the minimum footprint that satisfies FR-018's "exactly one home" rule
without introducing a new file for logic that already has a home.

## Complexity Tracking

*No entries — Constitution Check above found no violations requiring
justification.*
