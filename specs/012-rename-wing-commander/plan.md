# Implementation Plan: Rename to Wing Commander

**Branch**: `012-rename-wing-commander` | **Date**: 2026-07-15 | **Spec**: [specs/012-rename-wing-commander/spec.md](./spec.md)

**Input**: Feature specification from `/specs/012-rename-wing-commander/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Replace this product's own branding — "speckit"/"Speckit"/"speckit-action" —
with "Wing Commander" (display) / "wing-commander" (slug) everywhere it names
the product, while preserving honest attribution to the third-party Spec Kit
tool it is built on and leaving Spec Kit's own vendored `/speckit-*`
command/skill interface untouched. The technical approach, developed in
`research.md`, is a coordinated, exhaustive find-and-cross-reference sweep
across four categories: (1) human-facing display text (README, docs,
constitution title), (2) internal machine-referenced identifiers (reusable
workflow filenames — dropping the `reusable-` prefix per FR-009a — wrapper
workflow filenames, action directories, concurrency groups, the self-checkout
path, an OIDC audience string, and a parsed marker comment), (3) the
outward-facing GitHub repository/action reference (already renamed at the
platform level; redirect-backed today, documented for adopters regardless),
and (4) adopter-facing secret/variable interface names, which are a genuine
breaking change shipped behind a new major release tag per the project's
existing versioning contract. Historical `specs/001-011` artifacts and Spec
Kit's own vendored files are explicitly out of scope. No functional pipeline
behavior changes.

## Technical Context

**Language/Version**: N/A — this is a text/filename rename across Markdown,
YAML (GitHub Actions), and JSON configuration; no application code exists.

**Primary Dependencies**: GitHub Actions (`workflow_call` reusable
workflows, composite actions), `anthropics/claude-code-action`, Spec Kit
(`specify init`-managed `.specify/` tree, vendored `/speckit-*` skills) —
none of these dependencies themselves change; only this product's own naming
layered on top of them changes.

**Storage**: N/A

**Testing**: Manual verification per `quickstart.md` — repository-wide
`grep` sweeps for stray old identifiers (scoped to exclude the historical
`specs/001-011` record and the vendored exemption list), `actionlint` +
`release.yml`'s existing invariant-check gate against the renamed workflow
files, and an end-to-end pipeline dry-run on a sample issue to confirm every
stage still triggers and every renamed cross-reference resolves (FR-006,
SC-003). No unit/integration test suite applies to a naming change with no
application logic.

**Target Platform**: GitHub repository (Actions runners, repository UI,
Security/Settings surfaces); no other runtime.

**Project Type**: GitHub Actions pipeline / documentation repository (no
`src/`/`tests/` application tree — see Project Structure below).

**Performance Goals**: N/A — no runtime-performance-sensitive code is
touched; workflow trigger latency and stage behavior are unchanged (spec
Assumption: "no functional behavior... changes").

**Constraints**: Every renamed identifier's cross-references MUST all move
together in one coordinated change per identifier (FR-005, FR-008) — a
partially-renamed identifier is treated as a defect, not an acceptable
interim state; the vendored Spec Kit `/speckit-*` interface and
`.specify/workflows/speckit/` MUST NOT be touched (FR-003, FR-009); the
adopter-breaking secret/variable and published-path renames MUST ship only
behind a new major release tag with mandatory Breaking-changes release
notes (FR-007, FR-010, and the pre-existing `specs/010-reusable-pipeline/
contracts/versioning.md` contract).

**Scale/Scope**: ~40 tracked files touched across `README.md`, `docs/*.md`,
`.specify/memory/constitution.md`, 8 wrapper + 8 reusable workflow files (16
renamed filenames), 3 action directories, `release.yml`'s lint/invariant
gate, and `docs/adoption.md`'s migration section; `specs/001-011/*` (≈50
files) explicitly excluded; zero application source files (none exist).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applies? | Assessment |
|---|---|---|
| I. Guide — Repo Is Its Own First Example | Yes | This feature itself flows through issue #55 → spec (`spec-draft/012-rename-wing-commander`) → this plan → tasks → implementation, dogfooding the pipeline exactly as every prior feature has. Pass. |
| II. Cost-Conscious Model Tiering | Yes | This plan stage runs on `claude-sonnet-5` per the constitution's tiering table; the feature introduces no new agent invocations or stages — it renames identifiers inside existing stages. Pass. |
| III. Simple, GitHub-Native Interaction | Yes | The rename is surfaced entirely through ordinary GitHub artifacts (README, PR titles, issue comments); no new external dashboard or CLI is introduced. Pass. |
| IV. Automation-First | Yes | No new manual step survives beyond the existing human gates (plan PR review, tasks review if configured, implementation PR review, and — new for this feature — the deliberate `workflow_dispatch` release step that was already a manual, deliberate action before this feature). Pass. |
| V. Security — Untrusted Content Is Never Instructions | Yes | No change to trust boundaries, tool allowlists, or authentication mechanism; the App-token flow, least-privilege tool lists, and OWNER/MEMBER/COLLABORATOR gating are unchanged — only the App's *suggested* display name and secret *names* (not values or mechanism) change, and only behind a documented major-version bump. Pass. |
| VI. Portability — Consuming Repo Owns Its Artifacts | Yes | This rename touches this repository's own project-specific artifacts (its constitution, docs, `specs/`, and its own copies of the published workflow files) exactly as Principle VI scopes; nothing about the portability contract itself (how an adopting repo's own `.specify/`/`specs/`/constitution are resolved) changes. Pass. |

No violations. Complexity Tracking is not needed.

**Post-Phase-1 re-check**: `research.md`, `data-model.md`,
`contracts/rename-migration.md`, and `quickstart.md` introduce no new
dependencies, tools, automation, or trust-boundary changes beyond the naming
sweep and the reuse of the pre-existing breaking-release mechanism
(`release.yml`'s `breaking`/`breaking-notes` inputs, already governed by
Principle II/V's model-tiering and least-privilege rules, both unchanged).
All six principles above still pass unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/012-rename-wing-commander/
├── plan.md                    # This file (/speckit-plan command output)
├── research.md                # Phase 0 output (/speckit-plan command)
├── data-model.md              # Phase 1 output (/speckit-plan command)
├── quickstart.md              # Phase 1 output (/speckit-plan command)
├── contracts/                 # Phase 1 output (/speckit-plan command)
│   └── rename-migration.md
├── checklists/
│   └── requirements.md
└── tasks.md                   # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
README.md                                # product-name display text
docs/{adoption,architecture,setup}.md    # product-name display text + identifier cross-references
.specify/memory/constitution.md          # title rename + one Principle VI cross-reference
.github/workflows/
├── wing-commander-{1-intake,2-clarify,3-plan,4-tasks,5-implement,6-finalize,7-cleanup,rebase}.yml   # renamed wrappers (was speckit-*)
├── {intake,clarify,plan,tasks,implement,finalize,cleanup,rebase}.yml                                 # renamed reusable stages (was reusable-*, FR-009a)
├── claude.yml, claude-code-review.yml, lint-workflows.yml   # unaffected — no speckit references
└── release.yml                                              # lint glob + invariant-check grep + tag-message strings updated
.github/actions/
├── wing-commander-context/         # was speckit-context/
├── wing-commander-preflight/       # was speckit-preflight/
└── wing-commander-metrics-summary/ # was speckit-metrics-summary/
.claude/skills/speckit-*/           # UNCHANGED — vendored Spec Kit command interface (FR-003/FR-009 exemption)
.specify/                           # UNCHANGED except constitution.md above — vendored Spec Kit artifacts
specs/001-011-*/                    # UNCHANGED — historical record, explicitly out of scope (research.md)
```

**Structure Decision**: No `src/`/`tests/` application tree exists or is
needed — this repository's "source" is its GitHub Actions workflow/action
YAML and Markdown documentation, and the rename is scoped exactly to the
tree above, split three ways: (1) product-name display text, edited in
place with no filename changes; (2) internal identifiers, requiring
coordinated filename renames (`git mv`) plus every cross-reference site
enumerated in `data-model.md`; (3) the vendored `.claude/skills/speckit-*/`
and `.specify/` trees plus historical `specs/001-011/`, left untouched by
explicit decision.

## Complexity Tracking

*No violations — table not needed.*
