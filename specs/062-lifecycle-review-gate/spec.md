# Feature Specification: The Review That Clears the Check — An Automated Code Review Gates the Lifecycle's Merge-Worthy PRs

**Feature Branch**: `spec-draft/062-lifecycle-review-gate`

**Created**: 2026-09-24

**Status**: Draft

**Input**: Lifecycle issue #476 — "Add an automated code-review gate (with
optional auto-merge) for feature-lifecycle PRs"

## Overview

A pipeline pull request reaches a point where everything the pipeline knows
how to check has already passed: the gate suite is green, the branch is
mergeable, convergence says no task is left. Today that is where the
pipeline stops and a human starts — and what the human does next, every
time, is the same thing: read the diff for defects the gates cannot see,
say what is wrong, wait for the fix, read it again, merge.

That loop was run by hand on issue #473 / pull request #475 ("Finalize: The
Loop Recognizes Its Own Work"). Once the pull request looked ready, a code
review ran as several independent finder angles plus a verification pass;
it produced four confirmed defects, which were posted as a
changes-requested review. The existing post-review fold loop (spec 042)
picked the review up, folded the findings into `tasks.md`, and
re-dispatched implement, which fixed all four. A second review pass came
back clean, the local gate suite passed, and the pull request merged.

Nothing in that sequence needed a human's judgment except the last step.
This feature moves the rest of it into the pipeline: **when a lifecycle
pull request already looks ready by the pipeline's existing conditions, an
independent code review runs as one more gate.** Clean, and the gate
clears. Not clean, and the findings go back through the fold loop the
pipeline already owns, implement runs again, and the review comes back for
another round. Only when a setting is explicitly enabled does the pipeline
take the last step itself and merge.

### Why this is not just another workflow job

The merge at the end is the hard part, and it is not a plumbing question.
`.specify/memory/constitution.md` names exactly two classes of pull request
the bot may merge, and says so twice:

- **Principle V (Security — non-negotiable)**: "Humans merge every spec,
  plan and final implementation PR into `main`, and every amendment to this
  constitution; the bot never approves one of those and never merges one.
  The only merges the bot may perform are the two classes Principle X
  defines — the bounded fix-PR merge and the verified dependency-bump merge
  — behind X's deterministic gates and kill switch; a bot merge outside
  those classes violates this principle rather than extending X."
- **Principle X (Bounded Autonomy)**, closing sentence: "What stays human
  is unchanged: the spec, plan and final PR merges of the feature
  lifecycle, every amendment to this document, and every route that reaches
  `spec-request`."

(Lifecycle issue #476 attributes the first passage to Principle X; it is
Principle V's text. Both passages say the same thing, and **both** have to
move for auto-merge to be lawful in this repository.)

So an auto-merge setting is a **third class of bot-mergeable pull request**,
and shipping it is a constitutional amendment with its own Sync Impact
Report entry — not a quiet workflow change. Principle X's existing
fix-PR-merge class is the precedent worth copying rather than inventing
around: green checks re-derived on the exact head SHA being merged, an
independent review (a second agent invocation sharing no context with the
author) with zero open findings, a kill switch in the
`WING_COMMANDER_*_PAUSED` family, and a squash commit on `main` that one
human action reverts.

### What the existing machinery already gives this feature

- **The readiness shape.** The board loop already re-derives "is this pull
  request ready?" against the exact head SHA and reports the unmet
  condition when it is not. The same conditions are what the lifecycle gate
  should wait for before spending a review.
- **The fold loop.** Spec 042 already turns a changes-requested review into
  tasks, dispatches implement, and comes back for re-review when the fold
  converges. This feature must feed that loop, not grow a second one.
- **Structured findings and filing.** The board loop's review already
  emits findings as structured records (title / what / evidence /
  fingerprint basis), posts them on the pull request, and files the
  out-of-scope ones as issues carrying `Found by the code review of #N`
  through the shared durable-filing composite.

### The obstacle the fold path presents today

Two facts, both currently load-bearing, mean the pipeline's own review
cannot simply be dropped into the existing review-event path:

