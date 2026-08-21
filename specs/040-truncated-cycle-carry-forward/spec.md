# Feature Specification: A Turn-Exhausted Implement Cycle Is Carried Forward, Not Redone from Cold

**Feature Branch**: `040-truncated-cycle-carry-forward`

**Created**: 2026-08-21

**Status**: Draft

**Input**: User description: "implement: a turn-exhausted cycle is treated as a failure and redone on Opus from cold, instead of as an unconverged cycle the loop carries forward. When an implement cycle exhausts its turn budget, `implement.yml` treats it as an outright failure: the same iteration is redone from a cold context on the escalation model. But a truncated cycle is not a failed cycle — it is an *incomplete* one, and the work it did complete is already committed and pushed. The loop it sits in (`max-iterations`, default 5) exists precisely to carry incomplete work forward. This proposes treating `error_max_turns` as 'cycle completed, did not converge' — advance to iteration N+1 on the normal tier — rather than as a failure requiring an escalated redo. Filing for discussion rather than as an agreed change: there is a real failure mode in the naive version (§Risks, R1) that has to be handled or this makes things worse. Why now: measured over 491 retained agent transcripts (2026-07-05 → 2026-08-09), 13 of 31 implement cycles (42%) exhausted the 100-turn budget; those 13 cost $89.48 in truncated Sonnet cycles plus $79.82 in Opus retries, and the retry is the more expensive half and it restarts from nothing; every one of those retries succeeded, taking 13–94 further turns — i.e. the remaining work was usually small relative to a full redo. The cap has since been raised 100 → 180 (`fix/turn-budget-accounting`), which makes exhaustion rarer but not cheaper: at 180 turns a truncated cycle has more completed work to throw away, so the case for carrying it forward gets stronger, not weaker. Current behaviour: `Read back cycle outcome` sets ok=true only when the agent step exited zero and spec-meta.json advanced; `error_max_turns` exits non-zero, so ok=false regardless of how much landed on the branch, and `Implement and converge (retry at escalation model)` fires. The cycle prompt pushes after every task phase specifically so partial work survives — so the branch is usually in good shape when this happens. Proposed behaviour, narrowly: when the agent's own result record carries subtype == 'error_max_turns' AND spec-meta.json advanced to (implement, N) as instructed, treat the cycle as completed-not-converged — dispatch iteration N+1 on the normal tier, with no escalated retry. Everything else (crash, push rejection, unadvanced branch, agent error) keeps today's retry-then-stall path unchanged. Scenarios: S1 truncated cycle, most work pushed (11 of the 13) — today the whole iteration is redone on Opus from a cold context, $6.15 median; proposed, iteration N+1 starts on Sonnet with the checklist already ticked. S2 truncated cycle, nothing pushed — a cycle that burned its budget on denied-tool round-trips (cf. #99) advances nothing; today an Opus retry is arguably right; proposed, iteration N+1 does the same work at the same tier and may burn the same budget the same way. This needs a no-progress guard: if the branch tip did not move, fall back to today's escalation path. Without it, this change can spend all 5 iterations achieving nothing and reach finalize with the feature unbuilt. S3 genuine failure (crash, rejected push, unadvanced spec-meta) — unchanged; the value of the change depends on it staying narrow: error_max_turns is a specific, machine-readable subtype, not a proxy for 'the step went red'. S4 truncation on the last iteration — today Opus retry then finalize with converged=false and a remaining-work report; proposed, straight to finalize with the same report, one Opus run cheaper; the human-visible outcome is identical. S5 truncation when already on the escalation tier (the model:opus label, or model == escalation-model) — today the retry step is skipped by its own guard, so the run goes to stalled and needs manual restart, arguably the worst current case, since a truncated Opus cycle with plenty of committed work looks identical to a dead one; proposed, continues to iteration N+1 like any other truncated cycle. Risks: R1 the convergence signal inverts, and this is the blocking one — `converged` is derived from the absence of a `converge:` commit touching tasks.md; a truncated cycle never reached step 3 of its prompt, so it never ran /speckit-converge and never writes that commit, meaning a naive flip of ok to true would compute converged=true and dispatch finalize on a feature that is visibly unfinished; any implementation must special-case error_max_turns to force converged=false, never inferring convergence from commit absence for a run that was cut off (same shape as the continue-on-error defect fixed in a06d3da, where a hidden agent failure produced a false 'passed inspection'). R2 iteration budget is consumed by truncated cycles — five iterations that each truncate is five Sonnet cycles and no escalation; mitigated by S2's no-progress guard, but the interaction with max-iterations deserves a deliberate answer rather than a default. R3 losing escalation as an implicit quality lever — some truncations are 'this task is too hard for Sonnet', not 'this task is large'; today those get Opus automatically; under the proposal they would not, unless something else escalates on repeated truncation — e.g. escalate on the second consecutive truncated cycle rather than the first. Risks of leaving it as-is: every truncation pays for a cold-context Opus redo of work already on the branch ($79.82 across the 13 observed); S5 sends truncated Opus cycles to stalled with committed work sitting on the branch, requiring a human to notice and restart; at a 180-turn cap the redo discards proportionally more completed work. Suggested shape, if pursued: (1) read the agent's result subtype in `Read back cycle outcome` rather than inferring everything from the step's exit status; (2) add a third outcome alongside ok / not-ok: `truncated` — requires subtype == error_max_turns, spec-meta advanced, and branch tip moved; (3) force converged=false on truncated (R1) and skip the escalated retry; (4) keep truncated out of the stall path, but escalate on the second consecutive truncation (R3); (5) extend .github/scripts/ coverage the way gate 8/9 do — execute the shipped decision shell against synthetic transcripts, including one that truncates with no converge: commit, and assert converged=false; R1 is exactly the kind of defect that reads as green. Context: turn-budget accounting and the cap raises, branch `fix/turn-budget-accounting`; measurement basis 491 transcripts, implement cycles p50 89, p75/p90 100 of 100 before the raise."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A cycle that ran out of turns keeps its work and carries on (Priority: P1)

