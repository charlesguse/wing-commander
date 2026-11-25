# Feature Specification: Workflow security — a static-analysis gate, self-repository references, and documented trigger requirements

**Feature Branch**: `spec-draft/132-workflow-trigger-security`

**Created**: 2026-11-25

**Status**: Draft

**Input**: Issue #1188, "Workflow security: a zizmor gate, self-repository references, and documented trigger requirements". The issue follows a fact-check of a PSF / Alpha-Omega post on hardening risky GitHub Actions triggers across an organization. From December 2, 2026 GitHub blocks `pull_request_target` by default in public repositories, and the post recommends a narrow Actions event policy plus the zizmor workflow analyser. No workflow on main uses `pull_request_target`, but the post's recommended event allowlist (`pull_request`, `push`, `release`, `repository_dispatch`, `schedule`, `workflow_dispatch`, `workflow_run`) would quietly stop intake, clarify and PR conversation here and in every adopting repository, because the pipeline also runs on `issues`, `issue_comment`, `pull_request_review`, `pull_request_review_comment` and `workflow_call`. An offline zizmor 1.33.1 scan of `.github/workflows` and `.github/actions` reported 557 findings (224 suppressed). Among them: 3 `template-injection`, 7 `dangerous-triggers`, 103 `unpinned-uses`, 193 `self-repository`, and a few `github-env`, `artipacked`, `excessive-permissions` and `github-app` findings. Scope has three parts: (1) a zizmor gate, (2) a decision on self-repository (`$/`) references versus `./` references, (3) adopter documentation of the events the pipeline needs and how each is gated. Out of scope: creating an event policy on this repository or organization.

## Clarifications

### Session 2026-11-25

- Q1: Should third-party `uses:` references be pinned by full commit SHA or stay on tags? → A: Option C. Pin by SHA only actions outside a trusted-publisher set; the trusted set (such as `actions/*` and `github/*`) keeps version tags. The trusted-publisher list has one home that the gate reads, and the update automation keeps the SHA pins current (FR-009, FR-009a, FR-009b).
- Q2: Move local action references to `$/`, keep `./` with the audit disabled, or split by layer? → A: Option B. Keep `./`, disable the `self-repository` audit with a recorded reason, and add a gate that no job checks out untrusted code at the workspace root before a `./` step. No published-contract change; GHES stays supported. The FR-014 exposure audit and spec 086's trusted resolution stand alongside the new gate (FR-016, FR-016a, FR-017).

## Layer

This spec covers both interfaces Principle VII names. The static-analysis gate and the template-injection fixes apply to the **published contract** (the stage workflows and `.github/actions/**`) and to the **consuming instrument** (the `wing-commander-*.yml` wrappers). The adopter documentation describes the published contract as an adopter sees it. The self-repository decision (User Story 3) keeps `./` references, so it does not change the published contract (clarify Q2, 2026-11-25).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A workflow injection finding cannot reach main unseen (Priority: P1)

A maintainer or pipeline agent changes a workflow or composite action so that it expands an expression (`${{ ... }}`) whose value can come from outside straight into a shell script. Today nothing in the gate suite notices. With this feature, the PR-time gate suite runs a pinned workflow static analyser over every workflow and composite action. The PR fails and names the file, the line and the audit. The three injection sites present today are fixed (their values move into environment variables), so the gate starts green on main.

**Why this priority**: Template injection is the one finding class in the scan that is a live defect rather than a policy choice, and it is the class the source post's incidents turned on. A gate that blocks it is the smallest slice that delivers value on its own.

**Independent Test**: On a branch, add a `run:` step that expands `${{ github.event.issue.title }}` inline. Run the local gate suite: it fails and names that line. Move the value to `env:` and rerun: it passes.

**Acceptance Scenarios**:

1. **Given** main after this feature, **When** the gate suite runs, **Then** the analyser reports zero unwaived findings and the gate passes.
2. **Given** a PR that adds a new inline expression expansion in a `run:` block, **When** CI runs, **Then** the gate fails and its output names the file, the line and the audit.
3. **Given** the three current sites (`board-loop.yml`, the two `if [ "${{ inputs.directed-recovery }}" ...` lines; `wing-commander-rebase.yml`, the `--ref "${{ github.ref_name }}"` line), **When** this feature merges, **Then** each reads its value from an environment variable and behaves the same as before for every input it accepted before.
4. **Given** the same PR run locally with the local gate runner and in CI, **When** both finish, **Then** they use the same analyser version, configuration and file set, and give the same verdict (Principle VIII).

---

### User Story 2 - Every accepted finding is recorded with its reason (Priority: P1)

The pipeline runs on `issue_comment` and `workflow_run` by design, and the analyser flags those as dangerous triggers. A maintainer reviewing the gate wants each accepted finding recorded in one place: which finding, why it is accepted, how the workflow is gated (author association check, label check, workflow-level `permissions: {}`), and which issue tracks it. A finding that is neither fixed nor recorded fails the gate. A record that no longer matches a finding also fails the gate, so the register cannot grow stale.

**Why this priority**: Without a register, the gate either fails on day one or has to switch whole audits off, and switching off an audit is how a gate stops being able to fail its subject. The register is what makes Story 1's gate enforceable.

**Independent Test**: Remove one `dangerous-triggers` record from the register and run the gate: it fails and names the finding. Add a record for a finding that does not exist: it fails and names the stale record.

**Acceptance Scenarios**:

1. **Given** the 7 current `dangerous-triggers` findings, **When** the register is read, **Then** each has a record giving the trigger, the gate that protects it and the tracking issue.
2. **Given** a register record whose finding has been fixed or moved, **When** the gate runs, **Then** it fails and names the stale record.
3. **Given** a register record that cites an issue as its tracker, **When** that issue is closed, **Then** the existing waiver-citation check (gate 124) catches it the same way it catches other waiver registers.
4. **Given** each of the `github-env`, `artipacked`, `excessive-permissions` and `github-app` findings, **When** this feature merges, **Then** each has been either fixed or recorded with a reason. None is left suppressed with no record.

---

### User Story 3 - Composite actions resolve from trusted code only (Priority: P2)

A job that checks out a pull request's code or a consumer's ref at the workspace root, and then runs a local `./.github/actions/...` step, runs whatever copy of that action the checked-out code carries, not the trusted copy. The analyser's `self-repository` audit flags all about 639 `./` references (193 findings) as candidates for GitHub's `uses: $/...` form. That form resolves to the workflow's own repository at the running commit. A maintainer wants to know whether any job is actually exposed. The owner decided (clarify Q2, 2026-11-25) that the repository keeps `./`, switches the audit off with the reason recorded, and adds a gate that fails when a job checks out untrusted code at the workspace root before a `./` step.

**Why this priority**: Spec 086 (trusted composite resolution) already addressed part of this risk, so the exposure may be zero. The first deliverable is the audit of exposed jobs; the new gate keeps the answer true afterwards. Keeping `./` avoids a large migration and a published-contract change.

**Independent Test**: Run the exposure audit over the workflows. It lists every job in which a step checks out a ref other than the trusted workflow commit at the workspace root and a later step uses a `./` action. The list is checked by hand against two known jobs: one exposed (a fixture), one not.

**Acceptance Scenarios**:

1. **Given** the workflows on main, **When** the exposure audit runs, **Then** it reports every job where an untrusted or consumer checkout at the workspace root comes before a `./` action step. The report is recorded on the lifecycle issue.
2. **Given** an exposed job the audit found, **When** this feature merges, **Then** that job no longer runs a workspace copy of an action taken from untrusted code.
3. **Given** the self-repository decision, **When** this feature merges, **Then** the `self-repository` audit is disabled in the analyser configuration with a recorded reason, and the gate fails if that reason is removed.
4. **Given** a PR that adds a job which checks out a pull request's or consumer's ref at the workspace root and then runs a `./` action, **When** CI runs, **Then** the untrusted-checkout gate fails and names the job and the step.

