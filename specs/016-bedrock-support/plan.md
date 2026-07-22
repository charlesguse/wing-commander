# Implementation Plan: AWS Bedrock Support for Consuming Repositories

**Branch**: `016-bedrock-support` | **Date**: 2026-07-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/016-bedrock-support/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Consuming repositories cannot currently route the pipeline's agent calls
through AWS Bedrock — every stage only accepts an Anthropic API key or OAuth
token. This plan adds a `use-bedrock` opt-in flag (default off) plus
`aws-role-arn`/`aws-region` inputs to every agent-running stage's
`workflow_call` interface, wires `use-bedrock` through to
`anthropics/claude-code-action`'s own `use_bedrock` input at every agent call
site, and adds a new shared composite
(`wing-commander-bedrock-credentials`) that assumes the given AWS role via
OIDC (`aws-actions/configure-aws-credentials`, no long-lived AWS secrets)
only when Bedrock is enabled. The existing `wing-commander-preflight`
composite gains a branch: when Bedrock is enabled, it stops requiring an
Anthropic credential and instead requires `aws-role-arn`/`aws-region`,
failing fast and by name if either is missing. Bedrock model identifiers are
pure pass-through through the existing per-stage `model` inputs — no new
model-mapping mechanism. When `use-bedrock` is left unset, nothing about
today's behavior changes (no new required input, no new AWS call, no
different code path for the Anthropic-credential check). See
[research.md](./research.md) for the seven design decisions this rests on and
[contracts/bedrock-provider.md](./contracts/bedrock-provider.md) for the full
interface contract.

## Technical Context

**Language/Version**: GitHub Actions workflow YAML + Bash (composite
`run:` steps) — the pipeline itself has no application language/runtime; this
feature adds no new language to the project.

**Primary Dependencies**: `anthropics/claude-code-action@v1` (already in use
everywhere; this feature exercises its existing `use_bedrock` input for the
first time — research D1) and `aws-actions/configure-aws-credentials`
(new dependency, pinned to a release tag/SHA per this repo's existing
third-party-action pinning practice, wrapped in the new
`wing-commander-bedrock-credentials` composite — research D2).

**Storage**: N/A — no persisted state; Model Provider Selection and Bedrock
Configuration are both per-invocation values (see data-model.md), never
written to `spec-meta.json` or any other lifecycle record.

**Testing**: `.github/workflows/lint-workflows.yml` (YAML-parse + `bash -n`
static check over every workflow file) is the only automated check in this
repository's own CI and must continue to pass unchanged. There is no live
Bedrock round-trip test in this repository (spec Assumption: end-to-end
validation happens in a separate consuming repository). Validation here is
the manual/scripted scenario walkthrough in [quickstart.md](./quickstart.md)
(default-path regression, both missing-config failure messages, Bedrock-
without-Anthropic-credential, both-configured precedence, cross-stage
consistency grep, model-identifier pass-through).

**Target Platform**: GitHub Actions reusable (`workflow_call`) workflows
running on `ubuntu-latest` runners, consumed cross-repository by adopters.

**Project Type**: Infrastructure-as-configuration — GitHub Actions reusable
workflows and composite actions, not a conventional application with a
`src/`/`tests/` split. See Project Structure below for the actual layout.

**Performance Goals**: Not applicable in the conventional sense. When
`use-bedrock` is unset, zero added latency or network calls (the entire new
composite is gated behind an `if:`). When enabled, one additional STS
`AssumeRoleWithWebIdentity` call per job (via `configure-aws-credentials`) —
negligible relative to an agent turn's own latency.

**Constraints**:
- No long-lived AWS secrets — OIDC role assumption only (FR-003).
- Strictly additive interface change — no existing input, secret, or output
  of any stage is renamed, removed, or has its default changed (SC-002).
- Preflight failures for missing Bedrock configuration must be deterministic,
  pre-agent, and name the specific missing input(s) (FR-008, FR-009).
- The Bedrock flag and its configuration must only ever originate from
  trusted `workflow_call` inputs — never inferred from issue/comment content
  (FR-007, constitution V).
- The same enablement surface (same input names, same defaults, same
  preflight behavior) must appear identically across all nine agent-running
  stages (FR-002).

