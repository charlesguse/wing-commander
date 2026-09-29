# Feature Specification: An Auth-Refused Rebase Publish Is Reported as a Credential Failure, Not a Branch Race

**Feature Branch**: `spec-draft/104-rebase-publish-auth-refusal`

**Created**: 2026-09-29

**Status**: Draft

**Input**: Lifecycle issue #775 — "rebase.yml: report an auth-refused publish
push as a credential failure, not a branch race" (routed from board-loop.yml,
reason `contract_widening`; originating issue #661, itself found by the code
review of #641)

## Overview

`rebase.yml`'s `rebase` job ends in one of two arms. "Publish rebased branch"
pushes the rebased result with `git push --force-with-lease`; "Abandon and
escalate" comments on the lifecycle issue when the rebase could not be
completed. Spec 073 gave this job the full post-agent credential remedy: the
bot credential is re-established after the agent step, the checkout's persisted
remote is re-authenticated, and the combined outcome is folded into one
job-local status the escalation arm reads so it can name the credential as the
cause of a failure (FR-003, FR-004).

The publish arm never got that treatment. Its `else` branch treats **every**
refused push as one thing:

```
::warning::<branch>: force-with-lease push rejected (branch moved since
checkout) — skipping this run, no comment.
```

That reading is correct for the case it was written for — the lease compares
against the tip recorded at checkout, and a branch that moved underneath the
run should be skipped silently so the next run retries. It is wrong for the
case spec 073 was written for. When the post-agent credential re-establishment
has already failed, the push is refused for **authentication**, the run prints
a message asserting a race that did not happen, and the job ends **green**. The
maintainer is told nothing, the agent's conflict resolution is discarded
unpublished, and nothing anywhere in the run names the credential.

This is the outcome spec 073's FR-003 forbids ("report the credential as the
cause in its own outcome reporting ... rather than leaving a later step to fail
with an unexplained authentication error") and FR-004 forbids ("a maintainer
reading the escalation comment can tell a genuine conflict from a timed-out
credential"). The publish arm is the one bot-acting step in the job that was
left able to swallow the signal.

### Why the information is already in the job, and why it is out of reach

The job already computes exactly the fact the publish arm needs. "Determine
post-agent credential status" folds the re-mint and remote-refresh outcomes
into a single `ok`, and the escalation arm below it reads that value. But the
step sits **below** "Publish rebased branch", so the publish arm cannot read
it. The ordering is deliberate and documented: spec 052's live contract
`specs/052-agent-credential-lifetime/contracts/wing-commander-context-relay.md`
records that the status step is "deferred to the job's own last steps — after
every business-logic/report step the agent step's own success gates, so a
warning here cannot strand any of them", and names its rebase.yml placement as
"after the job's last bot-acting step that does not itself depend on it
(`Publish rebased branch`)".

Publish now *does* depend on it. That contract line and the placement it
describes are what this feature changes, which is why this is routed as a spec
rather than a drive-by fix: a documented placement convention shared with eight
other stages is being narrowed for one job, and the reason the deferral existed
(a status warning must not strand the business-logic steps below it) has to be
shown still to hold.

### Why nothing fails today

Nothing checks this. Gate 68 (`verify-post-agent-credential-refresh.py`)
inspects rebase.yml's publish arm for the *credential it holds*
(`mut_rebase_publish_reverted` asserts `GH_TOKEN` is the post-agent
`env.WC_BOT_TOKEN`, not the pre-agent mint). It does not inspect what the arm
*does* when the push using that credential is refused. A step can hold a
perfectly fresh credential and still misreport its own failure, and no gate in
the suite can currently tell the difference.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A refused publish after a failed re-mint is reported as a credential failure (Priority: P1)

The rebase agent spends a long time resolving conflicts. The post-agent
credential re-establishment fails. The publish push is then refused for
authentication. The maintainer expects to be told that the credential is the
reason — loudly, with the run red — not to see a green check and a warning
asserting that some other run moved the branch.

**Why this priority**: This is the defect. It converts a credential failure
into silence, discards the agent's completed work, and does so on the exact
path spec 073 was written to make legible. Every other story here exists to
keep this one honest.

**Independent Test**: Drive the shipped publish step against a git remote that
refuses the push, with the post-agent credential status reporting failure, and
confirm the step fails the job with an error that names the credential and
never claims the branch moved.

**Acceptance Scenarios**:

1. **Given** a `rebase` job whose post-agent credential status reports failure,
   **When** the publish push is refused, **Then** the step fails the job and
   emits an error naming the post-agent credential re-establishment as the
   cause, and does **not** emit the "branch moved since checkout" message.
2. **Given** the same job, **When** the run finishes, **Then** the run's
   conclusion is a failure a maintainer sees on the pull request, not a green
   check carrying a warning.
