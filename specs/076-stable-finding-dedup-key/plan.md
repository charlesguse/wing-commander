# Implementation Plan: A Stage-Finding Dedup Key That Does Not Drift With Agent Wording

**Branch**: `076-stable-finding-dedup-key` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/076-stable-finding-dedup-key/spec.md`

## Summary

The stage-finding dedup key (spec 056) hashes `stage`, a normalized file
path, and a normalized-but-still-agent-phrased `gate_or_artifact` name; a
five-run drill on #424 proved an agent can vary that third field's wording
indefinitely even after normalization, filing twins nothing catches. This
feature replaces that third field with a **verbatim anchor**: a value the
agent can only copy from the named file, which the pipeline checks occurs
there (normalized-substring containment, research.md D1) before it enters
the key at all. An anchor that fails the check does not drop the finding —
it takes a coarser stage-plus-file-path fallback key (FR-007) — so the key
gains exactly two derivable shapes, both deterministic, both re-derivable
by a reviewer from the run's own recorded inputs (FR-002), and both
distinguishable from each other by a literal shape tag (research.md D2).
The change touches one composite's internal logic
(`wing-commander-stage-findings/action.yml`), the canonical formula
statement it must stay in sync with (spec 056's data-model.md, held by a
new gate per FR-012), the one prompt sentence describing the rule to the
agent (six stage workflows, held by an extended gate per FR-013), and a
new gate holding spec 057's differently-composed key deliberately apart
(FR-015). No JSON Schema changes, no new composite inputs, no new agent
permissions (FR-016).

## Technical Context

**Language/Version**: Python 3 (gate scripts, fixture harness) and Bash
(the composite action's `run:` steps) — matching every existing gate and
composite this feature extends; no new language enters the repository.

**Primary Dependencies**: None new. `hashlib`, `re`, `json` (stdlib) inside
the composite's existing inline Python; `PyYAML` (already a gate
dependency) for the new gate's YAML parsing; `gh` CLI (already required)
for the unchanged filing/dedup calls this feature does not touch.

**Storage**: N/A — GitHub Issues via the existing
`wing-commander-durable-failure-issue` composite, unchanged by this
feature.

**Testing**: The existing colocated fixture harness
(`.github/scripts/stage-findings-tests/run_fixtures.py`, driven via
`run-tests.sh`), extended per research.md D8; the existing local gate
suite (`python .github/scripts/run-local-gates.py`), extended with one new
gate script and one extended gate.

**Target Platform**: GitHub Actions runners (`ubuntu-latest`), matching the
composite and gates this feature amends; the anchor check reads only the
job's own checkout, no network call.

**Project Type**: Single project — this repository's own CI/CD pipeline
infrastructure (`.github/actions/`, `.github/scripts/`, `.github/workflows/`).
No frontend/backend split applies.

**Performance Goals**: N/A beyond what already applies — the anchor check
adds one file read and one substring test per surviving finding (at most
3, per the existing cap), well inside the composite's existing per-run
cost.

**Constraints**: No new composite input (research.md D3); no new run-summary
counter (research.md D4); no widening of the published composite's
input/output surface (Principle VII — this is an internal-logic and
internal-gate change, not a compatibility-surface change); the anchor check
must not introduce a second, drifting copy of the `norm()` function
(reuses spec 056's, unchanged).

**Scale/Scope**: Six published stage workflows' prompts (FR-013), one
composite action's internal logic (FR-004-FR-007), one existing data model
document amended in place (FR-012), one new gate script, one extended gate
script, one set of comment markers (Gate 47), one extended fixture harness.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **I. Guide**: This feature is itself worked through the pipeline (issue
  #569 → spec → plan → tasks → implement), the same worked-example
  requirement every other spec here satisfies. Pass.
- **II. Cost-Conscious Model Tiering**: No agent invocation, model, or
  `--max-turns` value changes; only the prompt *sentence* an existing
  step already sends changes. Pass, no gate implication.
- **III. Simple, GitHub-Native Interaction**: No new interaction surface;
  filed issues and appends still live entirely on GitHub, unchanged shape
  except FR-008's append-carries-its-own-description requirement, which
  makes the existing surface *more* legible, not different in kind. Pass.
- **IV. Automation-First**: No new manual step; the anchor check is
  deterministic code, not a human review gate. Pass.
- **V. Security**: The anchor is still agent-supplied text the pipeline
  treats as data, now checked against the tree before being trusted as a
  key component (never executed, never interpolated into a shell command
  beyond the existing hashing) — this feature *strengthens* the
  untrusted-content posture already required, it does not weaken it. No
  new merge or approval grant is added (FR-016 says so explicitly). Pass.
- **VI. Portability**: All changes live in `.github/actions/`,
  `.github/scripts/`, `.github/workflows/`, and `.specify/`-adjacent
  `specs/` documents — the consuming repository's own artifacts, per this
  constitution's existing scope. Pass.
- **VII. Two Interfaces**: `wing-commander-stage-findings` is a published
  composite; this feature changes its *internal* key-derivation logic, not
  any declared `inputs:`/`outputs:` name, so the compatibility surface is
  unchanged — no deliberate-widening act is needed. Pass.
- **VIII. A Green Check Means What It Says**: Both new/extended gates
  (FR-012, FR-013, FR-015) are registered in `lint-workflows.yml`, run the
  same subject locally as in CI, are triggered by changes to the files
  they check, fail loudly when their subject is unreachable, and ship a
  regression fixture per failure branch (contracts/gates.md). Pass — this
  is the principle FR-012/FR-013/FR-015 exist to satisfy in the first
  place.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: This is the feature's own thesis — the anchor check moves "is
  this name stable enough to key on" from an unenforceable prompt request
  into code that computes the same containment test from the same input
  every time (FR-004/FR-005). Pass, centrally.
- **X. Bounded Autonomy**: Not exercised by this feature directly (it does
  not touch the board loop's merge/route logic), except FR-015's gate,
  which protects spec 057's own key composition from drifting as a side
  effect of this feature — consistent with, not a change to, X. Pass.

No violations; **Complexity Tracking** is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/076-stable-finding-dedup-key/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   ├── anchor-verification.md
│   └── gates.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This repository has no `src/`/`tests/` split; its "source" is the pipeline
itself, under `.github/`. This feature's changes land entirely here:

```text
.github/
├── actions/
│   └── wing-commander-stage-findings/
│       └── action.yml                          # anchor check + two key shapes (FR-004..FR-007)
├── schemas/
│   └── stage-finding.schema.json                # UNCHANGED (no shape change)
├── scripts/
│   ├── verify-dedup-key-canonical-rule.py       # NEW — FR-012 + FR-015 gates
│   ├── verify-stage-findings-wiring.py          # EXTENDED — FR-013 substring check
│   ├── verify-comment-canonical-pointers.py     # UNCHANGED code; new markers it validates
│   ├── run-local-gates.py                        # registers the new gate
│   └── stage-findings-tests/
│       └── run_fixtures.py                        # EXTENDED — FR-010/FR-011 fixtures
└── workflows/
    ├── intake.yml, clarify.yml, plan.yml,
    │   tasks.yml, implement.yml, finalize.yml     # FR-013 prompt sentence + comment markers
    └── board-loop.yml                             # UNCHANGED logic; read by the new FR-015 check

specs/
├── 056-stage-found-defect-filing/
│   └── data-model.md                              # amended in place (canonical rule + FR-014 note)
└── 057-autonomous-board-loop/                      # UNCHANGED; referenced by the new FR-015 check
```

**Structure Decision**: Single project (this repository's own CI/CD
pipeline). No new top-level directory is introduced; every change lands in
an existing, already-declared home (`.github/actions/`, `.github/scripts/`,
`.github/workflows/`) or amends an existing spec document in place, per
FR-012's single-home requirement and this repository's own "shared logic
has exactly one home" rule.

## Complexity Tracking

Not applicable — no Constitution Check violation requires justification.
