# Feature Specification: Consumer-Chosen Runners and Container Images

**Feature Branch**: `038-runner-container-passthrough`

**Created**: 2026-08-17

**Status**: Draft

**Input**: GitHub issue #219 — "[feature] Allow image passthrough"

> **What problem are you trying to solve?**
> Currently, `ubnutu-latest` is being used and `conatiner:` is not set.
>
> **What should happen instead?**
> Consumers of this tool should be able to pass in a different runners and containers of their choosing.
>
> **Anything else? (optional)**
> I want `container: ${{ inputs.container-image }}` to mean "no container" when unset, so adopters who don't care are unaffected.
>
> `runs-on` takes a string or an array. Self-hosted usually means multiple labels (`[self-hosted, linux, x64]`). A type: string input can only carry one, so multi-label consumers need `fromJSON(inputs.runner)` and a documented JSON-array convention.
>
> Private images need credentials. `container.credentials`

## Overview

The pipeline is adopted by other repositories, which call its published stages
(intake, clarify, plan, tasks, implement/converge, finalize, cleanup, rebase,
watchdog, pr-conversation, auto-update-spec-kit) to run spec-driven development in
their own repository. Every job in every one of those stages is hardcoded to
`ubuntu-latest`, and none of them declares a container.

That hardcoding is the *only* thing an adopter cannot fix from their own wrapper.
The keywords that choose where a job runs (`jobs.<job_id>.runs-on`) and what it runs
inside (`jobs.<job_id>.container`) are legal only *inside the called workflow*; a job
that calls a reusable workflow may set neither, and `on.workflow_call` will not
accept them from the caller. So — exactly like the deployment-environment binding of
specs/031-stage-environment-binding — the capability can only live inside the stage,
which makes this a change to the published stage interface rather than something an
adopter can add in their wrapper or in documentation.

Adopters who need this fall into three groups, and today all three are simply
blocked from using the pipeline at all:

- **Self-hosted runners.** Enterprises whose Actions runs must execute on their own
  infrastructure — inside a VPC, behind an egress proxy, or on hardware with
  credentials the hosted fleet does not have. Self-hosted selection is usually
  multi-label (`[self-hosted, linux, x64]`), not a single name.
- **Runner sizes and fleets.** Adopters on larger GitHub-hosted runners, ARM
  runners, or runner groups, who name a label of their own.
- **Controlled toolchains.** Adopters who must run pipeline jobs inside an approved,
  scanned base image — often pulled from a private registry that needs credentials.

This feature adds two optional controls to every published stage — where the job
runs, and what image (if any) it runs inside — both off by default. When unset,
nothing changes for any existing adopter: the default runner selection is the same
`ubuntu-latest` used today, and an unset image means **no container at all**, not an
empty or default one. When set, the adopter names their own runner labels and their
own image, and GitHub schedules the job accordingly.

The other half of Constitution VII is preserved: both values arrive as declared,
typed inputs. A stage never discovers a runner or an image on its own — no
repository-variable lookup, no ambient state, no defaulting to anything but today's
behavior.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run the pipeline on my own runners (Priority: P1)

As a maintainer of a consuming repository whose Actions work must run on
self-hosted infrastructure, I want to tell each pipeline stage which runner to
target — including a multi-label selection — so that the pipeline runs on my
hardware instead of GitHub's hosted fleet.

**Why this priority**: This is the requester's core, blocking need, and it cannot be
worked around from the adopter's side. An organization that may not use hosted
runners cannot adopt the pipeline at all today. Delivering runner selection is the
larger half of the feature.

**Independent Test**: In a scratch adopter repository with a registered self-hosted
runner, pass that runner's label selection to a stage and observe the stage's jobs
picked up by that runner and completing normally, with no pipeline file edited.

**Acceptance Scenarios**:

