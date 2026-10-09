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

## Clarifications

### Session 2026-10-09

- Q: Which candidates beyond watchdog diagnose are in scope? → A: Only a per-lifecycle `model:haiku` opt-in for implement. `model:opus` wins if both labels are present; the label affects implement only; a Haiku cycle escalates to `claude-sonnet-5-5` via the existing `escalation-model` input; its turn budget goes through `max-turns`. pr-conversation classify-and-announce/act and rebase become later specs.
- Q: What bar decides a step is ready for Haiku, and what makes a trial window? → A: Diagnose shadow: over ≥200 compared runs, ≥95% filing-decision agreement, ≥90% class agreement on shared findings, refused+exhausted+malformed ≤2% (errors reported separately); fewer than 200 runs reports "sample too small". Implement: no numeric bar; per-lifecycle comparison against the median Sonnet lifecycle.
- Q: Is the trial bound self-expiring or manual? → A: Self-expiring: the diagnose shadow runs at most 14 days or 300 compared runs, whichever first, then turns itself off; the single switch stops it sooner. Implement trials are bounded by the owner applying `model:haiku` one lifecycle at a time.
- Corrections from the same reply: the constitution amendment is MINOR 2.3.1 → 2.4.0 (not PATCH), covering both the model ID and the opt-in, and Principle II states how a trial shadow fits; the FR-006 check ignores `.github/scripts/` gate fixtures that hold model strings as data and the helper ID `claude-haiku-4-5-20251001`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The Haiku tier names the current Haiku model (Priority: P1)

As the repository owner, I want every place that runs or documents the Haiku tier to name `claude-haiku-5-5` instead of `claude-haiku-4-5`, so the constitution, the wrappers, the stages and the docs all describe the model that actually runs.

**Why this priority**: It is a self-contained correctness fix with the shape of #970 and is useful even if no trial ever runs. Its constitution change rides in the single MINOR amendment (2.3.1 → 2.4.0) that also adds the implement opt-in (FR-003).

**Independent Test**: Search the live tree (excluding merged historical spec documents) for `claude-haiku-4-5` as a pipeline-chosen model and find none; run each Haiku-tier step once and see `claude-haiku-5-5` recorded as its model in the metrics record.

**Acceptance Scenarios**:

1. **Given** the repository variable for the summary model is unset, **When** implement's progress comment, finalize's summary or cleanup's summary runs, **Then** it runs on `claude-haiku-5-5`.
2. **Given** an auto-update-spec-kit run reaches the T026 reply classifier, **When** it classifies a reply, **Then** it runs on `claude-haiku-5-5`.
3. **Given** the constitution is amended for this change, **When** a reader opens Principle II, **Then** the Haiku tier names `claude-haiku-5-5`, the per-lifecycle `model:haiku` opt-in for implement is described, a trial shadow is described as declaring an explicit Haiku model and acting on nothing, the version is 2.4.0 (MINOR), and a Sync Impact Report is added to the top of `constitution-history.md`.
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

### User Story 3 - Implement can be trialled on Haiku 5.5 per lifecycle (Priority: P3)

As the repository owner, I want to opt a single lifecycle into running implement on Haiku 5.5 with a `model:haiku` label, with its outcomes landing in the same place as the diagnose shadow's, so I can decide implement's tier from evidence.

**Why this priority**: Implement carries more risk (its output acts on branches and PRs) and more design surface (turn budget and retry ladder), so it follows the low-risk shadow.

**Scope**: The diagnose shadow (Story 2) and this implement opt-in are the only trials in this spec. pr-conversation's classify-and-announce and act steps (re-testing spec 033 D2) and rebase are out of scope and become later specs.

**Independent Test**: Apply `model:haiku` to one lifecycle, let implement run one cycle, and confirm its metrics/trial record shows `claude-haiku-5-5` with turns, tokens, cost and outcome.

**Acceptance Scenarios**:

1. **Given** a lifecycle issue labelled `model:haiku` (and not `model:opus`), **When** implement runs, **Then** wrapper 5's model resolution chooses `claude-haiku-5-5` for the cycle, with the turn budget passed through implement's existing `max-turns` input, and the wrapper passes `claude-sonnet-5-5` as `escalation-model` so the one-tier-up retry goes to Sonnet. implement.yml gains no extra escalation rung; Opus stays reachable only through `model:opus`.
2. **Given** a lifecycle issue labelled both `model:haiku` and `model:opus`, **When** implement runs, **Then** `model:opus` wins.
3. **Given** a `model:haiku` label on a lifecycle (or mirrored onto its PR by finalize), **When** pr-conversation or the board loop runs, **Then** they ignore it and run on their current tier.
4. **Given** a Haiku implement cycle finishes, **When** its record is written, **Then** a record captures model, turns, tokens, cost and outcome, comparable with Sonnet cycles' records (this may be the cycle's normal metrics record if it carries what FR-011 needs; planning decides).
5. **Given** no lifecycle carries `model:haiku`, **When** implement runs, **Then** it runs on its current tier with no behaviour change.

