# Feature Specification: Unattended Passage of the Pipeline's Human Gates in End-to-End Release Verification

**Feature Branch**: `055-unattended-e2e-gates`

**Created**: 2026-09-19

**Status**: Draft

**Input**: Lifecycle issue [#386](https://github.com/charlesguse/wing-commander/issues/386) — "auto-release: the end-to-end verification cannot pass the pipeline's human gates unattended"

## Context

`auto-release.yml`'s `verify-e2e` job drives a deliberately trivial feature
through the published stages against a dedicated, maintainer-onboarded test
repository, and `specs/045-auto-release-verified-head` FR-008 requires that
run to exercise the full intake→cleanup lifecycle. That lifecycle contains
four points where the pipeline, by design, stops and waits for a person:

1. the clarification gate — intake posts its `[NEEDS CLARIFICATION]`
   questions to the lifecycle issue and waits for a reply;
2. the spec PR — planning starts only when a `spec-draft/` pull request is
   merged;
3. the plan PR — task generation starts only when the plan pull request is
   merged (unless the plan review gate is configured off);
4. the finalize PR — the lifecycle reaches `stage:done` only when the final
   implementation pull request is merged.

Nothing in the harness can satisfy any of them. Every unattended attempt
therefore stops at the first one and ends `fail-timeout`
([#385](https://github.com/charlesguse/wing-commander/issues/385)). The two
attempts at `1880c9e` each did real agent work — intake ran to completion at
roughly a dollar — and then stopped at an `Action needed` comment. The
clarify stage was `skipped` both times because the only comment on the issue
was the bot's own, and the clarify wrapper's actor gate deliberately ignores
bots. The only passing runs on record (scratch #1 and #5, the latter cutting
`v2.7.3`) had the maintainer answer the questions by hand and merge three
pull requests. The end-to-end verification has therefore never passed
unattended, and no release has been cut on the evidence spec 045 describes.

This feature is about making that run reach a verdict on its own — and about
stating truthfully which gates it drives and which it removes, so the
verdict a release is cut on is not quietly weaker than FR-008 claims.

The scheduled attempt is currently suspended
(`WING_COMMANDER_AUTO_RELEASE_PAUSED=true`) so the daily failure stops
costing roughly a dollar and one new failure issue per day.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The scheduled verification reaches a verdict with nobody watching (Priority: P1)

The schedule fires, new work is found, and the trivial fixture feature is
driven through the published stages against the test repository. At each
point where the pipeline waits for a person, the harness acts as that
person: it answers the clarification questions, and it merges the pull
requests the lifecycle requires to be merged. The lifecycle issue closes
with `stage:done`, the run produces a `pass` verdict, and the release
decision reads it — all without anyone being awake.

**Why this priority**: This is the feature. Every other story here is a
constraint on it or a report about it. Until the run can get past the first
gate, the auto-release path described in spec 045 does not exist in
practice — it has only ever worked with a maintainer supplying four manual
acts.

**Independent Test**: With the pause switch cleared and no human touching
the test repository, dispatch one auto-release run against a head that
carries new work, and confirm the lifecycle issue in the test repository
closes with `stage:done` and the run reports a `pass` verdict — with the
test repository's audit trail showing every gate-satisfying act came from
the harness, not from a person.

**Acceptance Scenarios**:

1. **Given** an attempt in which intake posts clarification questions,
   **When** the harness replies, **Then** the clarify stage actually runs
   (the reply is accepted by the stage's own actor gate, not ignored as a
   bot comment) and the lifecycle advances past `stage:spec`.
2. **Given** an attempt whose spec pull request is open, **When** the
   harness merges it, **Then** the plan stage starts exactly as it does for
   a maintainer-merged spec pull request.
3. **Given** an attempt whose plan pull request is open with the plan
   review gate left on as an adopter would have it, **When** the harness
   merges it, **Then** task generation starts exactly as it does for a
   maintainer-merged plan pull request.
4. **Given** an attempt whose final implementation pull request is open,
   **When** the harness merges it, **Then** cleanup runs and the lifecycle
   issue closes with `stage:done`.
5. **Given** a complete unattended attempt, **When** the verdict is
   computed, **Then** it is `pass` and the release decision proceeds on it
   under the rules spec 045 already sets.
6. **Given** an unattended attempt, **When** a maintainer inspects the test
   repository afterwards, **Then** the number of human acts required for
   that attempt is zero.

---

### User Story 2 - The run's coverage claim matches what it actually exercised (Priority: P1)

Every gate the harness drives is asserted positively — the question was
posted *and* answered *and* the stage that consumes the answer ran; the
pull request existed *and* was merged. All four gates are driven, so the
written record states that and adds no gap to spec 045's FR-008a; were a
gate ever removed by configuring the fixture repository instead, it would
be named there with what goes unverified, and the run's own report would
name it too.

**Why this priority**: The whole point of the end-to-end run is that a
release is cut on evidence rather than on lint. A run that reaches
`stage:done` by having the gates switched off, while FR-008 still claims
full-lifecycle coverage, produces exactly the green check Constitution
Principle VIII forbids: it reads as evidence and proves less than it says.
Shipping the driving without the honest statement of what was driven would
be worse than the current failure, which at least fails loudly.

**Independent Test**: Read only the accepted-gap statement and the run's
report, then compare them against the lifecycle gates the test repository
actually exercised — every difference between "gates this pipeline has" and
"gates this run drove" is already written down, with nothing found by
reading the workflow.

**Acceptance Scenarios**:

1. **Given** a passing unattended run, **When** its verdict is read,
   **Then** each driven gate carries machine-observable evidence that it
   was satisfied, not merely that the lifecycle moved on.
2. **Given** the accepted-gap statement and the run's report, **When** they
   are read, **Then** they record that all four human gates were driven and
   name no gate as removed — and any gate that ever is removed is named in
   both, along with what goes unverified because of it.
3. **Given** a run in which a gate the harness was supposed to drive was
   never reached, **When** the verdict is computed, **Then** it is not
   `pass`, regardless of whether the lifecycle reached a terminal state by
   some other route.
4. **Given** the evidence the assertions read, **When** they are examined,
   **Then** they are repository state (issue state, labels, timeline, pull
   request merge state, committed artifacts) rather than any agent's
   narration of its own success.

---

### User Story 3 - A stall at a gate is reported as a stall at that gate (Priority: P2)

An attempt that does not get past a gate says so: which gate, when the
pipeline asked, what the harness did, and what was observed instead. It is
not reported as the generic "still open after 6900 seconds" that today
makes a gate stall indistinguishable from a hung stage or a slow runner.

**Why this priority**: Both failing attempts at `1880c9e` reported
`fail-timeout` with a label list, which reads like an infrastructure
problem. It took an investigation to establish that the pipeline was
working correctly and simply waiting. That investigation is the cost this
story removes, and it recurs on every future gate-shaped failure.

**Independent Test**: Force one gate to go unsatisfied (withhold the
harness's act for that gate alone) and confirm the failure report names
that gate, what the pipeline was waiting for, and that the cause is a gate
stall rather than a pipeline defect — readable without opening the run.

**Acceptance Scenarios**:

1. **Given** an attempt that stalls at the clarification gate, **When** the
   report is written, **Then** it names the clarification gate, the moment
   the question was posted, and what the harness attempted.
2. **Given** an attempt that stalls at a pull-request merge gate, **When**
   the report is written, **Then** it names which pull request and why the
   merge did not happen (not mergeable, required check failing, permission
   refused, or never attempted).
3. **Given** consecutive failing attempts for the same unreleased head,
   **When** each reports, **Then** they update one durable report, as spec
   045 FR-028 already requires.
4. **Given** a stall caused by a genuine pipeline defect rather than a
   gate, **When** the report is written, **Then** it is still classified as
   a pipeline defect and not mislabelled as a gate stall.

---

### User Story 4 - The harness's ability to act stops at the test repository (Priority: P1)

The dedicated machine user account that answers and merges in the test
repository cannot comment on, approve, or merge anything in this repository
or in any adopter's. The published stages' own actor and merge gates are
unchanged: nothing this feature ships gives an adopter a way to have a bot
merge into their default branch.

**Why this priority**: Constitution Principle V says humans merge every
pull request into `main` and the bot never approves or merges to `main`.
That rule governs the product and this repository. Granting an unattended
actor merge rights is defensible only for a disposable fixture repository
whose entire contents are force-reset before every attempt — and only if
the grant provably cannot reach anywhere else, which is the condition on
which FR-003 accepts it. It is P1 because it ships inseparably from US1:
the credential exists the moment US1 works.

**Independent Test**: Enumerate what the machine account and its credential
can reach and confirm the set is exactly the configured test repository;
then confirm that this repository's own gates, and the published stage
workflows' actor and merge conditions, are unchanged by this feature.

**Acceptance Scenarios**:

1. **Given** the harness's credential, **When** its scope is inspected,
   **Then** it grants nothing on this repository and nothing on any
   repository other than the configured test repository.
2. **Given** a configuration in which the test repository resolves to this
   repository, **When** an attempt starts, **Then** it refuses outright and
   reports the misconfiguration, as the existing self-repository refusal
   already does for the branch reset.
3. **Given** this feature shipped, **When** the published stage workflows
   are compared against their previous release, **Then** no actor gate,
   merge gate, or human-gate condition has been weakened.
4. **Given** the machine account's credential secret is unset or invalid,
   **When** an attempt starts, **Then** it produces the
   infrastructure-failure outcome naming what to set, cuts no release, and
   does not begin a lifecycle it cannot finish.

---

### User Story 5 - The daily schedule resumes on evidence, not on hope (Priority: P3)

The pause switch is lifted only once an unattended run has actually reached
`stage:done`, and the proof is recorded on the tracker issue. Until then the
schedule stays paused so a known-broken path stops spending a dollar and
filing an issue every day.

**Why this priority**: The pause is already in place and already doing its
job; the only open question is the condition for removing it. It is P3
because it costs nothing to leave paused and delivers nothing on its own.

**Independent Test**: Confirm the resume condition is written down, that
the tracker issue receives the run evidence, and that the switch is cleared
in the same change that records the evidence — not before.

**Acceptance Scenarios**:

1. **Given** no unattended run has yet reached `stage:done`, **When** the
   schedule would fire, **Then** it remains paused and nothing is spent.
2. **Given** one unattended run has reached `stage:done`, **When** the
   evidence is recorded on the tracker issue, **Then** the pause switch is
   cleared and the normal cadence resumes.
3. **Given** the resumed cadence, **When** an attempt waits on the gates
   the harness drives, **Then** the poll budget accommodates that wait, so
   a healthy unattended run does not exhaust the budget it is given.

---

### Edge Cases

- **The pipeline asks a question the harness has no prepared answer for**:
  the fixture feature is fixed, but the questions an agent asks about it are
  not guaranteed to be. Two independent runs asked the same two questions;
  nothing guarantees the third does. The one fixed reply answers those two
  and delegates anything else to the stage's own judgment, so the attempt
  proceeds rather than stalling.
- **The pipeline asks no question at all**: a spec with zero
  `[NEEDS CLARIFICATION]` markers means the clarification gate never opens.
  The run must not wait for an answer nobody was asked for, and must not
  fail for the absence of an exchange that was never required.
- **The clarification exchange does not settle in one round**: the answer
  itself provokes a follow-up question. The number of rounds the harness
  will answer is bounded, and exhausting that bound is a gate stall, not a
  timeout.
- **A human answers or merges first**: a maintainer watching the fixture
  repository acts before the harness does. The attempt continues normally
  and the harness does not duplicate or contradict the human's act.
- **A pull request the harness must merge is not mergeable**: conflict,
  failing required check, or branch protection refusing the identity. Each
  is a distinct observation and the report says which.
- **A leftover pull request from a previous attempt**: the pre-attempt
  cleanup already closes open issues and pull requests before the reset; the
  harness must only ever merge a pull request belonging to the attempt it is
  driving.
- **The lifecycle reaches `stage:stalled` for a non-gate reason**: reported
  as a pipeline defect, unchanged by this feature.
- **The poll budget expires mid-lifecycle with every gate satisfied on
  time**: a real timeout, distinguished in the report from a gate stall.
- **Two attempts overlap**: unchanged — at most one attempt is in flight,
  per spec 045 FR-023.
- **The pause switch is set mid-attempt**: unchanged — the in-flight
  attempt may finish; no new attempt starts.
- **The fixture's gate configuration drifts from this repository's own**:
  the fixture is configured as an adopter would be, with every human gate
  left on so all four are driven; any deliberate difference is part of the
  accepted-gap statement rather than an undocumented divergence.

## Requirements *(mandatory)*

### Functional Requirements

#### Passing the gates unattended

- **FR-001**: The end-to-end verification run MUST be able to carry its
  fixture feature from kickoff to a terminal lifecycle state with zero human
  acts in the test repository.
- **FR-002**: All four points at which the lifecycle waits for a human MUST
  be driven by the harness performing that act: the harness answers the
  clarification questions and merges the spec, plan, and finalize pull
  requests. No gate is removed by configuring the fixture repository, so
  spec 045 FR-008's full-lifecycle claim stays true with no new accepted
  gap. Each gate's disposition remains a recorded decision, never an
  incidental outcome; a gate that cannot be driven is a gate stall
  (FR-021), not a silent removal.
- **FR-003**: The harness MUST act as a dedicated machine user account — a
  real user account, not a bot identity — holding a credential scoped to the
  test repository alone, so that it is accepted by the published stages' own
  actor gates as they already stand, in particular by the clarify entry
  point, which ignores comments from bots and requires a maintainer
  association or the lifecycle issue's own author. Granting that account the
  ability to answer clarification questions and merge pull requests inside
  the disposable fixture repository is accepted, on the conditions FR-011
  through FR-015 impose.
- **FR-003a**: Provisioning that account and storing its credential as a
  secret in this repository is a maintainer act performed outside the
  pipeline, and MUST be stated as a prerequisite rather than automated. The
  credential MUST be read only by the auto-release verification job.
- **FR-004**: Driving a gate MUST NOT require modifying the published stage
  workflows, and MUST NOT require the fixture's installed wrapper workflows
  to differ from the set `docs/adoption.md` documents in any way that
  weakens what the run verifies.
- **FR-005**: The content the harness supplies at a gate — the answer text,
  the decision to merge — MUST be deterministic and pre-authored, not an
  agent's judgment call, in keeping with Constitution Principle IX: judgment
  that gates a durable action belongs in deterministic code.
- **FR-006**: The number of clarification rounds the harness will answer
  MUST be bounded, and exhausting that bound MUST end the attempt with a
  gate-stall outcome rather than an open-ended wait.
- **FR-007**: The harness MUST handle a clarification question it did not
  anticipate without stalling the attempt and without any human act, by
  posting one fixed, pre-authored reply that answers the two known questions
  and tells the stage to use its own judgment on anything else. The same
  reply is posted once per round, up to the bound FR-006 sets; an
  unanticipated question is therefore a normal event rather than a
  verification failure.
- **FR-008**: When the pipeline asks no clarification question at all, the
  attempt MUST proceed to the next gate rather than waiting for, or
  requiring, an exchange that never opened.
- **FR-009**: The harness MUST act only on the artifacts of the attempt it
  is currently driving — the issue it opened and the pull requests that
  attempt produced — and never on a leftover from a previous attempt.
- **FR-010**: If a human satisfies a gate before the harness does, the
  attempt MUST continue normally and the harness MUST NOT duplicate or
  contradict that act.

#### Containment

- **FR-011**: The machine user account's credential MUST be scoped to the
  test repository alone — the account holds access to no other repository,
  and the credential itself is narrowed to the same single repository. It
  MUST NOT be able to comment on, approve, or merge anything in this
  repository.
- **FR-012**: This feature MUST NOT weaken any actor gate, merge gate, or
  human gate in the published stage workflows. No adopter gains an
  unattended path to merging into their default branch as a result of it.
- **FR-013**: When the configured test repository resolves to this
  repository, the attempt MUST refuse outright before acting, extending the
  refusal the branch reset already performs to every act this feature adds.
- **FR-014**: When the harness's credential secret is unset, malformed, or
  rejected, the attempt MUST produce the infrastructure-failure outcome
  naming precisely what to configure — the same way the run already reports
  an unset test-repository variable — MUST cut no release, and MUST NOT
  start a lifecycle it cannot carry to a verdict.
- **FR-015**: The harness's acts MUST be attributable in the test
  repository's own audit trail, so a maintainer inspecting an attempt can
  tell every gate-satisfying act apart from a human's.

#### Asserting what was exercised

- **FR-016**: Each gate the harness drives MUST be asserted positively: the
  clarification question was posted, answered, and consumed by the stage
  that reads it; each required pull request existed and was merged. Reaching
  the next stage is not on its own evidence that the gate was satisfied.
- **FR-017**: Every assertion MUST read machine-observable repository state
  — issue state, labels, timeline events, pull request merge state,
  committed artifacts — never an agent's narration of its own success.
- **FR-018**: A run in which a gate the harness was supposed to drive was
  never reached or never satisfied MUST NOT produce a `pass` verdict, even
  if the lifecycle reached a terminal state by another route.
- **FR-019**: Because FR-002 drives all four gates, this feature adds no
  accepted gap: the accepted-gap statement alongside spec 045's FR-008a MUST
  record that the four human gates are driven rather than removed, and the
  run's own report MUST name the four gates it drove so a reader of the
  report knows what the pass covers. Should a gate ever be removed by
  fixture configuration instead, it MUST be named in both places along with
  what goes unverified as a result.
- **FR-020**: Spec 045's FR-008 claim of full intake→cleanup coverage MUST
  be reconciled with what this run actually exercises. Under FR-002 the
  coverage is genuinely full and the claim stands unamended; any future
  divergence MUST be stated as an accepted gap. The two MUST NOT disagree.

#### Reporting

- **FR-021**: An attempt that does not get past a gate MUST be reported as a
  stall at that named gate, distinct from a generic poll-budget timeout and
  from a pipeline defect.
- **FR-022**: A gate-stall report MUST state which gate, what the pipeline
  was waiting for, what the harness attempted, and what was observed
  instead.
- **FR-023**: A merge that the harness attempted and could not complete MUST
  be reported with the reason distinguished: not mergeable, a required check
  failing, the identity refused, or never attempted.
- **FR-024**: Gate-stall reports MUST use the existing durable one-report-
  per-head mechanics rather than introducing a second reporting channel.
- **FR-025**: Every attempt's outcome MUST remain legible from the run's own
  summary without opening logs, as spec 045 FR-030 already requires.

#### Budget and resumption

- **FR-026**: The poll budget MUST accommodate a complete unattended
  lifecycle including the time the harness spends satisfying each gate, so a
  healthy run does not exhaust it. It remains a value changed by a reviewed
  pull request, not a settings-side knob.
- **FR-027**: The expected per-attempt cost of a complete unattended run
  MUST be stated, and each attempt's actual cost MUST be reported, so the
  cadence remains a budget decision a maintainer can make with real numbers.
- **FR-028**: The pause switch MUST remain set until one unattended run has
  reached `stage:done`, and MUST be cleared in the same change that records
  that run's evidence on the tracker issue.
- **FR-029**: The tracker issue for the failure MUST receive the evidence of
  the first unattended run that reaches `stage:done`, per the expectation
  already recorded there.

### Key Entities

- **Lifecycle gate**: one point at which the pipeline waits for a human act
  in the test repository — the clarification exchange, the spec pull
  request, the plan pull request, the finalize pull request. Each carries a
  recorded disposition; under FR-002 all four are driven by the harness and
  none is removed by fixture configuration.
- **Fixture maintainer identity**: the dedicated machine user account the
  harness acts as inside the test repository, provisioned by a maintainer
  outside the pipeline and reached through a credential held as a secret in
  this repository. Satisfies the published stages' existing actor gates as a
  real user rather than a bot, and can reach no other repository.
- **Prepared answer**: the deterministic, pre-authored text the harness
  posts when the clarification gate opens — one fixed reply answering the
  two known questions and delegating anything else to the stage's judgment.
  Fixed content, not generated per run, posted once per round.
- **Gate evidence**: the machine-observable repository state proving a gate
  was actually satisfied — the question comment, the answer comment, the
  stage run that consumed it, each pull request's merge state.
- **Accepted-gap statement**: the written record of which gates this
  verification removes rather than drives, and what consequently goes
  unverified before a tag is cut. Sibling of spec 045's FR-008a; under
  FR-002 it records that all four gates are driven and names no removal.
- **Gate stall**: the outcome class for an attempt that stopped at a named
  gate, distinct from a poll timeout and from a pipeline defect.
- **Resume condition**: the evidence that must exist before the pause switch
  is cleared — one unattended run at `stage:done`, recorded on the tracker.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A scheduled attempt that finds new work reaches a terminal
  verdict — `pass` or a named failure — with zero human acts in the test
  repository, in 100% of attempts not blocked by infrastructure.
- **SC-002**: The number of human acts required per unattended attempt is
  zero, down from four (one answer plus three merges) today.
- **SC-003**: The number of acts the harness's identity performs outside the
  configured test repository is zero, across every run and every outcome.
- **SC-004**: Every driven gate in a `pass` verdict carries its own
  evidence: the count of gates recorded as satisfied without evidence is
  zero.
- **SC-005**: The count of gates removed by fixture configuration rather
  than driven is zero — all four are driven — and the count of any such
  removal absent from the accepted-gap statement is likewise zero.
- **SC-006**: A maintainer reading only the failure report can state, in
  under two minutes and without opening the run, whether an attempt stopped
  at a gate — and which — or failed for another reason.
- **SC-007**: After this ships, at least one unattended run reaches
  `stage:done` and its evidence appears on the tracker issue; the pause
  switch is cleared in that same change and not before.
- **SC-008**: The published stage workflows' actor and merge gates are
  unchanged by this feature: the count of weakened human gates on the
  published surface is zero.
- **SC-009**: Following the first unattended pass, the count of new failure
  issues filed per day by the scheduled attempt returns to zero while the
  path is healthy.
- **SC-010**: A gate stall and a poll-budget timeout are never reported as
  the same outcome: the count of gate stalls reported as `fail-timeout` is
  zero.
- **SC-011**: Spec 045's stated end-to-end coverage and this run's actual
  coverage agree: the count of stages claimed as exercised but not
  exercised, and not disclosed as a gap, is zero.
- **SC-012**: One head still yields at most one automatic release, and a
  failed or stalled attempt still creates and moves zero tags — unchanged
  from spec 045.

## Assumptions

- The test repository is the one `WING_COMMANDER_AUTO_RELEASE_E2E_REPO`
  already names. This feature introduces no second repository and no second
  onboarding path; `specs/053-e2e-scratch-provisioning` remains how such a
  repository comes into existence.
- Constitution Principle V governs this repository and the published
  product. The test repository is a disposable fixture whose entire contents
  are force-reset before every attempt, which is why an unattended actor
  merging there is discussable at all; FR-003 settles that it is acceptable
  there, and only there, under the containment requirements.
- The existing verdict shape, failure classification, durable failure issue,
  and run-summary mechanics are reused; this feature adds outcome classes to
  them rather than a new reporting channel.
- `specs/054-e2e-container-coverage` (container-mode coverage in the same
  verification) is orthogonal and lands independently; neither blocks the
  other.
- The clarify entry point's actor gate — no bots, maintainer association or
  the issue's own author — is a published compatibility surface and is not
  widened by this feature. The harness works within it: the machine user
  account carries the association the gate already requires in the fixture
  repository.
- Provisioning the machine user account, granting it access to the test
  repository, and storing its credential as a secret in this repository are
  maintainer prerequisites performed outside the pipeline (FR-003a). An
  attempt that runs before they exist reports the infrastructure failure of
  FR-014 rather than attempting to create them.
- The plan review gate is already configurable per repository
  (`WING_COMMANDER_PLAN_REVIEW`), so removing that one gate would need no
  new mechanism — but FR-002 does not remove it. The fixture leaves it on as
  an adopter would have it, and the harness merges the plan pull request.
- The current poll budget and the roughly one-dollar-per-attempt figure were
  sized before the run had to wait on any gate. Both are re-derived from an
  observed complete unattended run rather than being carried forward.
- An attempt that cannot reach a verdict still means no release. No outcome
  this feature adds can cause a tag to be cut on weaker evidence than spec
  045 requires.
- The two questions intake asked on both failing attempts — what moment "the
  timestamp" refers to, and whether a repeat run adds a file or overwrites
  one — are treated as representative of what the fixture request provokes,
  not as an exhaustive list. `specs/045-auto-release-verified-head`'s
  research D9 assumed the request was unambiguous; two independent runs
  disproved that, so nothing here assumes a fixed question set.
- Attributability (FR-015) is satisfied by the test repository's ordinary
  audit trail — who commented, who merged — rather than by a new ledger.

## Clarifications

### Session 2026-09-19

All three open questions were answered by the repository owner on lifecycle
issue [#386](https://github.com/charlesguse/wing-commander/issues/386). No
`[NEEDS CLARIFICATION]` markers remain.

**Question 1 — Which identity plays the maintainer in the test repository**
(FR-003, FR-003a, FR-011, FR-014, User Story 4)

*Asked*: which identity plays the maintainer in the test repository, and is
granting an unattended actor the ability to answer clarification questions
and merge pull requests acceptable given those gates exist to keep a human
in the loop?

*Answered*: **Option A** — a dedicated machine user account holding a
credential scoped to the test repository alone, stored as a secret in this
repository and used only by the auto-release verification job. Provisioning
the account and the secret is a maintainer act that happens outside the
pipeline, so it is stated as a prerequisite; the job fails with a clear
infrastructure verdict when the secret is unset, the way it already does for
the test-repository variable.

**Question 2 — Which gates are driven and which are removed** (FR-002,
FR-019, FR-020, SC-005, User Stories 1 and 2)

*Asked*: which gates does the unattended run drive, and which does it remove
by configuring the fixture repository — each removal subtracts a stage from
what spec 045 FR-008 claims the run exercises.

*Answered*: **Option A** — drive all four gates: the harness answers the
clarification questions and merges the spec, plan, and finalize pull
requests. Spec 045 FR-008's full-lifecycle claim stays true with no new
accepted gap.

**Question 3 — Handling an unanticipated clarification question** (FR-005,
FR-006, FR-007)

*Asked*: how is a clarification question the harness did not anticipate
handled — a single fixed reply that delegates anything else to the stage's
own judgment, a kickoff request precise enough that any question is a
verification failure, or a bounded generic reply repeated per round?

*Answered*: **Option A** — one fixed, pre-authored reply that answers the
two known questions and tells the stage to use its own judgment on anything
else, posted once per round up to a bounded number of rounds. Exhausting the
bound is a gate stall under FR-006.
