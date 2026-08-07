# Feature Specification: Structured Clarification Questionnaires With a Single Content-and-Decision Artifact

**Feature Branch**: `032-structured-clarification-gate`

**Created**: 2026-08-07

**Status**: Draft

**Input**: User description: "Make the clarification questionnaire a validated structured output so its content and its post/don't-post decision come from one artifact. Today the questionnaire content (an agent-authored side-file) and the decision to post it (a deterministic grep of spec.md for `[NEEDS CLARIFICATION]`) are produced by two independent mechanisms that can silently disagree, and when they do the content is dropped without a trace. Two recorded failures: #109, where the grep pattern could never match the real marker form so the callout never fired and the authored questionnaire was dropped; and #159, where the grep fired on a spec whose subject matter *is* the marker syntax (prose mentions of the token), so a 'you still have open questions' callout was posted when the agent had actually resolved everything — and because the callouts are mutually exclusive branches, taking the wrong one silently deleted the correct 'spec PR ready' callout and its PR link. Adopt the watchdog's diagnose contract (schema-constrained agent output + deterministic read-back): the agent emits a clarifications array; a deterministic step renders the `## Question N` markdown from that array and posts the action callout iff the array is non-empty; content and decision now come from the same artifact. Keep the marker grep only as a cross-check that raises a `clarification-mismatch` warning on disagreement — the structured output, authored by the party that read the document, decides which branch runs. Tighten the cross-check to require the colon form `[NEEDS CLARIFICATION:` so prose mentions of the bare token stop crying wolf. Drop any fallback that synthesises a questionnaire from raw marker text — marker prose is never a good questionnaire. Preserve clarify's ternary outcome (none / needs-clarification / ready) with a defined landing for `none` so an absent questionnaire is not reinterpreted as an empty array. Add `clarification-mismatch` to the watchdog's step-summary sentinel set so recurrences surface as findings. Scope: intake.yml, clarify.yml, watchdog.yml; the clarify agent's early-STOP self-comment path is untouched."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An authored questionnaire is always posted or visibly failed, never silently dropped (Priority: P1)

The clarification agent finishes a stage having authored a set of open questions for the maintainer. The maintainer expects that if the agent wrote questions, those exact questions reach the lifecycle issue as an action callout — or, if something went wrong producing them, that the failure is visible. What the maintainer must never get is the current outcome of #109: the agent wrote a questionnaire, the deterministic decision step disagreed, and the questions vanished with no trace on the issue and no error in the run.

**Why this priority**: This is the core value. The whole point of a clarification gate is to surface the agent's open questions to a human; a gate that can silently discard the agent's authored questions defeats its own purpose. Binding the content and the post decision to one artifact is what makes silent loss structurally impossible, so it is P1.

**Independent Test**: Run a stage on an issue the agent will find genuinely ambiguous so it authors questions. Confirm the authored questions appear verbatim in the posted action callout. Then force the questionnaire artifact to be malformed and confirm the run surfaces a validation failure rather than posting nothing and reporting success.

**Acceptance Scenarios**:

1. **Given** an agent that authored one or more clarification questions, **When** the stage runs to completion, **Then** those questions are posted as an action callout and none are dropped.
2. **Given** an agent whose structured questionnaire is malformed or missing a required field, **When** the read-back step processes it, **Then** the run surfaces a validation failure rather than silently posting nothing.
3. **Given** an agent that authored zero questions, **When** the stage runs, **Then** no clarification-questionnaire callout is posted.

---

### User Story 2 - The party that read the document decides whether questions remain (Priority: P1)

The decision to tell a maintainer "you still have open questions" versus "your spec is ready" is driven by the agent's structured output — the signal authored by the party that actually read the specification — not by a substring scan of the document. A spec whose subject matter *is* the clarification-marker syntax (this repository routinely produces specs about its own pipeline) must not be misread as carrying open questions merely because it names the marker token in prose.

