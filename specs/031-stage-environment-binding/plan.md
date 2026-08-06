# Implementation Plan: Bind Pipeline Stages to a Deployment Environment

**Branch**: `031-stage-environment-binding` | **Date**: 2026-08-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/031-stage-environment-binding/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Adopters have no way to gate an expensive stage behind a GitHub deployment
environment's protection rules (required reviewer, wait timer, branch/tag
policy, custom App rule), and cannot add that gate from their own wrapper —
`jobs.<job_id>.environment` is only legal inside the *called* workflow, and
`on.workflow_call` will not accept it as an input. This plan adds two optional
`workflow_call` inputs — `environment` (string, default `""`) and
`environment-deployment` (boolean, default `true`) — to every one of this
repository's ten published `workflow_call`-only stage workflows, and binds
every job in each of those files to the named environment via the mapping
form:

```yaml
environment:
  name: ${{ inputs.environment }}
  deployment: ${{ inputs.environment-deployment }}
```

`environment:` is a job attribute, not a step, so it structurally applies
before any step in the job — including the existing preflight check and any
agent step — with no reordering and no composite-action changes. An empty
name is a verified true no-op (identical to omitting the key). `deployment:
false` is a verified, real (if informally documented) sub-key that keeps the
environment's protection rules in force while suppressing the deployment
record GitHub would otherwise create. Both behaviors — plus the mapping
form's acceptance of an expression in `name` and GitHub's create-on-reference
behavior for a name that doesn't yet exist — were empirically probed against
GitHub-hosted runners on 2026-08-05
([charlesguse/wc-env-probe](https://github.com/charlesguse/wc-env-probe));
every occurrence added in implementation must carry a comment pointing back
to that evidence (FR-013), since none of the four is documented by GitHub in
a form this plan can cite as a stable public spec. No composite action, no
secret, no `permissions:` block, and no existing input/output changes. See
[research.md](./research.md) for the decisions this rests on and
[contracts/environment-binding.md](./contracts/environment-binding.md) for
the full interface contract.

## Technical Context

**Language/Version**: GitHub Actions workflow YAML — the pipeline itself has
no application language/runtime; this feature adds no new language to the
project.

**Primary Dependencies**: None new. No new third-party action, no new shared
composite under `.github/actions/**` — the entire feature is expressed
through GitHub Actions' own native job-level `environment:` key (mapping
form), which every stage workflow can already declare without any additional
`uses:` dependency.

**Storage**: N/A — no persisted state. The environment name and
deployment-record flag are per-invocation `workflow_call` input values, never
written to `spec-meta.json` or any other lifecycle record (spec edge case:
"no other new artifact appears anywhere in the repository").

**Testing**: `.github/workflows/lint-workflows.yml` (YAML-parse + `bash -n`
static check) must continue to pass unchanged over all ten files.
`release.yml`'s Gate 1a (`actionlint`) currently lints only 8 of the 10
published stage files (a pre-existing gap tracked by issue #149, out of scope
here) — implementation must confirm the new `environment:` mapping form and
its `deployment` sub-key parse cleanly under the pinned actionlint 1.7.7 for
at least those 8, since `deployment` is not part of any GitHub-published
schema this plan can point to (research D8 risk). Beyond lint, only the
empty-input no-op (User Story 2) is mechanically verifiable in this
repository — a cross-file consistency grep, mirroring
`specs/016-bedrock-support/quickstart.md`'s Scenario 5. Every protection-rule
scenario (required reviewer, wait timer, branch policy, deployment-record
suppression) requires a scratch adopter repository per the spec's own
Assumption and is out of this repository's CI.

**Target Platform**: GitHub Actions reusable (`workflow_call`) workflows
running on `ubuntu-latest` runners, consumed cross-repository by adopters.

**Project Type**: Infrastructure-as-configuration — GitHub Actions reusable
workflows, not a conventional application with a `src/`/`tests/` split. See
Project Structure below for the actual layout.

**Performance Goals**: Not applicable in the conventional sense. When
`environment` is left unset, zero added latency, zero added network calls,
and zero behavioral difference (SC-001) — GitHub evaluates the (empty,
no-op) job attribute the same way it evaluates every other job field today.
When set, whatever latency GitHub's own environment-protection evaluation
adds is entirely outside this pipeline's control (FR-006 — the pipeline adds
no waiting logic of its own).

