# Tasks: Read-Only Agents Hold No Write-Capable `gh` Grant

**Input**: Design documents from `/specs/101-read-only-gh-grants/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/gate-93-check-4c.md, contracts/diagnose-staged-logs.md, quickstart.md

**Tests**: The spec requires fixtures and a mutation self-test for the gate (FR-012, SC-003); those are tasks in US3. No other test tasks.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 diagnose, US2 auto-update, US3 gate, US4 docs and contracts

Workflow comments are load-bearing (gates byte-compare them): after any edit under `.github/workflows/`, run `python .github/scripts/run-local-gates.py`.

## Phase 1: Setup

**Purpose**: Establish the baseline before editing.

- [X] T001 Run `python .github/scripts/run-local-gates.py` on the branch and record the baseline result, so later failures are attributable to this feature.
- [X] T002 [P] Read the current `collect-step-summary` step in `.github/workflows/watchdog.yml` (job-log fetch near lines 1262-1309), the `diagnose` job's tool-args site (`Bash(gh:*)` near line 2585) and prompt, and the "Decide upgrade path" step in `.github/workflows/auto-update-spec-kit.yml` (lines ~1092-1131), so every later edit is made against the current text.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared fetch helper both the collector and the new staging step use (FR-018: one home, no second copy).

**⚠️ CRITICAL**: US1 depends on this.

- [X] T003 Create `.github/actions/_shared/fetch-job-logs.sh` per `contracts/diagnose-staged-logs.md`. Inputs are env `GH_TOKEN`, `GITHUB_REPOSITORY`, `RUN_ID` and an output-directory argument. List jobs with `--paginate`, capture through a direct pipeline with `|| rc=` (never a bare command substitution), and skip `skipped`/`cancelled` jobs. Do one bounded retry after `sleep 10` per failed read. Never write an error message or an empty body as log content. Write `jobs.json` and per-job log files. Print `ok` or `failed` on the final line and always return 0.
- [X] T004 Rewrite `collect-step-summary` in `.github/workflows/watchdog.yml` (~1262-1309) to call `.github/actions/_shared/fetch-job-logs.sh` instead of its inline per-job fetch. Keep the sentinel-scanning logic inline and keep `ACTIONS_TOKEN: ${{ github.token }}`. Verify its behaviour is unchanged on the success and failure paths.

**Checkpoint**: One fetch helper exists and is used by the collector.

---

## Phase 3: User Story 1 - Diagnose cannot touch the repository (Priority: P1) 🎯 MVP

**Goal**: `watchdog.diagnose` holds zero `gh` grants and reads failed-job logs staged by a deterministic step.

**Independent Test**: The composed allowed list for `watchdog.diagnose` has no `gh`. After the staging step, logs sit at the literal paths the prompt names. A failed fetch produces `outcome:"failed"` and a verdict stating that job logs could not be gathered.

- [X] T005 [US1] Add a `Stage failed-job logs` step to the `diagnose` job in `.github/workflows/watchdog.yml`, before the agent step, with `continue-on-error: true` and `ACTIONS_TOKEN: ${{ github.token }}` (the workflow already grants `actions: read`). Call `.github/actions/_shared/fetch-job-logs.sh`, keep jobs whose conclusion is `failure`, and write `${{ steps.ctx.outputs.runner-temp }}/watchdog-job-logs/<job_id>.log` and `watchdog-job-logs-status.json` with the shape in `data-model.md`. Write the status file on every path. On a listing failure, a log read failure or an empty body, set `outcome:"failed"`, write no log file for that job (`file: null`), and append `"job-logs"` to `watchdog-untrusted-collectors.json`. Add the `container-shell-safety` and `review-step-gating` checks to the PR review notes.
- [X] T006 [US1] Remove `Bash(gh:*)` from the `watchdog.diagnose` tool-args `default-allowed-tools` in `.github/workflows/watchdog.yml` (~line 2585). Keep `Read,Grep` and the `python3 -I …/git_read.py` wrapper grant.
- [X] T007 [US1] Rewrite the diagnose prompt in `.github/workflows/watchdog.yml`. Name the log directory and status file by literal path. Frame the logs as untrusted DATA like the signals file. Remove every sentence that names `gh` or a fetch the agent would perform. State that when the status is `failed`, the status file is missing, or `job-logs` is in the untrusted collectors file, the verdict says job logs could not be gathered and no signal is dropped silently.
- [X] T008 [US1] Run `python .github/scripts/run-local-gates.py` and fix any workflow-comment or gate fallout from T004-T007.

**Checkpoint**: US1 is complete and is the MVP.

---

## Phase 4: User Story 2 - Upgrade agent held to the same rule (Priority: P1)

**Goal**: The "Decide upgrade path" agent holds no `gh` grant.

**Independent Test**: The inline `--allowedTools` has no `gh`, and the prompt names only the staged `release-notes.json`.

- [X] T009 [P] [US2] In `.github/workflows/auto-update-spec-kit.yml`, remove `Bash(gh api:*)` from the "Decide upgrade path" inline `--allowedTools` (~line 1131).
- [X] T010 [US2] In the same step's prompt (~lines 1092-1094), rewrite the sentence that describes `gh api` as an evidence tool. It should say Bash is restricted to the git wrapper and that the only evidence is the staged `release-notes.json`. Then run `python .github/scripts/run-local-gates.py`.

**Checkpoint**: Both named agents are at zero `gh` grants.

---

## Phase 5: User Story 3 - The rule is mechanical (Priority: P1)

**Goal**: Gate 93 check 4b fails on any `gh` grant on a read-only agent step in any workflow, with fixtures and a mutation self-test.

**Independent Test**: `python .github/scripts/verify-issue-context-single-home.py` and `--self-test` pass on the real tree. Each fixture fails or passes as `contracts/gate-93-check-4c.md` lists.

**Depends on**: US1 and US2 (otherwise the gate fails the clean tree).

- [X] T011 [US3] In `.github/scripts/verify-issue-context-single-home.py`, extend `_bash_grant_problems` and `check_read_only_git(strict=False)` so a `Bash` grant whose first token's basename is `gh` (any wildcard spelling or path-qualified) is a problem. Match by whitespace-split token, not substring. Reword the message to name the workflow, step and grant, say `gh` reaches remote writes, local file writes and alias/extension execution, point at the staged-file route, and point at `docs/agent-friendly-workflows.md` rather than restating the rationale. Update the check 4b docstring to drop "Other Bash grants (`gh ...`) are not this check's business" and to state the shipped-defaults-only scope (FR-014).
- [X] T012 [US3] Add an exemption table in the same script for `pr-conversation.classify` (`.github/workflows/pr-conversation.yml`), scoped to exactly `gh pr view`, `gh issue view` and `gh search issues`, per research D4 and `data-model.md`. The gate fails if the site holds any other `gh` grant or holds none (stale). Cite the open "Maintenance backlog" issue (#889) as tracker. Before closing out, run `grep -rnE '"#889"|issue *= *\([^)]*\b889\b' .github/scripts/` and follow the waiver-register shape that Gate 124 (`verify-waiver-citations.py`) expects.
- [X] T013 [US3] Make the loud-failure cases fail: a `FLEET_READ_ONLY_STEP_LABELS` label with no matching site, and zero read-only sites across the fleet.
- [X] T014 [US3] Add the nine fixtures from `contracts/gate-93-check-4c.md` to the self-test, one per failure branch. Update the existing `_inline_fixture` default (`Bash(gh api:*)`) and the 4b "gh left alone" case, which encode the old behaviour.
- [X] T015 [US3] Add mutations to the self-test that restore `Bash(gh:*)` in `watchdog.yml`'s `watchdog.diagnose` site and `Bash(gh api:*)` in `auto-update-spec-kit.yml`'s inline list, on copies of the real files. The gate must fail on each.
- [X] T016 [US3] Run `python .github/scripts/verify-issue-context-single-home.py --self-test`, then `python .github/scripts/run-local-gates.py`. Confirm the gate is invoked the same way locally as in `lint-workflows.yml`.

**Checkpoint**: A regression of either grant fails the PR-time suite.

---

## Phase 6: User Story 4 - The record stops teaching the old grant (Priority: P2)

**Goal**: Docs and live contracts match the shipped lists, with one canonical rationale home.

**Independent Test**: Grep for `Bash(gh:*)` and `Bash(gh api:*)` in docs and contracts. Each survivor is labelled historical.

- [X] T017 [US4] In `docs/agent-friendly-workflows.md`, replace the `--allowedTools "Read,Grep,Bash(gh:*)"` read-only example with a list that cannot write. Make this section the single canonical rationale (FR-017): `gh` reaches remote writes, local file writes, and arbitrary execution via `gh alias set` / `gh extension install`, and the rule is total rather than per-subcommand.
- [X] T018 [P] [US4] Update `specs/010-reusable-pipeline/contracts/stage-interfaces.md`: the per-stage table (~line 339) and the `gh api` disposition paragraph (~line 293). State the new lists and point at the canonical home instead of restating the rationale.
- [X] T019 [P] [US4] Update the diagnose `--allowedTools` record in `specs/015-pipeline-watchdog/contracts/watchdog-workflow.md` (~line 81) to match the shipped list, and add the staged job-log files.
- [X] T020 [P] [US4] Update the evaluate-path `--allowedTools` record in `specs/027-auto-update-spec-kit/contracts/auto-update-spec-kit-workflow.md` (~line 104).
- [X] T021 [P] [US4] Rewrite the "pre-existing, wider `Bash(gh:*)` grant … untouched by this policy" paragraph in `specs/051-read-only-inspection-policy/contracts/inspection-policy.md` in the past tense, with a pointer to the canonical home.
- [ ] T022 [US4] Add a "single home" assertion for the rationale (per research D6) to the nearest existing gate: the rationale's distinguishing sentence must occur in exactly one file. If no cheap deterministic form exists, record why in the PR description instead.

**Checkpoint**: SC-006 and SC-007 hold.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T023 Grep `.github/` and `docs/` for remaining `Bash(gh:*)`, `Bash(gh api:*)`, and prompt text that coaches `gh` on read-only agents (SC-001, SC-006).
- [X] T024 Run `python .github/scripts/run-local-gates.py` clean, then walk `quickstart.md`.
- [ ] T025 Post-merge proof (hand to the maintainer, since the merge needs the `workflow` scope): re-drive one watchdog run with `gh workflow run` and record the schema-valid verdict with no denied-tool event (SC-004). Record one auto-update evaluation returning an outcome from the staged release notes (SC-005). Record a simulated fetch failure ending in `outcome:"failed"` and a verdict naming job logs (SC-008).

---

## Dependencies & Execution Order

- Setup → Foundational (T003, T004) → US1.
- US1 and US2 are independent of each other. Both must land before US3, whose gate would otherwise fail the clean tree.
- US4 is independent of US1 and US2, but T018-T021 should state the final lists, so run it after them.
- T004 and T005-T007 all edit `watchdog.yml`, so keep them sequential. T009 can run in parallel with US1 work (a different file).

### Parallel Opportunities

- T002 alongside T001.
- T009 alongside T005-T008.
- T018-T021 together (different files).

## Implementation Strategy

- **MVP**: Phases 1-3 (US1). This removes the exposure the issue was filed for.
- **Then** US2, then US3 (the guard that keeps both from regressing), then US4.
- Keep concurrent local agents to two (CLAUDE.md usage-window rule). Every fix PR gets a code review. Run `spec-cross-reference` on the review, since the changed files are referenced by specs.
- Out-of-scope findings go on the Maintenance backlog issue, not new issues.

## Maintainer Feedback

- [X] T001 (PR #991 comment by charlesguse) Run `python .github/scripts/run-local-gates.py` on the branch and record the baseline result. The rebuilt implement image (#996) now includes PyYAML (#989).
- [X] T008 (PR #991 comment) Run `python .github/scripts/run-local-gates.py` and fix any workflow-comment or gate fallout from T004-T007.
- [X] T016 (PR #991 comment) Run `python .github/scripts/verify-issue-context-single-home.py --self-test`, then `python .github/scripts/run-local-gates.py`. Confirm the gate is invoked the same way locally as in `lint-workflows.yml`.
- [ ] T022 (PR #991 comment) Add a single-home assertion for the rationale (research D6) to the nearest existing gate. The rationale's distinguishing sentence must occur in exactly one file. If no cheap deterministic form exists, record why in the PR description.
- [X] T024 (PR #991 comment) Run `python .github/scripts/run-local-gates.py` clean, then walk `quickstart.md`.
- T025 stays a post-merge maintainer step and is not part of this change.

## Phase 8: Convergence

- [ ] T026 Update the live contract `specs/101-read-only-gh-grants/contracts/diagnose-staged-logs.md` (its "Helper" heading, line 6): the fetch now lives in the published composite `.github/actions/wing-commander-fetch-job-logs/action.yml` (its own step, because Gate 12 forbids `gh` calls in `_shared/` scripts and Gate 60 forbids a published stage resolving `_shared/`), and the callers read its `result` output instead of the helper's last stdout line, per FR-018 (contracts are live) (partial)
