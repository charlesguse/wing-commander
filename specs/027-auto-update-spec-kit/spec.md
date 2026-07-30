# Feature Specification: Auto-Update Spec Kit

**Feature Branch**: `027-auto-update-spec-kit`

**Created**: 2026-07-29

**Input**: User description: "Spec Kit is currently behind the latest version. It is a manual process today to update Spec Kit. I want Spec Kit to be auto-updated as new versions come out. Ideally there will be some sort of smoke test to verify it generally works. If it is determined to not work, I want to either prevent the update or roll the update back to the last known working version automatically. Regardless of whether it works, please generate an issue and a PR but do it all automatically unless there are questions to prompt. Add information to the issue as it makes sense, similar to the spec-request workflow. I want the issue to close itself out as the upgrade succeeds and open and flag the issue if the upgrade fails and rolls back. If Spec Kit provides any options on upgrade functionality, try to determine if there is a clearly better upgrade path, otherwise present the questions to the issue. Note the thought process and decision made. Include sources if there are any. Please research into whether or not there is already a known automated update approach that should be considered. Please research into whether Spec Kit has had version issues in the past that might help decide on how quickly to adopt a new version."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A newly released Spec Kit version is adopted automatically when it passes verification (Priority: P1)

A maintainer of this repository wants the pinned Spec Kit version to keep up with upstream releases without anyone remembering to do it by hand. When a new eligible Spec Kit version is published upstream, the pipeline notices it, prepares the upgrade, verifies the pipeline still works with it, and — when verification passes — opens a pull request that bumps the pinned version and a lifecycle issue that tracks the attempt. The maintainer only has to review and merge the PR.

**Why this priority**: This is the core motivating request — turning a manual, easy-to-forget chore into an automated one. Everything else (rollback, questions, issue closing) exists to make this automatic path safe and legible. On its own it delivers the primary value: staying current without manual toil.

**Independent Test**: Simulate a new eligible upstream release, let the process run, and confirm it produces (a) a lifecycle issue describing the detected version and the upgrade, and (b) a pull request that bumps the pinned Spec Kit version, only after the verification step has passed.

**Acceptance Scenarios**:

1. **Given** the pinned Spec Kit version is behind an eligible newer upstream release, **When** the auto-update process runs, **Then** it detects the new version, prepares the upgrade, and runs the verification (smoke test) step.
2. **Given** the verification step passes for the prepared upgrade, **When** the process completes, **Then** it opens a pull request that bumps the pinned version and a lifecycle issue that records the attempt, without any human having initiated the run.
3. **Given** the pinned version already matches the latest eligible upstream version, **When** the process runs, **Then** it takes no action beyond (optionally) recording that no update was needed, and opens no PR.

---

### User Story 2 - A broken upgrade is blocked or rolled back automatically and flagged for a human (Priority: P1)

When a candidate Spec Kit version does not work with this pipeline, the maintainer must never end up with a silently broken pinned version. The process detects the failure during verification, refrains from adopting the broken version (or reverts to the last known working version if it had already been applied), and raises a clearly flagged lifecycle issue explaining what failed so a human can decide what to do.

**Why this priority**: Safety is equal in weight to the automation itself. An auto-updater that can quietly break the pipeline is worse than no auto-updater. This story is what makes Story 1 safe to leave unattended.

**Independent Test**: Simulate an upstream release that fails the verification step, let the process run, and confirm the pinned version stays at (or returns to) the last known working version and a flagged lifecycle issue is raised describing the failure.

**Acceptance Scenarios**:

1. **Given** a candidate version fails the verification step before being adopted, **When** the process completes, **Then** the pinned version is left unchanged (the broken version is not adopted) and a flagged issue is raised explaining the failure.
2. **Given** a candidate version was applied and then found not to work, **When** the process completes, **Then** the pinned version is automatically returned to the last known working version and a flagged issue is raised.
3. **Given** a failure and rollback occurred, **When** the maintainer reads the resulting issue, **Then** it clearly conveys which version failed, which version is now pinned, and what the verification detected — without the maintainer needing to inspect logs to learn that an upgrade was attempted and reverted.