3. **Given** a `rebase` job whose post-agent credential status reports failure,
   **When** the publish push nevertheless **succeeds**, **Then** the run
   behaves exactly as a successful publish does today — the rebased branch is
   published and any stale `rebase:blocked` label is dropped. A credential the
   status step could not confirm is not, by itself, grounds to discard a
   rebase that did in fact publish.

---

### User Story 2 - A genuine branch race is still tolerated silently (Priority: P1)

Two runs overlap and the second one's lease is stale because the branch really
did move. The maintainer expects today's behaviour: a warning, a step-summary
note, no lifecycle comment, no red run, and the next run retrying.

**Why this priority**: Equal to Story 1 and inseparable from it. The tolerant
arm exists because this race is routine and self-correcting; a fix that makes
every refusal red would replace a silent-failure defect with a noisy-alarm
defect and train maintainers to ignore the signal Story 1 adds.

**Independent Test**: Drive the shipped publish step against a remote that
refuses the push, with the post-agent credential status reporting healthy, and
confirm the outcome is byte-identical to today's tolerated warning.

**Acceptance Scenarios**:

1. **Given** a `rebase` job whose post-agent credential status reports healthy,
   **When** the publish push is refused, **Then** the step emits today's
   "branch moved since checkout" warning and step-summary lines unchanged, posts
   no lifecycle comment, and does not fail the job.
2. **Given** a clean rebase that needed no agent work — so the credential status
   step did not run and reports nothing at all — **When** the publish push is
   refused, **Then** the tolerant arm is taken, exactly as today. An absent
   status is not a failed status.
3. **Given** any rebase whose publish push **succeeds**, **When** the job runs,
   **Then** its step summary, its `rebase:blocked` auto-recovery and its
   lifecycle-issue interactions are unchanged from today.

---

### User Story 3 - The distinction is pinned by a check that can fail (Priority: P1)

A maintainer edits the publish arm — reordering the steps back, dropping the
status read, or collapsing the two arms again. They expect the gate suite to
fail on that pull request and say which distinction was lost.

**Why this priority**: P1, not P2, because the defect's whole history is that
the behaviour was never checkable. Gate 68 inspects the credential the arm
holds but not what the arm does with a refusal, so the misreport survived spec
073's own gate and its self-test. Shipping the fix without a check that can
fail leaves the next edit free to reintroduce it.

**Independent Test**: Reintroduce each regression — the tolerant message
emitted on a known-bad credential, the status read deleted, the status step
moved back below the publish step — and confirm the check fails naming the
regression in each case.

**Acceptance Scenarios**:

1. **Given** the publish arm reverted to treating every refusal as a branch
   race, **When** the gate suite runs, **Then** it fails and names the lost
   credential-failure reporting.
2. **Given** the credential-status step moved back below the publish step so
   the publish arm's read resolves to nothing, **When** the gate suite runs,
   **Then** it fails — a read that silently resolves to empty is the same
   defect wearing the fix's clothes.
3. **Given** an unmodified repository, **When** the gate suite runs locally and
   in CI, **Then** the check runs in both with the same subject and arguments
   and passes.
4. **Given** the publish step deleted or renamed out of the check's reach,
   **When** the gate suite runs, **Then** it fails loudly rather than passing
   over a subject it could not find.

---

### Edge Cases

- **The status step reports healthy but the refusal is still an auth refusal.**
  A credential can be well-formed and freshly minted and still be refused —
  a revoked installation, a branch protection rule, a lost permission. The
  status output is evidence about the re-establishment, not about the remote's
  answer. See [NEEDS CLARIFICATION 2].
- **The credential status step was skipped.** On a clean rebase the agent step
  never runs, so the status step is gated off and its output is empty. Empty
  must take the tolerant arm; treating unset as failure would turn every
  clean-rebase race red (User Story 2, scenario 2).
- **The run was cancelled.** The publish arm is `!cancelled()`-gated today for
  a reason spec 073 recorded — a cancelled leg must not force-push. Nothing
  here may weaken that, and a cancelled leg must not report a false credential
  failure.
- **`rebase.yml` runs as a matrix.** Each leg is its own job instance with its
  own mint, its own status, and its own publish arm; the distinction must hold
  per leg.
- **The push fails for a reason that is neither a race nor the credential** —
  a network error, a hook rejection, a protected-branch refusal. Today all of
  these are labelled "branch moved" too.
- **Moving the status step up must not strand the publish arm.** The status
  step's deferral existed so its warning could not strand the business-logic
  steps below it. The move is only safe while the status step cannot itself
  fail the job.
- **A failing publish step changes what runs below it.** The escalation arm is
  gated on the rebase outcome, not on the publish outcome, so a loud publish
  failure does not by itself reach the lifecycle issue. See
  [NEEDS CLARIFICATION 1].

