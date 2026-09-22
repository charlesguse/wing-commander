# Feature Specification: Converged Means No Task Is Left — The Cycle Signal Reads tasks.md

**Feature Branch**: `059-converged-means-tasks-done`

**Created**: 2026-09-22

**Status**: Draft

**Input**: Lifecycle issue [#450](https://github.com/charlesguse/wing-commander/issues/450) — "implement: a cycle that stops with unchecked tasks is reported converged, so finalize runs on unfinished work"

## Context

The implement stage decides whether a build-and-reassess cycle converged from
one fact and one fact only: whether a `converge:`-prefixed commit touching
`tasks.md` landed in the cycle's commit range. No such commit ⇒ `converged=true`
⇒ dispatch finalize. That reading is in the stage's own header comment
(`implement.yml:5-9`), in the `Read back cycle outcome` step
(`implement.yml:1273-1287`) and in its retry-arm twin (`1824-1838`), and in
`docs/architecture.md`'s stage-4 description.

It is a proxy, and spec 057's cycle 1 is where the proxy came apart. Per the
lifecycle issue: the cycle stopped **on its own** at 79 of 180 turns, having
finished T001–T011 (phases 1 and 2), and said in its closing message that
phases 3–10 (T012–T065, 54 unchecked tasks) were "deferred to future cycles".
The converge pass then reported `Converged` with `tasks.md` unchanged, and it
was right to: every remaining requirement already traced to an existing
unchecked task, so there was no *gap in coverage* for converge to append —
only remaining *completion*. Converge's contract is append-only; work that is
already a task is outside its remit.

So the stage saw no `converge:` commit, posted "Converged. Ready for finalize",
and dispatched finalize with 54 of 65 tasks unchecked. Nothing dispatches the
cycles the agent deferred to, because the only path to another cycle is
`converged=false`, and that requires a converge commit converge correctly did
not write. The owner re-dispatched cycle 2 by hand.

**Why this is a stage defect, not an agent mistake.** "Implement stopped with
tasks left" is a state neither party owns: the implement agent chose to stop,
converge only adds tasks, and the stage's signal cannot see it. A cycle that
ends healthy — not truncated, not failed — with unchecked tasks in `tasks.md`
is not converged, whatever the agent concluded. Under Principle IX, the
judgment that gates a durable action (dispatching finalize) belongs in
deterministic code reading the tree, not in the agent's closing message.

`docs/architecture.md:1330` already carries this as a known risk —
*"Converge 'unchanged tasks.md' is syntactic, not semantic | Iteration cap +
final converge report always posted to the issue"*. The accepted mitigation
was the cap. This run shows why it does not hold: the premature signal skips
the loop entirely, so the cap is never approached and the final converge
report describes a spec that is 11/65 built.

Specs 056 and 058 did not hit it. Their cycle 1 ran to the turn budget and
into the retry arm, so `truncated` forced `converged=false` (spec 040's
carry-forward) and the agent never got to choose to stop early.

### The part the issue names as the owner's call, and why it is bigger than it looks

The lifecycle issue proposes the deterministic signal, notes the prompt
alternative, and flags one trade-off to settle first: the cycle cap. Cycle 1
finished 11 tasks in 79 turns, so 65 tasks need roughly six cycles against a
default `max-iterations` of 5, and "a task that can never be completed would
loop to the cap".

Reading this repository's own `specs/` shows that last clause is not a corner
case but the common shape. **19 of the specs on `main` carry unchecked
`- [ ]` tasks in a finished `tasks.md`** (59 items total), and the ones that
remain are overwhelmingly work no cycle can do:

| spec | example leftover |
|---|---|
| 054-e2e-container-coverage (9) | `T007 … dispatch auto-release.yml on a day whose derived mode is container … record the run URL as evidence` |
| 052-agent-credential-lifetime (3) | a deferred gate self-test entry point, annotated in place as "deferred; out of proportion for this pass" |
| 044-private-registry-credentials (6), 055-unattended-e2e-gates (4), 058-per-job-minute-floor (4) | same shape — observe a real dispatched run, set a repository secret, watch a scheduled day arrive |

Finalize already knows about these: its summary agent is told to list "every
`tasks.md` item that is still unchecked (`- [ ]`), plus any checked item whose
text marks it as inherently human-only work (e.g. review, merge, deploy,
credential/secret setup) that no agent can complete"
(`finalize.yml:716-721`). That is the honest end state for such a spec — and
it means a bare "no unchecked task ⇒ converged" rule would send roughly a
third of this repository's specs around the loop until the cap every single
time, burning four extra agent cycles on the shared usage window to arrive at
the same non-converged finalize. The gap this feature closes is real; the rule
that closes it has to tell "a later cycle will finish this" apart from "no
cycle ever will", and that distinction is the one open question below.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A cycle that stops with work left gets another cycle (Priority: P1)

A cycle ends healthy — the agent exited cleanly, well inside its turn budget —
having ticked some tasks and left others. Converge finds no coverage gap and
writes nothing. The stage does not call this converged: it reads `tasks.md` on
the spec branch, sees unchecked tasks, reports `converged=false`, and
dispatches the next cycle. Finalize is not reached, and the owner does not
re-dispatch anything by hand.

**Why this priority**: it is the defect. Without it the pipeline hands
unfinished work to finalization and stops, and the only thing that notices is
a human reading the tasks list.

**Independent Test**: drive the stage's outcome and dispatch logic against a
branch whose `tasks.md` has unchecked tasks and whose range contains no
`converge:` commit; assert `converged=false` and a next-cycle dispatch. Shipping
only this story already fixes spec 057's failure.

**Acceptance Scenarios**:

1. **Given** a healthy cycle below the cap that ticked 11 of 65 tasks and left
   54 unchecked, **When** the stage reads back the cycle outcome, **Then**
   `converged=false` and cycle N+1 is dispatched — not finalize.
2. **Given** a healthy cycle that leaves no unchecked task and wrote no
   `converge:` commit, **When** the stage reads back the outcome, **Then**
   `converged=true` and finalize is dispatched, exactly as today.
3. **Given** a healthy cycle that left unchecked tasks **and** whose converge
   pass appended a convergence phase, **When** the stage reads back the
   outcome, **Then** `converged=false` — one reason is enough, and the two
   reasons do not conflict.
4. **Given** a cycle classified `truncated` (it ran out of turns but made
   progress), **When** the stage reads back the outcome, **Then**
   `converged=false` is forced without running any scan, unchanged from spec
   040's behaviour.

---

### User Story 2 - The signal is read from the tree, never from the agent's verdict (Priority: P1)

The convergence decision is computed by deterministic code from the `tasks.md`
the cycle actually pushed. An agent that announces "converged", or "deferred to
future cycles", or nothing at all, moves the signal only insofar as it moved
the checkboxes.

**Why this priority**: Principle IX. The premature finalize dispatch happened
because a durable action rode on a proxy that agreed with the agent's
narrative. A rule that can be satisfied by a closing message reintroduces the
same class of defect one layer up.

**Independent Test**: run the shipped outcome logic with an agent transcript
claiming convergence and a `tasks.md` full of unchecked boxes; the signal must
come out false.

**Acceptance Scenarios**:

1. **Given** an agent closing message that says the implementation converged,
   **When** `tasks.md` on the branch still has unchecked tasks, **Then**
   `converged=false`.
2. **Given** an agent that ticked every box, **When** its closing message says
   work remains, **Then** `converged=true` — the tree decides in both
   directions.
3. **Given** the primary arm and the retry arm of the same cycle, **When**
   each reads back its own outcome, **Then** both apply the identical rule
   against their own base, and neither can be changed without the other.

---

### User Story 3 - The issue comment says what is left and why (Priority: P2)

When a cycle does not converge, the lifecycle issue gets a comment naming the
reason — converge appended new work, or the cycle stopped with tasks left —
and listing the remaining tasks. A reader can tell "the spec grew" from "the
cycle ran short" without opening the branch.

**Why this priority**: Principle III — the lifecycle is legible from the issue
alone. Today the remaining-work text is extracted from the `converge:` commit's
diff, so on the new `converged=false` path (where there is no such commit)
it would be empty and the comment would render an empty fenced block.

**Independent Test**: drive the dispatch step with `converged=false` and no
converge commit; assert the posted body lists the unchecked tasks and names
the reason.

**Acceptance Scenarios**:

1. **Given** `converged=false` because tasks are unchecked and no `converge:`
   commit landed, **When** the stage reports remaining work, **Then** the
   comment lists the unchecked tasks read from `tasks.md` and states that the
   cycle ended with them outstanding.
2. **Given** `converged=false` because converge appended a phase, **When** the
   stage reports, **Then** the comment shows the appended work as it does
   today, and says that is what it is.
3. **Given** either reason, **When** the comment is posted, **Then** it never
   contains an empty remaining-work block.

---

### User Story 4 - A spec whose only leftovers are human-only does not grind to the cap (Priority: P1)

A spec has built everything an agent can build, and what remains in `tasks.md`
is work that requires a human or a real dispatched run — dispatch this
workflow on a container-mode day and record the URL, set this repository
secret, merge this PR. The loop recognises it has finished and hands off,
rather than spending every remaining cycle rediscovering that it cannot tick
those boxes.

**Why this priority**: without it this feature makes the common case worse. 19
specs on `main` end in exactly this state; each would pay the full cap in
agent cycles on the usage window the pipeline shares with the maintainers'
sessions, and land on the same non-converged finalize regardless. The rule
that separates this story from User Story 1 is the one open question this spec
carries into clarification (FR-010).

**Independent Test**: drive the loop against a branch whose only unchecked
tasks are ones no cycle can complete; assert the stage hands off without
consuming the remaining iteration budget.

**Acceptance Scenarios**:

1. **Given** a healthy cycle that ticked nothing and left only unchecked tasks
   no cycle can complete, **When** the stage reads back the outcome, **Then**
   it hands off to finalization rather than dispatching another cycle that
   would repeat the same result.
2. **Given** the hand-off in scenario 1, **When** finalize builds the PR body,
   **Then** the remaining unchecked tasks appear under "Remaining manual work"
   for the human reviewer, which is what finalize already does.
3. **Given** a healthy cycle that ticked at least one box and left unchecked
   tasks, **When** the stage reads back the outcome, **Then** it is User Story
   1's path — another cycle, not a hand-off.

---

### Edge Cases

- **`tasks.md` missing or unreadable on the spec branch.** The scan cannot
  reach its subject, so it must fail loudly rather than report a pass it did
  not earn (Principle VIII) — never silently read "zero unchecked tasks ⇒
  converged".
- **`tasks.md` has no task list at all** (a spec whose tasks stage produced an
  empty or malformed file). Zero unchecked tasks is indistinguishable from
  zero tasks; the stage must not treat "there was nothing to do" as a
  converged implementation without saying so in the step summary.
- **Unchecked tasks under indentation, or written `- [x]` with a capital X.**
  The counter must match the same checkbox forms the rest of the stage already
  counts, so a sub-task nested under a phase heading is not invisible to it.
- **A task's text contains a literal `- [ ]` inside a code fence or a quoted
  example.** A naive line match would count prose as an outstanding task and
  hold a finished spec in the loop forever.
- **The cycle ticks a box and unticks another.** The signal is the state at
  the cycle's end, not the delta; the count is taken from the pushed
  `tasks.md`, not inferred from what changed.
- **Converge appends a phase whose tasks are themselves unchecked.** Both
  reasons fire at once; `converged=false` either way, and the comment must not
  report the same work twice.
- **The cap is reached with tasks still unchecked.** The stage hands off to
  finalization flagged `converged=false` with the remaining work reported —
  the existing terminal behaviour. Whether the default cap of 5 is the right
  number now that the loop can actually reach it is FR-009.
- **A mid-cycle auto-rebase imports `main`'s commits.** The scan reads
  `tasks.md` at the branch tip; it must not be confused by commits the branch
  merely inherited, the way the progress test at `implement.yml:1245-1250`
  already guards against.

## Requirements *(mandatory)*

### Functional Requirements — the signal

- **FR-001**: A healthy cycle's convergence signal MUST be `false` when
  `tasks.md` on the spec branch still contains an outstanding unchecked task at
  the cycle's end, whether or not a `converge:` commit touching `tasks.md`
  landed in the cycle's range.
- **FR-002**: `converged=true` MUST require all of: the cycle completed
  (`ok=true`), it was not classified `truncated`, no `converge:`-prefixed
  commit touching `tasks.md` landed in the cycle's range, and no outstanding
  unchecked task remains. Any one failing MUST yield `converged=false`.
- **FR-003**: The unchecked-task determination MUST be computed by
  deterministic code from the `tasks.md` the cycle pushed. It MUST NOT read the
  agent's closing message, its verdict, its transcript, or any
  agent-authored summary (Principle IX).
- **FR-004**: The determination MUST recognise the same checkbox forms the
  stage already counts elsewhere, including leading whitespace and both `- [x]`
  and `- [X]`, and MUST NOT count a `- [ ]` that appears inside a fenced code
  block or is otherwise not a task-list entry.
- **FR-005**: A cycle classified `truncated` MUST continue to have
  `converged=false` forced without running any convergence scan, exactly as
  today. This feature MUST NOT introduce a path by which a truncated cycle can
  reach `converged=true`.
- **FR-006**: If `tasks.md` cannot be read on the spec branch, the step MUST
  fail loudly rather than resolve the signal in either direction (Principle
  VIII).
- **FR-007**: The rule MUST apply identically to the primary read-back and to
  the retry arm's read-back, each against its own base. The two MUST share one
  definition rather than two maintained copies, so the arms cannot drift
  (CLAUDE.md, "Shared logic has exactly one home").

### Functional Requirements — the loop and where it ends

- **FR-008**: A `converged=false` driven by outstanding unchecked tasks below
  the cap MUST re-dispatch the next cycle through the stage's existing
  non-converged path, consuming one iteration, with no new dispatch mechanism.
- **FR-009**: The stage MUST have a stated, deterministic terminal behaviour
  when the iteration cap is reached with tasks still unchecked. Today it posts
  the remaining work to the lifecycle issue and dispatches finalize with
  `converged=false`; finalize then banners the PR "Not fully converged — N
  tasks remain". [NEEDS CLARIFICATION: cycle 1 of spec 057 completed 11 tasks
  in 79 turns, so a 65-task spec needs roughly six cycles against a default
  cap of 5 — now that the loop can actually reach the cap, does the default
  `max-iterations` move, does the cap count only cycles that made progress, or
  does today's hand-off at 5 stand as the intended end state?]
- **FR-010**: The stage MUST distinguish an outstanding task a later cycle
  could complete from one no cycle can complete, and MUST NOT spend cycles on
  the latter. [NEEDS CLARIFICATION: 19 specs on `main` end with unchecked
  tasks that are inherently human-only (dispatch a run and record the URL, set
  a secret, merge a PR) — how is that told apart deterministically? (a) treat
  a healthy cycle that ticked zero boxes as the loop's natural end and hand
  off; (b) have the tasks stage mark human-only tasks explicitly and exclude
  marked tasks from the count; (c) neither — count every unchecked task and
  let such specs run to the cap.]
- **FR-011**: [NEEDS CLARIFICATION: does the implement agent's prompt also
  gain an instruction not to stop while unchecked tasks and turns both remain
  (the lifecycle issue's option 2, additive to the deterministic signal)? It
  would cut wasted cycles, but it pushes every cycle to consume its full turn
  budget, raising per-cycle cost and routing more cycles into the truncated
  carry-forward and opus escalation path.]

### Functional Requirements — legibility

- **FR-012**: When `converged=false` is driven by outstanding unchecked tasks
  and no `converge:` commit landed, the remaining-work text posted to the
  lifecycle issue MUST list those unchecked tasks, read from `tasks.md`. It
  MUST NOT render an empty block, which is what today's extraction from the
  `converge:` commit diff would produce on this path.
- **FR-013**: The comment MUST name which reason drove `converged=false` —
  converge appended new work, the cycle ended with tasks outstanding, or both
  — and MUST NOT report the same work twice when both fire.
- **FR-014**: The step summary of a cycle MUST record the outstanding-task
  count the decision used, so a run's own log shows why it converged or did
  not without re-deriving it from the branch.

### Functional Requirements — contract and coverage

- **FR-015**: Every place that documents the convergence signal as "no
  `converge:` commit ⇒ converged" MUST be corrected to the rule this feature
  ships: the stage header comment (`implement.yml:5-9`), the converge-pass
  instructions in both agent prompts, `docs/architecture.md`'s stage-4
  description, and the stage's published contract. Workflow comments are
  load-bearing here — gates byte-compare them.
- **FR-016**: `docs/architecture.md`'s risk-table row *"Converge 'unchanged
  tasks.md' is syntactic, not semantic — mitigated by the iteration cap"* MUST
  be retired or restated, because this feature replaces that mitigation with
  the signal itself.
- **FR-017**: The `converged` output keeps its name, type and both values; its
  *meaning* narrows. No `workflow_call` input or output may be added or
  renamed unless FR-009's answer requires it, and any such change is a
  deliberate, recorded widening of the published surface (Principle VII).
- **FR-018**: A gate registered in the gate suite MUST drive the **shipped**
  `run:` blocks of the read-back and dispatch steps — located in the workflow,
  never copied into the gate — against synthetic branch state, following
  `verify-truncated-cycle-carry-forward.py`'s established pattern.
- **FR-019**: Every failure branch the new logic ships MUST be exercised by a
  checked-in fixture (Principle VIII): unchecked tasks with no converge commit
  ⇒ false; zero outstanding ⇒ true; truncated ⇒ false with no scan; an
  unreadable `tasks.md` ⇒ loud failure; a `- [ ]` inside a code fence ⇒ not
  counted; the retry arm ⇒ identical verdict on its own base; the
  no-converge-commit remaining-work report ⇒ non-empty.
- **FR-020**: The gate MUST fail if a future edit restores a convergence
  decision that consults only the `converge:` commit range, and MUST fail if
  the primary and retry arms' definitions diverge.

### Out of Scope

- Changing what finalize does with `converged=false`. Its banner and its
  "Remaining manual work" section already read `tasks.md` directly and are
  correct; this feature only stops finalize being reached prematurely.
- Making converge itself append tasks for incomplete work. Its append-only,
  coverage-gap contract is right; the defect is the stage reading its silence
  as completion.
- Retroactively re-running the loop for the 19 specs already merged with
  unchecked tasks.
- Any change to the truncated-cycle classification, the escalation tier
  ladder, or the stalled path (spec 040).
- Per-task progress reporting, task-level time estimates, or a
  tasks.md schema change beyond whatever FR-010's answer may require.

### Key Entities

- **Outstanding task**: an unchecked task-list entry in the spec's `tasks.md`
  at the end of a cycle, counted by deterministic code from the pushed file —
  the input the convergence signal gains.
- **Convergence signal** (`converged`): the stage's boolean output. Unchanged
  in name and type; it now means "nothing is left to build", not "converge
  appended nothing".
- **Non-convergence reason**: which condition drove `converged=false` —
  appended coverage gap, outstanding tasks, both, or truncation — carried into
  the lifecycle comment and the step summary.
- **Cycle outcome read-back**: the deterministic post-agent step, in a primary
  and a retry arm, that owns this decision and must own it in one place.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A cycle that ends healthy with outstanding tasks results in
  another cycle being dispatched, in 100% of cases, verifiable from the
  stage run's own outputs and the dispatch it performed.
- **SC-002**: Finalization is never reached from a healthy cycle that left
  outstanding tasks below the cap — zero such hand-offs, where the live run
  behind issue #450 produced one.
- **SC-003**: Replaying spec 057's cycle-1 conditions (11 of 65 tasks ticked,
  no `converge:` commit, agent exited early and declared convergence) through
  the shipped logic yields `converged=false`.
- **SC-004**: A spec whose tasks are all complete still converges in one
  cycle — no additional cycle is spent confirming it, measured as an unchanged
  cycle count for a completing spec.
- **SC-005**: A spec whose only outstanding tasks are ones no cycle can
  complete consumes no more agent cycles than it does today, measured as
  cycles dispatched per spec.
- **SC-006**: Every `converged=false` comment on a lifecycle issue names its
  reason and lists at least one remaining item — zero empty remaining-work
  blocks.
- **SC-007**: The convergence verdict is reproducible from the branch state
  alone: given the same `tasks.md` and commit range, the decision is identical
  across runs and independent of the agent's message, demonstrated by the
  gate's fixtures.
- **SC-008**: The gate fails on a mutation that reverts the decision to the
  converge-commit-only rule, and on a mutation applied to only one of the two
  arms — both demonstrated by checked-in fixtures, not by a manual
  demonstration during development.
- **SC-009**: No document on `main` describes the convergence signal as "no
  `converge:` commit ⇒ converged" after this ships.

## Assumptions

- The defect is in the stage's signal, not in the implement agent's or
  converge's behaviour. Both acted within their contracts; only the stage drew
  a conclusion its inputs did not support. (FR-011 asks whether the prompt is
  *additionally* tightened, not whether the deterministic signal is optional —
  Principle IX makes the code the gate either way.)
- `tasks.md` remains the single record of what a spec's implementation has to
  do, and its checkboxes remain the record of what is done. This feature reads
  that record; it does not add a parallel one.
- A `converged=false` driven by outstanding tasks reuses the existing
  non-converged dispatch path and iteration accounting. No new stage input,
  output, dispatch payload field, or workflow is assumed.
- The scan runs on the spec branch tip the cycle pushed, which the read-back
  step has already fetched for its existing progress test — no new fetch and
  no new credential are assumed.
- The 19 merged specs carrying unchecked tasks stay as they are; they are
  evidence for FR-010's shape, not a migration to perform.
- Today's terminal behaviour at the cap — report remaining work, dispatch
  finalize with `converged=false`, finalize banners the PR — is the baseline
  FR-009 either confirms or changes. It is described here as observed in
  `implement.yml`'s dispatch step and `finalize.yml`'s body assembly, not
  assumed to be correct.
- Delivery is one spec rather than a split, because the signal, the
  remaining-work report, and the gate are one decision's implementation and
  one gate's subject.
