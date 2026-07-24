# Implementation Plan: Configurable Branch Prefixes & Consumer-Modifiable Naming

**Branch**: `spec/018-configurable-branch-prefixes` | **Date**: 2026-07-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/018-configurable-branch-prefixes/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Nine `.github/workflows/*.yml` files (the eight published reusable stages
plus `watchdog.yml`) hardcode five pipeline-owned branch-name prefixes
(`spec-draft/`, `spec/`, `plan/`, `tasks/`, `impl/`) as literal strings —
both at the CREATE sites (`git checkout -b`, `git push`) and the LOCATE
sites (`startsWith()` trigger guards, `${VAR#prefix}` slug stripping,
`gh pr list --head`, `git ls-remote` globs, `case` classifiers). Consumers
whose repositories enforce their own branch-naming convention cannot adopt
the pipeline without editing its internal stage logic, which the constitution
(Principle VI) says they should never need to do.

The approach reuses, verbatim, the configuration mechanism specs
014 (`configurable-gates`) and 017 (`parameterize-hardcoded-models`) already
established and validated: five new repository variables
(`WING_COMMANDER_{SPEC_DRAFT,SPEC,PLAN,TASKS,IMPL}_PREFIX`), each wired
through a new `workflow_call` input on the stage(s) that create or locate
that branch type, resolved by this repo's own thin wrapper workflows via the
existing `${{ vars.X || 'default' }}` idiom (or, for `watchdog.yml`, its
existing direct-`vars.*`-read exception). No stage's default branch name
changes, so every existing adopter sees identical behavior with zero
configuration (FR-005, User Story 2). A new `branch-prefixes` input on the
shared `wing-commander-preflight` composite adds one deterministic,
non-agent validation check — empty/illegal-character/collision — invoked by
the three CREATE-capable stages (`intake`, `plan`, `tasks`) so a bad value
fails the run before any branch is created (FR-010), diverging deliberately
from 014's fail-open gate-mode pattern because no safe default substitute
exists for a colliding prefix (research.md D4).

## Technical Context

**Language/Version**: GitHub Actions workflow YAML (`workflow_call` reusable
workflows) + POSIX `bash` steps; no application language — this is CI/CD
infrastructure, matching every other spec in this repo.

**Primary Dependencies**: `anthropics/claude-code-action` (agent invocation,
unaffected by this feature), `gh` CLI (branch/PR discovery and mutation —
`ls-remote`, `pr list --head`, `pr create --head`), `actionlint` (CI lint
gate in `release.yml`), the existing `wing-commander-preflight` composite
action (gains one new input/check).

**Storage**: N/A — configuration lives in GitHub repository Variables
(`vars.*`) and `workflow_call` input defaults; no database or file-based
store (research.md D1 rejects a checked-in naming-config file in favor of
the existing repo-variable mechanism).

**Testing**: This repo has no unit-test suite for workflows; correctness is
validated by (a) `actionlint` + the grep-based "published-stage invariant"
gate in `release.yml` (Gate 1b, unchanged by this feature — it already
forbids `vars.*` reads in the 8 reusable stages, which this feature's design
respects by construction), and (b) dogfooded live runs of the pipeline
against its own issues (constitution I). `quickstart.md` documents the
manual/CI validation scenarios that stand in for tests here, consistent with
how specs 016/017/014 were validated.

**Target Platform**: GitHub Actions (ubuntu-latest runners), consumed both by
this repo (dogfooded, local `uses: ./...` paths) and by adopting repositories
(pinned `uses: owner/repo/.github/workflows/*.yml@ref`).

**Project Type**: Single project — reusable GitHub Actions workflow library
plus this repo's own thin wrapper workflows that dogfood it (constitution I,
VI). No frontend/backend split.

**Performance Goals**: N/A — no latency/throughput target; the change is a
routing/configuration change, not a hot path. The new preflight check is a
single bash pass over at most five short strings, negligible relative to
existing preflight checks.

