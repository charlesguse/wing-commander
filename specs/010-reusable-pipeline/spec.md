# Feature Specification: Reusable Pipeline Extraction

**Feature Branch**: `010-reusable-pipeline`

**Created**: 2026-07-11

**Status**: Draft

**Input**: User description: "I want to make the whole project reusable but not dictate the entire process project management process. I want to make it so people can use the different speckit methods as similarly as to how they are consumed on this project. Ideally I would consume what I would publish for others to use. People will have to bring their own Claude subscription though of course whether it be the oauth token or an api key."

## Clarifications

### Session 2026-07-11

- Q: When an adopting repository has both a Claude OAuth token and an API key configured, which credential should a published stage use? → A: Follow Claude Code's documented authentication precedence (the API key outranks the subscription OAuth token); the pipeline defers to the underlying tool's precedence rather than defining its own.
- Q: How should stage-logic fixes reach adopters with respect to version pinning? → A: Publish both exact version tags and a floating major tag (e.g., `v1`); adopters tracking the major tag receive non-breaking fixes automatically, adopters pinning an exact tag upgrade deliberately.
- Q: How is "both credential types verified working" (SC-006) satisfied, given the publisher dogfoods with OAuth only? → A: The API-key path is implemented and code-reviewed only; live API-key verification is deferred to adopter feedback. The OAuth path is verified continuously by dogfooding.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Adopt the pipeline without copying it (Priority: P1)

A maintainer of another repository wants spec-driven development automation like this project has. They reference the published pipeline stages from their own repository, supply their own Claude credentials (an OAuth token from their Claude subscription, or an API key), and complete the documented one-time setup. From then on, opening an issue and applying the approval label in *their* repository drives the same spec → plan → tasks → implement → finalize lifecycle — operating entirely on their repository's own specs, constitution, and templates.

**Why this priority**: This is the core value of the feature. Today adoption requires copying workflow files wholesale (README "adopt it today" step 2), which means consumers fork the logic and never receive fixes. Published, referenceable stages are what make the project genuinely reusable.

**Independent Test**: Create a fresh repository, follow only the published adoption documentation (no file copying from this repository beyond the documented thin wrappers), open an issue, apply the label, and observe a spec PR appear that uses the fresh repository's own templates.

**Acceptance Scenarios**:

1. **Given** a repository with its own spec-kit setup and valid Claude credentials configured, **When** the maintainer wires up the published pipeline stages and triggers the intake flow, **Then** a spec PR is produced in that repository using that repository's templates and constitution, with no content originating from the publishing repository.
2. **Given** an adopting repository, **When** a fix ships in a new release of the published pipeline, **Then** the adopter receives the fix automatically (if tracking the floating major tag) or by updating a single version reference (if pinned to an exact tag) — no re-copying of stage logic.
3. **Given** an adopting repository whose credentials are missing or misconfigured, **When** a stage runs, **Then** it fails fast with a message naming the missing/invalid credential before any billable agent work starts.

---

### User Story 2 - Pick only the methods you want, keep your own process (Priority: P2)

A team already has its own project-management process — its own triggers, labels, review gates, and branching habits. They adopt only the speckit methods they want (for example, just spec intake and clarification, or just plan generation) and wire those into their existing process. The published stages do not require adopting the full issue-driven lifecycle, this project's label taxonomy, or its gate sequence.

**Why this priority**: The user explicitly does not want to dictate the consumer's project-management process. Without per-stage adoption, the pipeline is all-or-nothing and most teams can't fit it into existing workflows.

**Independent Test**: In a test repository, adopt exactly one stage (e.g., plan generation) with a custom trigger of the adopter's choosing, and verify it runs correctly with no other stages, labels, or lifecycle conventions present.

**Acceptance Scenarios**:

1. **Given** a repository that adopts only one published stage, **When** that stage is triggered through the adopter's own chosen event, **Then** the stage completes its work without requiring any other stage, label, or lifecycle convention to exist.
2. **Given** an adopter who wants different gating (e.g., tasks reviewed as a PR instead of auto-committed, a different iteration cap, different model choices), **When** they set the documented configuration options, **Then** the stage honors them without the adopter forking stage internals.
3. **Given** an adopter using their own trigger events and labels, **When** stages run, **Then** how a stage is *invoked* (events, gates, approvals) remains fully under the adopter's control while *what the stage does* comes from the published logic.

---

### User Story 3 - The publisher dogfoods the published pipeline (Priority: P3)

