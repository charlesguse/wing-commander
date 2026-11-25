# Tasks: Faster PR Lint — Parallelise the Gate Suite in CI

**Input**: `specs/129-parallel-pr-lint/` (spec.md, plan.md, research.md, data-model.md, contracts/lint-workflow-layout.md, quickstart.md)

**Tests**: Constitution VIII requires every new or changed gate to ship `--self-test` with a checked-in fixture per failure branch, so self-test tasks are included.

**Organization**: by user story. All paths are repository-relative. Workflow comments are byte-compared by gates: treat comment edits as code edits.

Standing guidance (prose, not tasks): run `python .github/scripts/run-local-gates.py` before pushing; a change touching an `if:`, `continue-on-error:` or failing step gets a `review-step-gating` pass; a `container:` job or a `run:` step inside one gets a `container-shell-safety` pass. Speeding up individual slow gates is out of scope (FR-012).

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup (inventory)

- [ ] T001 Inventory the current `lint` job in `.github/workflows/lint-workflows.yml`: list every step that installs tools or builds a fixture later gates read (R5), every step with no `!cancelled()` guard (the 70 of FR-009), and every consumer of `jobs.lint` structure or step names (grep `.github/scripts/` for `lint-workflows.yml`, `jobs["lint"]`, `wc_lint_gate_source`). Record the findings as a comment block at the top of the implementing PR description, not in a repo file.
- [ ] T002 Capture the baseline gate set: the step-name list of `lint` and `harness-tests` from `.github/workflows/lint-workflows.yml` and the list `python .github/scripts/run-local-gates.py` derives, for the SC-002 before/after comparison (kept in the PR description).
- [ ] T003 Capture per-gate durations from `run-local-gates.py` timing output (2026-11-24 baseline, ~2263 s summed) to drive the shard balancing in T011.

---

## Phase 2: Foundational (blocking)

**Purpose**: changes that must land before the job is split.

- [X] T004 Rename the second `Gate 23 self-test — the detector actually detects` step in `.github/workflows/lint-workflows.yml` so every PR-time step name is unique (R4, Key Entities); update every gate that reads that step name (found in T001, e.g. `.github/scripts/verify-gate-wiring.py`, `verify-gate-22*.py`, `verify-gate-23*.py`) and their fixtures.
- [ ] T005 [P] If T001 found setup/fixture steps shared by several gates, move them into a composite action under `.github/actions/` and call it from the job (single-home rule, R5); otherwise record "none" in the PR description.
- [ ] T006 [P] In `.github/scripts/wc_gate_registry.py`, make `pr_time_gates` exclude the aggregate job named `lint` by name (R6); update its self-test with a fixture where the aggregate job carries a `run:` step and is excluded.
- [ ] T007 Add `if: ${{ !cancelled() }}` to every step lacking a survivable guard in `.github/workflows/lint-workflows.yml` except checkout, and guard each self-test step `!cancelled() && steps.<gate id>.outcome != 'failure'` with an `id:` on its paired gate step, paired by step name (FR-009, R3). Run the gate suite and fix any gate that byte-compares the changed text.

**Checkpoint**: single `lint` job still green locally, names unique, isolation in place.

---

## Phase 3: User Story 1 — Verdict within 10 minutes (P1) 🎯 MVP

**Goal**: the suite runs as 8 shard jobs plus `harness-tests`, with the same gates, each its own step.

**Independent Test**: on a PR touching a workflow, the set of step names across units equals the T002 baseline (plus no duplicates) and the aggregate completes ≤ 10 min.

