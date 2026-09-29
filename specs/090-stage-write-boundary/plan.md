# Implementation Plan: No Stage Is Left Holding Work It Cannot Do — The Implement Stage's Write Boundary

**Branch**: `spec/090-stage-write-boundary` | **Date**: 2026-09-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/090-stage-write-boundary/spec.md`

## Summary

`implement.yml`'s two arms grant the agent an unscoped `Write`/`Edit` and
state no path it may not touch, so a task like spec 060's `T055` (edit
`.claude/skills/spec-cross-reference/SKILL.md`) is discovered to be
impossible only by being refused mid-cycle, and — because `/speckit-converge`
is append-only and convergence is `unchecked-count == 0` — it then holds the
loop open every remaining cycle and evaporates into `finalize.yml`'s
remaining-manual-work prose with no owner. This plan adds one new
`no-write-paths` input to `implement.yml` (default `.claude/`) as the single
declared definition FR-003/FR-019 require, renders it into the prompt by
extending `wing-commander-tool-args` the same way it already renders the
Tooling paragraph's shell-command sentence (FR-004), and adds a new
deterministic composite, `wing-commander-write-boundary`, that classifies
each unchecked task against that same input and reports whether every
remaining unchecked task is out of reach. Loop termination itself needs no
new logic — spec 059's existing hand-off (`progressed=false` and no
`converge:` commit) already stops the loop the moment the only unchecked
task cannot be advanced; this plan only changes what the terminal `reason`
says and adds the filing side effect FR-007 requires. Routing reuses
`wing-commander-stage-findings`'s existing fingerprinting, dedup, cap, and
lifecycle-issue recap machinery under a second, distinct label prefix — so
the routed item never carries a label the board loop would treat as
fix-shaped and hand to an automated fixer FR-002 forbids to write it — with
one new optional `finding-kind` input on that composite so its rendered text
says "routed" rather than "defect" without touching any of its existing
behavior. `finalize.yml` gains one deterministic lookup step, sharing a
newly-extracted fingerprint helper with `wing-commander-stage-findings`
(never a second copy of that formula), so the remaining-manual-work list can
point at a routed item's tracked issue instead of losing it as an orphan
line (FR-009, SC-005).

## Technical Context

**Language/Version**: Bash (`set -uo pipefail`, GitHub Actions `shell: bash`), YAML (GitHub Actions workflow/composite-action syntax), Python 3 (gate scripts under `.github/scripts/`, and the JSON/fingerprint logic already inside `wing-commander-stage-findings`)

**Primary Dependencies**: GitHub Actions (`workflow_call` stages, composite actions), `git`, `jq`, `gh` (issue search/list), the repo's own `wc_shell_harness.py` and `wc_gate_registry.py` gate helpers

**Storage**: N/A — state lives in git (`tasks.md` on the spec branch), `GITHUB_OUTPUT`/`GITHUB_STEP_SUMMARY`, and GitHub Issues (the routed item); no database

**Testing**: Deterministic Python gate scripts (`.github/scripts/verify-*.py`) executing the shipped `run:`/composite bodies against synthetic git repos and fixtures, run locally via `python .github/scripts/run-local-gates.py` and in CI via `lint-workflows.yml`

**Target Platform**: GitHub Actions runners (`ubuntu-latest`), Linux bash

**Project Type**: CI/CD pipeline (GitHub Actions reusable workflows + composite actions) — not a library/service/app

**Performance Goals**: N/A — a handful of additional composite calls and one `gh issue list` search per cycle/finalize run; no throughput target

**Constraints**: MUST NOT widen `implement.yml`'s contract except by new optional inputs with sensible defaults (FR-021); MUST NOT introduce a new `tasks.md` marker or checkbox state (FR-010); the no-write-paths set MUST have exactly one definition consumed by the prompt statement, the classification, and the routing label (FR-003); MUST NOT edit any vendored `.claude/skills/speckit-*` artifact (FR-016); a routed item's label MUST NOT be one the board loop treats as authorizing an automated fixer, since FR-002 binds that fixer too (Assumptions)

**Scale/Scope**: One new workflow_call input pair on `implement.yml` and `finalize.yml`; one extended composite (`wing-commander-tool-args`); one new composite + shared script (`wing-commander-write-boundary`); one additive input on `wing-commander-stage-findings` plus a shared-fingerprint extraction refactor; one new deterministic step in `finalize.yml`; one new gate script with fixtures for every Edge Case; doc corrections in `docs/adoption.md`'s per-stage input tables and `CLAUDE.md`/constitution cross-references per FR-018

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself the worked example FR-017/SC-006 name — spec 060's `T055`, closed by hand in #490, is the fixture this feature's gate replays. **Pass.**
- **II. Cost-Conscious Model Tiering**: No new agent invocation is introduced; every new decision (classification, routing, lookup) is deterministic shell/Python inside existing stage jobs. **Pass, N/A.**
- **III. Simple, GitHub-Native Interaction**: A routed item is an ordinary GitHub issue under a pipeline-owned label, and the lifecycle issue gets the existing recap-comment mechanism naming it — no new surface outside issues/PRs. **Pass.**
- **IV. Automation-First**: FR-009 makes the one manual step this feature can produce (a human-owned routed item) explicit on the lifecycle issue rather than silently assumed. **Pass.**
- **V. Security**: FR-002 is exactly this principle's least-privilege rule applied to `.claude/`; no tool grant is widened by this feature, and the new `no-write-paths` statement can only ever narrow what the prompt tells the agent to attempt, never broaden its actual tool grants. **Pass.**
- **VI. Portability**: Every new composite lives under this repository's own `.github/actions/`; the new `no-write-paths` input's default (`.claude/`) is this repository's own configuration, overridable per FR-019/FR-021 by an adopter with different consuming-instrument paths. **Pass.**
- **VII. Two Interfaces**: `implement.yml` and `finalize.yml` each gain two new optional `workflow_call` inputs (`no-write-paths` on `implement.yml` only; `write-boundary-label-prefix` on both) — additive, defaulted, non-breaking widenings of the published contract (FR-021), the same class of change spec 059's `wing-commander-tasks-checkbox-count` and spec 010's `wing-commander-spec-meta` already made. `wing-commander-write-boundary` is a new published composite (same class of addition). `wing-commander-stage-findings` gains one new optional input (`finding-kind`, default `defect`) with no change to any existing input, output, or default-path behavior. **Pass, with recorded minor-surface additions** (see Complexity Tracking).
- **VIII. A Green Check Means What It Says**: FR-020's new gate is reachable through the registry, executes the shipped composite/script bodies (never a re-implementation), and carries a checked-in fixture for every Edge Case this spec names, plus the SC-007 mutation battery (disable the check; drift the statement from the real input). **Pass by design; enforced at the tasks/implement stage.**
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic Code**: Classification (FR-006), routing (FR-007), idempotency (FR-008), and the `finalize.yml` lookup are all deterministic script/shell reading `no-write-paths` and `tasks.md`, never an agent's own judgement about whether a task is in reach. This is the spec's own thesis, extended to a new case spec 059/IX did not cover. **Pass.**
- **X. Bounded Autonomy**: A routed item's label (`write-boundary-label-prefix`, default `route-out-of-boundary`) is deliberately distinct from any label Principle X already names as board-loop entry authorization (a maintainer label, `found-by:<stage>`, `spec-request`), so the loop never auto-works it — it is read-only-visible to the loop's own triage-proposal path, never pushed for, until a human relabels it. This is the design choice the spec's Assumptions section asks the plan to make explicit. **Pass.**

No violations requiring justification beyond the recorded VII notes above.

## Project Structure

### Documentation (this feature)

```text
specs/090-stage-write-boundary/
├── plan.md                          # This file
├── research.md                      # Phase 0 output
├── data-model.md                    # Phase 1 output
├── quickstart.md                    # Phase 1 output
├── contracts/
│   ├── write-boundary-mechanism.md  # Phase 1 output — statement, classification, routing, lookup
│   └── write-boundary-gate.md       # Phase 1 output — the FR-020 gate's contract
└── tasks.md                         # Phase 2 output (/speckit-tasks — not produced here)
```

### Source Code (repository root)

This is a CI/CD pipeline repository, not an application; there is no `src/`.
The feature's real "source" is GitHub Actions workflow and composite-action
YAML plus Python/shell gate scripts:

```text
.github/workflows/
├── implement.yml                    # new `no-write-paths` and
│                                      # `write-boundary-label-prefix`
│                                      # workflow_call inputs; both
│                                      # tool-args compose steps (:849,
│                                      # :1562) pass the new input through;
│                                      # both Tooling paragraphs (:975-990,
│                                      # :1707-1722) render the new
│                                      # statement; a new classification
│                                      # step follows each checkbox-tip read
│                                      # (:checkbox-tip-cycle,
│                                      # :checkbox-tip-retry); both read-back
│                                      # steps (:1278-1442, :1966-2130) gain
│                                      # a routed reason branch; "Consolidate
│                                      # final outcome" carries the new
│                                      # step-local outputs through the
│                                      # existing RETRY_RAN selection; a new
│                                      # "Route out-of-boundary tasks" step
│                                      # sits beside "File findings from
│                                      # this run" (:2260-2274)
├── finalize.yml                     # new `write-boundary-label-prefix`
│                                      # workflow_call input; a new
│                                      # deterministic "Look up routed
│                                      # write-boundary items" step feeds
│                                      # the existing remaining-manual-work
│                                      # prompt (:686-738)
├── wing-commander-5-implement.yml   # wires the two new inputs from a new
│                                      # repo var,
│                                      # WING_COMMANDER_WRITE_BOUNDARY_LABEL_PREFIX
│                                      # (default route-out-of-boundary),
│                                      # and WING_COMMANDER_IMPLEMENT_NO_WRITE_PATHS
│                                      # (default .claude/)
├── wing-commander-6-finalize.yml    # wires write-boundary-label-prefix
│                                      # from the same repo var
└── lint-workflows.yml               # new "Gate N — ..." registration

