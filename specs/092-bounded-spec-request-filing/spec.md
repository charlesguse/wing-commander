# Feature Specification: Bounded, Idempotent spec-request Filing

**Feature Branch**: `092-bounded-spec-request-filing`

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "board-loop: bound spec-request filing retries and make filing idempotent — found by the code review of #514 (branch `fix/514-spec-request-create-guard`). Once #514 lands, a failed spec-request create fails the step loudly, leaves the issue unstalled, and a later run retries. That leaves two gaps: (1) no retry cap — every hourly run repeats triage and route (2 agent runs) and posts a fresh `route` marker, starving the rest of the board, which conflicts with spec 057 FR-050; causes include a missing `spec-request` label, a lost `issues:write` permission, and a `pr-title` longer than 256 characters. (2) no idempotency — if the create succeeds but the following comment or `board:stalled` label fails, the step still exits 0 and the issue stays eligible, so a later run files a second spec-request. Options to decide between: count earlier create failures recorded on the issue and stall on the Nth with an explicit 'no spec-request was filed' comment (Gate 93 check 3 would then need to allow that stall); or, before creating, look for an existing open spec-request whose body carries `Originating issue: …/issues/N` and reuse it; and decide what N should be and whether the cap is shared with the review round budget."

## Clarifications

### Session 2026-09-29 — answered on lifecycle issue #701

- Q1 (FR-017): deliver both bounds, only the attempt cap, or only the
  existence check? → A: **Both.** The two failure modes are disjoint: a
  reuse check cannot help a create that never succeeds, and a bound cannot
  stop a duplicate after a create that did succeed.
- Q2 (FR-010): what is N, and is it shared with the review round budget?
  → A: **Its own budget, N = 3, as a new `BOARD_LOOP_*` variable.** Filing
  retries and review rounds have no reason to move together, and three
  gives a transient failure two chances to heal before a human is asked.
- Q3 (FR-009): where does the failed-attempt count live? → A: **In the
  board item marker, as its own field — not the review `round` field**, so
  the two budgets stay decoupled. Counting failure comments would break the
  #514 rule that a failed create publishes nothing; run-history counting
  does not survive renames or log retention. US3's give-up comment is the
  maintainer-visible record.

### Status update 2026-09-29 — reconciled with current `main` and specs 100/108

- **#782 (label before marker, every stall site).** Each filing site now
  adds `board:stalled` *before* rendering the stalled marker and posting
  the closing comment, and a failed add fails the step with no marker. A
  failed closing comment therefore no longer leaves the item eligible (the
  label is already on); the post-create window that can still produce a
  duplicate is a failed label add at route's spec verdict or at
  readiness's ordinary backstop-breach entry. The fix job's post-push
  breach already falls through to readiness's `step=breach` retry, which
  performs the #530 lookup.
