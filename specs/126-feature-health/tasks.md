# Tasks: Feature Health

**Input**: Design documents from `/specs/126-feature-health/` (plan.md, spec.md, research.md, data-model.md, contracts/feature-health-report.md, quickstart.md)

**Tests**: The plan requires fixtures for every state and rule (quickstart.md step 1) and for each failed read, so fixture tasks are included. Each fixture must fail without the code it tests.

**Organization**: Grouped by user story. Scripts live in `.github/scripts/`; fixtures in `.github/scripts/fixtures/feature-health/`.

Guidance (prose, not tasks): run `python .github/scripts/run-local-gates.py` before pushing. Workflow comments are load-bearing; treat edits as code edits. Never reference private downstream consumers. The implement stage must not create or edit `fixtures/feature-health/sc001/corpus.json` or `expected.json`.

## Phase 1: Setup

- [X] T001 Create the fixtures directory `.github/scripts/fixtures/feature-health/` with a README-free `.gitkeep`-equivalent first fixture file `cases.json` skeleton (empty list of cases) in `.github/scripts/fixtures/feature-health/cases.json`
- [X] T002 [P] Create `.github/scripts/wc_feature_health.py` skeleton: module docstring, constants for state order (data-model.md "Health state"), called-out set, default quiet days 14, window days 30, marker `<!-- wing-commander-feature-health -->`
- [X] T003 [P] Create `.github/scripts/verify-feature-health.py` skeleton following `verify-proof-list.py`'s structure (fixture runner entry point, `EXEMPT_UNREGISTERED` and `EXEMPT_SC001_PENDING` tables passed as parameters, each citing #889)

---

## Phase 2: Foundational (blocking)

- [X] T004 Write the registry `.github/scripts/feature-health-registry.json` covering every feature in FR-001 (lifecycle with stages intake, clarify, plan, tasks, implement, finalize, cleanup; spec PR review; lifecycle review gate; PR conversation; board loop; watchdog; auto-release; Spec Kit updater; rebase; metrics; board status; proof list; private-image dogfood; gate suite), with fields per data-model.md `Registry entry.name`, `.workflows`, `.kill_switch`, `.requires_var`, `.signal`, `.quiet_days`, and `Workflow ref.cadence`/`.stage`; signals per FR-003 using `Signal.kind` values from data-model.md, referencing marker/branch/ground constants by name from the scripts that own them (`board_triage.py` for the triage grounds)
- [X] T005 Implement registry-drift checks in `.github/scripts/verify-feature-health.py` (research D2, contract "Registry file contract"): every row of reference.md's "At a glance", "Housekeeping and observability" and "Schedules" tables has an entry or is in `EXEMPT_UNREGISTERED`; each `Workflow ref.file` exists in `.github/workflows/`; each `Registry entry.kill_switch` is in reference.md's Kill switches table; `Registry entry.name` unique; `Registry entry.quiet_days` ≥ 1; `Signal.kind` in the allowed set
- [X] T006 [P] Add failing-registry fixtures (reference.md lists a feature the registry lacks; missing workflow file; unknown kill switch; duplicate name; `quiet_days` 0) under `.github/scripts/fixtures/feature-health/registry/` and wire them into `.github/scripts/verify-feature-health.py` (SC-007)
- [X] T007 Add the unnumbered `verify-feature-health.py` step to `.github/workflows/lint-workflows.yml`, in the style of the `verify-proof-list.py` step (derived by `wc_gate_registry`)

**Checkpoint**: registry and drift gate exist.

---

## Phase 3: User Story 1 - See quiet or failing features at a glance (P1) 🎯 MVP

**Goal**: pure classifier and renderer produce one state per feature and the Board-status section.

**Independent Test**: fixtures with one failing, one quiet, one healthy feature classify as such and the first two are called out.