An implement cycle works through its task list, pushing after each phase, and runs out of its turn budget partway through. The pipeline recognises that the cycle *completed a run without finishing the work*, records it as unconverged, and starts the next cycle at the ordinary tier. The next cycle opens on a branch where the finished tasks are already committed and already ticked off in the task list, and picks up the remainder.

**Why this priority**: This is the defect. Today the same iteration is thrown away and redone from a cold context one tier up, re-deriving from the spec, plan, and task list what the branch already records. Measured over the retained transcripts, 42% of implement cycles exhausted their budget, and the escalated redos cost more than the truncated cycles they replaced ($79.82 against $89.48) while every one of them succeeded after 13–94 further turns — i.e. the work that remained was small, and the redo was mostly re-reading. Every other story here protects or completes this one.

**Independent Test**: Drive the stage's cycle-outcome decision with a record of an agent run that ended because it ran out of turns, on a branch whose lifecycle record advanced and whose work moved forward, and confirm the decision is "completed, did not converge" — the next cycle is started at the ordinary tier and no escalated redo of the same cycle is run.

**Acceptance Scenarios**:

1. **Given** a cycle whose agent run ended by exhausting its turn budget, whose lifecycle record advanced to this stage and iteration, and which moved the feature's work forward, **When** the stage reads back the cycle outcome, **Then** the cycle is treated as completed-but-unconverged, the escalated redo of the same iteration does not run, and the next iteration is started at the same tier the cycle ran on.
2. **Given** the same conditions, **When** the next cycle begins, **Then** it starts from the branch the truncated cycle pushed to, with that cycle's completed work and its recorded task progress intact.
3. **Given** a cycle that completed normally, **When** the stage reads back the outcome, **Then** the behaviour is exactly today's — no new path is taken and nothing about a converged or unconverged normal cycle changes.
4. **Given** a truncated cycle carried forward, **When** the lifecycle issue is read, **Then** it says the cycle ran out of turns and the work is being carried into the next cycle — not that the cycle failed, and not that it simply "did not converge" with no explanation.

---

### User Story 2 - An unfinished feature is never handed to finalization as converged (Priority: P1)

A cycle runs out of turns before it ever reaches its convergence check. The pipeline treats it as unconverged, on the grounds that a run which was cut off never made a convergence judgement at all — rather than reading the missing convergence record as evidence that there was nothing left to do.

