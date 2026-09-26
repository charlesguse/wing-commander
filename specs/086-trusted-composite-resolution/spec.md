# Feature Specification: The Loop's Own Code Comes From a Trusted Commit — Composite Resolution in board-loop's Item-Branch Jobs

**Feature Branch**: `spec-draft/086-trusted-composite-resolution`

**Created**: 2026-09-25

**Status**: Draft

**Input**: Lifecycle issue #615 — "board-loop.yml's review/readiness/fix-resume
jobs resolve local actions and scripts from the item's own branch, not main"
(routed from the board loop, originating issue #468, with an additional
maintainer comment folded in)

## Overview

The board loop works one issue at a time through triage, route, fix, review
and readiness. Three of those jobs operate on the board item's own branch —
content that an agent wrote, or that an outside contributor authored — and
each of them makes that branch the **first and only** checkout in the job.
Everything the job reaches for afterwards by relative path therefore comes
from the item's branch rather than from a commit the repository trusts.

Two consequences follow, and the repository has already fixed exactly one
of them.

**Already fixed — helper scripts.** Issue #583 established that the fix,
review and readiness jobs must import `.github/scripts` and
`.github/schemas` helpers from a read-only snapshot taken from the commit
whose workflow definition is running, before any agent step. Gate 98
(`verify-board-loop-helper-provenance.py`) enforces it over every `run:`
block in those three jobs.

**Still open — composite actions.** The same three jobs reference the
loop's shared composite actions by relative path (`uses: ./.github/...`),
and a relative `uses:` resolves from the workspace, which is the item's
branch. Gate 98's allowlist inspects `run:` blocks; it says nothing about a
`uses:` reference, so the composite half of the same exposure is
unguarded. Among the composites reached this way are the ones that mint the
loop's GitHub App credential, stage untrusted issue and pull-request text
for agents, assemble agent tool allowlists and turn ceilings, validate
agent verdicts, file durable failure issues, and re-check the loop's
kill switch. The kill-switch composite is handed a token with Actions-write
scope.

Three distinct failure modes come out of this:

1. **Hard job failure on an in-flight item.** When a composite is *added*
   to one of these jobs, any item whose branch was cut before that addition
   and which reaches the job afterwards fails outright — the action
   directory simply is not on the branch. This is louder than drift but
   still a stall that needs a human.
2. **Silent drift.** An item branch carrying an older copy of a composite
   runs that older copy, with no signal that the loop's behaviour differs
   from the behaviour `main` describes.
3. **The agent can rewrite its own checks.** A fixer-authored branch that
   edits the loop's own judging surface gets that edited copy executed, in
   the job that judges the branch, holding the loop's real credentials. The
   trust-filtered issue-context staging, the agent-verdict validator, the
   findings extractor and the readiness and route backstops are all reached
   this way. Issue #504 was closed as a duplicate of this one on exactly
   that reading.

The established remedy is already in the repository. Every published stage
workflow (`clarify.yml`, `finalize.yml`, `implement.yml`, `intake.yml`,
`pr-conversation.yml`, `tasks.yml`) checks a pipeline copy into a separate
sidecar path *before* pointing the main workspace at the content it is
operating on, and resolves every composite from the sidecar.
`wing-commander-lifecycle-gate`'s header documents this as the general
rule for shared composites. The three board-loop jobs do the opposite. This
feature brings them into line and puts a gate behind the result.

### Scope of the affected surface

Confirmed on `main` at the time of writing:

- **`review`** — `Checkout the PR branch` is the job's first checkout;
  every composite reference in the job follows it. These include the
  context (credential-minting) composite, board labels, issue context,
  tool args, turn ceiling, post-agent credential status, agent verdict,
  metrics summary, durable failure issue, outstanding task item, the
  board stop check, and refresh remote — several of them at more than one
  call site, and a second cluster in the review-fixup leg.
- **`readiness`** — same shape: the item's branch is the first checkout,
  and the context, board-labels, board-stop-check, issue-context,
  outstanding-task-item and metrics-summary references follow it.
- **`fix`** — the job's first checkout takes the default ref, so the
  earliest composites resolve from trusted content. The exposure opens in
  two places. On the **resume** path, the job switches the working tree to
  an existing item branch and every later composite resolves from it. On
  **both** paths, the fixer agent holds Write/Edit on the workspace, so the
  post-agent composites — including the credential re-establishment step
  and the post-push-breach issue-context fetch — resolve from a tree the
  agent just edited.

The remaining jobs (`select`, `resolve-model`, `triage`, `route`,
`prove-gate`, `prove`) check out trusted content and are not exposed today.
They are nonetheless brought under the same rule: FR-011 settles the scope
question as every board-loop job uniformly, so the rule and its gate are one
unconditional statement rather than a per-job list — a list being the same
shape as the gap being fixed.