1. The pull-request-conversation wrapper deliberately ignores reviews whose
   author is a bot (`github.event.review.user.type != 'Bot'`), and just as
   deliberately has no `workflow_dispatch` entry point. A review the
   pipeline posts under its own App identity is invisible to the fold loop.
2. GitHub rejects `APPROVE` and `REQUEST_CHANGES` from the pull request's
   own author identity — the board loop records exactly this and posts
   `COMMENT` reviews instead. Lifecycle pull requests are opened by the
   same bot identity that would post the review, so the pipeline's review
   of them can only ever be a `COMMENT`, while the fold path keys on
   `CHANGES_REQUESTED`.

Neither is a bug to route around silently: the bot exclusion is a Principle
V security gate, and widening it generally would let any bot's review drive
the pipeline. How the pipeline's own review re-enters the fold loop without
widening that gate is the third open question below.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A clean review clears the check (Priority: P1)

A lifecycle pull request has reached the point where every existing
condition says ready. The pipeline runs an independent code review against
that exact head SHA, finds nothing, posts a review saying so, and the
review gate reports a pass on the pull request. The maintainer opens the
pull request and sees one more green check whose meaning is "a second agent
read this diff and found nothing", and merges.

**Why this priority**: This is the whole value of the feature for the
default configuration. It delivers a real, mergeable signal without
touching who merges, so it ships ahead of anything that changes merge
authority.

**Independent Test**: Drive a lifecycle pull request whose diff is known
clean to the ready point and confirm a single review run posts its result
on the pull request, records it on the lifecycle issue, and leaves a
passing status on the head SHA — with no change to who merges.

**Acceptance Scenarios**:

1. **Given** a lifecycle pull request whose other checks are green on head
   SHA `abc123` and whose branch is mergeable, **When** the review gate
   runs, **Then** exactly one review is posted on the pull request naming
   `abc123`, the gate reports a pass on `abc123`, and the outcome is stated
   on the lifecycle issue.
2. **Given** the gate already passed on head SHA `abc123`, **When** nothing
   new is pushed, **Then** no second review runs and no second cost is
   incurred.
3. **Given** the gate passed on `abc123`, **When** a new commit moves the
   head to `def456`, **Then** the earlier pass does not carry over and the
   gate re-runs against `def456`.
4. **Given** a lifecycle pull request whose other checks are not yet green,
   **When** the pipeline evaluates it, **Then** no review runs and the
   unmet condition is stated rather than a pass reported.

---

### User Story 2 - Findings come back as work, not as a dead end (Priority: P1)

The review finds real defects. They are posted on the pull request where a
maintainer can read them, the in-scope ones become tasks through the fold
loop the pipeline already owns, implement runs again and fixes them, and
the review comes back for another round against the new head. Out-of-scope
defects become their own issues instead of widening the pull request.

**Why this priority**: A gate that can only say "no" and stop is worth less
than the human loop it replaces. The fold-back is what made the hand-run
loop on #475 finish without a human between rounds.

**Independent Test**: Drive a lifecycle pull request with a seeded, review-
findable defect and confirm the finding reaches `tasks.md`, implement is
re-dispatched, and a second review round runs against the fixed head —
without a human acting in between.

**Acceptance Scenarios**:

1. **Given** a review round that produced two in-scope findings, **When**
   the round completes, **Then** both findings appear on the pull request
   and both become tasks through the existing fold mechanism, and the gate
   does not report a pass.
2. **Given** an out-of-scope finding, **When** the round completes,
   **Then** an issue is filed carrying the line `Found by the code review
   of #N`, that issue is not held against this pull request's readiness,
   and no commit for it is added to the pull request.
3. **Given** the folded work converged and implement pushed a new head,
   **When** the pull request returns to the ready point, **Then** a new
   review round runs against the new head SHA.
4. **Given** review rounds have reached the round budget without
   converging, **When** the budget is exhausted, **Then** the pipeline
   stops, reports the reason and the open findings on the lifecycle issue,
   and hands the pull request to a human rather than looping further.
5. **Given** a finding the review produced, **When** it is recorded,
   **Then** the same finding is not filed or folded twice across rounds.

---

### User Story 3 - The review never runs mid-implementation (Priority: P1)

