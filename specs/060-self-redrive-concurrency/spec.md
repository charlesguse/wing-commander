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
chosen resolution leaves them unchanged. The same pending-slot rule can also
cancel the `pull_request: closed` run that would have hosted the prove step
itself. FR-010b covers that case.

### What the owner decided

The lifecycle issue is explicit that this needs an owner decision rather than a
unilateral fix, and names three candidate shapes — a separate concurrency group
for re-drive dispatches, not waiting synchronously for a self-re-drive, or
accepting the current timeout-then-unrelated-run behaviour. A fourth shape the
issue does not name — scoping the concurrency group per trigger so a prove run
never holds the item slot — is cheaper but introduces a prove-vs-selection race
on the same issue. A fifth, raised on the second pass, is a proof run that
executes only the changed behaviour instead of a whole board iteration. The
three questions were posted to lifecycle issue
[#460](https://github.com/charlesguse/wing-commander/issues/460) rather than
guessed at, and all three are now answered.

**FR-014 is decided.** Board helper scripts join the uses-graph: the graph
captures `.github/scripts/**` references, so a board-helper-only merge
re-drives its wrapper like any other Actions-only change. Every `board_*.py`
helper is exercised on every iteration, so "nothing reaches this change" is
simply false for a script-only merge today. That option's own caveat — that
routing more merges into the re-drive branch is safe only once FR-002 has
shipped — is satisfied by both landing in this feature, so the ordering is
internal to it rather than something a follow-up has to get right later. User
Story 4, FR-013 and FR-015 therefore stay in this spec's scope. The answer was
confirmed again on 2026-09-24 and is not re-opened.

**FR-002 and FR-010 were re-answered on 2026-09-24.** They were first answered
on 2026-09-23 as "(a) re-drive dispatches get their own concurrency group" and
"the evidence bar is unchanged", and both answers rested on a single premise:
that once the group conflict is removed, the proof run completes inside the
prove step's existing synchronous wait (12 correlation attempts over 60s, then
60 poll attempts over 600s). Both were withdrawn on 2026-09-24, because the
review of the draft spec PR established that the premise does not hold on the
current tree. Four facts, each read off the tree rather than argued, govern the
answers that replaced them:

1. **A proof run that does real work cannot finish inside the wait.** A
   `board-loop.yml` run that works an item runs the triage, route, fix and
   review agents (`max-turns` 15, 25, 60, 30 and 40, across up to
   `BOARD_LOOP_ROUND_BUDGET: 5` fix→review rounds), which takes far longer than
   600s. A run that stands down at an entry gate does finish in time, but a
   stood-down run is not proof (FR-003). So under a synchronous wait, every
   proof run that exercises anything at all ends as "started-but-unfinished".
2. **A dispatched run cannot reach the prove step, and reaches any other stage
   only by chance.** `prove-gate` is gated on
   `github.event_name == 'pull_request'`, `prove` runs only when `prove-gate`
   reports the item eligible, and `select` is gated on
   `github.event_name != 'pull_request'`
   (`.github/workflows/board-loop.yml:76`, `:2283`, `:2405`), so a
   `workflow_dispatch` re-drive of `board-loop.yml` can never exercise a change
   to the prove step itself — including this feature's own change, which FR-022
   requires be provable — and which of triage, route, fix or review it does
   exercise depends on the issue `select` happens to pick.
3. **A separate concurrency group admits two full board iterations at once.** A
   proof dispatch of `board-loop.yml` is itself a complete iteration: it
   selects an item, runs agents, and may open a fix PR. Shape (a) therefore
   revokes spec 057 FR-048 rather than narrowing it, makes FR-017's guard a
   cross-run in-flight detection problem rather than a within-run check, and
   doubles concurrent agent spend.
4. **A proof run that outlives the wait carries on as an unrelated
   iteration.** Under shape (a) that is the usual outcome rather than a rare
   one, and it is exactly the Story 3 behaviour FR-011 forbids.

