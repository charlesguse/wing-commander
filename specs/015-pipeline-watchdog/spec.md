# Feature Specification: Pipeline Watchdog — Run Validation & Triage

**Feature Branch**: `015-pipeline-watchdog`

**Created**: 2026-07-20

**Status**: Draft

**Input**: User description: "Spec out a watchdog process for the Wing Commander pipeline: a job that inspects completed (or failed) pipeline runs — including its own — detects problems, and then acts on them along a triage ladder from auto-fix to opening a spec. Today diagnosis and remediation of a stalled/misbehaving run is entirely manual (a human reads the claude-execution-output-* artifacts and step summaries); the watchdog automates the first responder."

## User Scenarios & Testing *(mandatory)*

Today, when a pipeline run stalls or misbehaves, a human is the first responder:
they open the failed workflow run, read the `claude-execution-output-*`
transcript and step summaries, work out what went wrong, and then either fix it
by hand or file an issue. The motivating incident — an implement run that burned
turns on non-allowlisted read-only validators and then left no progress on the
branch because push only happened at the end — was diagnosed and fixed entirely
by a person, even though both root causes were minor and mechanical.

The watchdog automates that first-responder role. After a pipeline run finishes
(succeeded or failed), the watchdog inspects the run's evidence, detects known
classes of problems, and takes the **lightest sufficient action** along a triage
ladder: fix a truly minor issue on sight, open a PR for a bigger-but-not-spec
fix, or open/reopen an issue when the problem is large or has no home. It applies
the same discipline to its own runs, and it never files a duplicate.

### User Story 1 - Detect a run's problems and report them (Priority: P1)

As a maintainer, I want a run that stalls or misbehaves to be automatically
inspected and its findings posted where I already look — the lifecycle issue —
so that I learn what went wrong without having to open and read raw transcripts
myself.

**Why this priority**: Detection-and-reporting is the irreducible core of a "first
responder." On its own — with no autonomous writes at all — it already replaces
the manual post-mortem that a human does today and delivers value immediately. It
is also the foundation every higher rung of the ladder builds on: you cannot
triage a finding you have not detected and described.

**Independent Test**: Point the watchdog at a completed run that exhibits a known
problem pattern (e.g. repeated auto-denied tool calls, or a branch with no commits
after an interrupted implement). Confirm it produces a finding that names the
problem, cites the specific evidence (the run, the offending turns/tools), and
posts that finding to the run's lifecycle issue — without modifying any repository
files.

**Acceptance Scenarios**:

1. **Given** a completed run whose transcript shows a validator tool being invoked and auto-denied several times, **When** the watchdog inspects the run, **Then** it produces a finding that identifies the missing-allowlisted-tool problem and quotes the specific denied tool calls as evidence.
2. **Given** an implement run that was interrupted leaving zero commits on its work branch, **When** the watchdog inspects the run, **Then** it produces a finding describing the lost-progress condition and cites the branch-vs-origin state as evidence.
3. **Given** a run that completed cleanly with no detectable problems, **When** the watchdog inspects it, **Then** it records that the run passed inspection and files nothing.
4. **Given** any finding, **When** the watchdog reports it, **Then** the report is posted to the correct lifecycle issue and includes enough evidence for a human to confirm the diagnosis without opening the raw artifacts.

---

### User Story 2 - File or reopen an issue for a finding, without duplicating (Priority: P2)

As a maintainer, I want the watchdog to file a pipeline-defect issue for a new
finding, or comment on / reopen an existing one when the finding recurs, and to
never file the same finding twice, so that my backlog reflects real, distinct
problems and recurrences are visible as recurrences rather than as noise.

**Why this priority**: Once findings exist (US1), filing and deduplication are
what make them actionable rather than overwhelming. This layer never mutates
the repository's own source — it only manages the pipeline-defect issue
tracker — so it can ship as the watchdog's complete remediation surface.