---

### User Story 4 - The owner decides from a summary of trial evidence (Priority: P3)

As the repository owner, I want trial evidence summarised per step against agreed criteria, so the decision to move a step's default to Haiku (a MINOR constitution amendment) is mine and is made from data.

**Why this priority**: The trial has no value unless its evidence is readable; but no default moves within this spec.

**Independent Test**: After a trial window, produce the per-step summary from the metrics branch's records alone (FR-015) and check every figure against the records.

**Acceptance Scenarios**:

1. **Given** trial records exist for a step, **When** the summary is produced, **Then** it reports runs, agreement or success rate, refusal count, turn-exhaustion count, median turns and cost per run on each model (a run's model is its record's top-level `model`, per FR-011), computed deterministically.
2. **Given** at least 200 compared diagnose shadow runs, **When** the summary is produced, **Then** it states "meets" or "misses" against the diagnose bar (FR-017); **given** fewer than 200 when the window ends, it states that the sample is too small instead.
3. **Given** a Haiku implement lifecycle, **When** the summary is produced, **Then** it reports, against the median Sonnet lifecycle on the metrics branch, cycles to converge, escalations and the tier each went to, refusals and turn exhaustions, and total cost including retries — with no numeric meets/misses verdict.
4. **Given** the summary meets or misses the agreed bar, **When** the owner reads it, **Then** no default has moved; any move is a separate owner decision.

---

### Edge Cases

