# Feature Specification: A never-unblocking merge gate is named, and the unattended run can be proven without cutting a release

**Feature Branch**: `070-blocked-gate-dry-run`

**Created**: 2026-09-25

**Status**: Draft

**Input**: User description: "unattended E2E gates: containment verdict can drop its own evidence, no login-leak fixture, and the pause switch blocks the validation run" (lifecycle issue #533, routed from the board loop; originating review of #389 against spec 055). The two findings still open after #401, #469 and #523: (1) a merge gate whose pull request is permanently blocked with an unresolved check rollup is waited on until the whole poll budget expires and then reported as a generic timeout instead of a gate stall naming the gate and the pull request; (2) the pause switch gates every auto-release job, so the feature's own validation dispatch requires clearing it, and a passing validation run then goes on to decide a version and dispatch a real release — spec 055's FR-028 ("the switch stays set until one unattended run has reached `stage:done`") cannot be satisfied as written until a release-free validation path is decided.

## Context

Spec 055 (unattended passage of the end-to-end human gates) made the nightly
auto-release verification drive an adopter-shaped test repository through the
full pipeline without a human, and made each way that can go wrong report a
distinct, named outcome: an infrastructure failure, a pipeline defect, a
**gate stall** naming the gate that would not pass, or a generic timeout. The
third review of that work left six findings. Four of them (the containment
verdict leaking a masked login, the missing login-leak fixture, the pass-path
reads that degraded to `null`, and the case-sensitive login comparison) were
fixed in #401 and #469; the first half of the fifth — a legacy status context
reporting `EXPECTED` read as a resolved failure — was fixed in #523. A
related gap in the slug fallback's 404 handling is tracked separately as
#482.

What remains is one behaviour and one contradiction, and neither is
fix-shaped: both turn on a trade-off the owner has to settle.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A gate that will never unblock says so (Priority: P1)

A maintainer reads the durable failure report for an unattended attempt. The
attempt failed because one of the three pull-request merge gates in the test
repository sat blocked on required checks that never reported a result — a
misconfigured required check, a checks app that never picked the pull request
up. Today that attempt spends its entire poll budget waiting, then reports the
generic "the run under test never reached a terminal state" timeout: the
report names labels and a number of seconds, and nothing about the gate. The
maintainer has to go read the test repository by hand to learn which of the
three gates was stuck, and on what.

After this feature, the same attempt ends as a **gate stall** that names the
gate, names the pull request, and says the required checks never reported —
the same shape of evidence the other four gate-stall reasons (conflicting,
blocked, wrong-attempt, wrong-base) already produce.

**Why this priority**: distinguishing a gate stall from a timeout is the whole
point of spec 055's failure taxonomy, and this is the one remaining condition
that still lands in the generic bucket. It is also the condition a maintainer
is least able to reconstruct afterwards, because the run that observed it is
over and the test repository is reset by the next attempt.

**Independent Test**: drive the merge-gate decision and the poll loop's
handling of it with fixtures whose pull request stays blocked with an
unresolved check rollup for longer than the waiting allowance, and confirm the
attempt ends with a gate-stall verdict naming that gate rather than the
generic timeout — and, separately, that a pull request whose checks resolve
inside the allowance still merges. No live run is required.

**Acceptance Scenarios**:

1. **Given** the spec-draft merge gate's pull request reports as blocked with
   no resolved check result on every observation, **When** that gate's waiting
   allowance is exhausted, **Then** the attempt ends with a gate-stall verdict
   whose named gate is the spec-draft merge gate, whose evidence names the
   pull request, and whose reason says the required checks never reported.
2. **Given** the same pull request reports as blocked with an unresolved check
   result on the first observations and a passing one before the allowance is
   exhausted, **When** it is next observed, **Then** the gate merges it and no
   stall is reported.
3. **Given** a pull request that is blocked with no checks created yet because
   it was opened seconds ago, **When** it is observed inside the allowance,
   **Then** it is waited on, not declared stalled.
4. **Given** no merge gate is blocked and the run under test is simply still
   open when the poll budget expires, **When** the verdict is written, **Then**
   it is the existing generic timeout, unchanged.
5. **Given** a gate stall of this new kind, **When** the durable failure report
   is written, **Then** its classification reads "gate stall" — never
   "pipeline defect", "infrastructure", or a timeout.

---

### User Story 2 - Proving the unattended run without cutting a release (Priority: P2)

A maintainer wants to prove that the unattended end-to-end verification works
— the three gates pass unattended, the clarification question is answered, the
test repository's issue closes `stage:done`. Today that proof is unreachable
without a side effect: the pause switch gates the detect job and every job
after it, so a dispatch while it is set does nothing at all; and once the
switch is cleared, an attempt that passes goes straight on to decide a version
and dispatch a real release. The maintainer must therefore be ready to ship a
release before they can find out whether the verification works.

After this feature, the maintainer can dispatch the verification in a mode
that stops after the verdict: the same gates, the same verdict, the same
report — and no version decided and no release dispatched, whatever the
verdict says.

**Why this priority**: it unblocks the live proofs spec 055 still owes (its
T011, T020 and T022), which are the only evidence that the unattended path
works at all. It is P2 rather than P1 because the diagnostic in User Story 1
is what makes those proofs readable when they fail.

**Independent Test**: dispatch the verification in the release-free mode
against the test repository and confirm the verdict is produced and reported
while no release tag is created and no release dispatch occurs; then confirm
an ordinary dispatch still releases on a pass.

**Acceptance Scenarios**:

1. **Given** a maintainer dispatches the verification in the release-free
   mode, **When** the verdict is `pass`, **Then** no version is decided, no
   release is dispatched, and the run still reports the verdict.
2. **Given** the same dispatch, **When** the verdict is any failure outcome,
   **Then** the run reports it exactly as an ordinary attempt would.
3. **Given** a run in the release-free mode, **When** its report or summary is
   read, **Then** it states plainly that this run cut no release, so the
   absent release is not read as a failure.
4. **Given** an ordinary scheduled or on-demand attempt (not the release-free
   mode), **When** the verdict is `pass`, **Then** a version is decided and the
   release is dispatched exactly as today.
5. **Given** any configuration a scheduled run reads, **When** the schedule
   fires, **Then** the release-free mode is off — it can only ever be turned on
   by an explicit act at dispatch time, so it can never silently suppress a
   real release.

---

### User Story 3 - The resume condition can actually be followed (Priority: P3)

A maintainer follows spec 055's runbook to retire the pause switch. Today the
instructions fold back on themselves: FR-028 says the switch stays set until
one unattended run has reached `stage:done`, but no run can reach `stage:done`
while the switch is set, and the run that would prove it also cuts a release.
The quickstart now says this plainly (#401), which makes the contradiction
visible but does not remove it.

After this feature, the resume condition names a sequence a maintainer can
execute: which dispatch proves the feature, whether that proof counts towards
clearing the switch, and in what order the evidence is recorded and the switch
cleared.

**Why this priority**: it is documentation and requirement reconciliation
rather than behaviour, and it depends on the answers that User Story 2's mode
settles. It still matters: spec 055's remaining open tasks are unrunnable
until it is resolved, and a requirement that cannot be satisfied is a
requirement nobody can check.

**Independent Test**: read the runbook and the resume condition end to end and
confirm every step is executable in the stated order with no step that
requires the switch to be simultaneously set and cleared; confirm spec 055's
open validation tasks name a dispatch path that exists.

**Acceptance Scenarios**:

1. **Given** the reconciled resume condition, **When** a maintainer reads it,
   **Then** it states which run clears the pause switch and whether a
   release-free validation run satisfies it.
2. **Given** spec 055's still-open validation tasks (T011, T020, T022),
   **When** they are read after this feature, **Then** each names a dispatch
   path that exists and states whether following it cuts a release.
3. **Given** the runbook's dispatch step, **When** a maintainer reaches it,
   **Then** the release consequence of each mode is stated at that step, not
   only in a prerequisite paragraph further up.

---

### Edge Cases

- **A gate flips between "blocked with nothing reported" and "blocked with
  something still running" across observations.** The waiting allowance must
  not reset merely because the shape of the unresolved result changed — only
  observable progress (the gate merging, or its pull request leaving the
  blocked-with-unresolved-checks state) resets it. Otherwise a check that
  alternates forever resets the clock forever and the attempt times out again.
- **Two gates are blocked at once.** Only one verdict can be written; the
  first gate to exhaust its allowance is the one reported, and its evidence
  must not imply the other gates were healthy.
- **The waiting allowance would outlast the poll budget.** The diagnosis must
  still be reached: an allowance that cannot be exhausted before the budget
  expires gives back exactly the generic timeout this feature exists to
  remove.
- **A read failure while a gate is blocked.** Read and write failures are
  already bounded separately (three consecutive failures ends the attempt at
  that gate). A failed read is not an observation of "still blocked" and must
  not advance the waiting allowance.
- **The run under test reaches a terminal state while a gate is still
  blocked** — for example the issue is closed or labelled stalled. The
  terminal state wins, as it does today.
- **A release-free dispatch collides with a scheduled attempt.** The existing
  single-run concurrency for this verification is unchanged: one queues behind
  the other, so two resets of the test repository still cannot race.
- **A release-free dispatch while the pause switch is set** — see
  Clarification Q2.
- **A maintainer dispatches the release-free mode and later wants the
  release.** Nothing is consumed: the next ordinary attempt for the same
  unreleased head behaves as it would have.

## Requirements *(mandatory)*

### Functional Requirements

#### Naming a gate that will never unblock

- **FR-001**: The verification MUST distinguish a merge gate that is waiting on
  required checks which have not reported a result from the pipeline under
  test merely taking a long time, and MUST report the former as a gate stall.
- **FR-002**: A merge gate whose pull request is blocked with no resolved check
  result MUST continue to be waited on while it is within a bounded waiting
  allowance, so a pull request whose checks have not been created yet is never
  declared stalled.
- **FR-003**: When a gate's waiting allowance is exhausted, the attempt MUST end
  with a gate-stall verdict that names that gate using the same gate names the
  existing gate-stall reasons use, names the pull request, and states that its
  required checks never reported a result.
- **FR-004**: The waiting allowance MUST be short enough that the diagnosis is
  always reached before the attempt's poll budget expires, and long enough that
  a pull request whose checks are merely slow to be created is never declared
  stalled. [NEEDS CLARIFICATION: how long the allowance should be — see
  Clarification Q1]
- **FR-005**: The waiting allowance MUST be tracked per gate and MUST reset only
  when that gate makes observable progress — its pull request merges or leaves
  the blocked-with-unresolved-checks state — never merely because the shape or
  content of the unresolved check result changed between observations.
- **FR-006**: An observation that could not be made (a failed read) MUST NOT
  advance a gate's waiting allowance; such failures remain governed by the
  existing consecutive-failure bound.
- **FR-007**: The existing generic timeout verdict MUST remain the outcome when
  no merge gate is blocked and the run under test is simply still open when the
  poll budget expires.
- **FR-008**: The durable failure report MUST classify this outcome as a gate
  stall, never as a pipeline defect, an infrastructure failure, or a timeout.
- **FR-009**: Every decision branch this behaviour introduces MUST be exercised
  by checked-in fixtures reachable from the gate registry — at minimum: blocked
  with nothing resolved inside the allowance (wait); the same beyond the
  allowance (gate stall); blocked then resolving to a pass inside the allowance
  (merge); an allowance reset by observable progress; and the unchanged generic
  timeout.

#### Proving the run without cutting a release

- **FR-010**: A maintainer MUST be able to dispatch the end-to-end verification
  so that it stops after the verdict: no version decided, no release
  dispatched, whatever the verdict.
- **FR-011**: A release-free dispatch MUST exercise the same verification path
  an ordinary attempt exercises — the same gates, the same verdict outcomes,
  the same durable report — so that its pass is evidence about the real path
  and not about a parallel one.
- **FR-012**: A release-free run MUST state in what it reports that it cut no
  release, so that the absent release is never read as a failure or as a
  release that silently failed to dispatch.
- **FR-013**: The ordinary scheduled and on-demand path MUST be unchanged: a
  passing verdict still decides a version and dispatches the release.
- **FR-014**: The release-free mode MUST default to off and MUST only be
  selectable by an explicit act at dispatch time, so that no persisted
  configuration can cause a scheduled attempt to silently skip a release it
  would otherwise have cut.
- **FR-015**: The relationship between the pause switch and a release-free
  dispatch MUST be stated and enforced. [NEEDS CLARIFICATION: whether a
  release-free dispatch runs while the pause switch is set, or the switch must
  still be cleared first — see Clarification Q2]

#### Making the resume condition satisfiable

- **FR-016**: Spec 055's resume condition (its FR-028 and FR-029, and the
  corresponding runbook scenario) MUST be restated so that the sequence it
  describes is executable, naming which run clears the pause switch and in what
  order the evidence is recorded. [NEEDS CLARIFICATION: whether a release-free
  validation run satisfies the resume condition, or only a real releasing run
  does — see Clarification Q3]
- **FR-017**: The runbook MUST state the release consequence of each dispatch
  mode at the dispatch step itself, not only in a prerequisite further up the
  page.
- **FR-018**: Spec 055's still-open validation tasks (T011, T020 and T022) MUST
  each name a dispatch path that exists after this feature and state whether
  following it cuts a release.

### Key Entities

- **Merge gate**: one of the three pull-request gates the unattended run must
  pass in the test repository (spec-draft, plan, finalize). Each has a name
  already used in verdict evidence, an expected head branch, and an expected
  base branch.
- **Gate waiting state**: per merge gate, how long its pull request has been
  continuously observed as blocked with no resolved check result, and the last
  evidence observed for it. Exists only for the duration of one attempt.
- **Attempt verdict**: the existing record of an attempt's outcome — outcome,
  failing check, expectation, evidence. This feature adds a new gate-stall
  reason, not a new outcome value.
- **Dispatch mode**: whether this attempt is permitted to proceed past the
  verdict to deciding a version and dispatching a release.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An attempt in which a merge gate's pull request never receives a
  check result ends with a verdict that names that gate and that pull request,
  and ends before the poll budget is exhausted rather than consuming all of it.
- **SC-002**: 100% of the decision branches this feature introduces are covered
  by checked-in fixtures that fail when the behaviour regresses; none of the
  branches relies on a manual demonstration as its evidence.
- **SC-003**: A maintainer can obtain a full end-to-end verdict for the
  unattended run with zero releases cut — no release tag created and no release
  dispatch attributable to the validating run.
- **SC-004**: Following the resume condition from a cold start requires no step
  that is impossible as written: every step is executable in the stated order,
  and the pause switch is never required to be both set and cleared at the same
  point.
- **SC-005**: Attempts in which no merge gate is blocked report exactly the
  outcome they report today — the pass path, the existing four gate-stall
  reasons, the infrastructure and pipeline-defect outcomes, and the generic
  timeout are all unchanged.
- **SC-006**: Spec 055's three still-open validation tasks are each runnable by
  one maintainer following the runbook, with the release consequence known
  before the dispatch.

## Assumptions

- The existing verdict vocabulary is sufficient: this feature adds a new
  *reason* within the existing gate-stall outcome rather than a new outcome,
  so the report's classification logic and the consumers of the verdict do not
  need to learn a new value.
- The existing bounds on consecutive read/write failures at a gate (three) and
  on rate-limited polls stay as they are; the waiting allowance introduced here
  is a separate bound over *successful* observations that say "still blocked".
- The test repository's provisioning still configures no branch protection, so
  the condition this feature diagnoses is today reachable only through a
  misconfiguration or an adopter-shaped repository that does have required
  checks. It is specified anyway because the cost of meeting it undiagnosed is
  a wasted 135-minute attempt and a misleading report.
- The three merge gates keep the names they already use in verdict evidence
  ("spec-draft PR merge", "plan PR merge", "finalize PR merge"); this feature
  reuses them rather than introducing new labels for the same gates.
- One attempt writes one verdict. When more than one thing is wrong, the first
  condition to be detected is the one reported, as today.
- The findings from the originating review that are already fixed are out of
  scope: the containment verdict's masked-login evidence and the login-leak
  fixture (#401), the pass-path reads that degraded to `null` (#469), the
  case-sensitive login comparison (#401), and the legacy `EXPECTED` status
  context (#523). The slug fallback's missing 404 distinction is tracked as
  #482 and is not re-specified here. The stale "fine-grained" wording in spec
  055's T021 is checked-off history and is left alone.
- This feature governs this repository's own release verification — the
  consuming instrument, not the published stage contract — so no adopter-facing
  input or output changes shape as a result of it.

## Dependencies

- Spec 055 (`specs/055-unattended-e2e-gates/`) — this feature amends its
  FR-028/FR-029 resume condition, its runbook, and its open validation tasks,
  and extends the gate-stall taxonomy it defined.
- Spec 045 (`specs/045-auto-release-verified-head/`) — owns the auto-release
  verdict, report and release-dispatch contracts this feature's release-free
  mode must leave intact for the ordinary path.
- Issue #482 — the adjacent read-classification gap; independent, but touching
  the same verification step.

## Clarifications

Three questions are open. They are recorded here and posted to the lifecycle
issue; the spec carries `[NEEDS CLARIFICATION]` markers at the requirements
they govern.

### Q1 — How long may a gate sit blocked with nothing resolved before it is called a stall? (FR-004)

The trade-off is a false stall (ending a healthy attempt early because a
checks app was slow to create a check) against a wasted attempt (burning the
full budget and reporting the generic timeout). The allowance has to fit
inside the attempt's poll budget with room for the verdict to be written.

### Q2 — Does a release-free dispatch run while the pause switch is set? (FR-015)

The pause switch is a kill switch for the whole verification today. Letting
the release-free mode run past it makes the proof reachable without touching
the switch, but weakens the switch's meaning to "no releases" rather than "no
runs".

### Q3 — Does a release-free validation run satisfy spec 055's resume condition? (FR-016)

FR-028 of spec 055 requires one unattended run to have reached `stage:done`
before the switch is cleared. Whether a release-free run is that run decides
whether the switch can be retired on the strength of a validation dispatch or
only after a real releasing attempt.
