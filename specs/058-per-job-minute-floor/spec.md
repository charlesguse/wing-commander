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
18,858 job runs. Spec 057 / PR #403 (merged 2026-09-19) removed the largest
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
spec lifecycle drives dozens of completions in an hour, which is exactly
what makes coalescing pay and what makes a fixed schedule a poor fit alone.

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

The watchdog inspects a run that executed. Every collector ran, and none of
them emitted a signal. The watchdog records "passed inspection" on the
lifecycle issue from a deterministic step, files nothing, invokes no agent,
and bills only the collection job plus whatever guaranteed-report minute
cannot be folded away. A run with any signal — or with a failed collector —
reaches the diagnose agent and behaves exactly as it does today, including
the weaker "passed inspection on N of M collectors" wording when a collector
errored.

**Why this priority**: it removes an agent call from the common path, which
is the part of this spec that returns real budget on the usage window the
pipeline shares with its maintainers' sessions. It is second because it
edits `watchdog.yml`, which User Story 1 also rewrites.

**Independent Test**: drive one watchdog inspection over a healthy run and
one over a run carrying a known signal. Read both runs' jobs APIs: the first
shows no diagnose job and a passed-inspection comment on the issue; the
second shows diagnose running and the same behaviour as today.

**Acceptance Scenarios**:

1. **Given** a watchdog inspection where every collector ran and the
   aggregate signal set is empty, **When** the run completes, **Then** no
   agent step executed anywhere in the run, a "passed inspection" record was
   posted by a deterministic step, and no issue was filed or updated.
2. **Given** a watchdog inspection whose aggregate signal set is non-empty,
   **When** the run completes, **Then** the diagnose agent ran and the run's
   filing, triage and action behaviour is byte-for-byte what current `main`
   produces for the same evidence.
3. **Given** a watchdog inspection where every collector failed, **When** the
   run completes, **Then** the existing "could not inspect" path runs
   unchanged, and no passed-inspection record is posted.
4. **Given** any watchdog run, including one inspecting the watchdog's own
   runs, **When** the inspection is selected, **Then** it is neither skipped
   nor softened — the watchdog's own runs stay unexempted.
5. **Given** any watchdog run at all, including one where every other job
   died, **When** the run completes, **Then** the unhandled-failure report
   still executed.

---

### User Story 3 - Metrics persistence pays per burst, not per completion (Priority: P3)

A spec lifecycle drives dozens of stage completions in an hour. Instead of
one persistence run per completion, the pipeline's persistence work
collapses: a day of that traffic yields on the order of tens of persistence
runs, not hundreds. Every executed stage run is still persisted exactly
once, identified by its record key, and its record lands within minutes of
the run concluding. A maintainer can still re-drive persistence for one
named run by hand.

**Why this priority**: it is the largest single consumer, but it is last
because it is the only sub-problem that changes *when* a durable write
happens rather than *whether* an idle job is billed, and because its shape
depends on a decision the owner has not made (see the open questions).

**Independent Test**: drive a burst of stage completions and count the
persistence runs created, then read the records file: every executed run
appears exactly once, and the record count matches the completions.

**Acceptance Scenarios**:

1. **Given** a burst of stage completions inside one short window, **When**
   the burst has settled, **Then** the number of persistence workflow runs
   created is far smaller than the number of completions, and every executed
   run in the burst has exactly one record.
2. **Given** a stage run that concluded and whose metrics artifacts exist,
   **When** persistence next runs, **Then** its record is appended within
   minutes of the run concluding.
3. **Given** a run that has already been persisted, **When** persistence
   processes it again for any reason, **Then** no duplicate record is
   appended — idempotence by record key holds.
4. **Given** a maintainer who wants one named run persisted now, **When**
   they trigger the single-run re-drive by hand, **Then** that run is
   persisted, and it is safe to do so while a coalescing or scheduled
   persistence run is already in flight.
5. **Given** a persistence path that fails for any reason, **When** it fails,
   **Then** it fails only itself — it never touches, marks or fails the
   origin run it is collecting from.
6. **Given** a run whose metrics artifacts have expired before persistence
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
- **A persistence run that is superseded while pending.** If coalescing
  replaces a queued run, that run concludes as cancelled in the run list;
  nothing may treat that cancellation as a persistence failure, and no
  completion it was queued for may be lost.
- **Two persistence runs overlapping** — a coalesced or scheduled sweep and
  a hand-driven single-run re-drive. Both must be safe, with no duplicate
  record and no lost record.
- **A completion that arrives while the previous persistence run is already
  past the point where it would have seen it.** It must be picked up by the
  next run, not stranded between two.

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

