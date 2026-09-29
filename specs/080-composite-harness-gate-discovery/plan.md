# Implementation Plan: Composite Test Harness Gate Discovery

**Branch**: `spec/080-composite-harness-gate-discovery` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/080-composite-harness-gate-discovery/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

`wc_gate_registry.py` — the shared module `run-local-gates.py` and
`verify-gate-wiring.py` both import so they cannot disagree about what a
gate is — discovers gates under `.github/scripts/` only. That scoping is
already correct for FR-001 (it is the convention this feature makes
mechanical rather than assumed); what is missing is a check that fails
when a test harness or standalone gate script instead lands under
`.github/actions/`, a widened reverse-wiring check that catches a
`.github/actions/` script path a `run:` block names but that does not
exist on disk, a per-gate identity that survives five different
`run-tests.sh` harnesses sharing one basename, and one canonical
explanation of the placement convention that today's three composite
harnesses each restate in their own words.

The approach is four narrowly-scoped changes, each mapped to a requirement
group: a new gate (`verify-actions-no-gate-scripts.py`) that enforces
FR-001/FR-006/FR-012/FR-014 by walking `.github/actions/` for what does not
belong there; an extension of `verify-gate-wiring.py`'s existing
`.github/scripts/`-only reverse check to also cover `.github/actions/`
paths (FR-004), reusing the same substring-match technique that already
makes the self-checkout prefix a non-issue (FR-013); moving `run-local-
gates.py`'s gate-label computation into `wc_gate_registry.py` so it is
built from a gate's full discovery-relative path instead of its basename
(FR-007); and replacing the duplicated "why this harness lives here" prose
in three harness files with one canonical copy the new gate's docstring
carries, with pointer comments enforced by the existing Gate 47 (FR-009,
FR-011). FR-002/FR-003/FR-005/FR-008 are already true of the shipped code
and need verification, not new plumbing — recorded in research.md D1 and
exercised by quickstart.md rather than re-implemented.

## Technical Context

**Language/Version**: Python 3 (stdlib + PyYAML, matching every other
`.github/scripts/verify-*.py`), Bash for harness entrypoints (`run-tests.sh`).

**Primary Dependencies**: `wc_gate_registry.py` (shared discovery module),
`wc_shell_harness.py` (bash/jq resolution used by harnesses and the local
runner) — both already vendored in `.github/scripts/`. No new third-party
dependency.

**Storage**: N/A — every entity here is read from the checked-out tree
(workflow YAML, action YAML, the `.github/actions/`/`.github/scripts/`
directory structure) at gate-run time. `run-local-gates.py`'s timing
cache (`<tempdir>/wing-commander-gate-timings.json`) is pre-existing,
machine-local scratch, not a data store this feature introduces.

**Testing**: Each new/changed gate script's own `--self-test` flag against
in-source, checked-in fixtures (this repository's standing convention —
see `verify-actions-layer-invariants.py`'s `_write`/`FIXTURES` pattern),
invoked directly and via `python .github/scripts/run-local-gates.py`.

**Target Platform**: GitHub Actions `ubuntu-latest` runners (CI) and a
maintainer's own machine, Linux/macOS/Windows (`run-local-gates.py`
already resolves `bash`/`python3` portably; nothing here changes that).

**Project Type**: CI tooling embedded in this repository's own pipeline —
not an application with its own `src/`/`tests/` split. The "source tree"
for this feature is `.github/scripts/`, `.github/workflows/lint-
workflows.yml`, and `.github/actions/*/` (as the subject under review, not
as code this feature ships into).

**Performance Goals**: The new enforcement gate is a static directory walk
over `.github/actions/**` (a few dozen files) — sub-second, not a
measurable addition to the suite's wall-clock budget documented in
`run-local-gates.py`'s own docstring (1599s serial baseline, dominated by
three ~300s harnesses this feature does not touch).

