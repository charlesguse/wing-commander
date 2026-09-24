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

### What the owner decided, and what is open again

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
guessed at.

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

**FR-002 and FR-010 are open again.** They were first answered on 2026-09-23 as
"(a) re-drive dispatches get their own concurrency group" and "the evidence bar
is unchanged", and both answers rested on a single premise: that once the group
conflict is removed, the proof run completes inside the prove step's existing
synchronous wait (12 correlation attempts over 60s, then 60 poll attempts over
600s). Both were withdrawn on 2026-09-24, because the review of the draft spec
PR established that the premise does not hold on the current tree. Four facts
now govern any answer, each read off the tree rather than argued:

1. **A proof run that does real work cannot finish inside the wait.** A
   `board-loop.yml` run that works an item runs the triage, route, fix and
   review agents (`max-turns` 15, 25, 60, 30 and 40, across up to
   `BOARD_LOOP_ROUND_BUDGET: 5` fix→review rounds), which takes far longer than
   600s. A run that stands down at an entry gate does finish in time, but a
   stood-down run is not proof (FR-003). So under a synchronous wait, every
   proof run that exercises anything at all ends as "started-but-unfinished".
2. **A dispatched run cannot reach the prove step, and reaches any other stage
   only by chance.** `prove-gate` and `prove` are gated on
   `github.event_name == 'pull_request'` and `select` on
   `github.event_name != 'pull_request'`
   (`.github/workflows/board-loop.yml:76`, `:2356`, `:2478`), so a
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

The asynchronous shape and per-trigger scoping were rejected on the withdrawn
premise, so they are on the table again alongside (a) and accept-as-is. The two
open questions are carried at FR-002 and FR-010 below, and every requirement,
scenario and edge case that had named shape (a) as adopted is stated
resolution-neutrally again until they are answered.

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
   **When** the prove step dispatches the proof run, **Then** that run is able
   to start while the dispatching run is alive rather than queuing behind it, by
   whatever means FR-002's resolution establishes.
2. **Given** that proof run started, **When** it finishes, **Then** its terminal
   conclusion is recorded on the issue with the run URL — by the prove step
   itself, or by whatever observer FR-010's answer names.
3. **Given** the proof run concluded successfully, **When** the outcome is
   recorded, **Then** the issue closes citing that run URL and conclusion,
   exactly as spec 057 FR-043's success branch requires.
4. **Given** the proof run concluded as a failure, **When** the outcome is
   recorded, **Then** the issue stays open carrying the failing run URL,
   unchanged from today's behaviour.

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
part of this feature that would have had to hold under any resolution of
Story 1 — the recorded reason has to be truthful whether or not the proof run
can start.

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
rather than the broken guarantee. How much of it survives depends on FR-002's
answer, and not in the direction first assumed: a separate group for proof
dispatches removes the commonest cause today — a dispatch queued behind its own
caller — but because a dispatched `board-loop.yml` run is a full iteration that
outlasts any wait the caller can afford (see fact 1), it makes "the proof run
carried on as an unrelated iteration" the usual outcome rather than the rare
one. A shape in which no dispatch outlives its caller removes the cause
outright. Under every shape, a proof dispatch displaced from its group's
pending slot by a second one remains possible.

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

Whatever FR-002 resolves to, a maintainer can still state in one sentence what
the loop guarantees about simultaneity — which board-loop runs may overlap and
which must queue — and a fixture holds the loop to it.

**Why this priority**: Spec 057 FR-048 exists because two board iterations
racing can select the same issue, open two fix PRs, or close an issue another
run is still working. A resolution that quietly weakens that to make the proof
run start would trade a visible bug for an invisible one — and because a
dispatched `board-loop.yml` proof run is itself a complete iteration, "let the
proof run overlap" weakens more than it first appears to.

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
  hourly schedule tick, and under any resolution that leaves proof dispatches
  sharing a group with each other, a second merge proven close behind the
  first. The prove step must not read that as a failure of the fix (Story 2
  scenario 2, Story 3 scenario 2).