**Constraints**: Must not change any default branch name (FR-005); must not
introduce a `vars.*` read inside the 8 CI-gated reusable stage workflows
(`intake`, `clarify`, `plan`, `tasks`, `implement`, `finalize`, `cleanup`,
`rebase` — `release.yml` Gate 1b greps these and fails the build on any
`vars\.` match; `watchdog.yml` keeps its pre-existing documented exception);
every prefix used in a CREATE or LOCATE operation must resolve from a
declared input, never a literal (contracts/branch-prefix-override-points.md);
an invalid/colliding prefix must fail the run before any branch is created,
not after (FR-010).

**Scale/Scope**: 5 branch-type prefixes; ~9 hardcoded literal sites across 9
workflow files (`intake`, `clarify`, `plan`, `tasks`, `finalize`, `cleanup`,
`rebase`, `implement`, `watchdog`); 5 new repository variables; 1 new input +
1 new check on `wing-commander-preflight`; wiring touches all 9
`wing-commander-*.yml` wrapper files. Full location list and current
defaults are in `research.md` and `contracts/branch-prefix-override-points.md`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: Satisfied — this feature is itself spec 018 flowing through
  the pipeline's own stages, and its change is entirely to this repo's own
  workflow files (the worked example other adopters copy).
- **II. Cost-Conscious Model Tiering**: Not implicated — this feature adds no
  new agent step and changes no model selection; the one new check
  (`wing-commander-preflight`'s `branch-prefixes` validation) is
  deterministic bash, not an agent call, consistent with "agent cost only
  where an agent is genuinely needed."
- **III. Simple, GitHub-Native Interaction**: Satisfied — overrides are
  ordinary repository Variables (Settings → Variables), the same surface
  `WING_COMMANDER_PLAN_REVIEW`/`WING_COMMANDER_IMPLEMENT_MODEL` already use;
  no new dashboard or CLI. A misconfigured prefix is reported the same way
  every other preflight failure already is: `::error::` + step summary,
  visible from the run the requester (or maintainer) is already watching.
- **IV. Automation-First**: Satisfied — no new manual step; existing
  wrapper-to-reusable-workflow wiring is extended, not replaced. The one new
  failure mode (invalid/colliding prefix) is reported automatically, same as
  every other preflight check.
- **V. Security**: Satisfied — no change to trust boundaries, label gating,
  or checkout refs; branch-prefix strings are configuration values consumed
  only as git ref components and workflow input strings, never as agent
  instructions or executable content, and flow through the same
  `with:`/`vars.` paths already reviewed for models and gate modes. The new
  validation check is itself a hardening: it rejects characters that could
  otherwise let a malformed prefix behave unexpectedly in a `case`/glob
  match.
- **VI. Portability**: Directly reinforced — this is the constitution's own
  worked concern (Principle VI's adoption contract) receiving its first
  configurable-naming feature; a consuming repository's naming preference
  becomes something it owns via its own repository variables, never a value
  baked into the published reusable workflows. New inputs get defaults that
  reproduce current behavior, so existing adopters' checkouts keep working
  unmodified.

**Result**: PASS. No violations to record in Complexity Tracking.

*Post-Phase-1 re-check*: PASS, unchanged — Phase 1 design (data-model.md,
contracts/branch-prefix-override-points.md) introduces no new agent step, no
new trust boundary, and no default-value change; it only names and documents
the override points and the one new deterministic validation check designed
above. The constitution's own Operational Constraints line (branch
conventions) is updated for wording accuracy (research.md, Discoverability
decision) as a PATCH-level clarification, not a principle change, so it does
not itself trigger a fresh Constitution Check gate.

## Project Structure

### Documentation (this feature)

```text
specs/018-configurable-branch-prefixes/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── branch-prefix-override-points.md   # Phase 1 output (/speckit-plan command)
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── actions/
│   └── wing-commander-preflight/
│       └── action.yml                    # + branch-prefixes input; + emptiness/shape/collision check block
├── workflows/
│   ├── intake.yml                        # + spec-draft-prefix (CREATE) + 4 validation-only prefix inputs
│   ├── clarify.yml                       # + spec-draft-prefix (LOCATE: checkout ref)
│   ├── plan.yml                          # + spec-draft-prefix (LOCATE) + spec-prefix, plan-prefix (CREATE) + 2 validation-only inputs
│   ├── tasks.yml                         # + spec-prefix, plan-prefix (LOCATE) + tasks-prefix (CREATE/LOCATE) + 2 validation-only inputs
│   ├── implement.yml                     # + spec-prefix (LOCATE only; no branch-topology change)
│   ├── finalize.yml                      # + spec-prefix (LOCATE)
│   ├── rebase.yml                        # + spec-prefix (LOCATE)
│   ├── cleanup.yml                       # + all 5 prefix inputs (LOCATE + DELETE)
│   ├── watchdog.yml                      # + direct vars.WING_COMMANDER_*_PREFIX reads (existing exception), no new inputs
│   ├── release.yml                       # Gate 1b unchanged — new vars.* reads land only in wrapper files + watchdog.yml, outside its grep scope
│   ├── wing-commander-1-intake.yml       # + 5 vars.WING_COMMANDER_*_PREFIX wirings
│   ├── wing-commander-2-clarify.yml      # + vars.WING_COMMANDER_SPEC_DRAFT_PREFIX wiring
│   ├── wing-commander-3-plan.yml         # + 5 vars.WING_COMMANDER_*_PREFIX wirings
│   ├── wing-commander-4-tasks.yml        # + 5 vars.WING_COMMANDER_*_PREFIX wirings
│   ├── wing-commander-5-implement.yml    # + vars.WING_COMMANDER_SPEC_PREFIX wiring
│   ├── wing-commander-6-finalize.yml     # + vars.WING_COMMANDER_SPEC_PREFIX wiring
│   ├── wing-commander-7-cleanup.yml      # + 5 vars.WING_COMMANDER_*_PREFIX wirings
│   └── wing-commander-rebase.yml         # + vars.WING_COMMANDER_SPEC_PREFIX wiring
docs/
├── setup.md                              # Repository variables table: + 5 new rows
├── adoption.md                           # "shared artifact contract" sentence + per-stage Side effects cells reworded to configurable-with-default
└── architecture.md                       # Branches bullet + cleanup/watchdog sections reworded to configurable-with-default
specs/010-reusable-pipeline/
└── contracts/stage-interfaces.md         # Universal Behavior bullet reworded; new Common Inputs row for the CREATE-stage prefix inputs
.specify/memory/
└── constitution.md                       # Operational Constraints branch-conventions line reworded (adds missing tasks/ prefix, notes consumer-configurability); PATCH version bump + Sync Impact Report
```

**Structure Decision**: Single project, no new directories. Every change is a
targeted edit to existing `.github/workflows/*.yml` files (reusable stages
gain declared prefix inputs per `contracts/branch-prefix-override-points.md`;
the shared `wing-commander-preflight` composite gains one validation input;
this repo's own thin wrappers gain `vars.*` wiring mirroring the existing
`WING_COMMANDER_IMPLEMENT_MODEL`/`WING_COMMANDER_PLAN_REVIEW` pattern) plus
documentation updates to the four files (`docs/setup.md`,
`docs/adoption.md`, `docs/architecture.md`,
`specs/010-reusable-pipeline/contracts/stage-interfaces.md`) and one
constitution wording fix that together are FR-006/FR-007's single
discoverable-configuration surface. (Per the pipeline orchestrator's stated
constraint for this plan stage, none of the files in this section are edited
now — this section documents the touch-set `tasks.md`/implementation will
act on; only files under `specs/018-configurable-branch-prefixes/` are
written by this plan.)

## Complexity Tracking

*No Constitution Check violations — table intentionally omitted.*
