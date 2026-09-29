# Feature Specification: A Post-PR Failure Policy for the Finalize Stage

**Feature Branch**: `spec-draft/105-finalize-post-pr-stall-policy`

**Created**: 2026-09-29

**Status**: Draft

**Input**: Lifecycle issue #777 — "finalize: a failed \"Announce remaining
manual work\" step stalls the lifecycle, but the stall notice doesn't name
it" (routed from `board-loop.yml` as `agent_proposed_spec`; originating
issue #662; the defect was found by the code review of #647)

## Overview

The finalize stage does its durable work — open or refresh the final PR,
flip the lifecycle issue to `stage:review`, mirror the labels onto the PR
— and then spends seven more steps telling people about it: request a
re-review, announce the PR, commit `stage: review` into `spec-meta.json`,
and post either the remaining-manual-work callout or the "no manual work
remains" one. Every one of those seven steps hard-fails the job.

On finalize run `36264390069` (spec 069, lifecycle issue #516) the last
of them — "Announce remaining manual work on the lifecycle issue" — hit a
transient `GraphQL: Something went wrong`. The PR was already open. The
issue was already `stage:review`. But the job went red, the `stalled` job
ran, and the lifecycle came out of it in a state that describes no real
situation: the issue carried `stage:review` **and** `stage:stalled` at
once, `spec-meta.json` had been rewritten from `stage: review` back to
`stage: stalled`, and the stall notice said only that "a step after it did
not complete" — because the failing step is not one of the three entries
in finalize's `candidates-json`. The branch sat for two days.

Two distinct defects produced that. The narrow one is diagnostic: the
stall notice cannot name a step that is not in the candidates list, and
finalize's list covers three of its ten hard-failing post-agent steps. The
wider one is policy: finalize currently treats "the announcement did not
post" and "the PR was never opened" as the same class of failure, even
though by the time the announcements run the stage's contract with the
next stage is already satisfied and the only recovery on offer —
re-dispatch finalize — re-runs a paid agent step to retry one comment.

This feature settles the policy first and makes the diagnosis follow from
it: whatever set of post-PR steps is still allowed to stall the lifecycle
must be nameable in the stall notice, and the lifecycle state a stall
leaves behind must not contradict itself.

### Observed facts (verified against `main` at `bad1021`)

- `.github/workflows/finalize.yml:1406-1416` — the "Determine failed
  post-agent step" step passes exactly three candidates: "Verify agent
  output", "Verify the final pull request was created", and "Flip stage
  label".
- Seven hard-failing (non-`continue-on-error`) steps run **after** "Verify
  the final pull request was created" and are absent from that list:
  "Report re-review request failure" (`finalize.yml:1276`), "Compose
  review-announcement summary" (`:1289`), "Announce the implementation PR
  for review" (`:1309`), "Commit metadata (stage -> review)" (`:1328`),
  "Check for remaining manual work" (`:1354`), "Announce remaining manual
  work on the lifecycle issue" (`:1365`), and "Announce no remaining
  manual work on the lifecycle issue" (`:1376`). Five of the seven carry
  no `id:` at all, so they cannot be referenced by a candidate entry until
  one is added.
- `wing-commander-failed-post-agent-step` reads only the array it is
  handed; its own description states it "does not, and cannot, read the
  caller's own `steps` context to recover that order or to discover which
  steps exist". Completeness of the list is therefore a hand-maintained
  property with nothing checking it
  (`.github/actions/wing-commander-failed-post-agent-step/action.yml`).
- With an empty `failed-post-agent-step`,
  `wing-commander-stall-reason` falls to "the agent step ran (concluded:
  …) and a step after it did not complete"
  (`.github/actions/wing-commander-stall-reason/action.yml`), which is
  what #516 received.
- `wing-commander-callout` posts with a single bare
  `gh issue comment … --body-file` and no retry
  (`.github/actions/wing-commander-callout/action.yml`). One transient
  API error fails the step. Every stage's announcements share this
  composite.
