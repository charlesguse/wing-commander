# Feature Specification: Prompt Metrics Records for Pipeline-Dispatched Runs

**Feature Branch**: `120-dispatched-run-metrics`

**Created**: 2026-10-24

**Status**: Draft

**Input**: User description: "metrics-persist: runs dispatched with github.token never fire the workflow_run trigger, so implement and finalize records wait for the daily sweep" (lifecycle issue #1055, routed from #1053 by board-loop as spec-shaped).

## Background

Implement and pr-conversation start the next stage run using the workflow's
own built-in token: the next implement cycle, finalize, and a fold's
implement re-drive. Those runs' actor is `github-actions[bot]`. GitHub does
not start workflows from events caused by that token, so when these runs
complete, the metrics persistence wrapper's completion trigger never fires
for them. Their metrics records are written only by the daily 06:37 UTC
sweep.

Spec 058 FR-030(a) keeps the live completion trigger for the stages "whose
records are read back promptly", and lists `implement` and `finalize` among
them. In practice that promise holds only when a person dispatches the run.

Evidence from lifecycle #1020's rollup comment edit history:

| Dispatched by | Implement runs | First in the rollup |
|---|---|---|
| a person (manual restarts) | 2 | within a minute of completing |
| `github-actions[bot]` | 15 | only at a 07:00Z sweep edit |
| `github-actions[bot]` | 7 | never (dropped by the sweep — tracked separately in #1054) |

All 14 of #1020's finalize runs were started by `github-actions[bot]`; 12
first appeared at a sweep edit and 2 never did. Example: run 38619303808
completed 19:24:20Z on Oct 14; four live rollup edits passed before it first
appeared at the 07:00:29Z sweep on Oct 15.

The same token rule also suppresses every *other* completion listener for
these runs today. The watchdog lists `implement` and `finalize` among its
completion triggers, and the fold-cycle guard listens to `implement`
completions (acting on cancellations). None of these currently fire for
pipeline-dispatched runs, so any remedy that makes completions visible again
changes their behaviour too.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Rollup reflects implement and finalize spend promptly (Priority: P1)

The owner watches a lifecycle's metrics rollup comment while implement
cycles and finalize run. Each completed run — however it was dispatched —
appears in the rollup's totals shortly after it completes, not the next
morning.

**Why this priority**: Implement and finalize are the most expensive part
of a lifecycle; a rollup that lags by up to a day during exactly that phase
hides the spend the owner most needs to see.

**Independent Test**: Let the pipeline dispatch an implement cycle on a
lifecycle (no human dispatch). After it completes, check that its record is
in the records file and its cost is reflected in the rollup comment well
before the next daily sweep.

**Acceptance Scenarios**:

1. **Given** an implement run dispatched by the pipeline itself, **When** it
   completes, **Then** its metrics record is persisted and reflected in the
   lifecycle's rollup within the freshness window (SC-001), without waiting
   for the daily sweep.
2. **Given** a finalize run dispatched by the pipeline itself, **When** it
   completes, **Then** the same holds.
3. **Given** a fold's implement re-drive dispatched by pr-conversation,
   **When** it completes, **Then** the same holds.
4. **Given** a run dispatched by a person, **When** it completes, **Then**
   its record is persisted exactly as promptly as today (no regression).

---

### User Story 2 - Mid-lifecycle readers of the records file see current data (Priority: P2)

Automation that reads `records.jsonl` mid-lifecycle — for example spec 110's
diagnose-shadow cap — sees the records of implement and finalize runs that
have already completed, rather than data up to a day old.

**Why this priority**: Stale records silently weaken any cap or decision
computed from them; this is the correctness consequence of User Story 1.

**Independent Test**: After a pipeline-dispatched implement run completes,
read the records file before the next sweep and confirm the run's record is
present exactly once.

**Acceptance Scenarios**:

1. **Given** a pipeline-dispatched run has completed and the freshness
   window has passed, **When** a reader loads the records file, **Then** the
   run's record is present.
2. **Given** the run's record was persisted promptly, **When** the daily
   sweep later runs, **Then** it does not add a second copy of the record.

---

### User Story 3 - No unintended change to other completion listeners (Priority: P2)

The owner can rely on the watchdog, the fold-cycle guard, and any other
completion listener behaving deliberately for pipeline-dispatched implement
and finalize runs — either unchanged, or changed in a way this spec states
and accepts.

**Why this priority**: Making completions visible again can newly start
watchdog inspections (billed minutes, possible filings) and fold-cycle
guard runs that have never run for these completions before.

**Independent Test**: Inventory every workflow listening to implement,
finalize, or pr-conversation completions and confirm each one's behaviour on
a pipeline-dispatched run matches what FR-005 decides.

**Acceptance Scenarios**:

1. **Given** a pipeline-dispatched implement run completes, **When** the
   remedy is in place, **Then** each other completion listener either does
   not run or runs as FR-005 specifies.

---

### User Story 4 - Rollup is honest about what it may be missing (Priority: P3)

Whenever the rollup's total can still omit completed runs (for any run kind
whose records rely on the sweep), the rollup comment says so, so the owner
does not read a partial total as complete.

**Why this priority**: Honest labelling is the fallback that makes any
remaining lag harmless; it is the whole remedy only if the owner picks
sweep-only collection.

**Independent Test**: Render a rollup for a lifecycle with runs completed
since the last sweep and check the disclosure text is present when, and only
when, such runs can be missing.

**Acceptance Scenarios**:

1. **Given** some completed runs' records can only arrive via the sweep,
   **When** the rollup is rendered, **Then** it states that runs since the
   last sweep may be missing from the total and when the last sweep ran.

---

### Edge Cases

- A pipeline-dispatched run is cancelled or fails: its record (if it emits
  one) must still be persisted promptly, matching how person-dispatched
  failures are handled today.
- The prompt persistence path itself fails (e.g. a transient API error):
  the daily sweep remains the backstop and must still pick the run up.
- The same run is persisted by both the prompt path and the sweep: the
  records file must hold it once (existing de-duplication must cover the
  new path).
- The App token is unavailable or minting it fails at dispatch time: the
  next stage must still be dispatched (pipeline progress outranks metrics
  freshness); only freshness may degrade.
- A dispatch chain of many implement cycles: the remedy must not add a
  persistence or listener run per cycle beyond what FR-005 accepts.
- Runs dropped entirely by the sweep (#1054) are a separate defect; this
  spec must not depend on that fix, nor mask it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The metrics record of every completed implement, finalize, and
  fold-re-drive implement run MUST be persisted to the records file within
  the freshness window (SC-001), regardless of whether a person or the
  pipeline dispatched it.
- **FR-002**: The mechanism that achieves FR-001 MUST be
  [NEEDS CLARIFICATION: which remedy — (A) dispatch the next stage with the
  App token already in the dispatch step's environment, so completions fire
  the completion trigger; (B) have implement and finalize persist their own
  record as their last job; or (C) keep sweep-only collection for these runs
  and disclose the lag (which drops FR-001 and makes FR-006 the remedy)?]
- **FR-003**: Person-dispatched runs MUST keep their current prompt
  persistence behaviour unchanged.
- **FR-004**: Each run's record MUST appear in the records file exactly once
  even when both the prompt path and the daily sweep encounter it.
- **FR-005**: For pipeline-dispatched implement and finalize runs, the other
  completion listeners (the watchdog's completion trigger and the fold-cycle
  guard) MUST [NEEDS CLARIFICATION: newly start running for these
  completions as they already do for person-dispatched runs, or be kept from
  running for them as today?]
- **FR-006**: Whenever any completed run's record can still arrive only via
  the daily sweep, the rollup comment MUST state that runs since the last
  sweep may be missing from the total.
- **FR-007**: A failure in the prompt persistence path MUST NOT fail or block
  the stage run or the dispatch of the next stage; the daily sweep MUST remain
  the backstop.
- **FR-008**: Spec 058 FR-030(a)'s contract — that stages whose records are
  read back promptly keep a live completion-driven persistence — MUST be
  true in practice for implement and finalize after this feature, or the
  live contract/documentation MUST be corrected to state the actual model.
- **FR-009**: A deterministic gate MUST fail if a pipeline dispatch of
  implement or finalize reverts to a path that cannot produce prompt
  persistence under the chosen mechanism (e.g. a dispatch with the built-in
  token under remedy A, or a missing final persistence job under remedy B).

### Key Entities

- **Metrics record**: per-run cost/usage record uploaded by a stage run and
  appended to `records.jsonl`; keyed by run id.
- **Rollup comment**: per-lifecycle summary comment on the lifecycle issue,
  re-rendered from the records file by live persistence runs and the sweep.
- **Dispatch actor**: the identity that started a stage run (a person, the
  App, or `github-actions[bot]`); it decides whether completion listeners fire.
- **Completion listeners**: workflows triggered by a stage run's completion
  — metrics persistence, watchdog, fold-cycle guard.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a lifecycle driven end-to-end by the pipeline, at least 95%
  of implement and finalize runs appear in the records file and rollup within
  15 minutes of completing (today: 0% of `github-actions[bot]`-dispatched
  runs before the next sweep).
- **SC-002**: Zero duplicate records for any run after a full lifecycle plus
  one daily sweep.
- **SC-003**: Zero stage dispatches lost or delayed because of the change
  (every next-stage dispatch that happened before still happens).
- **SC-004**: The number of extra workflow runs added per implement cycle is
  bounded and stated (at most one persistence run per completed run, plus
  whatever FR-005 accepts).

## Assumptions

- The App token is already present in the dispatch steps' environment as
  `APP_TOKEN`, and App-dispatched runs fire completion triggers as
  person-dispatched ones do.
- The daily sweep stays as the backstop; this feature does not remove it.
- The sweep's dropping of some runs entirely (#1054) is out of scope and
  tracked separately.
- pr-conversation's other uses of the built-in token (cancelling runs,
  listing runs) are out of scope; only dispatches that start a stage run
  whose completion matters are in scope.
- Board-loop and watchdog records remain sweep-only as 058 and #889 decided.
