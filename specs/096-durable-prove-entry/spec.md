# Feature Specification: A Merged Fix Reaches Prove — The Prove Entry Survives a Displaced Queue Slot

**Feature Branch**: `spec-draft/096-durable-prove-entry`

**Created**: 2026-09-29

**Status**: Draft

**Input**: Lifecycle issue #723 — "board-loop: a queued prove run
(pull_request: closed) can be displaced by the next scheduled run, so a
merge is never proven" (routed from board-loop.yml, reason
`no_usable_proposal`; originating issue #537, itself found by the code
review of the #532 fix on branch `fix/532-board-awaiting-merge`)

## Overview

`board-loop.yml` declares one workflow-level concurrency group —
`wing-commander-board-loop`, `cancel-in-progress: false` (lines 57–63,
spec 057 FR-048) — and that one group is shared by all three of its
triggers: the hourly schedule (`cron: "13 * * * *"`, line 35),
`workflow_dispatch`, and `pull_request: types: [closed]` (line 51). GitHub
keeps at most **one pending** run per concurrency group. `cancel-in-progress:
false` protects the run that is already *in progress*; it does not protect
the run that is *pending*. A newly queued run takes the pending slot and the
run that was holding it is cancelled before it ever starts.

The `pull_request: closed` trigger is the only path into the prove step
(`prove-gate`, line 3633: `if: github.event_name == 'pull_request' && …`;
`prove`, line 3789: `needs: prove-gate`). So the loop's proof of a merge
rides in the one kind of run that a routine hourly tick can silently
evict:

1. A scheduled board run is in progress. An agent-bearing item (triage →
   route → fix → review) can hold that slot for tens of minutes.
2. A maintainer merges the loop's fix PR. The `pull_request: closed` run
   queues as pending.
3. The next schedule tick — or another PR close — queues and takes the
   pending slot. The prove run is cancelled before `prove-gate` runs.
4. Nothing has run, so nothing is recorded. The merge is not proven, and
   the issue carries no statement that it was not proven.

What happens next is worse than silence. The issue's newest marker is
`awaiting-merge` with a now-MERGED PR. `_awaiting_merge_holds()`
(`board_eligibility.py:226`) holds an item only while its PR is *not*
positively CLOSED or MERGED, so a MERGED PR re-admits the issue to
ordinary selection. The resume step then resolves that marker through the
"resolved by number but not OPEN" clause and records `stale marker --
recorded pr N is MERGED, not open` (`board-loop.yml:677`), clearing PR,
branch, round and base SHA and sending the item to a **fresh triage**. The
loop spends an item slot and an agent invocation re-triaging a defect it
has already fixed and merged. Triage has no deterministic ground to close
it either: "already fixed on `main`" is an `already_fixed_proposal`
(`board_triage.py:428`) that is *posted for a maintainer*, never acted on.
If triage instead reads "proceed", route and fix are free to cut a second
branch and open a second PR for an issue whose fix is already on `main`.

This is not a regression from #532. The same displacement existed when
readiness used a readiness marker instead of the `awaiting-merge` step;
#532 changed which marker is stranded, not whether it can be.

### The FR-048 rationale, checked

Issue #537 asks for this check before choosing a fix, so here it is.
FR-048's guarantee is "one board item in flight repository-wide, with a
second run queuing rather than cancelling or racing". The Constitution
states its reason directly (Principle X): *"The loop works one item at a
time under a global concurrency group, because pipeline runs and the
maintainers' own sessions share one usage window."* The bound is on
**agent** concurrency.

`prove-gate` and `prove` invoke no agent. Both jobs say so in their own
metrics comments (`board-loop.yml:3754`, `board-loop.yml:3965`): the
re-drive decision is `board_prove.py`'s, the dispatch and wait are
`wing-commander-dispatch-and-wait`'s, and the issue comment and close are
`gh`'s. Nothing on the `pull_request: closed` path spends the usage window
FR-048 exists to protect. The prove path also takes no board item: it is
directed at the one issue named by the merged PR's body, and `select` — the
job that picks an item — is explicitly excluded from this trigger
(`if: github.event_name != 'pull_request'`, line 106).

