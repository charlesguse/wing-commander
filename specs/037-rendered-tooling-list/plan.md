# Implementation Plan: The Prompt's Tooling List States What the Run Actually Permits

**Branch**: `037-rendered-tooling-list` | **Date**: 2026-08-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/037-rendered-tooling-list/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

`wing-commander-tool-args`'s `shell-commands` output — the prose rendering
of a step's composed shell allowlist that `implement.yml`'s prompt uses to
tell its agent what it may run — is wrong in four ways (no subtraction of
denied commands, a bare `Bash` grant renders as nothing, exact and prefix
grants collapse to the same text with duplicates, an empty result reaches
the model as a dangling em-dash inside a sentence claiming the list is
"exactly" the allowlist and "authoritative") and was never added to the
composite's published output contract. This is the same class of drift
already fixed once in one direction (deriving the statement from the
allowlist instead of hand-maintaining it) — the fix here closes the other
direction (subtracting the disallowed list) and every render defect
alongside it, then adds the executable coverage and the declared-output
check that keep both from regressing silently, since none exists today.

The technical approach: classify every composed grant into one of three
shell-command forms (unrestricted, prefix, exact — research.md D1), subtract
against the composed disallowed list per-grant rather than per-list
(research.md D2), and render one of four complete-sentence templates
instead of a bare list spliced into a fixed carrier sentence (research.md
D5) — this last change is what makes every case grammatical without special
casing the prompt. Two new gate scripts extend an existing harness pattern
(Gate 11's shipped-step extraction) to drive the corrected render and to
hold the composite's declared and emitted outputs in agreement, both
self-testing per this repository's established convention. No change to
tool-list composition itself (spec 026 is untouched), no new secret, and no
adopter-visible behavior change beyond the wording of the tooling sentence
and the now-declared output (FR-017).

## Technical Context

**Language/Version**: Bash (POSIX-ish, matching every existing composite
action) + GitHub Actions YAML (`workflow_call`, composite `action.yml`);
Python 3 for the two new gate scripts, matching every existing
`verify-*.py` in `.github/scripts/`. No application language.

**Primary Dependencies**: GitHub Actions (composite actions, `workflow_call`);
`anthropics/claude-code-action@v1` (consumed as-is by `implement.yml` — the
prompt text is a plain string input, so the corrected sentence is just
different text in the same place); `PyYAML` (already a dependency of the
existing `verify-*.py` gates that parse `action.yml`/workflow YAML, e.g.
`verify-metrics-turn-accounting.py`); `.github/scripts/wc_shell_harness.py`
(existing shared harness, reused rather than re-implemented — research.md
D8).

**Storage**: N/A — no persisted state; the rendered statement is
recomputed per run from that run's already-composed tool lists (spec 026)
and reaches only `$GITHUB_OUTPUT`, `$GITHUB_STEP_SUMMARY`, and the agent
prompt, none of which are read back by any later step.

**Testing**: `actionlint` + `yamllint` (already CI-gated per spec
025-lint-composite-actions) for the changed workflow/composite-action YAML;
two new `.github/scripts/verify-*.py` gates, each with an inline
mutation-based self-test, registered in `.github/workflows/
lint-workflows.yml` and auto-picked-up by the existing gate-wiring check
(`verify-gate-wiring.py`) — no test framework is introduced, matching every
other gate in this repository.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), consumed by
any GitHub repository that references these reusable workflows (constitution
VI).

**Project Type**: Infrastructure / reusable CI workflow library — not an
application; this feature's scope is one existing composite action's shell
step, one existing stage workflow's two prompt strings, two new gate
scripts, and four existing documentation files.

**Performance Goals**: N/A in the traditional sense — the render is a few
additional string/set operations inside a step that already runs in well
under a second; must add no perceptible wall-clock time.

**Constraints**: Zero change to `effective_allowed`/`effective_disallowed`
for any configuration (FR-003, SC-003); zero change to any published
stage's declared inputs or secrets (FR-017); the corrected sentence must be
a complete, grammatical sentence for every legal configuration including
ones no configuration in this repository exercises today (FR-008); the two
new gates must each carry a self-test that demonstrates a known-bad input
failing (FR-015), matching the one existing precedent for this
(`verify-metrics-turn-accounting.py`'s `MUTATIONS` phase) rather than
inventing a second self-test convention.

**Scale/Scope**: 1 composite action's render logic corrected (not its
composition, which is untouched); 2 prompt sites in 1 stage workflow
(`implement.yml` cycle + retry) rewritten; 2 new gate scripts; 4 existing
docs corrected (`tool-composition-action.md`, `stage-interfaces.md`,
`docs/architecture.md`, plus a 1-line addition each to `tool-list-inputs.md`
and `docs/adoption.md`); 0 new `workflow_call` inputs, 0 new secrets, 0
stages newly wired to consume the output.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide — dogfooded**: PASS. This spec flows through the same
  intake → plan → tasks → implement stages it modifies; the render it fixes
  is itself part of the `implement` stage's own prompt, and the quickstart's
  end-to-end check (a dogfood `implement.yml` run) exercises the fixed code
  on this repository, not a synthetic consumer.
- **II. Cost-Conscious Model Tiering**: PASS / not applicable. No new agent
  invocation — both new gate scripts and the composite's render step are
  pure Python/shell, no `anthropics/claude-code-action` call. `implement.yml`'s
  existing model/`--max-turns` values are untouched; only its prompt *text*
  changes.
