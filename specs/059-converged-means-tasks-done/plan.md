# Implementation Plan: Converged Means No Task Is Left — The Cycle Signal Reads tasks.md

**Branch**: `spec/059-converged-means-tasks-done` | **Date**: 2026-09-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/059-converged-means-tasks-done/spec.md`

## Summary

`implement.yml`'s two read-back steps ("Read back cycle outcome" and its
retry-arm twin) currently derive `converged` from one proxy — whether a
`converge:`-prefixed commit touching `tasks.md` landed in the cycle's commit
range — and never look at whether `tasks.md` still has unchecked boxes. This
plan replaces that proxy with a deterministic read of `tasks.md`'s checkbox
state at the cycle's pushed tip, gated by a progress test (checked-task count
rising against the cycle's own base) that tells "a later cycle will finish
this" apart from "no cycle ever will" (FR-010), so a healthy cycle that makes
no progress and lands no `converge:` commit hands off to finalize instead of
either looping to the cap or being reported converged. The approach factors
the checkbox count (already computed once, for a different purpose — the
truncated-cycle classification's Arm A) into one shared script + composite
action so the primary and retry arms consume one definition (FR-007), reuses
the existing cap-reached dispatch branch for the new zero-progress hand-off
(FR-010, no new dispatch mechanism), and rewrites the issue comment's
remaining-work text to be read from `tasks.md`'s tip rather than a converge
commit's diff, so it is never empty on the new no-converge-commit path
(FR-012).

## Technical Context

**Language/Version**: Bash (`set -uo pipefail`, GitHub Actions `shell: bash`), YAML (GitHub Actions workflow/composite-action syntax), Python 3 (gate scripts under `.github/scripts/`)

**Primary Dependencies**: GitHub Actions (`workflow_call` stage, composite actions), `git`, `awk`/`grep`, PyYAML (gate scripts), the repo's own `wc_shell_harness.py` and `wc_gate_registry.py` test/registration helpers

**Storage**: N/A — state lives in git (the spec branch's `tasks.md` and commit history) and `GITHUB_OUTPUT`/`GITHUB_STEP_SUMMARY`; no database

**Testing**: Deterministic Python gate scripts (`.github/scripts/verify-*.py`) that extract the shipped `run:` blocks by step name and execute them against synthetic git repos (`wc_shell_harness.py`), run locally via `python .github/scripts/run-local-gates.py` and in CI via `lint-workflows.yml`

**Target Platform**: GitHub Actions runners (`ubuntu-latest`), Linux bash

**Project Type**: CI/CD pipeline (GitHub Actions reusable workflows + composite actions) — not a library/service/app

**Performance Goals**: N/A — a handful of `git show`/`git log` invocations per cycle read-back; no throughput target

**Constraints**: Must not widen the `implement.yml` `workflow_call` input/output surface (FR-017, Principle VII); must not add a new `tasks.md` marker vocabulary or schema (FR-010, Out of Scope); the primary and retry arms must share one definition, never two copies (FR-007, CLAUDE.md "Shared logic has exactly one home"); a scan that cannot reach `tasks.md` must fail loudly, never resolve as converged (FR-006, Principle VIII)

**Scale/Scope**: Two call sites inside one workflow (`implement.yml`'s cycle and retry read-back arms), one new shared script, one new composite action, one new/extended gate script with fixtures for every FR-019 failure branch, and doc corrections in `implement.yml`'s header comments, both agent prompts, `docs/architecture.md`'s stage-4 section and risk table

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: N/A trigger — this is a bug fix to an existing published stage, not a new capability needing its own worked-example spec; the fix itself is delivered through the pipeline (this spec). **Pass.**
- **II. Cost-Conscious Model Tiering**: No new agent invocation is introduced; the fix is entirely deterministic shell/YAML plus a gate script. FR-011 explicitly forbids tightening the implement agent's prompt to change its behavior. **Pass, N/A.**
- **III. Simple, GitHub-Native Interaction**: FR-012/FR-013/FR-014 keep the lifecycle issue as the legible record of why a cycle did or didn't converge. **Pass.**
- **IV. Automation-First**: The fix removes a manual re-dispatch step (the owner's hand re-drive from the lifecycle issue) rather than adding one. **Pass.**
- **V. Security**: No change to trust boundaries, tool allowlists, or checkout refs. The new composite action reads only `tasks.md` already on the trusted spec branch. **Pass.**
- **VI. Portability**: The new composite action and shared script live under this repository's own `.github/actions/`; nothing is bundled from or resolved outside the consuming repository's checkout. **Pass.**
- **VII. Two Interfaces**: `implement.yml`'s `workflow_call` inputs/outputs are unchanged (FR-017). Adding a new non-underscore composite action (`wing-commander-tasks-checkbox-count`, resolved by `implement.yml` through self-checkout) **does** widen the published contract's action surface, the same way `wing-commander-spec-meta` did — that composite's own header comment records "adding it is a minor-version change at the next release." This plan carries the same note forward for the new composite; it is a deliberate, minor addition, not a breaking change. **Pass, with a recorded minor-surface addition** (see Complexity Tracking).
- **VIII. A Green Check Means What It Says**: The new/extended gate must be reachable through the registry, run the *shipped* `run:` blocks (not a copy), fail loudly when it can't reach its subject, and carry a fixture for every FR-019 branch plus a mutation battery per FR-020 — modeled directly on `verify-truncated-cycle-carry-forward.py`. **Pass by design; enforced at the tasks/implement stage.**
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic Code**: This is the spec's own thesis — the convergence signal, the progress test, and the hand-off decision move from an agent-observable proxy to deterministic code reading `tasks.md`. FR-003/FR-010a explicitly forbid reading the agent's message. **Pass.**
- **X. Bounded Autonomy**: N/A — this feature does not touch the board-loop merge gates. **Pass, N/A.**

No violations requiring justification beyond the recorded VII note above.

## Project Structure

### Documentation (this feature)

```text
specs/059-converged-means-tasks-done/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   └── convergence-signal.md   # Phase 1 output — the corrected decision contract
└── tasks.md              # Phase 2 output (/speckit-tasks — not produced here)
```

### Source Code (repository root)

This is a CI/CD pipeline repository, not an application; there is no `src/`.
The feature's real "source" is GitHub Actions workflow and composite-action
YAML plus Python gate scripts:

```text
.github/workflows/
├── implement.yml          # header comment (5-9, 1151-1164), both read-back
│                           # steps ("Read back cycle outcome" ~1180-1301,
│                           # "Read back retry outcome" ~1780-1861), both
│                           # agent prompts ("cycle" ~909-914, "retry"
│                           # ~1501-1506), "Consolidate final outcome"
│                           # (~1888-1949), "Dispatch next step" (~2498-2620)
└── lint-workflows.yml      # new/extended "Gate N — ..." registration

