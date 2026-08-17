# Feature Specification: A Successful Agent Step Is No Longer Failed by the Wrong Turn Counter

**Feature Branch**: `037-agent-turn-budget-guard`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "`anthropics/claude-code-action` fails a **successful** agent step when the result record's `.num_turns` exceeds `--max-turns`. Those are different counters. The cap is absorbed at exactly one of the 19 `--max-turns` call sites; the other 18 are exposed, and one of them has now taken out `clarify`. Upstream, `base-action/src/run-claude-sdk.ts` throws when `resultMessage.subtype == \"success\" && !resultMessage.is_error && sdkOptions.maxTurns !== undefined && resultMessage.num_turns > sdkOptions.maxTurns`; added 2026-08-07 in anthropics/claude-code-action#1607 ('fix: enforce max turns from claude args'). There is no opt-out other than not passing `--max-turns` at all. Evidence: run 31918153816 — `clarify`, lifecycle issue #204, step 'Fold answers into the draft spec': '##[error]Claude reported a successful result after 47 turns, exceeding the configured maximum of 40'. Counting the uploaded `claude-execution-output.json` the way `wing-commander-metrics-summary` counts it: distinct main-loop assistant messages (what `--max-turns` enforces) 36 / 40 (90%); subagent assistant messages 0; `.num_turns` (what the action compares) 47 (1.31x); result `subtype` `success`, `is_error` `false`; structured output `{\"answered\": true, \"clarifications\": []}`; cost $1.98. The run never came near exhausting its budget. It was failed for a number that does not measure the thing the flag caps. This is the second occurrence and the root cause was already correctly diagnosed: `auto-update-spec-kit.yml:894-911` ('Decide upgrade path'), written 2026-08-15 — one day before this run — records the same mismatch, the same Gate 11 (`verify-metrics-turn-accounting.py`) reference, and the same 1.0x-2.3x inflation. That step's cap was doubled 15 → 30 and the problem went away for that step. The fix was never generalised, so `clarify` met the identical failure 31 hours later. `wing-commander-metrics-summary/action.yml` has documented the same divergence since 2026-08-06, but only for rendering the ratio — Gate 11 verifies we report the right counter, nothing makes the action compare the right counter. Why it matters: the throw is post-hoc, so it strands completed work. The check runs after the result message, i.e. after every side effect the agent has already committed. On this run the agent had folded all three clarifications into `specs/035-auto-update-pr-guard/spec.md` and the requirements checklist, committed `acf35a6` and pushed it to `spec-draft/035-auto-update-pr-guard`, rewritten PR #205's body, and returned a valid structured result. Then the step failed. Every downstream step in `clarify.yml` is gated on `steps.agent.outcome == 'success'` with no status function, so 'Fail on agent API error' (446), 'Determine clarification follow-up outcome' (474), 'Resolve spec PR URL' (615) and 'Announce spec PR ready for review' (623) were all skipped. So #204 received no readiness callout: its last comment was the maintainer's own answer, the label stayed `stage:spec`, and PR #205 sat complete and unannounced. $1.98 of finished work, invisible, behind a red run. The callout was posted by hand. The lifecycle is not mechanically wedged — `wing-commander-3-plan.yml` triggers on `pull_request: closed` under `specs/**`, so merging #205 still advances — but the stage's entire human-facing output is lost, and the run is red for a healthy agent. The watchdog did not catch it: `WING_COMMANDER_WATCHDOG_PAUSED=true`, so runs 31918330136 / 31918332108 skipped at the wrapper gate. Exposure is 18 of 19 call sites: `auto-update-spec-kit.yml:916` (30 — absorbed, 2x of 15), `auto-update-spec-kit.yml:1632` (20), `auto-update-spec-kit.yml:2676` (8), `clarify.yml:417` (40 ← failed here), `cleanup.yml:515` (20), `finalize.yml:491` (20), `implement.yml:619` (180), `implement.yml:830` (180), `implement.yml:1020` (15), `intake.yml:586` (50), `plan.yml:623` (110), `plan.yml:736` (110), `pr-conversation.yml:706` (40), `pr-conversation.yml:1489` (40), `rebase.yml:624` (50), `tasks.yml:562` (60), `tasks.yml:662` (60), `watchdog.yml:1252` (30), `watchdog.yml:1784` (30). At the measured 1.0x-2.3x inflation, any run that uses more than ~43% of its real budget can be failed spuriously. The two observed hits were at 90% (clarify, 36/40) and at `.num_turns` 16 against a cap of 15. The smallest caps are the most exposed in relative terms: `auto-update-spec-kit.yml:2676` at 8 and `implement.yml:1020` at 15 fail after roughly 3 and 6 real turns respectively in the worst case. The 2026-08-06 `implement` cycle that `wing-commander-metrics-summary` cites — `.num_turns` 198 against a cap of 100, 87 turns actually used — would fail outright under this check today. Proposed change, three options, not mutually exclusive: (1) absorb at every site (what 'Decide upgrade path' did) by multiplying each cap by ~2.5 — cheap and mechanical, but it moves the real SDK cap by the same factor, so a genuinely runaway agent gets 2.5x the turns and 2.5x the spend before anything stops it; on `implement` that is 180 → 450. (2) Split the ceiling from the budget (preferred): pass the action an inflated `--max-turns` that only acts as a runaway ceiling, and enforce the intended budget deterministically in a post-step that counts main-loop assistant messages from the transcript — the counter `wing-commander-metrics-summary` already implements correctly and Gate 11 already verifies; the budget then means what the comments in these files say it means, and the exhaustion signal `implement` relies on (#179) becomes ours rather than the action's. (3) Report upstream — the comparison is between two different counters, #1607 shipped without accounting for the divergence, and no upstream issue exists for it yet. Interlock with #193: #193 proposes rescuing the six unrescued agent steps with `continue-on-error: true` plus a fail-loud arm gated on `steps.agent.outcome == 'failure'`. Applied as written, this defect still fails the run — the spurious throw sets `outcome == 'failure'`, the new arm fires, and the run stays red for a healthy agent, only with a better error message. Whatever rescue lands must distinguish an agent that genuinely failed / crashed / errored (fail loud) from an action that threw post-hoc while the result record says `subtype: success`, `is_error: false`, and (where a schema is set) structured output is present (continue the stage). That distinction is readable from the same transcript both #193's read-back and the metrics action already parse, which argues for one shared 'agent verdict' composite rather than a per-stage `if:` expression. Adjacent, out of scope here: three of this run's 36 turns went to `permission_denied` on compound Bash commands whose individual parts are allow-listed standalone — same class as #197, fixed in #207; it did not cause this failure, but it inflated both counters and consumed the margin that took this run to 90%. Found by post-mortem of run 31918153816 from the uploaded `claude-execution-output.json` artifact."

