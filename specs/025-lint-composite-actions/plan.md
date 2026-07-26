# Implementation Plan: Lint Composite Action Scripts

**Branch**: `025-lint-composite-actions` | **Date**: 2026-07-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/025-lint-composite-actions/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

`.github/workflows/lint-workflows.yml`'s "Parse YAML and bash -n every run
block" step (issue #41) only globs `.github/workflows/*.yml` and only walks
each file's `jobs.*.steps` list, so the embedded shell scripts inside the six
composite actions under `.github/actions/**` (`wing-commander-preflight`,
`wing-commander-context`, `wing-commander-callout`, `wing-commander-lifecycle-gate`,
`wing-commander-bedrock-credentials`, `wing-commander-metrics-summary` — all
`using: composite`) go completely unchecked, and a pull request touching only
one of those files never triggers the guard at all (`on.pull_request.paths`
names only `.github/workflows/**`). The fix extends the existing check step,
in place, along two axes that must land together (spec User Stories 1 and 2):
(1) discovery walks `.github/actions/**/action.{yml,yaml}` recursively in
addition to `.github/workflows/*.yml`, extracting scripts from each
discovered composite action's `runs.steps` list using the same per-step
`run:`/expression-neutralization/`bash -n` logic already applied to workflow
job steps (FR-001, FR-003, FR-004, FR-008); (2) the workflow's
`on.pull_request.paths` filter gains `.github/actions/**` so a
composite-action-only change fires the guard (FR-002). A composite action
file that fails to parse as YAML fails the run with the same annotation shape
already used for a malformed workflow file (FR-009). No existing gate (1, 2,
or 3) changes behavior, and none of them touch composite actions — gates 2
and 3 are specific to workflow-to-workflow relationships (`workflow_run`
name resolution, reusable-workflow permission grants) that composite actions
do not participate in, matching the spec's Assumptions. The guard's own
header-comment documentation gains an explicit statement that the check is
syntax-only and does not exercise composite scripts' `errexit`/`pipefail`
runtime behavior (FR-006, User Story 3).

## Technical Context

**Language/Version**: Python 3 (inline `python3 - <<'PYEOF'` heredoc, matching the existing check step) + Bash (`bash -n`) + GitHub Actions workflow YAML — `ubuntu-latest` runner defaults, no version pin beyond what the runner image ships (unchanged from the existing step)

**Primary Dependencies**: `PyYAML` (`import yaml`, already used by all three existing gates in this file), Python's `glob`/`re`/`subprocess` standard-library modules, `bash` — no new dependency introduced

**Storage**: N/A — the check reads repository files in the checkout only; no database, no artifact persisted between runs

**Testing**: No unit-test framework for workflow YAML in this repo (dogfooding per constitution I, consistent with `specs/020-fix-watchdog/`). Verification is scenario-based: introduce a deliberate shell syntax error into a composite action's embedded script on a throwaway branch, open a pull request, and confirm the guard fails with an annotation naming the action file and step — see quickstart.md

**Target Platform**: GitHub Actions, `ubuntu-latest` runners, this repository's own `.github/workflows/lint-workflows.yml` (a repo-local check, not a published reusable stage — it has no `workflow_call` trigger and is not part of the `specs/010-reusable-pipeline/` thin-wrapper/reusable-stage split)

**Project Type**: Single project — a GitHub Actions guard workflow; no application `src/`/`tests/` split applies

**Performance Goals**: Not applicable in the spec's success criteria; the extension adds a bounded, one-time-per-run glob over six known composite-action files (a small, fixed set) to a job that already globs and syntax-checks every workflow file, so added runtime is not material

**Constraints**: Constitution II (no agent step, no model tier — the guard is pure deterministic static analysis, unchanged); Constitution V (least privilege — the `lint` job's `permissions: contents: read` is unchanged; the check only reads files already in the checkout); Constitution VI (the guard is this repository's own dogfooded artifact, not a published reusable component consumers adopt, so no portability contract applies beyond what already governs `lint-workflows.yml`); FR-007 (must not regress existing workflow-script coverage — the extension is additive to the existing discovery/check logic, not a rewrite)

**Scale/Scope**: This repository's `.github/actions/**` tree (currently six composite action definitions, all `using: composite`, all with embedded `run:` scripts) plus whatever composite actions are added later, discovered recursively at any depth (FR-008) — no fixed count is hardcoded

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — the repo is its own first example | Fix flows through spec → plan → tasks → implement → converge, against a real issue (#41) and a real lifecycle issue | PASS |
| II. Cost-conscious model tiering | No agent step is added or changed; the extended check is the same pure-Python/bash static analysis the existing gates already run, with no LLM call and therefore no tiering decision | PASS |
| III. Simple, GitHub-native interaction | Failures still surface as `::error` annotations on the pull request the same way the existing gates already report — no new external surface, no new comment channel | PASS |
| IV. Automation-first | The fix removes a silent gap (composite-action scripts and composite-action-only PRs bypassing the guard entirely) rather than introducing a new manual step; nothing about this change requires a human to do more | PASS |
| V. Security — untrusted content is never instructions | The extended discovery only reads files already present in the checkout (composite action YAML, which is repository-controlled content, not issue/comment/PR-body text); no new tool allowlist, no new write surface, `permissions: contents: read` unchanged | PASS |
| VI. Portability | `lint-workflows.yml` is this repository's own guard, not a published `<stage>.yml` reusable workflow consumers adopt (constitution VI's portability contract governs the published pipeline stages under `specs/010-reusable-pipeline/`); this change stays entirely inside that self-contained guard file plus its own header-comment documentation | PASS |

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/025-lint-composite-actions/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── lint-guard-delta.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This repository has no application `src/`/`tests/` split — it *is* a
GitHub Actions pipeline. The feature's changes are confined to:

```text
.github/workflows/
└── lint-workflows.yml        # "Parse YAML and bash -n every run block" step:
                               # extend discovery to .github/actions/**/action.{yml,yaml}
                               # (recursive), extract runs.steps in addition to
                               # jobs.*.steps, extend on.pull_request.paths to add
                               # ".github/actions/**"; header comment gains the
                               # syntax-only limitation statement (FR-006)

.github/actions/                     # unchanged — the six existing composite
├── wing-commander-preflight/         # actions become newly-covered input, not
├── wing-commander-context/           # modified targets; any composite action
├── wing-commander-callout/           # added here later is discovered
├── wing-commander-lifecycle-gate/    # automatically (FR-008), no lint-workflows.yml
├── wing-commander-bedrock-credentials/  # change required per new action
└── wing-commander-metrics-summary/

specs/025-lint-composite-actions/    # this feature's own spec-kit artifacts
```

**Structure Decision**: Single project, no option-1/2/3 split applies. Every
change lives inside the existing guard workflow file `lint-workflows.yml`;
the fix extends the existing "Parse YAML and bash -n every run block" step's
discovery and collection logic and the job's trigger `paths:` filter, rather
than adding a new job or a new file, keeping the single-source-of-truth
failure count and annotation format the spec's User Story 1 depends on.

## Complexity Tracking

> Not applicable — Constitution Check has no violations to justify.
