# Feature Specification: A Run That Spent Money Says So — Intake's Silent Outcome Paths Report Their Cost

**Feature Branch**: `spec-draft/065-intake-silent-path-cost`

**Created**: 2026-09-24

**Status**: Draft

**Input**: Lifecycle issue #495 — "intake: a run whose agent found no feature
request reports no cost line" (routed from board-loop.yml; originating issue
#381, whose body was read as further description of the same request)

## Overview

Every intake run invokes a spec-authoring agent, and that agent costs real
money. The run's spend is computed once per run as a **cost line** (for
example `**Cost**: $1.74`) and is meant to reach the requester where they
are already looking: the lifecycle issue.

Today that line rides exclusively on intake's two outcome-announcing
callouts — "Answer the open clarification questions" and "Review the spec
PR". A run that takes neither of those paths posts nothing, and its spend is
reported nowhere the requester or the watchdog can see it.

The path named in the request is the most visible one: the agent is
instructed to stop at prompt step 2 when the issue contains no discernible
feature request, post its own explanatory comment, and return
`specified: false`. The workflow then deliberately announces nothing — there
is no spec and no pull request to point at — so the run finishes green,
having spent a full agent invocation, with no statement of what it cost.

It is not the only such path. The clarification-gating gate already records
**four** intake outcomes as deliberately silent:

1. **No discernible feature request, no questions** — the prompt's step-2
   STOP. The agent's own comment is the whole output.
2. **No discernible feature request, but questions returned** — the
   structured result is schema-conforming wherever the agent stopped, so a
   STOP can still carry questions. Posting them would be a dead end (no
   spec, no `spec:`/`stage:` label, so no reply can be acted on), and
   suppression is deliberate.
3. **A spec was authored with no open questions, but no branch resolved** —
   nothing is wrong with the spec; there is simply no pull request URL to
   point anyone at. An accepted gap, pinned as a decision.
4. **`specified: false` yet a spec branch did resolve, with a marker-free
   spec** — which run authored that branch is not knowable, so nothing is
   announced; the contradiction is emitted to the run log for the watchdog
   instead.

All four are correct decisions about *outcome* announcements. None of them
is a decision that the run's cost should go unreported — that is a side
effect of the cost line only ever travelling as a passenger on an outcome
callout.

