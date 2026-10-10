# Tasks: Agent Start-up Image Check

**Input**: Design documents from `/specs/112-agent-startup-image-check/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/agent-startup-check.md, quickstart.md

**Tests**: Requested by the spec (FR-008, SC-003): every failure branch of the classifier and of the git floor ships a checked-in fixture driven by a gate.

**Organization**: Grouped by user story. US1 and US2 share the classifier, so the classifier core is Foundational; US1 wires the check into workflows, US2 proves the pass/fail discipline through the gate and fixtures.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US4 from spec.md

## Path Conventions

Repository root; scripts in `.github/scripts/`, workflows in `.github/workflows/`, docs in `docs/`.

---

## Phase 1: Setup

**Purpose**: Capture the real evidence the classifier is built on (research D3 risk)

- [x] T001 Capture the agent action's real no-credential log: run `anthropics/claude-code-action@v1` with `github_token: ${{ github.token }}` and no model credential in the current reference image (and once in an image without `unzip`), and save both raw job logs as the seeds for `.github/scripts/agent-startup-fixtures/auth-reached.log` and `.github/scripts/agent-startup-fixtures/setup-failed-install-bun-unzip.log`. Record the exact authentication-failure wording and setup group header names at the top of `.github/scripts/classify-agent-startup.py` when it is created (T003). If a live run is impossible, hand-write the fixtures from the `Unable to locate executable file: unzip` line in #974 and mark them `# synthetic` in the sibling expect file.
- [x] T002 [P] Create the fixture directory `.github/scripts/agent-startup-fixtures/` with a short `README.md` stating the `<branch>.log` / `<branch>.expect.json` convention from data-model.md (`{"verdict", "step", "error_contains"}`).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The deterministic classifier every startup story depends on (Principle IX)

**⚠️ CRITICAL**: US1 and US2 cannot start until this is complete

- [x] T003 Implement `.github/scripts/classify-agent-startup.py` with CLI `--log <file> [--json]`. Output the Verdict (`verdict`, `step`, `error`, `reason`) per data-model.md. Exit 0 only for `setup-completed`, 1 for `setup-failed`, 2 for `unclassified`. Rules per research D3: read `##[group]` headers from the log (no hard-coded complete list); the first `##[error]` inside a setup group gives `setup-failed` naming the group and quoting the line verbatim; the first error after all setup groups matching the auth marker table gives `setup-completed`; everything else (missing/unreadable/empty/truncated log, no error, error after setup that is not auth, pull failure, no markers) is `unclassified`. `reason` prefixes are exactly "setup failed in image" and "could not reach subject". The auth marker table is a module-level list of regexes (positive marker "failed at authentication, after setup" per plan).
- [x] T004 Make the classifier importable (`main(argv)` plus a pure `classify(text) -> dict` function) so the gate in T007 imports the same subject CI runs, per plan Structure Decision. Same file as T003.

**Checkpoint**: `python3 .github/scripts/classify-agent-startup.py --log <seed fixture>` returns the expected verdict and exit code.

---

## Phase 3: User Story 1 - An image the agent cannot start in is caught (Priority: P1) 🎯 MVP

**Goal**: A daily dogfood run and every reference-image rebuild run the real agent action's setup in the image and fail naming the step and error when setup cannot complete.

**Independent Test**: Dispatch `private-image-dogfood.yml` with `startup-check: true` against an image lacking one setup dependency: `classify-startup` fails, summary names "Install Bun" and quotes the error. Against the current reference image it passes with zero model calls.

### Implementation for User Story 1

