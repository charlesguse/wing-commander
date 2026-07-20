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

### User Story 2 - Triage a finding to the right rung, without duplicating (Priority: P2)

As a maintainer, I want the watchdog to route each finding to the lightest
sufficient response — a PR when a fix is bigger than a one-liner, a new/reopened
issue when the problem is large or has no home — and to never file the same
finding twice, so that my backlog reflects real, distinct problems and recurrences
are visible as recurrences rather than as noise.

**Why this priority**: Once findings exist (US1), routing and deduplication are
what make them actionable rather than overwhelming. This layer files PRs and
issues but does not autonomously mutate the repository's own source on its own
judgement, so it can ship before the highest-trust rung.

**Independent Test**: Feed the watchdog a finding of "medium" size that is tied to
an existing open pipeline issue and confirm it opens a PR referencing that issue.
Then feed it the *same* finding again and confirm it comments on the existing item
rather than opening a second one; feed it a matching **closed** issue and confirm
it reopens that issue with the fresh evidence.

**Acceptance Scenarios**:

1. **Given** a finding bigger than a one-liner that is tied to an existing pipeline issue, **When** the watchdog triages it, **Then** it opens a PR with the fix and references that issue (rung 2).
2. **Given** a finding that is large, or that has no existing issue to attach to, **When** the watchdog triages it, **Then** it opens a new issue (or a spec proposal) carrying the evidence (rung 3).
3. **Given** a finding whose fingerprint matches an already-open issue, **When** the watchdog triages it, **Then** it adds the new evidence as a comment on that issue and files nothing new.
4. **Given** a finding whose fingerprint matches a **closed** issue, **When** the watchdog triages it, **Then** it reopens that issue and attaches the fresh evidence, because a recurrence is signal.
5. **Given** a finding whose fingerprint matches nothing open or closed, **When** the watchdog triages it, **Then** it creates exactly one new item.

---

### User Story 3 - Fix a truly minor problem on sight (Priority: P3)

As a maintainer, I want the watchdog to fix genuinely trivial, mechanical problems
autonomously — the kind not worth a human's attention — within tight guardrails I
control, so that the pipeline self-heals its smallest defects without paging me,
while I retain the ability to inspect, veto, or pause it.

**Why this priority**: Autonomous writes are the highest-trust, highest-risk rung.
They deliver the "fix it on sight" promise but must be earned on top of reliable
detection and triage, and are the most likely to be deferred, narrowed, or gated
behind an allowlist. Sequencing it last keeps the earlier value shippable
independently.

**Independent Test**: Configure the minor-fix allowlist to permit a specific class
of change (e.g. adding a named read-only tool to an allowlist). Feed the watchdog a
finding of that exact class and confirm it produces the fix through the least-
ceremony path allowed, records what it did on the lifecycle issue, and stays within
the configured path and scope restrictions. Feed it a finding just outside the
"minor" boundary and confirm it declines to auto-fix and falls back to rung 2.

**Acceptance Scenarios**:

1. **Given** a finding that meets the configured "minor" bar and falls within the allowed paths, **When** the watchdog triages it, **Then** it applies the fix through the lightest permitted path and records the action on the lifecycle issue.
2. **Given** a finding that is mechanical but falls **outside** the "minor" bar or the allowed paths, **When** the watchdog triages it, **Then** it does **not** auto-fix and instead falls back to rung 2 (open a PR).
3. **Given** a maintainer has paused/vetoed the watchdog's autonomous fixes, **When** any finding is triaged, **Then** the watchdog performs no autonomous write and instead reports the finding for human action.
4. **Given** the watchdog has already dispatched itself up to its self-dispatch cap, **When** another watchdog action would trigger a further run, **Then** it stops instead of looping.

---

### User Story 4 - Hold itself to the same ladder (Priority: P2)

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
- **FR-004**: The watchdog MUST NOT produce a finding when a run exhibits no detectable problem; it MUST instead record that the run passed inspection.
- **FR-005**: When a run's evidence is missing, expired, or unreadable, the watchdog MUST record that it could not inspect the run and MUST NOT fabricate a finding.
- **FR-006**: The set of detection sources in scope for v1 is **all** of the following: step summaries, workflow annotations, `claude-execution-output-*` artifacts (turn/tool-denial patterns), `spec-meta.json` state vs. expected stage, and branch-vs-origin drift. The watchdog MUST be able to draw findings from any of these sources; broad coverage is accepted with the understanding that it carries a larger v1 surface and more false-positive tuning.

#### Triage ladder

- **FR-007**: For each finding, the watchdog MUST select the **lightest sufficient** response on the triage ladder and MUST NOT escalate beyond what the finding warrants.
- **FR-008**: The watchdog MUST support rung 2 — opening a PR carrying the fix and referencing the existing pipeline issue the finding is tied to.
- **FR-009**: The watchdog MUST support rung 3 — opening a new issue (or a spec proposal) carrying the evidence, used when a finding is large or has no existing issue to attach to.
- **FR-010**: When a finding sits ambiguously between two rungs, the watchdog MUST resolve toward the higher rung (more human involvement).
- **FR-011**: The boundary between rung 1 (autonomous auto-fix) and rung 2 (open a PR) MUST be defined by a crisp, testable rule, because rung 1 writes to the repository autonomously. A fix qualifies as rung-1 "minor" **only when it satisfies all three** of the following conditions: (a) the change is confined to an allowlisted change-class, (b) it touches only allowlisted paths, and (c) its diff is under a small, configurable line cap. A fix that fails **any** of these conditions is not rung-1 and MUST fall back to rung 2. The qualifying change-classes are enumerated up front in the guardrail configuration (see FR-017); the v1 seed set covers the motivating incident's classes (e.g. an allowlist grant of a read-only tool, a path/typo correction, a syntax fix).

