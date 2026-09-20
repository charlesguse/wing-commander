# Feature Specification: The Board Loop — A Scheduled Run Takes One Open Issue From Triage To Proven

**Feature Branch**: `057-autonomous-board-loop`

**Created**: 2026-09-20

**Status**: Draft

**Input**: Lifecycle issue [#408](https://github.com/charlesguse/wing-commander/issues/408) — "board: a scheduled stage that picks up the next open issue and sees it through (triage, route, fix, review, merge, prove)"

## Context

This repository's issue board is worked by a written procedure — CLAUDE.md,
"Working the issue board" (#310) — in a fixed order: triage against current
`main`, route by shape, fix, review, merge, prove. The procedure is real and
it works. It just runs nowhere. Every one of those six steps is performed by
a human in a local agent session, which has three consequences the board
already shows:

- **It leaves nothing a maintainer can read.** The last two fix PRs, #401
  (merged) and #403, carry no review objects on GitHub at all. Their code
  reviews happened, and happened well — in a local session, where they
  produced no artifact anyone can open from the PR. Constitution III says the
  lifecycle is legible from GitHub; a review that exists only in a terminal
  scrollback is not.
- **It is re-derived every session.** The order, the rules, and the evidence
  standards are prose that an agent re-reads and re-interprets each time,
  which is exactly the failure mode Principle IX names: a prompt instruction
  is a request the model can silently fail to follow.
- **It stops when the session stops**, and while it runs it competes with the
  pipeline for one usage window.

Each of the six steps already has machinery in this repository. Nothing joins
them:

| board step | what already exists | what is missing |
|---|---|---|
| triage | the watchdog's collectors read a run's execution-output record — denied tools, rate-limit events, cost, turn count | nothing re-reads an *issue's* cited run against current `main`, or closes the issue on what it read |
| route | the pr-conversation stage's `small-unrelated-change` size backstop and its `new-functionality` spin-off to a `spec-request` issue, which a bot-applied label already hands to intake | the route is only ever taken from a *PR comment*, never from an open issue |
| fix | the pr-conversation stage opens a PR to the default branch; implement pushes to a spec branch | no stage opens a fix PR *from an issue* |
| review | `pr-conversation` folds a *human's* review into `tasks.md` | no agent reviews a fix PR and posts findings on it; out-of-scope findings never become issues |
| merge | `auto-release`'s end-to-end leg merges inside a disposable test repository (spec 055) | Constitution V forbade every bot merge to this repository's `main` until PR #409 |
| prove | `wing-commander-watchdog-test.yml`; `gh workflow run` on a wrapper | nothing re-drives a run after a merge and records the evidence |

**Constitution dependency, already satisfied.** Constitution 2.0.0 (PR #409,
commit `560a6ae`) added Principle X, *Bounded Autonomy — The Pipeline Works
Its Own Board*, and amended V to carve out exactly two bot merge classes. X
is what makes this feature legal, and X is also its hardest constraint: *the
bound is the shape of the change, never the confidence of the model.* Every
durable action this loop takes — a close, a route, a push, a merge — stands
behind deterministic code, not a prompt (IX).

**The feed is three sources**: issues a maintainer files, the watchdog's
`pipeline-defect` findings, and — from spec 056 (#412) — the defects every
stage files as it meets them during its own work. The board loop is the
consumer that gives that feed somewhere to go.

**What this is not.** This is not a second implement loop and it does not
touch the feature lifecycle. Its only exits into that lifecycle are a
`spec-request` issue (which intake already picks up) and a closed issue. The
spec, plan and final PR merges stay human, as V and X both say.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An issue its own evidence already answers is closed without a fix (Priority: P1)

A watchdog filed a `pipeline-defect` three days ago because an implement run
failed. The run's execution-output record shows one turn, zero cost, and an
API 429. Nothing is broken; the run was rate-limited. Today a scheduled run
picks that issue up, reads the record it cites, and closes the issue with the
429 quoted — because code read the record, not because an agent concluded it
had. A second issue, filed against a bug whose fixing commit landed on `main`
yesterday, is closed citing that commit.

**Why this priority**: Triage is the cheapest step and the one that most
often ends the work. An issue closed here costs no fix, no review, and no
merge. It is also the step where the "agent proposes, code decides" split is
sharpest — the evidence is machine-readable, so the close needs no judgment
at all.

**Independent Test**: Point the loop at a fixture issue citing a run whose
execution-output record carries a `rate_limit_event` with
`api_error_status: 429`, one turn and zero cost, and confirm the issue is
closed with that evidence quoted and no branch, PR or commit created. Repeat
with a record that shows a real failure and confirm the issue stays open.

**Acceptance Scenarios**:

1. **Given** an open `pipeline-defect` citing a run whose record shows a
   rate-limit 429, one turn and zero cost, **When** the loop triages it,
   **Then** the issue is closed with the record's own fields quoted and a
   comment naming the run, and nothing else is created.
2. **Given** an open issue whose described defect is already fixed by a
   commit on current `main`, **When** the loop triages it, **Then** the issue
   is closed citing that commit.
3. **Given** an open issue whose cited run shows a genuine failure, **When**
   the loop triages it, **Then** the issue stays open and the loop proceeds
   to route it.
4. **Given** an agent that proposes "close this, it's just a rate limit" for
   a run whose record contains no rate-limit evidence, **When** the close
   gate runs, **Then** nothing is closed and the disagreement is recorded on
   the issue.

---

### User Story 2 - Shape decides the route, and code has the last word (Priority: P1)

An issue asks for a new `verify-*` gate: deterministic, gate-shaped, no
design trade-off. The loop routes it to a fix. Another asks for a change to a
published stage's inputs across three stages. The loop files it as a
`spec-request` and stops — it never writes a line of it. A third looks
fix-shaped to the agent, but the change the fixer actually produced touches
nine files. Code re-checks the finished diff, withdraws the fix, and converts
it to a `spec-request`, exactly as the pr-conversation stage's size backstop
overrides its classify step's own "very small" judgment.

**Why this priority**: The route is the boundary Principle X draws. If the
agent's own classification were the last word, "fix-shaped" would mean
"whatever the model felt confident about", and X says the bound is the shape
of the change, never the confidence of the model.

**Independent Test**: Feed the router a fix-shaped fixture issue, a
spec-shaped fixture issue, and a fixture where the agent proposes
"fix-shaped" for a change that breaches the size-and-path backstop. Confirm
the routes are fix, `spec-request`, and `spec-request` respectively, and that
the third names the breached threshold in its body.

**Acceptance Scenarios**:

1. **Given** an issue the agent proposes as fix-shaped and whose change stays
   inside the backstop, **When** the router runs, **Then** the loop proceeds
   to the fix step.
2. **Given** an issue the agent proposes as spec-shaped, **When** the router
   runs, **Then** a `spec-request` issue exists (or the issue itself carries
   that label), the lifecycle issue is cross-linked to it, and no branch is
   created.
3. **Given** an issue the agent proposes as fix-shaped but whose change
   breaches the backstop, **When** the router runs, **Then** the route
   becomes `spec-request` and the recorded reason names the threshold and the
   measured value — the agent's proposal cannot widen the route, only narrow
   it.
4. **Given** a change that would widen or break the published contract (VII),
   **When** the router runs, **Then** the route is `spec-request` regardless
   of its size.

---

### User Story 3 - A fix-shaped issue becomes a green PR from fresh `main` (Priority: P1)

The loop checks out a freshly fetched `origin/main` — not a checkout that has
been sitting in a session since yesterday, which is how #319 got a
CONFLICTING PR with zero CI checks — cuts a `fix/<issue>-<slug>` branch, makes
the change, and runs the full local gate suite. The suite must be green
before anything is pushed. The PR body cites the issue, and the issue gets a
comment naming the PR.

**Why this priority**: This is the step that produces the change. Without it
the loop is a triage bot.

**Independent Test**: Drive one run against a fixture issue describing a
one-file defect and confirm the branch was cut from the SHA that
`origin/main` had at fetch time, the gate suite ran and was green before the
push, the PR exists citing the issue, and the issue carries the PR link.

**Acceptance Scenarios**:

1. **Given** a fix-shaped issue, **When** the fixer runs, **Then** the branch
   is cut from a `main` fetched in that run and the PR is not CONFLICTING.
2. **Given** a fix whose gate suite fails locally, **When** the push step is
   reached, **Then** nothing is pushed, no PR is opened, and the issue
   records which gate failed.
3. **Given** a fix that was pushed, **When** the run ends, **Then** the PR
   body cites the issue and the issue carries the PR link.

---

### User Story 4 - A review the maintainer can read, on the PR (Priority: P1)

A second agent invocation that shares no context with the fixer reviews the
PR and posts its findings as a PR review on GitHub — the artifact #401 and
#403 never got. In-scope findings are fixed in the same PR and re-reviewed.
Out-of-scope findings become new issues carrying the line
`Found by the code review of #N`, never extra commits that widen the PR. If
the fix→review cycle spends its round budget without reaching zero findings,
the PR stays open for a human and the issue gets a stall notice.

**Why this priority**: Principle X makes the review a gating input to the
merge, not a courtesy. It also fixes the specific legibility gap this feature
was filed over.

**Independent Test**: Drive a fixture PR carrying one in-scope defect and one
out-of-scope defect. Confirm a PR review object exists on GitHub carrying
both findings, the in-scope one is fixed by a later commit on the same PR,
the out-of-scope one exists as its own issue carrying the
`Found by the code review of #N` line, and the PR diff does not contain the
out-of-scope fix.

**Acceptance Scenarios**:

1. **Given** a fix PR, **When** the reviewer runs, **Then** a review object
   exists on the PR in GitHub carrying the findings, and the reviewer's
   invocation carried none of the fixer's context.
2. **Given** a review returning one in-scope finding, **When** the loop
   continues, **Then** a commit on the same PR addresses it and a fresh
   review runs against the new head.
3. **Given** a review returning an out-of-scope finding, **When** the loop
   continues, **Then** a new issue exists carrying
   `Found by the code review of #N`, the PR is not widened, and the finding
   does not block the merge gate.
4. **Given** the round budget is spent with findings still open, **When** the
   loop stops, **Then** the PR is left open and unmerged, the issue carries a
   stall notice naming the remaining findings, and no merge is attempted.

---

### User Story 5 - The merge gate refuses anything it cannot prove (Priority: P1)

Every condition is checked in code against the exact head SHA about to be
merged: checks green on *that* SHA (right after a push the PR's check summary
still shows the previous head's run, so the gate compares `headSha`, never
the summary); zero open findings from the review; the size-and-path backstop
holding on the final diff; the kill switch clear. A head with no checks at
all is not green. Anything that fails leaves the PR open with the reason on
the issue. The merge, when it happens, is a squash commit one human action
reverts.

**Why this priority**: This is the one irreversible-ish action the feature
adds, and the one V had to be amended for. Every other step can be undone by
closing something.

**Independent Test**: Run the gate against a checked-in fixture per refusal
branch — stale check summary over a newer head, a head with no checks at all,
a nonzero open-finding count, a final diff over the backstop, kill switch set
— and confirm each refuses with its own named reason, plus one fixture where
all conditions hold and the gate permits.

**Acceptance Scenarios**:

1. **Given** a PR whose checks are green on an older head and whose current
   head has no completed checks, **When** the gate runs, **Then** it refuses,
   naming the SHA mismatch.
2. **Given** a PR whose head has no checks at all, **When** the gate runs,
   **Then** it refuses — absence of checks is not green (VIII).
3. **Given** a PR with one open review finding, **When** the gate runs,
   **Then** it refuses, naming the finding count.
4. **Given** a final diff that breaches the size-and-path backstop, **When**
   the gate runs, **Then** it refuses and the loop routes the work to a
   `spec-request` instead.
5. **Given** the kill switch set mid-loop, **When** the gate runs, **Then**
   it refuses and the issue records the stand-down.
6. **Given** every condition holding, **When** the gate runs, **Then** the PR
   is squash-merged using the App token and the issue records the merge
   commit.

---

### User Story 6 - Behaviour that only runs in Actions is proven before the issue closes (Priority: P2)

The merged fix changes something that only ever executes inside a GitHub
Actions run. The loop re-drives one run through the wrapper that can dispatch
it, waits for a terminal outcome, and records the run URL and result on the
PR or the issue. Only then does the issue close. If the proof run fails or
cannot be dispatched, the issue stays open carrying the evidence.

**Why this priority**: A merged change to Actions-only behaviour that was
never re-driven is exactly the "green check that means nothing" VIII warns
about. It is P2 rather than P1 because the value of steps 1–5 does not depend
on it: without proof, the issue simply stays open for a human, which is
today's status quo.

**Independent Test**: Merge a fixture fix that declares itself Actions-only,
confirm a dispatched run URL and its outcome appear on the PR or issue and
the issue closes; then repeat with a proof run that fails and confirm the
issue stays open.

**Acceptance Scenarios**:

1. **Given** a merged Actions-only fix, **When** the prove step runs,
   **Then** a run URL and its terminal outcome are recorded and the issue
   closes citing them.
2. **Given** a proof run that ends in failure, **When** the prove step
   finishes, **Then** the issue stays open carrying the failing run URL.
3. **Given** a merged fix that changes nothing that runs only in Actions,
   **When** the prove step runs, **Then** it records why no re-drive was
   needed and the issue closes on the merge evidence alone.

---

### User Story 7 - One item at a time, and one human action stops it (Priority: P1)

Pipeline runs and the maintainers' own sessions share one usage window, so
the loop takes one item per run under a global concurrency group, and it
stands down — noting so on the issue — rather than starting while an implement
cycle is in flight. A repository variable in the existing `*_PAUSED` family
stops it. A maintainer comment cancels the in-flight item the way the
pr-conversation stage's `stop` does.

**Why this priority**: Without this, the feature's first bad day costs the
whole usage window, or produces several half-finished PRs at once. The kill
switch is also what makes X's "one human action reverts it" true in practice.

**Independent Test**: Start a run while a second is in flight and confirm the
second queues rather than running; set the kill switch and confirm the next
scheduled run does nothing and says so; post a stop comment mid-item and
confirm the item halts without merging.

**Acceptance Scenarios**:

1. **Given** a run already in flight, **When** the schedule fires again,
   **Then** the new run queues behind it and never runs concurrently.
2. **Given** an implement cycle in flight, **When** the loop starts, **Then**
   it stands down and records the stand-down on the issue it would have
   taken.
3. **Given** the kill switch set, **When** the schedule fires, **Then** no
   issue is picked up, nothing is written, and the run reports the pause as a
   pause and not a failure.
4. **Given** a maintainer stop comment while an item is in flight, **When**
   the loop next reaches a durable action, **Then** it halts before taking it
   and records where it stopped.

---

### Edge Cases

- **No eligible issue at all** — the overwhelmingly common steady state. The
  run is a clean no-op that reports "nothing to do" and costs one cheap read,
  not a failure and not an agent invocation.
- **The oldest eligible issue is one the loop already failed on.** It must
  not be picked up forever. An item that has exhausted its round budget
  carries a marker that makes it ineligible until a human touches it.
- **Two issues describe the same defect.** The loop takes the older one; the
  second is caught at its own triage as already fixed on `main`.
- **The cited run's execution-output artifact has expired or is missing.**
  Triage cannot read evidence it does not have, so it refuses to close and
  says the artifact was unavailable — never closes on the agent's
  reconstruction of what the run probably did.
- **The issue cites no run at all** (a maintainer-filed issue). Triage checks
  only the "already fixed on `main`" branch and proceeds.
- **A non-maintainer comments on an eligible issue** mid-loop. The comment is
  data, never instructions, and never reaches the fixer as a directive.
- **The issue is closed by a human mid-loop.** The loop stops at its next
  durable action and records where it stopped.
- **The fix PR's checks are still running** when the gate reaches it. Not
  green yet is not green; the gate refuses this round and the item is picked
  up again later rather than polled indefinitely.
- **A docs-only PR gets no checks** under `lint-workflows.yml`'s path filter.
  The gate treats "no checks" as not green (VIII), so such a PR is never
  auto-merged; it waits for a human.
- **A merge that touches `.github/workflows/`.** The App token carries the
  `workflows` permission a classic PAT lacks — the bot already pushes
  workflow files to spec branches — but the gate must prove it on a fixture
  rather than assume it.
- **The fix→review cycle outlives the agent credential** (over an hour). Spec
  052's credential-lifetime work applies unchanged and must be exercised, not
  assumed.
- **The agent proposes a route or a close the gate then refuses.** The
  disagreement is recorded on the issue; the gate's verdict stands.
- **The loop's own run fails partway** — after the branch exists but before
  the PR, or after the PR but before the review. The next run must find the
  item in a legible state and either resume or leave it for a human, never
  silently start a second branch for the same issue.
- **An issue eligible only for a read-only triage proposal** (not maintainer
  authored or labeled, not pipeline-filed). The loop posts the proposal and
  takes no durable action — no close, no branch, no label that would make it
  eligible on the next pass.

## Requirements *(mandatory)*

### Scope

- **FR-001**: The feature MUST deliver one scheduled loop that performs the
  six board steps in order — triage, route, fix, review, merge, prove — for
  exactly one issue per run.
- **FR-002**: The loop MUST be triggerable on a schedule and on demand, and
  MUST be gated by a repository-level kill switch in the existing
  `WING_COMMANDER_*_PAUSED` family.
- **FR-003**: [NEEDS CLARIFICATION: Does this feature ship the autonomous
  merge (Principle X's step 5), or stop at "ready to merge" with a human
  merging and a `pull_request: closed` trigger resuming at prove? Both are
  constitution-legal; (b) is strictly narrower than X permits, (a) is what
  "see it through" means.] Until this is settled, the spec states the full
  loop and marks the merge step's requirements so they can be deferred as one
  block without disturbing steps 1–4 or 6.
- **FR-004**: The feature MUST NOT change the feature lifecycle. Intake,
  clarify, plan, tasks, implement, converge, finalize, cleanup and their
  gates are out of scope; the loop's only exits into that lifecycle are a
  `spec-request` issue and a closed issue.
- **FR-005**: Existing filing routes — the watchdog's `pipeline-defect`, the
  pr-conversation stage's `spec-request` and `permission-request` spin-offs,
  `auto-update:*`, `auto-release:failed`, and spec 056's stage-found
  `found-by:*` filings — MUST be unchanged. This feature consumes them; it
  does not replace them.

### Entry and authorization

- **FR-006**: An issue MUST be eligible for durable action only when a
  maintainer authored it, a maintainer labeled it, or the pipeline itself
  filed it under a label only the pipeline applies — `pipeline-defect` and
  the watchdog's finding classes, `auto-update:*`, `auto-release:failed`, and
  spec 056's `found-by:*`. No label is required of a maintainer-authored
  issue (Constitution X).
- **FR-007**: Any other issue MUST receive at most a read-only triage
  proposal posted as a comment. The loop MUST NOT close it, branch from it,
  label it, or open anything for it.
- **FR-008**: Eligibility MUST be decided in code from the issue's author
  association and labels, never from the issue's text.
- **FR-009**: The loop MUST select the oldest eligible open issue that is not
  excluded by FR-010, so the board drains in filing order rather than by an
  agent's sense of importance.
- **FR-010**: An issue MUST be excluded from selection when it is closed,
  when it carries a disposition marking it settled (such as
  `disposition:false-positive`), or when it carries the exhausted-budget
  marker FR-030 sets. Exclusion MUST be a code-level check on labels and
  state.

### Triage

- **FR-011**: Triage MUST be read-only until its verdict. It MUST read the
  issue, the commits on current `main` since the issue was filed, and the run
  the issue cites, if any.
- **FR-012**: An issue MUST be closed at triage only on evidence the code
  itself read: a rate-limit event in the cited run's execution-output record
  (a `rate_limit_event`, `api_error_status: 429`, one turn, zero cost), an
  upstream action bump, or a commit already on `main` that fixes the
  described defect. The agent MAY propose the verdict; the close MUST be
  gated by code that re-derived the evidence (Principle IX).
- **FR-013**: Every close MUST quote the evidence it acted on — the record's
  own fields, or the commit — in a comment on the issue.
- **FR-014**: When the cited run's record cannot be read (expired artifact,
  missing run, API refusal), triage MUST NOT close the issue, and MUST record
  that the evidence was unavailable.
- **FR-015**: A triage verdict that closes the issue MUST end the run for
  that item; no branch, PR or label beyond the close is created.

### Route by shape

- **FR-016**: The route MUST be one of: fix-shaped (proceed to the fix step)
  or spec-shaped (file a `spec-request` and stop). The agent proposes; a
  deterministic backstop decides.
- **FR-017**: The backstop MUST be able to narrow the agent's proposal —
  fix-shaped to spec-shaped — and MUST NOT be able to widen it. A
  spec-shaped proposal is never overridden into a fix.
- **FR-018**: The backstop MUST be a size-and-path check with thresholds that
  are a checked-in, PR-reviewed constant, applied both before anything is
  pushed and again on the final diff before any merge.
- **FR-019**: A change that would widen or break the published contract (VII)
  MUST route to `spec-request` regardless of its size.
- **FR-020**: When the backstop re-routes a proposal, the recorded reason
  MUST name the threshold and the measured value, as the pr-conversation
  stage's size backstop does.
- **FR-021**: A `spec-request` route MUST leave the work for the feature
  lifecycle: the `spec-request` artifact is created, the originating issue is
  cross-linked to it, and no branch is cut.

### Fix

- **FR-022**: The fixer MUST work from a `main` fetched during that run, and
  MUST record the base SHA it used.
- **FR-023**: The fix MUST live on a branch named for the issue it fixes, so
  a human reading the branch list can tell what each branch is for.
- **FR-024**: The full local gate suite MUST run and be green before anything
  is pushed. A failing suite MUST stop the item with the failing gate named
  on the issue, and MUST NOT push or open a PR.
- **FR-025**: The gate suite the loop runs MUST be the same suite CI runs —
  one invocation, not a re-typed list of gates.
- **FR-026**: The fix PR body MUST cite the originating issue, and the issue
  MUST carry the PR link.
- **FR-027**: The fixer MUST run at the implementation tier with an explicit
  model and a bounded turn budget (Constitution II), honouring the existing
  `model:opus` escalation.

### Review

- **FR-028**: The review MUST be a separate agent invocation that shares no
  context with the fixer — not a continuation of the fixer's session.
- **FR-029**: The reviewer's findings MUST be posted on the PR as a review
  object visible in GitHub (Constitution III). Prose belongs in the review
  body; the findings the merge gate counts MUST also exist as a
  schema-validated structure the gate reads without parsing prose.
- **FR-030**: The fix→review cycle MUST repeat until the review returns zero
  open findings or a bounded number of rounds is spent. On exhaustion the PR
  MUST be left open and unmerged, the issue MUST carry a stall notice naming
  the remaining findings, and the item MUST become ineligible for re-selection
  until a human touches it.
- **FR-031**: In-scope findings MUST be fixed by further commits on the same
  PR and re-reviewed against the new head.
- **FR-032**: Out-of-scope findings MUST become new issues carrying the line
  `Found by the code review of #N`, MUST NOT become commits on the PR, and
  MUST NOT block the merge gate. Each MUST be cross-linked from the
  originating issue.
- **FR-033**: Whether a finding is in scope MUST be recorded per finding in
  the structure FR-029 defines, so the gate's open-finding count is
  computable without reading prose.

### Merge

*(Deferrable as one block — see FR-003.)*

- **FR-034**: The merge MUST be a squash merge performed with the App token,
  producing a single commit on `main` that one human action reverts.
- **FR-035**: The gate MUST refuse the merge unless every one of these holds,
  each checked in code: checks are green on the exact head SHA being merged;
  the gate suite ran on that same SHA; the open-finding count from FR-033 is
  zero; the size-and-path backstop holds on the final diff; the kill switch
  is clear.
- **FR-036**: Green MUST be evaluated against the head SHA, never against the
  PR's check summary, which after a push still reflects the previous head.
- **FR-037**: A head with no checks MUST be treated as not green (Principle
  VIII), including the docs-only case that `lint-workflows.yml`'s path filter
  produces.
- **FR-038**: A refusal MUST leave the PR open and record the named reason on
  the issue. Refusal is a normal outcome, not a run failure.
- **FR-039**: A merge whose diff touches `.github/workflows/` MUST be proven
  to succeed under the App token by a checked-in fixture, not assumed from
  the fact that the App pushes workflow files to spec branches.
- **FR-040**: [NEEDS CLARIFICATION: Does the second merge class Principle X
  permits — the Spec Kit upgrade PR the auto-update stage opened — ship in
  this feature, and does a patch-level jump qualify? X requires "the
  verification that stage assigns to the jump has passed"; a patch jump's
  assigned tier verifies without the end-to-end stage, so whether that counts
  is the owner's call.] If it ships, the size-and-path backstop does not apply
  to it — a vendored upgrade is measured by its verification, not its line
  count — and spec 027's rule that the upgrade stage never merges its own PR
  stands: the loop merges it, the stage does not.

### Prove

- **FR-041**: After a merge, the loop MUST decide whether the fixed behaviour
  runs only inside Actions, and MUST record that decision either way.
- **FR-042**: For Actions-only behaviour, the loop MUST re-drive one run
  through a wrapper that can dispatch it, wait for a terminal outcome, and
  record the run URL and outcome on the PR or the issue.
- **FR-043**: The issue MUST close only after the proof evidence exists. A
  failed or undispatchable proof run MUST leave the issue open carrying that
  evidence.

### Legibility on the issue

- **FR-044**: Every step MUST post what it did on the originating issue
  (Constitution III): the triage verdict and its evidence, the route and its
  reason, the PR, each review round's outcome, the merge or the refusal
  reason, and the proof run.
- **FR-045**: Every artifact the loop creates outside the issue — the fix PR,
  a review-finding issue, a `spec-request` issue — MUST be cross-linked from
  the issue in the way the existing outstanding-task-item mechanism does it,
  rather than a second hand-written link format.
- **FR-046**: A stand-down (kill switch set, implement cycle in flight) MUST
  be recorded rather than silent, so a quiet board is distinguishable from a
  paused one.
- **FR-047**: Every run MUST emit a cost line and a durable metrics record
  through the existing mechanisms, as every other stage does.

### Bounding, concurrency and stopping

- **FR-048**: The loop MUST run under a global concurrency group: one item in
  flight repository-wide, with a second run queuing rather than cancelling or
  racing.
- **FR-049**: The loop MUST decline to start while an implement cycle is in
  flight, and MUST record the stand-down (FR-046).
- **FR-050**: Each item MUST carry a bounded round budget and a per-agent turn
  ceiling with an explicit model (Constitution II).
- **FR-051**: The kill switch MUST stop the loop before any durable action,
  including between rounds of an item already in flight.
- **FR-052**: A maintainer comment MUST be able to stop an in-flight item,
  with the same `stop` semantics the pr-conversation stage already uses, and
  the stop point MUST be recorded.
- **FR-053**: A human closing the issue mid-loop MUST stop the loop at its
  next durable action.
- **FR-054**: An interrupted run MUST leave the item in a state the next run
  can read. The loop MUST NOT open a second branch or a second PR for an
  issue that already has one.

### Untrusted content

- **FR-055**: Issue bodies and comments MUST be framed as data, never as
  instructions, in every agent invocation the loop makes (Constitution V).
- **FR-056**: Content authored by non-maintainers MUST NOT reach the fixer as
  a directive. Which comments are carried into an invocation MUST be decided
  in code from author association, not by asking the agent to ignore the
  rest.
- **FR-057**: No agent invocation in the loop MAY have web tools enabled, and
  each MUST carry the least-privilege tool allowlist its step needs.
- **FR-058**: Nothing the loop writes — code, comment, commit, PR or issue —
  may name a downstream consumer of this repository.

### Reuse — single home

- **FR-059**: Issue filing and dedup MUST reuse the existing durable-failure
  issue mechanism and the watchdog's fingerprint discipline for "the same
  finding again", rather than a second filing implementation.
- **FR-060**: The App token MUST come from the existing context action, and
  spec 052's credential-lifetime handling MUST apply unchanged, since a
  fix→review cycle can exceed the credential's lifetime.
- **FR-061**: The size-and-path backstop, the announce-before-mutate
  ordering, and the cross-link format MUST reuse the existing
  implementations rather than pasted copies. Where a shared idiom is
  consolidated, a gate MUST enforce the single home.

### Published surface and coverage

- **FR-062**: [NEEDS CLARIFICATION: Does the loop ship as a published,
  `workflow_call`-only stage plus a thin wrapper (VII), or as an unnumbered
  repository-only workflow in the `auto-release.yml` shape? The loop encodes
  this repository's own conventions — 429 triage evidence, the
  `Found by the code review of #N` line, this repository's gate-suite entry
  point — which argues for repository-only unless each convention becomes a
  typed input.] The answer decides whether this feature moves the
  adopter-pinned surface at all.
- **FR-063**: If published, the stage MUST read no `vars.*` and no
  `github.event.*`; the kill switch, cadence, entry rule and thresholds
  arrive as declared typed inputs, and the wrapper owns the triggers and the
  security gates. If repository-only, the workflow MUST carry no
  `workflow_call` trigger and MUST state in its own header why it is not a
  published stage.
- **FR-064**: Every gate this feature ships MUST have a checked-in fixture
  for each failure branch (Principle VIII) — at minimum: the triage close
  gate (evidence present, evidence absent, evidence unreadable), the route
  backstop (under threshold, over threshold, contract-widening), and the
  merge gate (stale check summary, no checks, open findings, backstop breach,
  kill switch set, all-clear).
- **FR-065**: Every gate MUST be reachable through the gate registry and MUST
  run the same subject with the same arguments locally as in CI.

### Key Entities

- **Board item**: one open issue the loop has selected, with its eligibility
  basis, the run it cites, its round count, and its current step.
- **Triage verdict**: close or proceed, plus the evidence the code read —
  record fields, commit SHA, or the reason evidence was unavailable.
- **Route decision**: fix-shaped or spec-shaped, the agent's proposal, the
  backstop's verdict, and the measured values behind a re-route.
- **Review finding**: a defect the reviewer found on the fix PR, with an
  in-scope/out-of-scope classification, used by the merge gate as a count and
  by the filing step as issue content.
- **Merge decision**: permit or refuse, the exact head SHA it was evaluated
  against, and the named reason for a refusal.
- **Proof record**: the dispatched run's URL and terminal outcome, or the
  recorded reason no re-drive was required.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A maintainer can read an item's entire history — triage
  evidence, route and reason, PR, each review round, merge or refusal, proof
  run — from the originating issue alone, without opening a terminal.
- **SC-002**: 100% of fix PRs the loop opens carry a review object visible on
  GitHub, closing the gap #401 and #403 demonstrate.
- **SC-003**: No issue is closed, no branch pushed, and no PR merged except
  through a check that a fixture exercises in both its passing and its
  failing direction.
- **SC-004**: Zero merges occur on a head whose checks are absent, stale, or
  failing — verified by a fixture per refusal branch, not by observation of
  production runs.
- **SC-005**: At most one board item is in flight repository-wide at any
  moment, and the loop never starts while an implement cycle is running.
- **SC-006**: Setting the kill switch stops all durable action by the next
  scheduled run, and the pause is visible as a pause rather than as a
  failure.
- **SC-007**: An item that exhausts its round budget leaves exactly one open
  PR and one stall notice — never a second branch or a second PR for the same
  issue on a later run.
- **SC-008**: Out-of-scope review findings appear only as issues carrying
  `Found by the code review of #N`; the fix PR's diff never contains them.
- **SC-009**: A run with no eligible issue completes as a no-op that invokes
  no agent and reports "nothing to do".
- **SC-010**: Every run appears in the durable metrics record with a cost
  line, indistinguishable in form from any other stage's.

## Assumptions

Recorded where the issue left a choice with a defensible default, so that
clarify spends its questions on FR-003, FR-040 and FR-062 rather than these.

- **Cadence**: a schedule interval in the same spirit as `auto-release`'s —
  a one-line, PR-reviewed knob rather than a repository variable — with
  on-demand dispatch alongside it.
- **Round budget**: a small bounded number of fix→review rounds per item
  (the implement ⟲ converge cap is the nearest precedent at 5), with the
  exact number a PR-reviewed constant.
- **Reviewer tier**: the reviewer runs at the same tier as the fixer by
  default, with the existing `model:opus` escalation honoured, rather than
  hard-coding a more expensive second pair of eyes. Constitution II's
  cost-tiering argues for the cheaper default until evidence says otherwise.
- **Findings format**: not optional and not an assumption — X requires the
  merge gate to count open findings in code, so a schema-validated structure
  is required (FR-029) and prose is confined to the review body.
- **Settled dispositions stop the loop**: an issue carrying
  `disposition:false-positive`, or a closed lifecycle, is skipped rather than
  re-triaged (FR-010). This is the safe reading; clarify may narrow it.
- **Closing the issue mid-loop does not close its PR**: the loop stops, the
  PR is left open with a notice, and a human decides its fate. Deleting work
  is the more surprising behaviour of the two.
- **Backstop thresholds are the board's own, not the pr-conversation
  stage's.** That stage's `small-unrelated-change` backstop is ≤3 files and
  ≤40 changed lines, which a new `verify-*.py` gate plus its fixtures would
  exceed on day one. The board's thresholds are a separate PR-reviewed
  constant with the same *shape* and the same "narrow only" property.
- **Stand-down detection**: "an implement cycle is in flight" is read from
  the pipeline's own run state, not inferred from usage metrics.
- **The App token carries the `workflows` permission** the merge needs — the
  bot already pushes workflow files to spec branches — but FR-039 requires
  this to be demonstrated by a fixture rather than relied on.

## Dependencies

- **Constitution 2.0.0, Principle X** (PR #409, commit `560a6ae`) —
  satisfied. Without it, the merge step and the entry rule have no
  authorization.
- **Spec 056 / #412**, stage-found defect filing — one of the loop's three
  feed sources. The loop functions without it on the other two; the feed is
  simply thinner.
- **Existing machinery this feature consumes rather than rebuilds**: the
  durable-failure issue filing and its fingerprint discipline; the
  pr-conversation stage's size backstop, spin-off routes, and
  announce-before-mutate ordering; the context action's App token and spec
  052's credential-lifetime handling; the local gate-suite entry point; the
  metrics summary's cost line and the metrics-persist record.
