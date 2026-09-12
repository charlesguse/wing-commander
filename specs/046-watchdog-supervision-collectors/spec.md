# Feature Specification: Deterministic Watchdog Collectors for the Supervision Gap

**Feature Branch**: `046-watchdog-supervision-collectors`

**Created**: 2026-09-12

**Status**: Draft

**Input**: User description (lifecycle issue #274): "An adopting repository ran nine features through the pipeline at `@main` over two rounds (2026-08-25 → 27) with a maintainer-side supervising session watching the whole flight. Comparing what that supervision caught against what the watchdog inspects revealed a clean gap: the watchdog is a per-run mechanical-failure triager, while everything the supervision actually caught was cross-run or claim-vs-evidence — and every one of those catches was mechanizable with deterministic reads over data the pipeline already produces. Today's five collectors (denied-tool, branch-drift/lost-progress, spec-meta stage-mismatch, step-summary sentinels, annotations) all answer 'did this run mechanically misbehave?' None answer: (1) is a budget trend developing — implement cycle-1 turns grew monotonically with codebase size, 160/180 → 197/180 → 226/180 across three consecutive specs against an advisory budget of 180 and an enforced ceiling of 450, with each run posting its own observability note but nothing surfacing the trend or the shrinking headroom to the hard stop; (2) did the stage's self-report match reality — final-PR narratives drifted from ground truth in every round-2 feature (a claimed task count that was off by one against the actual, a 'new test cases' figure that was really a line count, a commit count off by two, a suite-wide test total stated nowhere), all cosmetic, but the maintainer only knew that by re-deriving every number locally; (3) is the cost accounting complete and well-formed — plan and tasks post no cost line at all, so every per-issue total is a floor missing two agent runs, and the lines that are posted had the #272 formatting defects; (4) are two in-flight specs about to collide — sequential spec numbering derives from `specs/` on main, so parallel intakes can mint the same number, avoided today purely by convention. Proposal: four deterministic collectors, no new agent surface — `collect-turn-budget`, `collect-cost-report`, `collect-final-pr-claims`, `collect-spec-collision` — each emitting normalized signals into the existing `signals.json` with the existing collector-outcome and untrusted-content discipline, flowing through the existing diagnose → evidence-validity gate → fingerprint → dedup → issue path unchanged. Explicitly out of scope: the parts of supervision that are judgment rather than verification — answering clarification questionnaires, merge decisions, routing, and product taste; the FR-014 pure-reporter surface is the right boundary. Suggested priority if sliced: 1 and 2 first, then 3, then 4."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A developing turn-budget trend is visible before it becomes a hard stop (Priority: P1)

An agent stage's turn usage creeps up run after run as the repository it works on grows. Each individual run finishes successfully and posts its own "used its full intended turn budget" note, so nothing ever looks broken — but the distance between what the stage actually uses and the ceiling that would kill it mid-work keeps shrinking. A maintainer wants to learn this from one accumulating report while there is still headroom, not from the first run that hits the ceiling and loses its work.

**Why this priority**: This is the only observed class where the cost of learning late is real work destroyed rather than a cosmetic blemish, and the data needed to see it is already durable in the metrics record. It is also the class the existing per-run collectors are structurally unable to see: every input is fine in isolation, and only the sequence is alarming.

**Independent Test**: Seed a history of metrics records for one stage whose counted turns climb across consecutive runs against a fixed budget and ceiling, run the watchdog against the last of those runs, and confirm one finding is reported that names the stage, the climb, and the remaining headroom to the enforced ceiling — and that a second, later run in the same climb attaches its evidence to that same finding rather than opening another.

**Acceptance Scenarios**:

1. **Given** a run whose counted turns reached or exceeded its intended budget, **When** the watchdog inspects it, **Then** a signal is emitted carrying the counted turns, the intended budget, the enforced ceiling, and the consumed fraction of that ceiling.
2. **Given** the recent history for a stage shows consecutive runs at or over budget, **When** the watchdog inspects the latest of them, **Then** a cross-run signal is emitted describing the trend, not just the latest run.
3. **Given** a trend has already produced a filed finding, **When** a later run extends the same trend within the same severity band, **Then** the new evidence is attached to the existing finding and no second finding is opened.
4. **Given** a run that finished comfortably under its intended budget, **When** the watchdog inspects it, **Then** no turn-budget signal of any kind is emitted.
5. **Given** a stage whose metrics record marks turn data unavailable, **When** the watchdog inspects it, **Then** no turn-budget signal is emitted and the collector still reports a successful outcome.

---

### User Story 2 - Every cost-bearing stage's spend actually reaches the lifecycle issue, correctly formatted (Priority: P1)

A requester adds up the cost lines on a lifecycle issue to learn what a feature cost. Today that total is silently a floor: some stages post no cost line at all, and some posted lines have carried formatting defects that make the figure hard to read. The pipeline already knows, per stage run, whether a cost figure was available — nobody cross-checks that knowledge against what the lifecycle issue actually received.

**Why this priority**: A number a reader believes is a total but that is actually an unmarked floor is worse than no number, and the check is a single comparison between two artifacts the pipeline already produces. It is also the class with the highest observed frequency — the gap was systematic, present on every feature, not intermittent.

**Independent Test**: Run a cost-bearing stage whose metrics record reports a cost as available but whose lifecycle comment carries no parseable cost figure, and confirm the watchdog reports a missing-cost-line finding naming the stage and the run; then repeat with a cost line present but malformed and confirm a distinct malformed-cost-line finding.

**Acceptance Scenarios**:

1. **Given** a stage run whose metrics record says a cost figure was available, **When** the lifecycle issue received no cost figure attributable to that run, **Then** a missing-cost-line signal is emitted naming the stage and the run.
2. **Given** a stage run whose lifecycle comment carries a cost figure, **When** that figure does not match the expected currency-and-two-decimals presentation, **Then** a malformed-cost-line signal is emitted carrying the observed text.
3. **Given** a stage run whose metrics record says no cost figure was available, **When** the lifecycle issue carries no cost line for it, **Then** no signal is emitted — an absent line for an unavailable cost is correct behavior.
4. **Given** a cost line that is present and well-formed, **When** the watchdog inspects the run, **Then** no signal is emitted regardless of the figure's magnitude.

---

### User Story 3 - The final PR's narrative is checked against the repository it describes (Priority: P2)

The final pull request is the artifact a reviewer reads instead of re-deriving the work themselves — it states how many tasks completed, how many commits landed, how many tests exist. When those numbers drift from what the branch actually contains, the only defense today is a maintainer re-running everything locally, which is precisely the work the final PR exists to save.

**Why this priority**: Every observed instance was cosmetic, so it ranks below the classes that cost work or money — but it erodes the trust the whole final-review gate rests on, and each of the three claim shapes has a deterministic ground truth already sitting in the branch.

**Independent Test**: Finalize a feature whose PR body states a task count, a commit count, and a test count that each disagree with the branch's checked task boxes, its commit range, and its test-run summary, and confirm the watchdog reports one finding per mismatched claim carrying the claimed value, the actual value, and where the actual value came from.

**Acceptance Scenarios**:

1. **Given** a final PR body claiming a number of completed tasks, **When** that number disagrees with the checked task boxes on the branch, **Then** a narrative-drift signal is emitted carrying the claimed value, the actual value, and the source of the actual value.
2. **Given** a final PR body claiming a commit count, **When** that number disagrees with the commits between the PR's base and head, **Then** a narrative-drift signal is emitted for that claim.
3. **Given** a final PR body claiming a test count, **When** that number disagrees with the test-run summary the run itself produced, **Then** a narrative-drift signal is emitted for that claim.
4. **Given** a final PR body that states a claim in a shape the check cannot parse, **When** the watchdog inspects the run, **Then** no signal is emitted for that claim — an unparseable claim is an absence of evidence, never a finding.
5. **Given** a final PR body whose three claims all match ground truth, **When** the watchdog inspects the run, **Then** no narrative-drift signal is emitted.

---

### User Story 4 - Two in-flight specs claiming the same number are detected, not discovered later (Priority: P3)

Spec numbers are minted by looking at what already exists on the main branch, so two intakes running before either has merged can mint the same number. Today the only thing preventing that is a maintainer's habit of starting the next feature only after the previous spec has merged — an undocumented serialization convention with nothing behind it.

**Why this priority**: It has not yet bitten, and the convention has held — but the failure mode is two features quietly writing into each other's directory, which is expensive to untangle, and the detection is a comparison of the spec paths on open pull requests.

**Independent Test**: With one spec pull request open, run an intake that produces a second spec directory carrying the same number, and confirm the watchdog reports a collision finding naming both claimants.

**Acceptance Scenarios**:

1. **Given** two open spec pull requests whose spec directories carry the same number, **When** the watchdog inspects the later intake run, **Then** a collision signal is emitted naming both pull requests and the contested number.
2. **Given** an open spec pull request whose number is already taken by a spec directory on the main branch, **When** the watchdog inspects that intake run, **Then** a collision signal is emitted naming the pull request and the existing directory.
3. **Given** open spec pull requests that all carry distinct numbers, **When** the watchdog inspects an intake run, **Then** no collision signal is emitted.
4. **Given** a collision that has already been reported, **When** the same two claimants are observed again on a later run, **Then** the existing finding accumulates the new evidence rather than a second finding being opened.

---

### Edge Cases

- What happens when the durable history a cross-run check reads is absent, empty, or carries records whose schema version the check does not know? The check emits no signal for the cross-run condition and reports its own outcome honestly; an unreadable history is "could not inspect," never "no trend."
- What happens when a stage run posts no lifecycle comment at all — is that a missing cost line, or nothing to inspect? It is a missing cost line whenever the metrics record says a cost figure was available for that run: the reader's total is short either way.
- What happens when the inspected run was skipped or cancelled, or when the artifact a check reads belongs to a different run? No signal is emitted — the existing attribution invariant applies to these checks exactly as it does to the existing ones.
- What happens when a final PR body contains text that looks like an instruction to an agent? It is treated as untrusted data to be compared against ground truth, never as an instruction; the same framing already applied to every inspected artifact applies here.
- What happens when the maintainer raises a stage's intended budget after a trend finding was filed? The trend's severity band is computed from the run's own budget and ceiling, so the new runs are classified against the new numbers.
- What happens when two collision claimants are the same pull request observed twice (a re-inspection of one run)? A pull request never collides with itself; only distinct claimants on the same number constitute a collision.
- What happens when a collector encounters a condition another part of the pipeline has already reported for this run? The existing coexistence rule applies — the watchdog must not double-report it.

## Requirements *(mandatory)*

### Shared collector obligations

- **FR-001**: The feature MUST add exactly four new deterministic collectors — a turn-budget check, a cost-report check, a final-PR-claims check, and a spec-number-collision check — to the watchdog's existing collect job, and MUST NOT introduce any new agent invocation: the number of agent steps in a watchdog run MUST remain exactly one (the existing `diagnose` step).
- **FR-002**: Each new collector MUST emit its findings as normalized signals into the existing signals structure the diagnose step consumes, and MUST record its own collector outcome (`ok`/`failed`) in the same way the existing collectors do, so that a collector that could not run is distinguishable from a collector that ran and found nothing.
- **FR-003**: Every signal each new collector emits MUST flow through the existing downstream path — diagnose, the evidence-validity gate, fingerprinting, dedup, and the issue-filing/lifecycle-report step — without that path being modified to special-case the new signals.
- **FR-004**: Each new collector MUST satisfy the existing attribution invariant: it MUST emit a signal about a run only when the inspected run both executed (its conclusion is not skipped or cancelled) and owned the artifact whose condition the signal describes.
- **FR-005**: Each new collector MUST own its own false-positive duty: a condition the collector cannot substantiate from the artifacts it read MUST be suppressed at the collector rather than emitted for the diagnose step to adjudicate. In particular, an input that is absent, empty, unparseable, or marked unavailable MUST produce no signal.
- **FR-006**: Every artifact a new collector reads — pull request bodies, issue comments, persisted records, task files, job output — MUST be treated as untrusted data and never as instructions, matching the framing the existing collectors use.
- **FR-007**: Each new collector MUST tolerate "this source produced nothing for this run" as a successful outcome, and MUST NOT fail the collect job when the source it reads is empty or does not apply to the inspected stage.
- **FR-008**: Each new collector MUST run only on the stage runs whose conditions it can meaningfully evaluate — the turn-budget check on runs of stages that declare a turn budget, the cost-report check on cost-bearing stage runs, the final-PR-claims check on finalize runs, and the collision check on intake completions — and MUST emit no signal on stage runs outside its scope.
- **FR-009**: The facts each new collector emits MUST be sufficient, on their own, for a reader of the filed finding to confirm the condition without re-deriving it from raw artifacts: each signal MUST carry the observed value, the expected or comparison value where one exists, and the identity of the run, stage, or artifact the values came from.

### Turn-budget trend detection

- **FR-010**: The turn-budget check MUST emit a per-run signal when a run's counted turns reached or exceeded that run's intended turn budget, carrying the counted turns, the intended budget, the enforced ceiling, and the fraction of the enforced ceiling consumed. [NEEDS CLARIFICATION: each stage already posts its own "used its full intended turn budget" observability note for exactly this condition, and the watchdog is required not to double-report a condition existing automation has already reported — should a per-run over-budget signal be able to produce a filed finding on its own, or should it serve only as evidence attached to a cross-run trend finding?]
- **FR-011**: The turn-budget check MUST emit a cross-run signal when the recent history for the same stage shows either a run of consecutive at-or-over-budget runs, or a climb in consumed turns that crosses a configured fraction of the enforced ceiling. Both the history window and the two thresholds MUST be configurable without a code change.
- **FR-012**: A cross-run trend signal MUST be identified such that successive runs extending the same trend at the same severity band map to a single accumulating finding rather than one finding per run, and a trend that escalates into a different severity band MUST be distinguishable from the one below it.
- **FR-013**: The turn-budget check MUST express the relationship between the advisory intended budget and the enforced ceiling as a monitored, reported quantity — the remaining headroom — rather than leaving the gap between them implicit.
- **FR-014**: The turn-budget check MUST read its per-run values from the inspected run's own durable metrics record where one exists, falling back to the run's execution-output artifact, and MUST emit no turn-budget signal when neither source yields turn values marked available.
- **FR-015**: The specification MUST state what happens when a maintainer has closed a filed turn-budget trend finding and a later run extends that same trend. [NEEDS CLARIFICATION: should the existing dedup behavior apply unchanged — reopen the closed finding and attach the fresh evidence, which for a persistent trend means reopening on every subsequent run — or should a maintainer's closure be treated as an acceptance that suppresses that stage's trend findings until the trend crosses into a higher severity band?]

### Cost-report completeness

- **FR-016**: The cost-report check MUST compare, per cost-bearing stage run, whether the run's metrics record marks a cost figure as available against whether a cost figure attributable to that run reached the lifecycle issue.
- **FR-017**: The check MUST emit a distinct signal for each of two conditions: a cost figure that was available but that the lifecycle issue never received, and a cost figure that reached the lifecycle issue in a form that does not match the expected presentation.
- **FR-018**: The expected presentation MUST be defined as a single explicit, machine-checkable form — a currency-marked amount rounded to a fixed number of decimal places — and the malformed-line signal MUST carry the observed text so the defect is legible from the finding alone.
- **FR-019**: The check MUST emit no signal when the metrics record marks the cost figure unavailable, when the stage is not cost-bearing, or when a well-formed cost figure is present, regardless of the amount.
- **FR-020**: The check's purpose MUST be stated as catching recurrence and regression of the formatting defects recorded in issue #272 and of the systematic missing-line gap, not as the fix for the currently known instances; it MUST NOT be specified in terms that pass only because those particular instances were repaired.

### Final-PR claim verification

- **FR-021**: The final-PR-claims check MUST parse the final pull request body for three claim shapes — a completed-task count, a commit count, and a test count — and MUST compare each parsed claim against a deterministically derived ground truth: the checked task boxes in the feature's task file, the commits between the pull request's base and head, and the test-run summary the run itself produced.
- **FR-022**: Each mismatch MUST produce its own signal carrying the claimed value, the actual value, and the source the actual value was derived from.
- **FR-023**: A claim the check cannot parse MUST produce no signal — a claim shape that does not match is an absence of evidence, never a finding — and the check MUST NOT treat an unparseable body as a mismatch.
- **FR-024**: A claim that matches its ground truth MUST produce no signal, and a pull request whose three claims all match MUST produce no output from this check.
- **FR-025**: Findings derived from claim mismatches MUST be reported at a severity that reflects their observed cosmetic nature. [NEEDS CLARIFICATION: should a claim mismatch open a pipeline-defect issue on the same path as every other finding — where it counts against the watchdog's ≥70% precision window and competes for maintainer attention with work-destroying defects — or be reported only on the lifecycle issue, or filed but excluded from the precision measurement?]

### Spec-number collision detection

- **FR-026**: The collision check MUST detect, on an intake completion, when two distinct open spec pull requests claim the same spec number, and when an open spec pull request claims a number already taken by a spec directory on the main branch.
- **FR-027**: A collision signal MUST name both claimants and the contested number, so the finding identifies what to renumber without further investigation.
- **FR-028**: The check MUST NOT report a pull request as colliding with itself, and MUST emit no signal when every open spec pull request carries a distinct number.
- **FR-029**: A collision observed again on a later run MUST map to the already-filed finding for those claimants rather than producing a second finding.

### Scope boundaries

- **FR-030**: This feature MUST NOT extend the watchdog's authority: it adds evidence only, and the watchdog remains a pure reporter whose remediation surface is detection, dedup, and issue filing. No new collector may produce a fix, a pull request, or any write beyond the existing reporting path.
- **FR-031**: The judgment aspects of maintainer supervision — answering clarification questionnaires, merge decisions, routing a change between the pipeline and a direct commit, and product taste — MUST remain out of scope and MUST NOT be mechanized by this feature.
- **FR-032**: This feature MUST NOT change the behavior of the five existing collectors, the diagnose step's model, prompt, tool allowlist, or output schema, the evidence-validity gate, the dedup rules, the self-dispatch cap, or the pause switch.
- **FR-033**: Fixing the currently known instances of the conditions these collectors detect — the stages that post no cost line, and the formatting defects of issue #272 — is out of scope for this feature; the collectors detect the conditions, and repairs are separate work.

### Key Entities

- **Turn-budget observation**: one stage run's counted turns together with the intended budget and enforced ceiling that run declared, plus the derived headroom to the ceiling. Ordered by run within a stage to form the history a trend is computed over.
- **Budget trend**: a bounded window of consecutive turn-budget observations for one stage, classified into a severity band by how much of the enforced ceiling the window's runs consume. The unit a trend finding accumulates evidence into.
- **Cost-line claim**: the pairing of a stage run's recorded cost availability with the cost figure, if any, that reached the lifecycle issue for that run — the two sides the completeness check compares.
- **Narrative claim**: one assertion parsed from a final pull request body (completed tasks, commits, or tests), carrying the claimed value, the value derived from the branch, and the derivation source.
- **Spec-number claim**: a spec number together with the claimant that asserts it — an open spec pull request or a directory on the main branch. Two distinct claimants on one number constitute a collision.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For each of the four new detection classes, a labeled corpus entry exists describing a run known to exhibit that condition, and the watchdog produces the expected finding for every entry and no finding for the paired negative entry.
- **SC-002**: Every failure branch each new collector ships — condition detected, condition absent, input unavailable, input unparseable, run unattributable — is exercised by a checked-in fixture, so no branch is proven only by a manual demonstration.
- **SC-003**: Adding the four collectors changes the number of agent invocations per watchdog run by zero; the marginal cost of the feature is measured in runner seconds, not in agent turns.
- **SC-004**: A turn-budget trend spanning multiple consecutive runs produces exactly one filed finding that accumulates evidence, not one finding per run — verifiable by running the watchdog against each run of a seeded climb and counting filed findings.
- **SC-005**: A maintainer reading a filed finding from any of the four classes can state the observed value, the expected value, and where the expected value came from without opening any artifact the watchdog read.
- **SC-006**: Across the corpus of runs that exhibit none of the four conditions, the new collectors emit zero signals — they add no findings to runs that were healthy before this feature existed.
- **SC-007**: The watchdog's existing precision target over its most recent distinct filed findings is still met after the new classes begin filing, measured over the same window definition in use today.

## Assumptions

- The durable metrics record already carries, per stage run, the counted turns, the intended budget, the enforced ceiling, and whether a cost figure was available, and the persisted history of those records is readable by the watchdog at inspection time. This feature reads that data; it does not add fields to it. Should a field it needs be absent, the affected check degrades to "no signal" rather than the feature requiring a schema change.
- An adopting repository that has not enabled durable metrics persistence has no cross-run history to read. The cross-run half of the turn-budget check reports that it could not inspect, and the per-run half continues to work from the run's own artifact.
- Default thresholds are chosen so the trend check is quiet by default and configurable per adopter: a history window of the most recent ten runs for the stage, three consecutive at-or-over-budget runs as the consecutive trigger, and sixty percent of the enforced ceiling as the climb trigger. These are starting values a maintainer is expected to tune, not derived constants.
- The three claim shapes the final-PR check parses are the ones the finalize stage reliably emits today. A future change to the finalize narrative's wording is expected to make claims unparseable — which degrades to silence, per FR-023 — rather than to produce false findings.
- Cost lines are attributed to a stage run through the lifecycle comment that run posted. A stage that posts no comment at all for a run is treated as having posted no cost line for it.
- Spec numbers are compared as the numeric prefix of a spec directory path. A spec pull request is identified by the branch-prefix convention already configured for the repository, so an adopter that has renamed its prefixes is covered by its own configuration rather than by a hardcoded pattern.
- The watchdog's existing coexistence rule is the mechanism by which these collectors avoid duplicating reports that other automation already posted; this feature relies on that rule rather than restating it per collector.
- The evidence cited in the originating issue comes from an adopting repository's dogfooding rounds. Corpus entries for this repository are expected to be constructed as fixtures rather than harvested from that repository's history.
