# Implementation Plan: A Fold Report Credits Only Its Own Run — Run-Scoped Fold Evidence

**Branch**: `spec/075-run-scoped-fold-evidence` | **Date**: 2026-09-26 | **Spec**: [specs/075-run-scoped-fold-evidence/spec.md](./spec.md)

**Input**: Feature specification from `/specs/075-run-scoped-fold-evidence/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

`pr-conversation.yml`'s `dispatch-once` and `report-fold-outcomes` jobs both
decide what a review folded by grepping `fold(<leg-id>): <summary>` commits
over the unscoped range `BASE_SHA..TIP_SHA`. Because leg ids restart at
`leg-0` in every run and two stage-9 runs can legitimately overlap on one
PR (#560's resolution), one run's range can contain another run's fold
commit under the same id — silencing exactly the case the report exists to
catch (a leg cancelled before it folded anything, credited with a sibling
run's commit). This plan makes fold evidence self-identifying: a
deterministic git hook, installed by the `act` job before each leg's agent
step runs (never an instruction the agent itself must remember), appends a
`Wing-Commander-Run-Id: <github.run_id>` trailer to every commit made in
that leg's checkout. A new composite action,
`.github/actions/wing-commander-fold-evidence`, becomes the one place both
downstream jobs read "which fold commits, in this range, are this run's
own" — replacing the two copies of the unscoped grep. `dispatch-once`'s
dispatch decision and fold list, and `report-fold-outcomes`'s per-leg
cross-check, both narrow to that same run-scoped evidence; the outcome
vocabulary, the job-conclusion read (including the #417 caller-prefixed
job-name fix), and the concurrency model are all unchanged. Coverage lands
as an extension of the existing Gate 34 (`verify-fold-dispatch-once.py`),
not a new gate, per the spec's own single-home requirement.

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps) and YAML workflow
definitions; Python 3 for the gate script (`verify-fold-dispatch-once.py`).

**Primary Dependencies**: GitHub Actions (`actions/checkout@v5`, the `gh`
CLI, `jq`), this repository's existing `wc_shell_harness.py`/
`wc_gate_registry.py` gate-testing infrastructure, `anthropics/claude-code-action@v1`
(unchanged — the agent's prompt and tool grants are not modified by this
feature).

**Storage**: N/A — every entity is a git commit, a job/step output, or a PR
comment (data-model.md).

**Testing**: `.github/scripts/verify-fold-dispatch-once.py` (Gate 34),
extended with new scenarios and one new mutation; `python
.github/scripts/run-local-gates.py` for the full PR-time gate suite.

**Target Platform**: GitHub Actions (`ubuntu`-hosted runners), this
repository's own `pr-conversation.yml` reusable stage workflow.

**Project Type**: CI/CD pipeline workflow (GitHub Actions reusable
workflows + composite actions) — not an application with its own
build/deploy target.

**Performance Goals**: N/A — no latency/throughput target; the fold-
evidence read is a bounded `git log`/`git show` pass over one review's
commit range, same order of magnitude as today's single grep.

**Constraints**: Must not add, remove, or rename any `pr-conversation.yml`
`workflow_call` input/output/secret (Constitution VII); must not change the
outcome vocabulary, the job-conclusion read, or the concurrency model
(Out of Scope); must not serialize stage 9 per PR (FR-006).

**Scale/Scope**: One reusable workflow (`pr-conversation.yml`), one new
composite action, one extended gate script and its fixtures. No other
stage workflow is touched.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is worked through the pipeline itself (issue
  #565 → this spec branch), consistent with prior spec-042/spec-056 work on
  the same file. Pass.
- **II. Cost-Conscious Model Tiering**: No new agent invocation is added;
  the existing `act` job's agent step is unchanged (its prompt and tool
  grants are untouched — the attribution hook is deterministic code, not a
  model call). Pass.
- **III. Simple, GitHub-Native Interaction**: The declined-dispatch notice
  (FR-015) and the narrowed fold list (FR-008) both improve, not regress,
  legibility from the PR alone — the explicit goal of this feature. Pass.
- **IV. Automation-First**: No new manual step. Pass.
- **V. Security**: No change to trust boundaries — issue/comment bodies
  remain data, not instructions; the attribution mechanism is deliberately
  *not* an instruction to the agent (research.md D1), which is itself a
  hardening against a prompt-injected `--no-verify` or similar bypass
  falling back to the safe "not this run's evidence" direction (FR-007)
  rather than misattribution. Pass.
- **VI. Portability**: No hardcoded repository name/owner is introduced;
  the new composite action reads `github.run_id`/`github.repository`
  ambiently, same as existing composites. Pass.
- **VII. Two Interfaces**: No `workflow_call` input/output/secret changes
  (data-model.md §7). The new composite action joins the published surface
  under `.github/actions/` (not `_shared/`, since it is consumed directly
  by a stage workflow's jobs, not only by other composites) — consistent
  with `wing-commander-inspected-run-identity`'s existing precedent. Pass.
- **VIII. A Green Check Means What It Says**: Gate 34's extension keeps its
  existing "run the shipped `run:` text against a real git fixture" shape
  (research.md D7); the new mutation (contracts/run-scoped-fold-evidence.md)
  ensures the gate fails if the unscoped-grep regression is reintroduced —
  the failure branch this feature exists to close. Pass.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: This is the feature's central mechanism — FR-004 explicitly
  forbids trusting the agent's own commit message for attribution, and D1's
  git-hook design puts that judgment in deterministic code the agent cannot
  silently skip. Pass.
- **X. Bounded Autonomy**: Not applicable — this is a spec-lifecycle
  feature (intake → plan → tasks → implement), not a board-loop fix PR.

No violations; Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/075-run-scoped-fold-evidence/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── run-scoped-fold-evidence.md   # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source code (repository root)

This feature touches only this repository's own GitHub Actions pipeline
(no application source tree, no `src/`/`tests/` split — see
specs/010-reusable-pipeline for the published stage/composite-action
layout this repository already uses):

```text
.github/
├── workflows/
│   └── pr-conversation.yml                         # act (new hook-install step),
│                                                    # dispatch-once, report-fold-outcomes
│                                                    # (both call the new composite action)
├── actions/
│   └── wing-commander-fold-evidence/                # NEW composite action (data-model.md §3)
│       └── action.yml
└── scripts/
    └── verify-fold-dispatch-once.py                 # Gate 34, EXTENDED (not duplicated) —
                                                       # new scenarios + one new mutation
```

**Structure Decision**: All changes land inside `pr-conversation.yml` (one
new step in `act`, changed logic in `dispatch-once` and
`report-fold-outcomes`), one new composite action under `.github/actions/`
(the published surface, self-checkout pattern, per Constitution VII), and
an extension of the existing Gate 34 script. No new workflow file, no new
gate number, no change to any other stage.

## Complexity Tracking

No Constitution Check violations — this section is not needed.
