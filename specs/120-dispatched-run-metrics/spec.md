# Feature Specification: Prompt Metrics Records for Pipeline-Dispatched Runs

**Feature Branch**: `120-dispatched-run-metrics`

**Created**: 2026-10-24

**Status**: Draft

**Input**: User description: "metrics-persist: runs dispatched with github.token never fire the workflow_run trigger, so implement and finalize records wait for the daily sweep" (lifecycle issue #1055, routed from #1053 by board-loop as spec-shaped).

## Background

Pipeline stages start implement and finalize runs using the workflow's own
built-in token: tasks dispatches implement cycle 1 (both its auto and
PR-merge modes), implement dispatches the next cycle and finalize, and the
fold dispatch composite (`wing-commander-fold-dispatch`, called by
pr-conversation and the lifecycle review gate) and the fold-cycle guard's
recovery re-dispatch start a fold's implement re-drive. Those runs' actor
is `github-actions[bot]`. GitHub does
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
completion triggers, the watchdog's self-verifier (8b) listens to every
watchdog completion, and the fold-cycle guard listens to `implement`
completions (acting on cancellations). None of these currently fire for
pipeline-dispatched runs. A remedy that made those completions visible
would change all of their behaviour too.

Making completions visible by dispatching with the App token is not
available either. The App's documented permission set (`docs/setup.md`:
Contents, Issues and Pull requests, "exactly these three") has no Actions
permission, and the token-permission gate (Gate 12) checks every App-token
call against that set. Dispatching a workflow needs Actions: write, which is
why every dispatch site uses the built-in token today.

The remedy this spec adopts (owner, 2026-10-26) leaves dispatch alone:
each implement and finalize run persists its own metrics record as its
last job, so freshness no longer depends on who dispatched the run or on
any completion trigger firing.

## Clarifications

### Session 2026-10-24

