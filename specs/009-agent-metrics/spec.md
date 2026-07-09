# Feature Specification: Surface Per-Run Agent Metrics for Pipeline Tuning

**Feature Branch**: `spec-draft/009-agent-metrics`

**Created**: 2026-07-09

**Status**: Draft

**Input**: User description: "Surface per-run agent metrics (turns, tokens, cost) for pipeline tuning. Every pipeline stage already uploads its full Claude execution transcript as the `claude-execution-output` artifact, whose final `result` record contains exactly the tuning signals we care about — e.g. the stage-2 plan run for spec 003: num_turns: 36 (of the 80 budgeted), duration_ms: 308648, total_cost_usd: 1.27, token usage, and a per-model breakdown. But today reaching it means downloading an artifact per run and parsing JSON by hand. What I want: make these metrics visible enough to drive decisions about the pipeline's knobs and levers — --max-turns budgets, model tiering (constitution II), and iteration caps. Ideas, roughly in increasing ambition: (1) Per-run visibility: each agent step is followed by a deterministic step that parses claude-execution-output.json and writes a one-line metrics summary (model, turns used/budgeted, duration, tokens, cost) to $GITHUB_STEP_SUMMARY. (2) Per-feature rollup: the lifecycle issue gets a compact metrics line appended to each stage's status comment (or one rolling table), so a feature's total spend is legible from the issue alone (constitution III). (3) Trend data: append one JSON line per agent run (stage, spec, model, turns, tokens, cost, outcome) to a durable location (e.g. a metrics branch or workflow summary index) so budgets can be tuned from history rather than anecdotes. Item 1 alone would already be valuable. Turn-budget warnings (e.g. flag runs that used >80% of --max-turns) would help spot stages about to start failing. Out of scope: dashboards or external services — GitHub-native only (constitution III)."

## User Scenarios & Testing *(mandatory)*

<!--
  User stories are prioritized as independently testable slices. P1 is the MVP:
  per-run visibility. P2 and P3 build on it toward per-feature and cross-feature legibility.
-->

### User Story 1 - Each agent run reports its own metrics where the run is watched (Priority: P1)

After any pipeline stage that invokes the Claude agent finishes, a maintainer watching that workflow run sees a concise, human-readable metrics summary for the run — the model used, turns consumed against the turn budget, wall-clock duration, token usage, and cost — right in the run's own summary, without downloading any artifact or reading raw JSON. When a run consumed most of its turn budget, the summary calls that out so the maintainer can spot a stage that is close to exhausting its budget before it starts failing.

**Why this priority**: This is the entire floor of value the requester called out ("Item 1 alone would already be valuable"). The tuning signals already exist in the execution transcript; the only missing thing is making them legible at the point a maintainer is already looking — the workflow run. Turn-budget warnings turn that legibility into an early-warning signal for stages about to hit their cap. Everything else in this feature aggregates or persists the same per-run numbers, so this story is the foundation the others build on.

**Independent Test**: Run any agent-invoking stage to completion and confirm its run summary shows model, turns used against the budget, duration, tokens, and cost derived from that run's execution transcript — and that a run which used a high fraction of its turn budget is visibly flagged — all without opening the uploaded artifact.

**Acceptance Scenarios**:

1. **Given** an agent stage that has just finished, **When** the maintainer opens that workflow run, **Then** a one-line-per-run metrics summary shows the model, turns used and budgeted, duration, token usage, and cost for the run.
2. **Given** a completed agent run that consumed at or above the warning fraction of its turn budget, **When** its metrics summary is produced, **Then** the summary visibly flags the run as close to its turn budget.
3. **Given** a completed agent run that consumed well under the warning fraction of its turn budget, **When** its metrics summary is produced, **Then** no turn-budget warning is shown.
4. **Given** a stage whose execution transcript is missing or unparseable, **When** the metrics summary step runs, **Then** it reports that metrics were unavailable and does not fail the stage.

---

### User Story 2 - A feature's total spend is legible from its lifecycle issue alone (Priority: P2)

A maintainer following a specification through the pipeline can read that specification's cumulative agent spend — per stage and in total — directly from its lifecycle issue, without opening individual workflow runs. As each agent stage reports its status to the lifecycle issue, it carries that run's compact metrics with it, so the issue accumulates a legible record of how many turns, tokens, and dollars the specification has cost across its stages.