An implement stage is running its cycles, or one cycle has just ended and
the next is about to be dispatched. No review runs, no cost is spent, and
no findings are posted about work that is still in motion.

**Why this priority**: This is an explicit exclusion in the request, and it
is a cost and noise control, not a nicety — a review per cycle would
multiply the pipeline's spend against a diff nobody has claimed is
finished.

**Independent Test**: Drive a full implement ⟲ converge loop of several
cycles and confirm the count of review invocations attributable to those
cycles is zero.

**Acceptance Scenarios**:

1. **Given** an implement cycle in flight on a spec branch, **When** the
   cycle pushes commits, **Then** no review gate run is triggered.
2. **Given** a cycle has just completed and convergence is deciding whether
   to dispatch another, **When** the decision is made either way, **Then**
   no review gate run is triggered by that boundary.
3. **Given** the implement ⟲ converge loop has finished and a lifecycle
   pull request has reached the ready point, **When** the gate evaluates it,
   **Then** the review runs — this is the first invocation for that spec's
   implementation.

---

### User Story 4 - Auto-merge, only when explicitly switched on (Priority: P2)

A maintainer turns the auto-merge setting on. From then on, a lifecycle
pull request whose review came back clean — with every other condition
re-derived green against the exact head SHA and the kill switch clear — is
squash-merged by the pipeline, and the merge is announced on the lifecycle
issue with the evidence that authorized it. With the setting off, which is
how the repository runs until a maintainer changes it, the pipeline never
merges and the human path is exactly what it is today.

**Why this priority**: It is the payoff the request names, but it depends
on User Story 1 being trustworthy and on a constitutional amendment. It
ships after the gate has proven itself, never as part of the same first
green check.

**Independent Test**: With the setting off, confirm a clean, ready pull
request is never merged by the pipeline. With it on, confirm the same pull
request is squash-merged and that the announcement names the head SHA, the
review round, and the conditions checked.

**Acceptance Scenarios**:

1. **Given** the auto-merge setting is off, **When** a lifecycle pull
   request's review comes back clean, **Then** the gate reports a pass and
   the pull request remains open for a human to merge.
2. **Given** the setting is on and every condition holds on head SHA
   `abc123`, **When** the pipeline merges, **Then** it is a squash merge of
   `abc123`, the merge is announced on the lifecycle issue with the
   conditions and the review round quoted, and one human action reverts it.
3. **Given** the setting is on but the head SHA moved between the review
   and the merge attempt, **When** the pipeline re-derives the conditions,
   **Then** it does not merge, and states which condition failed.
4. **Given** the setting is on and a human has an unresolved
   changes-requested review on the pull request, **When** the pipeline
   evaluates the merge, **Then** it does not merge.
5. **Given** the setting is on and the kill switch is set, **When** the
   pipeline evaluates the merge, **Then** it does not merge and says the
   kill switch stopped it.
6. **Given** the setting is on and the merge is refused because the
   pipeline's token lacks the scope a workflow-touching pull request
   requires, **When** the refusal is seen, **Then** the pull request is
   handed to a maintainer with that reason stated, and no alternative route
   to `main` is attempted.

---

### User Story 5 - The constitution says what the pipeline does (Priority: P2)

Before the pipeline merges its first lifecycle pull request, the
constitution names the class of merge it is performing, under the same
deterministic-gate discipline the fix-PR class already carries, and the
amendment is recorded in the Sync Impact Report history at the top of the
document. A reader of the constitution and a reader of the workflow see the
same rule.

**Why this priority**: Principle V is non-negotiable, and the amendment is
itself a human-merged change. Shipping auto-merge ahead of it is a
violation, not a sequencing detail.

**Independent Test**: Confirm that with auto-merge capability present but
the constitution unamended, a check fails; and that the amendment carries a
Sync Impact Report entry.

**Acceptance Scenarios**:

1. **Given** the auto-merge capability exists in the repository, **When**
   the constitution does not name the lifecycle-PR merge class, **Then** a
   check fails and says so.
2. **Given** the amendment lands, **When** the constitution is read,
   **Then** Principle V's enumeration of bot-mergeable classes, Principle
   X's "what stays human" sentence, and the Sync Impact Report history all
   reflect the new class.