- [x] T005 [US1] Add optional input `startup-check` (boolean, default `false`, description per contract table) to `.github/workflows/private-image-dogfood.yml` `workflow_call`. Additive only (FR-010); no new secret.
- [x] T006 [US1] Add job `startup-agent` to `.github/workflows/private-image-dogfood.yml`: `if: inputs.startup-check && inputs.container-image != ''`, same `needs`, `runs-on`, `container`, `credentials` binding as the `dogfood` job (Gates 7/22/23 shape, honouring `verify-image-prerequisites` result like `dogfood`), `permissions: contents: read`, one step `uses: anthropics/claude-code-action@v1` with `continue-on-error: true`, `github_token: ${{ github.token }}`, and no model credential input. Container steps need `shell: bash` per the `container-shell-safety` skill. Image arrives only from `inputs.container-image` (FR-011).
- [x] T007 [US1] Add job `classify-startup` to `.github/workflows/private-image-dogfood.yml`: `needs: [verify-image-prerequisites, startup-agent]`, `if: !cancelled() && inputs.startup-check && inputs.container-image != ''`, `permissions: actions: read`. Steps: fetch the `startup-agent` job log with `gh api repos/${{ github.repository }}/actions/jobs/<job id>/logs` (look up the job id by name via the run's jobs API), run `python3 .github/scripts/classify-agent-startup.py --log <file> --json` (check out the repo first), write the verdict to `$GITHUB_STEP_SUMMARY`, emit `::error::` with `reason`, and exit non-zero unless `setup-completed`. If the log fetch fails or the agent job was skipped/never started, classify an empty log so the result is `unclassified` rather than green. Apply the `review-step-gating` skill to every `if:` here.
- [x] T008 [US1] Opt the scheduled wrapper in: set `startup-check: true` and grant `actions: read` on the calling job in `.github/workflows/wing-commander-private-image-dogfood.yml`.
- [ ] T009 [US1] Add a job to `.github/workflows/wing-commander-e2e-reference-image.yml` after `build-and-publish` that calls `uses: ./.github/workflows/private-image-dogfood.yml` with the digest reference output by the build step as `container-image`, `startup-check: true`, `permissions: actions: read, contents: read, packages: read`, and `WING_COMMANDER_CONTAINER_REGISTRY_USERNAME`/`_PASSWORD` secrets passed explicitly (research D5/D8). Leave Gate 62's assertions unchanged.
- [x] T010 [US1] Run `python .github/scripts/run-local-gates.py`; fix any gate (7, 22, 23, 47, workflow-comment byte-compare gates) the new jobs trip. Workflow comments are load-bearing: re-run after any comment edit.

**Checkpoint**: US1 deliverable; a red `classify-startup` job names the failing step and error.

---

## Phase 4: User Story 2 - The check cannot pass without having reached setup (Priority: P1)

**Goal**: Every classifier branch is exercised by a fixture, and the suite fails when a branch has no fixture or a verdict drifts.

**Independent Test**: `python .github/scripts/verify-agent-startup-classifier.py --self-test` passes; deleting any fixture, or breaking the classifier on one branch, makes it fail.

### Tests for User Story 2

- [x] T011 [P] [US2] Add fixtures (`.log` + `.expect.json` each) in `.github/scripts/agent-startup-fixtures/`: `auth-reached` → `setup-completed`; `setup-failed-install-bun-unzip` → `setup-failed`, step contains "Install Bun", `error_contains` "Unable to locate executable file: unzip"; `setup-failed-other-step` → `setup-failed`.
- [x] T012 [P] [US2] Add fixtures for the unclassified branches in `.github/scripts/agent-startup-fixtures/`: `action-succeeded` (no error), `error-after-setup-not-auth`, `empty-log`, `truncated-log` (setup group opened, no end), `image-not-pulled` (job never started, no group headers). Each expects `unclassified` and a `reason` beginning "could not reach subject".
- [x] T013 [US2] Write `.github/scripts/verify-agent-startup-classifier.py` with `--self-test`: import `classify` from `classify-agent-startup.py` (via importlib, hyphenated name), run every fixture, fail on any verdict/step/`error_contains` mismatch, fail when any of the three verdicts has no fixture, fail when a fixture lacks its expect file, and assert the missing-`--log` path yields `unclassified` exit 2. Follow the structure of an existing `verify-*.py` (docstring, `--self-test` handling, exit codes).
- [x] T014 [US2] Register the gate in `.github/workflows/lint-workflows.yml` (path triggers include the classifier script, the fixtures directory, and `private-image-dogfood.yml`) and ensure `.github/scripts/run-local-gates.py` picks it up; take the next free gate number and add it wherever gate numbers are indexed (check how other gates are listed with Grep).
- [x] T015 [US2] Add a single-home check to the nearest existing gate: assert `private-image-dogfood.yml` invokes `classify-agent-startup.py` and contains no inline copy of the auth-marker or verdict logic (CLAUDE.md "Shared logic has exactly one home").
- [x] T016 [US2] Gate structural assertions for the workflow side, in the new gate or Gate 23: `startup-agent` has no model-credential input (no `anthropic_api_key`, `claude_code_oauth_token`, or secrets reference) and carries `continue-on-error: true`; `classify-startup` has an `if:` containing `!cancelled()`.

**Checkpoint**: Gate fails without a fixture per branch (SC-003).

---

## Phase 5: User Story 3 - Agent-action dependency changes are visible (Priority: P2)

**Goal**: The floating-tag policy and the start-up check are documented where maintainers and adopters read.

**Independent Test**: Grep the three docs for `@v1` policy text and `startup-check`.

- [x] T017 [P] [US3] Document in `docs/adoption.md` ("Runners and container images"): the agent action is consumed by floating `@v1`; its dependency changes are caught by the start-up check on the next daily dogfood or reference-image rebuild run; the optional `startup-check` input and the `actions: read` requirement; the git >= 2.38 floor.
- [x] T018 [P] [US3] Mirror the setup instructions in `docs/setup.md` (input, permission, what a red `classify-startup` means) with a pointer to `docs/adoption.md` rather than repeating prose.
- [x] T019 [P] [US3] Edit the 038 image-prerequisite contract under `specs/*/contracts/` (find it with Glob/Grep for the `required-tools.txt` contract table) to record the `@v1` policy, the git 2.38 floor, and the additive `startup-check` input. Contracts are live; edit as code.
- [x] T020 [US3] Add the header note to `.github/scripts/required-tools.txt` that the list is an inference cross-checked by the start-up check, and the basis for the git floor and `unzip` (FR-009: list contents unchanged). Re-run the gates that read this file (Gates 23, 62).

---

## Phase 6: User Story 4 - Git older than 2.38 is rejected (Priority: P2)

**Goal**: Every stage's `verify-image-prerequisites` probe fails on git < 2.38 naming the version, and on unparseable output.

**Independent Test**: Run the fragment against stub `git --version` outputs `git version 2.34.1` (fail naming 2.34.1), `git version 2.39.5` (pass), `garbage` (fail).

### Tests for User Story 4

- [x] T021 [P] [US4] Add fixtures under `.github/scripts/image-git-floor-fixtures/`: `2.34.1.txt`, `2.38.0.txt`, `2.43.0.txt`, `2.39.5.Apple-Git-154.txt` (suffix tolerated), `unparseable.txt`, `empty.txt`, each with its expected result.
- [x] T022 [US4] Extend the gate (new `verify-image-git-floor.py`, or an addition to `verify-agent-startup-classifier.py`; pick one and register it with the same steps as T014) to run `image-git-floor.sh` against each fixture with `git` stubbed, asserting pass/fail and that failure messages are exactly `git <found> is older than the 2.38 minimum` or `could not parse git version from "<output>"`.

### Implementation for User Story 4

- [x] T023 [US4] Create `.github/scripts/image-git-floor.sh`: POSIX `sh` fragment (runs inside the `docker run --entrypoint sh` probe, after the tool presence loop) that reads `git --version`, parses major.minor, fails below 2.38 with the contract message, fails on unparseable output with the contract message, no bashisms.
- [x] T024 [US4] Paste the fragment verbatim into the probe of `verify-image-prerequisites` in all 14 stage workflows under `.github/workflows/` (find them with Grep for `REQUIRED_TOOLS`; includes `private-image-dogfood.yml`). Keep indentation consistent with the existing probe.
- [x] T025 [US4] Extend Gate 23 to fail any stage whose probe lacks the fragment from `image-git-floor.sh` byte-for-byte (same mechanism as the `REQUIRED_TOOLS` comparison); add a self-test case with a probe missing the fragment.
- [x] T026 [US4] Run `python .github/scripts/run-local-gates.py`; confirm Gates 23 and 62 still assert everything they did before (FR-009).

---

## Phase 7: Polish & Cross-Cutting

- [ ] T027 [P] Run the `container-shell-safety` and `review-step-gating` skills over the changed workflows and fix findings in this PR.
- [ ] T028 Check no hardcoded repository/owner/image names or private consumer references were introduced (`grep` the diff; FR-011, public-repo rule).
- [ ] T029 Run quickstart.md validation end to end; confirm `python .github/scripts/run-local-gates.py` is green.
- [ ] T030 After merge: `prove-after-merge` — dispatch the wrapper, confirm `classify-startup` ran on the changed path, and record the evidence on #974.

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup (1) → Foundational (2) → US1 (3) and US2 (4) → US3 (5) → Polish.
- US4 (6) is independent of Phases 2–5 (only shares the gate-registration pattern from T014); can run in parallel after Setup.
- T017–T020 (US3) can start any time after T005 fixes the input name.

### Within Stories

- T003 before T004 (same file) and before T013.
- T005 → T006 → T007 (same workflow file) → T008, T009 → T010.
- T011/T012 before T013 (fixtures exist when the gate first runs); T013 → T014 → T015, T016.
- T023 → T024 → T025 → T026; T021 before T022.

### Parallel Opportunities

- T001 and T002; T011 and T012; T017, T018, T019 (different files); T021 alongside Phase 3.
- Per-story: Phase 3 and Phase 4 can proceed in parallel once T003 lands, except T014 must follow T013.

### Parallel Example: User Story 2

```text
Task: "Add fixtures for setup-completed/setup-failed in .github/scripts/agent-startup-fixtures/"   (T011)
Task: "Add fixtures for the unclassified branches in .github/scripts/agent-startup-fixtures/"      (T012)
```

---

## Implementation Strategy

### MVP First (US1 + US2, both P1)

1. T001–T004 (evidence + classifier).
2. T005–T010 (workflow wiring) with T011–T016 (fixtures and gate); ship together, because a start-up check with no fixture-backed gate does not meet Principle VIII.
3. Validate with a dispatched dogfood run against an image missing `unzip`.

### Incremental Delivery

1. MVP above.
2. US4 (git floor) as an independent PR-sized increment; touches 14 stage files, so keep it separate if the diff review is large.
3. US3 documentation last, once the input name and gate numbers are final.

---

## Notes

- Only `private-image-dogfood.yml` gains a published input (FR-010); no stage workflow other than the 14 probe edits changes.
- Workflow comments are load-bearing; re-run the suite after any comment edit.
- Spec documents in this directory are not edited by implementation except by corrections in this spec's open PR.

## Phase 8: Convergence

- [ ] T031 Run the start-up check on every reference-image rebuild without a `push`-event agent call: Gate 6 rejects `private-image-dogfood.yml` called from `wing-commander-e2e-reference-image.yml` because `anthropics/claude-code-action` does not support `push`. Have the rebuild workflow dispatch the check on a supported event (e.g. a `workflow_dispatch` wrapper run against the published digest) and keep Gate 62 unchanged, per FR-005 / T009 (partial)
- [ ] T032 Replace the synthetic fixtures in `.github/scripts/agent-startup-fixtures/` and the wording assumptions at the top of `classify-agent-startup.py` with a captured real no-credential log from `anthropics/claude-code-action@v1` (and one from an image without `unzip`), per FR-008 / T001 (partial)
- [ ] T033 Make the git-floor failure message reach the job log under its own name: the probe's non-zero exit currently surfaces behind the "could not run a POSIX shell" prefix in all 14 stages, so adjust the host-side message (and Gate 23/142 checks) so the floor failure is not mislabelled, per FR-013 (partial)

## Phase 9: Maintainer Feedback

- [ ] MF1 (T009/T031) Run the start-up check on every reference-image rebuild via a claude-code-action-supported event (e.g. a `workflow_dispatch` run against the published digest), not a `push`-event call to `private-image-dogfood.yml` (Gate 6). Keep Gate 62 assertions unchanged. Per T031's named approach.

## Maintainer Feedback

- [ ] MF2 (T033) Emit the git-floor failure under its own message, not behind the 'could not run a POSIX shell' prefix, in all affected stages. Update Gate 23/142 to match (FR-013).
