# Implementation Plan: Container-Mode Evidence in End-to-End Release Verification

**Branch**: `067-e2e-container-image-evidence` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/067-e2e-container-image-evidence/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

A container-mode turn of `auto-release.yml`'s end-to-end verification can
reach a `pass` today without the test repository ever having run inside a
container — an unset or drifted `WING_COMMANDER_CONTAINER_IMAGE` on the test
repository produces no objection, because nothing reads that variable or the
run's own job data before writing the verdict. This plan adds two evidence
reads, both using the fixture maintainer credential `specs/055` already
validates and containment-checks: a cheap pre-kickoff read of the test
repository's container image variable, compared against this repository's
own pin, and a pre-pass read of the completed run's Actions job data
confirming the stage jobs actually executed inside a container. Either read
failing, being absent, or being unreadable routes to the existing
`fail-infra` outcome with a new `failing_check` value naming which of the
six FR-005 cases occurred, never a silently downgraded pass. A new gate
(FR-015) proves the poll step's one `pass`-writing call site cannot be
reached without both evidence reads succeeding, with a fixture for every
failure branch. Default-runner turns are untouched.

## Technical Context

**Language/Version**: Bash (workflow steps, `_shared/` decision scripts), Python 3 (gate script + self-test, matching the existing `verify-gate-*.py` convention)

**Primary Dependencies**: `gh` CLI (`gh api`, `gh variable list`), `jq`, the GitHub Actions REST Jobs API (`GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs`), this repository's own `wc_shell_harness.py` (executes a shipped workflow step's shell verbatim under stubs, for the new gate)

**Storage**: N/A — the evidence observations are carried in step outputs and the existing end-to-end verdict (an issue comment / job output), never persisted separately

**Testing**: Gate self-test scripts (`verify-gate-N-selftest.py` or an inline `--self-test`), run through `.github/scripts/run-local-gates.py`; the new gate itself executes the shipped `poll`/evidence steps' shell against synthetic fixtures rather than mocking the logic it checks (Gate 52/64's idiom)

