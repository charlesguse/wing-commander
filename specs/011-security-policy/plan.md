# Implementation Plan: SECURITY.md Vulnerability-Reporting Policy

**Branch**: `011-security-policy` | **Date**: 2026-07-12 | **Spec**: [specs/011-security-policy/spec.md](./spec.md)

**Input**: Feature specification from `/specs/011-security-policy/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Add a single root-level `SECURITY.md` so GitHub surfaces it as the repository's security policy. The document directs reporters to GitHub's private vulnerability reporting (Security tab → "Report a vulnerability") instead of public issues, and states plainly that pipeline runs execute Claude agents with repository write access via a GitHub App, so credential-handling reports (leaked tokens, overly broad permissions) are explicitly in scope. The technical approach is entirely a documentation authoring task: one Markdown file, one H1 heading, at most three short paragraphs, no other files touched.

## Technical Context

**Language/Version**: N/A — Markdown documentation only, no code

**Primary Dependencies**: N/A

**Storage**: N/A

**Testing**: Manual review against FR-001…FR-007 / SC-001…SC-004 (heading count, paragraph count, presence of the four required disclosures, no other files changed). No automated test suite applies to a single static Markdown file.

**Target Platform**: GitHub repository UI (Security tab / repository root file listing)

**Project Type**: Single documentation file (no source tree, no build, no runtime)

**Performance Goals**: N/A

**Constraints**: File MUST be named `SECURITY.md` and live at the repository root (GitHub's convention for security-policy discovery); MUST contain exactly one top-level heading and no more than three body paragraphs (FR-006); MUST NOT modify or create any other file (FR-007)

**Scale/Scope**: 1 new file, ~3 short paragraphs

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applies? | Assessment |
|---|---|---|
| I. Guide — Repo Is Its Own First Example | Yes | This feature itself flows through issue #45 → spec (`spec-draft/011-security-policy`) → this plan → tasks → implementation, dogfooding the pipeline. Pass. |
| II. Cost-Conscious Model Tiering | Yes | This plan stage runs on `claude-sonnet-5` per the constitution's tiering table; no additional agent invocations are introduced by the feature itself (it is a static doc, not a pipeline capability). Pass. |
| III. Simple, GitHub-Native Interaction | Yes | The feature's entire purpose is to point reporters at a GitHub-native mechanism (private vulnerability reporting) instead of a custom channel. Pass. |
| IV. Automation-First | Yes | No manual step survives beyond the existing human gates (plan PR review, implementation PR review) already defined by the pipeline. Pass. |
| V. Security — Untrusted Content Is Never Instructions | Yes | Directly advances this principle by giving reporters a private, non-public channel and explicitly scoping in the GitHub App's write-access/credential risk surface the principle itself calls out. No new tool access or automation is introduced. Pass. |
| VI. Portability — Consuming Repo Owns Its Artifacts | Yes | `SECURITY.md` is repository-specific content for the speckit-action repo itself, authored and stored in this checkout like any other spec artifact; nothing is bundled into or resolved from a shared/reusable path. Pass. |

No violations. Complexity Tracking is not needed.

**Post-Phase-1 re-check**: research.md, data-model.md, contracts/, and
quickstart.md introduce no new dependencies, tools, or automation beyond the
static Markdown file itself. All six principles above still pass unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/011-security-policy/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── security-md-convention.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
SECURITY.md   # new file, repository root — the entire deliverable
```

**Structure Decision**: No `src/`, `tests/`, or application structure applies. The
feature adds exactly one file, `SECURITY.md`, at the repository root, alongside
existing root-level docs such as `README.md`. This is the location GitHub requires
for a repository to surface a security policy in its Security tab.

## Complexity Tracking

*No violations — table not needed.*
