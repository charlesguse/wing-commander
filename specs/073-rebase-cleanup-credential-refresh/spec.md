# Feature Specification: The Last Two Agent Stages Join the Credential Sweep — rebase.yml and cleanup.yml

**Feature Branch**: `spec-draft/073-rebase-cleanup-credential-refresh`

**Created**: 2026-09-25

**Status**: Draft

**Input**: Lifecycle issue #558 — "rebase.yml and cleanup.yml agents read the
pre-agent bot token after an unbounded run" (routed from board-loop.yml,
originating issue #411; found by the code review of #407)

## Overview

The App installation token this pipeline mints for the bot lives about **one
hour**. Spec 052 (`agent-credential-lifetime`, PR #407, fixing #345)
established the remedy for that: a job that runs an agent step re-establishes
the credential immediately after the agent step finishes, re-authenticates any
git remote the pre-agent checkout persisted, and folds the result into one
status every later step can read — so a step acting as the bot after a long
agent run never holds a credential minted before it.

Spec 052 applied that remedy to the **eight stages its FR-007 names**: intake,
clarify, plan, tasks, implement, finalize, pr-conversation, and the
auto-update workflow's end-to-end arm. Two workflows that also run an agent
step and also act as the bot afterwards were not in that list and did not get
the remedy:

- **`rebase.yml`**, job `rebase`
- **`cleanup.yml`**, job `teardown-done`

Both therefore carry the exact defect #345 described, and Gate 68
(`verify-post-agent-credential-refresh.py`) cannot see them, because its
`SUBJECTS` map is the same eight-file list.

### The exposure, on current main

`rebase.yml`, job `rebase`:

- The bot credential is minted at the `Wing Commander context` step
  (`rebase.yml:565`).
- A checkout at `rebase.yml:590` persists that credential into the git remote.
- The agent step (`Resolve conflicts`) is at `rebase.yml:693`, with no
  `timeout-minutes` on the step or the job — so the workflow default of 360
  minutes applies, six times the credential's lifetime.
- After it, steps act as the bot with the **pre-agent** mint:
  `Report over-budget agent run` (`:833`), `Publish rebased branch` (`:951` —
  and its `git push --force-with-lease` at `:955` also rides the persisted
  remote), `Abandon and escalate` (`:993`), and
  `Announce the rebase escalation on the lifecycle issue` (`:1056`).

`cleanup.yml`, job `teardown-done`:

- Mint at `cleanup.yml:509`; checkouts persisting it at `:567` and `:662`.
- The agent step (`Completion summary`) is at `cleanup.yml:691`, again with no
  `timeout-minutes` on the step or the job.
- After it: `Report over-budget agent run` (`:826`), `Close lifecycle issue
  and flip label` (`:863`), `Delete pipeline branches` (`:890` — `git push
  origin --delete` through the persisted remote), and
  `Report incomplete teardown on the lifecycle issue` (`:941`).

When the agent outruns the token, every one of those steps fails with a bare
`401`, and nothing anywhere names the expired credential as the reason. In
`cleanup.yml` the consequence is a lifecycle issue left open and pipeline
branches left undeleted; in `rebase.yml` it is a rebased result that is never
published and an escalation that is never announced.

### What the measurements say

The owner measured both agent jobs on 2026-09-21, over the last 40 runs of
each (`gh run view --json jobs`), and recorded the result on issue #411:

| workflow | agent job | longest observed | typical |
|---|---|---|---|
| `rebase.yml` | `rebase / rebase (<spec>)` | 25 min — spec 052's legs ran 25, 22, 21 and 11 min, **all cancelled by the concurrency race, so the true ceiling is higher** | 2 min on a clean rebase |
| `cleanup.yml` | `teardown-done` | 1 min | 1 min |

Nothing has crossed the hour yet. But a conflict-heavy rebase scales with the
number of conflicting files, so `rebase.yml`'s margin is not a property of the
stage — it is luck that has not run out. `cleanup.yml`'s agent is a read-only
summary whose turn budget already bounds it to about a minute.

### Why this is a specification and not a fix PR

The two workflows do not obviously want the same treatment, and choosing was a
trade-off, not a lookup:

- Full mechanism everywhere is uniform and needs no exemption, but puts three
  composite steps and a failure-naming arm into a job whose agent has never
  run longer than a minute.
- Bounding `cleanup.yml` with a wall-clock limit is cheaper and matches the
  precedent spec 052 already set for `auto-update-spec-kit.yml`'s
  `evaluate-path` and `comment-reply` jobs (excluded because each agent step
  carries `timeout-minutes: 10`), but it introduces a second, weaker kind of
  coverage that a future edit can silently remove.

**Decided** (clarification answered on #558, 2026-09-25): `rebase.yml` gets the
full post-agent mechanism; `cleanup.yml` gets the **wall-clock bound plus a
recorded, assertable exemption**, following spec 052's `timeout-minutes: 10`
precedent, because its agent has taken about a minute on every one of the 40
measured runs. The weaker-coverage objection is answered by FR-006: the bound
is not prose, it is a condition a gate asserts, so removing or raising it fails
the suite.

The related question — how Gate 68 decides *which* workflows it is
responsible for — has the same shape, and was tracked as item 1 of #410
("derive the subject list"). Two other workflows already bear on it:
`board-loop.yml` (spec 057) adopted the post-agent composites voluntarily
(`board-loop.yml:901, :1228, :1720, :1727, :2217, :2732, :2739`) and is still
not a Gate 68 subject, and `watchdog.yml`'s agent step carries
`timeout-minutes: 10` (`watchdog.yml:2286`) but is recorded nowhere as an
exemption.

**Decided** (same answer): Gate 68's subjects are **derived from the workflows**
rather than hand-listed, which resolves #410 item 1 inside this feature and
brings `board-loop.yml` and `watchdog.yml` into scope — each recorded as an
exemption whose condition the gate asserts, not as prose. The owner asked that
this stay consistent with the derivation-plus-floor answer given on #549, so the
derivation here must not contradict that decision; where the two touch the same
mechanism, #549's shape wins.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A long rebase still publishes its result (Priority: P1)

A spec branch has drifted badly and the rebase agent spends over an hour
resolving conflicts across many files. When it finishes, the maintainer
expects the rebased branch to be published and the lifecycle issue updated —
or, if that is impossible, to be told exactly why.

**Why this priority**: This is the stage with the measured exposure. The agent
has already spent 25 minutes and been cut off mid-flight; a conflict-heavy
rebase has no ceiling short of the workflow default of 360 minutes. It is also
the stage whose failure is most expensive — the work the agent just did is
thrown away unpublished, and the escalation that would tell a human is the
step that fails too.

**Independent Test**: Drive `rebase.yml` on a branch needing a real rebase and
confirm the publish and escalate arms act on a credential established after
the agent step finished, not the one minted before it; confirm a failed
re-establishment surfaces as a named credential failure rather than a `401` on
a later step.

**Acceptance Scenarios**:

1. **Given** a `rebase` job whose agent step ran longer than the credential's
   lifetime, **When** the publish arm runs, **Then** it pushes with a
   credential established after the agent step, and the push succeeds.
2. **Given** the same job, **When** the abandon/escalate arm runs instead,
   **Then** it comments on the lifecycle issue with a post-agent credential.
3. **Given** a `rebase` job whose post-agent re-establishment itself fails,
   **When** the job ends, **Then** the run names the credential as the cause
   in its own reporting, rather than leaving a later step to fail with an
   unexplained authentication error.
4. **Given** a clean rebase that needs no agent work at all, **When** the job
   runs, **Then** its outcome, its artifacts and its comments are unchanged
   from today.

---

### User Story 2 - Teardown finishes even behind a slow summary agent (Priority: P1)

A spec has merged and `cleanup.yml` runs its completion-summary agent. Whatever
that agent does, the maintainer expects the lifecycle issue to be closed, the
label flipped, and the pipeline branches deleted — or an incomplete-teardown
notice that says why.

**Why this priority**: A silent half-teardown is worse than a loud failure: the
lifecycle issue stays open and the branches stay behind, and the next run's
idempotency checks then see a state nobody intended. The measured risk is low
(one minute, every time), which is why the remedy chosen here is the wall-clock
bound rather than a copy of User Story 1's mechanism.

**Independent Test**: Drive `cleanup.yml` to the `teardown-done` outcome and
confirm the agent's run is bounded below the credential's lifetime by a limit a
deterministic check asserts is present; then delete or raise that limit and
confirm the check fails naming the job.

**Acceptance Scenarios**:

1. **Given** a `teardown-done` job, **When** the close/label/delete steps run,
   **Then** the agent step could not have run past the credential's lifetime,
   because an enforced wall-clock bound would have stopped it first.
2. **When** someone removes that bound or raises it past the credential's
   lifetime, **Then** a deterministic check fails and names the job.
3. **Given** a normal one-minute teardown, **When** the job runs, **Then** its
   completion summary, its issue close and its branch deletions are unchanged
   from today.
4. **Given** the agent step hits the bound and is killed, **When** the job
   continues, **Then** the close/label/delete steps still run on a credential
   that is still inside its lifetime, and the incomplete-teardown report says
   what did not finish.

---

### User Story 3 - No agent-bearing workflow is invisible to the gate (Priority: P2)

A maintainer adds an agent step to a workflow, or a new workflow with one.
They expect the repository to tell them, on that pull request, that the
workflow must either adopt the post-agent remedy or record why it does not
need it.

**Why this priority**: The whole reason this issue exists is that Gate 68's
subject list was a hand-written copy of FR-007's eight stages, so two
workflows with the identical defect were never checked and nothing said so.
Fixing the two files without fixing how they were missed leaves the next
workflow to be missed the same way. It is P2 only because the two known
exposures are what the maintainer is currently carrying — but the clarification
kept it in this feature rather than deferring it to #410, so it ships here.

**Independent Test**: Add an agent step to a workflow that is neither covered
nor exempt and confirm the gate fails naming that workflow and job; remove all
subjects and confirm the gate fails loudly rather than passing over an empty
set.

**Acceptance Scenarios**:

1. **Given** a workflow containing an agent step that is neither covered by
   the post-agent remedy nor carried in a recorded exemption, **When** the
   gate suite runs, **Then** it fails and names the workflow and the job.
2. **Given** a recorded exemption, **When** the gate suite runs, **Then** the
   exemption states its reason and cites the deciding issue, and the gate
   asserts the condition the exemption relies on still holds.
3. **Given** a workflow whose agent step is deleted, **When** the gate suite
   runs, **Then** the gate fails rather than passing vacuously — the same
   loud-empty-set rule spec 052's FR-022 already set.

---

### Edge Cases

- **The agent step fails rather than running long.** The post-agent steps must
  still run and still report; they must not run on a cancelled workflow. This
  is the `!cancelled()` versus `always()` distinction the `review-step-gating`
  skill covers, and `rebase.yml`'s publish arm is already status-gated
  (`rebase.yml:945`) in a way a naive edit can break.
- **The re-establishment itself fails.** A failed re-mint must degrade to a
  named, reported outcome — not a green check over steps that silently did
  nothing (Constitution Principle VIII).
- **The agent step is skipped.** A job that skips its agent step must not then
  require or report a post-agent refresh that had nothing to refresh.
- **`rebase.yml` runs as a matrix.** Each matrix leg is its own job instance
  with its own mint; the remedy must hold per leg, not once per workflow.
- **`rebase.yml` has no separate survivor job.** Its abandon/escalate path is
  an arm *inside* the same job, unlike the six stages whose separate `stalled`
  job Gate 68 checks for a stall-reason step. The requirement is that the arm
  that runs when the agent did not succeed can name an expired credential —
  not that a job shaped like `stalled` must be invented.
- **The concurrency race that cancelled spec 052's rebase legs.** A leg
  cancelled at 25 minutes never reaches its post-agent steps at all; the
  remedy must not make a cancelled leg report a false failure.
- **A workflow that mints two different credentials.** `cleanup.yml` and
  `rebase.yml` each mint one; any exemption or coverage record must not assume
  that stays true.

## Requirements *(mandatory)*

### Functional Requirements

**The exposure itself**

- **FR-001**: Every step in `rebase.yml`'s `rebase` job that acts as the bot
  after that job's agent step MUST hold a credential established after the
  agent step finished — specifically the over-budget report, the publish arm,
  the abandon/escalate arm, and the lifecycle-issue announcement.
- **FR-002**: In `rebase.yml`'s `rebase` job, any git remote authenticated by a
  checkout that ran **before** the agent step MUST be re-authenticated after it
  — its force-with-lease publish pushes through such a remote and would
  otherwise carry the superseded credential regardless of what any later step's
  environment says. `cleanup.yml`'s branch deletions push through the same kind
  of persisted remote; there the exposure is closed by FR-005's bound keeping
  the whole job inside the credential's lifetime, not by re-authentication.
- **FR-003**: When post-agent re-establishment fails, the job MUST report the
  credential as the cause in its own outcome reporting, naming the workflow,
  the job and the step, rather than leaving a later step to fail with an
  unexplained authentication error.
- **FR-004**: In `rebase.yml`, the arm that runs when the agent step did not
  succeed MUST be able to name an expired or unrefreshed credential as the
  reason it is escalating, so a maintainer reading the escalation comment can
  tell a genuine conflict from a timed-out credential.
- **FR-005**: `cleanup.yml`'s `teardown-done` job MUST be protected against the
  same defect by a **wall-clock bound** on its agent step or its job, strictly
  less than the credential's lifetime, together with a recorded exemption from
  the post-agent mechanism. It MUST NOT receive the post-agent composites.
  Following spec 052's precedent for `auto-update-spec-kit.yml`'s
  `evaluate-path` and `comment-reply` jobs, the bound is `timeout-minutes: 10`
  — an order of magnitude under the roughly 60-minute lifetime, and ten times
  the agent's measured one minute.
- **FR-006**: FR-005's bound MUST be enforced deterministically: a check MUST
  fail if the bound is absent, or is not strictly less than the credential's
  lifetime, so that removing or raising it cannot silently reintroduce the
  defect.
- **FR-007**: Any exemption MUST record its reason and cite the issue that
  decided it, in the same place the check that honours it reads — a reason
  stated only in prose no check consults does not count (Principle VIII). Its
  condition MUST be one the check can assert mechanically (a bound that is
  present and under the lifetime; post-agent composites that are present and
  consumed); an exemption whose condition the check cannot assert is not a valid
  exemption, and the check MUST fail on it rather than honour it. `cleanup.yml`
  and `watchdog.yml` cite #558 as the deciding issue; `board-loop.yml` cites
  #558 and #410.

**Coverage**

- **FR-008**: The deterministic check that pins the post-agent remedy MUST
  treat `rebase.yml`'s `rebase` job as a subject, and MUST treat
  `cleanup.yml`'s `teardown-done` job as a recorded exemption per FR-005.
- **FR-009**: The check's subject set MUST be **derived** from the workflows —
  discovered by finding the agent steps that are present, not read from a
  hand-maintained list — so that a workflow or job with an agent step is in
  scope by existing. Every derived agent-bearing workflow MUST be either a
  subject or covered by a recorded exemption, and the check MUST fail when one
  is neither. This resolves #410 item 1 within this feature, and brings two
  further workflows into scope now:
  - `board-loop.yml`, whose agent-bearing jobs already consume the post-agent
    composites voluntarily, is recorded as an exemption for now, with adoption
    of those composites as its asserted condition.
  - `watchdog.yml`, whose agent step carries `timeout-minutes: 10`, is recorded
    as an exemption on the same footing as `cleanup.yml` — the bound is its
    asserted condition and FR-006 applies to it.
  The derivation MUST stay consistent with the derivation-plus-floor decision
  answered on #549; it MUST NOT introduce a second, contradicting way of
  discovering the same subjects.
- **FR-010**: The check MUST fail loudly rather than pass when it cannot reach
  its subject: a named file missing, a named job absent, a subject job with no
  agent step, or an empty subject list. This restates spec 052's FR-022 for
  the widened subject set, so widening the set cannot weaken it.
- **FR-011**: The check MUST run with the same subject and the same arguments
  locally (`run-local-gates.py`) as in CI, and MUST be triggered by changes to
  every workflow it inspects.
- **FR-012**: The check MUST ship with a self-test that reintroduces each way
  the new coverage could regress — for `rebase.yml`'s `rebase` job, a post-agent
  step reverted to the pre-agent credential, a deleted re-establishment and a
  deleted remote re-authentication; for each bounded job, a removed and an
  over-long wall-clock bound; for the derived set, an agent-bearing workflow
  that is neither a subject nor an exemption, an exemption whose asserted
  condition no longer holds, and a subject whose agent step is gone — and
  asserts each one fails.

**Not changing anything else**

- **FR-013**: Observable behaviour on the paths that do not hit the defect
  MUST be unchanged: a clean rebase that needs no agent work, and a normal
  one-minute teardown, MUST produce the same outcomes, comments, labels,
  branch deletions and artifacts as today.
- **FR-014**: In `rebase.yml`, post-agent steps MUST run when the agent step
  failed and MUST NOT run when the workflow was cancelled, and the arms they
  feed (publish and abandon/escalate) MUST keep their existing gating
  semantics. In `cleanup.yml`, adding the bound MUST NOT change the gating of
  the close, delete and incomplete-teardown steps — an agent step killed by the
  bound counts as a failed agent step, not a cancelled workflow.
- **FR-015**: No published composite's declared input surface may be widened
  to accomplish this, and any shared logic MUST be consumed from its existing
  single home rather than re-pasted into either workflow.
- **FR-016**: The contract documents describing which jobs relay and refresh
  the credential MUST be updated to include the newly covered jobs, so the
  documented set and the checked set are the same set.

### Key Entities

- **Bot credential**: the minted App installation token, lifetime about one
  hour, held by every step that acts as the pipeline bot. The subject of the
  whole feature.
- **Agent step**: an `anthropics/claude-code-action` invocation. Unbounded in
  wall-clock terms unless something bounds it; its turn ceiling bounds work,
  not time.
- **Persisted remote credential**: the copy of the credential a checkout
  writes into the git remote, which no later environment change refreshes.
- **Subject list**: the set of workflow/job pairs the deterministic check
  holds to the post-agent remedy.
- **Exemption record**: a named, reasoned entry stating why a workflow with an
  agent step needs no post-agent remedy, together with the condition (e.g. a
  wall-clock bound) that makes it true.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Of the bot-acting steps that run after the agent step in
  `rebase.yml`'s `rebase` job, **zero** hold a credential established before
  that agent step — counted today as 4, plus one persisted remote.
  `cleanup.yml`'s 4 such steps (plus its persisted remote) keep the pre-agent
  mint by design, and are covered by SC-004's bound instead.
- **SC-002**: The number of workflows in this repository that contain an agent
  step and are neither a subject of the check nor covered by a recorded
  exemption is **zero**, verified by the check itself rather than by reading —
  measured over the derived set, so the count includes workflows nobody added
  to a list, and `board-loop.yml` and `watchdog.yml` are accounted for rather
  than merely absent.
- **SC-003**: A rebase whose agent runs past the credential's lifetime ends
  with the rebased branch published, or with a reported failure that names the
  credential — never with an unexplained authentication error and no
  explanation anywhere in the run.
- **SC-004**: No `teardown-done` agent step can run past the credential's
  lifetime: the enforced bound is present, is at most 10 minutes, and the check
  fails if it is deleted or raised — so the lifecycle issue is closed and the
  pipeline branches deleted on a credential still inside its hour.
- **SC-005**: Every regression the new coverage is meant to catch is
  demonstrated to fail by the check's self-test — 100% of the FR-012 list,
  with no case passing when reintroduced.
- **SC-006**: A pull request that adds an agent step to an uncovered,
  unexempted workflow fails the gate suite, naming the workflow and job.
- **SC-007**: Runs on the unaffected paths are byte-identical in outcome: a
  clean rebase and a one-minute teardown produce the same comments, labels,
  branches and artifacts as before the change.

## Assumptions

- The minted App installation token's lifetime is approximately 60 minutes.
  "Strictly less than the credential's lifetime" in FR-005/FR-006 means a
  bound with real margin under that — the precedent spec 052 set for
  `auto-update-spec-kit.yml`'s `evaluate-path` and `comment-reply` jobs is
  `timeout-minutes: 10`, an order of magnitude under, and the clarification
  chose that same figure for `cleanup.yml`.
- `board-loop.yml`'s exemption is provisional ("for now", per the
  clarification): it is exempt because it already consumes the post-agent
  composites, not because it is out of reach, so promoting it to a full subject
  later is expected to be a re-classification, not a new remedy.
- The measurements quoted in the Overview (40 runs per workflow, 2026-09-21)
  are accepted as the basis for the trade-off. They bound what has been
  observed, not what is possible — the rebase figures in particular are
  censored by the concurrency cancellations.
- Spec 058 (`per-job-minute-floor`, #434) has landed on main, so the
  sequencing caveat the owner attached to this work ("best done after 058,
  since 058's implement cycle is editing every published stage right now") no
  longer applies.
- `rebase.yml`'s `rebase` job runs as a matrix over in-flight branches; each
  leg is an independent job instance.
- The remedy is the one spec 052 chose and shipped; this feature extends its
  reach, it does not reopen the choice of remedy for the eight stages already
  covered.
- No consuming repository's published interface changes — both workflows are
  called through the existing wrapper surface, and FR-015 forbids widening any
  composite's inputs.
- Changes to `rebase.yml`'s publish and abandon/escalate arms touch `if:`
  conditions and a `continue-on-error:`-shaped path, so the
  `review-step-gating` skill applies to the implementing change; the repository
  gate suite (`run-local-gates.py`) is the acceptance bar for every gate
  requirement above.

## Dependencies

- Spec 052 (`052-agent-credential-lifetime`) — the remedy, its composites
  (`wing-commander-context` re-mint, `wing-commander-refresh-remote`,
  `wing-commander-agent-ran-signal`,
  `wing-commander-post-agent-credential-status`,
  `wing-commander-failed-post-agent-step`, `wing-commander-stall-reason`) and
  its gate, all already shipped and consumed by eight stages.
- Gate 68 (`.github/scripts/verify-post-agent-credential-refresh.py`) and its
  registration in `lint-workflows.yml` — the check this feature widens.
- Issue #410 item 1 ("derive the subject list") — resolved **inside** this
  feature by FR-009, per the clarification on #558; it should be closed against
  this spec rather than worked separately.
- Issue #549 — the derivation-plus-floor decision this feature's derivation must
  stay consistent with (FR-009).
- Issue #411 — the originating board item, carrying the measurement table.