- `wing-commander-chain-stop-notice` adds `stage:stalled` unconditionally
  and removes the caller's `stage-label` only
  (`action.yml:153-156`). Finalize passes `stage-label: "stage:finalize"`
  (`finalize.yml:1530`), which "Flip stage label" removed several steps
  earlier — so `stage:review` survives beside `stage:stalled`, exactly as
  #516 shows.
- The same composite's "Mark lifecycle record stalled" step rewrites
  `.stage = "stalled"` into `spec-meta.json` and pushes it
  (`action.yml:120-140`), overwriting the `stage: review` that finalize's
  "Commit metadata (stage -> review)" step had already committed and
  pushed on the same branch.
- Re-dispatching finalize is not a cheap retry. With the final PR open,
  "Check for an existing final pull request" yields `pr-state=open` and
  "Check for a diff …" yields `skip=false`
  (`finalize.yml:542-614`), so the whole job — including the agent step at
  `finalize.yml:682` — runs again to reach the announcement that failed.
- The gap is not unique to finalize. `intake.yml:1430`, `clarify.yml:1222`,
  `tasks.yml:1499`, `implement.yml:2938`, `pr-conversation.yml:1467` and
  `rebase.yml:1042` each pass a hand-written subset of their own
  hard-failing post-agent steps; `implement.yml` lists two and `rebase.yml`
  one.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The stall notice names the step that actually failed (Priority: P1)

A maintainer opens a lifecycle issue that has just gone `stage:stalled`
during finalize. They want the notice to tell them which step stopped the
run, so they can decide in one read whether it was the PR creation, the
label flip, or a comment that did not post — three situations with three
different recoveries.

**Why this priority**: It is the defect the issue was filed for, it is
independent of the policy question below (whichever steps remain able to
stall, they must be nameable), and it is what turned #516's two-day freeze
into a mystery rather than a two-minute fix.

**Independent Test**: Force each hard-failing post-agent step of finalize
to fail in turn and read the resulting stall notice. Every run names the
step that failed, using the step's own `name:` text.

**Acceptance Scenarios**:

1. **Given** a finalize run whose "Announce remaining manual work on the
   lifecycle issue" step fails and whose earlier steps all succeeded,
   **When** the `stalled` job posts its notice, **Then** the notice names
   that step rather than saying "a step after it did not complete".
2. **Given** a finalize run where two hard-failing post-agent steps fail,
   **When** the notice is composed, **Then** it names the later of the two
   in job order, matching the existing composite's documented contract.
