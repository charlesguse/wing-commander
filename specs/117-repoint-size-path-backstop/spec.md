# Feature Specification: Repoint pr-conversation's size backstop at its single home

**Feature Branch**: `117-repoint-size-path-backstop`

**Created**: 2026-09-30

**Status**: Draft

**Input**: User description: "Repoint pr-conversation's classify-and-announce size-path backstop to its composite (spec 057 T021). `.github/scripts/single-home-waivers.json` (entry 3) waives Gate 60 for the inline size-path backstop jq in `pr-conversation.yml`'s `classify-and-announce` job (~line 1225). Its reason ends \"Remove this waiver when T021 lands.\" T021 is still unchecked at `specs/057-autonomous-board-loop/tasks.md:260`, and its former tracker #408 is closed, so the waiver has no open tracker. Done when `classify-and-announce` consumes the `wing-commander-size-path-backstop` composite instead of its inline copy, the waiver entry is deleted, and Gate 60 passes without it."

## Overview

The repository holds one rule for "is this drafted change small enough to
ship as a small PR": count the changed files, count the changed lines,
compare each against a threshold. Two callers need that rule. One of them
— the board loop's route decision — reads it from the single home the rule
was extracted into. The other — the PR-conversation stage's
`classify-and-announce` job, the site the rule was extracted *from* — still
runs its own inline copy, because repointing it was deferred when the
extraction shipped.

That deferral was recorded honestly: a registered waiver in the
single-home register, a note in the composite's own header, a note in the
gate that enforces the rule, and a tracking issue. The tracking issue has
since been closed. So the repository now carries a duplicated
routing rule whose only remaining marker is a waiver pointing at nothing —
the exact state the waiver mechanism exists to prevent, since a waiver
that cannot expire is indistinguishable from a rule nobody enforces.

This feature closes that gap: the PR-conversation stage's size decision
comes from the same one home the board loop's does, the waiver is removed,
and the enforcement gate passes on its own merits rather than on an
exception.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The size rule has one home in fact, not just on paper (Priority: P1)

A maintainer needs to change how "small" is measured — say, to stop
counting pure-whitespace lines, or to fix an off-by-one in how a diff
header is skipped. Today they must find and change two copies, and nothing
fails if they change only one: the board loop and the PR-conversation
stage would silently start disagreeing about whether the same drafted
change is small. After this feature, the maintainer changes the measurement
in one place and both routing decisions move together.

**Why this priority**: This is the defect itself. Every other part of this
feature is bookkeeping that follows from it. A divergence between the two
copies is invisible until it produces a wrong routing decision on a live
PR — a drafted change routed as a small PR that should have become a spec
request, or the reverse.

**Independent Test**: Change the measurement in its single home in a
throwaway branch and confirm the PR-conversation stage's re-route decision
changes accordingly, with no second edit anywhere.

**Acceptance Scenarios**:

1. **Given** a PR-conversation run whose agent drafted a
   `small-unrelated-change` classification touching 2 files and 10 changed
   lines, **When** `classify-and-announce` computes its size decision,
   **Then** the classification stays `small-unrelated-change` and its
   drafted content is unchanged — the same outcome the inline copy
   produces today.
2. **Given** the same run but with a drafted change touching 5 files,
   **When** `classify-and-announce` computes its size decision, **Then**
   the classification is re-routed to `new-functionality` with
   `fold-target` `new-spec`, an issue title and issue body replacing the
   PR title and body, and the planned-action text amended — byte-identical
   to today's re-route.
3. **Given** a comment producing several classifications, only some of them
   `small-unrelated-change`, **When** the size decision runs, **Then**
   each `small-unrelated-change` leg is measured against its own drafted
   content and no other category's leg is altered.
4. **Given** the measurement altered in its single home only, **When** both
   the board loop's route decision and `classify-and-announce` run,
   **Then** both observe the altered measurement.

---

### User Story 2 - The waiver register carries no expired exceptions (Priority: P2)

A maintainer reading the single-home waiver register should be able to
trust that every entry in it is live: either permanently justified, or
tracked by an issue that is actually open. An entry whose tracker is closed
and whose stated removal condition has not been met teaches the next reader
that entries in this file are advisory.

**Why this priority**: It follows from US1 and cannot be done before it —
removing the waiver while the duplicate remains simply makes the gate fail.
But it is separately valuable: it is what restores the register's own
credibility, and it is the condition the originating issue names as "done".

**Independent Test**: Delete the waiver entry, run the single-home gate,
and confirm it reports no finding for the PR-conversation stage's file.

**Acceptance Scenarios**:

1. **Given** the repointed call site, **When** the single-home gate runs
   with the waiver entry deleted, **Then** it passes and reports no
   duplicate of the size measurement anywhere outside its single home.
2. **Given** the waiver entry deleted, **When** the waiver register's own
   stale-check runs in both directions, **Then** it neither fails for a
   waiver matching nothing nor for a count that no longer matches.
3. **Given** a future change that pastes the size measurement into a third
   place, **When** the single-home gate runs, **Then** it fails — the
   protection the waiver was suppressing is restored, not removed.