**Why this priority**: This is the blocking risk in the change, and it inverts the pipeline's most consequential signal. Convergence is inferred from the *absence* of a convergence commit touching the task list. A truncated cycle never reaches its convergence step, so it never writes that commit — meaning the naive version of story 1 computes "converged" for exactly the runs that are least finished, and hands a visibly unbuilt feature to finalization for human review. It is the same shape as an earlier defect in this repository where a hidden agent failure produced a false "passed inspection": a wrong answer that reads as green. Story 1 without this story is worse than shipping nothing.

**Independent Test**: Drive the cycle-outcome decision with a record of a turn-exhausted run on a branch that carries **no** convergence commit, and confirm the computed convergence answer is "not converged". A test that cannot distinguish "no convergence commit because nothing remained" from "no convergence commit because the run was cut off" does not satisfy this story.

**Acceptance Scenarios**:

1. **Given** a truncated cycle whose branch carries no convergence commit, **When** the stage computes the convergence answer, **Then** the answer is "not converged" — the absence of the commit is not read as evidence of convergence.
2. **Given** a truncated cycle carried forward and below the iteration cap, **When** the stage decides what happens next, **Then** it starts another cycle and does not hand off to finalization.
3. **Given** a truncated cycle carried forward *at* the iteration cap, **When** the stage decides what happens next, **Then** it hands off to finalization explicitly flagged as not converged, exactly as a cap-reached unconverged cycle does today.
4. **Given** a normal cycle that genuinely converged, **When** the stage computes the convergence answer, **Then** it is still "converged" — the special case applies only to runs that were cut off.
5. **Given** a truncated cycle whose branch *does* carry a convergence commit — the run was cut off after the convergence pass ran — **When** the stage computes the convergence answer, **Then** it is "not converged", as it would be today.

---

### User Story 3 - A truncated cycle that achieved nothing still gets escalated (Priority: P1)

A cycle burns its whole budget without moving the feature forward — for example, spending its turns on rejected tool calls. The pipeline does *not* carry it forward into an identical cycle at the same tier; it falls back to today's escalated redo.

**Why this priority**: Without this guard the change can make things strictly worse. A cycle that cannot make progress at a given tier will not make progress at the same tier next time, so carrying it forward spends the entire iteration budget achieving nothing and then hands an unbuilt feature to finalization — replacing one wasted escalated redo with five wasted ordinary cycles and a dead feature. It is P1 rather than P2 because it is a precondition of story 1 being safe, not an enhancement of it.

**Independent Test**: Drive the cycle-outcome decision with a record of a turn-exhausted run on a branch that did **not** move the feature forward, and confirm the escalated redo of the same iteration runs, exactly as it does today.

**Acceptance Scenarios**:

1. **Given** a cycle whose agent run exhausted its turn budget but which did not advance the feature's work, **When** the stage reads back the outcome, **Then** the cycle is treated as a failed attempt and today's escalated redo path runs unchanged.
2. **Given** a cycle whose agent run exhausted its turn budget but whose lifecycle record did not advance to this stage and iteration, **When** the stage reads back the outcome, **Then** the cycle is treated as a failed attempt and today's escalated redo path runs unchanged.
3. **Given** a truncated cycle that advanced only its own lifecycle bookkeeping and nothing else, **When** the stage reads back the outcome, **Then** it is treated as having made no progress — bookkeeping alone is not progress.
4. **Given** a no-progress truncated cycle that has already run at the top tier, **When** the stage reads back the outcome, **Then** it follows today's path for that case and the run is marked stalled with restart instructions.

---

### User Story 4 - A truncated top-tier cycle no longer strands its work (Priority: P2)

A cycle running at the escalation tier — because the feature was opted in to it, or because the repository configured it — runs out of turns with substantial work committed. Instead of the run being marked stalled and waiting for a human to notice and restart it, the next cycle is started automatically.

**Why this priority**: This is the worst of today's cases: the escalated redo is skipped by its own guard when the cycle already ran at the top tier, so the run goes straight to stalled. A truncated top-tier cycle with plenty of pushed work is indistinguishable, from the outside, from a dead one, and the pipeline stops until a human intervenes. It is P2 only because it is rarer than the ordinary-tier case that story 1 addresses; the mechanism is the same one.