3. **Given** a `continue-on-error` step that raw-failed (the credential
   re-establishment pair, the over-budget callout, "Fail loud on
   non-healthy agent verdict", "Open or update the final pull request"),
   **When** the notice is composed, **Then** that step is never named as
   the cause.
4. **Given** the stall notice names a post-PR step, **When** a maintainer
   reads its restart instruction, **Then** the instruction reflects what
   actually needs re-doing — not a blanket re-dispatch of a stage whose
   PR is already open.

---

### User Story 2 - A failed announcement leaves one coherent lifecycle state (Priority: P1)

A maintainer looking at the issue, the labels and `spec-meta.json` after a
post-PR failure wants all three to agree. Today they can disagree with
each other and with the open PR sitting in review, and nothing in the
repository tells the maintainer which one to believe.

**Why this priority**: The contradictory state is what actually froze the
branch in #516 — the PR was reviewable the whole time, but the issue
looked stalled and the record said `stage: stalled`, so nobody touched
it. It is separable from User Story 1: naming the step and choosing the
policy are independent improvements.

**Independent Test**: Drive a finalize run that reaches the announcements
and then fails one, and read the labels, `spec-meta.json` and the issue
comments. No two of them may describe different stages.

**Acceptance Scenarios**:

1. **Given** finalize has opened the final PR and flipped the issue to
   `stage:review`, **When** a later step fails, **Then** the issue does
   not end the run carrying both `stage:review` and `stage:stalled`.
2. **Given** the same run, **When** it ends, **Then** `spec-meta.json`'s
   `stage` field and the issue's `stage:*` label agree with each other and
   with whether the final PR is open.
3. **Given** the same run, **When** a maintainer reads the lifecycle
   issue, **Then** exactly one comment describes the outcome, and it makes
   clear whether the PR is reviewable now or whether the stage must be
   re-driven first.
4. **Given** a finalize run that fails **before** the final PR exists,
   **When** it ends, **Then** today's stall behaviour is unchanged — the
   issue is marked stalled and the stage must be re-dispatched.

---

### User Story 3 - A transient API error does not cost a lifecycle (Priority: P2)

A maintainer whose finalize run met one `GraphQL: Something went wrong`
wants the pipeline to shrug it off. The announcement is worth retrying;
it is not worth a paid agent re-run or two days of a frozen branch.

**Why this priority**: It addresses the root cause of #516 rather than its
symptoms, and it is the part that generalises — every stage's
announcements go through the same unretried composite. It is P2 because
Stories 1 and 2 already make the incident survivable and diagnosable
without it.

**Independent Test**: Make the announcement's first API call fail and its
second succeed. The comment posts, the run stays green, and the lifecycle
issue is never labelled `stage:stalled`.

**Acceptance Scenarios**:

1. **Given** an announcement whose first attempt fails transiently,
   **When** the step runs, **Then** it retries and the comment is posted
   without the run going red.
2. **Given** an announcement that fails every attempt, **When** the step
   finishes, **Then** the outcome is recorded where a maintainer can see
   it — in the run and on the lifecycle issue — and the content that could
   not be posted is not silently lost.
3. **Given** a retry is added, **When** the number of attempts is
   exhausted, **Then** the behaviour that follows is the one User Story 2
   defines for a post-PR failure, not a separate third path.

---

### User Story 4 - The candidates list cannot silently fall behind again (Priority: P2)

A contributor adds a hard-failing step to a stage's post-agent tail. They
want to find out at gate time, not during the next incident, that the
stall notice can no longer name it.

**Why this priority**: Constitution VIII — the existing arrangement reads
as coverage ("the notice names the failing step") while proving nothing
about the steps nobody remembered to list, and this gap was found by
accident during a code review, which is precisely the failure mode VIII
names. P2 because it prevents recurrence rather than fixing the incident.

**Independent Test**: Add a new hard-failing post-agent step to a stage
job without adding it to that job's `candidates-json`, run the local gate
suite, and observe a failure naming the step. Revert and observe a pass.

**Acceptance Scenarios**:

1. **Given** a stage job with a hard-failing post-agent step missing from
   its `candidates-json`, **When** the gate suite runs, **Then** it fails
   and names the step and the workflow.
2. **Given** a `continue-on-error` post-agent step absent from
   `candidates-json`, **When** the gate runs, **Then** it passes — such a
   step is excluded by construction and must not be demanded.
3. **Given** a candidate entry whose steps are listed out of job order,
   **When** the gate runs, **Then** it fails, because the composite's
   "last failing candidate wins" rule depends on the order.
4. **Given** the gate, **When** a maintainer runs
   `python .github/scripts/run-local-gates.py`, **Then** it runs there
   with the same subject and arguments CI uses, and fails loudly if it
   cannot reach any workflow to inspect.

---

### Edge Cases

- A post-PR step fails on a **refresh** run (`pr-state == 'open'`, a
  re-review already requested) rather than a create run. The PR was
  already in review before this run started; the stall must not un-review
  it.
- "Commit metadata (stage -> review)" fails because `rebase.yml`
  force-pushed the same spec branch mid-run. The PR is open and labelled,
  but the record still says `implement`. This is a durable-state failure,
  not a cosmetic one — it may warrant different treatment from a failed
  comment.
- Both an announcement **and** the credential re-establishment fail.
  `stall-reason` already has a combined branch for this; whatever policy
  is chosen must not make that branch unreachable.
- `stage:stalled` is added by `chain-stop-notice` with `|| true`, so the
  label write can silently no-op. A policy that depends on the label being
  absent must not depend on the removal having succeeded.
- A finalize run is cancelled (not failed). The `stalled` job is gated on
  `!cancelled()`; nothing here may change that.
- The final PR is already `merged` or `closed` when finalize re-runs —
  `skip=true` short-circuits the whole tail, so no post-PR step runs and
  no stall notice should claim one did.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The finalize stage MUST be able to name, in its stall
  notice, any of its own hard-failing post-agent steps that ended the run
  — including every step that runs after the final PR is verified open.
- **FR-002**: Each such step MUST carry a stable identifier so it can be
  referenced, and MUST be listed in the stage's failed-step candidates in
  the same order it runs, so the existing "last failing candidate wins"
  rule keeps selecting the right one.
- **FR-003**: Steps that cannot be the job's point of failure —
  `continue-on-error` steps, whose conclusion is always `success` — MUST
  remain excluded from the candidates, and the reason MUST stay stated at
  the call site.
- **FR-004**: A failure of a post-PR announcement step, after the final PR
  is open and the lifecycle issue is labelled, MUST be handled as
  [NEEDS CLARIFICATION: should such a failure stall the lifecycle at all?
  (a) keep today's stall, with the step now named; (b) tolerate it — warn
  on the run, report it on the issue, and leave the lifecycle at
  `stage:review`; (c) tolerate it only after a bounded retry, and stall if
  the retries are exhausted].
- **FR-005**: Whatever FR-004 resolves to, a finalize failure that occurs
  **before** the final PR is verified open MUST keep today's behaviour:
  the lifecycle is marked stalled and the stage must be re-dispatched.
- **FR-006**: When a run does stall after the stage's durable work
  completed, the lifecycle issue MUST NOT be left carrying two
  contradictory `stage:*` labels.
- **FR-007**: When a run does stall after the stage's durable work
  completed, `spec-meta.json`'s `stage` field MUST end the run consistent
  with the label and with the PR's actual state, rather than being
  reverted to `stalled` over a value the same run already committed.
  The reconciliation MUST be [NEEDS CLARIFICATION: which record wins —
  (a) the stall notice stops rewriting `stage` once the stage's durable
  work is recorded as done; (b) finalize signals "durable work complete"
  to the survivor job, which then marks a distinct state (e.g.
  `review-degraded`) instead of `stalled`; (c) the label and the record
  both stay `review` and the failure is reported as a comment only].
- **FR-008**: The stall notice's restart instruction MUST describe a
  recovery that matches what actually failed — in particular it MUST NOT
  tell a maintainer to re-dispatch finalize when doing so would re-run the
  agent step solely to retry an announcement.
- **FR-009**: A lifecycle-issue announcement MUST survive a single
  transient API error without failing its step, via a bounded retry in the
  one place announcements are posted, so the fix cannot be applied to one
  call site and missed at the others.
- **FR-010**: When an announcement cannot be posted after its retries are
  exhausted, the content that could not be posted MUST be recoverable from
  the run (for example in the step summary), and the failure MUST be
  visible rather than swallowed.
- **FR-011**: A deterministic, registry-reachable gate MUST fail when a
  stage job has a hard-failing post-agent step that its `candidates-json`
  does not list, or lists out of job order.
- **FR-012**: The gate's scope MUST be [NEEDS CLARIFICATION: does this
  feature fix only finalize's candidates list and gate the rest as
  pre-existing debt, or does it also complete the candidate lists of the
  other six consuming stages (`intake`, `clarify`, `tasks`, `implement`,
  `pr-conversation`, `rebase`) in the same change?].