So FR-048's *rationale* does not reach the prove path, even though
FR-048's *wording* currently covers it. Whether the wording should be
narrowed, or the same outcome reached from the scheduled side instead, is
the design question this spec leaves open (see Clarifications).

### Spec 060 already owns part of this

`specs/060-self-redrive-concurrency` is **in flight and unimplemented**
(`spec-meta.json`: `"stage": "spec"`, `"iteration": 0`, `"spec_branch":
null`), and its FR-010b describes this exact displacement:

> The `pull_request: closed` run that hosts the prove step can itself be
> cancelled from the item group's pending slot before it starts: the hourly
> schedule tick or another PR's close event takes the slot. In that case no
> prove step exists to record anything. Such a merge MUST NOT leave its
> issue open with no record. Deterministic code MUST detect a merged board
> fix PR whose issue carries neither a proof record nor a prove-step
> marker, and record that on the issue as a displaced prove run.

Spec 060 FR-010b stops at **recording** the displacement and leaving the
issue open. Issue #723 asks for something strictly larger: that the merge
actually *reaches* prove, so the proof evidence FR-043 requires exists
rather than a note explaining why it does not. Spec 060 also plans to
restate the simultaneity guarantee in "every concurrency block's own
comment" (FR-016) and to check that the one permitted overlap is safe
(FR-017) — the same lines of `board-loop.yml` any concurrency change here
would touch.

This spec is therefore written as the **delta beyond FR-010b**: recovery
rather than reporting. Whether that delta ships here, ships inside spec
060, or is declined in favour of FR-010b's record-only behaviour is the
first open question, and it is the owner's to answer.

### A rule with no gate behind it

The concurrency block's comment ends: *"Never loosen this without
re-establishing that guarantee some other way."* No gate enforces it. No
script under `.github/scripts/` mentions `wing-commander-board-loop` or
reads `board-loop.yml`'s `cancel-in-progress`. Whatever arrangement this
feature lands on, the arrangement itself — not the prose describing it —
has to be the thing a gate reads, the way
`verify-spec-branch-push-concurrency.py` already reads the spec-branch push
group. Per CLAUDE.md: a rule with no gate behind it lasts until the next
session.

## Clarifications

### Open — posted to lifecycle issue #723

Three questions are open; each is recorded as a `[NEEDS CLARIFICATION]`
marker on the requirement it blocks (FR-001, FR-004, FR-011). They are
ordered by scope impact: Q1 decides whether the feature ships at all, Q2
decides its mechanism, Q3 decides its breadth.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A merge the loop made is proven, not re-triaged (Priority: P1)

A maintainer merges a board fix PR while a scheduled board run is in
progress. The hourly tick takes the pending slot and the `pull_request:
closed` run never starts. On the next scheduled run the maintainer expects
to see the loop *prove* that merge — re-drive the affected behaviour, post
the run URL and conclusion, close the issue on that evidence — not to see a
fresh triage comment on an issue whose fix is already on `main`.

**Why this priority**: this is the whole of issue #723. Every other story
here is a consequence of it. Without it the loop's proof step is
conditional on nothing having ticked in a window a maintainer cannot see
and cannot control, and the Constitution's "A fix to behaviour that only
runs in Actions is proven after merge by re-driving one run" is satisfied
only by luck.

**Independent Test**: drive one board item to a merged fix PR with the
`pull_request: closed` run's pending slot taken by a second queued run,
then let the recovery path run. The issue receives the proof outcome
(closed on a successful re-drive, or left open carrying the failing run
URL), and never a fresh triage comment.

**Acceptance Scenarios**:

