# Quickstart: Validating the Rendered Tooling List

**Feature**: 037-rendered-tooling-list

How to prove the feature works end-to-end once implemented, mapped to the
spec's acceptance scenarios and success criteria. No full implementation
code here — see `contracts/tooling-statement-render.md` for the exact
render algorithm and `data-model.md` for the entities being validated.

## Prerequisites

- A checkout with this feature implemented: the corrected `shell-commands`
  render in `.github/actions/wing-commander-tool-args/action.yml`
  (`contracts/tooling-statement-render.md`), the rewritten prompt paragraphs
  in `.github/workflows/implement.yml` (research.md D6), and the two new
  gate scripts (`verify-tooling-statement.py`,
  `verify-tool-args-contract.py`) wired into `.github/workflows/
  lint-workflows.yml`.
- `actionlint` and `yamllint` available (already gated in CI per spec
  025-lint-composite-actions) for static validation of the changed workflow
  YAML.
- Ability to trigger `implement.yml`'s dogfood wrapper, or invoke the
  composite action's shell logic standalone, per this repo's existing
  dogfooding pattern (constitution I) and spec 026's own quickstart
  precedent.

## Static validation — the render (User Stories 1 and 2)

Run `python3 .github/scripts/verify-tooling-statement.py` (or invoke the
composite's extracted `run:` block by hand with the env vars below) and
confirm each `shell-commands` value:

1. No consumer configuration at all → statement enumerates exactly that
   step's hard-coded default `Bash(...)` entries, in first-seen order
   (Acceptance 1.3, SC-003).
2. `extra-disallowed-tools` denies (exactly or by prefix) a command the
   step's defaults allow → that command is absent from the statement, and
   the composed `allowed-tools`/`disallowed-tools` outputs are unchanged
   from the no-subtraction case (Acceptance 1.1, 1.2).
3. `allowed-tools-override` replaces the allowed list wholesale → statement
   is derived from the replacement, not the defaults (Acceptance 1.4).
4. A command denied via `extra-disallowed-tools` and re-allowed via
   `extra-allowed-tools` (spec 026's explicit-allow-beats-default-deny) →
   statement names it as permitted, agreeing with the enforced outcome
   (Acceptance 1.5).
5. Allowed list contains bare `Bash` → `This run permits any shell
   command.` (Acceptance 2.1).
6. Bare `Bash` allow plus a command-specific deny → `This run permits any
   shell command except: \`cmd\`.` (research.md D3).
7. Allowed list has no `Bash`/`Bash(...)` entry at all, but other tools are
   present → `This run permits no shell command.`, a complete sentence with
   no dangling punctuation, other tools untouched (Acceptance 2.2, edge
   case).
8. `Bash(cmd)` only (no `:*`) → `` `cmd` (exact command only) `` appears,
   distinguishing it from the any-arguments form (Acceptance 2.3).
9. Both `Bash(cmd)` and `Bash(cmd:*)` granted → `cmd` appears once, in the
   broader (`PREFIX`) form (Acceptance 2.4).
10. A deny that only partially overlaps an allow (e.g. `Bash(cmd)` denied
    while `Bash(cmd:*)` is allowed) → `cmd` remains stated (edge case:
    "remains largely permitted").
11. Every case above produces a value ending in a period with no
    unresolved template text (Acceptance 2.5, SC-002).

## Self-test verification (User Story 4)

Confirm `verify-tooling-statement.py`'s own mutation phase fails when run
against deliberately reverted copies of the shipped script — one mutation
each for: the subtraction (case 2 above), the unrestricted-shell case (case
5), the empty-list fallback (case 7), and the deduplication (case 9). Each
mutation must turn a *distinct* named test red (Acceptance 4.2).

## Contract-agreement check (User Story 3)

1. Run `python3 .github/scripts/verify-tool-args-contract.py` against the
   repository as shipped — passes (every emitted output is declared in both
   `action.yml`'s `outputs:` block and `tool-composition-action.md`'s
   Outputs table, and vice versa).
2. Confirm its self-test fixtures (an output declared-but-not-emitted, and
   an output emitted-but-not-declared) both fail the check when run
   standalone, naming the specific output (Acceptance 3.3, 3.4, 4.4).

## End-to-end scenario check (one dogfood run)

Trigger `implement.yml`'s dogfood wrapper (or a direct `workflow_call`) with
`extra-disallowed-tools` set to one command in the `implement.cycle` step's
default allowed list. Confirm from the run's own
`$GITHUB_STEP_SUMMARY` (no workflow source read required — User Story 5):

1. The `wing-commander-tool-args` step's summary carries a
   `**Tooling statement**:` line whose text names the run's actual permitted
   commands and omits the one just denied (SC-009, SC-010 — this is the
   direction that left spec 036 with four unrun tasks, now closed).
2. The prompt actually sent to the agent (visible in the `Implement and
   converge (cycle)` step's own log) contains that same sentence, not the
   old "are exactly ... — that list is ... authoritative" phrasing.

## Documentation check (User Story 3, SC-008)

Confirm, from `stage-interfaces.md`, `tool-composition-action.md`,
`tool-list-inputs.md`, and `docs/adoption.md` alone — no pipeline source
read — that an adopter configuring their own `extra-allowed-tools`/
`extra-disallowed-tools`/`*-override` values for a stage of their choice can
state in advance what their agent's tooling statement will say, including
which entries it excludes and why (Acceptance 3.2).

## Regression check (SC-004, SC-005)

Confirm the number of outputs `wing-commander-tool-args` emits without a
matching declaration is zero (down from the one — `shell-commands` — this
spec found undeclared before #214's retroactive documentation and this
feature's check), and that adding an undeclared output or removing a
declared one to a scratch copy fails `verify-tool-args-contract.py` before
merge.