- **FR-013**: The gate MUST be exercised by checked-in fixtures covering
  each failure branch it ships — a missing candidate, an out-of-order
  candidate, and a `continue-on-error` step correctly omitted — and MUST
  fail loudly rather than pass when it cannot reach a workflow to inspect.
- **FR-014**: Every comment this feature adds or edits in a workflow or
  composite MUST have exactly one canonical home, with the other consuming
  stages pointing at it, per the repository's single-home rule.

### Key Entities

- **Failed-step candidate**: a `{name, conclusion}` pair naming one
  hard-failing post-agent step of a stage job, ordered by execution
  position; consumed by the stall notice to name the cause.
- **Post-PR tail**: the finalize steps that run after the final pull
  request is verified open — the re-review report, the review
  announcement, the metadata commit, and the two remaining-manual-work
  callouts. The stage's contract with its reviewer is already satisfied
  when these run.
- **Lifecycle state**: the triple of the issue's `stage:*` label,
  `spec-meta.json`'s `stage` field, and the final PR's open/merged/closed
  state. Any two of the three disagreeing is the condition this feature
  eliminates for the post-PR tail.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every hard-failing post-agent step of the finalize job,
  a run in which that step is the one that fails produces a stall notice
  naming it; zero such runs produce the generic "a step after it did not
  complete" wording.