**Independent Test**: Drive the cycle-outcome decision with a record of a turn-exhausted run that made progress and whose tier is already the escalation tier, and confirm the next cycle is started rather than the run being marked stalled.

**Acceptance Scenarios**:

1. **Given** a truncated cycle that made progress and already ran at the escalation tier, **When** the stage decides what happens next, **Then** the next iteration is started and the run is not marked stalled.
2. **Given** the same conditions at the iteration cap, **When** the stage decides what happens next, **Then** it hands off to finalization flagged as not converged, rather than marking the run stalled.
3. **Given** a *failed* — not truncated — cycle that already ran at the escalation tier, **When** the stage decides what happens next, **Then** the run is marked stalled with restart instructions, exactly as today.

---

### User Story 5 - Repeated truncation is counted and visible, not silent (Priority: P2)

A feature whose cycles keep running out of turns does not quietly burn its iteration budget one ordinary cycle at a time. Each truncation is reported on the lifecycle issue as a truncation, and it carries how many consecutive truncations this feature has now had, so a reader can see the pattern without opening a run log.

**Why this priority**: Carrying truncated cycles forward removes an escalation that today happens automatically. Some truncations mean "this work is large" — carrying forward is right. Some mean "this work is too hard for this tier" — carrying forward at the same tier just re-runs the wall. Nothing else in the pipeline distinguishes them, so repeated truncation is the only available signal. This feature ships that signal without acting on it: escalating on repeated truncation is a deliberate follow-up, and shipping the count first means the follow-up arrives with evidence of how often the case actually occurs.

**Independent Test**: Drive a sequence of cycles that each truncate with progress, and confirm each is reported to the lifecycle issue as a truncation carrying an increasing consecutive-truncation count, and that a completed or failed cycle in between resets that count.

**Acceptance Scenarios**:

1. **Given** a cycle that truncates with progress immediately after another cycle that truncated with progress, **When** the stage decides what happens next, **Then** the next cycle is started at the same tier and the reported consecutive-truncation count is two.
2. **Given** a cycle that truncates with progress after a cycle that completed normally, **When** the stage decides what happens next, **Then** it is treated as a first truncation, carried forward at the same tier, and the reported count is one.
3. **Given** any truncated cycle, **When** the lifecycle issue is read, **Then** that cycle is identifiable as having run out of turns and carries the consecutive-truncation count, so a reader can see repeated truncation without opening a run log.
4. **Given** truncated cycles that exhaust the iteration budget, **When** the stage hands off to finalization, **Then** the hand-off is flagged as not converged and the report states that the last cycle ran out of turns, rather than presenting an empty remaining-work list.
5. **Given** repeated truncation of any length, **When** the stage decides what happens next, **Then** the tier is unchanged — this feature reports the pattern and does not act on it.

---

### User Story 6 - The decision is proven against recorded runs, not merely shipped (Priority: P2)

The rules that classify a cycle as completed, truncated, or failed are exercised by executable coverage against synthetic run records before merge. Removing the forced not-converged answer, removing the no-progress guard, or widening truncation to cover ordinary failures each fails a check.

**Why this priority**: The blocking risk in this change (story 2) is a wrong answer that reads as green: a run that looks successful and hands an unbuilt feature to a human as finished. Nothing in the ordinary flow of the pipeline surfaces that, and the truncation path itself only runs when a cycle happens to run out of turns, so a regression could sit unnoticed across many features. The repository already runs shipped decision logic against synthetic transcripts in exactly this way for other checks, so this joins an existing arrangement rather than establishing one.

**Independent Test**: Run the coverage against a synthetic record of a turn-exhausted run with no convergence commit and confirm it asserts "not converged"; then remove the forced answer from the shipped decision and confirm a check fails.

**Acceptance Scenarios**:

1. **Given** a synthetic record of a turn-exhausted run with progress and no convergence commit, **When** the coverage runs, **Then** it asserts the outcome is truncated **and** the convergence answer is "not converged".
2. **Given** the forced not-converged answer removed from the shipped decision, **When** the checks run, **Then** a check fails.
3. **Given** the no-progress guard removed, so that a truncated cycle with no progress is carried forward, **When** the checks run, **Then** a check fails.
4. **Given** truncation widened so that an ordinary agent failure is treated as truncated, **When** the checks run, **Then** a check fails.
5. **Given** a synthetic record of a normal successful cycle, **When** the coverage runs, **Then** it asserts today's outcome and convergence answer are unchanged.
6. **Given** the new coverage disabled, removed, or made unreachable, **When** the repository's checks run, **Then** a check fails — the coverage is wired into the same registry that proves every other check is actually run.

---

### Edge Cases

- **The escalated redo itself runs out of turns.** The redo is a cycle too. When it truncates with progress and an advanced lifecycle record, it is carried forward on the same terms as any other truncated cycle rather than falling through to stalled.
- **Truncation on the final permitted iteration.** Hand off to finalization flagged as not converged, with the remaining-work report — the same human-visible outcome as today, one escalated redo cheaper.
- **A truncated cycle produces no remaining-work list.** The remaining-work report is derived from the convergence commit, which a truncated cycle never writes. The report must say the cycle ran out of turns before assessing what remained, rather than printing an empty list that reads as "nothing left to do".
- **The run record is missing, unreadable, or does not say why the run ended.** Not truncation. The cycle takes today's failed path — the new treatment requires positive identification of turn exhaustion, never an inference from a red step.
- **The agent step fails for any other reason** — a crash, a rejected push, a lifecycle record that never advanced. Unchanged in every respect, including the escalated redo and the stalled path.
- **A truncated cycle that was cut off *after* its convergence pass ran.** Indistinguishable from one cut off before, and treated the same: not converged. The cost is one extra cycle in a rare case, and that cycle converges immediately and cheaply; the alternative is the false-green of story 2.
- **A truncated cycle whose only commit is its own lifecycle bookkeeping.** The lifecycle record advancing is a *precondition* of the carry-forward, so it cannot also serve as the evidence of progress; a cycle that advanced nothing else made no progress, even though its branch tip moved.
- **A truncated cycle that ticked a task in the task list but changed nothing else.** Progress. Marking a task complete is a claim about work that landed, and the next cycle reads the task list as its starting point; this is one of the two arms of the progress test.
- **A truncated cycle that changed files outside the spec directory but ticked no task.** Progress. Work landed on the branch and the cycle simply ran out of turns before recording it; the other arm of the progress test covers it.
- **A truncated cycle whose pushed work is a partial edit** — a half-finished change that leaves the branch worse than before. Carrying forward is still correct: the next cycle sees the branch as it is, and this is already the situation after any pushed phase of any cycle.
- **Two consecutive truncations where the first was at the top tier.** No different from any other repeated truncation under this feature — the tier never changes on repetition anyway — but the count must still be reported, since a top-tier feature is exactly where a future escalation would have nowhere to go.
- **A run in which the cycle step never attempted at all** — skipped by an entry gate or a guard. Not truncation, and untouched by this feature.
- **The visible outcome of the run itself.** A carried-forward truncated cycle must be legible as "completed, did not converge", not as a failure — a run that reports itself failed while the pipeline continues is the same confusion this feature exists to remove.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The implement stage MUST classify each cycle attempt into exactly one of three outcomes — **completed**, **truncated**, or **failed** — with no fourth or undefined path, and every downstream decision (escalated redo, next cycle, hand-off to finalization, stalled) MUST be driven by that classification.
- **FR-002**: A cycle MUST be classified **truncated** only when all of the following hold: the agent's own run record positively identifies the run as having ended by exhausting its turn budget; the feature's lifecycle record advanced to this stage and this iteration as the cycle was instructed to do; and the cycle made progress as defined in FR-004. If any one fails, the cycle MUST take today's path.
- **FR-003**: Truncation MUST be identified from the agent's machine-readable run record, never inferred from the agent step's exit status or from the step appearing red. A run whose record is absent, unreadable, or does not state why the run ended MUST NOT be classified as truncated.
- **FR-004**: The stage MUST require positive evidence that a truncated cycle moved the feature's work forward before carrying it forward. A cycle counts as having made progress when, comparing the branch as it stood at the *start* of the cycle with the branch as the cycle left it, **either** at least one task is newly marked complete in the feature's task list **or** at least one file outside the feature's spec directory changed. Either arm alone is sufficient.
- **FR-004a**: The advance of the feature's lifecycle record that FR-002 requires MUST be excluded from the FR-004 comparison and MUST NOT count as progress on its own. "The branch tip moved" MUST NOT be used as the test, because that advance is itself a commit and would make the guard always true and therefore inert.
- **FR-005**: When a cycle is classified truncated, the stage MUST record the convergence answer as **not converged**, regardless of whether a convergence commit is present on the branch. The stage MUST NOT infer convergence from the absence of a convergence commit for any run that was cut off.
- **FR-006**: When a cycle is classified truncated, the escalated redo of the same iteration MUST NOT run.
- **FR-007**: When a cycle is classified truncated and the iteration is below the cap, the stage MUST start the next iteration at the same tier the truncated cycle ran on — including when the same feature's previous cycles were also truncated (FR-011).
- **FR-008**: When a cycle is classified truncated and the iteration is at the cap, the stage MUST hand off to finalization flagged as not converged, and MUST NOT mark the run stalled.
- **FR-009**: A truncated cycle MUST NOT mark the run stalled, including when the cycle already ran at the escalation tier — the case that today skips the redo and stalls with committed work on the branch.
- **FR-010**: A truncated cycle MUST consume one iteration of the configured iteration budget, exactly as a completed-but-unconverged cycle does. Truncated cycles MUST NOT receive a separate or additional allowance, and MUST NOT be exempted from the budget on any grounds. The iteration budget therefore remains a true bound on total cost regardless of how cycles end; a feature whose cycles achieve nothing is caught by the no-progress guard of FR-004, not by iteration accounting, so exactly one mechanism does that job.
- **FR-011**: The number of *consecutive* truncated cycles for a feature MUST be counted and carried across separately-dispatched cycles, and MUST be reported to the lifecycle issue with each truncated cycle. A cycle that completed or failed MUST reset that count.
- **FR-011a**: This feature MUST NOT change the tier in response to repeated truncation. A truncated cycle with progress is carried forward at the same tier however many times it repeats; escalating on repeated truncation is deliberately deferred to a follow-up, and this feature ships only the signal that follow-up would act on.
- **FR-012**: Repeated truncation MUST be visible at every tier, including when the truncated cycles already ran at the escalation tier and there is no higher tier at all. The pipeline MUST NOT consume the iteration budget with a run of truncated cycles without that repetition being legible on the lifecycle issue.
- **FR-013**: Every truncated cycle MUST be reported to the lifecycle issue in terms that name turn exhaustion and state that the completed work is being carried into the next cycle. It MUST NOT be reported as a failed cycle, and MUST NOT be reported as an unexplained non-convergence.
- **FR-014**: When the stage hands off to finalization after a truncated cycle, the remaining-work report MUST state that the last cycle ran out of turns before it could assess what remained, instead of presenting the empty list that today's convergence-derived report would produce.
- **FR-015**: A run whose cycle was truncated and carried forward MUST be legible as "completed, did not converge" rather than as a failed run, both in the run's own summary and in what is posted to the lifecycle issue.
- **FR-016**: An escalated redo that itself ends in truncation MUST be classified by the same rules as any other cycle (FR-002) and, when truncated, MUST be carried forward under FR-007/FR-008 rather than falling through to stalled.
- **FR-017**: Behaviour for every non-truncated outcome MUST be unchanged: a completed cycle's convergence answer, hand-off, and reporting; and a failed cycle's escalated redo, stalled marking, and restart instructions. No existing path may be widened by this feature.
- **FR-018**: Executable coverage MUST drive the stage's shipped classification and convergence decision against synthetic agent run records, and MUST include at minimum: a turn-exhausted run with progress and no convergence commit (asserting truncated **and** not converged); a turn-exhausted run whose only change is the lifecycle-record advance (asserting today's failed path, so the FR-004a exclusion is proven and the guard is not inert); a turn-exhausted run whose only progress is a newly completed task in the task list, and one whose only progress is a changed file outside the spec directory (each asserting truncated, so both arms of FR-004 are proven); an ordinary failure (asserting today's failed path); and a normal successful cycle (asserting today's outcome unchanged).
- **FR-019**: Removing the forced not-converged answer of FR-005, removing the no-progress guard of FR-004, removing either arm of FR-004's progress test, counting the lifecycle-record advance as progress, or widening truncation to cover ordinary failures MUST each fail a check. Coverage that can only exercise the carry-forward path does not satisfy this requirement.
- **FR-020**: The new coverage MUST be wired into the repository's existing check registry, so coverage that stops being run is itself a failure.
- **FR-021**: This feature MUST NOT change the stage's declared inputs, outputs, or required access, and MUST NOT require any calling wrapper to be edited. Adopters pinned to a release see only the changed behaviour on truncation.
- **FR-022**: This feature MUST NOT change any turn budget, any turn-budget ceiling, or the default iteration cap. It changes only what the pipeline does when a budget is exhausted.

