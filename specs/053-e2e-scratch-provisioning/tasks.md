---

description: "Task list template for feature implementation"
---

# Tasks: On-demand E2E scratch repository provisioning

**Input**: Design documents from `specs/053-e2e-scratch-provisioning/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (cli.md, readiness-report.schema.json, readiness-workflow.md), quickstart.md

**Tests**: plan.md's Technical Context names a bash test harness
(`.github/scripts/e2e-provisioning-tests/`) as a core deliverable of this
feature (FR-005, FR-007, FR-016, SC-008 are each asserted by a named
scenario there), so test tasks are included below as regular
implementation tasks, not a strict TDD "write first" sequence.

**Organization**: Tasks are grouped by user story to enable independent
implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Single-project tooling addition, entirely inside this repository's existing
`.github/scripts/` and `.github/workflows/` layout (plan.md Structure
Decision) — no new top-level directory, no new language.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffold the new files this feature adds, matching this
repository's existing script conventions, before any onboarding-element
logic is written.

- [X] T001 Create `.github/scripts/e2e-provisioning/` with empty
  `profiles.sh` and `checks.sh` files, each starting with
  `#!/usr/bin/env bash` and `set -uo pipefail`, matching the shebang/strict
  -mode convention used by `.github/scripts/verify-watchdog-run.sh`.
- [X] T002 [P] Create `.github/scripts/e2e-provisioning-tests/` with
  `run-tests.sh` adapted from
  `.github/scripts/auto-update-spec-kit-tests/run-tests.sh` (same
  python-probe / suite-loop / `GITHUB_STEP_SUMMARY` shape), declaring
  `SUITES=(t1_new_target.sh t2_idempotent.sh t3_converge_after_install.sh t4_refuse_self.sh t5_refuse_foreign.sh t6_no_delete.sh t7_readiness_workflow.sh)`;
  `lib.sh` adapted from that directory's harness (real Actions step
  environment, a `gh` stub ahead of PATH, assertion helpers); and
  `gh_stub.py`, a JSON-state-backed `gh` stub implementing only the
  subcommands provisioning calls (`repo create`, `repo view`, `repo edit`,
  `secret set`, `secret list`, `label create`, `label view`, `variable
  set`, `variable list`, `api .../installation`), recording every
  invocation to `$GH_CALLS` the way the existing `gh_stub.py` does.
- [X] T003 [P] Create `.github/scripts/provision-e2e-target.sh` with a
  shebang, `set -uo pipefail`, and argument parsing for `--repo OWNER/NAME`
  (required), `--profile auto-release|spec-kit-scratch` (required), and
  `--check-only` (optional flag), per contracts/cli.md's Invocation table
  (`provision-e2e-target.sh --repo OWNER/NAME --profile
  auto-release|spec-kit-scratch [--check-only]`); print a usage error and
  exit non-zero on a missing/invalid flag, an unrecognized flag, or a
  `--profile` value outside the two named choices — "No other flags. No
  interactive prompts under any flag combination (FR-013)".

**Checkpoint**: Scaffolding exists; no onboarding-element logic yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The one shared library (`profiles.sh` + `checks.sh`) both
callers source (FR-008, FR-010, research.md D2) — every onboarding element
either profile requires must be checkable before any user story's
provisioning flow can produce a correct `ReadinessReport`.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 [P] Define `TargetProfile` data in
  `.github/scripts/e2e-provisioning/profiles.sh`: `spec-kit-scratch`'s
  `required_elements` = `repository`, `app_installation`,
  `scratch_marker`; `auto-release`'s `required_elements` built by
  extending the `spec-kit-scratch` list with `claude_credential`,
  `spec_request_label`, `wrapper_set`, `container_image_pin` in code
  (`auto-release = spec-kit-scratch + {...}`), not as an independent
  second list — so "`auto-release`'s element set is a strict superset of
  `spec-kit-scratch`'s... enforced by construction" (data-model.md)
  holds structurally, not just by inspection.