**Independent Test**: Feed the watchdog a finding with no existing pipeline
issue and confirm it opens a new one carrying the evidence. Then feed it the
*same* finding again and confirm it comments on the existing item rather than
opening a second one; feed it a matching **closed** issue and confirm it
reopens that issue with the fresh evidence.

**Acceptance Scenarios**:

1. **Given** a finding whose fingerprint matches nothing open or closed, **When** the watchdog triages it, **Then** it creates exactly one new pipeline-defect issue carrying the evidence.
2. **Given** a finding whose fingerprint matches an already-open issue, **When** the watchdog triages it, **Then** it adds the new evidence as a comment on that issue and files nothing new.
3. **Given** a finding whose fingerprint matches a **closed** issue, **When** the watchdog triages it, **Then** it reopens that issue and attaches the fresh evidence, because a recurrence is signal.

---

### User Story 4 - Hold itself to the same rules (Priority: P2)

As a maintainer, I want the watchdog to inspect its **own** runs with the same
detection, triage, and dedup rules as any other stage, so that a misbehaving
watchdog is caught by the same mechanism and is not silently exempt.

**Why this priority**: The watchdog is a pipeline stage like any other; an
un-inspected watchdog is a blind spot precisely where autonomous writes originate.
Self-inspection is a small addition on top of US1/US2 but is called out separately
because it is an explicit non-negotiable of the request and is independently
testable.

**Independent Test**: Trigger the watchdog against a prior *watchdog* run that
exhibited a problem, and confirm it produces and triages a finding using the same
rules — with no special-case branch that skips or softens the checks for itself —
including the loop-prevention cap so self-inspection cannot run away.

**Acceptance Scenarios**:

1. **Given** a completed watchdog run that exhibits a detectable problem, **When** the watchdog inspects it, **Then** it produces and triages a finding using the same rules applied to any other stage.
2. **Given** the watchdog is inspecting its own runs, **When** it acts on a finding, **Then** the self-dispatch cap and loop-prevention guardrails still apply, so it cannot trigger an unbounded chain of watchdog runs.

---

### Edge Cases

- **No evidence available**: A run's artifacts are missing, expired, or truncated. The watchdog records that it could not inspect the run and files nothing rather than guessing.
- **Ambiguous severity**: A finding sits exactly on the rung-1/rung-2 boundary. The watchdog resolves ties toward the *higher* rung (more human involvement, less autonomous write).
- **Concurrent watchdog runs**: Two watchdog runs inspect overlapping runs at once. Fingerprint-based dedup must prevent both from filing the same finding.
- **Fingerprint collision / drift**: Two genuinely different problems hash to the same fingerprint, or the same problem's evidence shifts slightly between runs. The watchdog must avoid both merging distinct findings and re-filing the same one.
- **A finding about the watchdog's own last fix**: The watchdog's autonomous fix itself introduced a problem. Loop-prevention and the self-dispatch cap must bound the corrective cascade.
- **Overlap with existing stalled/cleanup automation**: The `implement.yml` stalled job or cleanup automation already reported or handled the condition. The watchdog must complement, not double-report.
- **Untrusted transcript content**: A transcript or artifact contains text shaped like instructions to an AI. The watchdog treats all inspected content as data, never as instructions.

## Requirements *(mandatory)*

### Functional Requirements

#### Detection & inspection

- **FR-001**: The watchdog MUST inspect pipeline runs after they finish, for both succeeded and failed outcomes.
- **FR-002**: The watchdog MUST derive findings from the run's own evidence and MUST cite, in every finding, the specific evidence it relied on (the run identifier and the offending turns/tools/branch state), sufficient for a human to confirm the diagnosis without opening raw artifacts.
- **FR-003**: The watchdog MUST detect, at minimum for v1, the two problem classes from the motivating incident: (a) repeated invocation of a non-allowlisted read-only tool that is auto-denied, and (b) an interrupted run that left no progress (no commits) on its work branch.
- **FR-004**: The watchdog MUST NOT produce a finding when a run exhibits no detectable problem; it MUST instead record that the run passed inspection. This false-positive-avoidance duty rests on the collectors that produce signals — the components able to observe the world — and MUST NOT rest solely on the `diagnose` step, which consumes pre-computed signals and cannot determine that one of them is wrong (FR-002 of spec 024).
- **FR-005**: When a run's evidence is missing, expired, or unreadable, the watchdog MUST record that it could not inspect the run and MUST NOT fabricate a finding.
- **FR-006**: The set of detection sources in scope for v1 is **all** of the following: step summaries, workflow annotations, `claude-execution-output-*` artifacts (turn/tool-denial patterns), `spec-meta.json` state vs. expected stage, and branch-vs-origin drift. The watchdog MUST be able to draw findings from any of these sources; broad coverage is accepted with the understanding that it carries a larger v1 surface and more false-positive tuning.