- **FR-009**: A watchdog inspection whose collectors all ran and whose
  aggregate signal set is empty MUST record "passed inspection"
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
- **FR-019**: [NEEDS CLARIFICATION: does the agent-skip condition key on
  "zero signals" alone, or on "zero signals AND zero failed collectors"? A
  run with one failed collector and no signals is today a weaker pass; under
  the first reading it skips the agent and records a partial pass, under the
  second it still pays the agent call.]
- **FR-020**: [NEEDS CLARIFICATION: is folding the watchdog wrapper's run
  resolution into the stage — which makes the published `run-name` input
  optional and is therefore a versioned contract change under Constitution
  VII — in scope for this spec, or deferred to a later one? Deferring keeps
  one wrapper job (one billed minute) per inspection.]

### Functional Requirements — C. Metrics persistence (P3)

- **FR-021**: Persistence MUST cost per burst of completions rather than per
  completion: a day of ordinary pipeline traffic yields on the order of tens
  of persistence runs, not hundreds.
- **FR-022**: Every executed stage run MUST still be persisted exactly once,
  identified by its record key; the existing idempotence and
  write-contention retry behaviour MUST be preserved.
- **FR-023**: A record MUST land within minutes of its run concluding.
- **FR-024**: The single-run re-drive triggered by hand MUST be preserved,
  and MUST be safe to use while another persistence run is in flight.
- **FR-025**: The persistence path MUST stay isolated: it never touches the
  origin run it collects from, and a failure in it fails only itself.
- **FR-026**: Persistence MUST NOT be moved inside the watchdog run —
  isolation is why it is a separate workflow, and conversation-stage
  completions are not watched.
- **FR-027**: Work MUST NOT be lost at a boundary: a completion arriving
  while a persistence run is already past the point it would have seen it
  MUST be picked up by the next run.
- **FR-028**: A run whose metrics artifacts have expired before persistence
  reached it MUST be recorded with an explicit outcome rather than silently
  dropped or retried indefinitely.
- **FR-029**: Any change to a published stage input that this sub-problem
  requires (for example making the single-run identifier optional) MUST be
  recorded as a versioned decision in that stage's contract.
- **FR-030**: [NEEDS CLARIFICATION: which persistence model — (a) coalescing
  on completion: keep the completion trigger, have each run persist
  everything outstanding since a high-water mark under a concurrency group
  that does not cancel in progress, so a burst collapses to at most one
  running and one pending run, with a daily scheduled backstop; (b) a
  periodic scheduled sweep only, and at what cadence; or (c) accept
  per-completion persistence once sub-problem A has removed its second job?
  (a) keeps per-completion latency and pays per burst but makes the
  single-run identifier optional and leaves replaced pending runs concluding
  as cancelled; (b) is the simplest shape but trades latency for cadence;
  (c) ships nothing here.]

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
- **Persistence high-water mark**: the durable marker describing which
  concluded runs have already been persisted, so the next persistence run
  knows where to resume.
- **Metrics record**: one line per executed pipeline run, keyed so that
  appending it twice is a no-op.

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
- **SC-004**: A no-op stage run (nothing to do, no image configured) bills at
  most one job more than the number of jobs that actually performed work.
- **SC-005**: A watchdog inspection that finds nothing lists no agent step in
  any job, and posts exactly one passed-inspection record.
- **SC-006**: A watchdog inspection that finds nothing bills at most two
  jobs.
- **SC-007**: A watchdog inspection carrying at least one signal produces the
  same issue-filing, triage and action outcomes as current `main` for the
  same evidence.
- **SC-008**: Every watchdog run lists an executed unhandled-failure report,
  including runs in which every other job failed.
- **SC-009**: Over a 24-hour window of ordinary pipeline traffic, the number
  of persistence workflow runs created is at most one tenth of the number of
  stage completions in that window.
- **SC-010**: For that same window, every executed stage run appears in the
  records file exactly once.
- **SC-011**: The interval between a stage run concluding and its record
  appearing is under ten minutes for every run in that window.
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
  capability used for a high-water-mark scan, the per-spec and intake
  concurrency groups as the coalescing precedent, and the scheduled wrappers
  as the schedule precedent.
- **Completion events only fire for workflows on the default branch**, and a
  hand-driven dispatch exists for re-drives; any sweep shape must live with
  both facts.
- **The three evidence issues (#404, #405, #406) are closed by hand** with a
  pointer to this feature's final PR when it merges. That is a maintainer
  action, not a requirement of the implementation.
- **This repository is public**; nothing in this specification or its
  implementation names a downstream consumer.
