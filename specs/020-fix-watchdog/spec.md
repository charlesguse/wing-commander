# Feature Specification: Fix the Watchdog — Restore Reliable Run Inspection

**Feature Branch**: `020-fix-watchdog`

**Created**: 2026-07-24

**Status**: Draft

**Input**: User description (GitHub issue #96, "[bug] Fix the watchdog"): "The watchdog action isn't working" — reported against a specific pipeline workflow run.

## Overview

The pipeline watchdog (originally specified in `specs/015-pipeline-watchdog/`) is
the pipeline's automated first responder: after any pipeline stage finishes, the
watchdog inspects that run's evidence, reports whether the run passed inspection,
and — when it finds a problem — triages it along a ladder from an on-sight fix to
opening an issue. This feature is a **bug fix**: a maintainer reports that the
watchdog "isn't working." The desired end state is that the watchdog reliably does
the job it was already specified to do, and that whatever caused it to stop working
is corrected and guarded against recurrence.

This spec captures the *observable behavior* the fix must restore. It does not
re-specify the watchdog's design; where behavior is already defined by
`specs/015-pipeline-watchdog/`, this feature's requirement is that the behavior
actually occurs in practice.

## User Scenarios & Testing *(mandatory)*

Today a maintainer expects that, after a pipeline stage completes, the watchdog
follows up: either the lifecycle issue gets a "run passed inspection" note, or it
gets a finding with evidence, or (when evidence is unavailable) a "could not
inspect" note. The report is that this follow-up is not happening — the watchdog
"isn't working" — so a run that finished leaves the maintainer without the
watchdog's verdict, and the maintainer is back to reading raw run artifacts
themselves, which is exactly the manual toil the watchdog exists to remove.

### User Story 1 - The watchdog reaches a verdict for every inspected run (Priority: P1)

As a maintainer, when a pipeline stage's run completes and the watchdog is
triggered on it, I want the watchdog to run to completion and reach exactly one of
its defined verdicts — "passed inspection," "one or more findings," or "could not
inspect" — instead of failing partway or ending with no verdict at all, so that I
can trust that a finished run has actually been looked at.

**Why this priority**: This is the irreducible core of the bug. A watchdog that
does not reliably reach a verdict provides no value regardless of how good its
detection or triage logic is; every other capability of the watchdog builds on it
actually completing. Restoring this restores the feature.

**Independent Test**: Trigger the watchdog against a completed run in each of the
relevant contexts and confirm the watchdog run itself finishes without an
unexpected error and produces exactly one verdict, recorded where the maintainer
can see it.

**Acceptance Scenarios**:

1. **Given** a pipeline stage run has just completed, **When** the watchdog is triggered on it, **Then** the watchdog run finishes and records exactly one verdict for that run (passed inspection, findings, or could-not-inspect).
2. **Given** the specific run reported in issue #96 (the run that demonstrated the failure), **When** the watchdog is triggered on it after the fix, **Then** the watchdog reaches a verdict instead of exhibiting the reported failure.
3. **Given** a run that completed cleanly with no detectable problems, **When** the watchdog inspects it, **Then** it records "run passed inspection" and files nothing — and this outcome is actually reached rather than the watchdog erroring first.

---

### User Story 2 - The watchdog's verdict is delivered where the maintainer looks (Priority: P1)

As a maintainer, I want the watchdog's verdict to land in the place I already
watch — the inspected run's lifecycle issue when one can be resolved, or the
watchdog run's own summary when no lifecycle issue exists — so that I learn the
outcome without hunting through workflow logs.

**Why this priority**: A verdict that is computed but never surfaced is
indistinguishable, to the maintainer, from the watchdog not working at all.
Reaching a verdict (US1) and delivering it are together the minimum that makes the
maintainer's report "it isn't working" become "it works."

**Independent Test**: For a run with a resolvable lifecycle issue and for a run
without one, confirm the verdict is posted to the lifecycle issue in the first
case and to the run's own summary in the second.

**Acceptance Scenarios**:

1. **Given** an inspected run whose lifecycle issue can be resolved, **When** the watchdog reaches its verdict, **Then** the verdict is posted as a comment on that lifecycle issue.
2. **Given** an inspected run with no resolvable lifecycle issue, **When** the watchdog reaches its verdict, **Then** the verdict is recorded on the watchdog run's own summary rather than being silently dropped.
3. **Given** the watchdog produced a finding, **When** it reports, **Then** the report includes the cited evidence a maintainer needs to confirm the diagnosis without opening raw artifacts.

---

### User Story 3 - A failing watchdog explains itself rather than failing silently (Priority: P2)

As a maintainer, when the watchdog genuinely cannot complete — for example a
dependency it relies on is unavailable — I want it to surface *why* it could not
complete, so that the next occurrence of "the watchdog isn't working" is
diagnosable in minutes instead of requiring a manual dig through logs.

**Why this priority**: The original report ("isn't working," with only a run link)
shows how hard a silent watchdog failure is to act on. Making failures legible
reduces the cost of any future recurrence and directly serves this bug's spirit,
but it is secondary to actually restoring the working path (US1/US2).

**Independent Test**: Force a condition under which the watchdog cannot reach a
verdict and confirm that the reason is reported to a place the maintainer can see,
rather than the watchdog ending with no explanation.

**Acceptance Scenarios**:

1. **Given** the watchdog cannot reach a verdict because a needed input is missing or unreadable, **When** the watchdog run ends, **Then** it records a human-legible reason for the maintainer rather than ending silently.
2. **Given** the watchdog completed but took a non-default path (e.g. degraded to "could not inspect"), **When** the maintainer reviews the outcome, **Then** the reason for that path is discernible from what the watchdog reported.

---

### Edge Cases

- **The reported run is expired or unavailable**: The run referenced in the bug report may age out before the fix is verified. Verification must be reproducible against a fresh run exhibiting the same failure, not solely against the original run.
- **Partial evidence**: The watchdog can gather some but not all of its evidence sources. The fix must not turn a partial-evidence run into a hard failure when the original design intends it to proceed on what it has.
- **The watchdog fails only in certain contexts**: The failure may be specific to how the watchdog was invoked (e.g. a particular trigger, a particular stage being inspected, or self-inspection). The fix must cover the context in which the failure was reported and must not silently regress the others.
- **Regression protection**: Once fixed, the same failure must be prevented from silently returning, so a maintainer does not have to re-diagnose the same "isn't working" report later.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When the watchdog is triggered on a completed pipeline run, it MUST run to completion and reach exactly one of its defined verdicts: "run passed inspection," "one or more findings," or "could not inspect this run."
- **FR-002**: The watchdog MUST NOT end without a verdict; a watchdog invocation that produces no verdict and no explanation is the exact failure this feature must eliminate.
- **FR-003**: The watchdog MUST deliver its verdict to the inspected run's lifecycle issue when one can be resolved, and to the watchdog run's own summary when no lifecycle issue can be resolved, so the outcome is never silently dropped.
- **FR-004**: A finding the watchdog reports MUST carry the cited evidence needed for a maintainer to confirm the diagnosis without opening raw artifacts (preserving the behavior of `specs/015-pipeline-watchdog/`).
- **FR-005**: The specific failure reported in issue #96 MUST no longer occur when the watchdog is triggered on a run that previously exhibited it. [NEEDS CLARIFICATION: the exact observed symptom is not stated in the issue — only "isn't working" with a run link. Which failure is being reported: the watchdog workflow erroring/failing, the watchdog never being triggered, the watchdog completing but posting nothing, or the watchdog posting an incorrect/empty verdict?]
- **FR-006**: The fix MUST cover the context in which the failure was reported and MUST NOT regress the watchdog's behavior in the other invocation contexts (its normal per-stage trigger, on-demand manual dispatch, and self-inspection). [NEEDS CLARIFICATION: which invocation context exhibited the failure — the automatic per-stage trigger, a manual/on-demand dispatch, or the watchdog inspecting its own run?]
- **FR-007**: When the watchdog genuinely cannot reach a verdict, it MUST record a human-legible reason where the maintainer can see it, rather than ending silently.
- **FR-008**: The corrected behavior MUST be protected against silent regression, so the same failure does not quietly return and force the maintainer to re-diagnose it. [NEEDS CLARIFICATION: is a targeted fix of the one reported failure sufficient for this issue, or is broader hardening of the watchdog's reliability (covering related failure modes beyond the specific symptom) in scope?]
- **FR-009**: The fix MUST preserve every behavior already required of the watchdog by `specs/015-pipeline-watchdog/` (detection sources, dedup/fingerprinting, the triage ladder, guardrails, self-inspection, and untrusted-content handling); it corrects the watchdog, it does not narrow its contract.

### Key Entities *(include if data involved)*

- **Inspected run**: A completed pipeline run that the watchdog is triggered to examine; identified by its run reference and, where resolvable, associated with a lifecycle issue.
- **Verdict**: The watchdog's terminal outcome for an inspected run — "passed inspection," "findings," or "could not inspect" — which this feature requires to be reliably reached and delivered.
- **Reported failure**: The observed way in which the watchdog "isn't working," as described in issue #96; the concrete symptom to be reproduced, corrected, and guarded against.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In verification scenarios covering the reported failure context, the watchdog reaches exactly one verdict for 100% of inspected runs, with zero invocations ending without a verdict.
- **SC-002**: For 100% of inspected runs in verification, the watchdog's verdict is visible to the maintainer in the expected place (lifecycle issue when resolvable, run summary otherwise) without the maintainer reading raw workflow logs.
- **SC-003**: A run reproducing the originally reported failure yields a valid verdict after the fix, in 100% of reproduction attempts.
- **SC-004**: When the watchdog cannot complete, a human-legible reason is present in 100% of such cases; no watchdog invocation ends silently.
- **SC-005**: No behavior previously required of the watchdog is lost: every acceptance scenario from `specs/015-pipeline-watchdog/` that passed before the fix still passes after it.
- **SC-006**: Median time from a stage run finishing to its watchdog verdict appearing where the maintainer looks remains under 10 minutes, restoring the original watchdog service level.

## Assumptions

- **The watchdog was working as designed and regressed**: The report treats an existing, specified capability as broken rather than requesting a new one; this feature restores intended behavior rather than adding scope.
- **`specs/015-pipeline-watchdog/` remains the source of truth for design**: This feature changes the watchdog only as much as fixing the reported failure requires; it does not redefine the watchdog's detection sources, triage ladder, or guardrails.
- **Reproducibility over a single run link**: Because the referenced run may expire, verification is defined against a reproducible run exhibiting the same failure, not solely the original run instance.
- **Least-privilege and untrusted-content rules are unchanged**: The fix operates within the constitution's security posture; inspected content stays untrusted data, and the watchdog's tool allowlist is not broadened to make it "work."
- **Humans still own merges**: Consistent with the constitution, any fix the watchdog itself would propose is reviewed and merged by a human; this feature does not grant the watchdog new autonomous write authority.