- [X] T008 [US1] Implement `classify_workflow` in `.github/scripts/wc_feature_health.py` per data-model.md rules 1-8 (unreadable, paused, not configured, failing over last 3 qualifying runs per FR-005, not running per FR-006, quiet per FR-007 with `Registry entry.quiet_days` default 14, idle per FR-017, healthy), taking readings and an injected `now`; skipped/cancelled count toward cadence only
- [X] T009 [US1] Implement `classify_feature` in `.github/scripts/wc_feature_health.py`: worst-of across `Registry entry.workflows`, ignoring *idle* workflows when a sibling has a qualifying run, *idle* only if all are, lifecycle stage rows carrying their own state (FR-018)
- [X] T010 [US1] Implement `render_section` in `.github/scripts/wc_feature_health.py` exactly per contracts/feature-health-report.md "Section layout" (header, call-outs sorted by state order then name, collapsed table, stage rows beneath lifecycle, `never in window`, `not measured`, threshold shown, unreadable count; every feature exactly once; byte-deterministic)
- [X] T011 [US1] Add one fixture per state and rule listed in quickstart.md step 1 (healthy, idle, quiet, not running, failing with and without a single failure between successes, paused with green runs, not configured, skipped/cancelled run handling, worst-of and idle-sibling rules, lifecycle stage rows) in `.github/scripts/fixtures/feature-health/cases.json`, and run them from `.github/scripts/verify-feature-health.py`
- [X] T012 [US1] Add renderer fixtures (call-outs, "Nothing needs a look.", date formats, stage row ordering, over-size table drop with "table shortened") in `.github/scripts/fixtures/feature-health/render/` and check them in `.github/scripts/verify-feature-health.py`

**Checkpoint**: classification and rendering are verified offline.

---

## Phase 4: User Story 2 - "Did its job" measured per feature (P1)

**Goal**: declared output signals are read from the repository's own records and drive *quiet*.

**Independent Test**: all-success runs with a never-seen signal are not *healthy*; a feature with no signal says "not measured".

- [X] T013 [US2] Implement the signal readers per `Signal.kind` (`merged_pr`, `release`, `issue_or_comment`, `triage_close`, `branch_commit`, `issue_updated`, `issue_section`) in `.github/scripts/wc_feature_health.py`, importing triage grounds from `board_triage.py` and other markers/prefixes from their owning scripts rather than copying; a duplicate close at the route step does not count (FR-003)
- [X] T014 [US2] Add fixtures per signal kind (occurred, never seen, board-loop duplicate close not counted, no signal declared → "not measured") in `.github/scripts/fixtures/feature-health/signals/` and check them in `.github/scripts/verify-feature-health.py`
- [X] T015 [US2] Add determinism fixture (same input and `now` twice gives byte-identical output, SC-003) to `.github/scripts/verify-feature-health.py`

---

## Phase 5: User Story 3 - Unread never looks healthy (P2)

**Goal**: failed reads yield *unreadable* per feature; all-unreadable fails the build.

**Independent Test**: a failing run read marks only that feature unreadable and the report counts it.

- [X] T016 [US3] Implement the date-sliced run reader in `.github/scripts/wc_feature_health.py` (`collect`): per workflow, date-bounded listing at `per_page=100`, sliced by day past the 1,000-run cap, else `{"unreadable": reason}`; check `rate_limit` first and fail below a floor (research D4, FR-011); window covers the longest `Registry entry.quiet_days` and at least 30 days
- [X] T017 [US3] Implement switch and `Registry entry.requires_var` reads in `collect`, reusing `wc_board_status._switch_on` and `SWITCH_ENV` (not reimplemented); a failed read gives `"unreadable"` for that feature only (FR-010)
- [X] T018 [US3] Implement `build` in `.github/scripts/wc_feature_health.py`: collect, classify, render; exit non-zero with a clear message when every feature's run history is unreadable (FR-010)
- [X] T019 [US3] Add failure-branch fixtures using `wc_shell_harness.gh_error_stub_arm` (run read fails, over-cap read cannot be bounded, signal query fails, switch read fails, variable read fails, rate limit below floor, all-unreadable build fails, other features still classified, unreadable count reported) in `.github/scripts/fixtures/feature-health/unreadable/`, checked by `.github/scripts/verify-feature-health.py` (SC-006)

---

## Phase 6: User Story 4 - Shown, not filed (P3)

**Goal**: the workflow publishes by hand-off, read-only, and files nothing.

**Independent Test**: the workflow file has no write permissions, no agent, no dispatch, and the gate fails if it gains any.

