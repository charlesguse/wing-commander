# Feature Specification: Every Stage's Survivor Job Splits Its Notice From Its Mark

**Feature Branch**: `121-survivor-notice-mark-split`

**Created**: 2026-09-30

**Status**: Draft

**Input**: Lifecycle issue [#860](https://github.com/charlesguse/wing-commander/issues/860), routed from the board loop's work on [#754](https://github.com/charlesguse/wing-commander/issues/754) — "Per-spec-group stall/mark jobs can be silently cancelled while pending, or cancel another pending job". Originally found by the code review of #634.

## Context

GitHub Actions keeps **at most one pending run per concurrency group**. A
newer pending run in a group replaces the older one even when every member
declares `cancel-in-progress: false` — that setting protects the run that is
*already executing*, never the one waiting behind it. The waiting slot holds
exactly one run, and the newest arrival wins it.

Since #397 every job in this repository that can write a specification's
working branch `spec/NNN-slug` shares one group, `wing-commander-specs/NNN-slug`,
with `cancel-in-progress: false` (`specs/013-serialize-rebase-stages/contracts/concurrency-groups.md`,
enforced by Gate 80, `.github/scripts/verify-spec-branch-push-concurrency.py`).
That is the single-file guarantee that keeps a rebase's force-push out of the
middle of a running implement cycle, and it is correct for the writers it was
designed around.

It is not correct for **survivor jobs**. A survivor job (the #224 idiom,
`specs/041-implement-stall-notice`) is the job that runs when its stage's
entry job failed or never started. Its whole purpose is to leave a record of
a stall instead of letting the stall be silent, and it performs two very
different effects to do that:

1. a **human-facing notice** — a comment on the lifecycle issue (or the PR)
   saying the stage did not start, and the `stage:stalled` label; and
2. a **stall mark** — `stage: "stalled"` written into `spec-meta.json` on
   `spec/NNN-slug`, plus removal of the now-stale `stage:<name>` label.

Only the second effect is a spec-branch write. The first needs nothing from
the per-spec group at all. Today, in five jobs, both effects are performed
from one job that sits in that group.

### The two defects

**Silent cancel.** While a survivor job sits pending behind a running writer
— an implement cycle, a rebase, a fold — any *other* writer queuing into the
group displaces it from the pending slot. Those other writers are routine:
`rebase.yml` on a push to `main`, implement's next-iteration dispatch,
another `pr-conversation` `act` leg, finalize, cleanup. The notice and the
mark then never land, and **nothing watches for that cancellation** — which
is precisely the silence spec 041 was built to eliminate. A stall that
cancels its own stall notice is indistinguishable from no stall at all.

**Collateral cancel.** The displacement runs the other way too. A survivor
job queuing into a busy group evicts whatever was pending before it. Two
known victims have no natural re-trigger: a `pr-conversation` fold leg (the
loss recorded on #415/#560) and implement's next-iteration dispatch, whose
eviction silently ends the implement ⟲ converge chain.

Spec 013's research D4 accepted eviction in this group for exactly one
member — `rebase`, which the next push to `main` re-queues by itself. That
reasoning was never extended to a job whose only job is to be the record of
something going wrong, and it does not cover these jobs.

### The shape already exists

`pr-conversation.yml` was fixed this way once already, in
`specs/077-stalled-per-spec-group`. Its survivor job is now two jobs:

- `stalled` — posts the notice, calls the shared composite with
  `mark-record: "false"`, and **declares no `concurrency:` block at all**
  (Maintainer Feedback, T032), so no pending slot anywhere can be taken from
  it; and
- `stalled-mark` — writes the mark, calls the same composite with
  `post-notice: "false"`, and carries the canonical per-spec group.

Both jobs are admitted by identical `needs:`/`if:` criteria. The shared
composite `.github/actions/wing-commander-chain-stop-notice` already carries
the `mark-record` and `post-notice` inputs this split needs, and already
documents the two-call shape; both default to `"true"`, so every unsplit
caller behaves exactly as it does today.

That spec named the remaining jobs as out of scope and tracked them on #754,
which is where this feature comes from. What is left is to apply the same
shape to the other five survivor jobs, and to close the residual that the
split does not itself close: the mark, which must stay in the group, can
still be lost, and nothing today notices when a notice was posted and its
mark never landed.

### Jobs in scope

| Workflow | Job | Today |
|---|---|---|
| `tasks.yml` | `stalled` (mode `generate`) | notice + mark, per-spec group |
| `tasks.yml` | `stalled-approved` (mode `approved`) | notice + mark, per-spec group |
| `implement.yml` | `stalled` | notice + mark, per-spec group |
| `finalize.yml` | `stalled` | notice + mark, per-spec group |
| `cleanup.yml` | `mark-stalled` | notice + mark, per-spec group |

### Jobs deliberately not in scope

- `pr-conversation.yml`'s `stalled`/`stalled-mark` — already split (spec 077).
- `clarify.yml`'s `stalled` — waived for an unrelated reason: the branch it
  would mark does not exist yet at the clarify stage, so there is no
  spec-branch write to order and no per-spec group to be evicted from.
- `intake.yml`'s `intake` — no specification slug exists yet.
- `plan.yml` — has no survivor job today; if one is added later it inherits
  the rule this feature writes down, not a retrofit.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The stall notice reaches the human even when the specification is busy (Priority: P1)

A maintainer merges the tasks PR for `specs/121-some-feature` and the tasks
stage's entry job dies — a revoked token, a runner failure, a rate limit.
The survivor job queues, but the specification's group is held by a running
implement cycle, and while it waits a push to `main` queues a rebase for the
same specification. Today the rebase takes the pending slot, the survivor
job is cancelled, and the maintainer sees nothing at all: no comment, no
label, no stall mark — a stage that simply stopped existing.

After this change the notice half of that survivor job belongs to no
concurrency group, so nothing can take a slot from it. The maintainer gets
the "stage did not start" comment and the `stage:stalled` label within the
same run, regardless of what is holding or queuing for the specification.

**Why this priority**: It is the defect, and it defeats the entire purpose
of spec 041. A silent stall is the worst failure mode this pipeline has.

**Independent Test**: For each in-scope stage, the notice-only job is read
and confirmed to declare no `concurrency:` block and to pass
`mark-record: "false"`; the two jobs' `needs:`/`if:` admission criteria are
compared and confirmed identical. Fully testable against the workflow files
with no run required, and it delivers the whole of the "the human always
hears about it" value on its own.

**Acceptance Scenarios**:

1. **Given** a survivor job's stage has stalled and the specification's
   per-spec group is held by another writer with a third writer queuing,
   **When** the run reaches its survivor jobs, **Then** the notice-only job
   runs to completion and posts its comment, and no pending-slot contention
   can prevent it.
2. **Given** an in-scope stage file after this change, **When** its
   notice-only job is read, **Then** it declares no `concurrency:` block and
   invokes the shared chain-stop composite with `mark-record: "false"`.
3. **Given** an in-scope stage file after this change, **When** the
   notice-only job's and the mark-only job's `needs:` and `if:` are compared,
   **Then** they are identical, so no upstream outcome admits one without the
   other.
4. **Given** the notice-only job, **When** the notice it posts is compared
   with the notice the unsplit job posts today, **Then** the wording, the
   reason sentence, the restart instructions and the label are unchanged.

---

### User Story 2 - A stall mark that never landed is visible instead of absent (Priority: P1)

The notice now always lands, but the mark still has to wait for the
specification's group, and it can still lose the pending slot. When it does,
`spec-meta.json` on `spec/NNN-slug` keeps saying the stage is running, and
the stale `stage:<name>` label stays on the lifecycle issue — while the
notice on that same issue says the stage did not start. Anything that reads
the record to decide what to do next (cleanup's selection, the watchdog,
a maintainer scanning labels) reads the wrong state.

After this change, a notice that was posted without its mark landing is
detected and reported, so the inconsistency is named rather than left for
whoever trips over it.

**Why this priority**: Splitting the notice out of the group converts a
silent double loss into a silent single loss. Without detection, this
feature would move the silence rather than remove it.

**Independent Test**: A stall is driven in which the mark half is prevented
from landing while the notice half succeeds; the detection reports the
mismatch. Independently valuable even if User Story 1 were not shipped,
because the mark can be lost today for the same reason.

**Acceptance Scenarios**:

1. **Given** a stall whose notice was posted and whose mark-only job was
   cancelled, skipped, or failed, **When** detection runs, **Then** the
   mismatch is reported with the specification, the stage and the run that
   stalled.
2. **Given** a stall whose notice was posted and whose mark landed, **When**
   detection runs, **Then** nothing is reported.
3. **Given** a stall whose `spec-dir` could not be resolved at all, so the
   notice already rendered its "record could not be updated" wording,
   **When** detection runs, **Then** nothing is reported — there was no
   record to mark and no inconsistency to name.
4. **Given** the same unlanded mark observed twice, **When** detection runs
   the second time, **Then** it does not produce a second, duplicate report
   for the same stall.

---

### User Story 3 - A stalling stage no longer ends someone else's chain (Priority: P2)

An implement cycle finishes and queues its next-iteration dispatch for
`specs/121-some-feature`, which waits for the group. A `pr-conversation`
stage for a PR on the same branch stalls, and its mark-only job queues into
the same group — taking the pending slot and evicting the dispatch. The
implement ⟲ converge chain ends there, with nothing to re-trigger it. The
same eviction has already cost a fold leg (#415/#560).

After this change, a survivor job's mark cannot silently end another
pipeline chain.

**Why this priority**: It is a real, observed loss, but it is the arm of the
defect with the largest design surface — the notice split does not close it,
and closing it means deciding something about how the mark queues. Shipping
User Stories 1 and 2 leaves the pipeline strictly better off; this one
completes the fix.

**Independent Test**: A mark-only job and a next-iteration dispatch are
queued into the same held per-spec group; the dispatch is confirmed still
present when the group drains.

**Acceptance Scenarios**:

1. **Given** a next-iteration dispatch pending in a specification's group,
   **When** a survivor job's mark-only job queues into that same group,
   **Then** the dispatch is not lost.
2. **Given** a fold leg pending in a specification's group, **When** a
   survivor job's mark-only job queues into that same group, **Then** the
   fold leg is not lost.

---

### Edge Cases

- **Identity could not be resolved at all.** The survivor job's `spec-dir`
  is empty — the stage died before deriving it, or the derivation itself
  failed. The notice must still be posted (to the lifecycle issue, or to the
  PR number where that is the only identifier available), there is no mark to
  write, and the notice keeps its existing "record could not be updated"
  wording. This is the behaviour the chain-stop composite already implements;
  the split must not disturb it.
- **The mark job runs but the push fails** for a reason unrelated to
  concurrency — a revoked token, a deleted branch. The composite already
  degrades rather than failing the job. Detection must treat this the same as
  a cancelled mark: the record is inconsistent either way.
- **Both halves are admitted but the notice half fails.** The mark may still
  land. A mark with no notice is the inverse inconsistency; the record is
  correct and the human was not told.
- **Cleanup's `mark-stalled`** is reached through `select`'s `outcome`
  rather than an entry-job failure. Its admission condition differs in shape
  from the other four, so "identical `needs:`/`if:` on both halves" must be
  read as "identical to each other", not "identical across stages".
- **`tasks.yml` has two survivor jobs**, one per mode, and only one of them
  is ever admitted for a given run. Splitting each into two produces four
  jobs, of which at most two ever run.
- **A stage that stalls twice** for the same specification — a re-dispatch
  that also dies — produces two notices and two marks. Detection must not
  treat the first stall's landed mark as covering the second stall's
  unlanded one.
- **A run cancelled by a human** (a maintainer stopping the run, or the
  honoured-stop path) is not a lost mark. Detection must not report it.

## Requirements *(mandatory)*

### Functional Requirements

#### The split

- **FR-001**: Every survivor job named in the "Jobs in scope" table MUST be
  replaced by two jobs: a **notice-only job** that performs the human-facing
  effects, and a **mark-only job** that performs the spec-branch write and
  the stale-label removal.
- **FR-002**: The notice-only job MUST NOT declare a `concurrency:` block,
  so no pending run in any group — the per-spec group, or any per-PR or
  per-issue group the stage otherwise uses — can displace it.
- **FR-003**: The mark-only job MUST declare the canonical per-spec group
  `wing-commander-<spec-dir>` with `cancel-in-progress: false`, in the exact
  spelling Gate 80 accepts for that stage.
- **FR-004**: The two jobs of a split pair MUST carry identical `needs:` and
  identical `if:` conditions, so that no upstream outcome admits one without
  the other.
- **FR-005**: The notice-only job MUST invoke the shared chain-stop composite
  with `mark-record: "false"`, and the mark-only job MUST invoke it with
  `post-notice: "false"`. Across the pair every effect the unsplit job
  performed today MUST be performed exactly once, and none MUST be dropped.
- **FR-006**: Removal of the stale `stage:<name>` label MUST stay with the
  mark, conditional on the mark succeeding, exactly as the composite couples
  them today.
- **FR-007**: The human-facing notice MUST be byte-identical to the notice
  the unsplit job posts today for the same stall — the same reason sentence,
  restart wording, agent-ran/agent-conclusion handling, published-commits
  line and `stage:stalled` label.
- **FR-008**: A survivor job whose `spec-dir` is empty MUST still post its
  notice, and the mark-only job MUST NOT push to a guessed branch.
- **FR-009**: The split MUST NOT add, rename or remove any `workflow_call`
  input, secret or output of a published stage workflow, and MUST NOT
  introduce a new shared composite where the existing one already carries the
  behaviour.
- **FR-010**: The per-spec concurrency contract
  (`specs/013-serialize-rebase-stages/contracts/concurrency-groups.md`) and
  `.github/scripts/spec-branch-push-waivers.json` MUST both be updated to
  describe the post-split membership, with each notice-only job carrying a
  waiver that states it pushes nothing.

#### The rule stays enforced

- **FR-011**: A gate MUST fail when a survivor job in a published stage
  workflow performs both the notice effect and the mark effect from a single
  job, so a future stage cannot reintroduce the shape.
- **FR-012**: A gate MUST fail when a notice-only job declares a
  `concurrency:` block, and when the two jobs of a split pair carry
  differing `needs:` or `if:` conditions.
- **FR-013**: Every failure branch the gates in FR-011 and FR-012 ship MUST
  be exercised by a checked-in fixture, per Principle VIII.

#### Detection of an unlanded mark

- **FR-014**: When a stall notice is posted for a specification and the
  corresponding stall mark does not land, the pipeline MUST surface that
  mismatch rather than leaving the record silently inconsistent.
  [NEEDS CLARIFICATION: where does this detection live and what triggers it
  — a watchdog collector over the stalled run, a check inside the stalling
  run itself after the mark job's outcome is known, or a sweep over
  specifications carrying a `stage:stalled` label whose `spec-meta.json`
  disagrees?]
- **FR-015**: On detecting an unlanded mark, the pipeline MUST
  [NEEDS CLARIFICATION: report only — name the mismatch on the lifecycle
  issue and let a human or a later stage resolve it — or additionally
  re-attempt the mark itself, which makes the detector a writer of the spec
  branch and therefore a member of the per-spec group it is reporting on?]
- **FR-016**: Detection MUST NOT report a stall whose `spec-dir` was empty
  (there was no record to mark), nor a run a human cancelled.
- **FR-017**: Detection MUST NOT emit a duplicate report for a mismatch it
  has already reported.
- **FR-018**: A detected mismatch MUST name the specification, the stage, and
  the run whose mark was lost, so a maintainer can act without reconstructing
  the chain by hand.

#### Collateral cancel

- **FR-019**: A survivor job's mark-only job MUST NOT cause the loss of
  another run pending in the same per-spec group — specifically a
  `pr-conversation` fold leg or an implement next-iteration dispatch.
  [NEEDS CLARIFICATION: is this in scope for this feature, and if so by what
  means — the mark-only job waits for the group to be free rather than
  queuing for the single pending slot; the evictable pending work is made
  re-triggerable so an eviction is recoverable; the mark is written through a
  path that needs no per-spec ordering at all; or the residual is accepted
  and left to the FR-014 detection to name?]

### Key Entities

- **Survivor job**: the job a stage runs when its entry job failed or never
  started; its output is the record that the stage stalled.
- **Notice-only job**: the half of a split survivor job that posts the
  human-facing comment and the `stage:stalled` label, and belongs to no
  concurrency group.
- **Mark-only job**: the half that writes `stage: "stalled"` into the
  specification's record on its working branch and removes the stale
  `stage:<name>` label; the only half that needs per-spec ordering.
- **Per-spec concurrency group**: the single-file guarantee shared by every
  writer of a specification's working branch; holds one running member and
  one pending member, and the newest arrival takes the pending slot.
- **Pending-run slot**: the one waiting position a concurrency group holds.
  Both defects in this feature are consequences of its being a single slot.
- **Stall mark**: the `stage: "stalled"` state in `spec-meta.json`, the
  machine-readable half of the stall record.
- **Unlanded mark**: a stall whose notice was posted and whose mark was not
  written — the inconsistency FR-014 detects.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All five in-scope survivor jobs are split; zero jobs in any
  published stage workflow perform both the notice effect and the mark
  effect from one job.
- **SC-002**: Zero notice-only jobs declare a concurrency group, verified by
  reading every published stage workflow, so no stall notice in this
  repository can be displaced from a pending slot.
- **SC-003**: For every split pair, the two jobs' `needs:` and `if:` are
  identical, verified mechanically rather than by reading.
- **SC-004**: The notice a split stage posts for a given stall is identical
  to the notice the same stage posts today for that stall, compared across
  every combination of agent-ran, agent-conclusion and commits-published the
  existing chain-stop gates already model.
- **SC-005**: Gate 80 passes over the repository, and every notice-only job
  it now sees carries a waiver stating it pushes nothing, with no waiver
  left naming a job that no longer exists.
- **SC-006**: The `concurrency-groups.md` members table lists every
  post-split job with its actual group, and a reader of that table can tell
  which half of each stage's survivor pair writes the branch.
- **SC-007**: A stall in which the mark does not land produces exactly one
  report naming the specification, the stage and the run; a stall in which
  it does land produces none.
- **SC-008**: Every failure branch of the new gates is exercised by a
  checked-in fixture, and each new gate fails when run against that fixture.
- **SC-009**: The full PR-time gate suite passes.
- **SC-010**: A re-driven run of at least one split stage, stalled on
  purpose, records both the notice and the mark landing in the expected
  jobs — the Actions-only behaviour proven after merge rather than asserted.

## Assumptions

- The shared chain-stop composite's existing `mark-record` and `post-notice`
  inputs are the mechanism for the split; this feature adds no new composite
  and changes no default, so every caller that is not split behaves
  identically to today.
- `implement.yml`'s and `finalize.yml`'s survivor jobs are in scope even
  though the originating issue names only `tasks.yml`, cleanup and
  `pr-conversation`. They sit in the same per-spec group with the same
  notice-plus-mark shape, they take their `spec-dir` directly from a
  `workflow_call` input rather than from a prerequisite job (so their group
  expression needs no change at all), and the issue's own closing line says
  the shape applies to every stage's survivor job.
- `clarify.yml`'s survivor job stays waived and untouched: its target branch
  does not exist yet, which is a different reason with a different fix.
- Job-name churn inside a `workflow_call` stage is not a breaking change to
  the published contract (Principle VII), which is defined by inputs,
  secrets and outputs. Adopters who pin job names in branch-protection rules
  are out of scope, consistent with how spec 077 shipped the same split.
- The per-spec group's one-pending-run behaviour is GitHub's, not
  configurable; nothing in this feature attempts to change it.
- "Identical `needs:`/`if:`" is a property of a pair within one stage. The
  five stages' admission conditions differ from each other and stay that way
  — cleanup's `mark-stalled` in particular keys off `select`'s outcome, not
  an entry-job failure.
- Detection of an unlanded mark reuses the repository's existing mechanism
  for filing a machine-found problem under a pipeline-owned label
  (Principle X), rather than introducing a new reporting channel.

## Dependencies

- `specs/077-stalled-per-spec-group` — ships the split shape, the
  `mark-record`/`post-notice` inputs, and the precedent that a notice-only
  job carries no concurrency block. This feature generalizes it.
- `specs/041-implement-stall-notice` — defines the survivor-job idiom, the
  three-effect stall sequence, and the gates (29/33) that already model
  survivor-job conditions.
- `specs/013-serialize-rebase-stages` — owns the per-spec concurrency
  contract and the D4 decision this feature amends the reasoning of.
- `.github/scripts/verify-spec-branch-push-concurrency.py` (Gate 80) and
  `.github/scripts/spec-branch-push-waivers.json` — the enforcement and the
  waiver register both halves land in.
