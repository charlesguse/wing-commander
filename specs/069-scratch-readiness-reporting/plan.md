# Implementation Plan: A readiness verdict that is reachable and documentation that matches it

**Branch**: `spec/069-scratch-readiness-reporting` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/069-scratch-readiness-reporting/spec.md`

## Summary

Feature 053's readiness check folds "the checking credential cannot answer
this" into "not ready," which makes an all-clear verdict unreachable for
the `auto-release` profile through any route, and leaves four 053 documents
describing behavior a later amendment already removed. This feature makes
`checks.sh`'s `assemble_report` (the one existing home of readiness
computation, `.github/scripts/e2e-provisioning/checks.sh`) produce a
three-valued per-element outcome (`ready`/`missing`/`not_checkable`) and a
three-valued aggregate verdict (`all_clear`/`not_clear`/`unverified`, each
with its own exit status), narrows SC-001 to the profile that can actually
reach `all_clear`, corrects the 053 spec/plan/contracts/quickstart/adopter
docs that overstate what the tool does, fixes a misdiagnosed
repository-creation failure, and closes two test-coverage gaps a prior
review found but did not block on. No onboarding element is added, removed,
or renamed, and nothing provisioning writes to a target changes (FR-007).

## Technical Context

**Language/Version**: Bash (`set -uo pipefail`), matching every existing
file this feature touches; `jq` for JSON assembly (already a dependency of
`checks.sh`/`provision-e2e-target.sh`). Python 3 only for the existing gate
scripts this feature must keep passing (`verify-e2e-provisioning-single-home.py`);
no new Python is added.

**Primary Dependencies**: `gh` CLI (already required), `jq` (already
required). No new dependency.

**Storage**: N/A — every entity is re-derived live from the target's own
state on each invocation (unchanged from 053).

**Testing**: `.github/scripts/e2e-provisioning-tests/run-tests.sh` (the
existing `t1`-`t9` bash harness against `gh_stub.py`, wired into
`lint-workflows.yml`'s gate suite). This feature extends `t4_refuse_self.sh`
and `t9_maintainer_feedback.sh` and adds cases exercising the new tri-state
outcome and exit-code contract; it does not introduce a new test runner or
framework.

**Target Platform**: Linux runners (GitHub Actions `ubuntu-latest`) for the
dispatched route; any POSIX shell a maintainer runs locally for the local
route. Unchanged from 053.

**Project Type**: Single project — this repository's own `.github/scripts/`
tooling and `.github/workflows/` consuming-instrument workflow (Constitution
VII). No frontend/backend split.

**Performance Goals**: Unchanged from 053 (SC-006: ≤1 runner-minute, zero
Claude quota for the dispatched route). This feature adds no new `gh` calls
per element — it reclassifies outcomes already computed from calls the
existing checks already make.

**Constraints**: The onboarding-element list and `TargetProfile` mapping
must stay in their single home (`checks.sh`/`profiles.sh`) — Gate
`verify-e2e-provisioning-single-home.py` (Constitution VIII) fails a second,
independent copy of either. This feature adds no new element and no new
profile, so this gate's existing assertions are unaffected in shape; the
verdict-computation logic added by this feature belongs in `checks.sh`'s
`assemble_report` for the same single-home reason (research.md D1/D2).

**Scale/Scope**: Two scripts, one workflow, two test files (plus a possible
small addition to the `gh_stub.py`/`lib.sh` failure-injection seam for
FR-013's fixture), and the seven-document correction set User Story 2
names explicitly (053's `spec.md`, `plan.md`, `data-model.md`,
`quickstart.md`, `contracts/cli.md`, `contracts/readiness-workflow.md`, plus
`docs/setup.md` and `docs/adoption.md`). No new files beyond this feature's
own `specs/069-scratch-readiness-reporting/` artifacts.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **I. Guide**: This feature is built through the pipeline (spec → this
  plan → tasks → implement), same as 053 and its own review. PASS.
- **II. Cost-Conscious Model Tiering**: No agent/Claude invocation is part
  of this feature's shipped behavior — it is pure deterministic bash/doc
  changes. N/A (nothing to tier).
- **III. Simple, GitHub-Native Interaction**: Status is posted to lifecycle
  issue #516 at each stage, per the pipeline's own convention. PASS.
- **IV. Automation-First**: No new manual step is introduced;
  `app_installation` remains the sole `DeclaredManualStep` (FR-015/FR-016
  make the existing hint's use more visible, they do not add a step).
  PASS.
- **V. Security**: No change to any credential, token, or App permission
  (SC-007 — the App's Contents/Issues/Pull requests grant is explicitly
  unwidened). No new trust boundary. PASS.
- **VI. Portability**: Unaffected — this feature touches only this
  repository's own `.github/scripts` and `.github/workflows` tooling, none
  of it a published stage. PASS.
- **VII. Two Interfaces**: `provision-e2e-target.sh` and
  `auto-update-spec-kit-scratch-preflight.yml` are both consuming-instrument
  (already stated in 053's own `contracts/readiness-workflow.md`), so a
  breaking change to `ReadinessReport`'s JSON shape (research.md D4) is not
  a published-contract break. PASS.
- **VIII. A Green Check Means What It Says**: The three-valued verdict is
  the direct fix for a check that could not produce a signal a caller could
  honestly act on (the motivating defect). The new `unverified` exit status
  (`2`) is itself a new failure branch, and tasks.md (next stage) must give
  it a checked-in fixture in `t9_maintainer_feedback.sh` or a new test file,
  same as every other branch this suite already covers — noted so the tasks
  stage does not skip it. PASS (with that obligation carried forward).
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic Code**:
  The `ready`/`missing`/`not_checkable` classification and the
  `all_clear`/`not_clear`/`unverified` precedence are both plain,
  deterministic bash in `checks.sh` — no model judgment anywhere in this
  feature's shipped behavior. PASS.
- **X. Bounded Autonomy**: Not applicable to this feature directly (it is
  spec-shaped, already routed through the full lifecycle per issue #516's
  own filing, not the board loop). N/A.

No violations. No entries needed in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/069-scratch-readiness-reporting/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── contracts/
│   ├── readiness-report.schema.json   # Amends 053's schema (tri-state)
│   ├── cli.md                          # Amends 053's CLI exit-status contract
│   └── readiness-workflow.md           # Amends 053's job-summary contract
├── quickstart.md         # Phase 1 output
└── tasks.md              # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

No new directories. This feature edits files that already exist:

```text
.github/
├── scripts/
│   ├── e2e-provisioning/
│   │   ├── checks.sh          # Tri-state outcome + verdict computation (research.md D1/D2/D5/D8)
│   │   └── profiles.sh        # Unchanged
│   ├── provision-e2e-target.sh    # Exit codes 0/1/2 (D3); act_repository return-code check (D6)
│   └── e2e-provisioning-tests/
│       ├── t4_refuse_self.sh      # + FR-014 case (D7)
│       ├── t9_maintainer_feedback.sh  # + FR-013 case; FR-017 comment (D9)
│       ├── lib.sh / gh_stub.py    # + failure-injection seam for FR-013's fixture, if needed
│       └── run-tests.sh           # Unchanged (already runs every t*.sh)
└── workflows/
    └── auto-update-spec-kit-scratch-preflight.yml  # Job-summary rendering for 3 outcomes/verdicts

specs/053-e2e-scratch-provisioning/   # Amended in place (User Story 2, FR-008–012)
├── spec.md                           # Clarification-record wording (FR-009)
├── plan.md                           # Constraint wording (FR-009)
├── data-model.md                     # Read-call list + marker exemption (FR-011)
├── quickstart.md                     # auto-release walkthrough (FR-008)
└── contracts/
    ├── cli.md                        # Exit behavior + marker-refusal scope (FR-010)
    └── readiness-workflow.md         # (only if 053's copy needs a pointer to 069's amendment)

docs/
├── setup.md       # Convergence wording (FR-009) + hint documentation (FR-016)
└── adoption.md    # Convergence wording (FR-009)
```

**Structure Decision**: Single project, no new source directories. This is
a targeted correction of existing tooling and its governing documents, not
a new component — the "structure" this feature changes is entirely within
053's existing footprint plus this feature's own `specs/069-.../` planning
artifacts.

## Complexity Tracking

*No violations — table intentionally empty.*
