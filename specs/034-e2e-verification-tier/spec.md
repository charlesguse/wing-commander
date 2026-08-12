# Feature Specification: End-to-End Verification Tier That Actually Verifies the Candidate

**Feature Branch**: `034-e2e-verification-tier`

**Created**: 2026-08-12

**Status**: Draft

**Input**: User description: "Auto-update Spec Kit: the 'end-to-end' tier verifies almost nothing. Split out from #157, which bundled two gaps found during specs/027's T032 scenario walk; the other gap (a `prepare` failure leaving the lifecycle issue silent) shipped in #164, so this issue carries the surviving half. `quickstart.md` Scenario 7 describes the minor/major tier as 'a throwaway spec-kit-driven stage generated and discarded'. The implementation copies `spec-template.md` into the scratch feature directory and checks the copy is non-empty. No spec-kit script runs, no stage runs, and the `else` branch means a *missing* `spec-template.md` still passes. The candidate version's behaviour is never exercised beyond what the lightweight tier already covered, so the extra tier buys close to nothing for the case it exists to protect. The only change to this step since the original report was the `FEATURE_DIR` double-prefix repair, which made the tier actually execute — it did not make it verify anything. This matters now because the repo is pinned at 0.12.4 and upstream is at v0.16.2: the next adoption is a minor jump, which routes straight through this tier — the exact case it exists to protect, and the case it currently cannot fail. Suggested fix: run something that actually depends on the candidate's own artifacts — e.g. `setup-plan.sh --json` after the feature is created, asserting the documented shape — and drop the `else` fallback so a missing template fails rather than passes. `t4_verify.sh` (from #156) already has the harness to assert whatever shape is chosen. Open question carried over from #157 (spec `030-auto-update-gaps`, PR #170, stalled on it): when the end-to-end tier finds the expected artifact missing, should that be a verification failure or routed to human attention as a non-clean-bump per specs/027 FR-018? Answered in the issue conversation as **option C**: a missing expected artifact is a verification failure — the candidate is judged not working, it is not adopted, the pinned version is left unchanged, and the lifecycle issue is flagged with `auto-update:failed`. There is exactly one failure path, and the `else` fallback is removed. Additionally, the failure narration must state that a missing expected artifact can also mean the candidate legitimately reorganized its templates or scripts rather than that it is broken, and point the maintainer at the parent spec's FR-018 (non-clean-bump) route as the thing to consider when re-triaging. That is narration content only — it does not create a second outcome path and does not change the label, the adoption decision, or the flow of the run. The reasoning: distinguishing 'missing because broken' from 'missing because moved' is not something the tier can decide reliably on its own, so guessing between two automated outcomes would be worse than failing safe."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A broken minor/major candidate is caught by the deeper tier (Priority: P1)

The scheduled Spec Kit auto-update detects a new upstream version that is a minor or major jump from the pinned version. Because the jump is larger than a patch, the deeper verification tier runs in addition to the lightweight one. That deeper tier exercises the candidate version's *own* Spec Kit artifacts — running a real spec-kit operation out of the candidate's checkout and checking the result against the shape the pipeline depends on. When the candidate behaves differently from what the pipeline needs, the run reports a verification failure instead of proceeding to a version-bump PR.

**Why this priority**: This is the entire reason the tier exists. The pipeline is pinned at 0.12.4 with upstream at v0.16.2, so the very next adoption is a minor jump routed through this tier. Today that tier cannot fail for any candidate-specific reason, which means the largest jump the project has ever attempted would be waved through on the strength of the lightweight check alone. Fixing this one behaviour delivers the protection on its own.

**Independent Test**: Point the deeper tier at a candidate whose Spec Kit scripts are deliberately broken (made to exit non-zero, or made to emit a renamed/absent output field) and confirm the minor/major run reports verification failure with a reason naming the failing check — while the same tier passes for an unmodified, healthy candidate.

**Acceptance Scenarios**:

1. **Given** a minor or major candidate whose Spec Kit artifacts behave as the pipeline expects, **When** the deeper verification tier runs, **Then** it passes and the run proceeds to the version-bump PR as it does today.
2. **Given** a minor or major candidate whose Spec Kit operation exits non-zero, **When** the deeper verification tier runs, **Then** the tier fails and the failure reason names the operation and what went wrong.
3. **Given** a minor or major candidate whose Spec Kit operation succeeds but emits an output that no longer carries the documented shape the pipeline consumes, **When** the deeper verification tier runs, **Then** the tier fails and the failure reason states what shape was expected and what was observed.
4. **Given** any input to the deeper tier, **When** it reports a pass, **Then** that pass depended on at least one behaviour of the candidate's own artifacts that the lightweight tier did not already establish.

---

### User Story 2 - A missing expected artifact fails instead of silently passing (Priority: P1)

The deeper tier depends on artifacts that the candidate version is expected to ship (templates, scripts). Today, if one of those is absent, the step quietly substitutes locally-generated content and still reports a pass. Instead, an absent expected artifact is treated as the candidate not being verifiable, and the run fails.

**Why this priority**: This is the second half of "the tier cannot fail". Even after the tier is given real work to do, a fallback path that manufactures a substitute when the candidate's artifact is missing would restore the same blind spot. Removing the fallback is independently valuable and independently testable, and it is the specific behaviour the carried-over open question was about.

**Independent Test**: Run the deeper tier against a candidate checkout with an expected artifact removed and confirm the tier fails — with no locally-manufactured substitute written and no pass reported.

**Acceptance Scenarios**:

1. **Given** a candidate checkout missing an artifact the deeper tier expects, **When** the tier runs, **Then** it reports a verification failure naming the missing artifact and the path where it was expected.
2. **Given** the deeper tier fails for any reason, **When** the run continues, **Then** the candidate is not adopted, the pinned version is left unchanged, no version-bump PR is merged, and the lifecycle issue stays open and flagged `auto-update:failed`.
3. **Given** a missing expected artifact, **When** the outcome is determined, **Then** there is exactly one outcome — verification failure — and no separate "non-clean-bump" routing branch, label, or alternate flow is taken.

---

### User Story 3 - The failure narration tells the maintainer what to consider next (Priority: P2)

A maintainer opens the lifecycle issue after a deeper-tier failure. The narration tells them which check failed, what was expected and what was observed. When the failure was a missing expected artifact, the narration additionally says that the artifact may have been *relocated or reorganized* by the candidate rather than being evidence that the candidate is broken, and points at the non-clean-bump route (parent spec 027, FR-018) as the thing to weigh when re-triaging.

**Why this priority**: Failing safe is only useful if the human who picks it up knows what the failure might actually mean. Distinguishing "missing because broken" from "missing because moved" is a judgment the workflow cannot make reliably, so the value is in handing the maintainer that distinction explicitly. It depends on US1/US2 existing first, so it is P2.

**Independent Test**: Trigger a deeper-tier failure caused by a missing expected artifact and confirm the lifecycle issue comment alone — with no access to run logs — states the failing check, the expected artifact and path, and the non-clean-bump consideration with a pointer to FR-018.

**Acceptance Scenarios**:

1. **Given** a deeper-tier failure caused by a missing expected artifact, **When** the failure is narrated on the lifecycle issue, **Then** the comment states that the artifact may have been legitimately relocated by the candidate and names the non-clean-bump route (027 FR-018) as the thing to consider when re-triaging.
2. **Given** a deeper-tier failure caused by something other than a missing artifact (non-zero exit, wrong output shape), **When** the failure is narrated, **Then** the comment states the failing check and the expected-vs-observed detail.
3. **Given** any deeper-tier failure, **When** the run finishes, **Then** the label applied, the adoption decision, and the sequence of the run are identical regardless of which failure reason produced it — the narration text is the only thing that varies.
4. **Given** a maintainer reading only the lifecycle issue, **When** they read the failure comment, **Then** they can state which version was being verified, which check failed, and what to look at next, without opening the workflow run.

---

### User Story 4 - The behaviour is asserted by the executable harness, not desk-checked (Priority: P3)

The tier's pass and failure paths are covered by the repository's executable scenario harness for this workflow, so a future edit that re-weakens the tier fails a check instead of surviving until the next real upgrade.

**Why this priority**: The original defect survived a scenario walk precisely because Scenario 7 was desk-checked against a description rather than executed against behaviour. Coverage is what stops the same class of regression, but it delivers nothing on its own if US1–US3 have not landed, so it is P3.

