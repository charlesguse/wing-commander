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
deliberately narrow: it changes how readiness is *reported*, narrows the
governing success criterion to the profile that can actually reach an
all-clear, corrects the documents that overstate it, and closes four small
gaps the same review found. It does not add any new onboarding element,
does not change what provisioning writes, and does not widen any credential
(Clarification Q1).

## Clarifications

### Session 2026-09-25

- Q: How is the unreachable all-ready verdict for the `auto-release`
  profile resolved — scope the success criterion to `spec-kit-scratch`,
  make "not checkable" a distinct non-failing state, add a local flag by
  which a caller affirms the manual step, or grant the App a Secrets and
  Variables read on the test repository? → A: Both of the first two, and
  neither of the last two. "Not checkable" becomes a non-failing outcome:
  an element no route in play could verify is not counted as a failure,
  and SC-001 narrows to `spec-kit-scratch` as the profile a fully
  onboarded target can drive to all-clear. Elements nobody verified still
  produce their own distinct non-zero exit status, never a silent pass
  (constitution Principle VIII — a green check means what it says). The
  App's permission set is therefore unchanged, and no flag is added by
  which a caller asserts an unverified fact. (FR-002, FR-003, FR-004,
  SC-001, SC-007, SC-008)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A maintainer can tell "all clear" from "something is wrong" from "nobody could check" (Priority: P1)

A maintainer has provisioned an `auto-release` target and installed the
wing-commander App on it. They want one signal that says the target is good
to dispatch against. Today they cannot get one: every route reports
not-ready, for reasons that are properties of the checking credential rather
than of the target. They have to read the per-element reasons and decide by
hand which not-ready rows are real — which is exactly the judgement the
readiness report exists to remove.

After this feature they get the signal in the form it can honestly take.
Any element the caller genuinely cannot check is presented as its own
state, not as a failure indistinguishable from a missing secret, and the
aggregate verdict says which of three things happened: everything the
profile requires was checked and is in place; something was checked and
found missing; or nothing was found missing but some elements no route in
play could verify. Each carries its own exit status, so the unverified case
is never mistaken for a clean bill of health and never mistaken for a real
failure. A fully onboarded `spec-kit-scratch` target reaches the all-clear
through the dispatched route; a fully onboarded `auto-release` target reaches
the third verdict, which is its documented best.

**Why this priority**: this is the defect. Without it the readiness report
for the profile that matters most (`auto-release` is the one `auto-release.yml`
dispatches against) carries no usable aggregate signal, and the exit code
the contract tells callers they may rely on alone is always `1`.

**Independent Test**: take a target whose every onboarding element is in
place, run the documented route for each profile, and confirm the aggregate
verdict and exit status identify which of the three outcomes holds —
all-clear for `spec-kit-scratch`, nothing-missing-but-unverified for
`auto-release` — without a human reading individual rows.

**Acceptance Scenarios**:

1. **Given** a `spec-kit-scratch` target with every onboarding element in
   place, **When** the documented readiness route runs against it, **Then**
   the aggregate verdict is an all-clear, the exit status is the zero status
   documented for it, and no element is reported as a failure.
2. **Given** an `auto-release` target with every onboarding element in place
   and the App installed, **When** the documented readiness route runs
   against it, **Then** no element is reported as a failure, the elements
   that route cannot verify are reported as not checkable, and the aggregate
   verdict is the nothing-missing-but-unverified state with its own non-zero
   exit status — distinct from both the all-clear status and the status a
   checked-and-missing element produces.
3. **Given** the same target but with its Claude credential genuinely
   absent, **When** the same route runs, **Then** the verdict is not-clear,
   `claude_credential` is named as the failing element, its remaining action
   says what to do about it, and the exit status is the one documented for a
   checked-and-missing element rather than the unverified status.
4. **Given** a route whose credential cannot read some element at all (an
   App token that cannot read secrets, or a maintainer credential that
   cannot confirm the App installation), **When** the route runs against a
   fully onboarding-complete target, **Then** those elements are reported in
   a state distinct from "not ready", the report states which route *can*
   check them, and the aggregate verdict is not degraded into a failure by
   them alone — though it is still not an all-clear.
5. **Given** the readiness check dispatched in CI, **When** its job summary
   is read, **Then** an element that could not be checked is visually and
   textually distinct from an element that was checked and found missing,
   and the summary's aggregate line names which of the three verdicts the
   run reached.

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
  verdict must be the unverified state with its own exit status, reached
  deliberately rather than falling out of whichever branch happens to run
  last.
- A profile where one element is not checkable and another was checked and
  found missing: the verdict must be the checked-and-missing one, because a
  real failure outranks an unverified element.
