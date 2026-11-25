# Implementation Plan: Faster PR Lint — Parallelise the Gate Suite in CI

**Branch**: `spec/129-parallel-pr-lint` | **Date**: 2026-11-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/129-parallel-pr-lint/spec.md`

**Layer**: consuming instrument (constitution VII). No `workflow_call` input, secret or output changes (FR-010).

## Summary

Split the 291-step `lint` job of `.github/workflows/lint-workflows.yml` into N shard jobs (`lint-shard-1` … `lint-shard-8`), each keeping every gate as its own step, beside the existing `harness-tests` job. A new thin job named `lint` (the only check-run with that name) `needs:` every shard and `harness-tests`, runs under `always()` on `pull_request` only, and fails unless every needed job's result is exactly `success`. The job layout is the single record of gate-to-shard assignment; `pr_time_gates` already derives the gate set from the workflow's `run:` text, so `run-local-gates.py` follows with no edit. New deterministic gates enforce the layout invariants (every PR-time job is a unit under the aggregate; no gate in two units; step names unique; every non-setup step survives an unrelated failure; aggregate never skips on a unit failure). Restructure-sensitive gates are adapted in the same PR. Target: aggregate verdict ≤ 10 min (about 2263 s summed gate time over 8 shards ≈ 283 s each plus ~1 min setup, floor 156 s for Gate 97's self-test).

## Technical Context

**Language/Version**: GitHub Actions YAML; Python 3 gate scripts (`.github/scripts/verify-*.py`); bash.

**Primary Dependencies**: PyYAML, existing `wc_gate_registry.py`, `wc_lint_gate_source.py`, `wc_gha_expr.py`, `run-local-gates.py`.

**Storage**: N/A (the workflow file is the only record of the assignment).

**Testing**: each new or changed gate ships `--self-test` with checked-in fixtures for every failure branch (constitution VIII); full suite via `python .github/scripts/run-local-gates.py`.

**Target Platform**: `ubuntu-latest` GitHub-hosted runners (free minutes on a public repo).

**Project Type**: CI workflow / gate tooling.

**Performance Goals**: aggregate `lint` completes ≤ 10 min wall-clock for each of the first ten green first-attempt PR runs (SC-001).

**Constraints**: aggregate stays in `lint-workflows.yml`, workflow name `lint · workflows`, job name `lint`; each gate its own step; no separate assignment table; shards must not suppress each other.

**Scale/Scope**: 294 gates, ~2263 s summed, 8 shards + `harness tests` + aggregate.

No NEEDS CLARIFICATION remain; plan-level choices are in [research.md](research.md).

## Constitution Check

*Gate before research; re-checked after design.*

| Principle | Result |
|---|---|
| I Guide | Pass — built through the pipeline. |
| II Model tiering | Pass — no agent invocation added. |
| III GitHub-native | Pass — failed unit named on the aggregate's output and summary. |
| IV Automation-first | Pass. |
| V Security | Pass — no new permissions (`contents: read`), trusted refs only, no secrets. |
| VI Portability | Pass — repo-specific workflow only; nothing bundled. |
| VII Two interfaces | Pass — wrapper-layer file only; published stage workflows untouched. |
| VIII Green check means what it says | Pass by design — FR-004/FR-009 are the principle's own rules: aggregate cannot go green by omission, an unrelated failure cannot suppress a gate, new gates have self-tests, restructure-sensitive gates cannot pass vacuously. |
| IX Deterministic judgment | Pass — aggregate verdict is a deterministic `needs.*.result` check. |
| X Bounded autonomy | Pass — gate suite must still run green on the exact SHA; the `lint` check name that merge gates read is preserved. Workflow-touching PR: merge needs `workflow` scope (hand to maintainer). |

Post-design re-check: no violations; Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/129-parallel-pr-lint/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── lint-workflow-layout.md
└── tasks.md             # /speckit-tasks output
```

### Source Code (repository root)

```text
.github/workflows/lint-workflows.yml        # lint job → lint-shard-1..8 + aggregate `lint`
.github/scripts/verify-lint-shard-layout.py # NEW gate: units, aggregate needs, no duplicate step names/gates, FR-009 guards
.github/scripts/verify-lint-aggregate.py    # NEW gate: aggregate conclusion simulation (success/failure/cancelled/skipped/in-progress; PR vs push/schedule/dispatch)
.github/scripts/run-local-gates.py          # derivation check vs CI union (FR-005); aggregate exempt by name
.github/scripts/wc_gate_registry.py         # pr_time_gates: exclude aggregate job `lint` from gate set
.github/scripts/verify-gate-*.py            # adapt those reading `jobs.lint` structure / byte-compared comments
docs/reference.md                           # FR-011
```

**Structure Decision**: single workflow file with sharded jobs; layout is the sole assignment record.

## Complexity Tracking

None.
