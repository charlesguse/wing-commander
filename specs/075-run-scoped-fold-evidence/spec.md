# Feature Specification: A Fold Report Credits Only Its Own Run — Run-Scoped Fold Evidence

**Feature Branch**: `spec-draft/075-run-scoped-fold-evidence`

**Created**: 2026-09-25

**Status**: Draft

**Input**: Lifecycle issue #565, routed from board-loop issue #416 —
"pr-conversation: the fold report calls every clean leg 'partly folded'
because it matches the bare job name, not the caller-prefixed one"

## Overview

Stage 9 (`pr-conversation.yml`) turns one PR review into one matrix leg per
classified item. A leg that folds a change into the spec writes a commit
whose subject names the leg — `fold(leg-N): <summary>` — and two jobs read
those commits afterwards:

- **`report-fold-outcomes`** cross-checks each fold-route leg's
  GitHub-set job conclusion against the presence of that leg's fold commit.
  Two signals, neither of which a dead leg has to publish itself, so a leg
  that died without folding says so even when it was cancelled mid-step.
- **`dispatch-once`** decides whether anything folded at all, dispatches at
  most one implement cycle for the whole review, and lists what folded in
  its PR comment.

Both read the same evidence the same way: `git log --grep '^fold(...)'`
over the range `BASE_SHA..TIP_SHA`, where `BASE_SHA` is the spec branch tip
that *this* run read just before its legs started folding and `TIP_SHA` is
the tip read afterwards.

That range is not actually scoped to this run. Leg ids restart at `leg-0`
in **every** stage-9 run, and nothing in a fold commit says which run made
it. When two stage-9 runs overlap on one PR — the ordinary case when a
review and a follow-up comment arrive minutes apart — each run's range
spans the other run's fold commits too, and `fold(leg-0):` from one run is
indistinguishable from `fold(leg-0):` of the other.

The consequence is a false negative in the half of the cross-check that
exists to catch a lost item: a leg that was cancelled before it folded
anything can be credited with a sibling run's commit under the same id, and
reported as folded — or reported as "partly folded" — rather than as **not
folded**. The one case the report exists for is the one case this can
silence.

This feature makes fold evidence attributable to the run that produced it,
so no stage-9 run can read another run's work as its own.

### What is already fixed, and what is not

Issue #416 reported two flaws in the same step. The **classification** flaw
— the report matched the jobs API's bare `act (leg-N)` name where the API
reports the caller-prefixed `pr-conversation / act (leg-N)`, so every
conclusion read `missing` and every clean leg was warned about — was fixed
in #417 (merged `a4b6995`), with Gate 34 fixtures carrying the prefixed
shape and a mutation that restores the bare equality failing the gate.

What stays open, and is what this feature specifies, is the **attribution**
flaw: the evidence half of the cross-check is scoped to a commit range, not
to a run.

### Observed conditions

From PR #414 (spec 056), 2026-09-20, the same two-run overlap recorded in
issue #415:

| time (UTC) | event |
|---|---|
| 05:26:57 | review run 35491701810 starts — nine legs, `leg-0` … `leg-8` |
| 05:28:59 | follow-up run 35491785316 starts — two legs, `leg-0` and `leg-1` |
| 05:35:02 → 05:36:25 | the review run's `leg-5` is cancelled while pending; its item never reaches `tasks.md` |
| 05:39:27 onward | both runs' fold commits are on the branch, with ids drawn from the same `leg-N` space |

Each run captured its own pre-fold tip minutes before the other run pushed,
so each run's `BASE_SHA..TIP_SHA` range contains the other's fold commits.
A `fold(leg-0):` commit was present in both ranges, made by exactly one of
them.

### Why it matters

Constitution III: the lifecycle of a spec must be legible from its issue
and its PR. The fold report is the only signal a maintainer gets that a
review round landed item-for-item. A report that can credit a leg with
another run's commit is a report whose "everything folded cleanly" cannot
be trusted — and an item silently dropped from a review is exactly the loss
the report was added to prevent.

Constitution VIII: the evidence half of the D6 cross-check is supposed to
be independently load-bearing. While one run can satisfy it with another
run's commit, it is not.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A lost item is still reported as lost when two runs overlap (Priority: P1)

Two stage-9 runs are in flight on one PR. A leg of the first run is
cancelled before it folds anything, while a leg of the second run — bearing
the same `leg-N` id — folds successfully. The first run's report names its
cancelled leg as **not folded**, because the only fold commit under that id
belongs to a different run and is not this run's evidence.

**Why this priority**: This is the reported defect and the failure mode
with a real cost — an item silently dropped from a review while the report
says the review folded cleanly. Every other story here is coverage for it.