**FR-002 is decided: the directed proof run.** The loop re-drives *only the
changed behaviour*, not a whole board iteration — a proof run directed at the
changed stage. A directed proof run is not a board iteration: it does not select
a board item and it does not open a fix PR. Spec 057 FR-048's "one board item in
flight repository-wide" therefore **holds unchanged** — it is neither narrowed
nor revoked, because the only run this feature lets overlap a board-loop run
takes no board item. The directed run MUST be able to exercise the prove step
itself, so that this feature's own change is provable (FR-022); that is a
constraint on the mechanism, answering fact 2. Facts 1, 3 and 4 are what ruled
out the alternatives: a whole-iteration proof run cannot finish inside a bounded
wait, a separate group for it admits two complete iterations at once, and an
abandoned one carries on as the unrelated iteration FR-011 forbids. No way to
direct a run at one stage exists in the tree today; building it is this
feature's work.

**FR-010 is decided: the terminal-conclusion bar is kept.** The issue closes
only on an observed terminal conclusion, exactly as spec 057 FR-043 requires
today. This is consistent with FR-002 only because a directed proof run is
bounded: it MUST finish inside a bounded wait, and the prove step itself MUST
observe its conclusion before the issue closes. No asynchronous observer is
introduced, and the bar is not lowered to "observed to start".

**The fallback, for a change no directed run can reach.** When no directed run
reaches the changed behaviour, the prove step records on the issue that no
directed run reaches it, names what changed, and leaves the issue open. A human
reads the evidence and closes it. The loop never closes such an issue unattended,
and it never dispatches a full board iteration as a stand-in for proof.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A merged Actions-only fix gets a proof run that can actually start (Priority: P1)

A maintainer merges a board fix PR whose change only runs inside Actions. The
loop re-drives a run to prove it. That run starts, executes the changed
behaviour, and reaches a terminal conclusion that gets recorded — so what the
issue ends up saying is a statement about the fix rather than a statement about
a queue.

**Why this priority**: This is the defect. Today the re-drive branch cannot
succeed for any change, which means no Actions-only board fix can ever be
proven, which means no such issue can ever close on proof evidence. Every other
story in this spec is a consequence of getting this one right.

**Independent Test**: Merge a PR that changes only Actions-only behaviour
reachable from the loop, and observe that the proof run leaves the queued state
and that its terminal conclusion is recorded on the issue.

**Acceptance Scenarios**:

1. **Given** a merged fix PR whose changed paths make `actions_only` true and
   whose re-drive target is the same workflow the prove step is running in,
   **When** the prove step dispatches the directed proof run, **Then** that run
   is able to start while the dispatching run is alive rather than queuing
   behind it, and it takes no board item.
2. **Given** that directed proof run started, **When** it finishes — which it
   does inside the prove step's bounded wait — **Then** the prove step itself
   observes its terminal conclusion and records it on the issue with the run
   URL.
3. **Given** the proof run concluded successfully, **When** the outcome is
   recorded, **Then** the issue closes citing that run URL and conclusion,
   exactly as spec 057 FR-043's success branch requires.
4. **Given** the proof run concluded as a failure, **When** the outcome is
   recorded, **Then** the issue stays open carrying the failing run URL,
   unchanged from today's behaviour.

---

### User Story 2 - A proof that could not be produced says why, in terms a maintainer can act on (Priority: P1)

A maintainer reading the issue can tell the difference between "the proof run
ran and the fix is not proven", "the proof run could not start", "nothing in
the repository reaches this change", and "no directed run reaches the changed
behaviour, so a human has to read the evidence". Today the first two are both
rendered as `conclusion=timeout` against a plausible-looking run URL.

**Why this priority**: Spec 057 SC-001 promises the whole item history is
readable from the issue alone. A timeout that actually means "the loop
dispatched into its own queue" sends the maintainer to look at the fix, which
is fine, instead of at the loop, which is where the problem is. It is also the
part of this feature that would have had to hold under any resolution of
Story 1 — the recorded reason has to be truthful whether or not the proof run
can start.

**Independent Test**: Force each of the no-proof conditions and read the issue
comment for each; each must name its own distinct condition.

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
4. **Given** a merged change that no directed proof run can be aimed at,
   **When** the prove step records the outcome, **Then** the issue comment says
   so, names what changed, and the issue stays open for a human to read the
   evidence and close — distinctly from the three conditions above, and never
   as a proof produced by a full board iteration run as a stand-in.