- A caller that relies on the exit status alone, as `contracts/cli.md`
  invites: the exit status must remain a faithful summary of the aggregate
  verdict, so this caller is never told "clear" about a target with an
  unverified element — the unverified verdict is non-zero.
- The environment hint set to a value other than the exact affirmative
  string: it must be treated as absent, not as truthy.
- A `spec-kit-scratch` target, whose profile omits both elements the App
  token cannot read: no element of it may be newly reported ready or newly
  reported missing, and a fully onboarded one must still reach all-clear
  through the dispatched route. Its local run, whose `app_installation` is
  uncheckable, moves from the failure status to the unverified status
  (FR-006).
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
- **FR-002**: An element the checking route cannot verify MUST NOT be
  counted as a failure, and MUST NOT be counted as ready either. The
  aggregate verdict MUST therefore be three-valued: all-clear, not-clear
  because a required element was checked and found missing, and a third
  state — nothing found missing, something left unverified — which is the
  verdict for a profile whose only unresolved elements are uncheckable. The
  governing success criterion is narrowed accordingly (SC-001):
  `spec-kit-scratch` is the profile a fully onboarded target can drive to
  all-clear, and the `auto-release` profile's best attainable verdict is
  that third state. No App installation permission is widened, and no flag
  by which a caller asserts an unverified fact is added.
- **FR-003**: The aggregate verdict MUST remain conservative in the
  following sense: it MUST NOT report all-clear when an element the profile
  requires was checked and found missing, and MUST NOT report all-clear when
  an element the profile requires was left unverified. An unverified element
  therefore keeps a run from claiming all-clear without being reported as a
  failure (FR-002). Where both a missing element and an unverified element
  are present, the verdict MUST be the checked-and-missing one.
- **FR-004**: The exit status of the provisioning entry point MUST remain a
  faithful, documented summary of the aggregate verdict, so a caller acting
  on the exit status alone reaches the same conclusion as a caller parsing
  the report. Each of the three aggregate verdicts MUST map to its own
  documented exit status: zero for all-clear, and two distinct non-zero
  statuses for checked-and-missing and for unverified. A run with an
  unverified element MUST NOT exit zero.
- **FR-005**: For every element a route cannot check, the report MUST name
  the route that can check it, so a reader is never left with an
  unresolvable row.
- **FR-006**: The `spec-kit-scratch` profile MUST keep its present
  conclusions: the elements it requires are unchanged, no element it
  requires is newly reported ready or newly reported missing, and a fully
  onboarded target still reaches all-clear through the dispatched route. The
  three-valued outcome of FR-001 and FR-002 applies to this profile
  uniformly — so a local run whose only unresolved element is the
  uncheckable `app_installation` reports the unverified verdict and its exit
  status instead of a failure, which is the one intended change to it.
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
  exit behaviour — naming each of the three exit statuses FR-004 defines and
  the verdict each one summarises — and MUST scope the scratch-marker
  refusal to the mutating path, which is where it now applies.
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
- **Aggregate verdict**: the single conclusion derived from every element
  outcome in the profile, surfaced as both the report's top-level value and
  the entry point's exit status. Three-valued after this feature: all-clear,
  not-clear because a required element was checked and found missing, and
  nothing-missing-but-unverified (FR-002). Each value has its own exit
  status (FR-004).
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

- **SC-001**: A fully onboarded `spec-kit-scratch` target reaches an
  all-clear aggregate verdict, with the zero exit status, through a
  documented route. For a fully onboarded `auto-release` target the
  documented best attainable verdict is nothing-missing-but-unverified,
  reached through the dispatched route, with its own non-zero exit status;
  the success criterion states this explicitly rather than promising an
  all-clear. No profile is left with a documented promise no route can keep.
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
- **SC-007**: No permission held by any App installation changes, and the
  adopter-facing permission list (Contents, Issues, Pull requests) is
  identical before and after this feature (Clarification Q1).
- **SC-008**: The three aggregate verdicts map to three distinct exit
  statuses, each documented in the CLI contract, so a caller that reads only
  the exit status tells all-clear, checked-and-missing, and unverified apart
  in every case — and in no case reads zero for a target with an unverified
  element.

## Assumptions

- The endpoint that answers whether the App is installed on a target is
  reachable only with App-JWT authentication, which neither a maintainer's
  own credential nor an installation token can produce. This feature does
  not attempt to make the local route check that element directly; it is
  treated as a fixed constraint.
- The App installation's declared permission set on adopter repositories
  (Contents, Issues, Pull requests) is the baseline and stays there:
  Clarification Q1 rejected widening it, so `claude_credential` and
  `container_image_pin` remain unreadable by the dispatched route and are
  reported as not checkable rather than checked.
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
