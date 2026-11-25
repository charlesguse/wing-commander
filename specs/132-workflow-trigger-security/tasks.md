# Tasks: Workflow security — static-analysis gate, `./` references, trigger docs

**Input**: `specs/132-workflow-trigger-security/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: The spec requires a checked-in fixture for every gate failure branch (FR-006, SC-002), so each gate task ships its `--self-test` fixtures.

**Format**: `- [ ] ID [P?] [Story] Description with path`. Run `python .github/scripts/run-local-gates.py` before pushing; keep the gates green after each phase. Workflow comments are load-bearing (gates byte-compare them): treat comment edits as code edits.

## Phase 1: Setup

- [ ] T001 Create `.github/scripts/zizmor-pin.txt` with `version=1.33.1` and the release asset `sha256` per data-model.md "Analyser pin"
- [X] T002 [P] Create `.github/zizmor.yml`: `rules.self-repository.disable: true` with non-empty `reason`, and `rules.unpinned-uses.config.policies` (`actions/*`, `github/*`, `anthropics/*` → `ref-pin`; `*` → `hash-pin`) per data-model.md "Analyser configuration"
- [X] T003 [P] Create empty-array `.github/scripts/zizmor-findings-waivers.json` conforming to `specs/132-workflow-trigger-security/contracts/findings-register.schema.json`
- [X] T004 [P] Create `.github/scripts/repo-only-reusable-workflows.json` listing `shared-pr-reviewer.yml` (data-model.md "Repo-only reusable workflow list"; FR-016b)

## Phase 2: Foundational

**Purpose**: the zizmor gate skeleton every story's gate registration builds on.

- [X] T005 Implement `.github/scripts/verify-zizmor.py` per `contracts/zizmor-gate.md`: glob `.github/workflows` and `.github/actions` (incl. `_shared/`, nested), run pinned zizmor offline, parse JSON, subtract register; fail on analyser missing, empty file set, unparsable output (FR-001–FR-004)
- [X] T006 Add the register validation to `verify-zizmor.py`: records keyed on `zizmor-findings-waivers.json` fields `file`, `audit`, `location`, `reason`, `control`, `issue`, `decided_by` per data-model.md "Accepted-findings record"; stale record, duplicate key and unwaived finding fail, output names file, line, audit (FR-002, FR-010, FR-011)
- [X] T007 Add the `--self-test` fixtures under `.github/scripts/fixtures/zizmor/` (or the sibling gates' fixture location): one per branch — unwaived finding, stale record, analyser missing, empty file set, unparsable output (FR-006)
- [ ] T008 Register the gate in the gate registry used by `.github/scripts/run-local-gates.py` and add the step plus `paths:` triggers (scanned files, zizmor.yml, register, pin) and checksum-verified, SHA-pinned install step to `.github/workflows/lint-workflows.yml` (FR-001, FR-005)

**Checkpoint**: gate runs locally and in CI with identical version, config and file set.

## Phase 3: User Story 1 — injection cannot reach main unseen (P1) 🎯 MVP

**Goal**: zizmor gate green on main with zero `template-injection` findings.
**Independent Test**: add an inline `${{ github.event.issue.title }}` in a `run:`; gate fails naming the line; move to `env:` and it passes.

- [X] T009 [P] [US1] Move both `inputs.directed-recovery` expansions in `.github/workflows/board-loop.yml` to an `env:` variable, behaviour unchanged for empty string and `false` (FR-007)
- [X] T010 [P] [US1] Move the `--ref "${{ github.ref_name }}"` expansion in `.github/workflows/wing-commander-rebase.yml` to an `env:` variable, safe for refs containing `/` (FR-007)
- [ ] T011 [US1] Add a fixture to `verify-zizmor.py --self-test` proving an inline expansion fails and the `env:` form passes (US1 acceptance 2)
- [ ] T012 [US1] Confirm the same verdict locally and in CI on one commit (SC-003) by running `python .github/scripts/run-local-gates.py`

## Phase 4: User Story 2 — every accepted finding recorded (P1)

**Goal**: zero unwaived findings; every kept finding has a record with control and tracker.
**Independent Test**: remove one `dangerous-triggers` record → gate fails naming it; add a bogus record → gate fails as stale.

- [ ] T013 [US2] Add the 7 `dangerous-triggers` records to `.github/scripts/zizmor-findings-waivers.json`, each naming `control` and `issue` tracker (the Maintenance backlog issue) per data-model.md `zizmor-findings-waivers.json` `control` and `issue` (FR-012, SC-004)
- [ ] T014 [US2] Triage each `github-env`, `artipacked`, `excessive-permissions` and `github-app` finding one at a time: fix in the owning workflow under `.github/workflows/` or `.github/actions/`, or add a register record with `reason` (FR-008)
- [ ] T015 [US2] Verify gate 124 (`.github/scripts/verify-waiver-citations.py`) discovers the new register by name with no change, and add a fixture or check proving a closed tracker is caught (FR-013)
- [X] T016 [US2] Add a `verify-zizmor.py` check that fails when the `self-repository` disable `reason` in `.github/zizmor.yml` is missing, with a fixture (FR-016, SC-011)

## Phase 5: Third-party pins and trusted-publisher home (cross-cutting, FR-009–FR-009b, FR-017a)

- [ ] T017 [US1] SHA-pin every third-party `uses:` outside `actions/*`, `github/*`, `anthropics/*` across `.github/workflows/` and `.github/actions/`, each with a version comment, until `unpinned-uses` reports nothing (FR-009, SC-008)
- [X] T018 [US1] Implement the single-home check (`.github/scripts/verify-trusted-publisher-single-home.py`, or fold into `verify-zizmor.py`): fail on a second copy of the list under `.github/` and on analyser policy differing from `.github/zizmor.yml`, with fixtures for both (FR-009a, SC-010)
- [ ] T019 [US1] Add `action-runtime-pins.json` rows for every new SHA ref and drop replaced rows; confirm gate 170 (`verify-action-runtime-pins.py`) still fails a deprecated-runtime bump (FR-017a)
- [ ] T020 [P] [US1] Create `.github/workflows/update-action-pins.yml`: opens PRs updating SHA and version comment together, carrying runtime-register rows; human-merged, no bot merge (FR-009b)
- [ ] T021 [US1] Add a fixture rewriting one pin to another SHA and comment with its register rows, showing the full gate suite passes (SC-010)

## Phase 6: User Story 3 — composites resolve from trusted code only (P2)

**Goal**: no `./` reference resolves inside an untrusted tree.
**Independent Test**: exposed-job fixture fails; safe-job fixture passes; audit lists exposed jobs on main.

- [X] T022 [US3] Implement `.github/scripts/verify-untrusted-checkout-local-uses.py` per `contracts/untrusted-checkout-gate.md`: track checkout/artifact/extract/write placements, classify trusted vs untrusted by repository and ref, judge composites per calling job, read `repo-only-reusable-workflows.json` (FR-016a, FR-016b)
- [X] T023 [US3] Add `--self-test` fixtures: exposed job (PR-head checkout), artifact-extracted tree, passing safe job (sidecar and `.wc-pristine-repo`), and an unlisted `workflow_call` treated as repo-only (FR-006, US3 acceptance 4–5)
- [ ] T024 [US3] Run the exposure audit over main and record the report in a comment on lifecycle issue #1188 (FR-014) — drafted as `specs/132-workflow-trigger-security/quickstart.md` evidence, posted by the maintainer in Phase 9
- [ ] T025 [US3] Fold the checkout-before-`./` rule out of `.github/scripts/verify-board-loop-composite-provenance.py` and `.github/scripts/verify-lifecycle-review-gate-composite-provenance.py` into the new gate, or record why each keeps it, with no duplicated rule logic; update their self-tests (FR-016a one-home)
- [X] T026 [US3] Fix each exposed job the audit finds (including `pr-conversation.yml` `wing-commander-outstanding-task-item` step if still present) without adding an input, secret or output to a published stage (FR-015, SC-009)
- [ ] T027 [US3] Register the gate in the gate registry and `.github/workflows/lint-workflows.yml` with `paths:` triggers; confirm gates parsing `uses: ./` still pass (FR-017)

## Phase 7: User Story 4 — adopter event policy docs (P2)

**Goal**: one docs page lists every event, its gate and a sample policy; a check enforces coverage.
**Independent Test**: every event under `on:` of `wing-commander-*.yml` appears in the sample policy.

- [X] T028 [US4] Update `docs/adoption.md`: events table (what each drives, how gated), `wc-event-policy` sample block, Evaluate-mode advice with the unresolved Enterprise question, fork-PR limit, permissions-vs-trigger explanation, SHA-pin freeze note (FR-018, FR-018a, FR-019, FR-021, FR-022)
- [X] T029 [US4] Implement `.github/scripts/verify-adopter-event-policy.py`: compare `on:` events of `wing-commander-*.yml` with the `wc-event-policy` block, with `--self-test` fixtures for a missing event (FR-020, SC-006)
- [ ] T030 [US4] Register the gate in `.github/workflows/lint-workflows.yml` with `paths:` triggers for the wrappers and `docs/adoption.md`

## Phase 8: Polish

- [ ] T031 [P] Update `docs/reference.md` for every new gate, register, config, pin file and default (FR-023)
- [ ] T032 Run `python .github/scripts/run-local-gates.py`; confirm 0 unwaived findings, 0 stale records and every failure branch has a fixture (SC-001, SC-002); give workflow-touching changes a pass from the `review-step-gating` skill
- [ ] T033 Confirm no change creates or edits an Actions event policy (FR-024) and no private downstream names appear in any file

## Phase 9: Maintainer follow-up

- [ ] T034 [maintainer] Post the exposure audit report from T024 on lifecycle issue #1188 and the Roadmap issue as required by FR-014
- [ ] T035 [maintainer] After merge, re-drive one run of `update-action-pins.yml` (`gh workflow run`) and record the evidence on the PR (post-merge proof, SC-010)
- [ ] T036 [maintainer] Merge the PR if it touches `.github/workflows/` with a token holding the `workflow` scope

## Dependencies & Order

- Phase 1 → Phase 2 (blocks all) → stories. US1 and US2 (P1) are done first; Phase 5 follows US2 (the register must exist before pins settle). US3 depends on T004 and Phase 2; US4 is independent of US3.
- T025 depends on T022–T023. T026 depends on T024. T019 depends on T017. T021 depends on T019–T020.
- Parallel: T002–T004; T009–T010; T020 alongside T017–T019; US3 and US4 after Phase 2.

## Implementation Strategy

MVP = Phases 1–3 (zizmor gate plus the three injection fixes, green on main). Then US2 records, pins, US3 gate, US4 docs. Standing guidance: keep the gate suite green after each phase.