3. **Given** the amendment pull request itself, **When** it is merged,
   **Then** a human merged it.

---

### User Story 6 - A maintainer can see and stop it (Priority: P3)

Every review round and every merge decision is legible from the lifecycle
issue and the pull request alone, and a maintainer can stop the whole
behaviour with a repository setting without editing a workflow.

**Why this priority**: Observability and the stop control are what make the
first two stories safe to leave running; they are separable from them.

**Independent Test**: Set the kill switch and confirm that no review runs
and no merge occurs, with the stand-down recorded; unset it and confirm
normal operation resumes.

**Acceptance Scenarios**:

1. **Given** the kill switch is set, **When** a lifecycle pull request
   reaches the ready point, **Then** no review runs and the stand-down is
   recorded.
2. **Given** a completed review round, **When** a maintainer reads the
   lifecycle issue, **Then** the round number, head SHA, finding count and
   outcome are stated there.
3. **Given** a completed review round, **When** its cost is reported,
   **Then** it appears through the pipeline's existing per-run cost line
   rather than a second formatter.

---

### Edge Cases

- **The review round budget is exhausted.** The pipeline stops, states the
  open findings and the reason on the lifecycle issue, and leaves the pull
  request to a human (US2 scenario 4). It does not report a pass it did not
  earn.
- **A human reviews concurrently with a round.** A human's
  changes-requested review must not be lost by a pipeline round completing
  after it, and must block auto-merge until resolved.
- **The head SHA moves mid-round.** The round's result belongs to the SHA
  it reviewed; it neither passes nor merges a different SHA.
- **The pull request is closed, or its lifecycle issue is closed, during a
  round.** The round stops without posting findings onto a dead pull
  request.
- **The review agent fails, times out, or is rate-limited.** No pass is
  reported; the failure is distinguishable from "clean" on both the pull
  request and the lifecycle issue, and a rate-limited round is retryable
  rather than counted as a converged one.
- **The review returns findings on files the pull request did not touch.**
  These are out-of-scope by definition and become issues, never commits.
- **Two lifecycle pull requests reach the ready point at once.** Rounds
  serialize the way the rest of the pipeline serializes, so concurrent
  specs do not contend for the usage window.
- **Auto-merge is switched on while a pull request is already past its
  clean round.** The conditions are re-derived before merging; a stale
  clean round does not authorize a merge.
- **The pull request is a spec or plan pull request with no implementation
  branch behind it.** If such pull requests are in scope (open question 1),
  a not-clean outcome has no implement stage to dispatch — the findings
  must still reach a human, and the gate must not report a pass.

## Requirements *(mandatory)*

### Functional Requirements — trigger and scope

- **FR-001**: The pipeline MUST run a code review as an additional gate on
  a lifecycle pull request only after the conditions it already uses to
  call a pull request ready are satisfied, re-derived against the pull
  request's exact head SHA.
- **FR-002**: The pull request types in scope MUST be
  [NEEDS CLARIFICATION: the request explicitly includes the final
  implementation pull request ("specs being merged in"); it is not stated
  whether the spec pull request (`spec-draft/…` → `main`) and the plan
  pull request are also in scope. The answer changes which stages open
  pull requests the gate attaches to, and whether a not-clean outcome has
  an implement stage to dispatch at all].
- **FR-003**: The gate MUST NOT run during an implement stage's cycles, and
  MUST NOT run between cycles — no cycle start, cycle completion, or
  convergence decision may trigger a review.
- **FR-004**: The gate MUST record the head SHA a completed round reviewed,
  and MUST NOT re-review a head SHA a round already covered.
- **FR-005**: A pass MUST NOT carry over to a head SHA it was not derived
  on; any new head returns the gate to "not yet reviewed".
- **FR-006**: The gate MUST NOT run while the kill switch (FR-034) is set,
  and MUST record the stand-down when it declines for that reason.

### Functional Requirements — the review itself

- **FR-007**: The review MUST be performed by Claude Code's `code-review`
  capability rather than a bespoke, gate-specific prompt, so that
  improvements to the reviewer are inherited rather than reimplemented.
- **FR-008**: The review MUST be independent of the agent that produced the
  diff — a separate invocation sharing no context with the implementing or
  finalizing stage — matching the independence Principle X already requires
  of the fix-PR class.
