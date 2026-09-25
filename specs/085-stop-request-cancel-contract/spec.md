# Feature Specification: The Stop Decision Answers Both Questions — One Home for "Stand Down" and "Cancel What"

**Feature Branch**: `spec-draft/085-stop-request-cancel-contract`

**Created**: 2026-09-25

**Status**: Draft

**Input**: Lifecycle issue #612 — "wing-commander-board-stop-check
reimplements board_stop_check.py's own CLI instead of reusing it"
(routed from board-loop.yml; originating issue #466, found by the code
review of #465)

## Overview

The board loop's stop check asks one question with two answers: *must this
job stand down?* and *is there an earlier run worth cancelling?*
`board_stop_check.find_stop_request()` computes both internally — it tracks
`last_other_run_id` separately from the fallback — and then collapses them
into a single returned run id before handing it back. The caller is left to
un-collapse it in shell.

That collapse is the root cause of three coupled defects, all of them
visible in one composite action and one gate:

1. **The caller re-derives a distinction the function already made.**
   `find_stop_request()`'s docstring calls its return value "the run_id (str)
   to `gh run cancel`", but on a first pass through a run it returns
   `current_run_id` — a value the caller must *not* hand to `gh run cancel`,
   because cancelling the run executing the check races its own graceful
   stand-down. `wing-commander-board-stop-check/action.yml` reconstructs the
   distinction in bash (`if [ "$stop_run_id" != "$GITHUB_RUN_ID" ]`, the
   self-cancel fix from round 1 of #465's review). Every future caller has to
   know to do the same, and nothing tells one that forgets.

2. **The composite reimplements the module's own command-line interface.**
   Its single `run:` step opens an inline `python3 -c` block that inserts
   `.github/scripts` onto `sys.path`, imports `find_stop_request`, re-reads
   the comments file it just wrote, and prints the result — retyping, badly,
   what `board_stop_check.main()` has always done. `main()` predates #465,
   reads `{"comments": [...], "current_run_id": "...", "bot_login": "..."}`
   from stdin, and prints the same run id. It was written to be the
   interface and has never been called.

3. **The gate that guards the idiom is keyed on the line the fix deletes.**
   Gate 60 (`verify-single-home-idioms.py`, `check_board_stop_check`)
   declares a finding only when all three of `from board_stop_check import
   find_stop_request`, `gh run cancel` and `board-stop-check-comments.json`
   appear in the same file. The first of those is exactly the line defect 2's
   fix removes, so the gate's fragment set, its `_clean_tree()` fixture and
   its third-paste self-test all have to move in the same change. The
   fragment approach also leaves a narrower hole that survives the rename: a
   stylistically different second copy of the kill-switch-recheck idiom — one
   that already pipes to the CLI, say — matches none of the three fragments
   and is invisible to the check. `check_token_mint()` in the same file
   already demonstrates the alternative: parse each job's step list and
   reason about the resolved steps rather than about literal text.

Fixing 1 makes 2 trivial — once the decision function answers "cancel what?"
with an honest `nothing`, `main()` is directly safe to call and the inline
bootstrap collapses to a pipe. Fixing 2 forces 3. They are one change, not
three tracked separately.

### Why this is worth doing

The stop path is the mechanism a maintainer relies on to halt an in-flight
item. It is guarded well today (Gate 87 runs fifteen checked-in fixtures, a
stop-command accept/reject table, four decision-function mutations, and the
composite's own shell against a stub `gh`), and this feature must not spend
any of that. What it buys is that the one rule a reviewer most needs to
trust — *the loop never cancels the run it is executing in* — becomes a
property of a function with fixtures behind it, instead of a shell
comparison a second call site is free to omit. That is Principle IX applied
to the stop path's own last piece of judgment.

### A gate gap this work must close

Gate 87's composite-shell cases do not currently prove the self-cancel guard
is load-bearing. The one case that reaches it (`an OWNER human's forged
marker never reaches gh run cancel`) names run `999`, which is also
`GITHUB_RUN_ID` — and `999` is absent from the stub's run table, so the
workflow-path/readability guard suppresses the cancel on its own. Deleting
the `!= "$GITHUB_RUN_ID"` comparison today would leave every case green. The
mutation self-test covers the workflow-path guard and four decision-function
rules, but not this one. Whichever shape the new contract takes, the
invariant it now carries has to be mutation-proven (Principle VIII).

## Clarifications

### Session 2026-09-25

Three questions are open; they are marked in place below and carried to the
lifecycle issue.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A maintainer's stop halts the loop and never costs it its own run (Priority: P1)

A maintainer comments `stop` on the in-flight board item. Every job that is
about to take a durable action asks the stop check what to do. The check
answers with two separate facts: stand down, and — only when a genuinely
different, earlier run announced itself — a run id to cancel. On the common
first pass there is no second run, so the answer carries no cancel target at
all, and no caller has to know that the run id it was handed is really its
own.

**Why this priority**: This is the correctness core. The self-cancel bug was
real (it became reachable the moment #461 gave the cancel call a token that
works), and it was fixed in the one call site that existed. The fix belongs
where the knowledge is.

**Independent Test**: Drive the decision function over the existing
first-pass fixture and confirm it reports "stand down, nothing to cancel";
drive it over the earlier-run fixture and confirm it reports "stand down,
cancel run N". Delete the no-self-cancel rule and confirm at least one
checked-in case fails.

**Acceptance Scenarios**:

1. **Given** an authorized stop comment posted after this run's own
   `**Run:**` announcement and no earlier run's announcement, **When** the
   stop check runs, **Then** the job stands down and no cancel is attempted.
2. **Given** an authorized stop comment and an earlier run's own announcement
   naming a different run, **When** the stop check runs, **Then** the job
   stands down and that earlier run is the cancel target.
3. **Given** no authorized, unactioned stop request, **When** the stop check
   runs, **Then** the job does not stand down and no cancel is attempted.
4. **Given** the caller-side self-cancel comparison is removed from the
   composite, **When** every checked-in stop case runs, **Then** they still
   all pass — because the rule now lives in the decision function.

---

### User Story 2 - The composite calls the module's documented interface (Priority: P2)

The composite builds the payload the module documents, pipes it to
`board_stop_check.py`, and reads the answer. There is no `sys.path` insert,
no import line, and no second spelling of the call convention living in YAML.

**Why this priority**: It is the issue's headline defect and CLAUDE.md's
"shared logic has exactly one home" rule applied to a call convention. It
depends on User Story 1 only in that the guard-free form is the safe form;
the invocation change is independently valuable and independently testable.

**Independent Test**: Extract the composite's `check` step and run it against
the existing stub `gh`; every shell case produces the same `paused` output
and the same `gh run cancel` calls as before the change.

**Acceptance Scenarios**:

1. **Given** the shipped composite, **When** its `check` step is read,
   **Then** it contains no inline Python module import of
   `board_stop_check` and no `sys.path` manipulation.
2. **Given** a comments payload the module cannot parse, **When** the step
   runs, **Then** the step fails loudly rather than resolving to "no stop
   request" and letting the job proceed.
3. **Given** the unchanged inputs (`token`, `cancel-token`, `issue-number`,
   `bot-login`, `initial-paused`, `check-issue-closed`), **When** a caller
   invokes the composite, **Then** the `paused` output has the same name and
   the same meaning as before.

---

### User Story 3 - Gate 60 still catches a second copy, in any style (Priority: P3)

A future contributor pastes the kill-switch-recheck orchestration into a
seventh place — whether written the old way or the new way — and Gate 60
names the shared home instead of staying silent.

**Why this priority**: The gate is not load-bearing for the loop's runtime
behaviour, but it is the reason the idiom stays in one home, and this change
would otherwise quietly disarm it. Principle VIII: a check that cannot fail
its subject displaces the scrutiny it appears to provide.

**Independent Test**: Plant a copy of the idiom, written in the post-change
style, in a throwaway workflow inside the gate's own self-test tree and
confirm the gate reports a finding naming the declared home; run the gate's
clean-tree self-test and confirm no finding.

**Acceptance Scenarios**:

1. **Given** a planted second site that pipes a comments payload to
   `board_stop_check.py` and calls `gh run cancel`, **When** Gate 60 runs,
   **Then** it reports a `board-stop-check` finding at that site.
2. **Given** the declared home itself and any helper beside it, **When**
   Gate 60 runs, **Then** it reports nothing.
3. **Given** the repository as it ships after this change, **When** the gate
   suite runs locally and in CI, **Then** every gate passes.

---

### Edge Cases

- **A stop request with no run announcement at all.** The baseline is empty,
  so any authorized stop in the thread counts. The decision must still be
  "stand down", with no cancel target invented.
- **An earlier run that has already finished.** Board-loop's single
  serializing concurrency group means the earlier run is almost always
  terminal by the time this one looks; the composite already declines to
  cancel a `completed` run, and that behaviour is unchanged.
- **A cancel target that cannot be read, or that belongs to another workflow
  or repository.** Unchanged: no cancel, a warning, and `paused` still true.
- **A malformed or empty comments payload.** The invocation must fail the
  step rather than silently reporting "no stop" — the stop path failing open
  is the one failure mode that matters here.
- **A caller that wants only the stand-down answer.** Asking for the decision
  without intending to cancel anything must be possible without the caller
  reasoning about run ids at all.
- **The `prove` job's extra "issue already closed" pre-check.** It resolves
  `paused` before the comment scan and must keep doing so.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The stop decision MUST be expressed as two separate facts — a
  stand-down boolean and an optional cancel target — produced by one
  deterministic function, so that no caller re-derives either from the other.
- **FR-002**: The stand-down fact MUST be true whenever an authorized,
  unactioned stop request exists, whether or not a cancel target exists.
- **FR-003**: The cancel target MUST be absent whenever the only run
  announcement found is the run performing the check. The function MUST NOT
  return the current run's own id as a cancel target.
- **FR-004**: No call site MAY reconstruct the self-cancel distinction by
  comparing a returned run id to the current run id. [NEEDS CLARIFICATION:
  should the composite nonetheless retain a cheap defence-in-depth check that
  the target is not this run — matching the existing workflow-path/repository
  target guard's belt-and-braces style — or is the function's contract, once
  mutation-proven, the single guard?]
- **FR-005**: The module's documented interface MUST state the two-fact
  contract, and every docstring that describes the return value MUST match
  what the function returns.
- **FR-006**: The composite MUST obtain the decision by invoking
  `board_stop_check.py` through its own documented stdin/stdout interface.
  The composite MUST NOT contain an inline re-implementation of that call
  convention (no `sys.path` manipulation, no module import).
- **FR-007**: The composite's step MUST fail loudly when the decision cannot
  be computed — a malformed payload, a crash, a non-zero exit — and MUST NOT
  treat an unreadable answer as "no stop request".
- **FR-008**: The composite's published surface MUST be unchanged: the same
  input names and defaults, the `paused` output with the same name and
  meaning, the App-token/cancel-token split, the `completed`-status check,
  and the workflow-path and repository target guards.
- **FR-009**: Gate 60's `board-stop-check` check MUST detect a second site of
  the idiom regardless of the style it is written in, including one written
  against the module's CLI, and MUST NOT depend on a literal fragment that
  this change itself deletes. [NEEDS CLARIFICATION: should the check follow
  `check_token_mint()`'s structural pattern (parse each job's step list and
  reason about resolved steps), or is "any subject file outside the declared
  home that references `board_stop_check` at all" the simpler and stricter
  rule — noting the latter needs no co-occurrence reasoning but would flag a
  future legitimate non-loop consumer?]
- **FR-010**: Gate 60's declared-home comment, clean-tree fixture and
  third-paste self-test MUST be updated in the same change, and the gate's
  `--self-test` MUST pass both directions: silent on the clean tree, and a
  finding on a planted paste.
- **FR-011**: The no-self-cancel invariant MUST be proven by a mutation: with
  the rule removed, at least one checked-in case MUST fail, and that failure
  MUST NOT be attributable to the unreadable-run or workflow-path guards
  suppressing the cancel for an unrelated reason.
- **FR-012**: Every existing stop-check fixture and command case MUST produce
  the same outcome after the change as before — the maintainer-association
  rule, the stop-command rule, the bot-authored-marker rule, the
  last-`**Run:**`-line rule and the baseline rule are untouched.
- **FR-013**: The change MUST ship as one unit, because the gate's fragment
  set and the composite's invocation cannot be correct at the same time
  across two commits. [NEEDS CLARIFICATION: is the deeper return-contract
  redesign (FR-001/FR-003) in scope for this spec together with the CLI
  reuse, or should the minimal "call `main()` and keep the shell guard" fix
  ship first as a smaller change with the contract redesign tracked
  separately?]

### Key Entities

- **Stop decision**: the answer the stop check produces for one job at one
  moment — a stand-down fact and an optional cancel target. Replaces the
  single "run id, which may be your own" value.
- **Run announcement**: a `**Run:**` line at the start of a line in a comment
  the loop's own App posted (last such line in that comment). Sets the
  baseline and names candidate cancel targets. Unchanged by this feature.
- **Stop request**: a first-line `stop` command from an OWNER, MEMBER or
  COLLABORATOR, posted at or after the baseline. Unchanged.
- **Stop-check composite**: the one home of the surrounding orchestration —
  the issue-state read, the paginated comment read, the decision call, the
  guarded cancel, and the `paused` output.
- **Single-home check**: Gate 60's `board-stop-check` entry, which names the
  composite as the idiom's declared home and fails a second site.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer can determine which run the loop will cancel, and
  whether it will cancel anything at all, by reading exactly one function —
  with no reference to any call site's shell.
- **SC-002**: The shipped composite contains zero lines that import or
  path-bootstrap the stop-check module, and zero comparisons of a stop-check
  result against the current run id (subject to FR-004's open question).
- **SC-003**: All existing stop-check fixtures, command cases and composite
  shell cases produce identical stand-down and cancel outcomes before and
  after the change — no fixture is deleted or weakened to accommodate it.
- **SC-004**: Removing the no-self-cancel rule from the decision function
  causes at least one checked-in case to fail, and the gate reports which.
- **SC-005**: A copy of the kill-switch-recheck idiom planted in a second
  subject file is flagged by the single-home gate whether it is written in
  the pre-change style or the post-change style; the clean tree is silent.
- **SC-006**: The full local gate suite (`run-local-gates.py`) passes, and no
  gate's self-test is skipped or waived to achieve it.
- **SC-007**: An adopter pinning the published composite sees no change to
  its inputs, its `paused` output, or its token requirements.

## Assumptions

- `board_stop_check.py` and the other scripts under `.github/scripts/` are
  internal to this repository's consuming instrument, reached through
  self-checkout by the composites that use them. Changing the signature or
  return shape of `find_stop_request()` is therefore not a published-contract
  change under Principle VII; the composite's own inputs and outputs are, and
  FR-008 holds them fixed.
- The composite is the only production caller of the decision function today;
  no other workflow or script imports it. Any other consumer discovered
  during implementation is migrated in the same change rather than left on
  the old shape.
- The comment read stays in the composite's shell (the App token lives there,
  and the two-token split is deliberate). Moving the `gh api` pagination into
  the module is out of scope.
- The `gh run cancel` call, its `completed`-status check, and its
  workflow-path/repository target guards stay in the composite's shell; this
  feature changes what decides the target, not who performs the cancel.
- The gate number assignments (60 for single-home idioms, 87 for the
  stop-check gate) are stable and this change adds no new gate — it corrects
  two existing ones.
- Issue #612's quoted snippet of the call predates the `bot_login` argument
  added by #547; the current three-argument form is the subject.

## Dependencies

- `.github/actions/wing-commander-board-stop-check/action.yml` — the declared
  single home of the idiom, and the file whose `check` step changes.
- `.github/scripts/board_stop_check.py` — the decision function, its `main()`
  entry point, and the docstrings that state the contract.
- `.github/scripts/verify-single-home-idioms.py` — Gate 60, its
  `board-stop-check` fragment set, `_clean_tree()` fixture and third-paste
  self-test.
- `.github/scripts/verify-board-stop-check.py` and its fixtures under
  `.github/scripts/tests/board-stop-check/` — Gate 87, which must keep
  passing and must gain the missing mutation.
- `.github/workflows/board-loop.yml` — the six jobs that consume the
  composite's `paused` output; unchanged, and the proof that FR-008 held.
- Prior art this change must not undo: #461 (the two-token split that made
  the cancel effective), #465 (the self-cancel and completed-run fixes),
  #539 (the stop-command rule), #547 (the bot-authored-marker rule), #580
  (the last-`**Run:**`-line rule).

## Out of Scope

- Any change to what counts as a stop command, who may issue one, or how the
  baseline is computed.
- Moving the issue-comment pagination, the issue-state read, or the cancel
  call out of the composite.
- Redesigning the redrive/concurrency behaviour issue #460 is weighing; this
  spec assumes the current single serializing group and the composite's
  existing live `status` check rather than depending on either.
- Adding a new gate. The two existing gates are corrected in place.