5. **Given** any of the above, **When** the maintainer reads the issue, **Then**
   the recorded reason is enough to decide whether to re-run the proof, to look
   at the fix, or to close the issue by hand, without opening the Actions tab.

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
rather than the broken guarantee. FR-002's resolution removes the cause rather
than containing it: a directed proof run takes no board item and opens no fix
PR, so even one that outlives the caller's wait cannot become someone else's
board iteration. What remains to be specified is that this holds by
construction and is checked — and that a proof dispatch displaced from its
group's pending slot, which stays possible, is not read as a failing proof.

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

### User Story 4 - A board helper script a merge changed is reachable (Priority: P2)

A merged PR that changes only a `.github/scripts/board_*.py` helper gets a
recorded decision that reflects reality: the loop executes that script on every
run, so it is re-driven like any other Actions-only change rather than filed
under "nothing reaches this change".

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
   **When** the prove step decides the re-drive target, **Then** it selects the
   dispatchable workflow that references that script — never "nothing reaches
   this change" — and records the reason on the issue.
2. **Given** the reachability rule now admits script paths, **When** the target
   is chosen, **Then** it is chosen deterministically from the tree, with ties
   broken the same way for two runs over the same merge.

---

### User Story 5 - One board item in flight is still a guarantee a maintainer can rely on (Priority: P1)

A maintainer can state in one sentence what the loop guarantees about
simultaneity — which board-loop runs may overlap and which must queue — and a
fixture holds the loop to it. After this change that sentence still says one
board item is in flight repository-wide; the only thing that may overlap a
board-loop run is a directed proof run, which takes no item.

**Why this priority**: Spec 057 FR-048 exists because two board iterations
racing can select the same issue, open two fix PRs, or close an issue another
run is still working. A resolution that quietly weakened that to make the proof
run start would have traded a visible bug for an invisible one — and because a
dispatched `board-loop.yml` proof run is itself a complete iteration, "let the
proof run overlap" would have weakened more than it first appears to. The
directed shape avoids that trade, but only if "takes no board item" is checked
rather than asserted.

**Independent Test**: State the post-change guarantee and exercise the pairs it
permits and the pairs it forbids.

**Acceptance Scenarios**:

1. **Given** any pair of runs the post-change guarantee permits to overlap,
   **When** both are in flight, **Then** neither acts on an item the other is
   working, no second fix PR is opened for one issue, and neither closes an
   issue the other is acting on.
2. **Given** any pair the post-change guarantee forbids from overlapping,
   **When** the second is triggered, **Then** it queues rather than racing or
   cancelling the first.
3. **Given** the change is merged, **When** a maintainer reads the concurrency
   block's comment, **Then** it states the guarantee that now holds, not the
   one that used to.

---

### Edge Cases

- **The proof dispatch is displaced from the pending slot.** GitHub keeps at
  most one pending run per concurrency group, so a queued proof dispatch is
  cancelled without ever running when a later one takes the slot — today the
  hourly schedule tick, and if directed proof runs share a group with each
  other, a second merge proven close behind the first. The prove step must not
  read that as a failure of the fix (Story 2 scenario 2, Story 3 scenario 2).
