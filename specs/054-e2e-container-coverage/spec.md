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

As the maintainer of this repository, when the scheduled verification runs
against unreleased work on the default branch, I want at least one full
feature to be carried end to end with every stage job executing inside a
container image, so that a defect in the containerized execution path
fails the release gate instead of reaching an adopter who pinned the tag.

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
   image, **When** the scheduled verification runs, **Then** a feature is
   carried from labelled issue through to a closed, done-labelled issue
   with every stage job of that run having executed inside the reference
   image, and the release proceeds.
2. **Given** a head in which a stage's containerized execution is broken
   (for example a step that cannot resolve a shell inside the image, or a
   composite action that depends on a tool the image does not provide),
   **When** the scheduled verification runs, **Then** the verification
   returns a failing verdict and no release is dispatched.
3. **Given** the canonical required-tool list gains a new entry that the
   reference image does not yet provide, **When** the verification runs,
   **Then** the prerequisite check fails the run and the report names
   every missing tool.
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
4. **Given** a run in which both execution modes were exercised, **When**
   only one of them fails, **Then** the report identifies which mode
   failed and at which stage, rather than reporting a single
   mode-ambiguous failure.

---

### User Story 3 - Coverage that stays affordable and unblockable (Priority: P2)

As the maintainer, I want the added verification time to be bounded and
the container-mode leg to be independently pausable, so that a slow or
flaky container leg degrades release cadence in a way I control rather
than wedging auto-release entirely.

**Why this priority**: The existing verification already occupies a
substantial wall-clock budget. Adding a second full feature run roughly
doubles it, which pushes against the job's own time bound and lengthens
the window in which unreleased work sits unreleased. Valuable, but the
coverage in P1 is worth having even before this control exists.

**Independent Test**: Set the container-mode pause control and confirm the
scheduled run completes with the default-runner leg only, reports that
container mode was not exercised, and still reaches a release decision.

**Acceptance Scenarios**:

1. **Given** the container-mode leg is paused by the maintainer, **When**
   the scheduled verification runs, **Then** it completes the
   default-runner leg, reports container mode as not exercised, and
   proceeds to its release decision on that basis.
2. **Given** the container-mode leg exceeds its time budget, **When** the
   budget is reached, **Then** the run produces a timeout-class verdict
   attributed to container mode rather than being killed without a
   verdict.
3. **Given** the verification runs both legs, **When** the run completes,
   **Then** total wall-clock stays within the verification job's declared
   time bound.

---

### User Story 4 - The reference image has a named owner and upkeep path (Priority: P2)

As the maintainer, I want the image the verification pins to have a stated
home, a stated maintenance trigger, and documented behaviour when it falls
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
   position — the documentation does not imply the project hosts a
   supported image for adopter use unless that is what was decided.

---

### Edge Cases

- **Two legs, one scratch repository.** The verification resets the test
  repository's default branch and closes its open issues before each
  attempt. Two legs therefore cannot share one test repository
  concurrently; they must either run sequentially against the same
  repository or use distinct repositories. Overlapping legs would have one
  leg's reset destroy the other's in-flight run.
- **A leftover run from the other leg.** If the first leg leaves an open
  issue or branch behind, the second leg's reset must clear it — the same
  way a leftover from a previous scheduled attempt is cleared today.
- **Private image, unreachable secrets.** If the pinned image is private,
  the test repository needs registry credentials configured. A credential
  that is absent, wrong, or expired must surface as an
  infrastructure-class failure that names which credential was missing,
  not as a pipeline defect.
- **Upstream image changes underneath the pin.** If the reference is a
  moving tag rather than an immutable digest, an upstream rebuild can
  change what is verified between runs, and can block releases for a
  reason unrelated to this repository's own changes.
- **Registry rate limiting.** A pull refused for rate-limit reasons is an
  infrastructure condition, not evidence that the release candidate is
  broken, and must not be reported as one.
- **Only one leg finishes within budget.** If the default-runner leg
  passes and the container leg times out, the run must reach an explicit
  decision about whether that is releasable, rather than inheriting
  whichever verdict happened to be written last.