#### Remediation

- **FR-007**: **Removed** — the triage ladder this requirement selected across no longer exists; the watchdog's remediation surface is a single path (FR-014 of spec 024).
- **FR-008**: **Removed** — rung 2 (a PR referencing an existing issue) no longer exists (FR-014 of spec 024).
- **FR-009**: The watchdog MUST support opening a new pipeline-defect issue carrying the evidence, used when a finding matches no existing issue.
- **FR-010**: **Removed** — there is no longer a rung boundary to sit ambiguously between (FR-014 of spec 024).
- **FR-011**: **Removed** — rung 1 (autonomous auto-fix) no longer exists, so there is no rung-1/rung-2 boundary to define (FR-014 of spec 024).

#### Deduplication & recurrence

- **FR-012**: Before filing anything, the watchdog MUST check **both open and closed** issues for a matching finding.
- **FR-013**: When a finding matches an already-open issue, the watchdog MUST add the new evidence as a comment and MUST NOT open a duplicate.
- **FR-014**: When a finding matches a **closed** issue, the watchdog MUST reopen that issue and attach the fresh evidence.
- **FR-015**: The watchdog MUST create a new item only when a finding matches nothing open or closed.
- **FR-016**: The watchdog MUST assign each finding a stable fingerprint such that the same defect recurring across many runs maps to one issue (driving the dedup and reopen behavior), while genuinely distinct defects map to distinct fingerprints.

#### Loop prevention & pause

- **FR-017**: **Removed** — the rung-1 allowlist guardrail this requirement constrained no longer exists; there is no autonomous fix to constrain (FR-014 of spec 024).
- **FR-018**: The watchdog MUST enforce a hard cap on self-dispatch so that its own actions cannot trigger an unbounded chain of watchdog runs (loop prevention).
- **FR-019**: A maintainer MUST be able to veto or pause the watchdog's writes; while paused, the watchdog MUST fall back to reporting findings for human action and perform no write.
- **FR-020**: The watchdog MUST record every write it takes — and every case where a write was suppressed (an invalid-evidence finding, a failed dedup lookup, a paused or capped run) — on the relevant lifecycle issue, so no outcome is silent.

#### Self-inspection

- **FR-021**: The watchdog MUST be able to inspect its **own** prior runs and MUST apply the same detection, triage, dedup, and guardrail rules to them, with no special-case path that exempts or softens the checks for itself.

#### Reporting, security & coexistence

- **FR-022**: The watchdog MUST post its findings and actions to the lifecycle issue associated with the inspected run, keeping the run's history legible from that issue.
- **FR-023**: The watchdog MUST treat all inspected content (transcripts, artifacts, summaries, issue/comment bodies) as untrusted data and never as instructions to itself.
- **FR-024**: The watchdog MUST complement, not duplicate, existing stalled-run and cleanup automation; when such automation has already reported or handled a condition, the watchdog MUST NOT double-report it.
- **FR-025**: The watchdog is invoked in v1 by two triggers: `workflow_run` on each pipeline stage's completion, plus on-demand manual dispatch (a maintainer-initiated re-run lever). A scheduled sweep for catch-up on missed runs is explicitly deferred beyond v1.

#### Precision & determinism hardening (spec 024)

