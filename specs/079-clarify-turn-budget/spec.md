# Feature Specification: Clarify's Turn Budget Reflects the Work Clarify Actually Does

**Feature Branch**: `079-clarify-turn-budget`

**Created**: 2026-09-25

**Status**: Draft

**Input**: User description: "watchdog: turn-budget-trend. The turn-budget collector emitted a cross-run trend for the clarify stage at band `elevated` over a 10-run window. This run (35665831869) counted 39 turns against an `intended-budget` of 40, and the window's `max-consumed-ceiling-fraction` is 0.61 with `headroom-remaining-fraction` 0.39; `consecutive-at-or-over-budget` is 0, so no run is currently stacking against the budget back-to-back. Two runs in the recorded history did exceed the intended budget outright — run 35554001500 at 61 counted turns and run 35422301482 at 45 counted turns, both against intended-budget 40 — which is the climb that puts the band above baseline. No step or job failed on this basis; the signal is a consumption trend for clarify, not a run failure. Class note: the signal's own `class-hint` is `turn-budget-trend`, which the repository already treats as a registered class (`.github/workflows/watchdog.yml:2985` maps `turn-budget-trend) keys='[\"stage\",\"expected\",\"actual\"]'`), and it is a distinct resource dimension from the listed `token-budget-warning` (agent turn count, not token consumption), so it is proposed as its own class rather than folded into a near-synonym. Evidence caveat for this run: `watchdog-untrusted-collectors.json` names `[\"collect-step-summary\"]`, so step-summary/sentinel evidence could not be gathered this run — any stall- or failure-flavored sentinel the clarify job may have written is absent from the signals file and was not weighed either way. Evidence: turn-budget-trend, watchdog-signals.json, signal id 57d2ab2e36bd34ff: facts.stage=\"clarify\", facts.band=\"elevated\", facts.window-size=10, facts.max-consumed-ceiling-fraction=0.61, facts.headroom-remaining-fraction=0.39, facts.consecutive-at-or-over-budget=0; facts.history entries {run 35665831869, counted-turns 39, intended-budget 40}, {run 35554001500, counted-turns 61, intended-budget 40}, {run 35422301482, counted-turns 45, intended-budget 40}. Routed from board-loop.yml (issue #448): the route agent judged this spec-shaped — turn-budget-trend is a fully-implemented, working alert (specs/046) correctly reporting clarify's elevated turn consumption; the response (raise the budget, investigate clarify's turn usage, or accept the trend) is the owner's trade-off to decide."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A stage's declared turn budget describes the work that stage really does (Priority: P1)

The clarify stage declares an intended turn budget. Over the recorded window, real clarify runs finished at 39, 45 and 61 counted main-loop turns against a declared budget of 40 — so the declared number describes neither the typical run nor the heavy one. A maintainer reading the budget should be reading a statement about clarify's work that holds for the runs clarify actually performs, and the supervision signal that watches consumption should be quiet when nothing is wrong and loud when something is.

**Why this priority**: This is the request. The alert is working exactly as designed (specs/046); what it reports is that a declared expectation and observed reality have diverged for the clarify stage. Until the declared number is decided, every clarify run near the top of its range posts an over-budget note to the requester's lifecycle issue, the watchdog keeps re-filing the trend, and the budget stops functioning as a signal a maintainer can act on — the classic alert that is true, repeated, and therefore ignored.

**Independent Test**: Replay the recorded clarify history — 39, 45 and 61 counted turns — against the stage's declared budget after this feature lands, and confirm that runs representative of clarify's normal work are neither reported over budget nor counted toward a trend band, while a run genuinely outside clarify's established range still is.

**Acceptance Scenarios**:

1. **Given** a clarify run that consumes as many counted main-loop turns as the heaviest run in the recorded window (61), **When** the run finishes healthy, **Then** it is not reported as over budget and no over-budget note is posted to the lifecycle issue.
2. **Given** the recorded 10-run clarify history replayed against the post-change configuration, **When** the turn-budget collector computes a band, **Then** no trend band is produced for clarify and no `turn-budget-trend` signal is emitted.
3. **Given** a clarify run that consumes materially more turns than any run in the recorded window, **When** the run finishes, **Then** it is still identified and reported as over budget, so the instrument has not been silenced — only re-based.
4. **Given** the change, **When** a maintainer reads the clarify stage's declared budget and the reasoning recorded beside it, **Then** the number is traceable to the observed history it was derived from, not to an unexplained constant.

