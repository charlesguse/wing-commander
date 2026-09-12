# Feature Specification: Rate-limited agent verdict

**Feature Branch**: `047-rate-limited-verdict`

**Created**: 2026-09-12

**Status**: Draft

**Input**: User description (GitHub issue #306): "Watchdog: report a usage-window 429 as a distinct rate-limited verdict instead of filing a pipeline defect"

## Overview

When the organisation's five-hour usage window is exhausted, every model call
inside an agent step is rejected. The step dies after one turn, at zero cost,
having done no work at all. Today that outcome is indistinguishable from an
agent that crashed: the shared verdict classifier calls it `failed`, the
watchdog's diagnose reporter says "the diagnose agent failed, so this run was
**not inspected**", and the deterministic stage-8b verifier files a
`pipeline-defect` issue. Three such filings (#278 twice, #300) each cost a
maintainer a log dive to reach the conclusion "not a defect".

The evidence needed to tell the two apart is already written down
deterministically in the execution-output artifact every agent step uploads: a
`rate_limit_event` record naming the window and its reset time, and a terminal
result record whose failure cause is an API 429. This feature teaches the
pipeline to read that evidence and report the outcome as what it is — the
usage window ran out, retry after the reset time — rather than as a pipeline
defect that needs a human.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The maintainer is not paged for a usage-window outage (Priority: P1)

A watchdog run starts while the usage window is exhausted. Its diagnose agent
is rejected on its first call. Instead of a `pipeline-defect` issue titled
"stage 8 run failed deterministic verification", the maintainer sees a report
that says the usage window was exhausted and names the time it resets. No
issue is filed for this class, and the maintainer's triage queue stays empty.

**Why this priority**: This is the entire cost the issue is paying to remove.
Every other story is refinement on top of it. Delivered alone it already
returns the three log dives per incident to zero.

**Independent Test**: Replay an execution-output artifact from a known 429 run
(the evidence links in #300 name three) through the verdict classifier and the
stage-8b verification path, and confirm the reported outcome names the usage
window and its reset time, and that no `pipeline-defect` issue is created.

**Acceptance Scenarios**:

1. **Given** an execution transcript carrying a rejected `rate_limit_event` for
   the five-hour window and a terminal result whose failure is an API 429,
   **When** the shared verdict classifier reads it, **Then** the verdict is
   `rate-limited` (not `failed`) and the reason text names the window and its
   reset time in a human-readable form.
2. **Given** that same transcript, **When** the watchdog's diagnose reporter
   posts its outcome, **Then** the comment says the usage window was exhausted
   and the run was not inspected because of it, and does not describe the agent
   as having failed or crashed.
3. **Given** a stage-8 run whose only verification failures are caused by that
   rate-limited diagnose step, **When** the stage-8b verifier runs, **Then** it
   does not create or append to a `pipeline-defect` issue.
4. **Given** a stage-8 run that is rate-limited AND also breaches an unrelated
   check (for example its duration band), **When** the stage-8b verifier runs,
   **Then** the unrelated failure is still reported and still files as it does
   today — rate-limiting suppresses only the reasons it actually explains.

---

### User Story 2 - The uninspected run is still on the record (Priority: P2)

Suppressing the filing must not suppress the fact. A maintainer who asks "did
anything go uninspected while the window was out?" must be able to answer it
without reading run logs.

**Why this priority**: Without it, P1 trades a noisy true signal for a silent
blind spot — the explicit trade-off the issue asks the owner to decide. It is
P2 rather than P1 because the recording surface is the smaller half of the
work and is useless without P1's classification.

**Independent Test**: Drive two rate-limited runs and confirm both are
discoverable from a single durable place, each naming the run and its reset
time, without either creating a new triage-bearing issue.

**Acceptance Scenarios**:

1. **Given** a run classified `rate-limited`, **When** reporting completes,
   **Then** the fact that this run went uninspected is recorded durably, with a
   link to the run and the window's reset time.
2. **Given** several rate-limited runs inside one usage window, **When** they
   are recorded, **Then** they accumulate in one place rather than producing
   one new artefact per run.

---

### User Story 3 - Every stage names the outcome the same way (Priority: P3)

The verdict classifier is shared by every agent-bearing stage (intake,
clarify, plan, tasks, implement, finalize, cleanup, rebase, pr-conversation,
watchdog, spec-kit auto-update). A window exhaustion hits whichever stage is
running at the time, so any of them can produce this transcript.

**Why this priority**: Correctness for the other stages, not a new capability.
Without it, the same outage reads as "rate-limited" in the watchdog and as an
unrecognised outcome everywhere else.

**Independent Test**: Feed a rate-limited transcript to the metrics summary a
non-watchdog stage produces, and confirm it names the outcome as
rate-limited rather than degrading it to an unclassified or failed outcome.

**Acceptance Scenarios**:

1. **Given** a rate-limited transcript at any agent call site, **When** that
   stage summarises the run, **Then** the summary names the rate-limited
   outcome and the reset time, and the durable metrics record carries the same
   outcome value.
2. **Given** a rate-limited transcript, **When** the stage's cost accounting
   runs, **Then** the run is not counted as a pipeline failure.

---

### Edge Cases

- **A 429 the runtime recovered from.** A transcript can carry a
  `rate_limit_event` mid-run and still finish successfully. Such a run MUST
  stay `healthy`; the rate-limited verdict is reserved for runs whose terminal
  outcome is the rejection.
- **A 429 after real work.** The window can run out mid-run, leaving a
  transcript with many turns and non-zero cost that still ends in a rejection.
  The outcome is still `rate-limited` — but the work it did was still
  unfinished, so the report must not imply the run merely "did not start".
- **A rejection with no reset time.** The reset time may be absent or
  unparseable. The verdict still applies; the report says the reset time is
  unknown rather than printing an empty or epoch-zero timestamp.
- **A non-429 API error.** Any other terminal API error (500s, auth failures,
  the binary-not-found shape seen on #278's 2026-09-08 runs) is NOT
  rate-limited and must keep filing exactly as it does today.
- **A rate-limit-shaped transcript that is otherwise malformed.** Missing or
  unparseable transcripts keep their existing unclassifiable outcome; the new
  classification never rescues a transcript that cannot be read.
- **A rate-limited run that ALSO has an independent defect** (a stalled job, a
  red job, a failed evidence collector). The independent defect is reported and
  filed as today.
- **The classifier itself must never fail.** The composite that produces the
  verdict is contractually forbidden from failing its own step; adding this
  classification must not introduce a path that does.

## Requirements *(mandatory)*

### Functional Requirements

**Classification**

- **FR-001**: The shared agent-run classifier MUST emit a distinct
  `rate-limited` verdict for a transcript whose terminal result is a rejected
  model call caused by usage-window exhaustion, instead of the generic `failed`
  verdict it emits today.
- **FR-002**: The classifier MUST determine `rate-limited` solely from the
  already-written execution transcript — no network call, no second agent
  invocation, no job log parsing.
- **FR-003**: The classifier MUST expose the window's reset time to its callers
  when the transcript carries one, and MUST expose an explicit "unknown" when it
  does not.
- **FR-004**: The classifier MUST NOT classify as `rate-limited` a run that
  reached a successful terminal result, even if the transcript records one or
  more rate-limit events along the way.
- **FR-005**: The classifier MUST keep every existing verdict
  (`healthy`, `exhausted`, `failed`, `unclassifiable`) unchanged for every
  transcript shape that does not meet FR-001's condition, and MUST continue to
  never fail its own step.
- **FR-006**: The rate-limited determination MUST live in exactly one place
  consumed by all stages, consistent with this repository's "shared logic has
  exactly one home" rule — no per-workflow copy of the detection.

**Watchdog reporting**

- **FR-007**: The watchdog's diagnose reporting MUST, for a `rate-limited`
  diagnose step, post a report that states the usage window was exhausted, names
  the reset time (or "unknown"), and states that the inspected run was therefore
  not inspected.
- **FR-008**: That report MUST NOT describe the agent as having failed or
  crashed, and MUST be distinguishable at a glance from the existing
  "diagnose failed" report.
- **FR-009**: A `rate-limited` diagnose step MUST NOT be reported as a clean
  bill of health or as "passed inspection".

**Verifier behaviour**

- **FR-010**: The deterministic stage-8b verifier MUST recognise a stage-8 run
  whose diagnose step was rate-limited, and MUST NOT file or append to a
  `pipeline-defect` issue for the verification reasons that rate-limiting
  explains (the crashed-agent reporter having run, the absent successful
  terminal result, and the short-duration band breach that a one-turn death
  produces).
- **FR-011**: The verifier MUST continue to file for any verification reason
  that rate-limiting does not explain, in the same run.
- **FR-012**: [NEEDS CLARIFICATION: Where does the "this run went uninspected"
  fact land, and does the stage-8b job go red? Options: (a) a comment on one
  rolling tracking issue, job green; (b) an issue carrying a distinct
  `usage-limit` label that the watchdog dedups on, job green; (c) run summary
  only, job green; (d) any of the above but the job still turns red.]
- **FR-013**: Whatever surface FR-012 selects, the record MUST name the
  inspected run, the reset time, and the fact that no inspection took place,
  and MUST accumulate rather than multiply across runs inside one window.

**Fleet-wide consistency**

- **FR-014**: Every stage's run summary and durable metrics record MUST carry
  the `rate-limited` outcome for a rate-limited transcript, rather than
  degrading it to an unclassified or failed outcome.
- **FR-015**: [NEEDS CLARIFICATION: Outside the watchdog, does `rate-limited`
  behave as a failure? Options: (a) every stage's loud-failure step stays red
  as it is today for any non-healthy verdict; (b) `rate-limited` is exempted
  fleet-wide, staying loud in the log but not red; (c) `rate-limited` is
  exempted only where a stage would otherwise file or comment on an issue.]
- **FR-016**: The new verdict MUST be covered by the existing deterministic gate
  that exercises the classifier against synthetic transcripts, with at least the
  positive case (terminal 429 rejection), the recovered-429 negative case, and
  the non-429 API error negative case.
- **FR-017**: Documentation of the verdict vocabulary that ships alongside the
  classifier MUST list `rate-limited` wherever the existing four verdicts are
  enumerated.

### Key Entities

- **Rate-limit event**: The transcript record stating that a model call was
  rejected because a usage window was exhausted. Carries which window and when
  it resets.
- **Terminal result record**: The last record of a transcript, stating how the
  run ended. For this feature, the relevant shape is a terminal API error whose
  status is 429.
- **Verdict**: The single deterministic answer to "was this agent run healthy",
  produced once per agent step and consumed by every reporter, summary, and
  durable record downstream. Gains one new value.
- **Uninspected-run record**: The durable statement that a particular pipeline
  run went uninspected because the usage window was out. Surface to be decided
  (FR-012).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero triage-bearing defect reports are produced for usage-window
  exhaustion — down from three over the ~2 weeks the issue documents.
- **SC-002**: A maintainer can tell "usage window was out" from "the pipeline
  broke" by reading a single report, without opening run logs or downloading an
  artifact; the time to reach "not a defect" drops from a log dive to under one
  minute.
- **SC-003**: Every run that goes uninspected because of the usage window is
  discoverable from one place, with its reset time, within one navigation step
  of the pipeline's issue board.
- **SC-004**: 100% of the runs named in the issue's evidence (three 2026-09-12
  runs, one 2026-08-28 run) classify as rate-limited when their transcripts are
  replayed, and the 2026-09-08 binary-not-found runs continue to classify as
  failures.
- **SC-005**: No currently-passing deterministic gate regresses, and no existing
  verdict changes for any transcript that is not a terminal usage-window
  rejection.

## Assumptions

- The execution-output artifact is the sole evidence source. The issue
  documents the exact fields present (`rate_limit_event` with
  `status: rejected`, `rateLimitType: five_hour`, `resetsAt`; a terminal result
  with `terminal_reason: api_error`, `api_error_status: 429`); this spec treats
  those as the observed shape of today's runtime and assumes the classifier
  tolerates their absence rather than requiring all of them.
- The qualifying condition is the *terminal* outcome being a usage-window
  rejection. The one-turn, zero-cost shape observed in the cited runs is
  characteristic but not required — a rate limit that lands mid-run and kills it
  is the same outcome.
- Window types other than the five-hour window (should other usage windows
  exist) are treated the same way; the window's identity is reported, not used
  to gate the classification.
- Automatic retry after the reset time is out of scope. This feature reports
  and records; re-driving a rate-limited run stays a human action, as it is
  today.
- The verdict string is consumed by machinery inside this repository only; no
  external consumer depends on the closed set of four values. Adding a fifth is
  additive, not a breaking change.
- The watchdog pause switch, dedup logic, and finding-classification vocabulary
  are untouched by this feature.
