# Implementation Plan: Auto-Release After Merged Features Pass a Scheduled End-to-End Verification

**Branch**: `045-auto-release-verified-head` | **Date**: 2026-09-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/045-auto-release-verified-head/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Add one new, self-contained scheduled workflow, `.github/workflows/auto-release.yml`,
that closes the gap between "merged to `main`" and "released": on a fixed
daily cron (plus on-demand `workflow_dispatch`), it detects whether `main`
carries commits its latest release tag does not (a single `git tag
--points-at HEAD` read does double duty as both the no-op check and the
"already released this head" guard — Constitution IX, no extra state); if
so, it drives a real, deliberately trivial feature through the full
intake→cleanup lifecycle against a dedicated, maintainer-owned,
adopter-shaped end-to-end test repository (named by a new repository
variable, never created or deleted by this feature, its default branch
force-reset each run because GitHub only evaluates `issues:`-triggered
workflows from a repository's default branch); reads a deterministic
pass/fail verdict from that repository's own lifecycle-issue state,
labels, and merged artifacts — never from agent narration; computes the
next patch-or-minor version from the latest release tag and a fixed
opt-in PR label; and, only on a passing verdict, dispatches the existing
`release.yml` (`gh workflow run`, unmodified, always non-breaking) to cut
the actual release. Failures leave the current tag untouched and file or
update one durable, deduplicated issue on this repository naming what
failed. A repository-variable kill switch, checked job-level, stops the
whole thing from starting.

This plan makes no change to `release.yml`'s interface, to any published
stage's interface, or to any adopter-facing artifact — it is entirely new,
repository-specific automation, in the same category as
`auto-update-spec-kit.yml` and `watchdog.yml`.

## Technical Context

**Language/Version**: GitHub Actions workflow YAML + POSIX shell (`bash`), consistent with every other workflow in this repository; no application language is introduced.

**Primary Dependencies**: `gh` CLI (issue/PR/label/tag/workflow-run operations), `git` (tag/log/branch operations), `actions/create-github-app-token@v3` (scoped test-repository token, research.md D11), the existing composite actions `wing-commander-context` (this job's own primary token) and `wing-commander-turn-ceiling` is **not** needed here (this feature invokes no Claude agent step of its own — every agent turn happens inside the test repository's own stages, under its own configuration, per research.md D11).

**Storage**: None. All state is git tags (release history), GitHub issue state/labels (both the test repository's lifecycle issue and this repository's `auto-release:failed` issue), and one job's outputs passed to the next within a single run. No database, no file-based ledger.

**Testing**: `python .github/scripts/run-local-gates.py` (unchanged gate suite — this feature introduces no new `.github/scripts/verify-*.py` gate; see research.md D15) plus the manual `quickstart.md` scenarios run against a real test repository, since a scheduled workflow with live GitHub-side polling cannot be meaningfully unit-tested in isolation. The `review-step-gating` skill (per CLAUDE.md) is required at implementation time given the number of gated (`if:`) steps this design implies.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners, matching every other workflow here).

**Project Type**: CI/CD automation within an existing GitHub Actions-based pipeline repository — no new service, library, or application component.

**Performance Goals**: The no-op path (Scenario 1, most ticks) must invoke zero agent steps and touch zero external state (SC-005) — a `detect` job that is a few `git`/`gh` reads. The verification path is bounded by the job's own `timeout-minutes` (an implementation-time constant, not a new repository-variable knob — consistent with FR-002's own reasoning against adding configuration surface that rarely moves); it must be generous enough for eight real stages of a single-file fixture to converge in one iteration but does not need to be tuned in this plan.