**Independent Test**: Reproduce two overlapping runs (or their fixture
equivalent) where run A's `leg-0` is cancelled with no fold of its own and
run B's `leg-0` folds; confirm run A's report says `leg-0` was not folded.

**Acceptance Scenarios**:

1. **Given** run A's `leg-0` concluded `cancelled` and wrote no fold commit,
   **and** run B wrote a `fold(leg-0):` commit on the same branch inside
   run A's pre-fold-to-post-fold window, **When** run A reports, **Then**
   run A reports `leg-0` as **not folded**.
2. **Given** run A's `leg-0` concluded `success` and wrote its own fold
   commit, **and** run B also wrote a `fold(leg-0):` commit in the same
   window, **When** run A reports, **Then** run A treats `leg-0` as folded
   cleanly and says nothing about it — the coincidence of ids changes
   nothing for a leg that really did its work.
3. **Given** run A's `leg-0` concluded `success` but wrote no fold commit of
   its own, **When** run A reports, **Then** run A reports `leg-0` as
   **partly folded** even if another run's `fold(leg-0):` commit is present
   in the range.
4. **Given** no other run is in flight, **When** a run reports, **Then**
   every outcome it reports is identical to what it reports today — the
   single-run behaviour is unchanged.

---

### User Story 2 - The maintainer's fold list names this review's folds only (Priority: P2)

When a review's folds are announced on the PR — the "Folded in this review"
list, and the decision that there was something to dispatch an
implementation cycle for — the items named are the ones this review
actually folded, not whatever landed on the branch while it was running.

**Why this priority**: Same root cause, same reader, one step further down
the same comment thread. A dispatch notice listing another review's items
is the same legibility failure as a report crediting another run's commit,
and it is what a maintainer reads to decide whether their comment was
acted on.

**Independent Test**: With two overlapping runs' fold commits on one
branch, confirm each run's PR comment lists only the items it folded.

**Acceptance Scenarios**:

1. **Given** run A folded items X and Y and run B folded item Z in an
   overlapping window, **When** run A posts its fold list, **Then** the
   list names X and Y and does not name Z.