## Requirements *(mandatory)*

### Functional Requirements

**Telling the two refusals apart**

- **FR-001**: In `rebase.yml`'s `rebase` job, the publish arm MUST be able to
  read the job's post-agent credential status at the moment it handles a
  refused push. The value MUST be the same one the abandon/escalate arm reads —
  one status, one home, not a second computation of the same fact.
- **FR-002**: When the publish push is refused **and** the post-agent
  credential status reports failure, the step MUST fail the job and MUST emit
  an error that names the post-agent credential re-establishment as the cause,
  identifying the workflow, the job and the step, in the same spirit as spec
  073's FR-003. It MUST NOT emit the "branch moved since checkout" message on
  this path.
- **FR-003**: When the publish push is refused and the post-agent credential
  status reports healthy **or** reports nothing at all (the agent step was
  skipped, so the status step did not run), the step MUST take today's
  tolerant path unchanged: the same warning text, the same step-summary lines
  including the captured push error, no lifecycle comment, and no job failure.
- **FR-004**: The publish push MUST still be attempted regardless of the
  credential status. A status of "failed" MUST NOT short-circuit the push: the
  status describes the re-establishment, not the remote's answer, and a push
  that succeeds anyway MUST produce today's success behaviour in full,
  including the `rebase:blocked` auto-recovery.
- **FR-005**: The credential status MUST be computed before the publish arm
  needs it. Reordering the job to achieve this MUST NOT weaken the existing
  gating semantics of any step it moves past, MUST NOT cause the status step to
  be able to fail the job, and MUST NOT make it possible for the status step's
  own warning to strand the publish arm or the escalation arm below it.
- **FR-006**: Every step's existing `if:` semantics MUST be preserved:
  post-agent steps still run when the agent step failed, still do not run when
  the workflow was cancelled, and the publish and abandon/escalate arms keep
  the conditions that decide which of them runs.
- **FR-007**: A refusal classified as a credential failure MUST be surfaced to
  the maintainer through [NEEDS CLARIFICATION 1: a loud red job and an
  `::error::` only, or should the lifecycle issue also be told — and if so,
  through the existing abandon/escalate arm (which would also stamp
  `rebase:blocked`) or through a separate credential-specific comment?].
- **FR-008**: A refused push whose post-agent credential status reports healthy
  MUST be classified by [NEEDS CLARIFICATION 2: the credential status alone
  (so an auth refusal with a healthy status keeps today's "branch moved"
  wording), or must the push error itself also be consulted so that a refusal
  the remote answered with an authentication or permission error is never
  described as a race?].

**Keeping it checkable**

- **FR-009**: A deterministic check MUST fail when the publish arm can no
  longer tell a credential-caused refusal from a branch race — specifically
  when the tolerant message is emitted on a known-bad credential, when the
  credential-status read is removed from the arm, or when the status step is
  positioned so that the arm's read resolves to nothing.
- **FR-010**: The check MUST exercise the **shipped** step's own logic against
  a real refused push, not a paraphrase of it. A check that re-implements the
  branch it is asserting cannot fail when the workflow diverges from it.
- **FR-011**: The check MUST cover, at minimum: a push that succeeds (behaviour
  unchanged), a push refused with a healthy credential status (tolerated,
  unchanged), a push refused with a failed credential status (fails loudly,
  never called a race), and a push refused with no credential status at all
  (tolerated).
- **FR-012**: The check MUST fail loudly rather than pass when it cannot reach
  its subject — the workflow missing, the job absent, or the publish step
  deleted or renamed beyond recognition — restating spec 052's FR-022 rule for
  this new subject.
- **FR-013**: The check MUST run with the same subject and the same arguments
  locally (`run-local-gates.py`) as in CI, and MUST be triggered by changes to
  `rebase.yml`.
- **FR-014**: Gate 68's existing coverage of `rebase.yml` MUST continue to pass
  unchanged, including its position and reference checks and its self-test
  mutations for this job. The reordering in FR-005 MUST be shown not to weaken
  it.

**Not changing anything else**

- **FR-015**: Observable behaviour on every path that does not hit the defect
  MUST be unchanged: a successful publish, a clean rebase, a tolerated branch
  race, and the abandon/escalate path all produce the same outcomes, comments,
  labels, branches and artifacts as today.
- **FR-016**: The live contract that documents the credential-status step's
  placement and the reason for its deferral
  (`specs/052-agent-credential-lifetime/contracts/wing-commander-context-relay.md`)
  MUST be updated in the same change, so the documented placement and the
  shipped placement are the same placement. The contract MUST state why the
  deferral's original purpose still holds after the move.
