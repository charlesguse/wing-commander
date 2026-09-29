# Implementation Plan: Bounded, Idempotent spec-request Filing

**Branch**: `092-bounded-spec-request-filing` | **Date**: 2026-09-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/092-bounded-spec-request-filing/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

The board loop's three `spec-request` filing sites (route's spec verdict,
the fix job's post-push breach, and both of readiness's backstop-breach
entries) each retry an unbounded number of times on a failure that can
never heal itself (a missing label, a lost permission), starving the rest
of the board, and can file a duplicate `spec-request` when a create
succeeds but a later write in the same run fails. This plan generalizes
the one existence check that already exists at readiness's `step=breach`
retry entry (#530) into a single shared module
(`board_spec_request_filing.py`) all three sites call before creating, and
adds a bounded, marker-persisted attempt count (`spec_request_attempts`,
capped at a new `BOARD_LOOP_SPEC_REQUEST_ATTEMPT_BUDGET = 3`) that stalls
an item with an explicit give-up comment on its third consecutive failure
rather than retrying forever. Both changes route through the existing
marker, label, comment, and cross-link mechanisms with no new artifact
shape, and are enforced by a new check in the gate (Gate 93) that already
owns every other rule about a spec-request creation site.

## Technical Context

**Language/Version**: Python 3 (matching every other `.github/scripts/
board_*.py` module) and GitHub Actions workflow YAML/bash — no new
runtime.

**Primary Dependencies**: `gh` CLI (issue/PR read and write), `jq` (already
used throughout board-loop.yml for JSON plumbing), the repository's own
`.github/scripts/board_item_marker.py`, `board_eligibility.py`,
`board_spec_request_body.py` modules this feature extends or joins.

**Storage**: None beyond the existing board item marker — an HTML comment
embedded in a GitHub issue comment (spec 057). No database, no new file
format.

**Testing**: The repository's existing convention — a `verify-*.py` gate
script per concern, run via `python .github/scripts/run-local-gates.py`
(the same set `lint-workflows.yml` invokes in CI), with fixture-driven unit
tests for pure functions under `.github/scripts/tests/<concern>/`
(`verify-board-eligibility.py`'s pattern). No new test framework.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), against the
`board-loop.yml` workflow's own three jobs (`route`, `fix`, `readiness`).

**Project Type**: Single repository automation pipeline (GitHub Actions
workflows + Python helper scripts) — not a web/mobile/service split.

**Performance Goals**: Not latency-sensitive; bounded by SC-001 (at most 3
filing attempts, 6 agent invocations per starved item) rather than a
throughput target. The new lookup step adds at most two `gh api` calls
(issue events, issue search) per filing attempt, at each of three sites —
negligible against the existing per-run `gh` call volume.

**Constraints**: Must not widen the published contract (Constitution VII —
`board-loop.yml` is a consuming-instrument wrapper, not a published stage,
so this is a soft constraint here, but the shared logic still must not leak
into any `.github/actions/**` composite adopters could pin). Every durable
decision (the existence match, the attempt-cap crossing) must be
deterministic code, never an agent's judgment (Constitution IX). Gate 93's
existing ban on `gh api`/`gh issue view` inside a spec-request create step
constrains the new lookup to its own preceding step at each site.

**Scale/Scope**: Three call sites in one workflow file, two extended
scripts (`board_item_marker.py`, `board_spec_request_body.py`), one new
script (`board_spec_request_filing.py`), one extended gate
(`verify-issue-context-single-home.py`, Gate 93). No change to any other
stage workflow or composite action.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself worked through the pipeline (issue
  #701, this spec/plan on `specs/092-bounded-spec-request-filing`). Pass.
- **II. Cost-Conscious Model Tiering**: No new agent invocation is added by
  this feature — the existence check and attempt bound are both
  deterministic code, running in existing triage/route/fix/readiness
  steps that already declare their model and `--max-turns`. Pass.
- **III. Simple, GitHub-Native Interaction**: The give-up stall and the
  reuse notice are both ordinary issue comments/labels, legible from the
  issue alone (User Story 3, FR-012, SC-004) — no new dashboard or channel.
  Pass.
- **IV. Automation-First**: The bound and the existence check are fully
  automated; the one manual step that survives (removing `board:stalled`
  to re-admit a capped item) is the loop's existing, already-reported
  re-eligibility convention (FR-014), not a new one. Pass.
- **V. Security**: No change to entry authorization, trust filtering, or
  tool allowlists. The existence-check lookup reads only issue metadata
  (author, body, timestamps) already fetched today by the #530 lookup it
  generalizes, through the same `gh api` shape; no new untrusted content
  reaches an agent prompt (there is no agent in this path at all). Pass.
- **VI. Portability**: `board-loop.yml` and its `.github/scripts/board_*.py`
  helpers are this repository's own consuming-instrument code (spec 057),
  not part of the published `workflow_call` surface — this feature adds no
  new repository-specific hardcoding beyond what already exists there.
  Pass.
- **VII. Two Interfaces**: `board-loop.yml` is a wrapper/consuming-instrument
  workflow, not a published stage; no `workflow_call` input/output/secret
  is added, removed, or renamed. The new script joins `.github/scripts/`
  (already internal), not `.github/actions/**`. Pass.
- **VIII. A Green Check Means What It Says**: The new Gate 93 check 6 is
  triggered by changes to `board-loop.yml` and the new script (same
  trigger check 3 already uses), runs the same subject locally and in CI
  (`run-local-gates.py`), and its failure branches are fixture-covered
  (contracts/gate-spec-request-single-home.md). Pass — re-verified in
  Phase 1 design against the actual check design.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: The existence match, the attempt-cap crossing, and the give-up
  decision are all pure functions in `board_spec_request_filing.py`
  (research.md D1, D6), never an agent's read of "is this the same work".
  Pass.
- **X. Bounded Autonomy**: This feature strengthens X's own "each item
  MUST carry a bounded round budget" requirement (spec 057 FR-050) for a
  path that did not yet honor it; it adds no new merge class and touches
  none of the three the constitution already enumerates. Pass.

No violations requiring Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/092-bounded-spec-request-filing/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── spec-request-existence-check.md
│   ├── spec-request-attempt-bound.md
│   └── gate-spec-request-single-home.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

**Structure Decision**: This is not an application with a src/tests split
— it is a change to one GitHub Actions workflow and its Python helper
scripts, following the existing layout under `.github/`:

```text
.github/
├── workflows/
│   └── board-loop.yml                        # three filing sites updated: lookup step added/
│                                              # generalized, create-failure branch extended
├── scripts/
│   ├── board_spec_request_filing.py          # NEW: existence check + attempt-bound decisions
│   ├── board_item_marker.py                  # extended: spec_request_attempts field
│   ├── board_spec_request_body.py            # extended: truncate_title()
│   ├── verify-issue-context-single-home.py   # extended: Gate 93 check 6
│   ├── wc_gate_registry.py                   # unchanged registration point for check 6
│   └── tests/
│       └── board-spec-request-filing/        # NEW: fixtures for find_existing/reopened_since/
│                                              # record_attempt, and Gate 93 check 6's own cases

specs/057-autonomous-board-loop/
└── contracts/board-item-marker.md            # live, gate-read contract: implementation stage
                                               # updates its payload shape alongside
                                               # board_item_marker.py (out of scope for this
                                               # plan stage's specs/092-only edit boundary)
```

## Complexity Tracking

No Constitution Check violations. Not applicable.