---

### User Story 4 - An adopter can set an event policy without breaking the pipeline (Priority: P2)

An adopter's organization wants to apply an Actions event policy like the one the source post recommends. Before this feature, nothing tells them that such a policy would silently stop intake, clarify and PR conversation. With this feature, the adopter documentation lists every event Wing Commander's wrappers trigger on and what each one drives. It says how each is gated, gives a sample event policy that keeps the pipeline working, states the fork-PR limit on review events, and explains that `permissions:` blocks decide what a token can write, more than the trigger list does.

**Why this priority**: This is pure documentation with no code risk. It prevents a silent outage for any adopter who follows the post's advice before December 2.

**Independent Test**: Take the sample policy from the docs. Compare its event list with the set of events the wrapper workflows actually declare under `on:`. Every wrapper event appears in the policy.

**Acceptance Scenarios**:

1. **Given** the adopter docs, **When** an adopter reads the trigger section, **Then** they find each event, the stage or loop it drives, and the gate that protects it (author association, label, workflow-level `permissions: {}`).
2. **Given** the sample event policy, **When** it is compared with the events the wrapper workflows declare, **Then** no wrapper event is missing. A check enforces this so that adding a trigger to a wrapper without updating the docs fails.
3. **Given** the docs, **When** an adopter reads about fork pull requests, **Then** they learn that `pull_request_review` and `pull_request_review_comment` runs triggered from a fork get a read-only token and no secrets, and what that means for PR conversation on fork PRs.
4. **Given** the docs, **When** an adopter reads about event policies, **Then** they are told to run any new policy in Evaluate mode first. They are also told it is unresolved whether Evaluate needs Enterprise (the REST reference says yes, but GitHub's own default ran in Evaluate on Free).

---

### Edge Cases

- The analyser pin is bumped and a new version adds audits or renames one. The gate must fail loudly on findings the register does not cover. It must not pass because a renamed audit no longer matches the records.
- The analyser cannot run (binary missing, unsupported platform, network refused in offline mode). The gate must fail, not report a pass (Principle VIII).
- The file set the gate scans is empty or the path is wrong. The gate must fail.
- A composite action under `.github/actions/_shared/` or a nested action is added. It must be in the scanned set without a list being edited by hand.
- A register record matches a finding by line number, and an unrelated edit shifts the line. Records should be keyed on something stable (file, audit, job or step identity) so routine edits do not churn them. The plan decides the key.
- Moving the three injection sites to `env:` must not change behaviour: `inputs.directed-recovery` may be the empty string or `false`, and `github.ref_name` may contain `/`.
- GitHub Enterprise Server adopters cannot use `$/`, and runners older than 2.336.0 cannot resolve it. Because `./` is kept (FR-016), the published contract's documented minimums do not change.
- Gates that parse `uses: ./` today (for example the trusted-composite and composite-discovery gates) must keep working unchanged.
- An action from a trusted publisher moves out of the trusted set, or a new third-party action is added on a tag. The gate must fail until it is SHA-pinned.
- A SHA pin's version comment drifts from the SHA after a manual edit. The update automation's next run must bring them back in line; the plan decides whether a gate also checks it.

## Requirements *(mandatory)*

### Functional Requirements

**Static-analysis gate**

- **FR-001**: The PR-time gate suite MUST run a workflow static analyser, pinned to an exact version, over every workflow under `.github/workflows/` and every composite action under `.github/actions/` (including `_shared/`). It MUST be registered in the gate registry so the local gate runner and CI run it with the same version, configuration and file set.
- **FR-002**: The gate MUST fail when the analyser reports any finding that is neither fixed nor covered by a register record. Its output MUST name the file, the line and the audit for each such finding.
- **FR-003**: The gate MUST fail loudly when the analyser cannot run, when the scanned file set is empty, or when the analyser's output cannot be parsed. It MUST NOT report a pass it did not earn.
- **FR-004**: The gate MUST run without network access or a GitHub token by default, so it behaves the same on a fork PR, locally and in CI. Audits that only work online are out of the default run (see Assumptions).
- **FR-005**: The gate MUST be triggered by changes to any file it scans, to its own configuration, to the register, and to its pin.
- **FR-006**: Every failure branch of the gate (unwaived finding, stale record, analyser missing, empty file set, unparsable output) MUST be exercised by a checked-in fixture.

**Fixes**

- **FR-007**: The three `template-injection` sites (two in `board-loop.yml` expanding `inputs.directed-recovery` into `run:`, one in `wing-commander-rebase.yml` expanding `github.ref_name` into `run:`) MUST read their values through environment variables instead. Behaviour MUST be unchanged for every value they accepted before.
- **FR-008**: Each `github-env`, `artipacked`, `excessive-permissions` and `github-app` finding MUST be either fixed or recorded in the register with a reason.
- **FR-009**: Action references outside a trusted-publisher set MUST be pinned by full commit SHA, with a version comment. References to actions from the trusted-publisher set (for example `actions/*` and `github/*`) keep their version tags. The `unpinned-uses` findings MUST be fixed accordingly: no finding remains for an action outside the trusted set, and the analyser is configured to accept tags only for the trusted set. (Owner decision, clarify Q1 option C, 2026-11-25.)
- **FR-009a**: The trusted-publisher list MUST have exactly one home, and the gate MUST read it from there. No second copy of the list may exist in another gate, configuration or workflow.
- **FR-009b**: The repository's dependency-update automation MUST keep the SHA pins current, updating the SHA and its version comment together.

**Accepted-findings register**

- **FR-010**: The repository MUST keep one register of accepted analyser findings. Each record names the finding (file, audit and a stable location key), the reason it is accepted, the control that gates it, and the issue that tracks it.
- **FR-011**: The gate MUST fail on a register record that matches no current finding (a stale record).
- **FR-012**: Each of the 7 `dangerous-triggers` findings (the `issue_comment` and `workflow_run` wrappers) MUST have a register record that says how the wrapper is gated: author association, label, workflow-level `permissions: {}`, or another named control.
- **FR-013**: The register MUST be covered by the existing waiver-citation check (gate 124), so closing an issue the register cites as its tracker is caught like any other waiver register.

**Self-repository references**

- **FR-014**: The feature MUST deliver an exposure audit that lists every job in which a step checks out a ref other than the trusted workflow commit at the workspace root before a step that uses a `./` action. The result MUST be recorded on the lifecycle issue.
- **FR-015**: Every exposed job FR-014 finds MUST be fixed so it no longer runs a workspace copy of an action taken from untrusted or consumer code.
- **FR-016**: Local action references MUST stay in the `./` form. The analyser's `self-repository` audit MUST be disabled in the analyser configuration with a recorded reason, and the gate MUST fail if that reason is missing. No reference moves to `$/`, so the published contract does not change and GitHub Enterprise Server stays supported. (Owner decision, clarify Q2 option B, 2026-11-25.)
- **FR-016a**: A gate MUST fail when any job checks out untrusted or consumer code (any ref other than the trusted workflow commit) at the workspace root before a step that uses a `./` action. This gate is the standing enforcement of what the FR-014 exposure audit finds once; it stands alongside that audit and spec 086's trusted composite resolution, and replaces neither. Its failure branches MUST be exercised by checked-in fixtures (one exposed job, one safe job).
- **FR-017**: Gates that parse `uses: ./` references today MUST continue to pass on main unchanged.

**Adopter documentation**

- **FR-018**: The adopter documentation MUST list every event the wrapper workflows trigger on, what each one drives, and how each is gated.
- **FR-019**: The adopter documentation MUST give a sample Actions event policy that includes every event the pipeline needs. It MUST recommend running a new policy in Evaluate mode first, and say that it is unresolved whether Evaluate mode needs Enterprise.
- **FR-020**: A check MUST fail when a wrapper workflow declares a trigger event that the sample policy does not list.
- **FR-021**: The adopter documentation MUST state the fork-PR limit (review and review-comment events from a fork get a read-only token and no secrets) and what that means for PR conversation.
- **FR-022**: The adopter documentation MUST explain that a token's write access comes from the repository's default workflow permissions and each `permissions:` block, not from the trigger, and that trimming the trigger list does not replace least-privilege `permissions:` blocks.
- **FR-023**: `docs/reference.md` MUST be updated for every new gate, register and default this feature adds, as that file's own rules require.

**Out of scope**

- **FR-024**: This feature MUST NOT create, change or enable an Actions event policy on this repository or its organization. That is a repository setting and the owner's call.

### Key Entities

- **Analyser pin**: the exact analyser version the gate runs, kept in one place and read by both the local runner and CI.
- **Analyser configuration**: which audits run, at what level, and which are disabled with a recorded reason.
- **Accepted-findings register**: one record per accepted finding. Each record has a file, an audit, a stable location key, a reason, a gating control and a tracking issue.
- **Trusted-publisher list**: the one list of action publishers whose references may stay on version tags; every other third-party reference is SHA-pinned.
- **Exposure audit report**: the list of jobs where an untrusted or consumer checkout at the workspace root comes before a `./` action step.
- **Trigger inventory**: the set of events the wrapper workflows declare, matched against the sample event policy in the docs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On main after this feature, the analyser gate reports 0 unwaived findings, and 0 `template-injection` findings remain at all (the 3 current sites are fixed, not waived).
- **SC-002**: 100% of the gate's failure branches have a checked-in fixture that makes the gate fail.
- **SC-003**: The local gate runner and CI give the same verdict on the same commit for this gate in every fixture case.
- **SC-004**: Every one of the 7 `dangerous-triggers` findings has a register record that names its gating control, and 0 register records are stale.
- **SC-005**: The exposure audit's result is recorded, and 0 jobs remain in which untrusted or consumer code supplies a `./` action that then runs.
- **SC-005a**: 0 third-party action references outside the trusted-publisher set remain on a tag or branch, and the untrusted-checkout gate fails its exposed-job fixture and passes on main.
- **SC-006**: 100% of the events the wrapper workflows declare appear in the documented sample event policy, and a check enforces it.
- **SC-007**: An adopter can find, in one documentation page, every event the pipeline needs and the gate on each, without reading a workflow file.

## Assumptions

- The analyser is zizmor, pinned to 1.33.1 (the version the issue's scan used) unless planning finds a reason to move. The pin is moved deliberately, never floated.
- The gate runs offline by default. Audits that need the GitHub API (for example, checks against upstream tags) are not part of the PR-time run. A later spec can add an online run on push or schedule.
- "Fixed or recorded" for the `github-env`, `artipacked`, `excessive-permissions` and `github-app` findings is decided one finding at a time during implementation. The spec requires only that none is left without a record.
- Findings currently suppressed by the analyser's own defaults (224 in the scan) are judged by the configuration the plan picks. The gate's job is to make every finding that the chosen configuration reports either fixed or recorded.
- Spec 086 (trusted composite resolution) already limits where untrusted code can supply a composite action. The exposure audit may find zero exposed jobs, and that result is a valid outcome.
- The source post's claim that the trigger grants a "read/write token" is overstated (write access comes from permissions). The adopter docs state the corrected version.
- The repository's existing waiver-register conventions (JSON registers under `.github/scripts/`, tracker citations checked by gate 124) are reused for the accepted-findings register.
- December 2, 2026's `pull_request_target` default does not affect this repository, because no workflow on main uses that trigger. Nothing in this spec depends on it.
