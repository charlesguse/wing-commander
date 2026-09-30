# Feature Specification: Board-Loop Agent Jobs Are Ordinary Gate 68 Subjects

**Feature Branch**: `116-board-loop-full-subject`

**Created**: 2026-09-30

**Status**: Draft

**Input**: User description: "Spec 073 exempted board-loop.yml's triage, route, fix, and review jobs from Gate 68's post-agent credential-refresh rule 'provisionally' (research.md D7 called promotion a follow-up, tracked as this issue). Each job now calls the missing single-homed composites after every agent step and the corresponding `EXEMPT_JOBS` entries (and their now-dead `_composite_adoption_ok` condition/self-test) are removed, so Gate 68 checks all four jobs as ordinary full_subject jobs. — triage, route: add `wing-commander-agent-ran-signal` after the propose agent step (both already re-mint and check credential status). fix: add `wing-commander-agent-ran-signal` after the fixer agent step (it already refreshes the remote and checks credential status). review: add `wing-commander-refresh-remote` and `wing-commander-agent-ran-signal` after the Reviewer step, wire the new refresh's outcome into that step's credential-status call, and add `wing-commander-agent-ran-signal` after the Review-fixup step (which already refreshes the remote). `.github/scripts/verify-post-agent-credential-refresh.py`: delete the four board-loop `EXEMPT_JOBS` entries, the now-unused `_composite_adoption_ok` condition, its `mut_board_loop_composite_deleted` self-test mutation and list entry, and the docstring passages describing the composite-adoption exemption path. Found by the code review of #730."

## Context

Gate 68 (`.github/scripts/verify-post-agent-credential-refresh.py`) derives its
subject set from every job in `.github/workflows/*.yml` that runs an agent
step, then resolves each subject to one disposition: `full_subject`,
`exempt`, or `agentless_in_scope`. Spec 073 recorded `board-loop.yml`'s
`triage`, `route`, `fix`, and `review` jobs as `exempt` against a
*composite-adoption* condition — a weaker, board-loop-only condition that
deliberately does not require `wing-commander-agent-ran-signal` and, for the
`review` job's first agent step, does not require
`wing-commander-refresh-remote`. That exemption was recorded as provisional:
its own `reason` text says promotion "is a re-classification, not a new
remedy", and it names an open tracker issue rather than a permanent reason.

The four jobs are already `SUBJECT_FLOOR` members, already re-mint the
credential after every agent step, and already fold that outcome into a
credential-status call. What keeps them out of `full_subject` is a small,
enumerable set of missing composite calls — five `agent-ran-signal` calls and
one `refresh-remote` call across five agent steps — plus the exemption record
that lets the gate skip the checks those calls satisfy.

While the exemption stands, Gate 68's strongest checks (no stale credential
reference after an agent step; each agent step's own composite calls, checked
by position) are not applied to the busiest agent-bearing workflow in the
repository, and the gate's exemption surface carries a condition function
that exists for exactly these four entries.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every board-loop agent step carries the whole post-agent set (Priority: P1)

A maintainer reading any of board-loop's four agent-bearing jobs sees the
same post-agent shape every other stage uses: re-mint, remote refresh where
the job pushes, agent-ran signal, credential status — with no board-loop-only
subset.

**Why this priority**: the missing calls are the only substantive difference
between these jobs and a `full_subject` job. Nothing else in the promotion
can land first: removing the exemption before the calls exist would fail the
gate on every PR.

**Independent Test**: run Gate 68's `full_subject` checks against
`board-loop.yml`'s four jobs (locally, with the exemption record ignored) and
see zero failures — the calls alone, with no gate edits, satisfy the full
mechanism.

**Acceptance Scenarios**:

1. **Given** `board-loop.yml`'s `triage` job, **When** its propose agent step
   finishes, **Then** an `agent-ran-signal` composite call runs inside that
   agent step's own window (before the job's end), gated the same way as the
   sibling post-agent steps and resolved through board-loop's trusted copy of
   the composite.
2. **Given** `board-loop.yml`'s `route` job, **When** its propose agent step
   finishes, **Then** the same call is present on the same terms.
3. **Given** `board-loop.yml`'s `fix` job, **When** the fixer agent step
   finishes, **Then** an `agent-ran-signal` call joins the re-mint, remote
   refresh, and credential-status calls already there.
4. **Given** `board-loop.yml`'s `review` job, **When** the Reviewer agent step
   finishes, **Then** both a `refresh-remote` call and an `agent-ran-signal`
   call run in that step's window, and the Reviewer's credential-status call
   reads the new refresh's outcome alongside the re-mint's.
5. **Given** the same `review` job, **When** the Review-fixup agent step
   finishes, **Then** an `agent-ran-signal` call joins the re-mint, remote
   refresh, and credential-status calls already there.

---

### User Story 2 - Gate 68 checks the four jobs as ordinary full subjects (Priority: P1)

A maintainer (or a future agent) who deletes or renames one of board-loop's
post-agent composite calls learns it from Gate 68 on that PR, by the same
failure message any other stage would produce — not from a board-loop-only
condition that tolerates the gap.

