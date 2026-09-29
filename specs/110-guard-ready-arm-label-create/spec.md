# Feature Specification: Guard the `stage:spec` Label Create in clarify.yml's Ready Arm

**Feature Branch**: `110-guard-ready-arm-label-create`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "clarify.yml's 'Flip stage label for clarification' step has two arms. The `needs-clarification` arm guards its `gh label create \"stage:clarify\" ... --force` with `|| echo \"::warning::...\" >> \"$GITHUB_STEP_SUMMARY\"` (the fix T031 applied, and the same pattern used in intake.yml:1234). The `ready` arm's `gh label create \"stage:spec\" ... --force` has no such guard. Run steps execute under `bash -eo pipefail` by default, so a label-create failure here (e.g. a transient API error) fails the whole step. Because the following 'Announce spec PR ready for review' step's `if:` has no `!cancelled()`/`always()`, GitHub's implicit success() check skips it too -- so a spec PR could go up with the requester never notified it's ready for review, exactly the stranding this issue describes. This makes the `ready` arm match the `needs-clarification` arm's existing guard style: log a step-summary warning and continue, since the subsequent `gh issue edit --add-label` call already has its own independent guard and the PR itself was still opened successfully. Found by the implement stage of spec 063."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The requester is told their spec PR is ready, even when labelling hiccups (Priority: P1)

A requester answers the clarify stage's questions. The agent resolves every open
question, the spec PR is updated and the stage reaches the `ready` outcome. While
the run is writing the issue's stage labels, the label-creation call fails — a
transient API error, a rate limit, a permissions blip. Today that single failure
aborts the whole label step, and because the "Review the spec PR" announcement
downstream of it carries no `!cancelled()`, the announcement is skipped as well.
The requester is left with a ready spec PR and no notification that it is their
turn. After this change the labelling failure is recorded as a warning, the step
finishes green, and the announcement still reaches the issue.

**Why this priority**: This is the whole defect. The announcement is the only
signal the requester gets that the pipeline is waiting on them; losing it stalls
the lifecycle silently until a human notices by hand.

**Independent Test**: Drive the clarify stage to the `ready` outcome with the
label-creation call forced to fail (a fixture or a stubbed `gh`), and confirm the
label step ends successfully, a warning naming the label appears in the run's step
summary, and the "Review the spec PR" callout is posted to the lifecycle issue.

**Acceptance Scenarios**:

1. **Given** a clarify run whose outcome is `ready` and which is not blocked,
   **When** the `stage:spec` label creation fails, **Then** the label step
   completes successfully, the failure is reported in the run's step summary, and
   every step downstream of it that would have run on success still runs.
2. **Given** the same run, **When** the `stage:spec` label creation succeeds,
   **Then** behaviour is byte-for-byte what it is today: the label is added to the
   issue, `stage:clarify` is removed, and no warning is written.
3. **Given** a clarify run whose outcome is `ready` and which *is* blocked,
   **When** the label step runs, **Then** it takes no label action at all, exactly
   as today.

---

### User Story 2 - A maintainer can tell a labelling hiccup from a real failure (Priority: P2)

A maintainer opens a clarify run that finished green but whose issue is missing
its `stage:spec` label. The run's step summary names the label that could not be
created and states plainly that the spec PR was still announced, so the maintainer
can apply the label by hand instead of re-driving the stage or hunting through the
raw log for a swallowed error.

**Why this priority**: Without this the fix trades a loud failure for a silent
one. The sibling `needs-clarification` arm already sets the precedent for what a
readable warning looks like; matching it keeps one voice across the step.

**Independent Test**: Read the step summary produced by the User Story 1 test and
confirm it names the label, names the stage, and states what still happened.

**Acceptance Scenarios**:

1. **Given** a failed `stage:spec` creation, **When** the maintainer reads the
   run's step summary, **Then** it contains a warning identifying the clarify
   stage, the `stage:spec` label, and the fact that the spec PR was still
   announced ready.
