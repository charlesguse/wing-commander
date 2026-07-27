# Implementation Plan: Configurable Allowed/Disallowed Tool Lists Across Pipeline Stages

**Branch**: `026-configurable-tool-lists` | **Date**: 2026-07-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/026-configurable-tool-lists/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Downstream consumers of the pipeline's published `workflow_call` stages
(intake, clarify, plan, tasks, implement ⟲ converge, finalize, cleanup,
rebase, watchdog) currently cannot adjust which tools an agent step may or
may not use without forking the workflow file — every stage's
`--allowedTools`/`--disallowedTools` are hard-coded literals inline in
`claude_args:`. This feature adds, uniformly to every agent-running stage,
four optional `workflow_call` inputs (`extra-allowed-tools`,
`extra-disallowed-tools`, `allowed-tools-override`,
`disallowed-tools-override`) that let a consumer append to or fully replace
each stage's default allowed/disallowed lists, with zero behavior change
when unset. The technical approach centralizes composition and FR-010
conflict validation in one new shared composite action
(`wing-commander-tool-args`, mirroring the existing
`wing-commander-preflight` pattern) called once per internal agent step
from each stage's job, rather than duplicating the composition/precedence
logic 14 times across the 9 stage files.

## Technical Context

**Language/Version**: Bash (POSIX-ish, matching existing composite actions) + GitHub Actions YAML (`workflow_call`, composite `action.yml`); no application language.

**Primary Dependencies**: GitHub Actions (`workflow_call`, composite actions), `anthropics/claude-code-action@v1` (consumed as-is — it exposes no structured tool-list input, so composition must produce the same opaque `claude_args:` CLI-flag string it already receives), `jq` (already a dependency of `wing-commander-preflight` for similar list/JSON handling).

**Storage**: N/A — no persisted state; pure per-run computation from `workflow_call` input values.

**Testing**: `actionlint` + `yamllint` (already CI-gated per spec 025-lint-composite-actions) for the new/changed workflow YAML and the new composite action; standalone shell invocation of the composition logic with representative env var combinations asserting `$GITHUB_OUTPUT` (see `quickstart.md`); end-to-end dogfood runs via this repo's own `wing-commander-*.yml` wrapper workflows exercising the new inputs on real stages.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), consumed by any GitHub repository that references these reusable workflows (constitution VI — portability).

**Project Type**: Infrastructure / reusable CI workflow library — not an application; single scope covering `.github/workflows/` (9 stage files) and `.github/actions/` (one new composite action).

**Performance Goals**: N/A in the traditional sense — the new composition step is a few string/set operations in a fail-fast preflight-style step; must add negligible wall-clock time (well under a second) relative to the agent step it precedes.

**Constraints**: Zero breaking changes for existing consumers (SC-005); no new required secret; must produce output compatible with `anthropics/claude-code-action@v1`'s single opaque `claude_args:` string (no structured allowed/disallowed action input exists to target instead); new inputs must follow the existing kebab-case/string/optional convention already used for `spec-draft-prefix` etc.; conflicting append+override input (FR-010) must fail before any agent step, never silently resolve.

**Scale/Scope**: 9 published stage workflows; 14 individual agent steps across them (`implement.yml` alone has 3 with different defaults); 4 new inputs added uniformly to every stage's `workflow_call.inputs`; 1 new shared composite action.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide — dogfooded**: PASS. This spec itself flows through the same
  intake → plan → tasks → implement stages it modifies; no bootstrap
  exception needed.
- **II. Cost-Conscious Model Tiering**: PASS / not applicable. No new agent
  invocation is introduced — the new composite action is pure shell (no
  `anthropics/claude-code-action` call inside it), identical in kind to
  `wing-commander-preflight`, so it "can never itself incur cost." No
  existing stage's model or `--max-turns` changes.
- **III. Simple, GitHub-Native Interaction**: PASS. Configuration is
  ordinary `workflow_call` `with:` inputs set in the consumer's own
  workflow YAML (optionally backed by repository variables at a wrapper
  layer, following the existing branch-prefix precedent) — no new
  dashboard, CLI, or side channel.
- **IV. Automation-First**: PASS. No new manual step; a misconfiguration
  (FR-010) fails automatically with a message posted the same way
  `wing-commander-preflight` already reports failures (step summary +
  `::error::`), not a silent or manual fallback.