**Why this priority**: Constitution III requires a specification's lifecycle to be legible from its issue alone. Per-run summaries (Story 1) live on individual workflow runs, which scatter the picture; rolling the same numbers up onto the lifecycle issue is what makes a specification's total cost visible in one place. It depends on the per-run extraction from Story 1 and so follows it.

**Independent Test**: Take a specification through more than one agent stage and confirm its lifecycle issue shows each stage's metrics and the running total, so the specification's spend is readable from the issue without opening any workflow run.

**Acceptance Scenarios**:

1. **Given** an agent stage that reports its status to a specification's lifecycle issue, **When** that status is posted, **Then** it includes the stage's compact metrics (model, turns, tokens, cost).
2. **Given** a specification that has passed through several agent stages, **When** a maintainer reads its lifecycle issue, **Then** the specification's per-stage metrics and cumulative total are legible from the issue alone.

---

### User Story 3 - Budgets can be tuned from history instead of anecdotes (Priority: P3)

A maintainer deciding where to set turn budgets, which model tier a stage should use, or how many implement/converge iterations to allow can look at a durable, GitHub-native record of past agent runs — one entry per run capturing stage, specification, model, turns, tokens, cost, and outcome — rather than reasoning from one or two remembered examples. The record accumulates across features and stages so tuning decisions rest on a trend.

**Why this priority**: The requester's stated goal is to drive decisions about the pipeline's knobs and levers from data. Per-run and per-feature views (Stories 1 and 2) answer "what did this run/feature cost"; a durable cross-feature record answers "what do runs of this stage typically cost," which is what budget and tiering decisions actually need. It is the most ambitious tier and depends on the same per-run extraction, so it comes last.

**Independent Test**: Run agent stages across more than one specification and confirm that a durable GitHub-native record gains one structured entry per run, capturing stage, specification, model, turns, tokens, cost, and outcome, queryable after the runs complete.

**Acceptance Scenarios**:

1. **Given** an agent run has completed, **When** its metrics are recorded, **Then** one structured entry describing that run (stage, specification, model, turns, tokens, cost, outcome) is appended to the durable record.
2. **Given** agent runs across several specifications and stages, **When** a maintainer inspects the durable record, **Then** it contains one entry per run and can be read to compare typical spend across stages.

---

### Edge Cases

