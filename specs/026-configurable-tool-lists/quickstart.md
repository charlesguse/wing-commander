# Quickstart: Validating Configurable Tool Lists

**Feature**: 026-configurable-tool-lists

How to prove the feature works end-to-end once implemented, mapped to the
spec's acceptance scenarios and success criteria. No full implementation
code here — see `contracts/` for the exact input/action shapes and
`data-model.md` for the composition rule being validated.

## Prerequisites

- A checkout with this feature implemented: the four new `workflow_call`
  inputs on every agent-running stage (`contracts/tool-list-inputs.md`) and
  the `wing-commander-tool-args` composite action
  (`contracts/tool-composition-action.md`).
- `actionlint` and `yamllint` available (already gated in CI per spec
  025-lint-composite-actions) for static validation of the new/changed
  workflow YAML and the new composite action.
- Ability to trigger a stage's dogfood wrapper workflow (`wing-commander-*
  .yml`) or a direct `workflow_call` invocation, per this repo's existing
  dogfooding pattern (constitution I).

## Static validation (no agent run required)

1. `actionlint` and `yamllint` pass on every changed workflow file and the
   new `.github/actions/wing-commander-tool-args/action.yml`.
2. Run the composite action's shell logic standalone (extract the `run:`
   block, or invoke via a throwaway workflow) with representative env var
   combinations and assert `$GITHUB_OUTPUT` contents:
   - No `extra-*`/`*-override` set → outputs equal the stage's literal
     `default-allowed-tools`/`default-disallowed-tools` inputs exactly
     (SC-005 invariant, `data-model.md` "Invariant").
   - `extra-allowed-tools="Bash(npm run lint:*)"` only → output allowed list
     is the default list plus that one entry, defaults otherwise untouched.
   - `allowed-tools-override=""` (explicit empty) → output allowed list is
     empty, distinct from the unset case above (FR-009).
   - Both `extra-allowed-tools` and `allowed-tools-override` set (either
     non-sentinel value) → non-zero exit, `::error::` naming both values
     (FR-010).
   - `extra-allowed-tools="Bash(x:*)"` where `Bash(x:*)` is also in
     `default-disallowed-tools` → output disallowed list no longer contains
     `Bash(x:*)`, output allowed list does (FR-011, allow wins over default
     deny).
   - `extra-disallowed-tools="Read"` where `Read` is in `default-allowed-tools`
     → output allowed list still contains `Read` (unions don't subtract
     defaults) **and** output disallowed list contains `Read` (User Story
     2, Acceptance #2 — consumer's own explicit CLI precedence denies it
     downstream even though it's nominally still "allowed").
   - Duplicate entry across default and extra (e.g. `Read` in both) →
     output list contains `Read` exactly once.

## End-to-end scenario checks (one dogfood run each, or combined)

Map directly to `spec.md`'s acceptance scenarios:

1. **User Story 1 / SC-001**: pick any stage (e.g. `clarify`), run its
   wrapper workflow with `extra-allowed-tools` set to one tool not in that
   stage's default list. Confirm from the run's job logs / `claude_args`
   that both the new tool and every default tool are present, and the
   stage completes its normal work (comment/PR update as usual).
2. **Backward compatibility / SC-005**: run the same stage's wrapper
   workflow with none of the four inputs set. Confirm the composed
   `--allowedTools`/`--disallowedTools` values match the pre-feature
   literal strings in `contracts/stage-default-tool-lists.md` exactly.
3. **User Story 2 / SC-002**: run a stage with `extra-disallowed-tools` set
   to one tool that *is* in that stage's default allowed list. Confirm the
   agent is denied that tool while every other default still functions.
4. **User Story 3 / SC-003**: run a stage with `allowed-tools-override` set
   to a small custom list. Confirm the agent has exactly that list — no
   defaults beyond it. (Pick a stage/override where the custom list still
   covers what that stage needs to complete its lifecycle bookkeeping, per
   FR-012's consumer-responsibility note, so the run can actually finish
   and be observed succeeding.)
5. **FR-010 conflict**: run a stage with both `extra-allowed-tools` and
   `allowed-tools-override` set. Confirm the run fails at the composition
   step, before the agent step starts (no Claude credential/cost consumed —
   check the job log shows no `anthropics/claude-code-action` step ran).
6. **User Story 4 / SC-004**: repeat check 1 or 2 on every agent-running
   stage (intake, clarify, plan, tasks, implement, finalize, cleanup,
   rebase, watchdog) and confirm identical append behavior on each —
   100% coverage.

## Documentation check (FR-013, SC-006)

Confirm `specs/010-reusable-pipeline/contracts/stage-interfaces.md` (after
this feature's implementation carries over `contracts/tool-list-inputs.md`
and `contracts/stage-default-tool-lists.md`) lets a consumer answer, from
docs alone and without reading pipeline source: what are stage X's default
allowed/disallowed tools, and how do append and replace differ.