## Clarifications

### Session 2026-08-17

- Q: Does this feature deliver the shared agent-verdict evaluation for every agent step — including the ones with no rescue wiring today, subsuming #193 — or only the healthy-versus-genuinely-failed discrimination? → A: This feature owns the whole thing: the shared verdict plus the rescue wiring on all agent call sites, so #193 is closed by it. One review surface, one landing, and no window where the verdict exists but some steps still cannot use it.
- Q: When an agent run is healthy but its counted main-loop turns genuinely reach or exceed the stage's intended budget, what should the stage do? → A: Continue and report the over-budget condition loudly — in the run summary and, for stages that post to the lifecycle issue, there too. The intended budget becomes an observability instrument; the runaway ceiling is the only hard stop, so ceiling sizing carries the cost protection.
- Q: Is reporting the counter mismatch upstream to `anthropics/claude-code-action` part of this feature's deliverable? → A: In scope as a drafted report committed with the feature, written while the evidence is fresh. Actually filing it upstream is optional and at the maintainers' discretion — the feature is complete with the draft committed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Finished work is never stranded behind a spurious failure (Priority: P1)

An agent step completes its work successfully — it edits files, commits, pushes, updates a pull request, and returns a valid result well inside the turn budget the stage configured for it. The action's post-hoc comparison then rejects the run because a different, inflated counter exceeded the cap. The stage recognises this verdict for what it is — a healthy agent run — and carries on: every downstream step runs, the lifecycle issue receives its callout, the label advances, and the run ends green.

