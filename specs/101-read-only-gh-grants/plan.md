# Implementation Plan: Read-Only Agents Hold No Write-Capable `gh` Grant

**Branch**: `101-read-only-gh-grants` | **Date**: 2026-10-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/101-read-only-gh-grants/spec.md`

## Summary

Remove every `gh` grant from the two read-only agents that hold one
(`watchdog.diagnose`: `Bash(gh:*)`; `auto-update-spec-kit.yml` "Decide upgrade
path": `Bash(gh api:*)`), replace diagnose's lost job-log route with a
deterministic staging step (one shared fetch helper, `github.token`, fail
loud), and extend Gate 93 check 4b so a `gh` grant on any read-only agent step
in any workflow fails the PR-time suite, with fixtures and mutation
self-test. Correct the docs and live contracts that teach the old grant, with
one canonical rationale home.

Technical approach is in [research.md](research.md); interfaces in
[contracts/](contracts/).

## Technical Context

**Language/Version**: Python 3 (gate scripts, `-I` where run on untrusted trees), bash (workflow `run:` steps, `_shared` helpers), GitHub Actions YAML

**Primary Dependencies**: PyYAML (already used by Gate 93), `gh` CLI and `jq` in the runner container, `anthropics/claude-code-action@v1`

**Storage**: Files only: staged logs and failure markers under `$RUNNER_TEMP`

**Testing**: Gate 93 `--self-test` (fixtures plus mutation check against real workflows), `python .github/scripts/run-local-gates.py`, one post-merge re-driven watchdog run and one auto-update evaluation (spec SC-004/SC-005)

**Target Platform**: GitHub Actions runners with caller-supplied container images

**Project Type**: CI/CD pipeline repository (workflows, composite actions, verify scripts)

**Performance Goals**: N/A. Log staging must stay inside diagnose's 20-minute job bound; it fetches only failed jobs' logs

**Constraints**: No App-token widening; no new numbered gate unless 4b cannot host the rule; published-contract surface (Principle VII) unchanged; shared logic has one home (CLAUDE.md)

**Scale/Scope**: 2 workflows edited for grants, 1 gate extended, 1 shared helper, about 6 docs/contracts corrected

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1.*

| Principle | Assessment |
|-----------|------------|
| I Guide | Built through the pipeline; spec 101 is the worked example. Pass |
| II Model tiering | No model change. Pass |
| III GitHub-native | Gather failures surface in the verdict and on the lifecycle issue. Pass |
| IV Automation-first | No new manual step. Pass |
| V Security (NON-NEGOTIABLE) | Narrows least-privilege for two prompt-injection surfaces; staged logs are framed as untrusted data. Pass |
| VI Portability | Rule binds shipped defaults only; no hardcoded repo names. Pass |
| VII Two interfaces | Tool lists are internal defaults; no workflow_call input/output/secret added or removed. The shared helper lives in underscore-prefixed `_shared/`. Pass |
| VIII Green check | Extends a registered gate; fixtures for every failure branch; zero-site and missing-label failures; mutation self-test. Pass |
| IX Deterministic judgment | Staging and failure recording are code; the agent only reports what it could not see. Pass |
| X Bounded autonomy | Touches `.github/workflows/` so the merge needs the `workflow` scope handoff; not a constitution change. Pass |

Post-design re-check: unchanged. Pass, no Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/101-read-only-gh-grants/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── gate-93-check-4c.md
│   └── diagnose-staged-logs.md
└── tasks.md             # /speckit-tasks, not created here
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   ├── watchdog.yml                      # diagnose grant + prompt; new staging step; collect-step-summary uses shared helper
│   └── auto-update-spec-kit.yml          # "Decide upgrade path" grant + prompt
├── actions/_shared/
│   └── fetch-job-logs.sh                 # NEW: the one job-log fetch (loud on failure)
└── scripts/
    ├── verify-issue-context-single-home.py   # check 4b gains the gh rule, fixtures, mutations
    └── (waiver register entry for classify, see research D4)
docs/agent-friendly-workflows.md          # read-only example + canonical rationale home
specs/010-reusable-pipeline/contracts/stage-interfaces.md
specs/015-pipeline-watchdog/contracts/watchdog-workflow.md
specs/027-auto-update-spec-kit/contracts/auto-update-spec-kit-workflow.md
specs/051-read-only-inspection-policy/contracts/inspection-policy.md
```

**Structure Decision**: Extend existing files; one new `_shared` shell helper. No new gate number (spec Assumption; confirmed in research D1).

## Complexity Tracking

None.