---

### User Story 3 - The repoint is proven, not asserted (Priority: P3)

The reason this call site was skipped the first time was not difficulty —
it was the absence of evidence. The measurement sits inside a
per-classification pipeline that also rewrites the classification's
category and drafted content on the over-threshold branch, and there was no
way to demonstrate before shipping that a refactor left that rewrite
unchanged. A maintainer reviewing this change needs to see that evidence
rather than take the claim on trust.

**Why this priority**: The routing decision is live and production-facing;
a silent regression here mis-routes a real contributor's request. But the
evidence is a property of *how* US1 ships, so it is ranked after it rather
than instead of it.

**Independent Test**: Run the repository's own gate suite and confirm a
check exercises the re-route decision — both branches — against fixtures,
failing if the decision changes.

**Acceptance Scenarios**:

1. **Given** a fixture set covering under-threshold, over-by-files,
   over-by-lines, and exactly-at-threshold drafted changes, **When** the
   proof check runs, **Then** each fixture's resulting classification
   (category, fold-target, drafted content, planned-action) matches the
   decision the inline copy produces today.
2. **Given** a deliberate break introduced into the repointed decision,
   **When** the proof check runs, **Then** it fails — the check can fail
   its own subject.
3. **Given** the change merged, **When** one PR-conversation run is
   re-driven against a drafted `small-unrelated-change`, **Then** the run's
   own record shows the size decision taken and the announcement matching
   it, and that evidence is recorded on the pull request or the
   lifecycle issue.

---

### Edge Cases

- A `small-unrelated-change` leg whose drafted content has no file-changes
  at all, or an empty list: measures as zero files and zero lines, stays
  under threshold, is not re-routed — today's behavior.
- A file-change entry with no diff text: contributes to the file count and
  contributes zero lines, exactly as today.
- A drafted change sitting exactly on the threshold (3 files, 40 changed
  lines): stays under, because the comparison is strictly-greater on both
  sides. An off-by-one here silently changes which requests become spec
  requests.
- A run with zero `small-unrelated-change` legs: the size decision must be
  a no-op that cannot fail the job or alter any other leg — including the
  case where the measurement now happens somewhere other than inside the
  per-leg pipeline.
- The measurement cannot be computed (malformed drafted content, the
  measurement step itself erroring): the job must fail loudly rather than
  treat the leg as under-threshold, because "under threshold" is the
  direction that opens a PR nobody gated.
- The over-threshold re-route happens before confirmation requirements,
  the out-of-PR determination, and the intent announcement are computed —
  a leg that reaches the acting job is under-threshold by construction.
  Moving the measurement must not move it after any of those three.
- `classify-and-announce` runs inside a caller-supplied container image, so
  any new shell introduced by this change must not depend on the image's
  default shell being bash.
- An adopter pinning a release tag consumes the composite through the
  published surface; any change to the composite's own inputs or outputs is
  a compatibility surface change, not an internal refactor.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The changed-file-count and changed-line-count measurement
  used by the PR-conversation stage's `classify-and-announce` job MUST
  come from the same single home the board loop's route decision uses. No
  second copy of the measurement may remain in the stage workflow.

- **FR-002**: For any drafted content, the over/under-threshold verdict the
  repointed call site produces MUST equal the verdict the current inline
  copy produces: over when the changed-file count exceeds 3 or the changed
  line count exceeds 40, under otherwise, with changed lines counted as
  unified-diff lines beginning `+` or `-` excluding the `+++`/`---` file
  headers, summed across every file-change entry.

- **FR-003**: The measurement MUST be applied per classification leg,
  against that leg's own drafted content, for every leg categorised
  `small-unrelated-change` and for no other leg.

- **FR-004**: On the over-threshold branch, the existing re-route MUST be
  preserved unchanged: the category becomes `new-functionality`, the
  fold-target becomes `new-spec`, the drafted content becomes an issue
  title and issue body (the issue title falling back to the leg's summary
  when the drafted PR title is empty), the issue body gains the re-route
  explanation naming the measured file count, the measured paths and the
  measured line count, and the planned-action text gains its
  exceeded-the-threshold suffix.

- **FR-005**: The re-route MUST continue to be applied before the
  confirmation-requirement computation, the out-of-PR determination, and
  the intent announcement, so that all three see only the corrected
  classification.

- **FR-006**: The waiver entry registering this call site as an exception
  to the single-home rule MUST be deleted from the waiver register, and the
  single-home gate MUST pass with no waiver covering it.

- **FR-007**: Every live comment that states this call site is not yet
  repointed MUST be corrected in the same change — the single home's own
  header, the enforcement gate's declaration of that home, and any other
  live prose asserting the exception. Comments in this repository are
  load-bearing; a stale one is a defect, not cosmetics.

- **FR-008**: A check reachable from the repository's own gate suite MUST
  exercise the repointed re-route decision against checked-in fixtures
  covering under-threshold, over-by-files, over-by-lines, and
  exactly-at-threshold inputs, and MUST fail when that decision changes.