1. **Given** an issue whose `awaiting-merge` marker names a PR that is now
   MERGED, and whose issue carries no proof record and no prove-step
   marker, **When** the recovery path runs, **Then** the item is taken to
   the prove step — the same actions-only decision, re-drive and recording
   the `pull_request: closed` path performs — and not to triage.
2. **Given** the same issue, **When** the recovery path runs, **Then** the
   displacement itself is stated on the issue, distinctly from every other
   no-proof reason, before any durable action is taken.
3. **Given** a recovered prove that concludes `success`, **When** the
   outcome is recorded, **Then** the issue closes citing the re-driven run
   URL and its conclusion, exactly as the undisplaced path does.
4. **Given** a recovered prove whose re-drive concludes `failure` or
   `timeout`, or whose dispatch could not be correlated, **When** the
   outcome is recorded, **Then** the issue stays open carrying that
   evidence, and the item is not re-triaged on a later run either.
5. **Given** a `pull_request: closed` run that was **not** displaced,
   **When** it runs, **Then** its behaviour is byte-for-byte the behaviour
   it has today and the recovery path never duplicates its work.

---

### User Story 2 - A merged fix is never re-triaged as if it were unfixed (Priority: P1)

The loop must not spend an item slot, an agent invocation, and possibly a
second branch and PR on an issue whose fix it merged. Today's re-admission
of a MERGED `awaiting-merge` marker to a fresh triage is the concrete
harm; whether the item is then proven (Story 1) or merely held, it must
stop being re-triaged.

**Why this priority**: this is the part of #723 that costs money and can
produce a duplicate PR, and it holds whichever mechanism Q2 selects. It is
also the part that must not regress #532's own fix: an `awaiting-merge`
item whose PR is still OPEN must keep being passed over, and an
`awaiting-merge` item whose PR was closed *without* merging must keep
falling to a fresh triage.

**Independent Test**: with an issue carrying an `awaiting-merge` marker
whose PR resolves MERGED, run selection and resume against live-shaped
state. The item is not resolved to `triage`, and the three neighbouring
states (PR OPEN, PR CLOSED-unmerged, PR state unresolvable) each behave as
they do today.

**Acceptance Scenarios**:

1. **Given** an `awaiting-merge` marker whose PR is MERGED and whose issue
   is open with no proof record, **When** the step is resolved, **Then** it
   is not `triage`, and no branch, round or base SHA from the merged
   attempt leaks into whatever step it is.
2. **Given** an `awaiting-merge` marker whose PR is still OPEN, **When**
   selection runs, **Then** the item is passed over exactly as #532's fix
   requires.
3. **Given** an `awaiting-merge` marker whose PR was CLOSED without
   merging, **When** the step is resolved, **Then** it falls to a fresh
   triage, unchanged.
4. **Given** an `awaiting-merge` marker whose PR state cannot be resolved
   (the lookup 404ed or the `pr` field is malformed), **When** selection
   runs, **Then** the item is skipped rather than re-admitted — the
   fail-safe `_awaiting_merge_holds()` already documents.
5. **Given** an issue whose proof already succeeded (a `proven` marker),
   **When** selection runs, **Then** it is terminal and untouched.

---

### User Story 3 - The concurrency arrangement is what a gate reads (Priority: P2)

A maintainer changing `board-loop.yml`'s triggers or concurrency six
months from now should be stopped by a failing gate, not by noticing a
comment. Whatever arrangement this feature lands on — one group, two
groups, a keyed group — the arrangement is asserted against the real
workflow file, and the comment that describes it is checked against the
behaviour that actually holds.

**Why this priority**: Principle VIII, and CLAUDE.md's "a rule with no
gate behind it lasts until the next session". The existing "never loosen
this" comment is exactly the kind of rule that has already been loosened
once by accident — the prove path acquired a trigger that shares the group
without anything noticing what that implied.

**Independent Test**: run the new gate against the real tree (it passes)
and against fixtures that move the prove path back under the displaceable
arrangement and that drift the comment from the behaviour (each fails,
naming the file and the property).