**Why this priority**: This is the #159 failure and the reason the grep cannot be the gate. When the substring scan drove the decision, a resolved spec was labelled unresolved, and — because the two callouts are mutually exclusive branches — the correct "spec PR ready" callout and its PR link were silently deleted. The maintainer was told to redo finished work and was not given the link to the work that actually needed review. Getting the deciding signal right is as important as authoring the questions, so it is also P1.

**Independent Test**: Run the stage on a spec that mentions the bare `[NEEDS CLARIFICATION]` token in requirements prose but has no genuine unresolved markers, where the agent reports zero open questions. Confirm the ready-path callout (spec PR ready, with PR link) is posted and no "open questions" callout is posted.

**Acceptance Scenarios**:

1. **Given** an agent reporting zero open questions on a spec that mentions the marker token in prose, **When** the stage decides which callout to post, **Then** it takes the ready path and posts the spec-PR-ready callout with its PR link.
2. **Given** the ready path is taken, **When** the callouts are evaluated, **Then** the spec-PR-ready callout is never suppressed by a competing clarification-questionnaire branch.
3. **Given** an agent reporting open questions on a spec with genuine unresolved markers, **When** the stage decides, **Then** it takes the questions path.

---

### User Story 3 - A content/decision disagreement is loud, not invisible (Priority: P2)

When the agent's structured output and the marker cross-check disagree, the disagreement is recorded where a human and the watchdog can see it. The maintainer's stage is still driven by the structured output, but the discrepancy leaves a trace so the defect class that produced #109 and #159 cannot recur invisibly — the watchdog missed both original instances precisely because nothing compared the spec's content against the callout that was posted.

**Why this priority**: Correctness (US1, US2) is delivered by making the structured output authoritative; this story is about detectability of the residual disagreement. It hardens the fix against regression rather than delivering the headline behavior, so it is P2.

**Independent Test**: Construct a run where the marker cross-check and the structured output disagree (for example, genuine markers remain but the agent reported zero questions). Confirm a `clarification-mismatch` warning is written to the run's step summary and that a watchdog pass over the run surfaces it as a finding.

**Acceptance Scenarios**:

1. **Given** genuine markers remain in the spec but the agent reported zero open questions, **When** the stage reconciles the two signals, **Then** the structured output still decides the branch and a `clarification-mismatch` warning is written to the step summary.
2. **Given** the agent reported open questions but the cross-check finds no genuine markers, **When** the stage reconciles, **Then** the structured output still decides and a `clarification-mismatch` warning is written.
3. **Given** a run that emitted a `clarification-mismatch` warning, **When** the watchdog inspects the run's step summaries, **Then** the mismatch is surfaced as a finding rather than passing unnoticed.

---

### User Story 4 - Clarify's three outcomes stay distinct (Priority: P2)