- **A non-board PR closes during a proof wait.** Every `pull_request: closed`
  event in the repository creates a `board-loop` run that joins the item group
  even though `prove-gate` will find it ineligible. Whether it competes with
  the proof dispatch depends on FR-002's resolution; under every resolution it
  queues behind a prove run that is still waiting.
- **The changed behaviour is in a job a dispatch cannot reach.** A
  `workflow_dispatch` re-drive of `board-loop.yml` runs `select` and whichever
  of triage, route, fix or review the selected item calls for; it never runs
  `prove-gate` or `prove`, which are gated on the `pull_request` event. A
  change to the prove step — this feature's own change among them (FR-022) —
  has no dispatchable path that executes it, and a change to any other stage is
  executed only if `select` happens to pick an item at that stage.
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
  until proof arrives, so a proof run that selects an item may select that same
  issue and re-triage it from the top rather than resuming its prove step, as
  may an ordinary iteration running alongside it under any resolution that lets
  the two overlap. FR-017's check covers exactly this case.
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
  [NEEDS CLARIFICATION: which resolution shape does the owner want, now that a
  dispatched `board-loop.yml` proof run is known to be a full board iteration
  that runs agents for far longer than the prove step's 600s wait and that
  cannot reach the `prove` job at all? (a) give re-drive dispatches their own
  concurrency group — which admits two complete board iterations at once, so it
  revokes rather than narrows spec 057 FR-048, turns FR-017's guard into a
  cross-run in-flight check, doubles concurrent agent spend, and makes an
  abandoned dispatch carrying on as an unrelated iteration (FR-011) the usual
  outcome rather than a rare one; (b) scope the board loop's concurrency group
  per trigger so a `pull_request: closed` prove run never holds the item slot —
  narrower than (a) in that only the prove run's own grip on the group changes,
  at the cost of a prove-vs-selection race on the same issue that needs its own
  guard, and still leaving the proof run a full iteration the caller cannot
  outlast; (c) stop waiting synchronously for a self-re-drive — treat a
  correlated, successfully queued or started dispatch as the evidence and let a
  later run or a human read the conclusion, the only shape fact 1 leaves
  intact, at the cost of reopening FR-010 and spec 057 FR-043's three-way
  conclusion; (d) re-drive only the changed behaviour rather than a whole board
  iteration — a proof run directed at the changed stage, the only shape that
  answers fact 2 and could finish inside a bounded wait, but needing a way to
  direct a run at one stage that does not exist in the tree today; (e) accept
  the current behaviour and specify only the legibility and cost requirements
  below, leaving the re-drive branch permanently unable to produce proof.
  Whichever is chosen MUST also say how a proof run is directed at the changed
  behaviour, or what counts as proof when it cannot be — including for a change
  to the prove step itself (FR-022).]
  Whatever shape is adopted MUST state what it does to spec 057 FR-048's "one
  board item in flight repository-wide" — hold it, narrow it, or revoke it —
  and MUST leave the serialization of triage, route, fix, review and readiness
  otherwise unchanged.