**Why this priority**: This is the whole defect. The throw happens after every side effect has already been committed, so the stage's repository-facing work is done and only its human-facing output is lost. The requester sees a red run and no callout for work that is finished and correct, and a maintainer has to notice and post the callout by hand. Nothing else in this feature matters if a completed run still ends red and silent.

**Independent Test**: Replay a transcript matching run 31918153816 — terminal result `subtype: success`, `is_error: false`, valid structured output, counted main-loop turns below the intended budget, reported counter above the configured cap — through a stage, and confirm the stage's downstream steps all execute, the human-facing callout is posted, and the run concludes successfully.

**Acceptance Scenarios**:

1. **Given** an agent step whose transcript shows a successful terminal result and counted main-loop turns within the intended budget, **When** the action rejects the step because its reported counter exceeded the configured cap, **Then** the stage treats the agent run as successful and every step downstream of it runs.
2. **Given** the same situation in `clarify`, **When** the run finishes, **Then** the lifecycle issue receives the spec-PR-ready callout and the stage label advances exactly as it would have without the rejection.
3. **Given** the same situation, **When** the run finishes, **Then** the run is reported as a success, not a failure.
4. **Given** an agent step whose transcript shows a genuinely errored, crashed, or missing terminal result, **When** the step ends, **Then** the stage fails loudly with a message naming what actually went wrong, and does not continue as though the agent had succeeded.
5. **Given** an agent step that declares a result schema and whose terminal result is successful but carries no valid structured output, **When** the step ends, **Then** the stage fails loudly rather than continuing on an empty result.

---

### User Story 2 - The turn budget still means what the workflows say it means (Priority: P1)

Each agent step declares an intended turn budget. That budget continues to be enforced and reported against the counter that actually measures it — distinct main-loop assistant responses — so a run flagged as over budget really is over budget, and a genuinely runaway agent is still stopped before it spends without bound.

**Why this priority**: Removing the spurious failure must not remove the ceiling with it. The project's cost discipline requires every agent step to run under a bounded budget, and the `implement` stage consumes budget exhaustion as a real signal. A fix that only makes the cap bigger buys silence at the cost of letting a runaway agent spend several times more before anything stops it, so the budget and the ceiling have to be separable and both real. Reaching the intended budget is reported rather than fatal — nothing that completes successfully is failed for a number again — which puts all of the cost protection on how the ceiling is sized.

**Independent Test**: Replay one transcript that genuinely exhausts its intended budget and one that stays inside it, and confirm the over-budget run is identified and reported as over budget while the inside-budget run is not — with the classification driven by counted main-loop turns, not by the reported counter.

**Acceptance Scenarios**:

1. **Given** an agent run whose counted main-loop turns reach or exceed the stage's intended budget, **When** the step ends, **Then** the run is identified as budget-exhausted, that fact is reported loudly in the run's summary and on the lifecycle issue for stages that post there, and the stage still concludes successfully rather than failing on the over-budget condition alone.
2. **Given** an agent run whose counted main-loop turns are inside the intended budget but whose reported counter is above it, **When** the step ends, **Then** the run is not reported as budget-exhausted and no budget warning is raised.
3. **Given** an agent run that includes subagent activity, **When** turns are counted, **Then** subagent responses are excluded from the count and multiple records sharing one response identifier count once.
4. **Given** any agent step, **When** it is invoked, **Then** it still declares both an explicit model and a bounded turn ceiling, so no stage runs unbounded.
5. **Given** an agent that genuinely runs away, **When** it reaches the ceiling, **Then** it is stopped, and the amount it may spend before being stopped is stated in the stage's configuration rather than being an emergent side effect of a mismatch.

---

### User Story 3 - Every agent call site is covered, and stays covered (Priority: P2)