- **Agent-bearing steps inside a container.** The container leg runs real
  agent stages, so it consumes the same usage window as any other run; a
  rate-limited agent turn inside the container leg must be classified the
  same way it would be outside it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The scheduled end-to-end verification MUST exercise the
  containerized execution path by carrying a feature through the full
  stage chain with every stage job of that feature executing inside a
  container image.
- **FR-002**: The container-mode leg MUST exercise the same stage chain
  the existing leg does — intake through cleanup — not a reduced subset,
  and MUST assert the same per-stage evidence (stage labels observed in
  the issue timeline, expected spec artifacts present, terminal
  done-labelled closed issue).
- **FR-003**: The verification MUST record, in its verdict and in its
  report, which execution mode(s) were exercised on that run and the image
  reference used for the container leg.
- **FR-004**: The verification MUST NOT report an unqualified pass for a
  run in which the container-mode leg was configured to run but did not
  actually execute inside a container. Silent degradation to a hosted
  runner MUST be reported as a failure of the leg.
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
  cannot destroy another leg's in-flight run.
- **FR-009**: The container leg MUST be independently pausable by the
  maintainer without pausing auto-release as a whole, and a paused leg
  MUST be reported as not exercised rather than as passed.
- **FR-010**: The container leg MUST be bounded by its own time budget
  such that exhausting it yields a timeout-class verdict attributed to the
  container leg, rather than the job being killed before a verdict is
  written.
- **FR-011**: The total wall-clock of a verification run that exercises
  both legs MUST remain within the verification job's declared time bound.
- **FR-012**: The image reference used by the container leg MUST satisfy
  the project's canonical required-tool list, and drift between the list
  and the image MUST surface as a named failure of the verification.
- **FR-013**: Documentation MUST state where the reference image lives,
  who is responsible for updating it, what triggers an update, and whether
  it is intended for adopter use or solely for this repository's own
  verification.
- **FR-014**: If the reference image is private, the credential path the
  container leg uses MUST be the same published credential mechanism
  adopters use, so that the leg exercises that mechanism rather than a
  verification-only shortcut.
- **FR-015**: Reaching container-mode coverage MUST NOT require a manual
  step per run. Any one-time maintainer setup that remains MUST be
  documented and MUST produce a clear, named failure when absent rather
  than a silent skip.
- **FR-016**: The reference image for the container leg MUST be
  [NEEDS CLARIFICATION: a project-owned image built and published by this
  repository, or an existing third-party public image already satisfying
  the required-tool list? See Question 1.]
- **FR-017**: The image reference MUST reach the test repository by
  [NEEDS CLARIFICATION: automatic scaffolding as part of the existing
  fixture-scaffold step, or a maintainer-configured repository variable on
  the test repository, set once? See Question 2.]
- **FR-018**: The container leg MUST run at a cadence of
  [NEEDS CLARIFICATION: every scheduled verification alongside the
  default-runner leg (gating every release), alternating with it, or on a
  separate lower-frequency schedule that does not gate the release
  decision? See Question 3.]

### Key Entities

- **Execution mode**: One of the two supported ways a stage's jobs run —
  directly on a runner, or inside a container image. The verification's
  unit of coverage.