---

### User Story 2 - Re-basing a budget does not quietly re-base what a runaway agent may spend (Priority: P1)

The declared budget is an observability instrument; the runaway ceiling handed to the agent is the only hard stop, and today the ceiling is derived from the declared budget by a fixed multiplier. Any change to the declared budget therefore moves the worst-case spend with it. A maintainer changing the budget must see, and deliberately choose, the worst-case number of turns a runaway clarify agent may consume before anything stops it.

**Why this priority**: Constitution II puts all of this repository's cost protection on the ceiling — no stage may run without a bounded turn budget, and since spec 037 the ceiling is the only thing that actually stops a run. Raising a declared budget to quiet an alert, and thereby raising the hard stop as an unremarked side effect, converts an observability fix into a cost decision nobody made. Clarify runs on the premium model tier, so the per-turn cost of that side effect is at the top of the fleet's range.

**Independent Test**: Compare the worst-case turn count a clarify agent can reach before being stopped, before and after the change, and confirm the after value is the one stated in the feature's own record rather than an emergent product of the re-basing.

**Acceptance Scenarios**:

1. **Given** the re-based clarify budget, **When** the resulting runaway ceiling is computed, **Then** its value is stated explicitly in the change and is the value the change intended, not a by-product noticed later.
2. **Given** a clarify agent that genuinely runs away, **When** it reaches the ceiling, **Then** it is stopped at a finite, bounded turn count, and that count is recorded where a maintainer tuning the budget will see it.
3. **Given** the change, **When** the stage's configuration is inspected, **Then** every clarify agent invocation still declares both an explicit model and a bounded ceiling, with no invocation left unbounded.

---

### User Story 3 - A budget can be retuned without editing the published stage workflow (Priority: P2)

A maintainer (of this repository or of an adopting one) who sees a `turn-budget-trend` for a stage can change that stage's declared budget through the same kind of knob every other stage setting uses — a wrapper-owned repository variable with the current value as its default — instead of editing the pinned, adopter-facing stage workflow.

**Why this priority**: Today the clarify wrapper passes `model`, `runner`, `container-image`, the draft prefix and the findings knobs, but not `max-turns`, so the budget is fixed at the stage workflow's own default. That makes the answer to any future budget trend a code change to the published contract — which an adopter cannot make at all, and which this repository can only make by shipping a release. The trend signal exists to prompt a tuning action; the tuning action should not require modifying the instrument's housing. Under constitution VII the knob belongs in the wrapper, because a stage workflow reads no ambient repository state.

**Independent Test**: Change the repository variable for a stage's turn budget, dispatch that stage, and confirm the run uses the new budget and the correspondingly derived ceiling, with no edit to any file under the published stage-workflow surface.

**Acceptance Scenarios**:

1. **Given** no repository variable is set, **When** the stage runs, **Then** it uses exactly the budget it uses today, so adopters who set nothing see no behavioural change.
2. **Given** the repository variable is set to a valid positive value, **When** the stage runs, **Then** the declared budget, the derived ceiling, the over-budget determination and the reported metrics all reflect that value consistently.
3. **Given** the repository variable is set to a value that is not a valid positive turn budget, **When** the stage runs, **Then** the run fails loudly naming the invalid value rather than silently falling back to an unbounded or zero ceiling.

---

### User Story 4 - The next budget trend has a stated response, not a re-derivation (Priority: P3)

When the watchdog next reports a `turn-budget-trend` for any stage, the maintainer working it finds a written, evidence-based procedure: which recorded numbers to read, how to turn them into a new declared budget, what that does to the ceiling and the spend, and when the correct answer is instead to accept the trend rather than move the number.

**Why this priority**: This trend was routed as spec-shaped precisely because the response is a judgement with no recorded procedure behind it. Without one, the same three options get re-argued from scratch every time a stage's consumption drifts, and the cheapest wrong answer — raise the number until the alert stops — is the one a hurried session will reach for. This is the durable half of the feature, but it delivers nothing on its own if clarify's own number is not decided first.

**Independent Test**: Hand the recorded clarify history and the written procedure to someone who did not work this issue, and confirm they arrive at the same declared budget and the same ceiling this feature lands.

**Acceptance Scenarios**:

1. **Given** a new `turn-budget-trend` for some stage, **When** a maintainer follows the recorded procedure, **Then** it names the evidence to read, the arithmetic to apply, the cost consequence to check, and the conditions under which accepting the trend is the right answer.
2. **Given** the procedure, **When** it is applied to the clarify history in this issue, **Then** it reproduces the declared budget and ceiling this feature lands.

---

### Edge Cases

- A stage's recorded history is shorter than the trend window, or empty (a newly added stage, or a fresh metrics store): re-basing has no evidence to work from, and the declared budget must keep a stated default rather than being derived from one or two runs.
- A single outlier run — an unusually contentious clarification round with many questions — dominates the window's maximum. Re-basing to the outlier makes the budget describe the exception; re-basing to the median makes the alert fire every time the exception recurs.
- The recorded history includes runs whose counted turns were inflated by causes unrelated to clarify's real work (for example turns lost to denied tool calls, as diagnosed in spec 037). Re-basing on those turns bakes a defect into the declared budget.
- The currently open `pipeline-defect` issue for the `elevated` band is closed as accepted rather than fixed: the collector's suppression then keeps that band quiet for clarify, but a later escalation to a higher band files a new, separate finding. The response chosen here must be legible against that behaviour rather than fighting it.
- The re-based budget is raised far enough that the derived ceiling exceeds what any single clarify run could plausibly need, so the ceiling stops being a meaningful stop and becomes a formality.
- An adopting repository has deliberately tuned a stage to a small budget for cost reasons; the change must not raise their spend without them setting anything.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pipeline MUST respond to the reported clarify `turn-budget-trend` by [NEEDS CLARIFICATION: which response — (a) re-base clarify's declared budget upward from the recorded history so normal runs sit inside it, (b) reduce what clarify consumes so its real usage returns inside the existing budget of 40, or (c) accept the trend as tolerated and record that decision without moving any number?] and MUST record the reasoning for that response where a later maintainer reading the budget will find it.
- **FR-002**: The scope of the response MUST be [NEEDS CLARIFICATION: clarify only, or every stage's declared budget re-based from its own recorded history in one pass?], and any stage left unchanged MUST be left unchanged deliberately rather than by omission.
- **FR-003**: When a stage's declared budget changes, the worst-case turn count a runaway agent for that stage may reach before being stopped MUST [NEEDS CLARIFICATION: scale with the declared budget as it does today (fixed multiplier, so re-basing 40 → N raises the hard stop proportionally), or be pinned/sized separately so the hard stop and the reported budget move independently?].
- **FR-004**: Every agent invocation in every stage MUST continue to declare an explicit model and a bounded, finite turn ceiling; no change in this feature may leave an invocation unbounded.
- **FR-005**: A clarify run whose counted main-loop turns fall within clarify's established observed range MUST NOT be reported as over budget, either in the run summary or on the lifecycle issue.
- **FR-006**: A run whose counted main-loop turns genuinely exceed the stage's declared budget MUST still be reported as over budget, and MUST still complete rather than fail on that basis — the existing observability-not-failure behaviour is preserved unchanged.
- **FR-007**: After this feature lands, the recorded clarify history replayed against the new configuration MUST produce no trend band for clarify, so the watchdog stops re-filing a finding whose subject has been addressed.
- **FR-008**: A maintainer MUST be able to change a stage's declared turn budget without editing any file in the published, adopter-pinned stage-workflow surface.
- **FR-009**: The knob in FR-008 MUST default to the stage's current declared budget, so a repository that sets nothing observes no change in budget, ceiling, over-budget reporting or cost.
- **FR-010**: The knob in FR-008 MUST live in the trigger-owning wrapper layer and be passed to the stage as a declared input; the stage MUST NOT read it as ambient repository state.
- **FR-011**: An invalid value for the knob in FR-008 MUST fail the run loudly, naming the offending value, rather than resolving to zero, empty or unbounded.
- **FR-012**: The declared budget, the derived ceiling, the over-budget determination and the reported run metrics MUST all be computed from one value per stage per run, so no two of them can disagree about what that run's budget was.
- **FR-013**: The repository MUST carry a written, evidence-based procedure for responding to a future `turn-budget-trend` on any stage, naming the evidence to read, how a new declared budget is derived from it, the spend consequence to check, and when accepting the trend is the correct response.
- **FR-014**: The procedure in FR-013 MUST, when applied to the clarify history cited in this issue, reproduce the values this feature lands — so the procedure is demonstrated rather than merely asserted.
- **FR-015**: The feature MUST NOT change how the turn-budget collector computes bands, how signals are identified, how findings are fingerprinted or deduplicated, or how a closed finding suppresses its band; the supervision machinery from spec 046 is working correctly and is out of scope.
- **FR-016**: The feature MUST NOT change any stage's model tier; cost decisions here are made in turns, not in model choice.
- **FR-017**: Documentation that states a stage's declared budget or lists its tunable settings MUST agree with what the stage does after this change, with no stale number left behind.
- **FR-018**: Whatever rule this feature establishes about stage budgets MUST be enforced by a check in the repository's registered gate suite, so the rule cannot drift back without a failure — a rule with no gate behind it lasts until the next session.

### Key Entities

- **Declared turn budget**: the per-stage number a maintainer tunes and that consumption is reported against. Not a hard stop; an expectation.
- **Runaway ceiling**: the finite turn count at which an agent is actually cut off. Today derived from the declared budget by a single fleet-wide multiplier.
- **Counted main-loop turns**: the deterministic count of distinct main-loop assistant responses for a run, excluding subagent activity — the counter the declared budget is measured against.
- **Trend band**: the severity value (`watch`, `elevated`, `critical`, or none) the supervision collector computes for a stage from its recent history; `elevated` is produced when the window's maximum consumed-ceiling fraction reaches the climb threshold without consecutive at-or-over-budget runs.
- **History window**: the most recent N recorded runs for a stage, each carrying its counted turns, declared budget and ceiling; the evidence any re-basing decision reads.
- **Budget knob**: the wrapper-owned repository variable through which a maintainer sets a stage's declared budget, defaulting to the stage's current value.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Replaying the cited clarify history (39, 45 and 61 counted turns) against the post-change configuration produces zero `turn-budget-trend` signals for clarify.
- **SC-002**: A clarify run at the heaviest observed consumption (61 counted turns) completes with zero over-budget notes posted to the lifecycle issue.
- **SC-003**: The worst-case turn count a runaway clarify agent may reach before being stopped is a single stated number, recorded in the change, and no larger than the value that change chose.
- **SC-004**: Changing a stage's declared turn budget requires edits to zero files in the published stage-workflow surface.
- **SC-005**: A repository that sets no budget variable observes identical declared budgets, ceilings and over-budget behaviour before and after the change, across all stages.
- **SC-006**: Zero pipeline runs fail as a result of this change; no over-budget condition becomes fatal.
- **SC-007**: Every stage's declared budget after the change is traceable in one step to either its recorded history or a stated decision to leave it alone — no stage's number is unexplained.
- **SC-008**: An invalid budget value produces a failing run with a message naming the value, in 100% of the invalid shapes the repository's own fixtures exercise (empty, zero, negative, non-numeric).
- **SC-009**: Applying the recorded procedure to the cited clarify history reproduces the declared budget and ceiling this feature landed, with no additional judgement calls needed.

## Assumptions

- The watchdog's `turn-budget-trend` collector, its band arithmetic, its signal identity and its suppression behaviour (specs/046) are correct and stay untouched; this feature responds to the signal rather than tuning the detector.
- The deterministic turn-counting and agent-verdict machinery (specs/037) is correct; the counted main-loop turns in the cited history are accurate measurements of clarify's work.
- The cited history is the authoritative evidence base. No attempt is made to re-derive clarify's consumption from transcripts beyond what the recorded metrics already hold.
- Over-budget remains observability, never failure: nothing in this feature makes reaching the declared budget fail a run.
- Adopting repositories that set no configuration must be unaffected; any new knob is opt-in with today's behaviour as its default.
- The clarify stage's premium model tier is correct for the work and is not revisited here (constitution II).
- Clarify's own workload — how many questions it asks, how it folds answers — is treated as given unless FR-001 resolves toward reducing consumption; this spec does not presume clarify is doing unnecessary work.
- The currently open `pipeline-defect` issue for this trend is resolved by whatever FR-001 resolves to, including the case where the resolution is an explicit acceptance.

## Out of Scope

- Changing how bands, signal ids, fingerprints or dedup outcomes are computed.
- Changing model tiers for any stage.
- Changing the `token-budget-warning` class or any other supervision collector.
- Making an over-budget run fail, or removing the over-budget report.
- Re-architecting how turns are counted.
