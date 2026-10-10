# Implementation Plan: Agent Start-up Image Check

**Branch**: `spec/112-agent-startup-image-check` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/112-agent-startup-image-check/spec.md`

## Summary

Two additions to the image checks, both closing the gap that a green image
check proved a tool list, not that the agent can start (#974):

1. **Start-up check** (FR-001–FR-008, FR-010–FR-012). A job that runs the
   real `anthropics/claude-code-action@v1` inside the image under test with
   no model credential, then a deterministic classifier
   (`.github/scripts/classify-agent-startup.py`, Principle IX) reads the
   job's log and returns exactly one of `setup-completed` (pass),
   `setup-failed` (fail, names the setup step and quotes the error), or
   `unclassified` (fail, "could not reach subject"). Pass requires the
   positive marker "failed at authentication, after setup". It runs in the
   daily `private-image-dogfood.yml` (opt-in input, wrapper sets it) and on
   every rebuild of the e2e reference image
   (`wing-commander-e2e-reference-image.yml`), never as a per-stage
   preflight.
2. **Git floor** (FR-013, User Story 4). The in-container probe every
   stage's `verify-image-prerequisites` job runs also asserts git >= 2.38,
   naming the version found; an unparseable version fails.

The agent action stays on `@v1` (FR-007); the policy is written into the
image prerequisite contract documentation.

## Technical Context

**Language/Version**: GitHub Actions YAML, Bash (POSIX `sh` inside the
image probe), Python 3 (gate scripts; same interpreter as the existing
`verify-*.py`)

**Primary Dependencies**: `anthropics/claude-code-action@v1` (subject),
`gh api` for job logs, PyYAML (already required by the gate suite), Docker
on the hosted runner

**Storage**: N/A. Checked-in log fixtures under
`.github/scripts/agent-startup-fixtures/`

**Testing**: A `verify-agent-startup-classifier.py` gate with `--self-test`
driving every fixture; Gate 23 extension for the git-floor probe; existing
Gate 62 unchanged in what it asserts

**Target Platform**: GitHub-hosted `ubuntu-latest` runners; the image under
test is any Linux container image

**Project Type**: CI pipeline (workflows, composite actions, gate scripts)

**Performance Goals**: One extra job on a daily schedule and on reference
image rebuilds; no per-stage cost (FR-005). Roughly the action's setup time
(~30–60 s) plus a pull

**Constraints**: No model call, no model credential (FR-002); published
contract change must be additive and optional (FR-010); no hardcoded
repo/owner/image (FR-011); shared logic has one home (CLAUDE.md)

**Scale/Scope**: 1 new script + 1 gate + fixtures, edits to
`private-image-dogfood.yml`, its wrapper, the reference-image workflow,
the 14 pasted `verify-image-prerequisites` probes, Gate 23, docs

## Constitution Check

*GATE: passes before Phase 0 and after Phase 1.*

| Principle | Verdict | Note |
|---|---|---|
| I Guide | Pass | Built through the pipeline as spec 112 |
| II Model tiering | Pass (n/a) | No model invoked; the action is run with no credential. No `--max-turns` applicable because no agent turn is reachable |
| III GitHub-native | Pass | Failure is a red job on the run (FR-012) |
| IV Automation-first | Pass | Scheduled and rebuild-triggered, no manual step |
| V Security | Pass | Agent step gets no model credential; job `permissions` limited to `contents: read`, `actions: read` for the log read; no fork heads |
| VI Portability | Pass | Image arrives as a declared input; nothing repo-specific in the stage |
| VII Two interfaces | Pass, with care | New `startup-check` input (default `false`) on `private-image-dogfood.yml` is additive and optional; wrapper owns turning it on. Classifier lives in `.github/scripts/` (this repo's instrument), not in the published surface |
| VIII Green check | Pass | Positive-evidence pass only; every branch has a fixture; gate registered in `lint-workflows.yml` and run by `run-local-gates.py` |
| IX Deterministic judgment | Pass | Classification is code, not a prompt |
| X Bounded autonomy | Pass (n/a) | Not touched |

No violations; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/112-agent-startup-image-check/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── agent-startup-check.md
└── tasks.md             # /speckit-tasks, not created here
```

### Source Code (repository root)

```text
.github/
├── scripts/
│   ├── classify-agent-startup.py          # NEW: log -> verdict (single home)
│   ├── verify-agent-startup-classifier.py # NEW: gate + --self-test
│   ├── agent-startup-fixtures/            # NEW: one log per branch
│   ├── image-git-floor.sh                 # NEW: canonical git-floor probe fragment
│   └── required-tools.txt                 # header note on git floor / unzip basis
├── workflows/
│   ├── private-image-dogfood.yml          # +startup-check input, +job
│   ├── wing-commander-private-image-dogfood.yml  # wrapper opts in
│   ├── wing-commander-e2e-reference-image.yml    # +job calling the dogfood stage
│   ├── lint-workflows.yml                 # register new gate; Gate 23 probe check
│   └── <14 stage files>                   # git-floor fragment in the probe
docs/adoption.md, docs/setup.md            # git floor + @v1 policy + startup check
```

**Structure Decision**: Extend the existing image-check surface rather than
add a new stage. The job that needs `container:` cannot live in a composite,
so the dogfood stage hosts it and the reference-image workflow consumes that
stage (`uses: ./.github/workflows/private-image-dogfood.yml`), keeping one
copy of the job. The classification logic is a script, with a gate that
imports it, so CI and local runs share the same subject.

## Complexity Tracking

None.
