# Feature Specification: Restore Reliable Watchdog Diagnosis — Stop Masked Diagnose-Agent Crashes

**Feature Branch**: `023-reliable-diagnose-verdict`

**Created**: 2026-07-25

**Status**: Draft

**Input**: User description (GitHub lifecycle issue #117, auto-filed by the deterministic stage-8b verifier): "watchdog-verify: stage 8 run failed deterministic verification" — the diagnose agent FAILED (its "diagnose failed" reporter ran) so the inspected run was never actually inspected; the unhandled-failure safety net fired; the diagnose execution log has no successful terminal result record (empty output, `is_error`, or an error subtype); and the diagnose job log carries an agent crash signature that `continue-on-error` hid from every API conclusion.

## Overview

The pipeline watchdog (specified in `specs/015-pipeline-watchdog/` and repaired in
`specs/020-fix-watchdog/`) is the pipeline's automated first responder: after a
pipeline stage finishes, the watchdog gathers that run's evidence, has a
**diagnose** step inspect it, and posts a verdict — "passed inspection," a
finding, or "could not inspect" — to the lifecycle issue. A separate deterministic
stage-8b verifier then checks, without any judgment, that the watchdog run actually
did its job; when it did not, the verifier turns red and files a `pipeline-defect`
issue so a broken watchdog is never quiet.

This feature is a **bug fix**. The stage-8b verifier caught, and reported in issue
#117, that a stage 8 watchdog run *looked* green while its diagnose step had in fact
crashed: the diagnose agent died without producing a genuine terminal result, the
watchdog step's `continue-on-error` behavior kept the run green so the crash was
invisible in the API conclusions, the workflow's own "diagnose failed" reporter and
internal safety net fired, and no real verdict was ever reached. The inspected run
was therefore never actually inspected, even though nothing turned red on its own.

The desired end state is that a watchdog diagnosis either produces a **genuine,
recorded verdict** or has its failure **surfaced honestly** — a diagnose-agent
crash must never again present as a healthy, passed run — and that the specific
crash observed in issue #117 is root-caused and guarded against so this class of
failure stops recurring and stage 8 runs pass the stage-8b deterministic
verification going forward.

This spec captures the *observable behavior* the fix must achieve. It does not
re-specify the watchdog's or the verifier's design; where behavior is already
defined by `specs/015-pipeline-watchdog/` and `specs/020-fix-watchdog/`, this
feature's requirement is that the behavior actually occurs in practice.

## User Scenarios & Testing *(mandatory)*

Today a maintainer relies on two things being true together: after a pipeline stage
completes, the watchdog reaches a real verdict on it, and the stage-8b verifier
confirms the watchdog itself did its job. Issue #117 is the case where the first
broke silently and only the second caught it — the watchdog run was green, but its
diagnose step had crashed and produced no verdict, so the inspected run was never
truly inspected. The maintainer is left with an auto-filed defect issue and a stage
that never actually reported on the run it was supposed to watch.

### User Story 1 - Every watchdog diagnosis reaches a genuine verdict or an honest failure (Priority: P1)

As a maintainer, when the watchdog runs its diagnose step against a completed run,
I want it to end in exactly one of two states — a **genuine, recorded verdict**
(passed inspection, a finding, or an honest "could not inspect") or a **clearly
surfaced failure** — and never in a third state where the diagnose step crashed but
the run still presents as healthy and passed, so that a green watchdog run always
means the run was actually inspected.

**Why this priority**: This is the irreducible core of the defect in issue #117. A
diagnose step that can crash while the run stays green makes every watchdog verdict
untrustworthy: the maintainer cannot tell an inspected run from a crashed one
without re-reading raw logs, which is exactly the manual toil the watchdog exists to
remove. Closing the "silently green crash" gap restores that trust.

**Independent Test**: Trigger the watchdog against a completed run and force or
observe the diagnose agent to crash without producing a terminal result; confirm the
run does **not** present as a passed, healthy diagnosis — the outcome is either a
genuine verdict or a surfaced failure that the stage-8b verifier flags — and that a
normal run still reaches a genuine verdict.

**Acceptance Scenarios**:

1. **Given** a watchdog run whose diagnose agent completes normally, **When** the diagnose step finishes, **Then** it records a genuine terminal result (a real inspection outcome), and the run passes stage-8b deterministic verification.
2. **Given** a watchdog run whose diagnose agent crashes before producing a terminal result (as in issue #117), **When** the diagnose step finishes, **Then** the run does not present as "passed inspection," the crash is surfaced rather than masked, and the maintainer can tell the run was not inspected.
3. **Given** the specific stage 8 run reported in issue #117, **When** an equivalent run executes after the fix, **Then** it reaches a genuine verdict instead of the masked-crash outcome and passes stage-8b verification.

---

### User Story 2 - A crashed diagnosis never masquerades as "passed inspection" on the lifecycle issue (Priority: P1)

As a maintainer, I want the lifecycle issue to reflect the *true* diagnosis
outcome — never a "passed inspection" note written over a run that actually
crashed or produced an empty/`is_error`/error-subtype result — so that what I read
on the issue is trustworthy without cross-checking the raw execution log.

**Why this priority**: A verdict that is wrong is worse than a verdict that is
missing: "passed inspection" posted over a crashed diagnosis actively misleads the
maintainer into believing a run was cleared when it never was. Making the posted
verdict match reality is inseparable from US1 and equally load-bearing for trust.

**Independent Test**: For a run whose diagnose produced an empty output (`[]`), an
`is_error` result, or an error subtype, confirm the lifecycle issue does **not**
receive a "passed inspection" note and instead reflects the honest failure.

**Acceptance Scenarios**:

1. **Given** a diagnose step whose execution output has no successful terminal result record, **When** the watchdog decides what to post, **Then** it does not post "passed inspection" and instead records that the run could not be inspected.
2. **Given** a diagnose step that produced a genuine "passed inspection" result, **When** the watchdog posts to the lifecycle issue, **Then** the note is posted and the run is verifiably healthy.

---

### User Story 3 - The issue-#117 crash class is root-caused and stops recurring (Priority: P2)

As a maintainer, I want the specific failure that produced issue #117 — a diagnose
agent that crashed with an agent-crash signature and left no terminal result — to be
diagnosed to root cause and guarded against, so that stage 8 stops auto-filing this
`pipeline-defect` issue and the watchdog resumes reliably reporting on the runs it
watches.

**Why this priority**: US1 and US2 make a crash *honest*; this story makes the
observed crash *stop happening*. It restores the watchdog to routine working order
and ends the recurring defect noise, but it depends on the honesty guarantees above
being in place first so that any residual failure is still surfaced rather than
hidden.

**Independent Test**: After the fix, run the watchdog across a representative set of
stage completions and confirm the diagnose step reaches genuine verdicts, the
agent-crash signature from issue #117 does not reappear, and stage-8b verification
passes for those runs.

**Acceptance Scenarios**:

1. **Given** the conditions that triggered the issue-#117 crash, **When** the watchdog diagnose step runs after the fix, **Then** it no longer exhibits that crash and produces a genuine verdict.
2. **Given** a series of watchdog runs after the fix, **When** stage-8b verifies each, **Then** none fail verification for the issue-#117 reasons (masked diagnose crash, no terminal result, safety net fired).

---

### Edge Cases

- **Genuinely un-inspectable run**: When evidence truly cannot be gathered or the diagnose agent legitimately cannot reach a verdict, the outcome must be an honest "could not inspect" surfaced to the maintainer — never a masked green pass. When the diagnose agent fails, the watchdog retries the diagnosis only for recognized transient/infrastructure crash signatures; for all other failures it records the honest failure immediately with no retry.
- **Transient vs. persistent crash**: A one-off infrastructure hiccup versus a repeatable crash class should both end honestly; the fix must not convert a transient failure into a false pass.
- **Safety net interaction**: If the internal unhandled-failure safety net fires, that internal failure must remain visible (the run must not be reported as a clean success) so the stage-8b verifier can still catch it.
- **Verifier remains the backstop**: The fix must not weaken or bypass the stage-8b deterministic verifier; a healthy run must pass it, and a masked crash must still fail it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The watchdog diagnose step MUST end in exactly one of two observable states — a genuine recorded verdict, or a surfaced failure — and MUST NOT end in a state where the diagnose agent crashed while the run still presents as a healthy, passed diagnosis.
- **FR-002**: A watchdog diagnosis MUST be treated as genuine only when the diagnose agent produced a real, successful terminal result; an empty output, a missing terminal result, an error result, or an error subtype MUST NOT be reported as "passed inspection."
- **FR-003**: When the diagnose agent crashes or fails to produce a genuine terminal result, the watchdog MUST surface that failure to the maintainer (e.g., on the lifecycle issue as an honest "could not inspect"/failure) rather than posting a passed-inspection verdict.
- **FR-004**: A diagnose-agent crash MUST NOT be masked into an all-green run: the true outcome MUST remain externally visible so that the stage-8b deterministic verifier continues to detect it.
- **FR-005**: The specific failure class reported in issue #117 (agent-crash signature with no terminal result record) MUST be root-caused and guarded against so that equivalent stage 8 runs no longer exhibit it.
- **FR-006**: After the fix, a normal (non-crashing) stage 8 watchdog run MUST pass the existing stage-8b deterministic verification, and the pipeline-defect issue for the issue-#117 reasons MUST NOT be auto-filed for healthy runs.
- **FR-007**: The fix MUST NOT weaken, disable, or bypass the stage-8b deterministic verifier or the watchdog's honest-reporting steps; the verifier MUST still fail any future masked-crash run.
- **FR-009**: The fix's scope MUST be a targeted root-cause fix for the exact issue-#117 crash signature PLUS a general guarantee that no masked diagnose-agent crash — of any class — ever presents as a passed inspection; exhaustive per-crash-class handling is explicitly deferred, but the general "no masked crash ever passes" honesty guarantee applies to all crash classes.
- **FR-010**: When the diagnose agent fails to produce a genuine terminal result, the watchdog MUST retry the diagnosis only for recognized transient/infrastructure crash signatures (bounded), and MUST record the honest failure immediately with no retry for all other failure classes; a retried diagnosis that still fails MUST end in an honest surfaced failure, never a masked pass.
- **FR-008**: The watchdog's behavior on healthy runs (reaching and posting a genuine verdict to the lifecycle issue) MUST be preserved; this fix changes only the crashed/failed path so that failures are honest and the observed crash stops recurring.

### Key Entities *(include if feature involves data)*

- **Watchdog run**: A completed execution of the stage 8 watchdog against an inspected pipeline run; carries a conclusion, timing, per-step outcomes, and a diagnose execution-output record.
- **Diagnose outcome**: The terminal result the diagnose agent produces — genuine (a real inspection verdict: passed inspection, a finding, or an honest could-not-inspect) versus crashed/empty/error (no genuine verdict).
- **Lifecycle issue verdict**: The note the watchdog posts to the inspected run's lifecycle issue; must reflect the true diagnose outcome.
- **Stage-8b verification result**: The deterministic verifier's pass/fail judgment on whether the watchdog run actually did its job, and the `pipeline-defect` issue it files on failure.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of watchdog runs end in either a genuine recorded verdict or a surfaced failure; 0% present as a healthy, passed diagnosis over a crashed or empty/error diagnose result.
- **SC-002**: 0 "passed inspection" verdicts are posted to a lifecycle issue over a diagnose outcome that had no successful terminal result record.
- **SC-003**: The agent-crash signature and no-terminal-result condition reported in issue #117 do not recur across a representative sample of stage 8 runs after the fix.
- **SC-004**: Healthy stage 8 watchdog runs pass stage-8b deterministic verification 100% of the time after the fix, and the issue-#117 `pipeline-defect` is not auto-filed for them.
- **SC-005**: When the diagnose agent does fail, a maintainer can determine from the lifecycle issue alone — without opening raw run logs — that the run was not inspected.

## Assumptions

- The stage-8b deterministic verifier and its checks (as implemented for `specs/015-pipeline-watchdog/` and `specs/020-fix-watchdog/`) are the source of truth for "did the watchdog do its job" and are to be preserved, not replaced, by this feature.
- The four conditions reported in issue #117 (diagnose "failed" reporter fired, unhandled-failure safety net fired, no successful terminal result record, agent-crash signature in the diagnose log) accurately describe the incident to be fixed.
- The watchdog's honest-reporting steps ("diagnose failed," "could not inspect," unhandled-failure safety net) are intended mechanisms for surfacing failure and should continue to fire when a genuine failure occurs.
- "Genuine verdict" for the diagnose agent means a successful terminal result record that is not empty, not an error, and not an error subtype.
- The fix targets the diagnose/crash path of the stage 8 watchdog; upstream stage behavior and unrelated pipeline stages are out of scope.
- The lifecycle issue is the maintainer's primary surface for a run's verdict; the run/step summary is a secondary surface where no lifecycle issue applies.