---

### User Story 3 - The lifecycle issue self-manages its state as the upgrade succeeds or fails (Priority: P2)

The maintainer wants the lifecycle issue to behave like the rest of this GitHub-native pipeline: the issue narrates the attempt as it progresses, closes itself when the upgrade succeeds, and stays open and flagged when the upgrade fails and is rolled back. The maintainer should be able to understand the outcome from the issue alone.

**Why this priority**: This is the legibility layer requested ("close itself out as the upgrade succeeds; open and flag the issue if the upgrade fails and rolls back"). It is high value for a hands-off experience but secondary to the update actually happening safely (Stories 1 and 2).

**Independent Test**: Run one successful upgrade and one failing upgrade and confirm the successful run's issue ends closed while the failing run's issue ends open and flagged, each with a summary of what happened.

**Acceptance Scenarios**:

1. **Given** an upgrade attempt succeeds and its version-bump PR is merged, **When** the outcome is recorded, **Then** the lifecycle issue is closed as completed with a summary of the adopted version.
2. **Given** an upgrade attempt fails and rolls back, **When** the outcome is recorded, **Then** the lifecycle issue remains open, carries a visible failure flag/label, and summarizes the failure and the version now in effect.
3. **Given** the process adds information as it makes sense (mirroring the spec-request workflow style), **When** the maintainer reads the issue, **Then** they see the detected version, the decision taken, and the outcome as ordinary issue content.

---

### User Story 4 - Upgrade-path options are decided automatically when clear, or surfaced as questions when not (Priority: P2)

When upstream Spec Kit offers choices around how to upgrade (for example, different upgrade commands, flags, or migration paths), the process should pick a clearly better path on its own and record why. When there is no clearly better path, it should not guess silently — it should present the options as questions on the lifecycle issue, along with its reasoning, decision, and any sources it relied on, so a human can direct the choice.

**Why this priority**: This preserves human control at genuine decision points without adding friction to the common case, and it captures the requested "note the thought process and decision made / include sources" behavior. It is secondary because most upgrades will have a single obvious path and be fully handled by Stories 1–3.

**Independent Test**: Present the process with an upgrade that has one clearly superior path and confirm it proceeds while recording its reasoning; present one with genuinely ambiguous options and confirm it posts the options as questions to the issue instead of choosing silently.

**Acceptance Scenarios**:

1. **Given** upstream offers multiple upgrade paths but one is clearly better, **When** the process runs, **Then** it takes that path and records its reasoning, decision, and any sources on the lifecycle issue.
2. **Given** upstream offers upgrade options with no clearly better choice, **When** the process runs, **Then** it posts the options as questions to the lifecycle issue (with its reasoning and sources) and does not adopt a version until the question is resolved.
3. **Given** the process consulted external references to make a decision, **When** it records the decision, **Then** it includes the sources it relied on.

---

### Edge Cases