**Target Platform**: GitHub Actions, `ubuntu-latest` runners (the wrapper layer; no change to the published stage workflows' own container jobs)

**Project Type**: CI/CD wrapper workflow (this repository's own "consuming instrument," Constitution VII) — no application source tree

**Performance Goals**: The evidence reads add a small, constant number of API calls per container-mode turn (spec Assumptions); the configuration half MUST complete, and be able to fail, before the kickoff issue is created (FR-011, SC-003)

**Constraints**: No new App installation permission, on this repository or the test repository (FR-003); no write to the test repository's container image configuration (FR-003); the maintainer credential's validity and containment MUST be (re)confirmed the way `auto-release.yml`'s existing `maintainer-credential` step already does, not assumed (FR-014)

**Scale/Scope**: One workflow (`.github/workflows/auto-release.yml`), one new `_shared/` decision script, one new gate + self-test + fixtures, five documentation/spec sites carrying the accepted-gap language (FR-016)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: Satisfied. This feature is specified, planned, and will be implemented through the pipeline itself, against a real lifecycle issue (#509) and a real prior spec (`specs/054-e2e-container-coverage`) it amends.
- **II. Cost-Conscious Model Tiering**: N/A — this feature adds no new Claude/agent invocation. All evidence reads and the new gate are deterministic shell/Python; no model call is introduced.
- **III. Simple, GitHub-Native Interaction**: N/A — no end-user-facing interaction changes; the audience is the maintainer reading `auto-release.yml`'s run report, unchanged in kind from today.
- **IV. Automation-First**: Satisfied. No new manual step. The one prerequisite (`WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN`/`_USERNAME`) already exists from `specs/055`; this feature reads more with it, it does not ask a maintainer to do anything new.
- **V. Security**: Satisfied. The evidence reads are the verification's own `gh api`/`gh variable` calls, not agent-interpreted content; nothing from the test repository's issue/comment bodies is treated as instructions. No new secret is introduced. The credential stays a classic PAT per `specs/055`'s already-accepted exception — this plan does not widen it.
- **VI. Portability**: N/A — this feature lives entirely in `auto-release.yml`, this repository's own wrapper, not in anything a consuming repository inherits.
- **VII. Two Interfaces**: Satisfied. `auto-release.yml` is a wrapper (it already reads `vars.WING_COMMANDER_AUTO_RELEASE_E2E_CONTAINER_PAUSED` directly, which a published stage workflow may not do), so this change stays inside the consuming-instrument layer and touches no `workflow_call` stage contract or composite-action input/output surface. No registered exception is needed.
- **VIII. A Green Check Means What It Says**: This is the principle FR-015's new gate exists to serve, and the gate design (research.md D7) is held to its five requirements explicitly: reachable through the gate registry and `run-local-gates.py`; executes the same shipped step shell locally and in CI (not a reimplementation); triggered by changes to `auto-release.yml` and the new `_shared/` decision script; fails loudly (not vacuously) if it cannot locate the step or call site it checks; not suppressible by an unrelated gate; every FR-005 failure branch gets a checked-in fixture (SC-006).
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic Code**: Satisfied by construction — the not-configured/drift/unexecuted/unreadable classification is a pure decision script (research.md D5/D6), never a prompt. No agent is involved anywhere in this feature.
- **X. Bounded Autonomy**: N/A — this feature is not board-loop related; it is a normal spec-lifecycle feature.

No violations. Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/067-e2e-container-image-evidence/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   ├── container-evidence-outcomes.md
│   └── container-evidence-decision-script.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   └── auto-release.yml
│       # NEW step "Read container-mode configuration evidence" (id:
│       # container-evidence-config), gated on mode == container, placed
│       # immediately after the existing "maintainer-credential" step and
│       # before "cleanup"/"reset"/"speckit-version"/"scaffold" -- so an
│       # unconfigured turn fails before the fixture is even pushed, not
│       # just before the kickoff issue (FR-011, SC-003).
│       # NEW read inside the existing "poll" step, immediately before the
│       # single "pass"-writing write_verdict call (currently line ~1338):
│       # confirms the run's stage jobs executed inside a container
│       # (FR-006's execution half) before that call is allowed to run.
├── actions/
│   └── _shared/
│       ├── auto-release-verdict.sh                        # UNCHANGED (existing 8-arg verdict shape; no new fields)
│       └── auto-release-container-evidence-decision.sh     # NEW: pure decision script (research.md D5/D6)
├── scripts/
│   ├── e2e-provisioning/
│   │   └── checks.sh                 # EXTENDED OR REUSED: this_repo_container_image()/check_container_image_pin() consumed, not re-derived (research.md D3; CLAUDE.md single-home rule)
│   ├── verify-gate-<N>.py            # NEW gate for FR-015 (research.md D7; number confirmed at implement time against lint-workflows.yml)
│   └── verify-gate-<N>-selftest.py   # NEW
docs/
├── setup.md                          # FR-016: replace the known-limitation sentence at the WING_COMMANDER_AUTO_RELEASE_E2E_REPO row
└── architecture.md                   # FR-016: replace the "Reporting" bullet's open-gap narration in the container-mode leg section
specs/054-e2e-container-coverage/
├── spec.md                           # FR-016: FR-004/FR-006 accepted-gap notes replaced by a pointer to this feature
└── contracts/e2e-container-coverage.md   # FR-016: §1's accepted-gap section replaced by a pointer to this feature's contract
```

**Structure Decision**: This is a CI/CD wrapper-layer feature with no application `src/`/`tests/` tree; the "single project" is this repository's own consuming-instrument layer (Constitution VII). All new logic lives in `.github/workflows/auto-release.yml`, one new `_shared/` decision script, and one new gate; existing provisioning-script comparison logic is reused rather than duplicated per CLAUDE.md's "Shared logic has exactly one home" rule.

## Complexity Tracking

*No violations — table intentionally omitted.*