.github/actions/
├── wing-commander-tool-args/
│   └── action.yml                   # new `no-write-paths` input, new
│                                      # `write-paths-statement` output,
│                                      # rendered the same way as
│                                      # `shell-commands` (contracts/
│                                      # write-boundary-mechanism.md §1)
├── wing-commander-write-boundary/
│   └── action.yml                   # NEW — front door to
│                                      # classify-out-of-boundary-tasks.sh
├── wing-commander-stage-findings/
│   └── action.yml                   # new optional `finding-kind` input
│                                      # (default `defect`); delegates its
│                                      # fingerprint computation to the new
│                                      # shared helper instead of computing
│                                      # it inline
└── _shared/
    ├── classify-out-of-boundary-tasks.sh  # NEW — the one home of the
    │                                        # per-task boundary check
    └── compute-finding-fingerprint.sh     # NEW — extracted from
                                             # wing-commander-stage-findings
                                             # so finalize.yml's lookup step
                                             # and the findings composite
                                             # compute the same value once

.github/scripts/
└── verify-write-boundary.py          # NEW gate script, following
                                        # verify-tasks-checkbox-convergence-
                                        # signal.py's extraction + synthetic-
                                        # repo + mutation-battery pattern

docs/
└── adoption.md                       # per-stage input tables for
                                        # implement.yml/finalize.yml
                                        # (FR-018, FR-021)