- **FR-009**: The review invocation MUST declare an explicit model and a
  bounded turn budget (constitution II).
- **FR-010**: Findings MUST be emitted as structured records carrying at
  least a title, what is wrong, evidence (file paths, optionally quoted
  lines), an in-scope/out-of-scope determination, and a stable fingerprint
  basis — the same shape the pipeline's existing review findings already
  use, so filing and deduplication are reused rather than re-derived.
- **FR-011**: Pull request titles, bodies, diffs and comments MUST be
  framed to the reviewing agent as untrusted data, never as instructions
  (constitution V).
- **FR-012**: The first cut MUST run the review with no repository-authored
  additional review context. Supplying such context is a named, deferred
  follow-up (see Out of Scope); the review invocation MUST live in a single
  home so that a later feature adds it in one place rather than per call
  site.

### Functional Requirements — the clean outcome

- **FR-013**: When a round produces zero open in-scope findings, the gate
  MUST report a passing status on the reviewed head SHA, suitable for use
  as a required check.
- **FR-014**: The gate MUST report a non-passing status — distinguishable
  from "not yet run" — whenever findings are open, the round budget is
  exhausted, or the review itself failed. A gate that cannot reach its
  subject MUST fail loudly rather than report a pass (constitution VIII).
- **FR-015**: The round's outcome MUST be stated on the lifecycle issue,
  naming the round number, the head SHA, the finding count and the result
  (constitution III).

### Functional Requirements — the not-clean outcome

- **FR-016**: In-scope findings MUST be folded into the pipeline's existing
  post-review fold mechanism (spec 042) so they become tasks and
  re-dispatch implement. The feature MUST NOT introduce a second, parallel
  findings-to-tasks mechanism.
- **FR-017**: The mechanism by which the pipeline's own review reaches that
  fold path MUST be
  [NEEDS CLARIFICATION: the fold path is entered by a non-bot maintainer's
  `CHANGES_REQUESTED` review; the pipeline's review is authored by the same
  bot identity that opened the pull request, so it is excluded by the
  wrapper's bot filter and can only be a `COMMENT` review. Options: teach
  the fold path to accept the pipeline's own review identified by a
  pipeline-owned marker; have the gate invoke the fold logic directly
  rather than through the review event; or give the gate its own outcome
  shape that feeds the same task-generation step].
- **FR-018**: Whatever FR-017 resolves to MUST NOT widen the existing
  security gate to bot-authored reviews generally — only the pipeline's own
  review, identified deterministically, may drive the fold.
- **FR-019**: Out-of-scope findings MUST be filed as issues carrying the
  line `Found by the code review of #N`, through the pipeline's existing
  durable filing path, and MUST NOT become extra commits that widen the
  pull request (constitution X).
- **FR-020**: An out-of-scope finding MUST NOT be held against the
  reviewed pull request's readiness or its gate status.
- **FR-021**: A finding MUST NOT be folded or filed twice across rounds;
  deduplication MUST be deterministic code, not the reviewing agent's
  judgment (constitution IX).
- **FR-022**: Review rounds MUST be bounded by a round budget. On
  exhaustion the pipeline MUST stop, state the reason and the open findings
  on the lifecycle issue, and leave the pull request to a human.
- **FR-023**: A human's changes-requested review MUST continue to be
  honoured while pipeline rounds are running, and MUST NOT be discarded or
  overwritten by a round that completes after it.

### Functional Requirements — auto-merge

- **FR-024**: The pipeline MUST NOT merge a lifecycle pull request unless
  an explicit repository setting enabling it is present. The setting's
  default and granularity MUST be
  [NEEDS CLARIFICATION: off by default and repository-wide, off by default
  with a per-pull-request-type switch, or on by default. This decides
  whether adopting a release silently changes who merges, and whether a
  maintainer can enable it for the final pull request while keeping spec
  pull requests human-merged].
- **FR-025**: When the setting is off, the gate MUST still run and report
  its status; only the merge is withheld, and the human merge path is
  unchanged.