- **V. Security — Untrusted Content Is Never Instructions**: PASS, with a
  documented nuance (see research.md "Constitutional considerations"). The
  four new inputs are supplied by the *calling workflow's own YAML*
  (`with:` values, the same trust tier as `model`/`max-turns`/branch
  prefixes today) — never derived from issue or comment body text, so
  Principle V's untrusted-content rule is not implicated. FR-011's
  "explicit allow beats default deny, no protected subset" does mean a
  consumer can opt a stage into a less restrictive tool set than the
  pipeline's built-in default (e.g. re-enabling `WebFetch`) — this is an
  explicit, spec-resolved capability (clarified on the lifecycle issue,
  see `checklists/requirements.md`), not an accidental hole, and FR-013's
  documentation requirement is how consumers are informed before opting in.
  `ScheduleWakeup`/`Monitor`/`SendMessage` remain functionally inert
  regardless, since a one-shot Action cannot service them either way.
- **VI. Portability**: PASS. New inputs are wired at the `workflow_call`
  boundary and (optionally) the consumer's own wrapper workflow / repo
  variables — nothing pipeline-specific is bundled into or read from the
  consuming repository's `specs/`/`.specify/` beyond the existing pattern.

No violations requiring justification; Complexity Tracking table is empty
(N/A) — the one new composite action is additive infrastructure of the
same kind already established (`wing-commander-preflight`,
`wing-commander-context`, etc.), not a deviation from an existing gate.

**Post-Phase-1 re-check**: unchanged — `data-model.md` and `contracts/`
introduce no new agent invocations, no new secrets, no new external
dependency, and preserve the SC-005 zero-change-when-unset invariant
end-to-end. Gate still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/026-configurable-tool-lists/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   ├── tool-list-inputs.md          # consumer-facing workflow_call input contract
│   ├── tool-composition-action.md   # implementer-facing composite action contract
│   └── stage-default-tool-lists.md  # documented current defaults per stage/step (FR-013)
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This is an infrastructure feature with no `src/`/`tests/` application tree
— its "source" is GitHub Actions workflow and composite-action YAML, which
already exists at fixed, well-known paths in this repository. No new
top-level directories are introduced.

```text
.github/
├── workflows/
│   ├── intake.yml         # + 4 new workflow_call inputs; 1 agent step calls the new composite action
│   ├── clarify.yml        # + 4 new workflow_call inputs; 1 agent step
│   ├── plan.yml            # + 4 new workflow_call inputs; 2 agent steps (direct-commit, pr)
│   ├── tasks.yml            # + 4 new workflow_call inputs; 2 agent steps (direct-commit, pr)
│   ├── implement.yml        # + 4 new workflow_call inputs; 3 agent steps (cycle, retry, post-progress-comment)
│   ├── finalize.yml         # + 4 new workflow_call inputs; 1 agent step
│   ├── cleanup.yml          # + 4 new workflow_call inputs; 1 agent step
│   ├── rebase.yml           # + 4 new workflow_call inputs; 1 agent step
│   ├── watchdog.yml         # + 4 new workflow_call inputs; 2 agent steps (diagnose, propose-fix)
│   └── wing-commander-*.yml # this repo's own dogfood wrappers — unaffected unless exercising the new inputs for validation
└── actions/
    ├── wing-commander-preflight/       # existing — pattern this feature's new action mirrors
    ├── wing-commander-context/         # existing
    ├── wing-commander-tool-args/       # NEW — composition + FR-010 validation (contracts/tool-composition-action.md)
    │   └── action.yml
    └── ...                              # other existing composite actions, unaffected

specs/010-reusable-pipeline/contracts/
└── stage-interfaces.md   # extended (not created) with the new inputs + a default-tool-list reference (research.md D7); edited during implementation, not by this plan stage

docs/
├── architecture.md        # extended with a pointer to the new contract (FR-013)
└── adoption.md             # extended with a short append-vs-replace explainer (FR-013)
```

**Structure Decision**: No new project/module boundary. Changes are
additive edits to the 9 existing stage workflow files (new
`workflow_call` inputs + one new composite-action call per existing agent
step) plus one new composite action
(`.github/actions/wing-commander-tool-args/`). Documentation additions
land in the existing normative contract doc
(`specs/010-reusable-pipeline/contracts/stage-interfaces.md`) and existing
`docs/` files rather than new files, per constitution VI (one contract doc
consumers already know to check) — this plan stage only drafts that
content under `specs/026-configurable-tool-lists/contracts/`, since edits
outside this feature's own spec directory happen at implementation time.

## Complexity Tracking

*No entries — Constitution Check found no violations requiring
justification.*