- **SC-002**: A lifecycle issue never ends a finalize run carrying two
  `stage:*` labels, and its `spec-meta.json` `stage` never disagrees with
  the label it ends with.
- **SC-003**: A post-PR announcement that meets one transient API error
  and succeeds on retry costs zero stalled lifecycles and zero additional
  agent invocations.
- **SC-004**: A maintainer reading only the lifecycle issue after a
  post-PR failure can state, without opening the run, whether the final PR
  is reviewable now — measured by the notice containing that fact
  explicitly.
- **SC-005**: Adding a hard-failing post-agent step to any stage job
  without listing it in that job's candidates fails the local gate suite,
  demonstrated by a checked-in fixture rather than a one-off manual run.
- **SC-006**: The time from a transient post-PR announcement failure to a
  reviewable, correctly-labelled lifecycle drops from the two days
  observed on #516 to zero maintainer actions.

## Assumptions

- The `GraphQL: Something went wrong` seen on run `36264390069` was
  transient GitHub-side flakiness, not a token, permission or rate-limit
  condition — a retry would have succeeded. Persistent failures remain
  failures under every option FR-004 offers.
- `wing-commander-callout` is the single home for lifecycle-issue
  announcements across all stages, so a retry added there covers finalize
  and every other stage at once; no per-stage retry wrappers are wanted.
- The existing `wing-commander-failed-post-agent-step` contract — an
  explicit caller-ordered list read via `.conclusion`, never a runtime
  scan of the `steps` context — stands. This feature completes and gates
  the lists; it does not replace the composite's design.
- The finalize job's step order is stable enough for an ordering check;
  the gate reads the shipped workflow rather than a transcribed copy.
- Naming a step in the stall notice uses the step's own `name:` text, per
  the composite's existing polish decision, not its `id:`.
- Gate numbering and the choice of which existing gate script to extend
  are planning decisions, not specification ones.

## Out of Scope

- The `stalled` job's own admission condition. Its `if:` requires
  `needs.verify-image-prerequisites.result != 'failure'` and then offers
  `needs.verify-image-prerequisites.result == 'failure'` as a disjunct,
  which can never be true; the same shape appears in six stages. Reported
  separately rather than folded in here.
- Retrying or re-driving the finalize **agent** step. This feature only
  changes what happens around it.
- The one-PR-per-spec guard, the no-diff anomaly path, and the refresh
  behaviour introduced by the finalize-refresh feature — all unchanged.
- Any change to how the watchdog classifies the runs this feature makes
  green instead of red.