- **FR-026**: Before merging, the pipeline MUST re-derive, in deterministic
  code, against the exact head SHA it is about to merge: every other
  required check green (a head with no checks is not green), the gate suite
  having run on that SHA, the review round clean with zero open in-scope
  findings, no unresolved human changes-requested review, the pull request
  mergeable, and the kill switch clear.
- **FR-027**: If any condition fails, the pipeline MUST NOT merge and MUST
  state which condition failed.
- **FR-028**: An authorized merge MUST be a squash merge that one human
  action reverts.
- **FR-029**: Every automated merge MUST be announced on the lifecycle
  issue with the head SHA, the review round, and the conditions that
  authorized it.
- **FR-030**: When the merge is refused because the pipeline's credential
  lacks the scope a workflow-touching pull request requires, the pipeline
  MUST hand the merge to a maintainer with that reason stated, and MUST NOT
  attempt any other route to `main`.

### Functional Requirements — constitutional authority

- **FR-031**: The auto-merge capability MUST NOT ship before the
  constitution authorizes it. The amendment MUST update both passages that
  enumerate merge authority — Principle V's "the only merges the bot may
  perform are the two classes…" and Principle X's closing "what stays
  human is unchanged…" — to name the lifecycle pull request merge as a
  third class.
- **FR-032**: The amendment MUST carry a Sync Impact Report entry in the
  stacked history at the top of `.specify/memory/constitution.md`, and MUST
  state the class's deterministic gates and kill switch in the same terms
  the fix-PR class uses.
- **FR-033**: The amendment pull request MUST be merged by a human
  (constitution V); the pipeline MUST NOT merge its own constitutional
  amendment, and the new class MUST NOT be read as authorizing that.

### Functional Requirements — controls, plumbing and observability

- **FR-034**: The feature MUST carry a repository-level kill switch in the
  `WING_COMMANDER_*_PAUSED` family that stops both the review and the
  merge, settable without editing a workflow.
- **FR-035**: Logic shared with, or duplicated across, more than one call
  site — the readiness re-derivation, the merge preconditions, the finding
  fold, the cost line — MUST live in one home (a composite action or an
  existing shared script) with call sites consuming its outputs, never a
  pasted block.
- **FR-036**: The per-run cost of a review round MUST be reported through
  the pipeline's existing cost-line single home, not a second formatter.
- **FR-037**: The gate MUST be reachable through the repository's gate
  registry and MUST run the same subject with the same arguments locally as
  in CI; every failure branch it ships MUST be exercised by a checked-in
  fixture (constitution VIII).
- **FR-038**: A deterministic check MUST fail if the auto-merge capability
  is present in the repository while the constitution does not name the
  class it performs (the pairing US5 scenario 1 describes).
- **FR-039**: Trigger ownership MUST follow the published-contract split:
  the stage logic reads only declared inputs, and the wrapper owns the
  trigger, the repository variables and the security gate (constitution
  VII).

### Key Entities

- **Lifecycle pull request**: A pull request the feature lifecycle opens on
  the way to `main` — at minimum the final implementation pull request; the
  spec and plan pull requests pending FR-002.
- **Review round**: One invocation of the review against one head SHA,
  carrying a round number, the SHA, its findings and an outcome
  (clean / findings / failed / budget-exhausted).
- **Finding**: A structured defect record — title, what, evidence, in-scope
  determination, fingerprint basis — that becomes either a task (in-scope)
  or an issue (out-of-scope).
- **Round budget**: The bound on how many review-fold-implement rounds one
  pull request may take before the pipeline stops and hands over.
- **Auto-merge setting**: The explicit repository-level switch that
  authorizes the pipeline to merge; distinct from the kill switch, which
  stops the whole feature.
- **Kill switch**: The `WING_COMMANDER_*_PAUSED`-family repository variable
  that halts review and merge alike.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a lifecycle pull request with a clean diff, the interval
  between "every existing condition reports ready" and "a merge-worthy
  signal is available to the maintainer" requires zero human actions.
- **SC-002**: Across a complete implement ⟲ converge loop of any number of
  cycles, the number of review invocations attributable to those cycles or
  to the boundaries between them is zero.
