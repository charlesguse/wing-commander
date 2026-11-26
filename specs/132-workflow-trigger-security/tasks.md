# Tasks: Workflow security — static-analysis gate, `./` references, trigger docs

**Input**: `specs/132-workflow-trigger-security/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: The spec requires a checked-in fixture for every gate failure branch (FR-006, SC-002), so each gate task ships its `--self-test` fixtures.

**Format**: `- [ ] ID [P?] [Story] Description with path`. Run `python .github/scripts/run-local-gates.py` before pushing; keep the gates green after each phase. Workflow comments are load-bearing (gates byte-compare them): treat comment edits as code edits.

## Phase 1: Setup

- [X] T001 Create `.github/scripts/zizmor-pin.txt` with `version=1.33.1` and the release asset `sha256` per data-model.md "Analyser pin"
- [X] T002 [P] Create `.github/zizmor.yml`: `rules.self-repository.disable: true` with non-empty `reason`, and `rules.unpinned-uses.config.policies` (`actions/*`, `github/*`, `anthropics/*` → `ref-pin`; `*` → `hash-pin`) per data-model.md "Analyser configuration"
- [X] T003 [P] Create empty-array `.github/scripts/zizmor-findings-waivers.json` conforming to `specs/132-workflow-trigger-security/contracts/findings-register.schema.json`
- [X] T004 [P] Create `.github/scripts/repo-only-reusable-workflows.json` listing `shared-pr-reviewer.yml` (data-model.md "Repo-only reusable workflow list"; FR-016b)

## Phase 2: Foundational

**Purpose**: the zizmor gate skeleton every story's gate registration builds on.

- [X] T005 Implement `.github/scripts/verify-zizmor.py` per `contracts/zizmor-gate.md`: glob `.github/workflows` and `.github/actions` (incl. `_shared/`, nested), run pinned zizmor offline, parse JSON, subtract register; fail on analyser missing, empty file set, unparsable output (FR-001–FR-004)
- [X] T006 Add the register validation to `verify-zizmor.py`: records keyed on `zizmor-findings-waivers.json` fields `file`, `audit`, `location`, `reason`, `control`, `issue`, `decided_by` per data-model.md "Accepted-findings record"; stale record, duplicate key and unwaived finding fail, output names file, line, audit (FR-002, FR-010, FR-011)
- [X] T007 Add the `--self-test` fixtures under `.github/scripts/fixtures/zizmor/` (or the sibling gates' fixture location): one per branch — unwaived finding, stale record, analyser missing, empty file set, unparsable output (FR-006)
- [X] T008 Register the gate in the gate registry used by `.github/scripts/run-local-gates.py` and add the step plus `paths:` triggers (scanned files, zizmor.yml, register, pin) and checksum-verified, SHA-pinned install step to `.github/workflows/lint-workflows.yml` (FR-001, FR-005)

**Checkpoint**: gate runs locally and in CI with identical version, config and file set.

## Phase 3: User Story 1 — injection cannot reach main unseen (P1) 🎯 MVP

**Goal**: zizmor gate green on main with zero `template-injection` findings.
**Independent Test**: add an inline `${{ github.event.issue.title }}` in a `run:`; gate fails naming the line; move to `env:` and it passes.

- [X] T009 [P] [US1] Move both `inputs.directed-recovery` expansions in `.github/workflows/board-loop.yml` to an `env:` variable, behaviour unchanged for empty string and `false` (FR-007)
- [X] T010 [P] [US1] Move the `--ref "${{ github.ref_name }}"` expansion in `.github/workflows/wing-commander-rebase.yml` to an `env:` variable, safe for refs containing `/` (FR-007)
- [X] T011 [US1] Add a fixture to `verify-zizmor.py --self-test` proving an inline expansion fails and the `env:` form passes (US1 acceptance 2)
- [X] T012 [US1] Confirm the same verdict locally and in CI on one commit (SC-003) by running `python .github/scripts/run-local-gates.py`

## Phase 4: User Story 2 — every accepted finding recorded (P1)

**Goal**: zero unwaived findings; every kept finding has a record with control and tracker.
**Independent Test**: remove one `dangerous-triggers` record → gate fails naming it; add a bogus record → gate fails as stale.

- [X] T013 [US2] Add the 7 `dangerous-triggers` records to `.github/scripts/zizmor-findings-waivers.json`, each naming `control` and `issue` tracker (the Maintenance backlog issue) per data-model.md `zizmor-findings-waivers.json` `control` and `issue` (FR-012, SC-004)
- [X] T014 [US2] Triage each `github-env`, `artipacked`, `excessive-permissions` and `github-app` finding one at a time: fix in the owning workflow under `.github/workflows/` or `.github/actions/`, or add a register record with `reason` (FR-008)
- [X] T015 [US2] Verify gate 124 (`.github/scripts/verify-waiver-citations.py`) discovers the new register by name with no change, and add a fixture or check proving a closed tracker is caught (FR-013)
- [X] T016 [US2] Add a `verify-zizmor.py` check that fails when the `self-repository` disable `reason` in `.github/zizmor.yml` is missing, with a fixture (FR-016, SC-011)

## Phase 5: Third-party pins and trusted-publisher home (cross-cutting, FR-009–FR-009b, FR-017a)

- [X] T017 [US1] SHA-pin every third-party `uses:` outside `actions/*`, `github/*`, `anthropics/*` across `.github/workflows/` and `.github/actions/`, each with a version comment, until `unpinned-uses` reports nothing (FR-009, SC-008)
- [X] T018 [US1] Implement the single-home check (`.github/scripts/verify-trusted-publisher-single-home.py`, or fold into `verify-zizmor.py`): fail on a second copy of the list under `.github/` and on analyser policy differing from `.github/zizmor.yml`, with fixtures for both (FR-009a, SC-010)
- [X] T019 [US1] Add `action-runtime-pins.json` rows for every new SHA ref and drop replaced rows; confirm gate 170 (`verify-action-runtime-pins.py`) still fails a deprecated-runtime bump (FR-017a)
- [X] T020 [P] [US1] Create `.github/workflows/update-action-pins.yml`: opens PRs updating SHA and version comment together, carrying runtime-register rows; human-merged, no bot merge (FR-009b) — Met by Dependabot instead (owner decision on #890, research D6's first choice): `.github/dependabot.yml` opens weekly grouped bump PRs that update SHA and version comment together; a human adds the runtime-register rows (`python3 .github/scripts/wc_action_pins.py --write` on the bump branch; Gate 170 fails and says so until then) and merges. No workflow is added: a scheduled workflow would need the App's Workflows permission, which docs/setup.md does not grant.
- [X] T021 [US1] Add a fixture rewriting one pin to another SHA and comment with its register rows, showing the full gate suite passes (SC-010)

## Phase 6: User Story 3 — composites resolve from trusted code only (P2)

**Goal**: no `./` reference resolves inside an untrusted tree.
**Independent Test**: exposed-job fixture fails; safe-job fixture passes; audit lists exposed jobs on main.

- [X] T022 [US3] Implement `.github/scripts/verify-untrusted-checkout-local-uses.py` per `contracts/untrusted-checkout-gate.md`: track checkout/artifact/extract/write placements, classify trusted vs untrusted by repository and ref, judge composites per calling job, read `repo-only-reusable-workflows.json` (FR-016a, FR-016b)
- [X] T023 [US3] Add `--self-test` fixtures: exposed job (PR-head checkout), artifact-extracted tree, passing safe job (sidecar and `.wc-pristine-repo`), and an unlisted `workflow_call` treated as repo-only (FR-006, US3 acceptance 4–5)
- [X] T024 [US3] Run the exposure audit over main and record the report in a comment on lifecycle issue #1188 (FR-014) — drafted as `specs/132-workflow-trigger-security/quickstart.md` evidence, posted by the maintainer in Phase 9. Done 2026-11-26: the audit ran (`--audit`) over main and this branch, and its report went to the maintainer privately, not to a GitHub comment (owner rule for security findings); T034 posts it.
- [X] T025 [US3] Fold the checkout-before-`./` rule out of `.github/scripts/verify-board-loop-composite-provenance.py` and `.github/scripts/verify-lifecycle-review-gate-composite-provenance.py` into the new gate, or record why each keeps it, with no duplicated rule logic; update their self-tests (FR-016a one-home)
- [X] T026 [US3] Fix each exposed job the audit finds (including `pr-conversation.yml` `wing-commander-outstanding-task-item` step if still present) without adding an input, secret or output to a published stage (FR-015, SC-009)
- [X] T027 [US3] Register the gate in the gate registry and `.github/workflows/lint-workflows.yml` with `paths:` triggers; confirm gates parsing `uses: ./` still pass (FR-017)

## Phase 7: User Story 4 — adopter event policy docs (P2)

**Goal**: one docs page lists every event, its gate and a sample policy; a check enforces coverage.
**Independent Test**: every event under `on:` of `wing-commander-*.yml` appears in the sample policy.

- [X] T028 [US4] Update `docs/adoption.md`: events table (what each drives, how gated), `wc-event-policy` sample block, Evaluate-mode advice with the unresolved Enterprise question, fork-PR limit, permissions-vs-trigger explanation, SHA-pin freeze note (FR-018, FR-018a, FR-019, FR-021, FR-022)
- [X] T029 [US4] Implement `.github/scripts/verify-adopter-event-policy.py`: compare `on:` events of `wing-commander-*.yml` with the `wc-event-policy` block, with `--self-test` fixtures for a missing event (FR-020, SC-006)
- [X] T030 [US4] Register the gate in `.github/workflows/lint-workflows.yml` with `paths:` triggers for the wrappers and `docs/adoption.md`

## Phase 8: Polish

- [X] T031 [P] Update `docs/reference.md` for every new gate, register, config, pin file and default (FR-023)
- [X] T032 Run `python .github/scripts/run-local-gates.py`; confirm 0 unwaived findings, 0 stale records and every failure branch has a fixture (SC-001, SC-002); give workflow-touching changes a pass from the `review-step-gating` skill
- [X] T033 Confirm no change creates or edits an Actions event policy (FR-024) and no private downstream names appear in any file

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

## Review Gate Round 1 Findings

- [ ] Review finding: Gate 177 covers less than the Gate 104 rule (g1) it replaces

  Gate 104's (g1) banned any raw ./.github/actions reference in a published stage. Gate 177 only flags a ./ reference after a checkout, download-artifact or tar/unzip step it can see in the same job, so a composite that writes the workspace slips through.

  - .github/scripts/verify-untrusted-checkout-local-uses.py

  Detail: A published stage calls a composite that checks out the PR branch at '.', then a later uses: ./.github/actions/x is not flagged. Keep an unconditional published-stage ban on raw ./.github/actions/ references.

- [ ] Review finding: New gates fail open on unparsable workflows or a missing register

  scan skips workflows that raise YAML errors or are not dicts, and load_repo_only returns an empty set when repo-only-reusable-workflows.json is missing or invalid. verify-adopter-event-policy.wrapper_events does the same for wrapper files.

  - .github/scripts/verify-untrusted-checkout-local-uses.py

  Detail: A workflow with a YAML syntax error is silently skipped. A deleted or corrupt register makes shared-pr-reviewer.yml a published stage. Report parse errors and an unreadable register as failures.

- [ ] Review finding: verify-zizmor location_of collapses composite findings to 'workflow'

  Findings inside a composite action (route starts with runs) get location 'workflow'. A waiver keyed (file, audit, 'workflow') therefore covers every present and future finding of that audit in that composite.

  - .github/scripts/verify-zizmor.py

  Detail: The artipacked waiver on wing-commander-chain-stop-notice and the github-env waiver on wing-commander-context would also accept a new unsafe checkout or GITHUB_ENV write in the same composite. Produce step:<id-or-name> from runs.steps[idx].

- [ ] Review finding: tar/unzip with no -C/-d is treated as extracting to the whole workspace

  A run step with tar -x or unzip and no destination is recorded as an untrusted tree at '.', though it may extract elsewhere. A later checkout at '.' also fails to drop earlier nested entries.

  - .github/scripts/verify-untrusted-checkout-local-uses.py

  Detail: An unzip in a scratch directory causes false positives on every following ./.github/actions reference. Use working-directory, or treat the destination as unknown. Drop nested entries when '.' is re-checked-out.

- [ ] Review finding: run_zizmor does not handle errors from the scan call

  Only the --version call is wrapped for OSError and SubprocessError. A timeout or a vanished binary during the scan crashes the gate with a traceback instead of the promised 'analyser missing' failure.

  - .github/scripts/verify-zizmor.py

  Detail: A scan that exceeds the 600 s timeout raises an uncaught TimeoutExpired, so the ::error::verify-zizmor annotation is never emitted.

- [ ] Review finding: wc_action_pins plan can downgrade pins with short version comments

  _version accepts only three-part tags. A pin commented '# v4' or '# v10.0' parses to None, so the downgrade guard is skipped and the pin moves to the newest release whenever the SHA differs.

  - .github/scripts/wc_action_pins.py

  Detail: PIN_RE accepts those comment forms. A pin on a commit newer than v4.9.0 with the comment '# v4' is rewritten to the older v4.9.0 commit by --bump --write.

- [ ] Review finding: Dependabot composite coverage is hand-listed and its path is not in the lint trigger

  dependabot.yml lists composite directories by hand, while Gate 178 and wc_action_pins discover composites with **. Deeper nesting is not covered. lint-workflows.yml's pull_request.paths also omits .github/dependabot.yml.

  - .github/dependabot.yml

  Detail: A composite at .github/actions/_shared/foo/bar/action.yml has SHA pins that Dependabot never bumps. A PR editing only dependabot.yml does not trigger lint. Add a coverage gate and add the file to the paths filter.

- [ ] Review finding: Default or github.sha checkout is trusted on pull_request-triggered workflows

  TRUSTED_RUNNING_REFS treats a checkout with no ref, or ref github.sha, of the running repository as trusted in every top-level workflow. On pull_request, github.sha is the PR merge commit, which the PR author controls.

  - .github/scripts/verify-untrusted-checkout-local-uses.py

  Detail: A pull_request job that runs actions/checkout with no ref and then uses: ./.github/actions/x is reported safe. Don't trust that checkout on pull_request-style events, or add an explicit allowlist.