**Constraints**: Constitution IX (the release decision reads a concrete verdict, never judgment — research.md D10, data-model.md's verdict schema); Constitution VII (this workflow deliberately opts out of the stage/wrapper split — research.md D1 — because it has no ambient event to translate and is not adopter-facing); zero new repository-administration permissions (SC-010); zero artifacts of the end-to-end run reaching this repository's own `specs/` tree, pushed branches, or PRs (FR-013); the automatic path must be mechanically incapable of requesting a breaking release (FR-018/FR-019 — `breaking: false` is a hardcoded literal, not a computed value, at the one call site that dispatches `release.yml`).

**Scale/Scope**: One new workflow file; two new repository variables (`WING_COMMANDER_AUTO_RELEASE_PAUSED`, `WING_COMMANDER_AUTO_RELEASE_E2E_REPO`); two new fixed label names (`release:minor` on this repository, `auto-release:failed` on this repository); one new one-time maintainer setup procedure for the test repository (documented in `quickstart.md`, mechanically identical to onboarding any adopter per `docs/adoption.md`); zero changes to `release.yml`, zero changes to any published stage.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Guide — the repo is its own first example | This feature is itself being built through the pipeline (spec 045, lifecycle issue #296). Once shipped, it is also the mechanism that releases every future feature built the same way. Pass. |
| II. Cost-Conscious Model Tiering | `auto-release.yml` invokes no Claude agent step directly — every agent turn in a verification attempt runs inside the test repository's own stages, under that repository's own model/turn-budget configuration (already governed by this same principle, unchanged by this feature). N/A for this workflow's own steps; pass by inheritance for the stages it triggers. |
| III. Simple, GitHub-Native Interaction | Reporting is entirely GitHub-native: a job summary and a durable, labeled issue on this repository (data-model.md "Failure report"), no external dashboard. Pass. |
| IV. Automation-First | Fully automated after one-time maintainer setup of the test repository (unavoidable — something must be the pre-created, credentialed target, per FR-009); that manual step is documented explicitly in `quickstart.md`, never silently assumed. Pass. |
| V. Security — untrusted content is never instructions (NON-NEGOTIABLE) | The trivial feature's issue body is fixed, repository-authored text, not user input (research.md D9) — no untrusted content reaches an agent as instructions. The minor-vs-patch decision reads a maintainer-applied **label**, never PR title/body prose (research.md D5) — the one place this feature could have been tempted to parse free text, and it deliberately doesn't. The scoped test-repository token holds Contents + Issues only, never Administration (research.md D11, SC-010). Pass. |
| VI. Portability | This feature touches nothing an adopting repository owns or reads — it is wholly this repository's own release mechanics. Pass (trivially — no adopter-facing surface exists here to violate). |
| VII. Two Interfaces | Deliberately not split into a published stage + wrapper (research.md D1) — `auto-release.yml` declares no `workflow_call`, matching `release.yml`'s own precedent for a workflow with no ambient event to translate and no adopter consumer. Documented as a decision, not an oversight. Pass. |
| VIII. A Green Check Means What It Says | The verdict-reading step (research.md D10) fails loudly (`fail-infra`) rather than silently passing when the test repository is unreachable (FR-011) — it never reports a pass it did not earn. Every `fail-*` branch needs a checked-in fixture demonstration at implementation time (flagged in research.md D15 for the tasks stage — this plan does not itself satisfy VIII, it hands the obligation forward explicitly). |
| IX. Judgment That Gates a Durable Action Belongs in Deterministic Code | This is the principle this feature is built around: the release decision reads a JSON verdict object (data-model.md) computed from GitHub issue state, labels, and artifact presence — never from an agent's claim of success (research.md D10). The version bump reads a label, not model judgment. `breaking` is a hardcoded literal. Pass — centrally. |

No violations requiring justification. Complexity Tracking is empty below.

## Project Structure

### Documentation (this feature)

```text
specs/045-auto-release-verified-head/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── auto-release-workflow.md
│   ├── e2e-repository-wiring.md
│   └── release-dispatch.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This repository has no `src/`/`tests/` application layout — it is itself
a GitHub Actions pipeline; "source" is workflow YAML plus a small set of
Python/shell gate scripts. This feature's implementation footprint:

```text
.github/
└── workflows/
    └── auto-release.yml         # New. Single self-contained workflow (research.md D1) —
                                  # schedule + workflow_dispatch trigger, job-level pause
                                  # gate, detect → verify-e2e → decide-version →
                                  # dispatch-release → report jobs (contracts/auto-release-workflow.md)

docs/
├── setup.md                     # Touched: document the two new repository variables
│                                 # (WING_COMMANDER_AUTO_RELEASE_PAUSED,
│                                 # WING_COMMANDER_AUTO_RELEASE_E2E_REPO) alongside the
│                                 # existing watchdog/auto-updater pause-switch rows and
│                                 # the auto-updater's scratch-repo row
└── adoption.md                  # Not touched — this feature adds no adopter-facing surface

.github/scripts/
└── (no new file expected — research.md D15: this feature's deterministic
    checks are inline workflow steps reading a live run's state, the same
    shape auto-update-spec-kit.yml's own readback checks take, not a
    property of the workflow files themselves, which is what the
    verify-*.py gate family checks)
```

No `.github/actions/` composite is added — research.md D11/D13 found the
existing `wing-commander-context` (primary token) and a directly-minted
`actions/create-github-app-token@v3` step (scoped test-repository token,
matching `auto-update-spec-kit.yml`'s own `scratch-token` step) sufficient;
`wing-commander-callout` was considered and rejected for the failure
report (research.md D13 — it is scoped to an existing spec's lifecycle
issue, which an auto-release attempt does not have).

**Structure Decision**: One new top-level workflow file
(`.github/workflows/auto-release.yml`), no new composite action, no new
gate script, one documentation touch-up (`docs/setup.md`'s variable
table). This is the minimum footprint the spec's own scope implies:
everything else this feature needs (the scratch-repository reset
technique, the `gh workflow run` dispatch idiom, the durable-issue dedup
pattern) already exists as prior art to be followed inline, not factored,
per this repository's own "shared logic has exactly one home" rule
applying only once a second call site actually appears — none of these
techniques currently has a second consumer inside this feature that would
justify extracting a new composite action ahead of need.

## Complexity Tracking

*No entries — Constitution Check above recorded no violations requiring justification.*