**Scale/Scope**: 9 stage workflow files (`intake`, `clarify`, `plan`, `tasks`,
`implement`, `finalize`, `cleanup`, `rebase`, `watchdog`), each gaining 3
`workflow_call` inputs and one new composite `uses:` step per job containing
an agent step; ~13 existing `anthropics/claude-code-action` call sites each
gain one `with:` line; 1 existing composite (`wing-commander-preflight`)
extended with 3 inputs and a branch in its credential-check logic; 1 new
composite (`wing-commander-bedrock-credentials`). Documentation updates
(`docs/adoption.md`, `docs/setup.md`, `docs/architecture.md`, and a
companion note alongside `specs/010-reusable-pipeline/contracts/
credentials.md`) are scoped to the implementation stage, not this plan's own
artifacts.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | This feature is itself built through the pipeline (issue #83 → spec 016 → this plan → tasks → implement), and once merged is available to every future dogfooded run of this repo's own wrappers. | ✅ Pass |
| II. Cost-Conscious Model Tiering | This feature adds no new agent invocation and changes no stage's model tiering; it only changes which *backend* serves the existing, already-tiered `model` inputs (FR-006). The plan stage itself runs at `claude-sonnet-5` per the existing `plan.yml` default. | ✅ Pass — no tiering change |
| III. Simple, GitHub-Native Interaction | No new dashboards, CLIs, or out-of-GitHub surfaces; the flag is a `workflow_call` input set in a wrapper workflow, exactly like every other stage input today. | ✅ Pass |
| IV. Automation-First | Enabling/disabling Bedrock is fully automated once the wrapper sets the inputs; failures (missing AWS config) are reported via the existing deterministic preflight step, not a silent skip. | ✅ Pass |
| V. Security — untrusted content is never instructions | `use-bedrock`/`aws-role-arn`/`aws-region` are `workflow_call` inputs only, settable exclusively by the calling wrapper's own `with:` block — never derived from issue/comment text (FR-007). No change to tool allowlists, web-tool disablement, or trusted-ref checkout rules. | ✅ Pass |
| VI. Portability — consuming repo owns its artifacts | AWS role ARN/region are consumer-owned, trusted configuration supplied through the pipeline's existing calling surface (same as `model`, `pipeline-repo`) — nothing project-specific is bundled into or read from the pipeline repository itself. | ✅ Pass |

No violations. Complexity Tracking is not needed.

**Post-Phase-1 re-check**: Unchanged — the Phase 1 design (data-model.md,
contracts/bedrock-provider.md, quickstart.md) introduces no new agent
invocation, no new untrusted-input path, and no new persisted state; all six
gates above still hold after design.

## Project Structure

### Documentation (this feature)

```text
specs/016-bedrock-support/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── bedrock-provider.md
├── checklists/
│   └── requirements.md  # already present (intake stage output)
├── spec-meta.json
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source code (repository root)

This repository is a GitHub Actions pipeline, not a conventional
library/service — there is no `src/`/`tests/` split. The real layout this
feature touches:

```text
.github/
├── workflows/
│   ├── intake.yml            # + use-bedrock/aws-role-arn/aws-region inputs,
│   ├── clarify.yml           #   + wing-commander-bedrock-credentials step,
│   ├── plan.yml               #   + use_bedrock passed to every
│   ├── tasks.yml               #   anthropics/claude-code-action call site
│   ├── implement.yml           #   in the file (one composite invocation per
│   ├── finalize.yml            #   job containing an agent step — implement.yml
│   ├── cleanup.yml             #   and watchdog.yml need it more than once,
│   ├── rebase.yml              #   see research D2)
│   └── watchdog.yml
├── actions/
│   ├── wing-commander-preflight/
│   │   └── action.yml        # + use-bedrock/aws-role-arn/aws-region inputs,
│   │                         #   branch the credential-invariant check
│   │                         #   (research D3)
│   ├── wing-commander-bedrock-credentials/   # NEW composite (research D2)
│   │   └── action.yml        # conditional aws-actions/configure-aws-credentials
│   ├── wing-commander-context/               # unchanged
│   └── wing-commander-metrics-summary/       # unchanged
└── (wing-commander-1-intake.yml ... wing-commander-8-watchdog.yml)
                               # this repo's own dogfooded wrappers — unchanged
                               # by this feature (it does not enable Bedrock
                               # for the pipeline's own runs; adopters opt in
                               # independently)

docs/
├── adoption.md               # Credentials section gains a Bedrock subsection
│                              #   + stage reference table gains the 3 inputs
├── setup.md                  # Repository secrets/variables tables gain rows
└── architecture.md           # Model tiering section documents Bedrock
                               #   pass-through interaction

specs/010-reusable-pipeline/contracts/credentials.md
                               # "Non-goals" line currently says Bedrock is
                               #   out of scope for v1 — needs a companion
                               #   note pointing at this feature's contract
                               #   once implemented (implementation-stage
                               #   edit, not a plan-stage edit)
```

**Structure Decision**: No new top-level directories. The feature is
implemented entirely within the existing `.github/workflows/` (9 files) and
`.github/actions/` (1 extended composite + 1 new composite) layout already
established by this pipeline, plus documentation updates under `docs/` and a
cross-reference update to the specs/010 credentials contract — all scoped to
the implementation stage, consistent with constitution VI (pipeline-specific
mechanics live in `.github/`, never in application `src/`).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — table intentionally omitted.