- The execution transcript artifact is missing, empty, truncated, or not valid JSON: the metrics step reports that metrics were unavailable for that run and MUST NOT fail the stage or block the pipeline (see FR-009).
- The final `result` record is present but missing some fields (e.g. no per-model breakdown, or cost absent): the summary reports the fields it has and marks the rest as unavailable rather than erroring.
- A stage runs the agent more than once (e.g. an implement ⟲ converge iteration): each agent invocation is treated as its own run with its own metrics, and the per-feature rollup and durable record reflect every run, not just the last.
- A stage was configured without a discoverable turn budget: the summary still reports turns used and simply omits the used/budgeted ratio and any turn-budget warning rather than inventing a budget.
- The stage did not invoke the agent at all (deterministic-only stage): no metrics summary is expected and the absence is not an error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: After an agent invocation in a pipeline stage completes, the system MUST extract that run's metrics — at least model, turns used, turn budget, duration, token usage, and cost — from the stage's own execution transcript, deterministically and without human intervention.
- **FR-002**: The system MUST present each agent run's extracted metrics as a concise, human-readable summary attached to that stage's own workflow run, so a maintainer can read them without downloading the execution artifact or parsing raw JSON.
- **FR-003**: The per-run summary MUST express turns as the amount used against the run's turn budget (used and budgeted), so a maintainer can see how close the run came to its cap.
- **FR-004**: The system MUST flag any run that consumed at or above a warning fraction of its turn budget as close to that budget, and MUST NOT flag runs below that fraction. The warning fraction defaults to 80% of the turn budget.
- **FR-005**: When a run's turn budget cannot be determined, the system MUST still report turns used and MUST omit the used/budgeted ratio and the turn-budget warning rather than fabricating a budget.
- **FR-006**: When a specification's agent stage reports its status to that specification's lifecycle issue, that report MUST carry the stage's compact metrics (model, turns, tokens, cost), and the specification's per-stage metrics and cumulative total MUST be legible from the lifecycle issue alone. [NEEDS CLARIFICATION: should the per-feature rollup be a single rolling metrics table maintained on the issue, or a compact metrics line appended to each stage's existing status comment?]
- **FR-007**: The system MUST append one structured entry per agent run — capturing at least stage, specification, model, turns, tokens, cost, and outcome — to a durable, GitHub-native record, so past runs can be compared to tune budgets, model tiers, and iteration caps. [NEEDS CLARIFICATION: which durable GitHub-native store holds the trend record — a dedicated metrics branch, an aggregated workflow-summary index, or another GitHub-native location? The requester lists a metrics branch and a workflow summary index as examples.]
- **FR-008**: When a stage invokes the agent more than once (for example across implement/converge iterations), the system MUST treat each invocation as a distinct run with its own metrics, and the per-feature rollup and durable record MUST reflect every run rather than only the last.
- **FR-009**: If a run's execution transcript is missing, empty, truncated, or unparseable, the system MUST report that metrics were unavailable for that run and MUST NOT fail the stage, alter the stage's own outcome, or block the pipeline.
- **FR-010**: The system MUST remain GitHub-native: metrics surfacing MUST use the run summary, lifecycle issue, and repository-resident storage only, with no external dashboards or services and no dependency on anything outside the repository's own GitHub surfaces.
- **FR-011**: Metrics extraction and surfacing MUST be read-only with respect to the agent's work: they MUST derive from the already-produced execution transcript and MUST NOT re-run the agent or change any stage's behavior or result.
- **FR-012**: The system MUST scope which of the three ambition tiers (per-run summary, per-feature rollup, durable trend record) are delivered by this feature. [NEEDS CLARIFICATION: is the committed scope the per-run summary only (tier 1), tiers 1 and 2, or all three tiers? The requester notes tier 1 alone is already valuable.]

### Key Entities

- **Agent run**: A single invocation of the Claude agent within a pipeline stage. It is the unit every metric is attached to; a stage may contain more than one.
- **Execution transcript**: The full Claude execution output each stage already uploads (the `claude-execution-output` artifact), whose final `result` record is the authoritative source of a run's metrics. This feature reads it and never produces it.
- **Run metrics**: The extracted tuning signals for one agent run — model, turns used, turn budget, duration, token usage, cost, and outcome — and any per-model breakdown available.
- **Turn budget**: The bounded turn cap (`--max-turns`) the stage set for the run; the denominator the turn-budget warning is measured against.
- **Per-feature rollup**: The accumulation of a specification's per-stage run metrics onto its lifecycle issue, making the specification's total spend legible from the issue.
- **Trend record**: The durable, append-only, GitHub-native collection of one entry per agent run across all specifications and stages, used to tune the pipeline's budgets and tiers from history.
- **Lifecycle issue**: The per-specification issue every stage reports its status to; the per-feature rollup lives here.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A maintainer can read a completed agent run's model, turns-used-against-budget, duration, tokens, and cost from that run's own workflow summary without downloading any artifact or reading raw JSON.
- **SC-002**: Every agent run that used at or above the warning fraction of its turn budget is visibly flagged in its run summary, and no run below that fraction is flagged, so stages approaching their turn cap are spotted before they fail.
- **SC-003**: For a specification that has passed through multiple agent stages, its per-stage metrics and cumulative spend are legible from its lifecycle issue alone, with no workflow run opened.
- **SC-004**: After a set of agent runs across more than one specification, the durable trend record contains exactly one entry per run, each carrying stage, specification, model, turns, tokens, cost, and outcome.
- **SC-005**: A missing or unparseable execution transcript never causes a stage to fail or the pipeline to block; the affected run's metrics are reported as unavailable instead.
- **SC-006**: No metrics surfacing depends on any service or dashboard outside the repository's own GitHub surfaces.

## Assumptions

- "Pipeline stage," "lifecycle issue," "specification," "the pipeline's own automation," and the model-tiering and turn-budget conventions refer to the same concepts established by the existing pipeline stages and constitution (II, III); this feature adds no new such concepts and only makes existing per-run signals visible.
- Every agent-invoking stage already uploads a `claude-execution-output` transcript whose final `result` record contains the metrics of interest; this feature consumes that transcript and does not change how it is produced.
- The default turn-budget warning fraction is 80%, matching the requester's example; the exact threshold is a tunable default, not a fixed requirement.
- Metrics are informational: they inform human tuning decisions and never automatically change a stage's budget, model, or outcome.
- The durable trend record and per-feature rollup are additive reporting surfaces; they do not gate, block, or reshape any stage's execution.