The same shape has now been found and fixed twice elsewhere, each time
bespoke: in the clarify stage, for the agent's early-STOP path (issue #366),
and in the plan and tasks stages, for auto-mode hand-offs (issue #377). The
request explicitly raises the question of whether a third bespoke copy is
the right answer or whether one uniform per-stage cost report should replace
all of them. **The requester chose the uniform answer**: one cost report per
cost-bearing stage, emitted from the existing cost-line single home, with
the outcome callouts no longer carrying the cost line and the two bespoke
copies retiring in the same change.

### Why this is not cosmetic

- **The requester is left guessing.** On path 1 the only thing on the issue
  is the agent's "I could not produce a specification" comment. A
  maintainer deciding whether to rewrite the issue and try again cannot see
  what the failed attempt cost without opening the run and reading its
  summary.
- **The supervision layer files a defect for every such run.** The
  watchdog's cost-report collector raises a `cost-line-missing` signal
  whenever a run's cost is available but none of the run's own comments on
  the lifecycle issue carries a cost line. Each of the four paths above
  matches that description exactly, so each silent run costs a second,
  avoidable agent invocation to diagnose and file an issue about a
  known-missing line.
- **Cost-consciousness is a stated principle.** The constitution's
  cost-conscious tiering (II) and GitHub-native legibility (III) both
  assume the lifecycle issue tells the whole story of a spec, spend
  included, and automation-first (IV) requires anything the pipeline does
  to be reported rather than silently assumed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A run that found no feature request still reports what it spent (Priority: P1)

A maintainer labels a thin issue for the pipeline. Intake runs, the agent
judges there is no discernible feature request, posts its own comment
explaining what is missing, and stops. The lifecycle issue also carries a
short note stating what that run cost, so the maintainer can weigh a second
attempt against the price of the first, and the supervision layer sees the
spend it went looking for.

**Why this priority**: This is the reported defect and the most frequent of
the four silent paths — it is reachable by any thin issue, needs no unusual
repository state, and is the one a requester meets first.

**Independent Test**: Drive an intake run against an issue with no
discernible feature request and confirm the lifecycle issue ends the run
carrying both the agent's explanatory comment and a statement of the run's
cost.

**Acceptance Scenarios**:

1. **Given** an intake run whose agent returns `specified: false` with no
   questions, **When** the run finishes, **Then** the lifecycle issue
   carries exactly one statement of that run's cost, and the run stays
   green.
2. **Given** the same run, **When** the supervision layer inspects it,
   **Then** it finds the run's cost reported on the lifecycle issue and
   raises no missing-cost defect.
3. **Given** an intake run whose agent returns `specified: false` together
   with clarification questions, **When** the run finishes, **Then** no
   questionnaire is posted (unchanged) and the run's cost is still
   reported.

---

### User Story 2 - Every intake outcome reports its cost exactly once (Priority: P1)

Whatever intake decides — questionnaire, spec PR, deliberate silence, or a
suppressed announcement over a branch it cannot claim — the lifecycle issue
ends up with the run's cost stated once. Not twice on the paths that already
announce something, and not zero times on the paths that announce nothing.

**Why this priority**: Fixing only the reported path leaves the other three
silent, and the supervision layer will keep filing a defect for each of
them. Reporting twice on the happy paths would be a new defect of its own —
the requester reads two cost figures for one run and cannot tell whether the
run was charged once or twice.

**Independent Test**: Walk every intake outcome path and count the cost
statements on the lifecycle issue: each path yields exactly one.

**Acceptance Scenarios**:

1. **Given** an intake run that posts a clarification questionnaire, **When**
   the run finishes, **Then** the issue carries exactly one statement of
   the run's cost.
2. **Given** an intake run that announces a spec PR as ready, **When** the
   run finishes, **Then** the issue carries exactly one statement of the
   run's cost.
3. **Given** an intake run that authored a spec with no open questions but
   whose branch did not resolve, **When** the run finishes, **Then** the
   issue carries exactly one statement of the run's cost, and no outcome is
   announced (unchanged).
4. **Given** an intake run that returned `specified: false` while a
   marker-free spec branch resolved, **When** the run finishes, **Then** the
   contradiction is still recorded for the supervision layer (unchanged),
   the run still announces no outcome, and the issue carries exactly one
   statement of the run's cost.
5. **Given** an intake run whose metrics could not be read, **When** the run
   finishes, **Then** the issue still carries one cost statement, saying
   the metrics were unavailable rather than omitting the line.
6. **Given** an intake run the workflow deliberately fails — the readiness
   veto over unresolved clarification markers, or the contradiction veto —
   **When** the run finishes red, **Then** the issue still carries exactly
   one statement of the run's cost, and the run's conclusion is still red.
7. **Given** an intake run cancelled in flight, **When** the run ends,
   **Then** no cost statement is posted, matching what the supervision
   layer already skips.

---

### User Story 3 - One cost report, not a fourth copy of one (Priority: P1)

A maintainer reading the repository finds a single place where a stage's
cost report is defined and gated, shared by every cost-bearing stage. The
clarify stage's early-STOP report (#366) and the plan/tasks auto-mode
hand-off reports (#377) are that same shared report rather than three
private lookalikes, and the outcome callouts that used to embed the cost
line no longer carry it.

**Why this priority**: This is the answer the requester chose over a third
bespoke copy, and it is the reason the change is worth more than a one-line
patch. Shipping intake's fix as a fourth private copy would satisfy US1 and
US2 while leaving the next rounding fix to land in four places.

**Independent Test**: Search the repository for places that format or gate a
per-stage cost report; find exactly one, consumed by intake, clarify, plan
and tasks.

**Acceptance Scenarios**:

1. **Given** the shipped change, **When** the repository is searched for
   per-stage cost-report definitions, **Then** exactly one is found and
   every cost-bearing stage consumes it.
2. **Given** a clarify run that takes the agent's early-STOP path, **When**
   the run finishes, **Then** its cost is reported once, by the shared
   report rather than the retired bespoke copy.
3. **Given** a plan or tasks run that hands off in auto mode, **When** the
   run finishes, **Then** its cost is reported once, by the shared report
   rather than the retired bespoke copy.
4. **Given** an outcome callout on any stage, **When** it is posted,
   **Then** it no longer carries an embedded cost line, and the run's single
   cost statement comes from the shared report instead.

---

### User Story 4 - The cost report cannot quietly disappear again (Priority: P2)

The rule "a run that ran its agent reports its cost" is checked by a gate
that fails when the report is removed, ungated, or left carrying an empty
body, and the nearest existing gate also fails when a copy of the shared
report reappears in a workflow.

**Why this priority**: This defect existed because the silent paths were
recorded as "nothing is posted here, by design" with no distinction between
*no outcome announcement* and *no cost report*. Without a check that can
fail, the next refactor restores the gap and nothing notices until the
watchdog files the issue again.

**Independent Test**: Delete or blank the cost report from the workflow and
confirm the PR-time gate suite fails.

**Acceptance Scenarios**:

1. **Given** the shipped workflow, **When** the PR-time gate suite runs,
   **Then** every intake outcome path asserts the presence of exactly one
   cost report.
2. **Given** a deliberately broken cost report (removed, its gate
   condition stripped, or its body emptied), **When** the gate suite runs,
   **Then** a gate fails and names the path that would have gone silent.
3. **Given** the silent-outcome paths, **When** the gate suite runs,
   **Then** "this path announces no outcome" is expressed distinctly from
   "this path posts nothing at all", so a future silent path cannot inherit
   a cost exemption it was never granted.
4. **Given** a workflow into which a private copy of the cost report has
   been pasted, **When** the gate suite runs, **Then** a gate fails on the
   duplicate, so the single home cannot erode after this change ships.

---

### Edge Cases

- **Metrics unavailable.** The run still reports a cost statement carrying
  the existing "metrics unavailable" wording, so the requester learns the
  figure is missing rather than learning nothing.
- **The agent step never ran** (preflight refusal, closed lifecycle issue,
  a stage that stopped before invoking the agent). No agent invocation, no
  spend to report; the run posts no cost statement, and the supervision
  layer already treats such runs as carrying no cost signal.
- **A rate-limited run** (the agent turned away by an API 429: one turn,
  zero cost). Cost is effectively zero and the metrics may be absent; this
  feature must not turn such a run into a noisy comment claiming a spend
  that did not happen.
- **The lifecycle issue was closed while the run was in flight.** Posting
  to a closed issue is out of scope for this feature; the existing
  closed-lifecycle behaviour governs.
- **Posting the cost statement fails** (API error, permissions). The run's
  conclusion must be unchanged by that failure — a lost cost comment must
  never be the thing that turns a good spec run red, nor the thing that
  lets a bad one pass.
- **A run the workflow deliberately fails** (an announced-readiness veto
  over unresolved markers, or the contradiction veto). The agent ran and the
  money was spent, so the cost is reported and the run still ends red; the
  report must sit below the failing step without being stranded by it.
- **A cancelled run.** Nothing is posted — the supervision layer already
  skips cancelled runs, so a cancelled run carries no missing-cost signal to
  answer.
- **Two intake runs on one issue.** Each run's cost statement is
  attributable to its own run, so a reader with two comments can tell which
  run each figure belongs to.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: An intake run that invoked its agent MUST report that run's
  cost on the lifecycle issue, on every outcome path — including the four
  paths that deliberately announce no outcome.

- **FR-001a**: The same rule MUST hold for every other cost-bearing stage:
  a run that invoked its agent reports that run's cost on the lifecycle
  issue, whatever the stage decided and whatever the run's conclusion.

- **FR-002**: The scope of this change is one uniform per-stage cost report,
  adopted across every cost-bearing stage rather than a fourth stage-local
  copy. The report MUST be defined once, in the same single home the cost
  line already lives in, and MUST replace the bespoke copies added for the
  clarify stage (#366) and the plan/tasks stages (#377), folding them and
  this request (#381) into one mechanism.

- **FR-002a**: Outcome callouts MUST stop carrying the cost line. After this
  change the cost reaches the lifecycle issue only through the uniform
  report, so that no path can lose its cost statement by changing what it
  announces.

- **FR-003**: Exactly one cost statement MUST reach the lifecycle issue per
  run of a cost-bearing stage. A path that announces an outcome MUST NOT
  also post a separate cost statement, and a path that announces nothing
  MUST NOT be left without one.

- **FR-004**: The reported figure MUST come from the run's single existing
  cost-line source. This feature MUST NOT introduce a second place where a
  cost figure is formatted or rounded; it MUST reduce the count by retiring
  the bespoke copies FR-002 names.

- **FR-005**: The reported text MUST keep the existing cost-line format that
  the supervision layer validates (a currency amount, two decimal places at
  or above one dollar and four below), so that reporting the cost cannot
  itself trip a malformed-cost defect.

- **FR-006**: When the run's metrics cannot be read, the report MUST still
  be posted, carrying the existing "metrics unavailable" wording rather than
  an empty or absent line.

- **FR-007**: The cost report MUST be attributable to the run that spent the
  money: posted by a pipeline identity, on that run's lifecycle issue,
  within the run's own window, so the supervision layer's attribution can
  tell it from a comment left by an earlier run on the same issue.

- **FR-008**: Adding the cost report MUST NOT change which outcome callout
  fires on any path, MUST NOT change the wording of any existing outcome
  callout beyond removing the cost line FR-002a relocates, and MUST NOT
  change any path's decision to stay silent about its outcome.

- **FR-009**: A failure to post the cost report MUST NOT change the run's
  conclusion — it can neither turn a healthy run red nor mask a run that
  should have failed.

- **FR-010**: The requirement MUST be enforced by a gate that exercises each
  intake outcome path and fails when the cost report is absent, ungated,
  mis-gated, or carries an empty body. Each failure branch MUST be exercised
  by a checked-in fixture rather than a one-time manual demonstration.

- **FR-010a**: The single home MUST itself be gated: the nearest existing
  gate MUST fail when a copy of the cost report or its formatter reappears
  inside a workflow, the same way the existing metrics-summary check guards
  the cost line's formatter today.

- **FR-011**: The existing record of intake's deliberately silent paths MUST
  be restated so that "announces no outcome" and "posts nothing at all" are
  distinguishable, and a path may opt out of the outcome announcement
  without inheriting an exemption from the cost report.

- **FR-012**: Runs that intake deliberately fails — the readiness veto over
  unresolved clarification markers, and the contradiction veto — MUST also
  report their cost on the lifecycle issue. The rule is conclusion-blind: a
  run that invoked its agent reports what it spent whether it ends green or
  red, which is also what the supervision layer's cost collector expects,
  since it skips only skipped and cancelled runs.

- **FR-012a**: The cost report MUST NOT be strandable by a failing step
  above it. A step that deliberately fails the run MUST still leave the
  report to run, and the report's own gating MUST be reviewed for that
  property before it ships.

- **FR-013**: A run that invoked no agent (and therefore spent nothing) MUST
  NOT post a cost report. A cancelled run MUST NOT post one either.

- **FR-014**: The run's own summary MUST continue to carry the same metrics
  it carries today; this feature adds a report on the issue, it does not
  move reporting off the run.

### Key Entities

- **Cost line**: the single per-run statement of spend, produced once per
  run from the run's metrics, with a defined text format and a defined
  fallback when metrics are unavailable.
- **Outcome callout**: a comment intake posts on the lifecycle issue
  announcing what the requester should do next (answer questions, review the
  spec PR). Today it is the only carrier of the cost line; after this change
  it carries no cost line at all.
- **Uniform cost report**: the one shared per-stage report that delivers the
  cost line to the lifecycle issue, defined in a single home and consumed by
  every cost-bearing stage.
- **Silent outcome path**: an intake result that deliberately announces no
  outcome — four of them today, each a recorded decision rather than an
  oversight.
- **Lifecycle issue**: the requester-facing record of a spec's life, and the
  place the supervision layer reads to decide whether a run reported its
  cost.
- **Cost-report signal**: the supervision layer's finding that a run with
  available cost reported none of it on its lifecycle issue.

## Success Criteria *(mandatory)*

- **SC-001**: 100% of intake runs that invoke their agent end with exactly
  one cost statement on the lifecycle issue — measured across every outcome
  path the gate suite enumerates, not just the announcing ones, and
  regardless of the run's conclusion.

- **SC-002**: Zero missing-cost defects are filed against runs of any
  cost-bearing stage whose cost was available, over the first ten such runs
  after the change ships.

- **SC-003**: A maintainer reading only the lifecycle issue of a run that
  found no feature request can state what that run cost, without opening the
  run or downloading an artifact.

- **SC-004**: Removing, ungating, or blanking the cost report causes the
  PR-time gate suite to fail, and the failure message names the path that
  would have gone silent.

- **SC-005**: No outcome path of any cost-bearing stage posts two cost
  statements for one run.

- **SC-006**: The number of distinct places a per-stage cost report is
  defined in this repository decreases to one, and the number of places a
  cost figure is formatted does not increase.

- **SC-007**: Every cost-bearing stage's cost report is the shared one: no
  workflow contains its own copy, and a pasted copy fails a gate.

## Assumptions

- The existing per-run cost figure and its "metrics unavailable" fallback
  are correct and stay as they are; this feature changes where that line is
  delivered, never how it is computed.
- The four silent outcome decisions themselves are correct and out of scope.
  In particular, this feature does not propose announcing a spec PR on the
  path where the branch cannot be claimed, nor posting a dead-end
  questionnaire.
- A separate short comment carrying the cost is acceptable on the paths that
  post nothing else, following the precedent already set for the clarify
  stage's early-STOP path. Attaching the cost to the agent's own comment is
  not available — the workflow cannot edit what the agent posted.
- "Reports its cost" means a comment on the lifecycle issue. A run-summary
  entry alone does not satisfy it, because the requester does not see the
  run and the supervision layer reads comments.
- The supervision layer's cost collector keeps its current behaviour
  (skipping runs with no resolved lifecycle issue and runs whose conclusion
  is skipped or cancelled); this feature changes what the stages post, not
  what the collector looks for.
- Every cost-bearing stage is in scope, because FR-002 resolved to the
  uniform report. What changes for the stages other than intake is where
  their cost statement comes from, not whether they make one: clarify's
  early-STOP report and plan/tasks' auto-mode reports keep reporting, from
  the shared mechanism instead of their own copies.
- The requester's answer also directs that the report survive a failing step
  above it and that its gating get a `review-step-gating` pass before
  merge; that is recorded here as a constraint on the implementation, not as
  a behaviour this spec prescribes a mechanism for.

## Dependencies

- The per-run cost line and metrics summary this feature reports from.
- The supervision layer's cost-report collector, which is what makes an
  unreported cost visible as a defect rather than merely invisible.
- The existing clarification-gating gate, whose per-path scenario table is
  where intake's silent paths are recorded today and where the new
  requirement is most naturally enforced.
- The precedent fixes for the same shape in the clarify stage (#366) and the
  plan/tasks stages (#377), which FR-002's uniform report absorbs.
- The existing single-home check on the cost line's formatter, which the new
  single-home check for the report joins rather than duplicates.

## Out of Scope

- Changing how cost is computed, rounded, or formatted.
- Changing which outcome any stage announces on any path.
- Reporting cost for runs that never invoked an agent.
- The supervision layer's own behaviour, fingerprints, or defect wording.