- **FR-009**: When the measurement cannot be computed for a leg, the job
  MUST fail rather than proceed with an assumed verdict. Silently treating
  an unmeasurable change as under-threshold is the unsafe direction.

- **FR-010**: Any shell step this change introduces into
  `classify-and-announce` MUST resolve to bash explicitly, because the job
  runs inside a caller-supplied container image whose default shell is not
  guaranteed.

- **FR-011**: The full pull-request gate suite MUST pass locally and in CI
  with no new waiver, no new exception entry, and no gate suppressed.

- **FR-012**: The PR-conversation call site MUST NOT override the
  threshold values — it keeps 3 files and 40 lines, supplied by the single
  home's own defaults, so its behavior is unchanged.

- **FR-013**: If the chosen approach changes the single home's declared
  inputs or outputs, that change MUST be treated as a deliberate widening
  of the adopter-pinned published surface and recorded as such
  [NEEDS CLARIFICATION: the single home is a step-level composite that
  measures one drafted change per invocation, but this call site needs a
  verdict per classification leg with the leg count unknown until runtime —
  which shape should the repoint take?]

- **FR-014**: The re-route explanation text the requester reads MUST state
  thresholds consistent with the thresholds actually applied
  [NEEDS CLARIFICATION: the explanation currently hardcodes "<=3 files,
  <=40 changed lines" in two places — should it keep the literal prose
  (byte-identical output, but it can drift from a threshold change) or
  derive the numbers from the applied thresholds (drift-proof, but the
  emitted text is no longer byte-identical to today's)?]

- **FR-015**: The evidence obligation for this change MUST be satisfied
  before merge [NEEDS CLARIFICATION: is the fixture-driven check of
  FR-008 sufficient on its own, or does this feature also owe the
  behavioral harness for the whole `classify-and-announce` decision step
  that the deferred task named as its own recommended prerequisite?]

### Key Entities

- **Classification leg**: one agent-proposed action extracted from a PR
  comment, carrying a category, a summary, a planned action, a fold target
  and drafted content. Legs carry a stable identifier assigned before any
  reordering, and several legs may arise from one comment.
- **Drafted content**: the material a leg would act on. For a
  `small-unrelated-change` leg it holds a PR title, a PR body, and a list
  of file changes, each a path plus unified diff text.
- **Size verdict**: the measured file count, the measured changed-line
  count, and whether either exceeds the caller's threshold. Pure
  measurement — the caller decides what exceeding it means for routing.
- **Waiver entry**: a registered, reasoned exception to the single-home
  rule, naming a file, a check, a pattern, an expected count, and either an
  open tracking issue or a permanent justification. Stale-checked in both
  directions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The single-home enforcement gate reports zero copies of the
  size measurement outside its one home, with zero waivers covering the
  PR-conversation stage.

- **SC-002**: The waiver register contains zero entries whose stated
  removal condition has been met, and zero entries whose only named
  tracker is closed.

- **SC-003**: For 100% of the fixture cases, the classification the
  repointed decision produces — category, fold target, drafted content and
  planned action — is identical to the one produced before the change.

- **SC-004**: A single-file edit to the measurement changes the routing
  outcome observed by both callers; no second file needs editing for the
  two to agree.

- **SC-005**: One re-driven live run after merge shows a
  `small-unrelated-change` leg reaching the size decision and being
  announced consistently with the verdict, with that evidence recorded on
  the pull request or the lifecycle issue.

- **SC-006**: The full pull-request gate suite passes with no gate skipped,
  no new exception registered, and no existing exception widened.

## Assumptions

- The deferred task this issue names is the entire scope. The sibling
  exception recorded for the dispatch-then-correlate idiom, which is in the
  same "not yet repointed" state, is out of scope and its waiver stays.
- The thresholds themselves are not under review. This change moves where
  the comparison lives, not what it compares against; the board loop keeps
  its own, larger, separately reviewed thresholds.
- The specification artifacts of the feature that deferred this task are
  historical records now that its final pull request has merged, so its
  task list is not edited to tick the deferred item off. The correction
  lands in the code, the enforcement gate, and the live comments instead.
- `classify-and-announce` already resolves composite actions from the
  pipeline checkout it makes for its other steps, so the single home is
  reachable from this job without new checkout plumbing.
- The re-route's downstream consumers — the confirmation gate, the
  out-of-PR determination, the announcement, and the acting job — are
  unchanged by this feature; they continue to see only corrected
  classifications.
- "Byte-identical behavior" is the default bar for the routing verdict.
  Where the emitted human-readable prose is concerned, FR-014 records the
  one place that default is being questioned.
- Proving behavior that only runs in Actions requires one post-merge
  re-drive, per this repository's own rule; that re-drive is part of the
  work, not a follow-up.

## Dependencies

- The single home for the size measurement already exists and is already
  the board loop's only route to the formula; this feature adds a second
  consumer rather than creating the home.
- The extraction-and-execute test harness that exercises the single home's
  own shell already exists and can be extended or mirrored rather than
  invented.
- The single-home enforcement gate and the waiver register's two-direction
  stale check are both live and will react to this change immediately —
  the waiver deletion and the repoint must land together or the gate fails
  either way round.