- [X] T005 Implement the `repository` and `app_installation`
  onboarding-element check functions in
  `.github/scripts/e2e-provisioning/checks.sh`: `repository` is `ready`
  iff `gh repo view OWNER/NAME` succeeds; `app_installation` is `ready`
  iff a `gh api` read confirms an App installation covers the target —
  read-only, `remedy: manual`, and "never performed, only checked"
  (contracts/cli.md). Each function's `remaining_action` matches
  data-model.md's `OnboardingElement` row; for `app_installation`:
  `"Install the wing-commander App on <owner>/<name>:
  https://github.com/settings/installations"`.
- [X] T006 Implement the `claude_credential` and `spec_request_label`
  check functions in `.github/scripts/e2e-provisioning/checks.sh`
  (depends on T005, same file): `claude_credential` is `ready` iff `gh
  secret list --repo OWNER/NAME` shows `CLAUDE_CODE_OAUTH_TOKEN` or
  `ANTHROPIC_API_KEY` present — "Never inspects a secret's value
  (FR-009)"; `spec_request_label` is `ready` iff `gh label view
  spec-request --repo OWNER/NAME` succeeds.
- [X] T007 Implement the `wrapper_set` and `container_image_pin` check
  functions in `.github/scripts/e2e-provisioning/checks.sh` (depends on
  T006, same file): `wrapper_set` is `ready` iff all eight
  `wing-commander-{1-intake,2-clarify,3-plan,4-tasks,5-implement,6-finalize,7-cleanup,rebase}.yml`
  files exist in the target's default branch `.github/workflows/`;
  `container_image_pin` is `ready` iff the target's
  `WING_COMMANDER_CONTAINER_IMAGE` repository variable equals this
  repository's own `vars.WING_COMMANDER_CONTAINER_IMAGE` value, read once
  from this repository "so the two cannot drift into a second literal"
  (research.md D4/Assumptions) — including the case where this repository
  pins no image (FR-017), which is itself a valid pinned value.
- [X] T008 Implement the `scratch_marker` check function in
  `.github/scripts/e2e-provisioning/checks.sh` (depends on T007, same
  file; research.md D3): `ready` iff the target repository has zero
  commits, or its description (`gh repo view OWNER/NAME --json
  description`) equals the fixed marker string `"Wing Commander E2E
  scratch target — provisioned by provision-e2e-target.sh, do not use
  for real work"`; otherwise `not_ready` with a `remaining_action` naming
  that the repository "cannot be established as a reusable scratch
  verification target" and what was found instead (FR-007).
- [X] T009 Implement `assemble_report` in
  `.github/scripts/e2e-provisioning/checks.sh` (depends on T008, same
  file): iterate `TargetProfile.required_elements` in order, call each
  element's check, and build the object matching
  `contracts/readiness-report.schema.json` exactly — `target` matches
  `^[^/\s]+/[^/\s]+$`; `profile` is one of `auto-release` /
  `spec-kit-scratch`; each `elements[]` entry has `key`, `ready`, and
  `remaining_action`, where `remaining_action` is "Null iff `ready` is
  true. Never null when `ready` is false (FR-006)"; the top-level `ready`
  is `true` "iff every entry in `elements` has `ready == true`. FR-004:
  never true otherwise"; `generated_at` is an ISO-8601 timestamp.

**Checkpoint**: `checks.sh`/`profiles.sh` can compute a correct
`ReadinessReport` for either profile against any `gh_stub.py` state.
User story implementation can now begin.

---

## Phase 3: User Story 1 - Stand up a ready-to-target E2E repository on demand (Priority: P1) 🎯 MVP

**Goal**: One command, run locally under the maintainer's own `gh`
authentication, takes a brand-new repository name from "does not exist" to
"every onboarding element ready except the declared manual App
installation," and converges to fully ready on a second invocation after
that install.

