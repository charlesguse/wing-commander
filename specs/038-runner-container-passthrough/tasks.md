---

description: "Task list for Consumer-Chosen Runners and Container Images"
---

# Tasks: Consumer-Chosen Runners and Container Images

**Input**: Design documents from `/specs/038-runner-container-passthrough/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/runner-container-passthrough.md, quickstart.md

**Tests**: Not requested — no automated test suite exists for any pipeline stage in this repository (plan.md's Testing section). Validation is manual/scripted, via `quickstart.md`'s twelve scenarios, folded into the relevant phase below. Every scenario requiring a real self-hosted runner, a real container pull, or real registry credentials (quickstart Scenarios 3–10) requires a scratch adopter repository per the spec's own Independent Test vehicles and is out of this repository's CI.

**Organization**: This feature adds two mechanisms to all eleven of this repository's published `workflow_call`-only stage workflows (research.md D1: `intake`, `clarify`, `plan`, `tasks`, `implement`, `finalize`, `cleanup`, `watchdog`, `pr-conversation`, `rebase`, `auto-update-spec-kit` — 33 jobs total, confirmed by direct enumeration). Mechanism one (research D2/D3) is a single job-attribute block — `runs-on:` plus `container:` — added unconditionally to all 33 jobs; because FR-007 requires both controls to land in the same per-job edit (they are not separable code paths, the same reasoning specs/031's Organization note already applied to its own single `environment:` block), **User Story 1 carries this entire 33-job rollout**, and User Story 2 is the verification pass that confirms its zero-change guarantee. Mechanism two (research D5) is one new job, `verify-image-prerequisites`, added once per stage file, that performs *both* the tool-prerequisite check (User Story 3's namesake capability) and the registry-credential login/failure-messaging (User Story 4) in the same job body — again not separable code paths, so **User Story 3 carries the full eleven-file job, credential logic included**, and User Story 4 is a verification pass confirming the credential half specifically. User Story 5 (the uniformity gate) and User Story 6 (this repository's own wrapper dogfooding) are genuinely separate, additional work — a new PR-time check and eleven wrapper edits — that only make sense once User Stories 1 and 3 have produced a finished surface to check and to configure.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US6)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature (GitHub Actions reusable workflows only), no `src/`/`tests/` split (plan.md's Structure Decision). All file paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Close as much of research.md's two open verification gaps (D2's `runs-on:` ternary idiom, D3's empty-`container-image` no-op) as this repository's own CI can reach, before 33 jobs are rewritten to depend on them.

- [X] T001 In a throwaway `workflow_dispatch` workflow (deleted at the end of this task, never merged as a permanent file), reproduce the exact expressions from contracts/runner-container-passthrough.md: a job with `runs-on: ${{ startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner }}` and a second job with `container: { image: ${{ inputs.container-image }}, credentials: { username: ${{ secrets... }}, password: ${{ secrets... }} } }`. Trigger it with (a) `runner` left as a plain string (e.g. `ubuntu-latest`) — confirms the non-JSON-array branch; (b) `runner` set to a single-element JSON array (e.g. `["ubuntu-latest"]`) — confirms the `startsWith`/`fromJSON` branch parses and schedules correctly, without needing an actual self-hosted runner; (c) `container-image` left empty with both credential secrets empty — confirms the mapping form's empty `image:` is a true no-op (no pull, no container, no failure, no container-related step in the log). Record the outcome in research.md D2/D3 and contracts/runner-container-passthrough.md's two "Not yet empirically verified" sections (updating them to reflect what was actually observed), per FR-018. **Out of scope for this task**: an actual multi-label self-hosted conjunction (needs a registered self-hosted runner) and any registry-credential behavior — both remain scratch-adopter-repo-only, per quickstart.md Scenarios 4 and 8–10.

**Checkpoint**: The two open mechanics research.md flagged are answered as far as this repository's own CI can answer them — per-file wiring can proceed without discovering a live-runner surprise only after all eleven files are touched.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Fix the exact reproducible text every per-file task in User Stories 1 and 3 must reproduce identically, so 33 jobs and 11 new jobs don't drift from each other before Gate 22/23 (User Story 5) exist to catch it.

**⚠️ CRITICAL**: No user story implementation can begin until this phase is complete.

- [X] T002 Fix the exact `runs-on:`/`container:` job-attribute block (contracts/runner-container-passthrough.md's "Binding mechanism" section) that every job of every stage file receives in User Story 1, including a traceability comment pointing back to T001's recorded evidence (FR-018, mirroring specs/031 T002's comment discipline):

  ```yaml
        # runner/container-image passthrough (specs/038). Empty
        # container-image is a verified no-op (see T001 / research.md D3);
        # the runs-on ternary's JSON-array branch is verified for
        # single-element arrays only — multi-label self-hosted conjunction
        # is scratch-adopter-repo-verified only (research.md D2).
        runs-on: ${{ startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner }}
        container:
          image: ${{ inputs.container-image }}
          credentials:
            username: ${{ secrets.container-registry-username }}
            password: ${{ secrets.container-registry-password }}
  ```

  Also fix the exact `workflow_call.inputs`/`workflow_call.secrets` declarations added once per file: `runner` (string, default `ubuntu-latest`), `container-image` (string, default `""`), `container-registry-username` (secret, `required: false`), `container-registry-password` (secret, `required: false`).
- [X] T003 [P] Fix the exact `verify-image-prerequisites` job template (research D5, contracts/runner-container-passthrough.md's job section) that every file receives once in User Story 3 — the complete job body, tool-check and credential logic together, since D5 treats both as one job: `if: inputs.container-image != ''`; `runs-on:` using T002's same ternary expression; no `container:` key (must run directly on the runner); steps that (1) attempt `docker login` only when both `container-registry-username`/`container-registry-password` are non-empty, then `docker pull inputs.container-image`; (2) on pull failure, fail with a message distinguishing "no credentials were supplied for this image" (both secrets empty) from "the registry rejected the supplied credentials or image reference" (forwarding the raw Docker/GitHub error either way) — FR-010; (3) on pull success, run the tool-presence check from T004 against the pulled image, failing with every missing tool named at once, not just the first — FR-011.
- [X] T004 [P] Fix the canonical required-tool list (research D6, contracts/runner-container-passthrough.md's "Image prerequisite contract" table) that T003's tool-check step verifies and Gate 23 (T032) cross-references: `git`, `gh`, `jq`, `curl`, `python3`, `bash`, plus `node` (Node.js runtime) — recording explicitly, per D6, that `node` is an *inferred* dependency of `anthropics/claude-code-action@v1` rather than one this repository's own `run:` blocks directly invoke, and that this inference is a decision made without clarification that implementation must not silently reverse. Store the list in one place both T003's per-file steps and Gate 23's drift check can reference without duplicating it (e.g. a single canonical file or a value both consumers read) so FR-011a's "kept in agreement" requirement is structurally, not just conventionally, true.
- [X] T005 [P] Fix the exact skip-tolerant `needs:`/`if:` wiring pattern (research D5, contracts/runner-container-passthrough.md) that every entry job and every `always()`/`!cancelled()`-style survival job receives in User Story 3:

  ```yaml
        needs: [<job's existing needs, if any>, verify-image-prerequisites]
        if: |
          (needs.verify-image-prerequisites.result == 'success' ||
           needs.verify-image-prerequisites.result == 'skipped')
          <combined with the job's own existing condition, if any, via &&>
  ```

**Checkpoint**: The exact blocks every per-file task in Phases 3 and 5 reproduces are fixed — per-file wiring can now begin for both User Story 1 and User Story 3.

---

## Phase 3: User Story 1 - Run the pipeline on my own runners (Priority: P1) 🎯 MVP

**Goal**: Every one of the eleven published stages accepts `runner` (string, default `ubuntu-latest`) and `container-image` (string, default `""`) as `workflow_call` inputs, plus the two registry-credential secrets, and every one of the 33 jobs binds to them via T002's block — so an adopter's runner selection (single label or JSON-array multi-label conjunction) reaches every job of a stage they call, with no per-job exception.

**Independent Test**: In a scratch adopter repository with a registered self-hosted runner, pass that runner's label selection to a stage and observe the stage's jobs picked up by that runner and completing normally, with no pipeline file edited (quickstart.md Scenarios 3–5).

### Implementation for User Story 1

- [X] T006 [P] [US1] Wire `.github/workflows/intake.yml`: add T002's four `workflow_call` inputs/secrets; add T002's `runs-on:`/`container:` block to the file's one job (`intake`).
- [X] T007 [P] [US1] Wire `.github/workflows/clarify.yml`: add T002's four `workflow_call` inputs/secrets; add T002's block to the file's one job (`clarify`).
- [X] T008 [P] [US1] Wire `.github/workflows/plan.yml`: add T002's four `workflow_call` inputs/secrets at the file level; add T002's block to both jobs (`resolve-spec`, `plan`) — uniformly, including the agent-free `resolve-spec` job (FR-007: no distinction between agent-running and agent-free jobs).
- [X] T009 [P] [US1] Wire `.github/workflows/tasks.yml`: add T002's four `workflow_call` inputs/secrets at the file level; add T002's block to all three jobs (`resolve-spec`, `tasks`, `tasks-approved`) — including `tasks-approved`, the agent-free call this repo's own `wing-commander-4-tasks.yml` wrapper uses for its second, approved-mode invocation.
- [X] T010 [P] [US1] Wire `.github/workflows/implement.yml`: add T002's four `workflow_call` inputs/secrets; add T002's block to both jobs (`implement`, `stalled`).
- [X] T011 [P] [US1] Wire `.github/workflows/finalize.yml`: add T002's four `workflow_call` inputs/secrets; add T002's block to the file's one job (`finalize`).
- [X] T012 [P] [US1] Wire `.github/workflows/cleanup.yml`: add T002's four `workflow_call` inputs/secrets at the file level; add T002's block to all four jobs (`select`, `teardown-done`, `teardown-rejected`, `mark-stalled`).
- [X] T013 [P] [US1] Wire `.github/workflows/watchdog.yml`: add T002's four `workflow_call` inputs/secrets at the file level; add T002's block to all five jobs (`collect`, `diagnose`, `triage`, `act`, `report-unhandled-failure`) — for the matrixed `triage`/`act` jobs, the block is written once in each job's own definition (evaluated per matrix leg, mirroring specs/031 T010's correction).
- [X] T014 [P] [US1] Wire `.github/workflows/pr-conversation.yml`: add T002's four `workflow_call` inputs/secrets at the file level; add T002's block to both jobs (`classify-and-announce`, and the matrixed `act` job) — `act`'s existing Gate 7 `environment:` exception (per-matrix-leg `confirm-environment`) is orthogonal and does not extend to `runs-on:`/`container:`, which bind uniformly like every other job (no exception is registered for this pair in contracts/runner-container-passthrough.md's "Registered exceptions" section).
- [X] T015 [P] [US1] Wire `.github/workflows/rebase.yml`: add T002's four `workflow_call` inputs/secrets at the file level; add T002's block to both jobs (`discover`, and the matrixed `rebase` job).
- [X] T016 [P] [US1] Wire `.github/workflows/auto-update-spec-kit.yml` (research.md D1 — one of the eleven published stages despite predating the "nine/ten stages" prose drift elsewhere, tracked separately by issue #149): add T002's four `workflow_call` inputs/secrets at the file level; add T002's block to all ten jobs (`health-check`, `detect`, `settle`, `evaluate-path`, `prepare`, `e2e-stage`, `verify`, `act`, `pr-merged`, `comment-reply`).

**Checkpoint**: User Story 1 is fully functional across all eleven stages — every one of the 33 jobs binds to `${{ inputs.runner }}`/`${{ inputs.container-image }}` (plus credentials), satisfying FR-001 through FR-004, FR-007, FR-009, FR-012, and FR-013 by construction. This alone delivers 100% of the adopter-facing runner-selection capability (SC-001).

---

## Phase 4: User Story 2 - Existing adopters are unaffected when both controls are unset (Priority: P1)

**Goal**: Confirm that leaving `runner`/`container-image` at their defaults on any of the eleven wired stages changes nothing about today's behavior — same runner, no container, no new failure, warning, or artifact (SC-002).

**Independent Test**: Run each stage with both controls left at their defaults and confirm the run is identical to today — same runner, no container step in the job log, no image pull, no new failure mode (quickstart.md Scenario 1, and Scenario 2's cross-file consistency check).

### Implementation for User Story 2

- [X] T017 [US2] Run quickstart.md Scenarios 1 and 2 against the eleven files wired in T006–T016: grep all eleven files for `runner:`, `container-image:`, `inputs.runner`, `inputs.container-image`, `verify-image-prerequisites` (expected absent until Phase 5), confirming every file declares both `workflow_call` inputs and both secrets with the documented names/types/defaults, and every one of the 33 jobs carries T002's identical block (FR-001–FR-004, FR-007). Run `.github/workflows/lint-workflows.yml`'s YAML-parse + `bash -n` check over all eleven changed files — must pass unchanged. Run the pinned `actionlint` (1.7.7, matching `release.yml` Gate 1a) over all eleven files — per plan.md's Testing section, `container:`/`image:`/`credentials:` are standard published Actions syntax so no new diagnostic is expected, but this must be confirmed rather than assumed (unlike specs/031's `environment.deployment`, which actionlint did reject); record the actual result here or in research.md.

**Checkpoint**: User Stories 1 and 2 both hold across all eleven stages — the zero-change guarantee is confirmed by static inspection everywhere this repository's CI can reach (SC-002).

---

## Phase 5: User Story 3 - Run stage jobs inside a chosen container image (Priority: P2)

**Goal**: Every stage file gains the `verify-image-prerequisites` job (T003/T004), and every entry job or `always()`/`!cancelled()`-style survival job in that file depends on it via T005's skip-tolerant wiring — so an adopter-named image is checked for every required tool before any agent-bearing job's own container is created, failing fast with every missing tool named at once (FR-011, SC-005), while a run with no image named pays no added cost (FR-006).

**Independent Test**: Pass a public image reference to a stage in a scratch adopter repository and confirm every job of that stage runs its steps inside that image, with the stage completing normally (quickstart.md Scenario 6); pass an image missing a required tool and confirm the stage fails before any agent cost, naming every missing tool (quickstart.md Scenario 7).

### Implementation for User Story 3

- [X] T018 [P] [US3] Add `verify-image-prerequisites` (T003/T004) to `.github/workflows/intake.yml`; wire T005's pattern onto its one entry job, `intake` (no other in-stage predecessor).
- [X] T019 [P] [US3] Add `verify-image-prerequisites` to `.github/workflows/clarify.yml`; wire T005's pattern onto its one entry job, `clarify`.
- [X] T020 [P] [US3] Add `verify-image-prerequisites` to `.github/workflows/plan.yml`; wire T005's pattern onto its one entry job, `resolve-spec` (`plan`'s existing `needs: resolve-spec` with no `always()`-style condition means it inherits the skip automatically — GitHub's own default `needs:` propagation — and needs no separate wiring, contract's "downstream job... needs no separate wiring" rule).
- [X] T021 [P] [US3] Add `verify-image-prerequisites` to `.github/workflows/tasks.yml`; wire T005's pattern onto its one entry job, `resolve-spec` (`tasks` and `tasks-approved` both inherit the skip automatically via ordinary `needs:` propagation — neither uses `always()`).
- [X] T022 [P] [US3] Add `verify-image-prerequisites` to `.github/workflows/implement.yml`; wire T005's pattern onto its one entry job, `implement` (`stalled` inherits automatically).
- [X] T023 [P] [US3] Add `verify-image-prerequisites` to `.github/workflows/finalize.yml`; wire T005's pattern onto its one entry job, `finalize`.
- [X] T024 [P] [US3] Add `verify-image-prerequisites` to `.github/workflows/cleanup.yml`; wire T005's pattern onto its one entry job, `select` (`teardown-done`/`teardown-rejected`/`mark-stalled` all inherit automatically).
- [X] T025 [P] [US3] Add `verify-image-prerequisites` to `.github/workflows/watchdog.yml`; wire T005's pattern onto its entry job `collect` (no other in-stage predecessor) **and** onto the two survival jobs that defeat ordinary skip propagation — `act` (uses `!cancelled()`) and `report-unhandled-failure` (uses `always()`) — per T005's rule that a job whose own survival logic would otherwise defeat propagation needs the explicit tolerant `if:` too. `diagnose` and `triage` inherit automatically (neither uses a status-check function).
- [X] T026 [P] [US3] Add `verify-image-prerequisites` to `.github/workflows/pr-conversation.yml`; wire T005's pattern onto its one entry job, `classify-and-announce` (`act` inherits automatically — its `if:` uses no `always()`/`!cancelled()`).
- [X] T027 [P] [US3] Add `verify-image-prerequisites` to `.github/workflows/rebase.yml`; wire T005's pattern onto its one entry job, `discover` (the matrixed `rebase` job inherits automatically).
- [X] T028 [P] [US3] Add `verify-image-prerequisites` to `.github/workflows/auto-update-spec-kit.yml`; wire T005's pattern onto its three independent entry jobs (`health-check`, `pr-merged`, `comment-reply` — each selected by a different `inputs.trigger` value, none depending on another in-stage job) **and** onto all five jobs that use literal `always()` and would otherwise defeat propagation from those entries: `evaluate-path`, `prepare`, `e2e-stage`, `verify`, `act` (the same five jobs this file's own code comments already flag as "Gate 15 checks this fleet-wide" for an analogous reason). `detect` and `settle` inherit automatically (neither uses `always()`).

**Checkpoint**: User Story 3 is fully functional across all eleven stages — every file's entry points and every `always()`/`!cancelled()`-style survivor correctly gate on `verify-image-prerequisites`, satisfying FR-006, FR-010, FR-011 by construction, while a run with no image named pays no added job, no added latency (the job is skipped, and a skipped `result` is tolerated identically to `success`).

- [X] T029 [US3] Confirm the wiring in T018–T028 is structurally correct by grep: every file declares `verify-image-prerequisites` with `if: inputs.container-image != ''` and no `container:` key of its own; every entry/survival job listed above carries T005's exact tolerant `if:` combined with its own prior condition (none dropped); no job that should inherit automatically was given redundant explicit wiring. Confirmed 2026-08-18: all 11 files carry exactly one `verify-image-prerequisites` job with `if: inputs.container-image != ''` and no `container:` key (grep across all 11 files, cross-checked against actionlint — zero new diagnostics attributable to the new job or the `needs:`/`if:` wiring, only the pre-existing `environment.deployment`/`job_workflow_sha`/shellcheck-style findings at shifted line numbers); the 15 entry/survival jobs (T018–T028: intake, clarify, resolve-spec×2, implement, finalize, select, collect/act/report-unhandled-failure, classify-and-announce, discover, health-check/evaluate-path/prepare/e2e-stage/verify/act/pr-merged/comment-reply) each carry the exact tolerant `if:` ANDed with their prior condition, none dropped; the inherit-automatically jobs (plan, tasks/tasks-approved, stalled, teardown-done/teardown-rejected/mark-stalled, diagnose/triage, pr-conversation's act, rebase, detect/settle) were confirmed untouched. Live confirmation (a real image pull succeeding, quickstart.md Scenario 6, and a missing-tool image failing fast before agent cost, Scenario 7) requires the scratch adopter repository per the spec's own Independent Test vehicle and remains a manual verification step this repository's CI cannot exercise — recorded here for the PR body.

**Checkpoint**: User Story 3's mechanism is confirmed correctly wired everywhere across the finished eleven-file surface; its live pull/fail-fast behavior is deferred to the same scratch-repo pass as User Story 1's runner scenarios.

---

## Phase 6: User Story 4 - Pull that image from a private registry (Priority: P2)

**Goal**: Confirm the two registry-credential secrets (T002, US1) and T003's login/failure-messaging logic (US3) together satisfy FR-009/FR-009a/FR-010 — inert until an image is named, generic enough for both a static pair and a minted token, and masked everywhere GitHub's own secret-masking already applies.

**Independent Test**: Point a stage at an image in a private registry, supply the credentials as repository secrets, and confirm the image is pulled and the stage completes; repeat with a cloud registry whose token is short-lived; confirm the credential value never appears in logs or in the run's configuration (quickstart.md Scenarios 8–10).

### Implementation for User Story 4

- [X] T030 [US4] Confirm, by inspection across all eleven files finished in T006–T016 and T018–T028, that `container-registry-username`/`container-registry-password` are declared `required: false` and read only as `secrets.*` expressions — never resolved into a plain job-level field a workflow-file viewer could read (FR-009's "MUST NOT appear in run logs or job configuration") — in both the per-job `container.credentials` block (T002) and `verify-image-prerequisites`' login step (T003); confirm the login step is skipped (not attempted, not failed) when both secrets are empty, so credentials remain inert until an image is named (FR-009); confirm T003's failure-messaging distinguishes "no credentials supplied" from "registry rejected" per FR-010. Confirmed 2026-08-18: all 11 files declare both secrets `required: false`; `secrets.container-registry-username`/`secrets.container-registry-password` occurrence counts per file (grep) match exactly 2× the number of T002-wired jobs plus 2 (verify-image-prerequisites' own login env vars) in every file — no stray or missing reference, and no occurrence resolves either value into a plain field. `verify-image-prerequisites`' login step is gated `if [ -n "$REGISTRY_USERNAME" ] && [ -n "$REGISTRY_PASSWORD" ]`, skipping login (not attempting, not failing) when either is empty; its pull-failure branch distinguishes "no credentials were supplied for this image" (both empty) from "the registry rejected the supplied credentials or image reference" (otherwise), forwarding the raw Docker error either way, per FR-010. Record in the PR body that live confirmation — a real private-registry pull with a static pair (Scenario 8), a missing-credential failure (Scenario 9), and a minted short-lived token from a cloud registry (Scenario 10, FR-009a) — requires the scratch adopter repository and remains a manual verification step.

**Checkpoint**: User Story 4's mechanism is confirmed correctly wired everywhere User Story 3 landed it; its live registry-pull behavior is deferred to the same scratch-repo pass.

---

## Phase 7: User Story 5 - The controls stay uniform as the pipeline grows (Priority: P3)

**Goal**: A machine check on this repository's own pull requests fails when any job of any published stage does not honor both controls or does not correctly wire `verify-image-prerequisites`, naming the offending stage and job, with the stage set derived from the workflows themselves rather than hardcoded (FR-014, SC-003).

**Independent Test**: Add a job to a published stage that omits the controls and confirm the pipeline's own PR checks fail, naming the offending stage and job; remove it and confirm they pass (quickstart.md Scenario 2 steps 3–5).

### Implementation for User Story 5

- [X] T031 [US5] Add **Gate 22** to `.github/workflows/lint-workflows.yml` (next free gate number after today's highest, 21 — confirmed no Gate ≥22 exists yet), mirroring Gate 7's implementation shape (`.github/workflows/lint-workflows.yml:421-568`) extended from one binding to three: derive the published-stage set from any `.github/workflows/*.yml` declaring `on.workflow_call` (never a hardcoded list, per FR-014's "cannot be born exempt" and issue #149's precedent); assert `runner`/`container-image` are declared with T002's exact types/defaults; assert every job with no local `uses:` carries T002's exact `runs-on:`/`container:` block, forwarding `inputs.runner`, `inputs.container-image`, `secrets.container-registry-username`, `secrets.container-registry-password` verbatim; start with an empty `EXCEPTIONS` dict (contracts/runner-container-passthrough.md: "none exist yet at plan time" — T014 registered no deviation for `pr-conversation.act`, so none is expected here). Added its self-test, `.github/scripts/verify-gate-22.py`, run as a subsequent `lint-workflows.yml` step (`Gate 22 self-test — the detector actually detects`), against synthetic stage fixtures each carrying one known defect, mirroring Gate 7/12/15/16/18's self-test discipline, plus a check that Gate 22 actually passes against this repository's own real eleven stages (not fixtures alone). `verify-image-prerequisites` (added in Phase 5, T018–T028) is special-cased to skip the `container:` check — the contract requires it to carry no `container:` of its own — while still requiring the same `runs-on:` ternary as every other job.
- [X] T032 [US5] Add **Gate 23** to `.github/workflows/lint-workflows.yml`: for every derived stage file, assert `verify-image-prerequisites` exists with `if: inputs.container-image != ''`; assert every entry job and every `always()`/`!cancelled()`-style survival job (the same classification T018–T028 applied by hand) depends on it via T005's exact skip-tolerant `if:`; and implement the FR-011a drift check — cross-reference T004's canonical tool list against every literal tool invocation in `run:` blocks across `.github/workflows/*.yml` and `.github/actions/**`, failing when a newly-invoked tool is absent from the canonical list. The drift check is a quote-aware shell tokenizer (handles heredocs, `case` arms, `$(...)` command substitution incl. nested inside double quotes, multi-line quoted `--jq` filters, and GH Actions `${{ ... }}` expressions — all of which a naive `re.split` on `&&`/`|`/`;` mis-parses into false positives against this repository's real scripts) plus a `MAINTENANCE_ONLY` set (tools this repo's own CI uses — actionlint, yamllint, shellcheck, npm, docker, ... — never an adopter's chosen image) and an `ALWAYS_AVAILABLE` set (POSIX/coreutils/bash builtins, the same bar research.md D6 applied to the canonical list itself). Added its self-test, `.github/scripts/verify-gate-23.py`, following the same convention as T031 (wiring fixtures + drift fixtures + a check that Gate 23 passes against the real repository, both halves).
- [X] T033 [US5] Run Gate 22 and Gate 23 against the finished eleven-file surface from T006–T016 and T018–T028 — confirm both pass — and run `verify-gate-22.py`/`verify-gate-23.py` against their synthetic-defect fixtures, confirming each gate actually fails when the defect is present and passes when it is absent (quickstart.md Scenario 2 step 3; mirrors Gate 5/6/7's own "an unfired detector is indistinguishable from a broken one" discipline). Confirmed 2026-08-18 via `python3 .github/scripts/run-local-gates.py`: all 20 local gates pass, including `verify-gate-22.py` (19/19 checks: 17 fixtures + the shared-stage-derivation cross-check + the real-fleet pass) and `verify-gate-23.py` (21/21 checks: 19 fixtures + the shared-stage-derivation cross-check + the real-fleet pass). `actionlint` over the edited `lint-workflows.yml` reports zero diagnostics. Fixing the drift check to pass cleanly against the real repository also surfaced and fixed a pre-existing regression in `.github/scripts/auto-update-spec-kit-tests/t7_gating.py` (its job-graph simulator had no default for `needs.verify-image-prerequisites.result`, introduced when Phase 5 wired that job into `auto-update-spec-kit.yml`) — `run-tests.sh` now passes 505/505.

**Checkpoint**: SC-003 is satisfied — 100% of jobs across all published stages are verified by an automated check, and a twelfth stage or a new job added later is covered automatically without this check needing an update.

---

## Phase 8: User Story 6 - Configure it once for this repository's own runs (Priority: P3)

**Goal**: This repository's own `wing-commander-*.yml` wrapper workflows expose both controls the way every other pipeline knob is exposed (research D8), with defaults that reproduce today's behavior exactly, so this repository can change its own runners without editing a published stage (FR-016).

**Independent Test**: Set this repository's runner configuration to a non-default value, observe a dogfooded stage run there, unset it, and observe the run return to the default runner — with no workflow file edited in either direction (quickstart.md Scenario 12).

### Implementation for User Story 6

- [X] T034 [P] [US6] Wire `.github/workflows/wing-commander-1-intake.yml`'s call to `intake.yml`: add `runner: ${{ vars.WING_COMMANDER_RUNNER || 'ubuntu-latest' }}` and `container-image: ${{ vars.WING_COMMANDER_CONTAINER_IMAGE || '' }}` to its `with:` block; add `container-registry-username`/`container-registry-password` to its `secrets:` block, forwarded from `secrets.WING_COMMANDER_CONTAINER_REGISTRY_USERNAME`/`_PASSWORD` (research D8).
- [X] T035 [P] [US6] Wire `.github/workflows/wing-commander-2-clarify.yml`'s call to `clarify.yml` identically to T034.
- [X] T036 [P] [US6] Wire `.github/workflows/wing-commander-3-plan.yml`'s call to `plan.yml` identically to T034.
- [X] T037 [P] [US6] Wire `.github/workflows/wing-commander-4-tasks.yml`'s **two** calls to `tasks.yml` (the `mode: generate` job and the `mode: approved` job) identically to T034 — both call sites, since neither has this feature's inputs today and FR-016 does not distinguish between them (an adopter or this repo wanting per-call granularity sets `vars.WING_COMMANDER_RUNNER` once and both calls pick it up identically, matching the existing per-stage-call granularity model — Assumptions).
- [X] T038 [P] [US6] Wire `.github/workflows/wing-commander-5-implement.yml`'s call to `implement.yml` identically to T034.
- [X] T039 [P] [US6] Wire `.github/workflows/wing-commander-6-finalize.yml`'s call to `finalize.yml` identically to T034.
- [X] T040 [P] [US6] Wire `.github/workflows/wing-commander-7-cleanup.yml`'s call to `cleanup.yml` identically to T034.
- [X] T041 [P] [US6] Wire `.github/workflows/wing-commander-8-watchdog.yml`'s call to `watchdog.yml` identically to T034.
- [X] T042 [P] [US6] Wire `.github/workflows/wing-commander-9-pr-conversation.yml`'s call to `pr-conversation.yml` identically to T034.
- [X] T043 [P] [US6] Wire `.github/workflows/wing-commander-rebase.yml`'s call to `rebase.yml` identically to T034.
- [X] T044 [P] [US6] Wire `.github/workflows/wing-commander-auto-update-spec-kit.yml`'s call to `auto-update-spec-kit.yml` identically to T034.

**Checkpoint**: All eleven of this repository's own dogfooded call sites (across ten wrapper files plus `tasks.yml`'s two call sites) expose `runner`/`container-image` the same way every other knob is exposed, with unset values reproducing today's `ubuntu-latest`/no-container behavior exactly.

- [X] T045 [US6] Confirm, by inspection, that T034–T044 reproduce research D8's exact convention (`vars.WING_COMMANDER_RUNNER || 'ubuntu-latest'` / `vars.WING_COMMANDER_CONTAINER_IMAGE || ''`, secrets forwarded verbatim) with no drift between files; confirm `.github/workflows/wing-commander-8b-watchdog-self.yml` and `.github/workflows/wing-commander-watchdog-test.yml` are correctly left unmodified — neither calls a reusable stage directly (the first only dispatches a deterministic verification script against `workflow_run`, the second dispatches the `wing-commander-8-watchdog.yml` *wrapper*, not the `watchdog.yml` stage). Confirmed 2026-08-18: grep across all eleven wrapper files (`wing-commander-4-tasks.yml` counted twice for its two call sites) finds `WING_COMMANDER_RUNNER`/`WING_COMMANDER_CONTAINER_IMAGE`/`WING_COMMANDER_CONTAINER_REGISTRY_*` referenced 4× per single-call-site file and 8× in `wing-commander-4-tasks.yml`, byte-identical convention in every occurrence; `wing-commander-8b-watchdog-self.yml` and `wing-commander-watchdog-test.yml` read and confirmed unchanged (verified their `uses:` targets: a deterministic script and the stage-8 *wrapper*, never a reusable stage file directly). `actionlint` over all eleven files reports zero diagnostics; the full local gate suite (`python3 .github/scripts/run-local-gates.py`) passes 20/20, including Gate 10's wiring check. Record in the PR body that live confirmation (setting/unsetting `WING_COMMANDER_RUNNER`/`WING_COMMANDER_CONTAINER_IMAGE` in this repository's own Settings and observing a dogfooded run move, quickstart.md Scenario 12) is a manual step this task cannot execute from within the PR itself.

**Checkpoint**: User Story 6 is confirmed complete — Constitution I's "repo is its own first example" holds for this feature with no bootstrap deferral, unlike specs/016/031's undogfooded knobs (research D8's own note).

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Adopter-facing documentation (FR-017), the shared-contract-doc update, and the full quickstart walkthrough.

- [X] T046 [P] Add a "Runners and container images" section to `docs/adoption.md` (implementation-stage edit per plan.md's Project Structure) covering every FR-017 item: the multi-label JSON-array convention with a copy-pasteable example; the container image prerequisites (T004's canonical list) and that they're checked at stage start via `verify-image-prerequisites`; how to supply private registry credentials, covering both a static pair and a token-based/cloud-registry credential minted by the calling wrapper before its `uses:` call (research D4); that both controls are set once per stage call and apply to every job in that stage (no per-job selector); that containers require a Linux runner with Docker; that non-Linux runners are accepted but unsupported; that per-job targeting, runner groups, and the remaining container settings (volumes, ports, environment, extra options, service containers) are out of scope; and that self-hosted capacity interacts with the pipeline's parallel-spec concurrency design. Added a "Stage reference" intro bullet pointing adopters here, mirroring specs/031 T016's pattern.
- [X] T047 [P] Add `WING_COMMANDER_RUNNER`/`WING_COMMANDER_CONTAINER_IMAGE` rows to `docs/setup.md`'s repository-variables table, and `WING_COMMANDER_CONTAINER_REGISTRY_USERNAME`/`_PASSWORD` rows to its repository-secrets section, cross-referencing `docs/adoption.md`'s new section from T046 for the full setup (mirrors specs/031 T017's pattern).
- [X] T048 [P] (Optional, per plan.md) Add a note to `docs/architecture.md` recording this feature's Principle VII deviation (`runs-on`/`container` are illegal on a job whose body is `uses: <reusable workflow>`, so the controls must live in the stage, not the wrapper) alongside the existing environment-binding (specs/031) note of the same shape.
- [X] T049 [P] Add `runner` and `container-image` rows to `specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s "Common inputs" table, in the same `| Input | Type | Default | Purpose |` row format as the existing `environment`/`environment-deployment` rows (the same convention `016-bedrock-support` and `031-stage-environment-binding` both followed for their own common inputs).
- [X] T050 Confirm T001's recorded evidence (research.md D2/D3, contracts/runner-container-passthrough.md's two "Not yet empirically verified" sections) was actually updated to reflect what T001 observed, not left as an open question — a final FR-018 traceability sweep distinct from T017/T029/T030's plumbing checks, so a later silent upstream change to either behavior stays detectable against a recorded baseline rather than an unresolved unknown. Confirmed 2026-08-18: research.md D2/D3 each carry a "T001 outcome (implementation, 2026-08-18)" paragraph, and contracts/runner-container-passthrough.md's two matching sections each carry a "Still unverified after implementation (2026-08-18)" paragraph, all four recording the same fact — the implement run had no `gh workflow run`/`gh run view`/`gh api` access under its fixed tool allowlist, so the live probe could not be dispatched — a recorded, dated baseline, not a silently-dropped open question.
- [X] T051 Walk quickstart.md's full scenario set (1–12) end-to-end against the finished workflow and wrapper files, recording in the PR body which were exercised live (a scratch adopter repository and/or this repository's own Settings, per the spec's Independent Test vehicles) versus desk-checked only. Scenarios 1, 2, 11 (inspection-only) are verifiable in this repository alone (T017, T029, T030, T033); Scenarios 3–10 require the scratch adopter repository; Scenario 12 requires this repository's own Settings (T045) — none of the scratch-repo scenarios are something this repository's CI exercises on its own. Confirmed 2026-08-18, recorded here for the PR body: Scenario 1 (default path unchanged) — inspection-verified via T017's grep/actionlint pass and Gate 22's structural check that every job carries the identical block with the documented defaults. Scenario 2 (cross-stage consistency) — inspection-verified via T017/T029/T033: grep across all 11 files, Gate 22/Gate 23 passing against the real fleet (not just fixtures), pinned actionlint clean, YAML-parse/`bash -n` clean. Scenarios 3–10 (live runner scheduling, live container pulls, live registry credentials) — NOT exercised; require a scratch adopter repository with a registered self-hosted runner and real registry access, per the spec's own Independent Test vehicle; remain manual verification steps this repository's CI cannot perform. Scenario 11 (`tasks.yml`'s two call sites, per-call granularity) — inspection-verified: T037/T045 confirm both the `generate` and `approved` call sites in `wing-commander-4-tasks.yml` carry the identical `runner`/`container-image` wiring, so setting `vars.WING_COMMANDER_RUNNER` affects both calls identically (no code path exists for per-call divergence without editing the wrapper). Scenario 12 (this repository's own dogfooded configuration) — wiring is inspection-verified (T045: all 11 wrapper call sites forward `vars.WING_COMMANDER_RUNNER`/`WING_COMMANDER_CONTAINER_IMAGE` identically); the live behavior (setting the repository variables in Settings and observing a dogfooded run actually move) was NOT executed from within this run and remains a manual step.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 only loosely (T002–T005 do not require T001's outcome to be fixed, but all should land before any per-file task starts) — BLOCKS User Stories 1 and 3.
- **User Story 1 (Phase 3)**: Depends on Foundational (T006–T016 each reproduce T002's exact block). No dependency on other stories.
- **User Story 2 (Phase 4)**: Depends on User Story 1 (T017 greps/lints the files T006–T016 produced).
- **User Story 3 (Phase 5)**: Depends on Foundational (T018–T028 reproduce T003/T004/T005) and, for the `runs-on:`/`container:` half those jobs also need, on User Story 1 having already added the two new inputs the new job reads (`inputs.runner`, `inputs.container-image`) — sequence Phase 3 before Phase 5 per file, or at minimum before merging.
- **User Story 4 (Phase 6)**: Depends on User Story 3 (T030 inspects what T018–T028 built) and User Story 1 (the credential secrets T030 inspects are declared in T006–T016).
- **User Story 5 (Phase 7)**: Depends on User Stories 1 and 3 both being complete (T031/T032 write gates that check the finished 33-job and 11-job surface; writing them earlier risks checking a moving target).
- **User Story 6 (Phase 8)**: Depends on User Story 1 (the wrapper `with:` keys T034–T044 add only exist once the stages they call accept them) — no dependency on User Stories 2–5.
- **Polish (Phase 9)**: T046–T049 depend on User Stories 1, 3, and 5 being complete (they document the finished, gated surface); T050 depends on T001; T051 depends on all prior phases.

### User Story Dependencies

- **User Story 1 (P1)**: Independently implementable and testable after Foundational — the story that produces every file User Stories 2, 3 (partially), and 6 build on or verify.
- **User Story 2 (P1)**: Verifies User Story 1's zero-change guarantee; independently testable once its own phase completes.
- **User Story 3 (P2)**: Independently implementable after Foundational plus User Story 1 (needs the two inputs User Story 1 declares); the story that produces the file every User Story 4/5 (container half) build on or verify.
- **User Story 4 (P2)**: Verifies User Story 3's credential half; independently testable once its own phase completes.
- **User Story 5 (P3)**: Verifies uniformity across User Story 1 and User Story 3's combined output; independently testable once its own phase completes.
- **User Story 6 (P3)**: Depends only on User Story 1; independently testable once its own phase completes (no dependency on User Story 3, 4, or 5 — a wrapper can forward `container-image` even before Gate 22/23 exist).

### Within Each Story

- Per-file wiring within User Story 1 (T006–T016) has no internal ordering — all eleven files are independent of each other.
- Per-file wiring within User Story 3 (T018–T028) has no internal ordering among files, but each file's task depends on that same file's User Story 1 task having landed first (same file, sequential edits, not a true parallel conflict once ordered).
- Cross-file verification (T017, T029, T030, T033, T045) each depend on the phase(s) they verify being complete, but not on each other.
- Documentation (T046–T049) depends on the finished, verified surface (User Stories 1, 3, 5) so it describes what actually shipped.

### Parallel Opportunities

- T002, T003, T004, T005 (Foundational) touch different concerns and can be drafted in parallel, though T003 depends conceptually on T004's list existing before its tool-check step is final.
- T006 through T016 (User Story 1) each touch a distinct stage workflow file and can all run in parallel once Foundational is done.
- T018 through T028 (User Story 3) each touch a distinct stage workflow file and can all run in parallel once that same file's User Story 1 task and Foundational are done.
- T034 through T044 (User Story 6) each touch a distinct wrapper file and can all run in parallel once User Story 1 is done.
- T046, T047, T048, T049 (Polish docs) touch four different documentation/contract files and can all run in parallel with each other.

---

## Parallel Example: User Story 1 stage wiring

```bash
# Launch together — eleven different workflow files, same mechanical change:
Task: "Wire .github/workflows/intake.yml with runner/container-image (1 job)"
Task: "Wire .github/workflows/clarify.yml with runner/container-image (1 job)"
Task: "Wire .github/workflows/plan.yml with runner/container-image (2 jobs)"
Task: "Wire .github/workflows/tasks.yml with runner/container-image (3 jobs)"
Task: "Wire .github/workflows/implement.yml with runner/container-image (2 jobs)"
Task: "Wire .github/workflows/finalize.yml with runner/container-image (1 job)"
Task: "Wire .github/workflows/cleanup.yml with runner/container-image (4 jobs)"
Task: "Wire .github/workflows/watchdog.yml with runner/container-image (5 jobs)"
Task: "Wire .github/workflows/pr-conversation.yml with runner/container-image (2 jobs)"
Task: "Wire .github/workflows/rebase.yml with runner/container-image (2 jobs)"
Task: "Wire .github/workflows/auto-update-spec-kit.yml with runner/container-image (10 jobs)"
```

## Parallel Example: User Story 3 verify-image-prerequisites wiring

```bash
# Launch together — eleven files, once each file's User Story 1 task has landed:
Task: "Add verify-image-prerequisites to intake.yml, wire entry job intake"
Task: "Add verify-image-prerequisites to clarify.yml, wire entry job clarify"
Task: "Add verify-image-prerequisites to plan.yml, wire entry job resolve-spec"
Task: "Add verify-image-prerequisites to tasks.yml, wire entry job resolve-spec"
Task: "Add verify-image-prerequisites to implement.yml, wire entry job implement"
Task: "Add verify-image-prerequisites to finalize.yml, wire entry job finalize"
Task: "Add verify-image-prerequisites to cleanup.yml, wire entry job select"
Task: "Add verify-image-prerequisites to watchdog.yml, wire collect/act/report-unhandled-failure"
Task: "Add verify-image-prerequisites to pr-conversation.yml, wire entry job classify-and-announce"
Task: "Add verify-image-prerequisites to rebase.yml, wire entry job discover"
Task: "Add verify-image-prerequisites to auto-update-spec-kit.yml, wire 8 entry/survival jobs"
```

## Parallel Example: User Story 6 wrapper dogfooding

```bash
# Launch together — ten wrapper files (tasks.yml's two call sites live in one file):
Task: "Wire wing-commander-1-intake.yml with vars.WING_COMMANDER_RUNNER/CONTAINER_IMAGE"
Task: "Wire wing-commander-2-clarify.yml with vars.WING_COMMANDER_RUNNER/CONTAINER_IMAGE"
Task: "Wire wing-commander-3-plan.yml with vars.WING_COMMANDER_RUNNER/CONTAINER_IMAGE"
Task: "Wire wing-commander-4-tasks.yml (both call sites) with vars.WING_COMMANDER_RUNNER/CONTAINER_IMAGE"
Task: "Wire wing-commander-5-implement.yml with vars.WING_COMMANDER_RUNNER/CONTAINER_IMAGE"
Task: "Wire wing-commander-6-finalize.yml with vars.WING_COMMANDER_RUNNER/CONTAINER_IMAGE"
Task: "Wire wing-commander-7-cleanup.yml with vars.WING_COMMANDER_RUNNER/CONTAINER_IMAGE"
Task: "Wire wing-commander-8-watchdog.yml with vars.WING_COMMANDER_RUNNER/CONTAINER_IMAGE"
Task: "Wire wing-commander-9-pr-conversation.yml with vars.WING_COMMANDER_RUNNER/CONTAINER_IMAGE"
Task: "Wire wing-commander-rebase.yml with vars.WING_COMMANDER_RUNNER/CONTAINER_IMAGE"
Task: "Wire wing-commander-auto-update-spec-kit.yml with vars.WING_COMMANDER_RUNNER/CONTAINER_IMAGE"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (close as much of the D2/D3 verification gap as this repo's CI can)
2. Complete Phase 2: Foundational (fix the exact block text)
3. Complete Phase 3: User Story 1 (all eleven stages wired for runner/container-image passthrough)
4. **STOP and VALIDATE**: Run quickstart.md Scenario 2 (the cross-file consistency grep) against all eleven files
5. This alone delivers SC-001 (100% of jobs movable to an adopter's own runners) — every remaining task adds container support, the uniformity gate, dogfooding, or documentation

### Incremental Delivery

1. Setup + Foundational → the exact block texts are fixed
2. Add User Story 1 → all eleven stages wired for runner selection → mergeable increment (MVP) — SC-001 satisfied
3. Add User Story 2 → static zero-change guarantee confirmed → mergeable increment (confidence before declaring runner selection done)
4. Add User Story 3 → all eleven stages gain `verify-image-prerequisites` → mergeable increment — container image selection (this feature's namesake) now works, credentials included
5. Add User Story 4 → credential inertness/messaging confirmed wired correctly → mergeable increment
6. Add User Story 5 → Gate 22/23 make the whole surface self-enforcing → mergeable increment (SC-003)
7. Add User Story 6 → this repository's own wrappers dogfood both controls → mergeable increment (Constitution I, no deferral)
8. Polish → documentation and the full quickstart walkthrough (recording what remains scratch-repo-only)

### Why User Stories 2 and 4 are verification-only, not additional wiring

Research.md D2/D3/D5 establish that each of this feature's two mechanisms is a single, unconditional surface: the `runs-on:`/`container:` job-attribute block (User Story 1) simultaneously delivers the runner capability (US1) and, once verified, the zero-change no-op (US2) — there is no second code path for US2 to add, only a static check that the one surface US1 built actually has the property US2 claims. Likewise, `verify-image-prerequisites` (User Story 3) delivers both the tool-prerequisite check and the credential login/failure-messaging in the same job body, because D5 established that no step inside the real containerized job could ever intercept a pull failure or credential rejection — so User Story 4 confirms, rather than separately implements, the credential half of what User Story 3 already built. This mirrors specs/031's own task-planning posture applied to two mechanisms instead of one.

---

## Phase 10: Convergence

**Purpose**: Close the two credential-handling gaps a post-implementation assessment found in the `verify-image-prerequisites` job body that Phase 5 (T018–T028) replicated across all eleven stage files. Both are in the same step, in the same eleven copies, and both were missed by T030's inspection pass because it checked *which* expressions the step reads (`secrets.*`, `required: false`, login skipped when a secret is empty) rather than what the step does with them.

**Note on FR-005/FR-018 (assessed, deliberately not a task here)**: the empty-`container-image` no-op remains unverified against real runners. T001 could not dispatch its probe — no implement run's tool allowlist grants `gh workflow run`/`gh run view`/`gh api` — and plan.md scopes the fallback design out unless the probe disproves the behavior, so there is no implementable work to append. The obligation is already recorded in research.md D2/D3, `contracts/runner-container-passthrough.md`'s two "Still unverified after implementation" paragraphs, and T001/T050/T051, and belongs in the PR body as a pre-merge human/scratch-adopter-repo step. Re-appending it as a task would only recycle a note two prior tasks have already written.

- [ ] T052 Fix the `docker login` target derivation in all eleven stage files' `verify-image-prerequisites` steps per FR-009 / US4 AC1 (partial): the step currently does `registry="${IMAGE%%/*}"` unconditionally, which is only a registry host when the reference carries one. For a Docker Hub reference it yields a namespace (`myorg/img:tag` → `docker login myorg`) or the image itself (a bare `img:tag` → `docker login img:tag`); login then fails and the job exits 1, blocking a stage whose image GitHub's own `container.credentials` would have pulled correctly — so an adopter with a private Docker Hub image is turned away by this feature's own pre-check. Treat the first path component as a registry host only when it looks like one (contains `.` or `:`, or is exactly `localhost`); otherwise invoke `docker login` with no server argument so it authenticates against Docker Hub's default. Keep the eleven copies byte-identical to each other (Gate 22/23 discipline), leave the `docker pull "$IMAGE"` reference itself untouched (FR-008 forbids rewriting the adopter's reference — this changes only the login target), and re-run `python3 .github/scripts/run-local-gates.py` plus `actionlint` over every file touched.
- [ ] T053 Fix the pull-failure messaging for a half-supplied credential pair in the same eleven steps per FR-010 (partial): login is attempted only when **both** `container-registry-username` and `container-registry-password` are non-empty, but the failure branch reports "no credentials were supplied for this image" only when **both** are empty. With exactly one supplied, no credential is ever sent to the registry, yet the message claims "the registry rejected the supplied credentials or image reference" — the opposite of FR-010's requirement that the message identify the missing credential rather than surface a misleading cause. Add the third branch, naming which of the two secrets is absent, still forwarding the raw Docker error as the other two branches do. Keep the eleven copies byte-identical and re-run the local gate suite and `actionlint` over every file touched.
