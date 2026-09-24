# Feature Specification: Container-Mode Evidence in End-to-End Release Verification

**Feature Branch**: `067-e2e-container-image-evidence`

**Created**: 2026-09-24

**Status**: Draft

**Input**: Lifecycle issue [#509](https://github.com/charlesguse/wing-commander/issues/509) — "auto-release E2E: a container-mode pass cannot detect an unset test-repository container image variable" (routed from the board loop; originating issue [#390](https://github.com/charlesguse/wing-commander/issues/390))

## Context

The scheduled end-to-end release verification alternates between two
legs: a default-runner leg and a container leg. On a container-mode turn
the whole point of the run is that every stage job of the scaffolded
fixture executes inside a container image — the image reference comes
from a variable a maintainer sets once on the test repository, exactly as
an adopter would configure it.

Nothing the verification can read today tells it whether that variable is
actually set. When it is unset, the scaffolded wrappers fall back to
hosted runners, the per-stage prerequisite check has no image to pull and
succeeds vacuously, the feature is carried end to end successfully, and
the run reports a container-mode `pass`. The one path that *is* detected
is an image that was configured but could not be pulled or authorized:
the failing stage posts a chain-stop notice the poll step can read with
the permissions it already holds. "Never attempted" and "succeeded" look
identical from outside the test repository.

The previous feature (`specs/054-e2e-container-coverage`) recorded this
as an accepted gap with the repository owner's agreement: its FR-004 and
FR-006 forbid exactly this silent degradation, its contract still says an
unset variable "MUST produce fail-infra", and both `docs/setup.md` and
`docs/architecture.md` carry the caveat. The gap was accepted because
closing it needs access the verification did not have — the test
repository's own configuration, or its Actions run data.

What has changed since is that `specs/055-unattended-e2e-gates` shipped a
dedicated fixture-maintainer credential for this same test repository,
already checked for validity and for containment early in the
verification job. That makes at least one route to the missing evidence
cheap, and turns the question into a decision the repository owner has to
make rather than a permission nobody holds.

This feature closes the gap: a container-mode run must earn its `pass` by
observing that container mode was actually configured, and must report an
unconfigured turn as an infrastructure-class failure instead of a green
check that means less than it says (Constitution VIII).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An unconfigured container turn fails instead of passing (Priority: P1)

As the maintainer of this repository, when a scheduled verification takes
its container-mode turn against a test repository whose container image
variable was never set (or was cleared, or was set to an empty value), I
want the run to fail with an infrastructure-class verdict that names the
missing configuration, so that a release is never cut on the strength of
a container-mode pass that ran entirely on hosted runners.

**Why this priority**: This is the defect in the issue and the whole
value of the feature. Everything else here exists to keep this detection
honest.

**Independent Test**: Point the verification at a test repository with
the image variable unset, run a container-mode turn, and observe a
failing infrastructure-class verdict naming the unset variable and no
release dispatched. Then set the variable and observe the same turn reach
a pass that records the image reference it observed.

**Acceptance Scenarios**:

1. **Given** a container-mode turn and a test repository whose container
   image variable is unset, **When** the verification runs, **Then** it
   produces an infrastructure-class verdict that names the unset variable
   and the test repository, records container mode as not configured, and
   dispatches no release.
2. **Given** a container-mode turn and a test repository whose container
   image variable is set to an empty value, **When** the verification
   runs, **Then** it produces the same infrastructure-class verdict as
   the unset case — an empty value is not a configured image.
3. **Given** a container-mode turn and a correctly configured test
   repository, **When** the verification runs and the chain completes,
   **Then** the verdict is a pass that records container mode as
   configured together with the image reference the evidence named.
4. **Given** a container-mode turn whose configured image cannot be
   pulled or authorized, **When** the verification runs, **Then** the
   existing attempted-and-failed classification is what it reports — this
   feature does not reclassify it as "not configured".
5. **Given** a default-runner turn, **When** the verification runs,
   **Then** no container-image evidence is required, and the run behaves
   exactly as it does today.

---

### User Story 2 - The evidence check fails closed (Priority: P1)

As the maintainer, when the verification cannot obtain the evidence it
needs — the credential is missing, the access was revoked, the API
refuses or rate-limits the read — I want the run to say so in an
infrastructure-class verdict naming the unreadable evidence, so that a
broken detector can never quietly restore the old silent pass.

**Why this priority**: A detector that degrades to "assume configured" is
the same defect this feature exists to remove, one layer up. It ships
with User Story 1 or not at all.

**Independent Test**: Remove or invalidate the access the evidence check
depends on, run a container-mode turn, and observe an
infrastructure-class verdict naming the unobtainable evidence rather than
a pass.

**Acceptance Scenarios**:

1. **Given** a container-mode turn whose evidence source cannot be read
   (missing credential, revoked access, insufficient permission),
   **When** the verification runs, **Then** it produces an
   infrastructure-class verdict naming the evidence it could not obtain
   and how to restore it, and dispatches no release.
2. **Given** a container-mode turn whose evidence read is refused by a
   transient condition such as an API rate limit, **When** the
   verification runs, **Then** it produces an infrastructure-class
   verdict attributing the failure to that condition, distinct from the
   "not configured" verdict.
3. **Given** any container-mode verdict this feature can emit, **When**
   the reporting step renders it, **Then** the report names the failing
   check and the evidence location, and the verdict carries the
   container-mode configured flag as false.

---

### User Story 3 - A misconfigured turn is cheap (Priority: P2)

As the maintainer, when a container-mode turn is going to fail for lack
of configuration, I want that discovered before the run spends a full
stage chain's worth of agent turns and wall clock, so that a
misconfiguration costs a fast failure instead of two hours of the shared
usage window.

**Why this priority**: The detection is correct either way; this story is
about what it costs. It is separable — the check could be read at verdict
time and still satisfy User Story 1 — but the early read is what makes
the feature affordable to leave on.

**Independent Test**: Unset the variable, run a container-mode turn, and
observe the run reaching its failing verdict without having created the
kickoff issue or driven any stage.

**Acceptance Scenarios**:

1. **Given** a container-mode turn with the variable unset, **When** the
   verification runs, **Then** it reaches its verdict before the kickoff
   issue is created and before any stage agent turn is spent.
2. **Given** a container-mode turn with the variable unset, **When** the
   verification reaches its verdict early, **Then** the test repository
   is left in a state a subsequent, correctly configured run can use
   without manual cleanup.

---

### User Story 4 - The record stops describing the gap as accepted (Priority: P3)

As a reader of this repository's documentation and specs, I want the
accepted-gap language about the unset container image variable removed
once the gap is closed, and the new requirement (whatever access the
detection needs) documented in its place, so that the setup
documentation, the architecture notes and the governing spec agree with
what the verification actually does.

**Why this priority**: Stale caveats are how the next maintainer relearns
a solved problem. It is real work but it follows the behaviour.

**Independent Test**: Search the documentation and the prior spec's
requirements and contract for the accepted-gap wording and find none,
with each site instead stating the detection and its prerequisite.

**Acceptance Scenarios**:

1. **Given** this feature has shipped, **When** a maintainer reads the
   setup documentation, **Then** it states what the container leg
   requires on the test repository and what the verification does when
   that requirement is unmet, with no "known limitation" carve-out for
   the unset case.
2. **Given** this feature has shipped, **When** a maintainer reads the
   prior container-coverage spec's FR-004/FR-006 and its contract,
   **Then** the accepted-gap notes are replaced by a pointer to this
   feature's behaviour.
3. **Given** a future change re-introduces a container-mode pass path
   that does not consult the evidence, **When** the gate suite runs,
   **Then** a gate fails and names the unguarded path.

---

### Edge Cases

- The variable is **absent** versus **present but empty**: both mean "not
  configured" and produce the same verdict; an adopter's empty value is a
  documented, legitimate way to say "no container", which is precisely
  what a container-mode turn must not accept.
- The variable is **set but not consumed** — the scaffolded fixture's
  passthrough is missing or broken, so the chain still runs on hosted
  runners. Whether this is detected depends on how deep the evidence goes
  (see the open question on proof depth).
- The configuration **changes mid-run**: set at check time and removed
  before the chain runs, or vice versa. The verdict reports what was
  observed, and the observation's timing is part of the evidence.
- The evidence source is **unreachable** (credential missing, access
  revoked, rate-limited): fails closed, never assumed configured.
- The evidence-bearing credential reaches **more than the test
  repository**: containment must be checked the way the existing fixture
  maintainer credential's reach already is, before it is used.
- The container leg is **paused**: the turn runs the default-runner leg
  and reports container mode as not exercised; no evidence is required
  and no new failure mode appears.
- A **manually dispatched** verification in container mode is subject to
  the same evidence requirement as a scheduled one.
- The image is configured, pullable, and **missing a required tool**: the
  existing prerequisite-failure classification stands unchanged.
- The test repository variable is readable but holds a **moving tag**
  rather than a digest: what this means for the verdict depends on the
  open question on accepted values.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The verification MUST NOT report a passing verdict for a
  container-mode run unless it has observed positive evidence that the
  test repository was configured to run the stage chain inside a
  container image. Absence of evidence MUST NOT be read as configured.
- **FR-002**: A container-mode run whose test repository has no container
  image configured — the variable absent, or present with an empty value
  — MUST produce an infrastructure-class verdict that names the missing
  configuration and the test repository, MUST record container mode as
  not configured, and MUST NOT dispatch a release.
- **FR-003**: The verification MUST obtain that evidence via
  [NEEDS CLARIFICATION: which access route closes the gap — (a) read the
  test repository's container image variable with the existing fixture
  maintainer credential, (b) grant the App installation on the test
  repository read access to that repository's Actions run data or
  variables, (c) have the verification write the variable itself on
  container-mode turns, or (d) some combination]. Whichever route is
  chosen, the access MUST be scoped to the test repository alone and MUST
  be verified at the start of the run rather than discovered mid-flight.
- **FR-004**: The evidence check MUST fail closed: when the evidence
  cannot be obtained — credential unset, access insufficient or revoked,
  the read refused, rate-limited or erroring — the run MUST produce an
  infrastructure-class verdict naming the evidence it could not obtain,
  never a pass and never a silently downgraded default-runner pass.
- **FR-005**: The verdict MUST distinguish, as separate named outcomes,
  (i) container mode never configured, (ii) container mode configured but
  the image could not be obtained or inspected, (iii) the evidence itself
  unreadable, and (iv) container mode configured and exercised. Case (ii)
  MUST keep the classification it has today.
- **FR-006**: The evidence MUST establish [NEEDS CLARIFICATION: how deep
  the proof must go — (a) configuration evidence only: the test
  repository declares a container image, or (b) execution evidence: the
  stage jobs of this run actually executed inside a container. Option (a)
  closes the reported defect and needs the least access; option (b) also
  catches a configured-but-unconsumed image and a fixture whose
  passthrough regressed].
- **FR-007**: A configured value MUST be accepted or rejected according
  to [NEEDS CLARIFICATION: what counts as configured — (a) any non-empty
  value, (b) any non-empty value that is pinned by digest, or (c) a value
  matching this repository's own pinned reference image. Stricter answers
  catch a stale or moving pin, and make the verification depend on the
  reference image's publication cadence].
- **FR-008**: The container-mode evidence requirement MUST apply on every
  container-mode run, scheduled or manually dispatched, and MUST NOT
  apply on a default-runner run, which MUST behave exactly as it does
  today with no new failure mode.
- **FR-009**: The verdict field that states whether container mode was
  configured MUST be true only on a run where the evidence was observed,
  preserving today's honest default of false on every other path.
- **FR-010**: The run's report MUST let a maintainer tell the outcomes in
  FR-005 apart without opening the test repository, by naming the failing
  check, what was expected, what was observed, and where the evidence
  was read.
- **FR-011**: Reaching the failing verdict for an unconfigured
  container-mode turn MUST NOT require the run to drive the stage chain:
  the run MUST reach that verdict before the kickoff issue is created and
  before any stage agent turn is spent.
- **FR-012**: A run that ends at the unconfigured verdict MUST leave the
  test repository in a state a later, correctly configured run can use
  without manual cleanup.
- **FR-013**: Whatever credential or permission the chosen route requires
  MUST be documented as a setup prerequisite, with its least-privilege
  scope stated, and its absence or insufficiency MUST surface as the
  named infrastructure-class verdict of FR-004 rather than as an
  unexplained failure.
- **FR-014**: If the chosen route uses a credential that can reach
  repositories beyond the test repository, the run MUST verify that
  containment at runtime before using it, the way the existing fixture
  maintainer credential's reach is already checked.
- **FR-015**: The prohibition in FR-001 MUST be enforced by a
  deterministic gate — reachable through the existing gate registry,
  triggered by changes to the verification it checks, running the same
  subject locally and in CI — that fails when a container-mode pass path
  can be reached without consulting the evidence. Every failure branch
  the gate ships MUST be exercised by a checked-in fixture.
- **FR-016**: The documentation and specification sites that currently
  describe this case as an accepted gap — the setup documentation, the
  architecture notes, and the prior container-coverage spec's FR-004,
  FR-006 and contract — MUST be updated to describe the detection and its
  prerequisite instead, with no remaining carve-out saying the unset case
  cannot be told apart.
- **FR-017**: The container leg's existing kill switch MUST keep working
  unchanged: while the leg is paused, a turn that would have been
  container mode runs the default-runner leg, reports container mode as
  not exercised, and requires no evidence.

### Key Entities

- **Container-mode evidence**: the observation that justifies a
  container-mode pass — what was read, from where, and when, carried into
  the verdict and the report. Its absence, not merely its negative value,
  is a failure.
- **End-to-end verdict**: the existing per-run record the release
  decision and the report both read — outcome, verified head, failing
  check, expected, observed, evidence location, execution mode, and the
  container-mode configured flag. This feature constrains when that flag
  may be true and adds the outcomes of FR-005.
- **Test repository container image configuration**: the maintainer-set
  image reference on the test repository that makes a container-mode turn
  real. Absent or empty means "no container", which is legitimate for an
  adopter and disqualifying for a container-mode turn.
- **Evidence access grant**: the credential or permission the run uses to
  obtain the evidence, scoped to the test repository, checked for
  validity and containment before use.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A container-mode verification run against a test repository
  with no container image configured fails with an infrastructure-class
  outcome in 100% of runs, and releases nothing.
- **SC-002**: Zero container-mode runs report a passing outcome without a
  recorded container-mode evidence observation.
- **SC-003**: A container-mode run that will fail for missing
  configuration reaches its verdict without creating a kickoff issue and
  without spending any stage agent turn, in 100% of such runs.
- **SC-004**: 100% of container-mode verdicts state which evidence was
  observed or which evidence could not be obtained.
- **SC-005**: A maintainer reading a failed run's report can tell "never
  configured", "configured but the image was unobtainable" and "evidence
  unreadable" apart without opening the test repository.
- **SC-006**: Every failure branch introduced here — not configured,
  empty value, evidence unreadable, evidence source rate-limited — is
  exercised by a checked-in fixture, and removing the evidence check from
  the pass path fails the gate suite.
- **SC-007**: After this feature ships, zero documentation or
  specification passages describe the unset container image variable as
  an undetectable or accepted gap.
- **SC-008**: Default-runner runs show no change in outcome distribution
  or duration attributable to this feature.

## Assumptions

- The container leg's mode alternation, its kill switch, its time budget
  and its reporting shape are unchanged; this feature constrains only
  what a container-mode run may conclude and when it may conclude it.
- The image reference remains a maintainer-set repository variable on the
  test repository, as the prior feature decided, unless the open question
  on the access route is answered with the option that has the
  verification write it.
- The fixture maintainer credential introduced for the unattended human
  gates continues to exist, is already validated and containment-checked
  early in the run, and is available to this feature if the access-route
  question chooses it.
- "Not configured" is the failure of a *turn*, not a defect in the
  product under verification: it is infrastructure-class, so it blocks
  the release without being reported as a pipeline regression.
- Failing closed on an unreadable evidence source is acceptable even
  though it can block a release on an access problem; the alternative —
  assuming configured — is the defect being fixed. The existing
  infrastructure-class vocabulary already covers this outcome.
- The existing detection of a configured-but-unpullable image (the
  chain-stop notice the failing stage posts) stays as it is and keeps its
  current classification; this feature adds a case in front of it rather
  than replacing it.
- The evidence read is a small, constant number of API calls against the
  test repository, negligible against the run's existing budget.
- No new permission is required on this repository itself, and no
  permission is widened on any repository other than the dedicated test
  repository.
