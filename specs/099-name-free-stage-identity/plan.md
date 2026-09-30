# Implementation Plan: Name-Free Stage Identity for Watchdog Collectors

**Branch**: `099-name-free-stage-identity` | **Date**: 2026-09-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/099-name-free-stage-identity/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

The watchdog and its collectors identify the pipeline stage an inspected
run executed by matching the run's workflow **display name** against six
hardcoded reference strings (`"Wing Commander · 1 intake"` … `"6
finalize"`). An adopter who renames their wrapper workflows — exactly the
portability constitution VI promises — gets a silent "not my stage,
skipping" from every collector and a false "passed inspection" verdict
(constitution VIII's forbidden un-failable check).

The fix consolidates stage identification into a single **resolved
stage identity** (`resolved-stage`/`resolved-stage-source`), computed
once inside the existing `wing-commander-inspected-run-identity`
composite action (already the one home for the run's spec slug and its
`record-stage` output), with a fixed precedence: the run's own metrics
record wins; the display name is consulted only as a documented fallback
when the record yields no stage at all. Every FR-002 consumer site in
`watchdog.yml` switches from matching `$RUN_NAME` to reading this shared
output and now distinguishes three states — identified/in-scope,
identified/out-of-scope, and not-identified — where today it only ever
distinguished two, silently treating "not identified" as "out of scope."

Two further pieces close the gaps that would otherwise reopen once names
stop being the primary signal: (1) the existing single-spec-stage
allowlist that lets the slug-fallback trust a borrowed record is replaced
by a new field the record itself carries (`spec.identity_is_own`), set by
each stage that emits a record, so no central list of stage names has to
track which stages are "single-spec" as new stages are added; (2) a new
checked-in gate fails the build if a reference display name ever reappears
as a primary stage-identification condition anywhere in `watchdog.yml` or
the identity composite, outside the one documented fallback site — so the
consolidation this plan performs cannot silently erode on the next edit.

## Technical Context

**Language/Version**: Bash (`run:` steps, `set -uo pipefail` convention)
and Python 3 (gate scripts under `.github/scripts/`), matching every
other change to this repository's workflows and gate suite.

**Primary Dependencies**: GitHub Actions composite actions (`.github/
actions/**`), reusable workflows (`.github/workflows/*.yml`), `gh` CLI,
`jq`. No new external dependency.

**Storage**: The durable metrics-record JSON artifact
(`wing-commander-metrics-record*`), whose documented shape lives in
`specs/043-durable-metrics-record/contracts/metrics-record-schema.md`.
This feature adds one additive field to it; no new storage.

**Testing**: This repository's existing gate suite
(`.github/scripts/verify-*.py`/`.sh`, invoked via
`python .github/scripts/run-local-gates.py`, the same set
`lint-workflows.yml` runs in CI), fixture-driven against synthetic
metrics records and transcripts. No end-to-end Actions test exists
locally; Actions-only behavior is proven by a post-merge re-drive per
CLAUDE.md.

**Target Platform**: GitHub Actions (Linux runners), this repository's
published stage workflows and consuming-instrument wrappers.

**Project Type**: Single repository of GitHub Actions workflows and
composite actions (no frontend/backend split).

**Performance Goals**: N/A — no latency budget beyond FR-004's explicit
constraint (zero additional metrics-record downloads per inspection).

**Constraints**: FR-004 (no added metrics-record download); FR-002's
single named exception (the slug-fallback allowlist keeps consuming the
record's own declaration, not the resolved stage); spec 109's constraint
that `record-stage`'s own value and the signals keyed on it are
untouched (research.md R1).

**Scale/Scope**: One composite action (`wing-commander-inspected-run-
identity`), one workflow (`watchdog.yml`, ~4,100 lines, 7 FR-002 sites
plus the self-inspection guard), one shared metrics-emission composite
(`wing-commander-metrics-summary`) and its ~30 call sites across 12
stage/consuming-instrument workflows, one live contract document (spec
043's schema), one new gate script, one documentation section
(`docs/adoption.md`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide | Built through the pipeline itself, from a real issue (#750), a real spec, real PRs. | Pass |
| II. Model tiering | No new agent invocation introduced by this feature (it is deterministic workflow/gate logic only). | N/A / Pass |
| III. GitHub-native | No new interaction surface; lifecycle stays legible via the issue comment this stage posts. | Pass |
| IV. Automation-first | No new manual step introduced. | Pass |
| V. Security | No change to trust boundaries, tokens, or which content is treated as instructions. The new gate and record field are read-only/additive. | Pass |
| VI. Portability | This is the defect being fixed: today's hardcoded reference names in a published stage violate VI directly. Removing them is the point. | Addressed by this feature |
| VII. Two interfaces | Changes land in the published contract (`watchdog.yml`, the identity/metrics-summary composites) — output-additive only (`resolved-stage`/`resolved-stage-source`/`spec-identity-is-own` are new, nothing existing is renamed or removed), so this is a widening act, not a breaking one, and is deliberate per VII. | Pass, deliberate widening |
| VIII. Green check | This is the second defect being fixed: a collector that cannot fail its subject (silent skip on rename) reports a pass it did not earn. FR-005/FR-006/SC-003 close it; the new FR-012 gate fails loudly on regression, never silently. | Addressed by this feature |
| IX. Judgment in code | The resolved-stage precedence, the spec-identity declaration, and the FR-012 gate are all deterministic code, not a prompt — no agent judgment is introduced. | Pass |
| X. Bounded autonomy | N/A — this is a spec-shaped change already routed through the full lifecycle, not a board-loop fix. | N/A |

No violations requiring the Complexity Tracking table.

## Project Structure

### Documentation (this feature)

```text
specs/099-name-free-stage-identity/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── resolved-stage-identity.md
│   ├── spec-identity-declaration.md
│   └── stage-identity-name-gate.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This is not an application with src/tests directories — it is a
repository of GitHub Actions workflows, composite actions, and their
Python/bash gate scripts. The feature touches:

```text
.github/
├── actions/
│   ├── wing-commander-inspected-run-identity/
│   │   └── action.yml            # +resolved-stage/-source outputs; slug-fallback
│   │                              #   reads spec.identity_is_own instead of $RUN_NAME
│   └── wing-commander-metrics-summary/
│       └── action.yml            # +spec-identity-is-own input -> spec.identity_is_own
├── workflows/
│   ├── watchdog.yml               # 7 FR-002 sites switch to resolved-stage;
│   │                              #   collector-outcomes.json gains "unresolved";
│   │                              #   aggregate step + verdict strings extended;
│   │                              #   new FR-014 warning step
│   ├── intake.yml, clarify.yml, plan.yml, tasks.yml,
│   │   implement.yml, finalize.yml, cleanup.yml, rebase.yml,
│   │   pr-conversation.yml, board-loop.yml,
│   │   lifecycle-review-gate.yml  # each metrics-summary call site declares
│   │                              #   spec-identity-is-own explicitly
│   └── lint-workflows.yml         # +new Gate <N> step (verify-no-reference-
│                                  #   name-stage-match.py) and its self-test
└── scripts/
    ├── verify-no-reference-name-stage-match.py   # NEW (FR-012)
    ├── verify-metrics-record-schema.py           # +spec.identity_is_own fixtures
    ├── verify-metrics-summary-record-emission.py # +spec-identity-is-own cases
    └── fixtures/metrics-record-schema/           # +fixtures, pinned count bumped

specs/043-durable-metrics-record/contracts/
└── metrics-record-schema.md       # +spec.identity_is_own, additive, FR-008b

docs/
└── adoption.md                    # +new subsection (FR-011/US3)
```

**Structure Decision**: No new directories. Every change lands inside
this repository's existing layout for published stages
(`.github/workflows/`), shared composites (`.github/actions/`), gates
(`.github/scripts/`), and live cross-spec contracts
(`specs/043-.../contracts/`), per constitution VI/VII and CLAUDE.md's
"shared logic has exactly one home."

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — table intentionally omitted.