### Key Entities

- **Implement cycle**: one dispatched iteration of the implement ⟲ converge loop. It runs an agent that works the task list, pushes after each phase so partial work survives, advances the feature's lifecycle record to its stage and iteration, and finishes with a convergence pass.
- **Cycle outcome**: today a binary — the attempt completed, or it did not. This feature makes it a three-way classification: completed, truncated, failed.
- **Agent run record**: the machine-readable record the agent leaves behind for a run, including a positive statement of why the run ended. It already distinguishes a run that exhausted its turn budget from one that errored, and it is the only admissible evidence of truncation.
- **Convergence answer**: the pipeline's judgement of whether any work remains, inferred today from the absence of a convergence commit touching the task list. For a run that was cut off, that inference is invalid — the absence means the judgement was never made.
- **Progress evidence**: what distinguishes a truncated cycle that did work from one that burned its budget achieving nothing — a newly completed task in the task list, or a changed file outside the spec directory, measured against the branch as it stood when the cycle started and ignoring the lifecycle-record advance. It is the guard that keeps carry-forward from consuming the whole iteration budget for free, and it is deliberately generous: it asks whether anything happened, not whether enough happened.
- **Consecutive-truncation count**: how many cycles in a row have ended in truncation for this feature, reset by any cycle that completed or failed. This feature reports it and does not act on it; it exists so the follow-up that decides whether to escalate is designed against real frequencies.
- **Iteration budget**: the configured cap on cycles for one feature (default five). It bounds total cost and decides when the pipeline gives up and hands unfinished work to a human.
- **Escalation tier**: the higher-cost model the stage redoes a failed cycle on. Today it is also the implicit response to a cycle that ran out of turns; this feature separates those two uses.
- **Stalled state**: the terminal state for a cycle that failed and could not be redone, which marks the lifecycle record and asks a human to restart. It must remain reachable for genuine failures and unreachable for truncations with progress.