All agent invocation sites across the pipeline carry the same protection — the shared verdict and the rescue wiring that consumes it — including the steps that have no rescue wiring today. A newly added agent step cannot ship without it, and the coverage is asserted mechanically rather than depending on whoever adds the next step remembering the history.

**Why this priority**: The root cause was correctly diagnosed and correctly fixed at one call site the day before it took out a second one. A per-site fix that is not enforced is exactly the failure that produced this issue. The smallest budgets are the most exposed, so partial coverage leaves the cheapest, most frequent steps at the highest relative risk.

**Independent Test**: Add a new agent step that omits the protection and confirm the repository's own pre-merge checks reject it, naming the missing piece.

**Acceptance Scenarios**:

1. **Given** the pipeline after this feature lands, **When** the agent invocation sites are enumerated, **Then** every one of them carries the protection, with zero exposed sites.
2. **Given** a proposed change that adds an agent step without the protection, **When** the repository's pre-merge checks run, **Then** they fail and name the unprotected step.
3. **Given** a proposed change that lowers an agent step's ceiling back to its intended budget, **When** the pre-merge checks run, **Then** they fail rather than silently reintroducing the exposure.
4. **Given** an agent step that carried no rescue wiring before this feature, **When** its agent is rejected post-hoc despite a healthy transcript, **Then** it behaves exactly like an already-rescued step — the stage continues — with no separate follow-up change needed to get there.

---

### User Story 4 - A maintainer can tell the two verdicts apart from the run alone (Priority: P3)

When a stage continues past a rejected-but-healthy agent step, the run says so plainly: which verdict was reached, on what evidence, and what the counted and reported turn numbers were. When a stage stops because the agent genuinely failed, it says that just as plainly.

**Why this priority**: The rescue is only trustworthy if a human can audit it. A stage that silently swallows an action-level error is one defect away from swallowing a real one, and the existing job summary is already the place where turn accounting is reported.

**Independent Test**: Run one stage through each verdict and confirm the run's summary states the verdict, the evidence behind it, and both turn numbers.

**Acceptance Scenarios**:

1. **Given** a stage that continued past a post-hoc rejection, **When** a maintainer reads the run summary, **Then** it states that the agent run was healthy, why the step was rejected, and both the counted and reported turn totals.
2. **Given** a stage that failed on a genuine agent error, **When** a maintainer reads the run summary, **Then** it states the failure reason and does not present it as a spurious rejection.

---

### Edge Cases