- [ ] T008 [US1] Compute the shard assignment: greedy-balance the gate steps (with each self-test kept adjacent to its gate, and fixture-sharing gates together) across 8 groups using the T003 durations; the result exists only as step placement (FR-007), so keep any scratch table out of the repo.
- [X] T009 [US1] In `.github/workflows/lint-workflows.yml`, replace job `lint` with jobs `lint-shard-1` … `lint-shard-8`, each with `if: github.event_name == 'pull_request'`, `contents: read` permissions, the same runner and checkout/setup as today (or the T005 composite), and its assigned steps moved verbatim (FR-001, FR-006).
- [X] T010 [US1] Add the aggregate job `lint` (`name: lint`, `needs:` all eight shards and `harness-tests`, `if: always() && github.event_name == 'pull_request'`) whose single step fails unless every `needs.<job>.result` is exactly `success` and prints each non-success job by name (FR-003, FR-004, FR-004a, R2). Keep the workflow `name: lint · workflows`.
- [ ] T011 [US1] Re-balance if local per-shard sums from T003 exceed ~300 s for any shard (move whole gate+self-test pairs only); confirm the floor shard (Gate 97 self-test, 156 s) fits.
- [ ] T012 [P] [US1] Adapt `.github/scripts/verify-lint-supersedes-pr-runs.py` and every other gate that read the single `lint` job's `if`, `steps` or concurrency (list from T001) so each finds its subject across the shard jobs and cannot pass vacuously (FR-008); extend each one's self-test with a fixture for the sharded layout.
- [ ] T013 [US1] Run `python .github/scripts/run-local-gates.py` and compare the executed gate set with T002 (SC-002: none dropped, none duplicated).

**Checkpoint**: MVP — sharded suite, aggregate in place.

---

## Phase 4: User Story 2 — Verdict readers keep working (P1)

**Goal**: the aggregate is never green by omission and never changes main's run conclusion.

**Independent Test**: `verify-lint-aggregate.py --self-test` simulates every result combination and event.

