# Feature Specification: The Per-Job Minute Floor — No-Op and Healthy Paths Cost What They Run

**Feature Branch**: `058-per-job-minute-floor`

**Created**: 2026-09-21

**Status**: Draft

**Input**: Lifecycle issue [#434](https://github.com/charlesguse/wing-commander/issues/434) — "Actions usage: every stage's no-op and healthy paths pay the per-job minute floor (evidence: #404, #405, #406)"

## Context

GitHub bills every Actions job as at least one whole minute, however short
it runs. The usage page shows it directly: the watchdog self-verifier's
single job ran 1,142 times this month for 1,144 billed minutes, and each of
those jobs takes about seven seconds. This repository's stages are built as
several short jobs each, so on their **no-op and healthy paths** — the
overwhelming majority of runs — the bill is set by the number of jobs, not
by the work done.

`Insights → Actions usage metrics`, 1–19 Sep 2026: 21,213 minutes across
18,858 job runs. PR #403 (merged 2026-09-19) removed the largest
structural waste — wrappers reacting to source runs that had executed
nothing, and the metrics-persist wrapper's separate resolve job — worth
roughly 12,000 of those minutes at this month's volume. What #403 could not
touch is the per-run *shape* of the stages themselves. Sampled from runs on
current `main`:

| workflow | billed jobs per healthy run | wall clock of the real work |
|---|---|---|
| `metrics-persist` | 2 — `verify-image-prerequisites` (2 s), `persist` (13 s) | ~15 s |
| `8 watchdog` | 5 — wrapper `resolve` (3 s), `verify-image-prerequisites` (3 s), `collect` (25 s), `diagnose` (32 s, runs the agent), `report-unhandled-failure` (8 s) | ~70 s |
| `8b watchdog self` | 1 — `verify` (7 s) | 7 s |

Three sub-problems — filed separately as #404, #405 and #406 with the full
per-job tables — share one root cause, touch the same files (`watchdog.yml`
and `metrics-persist.yml` are edited by two of them each) and the same
uniformity gates. They are worth one spec rather than three concurrent
implements racing on the same workflows.

**A. The image check bills a minute in every stage when there is no image
(#404).** Every one of the 13 published stage workflows carries a
`verify-image-prerequisites` job whose one step is gated on a container
image being configured. With no image configured the *step* is skipped, but
the *job* still allocates a runner: a billed minute per stage run. About
5,100 minutes this month (24 % of the total) on a job whose only step was
skipped. It is not a local fix, because every downstream job reaches the
check through bare dependency skip-propagation as its image gate, so a
job-level condition on the check alone would skip every dependent job in
every stage.

**B. A healthy watchdog inspection costs five job-minutes and an agent call
(#405).** After #403 the watchdog only inspects runs that executed. Every
remaining inspection still pays five billed jobs and **runs the diagnose
agent even when every collector ran and emitted zero signals** — the
evidence gate only closes when every collector *failed*. This month: 5,786
minutes over 1,142 runs, and 1,126 agent calls on the shared usage window
for a verdict that was "passed inspection" in all but a handful.

**C. Metrics persistence runs once per stage completion for nine seconds of
work (#406).** `metrics-persist` was the largest consumer this month (9,283
minutes, 44 %, 3,092 runs). #403 cut it to two jobs and to executed sources
only; what remains is one workflow run per stage completion, about 1,300 a
month at current volume, each two billed minutes (one of them sub-problem
A's) for about nine seconds of work.

**Two honest framings.** On a public repository these minutes are free, so
the value is the usage metric itself, any adopter running the pipeline on a
private repository, and — for sub-problem B — the diagnose agent's token
spend on the usage window this repository's pipeline shares with its
maintainers' own sessions. And the pipeline's volume is bursty: a single
spec lifecycle drives dozens of completions in an hour, and those records
are read back mid-lifecycle, which is what makes a fixed schedule a poor fit
on its own for the completions that carry a record.

**Why this is not a cost-target spec.** Every outcome below is stated per
run and is verifiable from the jobs API of a single run — how many jobs
were billed, which jobs were skipped, whether an agent step ran. The usage
page lags and moves with volume, so it is evidence for the motivation, never
the acceptance criterion.

Constitution dependencies: VII (wrappers own triggers; any change to a
published stage's inputs is a versioned decision recorded in the stage's
contract), VIII (every gate this spec ships or amends carries a checked-in
fixture for each failure branch), IX (the passed-inspection record and the
persistence high-water mark are written by deterministic code, never by an
agent).

## Clarifications

### Session 2026-09-21 — answered on [#434](https://github.com/charlesguse/wing-commander/issues/434)

- Q: Does the watchdog's agent-skip condition key on "zero signals" alone, or
  on "zero signals and zero failed collectors"? → A: zero signals alone; the
  deterministic record states whether the pass was full or partial (FR-019).
- Q: Is folding the watchdog wrapper's run resolution into the stage — a
  versioned published-input change — in scope here or deferred? → A: in
  scope; `run-name` becomes optional and the decision is recorded in the
  watchdog stage's contract as a minor version (FR-020).
- Q: Which persistence model does sub-problem C adopt? → A: none of the three
  listed. Keep per-completion persistence for the nine stage workflows whose
  records are read back promptly, drop the watchdog from the completion
  trigger because sub-problem B empties it, add a daily scheduled sweep over
  a high-water mark, and use no concurrency-based coalescing (FR-030).

Four corrections the same reply raised are folded in: PR #403 is cited
without the unrelated spec 057; sub-problem B gains FR-031 for the record a
healthy inspection no longer emits; SC-004 is restated as a count a jobs
listing can actually show; and User Story 2's Independent Test says the
diagnose job is *skipped* rather than absent.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A stage with no container image pays nothing for the image check (Priority: P1)

A maintainer (or an adopter) runs any published stage without configuring a
container image — the default, and what every run in this repository does
today. The image check contributes no billed job to the run: it is reported
as skipped, and every job that depends on it proceeds exactly as it does
today, in the same order, with the same results. Nothing about the run's
outcome changes; only the job count drops by one.

The same maintainer, on a run that *does* configure an image, sees the
check run first and fail fast on a bad image or a rejected credential, and
sees every dependent job skipped behind it — exactly as today.

**Why this priority**: it is the broadest and cheapest win — one shape
change that reaches all 13 published stages and removes about a quarter of
the repository's billed minutes — and it must land before B and C, which
edit the same two files. It also carries the highest regression risk, since
the dependent-job rewrite touches roughly 40 jobs, so it deserves the first
and most careful pass.

**Independent Test**: dispatch any stage twice — once with no image
configured, once with an image — and read the jobs API of each run. The
first shows the check skipped and every other job successful; the second
shows the check successful (or failed, with every dependent skipped).

**Acceptance Scenarios**:

1. **Given** a published stage invoked with no container image, **When** the
   run completes, **Then** the image-check job is reported skipped, it
   contributes no billed job to the run, and every job that names it as a
   dependency runs and concludes exactly as it does on current `main`.
2. **Given** a published stage invoked with a container image that cannot be
   pulled or whose credentials the registry rejects, **When** the run
   completes, **Then** the image-check job fails, it has run before any
   other job's container was created, and every job that names it as a
   dependency is skipped.
3. **Given** a published stage invoked with a valid container image, **When**
   the run completes, **Then** the image check succeeds and the run behaves
   exactly as it does on current `main`.
4. **Given** a job that depends on both the image check and another job,
   **When** that other job fails or is skipped, **Then** the dependent job
   does not run — a dependent's original requirement of success from its
   other dependencies survives the rewrite, and is never widened to "run
   unless cancelled".
5. **Given** a contributor who reverts one dependent job to bare dependency
   skip-propagation on the image check, **When** the gate suite runs,
   **Then** a gate fails naming that job and that stage.

---

### User Story 2 - A clean watchdog inspection is decided by code, not by an agent (Priority: P2)

The watchdog inspects a run that executed. The collectors emitted no signal.
The watchdog records "passed inspection" on the lifecycle issue from a
deterministic step, files nothing, invokes no agent, and bills only the
collection job plus the guaranteed unhandled-failure report. An empty signal
set is enough on its own: when a collector errored, the same deterministic
step records the weaker "passed inspection on N of M collectors" wording it
posts today, and still invokes no agent. A run with at least one signal
reaches the diagnose agent and behaves exactly as it does today.

**Why this priority**: it removes an agent call from the common path, which
is the part of this spec that returns real budget on the usage window the
pipeline shares with its maintainers' sessions. It is second because it
edits `watchdog.yml`, which User Story 1 also rewrites.

**Independent Test**: drive one watchdog inspection over a healthy run and
one over a run carrying a known signal. Read both runs' jobs APIs: the first
shows the diagnose job skipped, no agent step executed, and a
passed-inspection comment on the issue; the second shows diagnose running
and the same behaviour as today.

**Acceptance Scenarios**:

1. **Given** a watchdog inspection where every collector ran and the
   aggregate signal set is empty, **When** the run completes, **Then** no
   agent step executed anywhere in the run, a full "passed inspection" record
   was posted by a deterministic step, and no issue was filed or updated.
2. **Given** a watchdog inspection where at least one collector ran, one or
   more collectors errored, and the aggregate signal set is empty, **When**
   the run completes, **Then** no agent step executed, and the deterministic
   record posted is the partial one naming how many collectors reported and
   how many errored.
3. **Given** a watchdog inspection whose aggregate signal set is non-empty,
   **When** the run completes, **Then** the diagnose agent ran and the run's
   filing, triage and action behaviour is byte-for-byte what current `main`
   produces for the same evidence.
4. **Given** a watchdog inspection where every collector failed, **When** the
   run completes, **Then** the existing "could not inspect" path runs
   unchanged, and no passed-inspection record is posted.
5. **Given** a watchdog inspection that found nothing, **When** the run
   completes, **Then** it uploaded no metrics record, and nothing downstream
   reports that run as a record that could not be retrieved.
6. **Given** any watchdog run, including one inspecting the watchdog's own
   runs, **When** the inspection is selected, **Then** it is neither skipped
   nor softened — the watchdog's own runs stay unexempted.
7. **Given** any watchdog run at all, including one where every other job
   died, **When** the run completes, **Then** the unhandled-failure report
   still executed.

---

### User Story 3 - Metrics persistence pays only for completions that emitted a record (Priority: P3)

A spec lifecycle drives dozens of stage completions in an hour. Each of the
nine stage workflows whose records are read back promptly still gets its own
persistence run on completion, so its record lands within minutes — that
latency is what the watchdog's cross-run collectors and the lifecycle rollup
depend on. What stops is spending a run on a completion that emitted no
record at all: once sub-problem B skips the diagnose job, a healthy watchdog
inspection uploads nothing, so the watchdog leaves the completion trigger
entirely. A daily scheduled sweep picks up the rest — the signal-bearing
watchdog inspections and any stage completion a per-run persistence missed —
from a durable high-water mark. A maintainer can still re-drive persistence
for one named run by hand.

**Why this priority**: it is the largest single consumer, but it is last
because it is the only sub-problem that changes *when* a durable write
happens rather than *whether* an idle job is billed, and because the
completions it stops reacting to are exactly the ones sub-problem B empties.

**Independent Test**: drive a burst of stage completions plus a healthy
watchdog inspection, then list the persistence runs created and read the
records file: one run per record-bearing completion, none for the healthy
inspection, and every executed run appearing exactly once.

**Acceptance Scenarios**:

1. **Given** a burst of stage completions inside one short window, **When**
   the burst has settled, **Then** exactly one persistence run was created
   per record-bearing completion, none was created for a completion that
   emitted no record, and every executed run in the burst has exactly one
   record.
2. **Given** a stage run that concluded and whose metrics artifacts exist,
   **When** persistence next runs, **Then** its record is appended within
   minutes of the run concluding.
3. **Given** a signal-bearing watchdog inspection, which the completion
   trigger no longer reacts to, **When** the next scheduled sweep runs,
   **Then** its record is persisted exactly once.
4. **Given** a run that has already been persisted, **When** persistence
   processes it again for any reason, **Then** no duplicate record is
   appended — idempotence by record key holds.
5. **Given** a maintainer who wants one named run persisted now, **When**
   they trigger the single-run re-drive by hand, **Then** that run is
   persisted, and it is safe to do so while a scheduled sweep is already in
   flight.
6. **Given** a persistence path that fails for any reason, **When** it fails,
   **Then** it fails only itself — it never touches, marks or fails the
   origin run it is collecting from.
7. **Given** a run whose metrics artifacts have expired before persistence
   reached it, **When** persistence processes it, **Then** the outcome is
   recorded explicitly rather than silently dropped, and the run is not
   retried forever.

---

### Edge Cases

- **A dependent job that has no other dependency besides the image check.**
  With the check skipped, such a job has nothing left to require. Its
  original semantics — "run when the check did not fail" — must be preserved
  explicitly, not by the absence of a condition.
- **A stage whose jobs form a chain through the image check** (the check →
  a middle job → a late job). The late job must still be skipped when the
  middle job fails, and must still run when the check is skipped.
- **An adopter's stage-binding tooling that iterates over every published
  stage uniformly.** The check must remain present, in the same position,
  in all 13 stages — the uniformity argument survives, enforced by the
  amended gates rather than by prose.
- **A watchdog run with zero signals and one failed collector.** This is
  today a *weaker* pass than a run where every collector reported. The
  deterministic record must be able to say which of the two it is.
- **A watchdog inspection where the aggregate step itself fails.** No
  passed-inspection record may be posted on the strength of an aggregate
  that did not complete.
- **A healthy watchdog inspection, which now emits no metrics record.**
  Nothing downstream may report it as a record that existed and could not be
  retrieved, and the rollup's "every agent run appears exactly once" must
  stay true — such a run is no longer an agent run.
- **Two persistence runs overlapping** — a scheduled sweep and a hand-driven
  single-run re-drive. Both must be safe, with no duplicate record and no
  lost record.
- **A run that concludes while a scheduled sweep is already past the point
  where it would have seen it.** It must be picked up by its own completion
  run or the next sweep, never stranded between two.

## Requirements *(mandatory)*

### Functional Requirements — A. The image check (P1)

- **FR-001**: When no container image is configured, a published stage run
  MUST contribute zero billed jobs for the image check — the check job is
  reported skipped rather than allocated.
- **FR-002**: FR-001 MUST hold for all 13 published stage workflows
  (`intake`, `clarify`, `plan`, `tasks`, `implement`, `finalize`, `cleanup`,
  `rebase`, `watchdog`, `pr-conversation`, `metrics-persist`,
  `auto-update-spec-kit`, `private-image-dogfood`), not a subset.
- **FR-003**: With a container image configured, the check MUST keep its
  fail-fast role and its placement — it runs before any other job's
  container is created — and a rejected credential or an unusable image MUST
  still skip every dependent job.
- **FR-004**: Every job that today reaches the image check through bare
  dependency skip-propagation MUST, after the rewrite, tolerate a *skipped*
  check while still requiring success from each of its other dependencies,
  stated explicitly per dependency. No dependent job may be widened to run
  merely because the workflow was not cancelled.
- **FR-005**: Each dependent job's set of run/skip outcomes over the cross
  product of its dependencies' outcomes MUST be unchanged from current
  `main`, except for the single new case "image check skipped".
- **FR-006**: The job-shape uniformity gates MUST be amended — never
  bypassed — to assert the new shape, and their self-tests extended
  accordingly.
- **FR-007**: A gate MUST fail when any dependent job in any published stage
  silently reverts to bare skip-propagation on the image check, naming the
  stage and the job.
- **FR-008**: Both the no-image branch and the image-rejected branch of the
  new shape MUST be proven by checked-in fixtures.

### Functional Requirements — B. The watchdog's clean path (P2)

- **FR-009**: A watchdog inspection whose aggregate signal set is empty and
  whose aggregate step completed MUST record "passed inspection"
  deterministically and MUST NOT execute any agent step.
- **FR-010**: The passed-inspection record MUST be written by deterministic
  code, never by an agent, and MUST be produced beside the aggregate that
  decided it.
- **FR-011**: The passed-inspection record MUST distinguish a full pass
  (every collector reported) from a partial pass (one or more collectors
  errored, so their evidence classes were not examined), preserving the
  wording distinction the watchdog makes today.
- **FR-012**: An inspection with at least one signal MUST behave exactly as
  it does on current `main` — same agent invocation, same filing, triage and
  action behaviour.
- **FR-013**: An inspection in which every collector failed MUST keep its
  existing "could not inspect" path, and MUST NOT emit a passed-inspection
  record.
- **FR-014**: Zero findings MUST still mean "record passed inspection, file
  nothing"; the duty of suppressing false positives stays with the
  collectors.
- **FR-015**: The watchdog's own runs MUST remain unexempted from inspection
  — this feature may not skip or soften them — and the self-dispatch cap
  MUST be unchanged.
- **FR-016**: A run that did not execute MUST still produce no signal.
- **FR-017**: The unhandled-failure report MUST still execute for every
  watchdog run, including one in which every other job died.
- **FR-018**: On the no-finding path, the run's billed job count MUST be the
  collection job plus at most one guaranteed-report job.
- **FR-019**: The agent-skip condition MUST key on an empty aggregate signal
  set alone, not on "zero signals AND zero failed collectors". A run with no
  signals, one or more failed collectors and at least one collector that
  reported MUST skip the agent and record a partial pass — the all-failed
  case stays with FR-013's "could not inspect" path. The agent weighs
  pre-computed signals, so an empty signal set
  leaves it nothing to weigh, and an evidence class no collector examined is
  not one the agent can examine either. The untrusted-collector set MUST stay
  an input to the agent on the signal-bearing path, unchanged.
- **FR-020**: Folding the watchdog wrapper's run resolution into the stage IS
  in scope for this feature. The published `run-name` input MUST become
  optional, resolved inside the stage's existing inspected-run lookup when it
  is empty, so the wrapper reduces to a single `uses:` job that allocates no
  runner of its own. The change MUST be additive, with a default that
  preserves current behaviour, and MUST be recorded as a versioned decision
  in the watchdog stage's contract (a minor version and a release note, not a
  breaking change).
- **FR-031**: After FR-009, a watchdog inspection that finds nothing MUST
  emit no metrics record at all — the diagnose job held the only run-summary
  call site. The lifecycle rollup's "every agent run appears exactly once"
  MUST stay correct on that basis, and no consumer may report such a run as a
  record that existed and could not be retrieved.

### Functional Requirements — C. Metrics persistence (P3)

- **FR-021**: No persistence run may be spent on a completion that emitted no
  record; a record-bearing completion costs at most one persistence run.
- **FR-022**: Every executed run that emitted a metrics record MUST still be
  persisted exactly once, identified by its record key, whichever path
  reaches it; the existing idempotence and write-contention retry behaviour
  MUST be preserved.
- **FR-023**: A record belonging to one of the nine stage workflows that
  keeps its completion trigger MUST land within minutes of its run
  concluding — the watchdog's cross-run collectors and the lifecycle rollup
  read that history mid-flight, and a record landing hours late blinds both.
  A record the scheduled sweep owns MUST land within one sweep interval.
- **FR-024**: The single-run re-drive triggered by hand MUST be preserved,
  and MUST be safe to use while another persistence run is in flight.
- **FR-025**: The persistence path MUST stay isolated: it never touches the
  origin run it collects from, and a failure in it fails only itself.
- **FR-026**: Persistence MUST NOT be moved inside the watchdog run —
  isolation is why it is a separate workflow, and conversation-stage
  completions are not watched.
- **FR-027**: Coverage MUST NOT depend on a single path: any record-bearing
  run that no completion-triggered persistence reached — every signal-bearing
  watchdog inspection, and any stage completion whose own run failed or never
  fired — MUST be picked up by the next scheduled sweep, which resumes from a
  durable high-water mark rather than from a fixed lookback.
- **FR-028**: A run whose metrics artifacts have expired before persistence
  reached it MUST be recorded with an explicit outcome rather than silently
  dropped or retried indefinitely.
- **FR-029**: The sweep-style input the metrics-persist stage gains MUST be
  additive, with a default that preserves today's single-run behaviour, and
  MUST be recorded as a versioned decision in that stage's contract.
- **FR-030**: The persistence model MUST be per-record-bearing-completion
  plus a daily scheduled sweep, composed of exactly these four parts:
  (a) the persistence wrapper keeps its completion trigger for the nine stage
  workflows whose records are read back promptly (`intake`, `clarify`,
  `plan`, `tasks`, `implement`, `finalize`, `cleanup`, `rebase`,
  `pr-conversation`); (b) the wrapper drops the watchdog from that trigger,
  because after FR-031 a healthy inspection emits no record and a run
  reacting to it would bill a minute to find nothing; (c) the wrapper owns a
  daily scheduled sweep that lists runs concluded since the high-water mark
  and persists every record-bearing run not already in the records file; and
  (d) no `concurrency`-based coalescing — at this pipeline's rhythm the
  pending-slot replacement would fire rarely, for the cost of cancelled runs
  in the run list and the same contract change. The hand-driven single-run
  re-drive stays (FR-024).

### Out of Scope

- The watchdog self-verifier's own one-job-per-inspection cost. Its shape is
  a question for the spec that owns the watchdog's self-check, and #403
  already cut its volume along with the watchdog's.
- Reducing the count of jobs inside `collect`, `diagnose`, `triage` or `act`
  on paths that actually do work. This feature targets no-op and healthy
  paths only.
- Any new agent invocation anywhere. Sub-problem B removes one from the
  common path and adds none.
- Changing what the metrics records contain, or how the cost line is
  formatted.
- Usage-page-level cost targets as acceptance criteria.

### Key Entities

- **Image check outcome**: for a given stage run, one of skipped (no image
  configured), success (image usable), or failure (image or credential
  rejected). It is the gate every other job in the stage reads.
- **Aggregate inspection evidence**: for a watchdog inspection, the set of
  signals the collectors emitted, the count of collectors that ran, and the
  count that failed. It is what decides whether an agent is needed.
- **Passed-inspection record**: the deterministic statement posted to the
  lifecycle issue when an inspection found nothing, carrying whether the
  pass was full or partial.
- **Persistence high-water mark**: the durable marker, kept beside the
  records, describing how far the last sweep got, so the next scheduled sweep
  knows where to resume instead of scanning a fixed lookback.
- **Metrics record**: one line per pipeline run that emitted one — after
  FR-031 a healthy watchdog inspection does not — keyed so that appending it
  twice is a no-op.

## Success Criteria *(mandatory)*

Every criterion below is verifiable from a single run's job list — job
count, which jobs were skipped, whether an agent step executed — or from the
records file. None depends on the usage page.

### Measurable Outcomes

- **SC-001**: For each of the 13 published stages, a run invoked with no
  container image lists the image check as skipped and lists zero billed
  jobs for it.
- **SC-002**: For each of the 13 published stages, a run invoked with an
  unusable container image lists the image check as failed and every
  dependent job as skipped.
- **SC-003**: Across all 13 published stages, every job's run/skip outcome
  for every combination of its dependencies' outcomes matches current
  `main`, except for the new "image check skipped" case.
- **SC-004**: For each of the 13 published stages, a no-op run with no image
  configured bills exactly one job fewer than the same no-op run on current
  `main`, and matches the concrete per-stage job count the plan records.
- **SC-005**: A watchdog inspection that finds nothing lists the diagnose job
  as skipped, lists no agent step in any job, and posts exactly one
  passed-inspection record — the full one when every collector reported, the
  partial one when some errored.
- **SC-006**: A watchdog inspection that finds nothing bills at most two
  jobs.
- **SC-007**: A watchdog inspection carrying at least one signal produces the
  same issue-filing, triage and action outcomes as current `main` for the
  same evidence.
- **SC-008**: Every watchdog run lists an executed unhandled-failure report,
  including runs in which every other job failed.
- **SC-009**: Over a 24-hour window of ordinary pipeline traffic, the number
  of persistence workflow runs created is at most the number of
  record-bearing completions plus the number of scheduled sweeps, and zero
  persistence runs were created for completions that emitted no record.
- **SC-010**: For that same window, every executed run that emitted a metrics
  record appears in the records file exactly once.
- **SC-011**: For that same window, the interval between a run concluding and
  its record appearing is under ten minutes for every stage run on the
  completion trigger, and within one sweep interval for every record the
  sweep owns.
- **SC-012**: Every gate this feature ships or amends fails on a purpose-built
  fixture for each of its failure branches, and passes on the real tree.
- **SC-013**: No workflow in the repository gains an agent invocation as a
  result of this feature.

## Assumptions

- **All 13 stages, not a subset.** Sub-problem A is implemented as the
  job-level skip plus the dependent-job rewrite across every published
  stage, rather than dropping the check from `metrics-persist` alone. It is
  the only option that reaches every stage, and the adopter-uniformity
  argument is preserved mechanically by the amended gates rather than by an
  exception.
- **The image check job stays, in its current position, in every stage.**
  This feature changes when it is *allocated*, never whether it exists.
- **Sub-problem A lands first.** B and C edit files A rewrites, so the plan
  sequences A ahead of both. Whether the three ship as one PR or three is a
  planning decision, not a specification one.
- **The guaranteed unhandled-failure report keeps its own job** unless the
  plan finds a shape that preserves its guarantee — that it survives every
  other job dying — at lower cost. One guaranteed minute is an acceptable
  price for that guarantee.
- **The existing aggregate outputs are the input to the new decision.** The
  watchdog already computes whether evidence is available, the signal set,
  which collectors failed, and which were untrusted; the agent-skip decision
  is derived from those, not from new collection.
- **Existing machinery is reused, not re-typed**: the persistence
  composite's idempotence and write-contention retry, the run-listing
  capability used for a high-water-mark scan, and the scheduled wrappers as
  the precedent for the daily sweep's trigger.
- **Completion events only fire for workflows on the default branch**, and a
  hand-driven dispatch exists for re-drives; any sweep shape must live with
  both facts.
- **The three evidence issues (#404, #405, #406) are closed by hand** with a
  pointer to this feature's final PR when it merges. That is a maintainer
  action, not a requirement of the implementation.
- **This repository is public**; nothing in this specification or its
  implementation names a downstream consumer.