- **Refusal on a Haiku step** (Haiku 5.5's safety classifiers can return `stop_reason: "refusal"` with no server-side fallback; this repository's agents routinely read token, credential and permission code): a summary step degrades exactly as any failed summary does today; T026 fails closed (no action it gates is taken); a trial records the refusal as its own outcome, never as a quality loss or a disagreement.
- **Haiku shadow exceeds its turn budget**: recorded as exhausted; the Opus diagnose result is unaffected.
- **Prompt crosses 100K tokens mid-run**: costs are recorded per request as reported; the trial record does not re-price.
- **Requests Haiku 5.5 rejects with a 400** (manual thinking budgets, non-default sampling parameters, assistant prefill, older computer-use tool version, edited history with thinking blocks): planning confirms no workflow sets any of them; if one does, it is removed for the Haiku path.
- **The pinned agent action does not accept `claude-haiku-5-5`**: planning confirms acceptance before any model ID changes; if it is not accepted, the upgrade is blocked rather than silently falling back.
- **Usage-window pressure**: trials share the usage window with live lifecycles; a trial must be stoppable by a single switch without touching live behaviour, and live implements stay at three or fewer.
- **Claude Code's own internal Haiku calls** (a small `claude-haiku-5-5` entry in `per_model`; through early October 2026 it reported as `claude-haiku-4-5-20251001`): not chosen by the pipeline and out of scope. Because the helper now reports under the same ID as the Haiku tier, every Sonnet and Opus run's record carries a `claude-haiku-5-5` `per_model` entry (intake run 37869073118 and clarify run 37872146619 on #972, about $0.0004 each). No check, record or summary this spec adds may count such an entry as a Haiku-tier or trial run (FR-011).

## Requirements *(mandatory)*

### Functional Requirements

**Haiku tier upgrade (Story 1)**

- **FR-001**: Every pipeline-chosen use of `claude-haiku-4-5` in stage workflows, wrapper fallbacks and auto-update-spec-kit MUST become `claude-haiku-5-5`.
- **FR-002**: T026's reply classifier model MUST NOT remain silently hardcoded to a superseded ID; it MUST name `claude-haiku-5-5`. Whether it becomes a declared input is a planning decision; if it does, the new input is a deliberate widening of the published contract (Principle VII).
- **FR-003**: Principle II MUST name `claude-haiku-5-5` for the Haiku tier, describe the per-lifecycle `model:haiku` implement opt-in (FR-014), and state that a trial shadow declares an explicit Haiku model and acts on nothing (so the diagnose shadow does not read as running against the diagnose carve-out). This is one MINOR amendment (2.3.1 → 2.4.0) covering both the model ID and the opt-in, with its Sync Impact Report moved to the top of `constitution-history.md` in the same commit. The amendment is merged by a human (Principles V and X): it MUST NOT reach `main` through the lifecycle pull request merge; planning decides how (e.g. a separate PR against `main`, as spec 062 did).
- **FR-004**: `docs/setup.md`, `docs/adoption.md` and `docs/architecture.md` MUST name `claude-haiku-5-5` for the Haiku tier.
- **FR-005**: The gate suite MUST stay green after the change. No existing gate checks the Haiku tier's model ID (#970 changed no gate); the gate scripts and fixtures under `.github/scripts/` that name `claude-haiku-4-5` (e.g. `verify-metrics-summary-record-emission.py`'s multi-model case and `fixtures/metrics-record-schema/valid-multi-model-sums-correct.json`) hold it only as transcript/record data and stay as they are, as #970 left its fixtures (FR-006).
- **FR-006**: A check MUST fail if a pipeline-chosen model reference to `claude-haiku-4-5` reappears in live workflows, wrappers, composites, the constitution or docs (`.github/workflows/`, `.github/actions/`, `.specify/memory/constitution.md`, `docs/`); after this change no mention of the string remains there, so any occurrence counts. It MUST ignore historical spec documents, `.specify/memory/constitution-history.md` (its Sync Impact Reports, including this amendment's, name the old ID by design), gate fixtures under `.github/scripts/` that hold model strings only as data (as #970 did), and Claude Code's own helper entries in `per_model` (formerly `claude-haiku-4-5-20251001`, now `claude-haiku-5-5`).
- **FR-007**: Each Haiku step MUST have defined refusal behaviour: summary steps degrade as a failed summary does today; T026 fails closed.

**Trial infrastructure (Stories 2–4)**

- **FR-008**: The watchdog MUST support an optional Haiku 5.5 shadow diagnose that runs on the same evidence as the Opus diagnose, with its own explicit model and turn budget (Principle II).
- **FR-009**: The shadow's output MUST NOT file, route, label, comment or otherwise act; only the Opus verdict acts.
- **FR-010**: Verdict comparison MUST be performed by deterministic code (Principle IX), and MUST record per-run agreement and the differing fields.
- **FR-011**: Every trial outcome MUST be recorded where metrics records already go, carrying the step, model, turns, tokens, cost and an outcome from a fixed set that distinguishes at least: agreed/succeeded, disagreed/failed, exhausted, malformed, error, refused. A run is a Haiku-tier or trial run only by its record's top-level `model` field (the model the pipeline chose), never by a `claude-haiku-5-5` entry in `per_model`: Claude Code's own helper reports under that ID on every Sonnet and Opus run. A trial record written to the metrics branch MUST satisfy the live metrics-record contract (`specs/043-durable-metrics-record/contracts/metrics-record-schema.md`): within `schema_version` 1 only additive fields, the existing `outcome` field keeping its current meaning and values, and the `per_model` sum invariant holding, or the persist collector rejects it. The shadow's record MUST be distinguishable from the acting Opus diagnose's record (its own `record_key` and label), so no existing reader of watchdog records (cost lines, the turn-budget trend collector, board status) counts it as the acting diagnose.
- **FR-012**: Trials MUST be off by default for adopters and switchable from the consuming wrapper (repository variable or label), not from ambient state inside a stage workflow (Principle VII). Any new stage input is a deliberate contract widening.
- **FR-013**: Trials MUST be bounded so they cannot consume the shared usage window unboundedly, and MUST be stoppable by a single switch. Once enabled, the diagnose shadow MUST run for at most 14 days or 300 compared runs, whichever comes first, counted deterministically, and then turn itself off; the single switch stops it sooner, and restarting a trial is a deliberate owner act. Implement trials are bounded by the owner applying `model:haiku` one lifecycle at a time, under the existing limit of three lifecycles in implement.
- **FR-014**: The only trial candidate other than the diagnose shadow is implement, opted in per lifecycle by a `model:haiku` label on the lifecycle issue. Wrapper 5's model resolution MUST choose `claude-haiku-5-5` for that lifecycle's cycles the same way `model:opus` chooses Opus; if both labels are present, `model:opus` MUST win. The label MUST affect implement only: pr-conversation and the board loop MUST ignore it, including when finalize mirrors it onto the PR. For a Haiku lifecycle the wrapper MUST pass `claude-sonnet-5-5` as `escalation-model`, so the one-tier-up retry goes to Sonnet; implement.yml gains no extra escalation rung, and Opus stays reachable only through `model:opus`. The Haiku cycle's turn budget MUST go through implement's existing `max-turns` input, with the value set in planning from data; that input also budgets the escalation retry, so the value applies to the Sonnet retry as well. pr-conversation classify-and-announce/act and rebase are out of scope.
- **FR-015**: A per-step summary of trial evidence MUST be producible deterministically from the records on the metrics branch alone (the trial records, plus the existing records that supply the Opus diagnose figures and the Sonnet implement baseline), against the agreed bar (FR-017), identifying each run's model as FR-011 does. The summary only reports.
- **FR-016**: This spec MUST NOT move any step's default model to Haiku; moving one is a later MINOR amendment on owner decision.
- **FR-017**: The trial bar ("good enough") and trial bound (FR-013) MUST be explicit before any trial runs:
  - **Diagnose shadow**: meets the bar when, over at least 200 compared runs, (a) at least 95% of runs agree with Opus on the filing decision (the same findings would be filed, or nothing would be); (b) at least 90% of the findings both verdicts raise agree on class; and (c) refused, exhausted and malformed outcomes together are at most 2% of runs. Error outcomes are reported separately and do not count toward the 2% (they are usually infrastructure, e.g. a 429 or runner fault). If the window ends before 200 compared runs, the summary reports the sample as too small rather than meets or misses. A compared run is a watchdog run on which the shadow was invoked and a trial record written; error outcomes are left out of the run count and every denominator, while refused, exhausted and malformed runs stay in and count as not agreeing under (a).
  - **Implement opt-in**: no numeric bar. For each Haiku lifecycle the summary reports, against the median Sonnet lifecycle on the metrics branch: cycles to converge; escalations and the tier each went to; refusals and turn exhaustions; and total cost including retries. The owner judges from that and from the final-PR review.

### Key Entities

- **Haiku tier**: the model tier Principle II assigns to triage, classification, labeling and summaries; this spec changes its model ID only.
- **Trial**: a bounded, opt-in period in which a candidate step also (shadow) or instead (opt-in) runs on Haiku 5.5.
- **Trial record**: one per trial run — step, model, run reference, turns, tokens, cost, outcome; lives alongside existing metrics records.
- **Verdict comparison**: deterministic result of comparing a Haiku shadow verdict with the acting Opus verdict — agree/disagree plus differing fields, or a non-verdict outcome (exhausted, malformed, error, refused).
- **Trial summary**: per-step aggregate of trial records against the agreed bar, for the owner's decision.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero pipeline-chosen references to `claude-haiku-4-5` remain in live workflows, wrappers, composites, constitution and docs (FR-006's scope and exclusions), and a check fails if one reappears.
- **SC-002**: 100% of Haiku-tier step runs after merge record `claude-haiku-5-5` as their chosen model in the record's top-level `model` field; `per_model` helper entries are not counted (FR-011).
- **SC-003**: With the diagnose shadow enabled, 100% of watchdog runs produce exactly the same filed/routed outcome as they would with it disabled.
- **SC-004**: 100% of shadow or trial runs produce a trial record with an outcome from the fixed set, including runs that are refused, exhausted or malformed.
- **SC-005**: The owner can read, for each trialled step, its runs, agreement/success rate, refusal count, exhaustion count, median turns and cost per run on each model, without reading any agent transcript.
- **SC-006**: Disabling trials via the single switch stops all trial model calls on the next run.
- **SC-007**: An enabled diagnose shadow makes no Haiku calls once 14 days or 300 compared runs have passed, whichever comes first, without any owner action.

