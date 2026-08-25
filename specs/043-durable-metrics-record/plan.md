# Implementation Plan: Durable Agent Run Metrics — Emit, Persist, and Roll Up What the Pipeline Spends

**Branch**: `spec/043-durable-metrics-record` | **Date**: 2026-08-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/043-durable-metrics-record/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Every agent step already extracts cost, tokens, and turns from its
execution transcript to render one `$GITHUB_STEP_SUMMARY` table, then
discards the values — the only durable copy is the raw transcript
artifact, which inherits a 90-day repository default and starts expiring
2026-10-03. This plan extends `wing-commander-metrics-summary` (the
composite action every stage already calls) to also write a normalized,
versioned JSON record from that same extraction (closing FR-004's
single-source requirement by construction, not convention), uploads it
alongside the transcript at all ~14 existing call sites, and adds a new
published `metrics-persist.yml` workflow — triggered out of band via
`workflow_run` by a new `wing-commander-metrics-persist.yml` wrapper —
that fetches a concluded run's records, appends them with bounded
retry-on-contention to a dedicated orphan `metrics` branch's
`records.jsonl`, and updates a machine-owned rollup region on the spec's
lifecycle issue. A second, in-band per-run cost line is appended to each
stage's existing status comment directly, decoupled from persistence
latency. Five new deterministic gates close the `.github/actions/**`
layer-split gap (#149) for this feature's own new composites, assert
schema conformance and unknown-version tolerance, drive the
contention-retry loop against a fixture, and assert every transcript
upload site (16, not the requester's assumed 14) declares
`retention-days: 90`. No piece adds an agent invocation (FR-040a) —
emission, persistence, and the rollup are all deterministic bash/jq/git,
matching constitution IX.

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps and composite
`action.yml` files), YAML (workflow/action definitions), `jq` for JSON,
`git`/`gh` for the store and cross-run artifact retrieval — identical
toolchain to every existing composite and gate in this repository; no
new language. Gate scripts follow the existing repository split
(Python for structural/YAML-aware checks, bash for behavioral/fixture-driven
ones) case by case, matching the closest existing gate each new one most
resembles.

**Primary Dependencies**: GitHub Actions (`workflow_call` stages and
composites), the GitHub CLI (`gh`) and REST API for cross-run job/artifact
discovery (the exact pattern `watchdog.yml`'s "Collect: execution-output
artifacts" step already uses), `git` for the append-with-retry store
writes, and this repository's own `wing-commander-metrics-summary`
(extended in place, research.md R1), `wing-commander-turn-ceiling`,
`wing-commander-lifecycle-gate` (its bounded-retry shape is the template
for R7, not code it calls), and `wc_published_stages.py` (unmodified —
the new `metrics-persist.yml` is picked up by its existing
`workflow_call` derivation with no edit needed).

**Storage**: A dedicated orphan git branch (`metrics` by default,
wrapper-configurable), one append-only `records.jsonl` file — see
research.md R5 and data-model.md. No database, no external service.

**Testing**: This repository's existing gate-registry convention —
`.github/scripts/verify-*.py`/`.sh` scripts wired into `lint-workflows.yml`
and runnable identically via `run-local-gates.py`. Five new gates
(research.md R12, contracts/gate-coverage-043.md), each with checked-in
fixtures, no manual-only demonstration (constitution VIII).

**Target Platform**: GitHub Actions runners (`ubuntu-latest` class, this
repository's existing default), any repository that adopts the published
stage workflows and composite actions (constitution VI/VII).

**Project Type**: GitHub Actions reusable-workflow pipeline (not an
application with a conventional `src/`/`tests/` split) — this feature
adds/extends workflow, composite-action, and gate-script files under
`.github/`, plus its own `specs/043-durable-metrics-record/` planning
artifacts.

**Performance Goals**: Emission adds negligible per-step cost (one more
`jq` pass over an already-read transcript, one more small file write).
Persistence runs out of band, after the pipeline run it reports on has
already concluded, so it adds zero latency to any stage; its own
append-with-retry loop is bounded at 8 attempts (research.md R7) so a
single persistence run terminates in a bounded number of git operations
even under sustained contention.

**Constraints**: No agent invocation anywhere in this feature
(FR-040a/constitution IX) — every new/changed step is deterministic.
Zero branches the pipeline builds from may be modified by persistence
(FR-015); zero commits to the default branch by the bot (constitution V,
FR-015). No adopter wrapper edit required to receive emission or the
retention declaration (FR-034/FR-036); persistence remains entirely
opt-in via the wrapper's destination configuration (FR-002/FR-013/FR-014).

**Scale/Scope**: ~14 existing `wing-commander-metrics-summary` call
sites gain a record-upload step and (at ~13 of them) a per-run cost
line; 16 existing transcript `upload-artifact` sites gain a declared
retention period; one new composite action, one new published workflow,
one new wrapper workflow, five new gate scripts with fixtures. Store
growth: on the order of a dozen-plus JSONL lines per specification,
indefinitely (research.md R5 — a flat file comfortably absorbs this).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | This feature is itself built through intake → plan → tasks → implement, the same pipeline it instruments. | Pass |
| II. Cost-Conscious Model Tiering | This plan was produced at the planning tier (`claude-sonnet-5`). The feature itself adds zero new agent invocations to instrument (FR-040a) — nothing here is subject to tiering because nothing here is a model call. | Pass |
| III. Simple, GitHub-Native Interaction | Directly served: Tier 2's rollup is exactly "the lifecycle of a spec is legible from its original issue alone" applied to cost, with no new dashboard, CLI, or external surface (Out of Scope explicitly excludes any dashboard). | Pass |
| IV. Automation-First | Emission and persistence both require zero manual steps once the wrapper is configured; persistence failure is reported loudly (FR-019), never silently assumed away. | Pass |
| V. Security — untrusted content is never instructions | The new pieces parse only GitHub API/CLI metadata and already-trusted transcript JSON — never issue/comment bodies as instructions. `metrics-persist.yml` self-checks-out the pipeline repo via the same trusted-ref pattern every stage uses (never a fork PR head); authenticates via the existing GitHub App token, never a new PAT; the bot still never approves or merges anything (FR-015 reasserts this for persistence specifically). | Pass |
| VI. Portability — consuming repo owns its artifacts | The destination (branch/path) is wrapper-supplied, never bundled with or inferred from Wing Commander itself (FR-013/FR-014); an adopter with no wrapper gets emission only, zero writes to their repository. | Pass |
| VII. Two Interfaces | This is the organizing constraint of the whole design (research.md R1-R12): emission and persistence are published, take every fact as a declared input, and read no `github.event.*`/`vars.*`; the wrapper is the only place a trigger or destination is chosen. | Pass |
| VIII. A Green Check Means What It Says | Five new gates close the `.github/actions/**` gap this feature would otherwise be invisible inside (issue #149), each fixture-backed, each wired the standard single-registration way (research.md R12, contracts/gate-coverage-043.md). | Pass (new coverage is part of this plan's own scope, not deferred) |
| IX. Judgment That Gates a Durable Action Belongs in Deterministic Code | Schema conformance, the multi-model sum invariant, contention-retry de-dup, and unknown-schema-version handling are all deterministic code paths (contracts/metrics-record-schema.md's invariant, FR-041) — no agent ever decides whether a record is well-formed enough to persist. | Pass |

No violations. Complexity Tracking below is empty.

## Project Structure

### Documentation (this feature)

```text
specs/043-durable-metrics-record/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This repository has no `src`/`tests` split — it is a GitHub Actions
pipeline. This feature's concrete changes:

```text
.github/
├── actions/
│   ├── wing-commander-metrics-summary/
│   │   └── action.yml                  # extended: record-path/stage/spec-dir/
│   │                                    # spec-issue inputs, record-json/record-key
│   │                                    # outputs (contracts/emission-contract.md)
│   └── wing-commander-metrics-persist/
│       └── action.yml                  # new: discover → retrieve → validate →
│                                        # append-with-retry → rollup
│                                        # (contracts/persist-workflow.md)
├── workflows/
│   ├── metrics-persist.yml             # new: workflow_call-only published stage
│   ├── wing-commander-metrics-persist.yml  # new: wrapper — workflow_run +
│   │                                    # workflow_dispatch trigger, destination vars
│   │                                    # (contracts/wrapper-contract.md)
│   ├── intake.yml, clarify.yml, plan.yml, tasks.yml, implement.yml,
│   │   finalize.yml, cleanup.yml, rebase.yml, watchdog.yml,
│   │   pr-conversation.yml             # changed: record-upload step + per-run
│   │                                    # cost line at each existing
│   │                                    # wing-commander-metrics-summary call site
│   ├── auto-update-spec-kit.yml        # changed: retention-days only (Story 4;
│   │                                    # not a metrics-summary call site)
│   └── lint-workflows.yml              # changed: five new gate `run:` lines
└── scripts/
    ├── verify-actions-layer-invariants.py       # new (extends #149's gap)
    ├── verify-metrics-record-schema.py          # new
    ├── verify-metrics-schema-version-tolerance.py  # new
    ├── verify-metrics-persist-retry.sh          # new
    ├── verify-transcript-retention-declared.py  # new
    └── fixtures/
        └── metrics-*/                  # new: checked-in fixtures per
                                         # data-model.md's "Gate fixtures" table

specs/043-durable-metrics-record/
├── plan.md, research.md, data-model.md, quickstart.md   # this plan
├── contracts/
│   ├── metrics-record-schema.md
│   ├── emission-contract.md
│   ├── persist-workflow.md
│   ├── wrapper-contract.md
│   └── gate-coverage-043.md
└── tasks.md                            # /speckit-tasks output — not produced here
```

**Structure Decision**: Extend the existing composite
(`wing-commander-metrics-summary`) rather than add a parallel one
(research.md R1); add exactly one new composite
(`wing-commander-metrics-persist`) and one new published workflow
(`metrics-persist.yml`) for the mechanism, plus one new wrapper for the
trigger and destination (research.md R11) — the three pieces spec.md's
own layer-split paragraph names, no more. Gate scripts follow the
existing `.github/scripts/verify-*.py`/`.sh` naming convention so they
are picked up by `verify-gate-wiring.py`'s existing derivation with no
registry edit.

## Complexity Tracking

*No Constitution Check violations — this section intentionally left empty.*