- **FR-003**: Whatever resolution is adopted, a proof run that starts MUST
  execute the changed behaviour rather than merely starting. A proof run that
  concludes `success` after standing down at an entry gate MUST NOT be recorded
  as proof, and neither MUST a proof run that started, selected an unrelated
  item, and exercised a stage the merge did not change.
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
  correlated, and observed to *start*, without a terminal conclusion having been
  observed — with the run URL recorded and the outcome left for a human or a
  later run to read? Or must a terminal conclusion be observed before any close,
  as spec 057 FR-043 requires today? This was answered "a terminal conclusion
  must be observed" on 2026-09-23, on the premise that removing the group
  conflict lets the proof run finish inside the existing ~11-minute synchronous
  wait. That premise does not hold: a proof run that works an item runs agents
  for far longer than the wait (fact 1), so under an unchanged bar and a
  synchronous wait every real proof ends as started-but-unfinished under FR-006
  and no Actions-only issue ever closes on proof evidence. So: (a) keep the
  terminal-conclusion bar and require FR-002 to pick a shape whose proof run
  genuinely finishes inside a bounded wait; (b) keep the bar but let the
  conclusion be observed by something other than the dispatching prove step — a
  later board run, or a follow-up triggered by the proof run's completion —
  which closes the issue asynchronously and needs that observer named and
  specified; (c) lower the bar to "dispatched, correlated, and observed to
  start", recording the run URL and leaving the conclusion for a human to read;
  (d) keep the bar and accept that an Actions-only board issue closes only when
  a human reads the proof run and says so. Whichever is chosen MUST also say
  what "proven" means for a change no dispatch can direct a run at (fact 2).]

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
- **FR-014**: The uses-graph MUST capture `.github/scripts/**` references, so a
  merge that changes only a board helper selects the dispatchable workflow that
  references that script and is re-driven like any other Actions-only change,
  rather than recording "nothing reaches this change". This routes many more
  merges into the re-drive branch, which is safe only because FR-002's
  resolution lands in the same feature; FR-014 MUST NOT ship ahead of FR-002.
- **FR-015**: The reachability rule MUST be derived from the checked-out
  tree of the merge commit being proven, so a script or reference added or
  removed by that very merge is accounted for.

### Functional Requirements — the concurrency guarantee

- **FR-016**: Whatever simultaneity guarantee holds after this change — which
  board-loop runs may overlap and which must queue — MUST be stated in one
  sentence in every concurrency block's own comment, and that sentence MUST
  describe the behaviour that actually holds afterwards rather than the one
  that used to.
- **FR-017**: For every overlap FR-002's resolution permits that spec 057
  FR-048 forbids today, the feature MUST establish by a check, rather than by
  argument, that the overlap cannot (a) cause the two runs to act on the same
  issue as their board item, (b) result in two fix PRs open for one issue, or
  (c) let either run close an issue the other is acting on. The check MUST
  cover the specific case that the issue being proven is still open — and
  therefore still eligible for ordinary selection — while its proof run is in
  flight. Where the permitted overlap is between two complete board iterations,
  the check MUST hold across two concurrent runs, not only within one.
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
  on FR-002's answer rather than a detail: a `workflow_dispatch` re-drive of
  `board-loop.yml` never reaches the prove step, so a resolution that only
  dispatches `board-loop.yml` cannot prove this feature's own change and MUST
  say what does.

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

- **SC-001**: A merged Actions-only board fix produces a recorded proof outcome
  that is a statement about the fix rather than about a queue, under the
  evidence bar FR-010 settles — the re-drive branch goes from zero working
  cases to working for every case the dispatchable set admits.
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
  the concurrency blocks' comments, in `contracts/prove-step.md`, and in the
  check that enforces it — verified by a gate, not by reading.
- **SC-009**: A change to the prove step itself is either exercised by a proof
  run or recorded as unprovable with the reason; it is never recorded as proven
  by a run that could not have executed it.
- **SC-007**: A maintainer can read an item's proof outcome and its reason from
  the originating issue alone, without opening the Actions tab (spec 057
  SC-001, held for the branches this feature adds).
- **SC-008**: Every branch this feature adds fails its gate when the behaviour
  it checks is mutated, demonstrated by the mutation, not asserted.

## Assumptions

- The board loop keeps some stated, checked repository-wide simultaneity
  guarantee. FR-002's answer may hold, narrow or revoke FR-048's current
  wording, but "any number of board-loop runs may race freely, unchecked" is
  not an acceptable outcome.
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
  was shown not to hold; both markers are open again and carry the four facts
  that now govern them. Two clarifications remain open; see "What the owner
  decided, and what is open again".
- FR-014 was answered in favour of capturing `.github/scripts/**`, and that
  answer was confirmed again on 2026-09-24, so the reachability gap stays in
  this feature: User Story 4, FR-013 and FR-015 are in scope and no separate
  reachability issue is filed. The ordering caveat that answer carries —
  FR-014 must not ship ahead of FR-002 — is internal to this feature, which
  delivers both.