**Constraints**:
- Strictly additive interface change — no existing input, secret, or output
  of any stage is renamed, removed, or has its default changed.
- The same two inputs (same names, types, defaults) must appear identically
  across all ten stage files (FR-001, FR-002).
- The environment name must be the sole source of the binding — never
  defaulted, never looked up from `vars.*`, never derived from ambient
  repository state (FR-011, constitution VII).
- Binding must take effect before any preflight or agent step (FR-005) —
  satisfied structurally by placing `environment:` at the job level, never by
  reordering steps.
- The pipeline must add no approval/wait/gating logic, no existence
  validation, and no lifecycle-issue "pending" reporting of its own (FR-006,
  FR-007, FR-009).

**Scale/Scope**: 10 published `workflow_call`-only stage workflow files —
`intake`, `clarify`, `plan`, `tasks`, `implement`, `finalize`, `cleanup`,
`rebase`, `watchdog`, and `auto-update-spec-kit` (research D1 explains why
the count is ten, not the "nine" still written in `docs/architecture.md` and
the constitution's Principle VII prose — a documentation-drift finding of
this plan, not something this feature's scope requires fixing). Each file
gains 2 new `workflow_call` inputs (20 new input declarations total) and one
`environment:` mapping block per job — roughly 40 jobs across the 10 files by
a heuristic count of top-level `jobs.<id>:` keys; exact per-file enumeration
is deferred to `tasks.md`. Zero composite-action changes, zero secret
changes. Documentation updates (`docs/adoption.md`, `docs/setup.md`,
`specs/010-reusable-pipeline/contracts/stage-interfaces.md`) are scoped to
the implementation stage, not this plan's own artifacts — matching the
`016-bedrock-support` precedent.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | Built through the pipeline itself (issue #171 → spec 031 → this plan → tasks → implement). The capability ships to every stage, including this repo's own; **not yet dogfooded** by any of this repo's own `wing-commander-*.yml` wrappers, because doing so requires an actual deployment environment configured in this repository's own Settings (a human, out-of-band action), and no such environment exists yet — recorded here per the constitution's bootstrap-phase allowance, not silently skipped. |
| II. Cost-Conscious Model Tiering | This plan runs at `claude-sonnet-5` (`plan.yml`'s default, planning-weight). The feature adds no new agent invocation and changes no stage's model tiering — it only adds an optional pre-agent gate. | ✅ Pass |
| III. Simple, GitHub-Native Interaction | The entire mechanism *is* a GitHub-native surface (deployment environments, reviewed the same way a PR is) — no external dashboard, no new CLI, nothing outside GitHub. | ✅ Pass |
| IV. Automation-First | The pipeline adds no manual step of its own; an adopter who opts in is choosing GitHub's own approval surface deliberately. A pending gate is silent by design (FR-009, spec edge case) rather than "manual step reported explicitly" — a deliberate, spec-scoped exception, not an omission (Out of Scope: "Reporting 'waiting for approval'... deliberate for now"). | ✅ Pass, with the documented exception above |
| V. Security — untrusted content is never instructions | The environment name and deployment-record flag arrive strictly as `workflow_call` inputs set in the calling wrapper's own `with:` block — never derived from `github.event.*`, `vars.*`, issue/comment text, or any other ambient state (FR-011). No change to tool allowlists, web-tool disablement, trusted-ref checkout, or App-only authentication. | ✅ Pass |
| VI. Portability — consuming repo owns its artifacts | The named environment is owned entirely by the adopter's own repository Settings; the pipeline stores nothing about it (no `spec-meta.json` field, no other artifact). | ✅ Pass |
| VII. Two Interfaces — published contract vs. consuming instrument | **Deliberate, registered deviation** (see Complexity Tracking): the gate must live in the *stage* (published contract), not the wrapper, because GitHub itself makes `jobs.<job_id>.environment` illegal in a job that calls a reusable workflow and illegal as an `on.workflow_call` input — there is no wrapper-side alternative to reject in favor of. The other half of the principle holds: the stage never discovers an environment on its own (FR-011). | ⚠️ Deviation — justified below |

**Post-Phase-1 re-check**: Unchanged — the Phase 1 design (data-model.md,
contracts/environment-binding.md, quickstart.md) introduces no new agent
invocation, no new untrusted-input path, and no new persisted state; all
seven rows above still hold after design. The Principle VII deviation is
unavoidable by construction (research D2), not merely convenient, so Phase 1
does not change its justification.

## Project Structure

### Documentation (this feature)

```text
specs/031-stage-environment-binding/
├── plan.md                          # This file (/speckit-plan command output)
├── research.md                      # Phase 0 output (/speckit-plan command)
├── data-model.md                    # Phase 1 output (/speckit-plan command)
├── quickstart.md                    # Phase 1 output (/speckit-plan command)
├── contracts/                       # Phase 1 output (/speckit-plan command)
│   └── environment-binding.md
├── checklists/
│   └── requirements.md              # already present (intake stage output)
├── spec-meta.json
└── tasks.md                         # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source code (repository root)

This repository is a GitHub Actions pipeline, not a conventional
library/service — there is no `src/`/`tests/` split. The real layout this
feature touches:

```text
.github/
└── workflows/
    ├── intake.yml                  # + environment/environment-deployment
    ├── clarify.yml                 #   workflow_call inputs, + environment:
    ├── plan.yml                    #   mapping block on every job in the
    ├── tasks.yml                   #   file (research D2/D5) — no other
    ├── implement.yml               #   step, composite, or job reordering
    ├── finalize.yml                #   changes
    ├── cleanup.yml                 #
    ├── rebase.yml                  #
    ├── watchdog.yml                #
    └── auto-update-spec-kit.yml    #   included per research D1

.github/actions/**                  # UNCHANGED — no composite action needs
                                     #   to know about the environment binding;
                                     #   it is a job attribute, not a step
(wing-commander-1-intake.yml ... wing-commander-8b-watchdog-self.yml)
                                     # this repo's own dogfooded wrappers —
                                     #   UNCHANGED by this feature (constitution
                                     #   I note above: not yet dogfooded, no
                                     #   environment configured in this repo's
                                     #   own Settings yet)

docs/
├── adoption.md                     # implementation-stage edit: new
│                                    #   "Deployment environments" section
│                                    #   (FR-012's five documented caveats)
│                                    #   + Stage reference intro bullet
├── setup.md                        # implementation-stage edit: private-repo
│                                    #   Team/Pro prerequisite note
└── architecture.md                 # implementation-stage edit (optional):
                                     #   the Principle VII deviation this
                                     #   feature registers could join the
                                     #   existing watchdog-vars.* exception
                                     #   paragraph, per constitution I

specs/010-reusable-pipeline/contracts/stage-interfaces.md
                                     # implementation-stage edit: Common
                                     #   inputs table gains the two rows
                                     #   (same convention 016-bedrock-support
                                     #   followed for use-bedrock/aws-*)
```

**Structure Decision**: No new top-level directories. The feature is
implemented entirely within the existing `.github/workflows/` (10 files,
each already `workflow_call`-only) layout this pipeline already has, with
zero changes to `.github/actions/**`, this repository's own wrappers, or any
persisted state. Documentation and shared-contract-doc updates are scoped to
the implementation stage, consistent with how `016-bedrock-support` scoped
its own cross-cutting doc edits — this plan's own artifacts stay inside
`specs/031-stage-environment-binding/`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|---------------------------------------|
| Principle VII: the environment gate is owned by the *stage* (published contract), not the wrapper (which normally owns every security gate) | `jobs.<job_id>.environment` is legal **only** inside a called (`workflow_call`) workflow's own job definitions. GitHub rejects it outright on a job whose `uses:` points at a reusable workflow, and `on.workflow_call.inputs` has no mechanism to accept or forward it either — so there is no syntax by which a wrapper could apply this gate to a stage it calls. | A wrapper-side gate — impossible, not merely more complex: GitHub's own parser refuses the keyword in that position. The next-best alternative, a pipeline-internal approval mechanism that mimics GitHub's environment gate without the keyword, was rejected by the spec itself (FR-006: "The pipeline MUST NOT add any approval, wait, or gating logic of its own") because it would duplicate GitHub's own reviewer/wait-timer/branch-policy machinery, need its own storage and audit trail, and give up native App-based protection rules entirely. |
