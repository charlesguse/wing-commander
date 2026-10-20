# Implementation Plan: Implement Stall Hand-off and Honest Remaining-Work Reporting

**Branch**: `spec/117-implement-stall-handoff` | **Date**: 2026-10-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/117-implement-stall-handoff/spec.md`

## Summary

Replace "one zero-progress cycle ends implement" with a deterministic stop
rule that hands off only on a shape-validated agent blocker or the iteration
cap; mark maintainer-only tasks with a `[maintainer]` token the tasks stage
emits and every reader treats the same way; and have finalize render the
remaining-work report deterministically as "Maintainer steps" versus
"Unfinished implementation" (with a stall statement). Re-entry from review
becomes legible (comment on no-op, remaining-cycle count). All logic lands in
shared scripts under `.github/actions/_shared/` with one new fixture-driven
gate. See research.md D1-D10.

## Technical Context

**Language/Version**: Bash (shared scripts, workflow `run:` steps), Python 3 (gates), GitHub Actions YAML

**Primary Dependencies**: `jq`, `awk`, `git`, PyYAML (gates, in the pinned image since #996)

**Storage**: files only (tasks.md, spec-meta.json, runner-temp blocker JSON)

**Testing**: checked-in fixtures under `.github/scripts/fixtures/117-implement-stall-handoff/` run by a new `verify-implement-stall-handoff.py`; `python .github/scripts/run-local-gates.py`

**Target Platform**: GitHub Actions runners / stage container image

**Project Type**: CI pipeline (reusable workflows + composite actions)

**Performance Goals**: N/A

**Constraints**: stage workflows read no ambient state (VII); no agent judgment on gating decisions (IX); workflow comments are load-bearing, re-run the full gate suite; public repo, no private consumer references

**Scale/Scope**: touches `implement.yml` (two read-back arms, idempotency guard), `finalize.yml`, `tasks.yml` prompt, the checkbox-count composite and `_shared` scripts, live docs

## Constitution Check

| Principle | Assessment |
|---|---|
| I Guide | Built through the pipeline; PASS |
| II Model tiering | No new agent invocations; the finalize agent loses a duty; PASS |
| III GitHub-native | Stall, no-op and remaining-cycle facts post on the lifecycle issue; PASS |
| IV Automation-first | Manual steps are now explicitly reported as maintainer steps; PASS |
| V Security | Blocker JSON is untrusted agent output, validated; written to runner temp, no `.claude/` writes; PASS |
| VI Portability | Paths resolve via the project folder; no repo names; PASS |
| VII Two interfaces | Additive composite outputs and possibly one additive `implement.yml` input, declared and typed; no removal or rename; flagged for release notes; PASS (deliberate widening) |
| VIII Green check | New gate in the registry, fixture per failure branch, same invocation local and CI; PASS |
| IX Deterministic judgment | Marker, standing rule, stop rule, finalize split and blocker validation are all code; the agent only supplies the blocker field, validated; PASS |
| X Bounded autonomy | Unaffected; PASS |

No violations; Complexity Tracking not needed. Post-design re-check: unchanged (design adds no agent steps, no new triggers).

## Project Structure

### Documentation (this feature)

```text
specs/117-implement-stall-handoff/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/shared-scripts.md
└── tasks.md             # tasks stage
```

### Source Code (repository root)

```text
.github/actions/_shared/
├── count-tasks-checkboxes.sh        # extended: classification (D2, D3)
├── validate-implement-blocker.sh    # new (D4)
├── decide-implement-outcome.sh      # new (D5, D6)
└── render-remaining-work.sh         # new (D7)
.github/actions/wing-commander-tasks-checkbox-count/action.yml  # additive outputs
.github/workflows/implement.yml      # both read-back arms, guard comment, blocker prompt line
.github/workflows/finalize.yml       # deterministic remaining-work report
.github/workflows/tasks.yml          # marker/placement rules in the stage prompt
.github/scripts/verify-implement-stall-handoff.py   # new gate
.github/scripts/fixtures/117-implement-stall-handoff/
docs/                                # live implement-loop and finalize docs
```

**Structure Decision**: extend the existing single home of the tasks.md read and add three small sibling scripts in `_shared/`, consumed by both implement arms and finalize, rather than inlining rules in workflows.

## Complexity Tracking

None.