2. **Given** a failed `stage:spec` creation *and* a subsequent failure adding the
   label to the issue, **When** the maintainer reads the step summary, **Then**
   both failures are reported and the step still completes successfully.

---

### User Story 3 - The guard cannot be removed again without something failing (Priority: P3)

A future edit to this step — a reformat, a copy into a sibling stage, a revert —
drops the guard. A gate in the PR-time suite fails and names the unguarded call,
rather than the regression shipping and waiting for the next stranded requester to
surface it.

**Why this priority**: The repository's stated rule is that a rule with no gate
behind it lasts until the next session. The prior cycle (spec 063, T031) fixed the
sibling arm and documented a "Never fails the job" guarantee, and this exact gap
survived anyway — because nothing enforced the guarantee.

**Independent Test**: Remove the new guard by hand, run the local gate suite, and
confirm it fails naming the file and the unguarded call; restore the guard and
confirm the suite passes.

**Acceptance Scenarios**:

1. **Given** the change is merged, **When** the guard is removed from the `ready`
   arm and the PR-time gate suite runs, **Then** the suite fails and the failure
   message names the workflow, the step, and the unguarded label-creation call.
2. **Given** the unmodified tree, **When** the PR-time gate suite runs, **Then**
   it passes.

---

### Edge Cases

- **Both calls in the arm fail.** Label creation fails *and* adding the label to
  the issue fails. Both are reported; the step still succeeds and the announcement
  still runs. The add-label call already has its own independent guard, so the two
  failures must not be collapsed into one report or allowed to mask each other.
- **The label already exists.** The forced create is a no-op today and must stay
  one; adding a guard must not turn a successful create into a reported warning.
- **The outcome is not `ready`.** The `needs-clarification` and `none`/default
  arms are untouched, including the `needs-clarification` arm's already-guarded
  create.
- **The run is blocked.** `ready` with the blocked signal set does no label work
  at all; the guard must not introduce a code path that runs in that case.
- **The step summary is unavailable.** If the warning cannot be written, the step
  must still succeed — reporting the failure must never become a second way to
  fail the step.
- **The removal of the label being replaced.** Removing `stage:clarify` when it is
  already absent exits non-zero and is already tolerated; the new guard must not
  change that.
- **Other unguarded label creations in the fleet.** Several other stages create
  labels without a guard. Whether any of them strands a downstream step the same
  way is the subject of a clarification below, not an assumption made here.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A failure of the `stage:spec` label creation in the `ready` arm of
  clarify.yml's stage-label flip step MUST NOT abort the step.
- **FR-002**: Such a failure MUST be reported in the run's step summary, naming the
  stage, the label that could not be created, and the fact that the spec PR was
  still announced ready — never swallowed silently.
- **FR-003**: The guard's shape and wording MUST match the sibling
  `needs-clarification` arm's existing guard, so the two arms read as one pattern
  rather than two.
- **FR-004**: Every step positioned after the stage-label flip step whose condition
  relies on the implicit success check MUST still execute when only the label
  creation failed — specifically the step that announces the spec PR as ready for
  review.
- **FR-005**: A label-creation failure MUST NOT change the job's conclusion: a run
  that is otherwise healthy stays green, and a run that should have failed for
  another reason is not rescued by this guard.
- **FR-006**: Behaviour when the label creation succeeds MUST be unchanged — same
  label, same colour, same description, same add and same removal of the label it
  replaces, and no warning emitted.
- **FR-007**: The governing contract that carries this step's literal shape and its
  "never fails the job" guarantee MUST be updated in the same change, so the
  contract and the workflow do not disagree the moment this merges.
- **FR-008**: The PR-time gate suite MUST fail if the guard is removed from any
  label-creation call inside a stage-label flip step, and MUST pass on the
  unmodified tree. [NEEDS CLARIFICATION: where should this enforcement live — a new
  dedicated gate script, an extension of the existing job-scoped label-creation
  gate, or an extension of the existing stage-label taxonomy gate?]
