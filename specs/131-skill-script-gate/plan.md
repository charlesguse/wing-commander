# Implementation Plan: Gate the skill scripts' self-tests and cross-tree imports

**Branch**: `spec/131-skill-script-gate` | **Date**: 2026-11-25 | **Spec**: [spec.md](spec.md)

## Summary

Add one gate, `.github/scripts/verify-skill-scripts.py`. It discovers every
`.claude/skills/*/scripts/*.py`, statically (via `ast`) checks that each
`from M import n` and each `m.attr` use of an imported `.github/scripts`
module resolves, and runs every script that declares `--self-test` as an
offline subprocess. It has its own `--self-test` with checked-in fixtures
for a removed name, a removed attribute, a removed module and a failing
skill self-test. Two `if: "!cancelled()"` steps in lint-workflows' `lint`
job invoke it; `wc_gate_registry` derives them into `run-local-gates.py`.
Details: [research.md](research.md).

## Technical Context

**Language/Version**: Python 3 (stdlib `ast`, `subprocess`; PyYAML not needed)

**Primary Dependencies**: none new; reads `wc_gate_registry` conventions only

**Storage**: N/A

**Testing**: the gate's `--self-test` plus fixtures in
`.github/scripts/verify-skill-scripts-fixtures/`

**Target Platform**: GitHub Actions Linux runner and local sessions

**Project Type**: CI gate script

**Performance Goals**: both steps under one minute (SC-004)

**Constraints**: offline, never executes a skill's normal path (FR-005)

**Scale/Scope**: six skill scripts today; discovered, not listed

## Constitution Check

- I Guide: built through the pipeline. Pass.
- II Model tiering: no agent step added. N/A.
- III GitHub-native: no new interface. Pass.
- IV Automation-first: gate list derived, no hand registration. Pass.
- V Security: no `.claude/` writes by an agent; the gate only reads
  `.claude/skills`. Skill scripts run only as `--self-test` from the PR's
  own head, same trust as every other gate. Pass.
- VI Portability: no repo names hardcoded. Pass.
- VII Two interfaces: adds no input, secret or output to a stage
  workflow or published composite. Pass.
- VIII Green check: fails loudly on empty subject, has fixtures for every
  failure branch, runs the same subject locally and in CI, own step with
  `!cancelled()`, triggered by the trees it checks (`paths:` already covers
  both). This feature serves the principle. Pass.
- IX Deterministic judgment: pure code. Pass.
- X Bounded autonomy: fix-shaped; sized by the split in research D6.

Post-design re-check: unchanged, pass. No Complexity Tracking entries.

## Project Structure

### Documentation

```text
specs/131-skill-script-gate/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/verify-skill-scripts.md
└── tasks.md   # tasks stage
```

### Source Code

```text
.github/scripts/
├── verify-skill-scripts.py
└── verify-skill-scripts-fixtures/     # bad-missing-name, bad-missing-module,
                                       # bad-attribute, bad-self-test, ok-*
.github/workflows/lint-workflows.yml   # two new steps in the lint job
```

**Structure Decision**: one script plus a fixtures directory under
`.github/scripts/` (where `gate_scripts()` discovers gates, Gate 119).
Nothing under `.claude/` is edited. `docs/reference.md` only if its
"Keeping this current" categories change.

## Decisions made without clarification

None were required; spec.md had no markers. Plan-level choices (static
`ast`, one script, split) are in research.md D1-D7.

## Complexity Tracking

None.