This repository itself consumes the exact stages it publishes. Its workflows become the same kind of thin wrappers an external adopter would write, referencing the published stages rather than containing the stage logic inline. Every future feature continues to be built through the pipeline, now exercising the published interface on every run.

**Why this priority**: Dogfooding (constitution principle I) is the project's quality mechanism — if this repository consumes the published interface, adoption breakage is discovered here first. It depends on P1 existing, hence P3.

**Independent Test**: Inspect this repository's active workflows and verify the stage logic lives only in the published, versioned location; run one full lifecycle here and confirm it exercises the same interface an external consumer would.

**Acceptance Scenarios**:

1. **Given** the extraction is complete, **When** a feature flows through this repository's pipeline, **Then** every stage executes via the same published interface offered to external adopters.
2. **Given** stage logic needs a fix, **When** the fix is made, **Then** it is made in exactly one place and both this repository and external adopters receive it the same way (via their version reference — floating major tag or exact pin).

---

### User Story 4 - Bring your own Claude subscription, either credential type (Priority: P2)

An adopter authenticates the agent stages with whichever credential their Claude plan provides: a Claude subscription OAuth token or an API key. Both are first-class; documentation explains where each comes from, and the pipeline uses whichever one the adopter configured.

**Why this priority**: Adoption is impossible without credentials, and today the pipeline assumes OAuth only. Supporting both removes the largest audience restriction; it is required for P1 to serve API-key users but is separable work.