**Acceptance Scenarios**:

1. **Given** the shipped `board-loop.yml`, **When** the gate runs from the
   repository root, **Then** it passes, having resolved the real file
   rather than a fixture.
2. **Given** a tree whose prove path can again be displaced from the
   pending slot, **When** the gate runs, **Then** it fails naming the
   property that no longer holds.
3. **Given** a tree whose concurrency comment describes an arrangement the
   file no longer has, **When** the gate runs, **Then** it fails.
4. **Given** the gate registry, **When** the gate suite runs locally and in
   CI, **Then** the gate runs in both with the same subject and arguments.

---

### User Story 4 - The recovery is legible and costed on the issue (Priority: P3)

A maintainer reading the lifecycle issue can tell, without leaving it,
that the proof was displaced, that the loop recovered it, and what the
recovery cost.

**Why this priority**: Constitution III and spec 057 FR-044/FR-047. The
behaviour is correct without it; the loop is only *auditable* with it.

**Independent Test**: after a recovered prove, the issue carries the
displacement statement, the proof outcome, and the run's cost line, and
the run emits a durable metrics record under a label naming the condition.

**Acceptance Scenarios**:

1. **Given** a recovered prove, **When** the run finishes, **Then** it
   emits a cost line and a durable metrics record whose run label names
   the recovery, distinguishable from an ordinary prove run.
2. **Given** a recovered prove, **When** its outcome is recorded, **Then**
   the issue comment says the proof was displaced and recovered, not
   merely what the proof concluded.

---

### Edge Cases

- **The merged PR is not the loop's own.** A human PR whose body says
  `Fixes #N` for an issue carrying a board marker must not drive a
  recovered prove any more than it drives the live one: the same
  `board:owned` + head-in-this-repository ownership test applies
  (`BOARD_PR_OWNED_JQ`).
- **Two merges displaced in the same window.** Two board issues could each
  have a merged, unproven PR when the recovery path next runs. One of them
  is recovered per run at most; the other must remain recoverable rather
  than falling through to triage.
- **The issue was closed by a human during the window.** A closed issue is
  not selected. The merge is then unproven and unrecorded forever; this
  must be an accepted, stated outcome rather than an unnoticed one.
- **The displaced run's own event payload is gone.** The live prove path
  reads the PR body, `merged`, labels and changed paths off
  `github.event.pull_request`. A recovery running off the schedule has no
  such payload and must re-derive every one of those facts from the API,
  including the changed-path list `board_prove.py`'s actions-only decision
  needs.
- **The re-drive target is `board-loop.yml` itself.** `board_prove.py`'s
  first re-drive case dispatches board-loop, which queues behind the very
  run waiting on it. That interaction is spec 060's FR-001/FR-002 subject,
  not this spec's, but a recovery path that runs inside a scheduled board
  run inherits it and must not make it worse.
- **A `prove` marker from a failed earlier attempt.** Such a marker is
  skipped by both `in_flight_candidate()` and `select()`'s fallback, and
  the `pull_request: closed` event cannot recur for an already-merged PR —
  so the item is unreachable until a maintainer acts. Whether recovery
  covers it is Q3.
- **The kill switch is set, or a maintainer requested a stop.** The
  recovery path takes durable actions (a comment, a dispatch, a close) and
  must re-check both immediately before the first of them, as the live
  prove job does.

## Requirements *(mandatory)*

### Functional Requirements — scope and mechanism

- **FR-001**: The feature MUST establish that a merged board fix PR reaches
  the prove step even when the `pull_request: closed` run that would have
  hosted it was cancelled from the concurrency group's pending slot before
  starting. [NEEDS CLARIFICATION: spec 060 FR-010b already requires
  deterministic *detection and recording* of this displacement, and spec 060
  is in flight and unimplemented. Does #723 want (a) FR-010b's record-only
  behaviour, in which case this feature is already covered and should be
  declined; (b) actual recovery so the merge is proven, specified here and
  sequenced after spec 060; or (c) actual recovery folded into spec 060
  itself as an amendment to that in-flight spec?]
