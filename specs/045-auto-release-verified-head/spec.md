# Feature Specification: Auto-Release After Merged Features Pass a Scheduled End-to-End Verification

**Feature Branch**: `045-auto-release-verified-head`

**Created**: 2026-09-12

**Status**: Draft

**Input**: User description (lifecycle issue #296): "Cutting a release is entirely manual today — `release.yml` only runs on `workflow_dispatch` with a hand-typed version. Nothing tells a maintainer 'there's new, verified work sitting on main, go tag it,' so releases lag behind merged features by however long it takes a human to remember to dispatch one. And the only pre-release verification that exists today (`release.yml`'s Gate 1a/1b) is static lint over the workflow files — nothing actually drives the pipeline's published stages against a real adopter-shaped repository before a tag goes out. After feature work has merged to main, automatically cut a release once — but only once — that unreleased head has been proven to work end-to-end against a real test repository, not just linted: a scheduled job checks whether main has any merged changes since the last release tag (nothing new = no-op); if there is new work, it drives a real feature through the published stages against a dedicated, pre-created end-to-end test repository — the same shape as the scratch-repository pattern `specs/034-e2e-verification-tier` and `auto-update-spec-kit.yml` already use: a maintainer-owned repo, named in a repository variable, never created or deleted by the pipeline itself, reset to a clean branch each run so a previous run's leftovers can never satisfy this run's checks; if that end-to-end run succeeds, automatically compute the next version and dispatch the existing `release.yml` (reusing its lint gates, tag creation, and release-notes flow rather than duplicating any of it) to cut a non-breaking (patch or minor) release. A breaking release should keep requiring a human to dispatch it manually with `breaking: true` and migration notes — per `specs/010-reusable-pipeline/contracts/versioning.md` that's meant to be a deliberate act. If the run fails, no release is cut, the current tag is left untouched, and the failure is reported clearly — which check failed, expected vs. observed — so a maintainer can act before the next scheduled attempt. Same report-only posture the watchdog already uses. A kill switch (repository variable) to pause auto-release entirely, same precedent as `WING_COMMANDER_WATCHDOG_PAUSED`. Open questions for spec/clarify: exactly how much of the 8-stage lifecycle the end-to-end run needs to exercise versus how expensive that gets per run; how the schedule's cadence is configured (fixed cron vs. repository variable); how patch-vs-minor is decided automatically. Prior art to reuse rather than re-derive: the scratch-repository resolve/reset/never-create-or-delete pattern from `specs/034-e2e-verification-tier`; `release.yml`'s existing tag/notes logic (`specs/010-reusable-pipeline/contracts/versioning.md`) — dispatch into it, don't duplicate its gates; Constitution Principle IX: whatever decides 'the end-to-end run passed, cut a release' must be deterministic code reading a concrete verdict, never an agent's judgment call."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Verified work on main reaches adopters without anyone remembering to tag (Priority: P1)

Feature work merges to main. On its own schedule, the pipeline notices that main carries commits the most recent release tag does not, drives a real feature through its published stages against a dedicated end-to-end test repository, and — when that run passes — cuts a non-breaking release at the exact head it verified, reusing the existing release automation for the tag, the floating major tag, and the release notes. Nobody typed a version number and nobody remembered anything.

**Why this priority**: This is the feature. Today the gap between "merged" and "released" is bounded only by a maintainer's memory, and adopters tracking the floating major tag sit behind verified work for that whole interval. Delivering just this story — detect, verify, dispatch — removes the manual step the issue was opened about.

**Independent Test**: Merge a trivial change to main, wait for (or dispatch) one scheduled check, and confirm that a new non-breaking release tag exists at that commit, that it was created by the existing release automation rather than by new tag-writing code, and that the end-to-end test repository shows this run's branch carrying the verification evidence.

**Acceptance Scenarios**:

1. **Given** main carries commits the latest release tag does not, **When** the scheduled check runs and the end-to-end verification passes, **Then** exactly one new non-breaking release is cut at the verified head, with the version computed from the latest release tag rather than typed by a human.
2. **Given** a release has just been cut automatically, **When** the next scheduled check runs with no further merges to main, **Then** no second release is cut for the same head.
3. **Given** the automatic path is cutting a release, **When** the tag, the floating major tag, and the release notes are produced, **Then** they are produced by the existing release automation — this feature supplies inputs to it and creates no tag, floating tag, or release of its own.
4. **Given** a release was cut automatically, **When** a maintainer reads the release, **Then** it is indistinguishable in shape from a hand-dispatched one (same notes structure, same Breaking-changes section stating "None").

---

### User Story 2 - A failing end-to-end run blocks the release and says exactly what broke (Priority: P1)

The scheduled run drives the published stages against the test repository and something does not behave as the pipeline requires — a stage does not complete, or completes without the documented output. No tag is created, the current release tag is left exactly where it was, and a report names the failing check with what was expected and what was observed, so a maintainer can fix it before the next scheduled attempt rather than discovering it from an adopter.

**Why this priority**: An auto-release that cuts a tag on unverified work is worse than the manual process it replaces — it converts a maintainer's deliberate act into an unattended one. The blocking half and the reporting half are what make the automatic half safe, so they ship with it.

**Independent Test**: Make the end-to-end run fail in a controlled way (a stage forced to produce no documented output) and confirm that zero tags and zero releases are created, that the latest release tag is byte-identical to what it was before, and that the report alone — without opening run logs — names the failing check and the expected-vs-observed detail.

**Acceptance Scenarios**:

1. **Given** an end-to-end run in which a stage does not complete, **When** the run finishes, **Then** no release is cut, no tag is created or moved, and the failure is reported with the failing check named.
2. **Given** an end-to-end run in which a stage completes but produces no documented output or output in the wrong shape, **When** the run finishes, **Then** the report states what was expected and what was observed.
3. **Given** a maintainer reading only the failure report, **When** they read it, **Then** they can state which head was being verified, which check failed, and whether the cause looks like an infrastructure problem or a real pipeline defect, without opening the workflow run.
4. **Given** a failed attempt, **When** the next scheduled check runs and main is unchanged, **Then** the same unreleased head is verified again rather than being skipped or permanently written off.
5. **Given** repeated failures for the same unreleased head, **When** each scheduled attempt reports, **Then** the maintainer gets one durable, updated report rather than a new one per attempt.

---

### User Story 3 - Nothing new on main costs nothing (Priority: P2)

Most scheduled checks find nothing to do. When main carries no commits beyond the latest release tag, the run ends there: no end-to-end verification, no agent invocation, no writes, no release.

**Why this priority**: The end-to-end run is the expensive part of this feature — real stages, real agent turns, real wall clock. Firing it on every scheduled tick regardless of whether there is anything to release would make the cadence question a budget question. The no-op path is what makes a frequent cadence affordable, but it delivers nothing without US1, so it is P2.

**Independent Test**: With main at exactly the latest release tag, run the scheduled check and confirm it completes having invoked no agent, touched no test repository, and created nothing.

**Acceptance Scenarios**:

1. **Given** main's head is the commit the latest release tag points at, **When** the scheduled check runs, **Then** it ends as a no-op — no end-to-end verification, no agent step, no test-repository branch reset, no release.
2. **Given** a no-op run, **When** a maintainer looks at the run afterwards, **Then** the reason it did nothing ("no new commits since `<tag>`") is legible without opening logs.
3. **Given** no release tag exists at all yet, **When** the scheduled check runs, **Then** the run does not crash and does not guess — it reports that there is no baseline to compare against and cuts nothing.

---

### User Story 4 - Breaking releases stay a deliberate human act (Priority: P2)

A change that breaks a published stage interface still requires a maintainer to dispatch the release by hand, declaring it breaking and supplying migration notes. The automatic path cuts patch and minor releases only and never advances or creates a major.

**Why this priority**: The versioning contract already makes a major tag a deliberate act, because an adopter tracking a floating major tag receives a non-breaking release with zero changes on their side. Automating that decision would move breakage onto adopters without anyone writing migration notes. It is P2 only because it is a constraint on US1 rather than a separate capability.

**Independent Test**: Confirm the automatic path has no way to request a breaking release — the dispatched release is always non-breaking, and no input path exists by which the scheduled run could set it otherwise.

**Acceptance Scenarios**:

1. **Given** any passing end-to-end run, **When** the automatic path dispatches a release, **Then** that release is non-breaking, and the version it computes never starts a new major.
2. **Given** unreleased work that is in fact breaking, **When** the automatic path runs, **Then** it still cuts only a non-breaking release — detecting breakage is out of scope, and the manual, human-declared breaking dispatch remains the only route to a major.
3. **Given** the manual release dispatch, **When** a maintainer uses it with `breaking: true` and migration notes, **Then** it behaves exactly as it does today, unchanged by this feature.

---

### User Story 5 - A maintainer can pause the whole thing (Priority: P3)

A repository variable pauses auto-release entirely. While it is set, no scheduled check starts: nothing is detected, no agent is invoked, no test repository is touched, and no release is cut. Clearing it resumes the normal schedule.

**Why this priority**: Every other unattended scheduled behaviour in this repository has a kill switch, for the case where the thing being automated is itself what a maintainer is debugging. It is P3 because the feature is useful before the switch exists, and the switch is trivially testable on its own.

**Independent Test**: Set the pause variable, run the scheduled check, and confirm no job starts at all; clear it and confirm the next check behaves normally.

**Acceptance Scenarios**:

1. **Given** the pause variable is set, **When** the schedule fires or a maintainer dispatches the check on demand, **Then** no job starts — nothing is detected, no agent runs, and nothing is billed.
2. **Given** the pause variable is cleared, **When** the next scheduled check runs, **Then** it behaves as if the switch had never been set.

---

### Edge Cases

- **No release tag exists yet**: nothing to compare against and no version to increment — the run reports that and cuts nothing (the first release stays a human act).
- **Main advances while the end-to-end run is in flight**: the release is cut only at the head that was actually verified. If main has moved on, no release is cut this attempt and the next scheduled check verifies the new head — a tag must never land on a commit no end-to-end run ever saw.
- **A previous attempt already released this head**: no-op; one head yields at most one automatic release, no matter how many times the schedule fires.
- **Two scheduled checks overlap** (a long verification still running when the next fires): at most one attempt is in flight; the later one does not start a second verification or a second release for the same head.
- **The end-to-end test repository is unconfigured**: verification cannot run, so no release is cut, and the report names it as an infrastructure problem with the variable to set — not as a pipeline defect.
- **The test repository is configured but not reachable** with the pipeline's own credentials: same single outcome — no release, reported as infrastructure, naming the installation to add.
- **A previous run left artifacts on the test repository's branch**: the branch is reset to a clean state before this run scaffolds anything, so nothing a previous run left can satisfy this run's checks.
- **The end-to-end run dies part-way** (error, timeout, cancelled, exhausted turn budget): treated as verification failure — no release — and reported as "did not complete", distinguished from "completed and produced the wrong thing".
- **The dispatched release itself fails** (its own lint gates, or tag creation): no tag is published, and the failure is reported as a release failure rather than silently recorded as a success.
- **The verification passes but the computed version already exists as a tag**: no release is cut and the collision is reported, rather than force-moving or overwriting an immutable tag.
- **Merged work contains only changes that cannot affect adopters** (docs, specs, this repository's own wrapper workflows): still treated as new work and still released — narrowing to "adopter-visible changes only" is out of scope, and a release of an unchanged published surface is harmless under the versioning contract.
- **The pause variable is set mid-run**: the in-flight attempt is not required to abort; the guarantee is that no *new* attempt starts.
- **Failure report noise**: consecutive failures for the same unreleased head update one report rather than filing a fresh one each cadence tick.
- **Verification artifacts**: no artifact of the end-to-end run reaches this repository's `specs/` tree, any pushed branch of this repository, or any pull request against it.

## Requirements *(mandatory)*

### Functional Requirements

#### Detecting unreleased work

- **FR-001**: The system MUST check, on a recurring schedule, whether the default branch carries commits that the most recent release tag does not.
- **FR-002**: The schedule's cadence MUST be adjustable by a maintainer without editing this repository's code. [NEEDS CLARIFICATION: the recurring trigger's interval cannot itself be read from a repository variable — a schedule expression is fixed in the workflow file. So "configurable cadence" must be delivered as either (a) a fixed frequent trigger plus a maintainer-settable minimum interval that makes intervening ticks a no-op, or (b) a fixed interval in the workflow that a maintainer changes by editing one line. Which is intended?]
- **FR-003**: When the default branch carries no commits beyond the latest release tag, the run MUST end as a no-op: no end-to-end verification, no agent invocation, no write to the test repository, and no release.
- **FR-004**: When no release tag exists at all, the run MUST report that there is no baseline and MUST NOT cut a release.
- **FR-005**: The system MUST be triggerable on demand by a maintainer in addition to its schedule, so the behaviour can be exercised without waiting for a tick.
- **FR-006**: A repository variable MUST act as a kill switch that prevents any auto-release job from starting — nothing detected, no agent invoked, nothing written, nothing billed — following the same wrapper-side precedent as the existing watchdog and auto-updater pause switches.

#### Verifying the unreleased head

- **FR-007**: When new work is detected, the system MUST drive a real feature through this repository's published stages against a dedicated end-to-end test repository, rather than relying on static lint of the workflow files as the only pre-release evidence.
- **FR-008**: The end-to-end run MUST exercise the lifecycle stages listed here against the test repository, and each exercised stage's documented output MUST be asserted. [NEEDS CLARIFICATION: how much of the intake→cleanup lifecycle must run for the verdict to count as real verification? Every stage end-to-end is the strongest evidence and the most expensive per attempt; a contract-shaped subset (e.g. intake→plan→tasks, stopping before the implement⟲converge loop) is materially cheaper but leaves the loop unverified. Which coverage is intended?]
- **FR-009**: The end-to-end test repository MUST be a pre-created repository named in a repository variable, owned by a maintainer. The system MUST NOT create or delete any repository, and MUST hold no repository-administration right.
- **FR-010**: The test repository's per-run branch MUST be reset to a clean state before this run scaffolds anything onto it, so no artifact of a previous run can satisfy any assertion of this one.
- **FR-011**: When the test repository is unconfigured, or is configured but unreachable with the pipeline's own credentials, the outcome MUST be the single verification-failure outcome — no release — reported as an infrastructure problem naming what to set or install, and distinguished from a pipeline defect.
- **FR-012**: An exercised stage that does not complete — error, timeout, cancellation, or an exhausted turn budget — MUST produce verification failure, and the report MUST distinguish "did not complete" from "completed and produced the wrong output".
- **FR-013**: No artifact produced by the end-to-end run may land in this repository's `specs/` tree, in any pushed branch of this repository, or in any pull request against it.
- **FR-014**: Every agent-driven step in the end-to-end run MUST declare an explicit model and a bounded turn budget, so one stuck attempt cannot consume the budget indefinitely.

#### Deciding and cutting the release

- **FR-015**: The decision "the end-to-end run passed, therefore cut a release" MUST be made by deterministic code reading a concrete machine-readable verdict. No agent's judgment may gate the release (Constitution Principle IX).
- **FR-016**: A release MUST be cut only when the end-to-end verification passed for the exact head being released. If the default branch has advanced past the verified head by the time the release would be dispatched, no release is cut for that attempt.
- **FR-017**: The next version MUST be computed from the most recent release tag rather than supplied by a human. [NEEDS CLARIFICATION: how is patch vs. minor chosen automatically? Options include: always patch unless an explicit opt-in signal requests minor (e.g. a label on the merged spec PR); derive it from the merged specs' own change classification; or always patch with minor left to a manual dispatch. Which signal is authoritative, and what happens when a range of merged work carries conflicting signals?]
- **FR-018**: The automatic path MUST cut non-breaking releases only. It MUST NOT declare a release breaking, MUST NOT compute a version that starts a new major, and MUST NOT create or advance a major tag other than through the existing release automation's own non-breaking behaviour.
- **FR-019**: Determining that unreleased work is breaking is explicitly out of scope: a breaking release remains a human act, dispatched manually with a declared breaking flag and migration notes.
- **FR-020**: The system MUST reuse the existing release automation for the tag, the floating major tag, the lint gates, and the release notes, by supplying it inputs. It MUST NOT duplicate, re-implement, or bypass any of them.
- **FR-021**: The existing manual release dispatch MUST keep working exactly as it does today; this feature adds no gate, input requirement, or precondition to the human path.
- **FR-022**: One head MUST yield at most one automatic release. A head that has already been released automatically MUST NOT be released again on a later tick.
- **FR-023**: At most one auto-release attempt may be in flight at a time; a tick that fires while an attempt is running MUST NOT start a second verification or a second release.
- **FR-024**: When the computed version already exists as a tag, the system MUST NOT cut a release and MUST report the collision — an already-published tag is immutable and is never overwritten or force-moved.

#### Reporting

- **FR-025**: A verification failure MUST leave the current release tag untouched — no tag created, none moved, no release published.
- **FR-026**: Every failure MUST be reported clearly enough that a maintainer can state, from the report alone and without opening run logs, which head was being verified, which check failed, and what was expected versus what was observed.
- **FR-027**: The posture MUST be report-only, matching the watchdog's: the system reports its verdict and takes no corrective action on the repository beyond the release it is specified to cut.
- **FR-028**: Consecutive failures for the same unreleased head MUST update one durable report rather than filing a new one each cadence tick.
- **FR-029**: A failure of the dispatched release itself (its own lint gates, or tag creation) MUST be reported as a release failure and MUST NOT be recorded as a successful auto-release.
- **FR-030**: Every attempt's outcome — released `<version>`, no new work since `<tag>`, verification failed, or paused — MUST be legible from the run's own summary without opening logs.

### Key Entities

- **Unreleased head**: the commit at the tip of the default branch, and whether it differs from the commit the most recent release tag points at. The subject of every attempt.
- **Latest release tag**: the baseline for both "is there new work" and "what is the next version".
- **End-to-end test repository**: one pre-created, maintainer-owned repository named in a repository variable, holding a per-run branch that is reset clean before each run. Never created or deleted by the pipeline; survives every outcome so a maintainer can inspect it.
- **End-to-end verdict**: the machine-readable pass/fail result of driving the published stages against the test repository, plus the failing check and its expected-vs-observed detail. The only input the release decision reads.
- **Version decision**: the next version computed from the latest release tag, plus whether it is a patch or a minor increment. Never a major.
- **Release dispatch**: the request handed to the existing release automation, carrying the computed version and a non-breaking declaration.
- **Failure report**: the durable, maintainer-facing record of a failed attempt — which head, which check, expected vs. observed, and whether the cause was infrastructure or a pipeline defect.
- **Kill switch**: the repository variable that prevents any auto-release job from starting.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Non-breaking releases require zero manual dispatches; after this ships, the count of hand-typed version numbers for non-breaking releases is zero.
- **SC-002**: The time between work merging to the default branch and a release carrying it is bounded by one cadence interval plus one verification run, in every case where verification passes — replacing today's unbounded "until a maintainer remembers".
- **SC-003**: 100% of automatically cut releases were preceded by a passing end-to-end run against the test repository at that exact head; there is no automatic release whose head was never verified.
- **SC-004**: For any single unchanged head, the number of automatic releases is exactly one — never zero after a passing run, never two.
- **SC-005**: When the default branch carries no new commits, the scheduled run invokes zero agent steps and performs zero writes, in 100% of such runs.
- **SC-006**: A failed verification results in zero tags created, zero tags moved, and zero releases published, in 100% of executions.
- **SC-007**: A maintainer reading only the failure report can state, in under 2 minutes and without opening run logs, which head failed, which check failed, and whether the cause was infrastructure or a pipeline defect.
- **SC-008**: The number of breaking or major releases cut automatically is zero, across every input and every outcome.
- **SC-009**: With the kill switch set, the number of jobs that start, agent invocations made, and writes performed is zero.
- **SC-010**: The number of repositories this feature creates or deletes is zero, in every run and every outcome — as is the count of repository-administration permissions its credentials hold.
- **SC-011**: Zero artifacts of the end-to-end run appear in this repository's `specs/` tree, in any pushed branch of this repository, or in any pull request against it.
- **SC-012**: The release decision is reproducible: the same verdict input yields the same release/no-release decision every time, with no run-to-run variation attributable to an agent's judgment.
- **SC-013**: The tag, floating major tag, and release-notes logic exist in exactly one place after this feature ships — the count of independent implementations is one, and a change to release mechanics lands once.
- **SC-014**: Consecutive failing attempts for one unreleased head produce one report, not one per tick.

## Assumptions

- The existing release automation's inputs (a version string, a breaking flag, and breaking notes) are the interface this feature drives; it is reached by dispatching that workflow rather than by extracting its logic. If those inputs change, this feature's dispatch changes with them.
- "Merged changes since the last release" is measured against the most recent release tag on the default branch, not against a per-adopter or per-major baseline. A repository with several active majors is out of scope — this repository publishes one.
- Every commit on the default branch counts as new work, including documentation, specs, and this repository's own wrapper workflows. Filtering to adopter-visible changes only was considered and rejected as scope: an extra patch release of an unchanged published surface costs adopters nothing under the versioning contract, whereas a filter that wrongly suppresses a release costs them a fix.
- The first release is a human act. This feature increments from an existing baseline and never invents one.
- The test repository follows the established scratch-repository pattern in this repository: pre-created by a maintainer, named in a repository variable, credentials scoped to that repository alone, never created or deleted by the pipeline, per-run branch force-reset before scaffolding, left in place after every outcome so the evidence is inspectable.
- Unconfigured test repository means no auto-release rather than an unverified auto-release — the same fail-safe posture the auto-updater's end-to-end tier already takes for minor and major candidates.
- The kill switch is read wrapper-side, so a paused repository starts no job at all rather than starting one that suppresses its own writes.
- Reporting reuses the repository's existing maintainer-facing reporting mechanics rather than introducing a new channel or dashboard.
- The end-to-end run costs real model and wall-clock budget per attempt. The no-new-work no-op is what keeps that cost proportional to merge activity rather than to cadence, which is why FR-003 precedes the verification rather than following it.
- Detecting whether unreleased work is breaking is out of scope in every form — no heuristic, no label-driven inference, no interface diff. The manual breaking dispatch is the only route to a major.
- Verification is expected to be inherently non-deterministic where it drives agent-based stages. The *decision* that reads its verdict is not: the verdict is a concrete machine-readable value, and the code reading it is deterministic.
- Behaviour of already-published tags is unchanged: immutable exact tags, a floating major tag advanced only by the existing release automation on non-breaking releases.
- Whatever coverage FR-008 resolves to, the same set of stages runs on every attempt — coverage is not varied per run or per change size.
