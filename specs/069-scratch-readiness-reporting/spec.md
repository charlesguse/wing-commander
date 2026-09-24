# Feature Specification: A readiness verdict that is reachable and documentation that matches it

**Feature Branch**: `069-scratch-readiness-reporting`

**Created**: 2026-09-24

**Status**: Draft

**Input**: User description (GitHub issue #516, routed from the board loop on issue #394; originating issue text): "scratch provisioning: auto-release readiness can never report all-ready, and docs still promise convergence. Findings from the third review of #374 (scratch repository provisioning, spec 053) that did not block the merge. Every functional defect from the first two reviews is fixed; what is left is a spec decision, documentation that still promises what the tool cannot do, and small gaps. **Needs a decision** — (1) `auto-release` readiness can never report all-ready, locally or in CI. `app_installation` is in both profiles, and a maintainer's local run cannot confirm it (the `installation` endpoint is App-JWT-only), so a local `--check-only` exits 1 whenever it is present. In CI the App token cannot read secrets or variables (docs/setup.md declares only Contents, Issues and Pull requests), so `claude_credential` and `container_image_pin` come back \"Not checkable\" and not ready (test t9 T036 asserts this). No route reaches all-ready for `auto-release`; only `spec-kit-scratch` can. That contradicts SC-001 and User Story 1 scenario 5 for that profile. Options: scope SC-001 to `spec-kit-scratch`; treat \"not checkable\" as a distinct non-failing state and report it separately from \"not ready\"; add a local `--assume-app-installed` flag for the manual step; or grant the App Secrets and Variables read on the test repository. **Documentation and spec text that still promise convergence** — (2) `quickstart.md` step 3 says the dispatched readiness check shows every element ready with exit 0 for `profile=auto-release` (see 1). (3) `spec.md:41` says \"converges on a re-run\"; `docs/setup.md:126` and `docs/adoption.md:55-56` still say \"for as long as it is absent\"; `plan.md:73` says \"one re-invocation\". The T050 amendment fixed FR-015, SC-001 and User Story 1 scenario 5 but not these. (4) `contracts/cli.md:19` and `:51` still describe a local read-only check that exits 0 when ready, and `:17` describes the marker refusal as applying to `--check-only` too (it now applies to the mutating path only). (5) `data-model.md:35` still lists `gh api .../installation` and `gh label view` as check calls, and `:39` omits the `--check-only` marker exemption. **Small gaps** — (6) No test for the `GITHUB_REPOSITORY` fallback refusing a self-target. `provision-e2e-target.sh:104-127` falls back to `GITHUB_REPOSITORY` and refuses when it names the target, and the reviewer confirmed it by hand, but t9 T045 covers only the neither-resolves case. (7) `act_repository`'s return code is ignored (`provision-e2e-target.sh:244-246`). If `gh repo create` fails, the run stops at the marker step with a misleading \"failed to write the scratch marker\" message. It fails closed, so nothing is written. (8) A stray `WC_APP_INSTALLATION_KNOWN_READY=true` in a maintainer's shell produces a false-ready local report. Nothing in the docs warns about it; consider ignoring the variable outside CI or printing when it is honoured. (9) t9's `--check-only` exit-0 case only passes by exporting `WC_APP_INSTALLATION_KNOWN_READY=true`. That is a fair stand-in for the CI path, but it hides item 1 for anyone reading the test; say so in the test. Found by the code review of #374. Related: #362, #386."

## Overview

Feature 053 gave this repository a single provisioning entry point
(`provision-e2e-target.sh`) and a readiness check workflow that between them
report, per onboarding element, whether an E2E target is ready to be
dispatched against. Three rounds of review fixed every functional defect.
What survived is a mismatch between the verdict the tool can actually
produce and the verdict its own specification, contracts and adopter-facing
documentation promise.

Concretely, for the `auto-release` profile there is no route — local or
dispatched — that reaches an all-ready verdict:

- Locally, `app_installation` can never be confirmed, because the endpoint
  that would answer it requires App-JWT authentication that no maintainer
  credential can supply. Any local run with that element in its profile
  exits non-zero.
- In CI, the App installation token holds Contents, Issues and Pull requests
  only, so reading the target's secrets and variables is refused. Two
  elements (`claude_credential`, `container_image_pin`) therefore report
  "Not checkable with this token" — and today "not checkable" is folded into
  "not ready", which makes the aggregate verdict not-ready as well.

Only the `spec-kit-scratch` profile, which needs neither of those two
elements, can reach all-ready. Yet `quickstart.md` step 3 tells a maintainer
to expect every element ready and exit 0 for `profile=auto-release`, and
several documents still describe a convergence-on-re-run behaviour that a
later amendment already removed.

This feature makes the verdict and the words about it agree. It is
deliberately narrow: it changes how readiness is *reported* (and possibly
what the `auto-release` profile's success criterion claims), corrects the
documents that overstate it, and closes four small gaps the same review
found. It does not add any new onboarding element, does not change what
provisioning writes, and does not widen any credential beyond whatever
Clarification Q1 resolves.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A maintainer can tell "all clear" apart from "something is wrong" (Priority: P1)

A maintainer has provisioned an `auto-release` target and installed the
wing-commander App on it. They want one signal that says the target is good
to dispatch against. Today they cannot get one: every route reports
not-ready, for reasons that are properties of the checking credential rather
than of the target. They have to read the per-element reasons and decide by
hand which not-ready rows are real — which is exactly the judgement the
readiness report exists to remove.

After this feature, a fully onboarded `auto-release` target produces an
unambiguous all-clear from at least one documented route, and any element
the caller genuinely cannot check is presented as its own state, not as a
failure indistinguishable from a missing secret.

**Why this priority**: this is the defect. Without it the readiness report
for the profile that matters most (`auto-release` is the one `auto-release.yml`
dispatches against) carries no usable aggregate signal, and the exit code
the contract tells callers they may rely on alone is always `1`.

**Independent Test**: take a target whose every onboarding element is in
place, run the documented route for the `auto-release` profile, and confirm
the aggregate verdict and exit status say "clear" without a human reading
individual rows.

**Acceptance Scenarios**:

1. **Given** an `auto-release` target with every onboarding element in place
   and the App installed, **When** the documented readiness route runs
   against it, **Then** the aggregate verdict is an all-clear and the exit
   status reflects that, with no element reported as a failure.
2. **Given** the same target but with its Claude credential genuinely
   absent, **When** the same route runs, **Then** the verdict is not-clear,
   `claude_credential` is named as the failing element, and its remaining
   action says what to do about it.
3. **Given** a route whose credential cannot read some element at all (an
   App token that cannot read secrets, or a maintainer credential that
   cannot confirm the App installation), **When** the route runs against a
   fully onboarding-complete target, **Then** those elements are reported in
   a state distinct from "not ready", the report states which route *can*
   check them, and the aggregate verdict is not degraded into a failure by
   them alone.
4. **Given** the readiness check dispatched in CI, **When** its job summary
   is read, **Then** an element that could not be checked is visually and
   textually distinct from an element that was checked and found missing.

---

### User Story 2 - Every document describes the behaviour the tool actually has (Priority: P2)

A maintainer or agent onboarding a new E2E target follows `quickstart.md`,
`docs/setup.md`, `docs/adoption.md` and the 053 contracts. Four of those
still describe behaviour that a later amendment removed — convergence by
re-running the local command, a local read-only check that exits 0 when
ready, a marker refusal that applies to the read-only path, and check calls
that the implementation no longer makes. Following them produces a result
that looks like a bug and is not one, which costs a debugging session every
time someone new stands up a target.

**Why this priority**: it is pure correction with no design trade-off, but
it depends on how User Story 1 resolves — the corrected text has to describe
the *new* verdict, so it lands after that decision, not before.

**Independent Test**: read each named location end to end against the
shipped behaviour and confirm no statement in it is false; a reader
following the documented steps sees exactly the described output.

**Acceptance Scenarios**:

1. **Given** the corrected `quickstart.md`, **When** a maintainer follows
   its `auto-release` walkthrough verbatim, **Then** the observed output and
   exit status match what each step says to expect.
2. **Given** the corrected 053 `spec.md`, `plan.md`, `contracts/cli.md` and
   `data-model.md`, **When** each statement about convergence, exit
   behaviour, the marker refusal's scope, and which read calls each check
   makes is compared against the shipped behaviour, **Then** none of them
   contradicts it.
3. **Given** the corrected `docs/setup.md` and `docs/adoption.md`, **When**
   their description of the remaining manual step is read, **Then** it
   describes how convergence is actually observed rather than "for as long
   as it is absent" from a command that can never observe it.

---

### User Story 3 - The provisioning tool fails with the true reason, and its tests say what they stand in for (Priority: P3)

A maintainer runs provisioning and repository creation fails — the name is
taken, the owner is wrong, a rate limit is hit. Today the run continues,
fails at the next step, and reports "failed to write the scratch marker",
which sends the maintainer looking at the wrong thing. Separately, two
behaviours the review verified only by hand have no regression test, and one
test passes only because it sets an environment hint that hides the very
defect User Story 1 is about.

**Why this priority**: none of these produces a wrong outcome today — the
tool fails closed and writes nothing — but each costs a wrong diagnosis or
an undetected regression later.

**Independent Test**: force repository creation to fail and confirm the
reported reason names repository creation; run the test suite and confirm
the two uncovered behaviours are now asserted.

**Acceptance Scenarios**:

1. **Given** a provisioning run whose repository creation fails, **When**
   the run stops, **Then** the reported failure names repository creation as
   the failed action, and no subsequent privileged action is attempted.
2. **Given** a mutating provisioning run with no resolvable git remote but
   an environment-provided repository identity that names the target,
   **When** it starts, **Then** it refuses before any remote call, and a
   regression test asserts this.
3. **Given** the environment hint that lets a caller assert the App is
   installed, **When** it is honoured by a run, **Then** the run states that
   it was honoured, and the documentation names the hint and the false-ready
   report a stray value produces.
4. **Given** the test whose read-only exit-0 case depends on that hint,
   **When** a reader opens it, **Then** the test states what the hint stands
   in for and which limitation it is masking.

---

### Edge Cases

- A target where an element is both unreadable by the checking credential
  *and* genuinely absent: the report must not claim it is fine, and the
  route that can check it must be named.
- A profile whose every not-clear element is "not checkable": the aggregate
  verdict must be defined for this case rather than falling out of whichever
  branch happens to run last.
- A caller that relies on the exit status alone, as `contracts/cli.md`
  invites: whatever the aggregate verdict becomes, the exit status must
  remain a faithful summary of it, so this caller is never told "clear"
  about an unverified target without that being a deliberate, documented
  choice.
- The environment hint set to a value other than the exact affirmative
  string: it must be treated as absent, not as truthy.
- A `spec-kit-scratch` target, whose profile omits both unreadable elements:
  its verdict must be unchanged by this feature.
- Repository creation that fails *after* partially succeeding (the
  repository exists but the call reports failure): the run must still stop
  with the true reason rather than continuing.

## Requirements *(mandatory)*

### Functional Requirements

#### Reaching a usable verdict (User Story 1)

- **FR-001**: The readiness report MUST distinguish an element the caller
  checked and found in place, an element the caller checked and found
  missing, and an element the caller's credential cannot check at all. These
  three outcomes MUST be separately identifiable by a machine consumer of
  the report and separately rendered in the human-readable summary.
- **FR-002**: There MUST be at least one documented route by which a fully
  onboarded `auto-release` target yields an unambiguous all-clear aggregate
  verdict, or the governing success criterion MUST be amended to state
  truthfully which profiles can reach one and what the `auto-release`
  profile's best attainable verdict is. Which of these the feature adopts is
  [NEEDS CLARIFICATION: the originating review offers four resolutions —
  scope the success criterion to `spec-kit-scratch`; treat "not checkable"
  as a distinct non-failing state; add a local affirmation flag for the
  declared manual step; or grant the App Secrets and Variables read on the
  test repository. These differ in whether the App's permission set changes,
  whether a caller can assert an unverified fact, and whether an all-clear
  for `auto-release` becomes reachable at all.]
- **FR-003**: The aggregate verdict MUST remain conservative in the
  following sense: it MUST NOT report all-clear when an element the profile
  requires was checked and found missing. Whether an
  uncheckable element degrades the aggregate verdict is settled by FR-002.
- **FR-004**: The exit status of the provisioning entry point MUST remain a
  faithful, documented summary of the aggregate verdict, so a caller acting
  on the exit status alone reaches the same conclusion as a caller parsing
  the report.
- **FR-005**: For every element a route cannot check, the report MUST name
  the route that can check it, so a reader is never left with an
  unresolvable row.
- **FR-006**: The `spec-kit-scratch` profile's verdict for a target in a
  given state MUST be unchanged by this feature.
- **FR-007**: No onboarding element may be added, removed, or renamed by
  this feature, and what provisioning writes to a target MUST be unchanged.

#### Documents that match behaviour (User Story 2)

- **FR-008**: The 053 quickstart's `auto-release` walkthrough MUST state the
  verdict and exit status a maintainer actually observes at each step,
  including the dispatched readiness check.
- **FR-009**: Every statement that a target converges to ready by
  re-invoking the local provisioning command MUST be corrected to describe
  how convergence is actually observed. This MUST cover the 053 spec's
  clarification record, the 053 plan's constraints, and the adopter-facing
  descriptions in `docs/setup.md` and `docs/adoption.md` that still say the
  local command reports the App installation as the sole remaining step "for
  as long as it is absent".
- **FR-010**: The CLI contract MUST describe the read-only path's actual
  exit behaviour, and MUST scope the scratch-marker refusal to the mutating
  path, which is where it now applies.
- **FR-011**: The data model MUST list only the read calls the checks
  actually make — no endpoint the implementation removed — and MUST record
  the scratch-marker exemption on the read-only path.
- **FR-012**: The corrected text MUST be consistent across all of these
  locations: no two of them may describe the verdict differently.

#### True failure reasons and honest tests (User Story 3)

- **FR-013**: A failed repository creation MUST stop the run and be reported
  as a failed repository creation, naming that action; no subsequent
  privileged action may be attempted after it.
- **FR-014**: A regression test MUST cover the mutating path refusing to
  proceed when the environment-provided repository identity names the
  target, distinct from the existing coverage of the case where no identity
  resolves at all.
- **FR-015**: When a run honours the environment hint that asserts the App
  installation is in place, it MUST say so in its human-readable output, so
  a false-ready report is traceable to the hint that caused it.
- **FR-016**: The documentation MUST name that environment hint, state which
  caller legitimately sets it, and warn that a stray value in a maintainer's
  shell produces a false-ready local report.
- **FR-017**: The test whose read-only all-clear case depends on that hint
  MUST state in the test itself what the hint stands in for and which
  limitation it masks.

### Key Entities

- **Element check outcome**: the per-element result of a readiness check.
  Today two-valued (ready / not ready); FR-001 makes it three-valued by
  separating "not checkable by this caller" out of "not ready". Carries the
  remaining action and, when not checkable, the route that can check it.
- **Aggregate verdict**: the single clear / not-clear conclusion derived
  from every element outcome in the profile, surfaced as both the report's
  top-level value and the entry point's exit status. How an uncheckable
  element folds into it is the subject of FR-002.
- **Readiness route**: a way of producing a report — the local entry point
  under a maintainer's own credential, or the dispatched readiness check
  under the App installation token. Each route can check a different subset
  of elements; this is the root cause the feature addresses.
- **App-installation assertion hint**: the environment signal by which a
  caller that has already proved the App installation asserts it rather than
  re-checking it. Legitimately set by the dispatched readiness check;
  hazardous when left set in a maintainer's shell (FR-015, FR-016).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For each supported profile, at least one documented route
  produces a correct, unambiguous aggregate verdict for a fully onboarded
  target — or the governing success criterion states explicitly which
  profiles that is true for and what the others can attain instead. No
  profile is left with a documented promise no route can keep.
- **SC-002**: A reader of any readiness report can classify every element
  into exactly one of the three outcomes without consulting the source, and
  every not-checkable element names the route that can check it.
- **SC-003**: Zero statements across the 053 spec, plan, CLI contract, data
  model, quickstart, `docs/setup.md` and `docs/adoption.md` contradict the
  shipped behaviour on convergence, exit status, the marker refusal's scope,
  or which read calls the checks make.
- **SC-004**: A provisioning run that fails at repository creation reports
  repository creation as the reason — the reported reason and the actual
  failed action match in 100% of failure modes of that step.
- **SC-005**: The onboarding elements each profile requires, and everything
  provisioning writes to a target, are identical before and after this
  feature.
- **SC-006**: Regression coverage exists for the self-target refusal via the
  environment-provided repository identity and for the failed
  repository-creation reason, both of which are untested today.
- **SC-007**: Any change to the credentials involved is explicit: either no
  permission held by any App installation changes, or the change is stated
  in the adopter-facing permission list alongside the reason.

## Assumptions

- The endpoint that answers whether the App is installed on a target is
  reachable only with App-JWT authentication, which neither a maintainer's
  own credential nor an installation token can produce. This feature does
  not attempt to make the local route check that element directly; it is
  treated as a fixed constraint.
- The App installation's declared permission set on adopter repositories
  (Contents, Issues, Pull requests) is the baseline. Widening it is one of
  the options Clarification Q1 puts on the table, not an assumption this
  spec makes on its own.
- The environment hint that asserts the App installation should be
  *announced when honoured* rather than ignored outside CI. Ignoring it
  outside CI would break the local test suite and a maintainer's local
  emulation of the CI route, which is a larger cost than the hazard;
  announcing it makes any false-ready report traceable. If the owner
  prefers the stricter behaviour, that is a change to FR-015.
- "Not checkable" is a property of the checking credential, not of the
  target: the same target checked by a different route may yield a
  checkable outcome for the same element. The report is therefore always
  route-relative, and this feature does not try to make one route
  authoritative for every element.
- Correcting the 053 documents in place is in scope. This feature amends the
  053 artifacts rather than superseding them; 053 remains the governing spec
  for the provisioning tool itself.
- The related issues named in the originating report (#362, #386) provide
  background only; nothing in them is a requirement of this feature.
- Deleting, archiving, or retiring a provisioned target remains outside
  every entry point, unchanged from 053.
