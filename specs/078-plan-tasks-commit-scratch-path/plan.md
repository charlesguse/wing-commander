# Implementation Plan: A Plan or Tasks Agent Can Write a Multi-Line Commit Message

**Branch**: `078-plan-tasks-commit-scratch-path` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/078-plan-tasks-commit-scratch-path/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Nine agent-prompt sites across five workflows (`plan.yml` ×2, `tasks.yml` ×2,
`board-loop.yml` ×2, `pr-conversation.yml` ×1, `implement.yml` ×2) instruct an
agent to `git commit`. Only `implement.yml`'s two sites tell the agent how to
compose a multi-line message safely (Write the message to a named scratch
path outside the checkout, then `git commit -F` that path); the other seven
say nothing, so the first time one of those agents composes a body it hits a
silent permission denial it cannot diagnose. The fix renders one canonical
guidance paragraph — a new composite action's output, following the same
"one source, many call sites" shape `wing-commander-tool-args`'s
`shell-commands` output and `wing-commander-metrics-summary`'s `cost-line`
output already use — into all nine prompts, each substituting its own scratch
filename, and backs the convention with a new deterministic gate so a future
prompt edit that drops the sentence fails the PR-time suite instead of the
next agent run.

## Technical Context

**Language/Version**: Bash (composite action step), Python 3.11 (gate script) — matching every other composite action and `verify-*.py` gate in this repository.

**Primary Dependencies**: GitHub Actions composite-action syntax (`.github/actions/*/action.yml`); `PyYAML` and this repo's `wc_shell_harness.py` / `wc_gate_registry.py` helpers for the new gate, matching `verify-stage-tool-lists.py` / `verify-plan-tasks-cost-line.py` / `verify-tooling-statement.py`.

**Storage**: N/A — no persisted state; the scratch file this feature names is workspace-local and job-scoped (`${{ runner.temp }}`), never committed (User Story 2).

**Testing**: The new gate's own `--self-test` mode (the repository's standard: every `verify-*.py` gate proves it can fail before it is trusted to pass, per Constitution VIII), run through `.github/scripts/run-local-gates.py`; the composite action's rendering logic is exercised the way `verify-tooling-statement.py` exercises `wing-commander-tool-args` — by extracting and executing the shipped `run:` block, not by re-implementing it in the test.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), same as every other stage/composite in this repository.

**Project Type**: GitHub Actions workflow automation — composite actions under `.github/actions/`, reusable stage workflows under `.github/workflows/`, and Python gate scripts under `.github/scripts/`. No `src/`/`tests/` application tree exists or is introduced.

**Performance Goals**: N/A — a handful of extra composite-action steps (pure bash, no network) added to jobs that already run an agent invocation; no measurable latency budget applies.

**Constraints**: FR-008 (no change to workflow logic, job structure, triggers, permissions, concurrency, or step gating at any touched site — this is prompt text plus new non-branching steps, nothing else); Constitution VII (a stage workflow's own deviation from ambient-state-free inputs would need a registered exception — not implicated here, since the new composite action is invoked the same way `wing-commander-tool-args` already is, with typed inputs only); Constitution IX (the gate's exemption decision is deterministic code, never left to a prompt).

**Scale/Scope**: 9 in-scope prompt sites across 5 workflow files; 1 new composite action; 1 new `verify-*.py` gate plus its `lint-workflows.yml` registration; 2 existing hand-written paragraphs (`implement.yml`) converted to render from the new source; 0 new entries expected in any `default-allowed-tools`/`default-disallowed-tools` list (FR-007 — research confirms `Write` and `Bash(git commit:*)` are already granted at all nine sites).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: N/A framing issue — this change is itself built through the pipeline (spec → plan → tasks → implement, issue #585). Pass.
- **II. Cost-Conscious Model Tiering**: no model or tier changes; the change only edits prompt text and adds deterministic (non-agent) steps. Pass.
- **III. Simple, GitHub-Native Interaction**: no user-facing interaction surface changes. Pass.
- **IV. Automation-First**: no manual step is introduced or removed. Pass.
- **V. Security**: no change to authorization, trust boundaries, or merge classes. Pass.
- **VI. Portability**: the new composite action lives under `.github/actions/` and is resolved from the consuming repository's own checkout exactly as `wing-commander-tool-args` and `wing-commander-metrics-summary` already are; no repo-specific literal is hardcoded outside the consuming repository's own workflows. Pass.
- **VII. Two Interfaces**: `plan.yml`, `tasks.yml`, `board-loop.yml`, `pr-conversation.yml`, and `implement.yml` are all published `workflow_call` stage contracts; this change adds no new input, secret, or output to any of them and reads no new ambient state — it only adds internal steps and edits prompt text. The new composite action is a plain (non-`_shared`) `.github/actions/` entry, matching `wing-commander-tool-args`'s own visibility, since every in-scope call site lives in a different published stage workflow, not in a single composite that only one workflow consumes. Pass.
- **VIII. A Green Check Means What It Says**: the new gate is reachable through the gate registry via a `lint-workflows.yml` step (deriving `run-local-gates.py`'s list automatically, per Gate 63/27/51 precedent), runs the same subject with the same arguments locally and in CI, is triggered by changes to the five workflow files and the new composite action, fails loudly if it cannot find a workflow file rather than reporting a vacuous pass, is not suppressible by an unrelated gate, and ships a `--self-test` exercising every failure branch (missing guidance, drifted rendering, unregistered exemption). Plan commits to this shape; Phase 1 names the concrete gate.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic Code**: whether a site is exempt from the guidance requirement is a literal constant in the gate script (mirroring Gate 51's `EXEMPT_SITES`), never a judgment the agent or a reviewer's prose makes at review time. Pass.
- **X. Bounded Autonomy**: not implicated — this feature does not touch the board loop's merge classes, only two of the prompts the board loop's own fixer/review-fixup agents read.

No violations. Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── actions/
│   └── wing-commander-commit-message-guidance/
│       └── action.yml          # NEW — the canonical guidance source (FR-011)
├── scripts/
│   ├── verify-commit-message-scratch-path.py   # NEW — the FR-012 gate
│   └── wc_shell_harness.py, wc_gate_registry.py, wc_yaml.py (existing helpers, reused)
└── workflows/
    ├── plan.yml               # 2 sites edited (direct-commit, PR)
    ├── tasks.yml               # 2 sites edited (direct-commit, PR)
    ├── board-loop.yml          # 2 sites edited (fixer, review-fixup)
    ├── pr-conversation.yml     # 1 site edited (fold agent)
    ├── implement.yml           # 2 sites converted from hand-written text to the render
    └── lint-workflows.yml      # gains the two verify-commit-message-scratch-path.py steps

specs/078-plan-tasks-commit-scratch-path/
├── plan.md              # This file
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── commit-message-guidance-action.md
│   └── commit-scratch-path-gate.md
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

**Structure Decision**: This is infrastructure-as-workflow, not an application
with a `src/`/`tests/` split — the repository's own convention (every existing
spec under `specs/`, e.g. 026, 037, 047, 063) is composite actions under
`.github/actions/`, Python gate scripts under `.github/scripts/`, and edits to
the affected `.github/workflows/*.yml` files, with the gate's own
`--self-test` standing in for a unit-test suite. That convention is followed
unchanged: one new composite action (the canonical source), one new gate
script plus its `lint-workflows.yml` registration, and edits confined to the
five workflow files the spec names.

## Complexity Tracking

No Constitution Check violations. This section is not applicable.
