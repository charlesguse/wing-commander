# Tasks: Container-Mode Coverage in End-to-End Release Verification

**Input**: Design documents from `/specs/054-e2e-container-coverage/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/e2e-container-coverage.md, quickstart.md

**Tests**: This feature has no application test suite — its "tests" are the existing gate suite (`.github/scripts/run-local-gates.py`), a new Gate 62 with its own `--self-test` fixture, and the live proofs quickstart.md's scenarios and SC-002 require against a real dispatched run. Those live-proof and quickstart-validation tasks are included below as their own checklist items, per plan.md's Testing section.

**Organization**: Tasks are grouped by user story (spec.md) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- File paths are exact and repository-relative

## Path Conventions

Single-project GitHub Actions pipeline (plan.md's Structure Decision) — no `src/`/`tests/` split. All touched paths live under `.github/` (workflows, one new Dockerfile, one new gate script) and `docs/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Build the new, standalone artifacts the container leg needs to have anything to point at. Neither task touches `auto-release.yml`.

- [X] T001 [P] Create the minimal Dockerfile at `.github/docker/e2e-reference-image/Dockerfile`, installing exactly the tools named in `.github/scripts/required-tools.txt` (`git`, `gh`, `jq`, `curl`, `python3`, `bash`, `node`, `timeout` via coreutils) on a minimal base image (research.md D5, FR-016)
- [X] T002 [P] Create `.github/workflows/wing-commander-e2e-reference-image.yml`: `on: push` (paths `.github/docker/e2e-reference-image/**`, `.github/scripts/required-tools.txt`) plus `workflow_dispatch`, no `workflow_call` trigger; builds and pushes `ghcr.io/charlesguse/wing-commander-e2e-image` tagged `:latest` and `:<commit-sha>` via `docker/login-action` + `docker/build-push-action`, and prints the resulting digest in the job summary for a maintainer to copy by hand — this workflow never writes the test repository's `WING_COMMANDER_CONTAINER_IMAGE` variable itself (research.md D5, FR-016, FR-019, contracts/e2e-container-coverage.md §4)

