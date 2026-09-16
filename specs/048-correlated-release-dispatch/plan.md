# Implementation Plan: Correlated, atomic release dispatch

**Branch**: `048-correlated-release-dispatch` | **Date**: 2026-09-14 | **Spec**: [specs/048-correlated-release-dispatch/spec.md](./spec.md)

**Input**: Feature specification from `/specs/048-correlated-release-dispatch/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

`auto-release.yml` currently finds "its" `release.yml` run by listing
the newest run on `main`, and only compares the verified head against
the branch tip once, before dispatching — leaving a window where a
merge lands between that check and `release.yml`'s own checkout. This
plan closes both seams by making the handover carry evidence instead of
assumption: `release.yml` gains two optional `workflow_dispatch` inputs
(`attempt-token`, `commit`), titles its run with the version and the
token via a new `run-name:`, and refuses to create any tag unless a
live, tag-time re-read of the branch tip still equals the requested
commit. `auto-release.yml` selects its own run by matching that title's
token *and* a time bound, and — independent of which run it finds or
whether release.yml's own run conclusion was green — decides whether a
release happened by reading tag state alone: the exact version tag
exists and points at the verified commit. A new deterministic gate
(`verify-correlated-release-dispatch.py`) keeps both guarantees from
regressing quietly. The manual release path gains no new required
input and no new gate (both new inputs default to `""`, reproducing
today's behavior exactly).

## Technical Context

**Language/Version**: Bash (`run:` steps in GitHub Actions workflows), Python 3 (gate scripts under `.github/scripts`, matching the rest of the repository's gate suite)

**Primary Dependencies**: GitHub Actions (`workflow_dispatch` inputs, `run-name:`, `concurrency`), the GitHub CLI (`gh run list`, `gh workflow run`), `git` (`ls-remote`, `rev-parse`, `fetch` of a single tag ref)

**Storage**: N/A — all state is git refs (tags, `refs/heads/main`) and one workflow run's own job outputs; nothing is persisted to `specs/`, a branch, or a database (consistent with specs/045's "End-to-end verdict" precedent)

**Testing**: Gate scripts' own `--self-test` mode against in-memory fixtures (the established pattern: Gate 50 `verify-release-contract.py`, Gate 51 `verify-rate-limited-exemption.py`), run via `python .github/scripts/run-local-gates.py`; no application-level test framework exists in this repository for workflow YAML itself — correctness of the runtime behavior (the poll loop, the tag-time refusal) is validated by the quickstart's manual dispatch scenarios, since the subject is cross-workflow coordination in GitHub's own Actions infrastructure and cannot be meaningfully unit-tested in isolation

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), this repository only

**Project Type**: CI/CD workflow automation — two existing `workflow_dispatch`/`schedule` workflows (`release.yml`, `auto-release.yml`) and one new gate script; no application code, no `src/`/`tests/` tree

**Performance Goals**: N/A — correctness- and latency-bound (the correlation poll and the end-to-end run's own timeout), not throughput-bound; at most one `auto-release.yml` attempt and one `release.yml` run each run at a time under their existing concurrency groups

**Constraints**: Must add zero new required inputs and zero new gates to the manual release path (FR-015–FR-017, SC-003); the tag-time refusal must be evaluated live at the moment the tag would be created, not at request or checkout time (FR-010a); the correlation waiting period is an explicitly non-load-bearing tuning knob (research.md D9) — the tag-state check must reach the right answer even if it elapses

**Scale/Scope**: Two workflow files modified (`release.yml`, `auto-release.yml`), one new gate script, one new `lint-workflows.yml` PR-time step (Gate 52 at plan time)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Guide | This feature is itself flowing through the pipeline (spec 048, issue #324) — no exception needed. |
| II. Cost-Conscious Model Tiering | N/A — this feature adds no Claude agent step to either workflow; everything is `bash`/`git`/`gh`. Nothing here touches an existing agent step's `--model`/`--max-turns` declaration. |
| III. Simple, GitHub-Native Interaction | Unchanged: the only maintainer-facing surface remains the `auto-release:failed` issue and `release.yml`'s own run summary — no new dashboard or CLI. |
| IV. Automation-First | Preserved by construction: the manual path (Story 3) gains no new required step, per FR-015–FR-017; every new mechanism is internal to the two existing workflows. |
| V. Security | No new secret, no new trust boundary. `attempt-token`/`commit` are values the dispatching workflow itself constructs (`github.run_id`, its own verified-head output) — never derived from issue/comment/PR text — so there is no injection surface distinct from what `dispatch-release` already handles today with `github.token`. |
| VI. Portability | N/A — `release.yml`/`auto-release.yml` are this repository's own consuming-instrument workflows (no `workflow_call` trigger), not part of the published, adopter-facing contract; this was already true before this feature (research.md D6). |
| VII. Two Interfaces | Confirmed neither touched file is a published stage (no `workflow_call`), so Gate 50/31's published-stage invariants do not apply and this feature does not need to satisfy them — verified directly against `wc_published_stages()`'s derivation logic in research.md D6. |
| VIII. A Green Check Means What It Says | Directly implemented by the new Gate 52 (research.md D7, `contracts/regression-gate.md`): reachable through the gate registry (`lint-workflows.yml` → `run-local-gates.py`), triggered by changes to the two files it checks, each of its five checks has a named mutation it must fail on, exercised by its own `--self-test` fixtures per Gate 50's established shape. |
| IX. Judgment That Gates a Durable Action Belongs in Deterministic Code | Directly the shape of this feature's two P1 guarantees: "which run is ours" (a durable report/issue-closing decision) is a textual token+time comparison, never an agent's or a workflow's own narration; "did a release happen" (closes the standing failure issue) is a `git rev-parse` tag comparison, never a run's `conclusion` field treated as ground truth. Both are called out explicitly in research.md D3/D5. |

No violations. Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/048-correlated-release-dispatch/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── release-handover-contract.md   # FR-019's single canonical contract doc
│   └── regression-gate.md             # FR-018's deterministic gate, Gate 52
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This repository has no `src`/`tests` application tree — it is a
GitHub Actions pipeline whose "source" is workflow YAML and the Python
gate scripts that lint it. This feature's changes are confined to:

```text
.github/
├── workflows/
│   ├── release.yml         # + run-name:, attempt-token/commit inputs, tag-time refusal step
│   ├── auto-release.yml    # dispatch-release: token minting, correlation search, tag-state outcome; report: new outcome rows
│   └── lint-workflows.yml  # + Gate 52 step (registration + --self-test), immediately after Gate 51
└── scripts/
    └── verify-correlated-release-dispatch.py   # new — Gate 52's implementation and --self-test
```

**Structure Decision**: No new project, directory, or layer is
introduced. This is a two-file behavioral change to existing
`workflow_dispatch`/`schedule` workflows plus one new gate script,
following the exact shape of every prior gate in `.github/scripts/`
(Gate 50, Gate 51) and registered the same way (`lint-workflows.yml`,
auto-picked-up by `run-local-gates.py`). `specs/045-auto-release-verified-head/`'s
own artifacts are left in place and cross-referenced, not duplicated —
see research.md D8.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

None — the Constitution Check above found no violations.