.github/actions/
├── _shared/
│   └── count-tasks-checkboxes.sh   # NEW — the one home of the checkbox read
└── wing-commander-tasks-checkbox-count/
    └── action.yml                  # NEW — the published front door composite

.github/scripts/
└── verify-tasks-checkbox-convergence-signal.py  # NEW gate script, following
                                                    # verify-truncated-cycle-
                                                    # carry-forward.py's
                                                    # extraction + synthetic-
                                                    # repo + mutation-battery
                                                    # pattern, sharing
                                                    # wc_shell_harness.py

docs/
└── architecture.md         # stage-4 section (467-500) and risk-table row
                             # (~1330) corrected per FR-015/FR-016
```

**Structure Decision**: Single-project CI pipeline layout already established
by this repository (`.github/workflows/`, `.github/actions/`,
`.github/scripts/`); this feature adds one shared script, one composite
action, and one gate script in the existing directories, and edits the
existing `implement.yml`/`docs/architecture.md` in place. No new top-level
directory is introduced.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|---------------------------------------|
| New published composite action `wing-commander-tasks-checkbox-count` widens Principle VII's action surface | FR-007 requires the primary and retry read-back arms to share one checkbox-counting definition; the existing sibling pattern (`wing-commander-spec-meta` / `_shared/read-spec-meta.sh`) is how this repository already gives a value shared across `implement.yml`'s own two arms one home, and Gate 61 already enforces that spec-meta reads have no second copy — the same shape of gate is planned here (FR-020, `verify-single-home-idioms.py`-style) | Keeping the counting logic as inline duplicated `grep`/`awk` in each arm was rejected outright by FR-007 and CLAUDE.md's "Shared logic has exactly one home"; a `_shared/`-only script with no composite front door was rejected because every existing `_shared/` script this repository has is reached by stage workflows only through a composite front door (the spec-meta comment: "stage workflows reach it only through the wing-commander-spec-meta composite... `_shared/` is not part of the adopter-pinned surface") — deviating from that would be the second inconsistent pattern, not a simplification |
