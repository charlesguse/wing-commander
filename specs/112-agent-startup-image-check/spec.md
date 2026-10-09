# Feature Specification: Agent Start-up Image Check

**Feature Branch**: `spec-draft/112-agent-startup-image-check`

**Created**: 2026-10-09

**Status**: Draft

**Input**: User description: "Image checks prove the agent can start, not just that listed tools exist (#974). The image checks (`verify-image-prerequisites` in every stage, the daily `private-image-dogfood`, and Gate 62 on the reference image) prove a container image holds the tools on the required-tool list; they do not prove the agent can start inside it. On 2026-10-09 intake run 37866026318 and the watchdog's diagnose agent (run 37866135715) both died at the agent action's 'Install Bun' step with `Unable to locate executable file: unzip` while every image check was green. The list modelled Claude Code's own installer, not the agent action's setup, and the action is consumed through a floating tag, so its dependencies can change with no commit here. #973 adds `unzip`; the next undeclared dependency will get through the same way. Proposal: add a check that runs the action's real setup inside the configured image and stops before any model call. Owner trade-offs: where it runs (daily dogfood, every reference-image rebuild, and/or a per-stage preflight costing ~30–60 s per agent job); how it runs (invoke the real action with no credential and assert it fails at authentication rather than setup, which tracks the floating tag but depends on the action's failure shape — or replay the setup steps by hand, which is stable but drifts); and whether to pin the agent action to an immutable revision so dependency changes arrive as reviewable bumps."

## Context

Constitution Principle VIII ("A Green Check Means What It Says") is the
governing principle: today's image checks passed an image the agent could
not start in, so they read as evidence of a usable image while proving only
that a fixed list of executables is present. The list is an *inference*
about what the agent action needs (see the header of
`.github/scripts/required-tools.txt`), and nothing checks the inference.

This spec describes both layers (Principle VII): the published contract
(the stage workflows and `private-image-dogfood.yml` an adopter calls, and
any image-check job they carry) and the consuming instrument (this
repository's own wrappers and the e2e reference image).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An image the agent cannot start in is caught before a lifecycle hits it (Priority: P1)

A maintainer (of this repository, or an adopter running the pipeline in
their own container image) wants to learn that the configured image cannot
start the agent from a check that fails and names the missing piece — not
from a lifecycle stage dying mid-run and a watchdog diagnosis that itself
dies the same way.

**Why this priority**: This is the defect the issue reports. Without it,
every other part of the feature is decoration.

**Independent Test**: Point the start-up check at an image that has every
tool on the required-tool list but lacks one thing the agent action's setup
needs (for example, the image as it was before `unzip` was added). The check
fails, and its failure output names the setup step that failed and the
error it raised. Pointing it at the current reference image passes.

**Acceptance Scenarios**:

1. **Given** an image that passes the tool-presence check but on which the
   agent action's setup cannot complete, **When** the start-up check runs
   against it, **Then** the check fails and its output identifies the setup
   step that failed and quotes the error.
2. **Given** an image on which the agent action's setup completes, **When**
   the start-up check runs against it, **Then** the check passes without
   making any model call and without consuming any model credential.
3. **Given** the agent action's own dependencies change upstream with no
   commit in this repository, **When** the next scheduled start-up check
   runs, **Then** an image now missing the new dependency is reported as
   failing on that run, not on the next lifecycle that happens to use it.

---

### User Story 2 - The check cannot pass without having reached setup (Priority: P1)

A maintainer reading a green start-up check needs it to mean the agent's
setup actually ran to completion in the image — not that the check skipped,
failed early for an unrelated reason, or was satisfied by an error it did
not expect.

**Why this priority**: Principle VIII. A start-up check that passes on any
failure is the same liability as the tool-list check it supplements.

**Independent Test**: Run the check against (a) an image where setup fails,
(b) an image where setup succeeds, and (c) a configuration where the check
cannot reach its subject at all (image unset, image pull fails, the setup
outcome cannot be determined). Only (b) passes; (a) and (c) fail with
distinct, readable reasons.

**Acceptance Scenarios**:

1. **Given** the check cannot determine whether setup completed (unexpected
   failure shape, missing output, unreachable image), **When** it finishes,
   **Then** it fails loudly and says it could not reach its subject, rather
   than passing.
2. **Given** each failure branch the check ships, **When** the gate suite
   runs, **Then** a checked-in fixture exercises that branch.

---

### User Story 3 - Agent-action dependency changes are visible (Priority: P2)

The owner wants a change to what the agent action requires of an image to be
something they can see and decide on, rather than something that arrives
silently through a floating tag.

**Why this priority**: Prevents recurrence at the source; the start-up check
detects, this governs when the change arrives.

**Independent Test**: Depends on the answer to the pinning question below;
under any answer, the spec's documentation of how the agent action is
referenced, and what a dependency change looks like when it arrives, is
reviewable in the repository.

**Acceptance Scenarios**:

1. **Given** the owner's chosen pinning policy, **When** the agent action
   publishes a release that changes its setup dependencies, **Then** that
   change either reaches this repository as a reviewable change (pinned) or
   is caught by the start-up check on its next run (floating), and the
   policy is recorded where both maintainers and adopters can read it.

---

### Edge Cases

- The image cannot be pulled (registry outage, credential error): the check
  fails as "could not reach subject", distinct from "setup failed in image".
- The agent action changes how it fails without a credential (different
  message, different step, succeeds further, or fails earlier): the check
  must not interpret an unrecognised outcome as a pass.
- The agent action's setup downloads from the network and the download is
  transiently unavailable: the failure is reported as setup failing, with
  the quoted error, so a human can tell a flaky fetch from a missing tool.
- The start-up check runs with no model credential available: it must still
  be able to reach and judge the end of setup.
- An adopter's image runs as a non-root user or has a read-only filesystem
  in places the setup writes to: setup failure is reported like any other.
- The required-tool list and the start-up check disagree (the start-up check
  passes an image the tool list rejects, or vice versa): both results are
  reported; neither silently overrides the other.
- No private dogfood image is configured: the dogfood-hosted variant of the
  check (if chosen) no-ops cleanly as the existing dogfood job does.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a start-up check that runs the agent
  action's real setup (everything the action does before its first model
  call) inside a given container image.