**Independent Test**: Configure a repository with only an OAuth token and verify a stage completes successfully (covered by this repository's dogfooding). For the API-key path, verify by review that the credential wiring treats the API key as first-class per Claude Code's documented precedence; a live API-key run is deferred to adopter feedback.

**Acceptance Scenarios**:

1. **Given** a repository configured with only an OAuth token, **When** a stage runs, **Then** the agent authenticates with the OAuth token and completes.
2. **Given** a repository configured with only an API key, **When** a stage runs, **Then** the agent authenticates with the API key and completes. (Verification posture for this scenario: see SC-006 — code review, with live verification deferred to adopter feedback.)
3. **Given** a repository configured with neither credential, **When** a stage runs, **Then** it fails before any agent work with a message telling the adopter exactly which of the two credentials to add.
4. **Given** a repository configured with both credentials, **When** a stage runs, **Then** the API key is used, matching Claude Code's documented authentication precedence, and the adoption documentation states this.

---

### Edge Cases

- What happens when an adopting repository has no spec-kit setup (`.specify/`, speckit skills)? Stages must detect this and fail with guidance pointing to the prerequisite step, not fail mid-run with confusing errors. Spec-kit *version* compatibility is a documented prerequisite (the pinned supported version), checked best-effort: when the adopter's recorded spec-kit version is detectable, a mismatch produces a warning, never a hard failure.
- What happens when the published pipeline releases a breaking change? Adopters pinned to an earlier version must be unaffected until they deliberately upgrade; the release notes must state what breaks.
- What happens when an adopter's repository uses different branch naming or default-branch conventions than this project? Stage behavior that depends on conventions must be configurable or derived from the consuming repository, never hardcoded to this project's habits.
- What happens when only part of the lifecycle is adopted and a stage expects a predecessor's output (e.g., plan without a merged spec)? The stage must report the missing precondition clearly rather than producing a broken artifact.
- What happens when this repository (the publisher) needs to test an unreleased stage change? The dogfooding setup must allow this repository to exercise in-development stage logic before a release is cut, without breaking external adopters.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Each pipeline stage (intake, clarify, plan, tasks, implement⟲converge, finalize, cleanup, auto-rebase) MUST be published as an independently consumable unit that another repository can invoke by reference, without copying the stage's internal logic.
- **FR-002**: Adopters MUST be able to compose any subset of stages with their own trigger events, approval gates, and labels; no published stage may require the full lifecycle, this project's label taxonomy, or its gate sequence in order to function.
- **FR-003**: Published stages MUST authenticate Claude agent work with adopter-supplied credentials, accepting either a Claude subscription OAuth token or an API key. When both are present, the API key takes precedence, consistent with Claude Code's documented authentication precedence; adoption documentation MUST state this rule.
- **FR-004**: A stage MUST fail before any billable agent work begins when required credentials are absent or empty, with an error naming the exact configuration the adopter must add.
- **FR-005**: Published stages MUST operate exclusively on the consuming repository's own artifacts (constitution, templates, skills, `specs/`) per constitution principle VI, and MUST NOT bundle, read, or write project content belonging to the publishing repository.
- **FR-006**: Stage behavior currently configurable in this repository (model selection, iteration caps, tasks-as-commit vs. tasks-as-PR, and similar) MUST remain configurable by adopters through documented inputs, without forking.
- **FR-007**: This repository MUST consume the published stages through the same interface offered to external adopters, so stage logic exists in exactly one maintained place.
- **FR-008**: The published pipeline MUST be versioned with both exact version tags and a floating major tag (e.g., `v1`). Adopters tracking the major tag receive non-breaking fixes automatically; adopters pinning an exact tag receive changes only by updating their pin. Breaking changes MUST land only behind a new major tag and MUST be identifiable from release information before upgrading.
- **FR-009**: A stage invoked in a repository missing its prerequisites (no spec-kit setup, missing predecessor artifacts) MUST stop with a message identifying the missing prerequisite and the step that provides it.
- **FR-010**: Adoption documentation MUST cover: prerequisites (own spec-kit setup, credentials from the adopter's Claude plan, one-time repository setup), a minimal full-pipeline example, and a per-stage reference enabling partial adoption.

### Key Entities

- **Published stage**: One reusable unit of pipeline behavior (e.g., intake, plan). Has a versioned identity, documented inputs (configuration, credentials) and outputs (PRs, commits, comments produced in the consuming repository).
- **Consumer wrapper**: The small piece an adopting repository owns — declares *when* a stage runs (events, gates) and passes credentials/configuration; contains no stage logic.
- **Adopter credentials**: The Claude subscription OAuth token or API key, plus repository automation identity (e.g., the GitHub App from setup) — always supplied by the consuming repository, never by the publisher.
- **Consumer spec-kit artifacts**: The adopting repository's own `.specify/` content, skills, constitution, and `specs/` directory — the data every published stage operates on.
- **Release**: A versioned snapshot of all published stages, referenced by adopters via an exact tag or the floating major tag; carries notes distinguishing breaking from non-breaking changes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A maintainer with an existing repository and Claude credentials can go from "never used speckit-action" to a working spec PR in their own repository in under 60 minutes using only the published documentation.
- **SC-002**: An adopter can enable a single stage in isolation, and 100% of published stages function without any sibling stage present.
- **SC-003**: After extraction, zero lines of stage logic are duplicated between this repository's active workflows and the published stages — this repository's wrappers are the same shape an external adopter's would be.
- **SC-004**: A stage-logic fix reaches any adopter (including this repository) through at most one change on the adopter's side: adopters tracking the floating major tag receive it automatically, and adopters pinning an exact tag update only the version reference.
- **SC-005**: 100% of stage runs with missing or empty Claude credentials terminate with an actionable error before any billable agent work occurs. Credential *validity* probing is out of scope: a present-but-invalid credential fails at the first agent call, still before any successful billable work.
- **SC-006**: The OAuth credential path is verified by at least one full stage run completing with only an OAuth token configured (satisfied continuously by this repository's dogfooding). The API-key path is implemented and code-reviewed as first-class, with its credential wiring inspectable in review; live API-key verification is deferred to adopter feedback rather than a publisher-run test.

## Assumptions

- GitHub is the delivery platform: "publishable and consumable by reference" means the mechanisms GitHub natively provides for sharing automation between repositories, matching the project's GitHub-native principle (III). No marketplace beyond GitHub's own is in scope.
- Versioning follows the ecosystem norm of tagged releases with semantic meaning (breaking vs. non-breaking): exact tags plus a floating major tag that is advanced for non-breaking releases. No stronger guarantee (e.g., LTS branches) is assumed for v1.
- The adopter's one-time setup mirrors this repository's documented setup (dedicated GitHub App identity, secrets, labels for the stages they adopt); simplifying that setup further is desirable but not required by this feature.
- The stub stages (finalize, cleanup, auto-rebase) are published in whatever state they are in when extraction lands; extraction does not require completing their bodies first, only that whatever exists is consumed through the published interface.
- "Not dictating the process" means adopters control triggers, gates, labels, and which stages run — it does not mean stages must support arbitrary alternative artifact layouts; the spec-kit artifact conventions (`specs/NNN-slug/`, `spec-meta.json`) remain the shared contract.
- Consumers bring their own Claude subscription and bear their own usage costs; the publisher provides no shared credentials, proxy, or billing.
- This repository migrates to the published interface as part of this feature (dogfooding), accepting a short transition period during which it may reference unreleased stage versions to test them.