- **FR-002**: The recovered path MUST produce the same outcomes as the
  undisplaced path, decision for decision: the actions-only decision, the
  re-drive target, the wait, the close-on-success, the leave-open on
  failure/timeout/uncorrelated dispatch. It MUST NOT be a second, parallel
  implementation of any of them — the existing prove logic is the one home
  (CLAUDE.md "shared logic has exactly one home").
- **FR-003**: The undisplaced `pull_request: closed` path's behaviour MUST
  be unchanged, and the recovery MUST NOT duplicate a proof that path has
  already performed or is performing.
- **FR-004**: The mechanism MUST be one of the two shapes issue #537 names,
  chosen against the FR-048 rationale rather than by preference.
  [NEEDS CLARIFICATION: (A) give the `pull_request: closed` path its own
  concurrency group, keyed per issue, so it cannot be displaced by a
  scheduled run — FR-048's rationale is agent concurrency and the prove path
  runs no agent; or (B) have the scheduled path detect a merged-but-unproven
  item and route it to prove, keeping one group; or (C) both, A for
  timeliness and B as the backstop for a run lost for any other reason.]
- **FR-005**: Whichever mechanism is chosen, the guarantee that actually
  holds afterwards MUST be stated in one sentence in the concurrency
  block's own comment, replacing the sentence that describes the old
  behaviour. Comment edits here are code edits (CLAUDE.md).
- **FR-006**: Spec 057's FR-048 MUST NOT be edited. Its spec is a merged
  historical record; this feature states the narrowing in its own
  requirements and points at FR-048 rather than amending it.

### Functional Requirements — selection and resume

- **FR-007**: An open issue whose newest marker is `awaiting-merge`, whose
  named PR resolves MERGED, and which carries no proof record MUST NOT be
  resolved to `triage`. The merged attempt's PR number, branch, round and
  base SHA MUST NOT leak into whatever step it is resolved to.
