# Feature Specification: Private-Image Credentials That Reach Every Stage Job

**Feature Branch**: `044-private-registry-credentials`

**Created**: 2026-09-07

**Status**: Draft

**Input**: GitHub issue #283 — "[feature] Registry-agnostic private-image credentials that reach every stage job (ECR first)"

> Make the private-registry credentials that specs/038 already declares on every
> stage (`container-registry-username` / `container-registry-password`) actually
> reach **every job** that runs under `container-image`, so a private image can be
> pulled without a pre-authenticated self-hosted runner. The mechanism must be
> registry-agnostic: the stages see only a username/password pair that the caller
> supplies, and the caller is free to mint that pair at run time (the primary
> short-term use case is **AWS ECR**, whose password is a short-lived token from
> `aws ecr get-login-password`).

## Overview

specs/038 gave every published stage two controls — which runner its jobs target,
and which container image they run inside — and declared two optional secrets for
the private-image case. Those secrets were briefly wired into each job's registry
authentication, that wiring broke every job of every stage, and it was removed
(#224, probe PR #226, fix PR #228). Issue #227 recorded the measured reason: the
per-job credential mapping GitHub offers cannot be conditionally absent. Once the
key is written it is always present; an empty value is a template error that stops
the job before its first step — which is every run naming no image — and a
placeholder value is always acted on, so it fails authentication against a public
image's registry. No single static job shape served all three cases, so the
credentials were left reaching exactly one job per stage.

Today that one job is `verify-image-prerequisites`: it authenticates, pulls the
named image, and checks it for the tools the pipeline needs — then emits a warning
saying the credentials it just used reach nothing else, and the adoption docs tell
private-image adopters to bring a runner that is already logged in. That is a
workable answer for an enterprise with self-hosted infrastructure and no answer at
all for the common case: an adopter on GitHub-hosted runners whose approved image
lives in ECR, GHCR, GCR, or ACR. Those adopters can name a private image and watch
every agent-bearing job fail to pull it.

This feature closes that gap. The adopter-facing interface does not change: the
same two secrets, the same names, the same "inert unless an image is named"
contract — which keeps this a non-breaking minor. What changes is reach: when an
adopter supplies the pair, every job of the stage authenticates with it, and when
they do not, every job behaves exactly as it does today. The stages stay
registry-agnostic — they receive a username and a password and know nothing about
who issued them. Registries whose credential is minted at run time are a
first-class case, because the credential is consumed before any step of the stage
job runs and therefore has to be minted on the caller's side and handed in;
Wing Commander ships the means to do that easily for the first-class example (AWS
ECR via OIDC) at the edge, in documentation and optional adapters, never inside a
stage.

The feature also carries a process obligation the last attempt did not: the
mechanism must be proven against real GitHub-hosted runners before implementation
starts, covering all three shapes, with the evidence recorded. specs/038's FR-018
asked for exactly that and it was never gathered, which is why a shipped feature
had to be ripped out.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pull a private image from every job, on hosted runners (Priority: P1)

As a maintainer of a consuming repository whose approved base image lives in a
private registry, I want every job of every stage to pull that image using the
credentials I supply, so that I can run the pipeline inside my required image on
GitHub-hosted runners without owning a pre-authenticated self-hosted runner.

**Why this priority**: This is the request. Everything else in this feature either
protects it or documents it. Without it, "private registry support" means one
prerequisite check that pulls successfully followed by every real job failing.

**Independent Test**: In a scratch adopter repository on GitHub-hosted runners,
name an image in a private registry, supply the two secrets, run a stage, and
observe every job of that stage start inside the image and the stage complete —
with no self-hosted runner involved and no pipeline file edited.

**Acceptance Scenarios**:

1. **Given** an adopter names a private image and supplies both credential
   secrets, **When** a stage runs on hosted runners, **Then** every job of that
   stage runs its steps inside the image, and none fails to pull it.
2. **Given** the same setup, **When** the run's logs and job configuration are
   inspected, **Then** the credential value appears nowhere in them.
3. **Given** an adopter names a private image and supplies no credentials or only
   one of the pair, **When** the stage runs, **Then** it fails at the prerequisite
   check with a message naming the missing credential, before any agent cost is
   incurred, rather than each job failing separately on a raw registry error.
4. **Given** credentials are supplied, **When** the stage runs, **Then** the reach
   of those credentials is the whole stage — which jobs authenticate is not a
   hidden per-job rule.

---

### User Story 2 - All three shapes keep working from one set of stage files (Priority: P1)

As a maintainer of a repository that adopts the release carrying this feature, I
want the no-image default and the public-image case to behave exactly as they do
today, so that gaining private-image support costs nothing to adopters who do not
use it.

**Why this priority**: This is the requirement the previous attempt failed. A
shape that serves the private case and breaks the other two is worse than no
private support at all — #224 is the proof, and it took every stage of every
adopter down. It is co-equal with User Story 1: the deliverable is all three
shapes from one set of stage files, not the private one.

**Independent Test**: Run a stage three times from the same stage files — no
image; a public image with no credentials; a private image with credentials — and
confirm each behaves per its contract, with the first two byte-for-byte identical
to the previous release.

**Acceptance Scenarios**:

1. **Given** no container image is named (the default), **When** any stage runs,
   **Then** its jobs run directly on the runner with no container: no image
   pulled, no container created, no container-related step or failure in the log.
2. **Given** a public image is named and no credentials are supplied, **When** any
   stage runs, **Then** every job runs inside the image with no authentication
   attempted, and nothing fails for want of a credential.
3. **Given** credentials are supplied but no image is named, **When** any stage
   runs, **Then** the credentials are inert — no login, no warning, no behavior
   change of any kind.
4. **Given** an adopter moves their pin to the release carrying this feature and
   changes nothing in their wrapper, **When** a full lifecycle runs, **Then** no
   stage fails, warns, or behaves differently because of this feature.
5. **Given** the private-image support ships, **When** the published stage files
   are inspected, **Then** there is exactly one set of them — no per-shape variant
   file, no duplicated stage, no fork.

---

### User Story 3 - Hand in a credential my registry mints at run time (Priority: P1)

As a maintainer whose registry issues a short-lived token rather than accepting a
stored password — AWS ECR being the immediate case — I want a supported way to
mint that token in my own wrapper and hand it to the stage, so that I never store
a long-lived registry secret and the stage still pulls my image.

**Why this priority**: The primary named use case is ECR, whose password cannot be
a stored secret by design. A mechanism that only accepts static pairs does not
serve the adopter who filed the request. It is separable from User Story 1 —
static-pair registries are served without it — but it is not deferrable, because
it constrains where the credential is produced and therefore what the stage
interface has to accept.

**Independent Test**: In a scratch adopter repository, add a wrapper job that
assumes a cloud role via the repository's OIDC identity, mints a registry token,
and passes it into the stage call; confirm the stage pulls a private cloud-registry
image and completes, with no long-lived registry credential stored anywhere.

**Acceptance Scenarios**:

1. **Given** an adopter mints a registry token in their own wrapper before the
   stage call and passes it as the password secret, **When** the stage runs,
   **Then** every job authenticates with it and the image is pulled.
2. **Given** a token is minted and handed across the wrapper's own job boundary
   into the stage call, **When** the run's logs are inspected, **Then** the token
   value is masked everywhere it could otherwise surface, including in the
   hand-off itself.
3. **Given** an adopter uses this flow, **When** they set it up, **Then** they do
   so entirely from their own wrapper — no published stage is edited or forked,
   and no registry-specific input is added to any stage.
4. **Given** the pipeline documents this flow, **When** an adopter follows the
   documentation, **Then** they reach a working private-image run from a
   copy-pasteable example rather than by rediscovering the pattern.

---

### User Story 4 - Registry-agnostic core, provider help at the edge (Priority: P2)

As a maintainer of the pipeline, I want the stages to know only about a username
and a password, with any provider-specific credential minting living in
documentation or optional adapters, so that supporting one more registry never
means changing a published stage.

**Why this priority**: It is what keeps User Story 3 from metastasizing into a
per-cloud matrix inside the stage files. It delivers no adopter capability by
itself, which is why it sits below the three P1 stories, but it is the constraint
that makes them maintainable.

**Independent Test**: Read the published stage files and confirm no provider name,
region, role, or registry-specific input appears in any of them; then complete a
private-image run against a registry that accepts a static pair (for example a
container registry authenticated with the repository's own workflow token) with no
adapter of any kind involved.

**Acceptance Scenarios**:

1. **Given** a registry that accepts a static username/password pair, **When** an
   adopter uses it, **Then** no adapter, composite action, or extra wrapper job is
   required — the two secrets alone suffice.
2. **Given** the pipeline adds help for a specific cloud registry, **When** the
   published stage files are inspected, **Then** that provider is named nowhere in
   them.
3. **Given** an adopter uses a registry the pipeline has never heard of, **When**
   it can present a username/password pair, **Then** it works with no pipeline
   change.

---

### User Story 5 - The mechanism is proven before it is built (Priority: P2)

As a maintainer of the pipeline, I want the chosen mechanism demonstrated on real
GitHub-hosted runners across all three shapes, with the evidence recorded in the
feature's research, before implementation begins, so that this feature cannot
repeat #224 — a capability assumed to work, shipped to every adopter, and
withdrawn.

**Why this priority**: The whole reason this spec exists rather than a one-line fix
is that the last attempt assumed platform behavior it never measured. The
obligation belongs in the spec because it is a condition of delivery, not a
planning preference.

**Independent Test**: Before any stage file is changed, point at a run on real
hosted runners exercising each of the three shapes with the candidate mechanism,
and at the recorded evidence in the feature's research artifact, each claim
traceable to a run.

**Acceptance Scenarios**:

1. **Given** a candidate mechanism, **When** implementation is proposed, **Then**
   a probe on real GitHub-hosted runners has already exercised all three shapes and
   the results are recorded, with the runs identifiable.
2. **Given** a probe result contradicts an assumption, **When** the plan is
   written, **Then** the rejected mechanism and the measured reason are recorded
   rather than dropped silently.
3. **Given** the feature relies on any platform behavior not documented by the
   platform, **When** the implementation is read, **Then** each such reliance is
   traceable back to the recorded evidence, so a silent upstream change is
   detectable.

---

### User Story 6 - The uniformity checks are amended, not bypassed (Priority: P3)

As a maintainer of the pipeline, I want the existing job-shape uniformity check to
be deliberately updated — with its own self-test extended to cover the new shape's
failure modes — so that the check keeps meaning what it says and a later job cannot
be born exempt from the credential binding.

**Why this priority**: The check currently forbids the very thing this feature
changes, so it cannot stay as it is; the risk is that it is loosened into
vacuousness on the way past. It protects the capability rather than providing it.

**Independent Test**: Introduce a stage job that omits the credential binding and
confirm the pipeline's own PR checks fail naming the stage file and job; restore it
and confirm they pass; confirm the self-test exercises each new failure branch from
a checked-in fixture.

**Acceptance Scenarios**:

1. **Given** a job in a published stage that does not carry the credential binding
   every other job carries, **When** the pipeline's own PR checks run, **Then**
   they fail and name the stage file and the job.
2. **Given** a new published stage file is added, **When** the checks run, **Then**
   it is covered automatically — the stage set stays derived, never listed.
3. **Given** the check is amended for the new shape, **When** its self-test runs,
   **Then** every failure branch it ships is exercised by a checked-in fixture,
   including the branches specific to the new shape.
4. **Given** a job must deviate for a stated reason, **When** the checks run,
   **Then** they pass only because that exact stage-and-job pair is registered with
   its reason.

---

### User Story 7 - Documentation says what is now possible (Priority: P3)

As a prospective adopter with a private image, I want the documentation to tell me
how to make every stage job pull it, with worked examples for a cloud registry and
for a repository-scoped registry, so that I can set it up without reading pipeline
source or discovering the removed limitation from a stale warning.

**Why this priority**: The current documentation actively tells adopters the
capability does not exist and directs them to a pre-authenticated runner. Leaving
that in place after the capability ships is a defect of its own, but it delivers
nothing until the capability exists.

**Independent Test**: A reader following the adoption documentation alone reaches a
working private-image run for both worked examples, and finds no surviving claim
that the credentials reach only the prerequisite check.

**Acceptance Scenarios**:

1. **Given** the feature has shipped, **When** an adopter reads the adoption and
   setup documentation, **Then** the pre-authenticated-runner guidance is presented
   as a fallback for registries that cannot present a username/password pair, not
   as the only option for a private image.
2. **Given** an adopter uses a cloud registry with run-time-minted credentials,
   **When** they read the documentation, **Then** they find a complete worked
   example of the wrapper-side minting job.
3. **Given** the credentials now reach every job, **When** any document or run
   output is inspected, **Then** no statement remains claiming they reach only the
   prerequisite check.

---

### Edge Cases

- **The hand-off from a wrapper job to a stage secret.** A credential minted in one
  wrapper job and consumed by another job's stage call has to cross a job boundary.
  The platform deliberately restricts what may cross that boundary in order to
  protect secrets, so the hand-off shape is exactly the kind of behavior this
  feature may not assume: it must be demonstrated to both work and stay masked, or
  a different hand-off must be found. This is the highest-risk unknown in the
  feature after the binding shape itself.
- **A credential that expires mid-lifecycle.** A minted token has a finite life.
  One stage run comfortably fits inside the primary use case's window, but a full
  lifecycle spans many stage runs over hours or days, and a queued job — a
  self-hosted fleet at capacity, a stage waiting on a deployment-environment
  approval — can start long after its token was minted. Each stage call mints its
  own credential at call time; the pipeline neither refreshes a credential nor
  detects its expiry, and a token that dies while a job waits surfaces as a pull
  failure. This is documented, not managed.
- **Credentials supplied with no image named.** They must remain completely inert:
  no login attempt, no warning, no new failure mode. This is the shape that broke
  before, and it is the default state of every adopter who sets the secrets for one
  stage call in a wrapper that makes several.
- **Credentials supplied for a public image.** An adopter who sets the secrets
  repository-wide and names a public image must not have their run fail because
  authentication was attempted where none was needed.
- **Only one of the pair supplied.** A username with no password, or the reverse,
  is a misconfiguration that must be reported as itself and fail fast — never
  become a half-attempted login or an unexplained per-job pull failure.
- **Which registry the credentials authenticate against.** The pair is scoped to
  one registry, derived from the image reference the adopter named. An image
  reference with no registry host component (a bare or namespaced public-hub
  reference) has no host to authenticate to — a case the prerequisite check already
  handles and the new binding must handle the same way, not differently.
- **One credential pair per stage call.** An image whose pull requires more than one
  registry's credentials is out of scope; the interface carries a single pair.
- **A stage bound to a deployment environment.** Environment binding, runner
  selection, container image, and now registry credentials are orthogonal; none
  changes another's behavior, and a stage may be gated, redirected, containerized,
  and authenticated at once.
- **The prerequisite check's own role is unchanged.** It still runs directly on the
  runner, before any other job's container is created, and still fails the stage
  fast with every missing prerequisite named. What changes is that its warning about
  credentials reaching nothing else stops being true and is removed.
- **A caller-side permission the caller must grant.** An adopter minting a token
  through a cloud identity flow needs a permission on their own side that their
  wrapper must declare. The pipeline requests no new permission for itself; where a
  documented example needs one, the example states it, and this repository's own
  permission checks must stay satisfied by whatever the shipped examples and
  wrappers declare.
- **Registries that cannot present a username/password pair.** Out of scope. The
  pre-authenticated runner remains the documented fallback for them, and the
  documentation must say so rather than leaving an adopter to discover it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When an adopter names a container image and supplies both credential
  secrets, every job of that stage that runs inside the image MUST authenticate to
  the image's registry with those credentials.
- **FR-002**: The adopter-facing interface MUST remain the two existing stage
  secrets, unchanged in name and meaning. No registry-specific, provider-specific,
  or credential-shape-specific input may be added to any published stage.
- **FR-003**: All three shapes — no image named, a public image with no
  credentials, and a private image with credentials — MUST be served by one set of
  published stage files. No per-shape stage variant, duplicated stage file, or fork
  is acceptable.
- **FR-004**: When no image is named, a stage MUST run with no container at all: no
  image pulled, no container created, no container-related step, no new failure
  mode — identical to the previous release.
- **FR-005**: When an image is named and no credentials are supplied, every job
  MUST run inside the image with no authentication attempted, and no job may fail
  for want of a credential.
- **FR-006**: When credentials are supplied and no image is named, they MUST be
  entirely inert — no login attempt, no warning, no behavior change.
- **FR-007**: When exactly one of the two credentials is supplied alongside an
  image, the stage MUST fail fast with a message naming which one is missing,
  before any agent work or cost, rather than surfacing only a registry error or
  attempting a partial login.
- **FR-008**: The credential binding MUST apply uniformly to every job of the stage
  it is set on — the same granularity as the existing runner and image controls,
  with no hidden per-job rule about which jobs authenticate.
- **FR-009**: The published stages MUST remain registry-agnostic: they receive a
  username and a password and MUST NOT contain any provider's name, region, role,
  endpoint, or credential-minting logic.
- **FR-010**: A registry that accepts a static username/password pair MUST work
  through the two secrets alone, with no adapter, extra wrapper job, or additional
  configuration of any kind.
- **FR-011**: Credentials minted at run time MUST be a supported first-class case.
  The pipeline MUST define where minting happens — on the caller's side, before the
  stage call, because the credential is consumed before any step of the stage job
  runs — and an adopter using such a flow MUST be able to do so without editing or
  forking a published stage.
- **FR-012**: The credential value MUST NOT appear in run logs, job configuration,
  or any pipeline output, including across the caller-side hand-off from wherever
  it is minted to the stage call that consumes it. The masking of that hand-off MUST
  be demonstrated rather than assumed.
- **FR-013**: The pipeline MUST ship what an adopter needs to mint a credential for
  the primary cloud-registry use case without rediscovering the pattern — at
  minimum a complete, copy-pasteable worked example; any shipped adapter MUST live
  at the edge (documentation or an optional, separately-invoked component), never
  inside a published stage, and MUST NOT require the adopter to store a long-lived
  cloud credential. [NEEDS CLARIFICATION: does Wing Commander ship the cloud-registry
  credential minting as a supported, versioned component that adopters call — widening
  the published contract surface it must then maintain and never break — or as a
  documented snippet only, which adopters copy and own?]
- **FR-014**: The existing prerequisite check MUST keep its current fail-fast role
  and placement: running before any other job's container is created, pulling the
  named image, and failing the stage with every missing prerequisite named at once.
- **FR-015**: Once the credentials reach every job, the prerequisite check's warning
  that they reach nothing else MUST be removed, and no document, comment, or run
  output may continue to claim the limitation.
- **FR-016**: The mechanism MUST be demonstrated on real GitHub-hosted runners,
  across all three shapes of FR-003, before implementation begins, and the evidence
  MUST be recorded in the feature's research artifact with each run identifiable.
- **FR-017**: Any candidate mechanism the probe rules out MUST be recorded with the
  measured reason, so that a future reader does not re-propose it.
- **FR-018**: Every platform behavior this feature depends on that the platform does
  not document MUST be traceable from the implementation back to the recorded
  evidence, so a silent upstream change is detectable.
- **FR-019**: The existing job-shape uniformity check MUST be amended deliberately
  to describe the new shape — never bypassed, disabled, or narrowed to a check that
  cannot fail — and MUST fail, naming the stage file and job, when any job of a
  published stage lacks the credential binding its siblings carry. Its stage set
  MUST stay derived from the workflows rather than listed.
- **FR-020**: The uniformity check's self-test MUST be extended so that every
  failure branch the amended check ships is exercised by a checked-in fixture,
  including the branches specific to the new shape.
- **FR-021**: A job that must deviate from the uniform binding MUST carry a
  registered, machine-checked exception naming the reason — never an unregistered
  deviation and never a code comment alone.
- **FR-022**: The pipeline's other standing checks MUST remain satisfied: the
  prerequisite-check presence and required-tool agreement, the environment-binding
  uniformity, the caller-permission coverage for anything a shipped example or
  wrapper requests, the permissioned-token rules, the guard-versus-degradation-path
  rules, and the composite-action description rules.
- **FR-023**: Adoption and setup documentation MUST state that credentials now reach
  every job, present the pre-authenticated runner as the fallback for registries
  that cannot present a username/password pair, and carry two worked examples: a
  cloud registry with run-time-minted credentials, and a registry authenticated with
  a repository-scoped token.
- **FR-024**: Documentation MUST state the credential's lifetime contract: each
  stage call carries the credential it was given, the pipeline never refreshes or
  renews one, and a credential that expires before a queued job starts surfaces as a
  pull failure.
- **FR-025**: Shipping this MUST be an additive, non-breaking change on the current
  major line: existing adopters who set neither secret see no behavioral change, and
  no existing input, secret, or output is renamed or removed.
- **FR-026**: If the probe of FR-016 shows that no single stage-file shape can serve
  all three shapes of FR-003, the feature MUST NOT ship a mechanism that regresses
  the no-image or public-image case. [NEEDS CLARIFICATION: in that outcome, what
  should this feature deliver — nothing beyond the recorded evidence and improved
  documentation of the existing fallback, or an opt-in the adopter sets explicitly
  when their image is private, accepting one more control on the stage interface?]
- **FR-027**: This repository's own use of the pipeline MUST stay consistent with
  what the feature claims. [NEEDS CLARIFICATION: must this repository dogfood the
  private-image path in its own runs — which requires it to own a private image and
  a registry identity — or is the probe evidence plus adopter documentation
  sufficient, leaving this repository's own runs on the no-image default?]

### Key Entities

- **Registry credential pair**: The username and password a stage's jobs use to
  pull a private image. Supplied per stage call as secrets, never as inputs. Inert
  unless an image is named. Opaque to the stage: it never learns who issued the
  pair or how long it lives.
- **Container binding**: What a stage job declares about where it runs and what it
  runs inside — now including, when and only when an adopter supplies them, the
  credentials for the image's registry. Must express three shapes from one
  declaration, and must be identical across every job of a stage.
- **Caller-side minting step**: The work an adopter performs before a stage call to
  produce a credential their registry will accept — for a cloud registry, obtaining
  a short-lived token through their own identity flow. Owned by the adopter's
  wrapper; the pipeline supplies the pattern, not the execution.
- **Provider adapter**: Optional, edge-located help for one registry family that
  turns an adopter's cloud identity into a username/password pair. Never referenced
  by a published stage; absent entirely for registries that accept a static pair.
- **Prerequisite check**: The per-stage job that pulls the named image and verifies
  the tools the pipeline needs, before any other job's container exists. Keeps its
  role; loses its warning about credential reach.
- **Probe evidence**: The recorded results of exercising a candidate mechanism on
  real hosted runners across all three shapes — the artifact that separates a
  measured claim from an assumed one, and the thing whose absence caused the
  previous attempt's withdrawal.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An adopter on GitHub-hosted runners with an image in a private
  registry can complete a full lifecycle, with 100% of the pipeline's jobs running
  inside that image, by editing only their own wrapper — zero pipeline file edits,
  zero forks, and no self-hosted runner.
- **SC-002**: With no image named, a full lifecycle is behaviorally identical to the
  same lifecycle on the previous release: no container anywhere, no new failure,
  warning, or artifact.
- **SC-003**: With a public image named and no credentials supplied, every job runs
  inside that image and none fails for want of a credential.
- **SC-004**: An adopter whose registry issues short-lived credentials completes a
  full lifecycle with no long-lived registry secret stored anywhere, and the
  credential value appears in no workflow file, log, or job configuration.
- **SC-005**: An adopter with a registry that accepts a static pair needs exactly
  two secrets and zero additional components to get a private-image run.
- **SC-006**: 100% of jobs across all published stages carry the credential binding,
  verified by a check that fails on a job which does not — including a job added
  after this feature ships — and whose every shipped failure branch is exercised by
  a checked-in fixture.
- **SC-007**: Every platform behavior the feature relies on that the platform does
  not document is traceable to a recorded run on real hosted runners, and each of
  the three shapes has at least one such run.
- **SC-008**: A new adopter can enable private-image support from a copy-pasteable
  example in the adoption documentation, for both worked registry examples, without
  reading pipeline source.
- **SC-009**: After this ships, zero statements anywhere in the repository's
  documentation, stage output, or code comments claim that registry credentials
  reach only the prerequisite check.

## Assumptions

- **The existing secret names are kept**, which is what makes this a minor rather
  than a breaking change; adopters who already set them for the prerequisite check
  gain reach without editing anything.
- **One credential pair per stage call**, matching the existing per-stage-call
  granularity of the runner and image controls. Per-job credentials and multi-
  registry pulls are out of scope and remain additive later.
- **The credential is minted before the stage call**, because it is consumed when
  the job's container is created — before any step inside the stage job could run.
  This is a structural constraint, not a design preference.
- **The primary cloud-registry example is AWS ECR**: a fixed username, a token
  obtained through the adopter's own identity flow with no long-lived stored
  credential, and a lifetime that comfortably exceeds a single stage run.
- **The repository-scoped-token example is a registry that accepts the caller's own
  workflow token as a password**, which needs no adapter and demonstrates the
  no-adapter path.
- **The stage never manages a credential's lifecycle** — it does not mint, refresh,
  renew, or validate one; it forwards what it was handed.
- **This feature is orthogonal to the deployment-environment binding, the runner and
  image controls, and the alternate model-provider option**; they compose, and none
  changes another's behavior.
- **The prerequisite check's required-tool list is unchanged** by this feature; only
  its warning about credential reach is affected.
- **No new permission or app scope is requested by the pipeline itself.** An adopter
  minting a credential through a cloud identity flow declares the permission that
  flow needs in their own wrapper.

## Dependencies

- The platform's own handling of container-job registry authentication, including
  whether a whole container declaration can be produced conditionally and whether
  the secrets it needs are in scope where it is declared — undocumented behavior
  that this feature is required to measure rather than assume.
- The platform's rules for passing a value between jobs when that value is a
  secret, which govern the caller-side hand-off of a minted credential.
- The existing published-stage surface, its prerequisite check, and this
  repository's PR-time workflow checks — in particular the job-shape uniformity
  check that currently forbids the very declaration this feature introduces, and its
  self-test.
- The recorded findings of the previous attempt (issue #227 and its probe), which
  establish which shapes are already known not to work and must not be re-proposed
  without new evidence.