- What happens when several new upstream versions are released between runs? The process targets the latest eligible version rather than stepping through every intermediate release, verifies against that target directly, and records which version it chose and why.
- What happens when the verification step itself is flaky (passes on retry)? Verification failure is treated conservatively — the version is not adopted and the issue is flagged; a human can re-run rather than the process silently retrying into a false pass.
- What happens when a previous auto-update issue is still open and unresolved (e.g. awaiting a question answer or a human decision on a prior failure)? The process does not open a duplicate competing attempt; it defers or annotates the existing open issue rather than stacking conflicting version bumps.
- What happens when the upgrade would require changes beyond bumping a pinned version (e.g. migrating `.specify/` scripts, templates, or skills)? The process surfaces that the upgrade is not a clean version bump and routes it to human attention rather than applying a partial or best-effort migration silently.
- What happens when the new version is a major (potentially breaking) release versus a minor or patch release? See FR-014 and the version-scope clarification.
- What happens when upstream version discovery is unavailable (network/source failure)? The process fails safe: it makes no change to the pinned version and does not raise a false "up to date" or false "failed upgrade" signal.
- What happens when the auto-update process runs while a normal spec is mid-flight through the pipeline? The version bump arrives as an ordinary reviewable PR and does not alter any in-flight spec's pinned tooling until merged.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST automatically detect when the repository's pinned Spec Kit version is behind an eligible newer upstream Spec Kit release, without a human initiating the check.
- **FR-002**: The system MUST run automatically on a recurring basis so that new eligible releases are picked up without manual triggering. It MUST also be possible to trigger it on demand. [NEEDS CLARIFICATION: desired check cadence (e.g. daily / weekly) and any stabilization delay before a freshly published version is considered eligible — the request asks to "decide how quickly to adopt a new version" but does not fix the cadence.]
- **FR-003**: When an eligible newer version is detected, the system MUST prepare the upgrade and run a verification ("smoke test") step that checks the pipeline generally still works with the new version before the version is adopted.
- **FR-004**: The verification step MUST exercise the Spec-Kit-dependent behavior the pipeline relies on (at minimum, that the `.specify/` scripts and spec-kit-driven stages still operate) so that a version that breaks the pipeline is caught. [NEEDS CLARIFICATION: exact scope of "generally works" — is a lightweight check of the `.specify/` scripts sufficient, or must the smoke test run a representative end-to-end pipeline stage (e.g. a spec generation) to declare success?]
- **FR-005**: When verification passes, the system MUST open a pull request that bumps the pinned Spec Kit version to the verified version.
- **FR-006**: When verification fails, the system MUST NOT adopt the broken version: if the version had not yet been applied it MUST be left unadopted, and if it had been applied it MUST be automatically rolled back to the last known working version.
- **FR-007**: The system MUST record and be able to identify the "last known working version" so that rollback returns to a version that previously passed verification.
- **FR-008**: For every attempt (success or failure), the system MUST open/maintain a lifecycle issue that tracks the attempt, mirroring the information style of the existing spec-request workflow (detected version, decision, outcome).
- **FR-009**: On a successful upgrade, the lifecycle issue MUST close itself with a summary of the adopted version.
- **FR-010**: On a failed upgrade that is blocked or rolled back, the lifecycle issue MUST remain open and carry a visible failure flag (label) and a summary of what failed and which version is now in effect.
- **FR-011**: The system MUST perform its work automatically without prompting a human, EXCEPT where a genuine decision is required (see FR-012), in which case it pauses for input rather than guessing.
- **FR-012**: When upstream offers upgrade-path options with no clearly better choice, the system MUST post the options as questions to the lifecycle issue — including its reasoning and any sources — and MUST NOT adopt a version until the question is resolved. When one path is clearly better, it MUST proceed and record why.
- **FR-013**: The system MUST record its decision-making — the thought process and the decision made — on the lifecycle issue, and MUST include any sources it relied on when such sources exist.
- **FR-014**: The system MUST treat potentially breaking (major-version) upgrades differently from routine (minor/patch) upgrades, so that a breaking change is not adopted with the same low-touch automation as a safe one. [NEEDS CLARIFICATION: which version jumps may auto-adopt on a passing smoke test (e.g. patch and minor) versus which require explicit human review regardless of the smoke test (e.g. major); the request asks the research to inform "how quickly to adopt a new version."]
- **FR-015**: The system MUST NOT open duplicate or conflicting upgrade attempts while a prior auto-update issue for an unadopted version is still open/unresolved.
- **FR-016**: The system MUST fail safe when upstream version discovery is unavailable — making no change to the pinned version and raising neither a false "up to date" nor a false "upgrade failed" outcome.
- **FR-017**: The version-bump change MUST arrive as an ordinary reviewable pull request that a human merges; the system MUST NOT merge the version change itself, consistent with the pipeline's human-merges-to-main rule.
- **FR-018**: When an upgrade requires more than a pinned-version bump (e.g. migrating `.specify/` scripts, templates, or skills), the system MUST surface that the upgrade is not a clean bump and route it to human attention rather than applying a partial migration silently.