**Checkpoint**: The reference image can be built and published; nothing yet consumes it.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The core `auto-release.yml` mechanics every user story below depends on — deriving which mode a run exercises, keeping the two legs from bleeding into each other, and making that mode visible in the verdict and report. No user story is independently testable until this phase is done.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Add a `mode` step near the top of the `verify-e2e` job in `.github/workflows/auto-release.yml` (before the existing `config` step): compute `mode` from UTC day-of-year parity (`date -u +%j`; even day-of-year → `default-runner`, odd → `container`), written as a step output; no value is persisted anywhere (research.md D1, FR-018, FR-020)
- [X] T004 In the `scaffold` step of `.github/workflows/auto-release.yml`, add a rewrite that runs only when `steps.mode.outputs.mode == 'default-runner'`: blank every copied wrapper file's container passthrough (`sed -i "s/vars\.WING_COMMANDER_CONTAINER_IMAGE || ''/''/"` across the eight copied `wing-commander-*.yml` files, alongside the existing `uses:`/branch-name `sed` rewrites), so a permanently-configured test-repository variable cannot leak container mode into a default-runner-turn run; no rewrite on a container-mode turn, since the copied wrapper's existing read of `vars.WING_COMMANDER_CONTAINER_IMAGE` already does the work (research.md D2, FR-002, FR-011, contracts/e2e-container-coverage.md §1) — depends on T003
- [X] T005 Extend every verdict-emitting `jq -n` call in the `verify-e2e` job of `.github/workflows/auto-release.yml` (the `config`, `reachable`, `reset`, `speckit-version`, `scaffold`, `kickoff`, and `poll` steps) to include `mode: $mode` (sourced from `steps.mode.outputs.mode`), threaded through exactly as `verified_head` already is today; also add `container_image_configured`, defaulted `true` whenever `mode == "container"` and omitted otherwise (User Story 2's tasks below are what actually falsify it) (research.md D9, data-model.md "Verdict", FR-003, FR-020, contracts/e2e-container-coverage.md §2) — depends on T003
- [X] T006 In the `report` job of `.github/workflows/auto-release.yml`, surface `mode` (and `paused`, once T012 exists) alongside `failing_check` in both the `write_failure_body` builder and the success-path `GITHUB_STEP_SUMMARY` line, so a passing run also states which mode it exercised — not only a failing one (FR-003, FR-007, FR-020, User Story 1 Acceptance Scenario 4) — depends on T005

**Checkpoint**: Every `verify-e2e` run now derives and records a mode; the two legs cannot bleed into each other. User story work can begin.

---

## Phase 3: User Story 1 - Container-mode regressions are caught before release (Priority: P1) 🎯 MVP (with US2)

**Goal**: A scheduled verification whose turn is container mode carries a full feature end to end with every stage job executing inside the reference image, and a defect in that path blocks the release.

**Independent Test**: Run the verification against a known-good head and observe a passing verdict recording container mode as exercised; then run it against a head with a deliberately broken container path and observe the release blocked with a verdict naming the container-mode failure.

- [ ] T007 [US1] Against a known-good head, dispatch `auto-release.yml` on a day whose derived mode is `container` (quickstart.md Scenario A) and confirm: `outcome: "pass"`, `mode: "container"`, every intermediate stage label present in the test repository's kickoff-issue timeline, and that the release proceeds — record the run URL as evidence (SC-001, SC-002 baseline, Acceptance Scenario 1) — depends on T001, T002, T003, T004, T005, T006
- [ ] T008 [US1] On a branch, introduce a deliberate container-path defect (e.g. a `run:` step inside a published stage's `container:` job missing `shell: bash` — the exact defect class the `container-shell-safety` skill exists to catch), point a manually dispatched `auto-release.yml` run at it with mode forced to `container`, and confirm the run reports a `fail-*` outcome naming the broken stage with `mode: "container"`, and that `dispatch-release` does not run (quickstart.md Scenario B, SC-002's required live proof — plan.md's Testing section requires this be demonstrated against a real run before the feature is considered complete; record the run URL as evidence on issue #364, Acceptance Scenario 2) — depends on T007

**Checkpoint**: Container-mode coverage exists and is proven to both pass and block a release.

---

## Phase 4: User Story 2 - A pass never overstates what was verified (Priority: P1) 🎯 MVP (with US1)

**Goal**: The verification cannot report an unqualified pass for a run in which container mode was configured to run but never actually exercised the image.

**Independent Test**: Point the verification at an unresolvable image reference and confirm the run produces a named, non-pass verdict distinguishing "the image could not be obtained" from "the pipeline failed inside the image."

- [ ] T009 [US2] Design and implement how `verify-e2e` (in `.github/workflows/auto-release.yml`) distinguishes "container mode was configured to run but the image was never resolved/pulled/authorized" from "the pipeline failed inside a correctly-resolved image," without granting the test-repository-scoped token any new permission to read `WING_COMMANDER_CONTAINER_IMAGE` itself (FR-017 forbids this). **This is an open design question research.md D7 explicitly flags rather than resolves**: if the only viable signal requires reading the test repository's Actions run/job data, that is not among the App installation permissions this repository currently documents (Contents/Issues/Pull requests only — `docs/setup.md` lines 24-26). If so, document the new `Actions: read` installation permission as a one-time maintainer step in `docs/setup.md` and comment the reading on issue #364 for owner confirmation before finalizing it, per D7's own instruction, rather than adding it silently — depends on T005
- [ ] T010 [US2] Using the mechanism from T009, set `container_image_configured: false` and `outcome: "fail-infra"` with a `failing_check` naming the unresolved image whenever a container-mode turn's image was never configured, could not be pulled, or had its credentials rejected, and point `evidence_url` at the container leg's `verify-image-prerequisites` job run in the test repository rather than only the kickoff-issue URL (research.md D7, FR-004, FR-006, contracts/e2e-container-coverage.md §1 "Unset behavior") — depends on T009
- [ ] T011 [US2] Validate quickstart.md Scenario C: unset `WING_COMMANDER_CONTAINER_IMAGE` on the test repository, dispatch `auto-release.yml` on a container-mode-derived day, and confirm `outcome: "fail-infra"`, `mode: "container"`, `container_image_configured: false`, and `failing_check` naming the unset variable — never `outcome: "pass"` (Acceptance Scenario 1) — depends on T010

**Checkpoint**: A container-mode run that never actually entered the image cannot be mistaken for a pass.

---

## Phase 5: User Story 3 - Coverage that stays affordable and unblockable (Priority: P2)

**Goal**: The maintainer can pause the container leg independently of auto-release as a whole, and the added coverage stays within today's wall-clock and concurrency guarantees.

**Independent Test**: Set the container-mode pause control and confirm scheduled runs whose turn would have been container mode instead run the default-runner leg, report container mode as not exercised, and still reach a release decision.

- [X] T012 [US3] Extend the `mode` step in `.github/workflows/auto-release.yml` to read `vars.WING_COMMANDER_AUTO_RELEASE_E2E_CONTAINER_PAUSED` immediately after computing day-of-year parity; when it is `'true'`, force `mode` to `default-runner` regardless of parity and set a `paused` output to `true` (it is never `true` on an already-even-day/default-runner result) (research.md D3, FR-009) — depends on T003
- [X] T013 [US3] Thread the `paused` output from T012 through the verdict schema (T005) and the `report` job (T006) so a paused run's report states "container mode not exercised: paused" rather than a plain pass (data-model.md "Execution mode" `paused` field, FR-009 Acceptance Scenario 1) — depends on T005, T006, T012
- [X] T014 [US3] Add a new row for `WING_COMMANDER_AUTO_RELEASE_E2E_CONTAINER_PAUSED` to the repository-variable table in `docs/setup.md`, mirroring the existing `WING_COMMANDER_AUTO_RELEASE_PAUSED` row (line 125): default unset, `'true'` = kill switch scoped to the container leg only, independent of the global pause (contracts/e2e-container-coverage.md §1)
- [X] T015 [P] [US3] Add a comment on the `concurrency:` block of `.github/workflows/auto-release.yml` (`group: wing-commander-auto-release`, `cancel-in-progress: false`) noting that this existing group is also what guarantees FR-008's leg isolation, so it must never be loosened — documentation only, no functional change (research.md D2 "Leg isolation")
- [ ] T016 [US3] Validate quickstart.md Scenario D: set `WING_COMMANDER_AUTO_RELEASE_E2E_CONTAINER_PAUSED` to `true`, dispatch `auto-release.yml` on a day whose parity would otherwise select `container`, and confirm the default-runner leg ran instead, `mode: "default-runner"`, `paused: true`, and `dispatch-release` still ran (Acceptance Scenario 1) — depends on T012, T013
- [ ] T017 [US3] Confirm FR-010/SC-005 by observation, not new code: a container-mode run either completes or times out into `outcome: "fail-timeout"` within the unchanged 150-minute `verify-e2e` job timeout and the existing `POLL_BUDGET_SECONDS` budget, since research.md D8 establishes no new timeout mechanism is needed — record the observation from a real run (Acceptance Scenario 2/3) — depends on T007 or T008 already having produced a real run

**Checkpoint**: The container leg is pausable without pausing auto-release, and its time bound is confirmed unchanged.

---

## Phase 6: User Story 4 - The reference image has a named owner and upkeep path (Priority: P2)

**Goal**: A change to the canonical required-tool list that the reference image does not yet satisfy is caught by a gate before it reaches the default branch, and documentation states who owns the image and why it exists.

**Independent Test**: Add a new entry to the canonical required-tool list and confirm the documented upkeep path names who updates the image and what the verification does in the interval.

- [X] T018 [P] [US4] Write `.github/scripts/verify-gate-62.py`: `docker build` the reference image from `.github/docker/e2e-reference-image/Dockerfile` locally (no push), then run the same `docker run --rm --entrypoint sh "$IMAGE" -c 'for t in $REQUIRED_TOOLS; do command -v "$t" || echo "missing:$t"; done'` check every stage's `verify-image-prerequisites` job runs, comparing against `.github/scripts/required-tools.txt`, naming every missing tool at once rather than stopping at the first (research.md D6, FR-019, SC-007, contracts/e2e-container-coverage.md §3) — depends on T001
- [X] T019 [US4] Add a `--self-test` mode to `.github/scripts/verify-gate-62.py` (matching the `--self-test` convention Gates 42-61 use, e.g. `.github/scripts/verify-spec-meta-single-home.py`), backed by a checked-in fixture that deliberately drifts the Dockerfile/tool list from each other, proving Gate 62's failure branch actually fails on its own subject (plan.md Testing section, Constitution VIII) — depends on T018
- [X] T020 [US4] Register Gate 62 in `.github/workflows/lint-workflows.yml`: a `python3 .github/scripts/verify-gate-62.py` step and a `python3 .github/scripts/verify-gate-62.py --self-test` step, unconditional (no path filter, matching every other gate in this file — no gate here is currently path-filtered), following Gate 61's registration shape at line 3456 so `run-local-gates.py` and `verify-gate-wiring.py` pick it up automatically (contracts/e2e-container-coverage.md §3) — depends on T019
- [X] T021 [P] [US4] Add a new subsection to `docs/adoption.md` under "Runners and container images" (after the private-registry-credentials guidance, around line 856) stating the reference image's provenance — built and published by this repository to `ghcr.io/charlesguse/wing-commander-e2e-image`, who is responsible for updating it, that a `.github/scripts/required-tools.txt` change is the update trigger, and that it exists for this repository's own verification rather than as a supported image for adopters (FR-013, Acceptance Scenario 3)
- [X] T022 [P] [US4] Extend the existing `WING_COMMANDER_CONTAINER_IMAGE`/`WING_COMMANDER_CONTAINER_REGISTRY_USERNAME`/`_PASSWORD` rows in `docs/setup.md` (lines 57-58, 123) with a note that, when set on the end-to-end test repository, these now also configure the `auto-release.yml` container leg
- [X] T023 [P] [US4] Add a short new subsection to `docs/architecture.md` (near "Private-image dogfood", line 1091) describing the alternating container/default-runner leg in `auto-release.yml`'s flow: how the mode is derived (research.md D1), the pause control (D3), and where the reference image comes from (D5)
- [X] T024 [US4] Validate quickstart.md Scenario E: locally add an entry to `.github/scripts/required-tools.txt` without updating `.github/docker/e2e-reference-image/Dockerfile`, run `python3 .github/scripts/run-local-gates.py`, and confirm Gate 62 fails naming the missing tool (SC-008) — depends on T020

  Validated 2026-09-17: added `gate62-t024-scratch-fixture-tool` to
  required-tools.txt, ran `python3 .github/scripts/run-local-gates.py
  verify-gate-62.py`, confirmed both the gate and its self-test failed
  naming exactly that tool, then reverted the file (confirmed clean via
  `git diff`).

**Checkpoint**: Drift between the required-tool list and the reference image cannot reach the default branch unnoticed, and the image's ownership is documented.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Repository-wide checks this CLAUDE.md and the Constitution require before any PR from this feature is proposed for merge.

- [X] T025 Run `python3 .github/scripts/run-local-gates.py` across every file this feature touched and fix any failures — the PR-time gate suite CLAUDE.md requires before pushing — depends on T001-T024

  Ran 2026-09-17: found `verify-auto-release-report.py` failing because
  the new "(mode: ...)" text on the success-path summary line broke its
  exact-string scenario assertions. Fixed by giving the `PASS`/
  `WRONG_OUTPUT` fixtures a `mode` field, updating the two affected
  `summary_contains` strings, and adding a new paused-turn scenario
  covering T013's annotation. Full suite: 93/93 passed.
- [X] T026 Since this feature adds `if:` conditions to `.github/workflows/auto-release.yml` (T003's mode step, T004's off-turn rewrite, T012's pause override), get a pass from the `review-step-gating` skill on that file's diff (CLAUDE.md requirement) — depends on T003, T004, T012

  Ran 2026-09-17: as implemented, T003/T004/T012 turned out not to add
  any YAML-level `if:` or `continue-on-error:` at all — the mode step
  runs unconditionally with no gating, and the off-turn/pause logic is a
  plain bash `if` inside existing `run:` blocks, invisible to skip
  propagation. Confirmed via `git diff` (no added `if:`/`continue-on-error`
  lines in this file) and Gate 24 (deterministic tolerate/strand check),
  which passes. The skill's own `stranded-steps.py` helper is outside
  this run's permitted command set, so this was confirmed by direct diff
  inspection instead of running it.
- [ ] T027 Validate quickstart.md Scenario F: cancel a scheduled `auto-release.yml` run mid-flight, then dispatch (or wait for) the next run, and confirm its `mode` step still resolves purely from that run's own calendar date, independent of the cancelled run's outcome (Edge Case: "the alternation loses its place") — depends on T003
- [X] T028 [P] Update `.github/scripts/required-tools.txt`'s header comment to name Gate 62 as a third consumer alongside the existing two (each stage's embedded `REQUIRED_TOOLS=` list, Gate 23's textual drift check), matching the file's own "must stay in agreement structurally, not by convention" framing (data-model.md "Required-tool list") — depends on T020

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: No dependency on Phase 1's artifacts existing yet (the `mode`/verdict/report wiring doesn't need the image to be built) — but T007 (US1's live proof) needs Phase 1 done. BLOCKS all user stories.
- **User Stories (Phase 3-6)**: All depend on Foundational (Phase 2) completion.
  - US1 and US2 (both P1) additionally depend on Phase 1 (T001, T002) for their live-proof tasks to have a real image to point at.
  - US3 and US4 (both P2) can proceed in parallel with US1/US2 once Phase 2 is done.
- **Polish (Phase 7)**: Depends on every phase above.

### User Story Dependencies

- **User Story 1 (P1)**: Depends on Foundational + Phase 1 (needs a real image for its live proof). No dependency on US2/US3/US4.
- **User Story 2 (P1)**: Depends on Foundational. Independently testable from US1, though its live-proof task (T011) is more convincing once US1's T007 has already shown a passing container-mode run.
- **User Story 3 (P2)**: Depends on Foundational only (T012 extends the same `mode` step T003 created).
- **User Story 4 (P2)**: Depends on Phase 1 (T001) only — no dependency on Foundational or the other stories.

### Within Each User Story

- US1/US2: implementation before live-proof validation.
- US3: mode/verdict extension before docs before live-proof validation.
- US4: gate script before self-test before registration before docs before quickstart validation.

### Parallel Opportunities

- T001 and T002 (Phase 1) run in parallel — different files, no shared dependency.
- Once Phase 2 (T003-T006) is done, US3's T015 and all of US4's doc tasks (T021-T023) and gate-script start (T018) can run in parallel with US1/US2's work.
- T028 (Polish) can run in parallel with T025-T027 once T020 lands.

---

## Parallel Example: Setup

```bash
# Launch both Setup tasks together — different files, no shared dependency:
Task: "Create the minimal Dockerfile at .github/docker/e2e-reference-image/Dockerfile"
Task: "Create .github/workflows/wing-commander-e2e-reference-image.yml"
```

## Parallel Example: User Story 4 documentation

```bash
# Once Gate 62 is registered (T020), all three doc tasks are independent files:
Task: "Add reference-image provenance subsection to docs/adoption.md"
Task: "Extend the container-image/secrets rows in docs/setup.md"
Task: "Add the alternating-leg subsection to docs/architecture.md"
```

---

## Implementation Strategy

### MVP First (User Stories 1 and 2 — both P1)

Unlike a single-P1-story MVP, this spec's own priority framing makes US1 and US2 jointly the minimum viable increment: "This is the entire point of the feature... this story is the coverage" (US1) and "Equal to P1 because the failure mode it prevents is the one this feature exists to correct" (US2). A pass that could still silently overstate coverage is not shippable coverage.

1. Complete Phase 1: Setup (reference image + publish workflow).
2. Complete Phase 2: Foundational (mode derivation, off-turn suppression, verdict/report wiring) — CRITICAL, blocks every story.
3. Complete Phase 3: User Story 1 (live proof of a pass and a caught defect).
4. Complete Phase 4: User Story 2 (live proof a mis-configured image cannot pass).
5. **STOP and VALIDATE**: both live-proof pairs (T007/T008, T011) against real dispatched runs, per SC-002's explicit requirement.

### Incremental Delivery

1. Setup + Foundational → mode-aware verification exists, nothing yet proven live.
2. Add User Story 1 → prove a pass and a caught defect → the coverage itself exists.
3. Add User Story 2 → prove a misconfigured image cannot pass → the coverage cannot lie.
4. Add User Story 3 → pause control + budget confirmation → the coverage is operable.
5. Add User Story 4 → Gate 62 + docs → the coverage stays maintained rather than rotting.

### Parallel Team Strategy

With two maintainers/agents (CLAUDE.md caps concurrent local agents at two for this repository):

1. Complete Setup + Foundational together first (T001-T006 are a short, sequential chain).
2. Once Foundational is done: one agent takes US1 → US2 (they share the same live-proof dispatched runs and verdict fields); the other takes US3 and US4 in parallel (independent files, independent of US1/US2's runtime behavior).
3. Both converge on Phase 7 (Polish) once their stories are checkpointed.

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to specific user story for traceability.
- T009 is a genuinely open design question research.md D7 flags rather than resolves — do not silently add a new App installation permission; comment on issue #364 if owner confirmation is needed before finalizing the mechanism.
- No published stage workflow (`intake.yml` … `cleanup.yml`, `rebase.yml`) or `.github/actions/**` composite action is touched by any task above — research.md D2 established the existing `container-image`/registry-credential passthrough is sufficient as-is.
- Commit after each task or logical group; stop at any checkpoint to validate a story independently.
