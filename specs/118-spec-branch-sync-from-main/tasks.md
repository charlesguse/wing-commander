# Tasks: Keep Spec Branches Current by Merging Main (sync-from-main)

**Input**: Design documents from `/specs/118-spec-branch-sync-from-main/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/sync-method-input.md, quickstart.md

**Tests**: The spec (FR-016, constitution VIII) requires checked-in git-fixture tests for every deterministic failure branch, so test tasks are included. Write each fixture first and see it fail.

**Organization**: Grouped by user story. All paths are relative to the repository root. Workflow comments are load-bearing (gates byte-compare them): treat comment edits as code edits. Under the `rebase` method every existing name, string and step stays byte-identical (SC-004).

Run `python .github/scripts/run-local-gates.py` after each phase and before pushing; a change touching any `if:` or `continue-on-error:` in `rebase.yml` also gets a pass from the `review-step-gating` skill, and the `container:`/`run:` steps get `container-shell-safety`. These are guidance, not tasks.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

**Purpose**: Locate the existing rebase pieces the new arm shares.

- [X] T001 Read `.github/workflows/rebase.yml`, `.github/workflows/wing-commander-rebase.yml`, `.github/scripts/verify-rebase-discover-selection.py` and the gate registry in `.github/workflows/lint-workflows.yml`; note the step ids, outputs, and the comment blocks the gates byte-compare, so the merge arm reuses them (no code change).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The deterministic helper and its gate. Every story calls this helper.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 Create `.github/scripts/wc_sync_from_main.py` (stdlib only) with the subcommand skeleton `validate-method`, `decide`, `verify-scope`, `publish-refspec` per `contracts/sync-method-input.md` "Deterministic helper contract".
- [X] T003 Implement `validate-method <value>` in `.github/scripts/wc_sync_from_main.py`: empty or `rebase` prints `rebase`, `merge` prints `merge`, anything else exits 1 with exactly `::error::wing-commander rebase: sync-method '<value>' is not valid; accepted values are 'rebase' and 'merge'`.
- [X] T004 Implement `publish-refspec <branch>` in `.github/scripts/wc_sync_from_main.py`: print `HEAD:refs/heads/<branch>`; exit 1 for a branch value with a leading `+` or any `--force*` token (SC-002).
- [X] T005 Create gate `.github/scripts/verify-sync-from-main.py` with the fixture harness (local bare origin + clone per case, temp dirs, git identity set) and the cases for `validate-method` (unset, `rebase`, `merge`, bogus value, case variant) and `publish-refspec` (plain, `+` prefix, `--force`).
- [X] T006 Register `verify-sync-from-main.py` in the gate registry in `.github/workflows/lint-workflows.yml` so `python .github/scripts/run-local-gates.py` runs it with the same arguments as CI; confirm it runs and passes.

**Checkpoint**: Helper validates the method and refspec; gate runs locally and in the registry.

---

## Phase 3: User Story 1 - A spec branch stays current without losing its history (Priority: P1) 🎯 MVP

**Goal**: Under `merge`, a clean behind-main branch gains exactly one two-parent sync commit, published with a plain push; an up-to-date branch is untouched.

**Independent Test**: Fixture: record branch head, add an unrelated `main` commit, run decide + merge + commit + push; old head is an ancestor of the new head, which contains the `main` commit; no commit when already current.

### Tests for User Story 1

- [X] T007 [P] [US1] Add fixture cases in `.github/scripts/verify-sync-from-main.py` for `decide`: branch already contains `main` → `current`; behind → `merge`; same-tree case (`main` gained a cherry-pick of branch work) → `merge` (FR-003).
- [X] T008 [P] [US1] Add fixture cases in `.github/scripts/verify-sync-from-main.py` for the clean path: `git merge --no-ff --no-commit` then explicit commit gives a commit with parents `[old tip, main tip]` and message `sync: merge <default> into <spec-branch>`; the same-tree merge still creates the commit; every pre-sync SHA stays an ancestor of the new head (SC-001).
- [X] T009 [P] [US1] Add fixture cases in `.github/scripts/verify-sync-from-main.py` for publish: plain `git push` succeeds as fast-forward with no `+`/`--force*`; when the remote head moved after checkout the push is rejected and the remote branch is untouched (FR-002).

### Implementation for User Story 1

- [X] T010 [US1] Implement `decide --main <sha>` in `.github/scripts/wc_sync_from_main.py`: print `current` if `git merge-base --is-ancestor <main> HEAD`, else `merge` (research D4).
- [X] T011 [US1] Add the `sync-method` input (type string, default `rebase`) to `.github/workflows/rebase.yml` `workflow_call.inputs`, with a description matching the contract.
- [X] T012 [US1] In `.github/workflows/rebase.yml`, add merge-arm steps to the per-branch matrix job, each gated `if: inputs.sync-method == 'merge'`: fetch `origin $DB` with an explicit refspec (never a bare fetch), call `wc_sync_from_main.py decide`, `git merge --no-ff --no-commit origin/$DB`, classify outcome `current|clean|conflict|error`, explicit `git commit` with the sync message and App identity as in the rebase arm, publish via `wc_sync_from_main.py publish-refspec` and plain `git push`. Existing rebase steps get `if: inputs.sync-method != 'merge'` only where required, with no change to their text.
- [X] T013 [US1] In `.github/workflows/rebase.yml`, make the matrix-leg `name:` switch on the method: `Sync spec branch with main ({0}, {1}, {2})` under `merge`, the unchanged `rebase ({0}, {1}, {2})` otherwise; step-summary prefix reads `sync-from-main` under merge (FR-007, research D3).
- [X] T014 [US1] Run `python .github/scripts/run-local-gates.py`; fix any gate that byte-compares a comment or step name changed in T011–T013.

**Checkpoint**: A clean merge sync works end to end in fixtures and the workflow has the merge arm.

---

## Phase 4: User Story 2 - The repository chooses its sync method with one switch (Priority: P1)

**Goal**: Unset or `rebase` keeps today's behaviour; `merge` selects the new arm; an invalid value fails before any branch is touched.

**Independent Test**: Run `validate-method` and the workflow's discover step with unset, `rebase`, `merge`, and a bogus value; the bogus value fails the discover job with the contract's error text and no matrix leg runs.

### Tests for User Story 2

- [X] T015 [P] [US2] Extend `.github/scripts/verify-rebase-discover-selection.py` (or a case in `.github/scripts/verify-sync-from-main.py`) so discovery selects the same branches for `rebase` and `merge`, and a bogus `sync-method` fails before `Select in-flight branches` (FR-005, FR-009, FR-012).
- [X] T016 [P] [US2] Add a wrapper check in `.github/scripts/verify-sync-from-main.py` that fails if `.github/workflows/rebase.yml` contains `vars.` for the sync switch, and fails unless `.github/workflows/wing-commander-rebase.yml` passes `sync-method: ${{ vars.WING_COMMANDER_SPEC_BRANCH_SYNC || 'rebase' }}` (FR-006, constitution VII).

### Implementation for User Story 2

- [X] T017 [US2] In `.github/workflows/rebase.yml` `discover` job, add a first step after checkout that calls `python .github/scripts/wc_sync_from_main.py validate-method "${{ inputs.sync-method }}"` (pass via env, not interpolated into the script) and fails the job on exit 1, before `Select in-flight branches`.
- [X] T018 [US2] In `.github/workflows/wing-commander-rebase.yml`, pass `sync-method: ${{ vars.WING_COMMANDER_SPEC_BRANCH_SYNC || 'rebase' }}` to the stage.
- [X] T019 [US2] Add the single-home check to `.github/scripts/verify-single-home-idioms.py`: method validation and the merge scope check live only in `wc_sync_from_main.py`, and no other workflow or script carries a copy.
- [X] T020 [US2] Run `python .github/scripts/run-local-gates.py`.

**Checkpoint**: Switch selects the method; unset behaviour is unchanged (SC-004).

---

## Phase 5: User Story 3 - Conflicts are resolved, verified and escalated the same way as today (Priority: P2)

**Goal**: Agent resolves a merge conflict; deterministic `verify-scope` decides publish vs escalate; escalation uses `rebase:blocked`.

**Independent Test**: Fixture with conflicting branch and `main` edits: in-scope resolution passes; out-of-scope path, leftover markers, wrong parents, or unhealthy verdict each fail with a reason and nothing is published.

### Tests for User Story 3

- [X] T021 [P] [US3] Add fixture cases in `.github/scripts/verify-sync-from-main.py` for `verify-scope`: resolution within the manifest passes; a resolution changing a path outside the manifest relative to the `git merge-tree --write-tree` tree fails; a textually clean change to a non-conflict file fails; a manifest file with `^(<<<<<<<|=======|>>>>>>>)( |$)` still present fails; HEAD with wrong first/second parent or an extra commit fails; unhealthy verdict fails; project-folder narrowing excludes paths outside the project (spec 114).
- [X] T022 [P] [US3] Add mutation cases in `.github/scripts/verify-sync-from-main.py` that disable each `verify-scope` guard in turn and assert the gate then fails (as `verify-rebase-discover-selection.py` does).

### Implementation for User Story 3

- [X] T023 [US3] Implement `verify-scope --before --main --conflicted-tree --manifest --project --verdict` in `.github/scripts/wc_sync_from_main.py` per research D5: parents check, `git diff --name-only <conflicted-tree> HEAD^{tree}` ⊆ manifest (project-narrowed), marker scan of manifest paths in HEAD, verdict `healthy`; print each failure reason to stderr, exit 1.
- [X] T024 [US3] In `.github/workflows/rebase.yml` merge arm, on `conflict` record `git merge-tree --write-tree --no-messages origin/$DB HEAD` as the conflicted tree and seed the conflict manifest; reuse the existing containment composite for project narrowing.
- [X] T025 [US3] In `.github/workflows/rebase.yml`, add the merge-arm conflict agent step reusing `wing-commander-tool-args` (default allowed tools `Read,Edit,Grep,Glob,Bash(git status:*),Bash(git diff:*),Bash(git add:*),Bash(git merge --continue:*),Bash(git merge --abort:*)`), the same `inputs.model`, `--max-turns`, turn-ceiling and agent-verdict composites, and a merge-analogue prompt (research D7). The agent gets no `git commit`, `git push`, or `gh`.
- [X] T026 [US3] In `.github/workflows/rebase.yml`, add the merge-arm verify step calling `wc_sync_from_main.py verify-scope` and setting `push`/`escalate` outputs as the rebase arm does; publish only on pass.
- [X] T027 [US3] In `.github/workflows/rebase.yml` `Abandon and escalate`, run `git merge --abort` under merge, keep label `rebase:blocked` and the `<!-- wing-commander-rebase: blocked … -->` marker unchanged, and use the merge prose (heading "Spec branch sync needs a human", remedy `git merge origin/$DB` and push, callout summary "Merge main into this branch") only under `merge` (FR-008, research D8).
- [X] T028 [US3] Confirm the metrics, execution-log, cost-line, over-budget and verdict steps in `.github/workflows/rebase.yml` also run for the merge arm with no pasted copies (FR-010); reuse `wing-commander-metrics-summary`.
- [X] T029 [US3] Run `python .github/scripts/run-local-gates.py`, and the `review-step-gating` and `container-shell-safety` skills over the `rebase.yml` diff.

**Checkpoint**: Every conflict ends in a verified published sync commit or an escalation (SC-005).

---

## Phase 6: User Story 4 - History-derived signals keep working under merge sync (Priority: P2)

**Goal**: Convergence signals and finalize fold range resolve across sync commits; main-side commits are not attributed to the lifecycle; rebase reports an explicit n/a reason.

**Independent Test**: Convergence fixture with a sync commit between two review rounds reports share and churn with values and attributes `main`-side commits to base.

### Tests for User Story 4

- [X] T030 [P] [US4] Add a fixture under `.github/scripts/wc_convergence_tests/`: two review rounds with a sync commit (merge of `main`) between them; assert share and churn are values, not n/a, and commits reachable from the sync commit's second parent are attributed to `base`, not `passK` (FR-011, SC-003).
- [X] T031 [P] [US4] Add a fixture under `.github/scripts/wc_convergence_tests/` where a sync commit carries a conflict resolution: resolution lines count as lifecycle work, lines taken from `main` do not (`diff_size`/`diff_fingerprint` against `git merge-base(base, head)`).
- [X] T032 [P] [US4] Add a fixture under `.github/scripts/wc_convergence_tests/` for the rebase path: after a rebase, share and churn cells read `n/a — rebase rewrites history; merge sync avoids it` and #1062's stored per-round diff size still feeds growth (FR-014).
- [X] T033 [P] [US4] Add a fixture asserting finalize's fold range `range_start..tip` resolves across a sync commit and `fold(` subject grep excludes the sync merge commit (SC-006); locate finalize's fold-range code first (`grep -rn "fold(" .github/`) and place the fixture beside its existing tests.

### Implementation for User Story 4

- [X] T034 [US4] Spike in `.github/scripts/wc_convergence.py`: confirm whether `Origins` can express main-side attribution from the sync commit's second parent without a new input; if not, fall back to taking `--base` as the latest `main` tip (research D9). Record the choice in a code comment.
- [X] T035 [US4] Implement main-side attribution in `Origins` in `.github/scripts/wc_convergence.py`: a commit that is an ancestor of the latest recorded `main` tip and not first-parent reachable from the branch's own work is `base`.
- [X] T036 [US4] In `.github/scripts/wc_convergence.py` `render_handoff` and the n/a cells, replace the "(the branch was rebased or force-pushed)" prose with `rebase rewrites history; merge sync avoids it`; add no new rebase workaround (FR-014).
- [X] T037 [US4] Make the T033 fold-range fixture pass; change finalize only if the fixture shows the range does not resolve.
- [X] T038 [US4] Run the convergence tests and `python .github/scripts/run-local-gates.py`.

**Checkpoint**: All four stories work; history consumers are merge-aware.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T039 [P] Update `docs/adoption.md` `### rebase`: open with the layer (published contract), add the `sync-method` input row and the merge side-effect row, and state the squash-merge assumption as documentation only (FR-013, FR-015).
- [X] T040 [P] Update `docs/architecture.md` Rebase section: add a "Merge sync" subsection with the linear-vs-stable-history trade-off, the FR-012 switch-back limit, and its layer.
- [X] T041 [P] Add `WING_COMMANDER_SPEC_BRANCH_SYNC` (default `rebase`, values `rebase`/`merge`) to the variable list in `docs/setup.md`, naming it as consuming-instrument layer.
- [X] T042 Walk `specs/118-spec-branch-sync-from-main/quickstart.md` against the finished code and fix any doc or code drift found.
- [X] T043 Run the full suite `python .github/scripts/run-local-gates.py` and confirm green.

---

## Phase 8: Maintainer follow-up

- [ ] T044 [maintainer] Merge the implementation PR (it touches `.github/workflows/`, so the merge needs a token with the `workflow` scope).
- [ ] T045 [maintainer] Set the repository variable `WING_COMMANDER_SPEC_BRANCH_SYNC` to `merge` on a test repository, then dispatch `wing-commander-rebase.yml` and confirm a clean sync commit is published without a force-push.
- [ ] T046 [maintainer] Post-merge proof: re-drive a conflicting-branch run in `merge` mode and an unset-variable run, and record the evidence on #1074 (use the `prove-after-merge` skill).

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 (blocks all stories) → US1 and US2 (both P1; US2's T017/T018 need the `sync-method` input from T011, so do US1 T011 first) → US3 (needs US1 merge arm in `rebase.yml`) → US4 (independent of workflow work; needs only git fixtures, can run parallel with US3) → Polish → Maintainer follow-up.
- Within a story: fixtures first and failing, then helper code, then workflow steps.
- All `rebase.yml` tasks edit one file and run sequentially (T011–T013, T017, T024–T028, T027).

### Parallel Opportunities

- T007, T008, T009 together; T015, T016 together; T021, T022 together; T030–T033 together; T039–T041 together.
- US4 (`wc_convergence.py` and its tests) can proceed alongside US3 once Phase 2 is done.

## Implementation Strategy

**MVP**: Phases 1–4 (Setup, Foundational, US1, US2): the switch plus clean-merge sync, which delivers the stable-history benefit for non-conflicting branches. Add US3 for conflicts before enabling it on a busy repository, then US4 for the downstream signals. Keep concurrent local agents to two.