- **Reference image**: The container image the container-mode leg pins.
  Has a home, an owner, an update trigger, and a visibility (public or
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
  every stage of the chain, by the scheduled verification at its decided
  cadence, with zero manual steps required per run.
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
- **SC-005**: A verification run that exercises both legs completes within
  the verification job's declared time bound, with no leg killed before it
  can write a verdict.
- **SC-006**: A maintainer can suppress the container leg and restore it
  through a single configuration change, without editing or pausing
  auto-release itself.
- **SC-007**: Drift between the canonical required-tool list and the
  reference image is detected by the verification, with a report that
  names every missing tool at once.

## Assumptions

- The existing default-runner end-to-end leg continues to run and to gate
  releases; this feature adds container-mode coverage rather than
  replacing the coverage that exists today.
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
- Agent usage consumed by a second full feature run is accepted as the
  cost of the coverage; the cadence question below is where that cost is
  traded off.
- The related on-demand scratch-repository provisioning work (issue #362)
  may change how test repositories are obtained. This spec states a
  constraint on leg isolation (FR-008) rather than assuming either a
  single shared repository or per-leg repositories.
- The project's published position that container images are
  bring-your-own is assumed to hold unless Question 1 is answered in a way
  that deliberately changes it.

## Open Questions

Three decisions carry trade-offs the owner should make; they are the
`[NEEDS CLARIFICATION]` markers above.

## Question 1: Reference image provenance and ownership

**Context**: FR-016. The project publishes no Dockerfile and hosts no
reference image; adoption documentation presents `container-image` as
strictly bring-your-own. The container leg needs *some* image that
satisfies the canonical required-tool list (`git`, `gh`, `jq`, `curl`,
`python3`, `bash`, `node`, `timeout`).

**What we need to know**: Should the project build and publish its own
minimal reference image, or pin an existing third-party public image that
already satisfies the list?

**Suggested Answers**:

| Option | Answer | Implications |
|--------|--------|--------------|
| A      | Build and publish a minimal project-owned image to this org's container registry | Full control over contents; the required-tool list and the image can be kept in agreement by a check; adds an image build/publish pipeline and an ongoing upkeep obligation; risks being read by adopters as a supported image unless documented otherwise |
| B      | Pin an existing third-party public image that already satisfies the list | No build pipeline, no hosting, no upkeep; verification now depends on an upstream the project does not control, which can change or disappear and block releases for reasons unrelated to this repository |
| C      | Reuse the existing private dogfood image already referenced by this repository's own configuration | No new artifact; exercises the private-registry credential path for real (FR-014); ties release verification to a private package and to credentials configured on the test repository |
| Custom | Provide your own answer | State the image, its home, and who maintains it |

## Question 2: How the image reference reaches the test repository

**Context**: FR-017. Every wrapper reads the container image from a
repository variable on the consuming repository, which on the test
repository is currently unset — which is exactly why container mode is
never entered. The verification already rewrites parts of the fixture it
scaffolds.

**What we need to know**: Should the verification configure the image
reference on the test repository itself as part of scaffolding, or should
it stay a repository variable a maintainer sets once, the way the test
repository's own identity is configured?

**Suggested Answers**:

| Option | Answer | Implications |
|--------|--------|--------------|
| A      | The verification scaffolds the image reference onto the test repository each run | Zero per-run manual steps and no drift between what the verification intends and what the test repository is configured with; requires the verification's token to carry permission to write repository configuration, widening what that token can do |
| B      | The image reference stays a maintainer-set repository variable on the test repository | No new permission on the verification's token; matches how the test repository itself is configured today; introduces a one-time manual setup whose absence must fail loudly (FR-015) rather than silently skipping the leg |
| C      | The verification bakes the reference into the scaffolded fixture files rather than into repository configuration | No new permissions and no manual setup; the scaffolded fixture then differs from the wrapper an adopter would actually write, weakening the claim that the leg exercises the adopter's own configuration path |
| Custom | Provide your own answer | State the mechanism and what it requires of the verification's permissions |

## Question 3: Cadence, and whether the container leg gates the release

**Context**: FR-018, User Story 3. The existing verification occupies
roughly one to two hours of wall clock. A second full feature run in
container mode roughly doubles that, against a job that already carries a
finite time bound.

**What we need to know**: Should the container leg run on every scheduled
verification and gate every release, or less often — and if less often,
does a failure still block a release?

**Suggested Answers**:

| Option | Answer | Implications |
|--------|--------|--------------|
| A      | Every scheduled run, both legs, both gating | Strongest guarantee: no release ships without container-mode coverage; roughly doubles verification time and agent spend per release, and pushes against the job's time bound; a flaky container leg blocks releases |
| B      | Alternate modes between scheduled runs — one leg per run, each gating the release it verifies | Constant per-run cost and time; every release is gated by one mode, and container mode is covered on a predictable cadence; a given release may be gated only by the mode it did not most need |
| C      | Container leg on its own lower-frequency schedule, reporting independently and not gating releases | No effect on release cadence or per-release cost; regressions are detected within the leg's period rather than before the release that introduced them; needs its own reporting path so a failure is not merely a red run nobody reads |
| Custom | Provide your own answer | State the cadence and whether a container-leg failure blocks a release |