- **The prove run itself is displaced.** A board fix PR's `pull_request:
  closed` run can go pending in the item group and then be cancelled when the
  hourly tick or another PR's close takes the pending slot. No prove step
  runs for that merge, so nothing on the issue explains the missing proof
  unless something else records it (FR-010b).
- **Two directed proof runs contend for one group.** When two merges are
  proven close together, the second target group is already occupied. The
  prove step learns this before dispatching (FR-001a), rather than after a
  full wait.
- **A non-board PR closes during a proof wait.** Every `pull_request: closed`
  event in the repository creates a `board-loop` run that joins the item group
  even though `prove-gate` will find it ineligible. It queues behind a prove run
  that is still waiting; it does not compete with the directed proof run, which
  does not hold the item group.
- **The changed behaviour is in a job an undirected dispatch cannot reach.** A
  plain `workflow_dispatch` re-drive of `board-loop.yml` runs `select` and
  whichever of triage, route, fix or review the selected item calls for; it
  never runs `prove-gate` or `prove`, which are gated on the `pull_request`
  event. This is why FR-002's resolution directs the proof run at the changed
  stage, and why FR-022 requires that the prove step itself be among the stages
  a directed run can exercise.
- **No directed run reaches the changed behaviour.** Where the changed stage is
  one the directed mechanism cannot aim at, the prove step records that fact and
  what changed, leaves the issue open for a human, and does not fall back to
  dispatching a whole board iteration.
- **The directed proof run stands down.** A directed run must not be admitted
  as proof merely for concluding `success`: if the loop's own entry gates — the
  kill switch, an implement cycle in flight (spec 057 FR-049) — stop it before
  the changed behaviour executes, it has proved nothing. A stood-down run is not
  proof.
- **The kill switch is set between the dispatch and the wait.** The prove job
  re-checks the kill switch before any durable action; a dispatch already in
  flight is not recalled by that check.
- **The merge changes both a board helper and a workflow.** Reachability and
  direct-target rules can both match; the chosen target must be deterministic.
- **The proof run picks up the very issue being proven.** The issue stays open
  until proof arrives, so a proof run that selected an item could select that
  same issue and re-triage it from the top rather than resuming its prove step.
  A directed proof run selects no item, which is what forecloses this; FR-017's
  check is what establishes that it selects none.
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
- **FR-001a**: The tree alone cannot say whether the target's concurrency
  group is free *now*: another directed proof run may already be running or
  pending in it, and a dispatch would then queue behind that run or displace
  it. Before dispatching, the prove step MUST read the target group's current
  state from the Actions API, using deterministic code rather than an agent.
  If the group is occupied, it MUST record a distinct "proof group busy"
  reason on the issue instead of dispatching into a wait it cannot win, and
  leave the issue open (FR-008).
- **FR-002**: The conflict this feature resolves is that the prove step runs
  inside the concurrency group its only re-drive target joins. The resolution is
  that the loop re-drives **only the changed behaviour**, not a whole board
  iteration: the prove step dispatches a *directed proof run* aimed at the stage
  the merge changed. A directed proof run MUST NOT select a board item and MUST
  NOT open a fix PR, and MUST be able to start while the dispatching run is
  alive. Spec 057 FR-048's "one board item in flight repository-wide"
  **holds unchanged** — neither narrowed nor revoked — because the only run this
  feature permits to overlap a board-loop run takes no board item; and the
  serialization of triage, route, fix, review and readiness is otherwise
  unchanged.
- **FR-002a**: The directed proof run MUST be able to exercise the prove step
  itself, not only the stages a plain `workflow_dispatch` of `board-loop.yml`
  can reach today (fact 2), so that a change to the prove step — including this
  feature's own — is provable (FR-022).
- **FR-002b**: The loop MUST NOT dispatch a whole board iteration as a stand-in
  for proof under any condition, including the condition of FR-010a where no
  directed run reaches the changed behaviour.
- **FR-003**: A proof run that starts MUST execute the changed behaviour rather
  than merely starting. A proof run that concludes `success` after standing down
  at an entry gate MUST NOT be recorded as proof, and neither MUST a run that
  started but exercised a stage the merge did not change.
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
  change" and from FR-010a's "no directed run reaches this changed behaviour".
- **FR-007**: A proof dispatch that was cancelled before starting — including
  displacement from the concurrency group's pending slot — MUST be recorded as
  a dispatch that did not run, never as a failing proof.
- **FR-008**: Every no-proof condition MUST leave the issue open carrying its
  own reason, preserving spec 057 FR-043's rule that the issue closes only on
  proof evidence.
- **FR-009**: The recorded reason MUST be sufficient for a maintainer to decide
  whether to look at the fix or at the loop, without leaving the issue
  (spec 057 SC-001).
- **FR-010**: The evidence bar for closing the issue is unchanged from spec 057
  FR-043: a terminal conclusion MUST be observed before the issue closes on
  proof evidence. "Dispatched, correlated and observed to start" is NOT
  sufficient. The dispatching prove step itself MUST be the observer — no later
  board run and no completion-triggered follow-up is introduced — which is
  consistent with FR-002 only because a directed proof run is bounded: it MUST
  reach a terminal conclusion inside the prove step's wait budget, and the
  feature MUST establish that bound rather than assume it.
- **FR-010a**: Where no directed proof run can be aimed at the changed
  behaviour, the prove step MUST record on the issue that no directed run
  reaches it, name what changed, and leave the issue open. Closing such an issue
  is a human's act after reading the evidence; the loop MUST NOT close it
  unattended, and MUST NOT substitute a whole board iteration for the directed
  run (FR-002b). This condition MUST be recorded distinctly from "nothing in
  the repository reaches this change" (FR-006).
- **FR-010b**: The `pull_request: closed` run that hosts the prove step can
  itself be cancelled from the item group's pending slot before it starts:
  the hourly schedule tick or another PR's close event takes the slot. In that
  case no prove step exists to record anything. Such a merge MUST NOT leave
  its issue open with no record. Deterministic code MUST detect a merged board
  fix PR whose issue carries neither a proof record nor a prove-step marker,
  and record that on the issue as a displaced prove run. That record MUST be
  distinct from every FR-006/FR-007 reason and MUST leave the issue open. The
  detecting mechanism is left to plan; it MUST NOT be an agent's judgement
  (Principle IX).

### Functional Requirements — the abandoned dispatch

- **FR-011**: A proof dispatch the prove step has stopped waiting for MUST NOT
  later run as an unattributable ordinary board iteration. Under FR-002's
  directed shape this holds by construction — a directed proof run selects no
  board item — and the feature MUST establish that by a check rather than by
  argument (FR-017). A directed proof run MUST additionally be attributable,
  from the run itself and from the issue, to the merge it was dispatched to
  prove.
- **FR-012**: The cost of an abandoned proof dispatch MUST be visible: the
  wasted wait and any run that results from it MUST appear in the loop's
  existing cost line and durable metrics record, under a run label that names
  the condition (spec 057 FR-047).

### Functional Requirements — reachability of board helper scripts

- **FR-013**: A merged change to a `.github/scripts/**` helper that the loop
  executes MUST receive a re-drive decision whose recorded reason is true.
  "Nothing reaches this change" MUST NOT be recorded for a script the target
  workflow runs on every invocation.
- **FR-014**: The uses-graph MUST capture every way a workflow executes a
  `.github/scripts/**` helper, not only a literal path. Most board helpers
  are loaded as Python modules (`sys.path.insert(0, '.github/scripts')`
  followed by `from board_item_marker import …`) and never appear as a
  `.github/scripts/<name>.py` path in `board-loop.yml`. So the graph MUST
  resolve module imports, including imports between helpers, and helpers
  executed inside a composite the workflow uses. A merge that changes only a
  board helper then aims a directed proof run (FR-002) at the stage or stages
  that execute that helper, rather than recording "nothing reaches this
  change". FR-021's real-tree assertion MUST include that every
  `.github/scripts/board_*.py` helper resolves to at least one stage. This routes many more
  merges into the re-drive branch, which is safe only because FR-002's
  resolution lands in the same feature; FR-014 MUST NOT ship ahead of FR-002.
- **FR-015**: The reachability rule MUST be derived from the checked-out
  tree of the merge commit being proven, so a script or reference added or
  removed by that very merge is accounted for.

### Functional Requirements — the concurrency guarantee

- **FR-016**: The simultaneity guarantee that holds after this change — one
  board item in flight repository-wide, with a directed proof run, which takes
  no item, the only run permitted to overlap a board-loop run — MUST be stated
  in one sentence in every concurrency block's own comment, and that sentence
  MUST describe the behaviour that actually holds afterwards rather than the one
  that used to.
- **FR-017**: The one overlap FR-002 permits that spec 057 FR-048 forbids today
  is a directed proof run running alongside the prove run that dispatched it.
  The feature MUST establish by a check, rather than by argument, that this
  overlap cannot (a) cause the two runs to act on the same issue as their board
  item, (b) result in two fix PRs open for one issue, or (c) let either run
  close an issue the other is acting on. The check MUST cover the specific case
  that the issue being proven is still open — and therefore still eligible for
  ordinary selection — while its proof run is in flight. Because the directed
  run's not selecting an item and not opening a fix PR is what makes all three
  hold, that property in particular MUST be checked, not assumed.
- **FR-018**: Any pair of runs the post-change rule forbids from overlapping
  MUST queue, never cancel or race, unchanged from FR-048's existing behaviour.

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
  loop unable to prove a fix to the loop. Fact 2 above makes this a constraint
  on the directed mechanism rather than a detail: a plain `workflow_dispatch`
  re-drive of `board-loop.yml` never reaches the prove step, so the directed
  proof run MUST be able to exercise the prove step itself (FR-002a). Falling
  back to FR-010a's human-read path for this feature's own change does NOT
  satisfy FR-022.

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
  feature — whether it can start while the caller is alive, and which changed
  stage the run is directed at.
- **Directed proof run**: a run aimed at the stage a merge changed, which
  selects no board item and opens no fix PR, reaches a terminal conclusion
  inside the prove step's wait budget, and is attributable to the merge it
  proves. It is the only run permitted to overlap a board-loop run.
- **Dispatchable set**: the workflows the composite can dispatch *and*
  correlate unattended. One member today; the feature must behave correctly at
  one member and at more than one.
- **Proof record**: the dispatched run's URL and terminal outcome, or the
  recorded reason no re-drive was required, extended by this feature with the
  reasons a dispatched run produced no outcome — never started, displaced,
  stood down, or abandoned — and with the reason no run was dispatched at all:
  no directed run reaches the changed behaviour.
- **Concurrency guarantee**: the sentence that says which board-loop runs may
  overlap and which must queue, and the check that holds the loop to it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A merged Actions-only board fix produces a recorded proof outcome
  that is a statement about the fix rather than about a queue, under the
  unchanged terminal-conclusion evidence bar (FR-010) — the re-drive branch goes
  from zero working cases to working for every changed stage a directed proof
  run can be aimed at, with the rest recorded under FR-010a rather than
  mis-recorded.
- **SC-002**: No issue closes on proof evidence that names a run which never
  started.
- **SC-003**: Each of the no-proof conditions — never started, displaced,
  stood down, started-but-unfinished, nothing reaches the change, no directed
  run reaches the changed behaviour, proof group busy (FR-001a), prove run
  displaced (FR-010b) — renders a distinct, named reason on the
  issue, verified by a fixture per condition rather than by observing production
  runs.
- **SC-004**: Zero board iterations run against an issue with no record
  anywhere of why that run exists, and zero proof dispatches take a board item.
- **SC-005**: The time a prove step spends waiting on a proof run that cannot
  start is reduced from the full ~11-minute budget to the time it takes the
  deterministic pre-dispatch checks (FR-001's tree check and FR-001a's
  runtime check of the target group) to say so.
- **SC-006**: The statement of which board-loop runs may overlap is the same in
  the concurrency blocks' comments, in `contracts/prove-step.md`, and in the
  check that enforces it — verified by a gate, not by reading.
- **SC-009**: A change to the prove step itself is exercised by a directed proof
  run (FR-002a); it is never recorded as proven by a run that could not have
  executed it, and never left to FR-010a's human-read path (FR-022).
- **SC-007**: A maintainer can read an item's proof outcome and its reason from
  the originating issue alone, without opening the Actions tab (spec 057
  SC-001, held for the branches this feature adds).
- **SC-008**: Every branch this feature adds fails its gate when the behaviour
  it checks is mutated, demonstrated by the mutation, not asserted.

## Assumptions

- The board loop keeps a stated, checked repository-wide simultaneity
  guarantee. FR-002's answer holds FR-048's current wording unchanged — one
  board item in flight repository-wide — because a directed proof run takes no
  board item.
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
- The three `[NEEDS CLARIFICATION]` markers were posted to lifecycle issue
  [#460](https://github.com/charlesguse/wing-commander/issues/460) rather than
  blocking the intake stage, and were answered there on 2026-09-23. The FR-002
  and FR-010 answers were withdrawn on 2026-09-24 when the premise they rested
  on — that a proof run completes inside the prove step's synchronous wait —
  was shown not to hold, and were re-answered the same day against the four
  facts that now govern them. No clarification remains open; see "What the owner
  decided".
- A mechanism for directing a run at one stage of the board loop does not exist
  in the tree today. FR-002's resolution requires one, including a path that
  reaches the prove step, and building it is this feature's work rather than a
  precondition it can assume.
- FR-014 was answered in favour of capturing `.github/scripts/**`, and that
  answer was confirmed again on 2026-09-24, so the reachability gap stays in
  this feature: User Story 4, FR-013 and FR-015 are in scope and no separate
  reachability issue is filed. The ordering caveat that answer carries —
  FR-014 must not ship ahead of FR-002 — is internal to this feature, which
  delivers both.
