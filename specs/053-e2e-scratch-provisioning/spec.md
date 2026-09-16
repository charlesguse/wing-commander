# Feature Specification: On-demand E2E scratch repository provisioning

**Feature Branch**: `053-e2e-scratch-provisioning`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description (GitHub issue #362): "Let an agent provision a fresh, immediately-testable E2E scratch repo on demand — today both E2E verification points (`WING_COMMANDER_AUTO_RELEASE_E2E_REPO` and `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_SCRATCH_REPO`) require a pre-created, maintainer-onboarded repository, set up by hand once (create the repo, install the wing-commander App on it, add its Claude credential, create its `spec-request` label). `docs/setup.md` documents why the automation stops there on purpose, and this issue is not asking to cross that boundary inside any App-token-scoped workflow step. The ask is narrower: running a fresh end-to-end verification requires a human to first walk through that one-time manual onboarding before an agent can dispatch anything against it. It would help to have a spec'd, scripted (or agent-assisted, using credentials the App itself is never granted) path to stand up a throwaway scratch repo that's immediately ready for `auto-release.yml` (or the spec-kit e2e-stage) to target."

## Overview

Two verification points in this repository need a *separate* GitHub repository
to run against:

- `auto-release.yml`'s `verify-e2e` job needs a **fully onboarded** target —
  its own wing-commander App installation, its own Claude credential, its own
  `spec-request` label, and the installed wrapper workflow set, because the
  run exercises that wrapper set end to end.
- the spec-kit updater's `e2e-stage` needs an **empty scratch** target — App
  installed for Contents read/write, nothing else.

Both targets exist only because a maintainer built one by hand, once. Nothing
in the repository can stand up a second one, so a session that wants to verify
a change end to end either borrows the one that exists or waits for a human.

This feature closes that gap **without** changing what any stage's App
installation token is allowed to do. Repository creation stays outside the
pipeline's token, exactly as `docs/setup.md` says it must; what this feature
adds is a single, documented, repeatable provisioning path a maintainer or an
agent can invoke with a credential the App is never granted — the
maintainer's own `repo`-scoped GitHub authentication, held locally and never
stored in Actions — which ends with a machine-readable verdict stating
whether the target is ready to be dispatched against.

## Clarifications

### Session 2026-09-16

- Q: Which identity performs the privileged half of provisioning — creating the repository and installing the App? → A: A maintainer's own `repo`-scoped GitHub authentication, exercised locally and never stored as an Actions secret. The provisioning entry point therefore runs outside this repository's workflows, and no secret this repository holds can create a repository at all — the asymmetry `docs/setup.md` documents is preserved by construction rather than by a grant that has to be kept narrow forever. The App installation is not covered by that credential; it is the declared manual step of the next answer. (FR-003, FR-013, FR-014)
- Q: Does "immediately testable" include the App-install step, which GitHub does not let an App grant to itself? → A: No. It means one non-interactive command, after which the target is ready, with installing the wing-commander App on the target as the single declared manual step a human performs in the GitHub UI. Provisioning performs and verifies every other element, reports the App installation as the named remaining action while it is absent, and converges on a re-run once the human has done it. (FR-002, FR-006, FR-015, SC-001, SC-004)
- Q: Are provisioned targets deleted after use, and by whom? → A: They are not deleted at all. Targets are reset and reused indefinitely by the per-run reset behaviour `auto-release.yml` and `e2e-stage` already own, so no credential this feature uses — including the maintainer's local one — is ever exercised for repository deletion, and the `Administration: write` concern never arises on the teardown side. Retiring a target that has outlived its usefulness stays a manual maintainer action in the GitHub UI, outside this feature. (FR-005, FR-007, FR-016, User Story 3)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stand up a ready-to-target E2E repository on demand (Priority: P1)

A maintainer (or an agent session working on their behalf) is verifying a
change to `auto-release.yml` and has no E2E target available — the existing
one is mid-run, is in an unknown state, or has never been created under this
account. They invoke one documented provisioning entry point locally, under
their own `repo`-scoped GitHub authentication, naming the target repository
and which kind of target they need. When it finishes, the target either *is*
ready to be dispatched against, or the output names precisely which
onboarding element is still missing and what to do about it — in the normal
case that is the one declared manual step, installing the wing-commander App
on the new repository, after which a second invocation of the same command
reports ready.

**Why this priority**: this is the whole ask. Everything else in this spec is
either a safety rail around it or a convenience on top of it. On its own it
removes the "wait for a maintainer to onboard a repo" step that blocks a
fresh end-to-end verification today.

**Independent Test**: point the provisioning entry point at a repository name
that does not exist yet, run it, and then run the existing reachability
diagnostic (and a real dispatch) against the resulting repository — the
dispatch reaches the agent stages rather than failing on infrastructure.

**Acceptance Scenarios**:

1. **Given** a repository name that does not exist under the target owner,
   **When** provisioning runs for the auto-release target profile, **Then**
   the repository exists, carries the `spec-request` label, carries a Claude
   credential its workflows can read, carries the wrapper workflow set, and
   the final report states which onboarding elements are ready and names the
   App installation as the remaining manual step if a human has not performed
   it yet.
2. **Given** provisioning has completed and reported the target ready,
   **When** `auto-release.yml`'s end-to-end verification is dispatched
   against it, **Then** the run gets past every infrastructure check
   (reachability, default-branch reset, scaffold, kickoff) rather than
   reporting an infrastructure failure.
3. **Given** a target that already exists and is already fully onboarded,
   **When** provisioning is run against it again, **Then** it reports ready,
   changes nothing that was already correct, and does not fail.
4. **Given** an onboarding element the maintainer's credential cannot perform
   — the App installation, which GitHub does not let an App grant itself —
   **When** provisioning reaches that element, **Then** it reports the target
   as **not** ready and names the exact remaining step, and where to take it,
   rather than reporting success with a gap.
5. **Given** the human has since installed the App on the target, **When**
   the same command is invoked a second time, **Then** it completes any
   element that was blocked behind the installation and reports ready,
   without redoing or undoing what the first invocation already did.

---

### User Story 2 - Know the target's readiness without spending an agent run (Priority: P2)

Before dispatching anything, a maintainer or agent asks "is this target
actually ready?" and gets an itemised answer — repository reachable, App
installation covering it, Claude credential present, `spec-request` label
present, wrapper set installed — without burning a Claude turn or reading a
failed run's log to find out.

**Why this priority**: the repository already has this shape for one element
(`auto-update-spec-kit-scratch-preflight.yml` answers "can the App mint a
token for the scratch repo?" for one runner-minute and zero Claude quota).
Extending that to the full onboarding checklist is what makes the P1 output
trustworthy and makes a half-provisioned target diagnosable, but P1 delivers
value without it.

**Independent Test**: run the readiness check against the hand-onboarded
target that exists today — it reports ready; run it against a repository
missing the label — it reports not-ready and names the label.

**Acceptance Scenarios**:

1. **Given** a target missing exactly one onboarding element, **When** the
   readiness check runs, **Then** it reports not-ready and names that element
   specifically, not a generic failure.
2. **Given** a fully onboarded target, **When** the readiness check runs,
   **Then** it reports ready and consumes no Claude quota.
3. **Given** the readiness check cannot reach the target at all, **When** it
   runs, **Then** it fails loudly rather than reporting "nothing found" as a
   pass (constitution VIII).

---

### User Story 3 - Reuse one scratch target instead of accumulating new ones (Priority: P3)

A target that has served one verification is still sitting there when the
next one starts. The maintainer wants the next verification to reuse it —
converged back to a ready state by the same provisioning command — rather
than standing up a second repository beside it, and wants deleting a
repository to stay something a human does by hand, never something any
credential in this feature is exercised for.

**Why this priority**: reuse is what keeps scratch repositories from
accumulating, and the first two stories work without it — a maintainer can
point provisioning at a fresh name every time. Nothing is blocked on it, so
it comes last.

**Independent Test**: provision a target, dispatch a verification against it,
then run provisioning against that same target again — it reports ready,
creates no second repository, and deletes nothing.

**Acceptance Scenarios**:

1. **Given** a target left behind by a previous verification, **When**
   provisioning is run against it again, **Then** it reports ready, reuses
   the existing repository, performs no deletion, and leaves the per-run
   reset to `auto-release.yml` / `e2e-stage` as it does today.
2. **Given** a maintainer wants a target gone for good, **When** they consult
   the documentation, **Then** it names repository deletion as a manual
   action they take in the GitHub UI, and no entry point in this repository
   offers to perform it.
3. **Given** a repository that is not a verification target (including this
   repository itself), **When** provisioning is pointed at it, **Then** it
   refuses and reports why rather than converging it toward a scratch
   target.

---

### Edge Cases

- A requested repository name that already exists under the target owner is
  adopted and converged in place, never deleted and recreated (FR-005,
  FR-016) — but what distinguishes "an existing scratch target" from "a
  repository that merely shares the name"?
- What happens when the target owner is an organisation rather than a user
  account, where App installation and repository-creation permissions differ?
- What happens when provisioning is interrupted partway (repository created,
  credential not yet written)? A re-run must converge rather than duplicate
  or double-fail.
- What happens when the App is installed on the owner but its repository
  *selection* does not cover the new repository — the case
  `auto-update-spec-kit-scratch-preflight.yml` exists precisely because it is
  easy to misread in the GitHub UI.
- What happens when the target is pointed at this repository itself?
  `auto-release.yml` already refuses that case because it force-resets the
  target's default branch; provisioning must refuse it too.
- What happens when the target already has open issues or pull requests from
  a prior run?
- What happens when the provisioning credential is expired, unscoped, or
  absent — the failure must be attributable to the credential, not reported
  as a broken target.
- What happens when a secret value would otherwise appear in a log, a job
  summary, or an issue comment?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The repository MUST provide a single documented provisioning
  entry point that takes a target repository identifier and a target profile,
  and drives that target toward being immediately usable as an E2E
  verification target.
- **FR-002**: Provisioning MUST cover every onboarding element an E2E target
  needs for its profile — the repository itself, the wing-commander App
  installation covering it, a Claude credential its workflows can read, the
  `spec-request` label, and (for the auto-release profile) the wrapper
  workflow set — either by performing the element or by verifying it is
  already in place.
- **FR-003**: Provisioning MUST NOT widen what any pipeline stage's App
  installation token can do. No stage may gain repository creation or
  deletion permission, and no `Administration` grant may be added to the App
  installation the stages use. The privileged half of provisioning runs under
  a separate credential that stage workflows never receive.
- **FR-004**: Provisioning MUST finish with a machine-readable report that
  states, per onboarding element, whether it is ready, and MUST NOT report
  the target as ready while any element for the chosen profile is missing.
- **FR-005**: Provisioning MUST be re-runnable against the same target: a
  second run against an already-ready target reports ready, performs no
  destructive action, and exits successfully.
- **FR-006**: When an onboarding element cannot be completed by the credential
  in use, provisioning MUST report the target as not-ready and name the exact
  remaining action a human must take, including where to take it.
- **FR-007**: Provisioning MUST refuse to act on this repository itself, and
  MUST refuse any target it cannot establish as a reusable scratch
  verification target, reporting the refusal rather than proceeding.
- **FR-008**: The readiness determination MUST be computed by deterministic
  code, not by an agent's judgement, so that an agent-driven session and a
  maintainer-run invocation reach the same verdict from the same target state
  (constitution IX).
- **FR-009**: Provisioning MUST NOT emit any credential value into a log, a
  job summary, a commit, an issue comment, or a pull request body.
- **FR-010**: The provisioning logic MUST have exactly one home shared by both
  target profiles, with the profiles differing only in which onboarding
  elements they require — not two parallel copies of the same steps.
- **FR-011**: Existing hand-onboarded targets MUST keep working unchanged: the
  `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` and
  `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_SCRATCH_REPO` contract stays
  `OWNER/NAME`, and neither `auto-release.yml`'s nor `e2e-stage`'s own
  reset/scaffold behaviour changes.
- **FR-012**: Documentation MUST be updated so that `docs/setup.md`'s
  pre-created-repository rows and `docs/adoption.md`'s onboarding walkthrough
  point at the provisioning entry point, and so that the existing statement
  that the pipeline never creates or deletes repositories remains true as
  written for every App-token-scoped step.
- **FR-013**: Provisioning MUST be invocable in a way that requires no
  interactive prompts, so an agent session can run it unattended against an
  already-authenticated local `gh` and act on its report. It MUST NOT prompt
  for the credential, and MUST NOT block waiting on the declared manual App
  installation — it reports that element as not-ready and exits.
- **FR-014**: The identity that creates the repository MUST be a maintainer's
  own `repo`-scoped GitHub authentication, exercised locally and never stored
  as an Actions secret in this repository. No workflow in this repository may
  hold a credential capable of creating a repository, so the provisioning
  entry point MUST be runnable from a maintainer's (or an agent session's)
  local environment rather than requiring a workflow run.
- **FR-015**: "Immediately testable" MUST mean one non-interactive command
  after which the target is ready, with installing the wing-commander App on
  the target as the single declared manual step a human performs in the
  GitHub UI. Provisioning MUST perform and verify every other onboarding
  element itself, MUST report the App installation as the named remaining
  action for as long as it is absent, and MUST converge to ready when
  re-invoked after the human has performed it. No second manual step may be
  introduced.
- **FR-016**: Provisioned targets MUST NOT be deleted by this feature.
  Targets are reset and reused indefinitely by the per-run reset behaviour
  `auto-release.yml` and `e2e-stage` already own; no entry point this feature
  adds may delete or archive a repository, and no credential it uses —
  including the maintainer's own — is exercised for repository deletion.
  Documentation MUST name retiring a target as a manual maintainer action
  taken in the GitHub UI, outside the automation.
- **FR-017**: Provisioning MUST [NEEDS CLARIFICATION: the reply on issue #362
  asked to "fold in the container-image scope" without naming which scope is
  meant — should provisioning pin the container image the provisioned
  target's wrapper workflows run the stages in, defaulting to the image this
  repository pins today; should the provisioning entry point itself be
  required to run inside that image, so a maintainer run and an agent run use
  identical tooling; or should the container image become a per-invocation
  parameter of the target profile, so a target can be stood up against a
  candidate image for verification?]

### Key Entities

- **Target profile**: the named set of onboarding elements a verification
  point requires. Two exist — the auto-release profile (full adopter
  onboarding, including the wrapper set) and the spec-kit scratch profile
  (empty repository, App installed for Contents read/write only).
- **Onboarding element**: one independently checkable precondition of a
  target — repository exists, App installation covers it, Claude credential
  present, `spec-request` label present, wrapper set installed.
- **Readiness report**: the per-element ready/not-ready verdict produced by
  provisioning and by the standalone readiness check, including the named
  remaining action for each not-ready element.
- **Provisioning credential**: the maintainer's own `repo`-scoped GitHub
  authentication, used locally for the privileged half of provisioning
  (repository creation, secret writing, label and wrapper-set creation) —
  never stored in Actions and never available to any stage's App
  installation token. It does not install the App; that is the declared
  manual step.
- **Declared manual step**: installing the wing-commander App on the target,
  performed by a human in the GitHub UI. The one thing provisioning reports
  rather than performs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A maintainer or agent can go from "no E2E target exists" to "a
  target that a verification dispatch reaches the agent stages against" in
  one invocation, the one declared manual step (installing the App), and one
  confirming re-invocation of the same command — under 15 minutes of
  wall-clock time in total.
- **SC-002**: The readiness report accounts for 100% of the onboarding
  elements the chosen profile requires; no element is silently assumed.
- **SC-003**: Re-running provisioning against an already-ready target
  produces the same ready verdict and zero changes to the target.
- **SC-004**: A session verifying an `auto-release.yml` change no longer
  depends on a maintainer having pre-onboarded a target beforehand — the
  dependency is reduced to exactly one declared manual step, installing the
  App on the target.
- **SC-005**: The permissions held by the App installation that stage
  workflows use are unchanged from before this feature, verifiable by
  comparing the declared grants.
- **SC-006**: Diagnosing a not-ready target costs zero Claude quota and one
  runner-minute or less, matching the cost of the reachability diagnostic
  that exists today.
- **SC-007**: Provisioning logic appears in exactly one place; a second copy
  of any onboarding step in a second workflow or script is detectable by a
  gate rather than by a reviewer's memory.
- **SC-008**: No entry point this feature adds can delete or archive a
  repository, verifiable by inspecting the provisioning surface for any
  deletion call — targets accumulate only when a maintainer deliberately
  names a new one instead of reusing an existing target.

## Assumptions

- Both verification points share one provisioning home, parameterised by
  target profile, rather than getting separate paths. `CLAUDE.md`'s "shared
  logic has exactly one home" rule makes a second copy of the onboarding
  steps a known-cost mistake, and the auto-release profile is a superset of
  the spec-kit scratch profile rather than a different shape. (This resolves
  the fourth open question in issue #362 by informed default; the clarify
  stage may overturn it.)
- The documented security boundary stands: no App-token-scoped workflow step
  gains repository creation or deletion ability. This is stated as a
  constraint in the issue, not a question, and FR-003 encodes it.
- Provisioned targets live under the same account as the existing
  hand-onboarded targets; multi-owner and organisation-owned targets are
  supported only to the extent the chosen credential already allows, and are
  not a goal of this feature.
- Repository-level configuration a target needs beyond the listed onboarding
  elements (branch protections, environments, runner labels) is out of scope;
  a verification target runs with defaults.
- `auto-release.yml` and `e2e-stage` keep owning their own per-run reset and
  scaffold behaviour. Provisioning stops at "ready to be targeted"; it does
  not scaffold a candidate or dispatch a run.
- The one-time GitHub App used by the pipeline today is not re-scoped by this
  feature, and no second App is introduced: the privileged half runs under a
  maintainer's local `repo`-scoped authentication (FR-014), so the only
  identity that can create a repository is a human's, held outside Actions.
- A maintainer running provisioning is already `gh`-authenticated with
  `repo` scope for the target owner; obtaining or rotating that
  authentication is outside this feature.
