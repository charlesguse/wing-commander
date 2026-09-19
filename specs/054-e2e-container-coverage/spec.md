# Feature Specification: Container-Mode Coverage in End-to-End Release Verification

**Feature Branch**: `054-e2e-container-coverage`

**Created**: 2026-09-16

**Status**: Draft

**Input**: Lifecycle issue [#364](https://github.com/charlesguse/wing-commander/issues/364) — "auto-release's E2E verification never exercises the containerized code path"

## Context

The scheduled auto-release verification scaffolds the published stage
workflows onto a dedicated test repository and drives one trivial feature
all the way through intake → clarify → plan → tasks → implement → review →
cleanup. It is the only automated check that runs the published contract
the way an adopter actually consumes it, and its verdict is what gates
whether a release is cut at all.

Today that verification only ever exercises one of the two supported
execution modes. Every stage job in the test repository runs directly on a
hosted runner, because nothing configures the test repository with a
container image — so the container-mode code path is never entered. That
path is not small: it is the `container:` block every stage job carries,
the shell resolution inside those jobs, the prerequisite check that pulls
and inspects the image against the canonical required-tool list, the
registry-credential binding, and every shared composite action that runs
*inside* the adopter's image rather than on the runner (the lifecycle
gate's use of `timeout` is a required tool precisely because of this).

The repository already has one partial dogfood of this area: a scheduled
private-image job that pulls a private package and runs the prerequisite
check against it. That proves the image can be pulled and inspected. It
does not prove a stage can *do its work* inside a container — no agent
step, no lifecycle gate, no composite action, no stage transition runs
there.

The result is a check whose green result means less than it appears to:
"the published pipeline carried a feature end to end" is currently true
only of the non-container half of the product. A container-path regression
would first surface on an adopter's runner.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Container-mode regressions are caught before release (Priority: P1)

As the maintainer of this repository, when a scheduled verification runs
in container mode against unreleased work on the default branch, I want a
full feature to be carried end to end with every stage job executing
inside a container image, so that a defect in the containerized execution
path fails that run's release gate instead of reaching an adopter who
pinned the tag.

**Why this priority**: This is the entire point of the feature. Without
it, nothing else in this spec has value — the remaining stories make the
coverage trustworthy and affordable, but this story is the coverage.

**Independent Test**: Run the verification against a head whose container
path is known-good and observe a passing verdict that records container
mode as exercised; then run it against a head carrying a deliberately
broken container path and observe the release blocked with a verdict
naming the container-mode failure.

**Acceptance Scenarios**:

1. **Given** unreleased work on the default branch and a healthy reference
   image, **When** a scheduled verification runs in container mode,
   **Then** a feature is carried from labelled issue through to a closed,
   done-labelled issue with every stage job of that run having executed
   inside the reference image, and the release proceeds.
2. **Given** a head in which a stage's containerized execution is broken
   (for example a step that cannot resolve a shell inside the image, or a
   composite action that depends on a tool the image does not provide),
   **When** a scheduled verification runs in container mode, **Then** the
   verification returns a failing verdict and no release is dispatched.
3. **Given** the canonical required-tool list gains a new entry that the
   reference image does not yet provide, **When** a verification runs in
   container mode, **Then** the prerequisite check fails the run and the
   report names every missing tool.
4. **Given** a passing verification, **When** the maintainer reads the
   run's report, **Then** the report states which execution mode(s) were
   exercised and which image reference was used.

---

### User Story 2 - A pass never overstates what was verified (Priority: P1)

As the maintainer, I want the verification to be incapable of reporting an
unqualified pass for a run in which container mode was not actually
exercised — whether because the image reference was missing, the image
could not be pulled, or the container-mode leg was deliberately skipped —
so that the verdict I release on means what it says.

**Why this priority**: Equal to P1 because the failure mode it prevents is
the one this feature exists to correct. A container-mode leg that silently
degrades to a hosted-runner run would reproduce today's gap while looking
like it had closed it, and would be harder to notice the second time.

**Independent Test**: Point the verification at an unresolvable image
reference and confirm the run produces a named, non-pass verdict (or an
explicitly mode-qualified result) rather than a plain pass, and that the
report distinguishes "the image could not be obtained" from "the pipeline
failed inside the image".

**Acceptance Scenarios**:

1. **Given** the reference image is unset or empty in the test
   repository's configuration, **When** the container-mode leg runs,
   **Then** the run reports an infrastructure-class failure naming the
   missing configuration, and does not report the leg as passed.
2. **Given** the reference image cannot be pulled (registry unavailable,
   rate-limited, reference deleted, or credentials rejected), **When** the
   container-mode leg runs, **Then** the run reports an
   infrastructure-class failure that names the pull failure and is
   distinguishable from a pipeline defect found inside the image.
3. **Given** the container-mode leg did not run for any reason, **When**
   the verification's report is written, **Then** the report states that
   container mode was not exercised on that run.
4. **Given** a run whose turn in the alternation was container mode,
   **When** that run fails, **Then** the report identifies the failing
   mode and the stage at which it failed, rather than reporting a single
   mode-ambiguous failure — and the same holds for a default-runner run,
   so consecutive runs are distinguishable by mode in the report.

---

### User Story 3 - Coverage that stays affordable and unblockable (Priority: P2)

As the maintainer, I want the added verification time to be bounded and
the container-mode leg to be independently pausable, so that a slow or
flaky container leg degrades release cadence in a way I control rather
than wedging auto-release entirely.

**Why this priority**: The existing verification already occupies a
substantial wall-clock budget. Alternating the modes run over run keeps
per-run wall clock and agent spend at today's level rather than doubling
them, but a container leg that is slow or flaky would still stall every
second scheduled run — so the maintainer needs to be able to take that
mode out of the rotation without pausing auto-release. Valuable, but the
coverage in P1 is worth having even before this control exists.

**Independent Test**: Set the container-mode pause control and confirm
that scheduled runs whose turn would have been container mode instead run
the default-runner leg, report that container mode was not exercised, and
still reach a release decision.

**Acceptance Scenarios**:

1. **Given** the container-mode leg is paused by the maintainer, **When**
   a scheduled verification whose turn is container mode runs, **Then** it
   runs the default-runner leg instead, reports container mode as not
   exercised, and proceeds to its release decision on that basis.
2. **Given** the container-mode leg exceeds its time budget, **When** the
   budget is reached, **Then** the run produces a timeout-class verdict
   attributed to container mode rather than being killed without a
   verdict.
3. **Given** a scheduled verification running the container leg, **When**
   the run completes, **Then** its wall clock stays within the
   verification job's declared time bound, which the alternation leaves
   unchanged from today's single-leg budget.

---

### User Story 4 - The reference image has a named owner and upkeep path (Priority: P2)

As the maintainer, I want the project-owned image the verification pins —
built and published by this repository to its own registry namespace — to
have a stated maintenance trigger and documented behaviour when it falls
behind, so that container-mode coverage does not quietly rot into a
permanently red or permanently skipped leg.

**Why this priority**: This is the difference between coverage that lasts
and coverage that is disabled after its third unexplained failure. It is
P2 because the coverage can ship before the upkeep story is fully
automated, provided the failure is loud.

**Independent Test**: Add a new entry to the canonical required-tool list
and confirm the documented upkeep path names who updates the image and
what the verification does in the interval.

**Acceptance Scenarios**:

1. **Given** the canonical required-tool list changes, **When** a
   maintainer consults the project's documentation, **Then** the
   obligation to update the reference image, and where that image lives,
   is stated.
2. **Given** the reference image is out of date with respect to the
   required-tool list, **When** the verification runs, **Then** the
   failure names the drift explicitly rather than presenting as a generic
   stage failure.
3. **Given** an adopter reads the published documentation, **When** they
   look up container-image guidance, **Then** the reference image is
   presented consistently with the project's existing bring-your-own
   position — the documentation states that the image exists for this
   repository's own verification and does not imply it is a supported
   image for adopter use.

---

### Edge Cases

- **Two legs, one scratch repository.** The verification resets the test
  repository's default branch and closes its open issues before each
  attempt. Alternation means only one leg runs per scheduled
  verification, so the two legs never contend within a run; the
  constraint survives across runs, where an overlapping or manually
  dispatched verification must not reset a test repository another leg is
  still using.
- **A leftover run from the other leg.** If the previous run's leg — in
  the other mode — leaves an open issue or branch behind, the next run's
  reset must clear it, the same way a leftover from a previous scheduled
  attempt is cleared today.
- **Private image, unreachable secrets.** If the pinned image is private,
  the test repository needs registry credentials configured. A credential
  that is absent, wrong, or expired must surface as an
  infrastructure-class failure that names which credential was missing,
  not as a pipeline defect.
- **The image changes underneath the pin.** The image is project-owned,
  but if the test repository's variable names a moving tag rather than an
  immutable digest, a republish can change what is verified between runs
  and can block a release for a reason unrelated to the head under
  verification.
- **Registry rate limiting.** A pull refused for rate-limit reasons is an
  infrastructure condition, not evidence that the release candidate is
  broken, and must not be reported as one.
- **The alternation loses its place.** The mode a run picks is derived
  from prior runs; a cancelled, skipped, or manually dispatched run must
  not leave the rotation stuck on one mode, or container coverage silently
  stops happening while every run still reports a mode.
- **A release gated by only one mode.** Under alternation, a release is
  gated by the mode its run exercised, so a container-mode regression can
  ship in a release that a default-runner run gated. The window is bounded
  by one scheduled interval, and the next container-mode run must still
  block the release after it.
- **Agent-bearing steps inside a container.** The container leg runs real
  agent stages, so it consumes the same usage window as any other run; a
  rate-limited agent turn inside the container leg must be classified the
  same way it would be outside it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The scheduled end-to-end verification MUST exercise the
  containerized execution path, on the runs whose turn is container mode
  (FR-018), by carrying a feature through the full stage chain with every
  stage job of that feature executing inside a container image.
- **FR-002**: The container-mode leg MUST exercise the same stage chain
  the existing leg does — intake through cleanup — not a reduced subset,
  and MUST assert the same per-stage evidence (stage labels observed in
  the issue timeline, expected spec artifacts present, terminal
  done-labelled closed issue).
- **FR-003**: The verification MUST record, in its verdict and in its
  report, which execution mode the run exercised — stating explicitly when
  container mode was not exercised — and, for a container-mode run, the
  image reference used.
- **FR-004**: The verification MUST NOT report an unqualified pass for a
  run in which the container-mode leg was configured to run but did not
  actually execute inside a container. Silent degradation to a hosted
  runner MUST be reported as a failure of the leg.
  **Accepted gap** (repository owner's decision on #373, tracked in #390):
  one case cannot be told apart today. A container-mode turn whose
  `WING_COMMANDER_CONTAINER_IMAGE` variable is unset on the test repository
  still reaches a plain `pass`, because `verify-image-prerequisites`
  vacuously succeeds and the run completes on a hosted runner; detecting it
  needs a permission (reading the test repository's variable or Actions
  run data) that this verification has not been granted. Every other route
  to a silent fallback is reported, and `container_image_configured`
  defaults to false on every verdict except the poll step's own `pass`.
- **FR-005**: Every failure mode of the container leg MUST degrade to a
  named verdict the reporting step can render, never to an unreported
  crash or an empty verdict.
- **FR-006**: The verification MUST distinguish failures caused by
  obtaining or inspecting the image (unset reference, pull failure,
  rejected credentials, missing prerequisite tool) from failures of the
  pipeline running inside the image, and MUST classify the former as
  infrastructure-class.
- **FR-007**: When the container leg fails, the report MUST name the
  stage at which it failed and identify the failure as belonging to the
  container leg specifically.
- **FR-008**: The two legs MUST NOT run concurrently against the same test
  repository; the design MUST guarantee that one leg's repository reset
  cannot destroy another leg's in-flight run, including when a manually
  dispatched verification overlaps a scheduled one.
- **FR-009**: The container leg MUST be independently pausable by the
  maintainer without pausing auto-release as a whole; while it is paused,
  runs whose turn would have been container mode MUST run the
  default-runner leg and MUST report container mode as not exercised
  rather than as passed.
- **FR-010**: The container leg MUST be bounded by its own time budget
  such that exhausting it yields a timeout-class verdict attributed to the
  container leg, rather than the job being killed before a verdict is
  written.
- **FR-011**: A scheduled verification MUST exercise exactly one leg, so
  that its total wall clock remains within the verification job's declared
  time bound without that bound being raised for this feature.
- **FR-012**: The image reference used by the container leg MUST satisfy
  the project's canonical required-tool list, and drift between the list
  and the image MUST surface as a named failure of the verification.
- **FR-013**: Documentation MUST state that the reference image is built
  and published by this repository to its own registry namespace, who is
  responsible for updating it, that a change to the canonical
  required-tool list is what triggers an update, and that the image exists
  for this repository's own verification rather than as a supported image
  for adopter use — the published bring-your-own position for
  container images is unchanged.
- **FR-014**: If the project-owned reference image is published private
  rather than public, the credential path the container leg uses MUST be
  the same published credential mechanism adopters use, so that the leg
  exercises that mechanism rather than a verification-only shortcut.
- **FR-015**: Reaching container-mode coverage MUST NOT require a manual
  step per run. The one-time maintainer setup that remains — configuring
  the image reference on the test repository (FR-017) — MUST be documented
  and MUST produce a clear, named failure when absent rather than a silent
  skip.
- **FR-016**: The reference image for the container leg MUST be a minimal
  project-owned image built and published by this repository to this
  org's container registry namespace.
- **FR-017**: The image reference MUST reach the test repository as a
  repository variable a maintainer sets once on that repository, the same
  way the test repository's own identity is configured today. The
  verification MUST NOT write that configuration itself, and MUST NOT
  require any new permission on its token to obtain the reference.
- **FR-018**: The container leg MUST alternate with the default-runner leg
  across scheduled verifications — each scheduled run exercises exactly
  one mode, the mode alternates run over run, and that run's release
  decision is gated by the leg it ran, so a container-leg failure blocks
  the release that run would otherwise have cut.
- **FR-019**: The build definition for the reference image MUST live in
  this repository, and a gate MUST fail when the image's tool set and the
  canonical required-tool list disagree, so that adding an entry to the
  list cannot silently leave the published image behind.
- **FR-020**: The mode a scheduled run exercises MUST be derived so that
  the alternation cannot become stuck on one mode after a cancelled,
  skipped, failed, or manually dispatched run; the report MUST state which
  mode the run selected and the runs MUST remain distinguishable by mode
  after the fact.

### Key Entities

- **Execution mode**: One of the two supported ways a stage's jobs run —
  directly on a runner, or inside a container image. The verification's
  unit of coverage.
- **Reference image**: The minimal container image the container-mode leg
  pins, built and published by this repository to this org's registry
  namespace. Owned by this repository's maintainer, updated when the
  required-tool list changes, and carrying a visibility (public or
  private, determining whether credentials are needed).
- **Verification leg**: One complete end-to-end feature run through the
  stage chain in a single execution mode, against a test repository, which
  produces exactly one verdict.
- **Verdict**: The machine-readable outcome of a leg — pass, or a named
  failure class — carrying the mode it describes, the verified head, the
  failing check, what was expected, what was observed, and evidence.
- **Required-tool list**: The canonical set of tools a container image
  must provide for the pipeline to run inside it. The reference image's
  correctness is defined against it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Container-mode execution is exercised end to end, through
  every stage of the chain, by at least one of every two consecutive
  scheduled verifications, with zero manual steps required per run.
- **SC-002**: A deliberately introduced container-path defect is caught by
  the verification and blocks the release, demonstrated at least once
  against a real run before the feature is considered complete.
- **SC-003**: 100% of verification runs report which execution mode(s)
  were exercised; no run reports an unqualified pass while having skipped
  or silently degraded a configured container leg.
- **SC-004**: 100% of container-leg failures are classified as either
  infrastructure-class (image could not be obtained or inspected) or
  pipeline-class (the pipeline failed inside the image), and name the
  stage at which they occurred.
- **SC-005**: A verification run in either mode completes within the
  verification job's declared time bound — unchanged from today's bound —
  with no leg killed before it can write a verdict.
- **SC-006**: A maintainer can suppress the container leg and restore it
  through a single configuration change, without editing or pausing
  auto-release itself.
- **SC-007**: Drift between the canonical required-tool list and the
  reference image is detected — by a gate at change time and by the
  verification at run time — with a report that names every missing tool
  at once.
- **SC-008**: Adding an entry to the canonical required-tool list without
  updating the reference image fails a gate before it can reach the
  default branch.
- **SC-009**: Over any window of consecutive scheduled verifications, no
  mode is exercised twice in a row while the other is skipped, unless the
  container leg is explicitly paused — and when it is paused, every run in
  that window reports container mode as not exercised.

## Assumptions

- The existing default-runner end-to-end leg continues to run and to gate
  the releases it verifies; this feature adds container-mode coverage
  rather than replacing the coverage that exists today. Under the decided
  alternation it runs on every other scheduled verification instead of on
  every one, which is an accepted reduction in default-runner cadence.
- The test repository remains a dedicated, disposable repository whose
  default branch the verification is free to reset, and the existing
  refusal to point that verification at this repository itself continues
  to apply to any additional test repository introduced here.
- The container leg exercises the published stage contract exactly as an
  adopter consumes it — the same wrapper fixture, the same published
  stages, pinned at the unreleased commit under verification — with the
  image reference as the only deliberate difference from the existing leg.
- The existing private-image prerequisite dogfood remains as-is; it covers
  pulling and inspecting a private image, which is a narrower question
  than the one this feature answers, and the two are complementary.
- This repository's own lifecycle stages continue to run on the
  no-container default; nothing here changes how this repository
  dogfoods its own pipeline day to day.
- Failure classes already defined by the verification (infrastructure,
  timeout, incomplete, wrong-output) are the vocabulary this feature
  extends, rather than a new taxonomy.
- Alternating the modes keeps agent usage and wall clock per scheduled
  run at today's level; the cost of the coverage is paid in cadence
  instead — each mode gates half as many releases as the single leg does
  today, and a regression in one mode can ship in a release the other
  mode gated.
- The related on-demand scratch-repository provisioning work (issue #362)
  may change how test repositories are obtained. This spec states a
  constraint on leg isolation (FR-008) rather than assuming either a
  single shared repository or per-leg repositories.
- The project's published position that container images are
  bring-your-own continues to hold: the reference image decided in
  Question 1 is this repository's own verification fixture, not a
  supported image offered to adopters (FR-013).
- The reference image's visibility (public or private in the org's
  registry namespace) is left to the plan stage; FR-014 covers the private
  case and adds no requirement in the public one.

## Clarifications

### Session 2026-09-17

All three open questions were answered by the repository owner on
lifecycle issue [#364](https://github.com/charlesguse/wing-commander/issues/364).
No `[NEEDS CLARIFICATION]` markers remain.

**Question 1 — Reference image provenance and ownership** (FR-016,
FR-019, FR-013, User Story 4)

*Asked*: should the project build and publish its own minimal reference
image, or pin an existing third-party public image that already satisfies
the canonical required-tool list?

*Answered*: **Option A** — build and publish a minimal project-owned
image to this org's container registry namespace, kept in agreement with
the canonical required-tool list by a gate. The project keeps full control
of the image's contents and accepts the build/publish pipeline and the
upkeep obligation; the published bring-your-own position for adopters is
unchanged, and the documentation must say the image exists for this
repository's verification rather than for adopter use.

**Question 2 — How the image reference reaches the test repository**
(FR-017, FR-015, User Story 2)

*Asked*: should the verification configure the image reference on the test
repository as part of scaffolding, or should it stay a repository variable
a maintainer sets once?

*Answered*: **Option B** — a maintainer-set repository variable on the
test repository, configured once, matching how the test repository's own
identity is configured today. The verification's token gains no permission
to write repository configuration. The variable's absence must produce a
named infrastructure-class verdict, never a silent fallback to
hosted-runner mode.

**Question 3 — Cadence, and whether the container leg gates the release**
(FR-018, FR-020, FR-011, User Story 3)

*Asked*: should the container leg run on every scheduled verification and
gate every release, or less often — and if less often, does a failure
still block a release?

*Answered*: **Option B** — alternate the modes between scheduled runs.
Each scheduled run exercises exactly one leg and its release decision is
gated by the leg it ran, so per-run wall clock and agent spend stay at
today's level while each mode gates half the releases.