- [X] T020 [US4] Create `.github/workflows/wing-commander-feature-health.yml`: daily 06:29 UTC plus `workflow_dispatch`, refuse non-default-branch dispatch first, pause step on `WING_COMMANDER_FEATURE_HEALTH_PAUSED`, `actions/checkout@v5` with `persist-credentials: false`, build with `GH_TOKEN: ${{ github.token }}`, upload artifact `feature-health-section`, read-only permissions (`contents`, `actions`, `issues`, `pull-requests`), own concurrency group, 15-minute timeout, later steps gated by `success()` only (no `always()`)
- [X] T021 [US4] Add workflow-file checks to `.github/scripts/verify-feature-health.py`: no write permission, no agent/Claude step, no `gh` write verbs (comment, label, close, edit, workflow run), artifact name equals the constant in `wc_board_status.py` (FR-012, FR-013)
- [X] T022 [US4] Add `feature_health_snapshot()`, the `SWITCH_ENV` entry for `WING_COMMANDER_FEATURE_HEALTH_PAUSED`, the artifact-name constant and the section render to `.github/scripts/wc_board_status.py`, with statuses `built`, `paused`, `failed`, `never`, `unreadable`, last-good date and the 48h stale notice per contracts/feature-health-report.md "Writer statuses", mirroring the proof-list hand-off
- [X] T023 [US4] Add the `WING_COMMANDER_FEATURE_HEALTH_PAUSED` env line to `.github/workflows/board-status.yml`
- [X] T024 [US4] Extend `.github/scripts/verify-board-status.py`: `SNAP` gains `feature_health`, fixtures for every writer status and the stale notice, error stubs via `wc_shell_harness.gh_error_stub_arm`, artifact name checked against the upload step
- [X] T025 [US4] Perform a `review-step-gating` skill pass over `.github/workflows/wing-commander-feature-health.yml` and the `.github/workflows/board-status.yml` change; fix findings in those files

---

## Phase 7: SC-001 replay and docs

- [X] T026 Add the SC-001 replay check to `.github/scripts/verify-feature-health.py`, reading `fixtures/feature-health/sc001/corpus.json` and `expected.json`, with `EXEMPT_SC001_PENDING` citing #889 while the corpus is absent (research D9); do not create either file
- [X] T027 [P] Update `docs/reference.md`: board-status row (feature-health section), new Housekeeping row, Kill switches entry, Schedules 06:29, "At a glance" (FR-016)
- [X] T028 [P] Update `docs/setup.md` §3 with a row for `WING_COMMANDER_FEATURE_HEALTH_PAUSED`, and `README.md` workflow list with the new workflow
- [X] T029 Run `python .github/scripts/run-local-gates.py` and fix failures in the files this feature touched

---

## Phase 8: Maintainer follow-up

- [ ] T030 [maintainer] Capture the SC-001 corpus and expected file (`.github/scripts/fixtures/feature-health/sc001/corpus.json`, `expected.json`) from a local session with full history and `gh` auth, scrubbing private names, and delete `EXEMPT_SC001_PENDING`'s entry in the same commit
- [ ] T031 [maintainer] Create repository variable `WING_COMMANDER_FEATURE_HEALTH_PAUSED` only if wanted
- [ ] T032 [maintainer] After merge, dispatch `wing-commander-feature-health.yml` on the default branch, then `board-status.yml`, and record the proof listed in quickstart.md step 3

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → stories. US1 (T008-T012) is the base; US2, US3 depend on `wc_feature_health.py` from US1; US4 depends on `build` (T018).
- Files shared (`wc_feature_health.py`, `verify-feature-health.py`) mean most tasks there are sequential; [P] marks only distinct-file tasks.
- Phase 7 after US4; Phase 8 after merge.

## Parallel Example

T002, T003 together; T027, T028 together.

## Implementation Strategy

MVP = Phases 1-3 (registry, drift gate, classifier, renderer, fixtures): the verifiable core. Then US2 signals, US3 reads, US4 publication and docs, then maintainer follow-up.

## Counts

32 tasks: Setup 3, Foundational 4, US1 5, US2 3, US3 4, US4 6, SC-001/docs 4, Maintainer 3.
