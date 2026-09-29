# Feature Specification: Classify the cancel call's own error instead of racing a pre-read status

**Feature Branch**: `087-stop-cancel-error-classification`

**Created**: 2026-09-25

**Status**: Draft — clarifications resolved (see issue #621)

**Input**: User description: "wing-commander-board-stop-check's cancel path reads the target run's status via `gh api .../actions/runs/<id>`, then -- in a separate call moments later -- conditionally calls `gh run cancel` and warns on any failure. If the target run completes in the window between the two calls, `gh run cancel` 409s and the warning fires anyway: the exact spurious-noise case this check exists to eliminate. This mirrors `pr-conversation.yml`'s own stop procedure, which gets the same 'don't warn on an already-completed run' guarantee with no pre-check and no race window: attempt `gh run cancel` unconditionally, then classify a failure from its own stderr (409 / 'already completed' / 'cannot cancel') instead of reading status first. The `gh api` read itself stays -- it also supplies the `path`/`repository` fields the issue #547 defence-in-depth check needs before a cancel is attempted at all -- only the now-redundant `.status` extraction and the status-gated branch are replaced with the pr-conversation.yml-style error classification. Low severity, cosmetic-only (log noise): `paused=true` already fires unconditionally regardless of the cancel outcome, so the kill-switch/stop-request behavior itself is unaffected either way. Fixes #470."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A stop request that lands as the target run finishes produces no spurious warning (Priority: P1)

A maintainer asks the board loop to stop an in-flight item. By the time the loop's
stop check gets as far as cancelling the earlier run it named, that run has already
reached a terminal state on its own. Today the check looked up the run's status a
moment earlier, saw a non-terminal value, attempted the cancellation anyway, and
then reported the resulting refusal as a warning on the run — the maintainer sees a
warning annotation describing a failure that is not one. After this change the
maintainer sees a clean run: the stop took effect, no warning is raised, a
non-warning informational line records that the target had already finished, and
the loop stands down exactly as before.

**Why this priority**: This is the entire defect. The status pre-check exists only to
suppress this warning, and it suppresses it only when the run happens to be already
terminal at the moment of the read — a guarantee it cannot make for the window
between the read and the cancellation. Eliminating the window is what makes the "no
warning for an already-finished run" promise hold in every case rather than most.

**Independent Test**: Drive the stop check against a target run whose cancellation is
refused with an already-terminal response, and confirm the step emits no warning
annotation, emits a non-warning line recording that the run had already finished,
still reports the item as paused, and still exits successfully.

**Acceptance Scenarios**:

1. **Given** an authorized stop request naming an earlier run of this workflow in this
   repository, **When** the cancellation is refused because that run has already
   reached a terminal state, **Then** no warning is emitted, a non-warning
   informational line records that the target had already finished, the step
   succeeds, and the paused result is reported.
2. **Given** the same stop request, **When** the run metadata read reports the target
   as already terminal but the cancellation is attempted anyway and refused,
   **Then** the outcome is identical to scenario 1 — the recorded status plays no
   part in whether the cancellation is attempted.
3. **Given** the same stop request, **When** the cancellation succeeds, **Then** no
   warning is emitted, no already-finished line is emitted, and the paused result is
   reported — a maintainer reading the run can tell this case apart from scenario 1.

---

### User Story 2 - A cancellation that fails for a real reason is still reported (Priority: P1)

A maintainer's stop request names a genuinely still-running earlier run, and the
cancellation call fails for a reason that is not "the run already finished" — a
permission error from a misconfigured cancellation credential, an API error, a
network failure. That run may still be executing. The maintainer must see a warning
naming the run and quoting what went wrong, so they can cancel it by hand.

**Why this priority**: Equal in priority to Story 1 — the two together are the whole
point. Suppressing the spurious warning is worthless if it also suppresses the real
one. The repository has already been bitten by exactly this collapse once: a
permission failure reported to a maintainer as a confirmed completion. A quiet stop
check that silently failed to stop anything is a strictly worse defect than the noise
this feature removes.

**Independent Test**: Drive the stop check against a target run whose cancellation
fails with a permission-style error, and confirm a warning is emitted that names the
run and carries the error text.

**Acceptance Scenarios**:

1. **Given** an authorized stop request naming a valid target, **When** the
   cancellation fails with an error that does not identify the run as already
   terminal, **Then** a warning is emitted naming the run and including the error
   output, and the step still succeeds and reports the item as paused.
2. **Given** the same stop request, **When** the cancellation fails with no usable
   error output at all, **Then** the failure is treated as a real failure and warned
   about — never as an already-terminal run.

---

### User Story 3 - The existing target and self-run protections are untouched (Priority: P2)

The stop check refuses to point a cancellation credential at anything that is not one
of this workflow's own runs in this repository, and it never cancels the run
executing the check itself. Both protections are decided before any cancellation is
attempted and must survive this change unchanged.

**Why this priority**: These are security and correctness guarantees already
specified and gated elsewhere; this feature must not weaken them as a side effect of
moving the outcome decision after the call. Lower priority only because it is a
preservation requirement, not new behaviour.

**Independent Test**: Re-run the existing checked-in stop-check cases — a different
workflow's run, an unreadable run, a forged marker from a human, a stop request
naming the current run — and confirm every one still results in no cancellation
attempt, the same paused result, and a successful step.

**Acceptance Scenarios**:

1. **Given** a stop request naming a run belonging to a different workflow or a
   different repository, **When** the stop check runs, **Then** no cancellation is
   attempted and the existing warning about the unverified target is emitted.
2. **Given** a stop request naming a run whose metadata cannot be read, **When** the
   stop check runs, **Then** no cancellation is attempted and the existing warning is
   emitted.
3. **Given** a stop request that resolves to the run executing the check itself,
   **When** the stop check runs, **Then** no cancellation is attempted and the item
   is reported as paused.

---

### Edge Cases

- The run metadata read succeeds and reports a terminal state, but the cancellation
  then succeeds anyway (the state was stale in the other direction): no warning, no
  already-finished line, and the item is still reported as paused.
- The cancellation is refused with an already-terminal response whose wording differs
  in case or surrounding punctuation from the canonical phrasing: still recognised,
  still no warning, still recorded as the non-warning informational line.
- The cancellation fails with an error that is not an already-terminal refusal but
  whose text happens to contain the digits of the already-terminal status code — a
  permission failure naming a run id or URL containing `409`, for instance: this MUST
  be warned about. The recognition vocabulary anchors the status code to its protocol
  prefix (`HTTP 409`) rather than matching the bare digits, precisely so this case
  cannot collapse into the silent path.
- The cancellation fails with output that merely *contains* a recognised
  already-terminal phrase inside an otherwise unrelated error: treated as
  already-terminal. This is an accepted trade-off for the phrase vocabulary — the
  canonical classification this repository already uses for the same decision accepts
  it, and the consequence is a suppressed warning about a cosmetic-only path.
- The cancellation credential lacks the permission the call needs: warned about, and
  never reported as, or silently treated as, an already-finished run.
- The cancellation's error output contains newlines or text that would otherwise be
  read as a workflow command by the runner: the warning still names the run and still
  conveys the error, and the surrounding annotation cannot be broken or forged by that
  output.
- Every outcome — success, already-terminal refusal, real failure — leaves the step
  exit status unchanged and leaves the paused result unchanged. A stop request always
  pauses the job's next durable action regardless of what the cancellation did.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Once a stop request has named a cancellation target and that target has
  passed the existing ownership check (it is one of this workflow's own runs in this
  repository, and it is not the run performing the check), the stop check MUST
  attempt the cancellation unconditionally — without first consulting the target's
  recorded execution state.
- **FR-002**: The run metadata read MUST remain, because the ownership check depends
  on the workflow path and repository it returns. The execution-state field of that
  read MUST no longer be extracted or consulted anywhere in the stop check.
- **FR-003**: When the cancellation fails and its own error output identifies the
  target as one that can no longer be cancelled, the stop check MUST NOT emit a
  warning.
- **FR-004**: When the cancellation fails for any other reason — including a failure
  with empty or unrecognised error output — the stop check MUST emit a warning that
  names the target run and includes the error output, so a maintainer can act on a run
  that may still be executing.
- **FR-005**: The vocabulary used to recognise an already-terminal refusal MUST be the
  same one this repository already uses for the identical decision in its other stop
  procedure, so the two sites cannot drift into disagreeing about what "already
  finished" looks like. While consolidating it, the vocabulary's status-code term MUST
  be anchored to its protocol prefix (`HTTP 409`) rather than matching the bare digits
  `409` anywhere in the output, so that a failure that is not an already-terminal
  refusal — a permission error quoting a run id or URL that happens to contain those
  digits — is not classified as one. Both consuming sites MUST get the anchored
  vocabulary; the other stop procedure's present unanchored form is corrected by this
  change rather than preserved.
- **FR-006**: No cancellation outcome may change the stop check's other observable
  results: the step MUST still succeed, MUST still report the item as paused whenever
  an authorized stop request was found, and MUST still use the dedicated cancellation
  credential for the cancellation call and the run metadata read while using the App
  credential for the issue-comment read.
- **FR-007**: The change MUST be covered by checked-in fixtures exercising every
  outcome branch it ships — a successful cancellation, an already-terminal refusal
  producing no warning and the informational line, a non-terminal failure producing a
  warning, and a non-terminal failure whose error text contains the bare digits of the
  already-terminal status code without its protocol prefix (which MUST warn) — and the
  existing ownership, unreadable-target, forged-marker and self-run fixtures MUST
  continue to pass unchanged.
- **FR-008**: The gate covering this behaviour MUST fail when the classification is
  removed or inverted — demonstrated by a mutation of the shipped logic that the gate
  catches — so the gate cannot sit green while the behaviour it names is absent.
- **FR-009**: What is consolidated is the **recognition vocabulary only**, not the
  whole procedure. The set of error signatures that identify an already-terminal
  refusal MUST live in exactly one place — a shared script under the repository's
  cross-workflow shared-script directory — and both sites that make the decision MUST
  consume it from there. Each site keeps its own reporting: the stop check emits an
  annotation-shaped outcome, the other stop procedure keeps its distinct comment
  bodies. Neither site's reporting is moved, merged, or made configurable by this
  change.
- **FR-009a**: The single home established by FR-009 MUST be enforced by a check added
  to the repository's existing single-home idioms gate, alongside the check that
  already covers this stop check, so a re-pasted copy of the vocabulary at a third
  site fails the suite rather than surviving until the first divergent fix.
- **FR-010**: The already-terminal path MUST record a **non-warning informational
  line** stating that the named run had already finished and that nothing was
  cancelled. It MUST NOT be a warning or an error, so that the annotation collector
  that gathers only warnings and failures does not pick it up, and so that a
  maintainer reading the run can still tell "the earlier run was cancelled" apart from
  "the earlier run had already finished".
- **FR-011**: The error output the warning of FR-004 includes MUST be neutralised
  before it reaches the run log, so that newlines or workflow-command-shaped text in
  that output cannot break out of or forge the surrounding annotation. This
  neutralisation belongs to this feature's classification change and MUST be delivered
  with it — the adjacent in-flight specification that also touches this error text
  MUST NOT ship a second rewrite of the same line.

### Key Entities

- **Stop request**: An authorized maintainer instruction, found on the board item,
  that halts the loop's next durable action and may name an earlier run to cancel.
  Unchanged by this feature.
- **Cancellation target**: The earlier run a stop request names. Already qualified by
  ownership (this workflow, this repository) and by not being the run performing the
  check. This feature removes execution state from that qualification.
- **Cancellation outcome**: The result of attempting the cancellation — cancelled,
  already-terminal, or failed. This feature changes how the outcome is determined
  (from the call's own error output, after the fact) rather than what the outcomes
  are. Only the failed outcome is warned about; the already-terminal outcome is
  recorded as a non-warning informational line, and the cancelled outcome is recorded
  by the absence of both.
- **Already-terminal vocabulary**: The set of error signatures that identify a refusal
  as "this run can no longer be cancelled". Owned by a single shared script and
  consumed by both stop procedures; its status-code term is anchored to its protocol
  prefix so a failure that merely quotes those digits is not mistaken for one.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A stop request whose target becomes terminal at any point before or
  during the cancellation attempt produces zero warning annotations and exactly one
  non-warning informational line naming the run — verified by a checked-in case in
  which the cancellation is refused as already-terminal, with no timing assumption in
  the check that could make the result depend on when the target finished.
- **SC-002**: 100% of cancellation failures that are not already-terminal refusals
  still produce a warning naming the run — verified by at least one checked-in
  permission-style failure case, one empty-error-output case, and one case whose error
  text contains the already-terminal status code's bare digits without its protocol
  prefix.
- **SC-003**: Removing or inverting the already-terminal classification causes the
  governing gate to fail, demonstrated by a mutation run that the gate catches.
- **SC-004**: Every stop-check case that passes today still passes with identical
  paused results, identical cancellation targets, identical credential usage and an
  identical successful exit status — zero regressions across the existing fixture set.
- **SC-005**: The repository's full pre-merge gate suite passes on the change.
- **SC-006**: No execution-state field of the run metadata read remains anywhere in
  the stop check, and no code path decides whether to attempt a cancellation from a
  value read before the attempt.
- **SC-007**: The already-terminal recognition vocabulary appears in exactly one file
  in the repository, both stop procedures read it from there, and introducing a copy
  of it at a third site fails the single-home gate — demonstrated by a mutation run
  that the gate catches.
- **SC-008**: Cancellation error output containing newlines or workflow-command-shaped
  text produces exactly one warning annotation, with no additional annotation
  attributable to that output — verified by a checked-in case.

## Assumptions

- The defect is cosmetic. The item is paused, and the loop stands down, regardless of
  the cancellation outcome — before and after this change. This feature's value is
  removing a misleading signal from run logs, not changing what the loop does.
- Attempting a cancellation against an already-terminal run is harmless and has no
  side effect beyond the refusal, so removing the pre-check costs nothing but one
  refused call in the case that used to be short-circuited.
- The ownership check's dependence on the run metadata read is unchanged and
  unquestioned: a target whose metadata cannot be read is still never cancelled, and
  the existing warning for that case is retained verbatim.
- A stop request naming the run performing the check continues to skip the
  cancellation entirely, for the reason already recorded: cancelling the run executing
  the check would race its own graceful stand-down.
- The reasoning that originally justified the pre-check — that the loop's single
  serialized concurrency group means a named earlier run is always already terminal —
  stays documented as context, but is no longer relied on to decide anything. This
  feature makes the stop check correct whether or not that property holds, which is
  what a design change to the loop's concurrency (already under consideration) would
  otherwise invalidate.
- The change is confined to one composite action's stop-check step, the gate that
  covers it, the single-home gate extended by FR-009a, the new shared vocabulary
  script, and the one line in the other stop procedure that switches to consuming it.
  No stage workflow, no decision helper, and no board-loop job needs to change.
- Sharing only the vocabulary (FR-009) rather than the whole procedure is a deliberate
  scope boundary: the two sites' reporting surfaces genuinely differ, and merging them
  would reopen already-settled specification and gate work for no behavioural gain.
- Changing the other stop procedure's status-code match from the bare digits to the
  anchored form is a behaviour change at that site, and a narrow one: it makes that
  site stop classifying a non-409 failure that merely quotes those digits as
  already-completed. It moves that site toward, never away from, its own governing
  requirement that a permission failure is never reported as a completion.
- The neutralisation required by FR-011 is claimed by this feature by agreement with
  the owner, to keep it and the adjacent in-flight specification from both rewriting
  the same line. That other specification's remaining scope is unaffected.