**Why this priority**: this is the outcome the tracker issue exists for. It
converts four waivers into ordinary coverage.

**Independent Test**: delete any one post-agent composite call in any of the
four jobs and run the gate — it fails, naming that job and that agent step.
Restore it and the gate passes.

**Acceptance Scenarios**:

1. **Given** the gate's exemption record, **When** it is read after this
   change, **Then** it holds no entry for `board-loop.yml` and no entry whose
   condition is composite adoption.
2. **Given** the four jobs, **When** the gate runs, **Then** each resolves to
   `full_subject` and all of the position-checked per-agent-step composite
   assertions apply to it.
3. **Given** one of the four jobs with an `agent-ran-signal` call deleted,
   **When** the gate runs, **Then** it fails, naming the workflow, the job and
   the agent step whose window lost the call.
4. **Given** one of the four jobs whose last agent step is removed, **When**
   the gate runs, **Then** it still fails on the `SUBJECT_FLOOR` invariant
   (this coverage is unchanged by the promotion).

---

### User Story 3 - No dead or contradictory record of the exemption survives (Priority: P2)

A reader of the gate, of its contracts, or of board-loop's own canonical
per-agent-step comment finds one consistent account of the mechanism: no
condition function with no callers, no self-test mutation asserting a
condition that no longer exists, and no document still describing
board-loop's four jobs as exempt.

**Why this priority**: an exemption path with no entries behind it is the
kind of record that reads as live coverage while proving nothing
(Constitution Principle VIII), and a stale contract row is what the next
agent will trust.

**Independent Test**: search the tree for the composite-adoption condition
function and for prose describing board-loop as exempt — both are absent,
and the gate's self-test still passes with no surviving mutation.

**Acceptance Scenarios**:

1. **Given** the gate script, **When** it is read after this change, **Then**
   the composite-adoption condition function, its self-test mutation, that
   mutation's entry in the mutation list, and the docstring passages
   describing the composite-adoption exemption path are all gone, and the
   remaining docstring describes only the wall-clock condition the surviving
   entries use.
2. **Given** the gate's `--self-test`, **When** it runs after this change,
   **Then** it passes: the clean tree passes, and every listed mutation still
   fails — including at least one mutation that proves the newly promoted
   jobs are actually checked.
3. **Given** the two live contracts that describe Gate 68's disposition model
   and its exemption table, **When** they are read after this change,
   **Then** neither presents board-loop's four jobs as exempt.
4. **Given** `board-loop.yml`'s canonical per-agent-step pattern comment,
   **When** it is read after this change, **Then** it names the agent-ran
   signal as part of the post-agent set and describes the `review` job's
   remote refresh accurately.

---

### Edge Cases

- **An agent step is skipped** (its own `if:` guard, a kill switch, a
  stand-down): the new calls carry the same `!cancelled() && steps.<agent
  id>.outcome != 'skipped'` guard the sibling post-agent steps in that job
  already use, so a skipped agent step leaves them skipped too. Gate 68 reads
  structure, not outcomes, so the call must be present regardless.
- **The `review` job's Reviewer step runs but the Review-fixup arm never
  does**: the new `refresh-remote` call after the Reviewer step refreshes a
  remote nothing subsequently pushes on that path. It must therefore be
  tolerated the way the `fix` job's is (its own failure folded into the
  credential-status verdict rather than failing the job), never a new hard
  failure on a path that used to succeed.
- **A composite call resolved from the wrong tree**: board-loop resolves every
  shared composite through its own write-protected trusted copy, not through
  the PR's checkout. New calls must use that same resolution, or the trusted
  composite resolution gate fails them.
- **Nothing in board-loop reads the agent-ran signal**: board-loop has no
  survivor/stall job consuming it. Publication with no reader is the existing,
  contracted precedent for such jobs, and this change does not add a reader.
- **A future board-loop job gains an agent step**: derivation covers it the
  day it ships and it defaults to `full_subject`; no exemption entry is
  reintroduced for it by this change.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Each of board-loop's five agent steps (triage's propose, route's
  propose, fix's fixer, review's Reviewer, review's Review-fixup) MUST be
  followed, inside its own post-step window, by a call to the single-homed
  agent-ran-signal composite, passing that agent step's own `outcome` (never
  its `conclusion`).
- **FR-002**: The `review` job's Reviewer agent step MUST additionally be
  followed by a call to the single-homed refresh-remote composite inside its
  own window, and the Reviewer's credential-status call MUST fold that
  refresh's outcome into its verdict alongside the re-mint's outcome.
- **FR-003**: Every new post-agent step MUST carry the same execution guard
  and the same failure tolerance as the sibling post-agent steps in its own
  job, so that adding it cannot turn a previously succeeding run into a
  failing one.
- **FR-004**: Every new composite call MUST resolve through board-loop's own
  trusted, write-protected copy of the composites, the same way every
  existing composite call in that workflow does.
- **FR-005**: Gate 68's exemption record MUST contain no entry for
  `board-loop.yml`, so each of its four agent-bearing jobs resolves to
  `full_subject` and every `full_subject` check applies to it.
