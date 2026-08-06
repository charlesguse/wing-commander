# Feature Specification: Bind Pipeline Stages to a Deployment Environment

**Feature Branch**: `031-stage-environment-binding`

**Created**: 2026-08-06

**Status**: Draft

**Input**: GitHub issue #171 — "[feature] Allow adopters to bind stages to a deployment environment"

## Overview

The pipeline is adopted by other repositories, which call its published stages
(intake, clarify, plan, tasks, implement, converge, finalize, and the supporting
rebase/watchdog stages) to run spec-driven development. Most of those stages run
an AI agent that spends real money the moment it starts.

GitHub offers a native mechanism for gating expensive or sensitive work — a
**deployment environment** — which can carry a required reviewer, a wait timer, a
deployment branch/tag policy, or a custom (GitHub App) protection rule. Today an
adopter has no way to attach such an environment to a pipeline stage, and — unlike
most configuration — they cannot fix it from their own wrapper either. The keyword
that binds a job to an environment (`jobs.<job_id>.environment`) is only legal
*inside the called workflow*; a job that calls a reusable workflow may not set it,
and `on.workflow_call` will not accept it as an input. So the only place the
capability can live is inside the stage, which makes this a change to the stage
interface rather than something an adopter can add in their wrapper or in docs.

This feature adds an optional environment binding to every published stage, off by
default. When unset, nothing changes for any existing adopter — byte-for-byte. When
set, the adopter names one of *their own* repository's environments and GitHub
applies whatever protection rules that environment carries before the stage's jobs
run.

This is a deliberate, narrow exception to the principle that wrappers own the gates
(Constitution VII): the keyword is legal nowhere else. The other half of that
principle is preserved — the environment name arrives as a declared input, and the
stage never discovers one on its own (no default name, no repository-variable
lookup, no ambient state).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Gate an expensive stage behind a required reviewer (Priority: P1)

As a maintainer of a consuming repository, I want to name one of my deployment
environments when I call a pipeline stage, so that GitHub applies that
environment's protection rules — for example a required reviewer — before the
stage's agent starts and spends any money.

**Why this priority**: This is the requester's core, blocking need. There is no way
today to put a human approval or a wait in front of an agent, and the capability
cannot be added from the adopter's side. Delivering the environment binding is the
whole feature.

**Independent Test**: In a scratch adopter repository, create an environment with a
required reviewer, pass its name to a stage, and observe that the stage's jobs pend
for approval before any preflight or agent step runs, with no agent cost incurred
while pending; on approval the stage proceeds normally.

**Acceptance Scenarios**:

1. **Given** an adopter passes the name of an environment that has a required reviewer, **When** the stage runs, **Then** its jobs enter a pending-approval state before preflight and before any agent step, and no agent cost is incurred while pending.
2. **Given** the same stage is pending approval, **When** the reviewer approves, **Then** the stage continues and completes exactly as it would have without the environment.
3. **Given** an adopter passes the name of an environment that has a wait timer, **When** the stage runs, **Then** its jobs wait the configured time before starting and no agent cost is incurred during the wait.
4. **Given** an adopter passes the name of an environment with a deployment branch/tag policy, **When** the stage runs from a ref that violates the policy, **Then** GitHub blocks the stage per its own policy without the pipeline adding any check of its own.

### User Story 2 - Existing adopters are unaffected when the input is unset (Priority: P1)

As a maintainer of a repository that adopts a version of the pipeline carrying this
feature but does not set the environment input, I want my runs to behave exactly as
before, so that upgrading changes nothing about how my pipeline runs and leaves no
new artifact in my repository.

**Why this priority**: The zero-change no-op is what makes the feature safe to ship
as a minor to every adopter, including this repository's own dogfooded runs. It is
as essential as the capability itself.

**Independent Test**: Run a stage with the environment input left at its default and
confirm the run is identical to today — no environment applied, no gate, no
deployment record, and no phantom environment created in repository settings.

**Acceptance Scenarios**:

