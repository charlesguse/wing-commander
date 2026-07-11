# Implementation Plan: Reusable Pipeline Extraction

**Branch**: `010-reusable-pipeline` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/010-reusable-pipeline/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Extract every pipeline stage (intake, clarify, plan, tasks, implement⟲converge, finalize, cleanup, auto-rebase) from this repository's monolithic workflows into independently consumable `workflow_call` reusable workflows, published from this repository under versioned tags (exact `vX.Y.Z` tags plus a floating `v1` major tag). Adopting repositories write thin, trigger-owning wrapper workflows that call the published stages with their own credentials (OAuth token and/or API key — both accepted; Claude Code's documented precedence applies when both are set) and their own configuration; all event gating, labels, and approval conventions stay in the wrapper. This repository converts its own eight `speckit-*` workflows into the same thin-wrapper shape, calling the reusable stages by local path so every dogfooded run exercises the exact interface offered to adopters, on unreleased head. Cross-repo internals (the `speckit-context` and `speckit-metrics-summary` composite actions) are resolved by checking out the pipeline repository at `github.job_workflow_sha`, eliminating version skew without release-time ref rewriting.

## Technical Context

**Language/Version**: GitHub Actions workflow YAML + POSIX bash steps (no application code)

**Primary Dependencies**: `anthropics/claude-code-action@v1`, `actions/create-github-app-token@v1`, `actions/checkout@v4`, `gh` CLI (runner-provided), GitHub spec-kit v0.12.4 (installed by the *consuming* repository, never bundled — constitution VI)

**Storage**: N/A — all durable state lives in the consuming repository's git data (`specs/NNN-slug/spec-meta.json`, branches, labels)

**Testing**: `actionlint` via `lint-workflows.yml`; dogfooded end-to-end lifecycle runs in this repository (constitution I); per-scenario validation runbook in `quickstart.md`. API-key credential path is verified by code review only (clarified in spec; live verification deferred to adopter feedback)

**Target Platform**: GitHub Actions, `ubuntu-latest` runners; consuming repositories on github.com

**Project Type**: Reusable CI/CD pipeline library — `workflow_call` reusable workflows + composite actions, published via git tags from this repository

**Performance Goals**: N/A (batch automation). Adoption effort is the measured quantity: SC-001 requires issue→spec-PR in a fresh repository in under 60 minutes using only the docs