The clarify stage has three outcomes, not two: `none` (the agent deliberately posted nothing itself — for example a reply that answered no open question, handled by the agent's own comment), `needs-clarification`, and `ready`. Moving to a structured questionnaire must not collapse `none` into "an empty questionnaire," because an empty questionnaire on the ready path would post a spurious "review the spec PR" callout for a stage that intentionally stayed silent.

**Why this priority**: This is a correctness guardrail specific to clarify's extra outcome. Without a defined landing for `none`, the structured-output change would introduce a new spurious-callout bug in the opposite direction from the one it fixes. It matters, but only for the clarify path, so it is P2 rather than P1.

**Independent Test**: Run clarify on a reply that answers none of the open questions (the early-STOP path). Confirm no clarification-questionnaire callout and no spec-PR-ready callout are posted, and that the absent questionnaire is treated as `none`, not as an empty-array `ready`.

**Acceptance Scenarios**:

1. **Given** the clarify agent took its early-STOP path and produced no questionnaire artifact, **When** the read-back runs, **Then** the outcome is `none` and neither a questions callout nor a spec-PR-ready callout is posted.
2. **Given** the clarify agent produced a questionnaire with zero questions on a resolved spec, **When** the read-back runs, **Then** the outcome is `ready` and the spec-PR-ready callout is posted.
3. **Given** the clarify agent produced a questionnaire with questions, **When** the read-back runs, **Then** the outcome is `needs-clarification`.

---

### Edge Cases

- **Agent authored questions, no genuine markers in spec**: structured output decides → questions are posted; a `clarification-mismatch` warning is emitted because the cross-check disagreed.
- **Genuine markers remain, agent reported zero questions**: structured output decides → no questions callout (ready path); `clarification-mismatch` warning emitted. No questionnaire is synthesised from the marker text.
- **Spec whose prose names the bare `[NEEDS CLARIFICATION]` token but has no real markers**: the colon-form cross-check does not fire, so there is no false mismatch and no false "open questions" callout.
- **Malformed or missing-required structured output**: surfaced as a validation failure at the output layer, not a silent drop.
- **Clarify early-STOP (`none`)**: no questionnaire artifact; the read-back lands on `none`, not on empty-array `ready`; no callout of either kind.
- **Ready path in clarify**: the spec-PR-ready callout and its PR link are posted and cannot be deleted by a competing clarification branch.
- **Watchdog over a run that emitted `clarification-mismatch`**: the sentinel matches and the mismatch becomes a finding.
- **Question with no options and no context**: only `question` is required; the rendered callout still produces a well-formed `## Question N` block.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The intake and clarify agent steps MUST emit the clarification questionnaire as a schema-validated structured output containing a `clarifications` array, where each item carries at minimum a question and optionally supporting context and a list of answer options, and an empty array means "no open questions."
- **FR-002**: A questionnaire that fails schema validation (malformed, or missing a required field) MUST surface as a failure at the output layer rather than being silently dropped or reinterpreted as "no questions."
- **FR-003**: A deterministic step MUST read the structured output back, render the `## Question N` questionnaire markdown from that same output, and post the clarification action callout if and only if the `clarifications` array is non-empty — so the questionnaire content and the post/don't-post decision are derived from a single artifact.
- **FR-004**: The structured output MUST be the deciding signal for whether the clarification-questionnaire callout is posted; the spec.md marker scan MUST NOT gate that decision.
- **FR-005**: The marker scan MUST be retained only as a cross-check that can raise a warning; it MUST NOT change which callout branch runs.
- **FR-006**: When the structured output and the marker cross-check disagree (in either direction), the stage MUST write a `clarification-mismatch` warning to the run's step summary while still letting the structured output decide the branch.
- **FR-007**: The stage MUST NOT synthesise a fallback questionnaire from raw marker text; when the two signals disagree, no questionnaire is produced from the spec's prose.
- **FR-008**: The marker cross-check MUST require the colon form of the marker (the `[NEEDS CLARIFICATION:` prefix that precedes a real question) so that prose mentions of the bare token do not trigger a false positive, and this tightening MUST apply at every cross-check call site. [NEEDS CLARIFICATION: is the colon-form cross-check delivered as part of this feature, or assumed already shipped as the "independently shippable" precursor the follow-up comment describes, so this feature only builds on it?]
- **FR-009**: The clarify stage MUST preserve its three distinct outcomes — `none`, `needs-clarification`, and `ready` — and the read-back MUST have a defined landing for `none` (the agent's deliberate early-STOP with no questionnaire artifact) that is NOT reinterpreted as an empty `clarifications` array, so that `none` posts no callout. [NEEDS CLARIFICATION: how is `none` distinguished from `ready` once questionnaires are structured — by the absence of any structured output for that run (agent stopped before emitting) versus a present-but-empty array, or by an explicit outcome discriminator carried in the structured output itself?]
- **FR-010**: The rendered questionnaire MUST preserve the reader-facing `## Question N` format (context, question, and a suggested-answer option table) so the callout a maintainer sees is unchanged from today.
- **FR-011**: When the ready path applies, the correct next-step callout (spec PR ready, including its PR link) MUST be posted and MUST NOT be suppressed by a competing clarification-questionnaire branch.
- **FR-012**: The watchdog's step-summary sentinel set MUST include `clarification-mismatch` so a recurrence of the content/decision disagreement surfaces as a finding.
- **FR-013**: The change MUST apply to both the intake gate and the clarify follow-up gate, which today share the same file-existence-plus-grep decision mechanism.
- **FR-014**: The clarify agent's early-STOP self-comment path (the agent posting its own "the reply answered nothing" comment) MUST remain untouched; this feature covers only the deterministic callout gates.

### Key Entities *(include if feature involves data)*

- **Clarification questionnaire (structured output)**: the schema-validated artifact the agent emits; carries a `clarifications` array whose items each hold a required question and optional context and answer options. Its emptiness or non-emptiness is the deciding signal for the callout.
- **Clarification question**: one item in the array — a question, optional context, optional answer options — rendered into a `## Question N` block.
- **Marker cross-check**: a deterministic scan of spec.md for the colon-form marker, used only to detect disagreement and raise a `clarification-mismatch` warning, never to decide the branch.
- **Stage outcome**: for clarify, one of `none`, `needs-clarification`, `ready`; for intake, whether the questionnaire callout is posted. Derived from the structured output.
- **Step-summary sentinel set**: the watchdog's list of phrases whose presence in a run's step summary marks a run as carrying a defect signal; gains `clarification-mismatch`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In every run where the agent authored one or more questions, 100% of those questions appear in the posted callout — zero authored questionnaires are silently dropped (the #109 class is eliminated).
- **SC-002**: A spec that names the bare marker token in prose but has no genuine unresolved markers produces zero false "open questions" callouts and never suppresses its spec-PR-ready callout (the #159 class is eliminated).
- **SC-003**: When the ready path applies, the spec-PR-ready callout with its PR link is posted in 100% of cases — no maintainer is left without the action item that actually needs doing.
- **SC-004**: Every disagreement between the structured output and the marker cross-check emits a `clarification-mismatch` warning that the watchdog surfaces as a finding — 100% visibility for the defect class, versus the 0% detectability that let #109 and #159 pass unnoticed.
- **SC-005**: Zero questionnaires are synthesised from raw requirements prose — the fallback rung produces no callouts in any run.
- **SC-006**: A malformed questionnaire results in a visible run failure in 100% of cases rather than a silent no-post-with-success.
- **SC-007**: The clarify `none` outcome posts neither a questions callout nor a spec-PR-ready callout in 100% of early-STOP runs.

## Assumptions

- **Precedent contract**: the schema-constrained-output-plus-deterministic-read-back pattern already used by the watchdog's diagnose step is the model reused here, including its documented inline-schema quoting considerations; it is assumed to work in the same execution environments the watchdog already runs in (including Bedrock).
- **Option rendering**: the structured answer options (a list) are rendered into the existing suggested-answer table; where an item carries no options or no "implications" detail, the rendered table still produces a well-formed block (for example a Custom row), and the absence of an implications field in the structured output is acceptable.
- **Cross-check trust ordering**: the structured output is treated as the more trustworthy signal on disagreement because it is authored by the party that read the specification; the marker cross-check exists only to make disagreement visible. The fallback-questionnaire rung from the original proposal is intentionally dropped, per the follow-up comment, because marker prose is never a good questionnaire.
- **Reader-facing format is stable**: maintainers continue to see the same `## Question N` callout format; this is an internal reliability change to how the content and decision are produced, not a change to what a well-behaved run looks like.
- **Scope boundary**: only the two deterministic callout gates (intake and clarify) and the one-word watchdog sentinel addition are in scope; the clarify agent's own early-STOP comment and the rest of both workflows are untouched.