- **III. Simple, GitHub-Native Interaction**: PASS. No new consumer-facing
  configuration surface — the four `workflow_call` inputs this feature reads
  (`extra-*`/`*-override`) already exist (spec 026); this feature changes
  only what the composite tells the agent about their effect, via ordinary
  workflow YAML and step summaries a maintainer already reads on the Actions
  run page.
- **IV. Automation-First**: PASS. The two new checks fail automatically,
  with a named discrepancy, rather than relying on a human noticing a
  drifted contract or a wrong sentence — this is the same automation gap
  (spec 036's four unrun tasks) the feature exists to close.
- **V. Security — Untrusted Content Is Never Instructions**: PASS, not
  implicated. Every value this feature reads (`effective_allowed`,
  `effective_disallowed`, the `workflow_call` inputs that produce them) is
  calling-workflow YAML, the same trust tier spec 026's Constitution Check
  already cleared — nothing here is derived from issue/comment body text.
  No tool grant becomes more or less permissive; only its prose description
  changes.
- **VI. Portability**: PASS. All changes are within `.github/actions/`,
  `.github/workflows/`, `.github/scripts/`, and this repository's own
  `docs/`/`specs/` — nothing pipeline-specific is bundled into or resolved
  from a consuming repository beyond the existing composite-action
  resolution pattern (`github.job_workflow_sha`, unchanged).
- **VII. Two Interfaces — The Published Contract and the Consuming
  Instrument**: This principle is the constitutional half of the feature
  itself (User Story 3's own "why," spec.md line 55). PASS, and directly
  advanced: the composite's `shell-commands` output — already resolved from
  the pipeline repository's own checkout, already part of the
  `workflow_call`-adjacent composite-action surface — moves from
  "discoverable only by reading its source" to declared, with a machine
  check (`verify-tool-args-contract.py`) holding declaration and emission
  in agreement in both directions, matching how every other stage
  input/output on this list is already governed. No input, secret, or
  output is removed or renamed; the one output that was undeclared becomes
  declared (a widening, done deliberately, per this principle's own text on
  widening being "a deliberate act rather than a convenience").

No violations requiring justification; Complexity Tracking table is empty.
This feature corrects an existing published surface and adds the missing
governance for it — it does not introduce a new architectural layer,
composite action, or consumer-facing input.

**Post-Phase-1 re-check**: unchanged — `data-model.md` and `contracts/`
introduce no new agent invocation, no new secret, no new external
dependency, and preserve the FR-003/SC-003 zero-enforcement-change
invariant end-to-end (the render is documented throughout as a pure read of
already-final composed lists). Gate still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/037-rendered-tooling-list/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   ├── tooling-statement-render.md   # implementer-facing render algorithm (replaces tool-composition-action.md's "Caveats as shipped" at implementation time)
│   └── contract-agreement-check.md   # implementer-facing contract for the new declared/emitted output check
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This is an infrastructure feature with no `src/`/`tests/` application tree
— its "source" is GitHub Actions workflow/composite-action YAML and two
Python gate scripts, at fixed, well-known paths already established by
spec 026 and the existing gate-registry pattern. No new top-level
directories.

```text
.github/
├── actions/
│   └── wing-commander-tool-args/
│       └── action.yml       # render step corrected (contracts/tooling-statement-render.md); composition logic (spec 026) untouched; outputs: block already declares shell-commands (#214) — description text corrected, not added
├── workflows/
│   ├── implement.yml         # 2 prompt sites rewritten (cycle, retry) — research.md D6; post-progress-comment untouched (never read shell-commands)
│   └── lint-workflows.yml    # + 2 new "Gate N — ..." steps invoking the scripts below; no manifest edit needed (verify-gate-wiring.py auto-detects)
└── scripts/
    ├── verify-tooling-statement.py      # NEW — render-correctness gate + inline mutation self-test (research.md D8)
    ├── verify-tool-args-contract.py     # NEW — declared/emitted output agreement check + inline self-test (research.md D9)
    └── wc_shell_harness.py               # existing — reused, not modified

specs/026-configurable-tool-lists/contracts/
├── tool-composition-action.md   # "Caveats as shipped" replaced with the corrected contract (research.md D10)
└── tool-list-inputs.md          # + 1-line pointer to tool-composition-action.md#outputs (FR-013)

specs/010-reusable-pipeline/contracts/
└── stage-interfaces.md   # "What the agent is told" paragraph corrected — drops the "known divergences" framing

docs/
├── architecture.md   # Security section paragraph corrected to match
└── adoption.md        # + 1 sentence on the existing "Tool-list inputs" bullet
```

**Structure Decision**: No new project/module boundary and no new composite
action. This is a correction-and-governance feature layered onto spec 026's
existing structure: the render fix lands inside the one shell step spec 026
already created, the two new gate scripts follow the exact naming and
registration convention every other `verify-*.py` gate already uses (no new
registry, no new CI job type), and every documentation edit lands in a doc
that already exists and already (per #214) partially anticipates this
feature rather than a new competing doc. This plan stage only drafts the
`contracts/` content under this feature's own `specs/` directory, per the
file-scope constraint on this stage — the edits to `tool-composition-action.md`,
`stage-interfaces.md`, `docs/architecture.md`, `docs/adoption.md`,
`tool-list-inputs.md`, `action.yml`, `implement.yml`, and the two new
scripts happen at implementation time.

## Complexity Tracking

*No entries — Constitution Check found no violations requiring
justification.*