**Constraints**: GitHub reusable-workflow rules — no expressions in `uses:` refs, ≤4 nesting levels, called workflows run in the caller's context (caller's `github.event`, caller's secrets/vars), `secrets` must be declared or `inherit`; relative `uses: ./...` inside a called workflow resolves against the *caller's* workspace checkout, so cross-repo internals need the `job_workflow_sha` checkout pattern (research.md D3). Constitution II (every agent step declares explicit `--model` and `--max-turns`), V (untrusted-content framing, least-privilege `--allowedTools`, no web tools, no fork-head checkouts), VI (all project artifacts from the consumer's checkout)

**Scale/Scope**: 8 published reusable stage workflows, 2–3 shared composite actions, 8 rewritten thin wrappers in this repository, 1 release workflow, adoption docs (new `docs/adoption.md` + updates to README, `docs/setup.md`, `docs/architecture.md`)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Assessment |
|---|---|---|
| I | Guide — repo is its own first example | **PASS.** US3/FR-007: this repo's wrappers call the published stages; every lifecycle run exercises the adopter interface. Feature itself flows through the pipeline. |
| II | Cost-conscious model tiering | **PASS.** Every stage's model and `--max-turns` become `workflow_call` inputs whose *defaults* are the constitution's tiering (Haiku triage, Opus spec/clarify, Sonnet plan/tasks/implement). Adopters may override (FR-006) — their constitution governs their repo; this repo's wrappers pass no overrides, keeping tiering intact here. |
| III | Simple, GitHub-native interaction | **PASS.** Reusable workflows, tags, and releases are GitHub-native sharing mechanisms (spec assumption 1). No new surfaces for requesters. |
| IV | Automation-first | **PASS.** Stage behavior unchanged; release tagging is automated by a release workflow. One-time adopter setup remains documented manual work (spec assumption 3). |
| V | Security — untrusted content is never instructions | **PASS with design obligation.** Prompt framing, least-privilege `--allowedTools`, no-web-tools, and trusted-ref checkout rules live *inside* the published stages, so adopters inherit them by default. Maintainer-label/commenter gates are trigger-side and move to wrappers — the adopter owns them (FR-002); `docs/adoption.md` must carry the security guidance and the example wrappers must show the gates. This repo's own wrappers retain all existing gates. |
| VI | Portability — consumer owns its artifacts | **PASS.** This feature is principle VI's realization. Published stages read `.specify/`, skills, and `specs/` only from the consumer checkout; FR-009 adds explicit preflight detection. The one self-reference — a stage checking out its *own* pipeline repo at `job_workflow_sha` for shared composite actions — is pipeline mechanics, not project content, and is parameterized (`pipeline-repo` input, defaulting to this repo) rather than hardcoded. |

**Initial gate: PASS** (no violations to justify). **Post-design re-check (after Phase 1): PASS** — the design introduced no new principle tensions; the V obligation is carried by contracts/stage-interfaces.md (wrapper security guidance) and quickstart scenario 2.

## Project Structure

### Documentation (this feature)

```text
specs/010-reusable-pipeline/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── stage-interfaces.md   # workflow_call signature per published stage
│   ├── credentials.md        # dual-credential contract, preflight, precedence
│   └── versioning.md         # tag/release contract, floating major tag
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   │  # Published stages — on: workflow_call only, event-agnostic, all context via inputs
│   ├── reusable-intake.yml
│   ├── reusable-clarify.yml
│   ├── reusable-plan.yml
│   ├── reusable-tasks.yml
│   ├── reusable-implement.yml        # single iteration; re-dispatch loop stays wrapper-side via dispatch input
│   ├── reusable-finalize.yml
│   ├── reusable-cleanup.yml
│   ├── reusable-rebase.yml
│   │  # This repo's thin wrappers — triggers, gates, and vars→inputs wiring only (SC-003)
│   ├── speckit-1-intake.yml
│   ├── speckit-2-clarify.yml
│   ├── speckit-3-plan.yml
│   ├── speckit-4-tasks.yml
│   ├── speckit-5-implement.yml
│   ├── speckit-6-finalize.yml
│   ├── speckit-7-cleanup.yml
│   ├── speckit-rebase.yml
│   ├── release.yml                   # NEW: tag vX.Y.Z, advance floating v1, release notes
│   ├── lint-workflows.yml            # existing, extended to lint reusable-*.yml
│   ├── claude.yml                    # existing, untouched
│   └── claude-code-review.yml        # existing, untouched
├── actions/
│   ├── speckit-context/              # existing; reached cross-repo via job_workflow_sha checkout
│   ├── speckit-metrics-summary/      # existing; same resolution pattern
│   └── speckit-preflight/            # NEW: credential + spec-kit-prerequisite fail-fast checks
docs/
├── adoption.md                       # NEW: prerequisites, minimal full-pipeline example, per-stage reference
├── setup.md                          # updated: adopter-oriented, both credential types
└── architecture.md                   # updated: extraction section becomes current-state
README.md                             # updated: "adopt it today" = thin wrappers + version pin
```

**Structure Decision**: Everything stays in this single repository — GitHub resolves reusable workflows only from `.github/workflows/` of the referenced repo, so published stages and this repo's wrappers are siblings in that directory, distinguished by the `reusable-` prefix and by `on: workflow_call` vs. event triggers. No new repository is created; publishing is done with tags on this one (research.md D1, D6).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations — table intentionally empty.