```

**Structure Decision**: Single-project CI pipeline layout already established
by this repository (`.github/workflows/`, `.github/actions/`,
`.github/scripts/`); this feature adds one shared script pair, one composite
action, one additive input on an existing composite, one gate script, and
edits the existing `implement.yml`/`finalize.yml`/wrapper workflows in
place. No new top-level directory is introduced.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|---------------------------------------|
| New published composite `wing-commander-write-boundary` widens Principle VII's action surface | FR-006 requires the per-task boundary classification to be deterministic code shared by both the cycle and retry arms (FR-003's single-definition rule extended to this derived value); the sibling pattern (`wing-commander-tasks-checkbox-count`) is how this repository already gives a value two arms need one home, and this feature's own gate enforces no second copy of the classification idiom | Inlining the classification in each read-back step was rejected by FR-003/FR-006 and CLAUDE.md's "Shared logic has exactly one home"; folding it into `wing-commander-tasks-checkbox-count` itself was rejected because that composite's contract (research.md D3) is pinned to being a pure read of checkbox state — the Dependencies section of spec.md explicitly says it is "left unchanged" by this feature, since FR-010 adds no new `tasks.md` state for it to read |
| `wing-commander-stage-findings` gains a new optional `finding-kind` input | FR-007's routed item must not be described to a maintainer as "a defect" — that composite's existing recap phrase and label description are hardcoded to defect framing, and FR-008's idempotency/dedup/cap value is worth reusing rather than rebuilding | A parallel filing composite duplicating fingerprinting, dedup, and cap logic was rejected outright by CLAUDE.md's "Shared logic has exactly one home" — the per-run cost line's own worked example in that document is exactly this failure mode; the new input is additive-only (default `defect` reproduces today's behavior byte-for-byte, so no existing caller's output text changes) |
