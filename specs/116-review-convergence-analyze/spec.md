# Feature Specification: Review Loops That Notice They Aren't Converging, and an Analyze Check Before Folded Review Tasks Reach Implement

**Feature Branch**: `116-review-convergence-analyze`

**Created**: 2026-10-17

**Status**: Draft

**Lifecycle issue**: #994 (umbrella over parked #833; #833 stays parked and its items 1–2 and their open clarify questions are taken in here)

**Input**: User description: "Review loops that notice they aren't converging, and an analyze check before folded review tasks reach implement. The pipeline's review loops stop for two reasons only: a clean round, or a spent budget. Nothing in either loop asks whether it is converging, nothing checks a folded review task against the spec before implement builds it, and the pipeline never runs `/speckit-analyze`. Proposal: (1) an analyze check at fold time, (2) convergence signals on every review round computed by code with an early `not-converging` stop, (3, optional) one home for the reviewer's judgement procedure. Owner decision 2026-10-17: promote as the umbrella over #833; thresholds and line-level attribution are settled by the merged `review-until-clean` skill (#998); when analyze objects, part 3, and the analyze step's model tier stay open."

## Clarifications

### Session 2026-10-17

- Q: When analyze objects to a fold task without a constitution conflict, hold, dispatch anyway, or hold only on a constitution conflict? → A: (c) Hold the dispatch only on a constitution conflict; for any other inconsistency or duplication naming a fold task, dispatch with the analyze report linked (FR-012).
- Q: Which model tier should the fold-time consistency check run on? → A: Sonnet — `claude-sonnet-5-5`, the tier plan and tasks use (constitution II) (FR-016).
- Q: Is part 3 (one shared file for the reviewer's judgement procedure) in scope? → A: (a) Out of scope for now, revisited once parts 1 and 2 land; the published contract (constitution VII) is untouched (FR-020, Story 5).

## Context

The pipeline runs two automated review loops:

- the **lifecycle review gate** (spec 062), which reviews a lifecycle's final implementation PR, folds in-scope findings back into the lifecycle as tasks, and re-reviews; and
- the **board loop** (constitution X), which reviews its own fix PRs and fixes the findings in the same PR.

Both allow 5 rounds. Today each loop stops for only two reasons: a clean round, or a spent budget. Three failure modes follow:

1. **The loop feeds on its own fixes.** On #969, 8 of 10 findings across four review passes sat in the PR's own new code; #954 took 15 rounds and grew into a full shell parser. Every round found something real, so every round looked like progress. The signal that was missed was *where* the findings sat: in code the loop itself had written.
2. **A recurring finding reads as a pass.** In the lifecycle review gate, a finding whose fingerprint an earlier round already folded is dropped as already handled. If nothing else remains, the round resolves `clean` and posts `success`, although the earlier fix did not hold (#833 item 2).
3. **A folded task can contradict the spec.** implement ⟲ converge builds whatever tasks.md says. A folded review task that conflicts with a functional requirement, an earlier fold, or the constitution is built anyway; converge then flags the code as contradicting the spec, and the next review sees the other side. Only the owner can settle such a conflict, and nothing hands it to them before a cycle is spent. (This is reasoning about the mechanism, not an observed failure.)

The local `review-until-clean` skill (merged in #998, on main at `.claude/skills/review-until-clean/`) already applies a convergence check by hand, with its arithmetic in `scripts/thrash_signals.py`. Its rules are the project's precedent for a review loop's stop rule.

**Layers** (constitution VII): the fold composites (`wing-commander-fold-commit`, `wing-commander-fold-dispatch`) and `pr-conversation` belong to the **published contract**; `lifecycle-review-gate.yml`, `board-loop.yml` and the `review-until-clean` skill belong to the **consuming instrument**. Each requirement below names the layer it touches.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A recurring finding is never reported as a clean round (Priority: P1)

As the owner relying on the lifecycle review gate's `success` status, I need a round that re-raises a finding whose fix was already folded or pushed to be reported as a recurrence, not silently dropped, so that a green status means the earlier fix actually held.

**Why this priority**: This is the one case where the gate today reports a pass it did not earn (constitution VIII). It is the smallest, most self-contained change and removes a false green.

**Independent Test**: Replay a review round whose only in-scope finding carries the fingerprint of a finding an earlier round already folded. The round must not resolve `clean`, must not post `success`, and must name the recurring finding.

**Acceptance Scenarios**:

1. **Given** round 2 folded finding F and implement pushed a fix, **When** round 3 raises a finding with F's fingerprint and nothing else, **Then** the round is recorded as not clean, the recurrence is named on the lifecycle issue, and the PR's review status is not `success`.
2. **Given** round 3 raises only findings whose fingerprints no earlier round folded or fixed, **When** the round is partitioned, **Then** no recurrence is reported and behaviour is unchanged from today.
3. **Given** a recurrence is detected on round 2 (before the early-stop window), **When** the round resolves, **Then** the finding is treated as open (re-folded or carried) rather than dropped, and the loop continues within its budget.

---

### User Story 2 - The review loops stop early when they stop converging (Priority: P1)

As the owner, I want both automated review loops to compute convergence signals on every round and, from round 3 on, stop and hand the PR to me when the loop is feeding on its own fixes, instead of spending the full budget on findings in code the loop itself wrote.

**Why this priority**: This is the failure that cost #954 15 rounds and #969 four passes. It applies to both loops and is where most wasted cycles go.

**Independent Test**: Feed recorded round histories (heads per round, findings with file and line, counts per round) to the signal computation and assert the computed signals and the stop/continue decision match the rules below; then run one loop against a fixture history that trips each rule and assert it posts a `not-converging` hand-off.

**Acceptance Scenarios**:

1. **Given** a loop at round 3 whose in-scope finding count did not fall from round 2, **When** the round is evaluated, **Then** the loop stops with stall reason `not-converging` and posts the hand-off.
2. **Given** a loop at round 3 where at least half of the round's in-scope findings sit on lines written after round 1's head by the loop's own fold/implement or fixup commits, **When** the round is evaluated, **Then** the loop stops with `not-converging`.
3. **Given** a loop at round 3 in which a finding recurs (Story 1), **When** the round is evaluated, **Then** the loop stops with `not-converging`.
4. **Given** a loop at round 3 in which the two most recent rounds each rewrote lines an earlier round wrote, **When** the round is evaluated, **Then** the loop stops with `not-converging`.
5. **Given** a loop at round 3 whose PR diff against its base has grown by more than half since round 1's head, **When** the round is evaluated, **Then** the loop stops with `not-converging`.
6. **Given** a loop at round 2 in which any of the above holds, **When** the round is evaluated, **Then** the signals are recorded but the loop does not stop early.
7. **Given** a loop at round 4 whose count fell, whose findings are mostly on the PR's original lines, and with no recurrence, churn streak or growth trip, **When** the round is evaluated, **Then** the loop continues, and the 5-round budget still applies unchanged.
8. **Given** the loop stops with `not-converging`, **When** the hand-off is posted, **Then** it states which signals tripped, each signal's value, the open in-scope findings, and the same human hand-off the budget exhaustion uses today (the PR is left open and unmerged).

---

### User Story 3 - A folded task that contradicts the spec reaches the owner before implement builds it (Priority: P2)

As the owner, when a review fold appends tasks to tasks.md, I want those new tasks checked against the spec, the plan, earlier fold sections and the constitution before implement is dispatched, so that a conflict only I can settle is put to me before a cycle is spent building one side of it.

**Why this priority**: The failure is reasoned rather than observed, and it adds a new agent step; it is valuable but less urgent than removing a false green and the observed thrash.

**Independent Test**: Fold a review task that conflicts with the constitution, and separately one that contradicts a functional requirement in a fixture spec without a constitution conflict. The analyze check must run between the fold commit and the implement dispatch and return a structured finding naming the fold task and the conflicting location; deterministic code must hold the first and dispatch the second with the report linked.

**Acceptance Scenarios**:

1. **Given** a fold appends a section to tasks.md, **When** the fold commit completes, **Then** a read-only consistency check runs over spec.md, plan.md and tasks.md, scoped to the new fold section, before implement is dispatched.
2. **Given** the check returns a finding that conflicts with the constitution, **When** deterministic code evaluates the result, **Then** the implement dispatch is held and the conflict is posted on the lifecycle issue as an owner question with the options: amend the spec (the review is right), drop the fold task (the spec is right), or proceed anyway.
3. **Given** the check returns an inconsistency or duplication finding naming a fold task (not a constitution conflict), **When** deterministic code evaluates the result, **Then** the dispatch is not held: implement is dispatched and the analyze report, including that finding, is linked on the lifecycle issue (FR-012).
4. **Given** the check returns no findings, or only findings outside the hold policy, **When** deterministic code evaluates the result, **Then** implement is dispatched as today, with the report linked on the lifecycle issue.
5. **Given** the fold came from a human review through pr-conversation's `act` path, **When** the fold commits, **Then** the same check runs as for a fold from the lifecycle review gate's `disposition` path.
6. **Given** the owner answers a held conflict, **When** the answer is "proceed anyway" or "drop the fold task", **Then** the hold is released and implement is dispatched against the resulting tasks.md; **When** the answer is "amend the spec", **Then** the lifecycle waits for the spec amendment and is dispatched afterward.

---

### User Story 4 - One home for the convergence arithmetic (Priority: P2)

As a maintainer, I want the convergence-signal arithmetic to live in one module that the workflows and the local `review-until-clean` skill both call, so that a fix to the arithmetic lands once and the local and automated loops can never disagree.

**Why this priority**: CLAUDE.md's "shared logic has exactly one home" rule; without it the automated loops would carry a second copy of `thrash_signals.py`'s math.

**Independent Test**: Run the local skill's thrash check and the automated loops' signal computation over the same recorded history and assert identical signals; a gate fails if a second copy of the arithmetic appears.

**Acceptance Scenarios**:

1. **Given** the shared module exists, **When** the `review-until-clean` skill runs its thrash check, **Then** it calls the shared module rather than carrying its own arithmetic.
2. **Given** a workflow or skill reintroduces its own copy of the attribution/churn/growth arithmetic, **When** the gate suite runs, **Then** a gate fails naming the copy.

---

### User Story 5 - One home for the reviewer's judgement procedure (Priority: P3, deferred — out of scope)

As a maintainer, I want the procedure for verifying a finding, refuting it against an FR, and carrying a "dismissed" list between rounds to live in one file read by both the pipeline reviewers and local sessions, instead of inline in each reviewer prompt.

**Why this priority**: Optional in the request. The owner placed it out of scope for this feature (2026-10-17), to be revisited once Stories 1–4 land — see FR-020. It is recorded here so the revisit has its statement of intent.

**Independent Test**: None for this feature; no reviewer prompt changes for it.

**Acceptance Scenarios**:

1. **Given** this feature has shipped, **When** any automated reviewer runs, **Then** its prompt and the published contract are unchanged by Story 5.

---

### Edge Cases

- **Round 1 has no earlier head.** Self-inflicted share, churn and growth are defined relative to round 1's head; on round 1 they are zero by definition and recurrence cannot occur.
- **A finding without a line number** (a reviewer omits `line`, or reports a whole-file concern). It is counted in the trend but not attributable; it does not count toward the self-inflicted share's numerator or denominator, and the hand-off reports how many findings were unattributable.
- **A finding's line does not exist at the reviewed head** (out of range, or the file was deleted). Deterministic code rejects the line as invalid, treats the finding as unattributable, and records the rejection; it never guesses a nearby line.
- **Main merged into the PR between rounds.** Lines introduced by a merge from the base branch are not loop-authored and must not count as self-inflicted or as churn.
- **A round with zero in-scope findings.** That round is clean and the loop ends as today; no early-stop rule applies.
- **A recurrence whose fingerprint matches a finding a human dismissed** (on the dismissed list), not one that was folded or fixed. It is not a recurrence: only a finding whose fix was folded or pushed earlier counts.
- **The analyze check itself fails** (the agent run errors, times out, or returns output that does not match the schema). The fold is not silently dispatched as if the check passed; the failure is named on the lifecycle issue and handled per FR-013.
- **A fold section with no tasks** (every finding was out of scope). The analyze check is skipped and dispatch proceeds as today.
- **The lifecycle review gate's kill switch is set.** The convergence signals and the analyze check do not run, because the gate does not run.
- **Both a `not-converging` trip and budget exhaustion fall on round 5.** The hand-off names the budget as the stop reason and still lists the tripped signals.

## Requirements *(mandatory)*

### Functional Requirements

**Recurrence (lifecycle review gate — consuming instrument; board loop — consuming instrument)**

- **FR-001**: Each automated review loop MUST keep, per PR, a record of every in-scope finding it has folded (lifecycle gate) or fixed (board loop), keyed by the finding's fingerprint and the round that resolved it.
- **FR-002**: A round's partition step MUST classify an in-scope finding whose fingerprint matches an earlier folded or fixed finding as a **recurrence**, and MUST NOT drop it.
- **FR-003**: A round containing a recurrence MUST NOT resolve `clean` and MUST NOT post a `success` review status; the recurrence MUST be named on the lifecycle issue (lifecycle gate) or the PR (board loop).

**Convergence signals (both loops — consuming instrument)**

- **FR-004**: On every review round, deterministic code (constitution IX) MUST compute and record these signals from the round's heads, findings and counts alone:
  - **trend**: in-scope finding count per round;
  - **self-inflicted share**: the fraction of this round's attributable in-scope findings on lines written after round 1's head by the loop's own commits (fold/implement commits for the lifecycle gate, fixup commits for the board loop);
  - **churn**: whether this round's commits rewrote lines an earlier round's commits wrote;
  - **growth**: the PR's diff size against its base at each round's head, relative to round 1's head;
  - **recurrence**: per FR-002.
- **FR-005**: Reviewer findings MUST carry a `line` alongside the file path. Deterministic code MUST check that the line exists in that file at the reviewed head; a finding with a missing or non-existent line is recorded as unattributable and excluded from the self-inflicted share.
- **FR-006**: From round 3 onward, a loop MUST stop early, with the new stall reason `not-converging`, when any of these holds (the rules of the merged `review-until-clean` skill, #998):
  - the in-scope count did not fall from the previous round;
  - at least half of this round's attributable in-scope findings are self-inflicted;
  - a finding recurs;
  - the two most recent rounds each churned an earlier round's lines;
  - the diff has grown by more than half since round 1's head.
- **FR-007**: The early stop MUST apply to both the lifecycle review gate and the board loop's review rounds.
- **FR-008**: A `not-converging` stop MUST perform the same human hand-off the round budget's exhaustion performs today (PR left open and unmerged, the existing stall labelling and re-eligibility rule), and the hand-off MUST state which signals tripped, each signal's value per round, the number of unattributable findings, and the open in-scope findings.
- **FR-009**: The 5-round budget (`LIFECYCLE_REVIEW_ROUND_BUDGET`, `BOARD_LOOP_ROUND_BUDGET`) MUST remain unchanged and MUST still stop the loop whatever the signals say.
- **FR-010**: The thresholds in FR-006 MUST be defined in exactly one place shared by both loops and the local skill; changing a threshold MUST be a one-place edit.

**Analyze check at fold time (fold composites — published contract)**

- **FR-011**: After `wing-commander-fold-commit` appends a fold section to tasks.md and before `wing-commander-fold-dispatch` starts implement, the pipeline MUST run the vendored, read-only `/speckit-analyze` over spec.md, plan.md and tasks.md, scoped by its arguments to the new fold section: check the new tasks against the spec, the plan, earlier fold sections, and the constitution. The single insertion point MUST serve both fold callers (pr-conversation's `act` and the lifecycle review gate's `disposition`), preserving spec 062 FR-017's single home for fold logic.
- **FR-012**: The analyze agent MUST return structured findings (severity, category, the fold task named, the location it conflicts with). Deterministic code — never the agent — MUST decide hold or dispatch from those findings. A constitution conflict MUST hold the dispatch. Only a constitution conflict holds the dispatch: an inconsistency or duplication finding naming a fold task that is not a constitution conflict MUST NOT hold it; implement is dispatched and the analyze report is linked on the lifecycle issue (FR-015).
- **FR-013**: When the analyze step itself fails (error, timeout, schema mismatch), the pipeline MUST name the failure on the lifecycle issue and MUST NOT present the dispatch as checked; it holds the dispatch for the owner, reusing the FR-014 question with the options "proceed anyway" and "retry the check".
- **FR-014**: On a hold, the pipeline MUST post the conflict on the lifecycle issue as an owner question with these options: the review is right, so amend the spec; the spec is right, so drop the fold task; or proceed anyway. The owner's answer MUST release the hold through an ordinary GitHub action (constitution III).
- **FR-015**: When dispatch proceeds, the analyze report MUST be linked on the lifecycle issue.
- **FR-016**: Any new input, output or secret the fold composites gain for this check MUST be added deliberately to the published contract (constitution VII), with the stage reading no ambient repository state; the analyze step MUST declare an explicit model and a bounded `--max-turns` (constitution II). The analyze step MUST run on `claude-sonnet-5-5`, the tier the plan and tasks stages use (constitution II).
- **FR-017**: The analyze step's agent MUST be read-only: it MUST NOT write files, commit, or push.

**Single homes (consuming instrument)**

- **FR-018**: The convergence-signal arithmetic (attribution, churn, growth) MUST live in one module under `.github/scripts/`, called by both review loops and by the `review-until-clean` skill's thrash check; the skill's `scripts/thrash_signals.py` is the starting point and MUST become a caller of (or be replaced by) that module.
- **FR-019**: A gate MUST fail when a second copy of the convergence-signal arithmetic appears in a workflow, composite or skill, in the manner of `verify-metrics-summary-record-emission.py`; every failure branch it ships MUST have a checked-in fixture (constitution VIII).
- **FR-020**: The shared reviewer-judgement procedure (Story 5) is out of scope for this feature, to be revisited once parts 1 and 2 (recurrence and convergence signals; the fold-time analyze check) have landed. No reviewer prompt is changed for it, and the published contract (constitution VII) is untouched by it.

### Key Entities

- **Review round record**: one per round per PR — the reviewed head SHA, the in-scope findings (fingerprint, file, line, attributable or not), the count, and the computed signals.
- **Resolved-finding ledger**: per PR, every finding fingerprint a round folded or fixed, with the resolving round; the input to recurrence.
- **Convergence signals**: trend, self-inflicted share, churn, growth, recurrence for a round, plus which FR-006 rules tripped.
- **`not-converging` stall reason**: a new stop reason beside the existing clean and budget-spent outcomes, carrying the tripped signals.
- **Analyze finding**: severity, category (constitution conflict, inconsistency, duplication, other), the fold task it names, and the conflicting location.
- **Fold hold**: the held dispatch, the owner question posted, and its resolution.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero review rounds whose only in-scope findings are recurrences resolve as clean or post a passing status, verified by a checked-in fixture that replays #833's case.
- **SC-002**: Replaying the recorded round histories of #954 and #969 through the signal computation stops each at or before round 3 with `not-converging`, rather than at a budget or an agreed stopping point.
- **SC-003**: On the same recorded history, the local skill and the automated loops compute identical signals (one module, one answer).
- **SC-004**: A fixture fold task that conflicts with the constitution is held before implement is dispatched in 100% of runs, and the owner question names both the task and the constitution principle it conflicts with.
- **SC-005**: Folds in which analyze finds no constitution conflict — including folds with inconsistency or duplication findings — reach implement with no added owner touchpoint beyond a linked report; a fixture fold task that contradicts a fixture spec's FR without a constitution conflict is dispatched with the report linked, the report naming both the task and the requirement.
- **SC-006**: No review loop exceeds the existing 5-round budget, and no lifecycle or fix PR is merged by a loop that stopped `not-converging`.
- **SC-007**: Every new gate's failure branches are exercised by a checked-in fixture, and the full local gate suite passes.

## Assumptions

- **Scope against #833** is settled by the owner (2026-10-17): this spec is the umbrella and takes in #833's items 1–2; #833 stays parked.
- **Thresholds** are settled by #998: from round 3, count did not fall, at least half self-inflicted, any recurrence, two consecutive churning rounds, or diff growth over half since round 1's head; budget stays 5. They apply to both loops.
- **Line numbers** are settled in shape by #998: findings gain a `line` checked at the reviewed head; per-file attribution is rejected because it would count a round's own edits in a large file as self-inflicted.
- "Lines written by the loop" means lines whose last author commit, by blame at the reviewed head, is one of the loop's own commits after round 1's head; merges from the base branch are excluded.
- The reviewer schemas for both loops can gain a `line` field without breaking an adopter-facing contract; where a reviewer schema is part of the published contract, the field is added as optional.
- `/speckit-analyze` is the vendored, pinned Spec Kit skill and is used as-is (no edits under `.claude/skills/speckit-*`); scoping to the fold section is achieved through its arguments.
- The local `review-until-clean` skill's merged rules (#998) stay the canonical statement of the thresholds' intent; this spec moves the arithmetic, not the rules' wording.

## Non-Goals

- Changing the 5-round budget.
- Implement's own zero-progress stop (#992).
- The board loop's fix routing.
- Automatically resolving a held conflict without the owner.
- A shared file for the reviewer's judgement procedure (part 3 / Story 5); deferred until parts 1–2 land (FR-020).
- Holding the dispatch on an analyze finding that is not a constitution conflict (FR-012).
