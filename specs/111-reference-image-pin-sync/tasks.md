# Tasks: Reference-Image Pin Sync on Rebuild

**Input**: Design documents from `/specs/111-reference-image-pin-sync/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/pin-sync-script.md, quickstart.md

**Tests**: The plan requires a fixture-driven gate (`verify-reference-image-pin-sync.py`) running the script against a stubbed `gh`; fixture tasks are included and written before the script behaviour they cover.

**Organization**: Grouped by user story. The script (`sync-reference-image-pin.sh`) and gate are single files, so tasks touching one file are sequential.

## Format: `[ID] [P?] [Story] Description`

## Path Conventions

- Script: `.github/actions/_shared/sync-reference-image-pin.sh`
- Workflow: `.github/workflows/wing-commander-e2e-reference-image.yml`
- Gate: `.github/scripts/verify-reference-image-pin-sync.py`; fixtures: `.github/scripts/tests/reference-image-pin-sync/`
- Gate registration: `.github/workflows/lint-workflows.yml`

---

## Phase 1: Setup

- [x] T001 Confirm spec 112's agent start-up check is present in `.github/workflows/wing-commander-private-image-dogfood.yml` and dispatched by `startup-check` in `.github/workflows/wing-commander-e2e-reference-image.yml`; if absent, stop (spec Assumptions: no pin may be written without it)
- [x] T002 [P] Create the stubbed-`gh` fixture scaffold in `.github/scripts/tests/reference-image-pin-sync/` (a stub `gh` executable that replays per-case canned responses for `api user/repos`, `api repos/<r>/actions/variables/...`, `variable get`, `variable set`, `run list`, and records every invocation to a log)

---

## Phase 2: Foundational

**Purpose**: Script skeleton and gate harness all stories build on.

- [x] T003 Create `.github/actions/_shared/sync-reference-image-pin.sh` (`set -euo pipefail`) reading env `SYNC_TOKEN`, `IMAGE`, `DIGEST`, `THIS_REPO`, `E2E_REPO`, `CHECKS_PASSED`, `RUN_NUMBER`, `OUTCOME_FILE`, `GITHUB_STEP_SUMMARY` per contracts/pin-sync-script.md; build the sync set (this repo, plus `E2E_REPO` when non-empty, case-insensitive); implement outcome-JSON writing (array of `{repo,status,reason,held,expected}`) and the summary-table append (FR-008); never echo `SYNC_TOKEN`; export it as `GH_TOKEN` only for the script's own `gh` calls
- [x] T004 Create `.github/scripts/verify-reference-image-pin-sync.py` harness: runs the script with the stub `gh` on `PATH` for a named fixture case, parses `OUTCOME_FILE`, asserts exit code, outcomes, the set of recorded writes, and that the token value appears nowhere in stdout/stderr/summary/outcome file
- [x] T005 Register the gate in `.github/workflows/lint-workflows.yml` so `python .github/scripts/run-local-gates.py` picks it up

**Checkpoint**: Harness runs an empty case.

---

## Phase 3: User Story 1 - A rebuild keeps both pins current (Priority: P1) 🎯 MVP

**Goal**: After both checks pass, both pins are written (or reported already current) and the summary says so.

**Independent Test**: Fixture cases all-current, both-written, checks-failed, E2E-unset pass; re-driving a build after merge leaves both variables equal to `<image>@<digest>`.

### Fixture cases (write first, expect failure)

- [x] T006 [US1] Add gate cases in `.github/scripts/verify-reference-image-pin-sync.py` with fixtures: `both-written` (two `variable set WING_COMMANDER_CONTAINER_IMAGE` calls, statuses `written`), `all-current` (no writes, statuses `current`), `checks-failed` (`CHECKS_PASSED=false` → every repo `skipped` "image check did not pass", exit 0, no API call), `e2e-unset` (this repo only written, E2E skipped "no test repository configured", exit 0), `superseded` (higher-numbered successful run → `skipped`, exit 0)

### Implementation

- [x] T007 [US1] In `.github/actions/_shared/sync-reference-image-pin.sh` implement contract steps 1, 3, 5 (read-probe via `gh api repos/<r>/actions/variables/WING_COMMANDER_CONTAINER_IMAGE`) and 6: `CHECKS_PASSED != true` skip; superseded guard using `gh run list --workflow wing-commander-e2e-reference-image.yml --status success` and `RUN_NUMBER`; per repo compare to `<IMAGE>@<DIGEST>` → `current`, else `gh variable set WING_COMMANDER_CONTAINER_IMAGE --repo <r>` as the only write; E2E-unset behaviour (D7)
- [x] T008 [US1] In `.github/workflows/wing-commander-e2e-reference-image.yml` change `startup-check` to find the dispatched run (created after dispatch, matched by digest input/title) and `gh run watch --exit-status` it, exposing job output `passed=true|false` (research D1/D2)
- [x] T009 [US1] In the same workflow add job `sync-pins`: `needs: [build-and-publish, startup-check]` (and the prerequisite-check job if separate), `if: !cancelled()`-style condition that still runs on check failure so skip is reported, `concurrency: {group: reference-image-pin-sync, cancel-in-progress: false}`, least-privilege `permissions`, one step calling the shared script with env from step outputs (digest/regex-validated, never interpolated into shell), `shell: bash` if a `container:` is used (consult the `review-step-gating` skill)
- [ ] T010 [US1] Run `python .github/scripts/run-local-gates.py` until T006 cases pass

**Checkpoint**: MVP — happy path, skip paths and no-op work.

---

## Phase 4: User Story 2 - A failed sync never leaves the pins silently apart (Priority: P1)

**Goal**: Any failure fails the run and files/updates exactly one deduplicated issue.

**Independent Test**: Failure fixtures exit non-zero with correct outcomes; workflow wiring check finds the issue step; repeated failure updates the same issue.

### Fixture cases

- [x] T011 [US2] Add gate cases: `token-unset` (all `failed`, names the credential not its value, no write), `one-write-refused` (one `written`, one `failed` with `held`/`expected`, exit 1), `malformed-digest` (all `failed`, exit 1, no variables API call), `empty-image`, `probe-failed` (no write)
- [x] T012 [US2] Add workflow-wiring assertions in the gate: failure-filing step is guarded to the sync step's failure only, uses `.github/actions/wing-commander-durable-failure-issue` with label `reference-image-sync:failed` and `issues: write`, a later step re-fails the job, and a fully successful sync closes the issue (`operation: close`)

### Implementation

- [x] T013 [US2] In the script implement contract steps 2 and the failure paths of 5–6: validate `DIGEST` against `^sha256:[0-9a-f]{64}$` and non-empty `IMAGE` before any API call; unset/unauthenticated `SYNC_TOKEN` → all `failed`; refused write → `failed` with held and expected; exit 1 iff any outcome is `failed`
- [x] T014 [US2] In `sync-pins` add the `if: failure()` issue step building the body from the outcome JSON (repo, held, expected, reason; no secrets) and calling `wing-commander-durable-failure-issue`; add the close-on-success step and the final re-fail step (research D6); check dedup behaviour matches auto-release's `auto-release:failed` usage
- [x] T015 [US2] Confirm `.github/workflows/auto-release.yml` neither calls nor reads the script and is unmodified (FR-009); add that assertion to the gate
- [ ] T016 [US2] Run `python .github/scripts/run-local-gates.py` until T011–T012 pass

**Checkpoint**: Failures are loud and deduplicated.

---

## Phase 5: User Story 3 - The sync credential reaches exactly what it syncs (Priority: P2)

**Goal**: Writes happen only when the token reaches exactly the sync set.

**Independent Test**: `over-reach` and `under-permission` fixtures produce zero writes; correctly scoped token syncs.

- [x] T017 [US3] Add gate cases: `over-reach` (reachable set includes one extra repo → all `failed` "credential reaches <names>", zero writes, SC-004), `under-permission` (a probe on one sync-set repo fails → zero writes), `exact-reach` (writes proceed), case-insensitive name match
- [x] T018 [US3] In the script implement contract step 4: `gh api user/repos?affiliation=owner,collaborator,organization_member --paginate --jq '.[].full_name'`, compare sorted lower-cased set to the sync set, mismatch → all `failed`, exit 1, before any probe or write; when `E2E_REPO` is empty the set is this repo alone
- [x] T019 [US3] In `sync-pins` pass the secret `WING_COMMANDER_REFERENCE_IMAGE_SYNC_TOKEN` as `SYNC_TOKEN` to the sync step only (no other step receives it)
- [x] T020 [US3] Add a gate assertion that the token secret is referenced only by that step, and the single-home check: no other workflow or `run:` block contains `gh variable set WING_COMMANDER_CONTAINER_IMAGE` (FR-003, CLAUDE.md "one home")

**Checkpoint**: Containment enforced.

---

## Phase 6: Polish & Cross-Cutting

- [x] T021 [P] Update the `WING_COMMANDER_CONTAINER_IMAGE` row in `docs/setup.md` to describe the sync, add a row for `WING_COMMANDER_REFERENCE_IMAGE_SYNC_TOKEN` (Variables write on exactly this repo and the test repo), and what to do when the sync fails; remove the manual "copy the digest" step (FR-011, SC-005)
- [x] T022 [P] Update the header comment of `.github/workflows/wing-commander-e2e-reference-image.yml` to match (workflow comments are gate-checked; treat as code)
- [ ] T023 Run `python .github/scripts/run-local-gates.py` in full; fix any gate that byte-compares the edited comments; run the `review-step-gating` skill on the workflow change
- [x] T024 Walk through `specs/111-reference-image-pin-sync/quickstart.md` fixture steps; note the post-merge proof (`prove-after-merge`: re-drive one build, confirm both variables equal the digest — SC-001) for the PR description

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → stories. T003 before T004; T006/T011/T017 extend the same gate file and script, so US1 → US2 → US3 sequentially (US3 is logically independent but shares files).
- T008 before T009 (needs `passed` output); T009 before T014, T019.
- Polish after all stories; T021 and T022 parallel.

### Parallel Opportunities

T002 with T001; T021 with T022.

## Implementation Strategy

MVP = Phases 1–3 (US1): happy path, skip and no-op. Do not merge MVP alone with a real token wired up: US3 containment (FR-005) should land before the secret is configured. Then US2, US3, polish; prove after merge by re-driving one build.