**Independent Test**: Run the existing scenario harness for this workflow and confirm it exercises, and can fail on, each of: a healthy candidate passing, a missing expected artifact failing, a wrong-shape result failing, and the narration carrying the non-clean-bump hint.

**Acceptance Scenarios**:

1. **Given** the scenario harness for this workflow, **When** it runs against the fixed tier, **Then** it asserts a pass for a healthy candidate and a failure for each defective-candidate case above.
2. **Given** a change that reintroduces a fallback pass or removes the candidate-dependent assertion, **When** the harness runs, **Then** at least one harness check fails.
3. **Given** the parent spec's Scenario 7 narrative, **When** it is compared with the implemented tier, **Then** the narrative describes what the tier actually does.

---

### Edge Cases

- **Expected artifact absent from the candidate**: verification failure; no substitute content is manufactured; narration carries the relocation/FR-018 hint.
- **Candidate operation exits non-zero**: verification failure; the captured reason (trimmed to a readable length) is carried to the lifecycle issue.
- **Candidate operation succeeds but emits a renamed, absent, or empty documented field**: verification failure describing expected vs. observed shape.
- **Lightweight tier already failed**: the deeper tier does not run and the combined verdict reports the lightweight reason — unchanged from today.
- **Deeper tier fails after creating scratch files**: the disposable worktree is still discarded, and nothing reaches the repository's real `specs/` tree or any pushed branch.
- **Patch-type jump**: the deeper tier does not run at all; tiering is unchanged.
- **Candidate legitimately reorganized its templates/scripts**: still a verification failure (single path), with the narration telling the maintainer that a non-clean bump is the alternative reading.
- **Deeper tier failure reason contains newlines or shell-hostile characters**: the reason still reaches the lifecycle issue intact and readable.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The end-to-end verification tier MUST execute at least one real Spec Kit operation resolved from and run out of the *candidate* version's own checkout, such that the tier's verdict depends on the candidate's own behaviour.
- **FR-002**: The tier MUST assert the documented result of what it runs — the documented output fields present and non-empty, and the documented on-disk artifacts created — rather than asserting only that some file exists and is non-empty. [NEEDS CLARIFICATION: should the tier exercise one additional Spec Kit operation beyond what the lightweight tier already runs, or every `.specify` script the pipeline depends on? Breadth trades regression coverage against how often a legitimate upstream reorganization fails the tier.]
- **FR-003**: The tier's assertions MUST add coverage beyond the lightweight tier: at least one assertion MUST be one that the lightweight tier's checks could not already have satisfied. [NEEDS CLARIFICATION: does "end-to-end" require invoking a real AI-driven pipeline stage against the candidate, or is exercising the candidate's Spec Kit scripts and templates without an agent run sufficient to satisfy the parent spec's FR-004? The former is closer to the parent spec's wording; the latter keeps the scheduled job free of agent cost and non-determinism.]
- **FR-004**: The tier MUST NOT contain any fallback path that substitutes locally generated content for an expected candidate artifact. When an expected artifact is absent, the tier MUST fail.
- **FR-005**: A deeper-tier failure MUST produce exactly one outcome: verification failure. The candidate is not adopted, the pinned version is left unchanged, no version bump is applied, and the lifecycle issue stays open and is flagged `auto-update:failed`.
- **FR-006**: The system MUST NOT introduce a second automated outcome path (such as a distinct non-clean-bump routing) for a missing expected artifact; the label applied, the adoption decision, and the flow of the run MUST be identical across all deeper-tier failure reasons.
- **FR-007**: The failure narration posted to the lifecycle issue MUST state which check failed and what was expected versus what was observed.
- **FR-008**: When the deeper-tier failure is a missing expected artifact, the narration MUST additionally state that the artifact may indicate the candidate legitimately reorganized its templates or scripts rather than that the candidate is broken, and MUST point the maintainer at the parent spec's non-clean-bump route (specs/027, FR-018) as the thing to consider when re-triaging.
- **FR-009**: The narration required by FR-008 MUST be narration content only — it MUST NOT change labels, the adoption decision, or the sequence of the run.
- **FR-010**: A maintainer MUST be able to determine, from the lifecycle issue's own comments alone and without opening run logs, which candidate version was being verified, which check failed, the expected-vs-observed detail, and what to consider next.
- **FR-011**: The tier MUST continue to run only for minor and major candidates and only after the lightweight tier has passed; tier selection and the patch-only-lightweight rule are unchanged.
- **FR-012**: The combined verification verdict MUST continue to carry the deeper tier's failure reason when the deeper tier is the failing check, and the lightweight reason when the lightweight tier is.
- **FR-013**: Every artifact the tier creates MUST remain inside a disposable isolated checkout that is discarded on every outcome (pass, fail, or error); no scratch artifact may land in the repository's real `specs/` tree, in any pushed branch, or in any opened pull request.
- **FR-014**: The failure reason MUST survive transport to the lifecycle issue intact, including multi-line content, trimmed to a readable length rather than dropped.
- **FR-015**: The pass and failure paths of the tier MUST be asserted by the repository's executable scenario harness for this workflow, covering at minimum: a healthy candidate passing, a missing expected artifact failing, a wrong-shape or non-zero-exit result failing, and the narration carrying the non-clean-bump hint.
- **FR-016**: The parent spec's Scenario 7 narrative MUST be updated to describe what the tier actually does, so the description and the implementation no longer disagree.

### Key Entities

- **Candidate version**: the upstream Spec Kit version being evaluated for adoption, materialized in a disposable isolated checkout; the subject of every deeper-tier assertion.
- **Verification tier**: a named group of checks (lightweight, end-to-end) selected by release type; produces a pass/fail verdict plus a human-readable failure reason.
- **Verification verdict**: the combined pass/fail result plus the tier label and the failure reason carried forward to the lifecycle issue and the job summary.
- **Failure narration**: the comment posted to the lifecycle issue; carries the failing check, expected-vs-observed detail, and — for a missing artifact — the non-clean-bump consideration.
- **Scratch feature artifacts**: the throwaway feature directory and files the tier creates inside the disposable checkout; never committed, never pushed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a minor or major candidate whose Spec Kit behaviour is broken (non-zero exit, or missing/renamed documented output), the run reports verification failure in 100% of executions — demonstrated by the executable scenario harness, not by inspection.
- **SC-002**: There is no input for which the deeper tier reports a pass without at least one assertion having depended on the candidate's own artifacts; in particular, a candidate missing an expected artifact never passes.
- **SC-003**: The deeper tier's assertions are strictly a superset of the lightweight tier's — at least one deeper-tier assertion fails on a defective candidate that the lightweight tier reports as healthy.
- **SC-004**: A maintainer reading only the lifecycle issue can, in under 2 minutes and without opening run logs, state which version failed, which check failed, and whether a non-clean bump is worth considering.
- **SC-005**: Across pass, fail, and error outcomes, zero scratch artifacts from the deeper tier appear in the repository's real `specs/` tree, in any pushed branch, or in any opened pull request.
- **SC-006**: The next real minor/major adoption (0.12.4 → the then-current upstream version) is decided on evidence produced by the candidate's own behaviour rather than on a check that cannot fail.
- **SC-007**: Every deeper-tier failure reason and the parent spec's Scenario 7 description match the tier's implemented behaviour when compared side by side.

## Assumptions

- The carried-over open question from #157 is treated as **answered — option C**, per the issue conversation: a missing expected artifact is a single verification failure whose *narration* carries the FR-018 non-clean-bump hint, not a second outcome branch.
- Tier selection itself is out of scope and unchanged: patch jumps run the lightweight check only; minor and major jumps run lightweight plus the deeper tier, and only after lightweight passes (parent spec 027, FR-004/FR-014).
- The existing lifecycle-issue mechanics are reused unchanged: the same `auto-update:failed` label, the same issue-stays-open behaviour, the same comment mechanism. Only the failure text gains the non-clean-bump sentence.
- The scheduled health check of the *already pinned* version keeps its lightweight-only scope; this feature changes the candidate-verification tier only.
- The deeper tier continues to operate inside the same disposable isolated checkout and scratch feature that the lightweight tier already established, rather than provisioning its own.
- The repository's existing executable scenario harness for this workflow (from #156) is the home for the new assertions; no new test framework is introduced.
- Rollback, revert-PR, and post-merge regression behaviour are unchanged by this feature.
- "Expected artifact" means an artifact the pipeline itself depends on and that the tier names explicitly — not any arbitrary file the candidate happens to ship.
