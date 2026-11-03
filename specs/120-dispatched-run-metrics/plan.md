# Implementation Plan: Prompt Metrics Records for Pipeline-Dispatched Runs

**Branch**: `120-dispatched-run-metrics` (persistent: `spec/120-dispatched-run-metrics`) | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/120-dispatched-run-metrics/spec.md`

## Summary

Runs dispatched with `github.token` never fire the metrics `workflow_run`
trigger. Rather than change dispatch (the App has no Actions permission), each
implement and finalize run persists its own records in a last job,
`persist-metrics`, in the two wrappers. The job calls the existing
`metrics-persist.yml` stage with the run's own id, gated by `always()` plus a
"something started" clause, with no App credentials and outside the per-spec
concurrency group. Two optional stage inputs (`run-in-cancelled-run`,
`tolerate-failure`, both default `false`) let the stage run in a cancelled run
and never fail the origin run. The record-key idempotence already dedups
against the `workflow_run` path and the sweep; re-run key stability is tested
first and fixed in the derivation if needed. The rollup gains a "last sweep"
line. Gate 79 is extended to hold the job's shape. See [research.md](research.md).

## Technical Context

**Language/Version**: GitHub Actions YAML (workflows, composite action), Bash and jq in `run:` steps, Python 3 for `verify-*.py` gates

**Primary Dependencies**: existing `metrics-persist.yml` stage and `wing-commander-metrics-persist` composite; Actions REST API (jobs, artifacts)

**Storage**: `records.jsonl` and `sweep-state.json` on the metrics branch (unchanged format)

**Testing**: `python .github/scripts/run-local-gates.py`; fixture-backed gate checks (Gate 79 extension); composite fixture test for re-run key stability; post-merge drills (quickstart.md)

**Target Platform**: GitHub Actions hosted/caller-supplied runners, including caller container images

**Project Type**: CI/CD pipeline (workflows + composite actions)

**Performance Goals**: SC-001 — ≥95% of runs persisted within 15 minutes

**Constraints**: one added job (+ image check when configured) per run (SC-004); no dispatch-token change (FR-010); additive optional stage inputs only (VII); no copied persistence logic; persisting job never fails the origin run (FR-007)

**Scale/Scope**: 2 wrappers, 1 stage, 1 composite, 1 gate script, 3 live contract docs

## Constitution Check

*Pre-design and post-design: PASS, no violations.*

- I Guide: built through the pipeline; the flow itself is the worked example.
- II Tiering: no agent step is added.
- III GitHub-native: rollup comment is the surface.
- V Security: no new token; persisting job holds the existing persist-path permissions and no App secret; no untrusted content is interpreted.
- VI Portability: destination stays in wrappers/vars; nothing hardcoded.
- VII Two interfaces: stage gains only optional, defaulted inputs (and at most one optional output); wrappers own `vars.*`, kill switch and destination. Underscore dirs untouched.
- VIII Green check: Gate 79 extended with a fixture per failure branch; gate registered and path-triggered.
- IX Deterministic: all gating is code, no prompt.
- X Bounded autonomy: workflow change is spec-shaped and goes through the lifecycle; proof after merge by re-driven runs.

## Project Structure

### Documentation (this feature)

```text
specs/120-dispatched-run-metrics/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── persisting-job.md
└── tasks.md             # tasks stage
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   ├── wing-commander-5-implement.yml      # + persist-metrics job
│   ├── wing-commander-6-finalize.yml       # + persist-metrics job
│   ├── metrics-persist.yml                 # + run-in-cancelled-run, tolerate-failure
│   ├── finalize.yml                        # + `started` output (only if drill D2 requires)
│   └── lint-workflows.yml                  # gate wiring touch only if paths change
├── actions/wing-commander-metrics-persist/
│   └── action.yml                          # rollup sweep line; re-run key fix if R6 fails
└── scripts/
    └── verify-metrics-wrapper-trigger-drops-watchdog.py   # Gate 79 extended + fixtures
specs/043-durable-metrics-record/contracts/{persist-workflow,wrapper-contract}.md   # amended
specs/058-per-job-minute-floor/contracts/metrics-persist-sweep-delta.md             # amended
```

**Structure Decision**: wrapper-side job reusing the published stage; no new
workflow, composite or gate script.

## Complexity Tracking

No constitution violations. Two known, stated exceptions, not violations:
SC-001 for the `stalled`-behind-next-cycle case (research R4), and the possible
finalize fallback to the zero-record no-op for queued cancels (R2).
