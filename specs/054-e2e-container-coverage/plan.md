# Implementation Plan: Container-Mode Coverage in End-to-End Release Verification

**Branch**: `054-e2e-container-coverage` | **Date**: 2026-09-17 | **Spec**: [specs/054-e2e-container-coverage/spec.md](./spec.md)

**Input**: Feature specification from `/specs/054-e2e-container-coverage/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

The scheduled `auto-release.yml` end-to-end verification only ever exercises
stage jobs on a bare runner, so the `container:` code path every published
stage carries (shell resolution, the image-prerequisite check, the
registry-credential binding) is never dogfooded end to end — a regression
there would first surface on an adopter's own runner. This feature adds a
container-mode leg to `verify-e2e` that alternates with the existing
default-runner leg on a per-scheduled-run basis (derived statelessly from
calendar-date parity, research.md D1), pins a new minimal project-owned
reference image published to `ghcr.io/charlesguse/wing-commander-e2e-image`
(research.md D5), and records which mode each run exercised in its verdict
and report (research.md D9) so a pass can never overstate coverage. The
technical approach reuses the published stage contract's existing
`container-image`/registry-credential passthrough verbatim (research.md D2)
— every published stage already forwards these inputs — so no stage
workflow or composite action changes; the only touched surface is
`auto-release.yml` itself (the consuming instrument, Constitution VII), a
new image build/publish workflow, a new gate, and documentation.

## Technical Context

**Language/Version**: Bash (`set -uo pipefail`) + `jq` for verdict
construction, matching every existing step in `auto-release.yml`; Python 3
for the new gate script, matching every existing `verify-*.py` gate.

**Primary Dependencies**: `gh` CLI, `docker` (build + run, both already
available on `ubuntu-latest`), `actions/create-github-app-token@v3`,
`docker/build-push-action` + `docker/login-action` for the new publish
workflow (standard GitHub Actions building blocks; not previously used in
this repository, since no Dockerfile/publish workflow exists yet — see
research.md D5).

**Storage**: N/A — no new persisted state (research.md D1 deliberately
avoids any stored rotation counter).

**Testing**: This repository's existing gate suite
(`.github/scripts/run-local-gates.py`, `lint-workflows.yml`), plus a
checked-in fixture proving the new Gate 62's failure branch (Constitution
VIII), plus the live proof required by SC-002 (a deliberately broken
container-path head observed to block a real scheduled/dispatched run).

**Target Platform**: GitHub Actions (`ubuntu-latest` runners; the container
leg additionally targets whatever platform the published reference image is
built for — linux/amd64, matching `ubuntu-latest`).

**Project Type**: GitHub Actions reusable-workflow pipeline (existing
project type; no new project category introduced).

**Performance Goals**: N/A (no request-rate or latency target; the relevant
bound is wall clock, see Constraints).

**Constraints**: A verification run in either mode MUST complete within
`verify-e2e`'s existing 150-minute job timeout (SC-005) — unchanged by this
feature, since alternation (not concurrent execution of both legs) keeps
per-run cost at today's single-leg level (research.md D8: the container
leg's added image-pull time is absorbed by the existing poll budget, not a
new one).

**Scale/Scope**: One new workflow (image build/publish), one new Dockerfile,
one new gate script, targeted edits to `auto-release.yml` and three docs
files. No published stage workflow or composite action changes (research.md
D2's zero-stage-contract-change finding).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide — the repo is its own first example**: satisfied by
  construction — this feature *is* wing-commander dogfooding its own
  container-mode code path through its own pipeline; no separate example is
  needed.
- **II. Cost-conscious model tiering**: not implicated. This feature changes
  which environment a stage's jobs execute in, not the stage chain's agent
  steps or their model choice; no new Claude invocation is introduced.
- **III. Simple, GitHub-native interaction**: not implicated — this is a
  maintainer-facing operational change (a repository variable, a scheduled
  workflow), not a requester-facing interaction surface.
- **IV. Automation-first**: satisfied — FR-015 requires reaching
  container-mode coverage without a manual step per run; the one remaining
  manual step (setting the test repository's `WING_COMMANDER_CONTAINER_IMAGE`
  and copying a new digest into it after a rebuild) is a one-time/occasional
  maintainer action, explicitly reported rather than silently assumed
  (Principle IV's own escape hatch), and documented in docs/setup.md.
- **V. Security — untrusted content is never instructions**: not implicated
  — no new issue/comment-driven trigger is added; the new build/publish
  workflow triggers only on `push`/`workflow_dispatch` against paths this
  repository's own maintainers control.
- **VI. Portability**: satisfied — nothing in this feature is bundled with
  or resolved from an adopting repository; the reference image and its
  build definition live in this repository only, consumed solely by this
  repository's own `auto-release.yml` (FR-013's explicit non-adopter-use
  statement is the same boundary this principle already draws).
- **VII. Two interfaces**: this is the central design constraint the plan
  satisfies by construction (research.md D2) — the published contract
  (`container-image`/registry-credential inputs on every stage) is reused
  unchanged; every new or changed file lives in the consuming-instrument
  layer (`auto-release.yml`, the new build/publish workflow, docs). No
  registered exception is needed because no stage deviates.
- **VIII. A green check means what it says**: directly motivates D6/Gate 62
  (a textual-only check, like Gate 23, could not fail if the Dockerfile
  stopped installing a required tool; Gate 62 builds and inspects the real
  image) and D9 (a container leg that silently ran on a bare runner must be
  reported as a failure of the leg, not a pass — FR-004).
- **IX. Judgment gating a durable action belongs in deterministic code**:
  satisfied — mode selection (D1), the pause check (D3), and
  infrastructure-vs-pipeline failure classification (FR-006, already the
  existing verdict step pattern) are all plain shell/jq, not agent
  judgment; no new agent step is introduced by this feature at all.

**Initial gate result**: PASS, no violations. Re-checked after Phase 1 design
below.

**Post-Phase-1 re-check**: PASS — Phase 1 design (data-model.md, contracts/,
quickstart.md) introduces no new stage-contract surface, no new agent step,
and no new persisted state; the Constitution Check above holds unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/054-e2e-container-coverage/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── e2e-container-coverage.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This repository is a GitHub Actions reusable-workflow pipeline, not an
application with a src/tests split; "source" is workflow YAML, composite
actions, and the Python gate scripts that check them. This feature's touched
paths:

```text
.github/
├── workflows/
│   ├── auto-release.yml                       # MODIFIED: mode step, scaffold's
│   │                                           #   off-turn sed, verdict schema,
│   │                                           #   report body (research.md D1-D3, D9)
│   ├── wing-commander-e2e-reference-image.yml  # NEW: build + publish the reference
│   │                                           #   image to ghcr.io (research.md D5)
│   └── lint-workflows.yml                      # MODIFIED: register Gate 62
├── docker/
│   └── e2e-reference-image/
│       └── Dockerfile                          # NEW: minimal image satisfying
│                                                #   required-tools.txt (research.md D5)
└── scripts/
    ├── verify-gate-62.py                       # NEW: image tool set vs.
    │                                            #   required-tools.txt (research.md D6)
    └── required-tools.txt                      # UNCHANGED (existing canonical source
                                                  #   the Dockerfile and Gate 62 both read)

docs/
├── setup.md          # MODIFIED: new pause-control variable row; note that the
│                      #   test repository's existing container-image variable
│                      #   now also configures the auto-release container leg
├── adoption.md        # MODIFIED: new subsection under "Runners and container
│                      #   images" stating the reference image's provenance (FR-013)
└── architecture.md    # MODIFIED: short addition describing the alternating leg
```

No published stage workflow (`intake.yml` … `cleanup.yml`, `rebase.yml`) and
no `.github/actions/**` composite action changes — research.md D2 establishes
that the existing `container-image`/registry-credential passthrough those
already carry is the entire mechanism the container leg needs.

**Structure Decision**: single-project GitHub Actions pipeline (no
frontend/backend or mobile split applies). All new/changed files are grouped
under `.github/` (workflows, one new Dockerfile, one new gate script) and
`docs/`, matching the repository's existing layout exactly — no new
top-level directory is introduced.

## Complexity Tracking

*No Constitution Check violations — this section is intentionally empty.*