- **FR-009**: The change MUST NOT alter either stage's declared workflow inputs,
  outputs, or secrets, and MUST NOT introduce a new published composite action.
- **FR-010**: The sibling stage whose flip step has no label-creation call in its
  second arm MUST be left unchanged; this feature adds no new label writes
  anywhere.
- **FR-011**: The blast radius of the guard MUST be decided explicitly rather than
  implied. [NEEDS CLARIFICATION: does this change fix only clarify.yml's `ready`
  arm, or does it sweep every unguarded label-creation call across the pipeline's
  stages that precedes a step relying on the implicit success check?]
- **FR-012**: Whether the downstream announcement step additionally becomes
  resilient in its own right MUST be decided explicitly. [NEEDS CLARIFICATION:
  should the "announce spec PR ready for review" step's condition also be widened
  so it survives *any* upstream step failure, or is guarding the label creation the
  whole fix — leaving the announcement correctly suppressed when something genuinely
  broke upstream?]

### Key Entities

- **Stage-label flip step**: the single step in the clarify stage that translates
  the run's already-computed clarification outcome into the issue's stage labels.
  It has three arms: questions remain, the spec is ready, and neither.
- **Ready arm**: the branch of that step taken when the agent resolved every open
  question and the run is not blocked. It creates the "spec drafted / awaiting
  review" label, adds it to the lifecycle issue, and removes the
  "open clarification questions" label.
- **Spec-PR-ready announcement**: the step downstream of the flip that posts the
  "Review the spec PR" callout to the lifecycle issue. Its condition relies on the
  implicit success check, which is why it disappears when the flip step aborts.
- **Stage-label flip contract**: the checked-in contract document that carries the
  literal body of both stages' flip steps and asserts that the step never fails the
  job. It is a live document, not a historical record.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a clarify run reaching the ready outcome, a failing label creation
  leaves 100% of the downstream notifications intact — the requester receives the
  "review the spec PR" callout in every such run, where today they receive none.
- **SC-002**: A failing label creation produces exactly one human-readable warning
  in the run's step summary that names the label and the stage, and zero failed
  steps attributable to the label write.
- **SC-003**: Deleting the guard causes the PR-time gate suite to fail, and the
  unmodified tree passes the full suite with no new failures relative to the
  pre-change baseline.
- **SC-004**: The contract document and the workflow agree: the contract's recorded
  body for this step matches the shipped step, and its stated guarantee holds for
  every arm rather than one.
- **SC-005**: No behaviour change is observable in a run where the label creation
  succeeds — the resulting issue label set and posted comments are identical to a
  pre-change run of the same shape.

## Assumptions

- Run steps in these stages execute with the shell's abort-on-error and
  pipeline-failure behaviour on by default; this is why an unguarded failing call
  ends the step rather than merely returning non-zero.
- The add-label call in the same arm already has its own guard and continues to
  carry it; this feature does not consolidate the two guards into one.
- The warning destination is the run's step summary, matching the sibling arm,
  because the governing requirement from the prior cycle asks for step-summary
  visibility rather than silence. Whether that warning also surfaces as a workflow
  annotation is cosmetic and out of scope.
- The spec PR itself is opened before the flip step runs, so a label failure never
  costs the requester the PR — only the notification about it.
- The contract document for the flip step is treated as live and is corrected like
  code, per this repository's rule that contracts a gate reads stay live after a
  feature's final PR merges; the surrounding spec, plan and tasks files of the
  prior cycle are historical and are not amended.
- The lifecycle issue's label state is repaired by hand or by the next stage when a
  create fails; this feature does not add a retry or a reconciliation pass.
- Other stages' unguarded label creations exist and are visible, but whether they
  strand anything is not assumed either way — it is the subject of FR-011's open
  question.