- **FR-008**: The three neighbouring `awaiting-merge` states MUST behave
  exactly as they do today: PR OPEN is passed over (#532), PR CLOSED
  without merging falls to a fresh triage, and an unresolvable PR state is
  skipped rather than re-admitted.
- **FR-009**: The step vocabulary MUST stay one list. Any new step or new
  hold MUST be expressed through `board_eligibility.py`'s existing step
  sets, never a second parallel list, and `select()`'s fallback and
  `in_flight_candidate()` MUST continue to apply one rule rather than two
  copies of it.
- **FR-010**: Every fact the recovered prove needs that the live path reads
  off the event payload — the citing issue, the merged state, the PR's
  ownership labels and head repository, and the changed-path list — MUST be
  re-derived from live GitHub state, and a failed re-derivation MUST fail
  loudly rather than be treated as "nothing to prove".
- **FR-011**: The feature MUST state whether recovery also reaches an item
  whose `prove` marker records an earlier failed, timed-out or
  uncorrelated re-drive. [NEEDS CLARIFICATION: such an item is currently
  unreachable by every automated path — both selection paths skip a `prove`
  marker by design, and the `pull_request: closed` event cannot fire again
  for an already-merged PR — so it waits for a maintainer. Should recovery
  retry it (and under what bound, so a permanently failing proof cannot
  starve the board), or is a maintainer's attention the intended exit?]

### Functional Requirements — safety and legibility

- **FR-012**: The recovery MUST re-check the kill switch and any maintainer
  stop request immediately before its first durable action, as the live
  prove job does.
- **FR-013**: A PR that fails the `board:owned` + head-in-this-repository
  ownership test MUST NOT drive a recovered prove, and nothing MUST be
  recorded on the issue for it.
- **FR-014**: The displacement MUST be stated on the lifecycle issue as its
  own distinct reason, separable from every other no-proof reason spec 060
  FR-006/FR-007 enumerates, and it MUST leave the issue open until proof
  evidence exists (spec 057 FR-043 is unchanged).
- **FR-015**: A run that performs a recovery MUST emit a cost line and a
  durable metrics record through the existing mechanisms, under a run label
  that names the recovery.
- **FR-016**: No agent invocation MAY be added by this feature. Every
  judgment it introduces — whether an item is merged-but-unproven, whether
  recovery applies, which run to re-drive — MUST be deterministic code
  (Principle IX).
- **FR-017**: Nothing this feature writes MAY name a downstream consumer of
  this repository, and any issue or PR text it introduces MUST treat issue
  and PR bodies as data (Principle V).

### Functional Requirements — coverage

- **FR-018**: The concurrency arrangement this feature lands on MUST be
  asserted by a gate that reads the real `board-loop.yml`, reachable through
  the gate registry, running the same subject with the same arguments
  locally as in CI. The precedent is
  `verify-spec-branch-push-concurrency.py`.
- **FR-019**: That gate MUST also check the concurrency comment against the
  arrangement it describes, so FR-005's sentence cannot drift from the
  behaviour.
- **FR-020**: Every failure branch this feature adds MUST be exercised by a
  checked-in fixture in both directions — the passing tree and a tree where
  the property is broken (Principle VIII). A manual demonstration is not
  coverage.
- **FR-021**: `specs/057-autonomous-board-loop/contracts/prove-step.md` is a
  live contract a gate reads and MUST be updated to describe the entry this
  feature adds, so the contract and the workflow agree. If spec 060 lands
  first, the two updates MUST reconcile to one description rather than two.
- **FR-022**: The feature MUST be proven after merge by re-driving one run,
  with the evidence recorded on the PR or the lifecycle issue — the same
  rule it exists to make reliable.

### Key Entities

- **Board item marker**: the loop's per-issue state comment, carrying
  `step`, `round`, `pr`, `branch`, `base_sha`. The steps this feature turns
  on are `awaiting-merge` (readiness handed the PR to a human), `prove` (a
  merge whose proof did not conclude) and `proven` (terminal).
- **Displaced prove run**: a `pull_request: closed` run cancelled from the
  pending slot before any job started. It leaves no record of any kind —
  no marker, no comment, no metrics record — which is why it can only be
  detected from the state it *failed* to change.
- **Merged-but-unproven item**: an open issue whose loop-owned PR is MERGED
  and whose issue carries neither a proof record nor a `prove` marker. This
  is the detectable shape of a displaced prove.
- **Concurrency group**: the named slot GitHub serializes runs into. One
  in-progress run and at most one pending run per group; the pending one is
  evictable regardless of `cancel-in-progress`.
- **Re-drive**: the dispatched run that proves Actions-only behaviour,
  correlated by attempt token and waited on to a terminal conclusion.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a rehearsal where the `pull_request: closed` run is
  displaced from the pending slot, the merge still reaches the prove step
  and the lifecycle issue records a proof outcome — 100% of the time across
  the checked-in cases, versus 0% today.
- **SC-002**: No board issue whose loop-owned fix PR is MERGED is ever
  resolved to `triage`. Zero fresh triage comments on merged-and-fixed
  issues across the coverage set.
- **SC-003**: A maintainer reading only the lifecycle issue can tell
  whether a merge was proven, was displaced and recovered, or was not
  proven and why — in one read, with no run log.
- **SC-004**: No agent invocation is added: the loop's per-merge agent cost
  after this feature equals its cost before, and the recovery path's cost
  line shows no agent turns.
- **SC-005**: The concurrency arrangement fails a gate when reverted to the
  displaceable shape, and that gate passes on the real tree — both
  demonstrated by fixtures, not by argument.
- **SC-006**: #532's own guarantee is intact: an `awaiting-merge` item whose
  PR is still open is selected zero times.
- **SC-007**: The undisplaced prove path's observable behaviour is
  unchanged — same comments, same close conditions, same metrics labels —
  verified against the existing prove coverage.

## Assumptions

- GitHub's documented concurrency behaviour is taken as given: at most one
  pending run per group, and a newly queued run evicts the pending one
  irrespective of `cancel-in-progress: false`. The feature is built on that
  behaviour rather than on a hope that it changes.
- FR-048's purpose is bounding **agent** concurrency, on the Constitution's
  own stated reason (Principle X: pipeline runs and maintainers' sessions
  share one usage window). `prove-gate` and `prove` run no agent, so
  narrowing FR-048's wording to exclude them preserves its purpose. If the
  owner holds that FR-048 also bounds API and Actions-minute concurrency,
  mechanism (B) is the only admissible answer to Q2.
- Spec 057's merged artifacts are frozen records (CLAUDE.md): FR-048 is
  cited and superseded in this spec's text, never edited in place. Its
  `contracts/` directory is live and is updated (FR-021).
- Spec 060 is in flight at stage `spec` with no plan yet, so its FR-010b is
  not yet implemented and this feature cannot build on it as shipped
  behaviour.
- The board loop remains a repository-only workflow (spec 057 FR-062):
  nothing here becomes part of the published, adopter-pinned surface.
- Recovery of at most one displaced item per run is sufficient; the board's
  one-item-at-a-time cadence means a second displaced item waits for the
  next tick rather than being lost.

## Dependencies

- `specs/060-self-redrive-concurrency` — FR-010b (detect and record a
  displaced prove), FR-016 (the simultaneity sentence in every concurrency
  block's comment), FR-017 (the one permitted overlap is safe by check) and
  FR-001/FR-002 (the self-re-drive shape). Q1 resolves the relationship;
  until it is resolved, both specs claim the same lines of
  `board-loop.yml`.
- `.github/workflows/board-loop.yml` — the concurrency block (57–63),
  `select`'s trigger exclusion (106), the resume step's step resolution
  (555–700), `prove-gate` (3632) and `prove` (3787).
- `.github/scripts/board_eligibility.py` — `in_flight_candidate()` (167),
  `_awaiting_merge_holds()` (226), `select()` (263) and the step sets
  (`PRE_FIX_STEPS`, `FIX_OR_LATER_STEPS`, `TERMINAL_STEPS`).
- `.github/scripts/board_prove.py` and
  `.github/actions/wing-commander-dispatch-and-wait` — the actions-only
  decision, the re-drive target and the correlated wait the recovered path
  must reuse rather than reimplement.
- `.github/scripts/board_item_marker.py` — `read_marker()`,
  `write_marker()` and the loop-author predicate.
- `specs/057-autonomous-board-loop/contracts/prove-step.md` and
  `contracts/board-item-marker.md` — live contracts this feature updates.
- The gate registry and `python .github/scripts/run-local-gates.py` — the
  one entry point FR-018's gate must be reachable through.

## Out of Scope

- The self-re-drive deadlock (a prove run dispatching `board-loop.yml`
  itself and then waiting on a run queued behind it). That is spec 060
  FR-001/FR-002's subject.
- Changing what `board_prove.py` decides is Actions-only, or which workflow
  it aims a re-drive at. Spec 060 FR-013/FR-014 own the reachability of
  board helper scripts.
- Any change to who merges a board fix PR, or to the merge gate's
  conditions. The human merge is the trigger this feature makes reliable,
  not a thing it touches.
- Retiring or restructuring the `awaiting-merge` step itself. #532's design
  stands; only the MERGED branch of its handling changes.
- Errata against spec 057's or spec 060's `spec.md`, `plan.md`,
  `research.md` or `tasks.md`.
- Making `board-loop.yml` a published `workflow_call` stage, or exposing any
  of this as an adopter-facing input.