- **Readiness has two filing entries.** Its ordinary backstop-breach entry
  (a breach measured after review converged) has no existence check today;
  only the `step=breach` retry entry does. Spec 100 (#752, FR-016–FR-018)
  defers that ordinary entry's duplicate in full to this feature, so "the
  readiness site" below means both entries.
- **Spec 108 (#791, merged) disposes of the originating issue at route
  time** by closing it as a duplicate of the spec-request, at all three
  sites, and names a maintainer reopening the original as the
  re-admission for a disposed issue. FR-005's "identical downstream
  treatment" therefore includes that disposition. A give-up stall files
  nothing, so its originating issue is left undisposed (spec 108 FR-011)
  and removing `board:stalled` remains its re-admission (FR-014).
- **Reconciled with spec 108 (maintainer, 2026-09-29).** FR-003 treats a
  *closed* prior spec-request as "already filed", which on its own would
  reuse it forever. Spec 108 FR-006/SC-005 (the owner's #791 answer)
  require that a maintainer reopening a disposed original after its linked
  spec-request has closed be routed afresh, at most once per reopen. That
  reopen is the one deliberate exception: FR-003 now scopes the existence
  check to spec-requests filed since the originating issue was last
  reopened, so the reopen is honoured and every other re-run still reuses.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One routing decision never produces two spec-requests (Priority: P1)

The board loop decides an issue is spec-shaped and files a `spec-request` for it. The
create succeeds, but the write that follows — the `board:stalled` label, which since #782
is applied before the marker and closing comment — fails. The issue is therefore still eligible on the next scheduled run, which
repeats triage and route, reaches the same verdict, and files a **second** `spec-request`
for the same originating issue. The maintainer now has two intake lifecycles for one piece
of work, each of which will cut its own spec branch and open its own spec PR.

With this feature, the loop asks first: "have I already filed a `spec-request` for this
originating issue?" If one exists it is reused — cross-linked, commented and stalled
exactly as a freshly filed one would be — and no second issue is created.

**Why this priority**: A duplicate `spec-request` is a durable, human-visible artifact that
costs a maintainer real cleanup and can burn a whole intake→plan→tasks lifecycle on work
already covered. It is the only gap here that produces wrong artifacts rather than wasted
runs, and it is already half-solved at one of the three filing sites, so it is both the
most damaging and the cheapest to close.

**Independent Test**: Drive the loop on an issue for which a `spec-request` already exists
carrying the originating-issue footer, and confirm the run reuses that issue's URL —
cross-link, comment and label all naming it — and creates nothing new. Shipping only this
story removes duplicate filings even while retries remain unbounded.

**Acceptance Scenarios**:

1. **Given** an issue for which the loop already filed a `spec-request`, **When** a later
   run reaches a spec verdict for that same issue, **Then** no new issue is created, the
   existing `spec-request` URL is what gets cross-linked and named in the closing comment,
   and the run records that it reused rather than filed.
2. **Given** a run whose `spec-request` create succeeds but whose `board:stalled` label
   write then fails, **When** the next scheduled run picks the item up, **Then** it
   completes the unfinished writes against the existing `spec-request` and the item ends
   stalled with exactly one `spec-request` in existence.
3. **Given** an issue with no `spec-request` filed for it, **When** the loop reaches a spec
   verdict, **Then** exactly one `spec-request` is created and the run behaves as it does
   today.
4. **Given** the existence check itself cannot be completed (the lookup fails), **When**
   the run reaches a spec verdict, **Then** the run files nothing and fails loudly, rather
   than filing on an unknown answer.

---

### User Story 2 - A filing that cannot succeed stops consuming the board (Priority: P1)

The `spec-request` label does not exist in the repository, or the token has lost
`issues:write`, or the drafted title exceeds GitHub's length limit. Every create fails.
Because a failed create deliberately leaves the issue unstalled (#514), every scheduled
run re-selects the same issue, spends two agent invocations on triage and route, fails
again, and posts a fresh `route` marker that makes the item the in-flight candidate for
the next run too. The rest of the board is never reached, and the item carries no bound at
all — which is what spec 057 FR-050 ("each item MUST carry a bounded round budget") asks
for.

With this feature, consecutive failed filings for an item are counted. On the third — the
configured cap — the loop stops retrying: it stalls the item with an explicit comment
saying that **no `spec-request` was filed**, why, and what the maintainer must do. The
board moves on to the next eligible item on the very next run.

**Why this priority**: Unbounded retry is a live board-starvation bug with a per-run agent
cost, and it is the requirement spec 057 already states but does not enforce for this path.
It is independent of User Story 1 — reuse cannot help when the create itself never
succeeds.

**Independent Test**: Make the create fail deterministically (for example, with the
`spec-request` label absent) and drive the loop repeatedly against a board holding that
item and one other eligible item. Confirm the failing item is attempted no more than three
times and that the other item is selected on the run after the cap is reached.

**Acceptance Scenarios**:

1. **Given** an item whose `spec-request` create has failed fewer than three times, **When**
   a scheduled run reaches a spec verdict for it, **Then** the create is attempted again and
   a failure fails the run loudly, leaving the item eligible.
2. **Given** an item whose `spec-request` create has now failed three times, **When** that
   third failure occurs, **Then** the item is stalled with a comment that states no
   `spec-request` was filed, names the last failure, and names the maintainer action that
   clears it; the run does not report the item as routed.
3. **Given** a stalled, capped item, **When** the next scheduled run starts, **Then** that
   item is not selected and a different eligible item is worked.
4. **Given** an item that failed to file once and then succeeded, **When** a later
   unrelated routing decision for the same item is reached, **Then** the earlier failures
   do not count against it.

---

### User Story 3 - A maintainer can see, from the issue alone, what happened (Priority: P2)

A maintainer looking at the originating issue can tell without opening an Actions log
whether a `spec-request` was filed, reused, or given up on; how many filing attempts have
been spent; and what to do next. The give-up state is recoverable by the same one action
that clears every other stall in this loop — removing `board:stalled` — so a maintainer who
creates the missing label or restores the permission can re-admit the item without
re-running anything by hand.

**Why this priority**: Both bounds above are only safe if the state they leave behind is
legible and reversible; without it, a capped item becomes a silent dead end. It is valuable
on its own but depends on at least one of the two bounds existing.

**Independent Test**: After driving an item to its cap, read only the issue's comments and
labels and confirm the attempt history, the give-up reason and the recovery step are all
present; then remove `board:stalled` and confirm the item is selected again.

**Acceptance Scenarios**:

1. **Given** a capped item, **When** a maintainer reads the issue, **Then** the number of
   attempts spent, the last failure reason, and the fact that no `spec-request` exists are
   all stated on the issue.
2. **Given** a capped, stalled item whose underlying cause has been fixed, **When** the
   maintainer removes `board:stalled`, **Then** the next run selects the item and its
   attempt count starts fresh.
3. **Given** an item whose `spec-request` was reused rather than newly filed, **When** a
   maintainer reads the issue, **Then** the comment names the reused `spec-request` and
   says it was reused.

---

### Edge Cases

- **A prior `spec-request` was closed.** The existence check treats a closed prior
  `spec-request` for the same originating issue as "already filed" and does not create a
  second one; re-filing work a maintainer explicitly closed is worse than filing nothing.
- **A maintainer filed the `spec-request` by hand.** The check only recognises artifacts
  the loop itself authored; a hand-filed one is not reused, because the loop cannot
  establish that it covers the same routing decision.
- **The existence check fails.** The run files nothing, fails loudly, and lets a later run
  retry — the same fail-closed posture #530 already uses — rather than risking a duplicate
  on an unknown answer. A failed check counts as a failed attempt against the bound, so a
  permanently broken check cannot itself starve the board.
- **The drafted title is longer than the platform's title limit.** The title is brought
  within the limit deterministically before the create, so this cause of repeated failure
  is removed rather than merely counted.
- **The failure happens at the *last* write.** An item whose create and comment succeeded
  but whose label write failed is completed on the next run through the reuse path, not
  re-filed.
- **Three filing sites, one rule.** Route's spec verdict, the fix job's post-push breach,
  and readiness's backstop breach (both its ordinary entry and its `step=breach` retry
  entry) all file `spec-request`s. The bound and the existence check
  apply to all three from one home; a fourth site added later inherits them or fails the
  gate suite.
- **The bound interacts with the existing create guard.** The guard that makes a failed
  create fail the job before anything is commented, labelled or published (#514) still
  holds on every attempt below the cap. The cap's own stall is the one place a comment and
  a `board:stalled` label follow a failed create, and it must be distinguishable from the
  defect that guard exists to prevent.
- **Two spec-requests already exist** for one originating issue when the feature ships. The
  loop reuses the oldest and does not attempt to close or merge the other; cleanup is a
  maintainer action.

## Requirements *(mandatory)*

### Functional Requirements

#### Idempotent filing

- **FR-001**: Before creating a `spec-request` for an originating issue, the loop MUST
  determine deterministically whether it has already filed one for that issue, and MUST
  reuse the existing artifact instead of creating a second one.
- **FR-002**: The existence check MUST match on artifacts authored by the loop's own
  identity and carrying the canonical originating-issue reference line the `spec-request`
  body builder already emits — never on title text, and never on a judgment made by an
  agent (Constitution IX).
- **FR-003**: The existence check MUST consider prior `spec-request`s regardless of whether
  they are currently open or closed, so an artifact a maintainer has already closed is not
  re-filed on the next run. The check MUST consider only `spec-request`s filed since the
  originating issue was last reopened: a maintainer reopening a disposed original after its
  spec-request closed is spec 108's (FR-006) deliberate re-admission, and MUST produce at
  most one fresh filing per reopen rather than a reuse of the closed one.
- **FR-004**: When more than one prior `spec-request` matches, the loop MUST reuse exactly
  one of them by a deterministic rule (the oldest), and MUST NOT create, close or modify
  any of the others.
- **FR-005**: A reused `spec-request` MUST receive the identical downstream treatment a
  newly filed one receives — the same cross-link mechanism, the same closing comment shape,
  the same `board:stalled` label and stalled marker — so the item ends in the same state
  either way.
- **FR-006**: The run's record MUST state whether the `spec-request` was newly filed or
  reused, and name the artifact either way.
- **FR-007**: If the existence check cannot be completed, the loop MUST NOT create a
  `spec-request` on that run, MUST fail the step loudly, and MUST leave the item in a state
  a later run can retry.

#### Bounded retries

- **FR-008**: Each item MUST carry a bounded number of `spec-request` filing attempts,
  satisfying spec 057 FR-050's requirement that every item carry a bounded budget.
- **FR-009**: The count of prior failed filing attempts for an item MUST be derived from
  durable state a later run can read, computed in deterministic code rather than inferred
  by an agent. That state is the board item marker the loop already writes and reads, and
  the count MUST occupy its own dedicated field in it — never the review `round` field, so
  the two budgets stay decoupled as FR-010 requires.
- **FR-010**: The attempt cap MUST be a single configured value, expressed the same way the
  loop's existing budgets are: a PR-reviewed, workflow-level `env:` constant in
  `board-loop.yml` beside `BOARD_LOOP_ROUND_BUDGET`. It MUST be its own budget — a new
  `BOARD_LOOP_*` value, separate from the existing review round budget — with a value of
  **3**. (`board-loop.yml` is not a published stage and targets only this repository's
  board, so there is no consuming repository to override it.)
- **FR-011**: While an item is below the cap, behaviour MUST be unchanged from today: a
  failed create fails the run loudly, nothing is commented, labelled or published on the
  failure, and the item is left eligible so a later run retries it.
- **FR-012**: On the attempt that reaches the cap, the loop MUST stall the item and MUST
  post a comment that states explicitly that no `spec-request` was filed, names the last
  observed failure, states how many attempts were spent, and names the maintainer action
  that re-admits the item.
- **FR-013**: A capped, stalled item MUST NOT be selected by later runs, and MUST NOT be
  left as the in-flight candidate that keeps the rest of the board from being worked.
- **FR-014**: Removing the stall MUST re-admit the item with a fresh attempt budget, using
  the loop's existing re-eligibility condition for an undisposed issue (removing
  `board:stalled`) rather than a new one.
- **FR-015**: A successful filing MUST clear the item's accumulated failed-attempt count, so
  an unrelated later routing decision for the same item starts from a full budget.
- **FR-016**: A title that would exceed the platform's title-length limit MUST be brought
  within it deterministically before the create, so that cause of repeated failure is
  removed rather than only bounded.

#### Scope, reuse and enforcement

- **FR-017**: Both the existence check and the attempt bound MUST apply to every site at
  which the loop files a `spec-request` — route's spec verdict, the fix job's post-push
  breach, and readiness's backstop breach, including both its ordinary entry and its
  `step=breach` retry entry (spec 100 FR-016 defers the ordinary entry's duplicate here). This feature delivers both the bound and the
  idempotency: delivering only the bound would leave duplicates possible, and delivering
  only idempotency would leave the board starvable.
- **FR-018**: The existence check MUST have exactly one implementation, generalising the
  one the breach-retry path already performs rather than adding a parallel copy, and the
  same MUST hold for the attempt bound.
- **FR-019**: A repository gate MUST fail when a `spec-request` filing site bypasses the
  shared existence check or the shared bound, or when a second copy of either appears — so
  the single-home rule survives the next site that is added.
- **FR-020**: The existing requirement that a failed create must fail the job before
  anything is commented, labelled or published MUST continue to be enforced for every
  attempt below the cap; the enforcement MUST be extended to admit the cap's deliberate
  give-up stall without admitting the defect it was written to catch.
- **FR-021**: Every artifact and message this feature writes MUST reuse the loop's existing
  cross-link, comment, label and marker mechanisms rather than a second hand-written
  format.
- **FR-022**: Nothing this feature writes — comment, artifact, or record — may name a
  downstream consumer of this repository.

### Key Entities

- **Filing attempt**: One run's attempt to put a `spec-request` in place for an originating
  issue. It either files a new artifact, reuses an existing one, or fails. Attempts are
  counted per item.
- **Attempt budget**: The bounded number of consecutive failed filing attempts an item may
  accumulate before the loop gives up on it and stalls it — its own configured value,
  defaulting to 3, distinct from the review round budget.
- **Prior-filing record**: The evidence that lets a later run answer "have I already filed
  for this issue?" — the loop's own authorship plus the canonical originating-issue
  reference carried in every `spec-request` body.
- **Give-up stall**: The terminal state of a capped item — stalled, with an explicit
  "no `spec-request` was filed" statement on the issue and one maintainer action that
  reverses it.
- **Board item marker**: The loop's existing per-issue durable state comment, which records
  the item's step and is read by selection on the next run. It gains one new field for this
  feature: the item's failed filing-attempt count, held separately from the review `round`
  field.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Across repeated runs in which the filing create fails deterministically, the
  same item is attempted at most three times (the configured cap); the number of agent
  invocations spent on that item is bounded at six rather than growing with time.
- **SC-002**: On the first scheduled run after an item reaches its cap, a different
  eligible item is selected — measured as: a board holding one capped item and one ordinary
  item makes progress on the ordinary item.
- **SC-003**: Zero duplicate `spec-request` artifacts are produced for one originating
  issue, including when the run is interrupted at each write that follows the create —
  verified by exercising a failure at every post-create write position.
- **SC-004**: A maintainer can determine an item's filing outcome — filed, reused, or given
  up on, and why — from the issue's comments and labels alone, with no Actions log.
- **SC-005**: Every `spec-request` filing site in the loop routes through one existence
  check and one attempt bound; introducing a site or a copy that does not fails the
  repository's gate suite.
- **SC-006**: A capped item whose underlying cause has been fixed returns to normal
  processing after exactly one maintainer action.
- **SC-007**: The behaviour of a below-cap failed create is unchanged: no comment, no
  label, no published artifact URL, and a red run.

## Assumptions

- Both gaps in the issue are closed by this feature (confirmed at clarification). They fail
  differently — reuse cannot help when the create never succeeds, and a bound cannot prevent
  a duplicate after a create that did succeed — so delivering only one leaves a live defect.
- The existence check generalises the lookup the readiness breach-retry path already
  performs (loop authorship + the originating-issue footer line + a reference to the PR +
  a `since` scope at the PR's creation time — the last two exist only where a PR does, so
  route's spec verdict needs its own scope), rather
  than introducing a second matching rule; this follows the repository's "shared logic has
  exactly one home" rule.
- The attempt cap is expressed as a workflow-level configured value in the same family as
  the loop's existing round budget — a new `BOARD_LOOP_*` `env:` constant set to 3, changed
  by a reviewed PR like `BOARD_LOOP_ROUND_BUDGET` (board-loop.yml is not published, so no
  adopter overrides it). It is deliberately a
  second knob rather than a reuse of the review round budget: filing retries and review
  rounds have no reason to move together, and 3 gives a transient failure (a rate limit, a
  flaky write) two chances to heal before a maintainer is asked to act.
- The failed-attempt count is carried in the board item marker rather than counted from
  comments or from prior run history. Counting posted failure comments would require the
  loop to publish something on a failed create, which the #514 guard (FR-011, FR-020)
  forbids; counting prior runs depends on run-history attribution that does not survive
  workflow renames or log retention. The give-up comment required by FR-012 is the
  maintainer-visible record instead (User Story 3).
- The give-up stall reuses the loop's existing stall mechanism — the `board:stalled` label
  plus a stalled marker — and its existing re-eligibility condition for an undisposed issue
  (removing the label; spec 108's reopen path applies only to a disposed original), rather
  than a new state.
- "The loop's own identity" means the App identity the loop already uses to author its
  markers and comments; artifacts authored by anyone else are not the loop's to reuse.
- A closed prior `spec-request` filed since the originating issue was last reopened counts as
  "already filed" (FR-003). The issue's own wording
  proposed matching an *open* one, but an open-only match would re-file work a maintainer
  deliberately closed on every subsequent run — the exact duplicate this feature exists to
  prevent. The time-scoped, state-agnostic match the breach-retry lookup already uses is
  carried over instead.
- The dedup decision and the attempt count are both computed in deterministic code. No
  agent is asked to judge whether a prior `spec-request` covers the same work
  (Constitution IX).
- The three known causes named in the issue — a missing `spec-request` label, a lost
  write permission, and an over-long title — are the causes the bound must survive. Only
  the last is fixable at source (FR-016); the other two are environmental and are what the
  give-up stall exists to report.
- Counting is per item and per routing decision, not repository-wide: two different issues
  each failing to file do not share a budget.

## Out of Scope

- Changing how triage or route reach their verdicts, or how the size-and-path backstop
  measures a change.
- Changing the semantics or value of the existing review round budget, which the new cap is
  separate from and does not touch.
- Bounding or deduplicating the loop's other artifacts — fix PRs, review-finding issues,
  watchdog reports — which have their own existing mechanisms.
- Making the label-bootstrap composite fail instead of warn when it cannot create a label;
  this feature bounds and reports the consequence rather than changing that composite's
  posture.
- Reconciling or closing duplicate `spec-request`s that already exist.

## Dependencies

- The create guard from #514 (a failed create fails the step before any comment, label or
  published URL), which this feature bounds rather than replaces.
- The breach-retry existence lookup from #530, which this feature generalises into the
  single home FR-018 requires.
- The `spec-request` body builder, whose canonical originating-issue reference line is what
  the existence check matches on.
- Spec 057's board loop: its selection order, its board item marker, its `board:stalled`
  convention, and FR-050's bounded-budget requirement.
- Spec 108 (routed-original disposition), whose route-time close of the originating issue
  every filing and reuse here must also perform, and spec 100 (stalled-item re-admission),
  which defers readiness's ordinary-entry duplicate to this feature.
- The repository gate that holds every `spec-request` filing site to the shared rules,
  which must be extended rather than duplicated.