1. **Given** the environment input is left at its default (unset/empty), **When** any stage runs, **Then** its jobs run unconditionally with no environment applied, no gate, no environment scope, and no deployment record.
2. **Given** the environment input is unset, **When** the stage completes, **Then** no environment is created in the adopter's repository settings and no other new artifact appears anywhere in the repository.

### User Story 3 - Keep the environment gate without cluttering the Deployments panel (Priority: P2)

As a maintainer who wants the protection rules of an environment but finds the
resulting deployment records noisy, I want a way to suppress the deployment record
while keeping the binding and its gate, so that my Deployments/Environments panel
stays clean.

**Why this priority**: A usability refinement on top of the core capability. Valued
by adopters who bind many runs, but subordinate to the gate itself, and it comes
with a documented trade-off (custom App protection rules stop working).

**Independent Test**: Bind a stage to an environment with a protection rule and
disable the deployment record; confirm the gate still applies and no deployment
record is created.

**Acceptance Scenarios**:

1. **Given** an adopter binds a stage to an environment and disables the deployment record, **When** the stage runs, **Then** the environment's protection rules still apply and no deployment record is created.
2. **Given** the deployment-record control is left at its default, **When** the stage runs bound to an environment, **Then** a deployment record is created (mirroring GitHub's own default) and every protection-rule type keeps working, including custom (GitHub App) rules that require a deployment object.

### User Story 4 - Per-job granularity from the wrapper (Priority: P2)

As a maintainer whose wrapper calls a stage more than once for different purposes, I
want to bind the environment on only the calls that run an agent, so that the
agent-free calls are not gated.

**Why this priority**: Preserves adopter control without adding hidden per-job rules
inside the stage. The single-input-per-stage design deliberately pushes granularity
to the wrapper, and the tasks stage — called twice, once to generate (agent) and
once for the approved/agent-free path — is the motivating case.

**Independent Test**: In a wrapper that calls a stage twice, pass the environment on
one call and omit it on the other; confirm only the first call's jobs bind to the
environment.

**Acceptance Scenarios**:

1. **Given** a wrapper calls a stage twice and passes the environment on only one call, **When** the wrapper runs, **Then** only the jobs of that call bind to the environment and the other call runs ungated.
2. **Given** a stage file with multiple jobs and an environment input that is set, **When** the stage runs, **Then** the environment is applied uniformly to every job in that stage file — which jobs bind is not a hidden internal rule.

### Edge Cases

- **Name that does not exist yet**: The named environment is created on reference by
  GitHub — with no protection rules — and the stage runs ungated. The pipeline adds
  no pre-existence check, allowlist, or failure. A typo or renamed environment
  therefore produces a *new*, unprotected environment, so a run the adopter believes
  is gated is not. This is accepted behavior, surfaced to adopters through
  documentation rather than prevented in code.
- **Empty name**: Treated as a true no-op — the job runs unconditionally with no
  environment applied, no gate, no deployment record, and no phantom environment
  created. This holds for the whole-run default and is the property the zero-change
  guarantee rests on.
- **Per-run rather than per-feature approval**: Each `implement` cycle is a fresh
  dispatch, so a required reviewer on the implement stage produces one approval
  prompt per iteration (up to the iteration cap, default 5), serially; a wait timer
  multiplies the same way. Adopters wanting fewer approvals per feature bind a
  once-per-feature stage (plan, or the tasks-generate call) instead of implement
  — noting that approval is per *job*, so those cost two prompts each rather than
  one; only the single-job stages (intake, clarify, finalize) cost one.
- **Pending job holds its concurrency slot, and only one call can wait**: A stage
  awaiting approval keeps its per-spec concurrency slot until it is approved or
  GitHub's 30-day pending limit expires. Work for the same spec does *not* queue
  up behind it: GitHub holds at most one pending run per concurrency group and
  **cancels** the previously pending one when a newer call arrives, so retriggers
  that land during a long review pause are silently dropped, not deferred.
  *(Corrected 2026-08-06: this originally said other work "queues behind" the
  unapproved run.)*
- **Environment secrets do not work here** (out of scope, documented): The stage's
  secret contract is kebab-case and GitHub environment-secret names cannot contain
  hyphens, so the stage's declared secrets can never *be* environment secrets; and
  an adopter's wrapper resolves `secrets.*` in the calling job, which has no
  environment, so an environment-scoped credential resolves empty and preflight
  fails with an unexplained "no credential" error. Because the failure is silent,
  this must be a documented non-goal, not merely an omission.
- **Lifecycle reporting is unchanged**: A pending gate is silent — it must not
  surface on the lifecycle issue as a stage failure or otherwise be reported as
  "waiting for approval". This can resemble a hung pipeline and is deliberate for
  now.
- **Private-repo plan requirement**: On a private or internal repository,
  environments require a paid GitHub plan (Pro, Team, or Enterprise), and the
  protection rules that make this feature worth using — required reviewers and
  wait timers — require Enterprise. Public repositories get all of it on every
  plan. Below the required tier nothing errors; the rule is simply never
  enforced. This is a documented prerequisite, not a code behavior.
  *(Corrected 2026-08-06: this originally read "Team or Pro", which is the
  tier for environments themselves, not for the protection rules.)*

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every published stage MUST accept an optional input that names a
  deployment environment in the adopter's own repository, defaulting to empty
  (unset).
- **FR-002**: Every published stage MUST accept an optional input controlling whether
  the environment-bound jobs create a deployment record, defaulting to enabled
  (mirroring GitHub's own default).
- **FR-003**: When the environment name is empty, a stage MUST behave byte-for-byte
  as it does without this feature — no environment applied, no gate, no deployment
  record, and no environment created in the adopter's repository.
- **FR-004**: When the environment name is set, a stage MUST bind every job in that
  stage file to the named environment, so that GitHub applies that environment's
  protection rules before those jobs run.
- **FR-005**: The binding MUST take effect before any preflight or agent step of the
  stage, so that a protection rule which pauses the run (required reviewer, wait
  timer) does so before any agent cost is incurred.
- **FR-006**: The pipeline MUST NOT add any approval, wait, or gating logic of its
  own. It names the environment; GitHub alone decides whether that means waiting.
  With no protection rules configured, the bound job starts immediately with no
  pause.
- **FR-007**: The environment name MUST be passed through unvalidated — the pipeline
  MUST NOT check that the environment exists, maintain an allowlist, or require any
  new App permission. A name that does not exist is created on reference by GitHub.
- **FR-008**: When the deployment-record control is disabled, a stage MUST keep the
  environment binding and its gate while suppressing the deployment record.
- **FR-009**: A pending (awaiting-approval) stage MUST NOT be reported to the
  lifecycle issue as a stage failure, and the pipeline MUST NOT add any
  "waiting for approval" reporting to the lifecycle issue thread.
- **FR-010**: Introducing these inputs MUST be a non-breaking, additive change:
  existing adopters who do not set them see no behavioral change, and the feature
  ships as a minor on the current major release line.
- **FR-011**: The environment name MUST be the sole source of the binding — a stage
  MUST NOT supply a default environment name, look one up from a repository variable,
  or otherwise derive it from ambient repository state.
- **FR-012**: Adopter documentation MUST record: the per-job approval multiplier
  (including per matrix leg) with the per-stage counts; the per-iteration (per-run)
  approval behavior and the once-per-feature-stage workaround; the concurrency-slot
  interaction, including that a newer call cancels the pending one rather than
  queueing behind it; the environment-secrets non-goal and why it fails silently;
  the create-on-reference caveat (a typo yields an ungated run, so the name is worth
  copying rather than typing); the OIDC subject-claim change and its effect on
  Bedrock adopters' AWS trust policies; and the private-repo plan tiers.
  *(The first, sixth, and the cancellation clause were added 2026-08-06 from code
  review of the implementation PR; the original list had five items.)*
- **FR-013**: The empirically verified GitHub behaviors this feature depends on
  (empty-name no-op, mapping-form expression binding, deployment-suppression key
  both as a literal and rendered from an expression,
  create-on-reference) MUST be traceable — anything in the implementation that
  depends on them carries a pointer back to the recorded evidence, so a silent
  upstream change is detectable.

### Key Entities

- **Deployment environment**: A GitHub-native, per-repository named scope owned by
  the adopter's repository. Carries optional protection rules (required reviewers,
  wait timer, deployment branch/tag policy, custom App rules). Names are
  case-insensitive, unique per repository, capped at 255 characters, with no
  character restrictions. Created on first reference if it does not already exist.
- **Environment input (per stage)**: The optional name an adopter sets in the
  wrapper's `with:` block to bind a stage's jobs to one of their environments. Empty
  by default; empty means no binding.
- **Deployment-record control (per stage)**: The optional switch determining whether
  a bound job creates a deployment record. Enabled by default; disabling it keeps
  the gate but keeps the Deployments/Environments panel clean at the cost of custom
  App-based protection rules.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With the environment input unset, a stage run is indistinguishable from
  a run of the prior version — zero new environments, zero deployment records, and
  zero behavioral differences observable in the adopter's repository.
- **SC-002**: With the input set to an environment carrying a required reviewer, the
  stage pauses for approval before any agent step and incurs zero agent cost while
  pending, in 100% of runs.
- **SC-003**: With the input set to an environment that has no protection rules, the
  stage starts immediately with no added pause, in 100% of runs.
- **SC-004**: With the input set to a name that does not exist, the environment is
  created on reference and the stage runs ungated, with no validation error and no
  failure — in 100% of runs.
- **SC-005**: With the deployment-record control disabled, the environment's gate
  still applies and no deployment record is created, in 100% of runs.
- **SC-006**: A pending gate never appears as a stage failure on the lifecycle issue.
- **SC-007**: Every adopter-facing consequence named in FR-012 is discoverable in the
  documentation an adopter reads before enabling the feature.

## Assumptions

- **"Every published stage" means all published stage workflows**, including the
  supporting rebase and watchdog stages, each receiving both inputs uniformly. The
  issue states "Every stage gets both"; binding is only meaningful where a job runs,
  and the empty default makes the inputs harmless on stages an adopter chooses not to
  gate.
- **The precedent to match is the existing optional pass-through inputs** (e.g. the
  Bedrock inputs): optional, off by default, set in the wrapper's `with:` block. Both
  new inputs follow that shape.
- **Manual verification is the acceptance vehicle for the protection-rule cases.**
  Required reviewers, wait timers, and branch policies cannot be exercised in this
  repository's CI; a scratch adopter repository with a required reviewer is the
  expected proving ground. The empty-input no-op case is the part that is
  automatically verifiable.
- **The recorded empirical evidence** (the referenced probe repository and its run
  IDs, verified 2026-08-05) **is the authority for the GitHub behaviors** this
  feature relies on; the spec does not re-derive them.
- **Private-repo paid-plan behavior is being confirmed separately** and does not gate
  this specification; it is documented as a prerequisite caveat.

## Out of Scope / Non-Goals

- **Environment secrets.** They cannot work here (kebab-case secret names cannot be
  environment secrets; wrapper-resolved `secrets.*` evaluate in the environment-less
  calling job), and the failure is silent, so this is a documented non-goal.
- **Validating that the named environment exists, or preventing create-on-reference.**
  Pass-through matches Actions' behavior everywhere else and is the least surprising;
  the consequence is documented, not coded around.
- **Reporting "waiting for approval" to the lifecycle issue thread.** A pending gate
  stays silent for now, even though it can look like a hung pipeline.
- **Setting an environment URL.**
- **Any pipeline-side dedup, memory, or short-circuiting of approvals across
  iterations.** A required reviewer on implement prompts once per iteration by
  design; adopters relocate the gate to a once-per-feature stage instead.