- **The transcript is missing, empty, or unparseable.** The verdict cannot be established, so the run must fail closed rather than assume health — an unreadable transcript is not evidence of success.
- **The terminal result says `subtype: success` but `is_error: true`, or there is no terminal result at all.** A genuine failure; the stage fails loudly. This is the distinction the existing per-stage "Fail on agent API error" steps already draw, and the verdict must not weaken it.
- **The agent genuinely reached the ceiling.** The terminal result reports exhaustion rather than success; that is a real outcome, not a spurious rejection, and must be surfaced as exhaustion (the signal `implement` already relies on).
- **A job runs more than one agent step and they share a transcript path.** Each step's verdict must be established from its own transcript before a later step overwrites it.
- **Turn counting fails on an unexpected transcript shape.** The budget comparison must be suppressed rather than computed from the wrong counter, matching how the existing metrics summary already degrades.
- **The upstream comparison is fixed or removed.** The stage's behaviour must remain correct when the post-hoc rejection stops happening — the ceiling then simply stops being reached, and nothing else changes.
- **The action's rejection emits a run-level error annotation.** Even when the stage continues, that annotation may remain visible; the run's own summary must explain it so a maintainer does not read a green run with a red annotation as ambiguous.
- **A stage whose agent step is the last meaningful step in its job.** Continuing past the rejection must still produce the stage's normal outputs and exit status rather than leaving the job's conclusion undefined.
- **An agent run that is both healthy and over its intended budget.** Two independent facts; the verdict must not collapse them into one. The run continues on the first and reports the second.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pipeline MUST distinguish an agent step rejected by a post-hoc comparison from an agent step whose agent genuinely failed, using the terminal result record's own success indicators as the evidence.
- **FR-002**: When the evidence shows a healthy agent run, the stage MUST continue: every step downstream of the agent step runs, and the run concludes successfully.
- **FR-003**: When the evidence shows a genuine failure — errored, crashed, missing, or malformed terminal result — the stage MUST fail loudly with a message naming the actual cause, and MUST NOT continue as though the agent had succeeded.
- **FR-004**: When an agent step declares a result schema, a successful terminal result whose structured output is missing or does not match the declared shape MUST be treated as a genuine failure.
- **FR-005**: When the verdict cannot be established at all — transcript missing, empty, or unparseable — the stage MUST fail closed rather than assume success.
- **FR-006**: The intended turn budget for each agent step MUST be enforced and reported against counted distinct main-loop agent responses, excluding subagent activity and counting records that share a response identifier once.
- **FR-007**: The value passed to the agent invocation as its turn cap MUST be a runaway ceiling that absorbs the observed divergence between the reported and counted turn counters, and MUST remain explicitly declared so that no agent step runs without a bounded ceiling.
- **FR-008**: Each agent step's intended turn budget MUST remain explicitly declared and legible in the stage's configuration, distinct from the ceiling.
- **FR-009**: The pipeline MUST report a budget-exhaustion outcome derived from the counted counter, preserving the exhaustion signal downstream stages already consume.
- **FR-010**: Every agent invocation site in the repository MUST carry this protection — no exposed sites.
- **FR-011**: The repository's pre-merge checks MUST fail when an agent step is added or changed without the protection, or when a ceiling is set back to its intended budget.
- **FR-012**: The run's own summary MUST state the verdict reached for each agent step, the evidence behind it, and both the counted and reported turn totals.
- **FR-013**: The verdict logic MUST be defined once and reused by every stage rather than duplicated per stage.
- **FR-014**: The verdict MUST be reachable from the transcript alone, without a network call, an additional agent invocation, or elevated permissions.
- **FR-015**: The verdict logic MUST be exercised against representative transcripts — at minimum a healthy-but-rejected run, a genuinely errored run, an exhausted run, a schema-violating run, and an unreadable transcript — with mutations proving the checks can fail.
- **FR-016**: This feature MUST deliver both the shared agent-verdict evaluation and the rescue wiring that consumes it, on every agent invocation site — including the agent steps that today have no rescue wiring at all. The separately tracked rescue work (#193) is subsumed by this feature rather than landing alongside it, so no agent step is left exposed while the two changes wait on each other.
- **FR-017**: When an agent run is healthy but its counted main-loop turns reach or exceed its intended budget, the stage MUST continue and report the over-budget condition loudly — in the run's own summary, and additionally on the lifecycle issue for stages that post there — and MUST NOT fail the run on the over-budget condition alone. The intended budget is therefore an observability instrument, and the runaway ceiling is the only hard stop.
- **FR-018**: A report of the counter mismatch addressed to `anthropics/claude-code-action` MUST be drafted and committed as part of this feature, carrying the evidence this repository already holds — both observed occurrences, the measured divergence sample, and the numbers from the run that prompted this issue. Filing it upstream remains a human act that is explicitly optional and at the maintainers' discretion; the feature is complete once the drafted report is committed, whether or not it is ever filed.

### Key Entities

- **Agent run verdict**: The classification of a finished agent step as healthy, genuinely failed, or unclassifiable. Derived solely from the run's own transcript; consumed by the stage to decide whether to continue or fail.
- **Counted turns**: Distinct main-loop agent responses in a transcript, excluding subagent activity. The counter that the intended budget is enforced and reported against.
- **Reported turns**: The turn total the run's terminal result record carries. Known to run 1.0x–2.3x higher than counted turns in this repository's history; used only for display and diagnosis, never for enforcement.
- **Intended turn budget**: The per-step turn allowance the stage declares and means — the number a maintainer tunes and the number reported against.
- **Runaway ceiling**: The larger bound actually handed to the agent invocation, sized to absorb counter divergence, whose only job is to stop an unbounded agent.
- **Agent call site**: One agent invocation in a workflow, with its model, intended budget, ceiling, and verdict handling. The unit that coverage is asserted over.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero pipeline runs end in failure while their agent run's transcript shows a successful terminal result and counted turns within the intended budget — measured across all runs after adoption, against a baseline of two such failures in the 31 hours before this issue was filed.
- **SC-002**: 100% of agent call sites carry the protection (0 exposed), verified by enumeration rather than inspection.
- **SC-003**: 100% of stage runs whose agent completes healthily produce their full human-facing output — lifecycle callout, label transition, and summary — with no maintainer having to post a callout by hand.
- **SC-004**: 100% of genuinely failed agent runs still fail their stage, with the failure message naming the actual cause; no genuine failure is reclassified as spurious.
- **SC-005**: A change that adds an agent step without the protection, or that lowers a ceiling to its intended budget, is rejected before merge 100% of the time.
- **SC-006**: The turn total a run reports against its budget equals the counted main-loop total in 100% of runs where counting succeeds, so the enforced number and the reported number are the same number.
- **SC-007**: A maintainer can determine, from a single run's summary alone and without opening the transcript, which verdict was reached and on what evidence.
- **SC-008**: No agent step's maximum possible spend increases beyond the ceiling explicitly declared for it, and each ceiling is stated in the stage's configuration.
- **SC-009**: Zero runs are failed for reaching or exceeding their intended turn budget while their agent completed healthily; 100% of such runs instead carry an over-budget report in the run summary, and on the lifecycle issue for stages that post there.
- **SC-010**: The drafted upstream report is present in the repository when the feature is complete, and feature completion does not depend on anyone having filed it.

## Assumptions

- The staged issue-comments file for this intake was empty; the specification is assembled from the issue title and body alone.
- The upstream comparison in `anthropics/claude-code-action` stays as shipped for the foreseeable future, and there is no opt-out short of omitting the turn cap entirely — omitting it is rejected here because the project requires every agent step to run under a bounded budget.
- The observed divergence between the reported and counted counters is 1.0x–2.3x, always upward, based on this repository's own history. A ceiling of roughly 2.5x the intended budget is assumed as the default sizing, subject to the plan stage confirming it against the full sample.
- The transcript already uploaded by each agent step is sufficient evidence for the verdict; no additional artifact, token, or network access is required.
- The counting rules the existing metrics summary implements — distinct response identifiers, subagent responses excluded — are correct and are the rules the budget is enforced against; this feature reuses them rather than defining new ones.
- The requirement that every agent step declare an explicit model and a bounded turn cap continues to hold, satisfied by the ceiling; the intended budget is an additional declaration, not a replacement.
- The 19 call sites enumerated in the issue are the complete set as of 2026-08-16, spanning both the published stage workflows and this repository's own automation; the plan stage re-enumerates rather than trusting the list.
- The `implement` stage's dependence on a budget-exhaustion signal is preserved in whatever form the exhaustion outcome takes.
- Runs already failed by this defect are not retroactively repaired; the feature changes future runs only.
- The rescue wiring tracked separately by #193 is delivered here rather than independently, so #193 is closed by this feature and nothing in the pipeline depends on the two landing in a particular order.

## Out of Scope

- The compound-Bash permission denials that inflated this run's counters — a separate defect class, already addressed elsewhere.
- Any change to how many turns a stage is intended to get; this feature changes which counter is enforced and what happens on rejection, not the tuning of the budgets themselves.
- Retroactive re-running or repair of runs that this defect already failed.
- Changes to the watchdog's pause behaviour, which is why this occurrence went unnoticed but is not why it happened.
- Actually filing the drafted upstream report, and anything that follows from it upstream — an optional human act at the maintainers' discretion, never a gate on this feature's completion.
- Designing the local fix for later removal should the upstream comparison change; the fix must stay correct in that event, but no removal path is a deliverable here.