## Assumptions

- Claude Code builds the API requests and no workflow sets manual thinking budgets, sampling parameters, prefill, or the older computer-use tool; planning confirms this.
- Planning confirms the pinned `anthropics/claude-code-action@v1` accepts `claude-haiku-5-5`.
- No workflow sets an effort level; Haiku 5.5's default (`medium`, thinking on) is accepted for both the tier upgrade and trials unless planning finds a reason otherwise.
- Haiku 5.5 tokenises the same text into ~30% more tokens than Haiku 4.5; turn budgets for existing Haiku steps are assumed sufficient and are re-checked during planning.
- The board loop's agent steps (triage-propose, route-propose, fixer, reviewer) are out of scope: their metrics records carry no model or token counts.
- Claude Code's internal Haiku calls are out of scope; the pipeline does not choose that model. They now report as `claude-haiku-5-5`, the same ID as the tier, so they are told apart by the record's top-level `model`, not by ID.
- The Opus and Sonnet tiers are unchanged (#970). Intake, clarify and plan are not trial candidates: Principle II pays for Opus at intake/clarify on purpose, and plan never stays under 100K tokens.
- Moving a step to Haiku or adding a Haiku opt-in for implement changes the tiering, which is a MINOR amendment to Principle II; adding the `model:haiku` opt-in (FR-014) is therefore a MINOR amendment (2.4.0) even though no default moves, and it carries the Haiku model-ID change with it (FR-003).
- Default trial switches are off; this repository's own wrappers enable the diagnose shadow.
- This repository's `WING_COMMANDER_SUMMARY_MODEL` variable is unset, so the summary steps follow the new wrapper fallback (SC-002); planning confirms, and if it is set to `claude-haiku-4-5` it is deleted with the change, as #970 did for `WING_COMMANDER_IMPLEMENT_MODEL`.