### Key Entities *(include if feature involves data)*

- **Pinned Spec Kit version**: The Spec Kit version the repository currently uses (recorded today in `.specify/init-options.json` as `speckit_version`, currently `0.12.4`, and referenced in the constitution). The value the auto-update process reads and proposes to change.
- **Upstream release**: A Spec Kit version published upstream, with a version number and release type (major/minor/patch). The candidate the process evaluates for eligibility and adoption.
- **Last known working version**: The most recent Spec Kit version that passed verification in this repository; the rollback target when a candidate fails.
- **Verification (smoke test) result**: The pass/fail outcome of checking that the pipeline works with a candidate version, together with what was checked and what (if anything) failed.
- **Auto-update lifecycle issue**: The GitHub issue that tracks a single upgrade attempt — its detected version, reasoning/decision, questions (if any), and final outcome (closed on success, open+flagged on failure).
- **Upgrade decision record**: The reasoning, chosen upgrade path, and sources the process recorded for an attempt.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A maintainer no longer needs to manually check for or apply Spec Kit updates; the routine path from "a new eligible version exists" to "a reviewable version-bump PR" happens with zero human actions before review.
- **SC-002**: 100% of upgrade attempts result in a tracking issue whose final state reflects the outcome — closed on success, open and flagged on failure/rollback.
- **SC-003**: No auto-update attempt ever leaves the repository pinned to a version that failed verification; a failed attempt always ends on a version that previously passed verification.
- **SC-004**: A maintainer can determine the outcome of any upgrade attempt — which version was tried, whether it was adopted or rolled back, and why — from the lifecycle issue alone, without reading run logs.
- **SC-005**: When an upgrade path is genuinely ambiguous, the process asks rather than guesses: 0% of ambiguous-path upgrades are adopted without either a clearly recorded rationale or a human answer.
- **SC-006**: The version change is always delivered as a human-reviewed pull request; the process never merges a Spec Kit version change on its own.
- **SC-007**: When no eligible newer version exists, the process makes no change and opens no PR (no false-positive upgrade churn).

## Assumptions

- The pinned Spec Kit version lives in this repository's own checkout (today `.specify/init-options.json` `speckit_version`, echoed in the constitution's Operational Constraints), consistent with the portability principle that the consuming repository owns its artifacts. The auto-update process reads and proposes changes to that repository-owned value.
- "Eligible" upstream releases are stable published releases; pre-releases/release candidates are out of scope for automatic adoption unless a future clarification includes them.
- The verification "smoke test" runs against this repository's pipeline, not against a hypothetical adopter's; each adopting repository would run its own equivalent check. This feature concerns Wing Commander's own instrument (its consuming configuration), and the mechanism is intended to be portable rather than hardcoded to this repository.
- "Rolling back to the last known working version" means reverting the pinned-version value (and any change applied alongside it in the same attempt), not undoing unrelated repository history.
- The lifecycle issue and version-bump PR are ordinary GitHub artifacts, interacted with the same GitHub-native way as the rest of the pipeline; no external dashboard or CLI is introduced.
- Any research the process performs to choose an upgrade path or judge how quickly to adopt a version is summarized on the lifecycle issue with sources; the act of researching does not, by itself, change any pinned version.
- "The upgrade succeeds" (for the purpose of closing the lifecycle issue, FR-009) is taken to mean the version-bump PR has merged and the new version is actually in effect, since the pipeline's rule is that a human merges every change to `main`. If instead success should be declared the moment verification passes and the PR is opened (leaving the issue to close before merge), that is a refinement rather than a change of intent.
- When multiple newer versions exist at once, the process targets and verifies the latest eligible version directly rather than verifying each intermediate release.
- Existing pipeline security rules apply: the process runs with least privilege, treats issue/comment content as data, and never self-approves or self-merges to `main`.