- **FR-026**: A collector MUST emit a signal about a run only when the inspected run both executed (its `conclusion` is not `skipped`/`cancelled`) and owned the artifact whose condition the signal describes. This attribution invariant applies to all five collectors named in FR-006, stated once here rather than per-collector.

### Key Entities *(include if feature involves data)*

- **Run under inspection**: A completed pipeline run (any stage, including the watchdog's own), identified by its run reference and associated with a lifecycle issue and, where applicable, a spec directory/stage.
- **Finding**: A detected problem — its class, a human-readable description, the cited evidence, an assessed severity/rung, and a fingerprint.
- **Fingerprint**: A stable identity for a finding that maps recurrences of the same defect to one issue and keeps distinct defects distinct.
- **Triage decision**: The single dedup-selected branch (create a new pipeline-defect issue / comment on an open match / reopen and comment on a closed match / suppress and report a failed lookup) — selected purely by the dedup outcome, since no autonomous-fix rung remains (FR-014 of spec 024).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For the two v1 problem classes, the watchdog detects and reports the problem on 100% of runs that exhibit it, verified against a labeled corpus of runs known to exhibit each problem class, with a finding a maintainer can confirm without opening raw artifacts.
- **SC-002**: The watchdog never files a duplicate: given the same finding twice, exactly one open item exists afterward, and a recurrence against a closed item reopens rather than re-creates it, in 100% of dedup test scenarios.
- **SC-003**: For the motivating incident class, the watchdog produces the same remediation a human produced manually (an allowlist grant and a commit-then-push ordering fix) as a proposed PR, without human diagnosis.
- **SC-004**: No autonomous write occurs outside the configured allowlist and path restrictions in any test scenario, and every autonomous action the watchdog takes is recorded on a lifecycle issue.
- **SC-005**: The watchdog cannot loop: across any test scenario, the number of watchdog runs it triggers on itself never exceeds the configured self-dispatch cap.
- **SC-006**: When existing stalled/cleanup automation has already handled a condition, the watchdog adds zero duplicate reports for that condition.
- **SC-007**: Median time from a run finishing to its findings appearing on the lifecycle issue is under 10 minutes, replacing the manual post-mortem for that run — measured as `gh run view --json updatedAt` (the inspected run's completion) against the `createdAt` of the watchdog's own report comment on the lifecycle issue.
- **SC-008**: Precision — among the most recent 20 distinct (post-dedup) pipeline-defect issues the watchdog has filed, at least 70% carry a maintainer-applied `disposition:confirmed` label rather than `disposition:false-positive`. Not evaluated until at least 10 distinct findings exist; below that threshold the criterion is reported "not applicable," never as a pass or a divide-by-zero failure.

## Assumptions

- **Self-inspection is not exempt**: The watchdog is treated as an ordinary pipeline stage; there is no default configuration that turns off its own inspection.
- **Tie-break toward humans**: When rung or severity is ambiguous, the watchdog prefers the option with more human involvement and less autonomous write.
- **v1 write-autonomy posture**: Unless clarified otherwise, v1 emphasizes reliable detection + reporting (US1) and rungs 2–3 (US2), with rung-1 autonomous fixes (US3) gated behind a tight, configurable allowlist rather than broad write access from day one. This mirrors the requester's stated "scope / non-goals."
- **Humans still own merges**: Consistent with the constitution, the watchdog proposes and triages; humans review and merge anything non-trivial, and the watchdog never merges to `main`.
- **Fingerprint default**: Absent a specified scheme, a finding's fingerprint is derived from its problem class plus the stable, normalized specifics of the offending evidence (e.g. the tool name for a denial pattern), chosen so cosmetic run-to-run differences do not change it.
- **Least-privilege & untrusted content**: The watchdog runs with the least-privilege tool allowlist it needs and follows the constitution's rule that inspected content is never instructions.
- **Existing automation to coexist with**: The watchdog is designed alongside the `implement.yml` stalled job and the cleanup automation (issue #73), and complements the static-analysis lint-workflows gap (#41) rather than replacing runtime post-run analysis.