#### Deduplication & recurrence

- **FR-012**: Before filing anything, the watchdog MUST check **both open and closed** issues for a matching finding.
- **FR-013**: When a finding matches an already-open issue, the watchdog MUST add the new evidence as a comment and MUST NOT open a duplicate.
- **FR-014**: When a finding matches a **closed** issue, the watchdog MUST reopen that issue and attach the fresh evidence.
- **FR-015**: The watchdog MUST create a new item only when a finding matches nothing open or closed.
- **FR-016**: The watchdog MUST assign each finding a stable fingerprint such that the same defect recurring across many runs maps to one issue (driving the dedup and reopen behavior), while genuinely distinct defects map to distinct fingerprints.

#### Autonomous-fix guardrails (rung 1)

- **FR-017**: Autonomous rung-1 fixes MUST be constrained by a configurable allowlist of change-classes and path restrictions; a fix outside those constraints MUST fall back to rung 2.
- **FR-018**: The watchdog MUST enforce a hard cap on self-dispatch so that its own actions cannot trigger an unbounded chain of watchdog runs (loop prevention).
- **FR-019**: A maintainer MUST be able to veto or pause the watchdog's autonomous fixes; while paused, the watchdog MUST fall back to reporting findings for human action and perform no autonomous write.
- **FR-020**: The watchdog MUST record every autonomous action it takes on the relevant lifecycle issue, so no autonomous change is silent.

#### Self-inspection

- **FR-021**: The watchdog MUST be able to inspect its **own** prior runs and MUST apply the same detection, triage, dedup, and guardrail rules to them, with no special-case path that exempts or softens the checks for itself.

#### Reporting, security & coexistence

- **FR-022**: The watchdog MUST post its findings and actions to the lifecycle issue associated with the inspected run, keeping the run's history legible from that issue.
- **FR-023**: The watchdog MUST treat all inspected content (transcripts, artifacts, summaries, issue/comment bodies) as untrusted data and never as instructions to itself.
- **FR-024**: The watchdog MUST complement, not duplicate, existing stalled-run and cleanup automation; when such automation has already reported or handled a condition, the watchdog MUST NOT double-report it.
- **FR-025**: The watchdog is invoked in v1 by two triggers: `workflow_run` on each pipeline stage's completion, plus on-demand manual dispatch (a maintainer-initiated re-run lever). A scheduled sweep for catch-up on missed runs is explicitly deferred beyond v1.

### Key Entities *(include if feature involves data)*

- **Run under inspection**: A completed pipeline run (any stage, including the watchdog's own), identified by its run reference and associated with a lifecycle issue and, where applicable, a spec directory/stage.
- **Finding**: A detected problem — its class, a human-readable description, the cited evidence, an assessed severity/rung, and a fingerprint.
- **Fingerprint**: A stable identity for a finding that maps recurrences of the same defect to one issue and keeps distinct defects distinct.
- **Triage decision**: The chosen rung (report-only / rung 1 auto-fix / rung 2 PR / rung 3 issue) and the dedup outcome (new / comment-on-open / reopen-closed).
- **Guardrail configuration**: The allowlist of auto-fixable change-classes, permitted paths, the self-dispatch cap, and the pause/veto switch.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For the two v1 problem classes, the watchdog detects and reports the problem on 100% of runs that exhibit it in test scenarios, with a finding a maintainer can confirm without opening raw artifacts.
- **SC-002**: The watchdog never files a duplicate: given the same finding twice, exactly one open item exists afterward, and a recurrence against a closed item reopens rather than re-creates it, in 100% of dedup test scenarios.
- **SC-003**: For the motivating incident class, the watchdog produces the same remediation a human produced manually (an allowlist grant and a commit-then-push ordering fix) as a proposed PR, without human diagnosis.
- **SC-004**: No autonomous write occurs outside the configured allowlist and path restrictions in any test scenario, and every autonomous action the watchdog takes is recorded on a lifecycle issue.
- **SC-005**: The watchdog cannot loop: across any test scenario, the number of watchdog runs it triggers on itself never exceeds the configured self-dispatch cap.
- **SC-006**: When existing stalled/cleanup automation has already handled a condition, the watchdog adds zero duplicate reports for that condition.
- **SC-007**: Median time from a run finishing to its findings appearing on the lifecycle issue is under 10 minutes, replacing the manual post-mortem for that run.

## Assumptions

- **Self-inspection is not exempt**: The watchdog is treated as an ordinary pipeline stage; there is no default configuration that turns off its own inspection.
- **Tie-break toward humans**: When rung or severity is ambiguous, the watchdog prefers the option with more human involvement and less autonomous write.
- **v1 write-autonomy posture**: Unless clarified otherwise, v1 emphasizes reliable detection + reporting (US1) and rungs 2–3 (US2), with rung-1 autonomous fixes (US3) gated behind a tight, configurable allowlist rather than broad write access from day one. This mirrors the requester's stated "scope / non-goals."
- **Humans still own merges**: Consistent with the constitution, the watchdog proposes and triages; humans review and merge anything non-trivial, and the watchdog never merges to `main`.
- **Fingerprint default**: Absent a specified scheme, a finding's fingerprint is derived from its problem class plus the stable, normalized specifics of the offending evidence (e.g. the tool name for a denial pattern), chosen so cosmetic run-to-run differences do not change it.
- **Least-privilege & untrusted content**: The watchdog runs with the least-privilege tool allowlist it needs and follows the constitution's rule that inspected content is never instructions.
- **Existing automation to coexist with**: The watchdog is designed alongside the `implement.yml` stalled job and the cleanup automation (issue #73), and complements the static-analysis lint-workflows gap (#41) rather than replacing runtime post-run analysis.
