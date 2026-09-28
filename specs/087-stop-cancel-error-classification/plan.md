# Implementation Plan: Classify the cancel call's own error instead of racing a pre-read status

**Branch**: `087-stop-cancel-error-classification` | **Date**: 2026-09-28 | **Spec**: [specs/087-stop-cancel-error-classification/spec.md](./spec.md)

**Input**: Feature specification from `/specs/087-stop-cancel-error-classification/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

`wing-commander-board-stop-check`'s cancel path reads a target run's status,
then conditionally calls `gh run cancel` and warns unconditionally on
failure — a race window between the read and the call means an
already-finished target still produces a spurious warning, the exact noise
the pre-check exists to prevent. The fix removes the status gate and ports
`pr-conversation.yml`'s already-accepted idiom: attempt the cancellation
unconditionally (once the existing ownership check passes), then classify
the outcome from the call's own error output. The already-terminal
recognition vocabulary — anchored to `HTTP 409` rather than bare digits, per
FR-005 — moves into one new shared script,
`.github/actions/_shared/cancel-already-terminal.sh`, consumed by both stop
procedures; each site keeps its own distinct reporting. The already-terminal
outcome becomes a non-warning informational line; every other failure stays
a `::warning::`, now with its error text neutralised before interpolation.
Coverage lands in the two gates that already own these subjects
(`verify-board-stop-check.py`, `verify-single-home-idioms.py`), extended
rather than duplicated, each carrying a mutation that proves it can fail.

## Technical Context

**Language/Version**: Bash (GitHub Actions `shell: bash` steps, composite
actions and workflow jobs) for the shipped behaviour; Python 3 for the gate
scripts that verify it.

**Primary Dependencies**: `gh` CLI, `jq`, GitHub Actions composite-action
mechanics (`$GITHUB_ACTION_PATH`); `pyyaml` for the gate scripts that parse
`action.yml`.

**Storage**: N/A — no persistent state; every value here lives for the
duration of one job step.

**Testing**: The repository's own gate-script harness —
`verify-board-stop-check.py` (checked-in JSON fixtures plus an extracted-
and-executed copy of the composite's own shell against a stubbed `gh`) and
`verify-single-home-idioms.py` (structural regex/co-occurrence scans over
`.github/actions/**` and `.github/workflows/**`), both invoked via `python
.github/scripts/run-local-gates.py` per CLAUDE.md.

**Target Platform**: GitHub Actions runners (`ubuntu-latest`), executing
this repository's own board loop and PR-conversation workflows.

**Project Type**: Single repository of GitHub Actions workflows, composite
actions, and the Python gate scripts that verify them — not a
library/CLI/web-service in the template's sense.

**Performance Goals**: N/A — this is log-noise/correctness behaviour on an
infrequent (stop-request-triggered) code path, not a throughput or latency
concern.

**Constraints**: Must not change the step's exit status or the `paused`
output in any outcome (FR-006); must not weaken the existing ownership/
self-run protections (User Story 3); must not widen either site's token
usage (App token for issue-comment/PR-comment reads, cancel/dispatch token
for `gh run cancel` calls, unchanged).

**Scale/Scope**: One composite action's `check` step, one new ~15-line
shared script, one line in `pr-conversation.yml`, two existing gate scripts
extended, no new gate ID.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: N/A to this gate directly — this feature is itself already
  flowing through the pipeline (issue #621, this spec/plan). No violation.
- **II. Cost-Conscious Model Tiering**: No new agent invocation is added by
  this feature; nothing to tier. Pass.
- **III. Simple, GitHub-Native Interaction**: No change to how a maintainer
  interacts with the pipeline. The lifecycle issue (#621) carries this
  plan's summary per the standard stage-posts-status convention. Pass.
- **IV. Automation-First**: No new manual step is introduced. Pass.
- **V. Security**: No change to trust boundaries, token scoping, or which
  actor's content is treated as instructions. The App-token/cancel-token
  split (issue #461) is explicitly preserved (FR-006, `data-model.md`).
  Pass.
- **VI. Portability**: All changes are within this repository's own
  `.github/` tree; no Wing-Commander-bundled artifact is touched. Pass.
- **VII. Two Interfaces**: `wing-commander-board-stop-check` is a composite
  action under `.github/actions/`, not a `workflow_call` stage workflow —
  it is consumed by `board-loop.yml` (a wrapper), so it is not part of the
  published stage contract VII defines, and this change does not touch any
  `workflow_call` input/output/secret name. `pr-conversation.yml` is
  likewise a wrapper-layer workflow, not a published stage. Pass, no
  registered exception needed.
- **VIII. A Green Check Means What It Says**: Directly governs this
  feature's own gate work. Both extended gates (`verify-board-stop-check.py`,
  `verify-single-home-idioms.py`) already satisfy "reachable through the
  gate registry" and "same subject, same arguments locally as CI" (both run
  under `run-local-gates.py`); this plan's `contracts/gate-coverage-087.md`
  requires each new branch to carry a checked-in fixture AND a mutation
  that the fixture set must catch (FR-008/SC-003, SC-007) — satisfying "not
  a manual demonstration" and "every failure branch exercised." Pass, and
  the plan's own gate design is written to keep passing this principle
  under review.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: The already-terminal classification is a durable-action gate (it
  decides whether a `::warning::` annotation — which can trigger the
  watchdog's collector, per `specs/088-stop-check-closed-read`'s own
  observed facts — is emitted). This feature implements it as a
  deterministic bash predicate (`cancel-already-terminal.sh`'s exit code),
  never a model judgment call. Pass.
- **X. Bounded Autonomy**: This feature is itself the kind of fix-shaped
  change X describes (deterministic, gate-shaped, no design trade-off left
  after clarification) — consistent with how issue #621 was routed
  (`reason=contract_widening` per the route agent, followed by clarify
  resolving the two open questions). Not itself a change to the board
  loop's own bounded-autonomy behaviour. Pass.

No violations requiring `Complexity Tracking`.

*Post-design re-check (after Phase 1): unchanged — the data model, contracts
and quickstart above introduce no new dependency, no new external
interface, and no principle-relevant surface beyond what this section
already evaluated. Pass.*

## Project Structure

### Documentation (this feature)

```text
specs/087-stop-cancel-error-classification/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── cancel-already-terminal-script.md
│   ├── board-stop-check-classification.md
│   ├── pr-conversation-vocabulary-consolidation.md
│   └── gate-coverage-087.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── actions/
│   ├── _shared/
│   │   └── cancel-already-terminal.sh          # NEW (FR-005, FR-009)
│   └── wing-commander-board-stop-check/
│       └── action.yml                          # MODIFIED: check step (FR-001–FR-004, FR-006, FR-010, FR-011)
├── workflows/
│   └── pr-conversation.yml                     # MODIFIED: one line in "Stop procedure" step (FR-005, FR-009)
└── scripts/
    ├── verify-board-stop-check.py              # MODIFIED: extended fixtures + mutation (FR-007, FR-008)
    ├── verify-single-home-idioms.py            # MODIFIED: new DECLARED_HOMES entry + check (FR-009a)
    └── tests/
        └── board-stop-check/                   # existing fixtures unchanged; harness in the .py gains inline cases
```

This repository has no `src/`/`tests/` application layout — it is a
GitHub Actions workflow/composite-action repository whose "source" is
`.github/workflows/**` and `.github/actions/**`, and whose "tests" are the
Python gate scripts under `.github/scripts/` plus their checked-in JSON
fixtures under `.github/scripts/tests/`. None of the template's
Option 1/2/3 layouts apply.

**Structure Decision**: Single project, this repository's existing
`.github/` layout. One new file
(`.github/actions/_shared/cancel-already-terminal.sh`), one composite
action modified in place, one workflow modified by a single line, and two
existing gate scripts extended in place — no new directory, no new gate ID,
no new top-level structure.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. Table intentionally omitted.