- **SC-003**: 100% of findings a round produces end up either as a task in
  the spec's `tasks.md` (in-scope) or as an issue carrying `Found by the
  code review of #N` (out-of-scope); none are dropped, and none appear
  twice across rounds.
- **SC-004**: A review-findings-fold-implement-re-review sequence completes
  on at least one real lifecycle pull request with no human action between
  the first round and the final clean round, and terminates within the
  round budget.
- **SC-005**: With the auto-merge setting in its shipped default state, the
  number of lifecycle pull requests merged by the pipeline is zero until a
  maintainer changes the setting.
- **SC-006**: Every pipeline-performed merge is reverted by exactly one
  human action, and is traceable from the lifecycle issue to the head SHA
  and the review round that authorized it.
- **SC-007**: A deliberately introduced disagreement between the
  constitution's enumerated merge classes and the repository's auto-merge
  capability is caught by a failing check, not by a reader.
- **SC-008**: Every failure branch of the gate — review failed, rate
  limited, budget exhausted, condition unmet — is distinguishable from
  "clean" on both the pull request status and the lifecycle issue, and each
  is exercised by a checked-in fixture.
- **SC-009**: The pipeline's total spend per lifecycle pull request grows
  by at most one review round per distinct reviewed head SHA — never more
  than one round per SHA.

## Assumptions

- The auto-merge setting ships **off**, so that adopting a release never
  silently changes who merges; FR-024's clarification may confirm or
  override this, and nothing else in the spec depends on the default.
- The review gate is additive: with it absent, disabled or paused, the
  lifecycle behaves exactly as it does today, and a maintainer can always
  merge by hand.
- "Looks ready by the pipeline's existing checks" means the conditions the
  pipeline already re-derives for a pull request against its exact head
  SHA, not a new definition of readiness invented for this gate.
- The reviewing identity is the pipeline's existing bot App identity; no
  new credential class is introduced, and the constraint that this identity
  cannot post `APPROVE`/`REQUEST_CHANGES` on its own pull requests holds.
- Rounds serialize under the pipeline's existing per-spec concurrency
  discipline; this feature adds no new concurrency model.
- The round budget has a conservative default (single digits) and is
  configurable the way the pipeline's other loop caps are.
- The final implementation pull request is in scope regardless of how
  FR-002 resolves — it is the case the request names explicitly.
- Findings the review produces are proposals; whether one is well-formed,
  novel, or safe to act on is decided by deterministic code, not by the
  reviewing agent (constitution IX).

## Dependencies

- `.specify/memory/constitution.md` — Principles V and X both constrain
  this feature and both must be amended before auto-merge ships (FR-031,
  FR-032).
- `specs/042-post-review-fold-loop` — the findings-to-tasks fold and the
  return-for-re-review path this feature must feed rather than duplicate
  (FR-016).
- The pull-request-conversation stage and its wrapper — the bot-author
  exclusion and the absence of a dispatch entry point are what FR-017 must
  resolve around without widening (FR-018).
- The board loop's review and readiness machinery — the precedent for
  structured findings, out-of-scope filing, exact-head-SHA condition
  re-derivation, and the kill switch this feature copies (FR-010, FR-019,
  FR-026, FR-034).
- The finalize stage — the owner of the final pull request, its
  `stage:review` flip and its re-review request; the gate attaches after
  it, and the re-review path is shared.
- The shared cost-line and durable-filing composite actions — the single
  homes FR-035 and FR-036 require call sites to consume.
- Claude Code's `code-review` capability — the reviewer itself (FR-007);
  its availability and invocation surface in Actions is a planning-stage
  input.

## Out of Scope

- **Repository-authored additional review context** (extra instructions,
  house rules, or a review checklist handed to the reviewer). The request
  names it as wanted but separable; it is deferred to a named follow-up,
  and FR-012 only requires this feature not to make it harder to add.
- Reviewing pull requests outside the feature lifecycle — fix pull
  requests already have the board loop's own review; nothing here changes
  it.
- Replacing or re-tuning the board loop's existing review.
- Changing what the gate suite itself checks, or adding new correctness
  gates to it.
- Auto-merging the constitutional amendment, or any change to who merges an
  amendment (FR-033).
- Reviewing fork-authored pull requests; the pipeline only checks out
  trusted refs.
