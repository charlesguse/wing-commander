# Implementation Plan: Fix the Watchdog — Restore Reliable Run Inspection

**Branch**: `020-fix-watchdog` | **Date**: 2026-07-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/020-fix-watchdog/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

The watchdog (`specs/015-pipeline-watchdog/`) is reported not working: the
automatic per-stage trigger produced a job/step failure and the inspected run
never got a verdict (issue #96, clarified Q1:A/Q2:A/Q3:C). Static analysis of
`.github/workflows/watchdog.yml` (research.md) finds the mechanism: the
`collect` job's non-collector steps (checkout, pipeline-ref resolution,
preflight, GitHub App token minting, and — most exposed — `gh run view` in
"Fetch inspected run metadata", which runs under `set -euo pipefail` with no
`continue-on-error`) have no failure boundary. If any of them fails for any
reason, the `collect` job fails outright; because `diagnose`/`triage`/`act`
all depend on `collect` succeeding, GitHub Actions skips every downstream job,
and the workflow ends with a red X and **zero** comments anywhere — exactly
FR-002's forbidden outcome and the reported symptom. The fix adds a
workflow-level safety net (a final `report-unhandled-failure` job, `if:
always()`, watching every other job's `result`) that guarantees a verdict —
specifically a "could not inspect" report carrying the failing job's name and
a link to its logs — is posted even when a step fails in a way none of the
existing per-source error handling anticipated. This is deliberately a
structural fix (one new job) rather than a pile of per-step patches, so it
also satisfies FR-008's "broader hardening" scope: it catches this reported
failure mode and any future one shaped the same way, without re-litigating
`specs/015-pipeline-watchdog/`'s detection, triage, or guardrail logic.

## Technical Context

**Language/Version**: Bash (workflow `run:` steps, `ubuntu-latest` default shell) + GitHub Actions workflow YAML

**Primary Dependencies**: `gh` (GitHub CLI), `jq`, `anthropics/claude-code-action@v1`, `actions/checkout@v4`, `actions/upload-artifact@v4` / `download-artifact@v4` — all already in use by `watchdog.yml`; no new dependency introduced

**Storage**: N/A — state lives in GitHub Issues/comments/labels and workflow artifacts (job-to-job handoff only); no database

**Testing**: No unit-test framework for workflow YAML in this repo (dogfooding per constitution I). Verification is: (a) re-triggering real workflow runs in each of the three invocation contexts (automatic per-stage, manual `workflow_dispatch`, self-inspection) and reading the posted verdict, and (b) fault-injecting a step failure to prove the new safety net fires — see quickstart.md

**Target Platform**: GitHub Actions, `ubuntu-latest` runners, this repository's own Actions environment (and any adopting repository that calls the reusable `watchdog.yml`)

**Project Type**: Single project — a GitHub Actions reusable-workflow pipeline component; no application `src/`/`tests/` split applies

**Performance Goals**: SC-006 — median time from a stage run finishing to its watchdog verdict appearing where the maintainer looks stays under 10 minutes (unchanged from `specs/015-pipeline-watchdog/`; the fix adds one short deterministic job, not an agent step, so it does not materially add latency)

**Constraints**: Constitution V (least privilege, untrusted content never instructions, no tool-allowlist broadening); Constitution II (no new model tier introduced — the safety net is deterministic, no LLM call); Constitution VI (fix stays inside the reusable stage, no repo-specific hardcoding)

**Scale/Scope**: This repository's own dogfooded pipeline usage, plus any adopting repository consuming `watchdog.yml` as a reusable workflow (per Constitution VI, the fix is repo-name-agnostic)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — the repo is its own first example | Fix flows through spec → plan → tasks → implement → converge, against a real issue (#96) and a real lifecycle issue | PASS |
| II. Cost-conscious model tiering | No new agent step or model tier introduced; `diagnose` stays `claude-haiku-4-5`, `propose-fix` stays `claude-sonnet-5`; the new safety-net job is pure deterministic bash, no LLM call, no tiering decision needed | PASS |
| III. Simple, GitHub-native interaction | Verdict still lands only on the lifecycle issue or the run's own summary — no new external surface | PASS |
| IV. Automation-first | The fix is itself automation: it removes the one surviving *silent* manual-diagnosis step (a maintainer digging through Actions logs) and replaces it with an explicit report, which is exactly what this principle requires of any manual step that survives | PASS |
| V. Security — untrusted content is never instructions | The safety-net job reads only `needs.*.result` (a workflow-engine-computed keyword, never user-influenced text) and job names/URLs it already trusts; no new tool allowlist broadening, no new web tool, no new write surface beyond the existing lifecycle-issue comment / run-summary path | PASS |
| VI. Portability | Change is confined to `watchdog.yml` (the published, reusable stage) and `docs/architecture.md`; no repository name/owner hardcoded; `wing-commander-8-watchdog.yml` (the thin wrapper) is expected to need no change | PASS |

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/020-fix-watchdog/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── watchdog-workflow-delta.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This repository has no application `src/`/`tests/` split — it *is* a
GitHub Actions pipeline. The feature's changes are confined to:

```text
.github/workflows/
├── watchdog.yml                     # reusable stage — collect job hardening +
│                                     # new report-unhandled-failure safety-net job
└── wing-commander-8-watchdog.yml    # thin wrapper — not expected to change
                                      # (trigger contract is unaffected)

.specify/memory/
└── watchdog-guardrails.json         # unchanged — read-only from this stage

docs/
└── architecture.md                  # Stage 9 — Watchdog section: document the
                                      # new safety-net job in the job list

specs/015-pipeline-watchdog/          # unchanged — remains the source of truth
                                      # for design; this feature only restores
                                      # behavior it already specifies
specs/020-fix-watchdog/               # this feature's own spec-kit artifacts
```

**Structure Decision**: Single project, no option-1/2/3 split applies. Every
change lives inside the existing reusable workflow file `watchdog.yml`; the
fix is additive (one new job, tightened error handling in one existing job)
rather than a restructuring, consistent with the spec's assumption that
`specs/015-pipeline-watchdog/` remains the source of truth for design.

## Complexity Tracking

> Not applicable — Constitution Check has no violations to justify.