**Independent Test**: point `provision-e2e-target.sh` at a repository name
that does not exist yet, run it, then run the existing reachability
diagnostic and a real `auto-release.yml` dispatch against the resulting
repository — the dispatch reaches the agent stages rather than failing on
infrastructure.

### Implementation for User Story 1

- [X] T010 [US1] Implement self-target refusal and flag validation in
  `.github/scripts/provision-e2e-target.sh` (depends on T003, T009): "Refuse
  and exit non-zero immediately if `--repo` names this repository, or is
  malformed (not `OWNER/NAME` shape) — FR-007" — before any `gh` call is
  made, naming which reason triggered the refusal.
- [X] T011 [US1] Implement the privileged `repository` action in
  `.github/scripts/provision-e2e-target.sh` (depends on T010, same file):
  when the `repository` element is `not_ready` and `--check-only` is
  absent, run `gh repo create OWNER/NAME --private` under the invoking
  shell's own `gh` authentication only — "never under
  `secrets.WING_COMMANDER_APP_ID`/`_PRIVATE_KEY`" (FR-003, FR-014).
- [X] T012 [US1] Implement the privileged `claude_credential` action
  (depends on T011, same file): read `CLAUDE_CODE_OAUTH_TOKEN` first, then
  `ANTHROPIC_API_KEY`, from the invoking shell's own environment
  (research.md D5) and `gh secret set <NAME> --repo OWNER/NAME` with its
  value; if neither is set, leave the element `not_ready` with an
  instruction to export one and re-run — never treated as the FR-015
  declared manual step.
- [X] T013 [US1] Implement the privileged `spec_request_label` action
  (depends on T012, same file): `gh label create spec-request --repo
  OWNER/NAME` when not already present.
- [X] T014 [US1] Implement the privileged `wrapper_set` and
  `container_image_pin` actions (depends on T013, same file): copy the
  eight wrapper files from this checkout's own `.github/workflows/`
  (research.md D6 — "the same files `auto-release.yml`'s `scaffold` step
  already copies"), rewrite each `uses:
  ./.github/workflows/<stage>.yml` to the pinned cross-repo form, apply
  the same two `main`-literal patches `auto-release.yml` applies
  (`wing-commander-3-plan.yml`'s `== 'main'` and
  `wing-commander-rebase.yml`'s `branches: [main]`, substituted with the
  target's actual default branch), commit and push to the target's
  default branch; then `gh variable set WING_COMMANDER_CONTAINER_IMAGE
  --repo OWNER/NAME` to this repository's own pinned value.
- [X] T015 [US1] Implement the privileged `scratch_marker`-write action
  (depends on T014, same file): on first successful provisioning, `gh
  repo edit OWNER/NAME --description "<marker string from T008>"`.
- [X] T016 [US1] Wire the orchestration in `provision-e2e-target.sh`'s
  main flow per contracts/cli.md Behavior (depends on T015, same file):
  unless `--check-only`, for each `required_elements` entry whose
  `remedy` is `privileged` and whose `check` currently returns
  `not_ready`, perform the matching T011-T015 action — "Performing an
  element that is already in place is a no-op, not an error (FR-005)";
  then call `assemble_report` (T009) for every element including
  `app_installation`; print the `ReadinessReport` as JSON to stdout and a
  human-readable summary to stderr; exit `0` if `ready: true`, else exit
  `1` — "never exit `0` with a not-ready report" (FR-004, FR-008).

### Tests for User Story 1

- [X] T017 [P] [US1] Write
  `.github/scripts/e2e-provisioning-tests/t1_new_target.sh` (depends on
  T016): seed `gh_stub.py` with no repository under the chosen name, run
  `provision-e2e-target.sh --repo OWNER/NAME --profile auto-release`,
  assert exit code `1`, every element `ready: true` except
  `app_installation`, and its `remaining_action` names
  `https://github.com/settings/installations` (Acceptance Scenario 1,
  quickstart step 1).
