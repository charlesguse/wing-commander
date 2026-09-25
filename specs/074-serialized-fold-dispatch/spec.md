# Feature Specification: One Fold Queue Per PR — Concurrent Stage-9 Runs Stop Cancelling Each Other's Legs and Cycles

**Feature Branch**: `074-serialized-fold-dispatch`

**Created**: 2026-09-25

**Status**: Draft

**Input**: Lifecycle issue [#560](https://github.com/charlesguse/wing-commander/issues/560) — "pr-conversation: two stage-9 runs on one PR race the per-spec concurrency group, losing a fold leg and cancelling the dispatched implement cycle". Routed from the board loop as spec-shaped (originating issue [#415](https://github.com/charlesguse/wing-commander/issues/415)).

## Context

Stage 9 (`pr-conversation.yml`) turns a maintainer's review of an implementation
PR into work. `classify-and-announce` splits the review into numbered items and
announces them; `act` folds each fold-route item onto the spec branch as its own
matrix leg (`max-parallel: 1`); `report-fold-outcomes` reports which items did
and did not fold; `dispatch-once` dispatches one implement cycle for the whole
review if anything was folded.

Every job that mutates the spec branch shares one serialization queue per spec.
`act` and `dispatch-once` join the group named by
`classify-and-announce.outputs.concurrency-group`
(`.github/workflows/pr-conversation.yml:1520-1522`, `:2608-2610`), which is
`wing-commander-<spec-dir>` for an ordinary review and a per-PR stop group for a
`stop`-only run (`:1300-1321`). `implement.yml`'s `implement` and `stalled` jobs
join the same `wing-commander-<spec-dir>` group
(`.github/workflows/implement.yml:363-365`, `:2706-2708`). All of them set
`cancel-in-progress: false`.

`cancel-in-progress: false` protects a **running** job. It does not protect a
**pending** one: GitHub keeps at most one pending entry per concurrency group,
and queuing a newer job cancels the older pending one. The fold loop is built on
the assumption that legs queue one at a time — true for one run, false the
moment a second stage-9 run is in flight on the same PR.

### What was observed

PR #414 (spec 056), 2026-09-20, folding a request-changes review and a follow-up
comment posted three minutes apart:

| time (UTC) | event |
|---|---|
| 05:26:57 | review run [35491701810](https://github.com/charlesguse/wing-commander/actions/runs/35491701810) starts with nine legs (items 1–9) |
| 05:28:59 | follow-up run [35491785316](https://github.com/charlesguse/wing-commander/actions/runs/35491785316) starts with two legs (items 10–11) |
| 05:35:02 → 05:36:25 | review leg-5 (item 6) sits pending behind follow-up leg-0; when follow-up leg-1 queues, leg-5 is **cancelled**. Item 6 never reaches `tasks.md`. The review run's `report-fold-outcomes` does not mention it; the follow-up run's report says *its own* legs were "partly folded" |
| 05:39:27 → 05:39:45 | the follow-up run's `dispatch-once` fires and dispatches implement cycle 2 ([35492233832](https://github.com/charlesguse/wing-commander/actions/runs/35492233832)) although the review run still has legs 7 and 8 to fold |
| 05:39:47 → 05:40:41 | cycle 2's `implement` job waits behind review leg-7; when leg-8 queues, the **implement job is cancelled**. The run concludes `cancelled`, `stalled` is skipped, and no notice is posted anywhere |
| 05:41:47 | the review run's own `dispatch-once` dispatches a fresh cycle, which survives because nothing else queues |

Net: one fold lost silently, one implement cycle wasted, and two "dispatched"
notices on the lifecycle issue for one review round. The recovery was luck — the
review run happened to have its own dispatch left. Had the follow-up been the
last run, the cancelled cycle would have been the end of the road with no stall
notice.

### The three defects behind it

1. **Legs are replaceable while pending.** The shared per-spec group serializes
   across runs but does not queue across them; a second run's leg evicts the
   first run's pending leg.
2. **`dispatch-once` is once per run, not once per PR.** The second run has no
   way to see that the first still has legs, so it dispatches into a group that
   is still being used for folds — and the cycle it dispatches is itself a
   pending job that the next leg evicts.
3. **A concurrency-replaced cancel is invisible.** `implement.yml`'s `stalled`
   job is `!cancelled()`-gated (`.github/workflows/implement.yml:2684-2708`
   family), and a job cancelled while pending runs no steps at all, so the
   cancelled run cannot report itself. Nothing reaches the lifecycle issue.

## Clarifications

### Session 2026-09-25 — answered on [#560](https://github.com/charlesguse/wing-commander/issues/560)

- Q: For a set of overlapping stage-9 runs on one PR that collectively folded at
  least one item, does the pipeline dispatch exactly one implement cycle for the
  whole set, or one cycle per stage-9 run? → A: exactly one cycle for the whole
  overlapping set; the later runs' folds ride along in it and the earlier runs'
  dispatches yield. A follow-up comment posted mid-fold is absorbed into the
  first round's iteration rather than producing a second iteration number
  (FR-009).
- Q: After a lost cycle is detected and reported, does the pipeline re-dispatch
  it automatically or report only and leave the re-drive to a maintainer? → A:
  neither in full — report, then re-dispatch the lost cycle **at most once**. The
  bound keeps the dispatch path from looping while still recovering the single
  eviction observed on PR #414 (Principles IV and X) (FR-016).
- Q: Does a maintainer whose review starts a second stage-9 run get a prompt
  acknowledgment, or may the whole second run queue behind the first? → A: the
  acknowledgment stays prompt — classification and per-item announcements are
  not serialized against another run's folds. Queuing the whole run per PR is
  not eviction-free anyway: a concurrency group holds one pending entry, so a
  third review would cancel the pending second run (FR-017).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - No review item is lost when two reviews land on one PR (Priority: P1)

A maintainer posts a request-changes review on an implementation PR, then — two
or three minutes later, before the fold has finished — posts a follow-up comment
with two more points. Both are classified. Every fold-route item from both
rounds either lands on the spec branch or is named as not folded in a report the
maintainer can read. Nothing disappears.

**Why this priority**: a silently lost item is a review the maintainer believes
was addressed and was not. It is the only failure in this family that changes
the content of the delivered work rather than its timing, and it is invisible
without hand-reconstructing the run timeline. Constitution III — the lifecycle
must be legible from the issue and the PR — is violated the moment an item
leaves no trace.

**Independent Test**: drive two overlapping stage-9 runs on one PR (the second
starting while the first's legs are still queued) and confirm that the union of
the fold-outcome reports accounts for every classified fold-route item of both
runs, with no item missing from both.

**Acceptance Scenarios**:

1. **Given** a stage-9 run with nine fold-route legs is folding item 5, **When**
   a second stage-9 run on the same PR classifies two more items and queues its
   own legs, **Then** none of the first run's pending legs is cancelled, and all
   eleven items reach a terminal outcome.
2. **Given** two overlapping stage-9 runs on one PR, **When** a leg of the first
   run does end without folding for any reason, **Then** the report that names
   it as not folded belongs to the run that owns the item, and no run reports
   another run's items as its own.
3. **Given** two stage-9 runs in flight on one PR and a third arriving while
   both still have legs, **When** the third run's legs queue, **Then** no
   pending leg of either earlier run is cancelled.
4. **Given** two stage-9 runs in flight for **different** specs, **When** both
   fold concurrently, **Then** they run in parallel exactly as today — this
   feature adds no cross-spec serialization.
5. **Given** a stage-9 run is mid-fold on a PR, **When** a maintainer's
   follow-up comment starts a second run on that PR, **Then** the second run's
   classification and per-item announcements are posted without waiting for the
   first run's legs — only its branch-mutating work queues.

---

### User Story 2 - The dispatched implement cycle actually starts (Priority: P2)

After the folds of every stage-9 run in flight on an implementation PR have
finished, exactly one implement cycle is dispatched for the whole overlapping
set, and the run named in the "Implementation cycle N dispatched" reply is a run
that actually starts and does the work. A follow-up comment that lands mid-fold
rides along in that one cycle rather than earning its own iteration number. A
cycle is never dispatched into a queue that is still being used for folds.

**Why this priority**: a cancelled cycle costs a wasted dispatch and, when it is
the last dispatch of the round, stops the lifecycle dead. It is recoverable by
hand once seen, which is why it ranks below the silent data loss of US1, but it
is what makes the failure terminal rather than merely untidy.

**Independent Test**: drive two overlapping stage-9 runs that both fold at least
one item, and confirm that exactly one implement run is dispatched for the pair,
that it reaches a non-`cancelled` conclusion, and that the lifecycle issue shows
one dispatch outcome for the overlapping set rather than one per stage-9 run.

**Acceptance Scenarios**:

1. **Given** stage-9 run A still has pending fold legs, **When** stage-9 run B
   on the same PR finishes its own legs, **Then** no implement cycle is
   dispatched until every fold leg of every in-flight stage-9 run on that PR has
   reached a terminal state.
2. **Given** an implement cycle has been dispatched for a review round, **When**
   any further job of a stage-9 run on the same PR queues, **Then** the
   dispatched implement run is not cancelled by that queuing.
3. **Given** a review round in which no leg folded anything, **When** every leg
   has finished, **Then** no implement cycle is dispatched, and the PR reply
   says so (today's no-op behaviour is unchanged).
4. **Given** a `stop`-classified run overlapping a fold run on the same PR,
   **When** the stop run's jobs queue, **Then** they join the per-PR stop group
   as today and cannot evict any pending job in the per-spec group.
5. **Given** two overlapping stage-9 runs on one PR that each folded at least
   one item, **When** the last fold leg of the set reaches a terminal state,
   **Then** exactly one implement cycle is dispatched for the pair, carrying one
   iteration number, and its reply names the folds of both runs.

---

### User Story 3 - A lost cycle is visible on the lifecycle issue (Priority: P3)

When an implement run is cancelled because a concurrency group replaced it while
it was pending, a one-line notice appears on the lifecycle issue naming the
spec, the iteration, the cancelled run, and what replaced it, and the cycle is
re-dispatched once. A maintainer reading the issue alone can tell that a cycle
was lost, why, and whether the pipeline recovered it — without opening the
Actions tab.

**Why this priority**: this is the safety net rather than the fix. Once US1 and
US2 hold, a replacement cancel should not happen — but the class of bug is
exactly the class that hides, so the notice is what makes the next instance
findable in minutes instead of by hand-reconstructing a timeline. It is
independently valuable and independently shippable.

**Independent Test**: force an implement run to be cancelled while pending in
its group and confirm a notice naming it appears on the lifecycle issue and that
the cycle is re-dispatched exactly once; force the replacement to happen again
and confirm the second loss is reported with no third dispatch; confirm a
maintainer's own manual cancel of an implement run still produces no notice and
no re-dispatch.

**Acceptance Scenarios**:

1. **Given** a dispatched implement run is cancelled while pending in a
   concurrency group, **When** the cancellation is detected, **Then** a notice
   is posted to the lifecycle issue naming the spec, the iteration, the
   cancelled run URL, and the fact that a concurrency group replaced it.
2. **Given** a maintainer cancels an implement run by hand, **When** the run
   concludes `cancelled`, **Then** no notice is posted — today's deliberate
   silence for a human cancel is preserved.
3. **Given** an implement run that was cancelled while pending, **When** a
   maintainer reads the lifecycle issue, **Then** the "dispatched" notice for
   that cycle and the "lost" notice for the same cycle can be matched to each
   other by run URL or iteration number.
4. **Given** a lost cycle has been reported, **When** the pipeline recovers it,
   **Then** the cycle is re-dispatched exactly once and the re-dispatch is named
   on the lifecycle issue next to the lost-cycle notice.
5. **Given** a cycle that has already been re-dispatched once, **When** the
   re-dispatched run is itself replaced while pending, **Then** the second loss
   is reported, no further cycle is dispatched automatically, and the notice
   says a maintainer's re-drive is the remaining step.
6. **Given** a maintainer cancels an implement run by hand, **When** the run
   concludes `cancelled`, **Then** nothing is re-dispatched.

---

### Edge Cases

- **Three or more overlapping stage-9 runs on one PR.** Whatever holds for two
  must hold for N; the fix must not be a two-run special case.
- **The second run arrives after the first has already dispatched.** The first
  run's cycle may already be running; the second run's legs must queue behind it
  without either side being cancelled, and without the fold loop deadlocking
  against a long-running implement job. The one-cycle collapse of FR-009 covers
  only the runs still folding when the dispatch decision is taken — a run that
  arrives after the dispatch has fired owns its own cycle and its own iteration
  number.
- **A run whose legs all fail, hold, or reply-only.** No fold commits exist, so
  no cycle is dispatched — unchanged.
- **Attribution of fold commits across runs.** `dispatch-once` decides whether
  anything folded by comparing the spec branch tip against the pre-fold tip
  captured by its own run, and lists `fold(<id>):` commits from that range
  (`.github/workflows/pr-conversation.yml:2657-2702`). With two runs folding
  into one branch, that range can contain the *other* run's commits, so a
  round's "Folded in this review" list can name items the run did not fold.
- **A human cancel of a stage-9 run mid-fold.** The remaining legs are gone by
  the maintainer's choice; the outcome report must still distinguish this from a
  concurrency eviction.
- **The `stop` carve-out.** A `stop`-only run deliberately does *not* join the
  per-spec group, precisely so it cannot evict a pending job there (spec 042
  FR-024/SC-009). Any new grouping must keep that carve-out intact.
- **An adopter who runs stage 9 without an implement workflow configured**
  (`implement-workflow` empty, standalone mode). The fold still has to be
  serialized correctly even though nothing is dispatched.

## Requirements *(mandatory)*

### Functional Requirements

#### Not losing work

- **FR-001**: When two or more stage-9 runs are in flight on the same
  implementation PR, every fold-route item classified by any of them MUST reach
  a recorded terminal outcome — folded onto the spec branch, or named as not
  folded in a report a maintainer can read.
- **FR-002**: A pending fold leg MUST NOT be cancelled by the queuing of a job
  belonging to a different stage-9 run on the same PR.
- **FR-003**: The existing per-spec serialization guarantee MUST be preserved:
  no two jobs that mutate one spec's branch (a fold leg, an implement cycle) may
  run at the same time.
- **FR-004**: Stages of *different* specs MUST continue to run in parallel; the
  fix MUST NOT introduce any repository-wide or cross-spec serialization
  (Operational Constraints, "Concurrent specs are supported").
- **FR-005**: The `stop`-classification carve-out MUST be preserved: a
  `stop`-only run's branch-touching jobs continue to join a per-PR stop group
  and MUST NOT be able to evict a pending job in the per-spec group.
- **FR-006**: A run's fold-outcome report MUST account for exactly the
  fold-route items that run classified — never another run's items — and MUST
  name any of its own items that ended without folding, including one whose leg
  never started.

#### Not wasting or losing a cycle

- **FR-007**: No implement cycle may be dispatched for a PR while any fold leg
  of any in-flight stage-9 run on that PR is still pending or running.
- **FR-008**: A dispatched implement run MUST NOT be cancelled by the later
  queuing of any job belonging to a stage-9 run on the same PR.
- **FR-009**: For a set of overlapping stage-9 runs on one PR that collectively
  folded at least one item, the pipeline MUST dispatch exactly one implement
  cycle for the whole set. The later runs' folds ride along in that one cycle
  and the earlier runs' dispatches yield to it, so a maintainer's follow-up
  comment posted mid-fold is absorbed into the round already in flight rather
  than producing a second iteration number.
- **FR-010**: The "Implementation cycle N dispatched" reply MUST name a run that
  goes on to start. When the named run does not start, the discrepancy MUST be
  reported rather than left standing as the last word on the round.
- **FR-011**: Because one dispatch now covers a whole overlapping set (FR-009),
  the `folded` list that dispatch reply publishes MUST name exactly the items
  the set folded — every one of them, and no item no run in the set folded —
  so the list and the per-run per-item reports (FR-006) cannot disagree.

#### Making a lost cycle visible

- **FR-012**: An implement run that concludes `cancelled` because a concurrency
  group replaced it while pending MUST produce a notice on the lifecycle issue
  naming the spec, the iteration, the cancelled run URL, and the cause.
- **FR-013**: That notice MUST distinguish a concurrency-replacement cancel from
  a maintainer's manual cancel; a manual cancel MUST remain silent, as today.
- **FR-014**: Because a job replaced while pending executes no steps, the notice
  MUST be produced by an observer other than the cancelled run itself.
- **FR-015**: The decision that a given cancelled run was replaced (rather than
  cancelled by a human) MUST be made by deterministic code reading run state,
  never by an agent's judgment (Principle IX).
- **FR-016**: After a lost cycle is detected and reported, the pipeline MUST
  re-dispatch that cycle automatically **at most once**. The re-dispatch MUST be
  named on the lifecycle issue alongside the lost-cycle notice, and the
  at-most-once bound MUST be enforced by deterministic code, so no chain of
  replacements can drive an unbounded dispatch loop (Principles IV and X).
- **FR-016a**: If the re-dispatched cycle is itself lost to a concurrency
  replacement, the pipeline MUST report that second loss and stop — no further
  automatic re-dispatch — and the notice MUST say that a maintainer's re-drive
  is the remaining step.

#### Latency and interaction shape

- **FR-017**: A maintainer whose review or comment starts a second stage-9 run
  on a PR MUST receive a prompt acknowledgment of their round: classification
  and the per-item announcements MUST be posted without waiting for any other
  run's fold legs. Only the branch-mutating work is serialized.
- **FR-017a**: The serialization MUST NOT be achieved by queuing whole stage-9
  runs in one per-PR group. Because a concurrency group holds at most one
  pending entry, a third review would evict the pending second run — the same
  defect in a new place. The mechanism chosen MUST hold every in-flight run's
  branch-touching work without relying on more than one pending entry per
  group.
- **FR-018**: Whatever the serialization shape, the pipeline MUST NOT deadlock:
  no job may wait on a queue slot held by a run that is itself waiting on that
  job.

#### Contract and evidence

- **FR-019**: The published `workflow_call` contract of the affected stages MUST
  NOT change: no input, secret, or output may be removed or renamed, and no new
  required input may be added. Any new input MUST be optional with a default
  that preserves today's behaviour (Principle VII).
- **FR-020**: Every workflow comment that explains the current grouping —
  including the block at `.github/workflows/pr-conversation.yml:2600-2607` that
  states why `dispatch-once` follows `act`'s group — MUST be updated to describe
  the shipped behaviour, with one canonical statement of the rule and pointers
  from the other call sites rather than a pasted copy.
- **FR-021**: Each failure branch this feature ships MUST be exercised by a
  checked-in fixture, and the gate that checks the grouping MUST evaluate the
  real expressions from both `pr-conversation.yml` and `implement.yml` rather
  than a restatement of them (Principle VIII; Gate 70's style).
- **FR-022**: The gate MUST fail against the pre-fix expressions — a fixture
  that passes on both the old and the new shape is not coverage.
- **FR-023**: Because the behaviour only runs in GitHub Actions, the fix MUST be
  proven after merge by re-driving a real two-run scenario, with the evidence
  recorded on the PR or the lifecycle issue.

### Key Entities

- **Stage-9 run**: one `pr-conversation` workflow run, scoped to one PR, holding
  a classification of one review round into numbered items and one leg per item.
- **Fold leg**: one matrix job of a stage-9 run, folding one fold-route item
  onto the spec branch and producing a `fold(<id>): <summary>` commit.
- **Per-spec serialization group**: the queue (`wing-commander-<spec-dir>`)
  shared by every job that mutates one spec's branch — fold legs, `dispatch-once`,
  and `implement.yml`'s own jobs. Holds at most one running and one pending
  entry; the pending entry is replaceable.
- **Per-PR conversation group**: the queue
  (`wing-commander-pr-conversation-pr-<n>`) that `classify-and-announce` and
  `stalled` already join, and the per-PR stop group a `stop`-only run uses.
- **Implement cycle**: one dispatched `implement` run for a spec, carrying an
  iteration number derived from `spec-meta.json`.
- **Lost-cycle notice**: the lifecycle-issue record that a dispatched cycle was
  cancelled before it started, and why.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the reproduced two-run scenario (9 items then 2 items), 11 of
  11 fold-route items reach a recorded terminal outcome. Zero items are absent
  from every report.
- **SC-002**: Across the fixture-covered overlapping-run scenarios, zero
  implement runs conclude `cancelled` as a result of pending replacement.
- **SC-003**: For a set of overlapping stage-9 runs on one PR, the lifecycle
  issue carries exactly one dispatch outcome — one "dispatched" notice whose run
  started, or one explicitly-reported reason no cycle was dispatched — never one
  notice per stage-9 run. In the reproduced two-run scenario this is one
  "dispatched" notice where today there are two.
- **SC-004**: 100% of implement runs cancelled by concurrency replacement
  produce a lifecycle-issue notice; 0% of maintainer-cancelled runs do.
- **SC-004a**: A cycle lost to concurrency replacement is automatically
  re-dispatched at most once — never twice for the same cycle, and never for a
  maintainer's manual cancel — so a chain of replacements can add at most one
  run to the round.
- **SC-005**: A maintainer can determine, from the lifecycle issue and the PR
  alone, how many cycles a review round dispatched, whether any was lost, and
  whether a lost one was recovered by the single re-dispatch or still needs a
  hand re-drive — without opening the Actions tab (Principle III).
- **SC-006**: Two specs' stage runs still overlap in wall-clock time in a
  two-spec scenario; no measurable increase in end-to-end time for a single-run
  review round.
- **SC-007**: The grouping gate fails when run against the pre-fix expressions
  of both workflow files and passes against the shipped ones, demonstrated by a
  checked-in fixture for each failure branch (Principle VIII).
- **SC-008**: One post-merge re-driven run reproduces the two-run scenario and
  loses neither a fold nor a cycle, with the run URLs recorded on the PR or the
  lifecycle issue.

## Assumptions

- GitHub Actions keeps at most one pending job per concurrency group and cancels
  the older pending entry when a newer one queues; `cancel-in-progress: false`
  protects a running job only. This is the mechanism observed on PR #414 on
  2026-09-20 and is treated as platform behaviour that cannot be configured
  away.
- A job cancelled while pending executes none of its steps, so it can neither
  report nor clean up after itself.
- Fold legs already run `max-parallel: 1` within one run; the problem is between
  runs, not within one.
- The lifecycle issue is the canonical home for a lifecycle notice
  (Principle III), and the PR is the home for per-item review replies.
- The change is stage-side and wrapper-side only; no adopter re-pins anything
  and no published input changes (Principle VII).
- A maintainer's manual cancel remains a deliberate silence — this feature does
  not make every cancelled run chatty.
- The four options sketched on the originating issue (serialize the whole run
  per PR; make dispatch PR-wide; re-group the implement job so legs wait on it;
  report the cancellation independently) are input to planning, not a decision
  taken here — with one exception now settled: FR-017a rules out serializing
  whole stage-9 runs in a single per-PR group, because that group's one pending
  slot reproduces the eviction. The three scope-level choices are answered in
  Clarifications: one cycle per overlapping set (FR-009), report plus a single
  automatic re-dispatch (FR-016), and a prompt acknowledgment for every round
  (FR-017).

## Out of Scope

- Issue #397 — `cleanup`'s `mark-stalled` pushing outside the per-spec group. It
  is the same family and a different job; it stays its own issue.
- Reducing the total wall-clock time of the fold loop, or parallelising folds
  within one run.
- Any change to how a review is classified into items, or to which route an item
  takes.
- Concurrency-group behaviour of stages other than `pr-conversation` and
  `implement`.
