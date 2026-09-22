# Feature Specification: The Proof Run Can Actually Start — Self Re-Drive vs. the Board Loop's Own Concurrency Group

**Feature Branch**: `060-self-redrive-concurrency`

**Created**: 2026-09-22

**Status**: Draft

**Input**: Lifecycle issue [#460](https://github.com/charlesguse/wing-commander/issues/460) — "board-loop.yml's self re-drive deadlocks against its own concurrency group", found by the code review of #451

## Context

The board loop's last step is **prove**: when a human merges the fix PR, the
`pull_request: closed` trigger resumes the item, the loop decides whether the
merged change is Actions-only behaviour, and if it is, it re-drives one run
through a wrapper that can dispatch it, waits for a terminal outcome, and
records the run URL and outcome before the issue may close (spec 057 FR-041,
FR-042, FR-043; `contracts/prove-step.md`).

Which wrapper to re-drive is deterministic and code-derived, never the agent's
pick (Principle IX). `board_prove.redrive_target()` documents three cases:

1. a changed workflow that is itself `workflow_dispatch`-capable is its own
   wrapper — re-drive it directly;
2. otherwise re-drive the dispatchable workflow that references the changed
   thing;
3. neither exists — record that nothing reaches this change and leave the
   issue open.

### The deadlock

PR #451 fixed a dead redrive mechanism: `is_safe_redrive_target()` had been
rejecting every workflow in the repository, including `board-loop.yml` itself,
so the dispatchable set was always empty and the prove step never dispatched
anything. Making the mechanism live surfaced the conflict the dead code was
masking.

`board-loop.yml`'s concurrency block is **workflow-level**, so it applies
uniformly across every trigger of that one file — `schedule`,
`workflow_dispatch`, and `pull_request: closed` alike
(`.github/workflows/board-loop.yml:40-46`):

```
group: wing-commander-board-loop
cancel-in-progress: false
```

The `prove` job runs on the `pull_request: closed` trigger, so the run it is
part of is *already holding that group's slot*. When the Re-drive step calls
`gh workflow run board-loop.yml`, the dispatched run joins the same group and
queues behind the run that dispatched it. Under `cancel-in-progress: false` it
cannot start until the prove run finishes — and the prove run is, by
construction, waiting for it.

`wing-commander-dispatch-and-wait`'s default budget is 12 correlation attempts
5s apart (60s) plus 60 wait attempts at `poll-interval-seconds: 10` (600s).
Correlation *succeeds* — a queued run already carries its `run-name`, so the
`[attempt:…]` token is visible in `gh run list` — and then the wait exhausts
against a run that never leaves `queued`. The composite returns
`conclusion=timeout` with a real `run-url`, and FR-043's failure branch fires:
the issue stays open carrying an eleven-minute-old URL of a run that had not
begun.

Only when the prove job ends, releasing the group, does the dispatched run
actually start — as an ordinary board iteration on whatever issue is
oldest-eligible at that point, no longer correlated back to the fix being
proven from the caller's point of view, and spending a full agent budget on
unrelated work while the maintainer reads "Not proven" on the issue.

### This is the whole re-drive path, not only case 1

The lifecycle issue frames the conflict around case 1 (`board-loop.yml`
re-driving itself). On the current tree it is wider than that.
`is_safe_redrive_target()` admits a workflow only when its own `run-name:`
reads `inputs.attempt-token` and it declares no *other* required
`workflow_dispatch` input. Exactly two workflows carry the run-name wiring —
`board-loop.yml` and `release.yml` — and `release.yml` is rejected for its
required `version` input. **`board-loop.yml` is therefore the only member of
the dispatchable set.**

Case 2 selects "the dispatchable workflow that references the changed thing",
and the only candidate it can ever select is `board-loop.yml`. So *every*
re-drive the prove step can perform today — a change to `board-loop.yml`
itself, to a composite under `.github/actions/` that it uses, to a
`workflow_call`-only stage it references — dispatches `board-loop.yml` from
inside a `board-loop.yml` run, and every one of them hits the same queue. The
prove step's re-drive branch has no working path at all, not one broken case.

### The reachability gap the same review found

`scan_dispatchable_and_uses_graph()` builds `uses_graph` from textual
`.github/workflows/*.yml` and `.github/actions/*` references found in each
workflow's own file. A bare `.github/scripts/…` path is not matched. A merged
PR that changes only a board helper — `board_prove.py`, `board_stop_check.py`,
`board_item_marker.py` — is not a `verify-*.py` gate, so `actions_only` is
`true`, but `redrive_target()` finds no candidate referencing it and returns
`null`. FR-043's "nothing reaches this change" branch fires, correct by the
letter of the contract, on a script `board-loop.yml` executes on every single
run.

The two gaps interact. Closing the reachability gap would route *more* merges
into the re-drive branch, and every one of those re-drives lands in the queue
described above. Whatever is done about reachability must not be shipped ahead
of a re-drive that can start.

### Related surface the same concurrency block creates

Because the group is workflow-level, a `pull_request: closed` event for *any*
PR in the repository — not only a board fix PR — creates a `board-loop` run
that occupies `wing-commander-board-loop` while `prove-gate` evaluates
eligibility and decides the item is not one of the loop's. GitHub also keeps
at most one *pending* run per group, so a queued proof dispatch can be
displaced outright by the next hourly schedule tick. Both are consequences of
the same block and are in this feature's scope to account for, even if the
chosen resolution leaves them unchanged.

### What the owner has to decide

The lifecycle issue is explicit that this needs an owner decision rather than a
unilateral fix, and names three candidate shapes — a separate concurrency group
for re-drive dispatches, not waiting synchronously for a self-re-drive, or
accepting the current timeout-then-unrelated-run behaviour. Each trades
something different away: the first weakens spec 057 FR-048's "one board item
in flight repository-wide" for the re-drive path; the second reopens FR-043's
three-way conclusion and the definition of proof evidence; the third leaves the
re-drive branch permanently non-functional while continuing to spend eleven
minutes and an unrelated agent budget per merge. A fourth shape the issue does
not name — scoping the concurrency group per trigger so a prove run never holds
the item slot — is cheaper but introduces a prove-vs-selection race on the same
issue. Those are the spec's three open questions, recorded as
`[NEEDS CLARIFICATION]` below and posted to the lifecycle issue rather than
guessed at.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A merged Actions-only fix gets a proof run that can actually start (Priority: P1)

A maintainer merges a board fix PR whose change only runs inside Actions. The
loop re-drives a run to prove it. That run starts, executes the changed
behaviour, and reaches a terminal conclusion while the prove step is still
watching — so the conclusion recorded on the issue is a statement about the fix
rather than a statement about a queue.

**Why this priority**: This is the defect. Today the re-drive branch cannot
succeed for any change, which means no Actions-only board fix can ever be
proven, which means no such issue can ever close on proof evidence. Every other
story in this spec is a consequence of getting this one right.

**Independent Test**: Merge a PR that changes only Actions-only behaviour
reachable from the loop, and observe that the proof run leaves the queued state
and reaches a terminal conclusion inside the prove step's wait budget.

**Acceptance Scenarios**:

1. **Given** a merged fix PR whose changed paths make `actions_only` true and
   whose re-drive target is the same workflow the prove step is running in,
   **When** the prove step dispatches the proof run, **Then** that run starts
   rather than queuing behind the dispatching run.
2. **Given** that proof run started, **When** it finishes, **Then** the prove
   step observes its terminal conclusion and records it on the issue with the
   run URL.
3. **Given** the proof run concluded successfully, **When** the prove step
   records the outcome, **Then** the issue closes citing that run URL and
   conclusion, exactly as spec 057 FR-043's success branch requires.
4. **Given** the proof run concluded as a failure, **When** the prove step
   records the outcome, **Then** the issue stays open carrying the failing run
   URL, unchanged from today's behaviour.

---

### User Story 2 - A proof that could not be produced says why, in terms a maintainer can act on (Priority: P1)

A maintainer reading the issue can tell the difference between "the proof run
ran and the fix is not proven", "the proof run could not start", and "nothing
in the repository reaches this change". Today the first two are both rendered
as `conclusion=timeout` against a plausible-looking run URL.

**Why this priority**: Spec 057 SC-001 promises the whole item history is
readable from the issue alone. A timeout that actually means "the loop
dispatched into its own queue" sends the maintainer to look at the fix, which
is fine, instead of at the loop, which is where the problem is. It is also the
part of this feature that must hold no matter which resolution the owner picks
for Story 1 — even "accept the current behaviour" needs the recorded reason to
be truthful.

**Independent Test**: Force each of the three no-proof conditions and read the
issue comment for each; each must name its own distinct condition.

**Acceptance Scenarios**:

1. **Given** a proof run that was dispatched but never left the queued state
   within the wait budget, **When** the prove step records the outcome, **Then**
   the issue comment names that the run never started and why, and does not
   present it as a failed execution of the fix.
2. **Given** a proof run that started and exhausted the wait budget while still
   executing, **When** the prove step records the outcome, **Then** the issue
   comment distinguishes that case from the never-started case.
3. **Given** a merged change nothing in the repository can re-drive, **When**
   the prove step records the outcome, **Then** the issue comment names that
   condition and the issue stays open, unchanged from today.
4. **Given** any of the above, **When** the maintainer reads the issue, **Then**
   the recorded reason is enough to decide whether to re-run the proof or to
   look at the fix, without opening the Actions tab.

---

### User Story 3 - A dispatch the loop abandoned does not quietly become someone else's board iteration (Priority: P2)

A proof dispatch that the prove step stopped waiting for must not start later
and consume a board item and an agent budget as an anonymous ordinary
iteration. Either it does not outlive the caller, or it is attributable to the
merge it was dispatched to prove.

**Why this priority**: This is the silent cost of today's behaviour: eleven
minutes after the maintainer is told "not proven", a full board iteration runs
against an unrelated issue with nothing on any issue explaining where it came
from. It is lower priority than Stories 1 and 2 because it is a side effect
rather than the broken guarantee — and some resolutions to Story 1 remove it
outright.

**Independent Test**: Dispatch a proof run, let the caller stop waiting, and
check both that the dispatched run's eventual behaviour is accounted for and
that its origin is recoverable from the issue or the run itself.

**Acceptance Scenarios**:

1. **Given** a proof dispatch the prove step gave up waiting on, **When** that
   run later becomes eligible to start, **Then** either it does not run as an
   unrelated board iteration, or the issue it works and the run itself record
   that it originated as a proof re-drive of a named merge.
2. **Given** a proof dispatch that was displaced from the pending slot before
   it ever started, **When** the prove step records the outcome, **Then** the
   issue says the dispatch was displaced rather than that the proof failed.

---

### User Story 4 - A board helper script a merge changed is either reachable or explicitly declared unreachable (Priority: P2)

A merged PR that changes only a `.github/scripts/board_*.py` helper gets a
recorded decision that reflects reality: the loop executes that script on every
run, so either it is re-driven like any other Actions-only change, or the issue
records a reason that is true rather than "nothing reaches this change".

**Why this priority**: This is the second, smaller gap the same review found.
It is real — the board helpers are exactly the files a board-loop fix PR is
most likely to touch — but it is strictly downstream of Story 1: routing more
merges into a re-drive branch that cannot start would make things worse, not
better.

**Independent Test**: Take a merged PR whose changed paths are only a board
helper script and check the recorded re-drive decision against the reachability
rule the feature adopts.

**Acceptance Scenarios**:

1. **Given** a merged PR changing only a `.github/scripts/board_*.py` helper,
   **When** the prove step decides the re-drive target, **Then** the decision
   and its reason are consistent with the reachability rule this feature
   adopts, and the reason is recorded on the issue either way.
2. **Given** the reachability rule admits script paths, **When** the target is
   chosen, **Then** it is chosen deterministically from the tree, with ties
   broken the same way for two runs over the same merge.

---

### User Story 5 - One board item in flight is still a guarantee a maintainer can rely on (Priority: P1)

Whatever changes about concurrency, a maintainer can still state in one
sentence what the loop guarantees about simultaneity, and a fixture holds the
loop to it.

**Why this priority**: Spec 057 FR-048 exists because two board iterations
racing can select the same issue, open two fix PRs, or close an issue another
run is still working. A resolution that quietly weakens that to make the proof
run start would trade a visible bug for an invisible one.

**Independent Test**: State the post-change guarantee and exercise the pairs it
permits and the pairs it forbids.

**Acceptance Scenarios**:

1. **Given** the resolution this feature adopts, **When** two runs that the new
   rule permits to overlap do overlap, **Then** neither selects an item the
   other is working and neither closes an issue the other is acting on.
2. **Given** two runs the rule still forbids from overlapping, **When** the
   second is triggered, **Then** it queues rather than racing or cancelling the
   first.
3. **Given** the change is merged, **When** a maintainer reads the concurrency
   block's comment, **Then** it states the guarantee that now holds, not the
   one that used to.

---

### Edge Cases

- **The proof dispatch is displaced from the pending slot.** GitHub keeps at
  most one pending run per concurrency group. While the prove run waits, the
  hourly schedule tick can enter the group and displace the queued proof
  dispatch, which is then cancelled without ever running. The prove step must
  not read that as a failure of the fix (Story 2 scenario 2, Story 3
  scenario 2).
- **A non-board PR closes during a proof wait.** Every `pull_request: closed`
  event in the repository creates a `board-loop` run that joins the group even
  though `prove-gate` will find it ineligible. That run competes for the same
  pending slot.
- **The proof run itself stands down.** A proof re-drive of `board-loop.yml`
  runs the loop's own entry gates: the kill switch, an implement cycle in
  flight (spec 057 FR-049), or an empty eligible board. It can therefore
  conclude `success` having stood down without exercising the changed
  behaviour at all. A stood-down run is not proof.
- **The kill switch is set between the dispatch and the wait.** The prove job
  re-checks the kill switch before any durable action; a dispatch already in
  flight is not recalled by that check.
- **The merge changes both a board helper and a workflow.** Reachability and
  direct-target rules can both match; the chosen target must be deterministic.
- **The proof run picks up the very issue being proven.** The issue stays open
  until proof arrives, so an abandoned proof dispatch that later starts as an
  ordinary iteration may select that same issue and re-triage it from the top
  rather than resuming its prove step.
- **A second dispatchable target appears.** The dispatchable set is one
  workflow today; a future workflow that adds the run-name/attempt-token wiring
  joins it and may not share the board loop's concurrency group. The rule must
  behave correctly for a target outside the caller's own group, not only for
  the self-target.

## Requirements *(mandatory)*

### Functional Requirements — the proof run must be able to start

- **FR-001**: The loop MUST NOT dispatch a proof run that cannot start while
  the dispatching run is alive. Whether a candidate target can start is
  determined before the dispatch, by deterministic code reading the tree
  (Principle IX), never by an agent and never by observing the timeout after
  the fact.
- **FR-002**: The conflict this feature resolves is that the prove step runs
  inside the concurrency group its only re-drive target joins.
  [NEEDS CLARIFICATION: which resolution shape does the owner want? (a) give
  re-drive dispatches their own concurrency group, explicitly narrowing spec
  057 FR-048's "one board item in flight repository-wide" to exclude proof
  runs; (b) scope the board loop's concurrency group per trigger so a
  `pull_request: closed` prove run never holds the item slot, at the cost of a
  prove-vs-selection race on the same issue that then needs its own guard;
  (c) stop waiting synchronously for a self-re-drive — treat a correlated,
  successfully queued dispatch as the proof evidence and revisit FR-043's
  three-way conclusion; (d) accept the current behaviour and specify only the
  legibility and cost requirements below, leaving the re-drive branch
  permanently unable to produce proof.]
- **FR-003**: Whatever resolution is adopted, a proof run that starts MUST
  execute the changed behaviour rather than standing down. A proof run that
  concludes `success` after standing down at an entry gate MUST NOT be recorded
  as proof.
- **FR-004**: The rule MUST be correct for a re-drive target that does **not**
  share the caller's concurrency group, not only for the self-target case.
  A target in an unrelated group MUST continue to be dispatched and waited on
  exactly as today.
- **FR-005**: The re-drive target decision MUST remain deterministic and
  code-derived, with ties broken so that two runs over the same merge choose
  the same target (spec 057 Principle IX commitment, `redrive_target()`'s own
  contract).

### Functional Requirements — what the issue records

- **FR-006**: A dispatched proof run that never left the queued state within
  the wait budget MUST be recorded on the issue as a run that did not start,
  distinctly from a run that started and exhausted the budget while executing.
  Both MUST remain distinct from "nothing in the repository reaches this
  change".
- **FR-007**: A proof dispatch that was cancelled before starting — including
  displacement from the concurrency group's pending slot — MUST be recorded as
  a dispatch that did not run, never as a failing proof.
- **FR-008**: Every no-proof condition MUST leave the issue open carrying its
  own reason, preserving spec 057 FR-043's rule that the issue closes only on
  proof evidence.
- **FR-009**: The recorded reason MUST be sufficient for a maintainer to decide
  whether to look at the fix or at the loop, without leaving the issue
  (spec 057 SC-001).
- **FR-010**: The evidence bar for closing the issue is
  [NEEDS CLARIFICATION: may the issue close on a proof run that was dispatched,
  correlated, and observed to *start*, without the prove step seeing a terminal
  conclusion — with the run URL recorded and the outcome left for a human or a
  later run to read? Or must a terminal conclusion be observed before any
  close, as spec 057 FR-043 requires today? The first makes an asynchronous
  resolution viable and keeps the prove step short; the second keeps "proven"
  meaning "ran green" and needs whatever resolution FR-002 picks to fit inside
  a synchronous wait.]

### Functional Requirements — the abandoned dispatch

- **FR-011**: A proof dispatch the prove step has stopped waiting for MUST NOT
  later run as an unattributable ordinary board iteration. It MUST either not
  start at all, or be attributable — from the run itself and from the issue it
  acts on — to the merge it was dispatched to prove.
- **FR-012**: The cost of an abandoned proof dispatch MUST be visible: the
  wasted wait and any run that results from it MUST appear in the loop's
  existing cost line and durable metrics record, under a run label that names
  the condition (spec 057 FR-047).

### Functional Requirements — reachability of board helper scripts

- **FR-013**: A merged change to a `.github/scripts/**` helper that the loop
  executes MUST receive a re-drive decision whose recorded reason is true.
  "Nothing reaches this change" MUST NOT be recorded for a script the target
  workflow runs on every invocation.
- **FR-014**: The reachability rule for script paths is
  [NEEDS CLARIFICATION: should the uses-graph capture `.github/scripts/**`
  references so a board-helper-only merge re-drives `board-loop.yml` like any
  other Actions-only change — accepting that this routes many more merges into
  the re-drive branch and so depends entirely on FR-002 being resolved first?
  Or should such a merge instead be classified as not needing a re-driven run
  at all, closing on the merged PR's own required checks the way
  `verify-*.py`-only changes already do? Or should it stay out of scope for
  this feature and be filed separately once FR-002 has shipped?]
- **FR-015**: Whichever rule is adopted, it MUST be derived from the checked-out
  tree of the merge commit being proven, so a script or reference added or
  removed by that very merge is accounted for.

### Functional Requirements — the concurrency guarantee

- **FR-016**: The guarantee that replaces or preserves spec 057 FR-048 MUST be
  stated in one sentence in the concurrency block's own comment, and that
  sentence MUST describe the behaviour that actually holds after this change.
- **FR-017**: If the resolution permits two runs to overlap that FR-048
  previously forbade, the feature MUST establish, by a check rather than by
  argument, that the permitted overlap cannot cause two runs to select the same
  item, open two fix PRs for one issue, or close an issue another run is acting
  on.
- **FR-018**: A run that the rule still forbids from overlapping MUST queue,
  never cancel or race, unchanged from FR-048's existing behaviour.

### Functional Requirements — contract and coverage

- **FR-019**: `contracts/prove-step.md` MUST be updated to describe the
  re-drive path that this feature establishes, including the concurrency
  precondition FR-001 introduces, so the contract and the workflow agree.
- **FR-020**: Every new branch this feature adds MUST be exercised by a fixture
  in both its passing and its failing direction, through the existing gate
  registry, running the same subject with the same arguments locally as in CI
  (spec 057 FR-065, Principle VIII).
- **FR-021**: The coverage MUST include an assertion against the repository's
  own real tree, not fixtures alone — the dispatchable set and the concurrency
  relationship between the prove step and its target are exactly the facts that
  went silently wrong once already, with the synthetic fixtures all passing.
- **FR-022**: A merge that proves this feature's own change MUST itself be
  provable by the mechanism the feature ships; the feature MUST NOT leave the
  loop unable to prove a fix to the loop.

### Out of Scope

- Making `release.yml` a dispatchable re-drive target. Its required `version`
  input is why `is_safe_redrive_target()` rejects it; changing that is a
  release-contract decision, not this feature's.
- Changing the board loop's schedule, round budget, turn ceilings, or
  size-and-path backstop thresholds.
- Changing what counts as an Actions-only change for `docs/**`, `specs/**`, or
  `.github/scripts/verify-*.py` paths. Only the script-reachability question of
  FR-013/FR-014 is in scope.
- Changing spec 057 FR-003's rule that a human merges the fix PR, or any part
  of triage, route, fix, review, or readiness.
- Any change to `wing-commander-dispatch-and-wait`'s correlation mechanism
  itself. Its attempt-token correlation is working correctly; the defect is in
  what the board loop asks it to dispatch.

### Key Entities

- **Re-drive target**: the workflow the prove step dispatches to exercise a
  merged change, with the case that selected it, the reason, and — new in this
  feature — whether it can start while the caller is alive.
- **Dispatchable set**: the workflows the composite can dispatch *and*
  correlate unattended. One member today; the feature must behave correctly at
  one member and at more than one.
- **Proof record**: the dispatched run's URL and terminal outcome, or the
  recorded reason no re-drive was required, extended by this feature with the
  reasons a dispatched run produced no outcome — never started, displaced,
  stood down, or abandoned.
- **Concurrency guarantee**: the sentence that says which board-loop runs may
  overlap and which must queue, and the check that holds the loop to it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A merged Actions-only board fix produces a proof run that reaches
  a terminal conclusion the prove step observes — the re-drive branch goes from
  zero working cases to working for every case the dispatchable set admits.
- **SC-002**: No issue closes on proof evidence that names a run which never
  started.
- **SC-003**: Each of the no-proof conditions — never started, displaced,
  stood down, started-but-unfinished, nothing reaches the change — renders a
  distinct, named reason on the issue, verified by a fixture per condition
  rather than by observing production runs.
- **SC-004**: Zero board iterations run against an issue with no record
  anywhere of why that run exists.
- **SC-005**: The time a prove step spends waiting on a proof run that cannot
  start is reduced from the full ~11-minute budget to the time it takes the
  deterministic pre-dispatch check to say so.
- **SC-006**: The statement of which board-loop runs may overlap is the same in
  the concurrency block's comment, in `contracts/prove-step.md`, and in the
  check that enforces it — verified by a gate, not by reading.
- **SC-007**: A maintainer can read an item's proof outcome and its reason from
  the originating issue alone, without opening the Actions tab (spec 057
  SC-001, held for the branches this feature adds).
- **SC-008**: Every branch this feature adds fails its gate when the behaviour
  it checks is mutated, demonstrated by the mutation, not asserted.

## Assumptions

- The board loop keeps a repository-wide simultaneity guarantee of some kind.
  This feature may narrow FR-048's wording, but "any number of board-loop runs
  may race freely" is not an outcome any FR-002 option is read as permitting.
- The human-merge rule (spec 057 FR-003) is unchanged: the prove step is still
  entered by a human's merge reaching the `pull_request: closed` trigger.
- The proof of an Actions-only change is still "a real run of the changed
  behaviour in Actions", not a local re-execution, a simulation, or an agent's
  reading of the diff.
- `wing-commander-dispatch-and-wait` remains the single home for dispatch and
  correlation; anything this feature needs from it is added there rather than
  re-implemented in `board-loop.yml` (CLAUDE.md, "shared logic has exactly one
  home").
- `board_prove.py` remains the single home for the actions-only decision, the
  dispatchable scan, and the target choice; the pre-dispatch check FR-001
  introduces belongs with them rather than in a workflow `run:` block.
- The three `[NEEDS CLARIFICATION]` markers are posted to lifecycle issue
  [#460](https://github.com/charlesguse/wing-commander/issues/460) rather than
  blocking this stage; the clarify stage encodes the owner's answers back into
  this spec.
- FR-014's answer may reasonably be "not in this feature". If so, the
  reachability gap is filed as its own issue carrying the line
  `Found by the code review of #451`, and FR-013/FR-015 and User Story 4 leave
  this spec's scope with it.