- **FR-006**: The composite-adoption condition function MUST be removed along
  with its last entry, together with its self-test mutation, that mutation's
  entry in the mutation list, and the gate docstring passages that describe
  composite adoption as a disposition path — leaving the wall-clock bound as
  the only condition shape the gate documents and implements.
- **FR-007**: Gate 68's `full_subject` per-agent-step composite requirement
  for the `triage` and `route` jobs — neither of which pushes a git remote or
  persists a remote credential — MUST be satisfied without inventing a remote
  refresh those jobs have no use for. [NEEDS CLARIFICATION: record `triage`
  and `route` in the gate's existing "no persisted remote to refresh"
  exception set (the precedent used for two other jobs), or add a
  refresh-remote call to them anyway for uniformity?]
- **FR-008**: Gate 68's self-test MUST gain at least one mutation per promoted
  job that fails only because the job is now checked as a `full_subject` (for
  example, that job's newly added agent-ran-signal call deleted), so removing
  the composite-adoption mutation does not reduce the gate's mutation
  coverage of `board-loop.yml`.
- **FR-009**: `board-loop.yml`'s canonical per-agent-step pattern comment MUST
  describe the post-agent set this change lands — including the agent-ran
  signal and the `review` job's remote refresh — so the workflow's own
  load-bearing prose does not contradict its steps.
- **FR-010**: The live contract documents that describe Gate 68's disposition
  model and its exemption table MUST stop presenting board-loop's four jobs
  as exempt. [NEEDS CLARIFICATION: amend the existing rows and prose in place,
  or leave spec 073's "entries this feature adds" table as its historical
  record and add a superseding note pointing at this feature?]
- **FR-011**: The four `SUBJECT_FLOOR` entries for `board-loop.yml` MUST
  remain, so a promoted job losing its last agent step still fails loudly.
- **FR-012**: After this change no remaining exemption entry may cite the
  tracker issue this feature closes, and every remaining entry MUST still
  satisfy the waiver-citation rule (exactly one of an open tracker issue or a
  permanent reason).
- **FR-013**: The repository's full PR-time gate suite MUST pass with the
  change applied, Gate 68's own `--self-test` included.

### Key Entities

- **Derived subject**: a `(workflow path, job name)` pair with at least one
  agent step. Board-loop's four jobs are already derived subjects; this
  feature changes only their disposition.
- **Disposition**: `full_subject`, `exempt`, or `agentless_in_scope`. After
  this change, board-loop's four jobs are `full_subject`.
- **Exemption entry**: a checked-in record naming a reason, a tracker or a
  permanent reason, deciding issues, and a mechanically evaluated condition.
  Four such entries are deleted; the condition shape one of them introduced
  is deleted with them.
- **Post-agent composite set**: the re-mint, the remote refresh (for a job
  with a persisted remote), the agent-ran signal, and the credential-status
  verdict that folds the others' outcomes.
- **Subject floor**: the checked-in lower bound on the derived set, unchanged
  here.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Gate 68 reports zero failures on the change, with zero exemption
  entries naming `board-loop.yml` and all four of its agent-bearing jobs
  resolving to `full_subject`.
- **SC-002**: For each of the four promoted jobs, deleting any single
  post-agent composite call in any of its agent steps' windows makes Gate 68
  fail, naming that job and that agent step — demonstrated by checked-in
  self-test mutations, not by a manual trial.
- **SC-003**: Gate 68's mutation count for `board-loop.yml` after the change
  is greater than or equal to the count before it (one composite-adoption
  mutation out, at least one promotion mutation per job in).
- **SC-004**: Searching the repository finds zero occurrences of the
  composite-adoption condition function and zero live documents describing
  board-loop's jobs as exempt from the post-agent mechanism.
- **SC-005**: The full local gate suite passes, and `--self-test` reports the
  clean tree passing with every listed mutation failing.
- **SC-006**: One board-loop run after merge exercises at least one promoted
  job's complete post-agent set with every new step reporting success (or
  skipped for a skipped agent step), recorded as evidence on the PR or the
  lifecycle issue.

## Assumptions

- The agent-ran signal published by these five call sites has no reader inside
  `board-loop.yml`, and none is added. Publication with no consumer is the
  already-contracted behaviour for jobs outside the six stages that consume
  it.
- Board-loop's jobs are not added to the set required to call the
  failed-post-agent-step composite: that requirement exists for the entry jobs
  whose stall path reads the resulting context, and board-loop has no such
  job.
- No board-loop step after an agent step reads a raw credential output today,
  so the promotion's stale-credential-reference check is satisfied by the
  existing steps without further edits.
- Gate 68's `triage`/`route`/`fix`/`review` floor entries, the derivation rule,
  and the four surviving wall-clock exemptions are all out of scope beyond the
  consistency requirements above.
- Spec, plan, research and tasks documents of already-merged features are
  historical and are not edited by this feature; only live contracts, live
  gate code, and live workflow prose are.
- The change is gate-and-plumbing shaped: no new composite, no new gate, and
  no change to what any agent step is asked to do.