- **FR-017**: No published `workflow_call` input, secret or output of
  `rebase.yml` may change, and no composite's declared input surface may be
  widened. Any shared logic MUST be consumed from its existing single home
  rather than re-pasted into the workflow.
- **FR-018**: The change touches an `if:`, a failing step, and step ordering in
  a workflow, so it MUST get a pass from the `review-step-gating` skill before
  merge, per CLAUDE.md.

### Key Entities

- **Publish arm**: `rebase.yml`'s "Publish rebased branch" step — the shared
  exit for a clean rebase and a scope-verified AI resolution. Holder of the
  defect.
- **Post-agent credential status**: the single job-local `ok` value folding the
  post-agent re-mint and remote-refresh outcomes, produced by the
  `wing-commander-post-agent-credential-status` composite. Three states matter:
  healthy, failed, and absent (the agent step was skipped).
- **Refusal classification**: the decision the publish arm makes about *why* a
  `--force-with-lease` push was refused. Today it is a constant ("the branch
  moved"); this feature makes it a judgement with at least two outcomes.
- **Persisted remote credential**: the credential the pre-agent checkout wrote
  into the git remote, which the publish push rides and which the post-agent
  remote refresh rewrites. Its failure is one of the two inputs to the status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The number of runs in which a rebase publish is refused because
  the post-agent credential failed and the run nevertheless concludes green is
  **zero** — down from all of them today.
- **SC-002**: The number of refusal outcomes the publish arm can distinguish is
  at least **two** (credential-caused, branch race), up from one, and each is
  demonstrated by the check rather than by reading the workflow.
- **SC-003**: A maintainer reading a run in which the credential failed can
  identify the credential as the cause from the run's own output alone, without
  opening the step log of any other step.
- **SC-004**: **100%** of the FR-011 cases are exercised by the check against
  the shipped step and a real refused push, and every regression in FR-009
  fails the check when reintroduced.
- **SC-005**: Runs on the unaffected paths are identical in outcome: a
  successful publish, a clean rebase, a tolerated race and an abandon/escalate
  produce the same comments, labels, branches, step summaries and artifacts as
  before the change.
- **SC-006**: Gate 68 and its self-test pass unchanged, so widening what is
  checked about the publish arm costs nothing that was already checked about
  it.
- **SC-007**: The documented placement of the credential-status step in
  `rebase.yml` matches the shipped placement in **100%** of the contract
  documents that describe it, verified after the change.

## Assumptions

- The post-agent credential status composite does not itself fail the job — it
  warns and publishes an output (spec 052's contract, second maintainer review
  of PR #407). This is what makes moving it above the publish arm safe, and
  FR-005 requires that property to be preserved rather than assumed.
- Gate 68's check 6 matches the credential-status composite by reference — each
  agent step's mint id named by some `mint-outcome` **anywhere** in the job —
  rather than by sequential position, so reordering the status step above the
  publish step does not weaken it. FR-014 requires this to be confirmed by
  running the gate, not taken on trust.
- `rebase.yml` is the only workflow in the repository with a
  `--force-with-lease` push and a refusal-tolerating arm, so the scope of this
  feature is that one step. No parallel site needs the same treatment, and no
  shared home for the classification logic is warranted for a single caller.
- The status step's three states are healthy, failed, and absent, and "absent"
  arises only from the agent step being skipped. Any other cause of an empty
  status would be a separate defect, not something this feature interprets.
- `rebase.yml`'s `rebase` job runs as a matrix over in-flight spec branches;
  each leg is an independent job instance, as spec 073 already assumed.
- The repository gate suite (`run-local-gates.py`) is the acceptance bar for
  every check requirement above, and the next free gate number at the time of
  writing is 125.
- Specs for merged features are historical records (CLAUDE.md), so spec 073's
  own `spec.md` is not edited by this work; the live contract under
  `specs/052-agent-credential-lifetime/contracts/` is, because contracts a gate
  or a call site reads stay live.

## Dependencies

- Spec 073 (`073-rebase-cleanup-credential-refresh`) — the feature that brought
  `rebase.yml` into the post-agent credential sweep and whose FR-003/FR-004 the
  publish arm currently misses.
- Spec 052 (`052-agent-credential-lifetime`) — the remedy, the
  `wing-commander-post-agent-credential-status` composite, the call-site
  convention this feature narrows, and the live contract FR-016 updates.
- Gate 68 (`.github/scripts/verify-post-agent-credential-refresh.py`) — must
  keep passing (FR-014) and is the reason the defect was invisible.
- `lint-workflows.yml` and `.github/scripts/run-local-gates.py` — where the new
  check is registered and where FR-013's local/CI parity is satisfied.
- Issue #661 — the originating board item, filed by the code review of #641.
- Issue #641 — the pull request whose review found this.