2. **Given** run A folded nothing at all (every leg was a reply, a question,
   or died) while run B folded item Z in the same window, **When** run A
   reaches its dispatch decision, **Then** run A does not treat Z as
   evidence that its own review folded something.
   [NEEDS CLARIFICATION: is the dispatch *decision* in scope, or only the
   *list* the comment shows? Making the decision run-scoped means a run
   that folded nothing dispatches nothing even when the branch moved —
   which removes a duplicate cycle but also removes the incidental
   re-dispatch that recovered PR #414's cancelled cycle.]

---

### User Story 3 - The rule has a fixture that fails when it is broken (Priority: P2)

The two-run case is covered by checked-in fixtures, so the next change to
fold attribution fails a gate at PR time rather than surfacing weeks later
as a quietly dropped review item.

**Why this priority**: Constitution VIII. The unscoped range shipped and
survived a fix to the step immediately beside it because no fixture ever
put two runs' commits in one range — the gate's fixtures are all
single-run, so the cross-run case could not fail anything.

**Independent Test**: Run the repository's PR-time gate suite against a
deliberately unscoped fold-evidence read and confirm a gate fails.

**Acceptance Scenarios**:

1. **Given** the fold-evidence rule and its fixtures, **When** the PR-time
   gate suite runs, **Then** a fixture places two runs' `fold(leg-0):`
   commits in one range and asserts the reporting run's exact outcome for
   each leg.
2. **Given** a change that reverts fold-evidence attribution to an
   unscoped range grep, **When** the gate suite runs, **Then** a gate
   fails.
3. **Given** a fixture file the gate expects is missing, **When** the gate
   runs, **Then** it fails loudly rather than reporting a pass it did not
   earn.

---

### Edge Cases

- **A fold commit carries no run attribution at all** — a commit made
  before this change, or one a human made by hand on the spec branch. It is
  not this run's evidence: the reporting run treats it as absent, which
  yields "not folded" or "partly folded" rather than silence. The
  conservative direction is deliberate — a false "not folded" costs a
  maintainer one look at the job list; a false "folded cleanly" costs a
  lost item.
- **A leg folds more than one commit.** Any one commit attributable to this
  run and this leg is sufficient evidence that the leg folded.
- **The spec branch is gone when the report runs** (merged and deleted, or
  force-deleted). No range exists, so no leg has evidence; the report says
  so rather than inferring anything.
- **The branch moved between the pre-fold read and the post-fold read for
  reasons unrelated to folding** — a rebase stage, a human push. Attribution
  is per-commit, so unrelated commits in the range are simply not fold
  evidence for any leg.
- **Three or more stage-9 runs overlap on one PR.** Nothing about the rule
  is specific to two; each run reads only its own.
- **A run is cancelled after its legs folded but before it reports.** No
  report is posted, exactly as today — this feature does not change which
  runs report, only what they may count as evidence.
- **Two legs in the SAME run carry the same id.** Ids are assigned from the
  classification index and are unique within a run; if that ever ceases to
  hold, the ambiguity is within one run and is out of this feature's reach.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A stage-9 run's fold-outcome report MUST count a
  `fold(<leg-id>):` commit as evidence for one of its own legs only when
  that commit is attributable to **this run**. A commit made by a different
  stage-9 run, under any leg id, MUST NOT satisfy the evidence half of the
  cross-check for this run.

- **FR-002**: The cross-check MUST keep both halves independently
  load-bearing: a leg is reported as folded cleanly only when its own
  GitHub-set job conclusion is `success` **and** this run's own fold
  evidence for that leg exists. Neither half alone may silence the report.

- **FR-003**: A fold-route leg with no fold evidence of this run's own MUST
  be reported as **not folded** when its job conclusion is anything other
  than `success`, and as **partly folded** when its job conclusion is
  `success`. These are the outcomes the report uses today; this feature
  changes what counts as evidence, not the vocabulary.

- **FR-004**: Fold evidence MUST be attributable to its producing run by a
  signal a deterministic step records, not by an instruction an agent is
  asked to follow when it writes its commit. Per Constitution IX, judgment
  that gates what the report says about a durable action belongs in
  deterministic code — an attribution the model can silently omit produces
  no error and no signal that the check was skipped, which is the same
  class of defect as the one being fixed.

- **FR-005**: The run-attribution signal MUST be readable by the reporting
  run without depending on any leg's own steps having completed — a
  cancelled leg publishes nothing, and reporting on a leg that published
  nothing is the report's entire purpose (FR-006a of spec 042).

- **FR-006**: Two stage-9 runs on the same PR MUST NOT be able to read each
  other's fold evidence as their own, by either of two means:
  [NEEDS CLARIFICATION: eliminate the overlap, or tolerate it? Option A —
  serialize the whole stage-9 run per PR, so two runs never overlap and no
  cross-run evidence can exist; this is issue #415's option 1 and it delays
  the second review by the first's full duration. Option B — allow runs to
  overlap and make each fold commit self-identifying as to its run; this is
  #415's "run id in the fold trailer" and leaves the #415 pending-job race
  untouched. Option C — both. The maintainer's triage of #416 on 2026-09-21
  recorded that this decision is #415's to make.]

- **FR-007**: A fold commit with no run attribution MUST be treated as not
  belonging to the reporting run. The report MUST NOT fall back to
  id-matching alone when attribution is absent.

- **FR-008**: The items a run names in its "folded in this review" list on
  the PR MUST be exactly the items that run folded, under the same
  attribution rule as FR-001. A maintainer reading the list MUST NOT see an
  item another review folded.

- **FR-009**: The fold-evidence rule MUST have exactly one home shared by
  every reader of fold evidence in this stage, with one canonical comment
  explaining it and every other site pointing at it, per this repository's
  single-home rule. Two copies of a range-and-grep are what let this defect
  ship twice in one file.

- **FR-010**: The two-run case MUST be covered by checked-in fixtures
  asserting the reporting run's exact outcome for at least: this run's leg
  succeeded with its own fold commit present and another run's commit under
  the same id also present (silent); this run's leg cancelled with no
  commit of its own and another run's commit under the same id present
  (**not folded**); this run's leg succeeded with no commit of its own
  (**partly folded**); a fold commit bearing no attribution at all (not
  this run's); and the single-run baseline (unchanged from today). The gate
  MUST fail loudly when a fixture is missing rather than skipping it
  (Constitution VIII).

- **FR-011**: A mutation that restores an unscoped `BASE_SHA..TIP_SHA` grep
  as the sole fold evidence MUST fail the PR-time gate suite.

- **FR-012**: Single-run behaviour MUST be unchanged. A stage-9 run with no
  concurrent sibling on its PR MUST produce the same report and the same
  fold list it produces today.

- **FR-013**: Fold commits made before this change carry no attribution and
  become invisible as evidence (FR-007). The change MUST NOT retroactively
  reinterpret them, and the transition MUST NOT make a run in flight during
  rollout report a false "folded cleanly".

### Key Entities

- **Fold commit**: the record a leg writes when it folds a classified item
  into the spec — subject `fold(<leg-id>): <summary>`. It is the
  git-history half of the D6 cross-check. This feature adds a run
  attribution to it or to what stands beside it; it does not change what a
  fold is or when one is written.
- **Leg id**: `leg-N`, assigned from the classification's original index
  within one run. Stable across the confirm-gating re-sort, unique within a
  run, **not** unique across runs — which is the ambiguity this feature
  resolves.
- **Pre-fold tip / post-fold tip**: the spec branch head read immediately
  before the leg matrix starts and again after it finishes. Together they
  bound the range fold evidence is read from today; under this feature they
  remain a bound but stop being the sole attribution.
- **Fold-route leg**: a leg whose category is `in-scope-change`, or
  `new-functionality` with fold-target `current-spec` — the only categories
  expected to write a fold commit, and the only ones the report judges.
  Unchanged by this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the two-run overlap of PR #414, replayed as a fixture, the
  run whose leg was cancelled without folding reports that leg as **not
  folded** — 100% of the time, with the sibling run's same-id commit
  present on the branch.
- **SC-002**: Zero stage-9 reports credit a leg with a commit another run
  made, measured across the fixture set of FR-010 and one live overlapping
  pair after merge.
- **SC-003**: Every branch named in FR-010 is covered by a checked-in
  fixture, and an unscoped-range mutation fails the PR-time gate suite.
- **SC-004**: A stage-9 run with no concurrent sibling produces byte-identical
  report and fold-list output to the pre-change behaviour, across the
  existing single-run fixtures.
- **SC-005**: A maintainer reading a review's fold list can tell, without
  opening the branch history or the Actions tab, which items that review
  folded — no item from another review appears in it.
- **SC-006**: After merge, one re-driven stage-9 run records its own
  attribution signal and its report reads it, proving the mechanism works
  in Actions and not only in fixtures (this repository's "prove it after
  merge" rule for Actions-only behaviour).

## Assumptions

- The classification fix from #417 (caller-prefixed job-name matching) is
  correct as shipped and is not revisited here; its Gate 34 fixtures and
  its bare-equality mutation stay as they are.
- Leg ids remain per-run and keep restarting at `leg-0`. Making them
  globally unique is one possible mechanism for FR-006 Option B, but the
  requirement is attribution, not id uniqueness — a unique id is an
  implementation of the former, not a separate goal.
- The report's existing outcome vocabulary ("not folded" / "partly folded"
  / silence) is right and is not extended. An unattributable commit
  collapses into the existing outcomes (FR-007) rather than earning a
  fourth category.
- Reporting a leg as **not folded** when it really did fold is an
  acceptable direction of error and the conservative one; reporting a leg
  as folded when it did not is the error this feature removes.
- Stage 9's leg matrix keeps `max-parallel: 1` and the per-spec concurrency
  group for `act`; whatever FR-006 resolves to, it layers onto that rather
  than replacing it.
- The spec branch's history is readable by the reporting job at the time it
  reports (it checks the branch out at its current tip today), so evidence
  can be read from history rather than needing to be carried in a separate
  artifact — though an artifact is a legitimate mechanism if the plan
  prefers it.

## Dependencies

- **Spec 042** (`specs/042-post-review-fold-loop`): research D1/D3/D6,
  `contracts/fold-dispatch-once.md`, `contracts/gate-coverage-042.md`, and
  data-model §4 define the cross-check, the "not folded" / "partly folded"
  vocabulary, and the fold-once/dispatch-once shape. This feature is a
  correction inside that feature's boundary.
- **Issue #415** (open, `board:stalled`): the two-run concurrency race that
  creates the overlap this defect exploits. FR-006's decision is the same
  decision #415 is waiting on; whichever way #415 is resolved determines
  whether this feature eliminates the overlap or survives it.
- **Issue #416 / PR #417**: the originating report and the already-merged
  classification half of the fix.
- **Gate 34** (`verify-fold-dispatch-once.py`) and its shell harness: the
  existing home for the fixtures FR-010 requires, extended rather than
  duplicated.
- `pr-conversation.yml`'s `classify-and-announce` (pre-fold tip), `act`
  (fold commits), `dispatch-once` (post-fold tip, dispatch, fold list) and
  `report-fold-outcomes` (the report) jobs.

## Out of Scope

- Fixing issue #415's pending-job cancellation race itself — the lost leg
  and the cancelled implement cycle. This feature makes the *report*
  truthful about what happened; it does not stop the thing it reports on,
  except insofar as FR-006 Option A would.
- Changing the job-conclusion half of the cross-check, including the
  caller-prefixed job-name matching from #417.
- Changing the categories the report judges, the outcome vocabulary, or the
  wording of the warning comment beyond what attribution requires.
- Changing when at most one implement cycle is dispatched per run, the
  iteration accounting, or the standalone (`implement-workflow` empty)
  path's behaviour.
- Retrofitting attribution onto fold commits already on existing spec
  branches.
- Posting a notice when a run's implement dispatch is cancelled by
  concurrency replacement (#415 option 4) — a separate signal with a
  separate owner.
