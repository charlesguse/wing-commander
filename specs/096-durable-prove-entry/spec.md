# Feature Specification: A Merged Fix Reaches Prove — The Prove Entry Survives a Displaced Queue Slot

**Feature Branch**: `spec-draft/096-durable-prove-entry`

**Created**: 2026-09-29

**Status**: Draft — clarifications resolved

**Input**: Lifecycle issue #723 — "board-loop: a queued prove run
(pull_request: closed) can be displaced by the next scheduled run, so a
merge is never proven" (routed from board-loop.yml, reason
`no_usable_proposal`; originating issue #537, itself found by the code
review of the #532 fix on branch `fix/532-board-awaiting-merge`)

> Every `board-loop.yml`, `board_*.py` and `verify-*.py` line number in
> this spec is against `main` at `fa656bc` — the commit that merged spec
> 060 (PR #490, 2026-09-29). This feature's own branch was cut before that
> merge, so its working tree still shows the pre-060 shape; the
> requirements below are written against `main`.

## Overview

`board-loop.yml` serializes its work through **per-job** concurrency
groups, all named `wing-commander-board-loop` with `cancel-in-progress:
false` (`select` :139, `triage` :1014, `route` :1486, `fix` :1959, `review`
:2510, `readiness` :3526, `prove-gate` :3973, `prove` :4153 — spec 057
FR-048, restated per job by spec 060 FR-016). `prove-gate` and `prove`
alone carry a second branch: a directed `workflow_dispatch`
(`inputs.directed-stage != ''`) puts them in
`wing-commander-board-loop-directed-proof` instead. On the
`pull_request: closed` path they are in the ordinary group like everything
else.

GitHub keeps at most **one pending** entrant per concurrency group.
`cancel-in-progress: false` protects the entrant that is already *in
progress*; it does not protect the one that is *pending*. A newly queued
entrant takes the pending slot and the one that was holding it is cancelled
before it ever starts.

The `pull_request: closed` trigger (:70–71) is the only ordinary path into
the prove step (`prove-gate` :3959–3963: `github.event_name ==
'pull_request' || (workflow_dispatch && inputs.directed-stage == 'prove')`;
`prove` :4140–4142: `needs: prove-gate`). So the loop's proof of a merge
rides in the one kind of run that a routine hourly tick can silently
evict:

1. A scheduled board run holds `wing-commander-board-loop`. An
   agent-bearing item (triage → route → fix → review) can hold it for tens
   of minutes.
2. A maintainer merges the loop's fix PR. The `pull_request: closed` run
   starts and its `prove-gate` job goes pending on that group.
3. The next schedule tick — or another PR close — queues for the same group
   and takes the pending slot. `prove-gate` is cancelled before it runs, so
   `prove` never runs either.
4. No prove step executed, so the prove step recorded nothing.

Spec 060 landed the part that notices this. `select`'s "proof run
displacement" step (:210–301) lists recently merged `board:owned` PRs,
calls `board_prove_displacement.find_undetected_merges()`, and for each
merged PR whose issue carries no later `prove`/`proven` marker posts *PR
#N merged, but its proof run never started …  This issue stays open* plus a
`--step prove` marker (:298–300).

That record changes the harm rather than removing it, and it is worth
being precise about what it changed:

- **Before spec 060**, the issue's newest marker stayed `awaiting-merge`
  with a now-MERGED PR. `_awaiting_merge_holds()`
  (`board_eligibility.py:226`) holds an item only while its PR is *not*
  positively CLOSED or MERGED, so a MERGED PR re-admitted the issue to
  ordinary selection, the resume step resolved it through the "resolved by
  number but not OPEN" clause (`stale marker -- recorded pr N is MERGED,
  not open`, :804) and sent it to a **fresh triage** — spending an item
  slot and an agent invocation re-triaging an already-merged fix, with
  route and fix free to cut a second branch and PR.
- **After spec 060**, the displacement step writes its `prove` marker in
  `select`, ahead of resolution, and a `prove` marker is skipped by both
  `in_flight_candidate()` (:167) and `select()`'s fallback (:263). The
  re-triage is foreclosed. What remains is an issue that is **recorded and
  then stranded**: no automated path can reach a `prove` marker again, and
  the `pull_request: closed` event cannot fire twice for one merge, so the
  merge stays unproven until a maintainer acts.

Issue #723 asks for the part spec 060 deliberately left alone: that the
merge actually *reaches* prove, so the proof evidence spec 057 FR-043
requires exists rather than a note explaining why it does not.

### The FR-048 rationale, checked

Issue #537 asks for this check before choosing a fix, so here it is.
FR-048's guarantee is "one board item in flight repository-wide, with a
second run queuing rather than cancelling or racing". The Constitution
states its reason directly (Principle X): *"The loop works one item at a
time under a global concurrency group, because pipeline runs and the
maintainers' own sessions share one usage window."* The bound is on
**agent** concurrency.

`prove-gate` and `prove` invoke no agent. Both jobs say so in their own
metrics comments (`board-loop.yml:4107`, `board-loop.yml:4492`): the
re-drive decision is `board_prove.py`'s, the dispatch and wait are
`wing-commander-dispatch-and-wait`'s, and the issue comment and close are
`gh`'s. Nothing on the `pull_request: closed` path spends the usage window
FR-048 exists to protect. The prove path also takes no board item: it is
directed at the one issue named by the merged PR's body, and `select` — the
job that picks an item — is excluded from this trigger (`if:
github.event_name != 'pull_request' && inputs.directed-stage == ''`, :130).

Spec 060 already relied on exactly this property for its own group split:
*"A directed proof run is not a board iteration: it does not select a board
item and it does not open a fix PR. Spec 057 FR-048's 'one board item in
flight repository-wide' therefore holds unchanged."* The
`pull_request: closed` prove path has the same two properties. Giving it
its own group narrows nothing FR-048 actually guarantees — which is the
ground the owner's answer to Q2 stands on.

### What spec 060 owns, and what this feature adds

`specs/060-self-redrive-concurrency` is **merged and implemented** (PR
#490, commit `fa656bc`, 2026-09-29). Its parts this feature builds on
rather than repeats:

- **FR-010b** — detection and recording of a displaced prove run, shipped
  as `board_prove_displacement.find_undetected_merges()` and `select`'s
  displacement step. This feature does **not** re-detect; it reuses this
  detection and this recorded reason.
- **FR-016** — the one-sentence simultaneity guarantee, canonical in
  `specs/060-self-redrive-concurrency/contracts/concurrency-groups.md`
  ("## The guarantee"), restated verbatim in all eight per-job
  `concurrency:` comments and in
  `specs/057-autonomous-board-loop/contracts/board-loop-workflow.md`, and
  held together by Gate 101
  (`verify-concurrency-guarantee-statement.py`).
- **The directed proof entry** — `workflow_dispatch` with
  `directed-stage: prove` plus `directed-issue`/`directed-pr` already
  reaches `prove-gate`/`prove` for a named issue and PR, in its own group,
  with `board_prove.joins_directed_group()` and
  `directed_proof_group_busy()` guarding the dispatch. This is the one
  existing way into the prove step that is not the `pull_request: closed`
  event, so it is the entry this feature's recovery uses rather than a
  second prove implementation.
- **The outcome taxonomy** — `contracts/proof-outcome-taxonomy.md`'s eight
  `outcome_reason` values, which make "the loop could not observe a proof"
  distinguishable from "a proof ran and said no" in deterministic code.
  Q3's answer is expressed against these names.

One statement in spec 060's live contract becomes false under this
feature and has to be changed by it: `concurrency-groups.md`'s "What does
not change" section records that *"the hourly schedule tick can still
displace a queued `pull_request: closed` run's pending slot … this feature
does not change whether it can happen"*. That sentence, its "Groups, per
job" table row for `prove-gate`/`prove`, and the canonical guarantee
sentence are this feature's to update (FR-005).

### A rule with no gate behind it

Spec 060 gave the guarantee *sentence* a gate (Gate 101 byte-compares the
prose at all ten sites). It did not give the *arrangement* one: no script
asserts which group `prove-gate` actually joins on a `pull_request` event,
so an edit collapsing this feature's group back into
`wing-commander-board-loop` would pass the suite as long as the comments
still matched. Whatever arrangement this feature lands on, the arrangement
itself — not the prose describing it — has to be the thing a gate reads,
the way `verify-spec-branch-push-concurrency.py` already reads the
spec-branch push group. Per CLAUDE.md: a rule with no gate behind it lasts
until the next session.

## Clarifications

### Resolved — reply on lifecycle issue #723 by @charlesguse, 2026-09-29

**Q1 (scope) — recovery, specified here, built on spec 060 as merged.**
Not FR-010b's record-only behaviour, and not an amendment to spec 060:
spec 060 has landed (PR #490, 2026-09-29), so this feature is sequenced
after it and builds on its shipped detection, its directed proof entry and
its outcome taxonomy. FR-010b's record remains, as the backstop. Folded
into FR-001.

**Q2 (mechanism) — (A) the `pull_request: closed` prove path gets its own
concurrency group, keyed per item.** No scheduled tick and no other PR's
close can displace it. FR-048's one-item-in-flight guarantee bounds fix
work; a prove run touches only its own merged item's issue, selects no
board item and opens no fix PR — the same property spec 060 used to admit
the directed-proof group. Spec 060's FR-010b detection stays as the
backstop record. Not (B), and not (C)'s scheduled-side routing. Folded
into FR-004.

**Q3 (breadth) — retry only the case where the loop could not observe a
proof.** An item whose `prove` marker records the displacement itself, or
an `uncorrelated` re-drive, is retried once. A proof that ran and
concluded `failure`, or that timed out while executing (`unfinished`),
still waits for a human. Spec 060's outcome taxonomy already records which
no-proof condition occurred, so the distinction is deterministic. Folded
into FR-011.

### Consequences of Q2 (A) rather than (C), recorded rather than re-asked

Mechanism (A) is *prevention*: once the prove jobs sit in a group nothing
else contends for, a merge cannot be displaced in the first place, and the
scheduled side is not given a route into prove. Two consequences follow,
and this spec takes them as decided rather than sending a fourth question:

1. **Recovery still has work to do, but a bounded amount of it.** Merges
   already stranded with a `prove` marker when (A) ships — and Q3's
   `uncorrelated` case, which (A) does not address — are unreachable by
   every automated path. Without a recovery they stay unproven forever.
   This spec therefore keeps a recovery, scoped to exactly the two marker
   shapes Q3 names and bounded to one attempt each (FR-011).
2. **That recovery enters prove through spec 060's directed dispatch.**
   It is the only existing entry into `prove-gate`/`prove` that is not the
   `pull_request: closed` event, and reusing it is what keeps FR-002's "one
   home" true. (A) supplies timeliness for every future merge; the directed
   entry supplies reach for the stranded ones.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A merge the loop made is proven, not stranded (Priority: P1)

A maintainer merges a board fix PR while a scheduled board run is in
progress. The hourly tick queues for the same group. The maintainer expects
the merge to be *proven* — the affected behaviour re-driven, the run URL
and conclusion posted, the issue closed on that evidence — not to find, on
the next scheduled run, a comment saying the proof run never started and an
issue nothing will pick up again.

**Why this priority**: this is the whole of issue #723. Every other story
here is a consequence of it. Without it the loop's proof step is
conditional on nothing having ticked in a window a maintainer cannot see
and cannot control, and the Constitution's "A fix to behaviour that only
runs in Actions is proven after merge by re-driving one run" is satisfied
only by luck.

**Independent Test**: drive one board item to a merged fix PR while a
second entrant contends for `wing-commander-board-loop`, and confirm
`prove-gate`/`prove` still execute. Then, separately, take an issue already
carrying a displacement `prove` marker and let the recovery run: the issue
receives the proof outcome (closed on a successful re-drive, or left open
carrying the failing run URL), and never a fresh triage comment.

**Acceptance Scenarios**:

1. **Given** a `pull_request: closed` event for a merged board fix PR and a
   scheduled run in progress, **When** both contend, **Then** `prove-gate`
   and `prove` run to completion — they are in a group the scheduled run
   does not join, so neither is displaced from a pending slot.
2. **Given** a second board fix PR closing in the same window, **When** its
   own `prove-gate` queues, **Then** it does not displace the first PR's
   `prove-gate`: the group key distinguishes the two merges.
3. **Given** an issue whose newest marker is a `prove` marker recording the
   FR-010b displacement, **When** the recovery runs, **Then** the item is
   taken to the prove step — the same actions-only decision, re-drive and
   recording the `pull_request: closed` path performs — and not to triage.
4. **Given** a recovered prove that concludes `success`, **When** the
   outcome is recorded, **Then** the issue closes citing the re-driven run
   URL and its conclusion, exactly as the undisplaced path does.
5. **Given** a recovered prove whose re-drive concludes `failure` or
   `unfinished`, **When** the outcome is recorded, **Then** the issue stays
   open carrying that evidence, and the item is not recovered again on a
   later run.
6. **Given** a `pull_request: closed` run that was **not** contended,
   **When** it runs, **Then** its observable behaviour is the behaviour it
   has today and the recovery never duplicates its work.

---

### User Story 2 - A merged fix is never re-triaged as if it were unfixed (Priority: P1)

The loop must not spend an item slot, an agent invocation, and possibly a
second branch and PR on an issue whose fix it merged. Spec 060's
displacement marker forecloses that today by writing `prove` before
resolution; this feature must keep it foreclosed while changing what
happens to such an item next.

**Why this priority**: this is the part of #723 that costs money and can
produce a duplicate PR. It is also the part that must not regress #532's
own fix: an `awaiting-merge` item whose PR is still OPEN must keep being
passed over, and an `awaiting-merge` item whose PR was closed *without*
merging must keep falling to a fresh triage.

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
comment. The arrangement this feature lands on is asserted against the real
workflow file, and the sentence that describes it stays checked by the gate
spec 060 already added.

**Why this priority**: Principle VIII, and CLAUDE.md's "a rule with no
gate behind it lasts until the next session". Gate 101 checks the *prose*;
nothing yet checks which group `prove-gate` joins on a `pull_request`
event, so the arrangement this feature depends on could be reverted
silently as long as the comments were updated to match.

**Independent Test**: run the gate against the real tree (it passes) and
against fixtures that put the `pull_request: closed` prove path back into
`wing-commander-board-loop`, that make the group key shared across merges,
and that drift the guarantee sentence from the arrangement (each fails,
naming the file and the property).

**Acceptance Scenarios**:

1. **Given** the shipped `board-loop.yml`, **When** the gate runs from the
   repository root, **Then** it passes, having resolved the real file
   rather than a fixture.
2. **Given** a tree where `prove-gate` or `prove` joins the ordinary group
   on a `pull_request` event, **When** the gate runs, **Then** it fails
   naming the property that no longer holds.
3. **Given** a tree whose prove-path group key is not distinct per merged
   item, **When** the gate runs, **Then** it fails.
4. **Given** a tree whose guarantee sentence describes an arrangement the
   file no longer has, **When** the gate suite runs, **Then** it fails —
   through the existing Gate 101, not through a second prose-comparing
   gate.
5. **Given** the gate registry, **When** the gate suite runs locally and in
   CI, **Then** the gate runs in both with the same subject and arguments.

---

### User Story 4 - The recovery is legible and costed on the issue (Priority: P3)

A maintainer reading the lifecycle issue can tell, without leaving it,
that the proof was displaced, that the loop recovered it, and what the
recovery cost.

**Why this priority**: Constitution III and spec 057 FR-044/FR-047. The
behaviour is correct without it; the loop is only *auditable* with it.

**Independent Test**: after a recovered prove, the issue carries spec
060's displacement statement, the recovery statement, the proof outcome,
and the run's cost line, and the run emits a durable metrics record under a
label naming the condition.

**Acceptance Scenarios**:

1. **Given** a recovered prove, **When** the run finishes, **Then** it
   emits a cost line and a durable metrics record whose run label names
   the recovery, distinguishable from an ordinary prove run and from every
   label spec 060's taxonomy already maps.
2. **Given** a recovered prove, **When** its outcome is recorded, **Then**
   the issue comment says the proof was displaced and recovered, not
   merely what the proof concluded.
3. **Given** an item whose one recovery attempt is spent, **When** a later
   run reads the issue, **Then** it can tell that the attempt was spent
   and leaves the item alone.

---

### Edge Cases

- **The merged PR is not the loop's own.** A human PR whose body says
  `Fixes #N` for an issue carrying a board marker must not drive a
  recovered prove any more than it drives the live one: the same
  `board:owned` + head-in-this-repository ownership test applies
  (`BOARD_PR_OWNED_JQ`).
- **Two merges displaced in the same window.** Two board issues could each
  have a merged, unproven PR when the recovery next runs. One of them is
  recovered per run at most; the other must remain recoverable rather than
  falling through to triage or losing its one attempt without using it.
- **Two merges closing in the same window.** Under mechanism (A) these must
  not contend with each other either: a group key shared by all merges
  would move the displacement rather than remove it.
- **The directed-proof group is already busy.** A recovery dispatch is a
  directed dispatch, so `board_prove.directed_proof_group_busy()` applies:
  the recovery must take `group-busy` as "not now" and leave the item
  recoverable, never spend its one attempt on a dispatch it did not make.
- **The issue was closed by a human during the window.** A closed issue is
  not selected. The merge is then unproven and unrecorded forever; this
  must be an accepted, stated outcome rather than an unnoticed one.
- **The displaced run's own event payload is gone.** The live prove path
  reads the PR body, `merged`, labels and changed paths off
  `github.event.pull_request`. A recovery running off the schedule has no
  such payload, and spec 060's displacement marker carries no `pr`,
  `branch` or `base_sha` (it is written `--step prove` alone, :298), so
  every one of those facts must be re-derived from live GitHub state.
- **The re-drive target is `board-loop.yml` itself.** `board_prove.py`'s
  self-target case is spec 060's FR-001/FR-001a subject and is solved there
  by the directed group plus the busy check. A recovery that dispatches
  through that same entry inherits that solution and must not weaken it.
- **A `prove` marker from a failed earlier attempt.** Per Q3 this is
  recovered only when the recorded reason is the displacement itself or
  `uncorrelated`. A `failure` or `unfinished` marker waits for a
  maintainer, and the other taxonomy reasons (`group-busy`, `not-started`,
  `displaced` of a directed dispatch, `no-target`, `nothing-reaches`)
  remain spec 060's record-only subject.
- **The kill switch is set, or a maintainer requested a stop.** The
  recovery takes durable actions (a comment, a dispatch, a close) and must
  re-check both immediately before the first of them, as the live prove job
  does and as spec 060's displacement step already does (:218).

## Requirements *(mandatory)*

### Functional Requirements — scope and mechanism

- **FR-001**: The feature MUST establish that a merged board fix PR reaches
  the prove step even when another entrant contends for the concurrency
  group that hosts the loop's ordinary work. Recovery, not record-only
  reporting, is the outcome required (Q1): spec 060's FR-010b detection and
  record remain in place as the backstop, and this feature builds on spec
  060 as merged (PR #490) rather than amending it.
- **FR-002**: The recovered path MUST produce the same outcomes as the
  undisplaced path, decision for decision: the actions-only decision, the
  re-drive target, the wait, the close-on-success, the leave-open on every
  non-`success` outcome reason. It MUST NOT be a second, parallel
  implementation of any of them — `prove-gate`/`prove` and `board_prove.py`
  are the one home (CLAUDE.md "shared logic has exactly one home"), and the
  recovery's entry into them MUST be spec 060's existing directed dispatch
  (`directed-stage: prove` with `directed-issue`/`directed-pr`), not a new
  trigger and not a copy of the prove steps.
- **FR-003**: The undisplaced `pull_request: closed` path's behaviour MUST
  be unchanged, and the recovery MUST NOT duplicate a proof that path has
  already performed or is performing.
- **FR-004**: `prove-gate` and `prove` on the `pull_request: closed` path
  MUST join a concurrency group of their own (Q2, mechanism A): distinct
  from `wing-commander-board-loop`, distinct from
  `wing-commander-board-loop-directed-proof`, and keyed so that no two
  distinct merged items share one group. The key MUST be derivable from
  context available to a job-level `concurrency.group` expression on a
  `pull_request` event (the merged PR's own number is such a value and is
  one-to-one with the item's issue, which `prove-gate` resolves from the PR
  body). The existing directed branch of those two jobs' group expressions
  MUST be preserved, and the expression MUST stay readable by
  `board_prove.joins_directed_group()`, which parses a target job's own
  group expression off the checked-out tree.
- **FR-005**: The guarantee that actually holds afterwards MUST be stated by
  editing the canonical sentence in
  `specs/060-self-redrive-concurrency/contracts/concurrency-groups.md`
  ("## The guarantee"), never by writing a new sentence into one
  `concurrency:` comment — Gate 101
  (`verify-concurrency-guarantee-statement.py`) then holds all eight
  per-job comments and
  `specs/057-autonomous-board-loop/contracts/board-loop-workflow.md` to it.
  The same change MUST update that contract's "Groups, per job" table row
  for `prove-gate`/`prove` and its "What does not change" bullet, which
  today records that the hourly tick can still displace a queued
  `pull_request: closed` run and which mechanism (A) makes false. Comment
  edits here are code edits (CLAUDE.md).
- **FR-006**: Spec 057's FR-048 and spec 060's `spec.md` MUST NOT be
  edited. Both are merged historical records; this feature states the
  narrowing in its own requirements and points at them. Their `contracts/`
  directories are live and are updated (FR-005, FR-021).

### Functional Requirements — selection, resume and recovery

- **FR-007**: An open issue whose loop-owned PR is MERGED and which carries
  no proof record MUST NOT be resolved to `triage`, whether or not spec
  060's displacement step has yet written its `prove` marker. The merged
  attempt's PR number, branch, round and base SHA MUST NOT leak into
  whatever step it is resolved to, and the resume step's `stale marker --
  recorded pr N is MERGED, not open` path (:804) MUST NOT become the route
  such an item takes.
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
  re-derived from live GitHub state, by the re-derivation routes
  `specs/057-autonomous-board-loop/contracts/board-item-marker.md` already
  names, never read from the displacement marker (which carries none of
  them). A failed re-derivation MUST fail loudly rather than be treated as
  "nothing to prove".
- **FR-011**: Recovery MUST reach exactly two marker shapes (Q3), decided
  from spec 060's recorded outcome reason rather than from prose:
  (a) a `prove` marker recording the FR-010b displacement itself, and
  (b) a `prove` marker whose recorded outcome reason is `uncorrelated` —
  the cases where the loop could not observe a proof at all. A marker
  recording `failure` or `unfinished` MUST NOT be retried; a maintainer's
  attention is its intended exit. The remaining taxonomy reasons
  (`group-busy`, `not-started`, `displaced`, `no-target`,
  `nothing-reaches`) stay spec 060's record-only subject.
- **FR-011a**: Recovery MUST be bounded to **one** attempt per merged PR,
  and that the attempt is spent MUST be durable on the issue and readable
  by deterministic code, so a permanently unobservable proof cannot be
  retried on every tick and cannot starve the board. A dispatch not made
  because the directed group was busy MUST NOT count as the attempt.
- **FR-011b**: At most one item MAY be recovered per run, and an item not
  recovered in this run MUST remain recoverable rather than falling to
  triage or losing its attempt.

### Functional Requirements — safety and legibility

- **FR-012**: The recovery MUST re-check the kill switch and any maintainer
  stop request immediately before its first durable action, as the live
  prove job and spec 060's displacement step (:218) do.
- **FR-013**: A PR that fails the `board:owned` + head-in-this-repository
  ownership test MUST NOT drive a recovered prove, and nothing MUST be
  recorded on the issue for it.
- **FR-014**: The displacement MUST continue to be stated on the lifecycle
  issue through spec 060's existing record
  (`board_prove_displacement.RECORDED_REASON`, "prove run displaced", and
  the comment at :300) — this feature MUST NOT add a second reason for the
  same condition. What it adds is the statement that the displaced proof
  was *recovered*, and the proof outcome, each distinct from every reason
  spec 060's taxonomy enumerates. The issue stays open until proof
  evidence exists (spec 057 FR-043 is unchanged).
- **FR-015**: A run that performs a recovery MUST emit a cost line and a
  durable metrics record through the existing mechanisms — the
  `wing-commander-metrics-summary` `cost-line` output and the existing
  "Determine this run's outcome for the metrics record" step's label
  mapping — under a run label that names the recovery and is distinct from
  every label spec 060's taxonomy already maps.
- **FR-016**: No agent invocation MAY be added by this feature. Every
  judgment it introduces — whether an item is merged-but-unproven, whether
  recovery applies, whether its attempt is spent, which run to re-drive —
  MUST be deterministic code (Principle IX).
- **FR-017**: Nothing this feature writes MAY name a downstream consumer of
  this repository, and any issue or PR text it introduces MUST treat issue
  and PR bodies as data (Principle V).

### Functional Requirements — coverage

- **FR-018**: The concurrency arrangement this feature lands on MUST be
  asserted by a gate that reads the real `board-loop.yml` — which group
  `prove-gate` and `prove` join on a `pull_request` event, and that its key
  distinguishes two merged items — reachable through the gate registry and
  running the same subject with the same arguments locally as in CI. The
  precedent is `verify-spec-branch-push-concurrency.py`; where spec 060's
  `board_prove.joins_directed_group()` already parses a job's group
  expression, that reader MUST be reused rather than re-implemented.
- **FR-019**: The guarantee sentence MUST stay checked against the
  arrangement through the existing Gate 101, extended if its expectations
  (its per-job block count, its canonical source) need it. This feature
  MUST NOT add a second gate that compares the same prose.
- **FR-020**: Every failure branch this feature adds MUST be exercised by a
  checked-in fixture in both directions — the passing tree and a tree where
  the property is broken (Principle VIII). A manual demonstration is not
  coverage.
- **FR-021**: `specs/057-autonomous-board-loop/contracts/prove-step.md` is a
  live contract a gate reads and MUST be updated to describe the entry this
  feature adds, reconciling with the edits spec 060 already made to its
  "Re-drive" section so the contract carries one description rather than
  two. `specs/060-self-redrive-concurrency/contracts/`'s
  `concurrency-groups.md`, `directed-proof-run.md` and
  `proof-outcome-taxonomy.md` are live for the same reason and MUST agree
  with the shipped arrangement.
- **FR-022**: The feature MUST be proven after merge by re-driving one run,
  with the evidence recorded on the PR or the lifecycle issue — the same
  rule it exists to make reliable.

### Key Entities

- **Board item marker**: the loop's per-issue state comment, carrying
  `step`, `round`, `pr`, `branch`, `base_sha`. The steps this feature turns
  on are `awaiting-merge` (readiness handed the PR to a human), `prove` (a
  merge whose proof did not conclude — including spec 060's displacement
  record, written with `step` alone) and `proven` (terminal).
- **Displaced prove run**: a `pull_request: closed` run whose `prove-gate`
  job was cancelled from its group's pending slot before it executed. It
  records nothing itself, which is why spec 060 detects it from the state
  it *failed* to change.
- **Merged-but-unproven item**: an open issue whose loop-owned PR is MERGED
  and whose issue carries no `prove`/`proven` marker later than the merge.
  This is `find_undetected_merges()`'s subject and the detectable shape of
  a displaced prove.
- **Recoverable item**: a merged-but-unproven item whose recorded reason is
  the displacement or `uncorrelated`, and whose one recovery attempt is
  unspent.
- **Concurrency group**: the named slot GitHub serializes entrants into.
  One in-progress and at most one pending entrant per group; the pending
  one is evictable regardless of `cancel-in-progress`.
- **Re-drive**: the dispatched run that proves Actions-only behaviour,
  correlated by attempt token and waited on to a terminal conclusion.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a rehearsal where a scheduled entrant contends for
  `wing-commander-board-loop` at the moment a board fix PR closes, the
  merge still reaches the prove step — 100% of the time across the
  checked-in cases, versus 0% today.
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
  shared group, and when its key stops distinguishing two merged items —
  both demonstrated by fixtures, not by argument — and that gate passes on
  the real tree.
- **SC-006**: #532's own guarantee is intact: an `awaiting-merge` item whose
  PR is still open is selected zero times.
- **SC-007**: The undisplaced prove path's observable behaviour is
  unchanged — same comments, same close conditions, same metrics labels —
  verified against the existing prove coverage.
- **SC-008**: A permanently unobservable proof is retried at most once: the
  coverage set shows a second recovery attempt on the same merged PR
  happening zero times, and `failure`/`unfinished` markers retried zero
  times.

## Assumptions

- GitHub's documented concurrency behaviour is taken as given: at most one
  pending entrant per group, and a newly queued entrant evicts the pending
  one irrespective of `cancel-in-progress: false`. The feature is built on
  that behaviour rather than on a hope that it changes.
- FR-048's purpose is bounding **agent** concurrency, on the Constitution's
  own stated reason (Principle X: pipeline runs and maintainers' sessions
  share one usage window), and the owner's answer to Q2 settles that
  reading. `prove-gate` and `prove` run no agent, select no board item and
  open no fix PR, so giving them their own group narrows nothing FR-048
  guarantees — the same ground spec 060 stood on for its directed group.
- Spec 060 is merged and implemented (PR #490, `fa656bc`, 2026-09-29). Its
  detection, its directed proof entry, its outcome taxonomy and Gate 101
  are shipped behaviour this feature builds on. This feature's own branch
  predates that merge and is rebased before implementation.
- Spec 057's and spec 060's merged artifacts are frozen records (CLAUDE.md):
  their requirements are cited and superseded in this spec's text, never
  edited in place. Their `contracts/` directories are live and are updated.
- Keying the prove path's group by the merged PR's number is sufficient to
  distinguish two merged items, because a loop fix PR cites exactly one
  issue and one issue has at most one merged loop fix PR in flight. Plan
  chooses the exact expression; FR-004 states the property it must have.
- One recovery attempt per merged PR is the bound Q3's starvation concern
  asks for, and one recovered item per run is sufficient: the board's
  one-item-at-a-time cadence means a second recoverable item waits for the
  next tick rather than being lost.

## Dependencies

- `specs/060-self-redrive-concurrency` as merged — `board_prove_displacement.py`
  (FR-010b's detection), `select`'s displacement step
  (`board-loop.yml:210-301`), the directed dispatch inputs and
  `prove-gate`/`prove`'s directed group branch, `board_prove.py`'s
  `joins_directed_group()`/`directed_proof_group_busy()`/`directed_stage()`,
  Gate 101 (`verify-concurrency-guarantee-statement.py`) and the contracts
  `concurrency-groups.md`, `directed-proof-run.md` and
  `proof-outcome-taxonomy.md`.
- `.github/workflows/board-loop.yml` — the per-job concurrency blocks (139,
  1014, 1486, 1959, 2510, 3526, 3973, 4153), `select`'s trigger exclusion
  (130), the resume step's step resolution (573-830), `prove-gate` (3959)
  and `prove` (4140).
- `.github/scripts/board_eligibility.py` — `in_flight_candidate()` (167),
  `_awaiting_merge_holds()` (226), `select()` (263) and the step sets
  (`PRE_FIX_STEPS`, `FIX_OR_LATER_STEPS`, `TERMINAL_STEPS`).
- `.github/scripts/board_prove.py` and
  `.github/actions/wing-commander-dispatch-and-wait` — the actions-only
  decision, the re-drive target and the correlated wait the recovered path
  must reuse rather than reimplement.
- `.github/scripts/board_item_marker.py` — `read_marker()`,
  `read_marker_with_timestamp()`, `write_marker()` and the loop-author
  predicate.
- `specs/057-autonomous-board-loop/contracts/prove-step.md`,
  `contracts/board-item-marker.md` and `contracts/board-loop-workflow.md` —
  live contracts this feature updates or is held to.
- The gate registry and `python .github/scripts/run-local-gates.py` — the
  one entry point FR-018's gate must be reachable through.

## Out of Scope

- The self-re-drive deadlock and the directed proof mechanism itself. Spec
  060 shipped both; this feature consumes them.
- Re-detecting the displacement. `find_undetected_merges()` is the one
  detector and stays the only one.
- Changing what `board_prove.py` decides is Actions-only, or which workflow
  it aims a re-drive at.
- Retrying the taxonomy reasons FR-011 excludes, or changing what spec 060
  records for them.
- Any change to who merges a board fix PR, or to the merge gate's
  conditions. The human merge is the trigger this feature makes reliable,
  not a thing it touches.
- Retiring or restructuring the `awaiting-merge` step itself. #532's design
  stands; only the MERGED branch of its handling changes.
- Errata against spec 057's or spec 060's `spec.md`, `plan.md`,
  `research.md` or `tasks.md`.
- Making `board-loop.yml` a published `workflow_call` stage, or exposing any
  of this as an adopter-facing input.
