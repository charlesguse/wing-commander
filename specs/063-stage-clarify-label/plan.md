# Implementation Plan: The Label Table Tells the Truth — `stage:clarify` Is Either Applied or Retired

**Branch**: `063-stage-clarify-label` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/063-stage-clarify-label/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

`docs/setup.md` documents `stage:clarify` as part of the lifecycle label
taxonomy every adopter is told to create, but no shipped workflow ever
applies it — the only one of eight documented labels with no writer. The
owner's resolution on lifecycle issue #483 (Clarifications, spec.md) is
Direction A: wire it up. This plan adds one new deterministic step each to
`intake.yml` and `clarify.yml`, placed immediately after each stage's
existing clarification-decision step (`Check whether the spec still needs
clarification` / `Determine clarification follow-up outcome`) so the label
write is derived from the exact same single, schema-validated signal that
already decides which callout to post (FR-013; `docs/architecture.md:372-
374`'s "structural fix for #159," now extended to the label). Applying
`stage:clarify` flips out `stage:spec` (FR-012); resolving the questions
flips back (FR-011). Both new steps are best-effort and visibly non-fatal on
a label-write failure (FR-015): a failed `--add-label` warns in the step
summary rather than failing the job the questionnaire was already posted
in.

A new gate, **Gate 105** (`.github/scripts/verify-lifecycle-label-
taxonomy.py`), enforces FR-001/FR-007 going forward: it derives the
documented `stage:*` label set from `docs/setup.md` and the applied set from
every shipped workflow and composite action's `gh issue edit`/`gh issue
create` calls — neither side hardcoded — and fails when a documented label
has no writer and no entry in a new checked-in exemption registry
(`.github/scripts/lifecycle-label-taxonomy-waivers.json`, structurally
identical to the existing `stage-invariant-waivers.json` pattern, Gate 31).
Wiring costs exactly one `run:` step in `lint-workflows.yml` —
`wc_gate_registry.py`'s filename-glob convention means Gate 10 and
`run-local-gates.py` discover it automatically (FR-009; research.md D8).

The one comment this feature makes false — `auto-release.yml:1143-1147`'s
"stage:clarify is never applied as an issue label by any stage workflow" —
is corrected in the same change (FR-005), and the E2E pass-path's stage-
label-timeline assertion gains the conditional `stage:clarify` check
FR-021 requires, reusing (not re-deriving) the existing `auto-release-e2e-
clarify-decision.sh markers` read that the neighboring `clarification_
satisfied` check already trusts, moved earlier in the script so both
consume one read (research.md D5 — the one decision this plan makes without
a further clarification round, reported on the issue).

See [research.md](./research.md) for the full decision record (D1-D8),
[data-model.md](./data-model.md) for the per-stage step contract and the
new gate's derived sets, and [contracts/](./contracts/) for the label-flip
step, the new gate, and the amended E2E assertion.

## Technical Context

**Language/Version**: Bash (`run:` steps inside two existing published
stage workflows, matching every existing label-flip site in this fleet —
`plan.yml:1153-1155`, `:1241`), Python 3 (`.github/scripts/verify-*.py`,
matching every existing gate script) — no new language introduced.

**Primary Dependencies**: `gh` CLI, `jq` (already the sole dependencies of
every existing stage-label flip and of the E2E harness script this feature
amends); `wc_gate_registry.py` (existing, unmodified — Gate 105 is discovered
by it, not registered in it); `wc_shell_harness.py` (existing, reused to
extract and drive the two new steps and the amended E2E script in
isolation, matching `verify-clarification-gating.py`'s own convention).

**Storage**: GitHub issue labels (existing mechanism; this feature adds two
new writer sites for `stage:clarify` and one new writer site in `clarify.yml`
for `stage:spec`, no new label name, no `spec-meta.json` field). One new
checked-in registry file, `.github/scripts/lifecycle-label-taxonomy-
waivers.json` (JSON, structurally identical to `stage-invariant-
waivers.json`).

**Testing**: New `.github/scripts/verify-lifecycle-label-taxonomy.py`
(Gate 105), wired into `.github/workflows/lint-workflows.yml`, following this
repository's established `verify-*.py` + `--self-test` convention (no shared
test framework beyond `wc_shell_harness.py` and `wc_gate_registry.py`).
`verify-clarification-gating.py` (Gate 8) is exercised, not modified, to
confirm the two new steps sit outside its `wanted`-step extraction
(research.md D1). Gate 66 (the two E2E gate-decision scripts' branch
coverage) is exercised, not modified, since this feature adds no new mode
to `auto-release-e2e-clarify-decision.sh`.

**Target Platform**: GitHub Actions, `ubuntu-latest` runner (gate script and
both stage workflows already run here; no new runner requirement).

**Project Type**: Single project — a GitHub Actions reusable-workflow
pipeline component; no application `src`/`tests` split applies.

**Performance Goals**: No added cost on a run that never needs
clarification (the new steps are no-ops there — data-model.md's condition
table). A run that does post a questionnaire pays two additional `gh`
calls (`label create --force`, `issue edit --add-label`) and one additional
best-effort `gh issue edit --remove-label` — the same shape and cost class
`plan.yml`'s existing flip already pays per stage transition.

**Constraints**:
- FR-013: the label decision MUST read the same decision-step output the
  stage's own callout already reads — never a second parse of the agent's
  structured result (research.md D1).
- FR-015: a label-write failure MUST NOT fail the run or suppress the
  questionnaire/readiness callout already posted in the same job — every
  `--add-label` failure is caught explicitly, never left to the step's
  default `bash -eo pipefail` behavior (research.md D2/D3).
- FR-016 (constitution VII): no `workflow_call` input, output, or secret of
  either published stage changes. Both new steps read only inputs/outputs
  those stages already declare or compute.
- Out of Scope: `spec-request`, `model:*`, `disposition:*`, `board:*` labels
  are not covered by Gate 105; retiring `stage:clarify` (Direction B,
  FR-016..FR-020) is not implemented; no historical `specs/` document is
  rewritten (FR-022).

**Scale/Scope**: Two new steps (one per stage: `intake.yml`, `clarify.yml`);
one new gate script and its exemption registry; six documentation sites
audited under FR-006 (four edited, two confirmed already correct —
research.md D6); one amended check inside `auto-release.yml`'s existing
inline verdict script (a comment correction plus a reordered read plus one
new conditional branch — no new script, no new `gh` call).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | Built through the pipeline itself (issue #483 → this spec → this plan → tasks → implement); the new gate is validated the same way every other gate in this repository validates itself (`wc_gate_registry.py`/`wc_shell_harness.py`). | ✅ Pass |
| II. Cost-Conscious Model Tiering | This plan runs at `claude-sonnet-5` (planning-weight default). The feature adds no new agent invocation — every new/changed step is deterministic bash or a Python gate script. | ✅ Pass |
| III. Simple, GitHub-Native Interaction | The label change is visible on the lifecycle issue the requester is already watching, through the same label mechanism every other stage transition already uses. No new interaction surface — SC-004 is exactly this principle restated as a measurable outcome. | ✅ Pass |
| IV. Automation-First | Closes an automation gap: a label the docs promise but no automation delivers. The new steps are fully automatic; a label-write failure is reported (FR-015), never silently assumed to have succeeded. | ✅ Pass |
| V. Security — untrusted content is never instructions | No new untrusted-content path. Both new steps read only this repository's own step outputs, computed from the agent's schema-validated structured result (already trusted for the callout decision) — never `github.event.*` comment body text directly. | ✅ Pass |
| VI. Portability — consuming repo owns its artifacts | The new gate and registry live under `.github/scripts/`, resolved the same way every existing gate is; no bundled or hardcoded repository-specific content. | ✅ Pass |
| VII. Two Interfaces — published contract vs. consuming instrument | No `workflow_call` input, output, or secret of `intake.yml`/`clarify.yml` changes — the new steps are internal to each stage's own job, reading only inputs/outputs already declared or computed inside it. `wing-commander-chain-stop-notice`'s published `stage-label` input contract (specs/041) is unchanged; this feature only makes an existing input do real work. | ✅ Pass |
| VIII. A Green Check Means What It Says | This is the principle FR-007/FR-008/User Story 3 restate at the spec level. Gate 105 is reachable through the gate registry (research.md D8), runs the same subject locally and in CI, is triggered by changes to `docs/setup.md` and every workflow/composite action (already in `lint-workflows.yml`'s `pull_request.paths:` filter), fails loudly rather than vacuously when it cannot read its subject, and every failure branch it ships (contracts/lifecycle-label-taxonomy-gate.md's nine required fixtures) is exercised by a checked-in `--self-test` fixture, including the exact pre-change regression (FR-008) demonstrated live in the implementation PR. | ✅ Pass |
| IX. Judgment That Gates a Durable Action Belongs in Deterministic Code | The label write is deterministic code reading a deterministic step output (FR-013) — never an agent's judgment call folded into the write. Gate 105's documented-vs-applied comparison and its waiver stale-checks are likewise pure code, no model in the loop. | ✅ Pass |
| X. Bounded Autonomy — The Pipeline Works Its Own Board | Not applicable — this feature is a spec-shaped change routed through the full lifecycle (a design trade-off, FR-002, required the owner's call), not a board-loop fix-shaped PR. | N/A |

**Post-Phase-1 re-check**: Unchanged. Phase 1 design (data-model.md,
contracts/, quickstart.md) confirms both new steps read only pre-existing
step outputs local to their own job (no new ambient state, no new
`workflow_call` surface) and that Gate 105's own derivation logic is the
only new compatibility surface this feature adds internally (it is not part
of the published contract — a gate script, not a stage or composite).

## Project Structure

### Documentation (this feature)

```text
specs/063-stage-clarify-label/
├── plan.md                                    # This file (/speckit-plan command output)
├── research.md                                # Phase 0 output (/speckit-plan command)
├── data-model.md                              # Phase 1 output (/speckit-plan command)
├── quickstart.md                              # Phase 1 output (/speckit-plan command)
├── contracts/                                 # Phase 1 output (/speckit-plan command)
│   ├── clarify-label-flip.md                  # the two new steps' shared shape and per-stage behavior
│   ├── lifecycle-label-taxonomy-gate.md        # Gate 105's derivation rules, verdict table, required fixtures
│   └── e2e-clarification-label-assertion.md    # auto-release.yml's amended pass-path check
├── checklists/
│   └── requirements.md                        # already present (intake stage output)
├── spec-meta.json
└── tasks.md                                   # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source code (repository root)

This repository is a GitHub Actions pipeline, not a conventional
library/service — there is no `src`/`tests` split. The real layout this
feature touches:

```text
.github/
├── actions/
│   └── wing-commander-chain-stop-notice/    # UNCHANGED — its existing
│       └── action.yml                       #   stage-label input starts
│                                             #   removing a real label
├── scripts/
│   ├── verify-lifecycle-label-taxonomy.py   # NEW — Gate 105's script
│   ├── lifecycle-label-taxonomy-waivers.json  # NEW — exemption registry
│   │                                         #   (empty/absent at merge —
│   │                                         #   Direction A needs none)
│   └── wc_gate_registry.py                  # UNCHANGED — discovers Gate 105
│                                             #   by filename convention
└── workflows/
    ├── lint-workflows.yml                   # + one Gate 105 run: step
    ├── intake.yml                           # + "Flip stage label for
    │                                         #   clarification" step
    ├── clarify.yml                          # + "Flip stage label for
    │                                         #   clarification" step
    ├── plan.yml                             # UNCHANGED — its two existing
    │                                         #   stage:clarify removal
    │                                         #   lines start doing real
    │                                         #   work with no edit
    ├── wing-commander-2-clarify.yml         # UNCHANGED — its stage:clarify
    │                                         #   trigger disjunct becomes
    │                                         #   reachable with no edit
    └── auto-release.yml                     # comment corrected + read
                                              #   reordered + conditional
                                              #   stage:clarify check
                                              #   (FR-005, FR-021)

docs/
├── setup.md          # UNCHANGED (research.md D6 — already correct)
├── architecture.md   # one clause added (:372-374) — label write named
│                      #   alongside the callout as a second consumer of
│                      #   the same signal
└── adoption.md        # two "Side effects" rows gain the conditional
                        #   label outcome (intake :1125, clarify :1163)
```

**Structure Decision**: Two new inline steps in the two stages the spec
names (no new composite action — research.md D1 rejects a shared composite
as disproportionate for two ~10-line, differently-shaped bodies); one new
self-contained gate script plus its exemption registry, wired by one
`lint-workflows.yml` line (research.md D7/D8); one amended check inside an
existing inline script (`auto-release.yml`), no new script or `gh` call;
four documentation edits, two sites confirmed already correct and left
untouched (research.md D6). No new top-level directory, no change to any
stage's declared `workflow_call` surface, no change to `plan.yml`,
`wing-commander-2-clarify.yml`, or `wing-commander-chain-stop-notice`
(all three become correct by virtue of `stage:clarify` finally having a
writer, not by any edit of their own).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — table intentionally omitted.