- [X] T014 [US2] Create `.github/scripts/verify-lint-aggregate.py`: parse the aggregate job from `.github/workflows/lint-workflows.yml` and, using `wc_gha_expr.py`, simulate its `if:` and step for needs results success/failure/cancelled/skipped/in-progress on `pull_request` (must run and conclude failure unless all `success`) and on `push`/`schedule`/`workflow_dispatch` (must be skipped) (contract items 4, 5, 9).
- [X] T015 [US2] Add `--self-test` to `.github/scripts/verify-lint-aggregate.py` with checked-in fixtures (under the existing gate fixture directory convention) for each failure branch: `if:` using `!cancelled()`, missing `always()`, skip-tolerant result check, aggregate that does not list `harness-tests`.
- [X] T016 [US2] Register the new gate as its own step in a shard job of `.github/workflows/lint-workflows.yml` (with its self-test step, guarded per T007) and in whatever gate registry/index the existing gates use (see `.github/scripts/wc_gate_registry.py` and `verify-gate-wiring.py` expectations).
- [ ] T017 [P] [US2] Verify the verdict readers (`board_readiness.gate_suite_green`, `lifecycle_readiness`'s copy, `lifecycle_merge_preconditions.gate_suite_green_in_rollup`, `wc_board_status.py`) still match check-run `lint` / workflow `lint · workflows` / file `lint-workflows.yml`; add a regression test in the existing test module of each reader only if one lacks coverage of a skipped-vs-failure `lint` check.
- [ ] T018 [US2] Pass the changed workflow through the `review-step-gating` skill (aggregate `always()` vs `!cancelled()`, cancelled-run behaviour per R2) and fix findings in this PR.

---

## Phase 5: User Story 3 — Local and CI stay the same suite (P2)

**Goal**: `run-local-gates.py` derivation equals the union over units, enforced.

**Independent Test**: adding a gate to any shard appears in the local list with no second edit.

- [ ] T019 [US3] Create `.github/scripts/verify-lint-shard-layout.py` enforcing contract items 1–3, 6, 7 and 8: workflow name; exactly one job named `lint`; every PR-time job other than the aggregate is in the aggregate's `needs` and every `needs` entry exists; step names unique; no gate invocation (script + args) in two units; every non-checkout step has a survivable guard, self-tests paired by step name; `pr_time_gates` output equals the union of gate invocations across units, aggregate exempt by name (FR-005, FR-007, FR-009).
- [X] T020 [US3] Add `--self-test` to `.github/scripts/verify-lint-shard-layout.py` with a fixture per failure branch (unit not under aggregate, aggregate lists missing job, shard named `lint`, duplicate step name, gate in two units, unguarded step, self-test guard paired to the wrong gate, derived/union divergence).
- [ ] T021 [US3] Register `verify-lint-shard-layout.py` and its self-test as steps in `.github/workflows/lint-workflows.yml` (guarded per T007) and confirm `.github/scripts/run-local-gates.py` derives both with no edit to its source beyond any exemption T006 requires (FR-005); if `run-local-gates.py` needs an aggregate exemption by name, add it there with a self-test case.
- [ ] T022 [US3] Confirm US3 scenario 2: temporarily move one gate step between shards locally and check `python .github/scripts/run-local-gates.py` lists it unchanged and `verify-lint-shard-layout.py` stays green (not committed).

---

## Phase 6: User Story 4 — Failing gate easy to find (P2)

**Goal**: red run names the failed unit; the failing gate is its own failed step.

**Independent Test**: simulated failure output lists the failed job id.

- [X] T023 [US4] In the aggregate step of `.github/workflows/lint-workflows.yml`, also write the non-success unit names and their results to `$GITHUB_STEP_SUMMARY` (Principle III), and extend the `verify-lint-aggregate.py` self-test to assert the failure message names each non-success unit (SC-005).

---

## Phase 7: Polish & cross-cutting

- [ ] T024 [P] Update `docs/reference.md` where it describes the lint job, its check names and limits: shard jobs, aggregate `lint`, `harness tests` as a unit, the new gates, the 10-minute target (FR-011); follow `docs/reference.md`'s own rule for which changes must update it.
- [ ] T025 [P] Add a "single home" check if any shared logic was consolidated (T005) to the nearest existing gate (CLAUDE.md "Shared logic has exactly one home").
- [ ] T026 Run `python .github/scripts/run-local-gates.py` to green on the final tree, then validate against `specs/129-parallel-pr-lint/quickstart.md`.

---

## Phase 8: Maintainer follow-up

- [ ] T027 [maintainer] Merge the workflow-touching PR with a token holding the `workflow` scope (`gh auth refresh -h github.com -s workflow`).
- [ ] T028 [maintainer] Post-merge proof (`prove-after-merge` skill): re-drive a `pull_request` run and a `workflow_dispatch`/push run of `lint-workflows.yml`; confirm main's run concludes success with units and aggregate skipped, and record evidence on the PR (SC-003, FR-004).
- [ ] T029 [maintainer] Run the deliberate-failure drill (break one gate per unit, cancel one unit) and confirm every verdict reader reports not-ready; record the evidence on the PR (SC-003).
- [ ] T030 [maintainer] Check the first ten green first-attempt PR runs for aggregate `lint` completion ≤ 10 min from `run_started_at` (SC-001) and record the result on issue #1198.
- [ ] T031 [maintainer] Read branch protection's required checks and confirm `lint` remains the required name; change nothing if so.

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → US1 (Phase 3) → US2 (4) and US3 (5) → US4 (6) → Polish → Maintainer follow-up.
- T004 and T007 edit the same workflow; run them sequentially. T005, T006 are [P] with each other.
- US2 and US3 both add steps to the workflow (T016, T021): serialise those two edits; the scripts (T014/T015, T019/T020) are parallel.
- T023 depends on T010 and T014.

## Parallel Examples

- After T004: T005 and T006 together.
- US2/US3 scripts: T014+T015 alongside T019+T020 (different files); T012 and T017 alongside either.
- Polish: T024 and T025 together.

## Implementation Strategy

MVP = Phases 1–3 plus T014–T016 from US2: a sharded suite whose aggregate cannot go green by omission. Nothing should merge without US2's aggregate gate, since Principle VIII makes the aggregate the whole point of the split. Then US3's layout gate, US4's summary, docs, and the maintainer proof.
