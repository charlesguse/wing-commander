---

description: "Task list for End-to-End Verification Tier That Actually Verifies the Candidate"
---

# Tasks: End-to-End Verification Tier That Actually Verifies the Candidate

**Input**: Design documents from `/specs/034-e2e-verification-tier/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/e2e-verification-tier.md, quickstart.md

**Tests**: Requested — FR-015/FR-020 and User Story 4 require the existing executable scenario harness (`.github/scripts/auto-update-spec-kit-tests/`, from specs/027 #156) to assert every pass/fail path of this feature deterministically, without live agent runs or real `gh repo create`/`delete` calls. Harness tasks are folded into each user-story phase (the story that introduces a behavior also gets the harness assertion for it), not deferred to a separate testing phase.

**Organization**: This feature's footprint is two modified workflow files (`.github/workflows/auto-update-spec-kit.yml`, `.github/workflows/wing-commander-auto-update-spec-kit.yml`), three modified test-harness files (`t4_verify.sh`, `gh_stub.py`, `t7_gating.py`) plus its `README.md`, and one out-of-tree doc correction (`specs/027-auto-update-spec-kit/quickstart.md`, FR-016). No new workflow file, no new source directory (plan.md's Structure Decision). Because most tasks edit `auto-update-spec-kit.yml`, `[P]` is used sparingly — only for tasks touching genuinely different files.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature, no `src/`/`tests/` split. All file paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Add the new `workflow_call` inputs the rest of this feature depends on, following the exact pattern the existing `model` input already establishes.

- [X] T001 In `.github/workflows/auto-update-spec-kit.yml`, add `e2e-stage-model` (`type: string`, `required: false`, `default: claude-sonnet-5`) and `e2e-stage-max-turns` (`type: string`, `required: false`, `default: "20"`) to the `workflow_call.inputs` block (mirroring the existing `model` input at lines 77-81). In `.github/workflows/wing-commander-auto-update-spec-kit.yml`, thread both from the wrapper the same way `model` already is: `e2e-stage-model: ${{ vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_STAGE_MODEL || 'claude-sonnet-5' }}` and `e2e-stage-max-turns: ${{ vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_STAGE_MAX_TURNS || '20' }}` (research.md's model-tiering decision; constitution VI's `WING_COMMANDER_<PURPOSE>_<KNOB>` naming convention).

**Checkpoint**: The reusable stage accepts the two new inputs; the wrapper resolves them from repo variables with the documented defaults.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Give the harness the ability to record scratch-repository state, and wire the new `e2e-stage` job's empty skeleton into `verify`'s dependency graph — the scaffold every user story's own logic attaches to.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Extend `.github/scripts/auto-update-spec-kit-tests/gh_stub.py` with `gh repo create`, `gh repo delete`, and `gh repo list` handlers (research.md's "test-harness extensions" decision). Add a `repos` dict to the state shape (`{"NAME": {"owner": .., "deleted": bool}}`, included in `load()`'s `s.setdefault(...)` calls alongside `issues`/`prs`/`labels`). `repo create OWNER/NAME [--private] [--clone ...] [...]`: records the repo, idempotent (a second create for an already-present, non-deleted name is a no-op success). `repo delete OWNER/NAME --yes`: marks `deleted: true` (or removes the entry), idempotent on an already-absent or already-deleted name (never errors). `repo list OWNER --json name`: emits the names of all non-deleted repos under `owner`, filterable by the harness fixture the same way `releases_file` already seeds `gh api repos/github/spec-kit/releases`.
- [X] T003 Add the `e2e-stage` job skeleton to `.github/workflows/auto-update-spec-kit.yml` per contracts/e2e-verification-tier.md: `needs: prepare`, `if: needs.prepare.outputs.release-type != 'patch'`, `runs-on: ubuntu-latest`, `outputs: { passed: steps.readback.outputs.passed, failure-detail: steps.readback.outputs.failure-detail, scratch-repo: steps.scratch-repo.outputs.full-name }`, and the standard bootstrap steps every job repeats (Checkout consumer repository, Resolve pipeline ref, Checkout pipeline repository, Wing Commander context — copy verbatim from `verify`'s own copies at lines 1172-1210). Leave the scratch-repo/agent/read-back steps as placeholders for Phase 3 (US1).
- [X] T004 In `.github/workflows/auto-update-spec-kit.yml`, add `e2e-stage` to the `verify` job's `needs:` list (`needs: [prepare, e2e-stage]`, currently `needs: prepare` at line 1154) and change `verify`'s job-level `if:` from `needs.prepare.result == 'success'` to `always() && needs.prepare.result == 'success'` (matching `act`'s own `always() && (...)` convention at lines 1383-1388) — without `always()`, GitHub Actions' default "skip if any needed job did not succeed" behavior would skip `verify` whenever `e2e-stage` fails or times out, but `verify`'s combine step (T013) needs to read `needs.e2e-stage.*` precisely in that case.

**Checkpoint**: `gh_stub.py` can record/query scratch-repo state; the workflow has an empty `e2e-stage` job correctly wired into `verify`'s dependency graph — user story work can begin.

---

## Phase 3: User Story 1 - A broken minor/major candidate is caught by the deeper tier (Priority: P1) 🎯 MVP

**Goal**: The deeper tier's verdict actually depends on the candidate's own behaviour — every Spec Kit script the pipeline depends on is exercised out of the candidate's checkout and asserted against its documented shape, and one real AI-driven stage runs against the candidate and gates adoption.

**Independent Test**: Point the deeper tier at a candidate whose Spec Kit scripts are deliberately broken (non-zero exit, or a renamed/absent output field) and confirm the minor/major run reports verification failure naming the failing check, while the same tier passes for an unmodified, healthy candidate; repeat with the AI-driven stage unable to complete and confirm the tier fails there too — `quickstart.md` Scenarios 1, 3, 4, 5.

### Implementation for User Story 1

- [X] T005 [US1] In `.github/workflows/auto-update-spec-kit.yml`, replace the "End-to-end verification (minor/major only)" step's body (`id: end-to-end`, currently lines 1294-1325, including its `cp $template $target` / `else printf ...` fallback) with the first check of the per-script assertion chain: `[ -s "$FEATURE_DIR/spec.md" ]`. No `cp`/`printf`/fallback content of any kind — FR-004. Fail → `passed=false`, `failure-detail` names `spec.md` under `$FEATURE_DIR`. Keep the step's existing `if: needs.prepare.outputs.release-type != 'patch' && steps.lightweight.outputs.passed == 'true'` gate and its `$WORKTREE`/`$FEATURE_DIR` env vars sourced from `steps.lightweight.outputs`.
- [X] T006 [US1] In the same step (or a chained step still reading `$WORKTREE`/`$FEATURE_DIR`), after T005's check passes, run `SPECIFY_FEATURE_DIRECTORY="$FEATURE_DIR" bash .specify/scripts/bash/setup-plan.sh --json` inside `$WORKTREE`. Non-zero exit → `failure-detail` names `setup-plan.sh` and the captured stderr tail (`tail -c 500`, matching the lightweight tier's existing pattern at lines 1247/1268). Success → assert `FEATURE_SPEC`/`IMPL_PLAN`/`SPECS_DIR`/`BRANCH` are all present and non-empty in the JSON output, and `[ -s "$IMPL_PLAN" ]` on disk; either failing → `failure-detail` names the missing field or the empty `plan.md` path.
- [X] T007 [US1] Chain `SPECIFY_FEATURE_DIRECTORY="$FEATURE_DIR" bash .specify/scripts/bash/setup-tasks.sh --json` after T006's check passes. Non-zero exit → `failure-detail` names `setup-tasks.sh` and the captured stderr tail. Success → assert `FEATURE_DIR`/`AVAILABLE_DOCS`/`TASKS_TEMPLATE` are present, `AVAILABLE_DOCS` is a JSON array (possibly empty), and `TASKS_TEMPLATE` is non-empty and resolves to an existing file on disk. Set this step's final `passed`/`failure-detail` outputs from whichever of T005/T006/T007's three checks failed (or `true` if all passed).
- [X] T008 [US1] Fill in `e2e-stage`'s (T003) scratch-repository create-or-reuse step: `gh repo view "${{ github.repository_owner }}/wing-commander-e2e-${{ needs.prepare.outputs.issue-number }}"`; absent → `gh repo create` (private, per data-model.md's Scratch repository entity); emit a `full-name` output (`id: scratch-repo`). Idempotent — a re-dispatched run for the same still-open lifecycle issue reuses the existing repository rather than erroring or duplicating.
- [X] T009 [US1] Add the scaffold-push step to `e2e-stage`: clone the scratch repository locally using the Wing Commander context token, run the candidate's own `uvx --from git+https://github.com/github/spec-kit.git@v${CANDIDATE} specify init . --ai claude --script sh --ai-skills --here --force` (the same command `prepare`'s "Write version-bump diff" step already runs at lines 1119-1130) inside the clone, then commit and push — so the scratch repository reflects "candidate scaffolded and ready" even if the agent step below never completes (FR-022).
- [X] T010 [US1] Add the `claude-code-action@v1` step to `e2e-stage` (`id: decide`, matching `evaluate-path`'s `decide` step shape at lines 810-857): `continue-on-error: true`, a bounded `timeout-minutes`, `--model ${{ inputs.e2e-stage-model }}`, `--max-turns ${{ inputs.e2e-stage-max-turns }}`, least-privilege `--allowedTools` scoped to the candidate's own `.specify/scripts/bash/create-new-feature.sh` plus `Write`/`Edit` inside the scratch clone, `--disallowedTools` including `WebSearch,WebFetch,Bash(git push:*)` (the workflow's own deterministic steps do any pushing, never the agent). Prompt: a fixed, hardcoded throwaway feature description — never issue/comment text (there is no untrusted input to this step at all) — instructing the agent to produce one feature spec via the candidate's own `/speckit-specify`-equivalent flow, working inside the scratch clone checked out in T009.
- [X] T011 [US1] Add the deterministic "Read back stage result" step to `e2e-stage` (`id: readback`, matching `evaluate-path`'s `decide-outcome` read-back convention at lines 872-923 — never trusts agent narration): `steps.decide.outcome != 'success'` → `passed=false`, `failure-detail` states explicitly that the stage did not complete (FR-021's completion-vs-shape distinction). Otherwise check the local clone's working tree for a non-empty `specs/*/spec.md`; absent or empty → `passed=false`, `failure-detail` names the expected output (a non-empty `specs/*/spec.md`) versus what was observed (none). Both present → `passed=true`. This step's outputs feed `e2e-stage`'s job-level `passed`/`failure-detail` outputs declared in T003.
- [X] T012 [US1] Add the best-effort push-back step to `e2e-stage`: if `steps.readback.outputs.passed == 'true'`, push the agent-produced `spec.md` to the scratch repository too. A push failure here must not flip `passed` — the gating assertion already happened against the local working tree in T011; do not propagate this step's exit code to the job.
- [X] T013 [US1] In `verify`'s "Combine verification result" step (lines 1331-1366), replace the single `E2E_PASSED`/`E2E_DETAIL` env vars (sourced from the now-deleted `steps.end-to-end.outputs`) with the fourth gating check, `needs.e2e-stage.result`/`needs.e2e-stage.outputs.passed`/`needs.e2e-stage.outputs.failure-detail`, alongside T005/T006/T007's three script checks (contracts/e2e-verification-tier.md's `verify` job section). `end_to_end.passed` is `true` only when all four checks pass; `failure-detail` carries whichever single check actually failed, verbatim from that check's own detail string.
- [X] T014 [US1] Add a `t4_verify.sh` scenario for a healthy candidate (quickstart Scenario 1): run the extracted spec.md/`setup-plan.sh`/`setup-tasks.sh` chain (T005-T007) against a real fixture worktree seeded from this repository's own `.specify/templates/`, then feed the extracted combine step (T013) an `agent_out()`-built `claude-execution-output.json` (reusing `t6_reply.sh`'s helper, per research.md) representing a completed e2e-stage that produced a `spec.md`; confirm each check reports `passed=true` and `combine` reports `tier=lightweight+end-to-end`, `passed=true`.
- [X] T015 [US1] Add `t4_verify.sh` scenarios for wrong-shape/non-zero-exit failures (quickstart Scenario 3, SC-008): inject a mutant per script in scope (`create-new-feature.sh`, `check-prerequisites.sh`, `setup-plan.sh`, `setup-tasks.sh` — rename a documented JSON field, e.g. `TASKS_TEMPLATE` → `TASKS_TMPL`, or force a non-zero exit via a fixture edit) and confirm each, in isolation, fails the corresponding extracted assertion step (T006/T007) with `failure-detail` stating the expected vs. observed shape/exit.
- [X] T016 [US1] Add `t4_verify.sh` scenarios for the e2e-stage read-back (quickstart Scenarios 4/5, FR-021): an `agent_out()`-built fixture with `is_error=true` (or the file omitted, simulating a timeout) run through T011's extracted read-back step → `passed=false` with `failure-detail` stating the stage did not complete; a successful fixture whose working-tree fixture has no `specs/*/spec.md` → `passed=false` with `failure-detail` naming the expected non-empty file vs. none observed; confirm the two failure-detail strings use distinct wording (FR-021, so a maintainer can tell an infrastructure problem from a broken candidate).

**Checkpoint**: User Story 1 is fully functional — `quickstart.md` Scenarios 1, 3, 4, 5 pass via the harness.

---

## Phase 4: User Story 2 - A missing expected artifact fails instead of silently passing (Priority: P1)

**Goal**: An absent expected artifact is treated as the candidate not being verifiable — the tier fails, with no locally-manufactured substitute ever written and no second outcome path.

**Independent Test**: Run the deeper tier against a candidate checkout with an expected artifact removed and confirm the tier fails — with no locally-manufactured substitute written and no pass reported; confirm the failure reaches the exact same single outcome path as every other deeper-tier failure — `quickstart.md` Scenario 2.

### Implementation for User Story 2

- [ ] T017 [US2] Confirm, by inspecting the per-script chain built in T005-T007, that no `else`/fallback branch of any kind remains anywhere in the extracted steps' source — `create-new-feature.sh` and `setup-plan.sh`'s own `touch`-degrade-to-empty behaviour is exactly what T005/T006's non-empty checks catch (research.md's "FR-004 satisfied by non-empty checks alone" decision); `setup-tasks.sh` has no equivalent silent path — a missing `tasks-template.md` makes it exit non-zero directly, which T007 already fails on. If any stray fallback remains from the deleted old step, delete it.
- [ ] T018 [US2] Add `t4_verify.sh` scenarios for the missing-artifact path (quickstart Scenario 2, FR-004, SC-002): seed the fixture worktree's `.specify/templates/` **without** `plan-template.md`, run `setup-plan.sh --json` for real, confirm it exits `0` but writes a zero-byte `plan.md`, and confirm T006's extracted non-empty assertion reports `passed=false` naming `plan.md` — with a `check_not_contains`/source-inspection assertion confirming no locally-manufactured substitute is ever written by the tier itself. Repeat with `spec-template.md` missing instead (same shape, via `create-new-feature.sh`'s own identical fallback, exercising T005).
- [ ] T019 [US2] Extend `t7_gating.py`'s `act` step-set scenarios (or add a `t4_verify.sh` assertion) confirming a missing-artifact failure reaches the exact same single `act` branch ("Comment verification failure on the issue" / "Apply the failed label") as every other deeper-tier failure (T015/T016's mutants) — no distinct label, no second comment kind, no routing branch (FR-005/FR-006).

**Checkpoint**: User Stories 1 AND 2 both work independently — `quickstart.md` Scenarios 1-5 pass.

---

## Phase 5: User Story 3 - The failure narration tells the maintainer what to consider next (Priority: P2)

**Goal**: The lifecycle issue states which check failed and what was expected vs. observed; a missing-artifact failure additionally names the relocation/FR-018 consideration; every `lightweight+end-to-end` run names the scratch repository and its deletion-on-close guarantee; closing the lifecycle issue deletes the scratch repository, with a scheduled sweep as backstop.

**Independent Test**: Trigger a deeper-tier failure caused by a missing expected artifact and confirm the lifecycle issue comment alone states the failing check, the expected artifact and path, and the non-clean-bump consideration with a pointer to FR-018; confirm a maintainer closing the lifecycle issue results in the scratch repository being deleted — `quickstart.md` Scenarios 6, 7.

### Implementation for User Story 3

- [ ] T020 [US3] Extend T005's and T006's `failure-detail` composition to append the FR-008 sentence — stating the artifact may indicate the candidate legitimately reorganized its templates or scripts rather than that it is broken, and pointing at specs/027's FR-018 non-clean-bump route — **only** for their missing-expected-artifact branches (T005's `spec.md` check; T006's empty-`plan.md` branch), never for a non-zero exit or wrong-JSON-shape failure (data-model.md's Failure narration `non_clean_bump_hint` field; FR-009 — narration content only).
- [ ] T021 [US3] Extend `verify`'s combine step (T013) and `act`'s existing narration steps ("Comment verification failure on the issue" at line 1590, and the pass-path PR-body "Verified: ..." line at line 1569) to always append a scratch-repository pointer — naming `wing-commander-e2e-<issue-number>` and stating it is deleted when the lifecycle issue closes — whenever `tier == lightweight+end-to-end`, regardless of pass/fail (FR-022, SC-012; data-model.md's `scratch_repo_pointer` field, sourced from `needs.e2e-stage.outputs.scratch-repo`).
- [ ] T022 [US3] Add `issues: {types: [closed]}` to `.github/workflows/wing-commander-auto-update-spec-kit.yml`'s `on:` block, and extend its `trigger` resolution expression (contracts/e2e-verification-tier.md's exact expression) to add `github.event_name == 'issues' && 'issue-closed'`, reusing the existing `issue-number: ${{ github.event.issue.number || '' }}` input.
- [ ] T023 [US3] Add a new `issue-closed` entry-point job to `.github/workflows/auto-update-spec-kit.yml` (`if: inputs.trigger == 'issue-closed'`, matching `pr-merged`/`comment-reply`'s own entry-point job shape and bootstrap): fetch the closed issue's body, verify it carries this feature's settle-tracking marker `<!-- wing-commander-auto-update-spec-kit: candidate=` (self-recognition guard, same discipline as every other trigger) — an unrelated closed issue is a no-op; then `gh repo delete "${{ github.repository_owner }}/wing-commander-e2e-${{ inputs.issue-number }}" --yes 2>/dev/null || true` (idempotent — a repository that was never created, e.g. a patch-only cycle, is a silent no-op).
- [ ] T024 [US3] Add a new `reap-scratch-repos` job to `.github/workflows/auto-update-spec-kit.yml` (`if: inputs.trigger == 'scheduled' || inputs.trigger == 'dispatch'`, independent of that day's own `detect`/`settle`/`verify` cycle — runs even when there's nothing new to check): `gh repo list "${{ github.repository_owner }}" --json name --jq '.[].name' | grep '^wing-commander-e2e-'`; for each match, derive `<issue>` from the name suffix, `gh issue view <issue> --json state` (state `CLOSED` or the lookup itself failing → delete; state `OPEN` → leave alone) — matched only against the `wing-commander-e2e-<digits>` pattern exactly, never a broader glob (contracts/e2e-verification-tier.md's Self-recognition contract).
- [ ] T025 [US3] Add `t4_verify.sh` scenarios for the narration hint (quickstart Scenario 6, FR-008/FR-009): drive `combine` (T013) once with a missing-template failure (T018's fixture shape) and once with a non-zero-exit or e2e-incomplete failure (T015/T016's fixtures); assert only the missing-artifact case's `failure-detail` contains the relocation/FR-018 sentence (`check_contains`) and the others don't (`check_not_contains`); assert every `tier=lightweight+end-to-end` run's composed narration — pass or fail — names the scratch repository (`check_contains` on the composed detail/summary text, per T021).
- [ ] T026 [US3] Add scratch-repo lifecycle scenarios to `t4_verify.sh` or a new suite section (quickstart Scenario 7, using T002's `gh_stub.py` extensions): drive T008's extracted create step for a lifecycle issue number, confirm `gh repo view` then reports it present; re-run the create step (simulating a re-dispatch) and confirm no duplicate is recorded (idempotency); drive T023's `issue-closed` deletion branch against that same issue number, confirm the stub's state marks the repo deleted, and confirm re-running it against an already-deleted (or never-created) repo does not error; drive T024's `reap-scratch-repos` sweep against a stub state containing one repo whose issue is `OPEN`, one whose issue is `CLOSED`, and one whose issue number no longer exists at all, confirming only the latter two are deleted.
- [ ] T027 [US3] Extend `t7_gating.py` with the `issue-closed` trigger's job-routing (reading `if:` conditions verbatim from the YAML, per its existing no-retyping convention): the `issue-closed` job runs only when `inputs.trigger == 'issue-closed'`; `reap-scratch-repos` runs on `scheduled`/`dispatch` regardless of that day's `detect`/`verify` outcomes; `e2e-stage`'s own gating (`needs.prepare.outputs.release-type != 'patch'`) and `verify`'s `always() && needs.prepare.result == 'success'` condition (T004) are asserted alongside the existing job-routing scenarios.

**Checkpoint**: User Stories 1, 2, AND 3 all work independently — `quickstart.md` Scenarios 1-7 pass.

---

## Phase 6: User Story 4 - The behaviour is asserted by the executable harness, not desk-checked (Priority: P3)

**Goal**: The tier's pass and failure paths are fully covered by the executable scenario harness, the harness is provably deterministic and never touches real GitHub repositories, and the parent spec's Scenario 7 narrative matches the implemented tier.

**Independent Test**: Run the existing scenario harness and confirm it exercises, and can fail on, each defective-candidate case plus the scratch repository's retain-then-delete lifecycle; run it twice and confirm identical verdicts — `quickstart.md` Scenarios 8, 9.

### Implementation for User Story 4

- [ ] T028 [US4] Add `t4_verify.sh`/`t7_gating.py` coverage for the patch-only tier (quickstart Scenario 8, Edge Case): confirm `e2e-stage`'s `if:` condition short-circuits for `release-type == 'patch'` (no scratch repository ever created for that cycle) and `combine` still reports `tier=lightweight` — reusing T027's verbatim-`if:` reading and T014's existing `t4_verify.sh` "Scenario 7: tier selection" block.
- [ ] T029 [US4] Confirm and document (in `run-tests.sh`'s output or a comment in `t4_verify.sh`) that running the full suite twice produces identical verdicts (SC-010, FR-020) — the AI-driven stage's non-determinism is fully contained to the fixed `agent_out()` fixtures T014/T016/T025/T026 build, never a live agent call — and that no scenario added by T002/T008/T023/T024/T026 ever shells out to real `gh repo create`/`delete`/`list` (only `gh_stub.py`'s JSON state file).
- [ ] T030 [P] [US4] Correct `specs/027-auto-update-spec-kit/quickstart.md` Scenario 7's narrative (FR-016, SC-007): replace "a throwaway spec-kit-driven stage generated and discarded" with language matching this feature's spec.md and quickstart.md — the tier exercises every dependent Spec Kit script plus one real AI-driven stage against a scratch repository, has a single failure path, and contains no fallback.
- [ ] T031 [P] [US4] Update `.github/scripts/auto-update-spec-kit-tests/README.md` per research.md's test-harness-extensions decision: extend the `t4_verify.sh` row in the scenario table (per-script chain, e2e-stage read-back, scratch-repo retain/delete lifecycle) and add mutation-table rows for: the `else` fallback reintroduced, a per-script assertion silently skipped, and the e2e-stage result reported but non-gating (each caught by T015/T016/T018's and T013's assertions).

**Checkpoint**: All four user stories are independently functional — the full `quickstart.md` scenario set (1-9) passes via the harness.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation consistency and end-to-end validation across the whole feature.

- [ ] T032 [P] Update `docs/architecture.md`'s existing "Auto-Update Spec Kit" section: replace the `verify` bullet (lines 851-855, which still describes "a disposable spec generated and discarded") with the four-check deeper tier (per-script assertion chain against the candidate's own `create-new-feature.sh`/`check-prerequisites.sh`/`setup-plan.sh`/`setup-tasks.sh`, plus the gating AI-driven `e2e-stage`), and add a new bullet describing the scratch-repository lifecycle (created per run inside `e2e-stage`, retained while the lifecycle issue is open, deleted by the `issue-closed` trigger or the `reap-scratch-repos` scheduled backstop sweep).
- [ ] T033 [P] Add `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_STAGE_MODEL` (default `claude-sonnet-5`) and `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_STAGE_MAX_TURNS` (default `20`) rows to `docs/setup.md`'s repository-variables table, mirroring the existing `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_MODEL` row's format (T001).
- [ ] T034 Validate `.github/workflows/auto-update-spec-kit.yml` and `.github/workflows/wing-commander-auto-update-spec-kit.yml` end-to-end: YAML parses (e.g. `python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))"` or actionlint if available), every embedded `run:` script passes `bash -n` (matching `lint-workflows.yml`'s CI checks), and every job/step touched by this feature matches `contracts/e2e-verification-tier.md` verbatim.
- [ ] T035 Run `bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh` (all suites) and confirm the full harness passes, including the pre-existing specs/027 suites unaffected by this feature (`t1_detect.sh`, `t2_settle.sh`, `t3_healthcheck.sh`, `t5_act.sh`, `t6_reply.sh`) alongside the `t4_verify.sh`/`t7_gating.py` suites this feature extends.
- [ ] T036 Surface, in the feature's PR body and the transmittal comment on issue #184 (matching specs/027 T033's precedent), the decisions research.md flags as made without clarification or needing maintainer confirmation before the first real minor/major run reaches this tier: `e2e-stage-max-turns`'s default of `20` is an estimate; the `e2e-stage-model` tiering decision (`claude-sonnet-5`, not `claude-opus-5`) was made without clarification; and the scheduled job's App installation needs a broader `gh repo create`/`delete` permission grant it does not have today — a grant a workflow YAML `permissions:` block cannot itself provide, so `e2e-stage`/`issue-closed`/`reap-scratch-repos` cannot run for real until a maintainer grants it out-of-band (spec.md's own flagged Assumption).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 (T003/T004 reference `inputs.e2e-stage-model`/`inputs.e2e-stage-max-turns` in later phases, and T004's `always() &&` guard is meaningless before `e2e-stage` exists) — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational. No dependency on other stories — the only story that can be independently implemented and tested first.
- **User Story 2 (Phase 4)**: Depends on Foundational AND User Story 1 (T017-T019 inspect and test the exact per-script chain T005-T007 build; there is no separate "no-fallback" code path to write).
- **User Story 3 (Phase 5)**: Depends on User Story 1 (T020/T021 extend T005/T006/T013's checks and narration; T023's deletion branch reaps the repository T008 creates).
- **User Story 4 (Phase 6)**: Depends on User Stories 1, 2, AND 3 (its harness-completeness and Scenario-7-narrative tasks have nothing to assert or correct until the behavior they describe exists).
- **Polish (Phase 7)**: Depends on all prior phases.

### User Story Dependencies

- **User Story 1 (P1)**: Independently implementable and testable after Foundational — delivers the entire reason the tier exists (SC-001/SC-002/SC-003/SC-006/SC-009) on its own.
- **User Story 2 (P1)**: Builds on User Story 1's per-script chain (T005-T007) with inspection + harness tasks only, since FR-004's fix is that chain having no fallback branch by construction, not a separate feature.
- **User Story 3 (P2)**: Builds on User Story 1's checks (narration) and scratch-repository creation (deletion lifecycle) — its own Independent Test explicitly depends on US1/US2 existing first (spec.md's own "Why this priority").
- **User Story 4 (P3)**: Extends the harness and corrects a narrative describing US1-US3's combined behavior — has nothing to cover or correct until they exist (spec.md's own "Why this priority").

### Within Each Story

- T005 before T006 before T007 (the per-script chain's own execution order — `setup-tasks.sh` hard-errors without `plan.md`, so out-of-order execution would make US1 fail on an ordering bug indistinguishable from a real candidate defect, per research.md).
- T008 before T009 before T010 before T011 before T012 (US1's `e2e-stage` job — each step's env/working tree depends on the one before it).
- T013 depends on T005-T007 AND T008-T012 (the combine step folds in all four checks).
- T014-T016 (US1's harness tasks) depend on T005-T013 (nothing to assert until the steps exist).
- T022 before T023 (the wrapper's trigger must resolve `issue-closed` before the stage-side job can gate on it).
- T024 has no dependency on T022/T023 beyond Phase 2 — it runs on the pre-existing `scheduled`/`dispatch` triggers.

### Parallel Opportunities

- T002 (harness) and T003/T004 (workflow) touch different files and have no data dependency on each other — safe to run in parallel within Phase 2.
- Within Phases 3-5, nearly every task edits the same `auto-update-spec-kit.yml` file (different jobs or different steps within a job) — treat as sequential, not `[P]`, matching specs/027/tasks.md's identical call on its own file-concentration.
- T030 and T031 (Phase 6) touch different files (`specs/027-.../quickstart.md`, `README.md`) from each other and from T028/T029 — parallel-safe.
- T032 and T033 (Polish, two different doc files) are parallel-safe with each other and with T034/T035/T036.

---

## Parallel Example: Foundational Phase

```bash
# Launch together — different files, no shared state:
Task: "Extend gh_stub.py with repo create/delete/list handlers"
Task: "Add the e2e-stage job skeleton to auto-update-spec-kit.yml and wire it into verify's needs"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Run `quickstart.md` Scenarios 1, 3, 4, 5 via the harness (`bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh t4_verify`)
5. This alone delivers SC-001/SC-002/SC-003/SC-006/SC-009 — the deeper tier's verdict now genuinely depends on the candidate's own behaviour, including the gating AI-driven stage. It does **not** yet guarantee no separate outcome path exists for a missing artifact (User Story 2), narrate the failure usefully (User Story 3), or have full harness coverage of the scratch-repository lifecycle (User Story 4) — spec.md frames US1 and US2 as equally P1, so a real rollout should not stop here.

### Incremental Delivery

1. Setup + Foundational → scaffold ready
2. Add User Story 1 → validate Scenarios 1, 3, 4, 5 → the deeper tier can actually fail on a broken candidate
3. Add User Story 2 → validate Scenario 2 → confirmed no fallback path and no second outcome branch (both P1 — ship together, per spec.md's own framing carried over from #157)
4. Add User Story 3 → validate Scenarios 6, 7 → a maintainer reading only the lifecycle issue knows what failed, what to consider next, and that the scratch repository disappears when they close the issue
5. Add User Story 4 → validate Scenarios 8, 9 → full harness coverage, deterministic verdicts, and a corrected parent-spec narrative
6. Polish → validate the full Scenario 1-9 sweep together, plus the pre-existing specs/027 suites

### Why User Story 1 and User Story 2 should ship together

Both are Priority P1 for the same reason spec.md states explicitly: User Story 1's per-script chain (T005-T007) *is* the code that also satisfies FR-004 by construction (no `else` branch is ever written) — there is no independent "no-fallback only" build. Shipping User Story 1 alone would already close the FR-004 gap in practice, but User Story 2's own tasks (T017-T019) are what *proves* it via the harness rather than leaving it desk-checked, and the carried-over #157 open question this feature exists to resolve was specifically about that fallback behaviour.