### Exposure as of this filing

`board-loop.yml` has never run on its `schedule` or via
`workflow_dispatch`; its only completed run was the `prove` job from the
`pull_request: closed` trigger of the pull request that shipped it. No item
has been triaged and no item branch is in flight, so there is no victim
waiting. The exposure becomes live the first time the loop picks up an item
— and failure mode 3 becomes live on the very first fixer-authored branch,
with no composite addition required.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The loop's judging code cannot be edited by the branch it judges (Priority: P1)

The maintainer relies on the loop's review and readiness passes to be an
independent check on a fixer agent's work. Today an agent that edits the
loop's own trust filter, verdict validator, findings extractor, or
readiness backstop gets its edited copy run *as that independent check*,
with the loop's credentials in hand. After this change, every job that
operates on an item branch runs the loop's own code from a commit the
repository trusts, no matter what the branch contains.

**Why this priority**: It is the security property the loop's autonomy
rests on. Principle V is non-negotiable and Principle X's bounded autonomy
is only bounded if the bounds are not editable by the thing being bounded.
Both other failure modes are availability problems; this one is a trust
problem.

**Independent Test**: Put a branch through review whose diff replaces one
of the loop's composites and one of its judging helpers with a version that
would visibly misbehave (for example, emitting a distinguishing marker or
approving unconditionally). The review pass must show the trusted
behaviour, not the branch's.

**Acceptance Scenarios**:

1. **Given** a board item branch whose diff modifies a composite action the
   `review` job references, **When** the `review` job runs on that branch,
   **Then** the composite that executes is the trusted commit's copy and
   the branch's copy is never executed.
2. **Given** a board item branch whose diff modifies a judging helper
   script the `readiness` job uses, **When** `readiness` runs, **Then** the
   readiness decision is computed by the trusted copy.
3. **Given** the `fix` job resuming on an existing item branch, **When** any
   composite in the job runs after the working tree has been pointed at that
   branch, **Then** it is the trusted commit's copy that runs.
4. **Given** the `fix` job on a freshly authored branch, **When** the
   post-agent steps run after the fixer agent has edited the workspace,
   **Then** the credential-re-establishment and post-push composites are the
   trusted commit's copies.

---

### User Story 2 - Adding a composite to these jobs never breaks an item already in flight (Priority: P1)

A maintainer who adds a new shared composite to the review, readiness or
fix path should not have to reason about which item branches were cut
before the addition. Today such an addition hard-fails any in-flight item
whose branch predates it, because the action directory is not on the
branch. After this change the composite is resolved from the trusted
commit, which always has it.

**Why this priority**: It is the failure mode that turned a long-standing
latent gap into a reported defect, it produces an outright job failure
rather than a degraded pass, and it recurs on every future composite
addition until fixed.

**Independent Test**: Take an item branch cut from an earlier commit that
lacks one of the composites the jobs reference, drive it through `review`,
and confirm the job completes rather than failing to locate the action.

**Acceptance Scenarios**:

1. **Given** an item branch cut before a composite the `review` job
   references existed, **When** `review` runs on that branch, **Then** the
   job resolves and runs the composite successfully.
2. **Given** an item branch cut before a helper script the `readiness` job
   imports existed, **When** `readiness` runs, **Then** the import succeeds
   from the trusted copy.

---

### User Story 3 - A gate keeps the rule true after this session (Priority: P2)

A maintainer editing these jobs later, or adding a new job to the loop, gets
a failing gate — not a silent regression — if a reference resolves from the
workspace. Because the rule is uniform across every board-loop job (FR-011),
a new job is covered the moment it is added, with no allowlist to update.
The gate must be able to fail its own subject.

**Why this priority**: The repository's own experience (CLAUDE.md: "a rule
with no gate behind it lasts until the next session"; Principle VIII) is
that this class of rule regresses without mechanical enforcement. It is P2
only because it protects the fix rather than delivering it.

**Independent Test**: Mutate the workflow so one reference in an affected
job resolves from the workspace instead of the trusted copy, and confirm
the gate fails; revert and confirm it passes. A self-test mode that applies
one mutation per rule is the existing house pattern.

**Acceptance Scenarios**:

1. **Given** the workflow as shipped, **When** the gate suite runs, **Then**
   the new check passes.
2. **Given** a mutation that reintroduces a workspace-resolved reference in
   an affected job, **When** the gate suite runs, **Then** the check fails
   and names the offending job and reference.
3. **Given** a mutation that removes or reorders the trusted-copy checkout
   so it no longer precedes the references that depend on it, **When** the
   gate suite runs, **Then** the check fails.

---

### Edge Cases