- **FR-002**: The start-up check MUST stop before any model call and MUST
  NOT require, read, or consume a model credential.
- **FR-003**: The start-up check MUST fail when the agent action's setup
  cannot complete in the image, and its failure output MUST name the setup
  step that failed and quote the error it raised.
- **FR-004**: The start-up check MUST pass only on positive evidence that
  setup completed; any outcome it cannot classify (unrecognised failure
  shape, missing output, image not pulled, check skipped) MUST fail with a
  reason distinct from "setup failed in image".
- **FR-005**: The start-up check MUST run at [NEEDS CLARIFICATION: where
  should the start-up check run — on the daily private-image dogfood
  schedule, on every reference-image rebuild, as a preflight in every
  agent-bearing stage job (≈30–60 s each), or a combination?].
- **FR-006**: The start-up check MUST determine "setup completed" by
  [NEEDS CLARIFICATION: invoke the real agent action with no credential and
  assert it fails at authentication rather than setup (tracks the floating
  tag automatically, depends on the action's failure shape), or replay the
  action's setup steps directly (stable, but can drift from the action)?].
- **FR-007**: The agent action MUST be referenced according to
  [NEEDS CLARIFICATION: keep the floating major-version tag, or pin to an
  immutable revision so dependency changes arrive as reviewable bumps?],
  and the chosen policy MUST be recorded in the documentation of the image
  prerequisite contract.
- **FR-008**: Every failure branch the start-up check ships MUST be
  exercised by a checked-in fixture, and the check MUST be reachable
  through the gate registry and run identically locally and in CI where it
  is gate-shaped (Principle VIII).
- **FR-009**: The existing tool-presence checks (`verify-image-prerequisites`,
  Gate 23, Gate 62) MUST continue to run unchanged in what they assert; the
  start-up check supplements them and does not replace the required-tool
  list.
- **FR-010**: Any input, secret, or output the start-up check adds to a
  published stage workflow or to `private-image-dogfood.yml` MUST be an
  additive, optional change to the published contract (Principle VII); an
  adopter who changes nothing keeps working.
- **FR-011**: The start-up check MUST NOT hardcode this repository's name,
  owner, or image; the image under test arrives as a declared input
  (Principle VI).
- **FR-012**: When the start-up check fails on a scheduled or rebuild run,
  the failure MUST be visible on the run itself (failed job with the quoted
  reason), so the existing watchdog/board machinery can pick it up without
  a new reporting channel.

### Key Entities

- **Start-up check**: A job or step that executes the agent action's
  pre-model setup inside an image and reports pass / setup-failed /
  could-not-reach-subject, with the failing step and error.
- **Image under test**: The container image a stage would run its agent in
  — the adopter's configured image, the private dogfood image, or the e2e
  reference image.
- **Required-tool list**: The existing declared list of executables
  (`.github/scripts/required-tools.txt`); unchanged by this feature, now
  cross-checked by observed start-up.
- **Agent-action reference policy**: Whether the agent action is consumed by
  floating tag or pinned revision, and where that is recorded.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Run against the reference image as it stood before #973 (no
  `unzip`), the start-up check fails and names the "Install Bun" setup step
  — 100% of the time, with zero model calls made.
- **SC-002**: Run against the current reference image, the start-up check
  passes with zero model calls and zero model-credential use.
- **SC-003**: For every distinct failure branch the check ships, a fixture
  in the gate suite drives that branch and asserts the check fails.
- **SC-004**: After the feature ships, an upstream change to the agent
  action's setup dependencies that breaks a configured image is reported by
  a failing start-up check before, or no later than, the first lifecycle
  stage that would have died on it, at whichever cadence FR-005 settles.
- **SC-005**: No existing adopter wrapper requires a change to keep passing
  its current checks after the feature ships.

## Assumptions

- "Setup" means every step the agent action performs before it first
  contacts the model provider (runtime installs, CLI install, configuration);
  the authentication step is the boundary.
- The auto-release container leg, which already runs a real agent in the
  image, is left as it is; this feature does not replace or reschedule it.
- The start-up check may download the same artifacts the agent action does
  at runtime; network access during the check is acceptable, and its
  failure is reported as a setup failure with the quoted error.
- #973 (adding `unzip` to the required-tool list) lands independently; this
  feature does not depend on it, and SC-001 uses an image without `unzip`
  as its fixture rather than relying on the list.
- Cost of the check is bounded by not calling the model; runner minutes are
  the only cost, and the per-stage preflight option's ≈30–60 s per agent
  job is the upper bound the owner weighs in FR-005.