**Constraints**: FR-001 requires `.github/scripts/` to remain the *only*
discovery root `gate_scripts()` walks — the new enforcement logic must be
additive (a second, separate query: "what should NOT be under
`.github/actions/`"), never a widening of what `run-local-gates.py`
treats as a gate to run. The enforcement walk must be rooted at this
repository's own `.github/actions/` directory, never a recursive sweep
from repo root, so a vendored self-checkout directory (`.wing-commander-
pipeline/.github/actions/**`, present during this repository's own
auto-update/auto-release E2E runs) is never swept as if it were part of
the tree under review (spec.md Edge Cases, FR-012).

**Scale/Scope**: ~100 PR-time gates today (`wc_gate_registry.pr_time_gates()`
over `lint-workflows.yml`); five `.github/scripts/*/run-tests.sh` harnesses
sharing the basename `run-tests.sh`, three of which are composite-action
harnesses in scope for FR-009/FR-011; zero existing files under
`.github/actions/` violate FR-012 today (verified: no `run-tests.sh` or
standalone `verify-*` exists there yet), so this feature's own gate ships
with nothing of its own to fix and depends entirely on fixtures for
coverage (FR-010).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle VIII (A Green Check Means What It Says)** — this feature
  *is* principle VIII's worked example, cited by number in spec.md Story
  2 ("Principle VIII calls a liability"): the originating defect
  (composite harnesses invisible to `run-local-gates.py` while CI ran
  them) is exactly "a check that cannot fail its own subject." Every
  design decision below keeps a gate reachable through the registry, run
  with the same subject/arguments locally as in CI, triggered by an edit
  to what it checks, loud rather than vacuous when it cannot reach its
  subject, and covered by a checked-in fixture per failure branch. PASS —
  no tension, this plan implements the principle rather than trading
  against it.
- **Principle IX (Judgment That Gates a Durable Action Belongs in
  Deterministic Code)** — every check this feature adds or extends is a
  plain Python/Bash static-analysis script with no model in the loop;
  "is this file in an unsupported location" and "does this path exist on
  disk" are deterministic questions today and remain so. PASS.
- **FR-014 / `wc_gate_registry.py`'s own stated philosophy** — "a
  mechanical convention, not a manifest of gate names" (module docstring,
  quoted in research.md D2) is the same discipline issue #149 already
  forced on gate discovery; this feature applies it a second time, to
  placement rather than invocation. The design below reads the directory
  tree by convention (a filename pattern and a fixed carve-out directory),
  never a list of harness names. PASS.
- **Constitution VII (Two Interfaces)** — `.github/actions/**` composites
  are the published, adopter-pinned contract; this feature adds no input,
  secret, or output to any composite's `action.yml`, and touches no
  `workflow_call` interface (spec.md Assumptions confirms this
  explicitly). The new gate and the reverse-check extension are pure
  additions to the *consuming instrument* (`.github/scripts/`,
  `lint-workflows.yml`). PASS.

No violations. Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/080-composite-harness-gate-discovery/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   ├── gate-registry-extensions.md
│   └── enforcement-gate-cli.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This feature ships no application code; it changes this repository's own
CI tooling tree. Concrete paths, not the generic template options:

```text
.github/
├── scripts/
│   ├── wc_gate_registry.py                 # gains: unsupported-actions-location
│   │                                        #   walk, .github/actions/ reference
│   │                                        #   extraction, shared gate_label()
│   ├── verify-actions-no-gate-scripts.py   # NEW gate — FR-001/006/012/014,
│   │                                        #   carries the canonical placement
│   │                                        #   prose (FR-009)
│   ├── verify-gate-wiring.py                # extended reverse check (FR-004),
│   │                                        #   gains --self-test (FR-010)
│   ├── run-local-gates.py                   # label_of -> wc_gate_registry.gate_label
│   ├── dispatch-and-wait-tests/run-tests.sh # prose -> pointer (FR-009/FR-011)
│   ├── size-path-backstop-tests/run-tests.sh    # prose -> pointer
│   └── stage-findings-tests/run-tests.sh        # prose -> pointer
└── workflows/
    └── lint-workflows.yml                   # + Gate <N> step/self-test step;
                                              #   paths: filter verified, not
                                              #   edited (FR-008; research.md D1)
```

**Structure Decision**: Single project — this repository's own
`.github/scripts` + `.github/workflows` + `.github/actions` tree, reviewed
as the subject of a CI-tooling feature rather than as this feature's
delivery vehicle. No `src/`/`tests/` split applies; every change is
additive to existing files in place, plus one new gate script.

## Complexity Tracking

*No violations — this section intentionally left without rows.*