- **The trusted-copy checkout itself fails** (transient network, a ref that
  cannot be resolved). The job must fail before any agent step and before
  any credential is minted, rather than silently falling back to the
  workspace copy. A fallback that resolves from the item's branch would
  reintroduce exactly the defect being fixed.
- **The sidecar copy lands inside the item's working tree.** The fix job
  commits and pushes the item branch; a sidecar directory inside the
  workspace must never be staged into the item's commit. The repository has
  shipped this bug before, in the pipeline-copy path of the auto-update
  stage.
- **The gate suite runs the item's tree by design.** Checking the agent's
  change is the gate suite's job, so its invocation is not part of the
  trusted-copy rule. That exemption must be explicit and narrow, the way
  Gate 98's existing exemption for the same invocation is.
- **An item branch that deletes a composite or helper the jobs need.** With
  trusted resolution this is a no-op for the loop's own execution; the
  deletion is a finding for the review pass to report, not a job failure.
- **An item branch that adds a *new* composite the loop is expected to
  use.** It cannot be used by the job until it is on the trusted ref. This
  is the intended direction of the trade-off and should be stated, not
  worked around.
- **Two runs at different workflow versions.** An item can be triaged by
  one version of the loop and reviewed by a later one. FR-003 resolves this
  by construction: each job takes its trusted copy from the commit whose
  workflow definition is running, so within a single run the workflow
  definition, the composites and the helper scripts always agree. Across
  runs the item may be handled by two different versions of the loop, each
  internally consistent; that is accepted.
- **A branch from a fork.** If an item's pull request head is on a fork,
  the item content is fully outside the repository's control; trusted
  resolution must hold identically.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every job in the board loop MUST resolve the loop's own
  composite actions from a copy of this repository taken at the trusted ref,
  never from the workspace — unconditionally, whether or not the job puts
  board-item content in its workspace.
- **FR-002**: The trusted copy MUST be established before any step that
  resolves a composite from it, before any credential is minted, and before
  any agent step in the job.