- [X] T018 [P] [US1] Write
  `.github/scripts/e2e-provisioning-tests/t2_idempotent.sh` (depends on
  T016): run `provision-e2e-target.sh` twice against a `gh_stub.py` state
  that is already fully onboarded, and assert the second run performs
  zero privileged calls (via `$GH_CALLS`) and produces an identical
  `ReadinessReport` (FR-005, SC-003, Acceptance Scenario 3, quickstart
  step 4).
- [X] T019 [P] [US1] Write
  `.github/scripts/e2e-provisioning-tests/t3_converge_after_install.sh`
  (depends on T016): seed a state where every element except
  `app_installation` is ready, run once (assert `ready: false`, exit
  `1`), flip `app_installation` to ready in the stub state (simulating
  the human installing the App), run again, and assert `ready: true`
  with none of the already-ready elements re-performed (Acceptance
  Scenario 5, quickstart step 3).
- [X] T020 [P] [US1] Write
  `.github/scripts/e2e-provisioning-tests/t4_refuse_self.sh` (depends on
  T010): run `provision-e2e-target.sh --repo <this-repository>
  --profile auto-release`, assert immediate non-zero exit, and assert
  `$GH_CALLS` is empty (FR-007, quickstart step 6's first command).

**Checkpoint**: User Story 1 is fully functional and independently
testable — provisioning a brand-new target now works end to end.

---

## Phase 4: User Story 2 - Know the target's readiness without spending an agent run (Priority: P2)

**Goal**: Extend the existing single-element scratch preflight into a
full, itemised readiness check for either profile, at zero Claude quota.

**Independent Test**: run the readiness check against the hand-onboarded
target that exists today — it reports ready; run it against a repository
missing the label — it reports not-ready and names the label.

### Implementation for User Story 2

- [X] T021 [US2] Generalize
  `.github/workflows/auto-update-spec-kit-scratch-preflight.yml` per
  contracts/readiness-workflow.md: add `target` (string, default `''`)
  and `profile` (choice `auto-release` | `spec-kit-scratch`, default
  `spec-kit-scratch`) `workflow_dispatch` inputs; when `target` is empty,
  resolve it from `vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_SCRATCH_REPO`
  for `profile == spec-kit-scratch` or
  `vars.WING_COMMANDER_AUTO_RELEASE_E2E_REPO` for `profile ==
  auto-release`, "failing loudly (constitution VIII), naming
  `docs/setup.md`, if the resolved value is unset or malformed".
- [X] T022 [US2] Replace the workflow's inline reachability/report steps
  (depends on T021, same file): keep minting the App-scoped token with
  `continue-on-error: true` as today, then source
  `.github/scripts/e2e-provisioning/checks.sh` and invoke
  `provision-e2e-target.sh --repo <target> --profile <profile>
  --check-only` with the minted token as `GH_TOKEN` — "no privileged
  action is ever attempted from this workflow" (FR-003, SC-005) — and
  render the resulting `ReadinessReport` as a `GITHUB_STEP_SUMMARY` table
  (one row per element, ✅/❌, remaining action for each ❌), exiting
  non-zero when `ready` is `false`; a dispatch with no inputs must
  reproduce today's exact behaviour byte-for-byte (same target
  resolution, same single-element scratch check, same summary shape) —
  FR-011.

### Tests for User Story 2

- [X] T023 [P] [US2] Write
  `.github/scripts/e2e-provisioning-tests/t7_readiness_workflow.sh`
  (depends on T022): assert a no-input dispatch resolves the same target
  and profile as today's behaviour (compatibility contract), and assert
  the workflow's `run:` steps never invoke `provision-e2e-target.sh`
  without `--check-only` — no privileged action is reachable from this
  workflow (SC-006).

**Checkpoint**: Readiness of either profile is diagnosable from CI for
zero Claude quota and about one runner-minute, without touching User
Story 1's code paths.

---

## Phase 5: User Story 3 - Reuse one scratch target instead of accumulating new ones (Priority: P3)

