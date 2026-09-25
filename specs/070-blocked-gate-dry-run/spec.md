# Feature Specification: A never-unblocking merge gate is named

**Feature Branch**: `070-blocked-gate-dry-run`

**Created**: 2026-09-25

**Status**: Draft

**Input**: User description: "unattended E2E gates: containment verdict can drop its own evidence, no login-leak fixture, and the pause switch blocks the validation run" (lifecycle issue #533, routed from the board loop; originating review of #389 against spec 055). Two findings were still open after #401, #469 and #523: (1) a merge gate whose pull request is permanently blocked with an unresolved check rollup is waited on until the whole poll budget expires and then reported as a generic timeout instead of a gate stall naming the gate and the pull request; (2) the pause switch gates every auto-release job, so the feature's own validation dispatch requires clearing it, and a passing validation run then goes on to decide a version and dispatch a real release. The clarification round on #533 scoped this spec to (1) alone and deferred (2) — see Clarifications Q2 and Q3.

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

What remains in scope here is the second half of that fifth finding: a merge
gate blocked on required checks that never report a result is indistinguishable,
in the report a maintainer reads afterwards, from the pipeline under test simply
being slow.

### Scope

This spec covers the empty-rollup blocked gate stall and nothing else. The
sixth finding — that the pause switch gates the feature's own validation
dispatch, and that a passing validation run cuts a real release — was ruled
out of scope in the clarification round on #533. The release-free dispatch
mode, spec 055's FR-028/FR-029 resume condition, and its still-open
validation tasks (T011, T020, T022) are therefore untouched by this feature
and can return as their own `spec-request`.

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
- **The waiting allowance is reached late in the poll budget.** The diagnosis
  must still be reached and written: 20 minutes of allowance against a
  135-minute poll budget leaves about 115 minutes, so a gate that is blocked
  from the attempt's first observation is diagnosed with the budget barely
  touched, and even a gate that only becomes blocked late has its allowance
  bounded by the budget rather than silently giving back the generic timeout
  this feature exists to remove.
- **A read failure while a gate is blocked.** Read and write failures are
  already bounded separately (three consecutive failures ends the attempt at
  that gate). A failed read is not an observation of "still blocked" and must
  not advance the waiting allowance.
- **The run under test reaches a terminal state while a gate is still
  blocked** — for example the issue is closed or labelled stalled. The
  terminal state wins, as it does today.

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
- **FR-004**: The waiting allowance MUST be 20 minutes of continuous
  blocked-with-nothing-resolved observations, measured per gate. Twenty minutes
  is well past any plausible check-creation delay, so a pull request whose
  checks are merely slow to be created is never declared stalled; and it leaves
  about 115 minutes of the attempt's 135-minute poll budget, so the gate-stall
  diagnosis is always reached and written before the budget expires.
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

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An attempt in which a merge gate's pull request never receives a
  check result ends with a verdict that names that gate and that pull request,
  and ends before the poll budget is exhausted rather than consuming all of it.
- **SC-002**: 100% of the decision branches this feature introduces are covered
  by checked-in fixtures that fail when the behaviour regresses; none of the
  branches relies on a manual demonstration as its evidence.
- **SC-003**: Attempts in which no merge gate is blocked report exactly the
  outcome they report today — the pass path, the existing four gate-stall
  reasons, the infrastructure and pipeline-defect outcomes, and the generic
  timeout are all unchanged.

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
- The poll budget this feature's allowance must fit inside is spec 055's
  existing 135-minute (8100-second) budget; this feature does not change it.
- The findings from the originating review that are already fixed are out of
  scope: the containment verdict's masked-login evidence and the login-leak
  fixture (#401), the pass-path reads that degraded to `null` (#469), the
  case-sensitive login comparison (#401), and the legacy `EXPECTED` status
  context (#523). The slug fallback's missing 404 distinction is tracked as
  #482 and is not re-specified here. The stale "fine-grained" wording in spec
  055's T021 is checked-off history and is left alone.
- The pause switch, the release-free dispatch mode and spec 055's resume
  condition are out of scope by the owner's answers to Q2 and Q3; this feature
  changes nothing about when a release is cut, and a maintainer proving it
  still faces spec 055's runbook exactly as it stands today.
- This feature governs this repository's own release verification — the
  consuming instrument, not the published stage contract — so no adopter-facing
  input or output changes shape as a result of it.

## Dependencies

- Spec 055 (`specs/055-unattended-e2e-gates/`) — this feature extends the
  gate-stall taxonomy it defined and must fit inside its poll budget. Its
  FR-028/FR-029 resume condition, its runbook and its open validation tasks
  are out of scope here and are left as they are.
- Issue #482 — the adjacent read-classification gap; independent, but touching
  the same verification step.

## Clarifications

All three questions posted to lifecycle issue #533 were answered. None remain
open, and no `[NEEDS CLARIFICATION]` markers remain in this spec.

### Q1 — How long may a gate sit blocked with nothing resolved before it is called a stall? (FR-004)

The trade-off was a false stall (ending a healthy attempt early because a
checks app was slow to create a check) against a wasted attempt (burning the
full budget and reporting the generic timeout).

**Answer**: 20 minutes of continuous blocked-with-nothing-resolved
observations, per gate. That is well past any check-creation delay, and it
leaves about 115 minutes of the 8100-second budget, so the gate-stall
diagnosis is always reached. Folded into FR-004.

### Q2 — Does a release-free dispatch run while the pause switch is set? (FR-015)

**Answer**: out of scope. This spec covers only the empty-rollup blocked gate
stall. The release-free dispatch mode and the former User Story 2
(FR-010..FR-015) are dropped; they can return as their own `spec-request`.

### Q3 — Does a release-free validation run satisfy spec 055's resume condition? (FR-016)

**Answer**: out of scope for the same reason. The former User Story 3
(FR-016..FR-018), which restated spec 055's resume condition and its open
validation tasks, is dropped and can return with Q2's work.