1. **Given** an adopter passes a single runner label (for example a larger hosted
   runner's name), **When** the stage runs, **Then** its jobs are scheduled on that
   runner and the stage completes exactly as it would on the default runner.
2. **Given** an adopter passes a multi-label self-hosted selection (for example
   `self-hosted`, `linux`, `x64` together), **When** the stage runs, **Then** all of
   those labels are applied as a conjunction — the job goes to a runner carrying
   every label, not to one carrying only the first.
3. **Given** an adopter passes a label no registered runner carries, **When** the
   stage runs, **Then** GitHub queues the job per its own behavior and the pipeline
   adds no validation, allowlist, or pre-existence check of its own.
4. **Given** a runner selection is passed to a stage, **When** that stage runs,
   **Then** every job in that stage honors it — which jobs move is not a hidden
   internal rule.

---

### User Story 2 - Existing adopters are unaffected when both controls are unset (Priority: P1)

As a maintainer of a repository that adopts a version of the pipeline carrying this
feature but sets neither control, I want my runs to behave exactly as before, so
that moving my pin changes nothing about where my pipeline runs, what it runs
inside, or what it costs.

**Why this priority**: The zero-change no-op is what makes the feature safe to ship
as a minor to every adopter, including this repository's own dogfooded runs. It is as
essential as the capability itself, and the container half is where it is easy to get
wrong: a container that is "empty" rather than "absent" changes every step of every
stage.

**Independent Test**: Run each stage with both controls left at their defaults and
confirm the run is identical to today — same runner, no container step in the job
log, no image pull, no new failure mode.

**Acceptance Scenarios**:

1. **Given** both controls are left at their defaults, **When** any stage runs,
   **Then** its jobs run on the same runner they use today and the run is behaviorally
   identical to a run of the previous release.
2. **Given** the container image is left unset, **When** any stage runs, **Then** the
   job runs directly on the runner with **no container**: no image is pulled, no
   container is created, and no container-related step appears in the job log.
3. **Given** an adopter upgrades their pin to the release carrying this feature and
   changes nothing in their wrapper, **When** a full lifecycle runs, **Then** no stage
   fails, warns, or behaves differently because of this feature.

---

### User Story 3 - Run stage jobs inside a chosen container image (Priority: P2)

As a maintainer whose organization requires all CI work to execute inside an
approved, scanned base image, I want to name that image for each pipeline stage, so
that the pipeline's jobs run inside it instead of directly on the runner.

**Why this priority**: This is the feature's namesake and the second of the two
blocked adopter groups, but it is subordinate to runner selection: an adopter can
often satisfy a toolchain policy by baking the image into a self-hosted runner,
whereas nothing substitutes for choosing the runner.

**Independent Test**: Pass a public image reference to a stage in a scratch adopter
repository and confirm every job of that stage runs its steps inside that image, with
the stage completing normally.

**Acceptance Scenarios**:

1. **Given** an adopter names a container image, **When** the stage runs, **Then**
   every job of that stage executes its steps inside that image.
2. **Given** an adopter names an image that lacks a tool a stage requires, **When**
   the stage runs, **Then** the failure identifies the missing prerequisite rather
   than surfacing as an unexplained stage error.
3. **Given** an adopter names an image, **When** the stage runs, **Then** the
   pipeline neither rewrites nor supplements the reference — no implicit registry,
   no implicit tag, no fallback image.

---

### User Story 4 - Pull that image from a private registry (Priority: P2)

As a maintainer whose approved base image lives in a private registry, I want to
supply the registry credentials to the stage without putting them in a workflow
file, so that the pipeline can pull the image my policy requires.

**Why this priority**: Approved-image policies and private registries travel
together — an organization strict enough to mandate a base image rarely publishes it
publicly. Without credentials, User Story 3 serves only adopters with public images.
It sits below the image itself because it is inert until an image is named.

**Independent Test**: Point a stage at an image in a private registry, supply the
credentials as repository secrets, and confirm the image is pulled and the stage
completes; confirm the credential value never appears in logs or in the run's
configuration.

**Acceptance Scenarios**:

1. **Given** an adopter names a private image and supplies registry credentials as
   secrets, **When** the stage runs, **Then** the image is pulled and the stage
   completes normally.
2. **Given** an adopter names a private image and supplies no credentials, **When**
   the stage runs, **Then** the stage fails with a message that identifies the
   missing credential as the cause rather than only surfacing the registry's raw
   error.
3. **Given** credentials are supplied, **When** the run's logs and job configuration
   are inspected, **Then** the credential value appears nowhere in them.

---

### User Story 5 - The controls stay uniform as the pipeline grows (Priority: P3)

As a maintainer of the pipeline, I want a machine check that every job of every
published stage honors both controls, so that a job added later cannot silently
ignore an adopter's runner or image and run on hosted infrastructure the adopter
believes they opted out of.

**Why this priority**: A partial rollout is the worst shape of this defect — an
adopter who moved to self-hosted runners for compliance reasons would see most jobs
comply and have no way to notice the one that did not. The same reasoning already
produced the environment-binding gate (specs/031, lint Gate 7), and the same failure
mode already occurred once for a different gate whose stage list was hardcoded
(issue #149). It is P3 only because it protects the capability rather than providing
it.

**Independent Test**: Add a job to a published stage that omits the controls and
confirm the pipeline's own PR checks fail, naming the offending stage and job; remove
it and confirm they pass.

**Acceptance Scenarios**:

1. **Given** a job in a published stage that does not honor the runner and container
   controls, **When** the pipeline's own PR checks run, **Then** they fail and name
   the stage file and job.
2. **Given** a new published stage file is added, **When** the checks run, **Then**
   it is covered automatically — the stage set is derived, not listed, so a new stage
   cannot be born exempt.
3. **Given** a job must deviate for a stated reason, **When** the checks run,
   **Then** they pass only because that exact stage-and-job pair is registered with
   its reason, not because the check was loosened.

---

### User Story 6 - Configure it once for this repository's own runs (Priority: P3)

As a maintainer of this repository, I want its own wrapper workflows to expose both
controls the way every other pipeline knob is exposed, so that the worked example
adopters copy is real and this repository can change its own runners without editing
a published stage.

**Why this priority**: Constitution I — the repo is its own first example — and
consistency with the existing knobs (models, branch prefixes, tool lists), which are
all set from this repository's own configuration rather than hardcoded in wrappers.
It delivers no adopter capability on its own.

**Independent Test**: Set this repository's runner configuration to a non-default
value, observe a dogfooded stage run there, unset it, and observe the run return to
the default runner — with no workflow file edited in either direction.

**Acceptance Scenarios**:

1. **Given** this repository's wrappers, **When** no runner or image is configured,
   **Then** every wrapper passes values that reproduce today's behavior exactly.
2. **Given** a runner selection is configured for this repository, **When** a stage
   is triggered through its wrapper, **Then** the stage's jobs run on that selection
   without any workflow file being edited.

---

### Edge Cases

- **Empty image means no container, not an empty one.** This is the property the
  whole zero-change guarantee rests on and the one behavior in this feature that is
  not documented by GitHub. It must be *verified* against real runners before being
  relied upon, in the same way specs/031 verified that an empty environment name is a
  true no-op. If verification shows an empty value does not suppress the container,
  the pipeline needs another way to express "no container" — and whatever that is
  must still leave unset adopters byte-for-byte unchanged.
- **One label versus many.** `runs-on` accepts either a single label or a list, but a
  string-typed input can carry only one value. Multi-label adopters therefore need a
  documented convention (a JSON array in the input) and the pipeline must interpret
  it as a conjunction of labels, not as one label whose name contains brackets.
- **A single-label value that looks like a list.** Whatever convention distinguishes
  "one label" from "several labels", the rule must be stated so that a value is never
  silently reinterpreted — an adopter must be able to predict which reading applies
  from the documentation alone.
- **Runner groups.** Some adopters target a runner *group* rather than (or in
  addition to) labels. Group targeting is a different shape than a label list and is
  out of scope for this feature; documentation must say so rather than leave adopters
  to discover it.
- **Containers require Docker on the runner.** A container image on a self-hosted
  runner requires a Linux runner with Docker available. Combining a container with a
  runner that cannot host one is an adopter-side misconfiguration the pipeline does
  not detect; it is documented, not prevented.
- **Non-Linux runners are out of scope.** Every stage's steps are Linux shell scripts
  using `git`, `gh`, and standard POSIX tooling. Naming a Windows or macOS runner is
  accepted by the input and will fail in the steps; this is a documented non-goal,
  not a validated one.
- **The pipeline's own checkout still happens inside whatever is chosen.** The shared
  composite actions each stage checks out run inside the same job, so they inherit the
  runner and the container. An image that cannot reach the pipeline repository, or
  lacks the tools those composites use, fails the stage — which is why the image's
  prerequisites must be documented as a contract rather than discovered per adopter.
- **A stage bound to a deployment environment.** Runner and container selection is
  orthogonal to the environment binding of specs/031: a stage may be gated *and*
  redirected, and neither control changes the other's behavior.
- **Cost and concurrency change with the runner.** Self-hosted capacity is finite; a
  pipeline whose stages all target one runner can serialize behind it, and the
  per-spec concurrency design assumes stages of different specs can run in parallel.
  This is an adopter-side capacity concern, documented rather than managed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every published stage MUST accept an optional input selecting the
  runner its jobs target, defaulting to the runner used today (`ubuntu-latest`).
- **FR-002**: The runner selection MUST be able to express both a single label and a
  multi-label selection (for example `self-hosted` + `linux` + `x64`), and a
  multi-label value MUST be applied as a conjunction — the job targets a runner
  carrying every named label.
- **FR-003**: The convention that distinguishes a single-label value from a
  multi-label one MUST be unambiguous and documented, such that an adopter can
  predict from documentation alone how any given value will be read.
- **FR-004**: Every published stage MUST accept an optional input naming a container
  image for its jobs, defaulting to unset.
- **FR-005**: When the container image is unset, a stage MUST run with **no
  container**: no image pulled, no container created, no container-related step or
  failure. This MUST be verified against real runners rather than assumed, and the
  evidence recorded.
- **FR-006**: When both controls are left at their defaults, a stage MUST behave
  exactly as it does without this feature — same runner, no container, no new
  warning, no new artifact, and no change to any stage output.
- **FR-007**: When a control is set, it MUST apply uniformly to every job in that
  stage file — no hidden per-job rule about which jobs move.
  [NEEDS CLARIFICATION: is one runner selection per stage the right granularity, or
  should agent-bearing jobs and lightweight bookkeeping jobs be separately
  targetable? Uniform selection means an adopter with scarce self-hosted capacity
  sends short label/comment jobs there too.]
- **FR-008**: Both values MUST be passed through unvalidated: the pipeline MUST NOT
  check that a runner label or an image exists, maintain an allowlist, rewrite an
  image reference (no implicit registry, no implicit tag), or supply a fallback.
- **FR-009**: Registry credentials for a private image MUST be accepted as stage
  secrets — never as inputs — and MUST NOT appear in run logs or job configuration.
  [NEEDS CLARIFICATION: is private-registry support in scope for this feature, and in
  what shape — a username/password secret pair on every stage, or deferred to a
  follow-up with public images and pre-authenticated self-hosted runners as the
  documented interim?]
- **FR-010**: When an image is named but a required credential is absent, the stage
  MUST fail with a message identifying the missing credential rather than only
  surfacing the registry's raw error.
- **FR-011**: The prerequisites a container image must satisfy for the stages to run
  (the tools and runtimes every stage and shared composite action depends on) MUST be
  stated as a documented contract.
  [NEEDS CLARIFICATION: is documenting the prerequisites sufficient, or must the
  pipeline actively verify them at the start of a stage and fail with an actionable
  message naming what is missing?]
- **FR-012**: Both controls MUST be sourced solely from the stage's declared inputs.
  A stage MUST NOT read a runner or image from a repository variable, an environment
  variable, or any other ambient repository state (Constitution VII).
- **FR-013**: Introducing these controls MUST be an additive, non-breaking change:
  existing adopters who do not set them see no behavioral change, and the feature
  ships as a minor on the current major release line.
- **FR-014**: A machine check that runs on the pipeline's own pull requests MUST fail
  when any job of any published stage does not honor both controls, naming the stage
  file and job. Its stage set MUST be derived from the workflows themselves rather
  than hardcoded, so a newly added stage is covered automatically.
- **FR-015**: A job that must deviate MUST carry a registered exception naming the
  reason, checked by the same mechanism — never an unregistered deviation and never a
  code comment alone (Constitution VII).
- **FR-016**: This repository's own wrapper workflows MUST expose both controls
  through its ordinary configuration mechanism, with defaults that reproduce today's
  behavior exactly.
- **FR-017**: Adopter documentation MUST record: the multi-label convention with a
  copy-pasteable example; the container image prerequisites; how to supply private
  registry credentials (or, if deferred, that private registries are not yet
  supported and what to do instead); that containers require a Linux runner with
  Docker; that non-Linux runners are not supported; that runner *groups* and the
  remaining container settings (volumes, ports, environment, extra options, service
  containers) are out of scope; and that self-hosted capacity interacts with the
  pipeline's parallel-spec design.
- **FR-018**: Any behavior this feature depends on that is not documented by GitHub —
  above all the unset-image no-op — MUST be traceable from the implementation back to
  the recorded evidence, so that a silent upstream change is detectable.

### Key Entities

- **Runner selection**: The set of labels a stage's jobs target. One label or several;
  several are a conjunction. Supplied by the adopter per stage call, defaulting to the
  single hosted label used today. Not validated by the pipeline.
- **Container image reference**: The image a stage's jobs run inside, as the adopter
  writes it (registry, repository, tag or digest). Unset is meaningful and distinct
  from empty: it means no container at all.
- **Registry credentials**: The secret pair needed to pull a non-public image.
  Inert unless an image is named; carried as secrets, never as inputs, and never
  logged.
- **Published stage**: A `workflow_call`-only stage workflow that adopters pin —
  eleven of them at the time of writing, spanning thirty-three jobs. The unit both
  controls are set on, and the unit the parity check enumerates.
- **Image prerequisite contract**: The tools and runtimes a chosen image must provide
  for stages and their shared composite actions to run.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An adopter can move 100% of the pipeline's jobs onto their own runners,
  including a multi-label self-hosted selection, by editing only their own wrapper
  configuration — zero edits to any pipeline file and zero forks.
- **SC-002**: With both controls unset, a full lifecycle (intake through cleanup) is
  behaviorally identical to the same lifecycle on the previous release: same runner
  for every job, no container created anywhere, and no new failure, warning, or
  artifact.
- **SC-003**: 100% of jobs across all published stages honor both controls, verified
  by an automated check that fails on a job which does not — including a job added
  after this feature ships.
- **SC-004**: An adopter whose approved base image lives in a private registry can
  complete a full lifecycle with no credential value present in any workflow file,
  log, or job configuration.
- **SC-005**: An adopter who names an image missing a required tool learns which
  prerequisite is missing from the run's own output, without reading pipeline source.
- **SC-006**: The adoption documentation lets a new adopter enable each control from
  a copy-pasteable example, with the multi-label convention and the image
  prerequisites stated in one place.

## Assumptions

- **The multi-label convention is a JSON array in a string input.** The requester
  proposed it and it is the only shape that fits a typed `workflow_call` input, so it
  is taken as the default rather than raised as a question. A value that is not an
  array is read as a single label.
- **Both controls are per stage call**, so an adopter whose wrapper calls a stage
  more than once can target the calls differently — the same granularity model as the
  environment binding (specs/031), pending FR-007's clarification.
- **Only the image and its credentials are configurable.** The remaining container
  settings (volumes, ports, environment variables, extra options) and service
  containers are out of scope for this feature; they can be added later without
  changing what this one establishes.
- **Runner groups are out of scope**, as is any form of runner selection other than
  labels.
- **Linux only.** Every stage's steps assume a Linux shell environment; the controls
  are pass-through and the pipeline does not attempt to support other platforms.
- **The image must already contain the pipeline's prerequisites.** The pipeline does
  not install tools into an adopter's image.
- **No new permissions or App scopes** are required by either control.
- **Cost and capacity are the adopter's concern.** Choosing a runner may change what
  a run costs and how much of the pipeline can run in parallel; the pipeline does not
  manage or report on this.
- **This feature is orthogonal to the deployment-environment binding** (specs/031)
  and to the Bedrock provider option: they compose, and none of them changes another's
  behavior.

## Dependencies

- GitHub Actions' own scheduling of `runs-on` labels and its container-job support,
  including the (undocumented, to-be-verified) treatment of an unset container value.
- The pipeline's existing published-stage surface and the shared composite actions
  each stage checks out, which run inside whatever runner and image the job selects.
- This repository's existing PR-time workflow-linting checks, which are where the
  parity check of FR-014 belongs.