**Goal**: An existing, non-fresh repository under the requested name is
either adopted (if it is empty or already carries this tool's marker) or
refused with a named reason (if it is a foreign repository) — never
deleted, never silently accepted.

**Independent Test**: provision a target, dispatch a verification against
it, then run provisioning against that same target again — it reports
ready, creates no second repository, and deletes nothing.

### Implementation for User Story 3

- [X] T024 [P] [US3] Write
  `.github/scripts/e2e-provisioning-tests/t5_refuse_foreign.sh`: seed
  `gh_stub.py` with a pre-existing, non-empty repository under the chosen
  name whose description does not match the marker string, run
  `provision-e2e-target.sh --repo OWNER/NAME --profile
  spec-kit-scratch`, and assert refusal naming that the repository
  "cannot be established as a reusable scratch verification target" with
  no mutating call made (data-model.md D3, Acceptance Scenario 3,
  quickstart step 6's second command).
- [X] T025 [US3] Harden the `scratch_marker` refusal ordering (depends on
  T024 exposing the gap; touches
  `.github/scripts/e2e-provisioning/checks.sh` and
  `.github/scripts/provision-e2e-target.sh`): refusal of a foreign
  repository must happen before any privileged action in T011-T015 is
  attempted against it, while an empty pre-existing repository (zero
  commits, no non-default description) is adopted rather than refused —
  making T024 pass.
- [X] T026 [P] [US3] Write
  `.github/scripts/e2e-provisioning-tests/t6_no_delete.sh`: statically
  assert no code path in `provision-e2e-target.sh` or
  `.github/scripts/e2e-provisioning/*.sh` issues `gh repo delete`, `gh
  repo archive`, or any equivalent API call (FR-016, SC-008) — mirroring
  how `auto-update-spec-kit-tests/t4_verify.sh` already asserts the
  narrower `e2e-stage` scope.

**Checkpoint**: All three user stories are independently functional;
targets accumulate only when a maintainer deliberately names a new one.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation (FR-012), the single-home gate (SC-007), and
wiring both into the PR-time gate suite.

- [X] T027 [P] Update `docs/setup.md`'s
  `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_SCRATCH_REPO` and
  `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` rows to point at
  `.github/scripts/provision-e2e-target.sh` instead of "create one empty
  private repository by hand" / requiring a pre-created,
  maintainer-onboarded repository, while keeping "the pipeline never
  creates or deletes repositories" true as written for every
  App-token-scoped step (FR-012); add a note that retiring a provisioned
  target is a manual maintainer action in the GitHub UI and that no
  entry point in this repository offers to delete or archive one
  (FR-016, Acceptance Scenario 2 of User Story 3).
- [X] T028 [P] Update `docs/adoption.md`'s Prerequisites walkthrough to add
  a pointer to `.github/scripts/provision-e2e-target.sh` as the tool this
  repository uses to stand up its own E2E targets (FR-012).
- [X] T029 Write `.github/scripts/verify-e2e-provisioning-single-home.py`
  (SC-007, Constitution VIII), following
  `.github/scripts/verify-spec-meta-single-home.py`'s shape: fails when
  any workflow or script outside
  `.github/scripts/e2e-provisioning/checks.sh` and `profiles.sh` defines
  its own copy of the onboarding-element list or a second
  `TargetProfile`-shaped mapping; a `--self-test` fixture that (a) passes
  the real tree, (b) pastes a second copy of the element list into a
  workflow and expects a failure naming that line, (c) removes
  `auto-update-spec-kit-scratch-preflight.yml`'s call to `checks.sh` and
  expects a failure ("a gate that cannot fail proves nothing").
- [X] T030 Add a `run: python3
  .github/scripts/verify-e2e-provisioning-single-home.py` step and a
  `run: bash .github/scripts/e2e-provisioning-tests/run-tests.sh` step to
  `.github/workflows/lint-workflows.yml`, mirroring the existing
  `auto-update-spec-kit-tests/run-tests.sh` step, so both are picked up
  automatically by `run-local-gates.py`'s derivation from
  `wc_gate_registry.pr_time_invocations` (no separate registration
  needed).
- [X] T031 Run `python .github/scripts/run-local-gates.py` and fix any
  failures this feature introduces, including
  `review-step-gating`/`container-shell-safety` skill passes if T021/T022
  touched an `if:`/`continue-on-error:` in a way either skill covers.
- [ ] T032 Manually walk through
  `specs/053-e2e-scratch-provisioning/quickstart.md` steps 1-7 end to end
  against a real disposable repository, confirming each `Expected:`
  outcome, and record the result for the implementation-stage report.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion (T001) — BLOCKS
  all user stories, since `checks.sh`/`profiles.sh` is the one shared
  library FR-008/FR-010 require both callers to source.
- **User Story 1 (Phase 3)**: Depends on Foundational (Phase 2) and the
  `provision-e2e-target.sh` stub (T003). No dependency on US2 or US3.
- **User Story 2 (Phase 4)**: Depends on Foundational (Phase 2) and on
  `provision-e2e-target.sh`'s `--check-only` path existing (T016, end of
  US1) — the readiness workflow invokes that flag. Can be staffed in
  parallel with US3 once US1's T016 lands.
- **User Story 3 (Phase 5)**: Depends on Foundational (Phase 2) and on
  `provision-e2e-target.sh`'s privileged actions existing (T011-T015, US1)
  so the refusal-ordering fix (T025) has something to reorder. Can be
  staffed in parallel with US2.
- **Polish (Phase 6)**: Depends on US1, US2, and US3 all being complete.

### Within Each User Story

- US1's implementation tasks (T010-T016) all edit
  `provision-e2e-target.sh` and are strictly sequential.
- US1's test tasks (T017-T020) each write a different file and can run
  in parallel with each other, after T016.
- US2's two implementation tasks (T021-T022) edit the same workflow file
  and are sequential; its one test task (T023) follows.
- US3's T024 (test) and T026 (test) touch different new files and can
  run in parallel with each other; T025 (the fix) depends on T024 and
  touches both `checks.sh` and `provision-e2e-target.sh`.

### Parallel Opportunities

- Setup: T002 and T003 in parallel (different files from T001).
- Foundational: T004 in parallel with the start of T005 (different
  files); T005-T009 are sequential (same file, `checks.sh`).
- User Story 1: T017-T020 in parallel once T016 lands.
- Once Foundational (Phase 2) and US1's T011-T016 are done, US2 and US3
  can proceed in parallel (different files: a workflow vs. the shared
  library/entry point).
- Polish: T027 and T028 in parallel (different doc files).

---

## Parallel Example: User Story 1 tests

```bash
# After T016 (orchestration) lands, launch all four test files together:
Task: "Write t1_new_target.sh — brand-new repository, app_installation is the only gap"
Task: "Write t2_idempotent.sh — second run against an already-ready target is a no-op"
Task: "Write t3_converge_after_install.sh — app_installation flips ready after a simulated install"
Task: "Write t4_refuse_self.sh — pointing at this repository is refused with zero gh calls"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational — the shared `checks.sh`/`profiles.sh`
   library (CRITICAL, blocks every story).
3. Complete Phase 3: User Story 1.
4. **STOP and VALIDATE**: run `t1_new_target.sh` through
   `t4_refuse_self.sh`, then quickstart.md steps 1-5 against a real
   disposable repository (Acceptance Scenarios 1, 2, 3, 5).
5. This is SC-001/SC-004's whole ask delivered: a maintainer or agent can
   go from "no E2E target" to "a target a dispatch reaches the agent
   stages against" without waiting on a human to pre-onboard one.

### Incremental Delivery

1. Setup + Foundational → shared library ready.
2. Add User Story 1 → validate independently → the core ask is delivered
   (MVP).
3. Add User Story 2 → validate independently → readiness is diagnosable
   for zero Claude quota.
4. Add User Story 3 → validate independently → reuse and the
   never-delete guarantee are locked in by a gate-checked test.
5. Polish → docs point at the new tool, the single-home gate protects
   FR-010/SC-007, and the full local gate suite passes.

### Parallel Team Strategy

With two maintainers/agents (CLAUDE.md's "keep concurrent local agents to
two"):

1. Both complete Setup + Foundational together (small, sequential-file
   work anyway).
2. Once Foundational is done: one continues User Story 1
   (`provision-e2e-target.sh`'s privileged actions); the other starts
   drafting User Story 2's workflow generalization against the
   Foundational library, ready to wire in `--check-only` the moment
   User Story 1's T016 lands.
3. Once User Story 1 lands, User Story 2 and User Story 3 proceed in
   parallel (different files: workflow vs. shared library/entry point).
4. Either agent finishes with Polish once all three stories are done.

---

## Phase 7: Convergence

- [X] T033 Add real test coverage for the `container_image_pin` onboarding
  element per FR-017 / US1 Acceptance Scenario 1 (partial): extend
  `.github/scripts/e2e-provisioning-tests/` (either a new `tN_*.sh` or an
  addition to `t1_new_target.sh`) with a scenario that sets
  `WC_SOURCE_CONTAINER_IMAGE` to a real, non-empty value and seeds a target
  whose `WING_COMMANDER_CONTAINER_IMAGE` variable is absent or set to a
  different value; assert `container_image_pin` starts `ready: false` with
  a `remaining_action` naming the image, assert `provision-e2e-target.sh`
  performs a `gh variable set WING_COMMANDER_CONTAINER_IMAGE` call (via
  `$GH_CALLS`) to converge it, and assert a subsequent run reports
  `ready: true` with zero further mutating calls. `t1_new_target.sh`'s
  existing assertion that `container_image_pin` is `ready` never actually
  exercises `act_container_image_pin` — both sides default to the empty
  string, so it is vacuously ready without the privileged action ever
  running.

---

## Maintainer Feedback

Findings from charlesguse's code review of PR #374 at head 551f6ce. Confirmed against the current branch by reading `.github/scripts/e2e-provisioning/checks.sh` and `.github/scripts/provision-e2e-target.sh` directly (not just the test suite, since `gh_stub.py` implements behaviours the real `gh`/API do not have and would hide these).

- [X] T034 Fix `check_spec_request_label` (checks.sh:75): `gh label view` is not a real `gh label` subcommand (gh offers clone/create/delete/edit/list only), so this check can never pass against the real CLI. Replace with `gh label list --json name` matched against `spec-request`, or `gh api repos/{owner}/{name}/labels/spec-request`. Update `gh_stub.py` to reject `label view` so the test suite would have caught this (FR-002, FR-004).
- [X] T035 Fix `check_app_installation` (checks.sh:35): confirm against the REST API docs whether `GET /repos/{owner}/{repo}/installation` requires an App-JWT (not a maintainer's or installation's own token); if so, answer this element from the token-mint outcome the readiness workflow's own header already describes ($TOKEN_OUTCOME) rather than this call, or from a call that works with the caller's own token (FR-002, FR-004, FR-015, US1 Acceptance Scenario 4/5).
- [X] T036 Confirm the App's declared permission set (docs/setup.md: Contents, Issues, Pull requests) actually covers `gh secret list` (checks.sh:67) and `gh variable list` (checks.sh:118), which need Secrets/Variables read. Either document and require the extra permissions for `--check-only` in CI, or have those checks report "not checkable with this token" instead of "not-ready" when the call fails for a permission reason (FR-002, FR-017).
- [X] T037 Move the scratch-marker self-refusal (provision-e2e-target.sh:107) so it only runs on the mutating path, not before the `--check-only` branch (line 179). Today `--check-only` against a hand-onboarded, non-empty, unmarked target (the normal shape of an existing pre-053 target) exits 1 with no JSON report instead of reporting `ready`, breaking FR-011 and US2 Acceptance Scenario 2/Independent Test.
- [X] T038 Fix marker assignment for an empty target: `check_scratch_marker` (checks.sh:48-58) returns success (ready) for `diskUsage == 0`, so `act_scratch_marker` (provision-e2e-target.sh:194-196) is never invoked for a freshly created, still-empty target (e.g. `spec-kit-scratch` profile, which pushes nothing). Once the target is later populated by `e2e-stage`, a re-provision is refused as foreign-non-empty-unmarked. Separate "already marked" from "empty enough to claim" and write the marker whenever it is absent, regardless of disk usage (US3 Acceptance Scenario 1, SC-003).
- [X] T039 Together with T038, write the scratch marker before the first content push (currently last, after `act_wrapper_set`), so a run that dies or whose `gh repo edit` fails between the two leaves a re-runnable state instead of a non-empty, unmarked repository that the self-refusal then blocks forever (spec.md Edge Cases: "interrupted partway").
- [X] T040 Fix `act_container_image_pin` (provision-e2e-target.sh:169-173): `value="$(this_repo_container_image)" || value=""` silently overwrites the target's pin with an empty string when the source read fails (auth, cwd, network), rather than failing loudly. Fail the action instead of writing a wrong empty pin, and confirm what `gh variable set --body ""` actually does before relying on empty-string-as-valid semantics elsewhere (FR-017).
- [X] T041 Verify: `check_scratch_marker`'s and the foreign-non-empty rail's reliance on `diskUsage == 0` (checks.sh:54-55) can read 0 for a tiny or freshly-pushed repo; consider `gh repo view --json isEmpty` instead. Also verify that `check_scratch_marker`/`check_repository` treating any `gh repo view` failure (auth, network) as "does not exist" doesn't fail the FR-007 self-refusal open when the git remote can't be resolved (provision-e2e-target.sh:95, constitution VIII: fail loudly rather than pass vacuously).
- [X] T042 Verify: wrapper pinning at provision-e2e-target.sh:139-143 pins wrapper `uses:` refs to local `HEAD` (`git rev-parse HEAD`, possibly unpushed) and to `this_repo_from_git` (empty without an `origin` remote). Confirm whether this can produce wrappers pointing at an unreachable ref, and fix if so.

**Resolution notes** (this session, no live GitHub API access to fully verify T035/T041 against a real installation): T034 switched to `gh api repos/{owner}/{name}/labels/spec-request`, with `gh_stub.py` no longer implementing `label view` at all. T035 trusts a new `WC_APP_INSTALLATION_KNOWN_READY` env hint (set by the readiness workflow, which already proved installation by successfully minting a target-scoped token) ahead of the JWT-only REST call, which is kept as a best-effort fallback for the local path -- this is the documented behavior of that endpoint, but wasn't re-verified against a live installation here. T036 distinguishes a 403 (`Resource not accessible by integration`) from a real not-ready and reports "not checkable with this token" instead of a false not-ready -- and, for `container_image_pin`, closes a latent false-positive where a swallowed 403 with both sides empty previously read as ready. T037 scopes the scratch-marker self-refusal to the mutating path only. T038/T039 write the marker immediately once the repository exists (separating "already marked" from "empty enough to claim"), before any other privileged action. T040 fails loudly instead of pinning an empty image on a read failure. T041 switches to `isEmpty` over `diskUsage == 0`; the `gh repo view` "does not exist" fallback and the self-refusal's git-remote resolution were left as designed (a mis-resolved "not ready" only ever pushes the aggregate report further toward not-ready, never a false ready) rather than re-verified live. T042 fails loudly when `this_repo_from_git` can't resolve an owner/repo, and warns (non-fatal, to avoid breaking a normal commit-then-push local workflow) when HEAD is ahead of its upstream tracking branch. New regression coverage: `t9_maintainer_feedback.sh`.