- Q: Which remedy achieves prompt persistence for pipeline-dispatched runs?
  → A: (A) Dispatch the next stage with the App token (`APP_TOKEN`, already
  in the dispatch step's env), so pipeline-dispatched implement, finalize
  and fold re-drive completions fire `wing-commander-metrics-persist.yml`'s
  `workflow_run` job and spec 058 FR-030(a) holds as written.
  *Superseded by the 2026-10-26 session: the App has no Actions permission
  (see Background).*
- Q: How should the other completion listeners behave for
  pipeline-dispatched completions? → A: (C) The fold-cycle guard fires for
  pipeline-dispatched implement completions. The watchdog's `workflow_run`
  trigger does not; it keeps today's behaviour for those runs through an
  explicit filter on the run's dispatcher, and a gate enforces that filter.
  *Moot since the 2026-10-26 session: no dispatch changes, so no listener
  starts firing and there is nothing to filter.*

### Session 2026-10-26 (owner, after the spec PR review)

- Q: Remedy A needs an Actions permission the App does not have. Which
  remedy replaces it? → A: (B) Each implement and finalize run persists its
  own metrics record as its last job, whoever dispatched it. The dispatch
  token stays `github.token`, so no listener starts firing that does not
  fire today. Spec 058's FR-030 model is restated for these two stages
  (FR-008). The record is de-duplicated against the `workflow_run` path
  (which person-dispatched runs still fire) and the daily sweep by the
  existing record-key idempotence, not a second scheme. The persisting job
  reuses the existing persistence code, runs even when an earlier job
  failed or was cancelled where a record exists, and holds no App token.
- Q: Should `tasks` (dispatched by plan) and `rebase` (which re-dispatches
  itself) be covered too? → A: (a) No. Both stay out of scope; the
  orchestrator adds a line for them to the Maintenance backlog (#889).
- Consequence: the 2026-10-24 Q2 answer (C) is moot. FR-005 (with
  FR-005a–c), the user story and edge cases about listeners newly firing,
  and the dispatcher entity are removed or marked superseded below.

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
before the next daily sweep, and that the run's own last job is what
persisted it.

**Acceptance Scenarios**:

1. **Given** an implement run dispatched by the pipeline itself, **When** its
   stage job finishes, **Then** the run's own persisting job persists its
   metrics records and re-renders the lifecycle's rollup within the
   freshness window (SC-001), without waiting for the daily sweep.
2. **Given** a finalize run dispatched by the pipeline itself, **When** its
   stage job finishes, **Then** the same holds.
3. **Given** a fold's implement re-drive dispatched by the pipeline (the
   fold dispatch composite, from pr-conversation or the lifecycle review
   gate, or the fold-cycle guard's recovery re-dispatch), **When** its
   stage job finishes, **Then** the same holds.
4. **Given** implement cycle 1 dispatched by tasks, **When** its stage job
   finishes, **Then** the same holds.
5. **Given** a run dispatched by a person, **When** it completes, **Then**
   its records are persisted at least as promptly as today (no
   regression), and the later `workflow_run` persistence run for it
   appends nothing new.

---

### User Story 2 - Mid-lifecycle readers of the records file see current data (Priority: P2)

Automation that reads `records.jsonl` mid-lifecycle sees the records of
implement and finalize runs that have already completed, rather than data up
to a day old. (Spec 110's diagnose-shadow cap is not such a reader: it counts
watchdog records, which stay sweep-only.)

**Why this priority**: Stale records silently weaken any cap or decision
computed from them; this is the correctness consequence of User Story 1.

**Independent Test**: After a pipeline-dispatched implement run completes,
read the records file before the next sweep and confirm the run's record is
present exactly once.

**Acceptance Scenarios**:

1. **Given** a pipeline-dispatched run has completed and the freshness
   window has passed, **When** a reader loads the records file, **Then** the
   run's records are present.
2. **Given** the run's records were persisted by its own persisting job,
   **When** the `workflow_run` persistence path (person-dispatched runs) or
   the daily sweep later encounters the same run, **Then** neither adds a
   second copy of any record.

---

### User Story 3 - A failed or cancelled run's spend is still visible promptly (Priority: P2)

When an implement or finalize run fails, or is cancelled after it has
started work (for example pr-conversation cancelling an in-flight implement
run before a fold re-drive), the records it had already emitted still reach
the rollup promptly. Failed and cancelled runs still cost money.

**Why this priority**: A run that dies mid-cycle is exactly the case the
owner investigates; a rollup that hides its spend until the next morning
hides the cost of the failure.

**Independent Test**: Cancel a pipeline-dispatched implement run after its
agent step has emitted a record. Confirm its persisting job still runs and
the record is in the records file before the next sweep. Separately, cancel
a run before any of its jobs start and confirm its persisting job does not
start.

**Acceptance Scenarios**:

1. **Given** an implement or finalize run whose stage job failed after
   emitting a record, **When** the stage job ends, **Then** the persisting
   job runs and persists the emitted records.
2. **Given** an implement or finalize run cancelled after its stage job
   started, **When** the run is cancelled, **Then** the persisting job
   still runs and persists whatever records were emitted.
3. **Given** a run cancelled before any of its jobs started, **When** the
   run concludes, **Then** the persisting job does not start (it has no
   record to persist, and a started job would change how the fold-cycle
   guard classifies the cancellation; FR-011).

---

### User Story 4 - Rollup is honest about what it may be missing (Priority: P3)

Whenever the rollup's total can still omit completed runs (for any run kind
whose records rely on the sweep), the rollup comment says so, so the owner
does not read a partial total as complete.

**Why this priority**: Honest labelling is the fallback that makes any
remaining lag harmless (for example a run whose persisting job failed, or
run kinds that remain sweep-only).

**Independent Test**: Render a rollup for a lifecycle and check it states
when the last sweep ran and that runs completed since then may be missing
from the total.

**Acceptance Scenarios**:

1. **Given** some completed runs' records can only arrive via the sweep,
   **When** the rollup is rendered, **Then** it states that runs since the
   last sweep may be missing from the total and when the last sweep ran.

---

### Superseded: User Story "No unintended change to other completion listeners"

Removed by the 2026-10-26 session. It existed because remedy A made
pipeline-dispatched completions visible to the watchdog, 8b and the
fold-cycle guard. Under B the dispatch token does not change, so those
listeners keep firing exactly when they fire today. FR-010 and FR-011
now state the no-change requirement.

### Edge Cases

- A run's stage job fails or is cancelled after starting: the persisting job
  still runs and persists what was emitted (User Story 3).
- A run is cancelled before any job starts, or its stage job is skipped by
  its own `if:`: it emitted no record, so the persisting job does not run
  (FR-002 gating). The sweep's existing skipped-run filter and FR-021's
  zero-record no-op already cover such runs.
- The persisting job itself fails (e.g. a transient API error, or the
  append retries running out): the run's own outcome is unchanged (FR-007),
  and the daily sweep remains the backstop that picks the run up.
- The same run is persisted by its own persisting job, by the `workflow_run`
  path (person-dispatched runs), and by the sweep: the records file holds
  each record once, through the existing record-key idempotence (FR-004).
- The persisting job runs before the run as a whole has concluded. Spec
  043's persistence contract currently says persistence "runs only after
  the origin run has concluded"; the plan must amend that live contract and
  confirm that every record-emitting job's artifact is listable at that
  point (the persisting job depends on every job that can emit one).
- The implement and finalize stage jobs share a per-spec concurrency group
  with the next cycle. The persisting job must not join that group, or it
  would queue behind the next cycle it just helped dispatch.
- A person re-runs a run, or re-runs only its failed jobs: the persisting
  job runs again on that attempt and appends only records it has not seen.
- A dispatch chain of many implement cycles: the remedy adds exactly one
  persisting job per run (SC-004), and no new listener run, because the
  dispatch token is unchanged.
- An adopter's wrapper that does not add the persisting job keeps today's
  behaviour (the published stages do not change on their own; FR-008).
- Runs dropped entirely by the sweep (#1054) are a separate defect; this
  spec must not depend on that fix, nor mask it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The metrics records of every completed implement, finalize, and
  fold-re-drive implement run MUST be persisted to the records file within
  the freshness window (SC-001), regardless of whether a person or the
  pipeline dispatched it.
- **FR-002**: The mechanism that achieves FR-001 MUST be a persisting job
  in each implement and finalize run, as that run's last job, that persists
  the run's own records and re-renders the rollup. Specifically:
  - It MUST depend on every job in the run that can emit a metrics record,
    so it starts only after all of them have ended.
  - It MUST run when the stage job's result is `success`, `failure` or
    `cancelled` after the stage job started (a run cancelled mid-cycle
    still persists). It MUST NOT run when the stage job was skipped, or
    when the run was cancelled before any job started. In both cases no
    record exists. When the persistence kill switch
    (`WING_COMMANDER_METRICS_PAUSED`) is `true`, it MUST NOT run either.
  - It MUST reuse the existing persistence implementation (the
    `metrics-persist.yml` stage and the `wing-commander-metrics-persist`
    composite it calls). It MUST NOT paste a copy of discovery, retrieval,
    validation, append or rollup logic into a workflow (CLAUDE.md "Shared
    logic has exactly one home").
  - It MUST receive no App credentials: persistence uses the built-in token
    today, and the job needs nothing more than the permissions the
    `workflow_run` path's job holds.
  - It MUST NOT be in the stage's per-spec concurrency group.
  - It lives wherever constitution VII puts the destination choice: in
    this repository's wrappers, which own the destination branch, path and
    kill switch. The plan decides any declared stage input or output the
    gating needs.
- **FR-003**: Person-dispatched runs MUST keep their current prompt
  persistence behaviour unchanged. The `workflow_run` trigger keeps listing
  implement and finalize.
- **FR-004**: Each record MUST appear in the records file exactly once even
  when the persisting job, the `workflow_run` path and the daily sweep all
  encounter its run. De-duplication MUST be the existing record-key
  idempotence (spec 043; `record_key` embeds the run id). This feature
  MUST NOT add a second de-duplication scheme.
- **FR-005**: *Superseded (2026-10-26).* FR-005a (the fold-cycle guard newly
  fires), FR-005b (the watchdog's dispatcher filter, and 8b standing down
  for runs it filters out) and FR-005c (the gate holding that filter) only
  made sense under remedy A. Under B no completion listener's firing
  changes (FR-010).
- **FR-006**: The rollup comment MUST state when the last daily sweep ran
  and that runs completed since then may be missing from the total, because
  some records can still arrive only via the sweep: sweep-only run kinds,
  and runs whose persisting job failed or never ran.
- **FR-007**: A failure of the persisting job MUST NOT fail, block or delay
  the stage job or the dispatch of the next stage. It MUST NOT turn a run
  whose stage job succeeded into a failed run as seen by listeners, the
  rollup and readers of run conclusions. The failure MUST stay visible in
  the persisting job's own summary and annotations, and the daily sweep
  MUST remain the backstop.
- **FR-008**: Spec 058 FR-030's trigger model is restated for implement and
  finalize. Their prompt persistence comes from each run's own persisting
  job (FR-002), not from the completion trigger. The completion trigger
  stays for person-dispatched runs and the other promptly-read stages. The
  daily sweep stays as the backstop (FR-030(c)). Spec 058's spec.md is a
  merged historical record and is not edited. The plan MUST update the live
  contracts that state the trigger model:
  `specs/058-per-job-minute-floor/contracts/metrics-persist-sweep-delta.md`
  (its "unchanged nine-stage path" for completion-triggered runs) and spec
  043's `contracts/persist-workflow.md` ("runs only after the origin run
  has concluded") and `contracts/wrapper-contract.md`. This feature makes
  no claim for `tasks` (dispatched by plan) or `rebase` (which
  re-dispatches itself). Their pipeline-dispatched runs stay sweep-only.
- **FR-009**: A deterministic gate MUST fail when any of these holds:
  - the implement or finalize wrapper lacks the persisting job;
  - the persisting job's gating would skip a stage job that failed, or one
    cancelled after it started;
  - the persisting job does not depend on every record-emitting job in the
    run;
  - the persisting job reaches persistence other than through the existing
    stage or composite;
  - the persisting job is handed App credentials;
  - the persisting job joins the per-spec concurrency group.
  The plan names which existing gate this extends (e.g. Gate 79's
  record-owner checks).
- **FR-010**: Every site that starts an implement or finalize run MUST keep
  dispatching with the built-in token. This feature MUST NOT change any
  dispatch token, so the watchdog, its self-verifier (8b) and the
  fold-cycle guard fire for exactly the completions they fire for today.
- **FR-011**: The persisting job MUST NOT change the verdict of any
  completion listener that inspects the run's jobs when it does fire
  (person-dispatched runs). In particular the fold-cycle guard's
  never-started classification counts any job with a start time, so the
  persisting job MUST NOT start in a run cancelled before its other jobs
  started (FR-002). The watchdog's inspection MUST NOT read the persisting
  job's outcome as the stage's outcome.

### Key Entities

- **Metrics record**: per-run cost/usage record uploaded by a stage run and
  appended to `records.jsonl`; identified by its `record_key` (run id, job
  id, step index).
- **Persisting job**: the last job of an implement or finalize run. It
  calls the existing persistence stage for its own run id and re-renders
  the rollup.
- **Rollup comment**: per-lifecycle summary comment on the lifecycle issue,
  re-rendered from the records file by persisting jobs, live persistence
  runs and the sweep.
- **Completion listeners**: workflows triggered by a stage run's completion
  (metrics persistence, watchdog, fold-cycle guard), plus the watchdog
  self-verifier (8b). This feature leaves when they fire unchanged
  (FR-010).
- *Dispatch actor*: superseded (2026-10-26). Who dispatched a run no longer
  decides whether its records are persisted promptly.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a lifecycle driven end-to-end by the pipeline, at least 95%
  of implement and finalize runs appear in the records file and rollup within
  15 minutes of completing (today: 0% of `github-actions[bot]`-dispatched
  runs before the next sweep).
- **SC-002**: Zero duplicate records for any run after a full lifecycle plus
  one daily sweep, including person-dispatched runs persisted by both the
  persisting job and the `workflow_run` path.
- **SC-003**: Zero stage dispatches lost or delayed because of the change
  (every next-stage dispatch that happened before still happens, at the
  same point in the run).
- **SC-004**: The extra runner work per implement or finalize run is
  bounded and stated: at most one persisting job (plus its image-check job
  when a container image is configured). It adds no new workflow run and
  no new watchdog, 8b or fold-cycle guard run. Person-dispatched runs keep
  their existing `workflow_run` persistence run, which appends nothing new.
- **SC-005**: Every implement and finalize run whose stage job failed, or
  was cancelled after starting, during the measured lifecycle has its
  emitted records in the records file within the SC-001 window.

## Assumptions

- Artifacts uploaded by a run's earlier jobs can be listed and downloaded
  through the Actions API while the run is still in progress, and those
  jobs' ids are already resolvable, so the persisting job can derive the
  same `record_key` the post-completion path does. The plan verifies this
  before relying on it.
- A job gated to run after a cancelled job still runs when the run is
  cancelled, given the right status function. The plan states which
  function the gating uses and why (`review-step-gating` skill).
- The daily sweep stays as the backstop; this feature does not remove it.
- The sweep's dropping of some runs entirely (#1054) is out of scope and
  tracked separately.
- Board-loop and watchdog records remain sweep-only as 058 and #889 decided.

## Out of Scope

- Changing any dispatch token, or granting the App an Actions permission
  (remedy A, superseded 2026-10-26).
- `tasks` runs (dispatched by plan) and `rebase` runs (which re-dispatch
  themselves). Their pipeline-dispatched runs stay sweep-only; the
  orchestrator records them as a Maintenance backlog (#889) line (owner,
  2026-10-26, Q2 (a)).
- Removing implement and finalize from the `workflow_run` trigger list.
  The trigger stays for person-dispatched runs (FR-003).
- pr-conversation's other uses of the built-in token (cancelling runs,
  listing runs).
- The sweep dropping runs entirely (#1054).
