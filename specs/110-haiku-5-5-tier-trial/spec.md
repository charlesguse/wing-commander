# Feature Specification: Haiku 5.5 Tier Upgrade and Measured Trial

**Feature Branch**: `110-haiku-5-5-tier-trial`

**Created**: 2026-10-09

**Status**: Draft

**Input**: User description: "Haiku 5.5: move the Haiku tier to claude-haiku-5-5 and trial it on small, frequent Sonnet/Opus steps" (issue #972)

## Context

Claude Haiku 5.5 (`claude-haiku-5-5`) has been released. #970 moved the Opus and Sonnet tiers to 5.5 and left the Haiku tier on `claude-haiku-4-5`. Two gaps follow:

1. **The Haiku tier names a superseded model.** `claude-haiku-4-5` is still named by the summary steps (implement's progress comment, finalize, cleanup), by the summary-model fallbacks in wrappers 5, 6 and 7, by auto-update-spec-kit's T026 reply classifier (hardcoded, not taken from an input), and by Principle II, `docs/setup.md`, `docs/adoption.md` and `docs/architecture.md`.
2. **Nobody has measured whether Haiku 5.5 can take work off Sonnet and Opus.** Haiku 5.5 is priced roughly an order of magnitude below Haiku 4.5 for prompts up to 100K tokens (input $0.10 / output $0.50 per million tokens), with a higher rate card above 100K. Several Sonnet and Opus steps are small and frequent. The two recorded reasons for keeping them off the Haiku tier — #124 (watchdog diagnose ran out of turns on Haiku 4.5; Principle II's carve-out, constitution 1.3.0) and spec 033 research.md D2 (pr-conversation's classify step judges constitution conflicts and "very small" changes) — were both about Haiku 4.5.

The requester's 28-day sizing (metrics branch, 2026-09-11 to 2026-10-08, token counts re-priced, approximate) shows: watchdog diagnose runs ~40×/day on Opus at 2 turns and ~23K-token prompts (every request on Haiku 5.5's low rate card; ~$0.08/run on Opus vs ~$0.002 on Haiku 5.5); pr-conversation's act and classify-and-announce steps stay under 100K tokens on every run (~11 runs/day on Sonnet); implement is the costliest step but ~70% of cycles exceed 100K tokens, so its saving is ~3× rather than ~20×; plan never stays under 100K. Pipeline runs and local sessions share one usage window, which is the real limit rather than dollars.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The Haiku tier names the current Haiku model (Priority: P1)

As the repository owner, I want every place that runs or documents the Haiku tier to name `claude-haiku-5-5` instead of `claude-haiku-4-5`, so the constitution, the wrappers, the stages and the docs all describe the model that actually runs.

**Why this priority**: It is a self-contained correctness fix with the shape of #970 (a constitution PATCH, 2.3.1 → 2.3.2) and is useful even if no trial ever runs.

**Independent Test**: Search the live tree (excluding merged historical spec documents) for `claude-haiku-4-5` as a pipeline-chosen model and find none; run each Haiku-tier step once and see `claude-haiku-5-5` recorded as its model in the metrics record.

**Acceptance Scenarios**:

1. **Given** the repository variable for the summary model is unset, **When** implement's progress comment, finalize's summary or cleanup's summary runs, **Then** it runs on `claude-haiku-5-5`.
2. **Given** an auto-update-spec-kit run reaches the T026 reply classifier, **When** it classifies a reply, **Then** it runs on `claude-haiku-5-5`.
3. **Given** the constitution is amended for this change, **When** a reader opens Principle II, **Then** the Haiku tier names `claude-haiku-5-5`, the version is 2.3.2 (PATCH), and a Sync Impact Report is added to the top of `constitution-history.md`.
4. **Given** the setup, adoption and architecture docs, **When** a reader looks up the Haiku tier, **Then** they name `claude-haiku-5-5`.

---

### User Story 2 - Watchdog diagnose runs a Haiku 5.5 shadow next to Opus (Priority: P2)

As the repository owner, I want a Haiku 5.5 diagnose to run alongside the Opus diagnose on the same evidence, with only the Opus verdict acting and deterministic code comparing the two, so I can decide from evidence whether #124's reason for the carve-out still holds.

**Why this priority**: Watchdog diagnose is the best-fitting candidate (high frequency, tiny prompts, entirely on the low rate card) and its shadow cannot affect live behaviour, so it is the safest and most informative trial.

**Independent Test**: Trigger a watchdog run with the shadow enabled; confirm the filed/routed outcome is identical to a run with the shadow disabled, and that a comparison record for the run appears where metrics records go.

**Acceptance Scenarios**:

1. **Given** the shadow is enabled, **When** the watchdog diagnoses a run, **Then** both an Opus and a Haiku 5.5 diagnose receive the same evidence, and only the Opus verdict files, routes or reports anything.
2. **Given** both verdicts exist, **When** the comparison step runs, **Then** deterministic code (not an agent) records whether they agree, and on which fields they differ, in a trial record alongside the existing metrics records.
3. **Given** the Haiku shadow runs out of turns, errors, produces output that fails the verdict schema, or is refused, **When** the comparison runs, **Then** the trial record names that outcome distinctly (exhausted, error, malformed, refused), and the Opus path is unaffected.
4. **Given** the shadow is disabled (the default for adopters), **When** the watchdog runs, **Then** no Haiku diagnose runs and behaviour is identical to today.

---

### User Story 3 - Further candidates can be trialled under the same evidence model (Priority: P3)

As the repository owner, I want the other candidate steps chosen during clarification to be trialled on Haiku 5.5 in a bounded way, with their outcomes landing in the same place as the diagnose shadow, so I can decide each step's tier from evidence.

**Why this priority**: These candidates carry more risk (their outputs act on PRs and branches) or more design surface (implement's turn budget and retry ladder), so they follow the low-risk shadow.

**Independent Test**: For each in-scope candidate, run one trial-enabled invocation and confirm a trial record appears with the model, turns, tokens, cost and outcome.

**Acceptance Scenarios**:

1. **Given** a lifecycle opted into a Haiku implement trial, **When** implement runs, **Then** the cycle runs on `claude-haiku-5-5` with its own turn budget, and its escalation retry goes one tier up (to Sonnet) before Opus.
2. **Given** a trial-enabled run of an in-scope step, **When** it finishes, **Then** a trial record captures model, turns, tokens, cost and outcome, comparable with the same step's non-trial records.
3. **Given** no trial is enabled, **When** any candidate step runs, **Then** it runs on its current tier with no behaviour change.

[NEEDS CLARIFICATION: Which candidates beyond watchdog diagnose are in scope for this spec — pr-conversation classify-and-announce and act (re-testing D2), rebase, and/or a per-lifecycle Haiku opt-in for implement?]

---

### User Story 4 - The owner decides from a summary of trial evidence (Priority: P3)

As the repository owner, I want trial evidence summarised per step against agreed criteria, so the decision to move a step's default to Haiku (a MINOR constitution amendment) is mine and is made from data.

**Why this priority**: The trial has no value unless its evidence is readable; but no default moves within this spec.

**Independent Test**: After a trial window, produce the per-step summary from the trial records alone and check every figure against the records.

**Acceptance Scenarios**:

1. **Given** trial records exist for a step, **When** the summary is produced, **Then** it reports runs, agreement or success rate, refusal count, turn-exhaustion count, median turns and cost per run on each model, computed deterministically.
2. **Given** the summary meets or misses the agreed bar, **When** the owner reads it, **Then** no default has moved; any move is a separate owner decision.

---

### Edge Cases

- **Refusal on a Haiku step** (Haiku 5.5's safety classifiers can return `stop_reason: "refusal"` with no server-side fallback; this repository's agents routinely read token, credential and permission code): a summary step degrades exactly as any failed summary does today; T026 fails closed (no action it gates is taken); a trial records the refusal as its own outcome, never as a quality loss or a disagreement.
- **Haiku shadow exceeds its turn budget**: recorded as exhausted; the Opus diagnose result is unaffected.
- **Prompt crosses 100K tokens mid-run**: costs are recorded per request as reported; the trial record does not re-price.
- **Requests Haiku 5.5 rejects with a 400** (manual thinking budgets, non-default sampling parameters, assistant prefill, older computer-use tool version, edited history with thinking blocks): planning confirms no workflow sets any of them; if one does, it is removed for the Haiku path.
- **The pinned agent action does not accept `claude-haiku-5-5`**: planning confirms acceptance before any model ID changes; if it is not accepted, the upgrade is blocked rather than silently falling back.
- **Usage-window pressure**: trials share the usage window with live lifecycles; a trial must be stoppable by a single switch without touching live behaviour, and live implements stay at three or fewer.
- **Claude Code's own internal Haiku calls** (`claude-haiku-4-5-20251001` in `per_model`): not chosen by the pipeline and out of scope; they must not be counted as a pipeline-chosen Haiku 4.5 use by any check this spec adds.

## Requirements *(mandatory)*

### Functional Requirements

**Haiku tier upgrade (Story 1)**

- **FR-001**: Every pipeline-chosen use of `claude-haiku-4-5` in stage workflows, wrapper fallbacks and auto-update-spec-kit MUST become `claude-haiku-5-5`.
- **FR-002**: T026's reply classifier model MUST NOT remain silently hardcoded to a superseded ID; it MUST name `claude-haiku-5-5`. Whether it becomes a declared input is a planning decision; if it does, the new input is a deliberate widening of the published contract (Principle VII).
- **FR-003**: Principle II MUST name `claude-haiku-5-5` for the Haiku tier, as a PATCH amendment (2.3.1 → 2.3.2) with its Sync Impact Report moved to the top of `constitution-history.md` in the same commit.
- **FR-004**: `docs/setup.md`, `docs/adoption.md` and `docs/architecture.md` MUST name `claude-haiku-5-5` for the Haiku tier.
- **FR-005**: The existing check that guards metrics/summary emission and any fixtures that name the Haiku tier model MUST be updated consistently so the gate suite stays green and still fails on a drifted copy.
- **FR-006**: A check MUST fail if a pipeline-chosen model reference to `claude-haiku-4-5` reappears in live workflows, wrappers or docs (historical spec documents excluded).
- **FR-007**: Each Haiku step MUST have defined refusal behaviour: summary steps degrade as a failed summary does today; T026 fails closed.

**Trial infrastructure (Stories 2–4)**

- **FR-008**: The watchdog MUST support an optional Haiku 5.5 shadow diagnose that runs on the same evidence as the Opus diagnose, with its own explicit model and turn budget (Principle II).
- **FR-009**: The shadow's output MUST NOT file, route, label, comment or otherwise act; only the Opus verdict acts.
- **FR-010**: Verdict comparison MUST be performed by deterministic code (Principle IX), and MUST record per-run agreement and the differing fields.
- **FR-011**: Every trial outcome MUST be recorded where metrics records already go, carrying the step, model, turns, tokens, cost and an outcome from a fixed set that distinguishes at least: agreed/succeeded, disagreed/failed, exhausted, malformed, error, refused.
- **FR-012**: Trials MUST be off by default for adopters and switchable from the consuming wrapper (repository variable or label), not from ambient state inside a stage workflow (Principle VII). Any new stage input is a deliberate contract widening.
- **FR-013**: Trials MUST be bounded so they cannot consume the shared usage window unboundedly, and MUST be stoppable by a single switch.
- **FR-014**: Each in-scope trial candidate other than diagnose MUST be opt-in per run or per lifecycle (for implement, a lifecycle label analogous to `model:opus`), with its own explicit turn budget; an implement Haiku cycle's escalation retry MUST go to Sonnet before Opus.
- **FR-015**: A per-step summary of trial evidence MUST be producible deterministically from the trial records alone, against the agreed bar.
- **FR-016**: This spec MUST NOT move any step's default model to Haiku; moving one is a later MINOR amendment on owner decision.
- **FR-017**: The trial bar ("good enough") and trial bound MUST be explicit before any trial runs. [NEEDS CLARIFICATION: What bar decides that a step is ready to move to Haiku — e.g. diagnose verdict agreement rate with Opus, refusal and exhaustion ceilings — and how many runs (or how many days) make a trial window?]

[NEEDS CLARIFICATION: Does the trial bound mean a fixed run count/day window after which trials switch themselves off, or an open-ended trial the owner switches off manually?]

### Key Entities

- **Haiku tier**: the model tier Principle II assigns to triage, classification, labeling and summaries; this spec changes its model ID only.
- **Trial**: a bounded, opt-in period in which a candidate step also (shadow) or instead (opt-in) runs on Haiku 5.5.
- **Trial record**: one per trial run — step, model, run reference, turns, tokens, cost, outcome; lives alongside existing metrics records.
- **Verdict comparison**: deterministic result of comparing a Haiku shadow verdict with the acting Opus verdict — agree/disagree plus differing fields, or a non-verdict outcome (exhausted, malformed, error, refused).
- **Trial summary**: per-step aggregate of trial records against the agreed bar, for the owner's decision.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero pipeline-chosen references to `claude-haiku-4-5` remain in live workflows, wrappers, constitution and docs, and a check fails if one reappears.
- **SC-002**: 100% of Haiku-tier step runs after merge record `claude-haiku-5-5` as their chosen model.
- **SC-003**: With the diagnose shadow enabled, 100% of watchdog runs produce exactly the same filed/routed outcome as they would with it disabled.
- **SC-004**: 100% of shadow or trial runs produce a trial record with an outcome from the fixed set, including runs that are refused, exhausted or malformed.
- **SC-005**: The owner can read, for each trialled step, its runs, agreement/success rate, refusal count, exhaustion count, median turns and cost per run on each model, without reading any agent transcript.
- **SC-006**: Disabling trials via the single switch stops all trial model calls on the next run.

## Assumptions

- Claude Code builds the API requests and no workflow sets manual thinking budgets, sampling parameters, prefill, or the older computer-use tool; planning confirms this.
- Planning confirms the pinned `anthropics/claude-code-action@v1` accepts `claude-haiku-5-5`.
- No workflow sets an effort level; Haiku 5.5's default (`medium`, thinking on) is accepted for both the tier upgrade and trials unless planning finds a reason otherwise.
- Haiku 5.5 tokenises the same text into ~30% more tokens than Haiku 4.5; turn budgets for existing Haiku steps are assumed sufficient and are re-checked during planning.
- The board loop's agent steps (triage-propose, route-propose, fixer, reviewer) are out of scope: their metrics records carry no model or token counts.
- Claude Code's internal Haiku calls are out of scope; the pipeline does not choose that model.
- The Opus and Sonnet tiers are unchanged (#970). Intake, clarify and plan are not trial candidates: Principle II pays for Opus at intake/clarify on purpose, and plan never stays under 100K tokens.
- Moving a step to Haiku or adding a Haiku opt-in for implement changes the tiering, which is a MINOR amendment to Principle II; adding an opt-in (FR-014) is therefore a MINOR amendment even though no default moves.
- Default trial switches are off; this repository's own wrappers enable the diagnose shadow.
