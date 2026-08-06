---

description: "Task list for Bind Pipeline Stages to a Deployment Environment"
---

# Tasks: Bind Pipeline Stages to a Deployment Environment

**Input**: Design documents from `/specs/031-stage-environment-binding/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/environment-binding.md, quickstart.md

**Tests**: Not requested — no automated test suite exists for any pipeline stage in this repository (plan.md's Testing section: `lint-workflows.yml`'s YAML-parse + `bash -n` static check, plus a pinned-`actionlint` run, are the only automated CI-adjacent checks). Validation is manual/scripted, via `quickstart.md`'s nine scenarios, folded into the relevant phase below. Every protection-rule scenario (required reviewer, wait timer, branch policy, deployment-record suppression) requires a scratch adopter repository per the spec's own Assumptions and is out of this repository's CI.

**Organization**: This feature is a uniform, mechanical change repeated identically across all ten of this repository's published `workflow_call`-only stage workflows (research.md D1: `intake`, `clarify`, `plan`, `tasks`, `implement`, `finalize`, `cleanup`, `rebase`, `watchdog`, `auto-update-spec-kit`) — 30 `jobs.<id>:` blocks total (confirmed by direct enumeration; plan.md's own "roughly 40" was a heuristic, deferred to this file for the exact count). Unlike `016-bedrock-support`, this feature adds no shared composite action and no preflight change (research.md D4/D6) — the entire mechanism is two new `workflow_call` inputs plus one job-level `environment:` mapping block, added unconditionally to every job in every file (research.md D2). Because that single block is what delivers the gate (US1), the verified no-op (US2), the deployment-record control (US3), and the per-job granularity (US4) all at once — they are not separable code paths — User Story 1 carries the full ten-file rollout (FR-001/FR-002/FR-004 apply identically to all ten regardless of story), and User Stories 2–4 are the verification passes that confirm each story's specific guarantee holds across the finished surface.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature (GitHub Actions reusable workflows only), no `src/`/`tests/` split (plan.md's Structure Decision). All file paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Resolve the one open verification item research.md flags before any wiring begins.

- [X] T001 Verify the pinned `actionlint` 1.7.7 (matching `release.yml` Gate 1a) accepts the job-level `environment:` mapping form and its `deployment` sub-key (research.md D8 — flagged, not resolved, in planning: `deployment` is not part of any GitHub-published schema this plan can cite). Run actionlint 1.7.7 against a scratch workflow file/job declaring `environment: {name: ${{ inputs.environment }}, deployment: ${{ inputs.environment-deployment }}}`. If it accepts the mapping cleanly, proceed with T003–T012 as written and note this in T013. If it rejects the `deployment` key, record the exact failure text and prepare an `-ignore` pattern for `release.yml` Gate 1a mirroring the existing `job_workflow_sha` precedent (research.md D8) — apply it in T013, in the same PR, per D8's stated fallback.

**Checkpoint**: the actionlint-acceptance question is answered — per-file wiring can proceed without discovering a lint failure only after all ten files are touched.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Fix the one piece of text every one of the ten per-file wiring tasks must reproduce identically.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 Fix the exact FR-013 traceability comment (contracts/environment-binding.md's "Traceability" section) that must precede every `environment:` block added in T003–T012, pointing back to the four empirically-verified GitHub behaviors this feature relies on (empty-name no-op, mapping-form expression binding, `deployment: false` suppression, create-on-reference) and the probe repository (`charlesguse/wc-env-probe`, verified 2026-08-05). Every subsequent per-file task reproduces this block verbatim, once per job:

  ```yaml
        # Empirically verified 2026-08-05 against GitHub-hosted runners
        # (charlesguse/wc-env-probe): empty name is a true no-op; mapping
        # form accepts an expression; deployment: false suppresses the
        # deployment record while keeping the gate; an unknown name is
        # created on reference. Not part of GitHub's published schema
        # (FR-013) — see contracts/environment-binding.md.
        environment:
          name: ${{ inputs.environment }}
          deployment: ${{ inputs.environment-deployment }}
  ```

**Checkpoint**: the exact block (comment + mapping) that every job in every file receives is fixed — per-file wiring (User Story 1) can now begin.

---

## Phase 3: User Story 1 - Gate an expensive stage behind a required reviewer (Priority: P1) 🎯 MVP

**Goal**: Every one of the ten published stages accepts `environment` (string, default `""`) and `environment-deployment` (boolean, default `true`) as `workflow_call` inputs, and every job in every stage file binds to the named environment via T002's block — so GitHub applies that environment's protection rules (required reviewer, wait timer, branch/tag policy, custom App rule) before any of that job's steps, including preflight and the agent step, ever run.

**Independent Test**: In a scratch adopter repository, create an environment with a required reviewer, pass its name to a stage (e.g. `plan.yml`), and observe that the stage's jobs pend for approval before any preflight or agent step runs, with no agent cost incurred while pending; on approval the stage proceeds normally (quickstart.md Scenarios 3–5, 7).

### Implementation for User Story 1

- [X] T003 [P] [US1] Wire `.github/workflows/intake.yml`: add `environment` (type `string`, default `""`) and `environment-deployment` (type `boolean`, default `true`) to the `workflow_call.inputs` block (alongside the existing `model`/`pipeline-repo`/`default-branch` inputs, FR-001/FR-002); add T002's block to the file's one job (`intake`).
- [X] T004 [P] [US1] Wire `.github/workflows/clarify.yml`: add the two `workflow_call` inputs; add T002's block to the file's one job (`clarify`).
- [X] T005 [P] [US1] Wire `.github/workflows/plan.yml`: add the two `workflow_call` inputs at the file level; add T002's block to both jobs (`resolve-spec`, `plan`) — uniformly, including the agent-free `resolve-spec` job (FR-004: no distinction between agent-running and agent-free jobs within a stage file).
- [X] T006 [P] [US1] Wire `.github/workflows/tasks.yml`: add the two `workflow_call` inputs at the file level; add T002's block to all three jobs (`resolve-spec`, `tasks`, `tasks-approved`) — including `tasks-approved`, the agent-free call this repo's own `wing-commander-4-tasks.yml` wrapper uses for its second, approved-mode invocation (the motivating multi-call case for User Story 4, verified in T015).
- [X] T007 [P] [US1] Wire `.github/workflows/implement.yml`: add the two `workflow_call` inputs; add T002's block to both jobs (`implement`, `stalled`).
- [X] T008 [P] [US1] Wire `.github/workflows/finalize.yml`: add the two `workflow_call` inputs; add T002's block to the file's one job (`finalize`).
- [X] T009 [P] [US1] Wire `.github/workflows/cleanup.yml`: add the two `workflow_call` inputs at the file level; add T002's block to all four jobs (`select`, `teardown-done`, `teardown-rejected`, `mark-stalled`).
- [X] T010 [P] [US1] Wire `.github/workflows/rebase.yml`: add the two `workflow_call` inputs at the file level; add T002's block to both jobs (`discover`, and the matrixed `rebase` job) — note the matrixed job needs the block once in its own job definition, not per matrix leg (`environment:` is evaluated per job, not per matrix instance).
- [X] T011 [P] [US1] Wire `.github/workflows/watchdog.yml`: add the two `workflow_call` inputs at the file level; add T002's block to all five jobs (`collect`, `diagnose`, `triage`, `act`, `report-unhandled-failure`).
- [X] T012 [P] [US1] Wire `.github/workflows/auto-update-spec-kit.yml` (research.md D1 — included as a published `workflow_call`-only stage despite predating the "nine stages" prose still in `docs/architecture.md` and the constitution): add the two `workflow_call` inputs at the file level; add T002's block to all nine jobs (`health-check`, `detect`, `settle`, `evaluate-path`, `prepare`, `verify`, `act`, `pr-merged`, `comment-reply`).

**Checkpoint**: User Story 1 is fully functional across all ten stages — every one of the 30 jobs binds to `${{ inputs.environment }}` with `deployment: ${{ inputs.environment-deployment }}`, satisfying FR-001, FR-002, FR-004, FR-005 (structurally, by job-attribute placement — research.md D4), FR-007, FR-011, and FR-013 by construction.

---

## Phase 4: User Story 2 - Existing adopters are unaffected when the input is unset (Priority: P1)

**Goal**: Confirm that leaving `environment` at its default (`""`) on any of the ten wired stages changes nothing about today's behavior — no environment applied, no gate, no deployment record, no phantom environment created (SC-001).

**Independent Test**: Run a stage with the environment input left at its default and confirm the run is identical to today (quickstart.md Scenario 1), and confirm the plumbing is uniform and complete across all ten files (quickstart.md Scenario 2 — the one scenario mechanically verifiable in this repository).

### Implementation for User Story 2

- [X] T013 [US2] Run quickstart.md Scenarios 1 and 2 against the ten files wired in T003–T012: grep `intake.yml`, `clarify.yml`, `plan.yml`, `tasks.yml`, `implement.yml`, `finalize.yml`, `cleanup.yml`, `rebase.yml`, `watchdog.yml`, `auto-update-spec-kit.yml` for `environment:`, `inputs.environment`, and `inputs.environment-deployment`, confirming every file declares both `workflow_call` inputs with the documented names/types/defaults and every one of the 30 jobs carries T002's identical block — no stage missing the surface, no job skipped (FR-001–FR-004). Run `.github/workflows/lint-workflows.yml`'s checks (YAML-parse + `bash -n`) over all ten changed files — must pass unchanged (SC-001). Run the pinned actionlint 1.7.7 over at least the 8 files `release.yml` Gate 1a already covers, applying T001's `-ignore` pattern if T001 found one was needed.

**Checkpoint**: User Stories 1 and 2 both hold across all ten stages — the zero-change guarantee is confirmed by static inspection everywhere this repository's CI can reach.

---

## Phase 5: User Story 3 - Keep the environment gate without cluttering the Deployments panel (Priority: P2)

**Goal**: Confirm `environment-deployment: false` keeps the environment's protection rules in force while suppressing the deployment record GitHub would otherwise create (FR-008), and that the default (`true`) keeps every protection-rule type — including custom App rules that require the deployment object — working out of the box (FR-002).

**Independent Test**: Bind a stage to an environment with a protection rule and disable the deployment record; confirm the gate still applies and no deployment record is created (quickstart.md Scenario 6 — manual, scratch repo).

### Implementation for User Story 3

- [X] T014 [US3] Confirm the `deployment: ${{ inputs.environment-deployment }}` sub-key (FR-008, contracts/environment-binding.md's "Deployment-record suppression" section) is correctly wired — not hardcoded to `true` or `false` — in every one of the 30 job blocks added in T003–T012, by re-scoping T013's grep to `inputs.environment-deployment` specifically. Record in the PR body that live confirmation of the gate persisting while the deployment record is suppressed (quickstart.md Scenario 6) requires the scratch adopter repository per the spec's Assumptions, and remains a manual verification step this repository's CI cannot exercise.

**Checkpoint**: User Story 3's mechanism is confirmed correctly wired everywhere User Story 1 landed it; its live behavior is deferred to the same scratch-repo pass as User Story 1's protection-rule scenarios.

---

## Phase 6: User Story 4 - Per-job granularity from the wrapper (Priority: P2)

**Goal**: Confirm binding applies uniformly to every job in a stage file, with no hidden per-job selector (FR-004, User Story 4 acceptance scenario 2) — so a wrapper that calls a stage more than once (the motivating case: `tasks.yml`, called once with `mode: generate` and once with `mode: approved`) achieves per-call granularity by setting `environment` on only the calls it wants gated, with no stage-side change needed (research.md D7).

**Independent Test**: In a wrapper that calls a stage twice, pass the environment on one call and omit it on the other; confirm only the first call's jobs bind to the environment (quickstart.md Scenario 8).

### Implementation for User Story 4

- [X] T015 [US4] Confirm per-job uniformity within every multi-job stage file wired in T005–T007 and T009–T012 (`plan.yml`, `tasks.yml`, `implement.yml`, `cleanup.yml`, `rebase.yml`, `watchdog.yml`, `auto-update-spec-kit.yml`): every job in each file carries T002's identical block, with no `if:` or other selector distinguishing agent-running jobs from agent-free ones. Desk-check that this repository's own `wing-commander-4-tasks.yml` wrapper's existing two-call shape (`mode: generate` then `mode: approved`) already gives an adopter the granularity User Story 4 describes — setting `environment` on the `generate` call only — with no wrapper change required (research.md D7). Confirm `wing-commander-4-tasks.yml` itself is left unmodified by this feature, per plan.md's Project Structure note (no environment configured in this repository's own Settings yet — constitution I bootstrap-phase allowance).

**Checkpoint**: All four user stories are independently confirmed across the finished ten-file surface — the mechanically verifiable portion of quickstart.md's scenario set (1, 2, 8) passes; the scratch-repo scenarios (3–7, 9) remain the acceptance vehicle for live protection-rule behavior.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Adopter-facing documentation (FR-012), the shared-contract-doc update, a final traceability sweep, and the full quickstart walkthrough.

- [X] T016 [P] Add a "Deployment environments" section to `docs/adoption.md` (implementation-stage edit per plan.md's Project Structure) covering all five FR-012 caveats: the per-iteration (per-run) approval behavior and the once-per-feature-stage workaround; the concurrency-slot interaction (a pending job holds its per-spec concurrency slot); the environment-secrets non-goal and why it fails silently (kebab-case secret names, wrapper-resolved `secrets.*` in the environment-less calling job); the create-on-reference caveat (a typo yields a new, unprotected, ungated environment); and the private-repo paid-plan (Team/Pro) prerequisite. Add a short "Stage reference" intro bullet pointing adopters here.
- [X] T017 [P] Add a private-repo Team/Pro prerequisite note to `docs/setup.md`'s repository-configuration section, cross-referencing `docs/adoption.md`'s new "Deployment environments" section for the full setup.
- [X] T018 [P] (Optional, per plan.md) Add a note to `docs/architecture.md` recording the Principle VII deviation this feature registers (the gate lives in the stage, not the wrapper, because `jobs.<job_id>.environment` is illegal on a job whose body is `uses: <reusable workflow>`), joining the existing watchdog `vars.*` exception paragraph — and optionally correct the stale "workflow_call — nine of them today" count to ten (research.md D1's documentation-drift finding; not required by this feature's scope but noted here to avoid rediscovery).
- [X] T019 [P] Add `environment` and `environment-deployment` rows to `specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s "Common inputs" table, alongside `pipeline-repo`/`default-branch`/`use-bedrock` — the same convention `016-bedrock-support` followed for its own common inputs.
- [X] T020 Grep all ten stage files for the FR-013 traceability comment fixed in T002, confirming it precedes every one of the 30 `environment:` blocks — no block added without its comment. Distinct from T013's broader plumbing check: this pass verifies comment presence specifically, so a future silent upstream change to any of the four empirical behaviors stays detectable (FR-013).
- [X] T021 Walk quickstart.md's full scenario set (1–9) end-to-end against the finished workflow files, recording in the PR body which were exercised live (a scratch public adopter repository, per the spec's Assumptions) versus desk-checked only. Scenarios 1, 2, and 8 are verifiable in this repository alone (T013, T015); Scenarios 3, 4, 5, 6, 7, and 9 require the scratch adopter repository and remain the acceptance vehicle for GitHub's own protection-rule behavior, not something this repository's CI exercises.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 only loosely (T002 does not require T001's answer to be fixed, but both should land before any per-file task starts) — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational (T003–T012 each reproduce T002's exact block). No dependency on other stories.
- **User Story 2 (Phase 4)**: Depends on User Story 1 (T013 greps/lints the files T003–T012 produced).
- **User Story 3 (Phase 5)**: Depends on User Story 1 (T014 re-scopes T013's grep to the same finished files).
- **User Story 4 (Phase 6)**: Depends on User Story 1 (T015 desk-checks the same finished files for per-job uniformity).
- **Polish (Phase 7)**: T016–T019 depend on User Story 1 being complete (they document the finished, consistent surface); T020 depends on T002 (the comment it greps for) and T003–T012; T021 depends on all prior phases.

### User Story Dependencies

- **User Story 1 (P1)**: Independently implementable and testable after Foundational — the only story with no dependency on another story's tasks, and the one that produces every file the other three stories verify.
- **User Story 2 (P1)**: Verifies User Story 1's zero-change guarantee; independently testable once its own phase completes (quickstart.md Scenarios 1–2 across all ten stages).
- **User Story 3 (P2)**: Verifies User Story 1's deployment-record control specifically; independently testable once its own phase completes (grep scoped to `environment-deployment`; live confirmation is scratch-repo-only).
- **User Story 4 (P2)**: Verifies User Story 1's per-job uniformity and the existing wrapper's two-call granularity; independently testable once its own phase completes.

### Within Each Story

- Per-file wiring (T003–T012) has no internal ordering — all ten files are independent of each other.
- Cross-file verification (T013, T014, T015) each depend on all ten files being wired, but not on each other — they can run in any order, or in parallel, once T003–T012 are complete.
- Documentation (T016–T019) depends on the finished, verified surface (User Story 1, ideally after T013 confirms consistency) so it describes what actually shipped.

### Parallel Opportunities

- T003 through T012 each touch a distinct stage workflow file and can all run in parallel once Foundational (Phase 2) is done.
- T013, T014, and T015 are all read-only verification passes over the same finished files and can run in parallel with each other once T003–T012 are complete.
- T016, T017, T018, and T019 touch four different documentation/contract files and can all run in parallel with each other, and with T020, once User Story 1 is confirmed (T013).

---

## Parallel Example: User Story 1 stage wiring

```bash
# Launch together — ten different workflow files, same mechanical change:
Task: "Wire .github/workflows/intake.yml with environment/environment-deployment"
Task: "Wire .github/workflows/clarify.yml with environment/environment-deployment"
Task: "Wire .github/workflows/plan.yml with environment/environment-deployment (two jobs)"
Task: "Wire .github/workflows/tasks.yml with environment/environment-deployment (three jobs)"
Task: "Wire .github/workflows/implement.yml with environment/environment-deployment (two jobs)"
Task: "Wire .github/workflows/finalize.yml with environment/environment-deployment"
Task: "Wire .github/workflows/cleanup.yml with environment/environment-deployment (four jobs)"
Task: "Wire .github/workflows/rebase.yml with environment/environment-deployment (two jobs)"
Task: "Wire .github/workflows/watchdog.yml with environment/environment-deployment (five jobs)"
Task: "Wire .github/workflows/auto-update-spec-kit.yml with environment/environment-deployment (nine jobs)"
```

## Parallel Example: Cross-file verification (User Stories 2–4)

```bash
# Launch together — three independent read-only passes over the same finished files:
Task: "Grep/lint/actionlint all ten stage files for consistent plumbing (US2)"
Task: "Grep all ten stage files for correct environment-deployment wiring (US3)"
Task: "Desk-check per-job uniformity in every multi-job stage file (US4)"
```

## Parallel Example: Polish Documentation

```bash
# Launch together — four different doc/contract files:
Task: "Add a Deployment environments section to docs/adoption.md"
Task: "Add a private-repo Team/Pro prerequisite note to docs/setup.md"
Task: "Add a Principle VII deviation note to docs/architecture.md"
Task: "Add environment/environment-deployment rows to specs/010-reusable-pipeline/contracts/stage-interfaces.md"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (confirm actionlint acceptance)
2. Complete Phase 2: Foundational (fix the exact block text)
3. Complete Phase 3: User Story 1 (all ten stages wired)
4. **STOP and VALIDATE**: Run quickstart.md Scenario 2 (the cross-file consistency grep) against all ten files
5. This alone delivers the entire adopter-facing capability — every remaining task is verification or documentation of what Phase 3 already built

### Incremental Delivery

1. Setup + Foundational → the exact block text is fixed
2. Add User Story 1 → all ten stages wired → mergeable increment (MVP) — the gate exists everywhere FR-001 requires it
3. Add User Story 2 → static zero-change guarantee confirmed → mergeable increment (confidence before declaring done)
4. Add User Story 3 → deployment-record control confirmed wired correctly → mergeable increment
5. Add User Story 4 → per-job uniformity and existing-wrapper granularity confirmed → mergeable increment
6. Polish → documentation, final traceability sweep, and the full quickstart walkthrough (recording what remains scratch-repo-only)

### Why User Stories 2–4 are verification-only, not additional wiring

Research.md D2 establishes that a single unconditional block — the same `environment:` mapping, added to every job — is what simultaneously delivers the gate (US1), the verified no-op (US2, via GitHub's own empty-name no-op behavior), the deployment-record control (US3, via the `deployment` sub-key), and the per-job granularity (US4, via per-job uniformity plus the wrapper's own multi-call shape). There is no second code path for any of the three later stories to add — each one's "Implementation" is confirming, by inspection, that the single surface User Story 1 built actually has the property that story claims. This mirrors research.md D4/D5/D7's own posture ("confirm an existing structural guarantee rather than build a new mechanism") applied to task planning, not just to the workflow YAML itself.