## Out of Scope

- **Changing turn budgets or the runaway ceiling.** The cap raise (100 → 180) already happened separately, and this feature is explicitly about what happens when a budget is exhausted, not about how large it is.
- **Changing the default iteration cap** or making it depend on how cycles ended.
- **Changing how convergence itself is assessed** for cycles that ran to completion. The convergence-commit inference is unchanged for every run that was not cut off.
- **Applying the same treatment to other stages' agent steps.** Specification, planning, task generation, clarification, and the watchdog all run bounded agents too; whether any of them should carry truncated work forward is a separate question this feature does not answer.
- **Resuming a truncated agent run in place**, or otherwise preserving its context across cycles. Carry-forward here means the *branch* carries the work; the next cycle is a fresh run reading a branch that records more than it did before.
- **Automatic restart of runs that are marked stalled.** Fewer runs reach stalled under this feature; getting out of stalled is unchanged.
- **Changes to the watchdog**, to the cost and turn metrics the pipeline already records, or to how transcripts are retained.
- **Reworking the escalated redo itself** — its prompt, its budget, or the fact that it re-runs the same iteration. This feature only changes *when* it fires.
- **Escalating the tier in response to repeated truncation.** This feature counts consecutive truncations and reports them (FR-011) but never acts on the count. Deciding what the pipeline should do about a feature that truncates repeatedly is a follow-up, to be filed against the source request's R3 once this lands, and designed against the data this feature's reporting produces.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A cycle that runs out of turns with work pushed advances the feature to the next cycle instead of being redone, so the number of escalated redos triggered by turn exhaustion alone falls to zero.
- **SC-002**: For a feature whose cycle runs out of turns, the escalated redo of that same iteration — which across the measured sample cost more than the truncated cycles it replaced — is not spent, while the feature still reaches the same finished state.
- **SC-003**: No run that was cut off before its convergence pass is ever handed to finalization as converged; measured across the coverage, the count is zero, where the naive change would report converged for every one of them.
- **SC-004**: A cycle that runs out of turns without moving the feature forward still escalates on its first occurrence, so the iteration budget cannot be consumed by cycles that achieve nothing.
- **SC-005**: A cycle that runs out of turns at the top tier with work pushed continues automatically, so the number of such runs requiring a human to notice and restart falls to zero from today's all of them.
- **SC-006**: Cycles that fail for any reason other than turn exhaustion behave identically before and after this feature — same redo, same stalled marking, same restart instructions, same reporting.
- **SC-007**: A reader of the lifecycle issue alone can tell a truncated cycle from a failed one and from a normally unconverged one, and can see how many consecutive cycles have truncated, without opening a run log.
- **SC-008**: A finalization hand-off that follows a truncated cycle never presents an empty remaining-work list; it states that the cycle ran out of turns before assessing what remained.
- **SC-009**: Removing the forced not-converged answer fails a check; removing the no-progress guard fails a check; widening truncation to ordinary failures fails a check; disabling or removing the new coverage fails a check.
- **SC-010**: The change reaches every consumer without editing any wrapper and without altering the stage's declared inputs, outputs, or required access.