- **FR-003**: The trusted ref MUST be the commit whose workflow definition
  is running. This is the same provenance as the helper-script and schema
  snapshot the loop already takes (issues #583/#589), so a single run's
  workflow definition, composites and helper scripts all come from one
  commit and are self-consistent by construction. A fix landed on the
  default branch mid-flight therefore takes effect on the next run of the
  loop rather than immediately; that is the accepted cost of one
  provenance.
- **FR-004**: Helper scripts and schemas MUST continue to resolve from a
  read-only, pre-agent copy of trusted content, as they do today; this
  feature MUST NOT weaken that guarantee. Because FR-003 selects the same
  commit the existing snapshot uses, composites and helpers MUST be
  presented as one provenance rule rather than two unrelated mechanisms.
- **FR-005**: The item's own content MUST remain available to the job for
  the work that legitimately needs it — reading the diff, editing files,
  committing, pushing, and running the gate suite over the change.
- **FR-006**: Establishing the trusted copy MUST be fail-closed: if it
  cannot be established, the job MUST fail before any agent step and before
  any credential is minted, with no fallback to workspace-resolved
  references.
- **FR-007**: The trusted copy MUST NOT be committed to, pushed to, or
  otherwise included in the board item's branch or pull request.
- **FR-008**: A registered gate MUST fail when any job covered by FR-001
  resolves a composite or helper from the workspace, when the trusted copy
  is not established before the first reference that depends on it, or when
  the fail-closed requirement of FR-006 is not met.
- **FR-009**: The gate of FR-008 MUST carry a self-test that applies one
  mutation per rule it enforces and asserts each mutation is caught.
- **FR-010**: The gate of FR-008 MUST state its one narrow exemption
  explicitly — the gate-suite invocation that runs the item's tree on
  purpose (FR-005) — and MUST NOT admit any broader workspace reference.
- **FR-011**: The jobs covered by FR-001 MUST be every job in the board
  loop, uniformly — including the jobs that check out only trusted content
  today (`select`, `resolve-model`, `triage`, `route`, `prove-gate`,
  `prove`). The rule and its gate are one unconditional statement, so a job
  that later gains an item checkout is covered before anyone notices. A
  per-job allowlist is the same shape as the gap being fixed and MUST NOT be
  introduced.
- **FR-012**: When a board item's branch modifies the loop's own judging
  surface — the shared composites, the helper scripts, or the workflow
  definitions the loop runs — the loop MUST rely on trusted resolution
  alone and work the item normally. It MUST NOT stand the item down, label
  it, or require a human decision on the strength of what the branch
  touches: doing so would stop the loop fixing most of the board, since the
  loop's own surface is most of what the board is about. The residual gap
  this leaves — the gate suite runs the item's tree by design (FR-005)
  while the loop's credential is in hand — is out of scope here and stays
  tracked on issue #590.
- **FR-013**: Trusted resolution MUST be unconditional: no code and no
  agent may branch on whether an item's content touches the loop's own
  surface. Each job's run record MUST show the provenance of the trusted
  copy it used — the ref and commit it was taken from — so the property is
  observable after the fact rather than inferred.
- **FR-014**: Documentation that describes how the loop's jobs obtain the
  loop's own code — those jobs' comments, the board-loop workflow contract,
  and the header that states the general rule for shared composites — MUST
  be updated to match the shipped behaviour, with one canonical statement
  and pointers from the other sites rather than repeated prose.
- **FR-015**: The change MUST NOT alter what the loop decides about a board
  item — its eligibility, routing, findings, readiness verdict or round
  accounting — beyond the cases where the item's branch was previously
  supplying the deciding code.

### Key Entities

- **Board item**: the open issue the loop is working, together with its
  branch and pull request. Its branch content is untrusted.
- **Item-branch job**: a board-loop job whose workspace holds board-item
  content at some point in its execution — today `fix` (resume path, and
  every post-agent step on both paths), `review`, and `readiness`. These are
  where the defect is observable; the rule of FR-001 applies to every job
  regardless.
- **Trusted copy**: a checkout of this repository at the commit whose
  workflow definition is running, kept separate from the item's workspace,
  from which the loop's own composites and helpers resolve.
- **Judging surface**: the parts of the loop that decide something about an
  item — the untrusted-content filter, the agent-verdict validator, the
  findings extractor, the readiness and routing backstops, the kill-switch
  check — plus the credential-minting composite that arms them.
- **Provenance gate**: the registered check that asserts every reference in
  an item-branch job resolves from the trusted copy.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Of the references to the loop's own composites and helpers in
  every board-loop job, 100% resolve from the trusted copy; the only
  workspace-resolved invocation left is the gate suite over the item's
  change.
- **SC-002**: A branch that rewrites any part of the judging surface
  produces byte-identical loop behaviour to a branch that does not, in a
  demonstration run covering the review and readiness passes.
- **SC-003**: An item branch cut before a composite or helper the jobs
  reference existed completes `review` and `readiness` without a
  resolution failure — the failure mode reported on this issue occurs zero
  times.
- **SC-004**: The provenance gate fails on every one of its mutations in
  self-test and passes on the shipped workflow, and is registered in the
  gate suite that pull requests run.
- **SC-005**: A maintainer adding a composite to one of these jobs needs no
  reasoning about in-flight branch age: the number of branch-age
  preconditions such an addition carries is zero, stated in the contract.
- **SC-006**: No board item's pull request contains the trusted copy's
  files, across every demonstration run.

## Assumptions

- The loop's exposure is read as a trust boundary, not only as a drift
  annoyance. Issue #504 was closed as a duplicate on that reading, and the
  maintainer's comment on this issue restates it; this spec treats the
  trust property (User Story 1) as the primary deliverable.
- `board-loop.yml` is not a published, adopter-called stage, so the trusted
  copy is this repository at the commit whose workflow definition is running
  (FR-003) — there is no adopter-supplied pipeline ref to resolve, and no
  new typed input is implied.
- The existing helper-script snapshot and its gate are correct and stay;
  this feature extends the same guarantee to composites rather than
  replacing the mechanism.
- Fixing this makes the reported hard-failure mode impossible for future
  composite additions, so no migration or backfill for already-cut branches
  is needed. No item branch is in flight at filing time in any case.
- The fixer and review-fixup agents keep write access to the item's
  workspace; this feature changes where the loop's *own* code comes from,
  not what an agent may edit.
- The gate suite deliberately runs the item's tree, and that exemption
  survives unchanged.
- Jobs that check out only trusted content today (`select`, `triage`,
  `route`, `prove-gate`, `prove`) are not defective. FR-011 brings them
  under the same uniform rule anyway, for the durability of the rule and its
  gate, not as a correctness claim about them.
- The gate suite running the item's tree while the loop's credential is in
  hand remains a real residual exposure. FR-012 deliberately leaves it
  alone; it is tracked on issue #590 and is not re-opened here.

## Out of Scope

- Changing what the loop decides about an item, its round budget, its
  eligibility ordering, or its merge policy.
- Publishing `board-loop.yml` as a reusable stage, or adding adopter-facing
  inputs to it.
- Re-litigating the helper-script snapshot shipped for issue #583 or its
  gate.
- The pipeline-copy arrangements in the published stage workflows, which
  already follow the rule this feature adopts.
- Sandboxing or otherwise restricting what the fixer agent may edit in the
  item's workspace.
- Standing an item down, labelling it, or holding it for a human because its
  branch touches the loop's own judging surface — settled against by FR-012.
- Closing the residual exposure of the gate suite running the item's tree
  while the loop's credential is in hand; that is tracked on issue #590.
