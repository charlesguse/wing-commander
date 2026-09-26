---

description: "Task list for feature 067: Container-Mode Evidence in End-to-End Release Verification"
---

# Tasks: Container-Mode Evidence in End-to-End Release Verification

**Input**: Design documents from `/specs/067-e2e-container-image-evidence/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/container-evidence-outcomes.md, contracts/container-evidence-decision-script.md, quickstart.md (all present)

**Tests**: Not explicitly requested as TDD. Constitution VIII and this repository's own PR-time gate suite (`.github/scripts/run-local-gates.py`) require the new pure decision script and every FR-005 outcome branch to ship with a checked-in, locally runnable fixture (SC-006) — those fixture tasks are folded into User Story 1 as the new gate's own acceptance mechanism, not a separate opt-in pass. This feature also carries several live-proof tasks against a real (or fixture-driven) `auto-release.yml` container-mode turn, mirroring `quickstart.md`'s scenarios and matching the precedent `specs/054-e2e-container-coverage/tasks.md` and `specs/055-unattended-e2e-gates/tasks.md` both set for this workflow.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P1/P2/P3). The pure decision script (D6), the provisioning-script pin-comparison reuse (D3), and the shared read-status classification (D6's fetch half) are pulled into Foundational rather than into User Story 1, because both of User Story 1's new evidence steps call them from the moment they exist, and User Story 2's fail-closed behaviour depends on the same classification already existing rather than being invented twice — see Dependencies & Execution Order below.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US4)
- Line numbers cited below are today's positions in `.github/workflows/auto-release.yml`, confirmed during this stage's own research against the current checkout: `id: maintainer-credential` at line 301 (step ends ~413), `id: cleanup` at line 424, `id: scaffold` at line 588, `id: kickoff` at line 688, `id: poll` at line 751, the existing chain-stop-notice branch (case iii) at lines 1091-1113, and the sole `pass`-writing call at line 1338. Locate sites by step `id`/name once a prior task in the same phase has landed, since each edit shifts later line numbers.

## Path Conventions

CI/CD pipeline infrastructure repository — no `src`/`tests` split. Paths below are repository-root-relative (`.github/`, `docs/`, `specs/`), per plan.md's Project Structure. No published stage workflow (`.github/workflows/{intake,clarify,plan,tasks,implement,finalize,cleanup,rebase}.yml`) or `.github/actions/**` composite action other than the one new `_shared/` script is touched by any task below (plan.md's Structure Decision).

---

## Phase 1: Setup

**Purpose**: Confirm the baseline this feature edits against, before any file changes.

- [ ] T001 Confirm today's line anchors in `.github/workflows/auto-release.yml` match research.md/plan.md's citations: `id: maintainer-credential` (~lines 301-413), `id: cleanup` (~line 424), `id: scaffold` (~lines 588-681), `id: kickoff` (~line 688), `id: poll` (~lines 751-1339) including its existing chain-stop-notice branch (~lines 1091-1113) and its sole `pass`-writing call (~line 1338). Record any drift from research.md's citations in the PR description rather than in a spec file. No file changes.

**Checkpoint**: Baseline confirmed; Foundational work can begin.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The pure decision script, the reused pin-comparison read, and the shared read-status classification every user story's new evidence-reading steps depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T002 [P] Create `.github/actions/_shared/auto-release-container-evidence-decision.sh` implementing exactly the contract in `contracts/container-evidence-decision-script.md`: positional args `check` (`config`|`execution`), `read_status` (`ok`|`unreadable`|`rate-limited`), `expected`, `observed`; three-line stdout `failing_check=<...>` / `expected=<...>` / `observed=<...>` in that order; every row of the contract's behaviour table (`config`/`unreadable` → `container-mode evidence unreadable`, `config`/`rate-limited` → `container-mode evidence rate-limited`, `config`/`ok`+empty-observed → `container image not configured on the test repository`, `config`/`ok`+non-empty-mismatch → `container image configured but does not match this repository's pin`, `config`/`ok`+match → empty/proceed, and the four `execution` rows). Pure function of its arguments — no `gh` call inside it, callable by the new gate's fixtures with no network access (research.md D6).
- [ ] T003 Confirm `.github/scripts/e2e-provisioning/checks.sh`'s existing `this_repo_container_image()` (lines ~161-172) can be sourced and called read-only from a new `auto-release.yml` step for the "expected" side of the FR-007 comparison (research.md D3). If `check_container_image_pin()`'s existing call shape doesn't fit a read-only comparison call from `auto-release.yml` cleanly, extract the shared "read this repository's own pin" logic into one function both `provision-e2e-target.sh` and the new step call, so no second copy of that read exists (CLAUDE.md "Shared logic has exactly one home"). The exact refactor shape (call the existing function vs. extract a narrower one) is this task's own decision; the constraint is that no second copy of the read is created.
- [ ] T004 Decide and implement one shared place, in `.github/workflows/auto-release.yml`, for classifying a failed `gh` call's captured exit status and stderr text into `read_status` (`ok`/`unreadable`/`rate-limited`) — reusing the existing rate-limit-text-grep idiom this file's `write_repeated_failure_verdict` helper already applies (`grep -qi 'rate limit'`, ~line 798) — so the classification exists in exactly one place both T005's config-evidence step and T007's execution-evidence check call, never pasted twice (CLAUDE.md single-home rule). Any non-rate-limited `gh` failure (unset credential, insufficient permission, any other API error) classifies as `unreadable`; a rate-limit-text match classifies as `rate-limited`, distinct from `unreadable` (FR-004; US2 AC1/AC2 depend on this distinction existing before either call site is written).

**Checkpoint**: The decision script, the pin-comparison reuse, and the shared read-status classification all exist. User Story 1 can now wire them into `auto-release.yml`.

---

## Phase 3: User Story 1 - An unconfigured container turn fails instead of passing (Priority: P1) 🎯 MVP (with US2)

**Goal**: A container-mode turn earns its `pass` only by observing that the test repository was configured to run inside a container image matching this repository's pin, and that the stage jobs of the run it drove actually executed inside a container; every other case reaches a named `fail-infra` verdict instead.

**Independent Test**: Point the verification at a test repository with the image variable unset, run a container-mode turn, and observe a failing infrastructure-class verdict naming the unset variable and no release dispatched. Then set the variable and observe the same turn reach a pass that records the image reference it observed.

- [ ] T005 [US1] Add a new step "Read container-mode configuration evidence" (`id: container-evidence-config`) to the `verify-e2e` job of `.github/workflows/auto-release.yml`, positioned immediately after `id: maintainer-credential` and before `id: cleanup`, gated `if: steps.maintainer-credential.outputs.ok == 'true'` (research.md D1/D2). On a default-runner turn (`MODE != container`) it is a no-op that sets `ok=true` immediately (FR-008). On a container-mode turn: read the test repository's `WING_COMMANDER_CONTAINER_IMAGE` via `gh variable list --repo "$E2E_REPO"` with the maintainer token, and this repository's own pin via T003's `this_repo_container_image()`; classify each read's outcome with T004's shared classification; call T002's decision script with `check=config`. On a non-empty `failing_check`, write a `fail-infra` verdict with that exact triple — handling: an absent or empty test-repository value is "not configured" (FR-002, Edge Case); a non-empty value that differs from this repository's pin is drift (FR-007); this repository's own pin being unreadable fails closed rather than compared as empty (FR-007's last sentence) — and set `ok=false`. Otherwise set `ok=true` and record `configuration.expected_image`/`observed_image`/`observed_at` step outputs (data-model.md "Container-Mode Evidence") for T009 to carry into the eventual pass verdict.
- [ ] T006 [US1] Re-point the `id: cleanup` step's `if:` condition in `.github/workflows/auto-release.yml` from `steps.maintainer-credential.outputs.ok == 'true'` to `steps.container-evidence-config.outputs.ok == 'true'`, so an unconfigured, drifted, or unreadable container-mode turn cannot reach `cleanup`/`reset`/`speckit-version`/`scaffold`/`kickoff` (FR-011, SC-003; research.md D2) — depends on T005.
- [ ] T007 [US1] Inside the existing `id: poll` step of `.github/workflows/auto-release.yml`, immediately before the sole `pass`-writing call `write_verdict "pass" "" "" "" "$ISSUE_URL" "true"` (currently line ~1338) and strictly *after* the existing chain-stop-notice branch (~lines 1091-1113, case iii), which this task MUST leave untouched (FR-005's explicit "Case (iii) keeps its classification"; quickstart Scenario 4), add the execution-evidence read: using the maintainer token, read the test repository's Actions job data via `GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs` (the paginated `gh api .../jobs --jq` idiom `watchdog.yml` already uses, research.md D4); classify the read with T004's shared classification; determine per-job containerization from `steps[]` presence of an `Initialize containers` step (research.md D4 — unconfirmed pending T017's live check); call T002's decision script with `check=execution`. On a non-empty `failing_check`, write a `fail-infra` verdict naming the non-containerized stage job(s) and `exit 0` before the `pass` call is reached.

  **Open point to resolve before this task is complete**: data-model.md's `execution.run_id` field and research.md D4 both describe reading job data for a single test-repository run, but one attempt drives up to eight separate stage-workflow runs on the test repository (intake, clarify, plan, tasks, implement, finalize, cleanup, and any rebase), and the `poll` step's success path does not currently track any of their run IDs. Confirm against real run data (T017) whether one run's job data is sufficient, or whether every stage-workflow run this attempt drove must be enumerated (e.g. via `gh run list --repo "$E2E_REPO"` filtered to runs created after kickoff) and checked; implement whichever the real data requires. Do not assume a single run_id without that confirmation.
- [ ] T008 [US1] Confirm the `pass` call at `.github/workflows/auto-release.yml`'s `poll` step remains the only literal `"pass"` argument to `write_verdict` anywhere in the `verify-e2e` job (grep the file to confirm), so the new gate (T011-T014) has exactly one call site to prove is guarded (FR-001, FR-015) — depends on T007.
- [ ] T009 [US1] Update the `pass` call in `.github/workflows/auto-release.yml`'s `poll` step to populate its `expected`/`observed` arguments (currently empty strings — `write_verdict "pass" "" "" "" "$ISSUE_URL" "true"`) with the matching image reference `container-evidence-config` observed (T005) and a summary of the containerized stage jobs confirmed by T007's execution-evidence read, so the pass verdict itself records both observations instead of leaving them blank (Acceptance Scenario 3: "the verdict's evidence fields record both the matching image reference... and the observation that the stage jobs executed inside a container"; data-model.md "Container-Mode Evidence") — depends on T005, T007.
- [ ] T010 [US1] Immediately before naming the new gate script, re-check `.github/workflows/lint-workflows.yml` for the highest-numbered gate currently registered (research.md D7 provisionally reserved Gate 99 as of plan-writing) and confirm no other in-flight spec has already claimed that number; pick the next free number and use it consistently across T011-T014.
- [ ] T011 [US1] Write `.github/scripts/verify-gate-<N>.py` (`<N>` from T010) structural half: scan `.github/workflows/auto-release.yml` to prove the `pass`-writing call site confirmed unique in T008 is reachable only when both `container-evidence-config`'s and the execution-evidence check's decision outputs are consulted in its guarding condition (modeled on Gate 60's `verify-single-home-idioms.py` reachability technique) — fails, naming the site, if a future edit adds a second `pass` call or loosens the existing guard (FR-015 structural half, research.md D7; this also satisfies User Story 4 Acceptance Scenario 3).
- [ ] T012 [US1] Extend `.github/scripts/verify-gate-<N>.py` with the executed-step half: using `wc_shell_harness.py`'s `find_step`/`run_step` (modeled on Gate 52's `verify-auto-release-report.py`), extract and run the shipped `container-evidence-config` step's shell and the shipped `poll` step's execution-evidence block verbatim under stubbed `gh`/`date`, against one checked-in fixture per FR-005 branch: not configured, empty value, drift, unreadable, rate-limited, stage jobs not containerized, and the passing case (SC-006, research.md D7 executed-step half) — depends on T005, T007, T009 (needs the shipped steps to exist).
- [ ] T013 [US1] Add a `--self-test` mode to `.github/scripts/verify-gate-<N>.py` (or a paired `verify-gate-<N>-selftest.py` — implementer's choice per plan.md's Testing section) that mutates each fixture's expected guard or branch and asserts the gate then fails, matching Gate 60/64's mutation idiom (FR-015, Constitution VIII: "a test that cannot fail is not a test") — depends on T011, T012.
- [ ] T014 [US1] Register the new gate in `.github/workflows/lint-workflows.yml`: a `Gate <N> — ...` step running `python3 .github/scripts/verify-gate-<N>.py` plus a `Gate <N> self-test — ...` step running its self-test/mutation mode, unconditional (`if: "!cancelled()"`), following the Gate 97/98 registration shape (~lines 4131-4136) so `run-local-gates.py` and `verify-gate-wiring.py` pick it up automatically — depends on T010, T013.
- [ ] T015 [US1] Run `python .github/scripts/run-local-gates.py` and fix anything the new gate or any pre-existing gate (especially Gate 52, Gate 60, and Gate 64, which touch the same file/idioms) newly flags as a result of this feature's changes — depends on T014.
- [ ] T016 [US1] Validate quickstart.md Scenarios 1, 2, and 6 against a real (or fixture-driven) container-mode turn: unset the variable, then an empty-string value, then a value that differs from this repository's pin, confirming the exact `failing_check`/`expected`/`observed` strings from `contracts/container-evidence-outcomes.md` §2 for cases (i) and (ii) each time, and that no kickoff issue was created on the test repository (Acceptance Scenarios 1, 2, 6; SC-001) — depends on T005, T006.
- [ ] T017 [US1] Validate quickstart.md Scenario 3 against a real container-mode turn run to completion: confirm `outcome: pass`, `container_image_configured: true`, and inspect that run's own Jobs API response by hand (`gh api repos/<test-repo>/actions/runs/<id>/jobs`) to confirm an `Initialize containers` step is present in a stage job's `steps[]` array (research.md D4's required confirmation). If it is absent, misnamed, or inconsistent, fall back to the job-log-scan signal D4 documents and update T007 before this task is considered complete; also resolve T007's open run-enumeration point against this real data (Acceptance Scenario 3, SC-002) — depends on T009, T012.
- [ ] T018 [US1] Validate quickstart.md Scenario 4: configure an image the test repository cannot pull or authorize, run a container-mode turn, and confirm the existing chain-stop-notice classification (case iii, ~lines 1091-1113) is unchanged — not reclassified as "not configured" or "drift" (Acceptance Scenario 4; confirms T007's non-interference) — depends on T007.

**Checkpoint**: An unconfigured, drifted, or never-executed container-mode turn fails closed with a named verdict; a correctly configured turn reaches a pass that records both evidence observations; a regression is caught by the new gate.

---

## Phase 4: User Story 2 - The evidence check fails closed (Priority: P1) 🎯 MVP (with US1)

**Goal**: When the evidence itself cannot be obtained — credential missing, access revoked, the read refused or rate-limited — the run says so in an infrastructure-class verdict naming the unreadable evidence, distinct from "not configured," never a silently restored pass.

**Independent Test**: Remove or invalidate the access the evidence check depends on, run a container-mode turn, and observe an infrastructure-class verdict naming the unobtainable evidence rather than a pass.

- [ ] T019 [US2] Validate quickstart.md Scenario 8's first half: temporarily invalidate `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN` (or its permission) in a disposable test run and confirm `outcome: fail-infra`, `failing_check: "container-mode evidence unreadable"`, naming the credential to restore (US2 AC1, FR-004, FR-010) — depends on T005, T007.
- [ ] T020 [US2] Confirm the gate's fixtures (T012) exercise the rate-limited branch distinctly from the unreadable branch for both `check=config` and `check=execution`, per the behaviour table in `contracts/container-evidence-decision-script.md`, satisfying US2 AC2's "distinct from the 'not configured' verdict" requirement without needing to induce a real GitHub rate limit — depends on T012.
- [ ] T021 [US2] Confirm, by reading `.github/workflows/auto-release.yml`'s `report` job classification logic (`fail-infra) classification="infrastructure" ;;`, ~line 1791), that no change is needed there for the new `failing_check` strings this feature adds — `report` classifies purely by `outcome == "fail-infra"`, not by `failing_check` text, so every new case renders automatically (FR-010, SC-004, SC-005; research.md D5's stated rationale). Record this confirmation in the PR description; if `report` turns out to need a change, make it here rather than assuming it doesn't.

**Checkpoint**: A broken evidence detector reports itself as broken rather than silently reverting to the old undetected pass.

---

## Phase 5: User Story 3 - A misconfigured turn is cheap (Priority: P2)

**Goal**: A container-mode turn that is going to fail for lack of configuration is discovered before the run creates a kickoff issue or spends any stage agent turn.

**Independent Test**: Unset the variable, run a container-mode turn, and observe the run reaching its failing verdict without having created the kickoff issue or driven any stage.

- [ ] T022 [US3] Validate quickstart.md Scenario 1 steps 4-5 specifically (separable from T016's verdict-shape check): with the variable unset, confirm directly against the test repository's issue list that no kickoff issue was created for this turn, and that the test repository is left in a state a subsequent, correctly configured run can use without manual cleanup (FR-011, FR-012, SC-003; US3 AC1/AC2) — depends on T005, T006, T016.

**Checkpoint**: A misconfigured turn costs a fast failure, not a full stage chain's worth of agent turns and wall clock.

---

## Phase 6: User Story 4 - The record stops describing the gap as accepted (Priority: P3)

**Goal**: The accepted-gap language about the unset container image variable is removed from every documentation and prior-spec site now that the gap is closed, with the new requirement documented in its place.

**Independent Test**: Search the documentation and the prior spec's requirements and contract for the accepted-gap wording and find none, with each site instead stating the detection and its prerequisite.

- [ ] T023 [P] [US4] In `docs/setup.md`: replace the `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` row's "Known limitation" paragraph (line 128, the sentence beginning "Known limitation (specs/054-e2e-container-coverage, research.md D7/tasks.md T009)...") with a statement of what the container leg now requires on the test repository and what the verification does when that requirement is unmet — no "known limitation" carve-out for the unset case — and, in the same edit, document the fixture maintainer credential as a setup prerequisite of the container leg specifically (not only of the unattended human gates), stating its least-privilege scope: Write collaborator on the test repository and nothing more (FR-013, FR-016; Acceptance Scenario 1).
- [ ] T024 [P] [US4] In `docs/architecture.md`: replace the container-mode leg's "Reporting" bullet's accepted-gap sentence (~lines 1281-1293, the sentence beginning "This narrows, but does not close, the overstatement risk...") with a statement of the two evidence checks (configuration and execution) and their prerequisite (FR-016; Acceptance Scenario 1).
- [ ] T025 [P] [US4] In `specs/054-e2e-container-coverage/spec.md`: replace FR-004's and FR-006's "Accepted gap" notes (FR-004 ~lines 260-266, FR-006 ~lines 279-284) with a pointer to `specs/067-e2e-container-image-evidence/contracts/container-evidence-outcomes.md` (FR-016; Acceptance Scenario 2).
- [ ] T026 [P] [US4] In `specs/054-e2e-container-coverage/contracts/e2e-container-coverage.md` §1: replace the "Unset behavior" accepted-gap paragraph with a pointer to `specs/067-e2e-container-image-evidence/contracts/container-evidence-outcomes.md` (FR-016; Acceptance Scenario 2).
- [ ] T027 [US4] Validate quickstart.md's Documentation check: `grep -ri "known limitation" docs/setup.md docs/architecture.md` and `grep -ri "accepted gap" specs/054-e2e-container-coverage/spec.md specs/054-e2e-container-coverage/contracts/e2e-container-coverage.md`, confirming zero matches referring to the unset container-image variable (FR-016, SC-007) — depends on T023, T024, T025, T026.
- [ ] T028 [US4] Confirm Acceptance Scenario 3 by reference to T011's structural gate half rather than a new mechanism: a future change that reintroduces an unguarded container-mode pass path fails that gate and names the unguarded path — depends on T011.

**Checkpoint**: No documentation or specification passage anywhere in the repository still describes the unset container image variable as an undetectable or accepted gap.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Repository-wide checks this CLAUDE.md and the Constitution require before any PR from this feature is proposed for merge.

- [ ] T029 [P] Confirm default-runner turns are unaffected (Acceptance Scenario 5, SC-008): T005's no-op branch and T007's `MODE == container`-only gating add no new `failing_check` value and no measurable duration change on a default-runner turn — depends on T005, T007.
- [ ] T030 Since this feature adds `if:` conditions to `.github/workflows/auto-release.yml` (T005's new gated step, T006's re-pointed `cleanup` guard), get a pass from the `review-step-gating` skill on that file's diff (CLAUDE.md requirement) — depends on T005, T006.
- [ ] T031 Run `python .github/scripts/run-local-gates.py` across every file this feature touched (CLAUDE.md's PR-time gate suite) and fix any failures — depends on T001-T030.
- [ ] T032 [P] Update research.md D4's status note (or add a short dated addendum) recording whichever signal T017 actually confirmed (`Initialize containers` in `steps[]`, or the job-log fallback), so the shipped behaviour and the plan-stage record agree — depends on T017.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: No dependency on Phase 1 completing first, but both should land before any workflow edit. BLOCKS all user stories.
- **User Stories (Phase 3-6)**: All depend on Foundational (Phase 2) completion.
  - US1 and US2 (both P1) share the same new steps and the same gate; US2's tasks are almost entirely validation of behaviour US1's implementation tasks (T005, T007) already produce via T004's classification and T002's decision script.
  - US3 (P2) depends only on US1's T005/T006 already existing (it validates a side effect of their placement, not new code).
  - US4 (P3) depends only on the feature existing in some form — its doc tasks can start once US1's core behaviour is stable enough to describe accurately, ideally after T016-T018's live proofs.
- **Polish (Phase 7)**: Depends on every phase above.

### User Story Dependencies

- **User Story 1 (P1)**: Depends on Foundational. No dependency on US2/US3/US4.
- **User Story 2 (P1)**: Depends on Foundational and on US1's T005/T007 existing as call sites to validate — ships with US1, not independently, per spec.md's own "It ships with User Story 1 or not at all."
- **User Story 3 (P2)**: Depends on Foundational and US1's T005/T006 only.
- **User Story 4 (P3)**: Depends on the feature's behaviour being implemented (ideally through T018) so the documentation it writes describes what actually shipped, not what was planned.

### Within Each User Story

- US1: decision script/classification (Foundational) → config-evidence step → cleanup re-pointing → execution-evidence read → single-pass-site confirmation → pass-verdict population → gate (structural, then executed-step, then self-test, then registration) → local gate run → live-proof validation.
- US2: entirely validation of US1's classification and gate fixtures, plus one confirmation read of the `report` job.
- US3: validation only, no new code.
- US4: five independent-file doc/spec edits → grep validation → gate cross-reference confirmation.

### Parallel Opportunities

- T002 (decision script) has no dependency on T003/T004 and can be written in parallel with them.
- Once Foundational is done, T023-T026 (US4's four doc/spec files) can all proceed in parallel with each other and with US1/US2/US3's work, though their content will read best once T016-T018 confirm actual behaviour.
- T029 and T032 (Polish) can run in parallel with each other once their dependencies land.

---

## Parallel Example: User Story 4 documentation

```bash
# Once the feature's behaviour is stable (after T018), all four doc/spec edits are independent files:
Task: "Replace docs/setup.md's known-limitation paragraph and add the credential-prerequisite note"
Task: "Replace docs/architecture.md's Reporting bullet's accepted-gap sentence"
Task: "Replace specs/054-e2e-container-coverage/spec.md's FR-004/FR-006 accepted-gap notes"
Task: "Replace specs/054-e2e-container-coverage/contracts/e2e-container-coverage.md §1's Unset behavior paragraph"
```

---

## Implementation Strategy

### MVP First (User Stories 1 and 2 — both P1)

Like `specs/054`'s own framing, US1 and US2 are jointly the minimum viable increment here: a detector that can be silently defeated by a revoked credential is the same defect this feature exists to remove, one layer up.

1. Complete Phase 1: Setup (baseline confirmation).
2. Complete Phase 2: Foundational (decision script, pin-comparison reuse, shared read-status classification) — CRITICAL, blocks every story.
3. Complete Phase 3: User Story 1 (both evidence steps, the gate, and the live proofs).
4. Complete Phase 4: User Story 2 (validate the fail-closed paths the same implementation already produces).
5. **STOP and VALIDATE**: T016-T018 and T019 against real dispatched runs, per SC-001/SC-002's explicit requirement.

### Incremental Delivery

1. Setup + Foundational → the shared decision-making machinery exists, nothing yet wired into `auto-release.yml`.
2. Add User Story 1 → the detection itself exists, proven by a new gate and live runs.
3. Add User Story 2 → prove the detection cannot be quietly defeated by a broken credential.
4. Add User Story 3 → confirm the cheap-failure property the placement in US1 already earned.
5. Add User Story 4 → the documentation and prior spec catch up with what actually shipped.

### Parallel Team Strategy

With two maintainers/agents (CLAUDE.md caps concurrent local agents at two for this repository):

1. Complete Setup + Foundational together first (T001-T004 are a short, largely sequential chain).
2. Once Foundational is done: one agent takes US1 (through its gate and live proofs); the other prepares US4's doc/spec edits in parallel, revising them once US1's live proofs (T016-T018) confirm actual behaviour, then picks up US2's validation tasks and US3.
3. Both converge on Phase 7 (Polish) once their stories are checkpointed.

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to specific user story for traceability.
- T007 carries a genuinely open implementation question (single test-repository run vs. every stage-workflow run this attempt drove) that research.md/data-model.md assumed rather than resolved — do not silently pick one without T017's live confirmation.
- T010's gate number is provisional at every stage before implementation; re-check `lint-workflows.yml` immediately before registering, since another in-flight spec may have already claimed the number research.md reserved.
- No published stage workflow or `.github/actions/**` composite action other than the one new `_shared/` decision script is touched by any task above (plan.md's Structure Decision) — the container leg's own reference-image and prerequisite-check mechanics from `specs/054` are unchanged.
- Commit after each task or logical group; stop at any checkpoint to validate a story independently.