## Assumptions

- The agent's run record positively and reliably distinguishes "ran out of turns" from every other way a run can end, and the pipeline already reads it — the stage computes a per-run verdict from that record today, including a distinct value for turn exhaustion. This feature consumes that existing signal rather than introducing a new way to detect truncation.
- Work pushed by a truncated cycle is sound enough to build on. The cycle prompt pushes after each task phase precisely so partial work survives, and the measured evidence — every escalated redo succeeded, most after few further turns — indicates the branch was in usable shape.
- The recorded task list is a better starting point for the next cycle than a cold re-derivation from the spec and plan. This is the premise of the whole change: the next cycle reads state the branch records instead of inferring it.
- Turn exhaustion usually means "the work was large", not "the tier was too weak" — but not always. This feature records repeated truncation (FR-011) rather than acting on it, on the basis that the follow-up which decides what to do about it should be designed against evidence of how often it happens; the no-progress guard (FR-004) is the one case where a truncated cycle escalates immediately, because a cycle that achieved nothing has already demonstrated it will not achieve anything next time either.
- The wide reading of progress (FR-004: either arm suffices) is deliberate. A wrong escalation costs a whole cycle redone cold at the escalation tier, which is precisely the waste this feature exists to remove, so the guard errs toward carrying forward. It is a guard against cycles that achieved *nothing*, not a judgement of how much they achieved.
- The lifecycle record is the natural place to carry per-feature cycle state across separately-dispatched cycles, including the consecutive-truncation count of FR-011; it is already the machine-readable source of truth for a feature's lifecycle and already carries the stage and iteration this feature reads. The requester deferred the question of *what writes* that count to the follow-up, so this spec requires the count to exist and be reported without fixing the mechanism.
- A truncated cycle consumes one iteration of the budget (FR-010), and the budget therefore remains a bound on total cost rather than on successful cycles only. Runaway truncation is bounded by exactly one mechanism — the no-progress guard — rather than by both that guard and a second budget rule.
- The repository's existing practice of running shipped decision logic against synthetic transcripts, wired into a registry that proves each check runs, is the right home for the new coverage; this feature joins that arrangement rather than establishing a new one.
- The extra cost of forcing "not converged" on a cycle that happened to be cut off after its convergence pass is one additional cycle that converges immediately, and that is an acceptable price for never reporting an unfinished feature as finished.
- The pipeline's per-feature serialization means one feature's cycles do not interleave, so "the immediately preceding cycle" is well defined.
