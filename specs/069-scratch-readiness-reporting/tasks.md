---

description: "Task list template for feature implementation"
---

# Tasks: A readiness verdict that is reachable and documentation that matches it

**Input**: Design documents from `specs/069-scratch-readiness-reporting/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (cli.md, readiness-report.schema.json, readiness-workflow.md), quickstart.md

**Tests**: plan.md's Technical Context names the existing bash harness
(`.github/scripts/e2e-provisioning-tests/`) as the test surface this feature
extends, not a new one, and lists specific extensions (`t4_refuse_self.sh`,
`t9_maintainer_feedback.sh`) plus new tri-state/exit-code cases. Test tasks
are included below as regular implementation tasks, matching this
repository's own precedent in `specs/053-e2e-scratch-provisioning/tasks.md`.

**Organization**: Tasks are grouped by user story to enable independent
implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Single-project tooling correction, entirely inside this repository's
existing `.github/scripts/`, `.github/workflows/`, `docs/`, and
`specs/053-e2e-scratch-provisioning/` layout (plan.md Structure Decision) —
no new file, directory, or language. This feature's own
`specs/069-scratch-readiness-reporting/{data-model.md,contracts/,quickstart.md}`
are already the Phase 0/1 design output and are not themselves edited by
any task below; they are the target state several tasks converge other
files to.

---

## Phase 1: Setup

**Purpose**: Establish a baseline before changing behaviour, so every
resulting test diff is attributable to this feature and nothing else.

- [X] T001 Run `bash .github/scripts/e2e-provisioning-tests/run-tests.sh`
  on the unmodified tree and record the result (all nine suites passing) as
  the baseline this feature's test-file edits are diffed against.

---

## Phase 2: Foundational

**Not applicable to this feature.** No shared blocking prerequisite spans
more than one user story: User Story 1's tri-state classification lives
entirely inside `checks.sh`/`provision-e2e-target.sh`/the readiness
workflow; User Story 2 is a documentation-only correction that depends on
User Story 1's *shipped shape* (tracked below, in Dependencies, not as a
blocking phase); User Story 3's `act_repository` fix, its two new
regression cases, and its hint-disclosure work are independent bugs in
different code paths. Noted explicitly rather than silently skipped
(matching this repository's own constitution-check convention for an
inapplicable gate).

---

## Phase 3: User Story 1 - A maintainer can tell "all clear" from "something is wrong" from "nobody could check" (Priority: P1) 🎯 MVP

**Goal**: `assemble_report` (`.github/scripts/e2e-provisioning/checks.sh`)
produces a three-valued per-element outcome (`ready`/`missing`/
`not_checkable`) and a three-valued aggregate verdict (`all_clear`/
`not_clear`/`unverified`), each with its own exit status, replacing the
two-valued `ready: bool` that made `auto-release`'s all-clear verdict
unreachable.

**Independent Test**: run the documented route for each profile against a
fully onboarded target and confirm the aggregate verdict and exit status
alone identify which of the three outcomes holds — `all_clear` for
`spec-kit-scratch`, `unverified` for `auto-release` — without reading
individual element rows.

### Implementation for User Story 1

- [X] T002 [US1] In `.github/scripts/e2e-provisioning/checks.sh`, make
  `check_app_installation` set a global `APP_INSTALLATION_NOT_CHECKABLE=true`
  whenever `WC_APP_INSTALLATION_KNOWN_READY` is not exactly the literal
  string `true`, mirroring the existing `CLAUDE_CREDENTIAL_NOT_CHECKABLE`/
  `CONTAINER_IMAGE_PIN_NOT_CHECKABLE` convention (research.md D1). Add a
  comment noting this element's `check` therefore never has a
  `missing`-shaped failure — only `ready` or `not_checkable` (research.md
  D5) — because the one route that could ever prove non-installation (the
  readiness workflow's own App-token mint failing) already exits before
  `checks.sh` runs at all.
- [X] T003 [US1] Rewrite `assemble_report` in
  `.github/scripts/e2e-provisioning/checks.sh` to classify each element's
  outcome as `ready` (`check_$key` returned 0), `not_checkable`
  (`check_$key` returned 1 and `<KEY_UPPER>_NOT_CHECKABLE=true`), or
  `missing` (`check_$key` returned 1, flag unset); compute `verdict` with
  the precedence "any element `missing` → `not_clear`; else any element
  `not_checkable` → `unverified`; else `all_clear`" (research.md D2, FR-003);
  emit the shape `contracts/readiness-report.schema.json` defines:
  `elements[].outcome` (enum `ready`/`missing`/`not_checkable`),
  `elements[].remaining_action` (non-null iff `outcome != "ready"`, and for
  `not_checkable` naming the route that can check it, FR-005), and
  top-level `verdict` (enum `all_clear`/`not_clear`/`unverified`) — dropping
  `ready`/`elements[].ready` entirely (this is a breaking JSON-shape change,
  research.md D4, deliberately with no compatibility field). Depends on
  T002.
- [X] T004 [US1] In `.github/scripts/provision-e2e-target.sh`, update the
  stderr human-readable summary (the `jq -r '.elements[] | (if .ready then
  ... else ...)' ` line) to render three distinct labels for `ready`/
  `missing`/`not_checkable` keyed on `.outcome`, replacing the current
  `[ready]`/`[NOT READY]` two-valued rendering. Depends on T003.
- [X] T005 [US1] In `.github/scripts/provision-e2e-target.sh`, replace the
  closing `if [ "$(jq -r .ready <<<"$REPORT")" = "true" ]; then exit 0; fi;
  exit 1` block with one that reads `.verdict` from `$REPORT` and exits `0`
  for `all_clear`, `1` for `not_clear`, `2` for `unverified` (research.md
  D3) — a run MUST NOT exit `0` for anything but `all_clear` (FR-004).
  Depends on T003.
- [X] T006 [P] [US1] In
  `.github/workflows/auto-update-spec-kit-scratch-preflight.yml`'s "Run the
  readiness check" step, replace the
  `(if .ready then "✅" else "❌" end)` job-summary rendering with three
  visually and textually distinct states keyed on `.outcome` (`ready` → ✅,
  `missing` → ❌, `not_checkable` → ➖ or an equivalently distinct glyph,
  never ✅ or ❌ — contracts/readiness-workflow.md), and add an aggregate
  line naming which of `all_clear`/`not_clear`/`unverified` the run reached
  instead of a bare pass/fail; keep exiting with
  `provision-e2e-target.sh`'s own `$rc` unchanged. Depends on T003.

### Tests for User Story 1

- [X] T007 [P] [US1] Update
  `.github/scripts/e2e-provisioning-tests/t1_new_target.sh`: the expected
  exit code changes from `1` to `2` (nothing is missing; only
  `app_installation` is `not_checkable`); `"T1 overall ready is false"`
  becomes an assertion that `.verdict` is `"unverified"`; `"T1
  app_installation is not ready"` becomes an assertion that its `.outcome`
  is `"not_checkable"`; every other `.elements[].ready` check is renamed to
  `.elements[].outcome == "ready"`. Depends on T003, T004, T005.
- [X] T008 [P] [US1] Update
  `.github/scripts/e2e-provisioning-tests/t2_idempotent.sh`: rename both
  `jq -r .ready` checks to `jq -r .verdict`, asserting `"all_clear"`
  (behaviour is unchanged here — `app_installation` is hinted ready).
  Depends on T003, T004, T005.
- [X] T009 [P] [US1] Update
  `.github/scripts/e2e-provisioning-tests/t3_converge_after_install.sh`:
  the first run's expected exit code changes from `1` to `2`; `"T3 first
  run reports not ready"` becomes `.verdict == "unverified"`; `"T3 first
  run: only app_installation is not ready"` becomes a
  `select(.outcome != "ready")` assertion naming `app_installation`
  (`not_checkable`, not `missing`); the second run's `.ready == "true"`
  check becomes `.verdict == "all_clear"`. Depends on T003, T004, T005.
- [X] T010 [P] [US1] Update
  `.github/scripts/e2e-provisioning-tests/t5_refuse_foreign.sh` (the
  `select(.key=="repository") | .ready` check): rename to `.outcome`,
  asserting `"ready"` — no behavioural change, this element is never
  checked-and-missing in this scenario. Depends on T003, T004, T005.
- [X] T011 [P] [US1] Update
  `.github/scripts/e2e-provisioning-tests/t8_container_image_pin.sh`:
  rename every `.ready`/`.elements[].ready` reference to `.verdict`/
  `.outcome`; the check-only mismatch case keeps exit `1` because
  `container_image_pin` is genuinely `missing` under the maintainer's own
  credential here (not `not_checkable` — that only happens to the App
  token on the dispatched route), so its top-level check becomes
  `.verdict == "not_clear"`; the two real-run cases become
  `.verdict == "all_clear"`. Depends on T003, T004, T005.
- [X] T012 [US1] Update
  `.github/scripts/e2e-provisioning-tests/t9_maintainer_feedback.sh`'s
  T036, T037/T044, T038/T039, and T043 blocks: rename every
  `.elements[].ready` check to `.outcome` (T036's two permission-denied
  elements now assert `"not_checkable"`, not the boolean `"false"`;
  T037/T038/T039/T043's ready elements assert `"ready"`); add to T036 an
  overall `.verdict == "unverified"` assertion and a captured exit-code
  `2` assertion (this block never asserted the aggregate before); add to
  T038/T039's *first* run (spec-kit-scratch profile, no hint exported) a
  captured `RC=$?` asserting `2` and `.verdict == "unverified"` — closing
  the gap that no existing test covers the Edge Cases scenario "a
  `spec-kit-scratch` target['s] local run ... moves from the failure
  status to the unverified status (FR-006)"; rename T043's two `.ready`
  checks to `.outcome` (`"not_checkable"` then `"ready"`). Depends on T003,
  T004, T005.
- [X] T013 [P] [US1] Update
  `.github/scripts/e2e-provisioning-tests/t7_readiness_workflow.sh`: add
  assertions that the workflow's `run:` block reads `.outcome`/`.verdict`
  (not the retired `.ready`) and renders three distinct glyphs plus a named
  aggregate verdict line, so a regression that reintroduces the old
  two-valued rendering fails this suite. Depends on T006.

**Checkpoint**: User Story 1 is fully functional and independently
testable — `spec-kit-scratch` reaches `all_clear`/exit `0` through the
dispatched route, `auto-release`'s best attainable verdict is `unverified`/
exit `2`, and a genuinely missing element still reports `not_clear`/exit
`1`.

---

## Phase 4: User Story 2 - Every document describes the behaviour the tool actually has (Priority: P2)

**Goal**: The 053 spec, plan, data model, quickstart, three contracts, and
the two adopter-facing docs (`docs/setup.md`, `docs/adoption.md`) describe
the tri-state verdict User Story 1 ships — not the two-valued,
convergence-by-re-run behaviour a prior amendment already removed.

**Independent Test**: read each named location end to end against the
shipped tri-state behaviour and confirm no statement in it is false.

### Implementation for User Story 2

- [X] T014 [US2] Correct
  `specs/053-e2e-scratch-provisioning/spec.md`'s Clarifications
  session-2026-09-16 record (currently ending "...and converges on a
  re-run once the human has done it") to describe convergence as observed
  by dispatching the readiness check, not a re-run of the local command
  (FR-009) — matching this file's own already-corrected FR-015 wording
  elsewhere.
- [X] T015 [US2] Correct `specs/053-e2e-scratch-provisioning/plan.md`'s
  Constraints bullet (currently "...the one declared manual App-install
  step, and one re-invocation complete in under 15 minutes wall-clock") to
  measure completion by dispatching the readiness check instead of "one
  re-invocation" (FR-009).
- [X] T016 [US2] Correct
  `specs/053-e2e-scratch-provisioning/data-model.md`: remove
  `gh api .../installation` and `gh label view` from `OnboardingElement`'s
  `check` read-call list (neither is called by the shipped implementation
  — the label check uses `gh api repos/.../labels/spec-request`, and
  `app_installation` trusts `WC_APP_INSTALLATION_KNOWN_READY` alone);
  record the `--check-only` scratch-marker exemption next to
  `scratch_marker`'s row; replace the `ReadinessReport`/`ready: bool`
  table and the Relationships/State-transitions sections with this
  feature's tri-state shape, matching
  `specs/069-scratch-readiness-reporting/data-model.md`, which states it
  "is the target state the User Story 2 documentation tasks converge
  [this file] to" (FR-011, SC-003).
- [X] T017 [US2] Correct `specs/053-e2e-scratch-provisioning/quickstart.md`
  steps 1, 3, and 4: step 1's brand-new `auto-release` target now reports
  exit code `2` (`unverified`) with `app_installation` `not_checkable`, not
  exit `1`; step 3's dispatched `auto-release` run now shows
  `claude_credential`/`container_image_pin` as `not_checkable` with the
  aggregate line `unverified`, exit `2` — never the `all_clear`/exit-`0`
  it currently promises (the originating defect, review item 2); step 4's
  local re-run's exit code changes from `1` to `2` for the same reason as
  step 1 (FR-008).
- [X] T018 [US2] Merge this feature's CLI contract amendment
  (`specs/069-scratch-readiness-reporting/contracts/cli.md`) into
  `specs/053-e2e-scratch-provisioning/contracts/cli.md` in place: replace
  step 5's two-valued exit description with the three-row `all_clear`/
  `not_clear`/`unverified` table, and add the sentence scoping the
  `scratch_marker` refusal to the mutating path only (FR-010).
- [X] T019 [P] [US2] Merge this feature's workflow contract amendment
  (`specs/069-scratch-readiness-reporting/contracts/readiness-workflow.md`)
  into
  `specs/053-e2e-scratch-provisioning/contracts/readiness-workflow.md` in
  place: replace step 4's ✅/❌-only rendering description with the
  three-outcome table and the named aggregate verdict (FR-010).
- [X] T020 [P] [US2] Merge this feature's schema amendment
  (`specs/069-scratch-readiness-reporting/contracts/readiness-report.schema.json`)
  into
  `specs/053-e2e-scratch-provisioning/contracts/readiness-report.schema.json`
  in place: replace `elements[].ready`/top-level `ready` with
  `elements[].outcome` (enum `ready`/`missing`/`not_checkable`) and
  `verdict` (enum `all_clear`/`not_clear`/`unverified`) (FR-011).
- [X] T021 [US2] Correct `docs/setup.md`'s
  `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` row (currently "...then reports
  the App installation as the one remaining manual step for as long as it
  is absent") to describe convergence as observed by dispatching the
  readiness check against the target, not a further local re-invocation
  (FR-009).
- [X] T022 [P] [US2] Correct `docs/adoption.md`'s matching sentence
  (currently "...which it reports as the sole remaining step for as long
  as it is absent") the same way (FR-009).
- [X] T023 [US2] Read
  `specs/053-e2e-scratch-provisioning/{spec.md,plan.md,data-model.md,
  quickstart.md,contracts/cli.md,contracts/readiness-workflow.md,
  contracts/readiness-report.schema.json}` and
  `docs/{setup.md,adoption.md}` end to end against the shipped tri-state
  behaviour and confirm no two of them describe the verdict, exit status,
  marker-refusal scope, or read-call list differently (FR-012, SC-003) —
  User Story 2's own Independent Test. Depends on T014, T015, T016, T017,
  T018, T019, T020, T021, T022.

**Checkpoint**: Every document User Story 2 names matches the tri-state
behaviour User Story 1 shipped; a reader following any of them sees exactly
the described output.

---

## Phase 5: The provisioning tool fails with the true reason, and its tests say what they stand in for (Priority: P3)

**Goal**: A failed repository creation is reported as a failed repository
creation, not a misdiagnosed marker-write failure; the two behaviours the
prior review verified only by hand gain regression coverage; the
honoured-hint disclosure (FR-015) is visible and tested; the test that
depends on the hint states what it stands in for.

**Independent Test**: force repository creation to fail and confirm the
reported reason names repository creation; run the test suite and confirm
the two previously-uncovered behaviours are now asserted.

### Implementation for User Story 3

- [X] T024 [US3] In `.github/scripts/provision-e2e-target.sh`, change the
  `if ! check_repository "$OWNER" "$NAME"; then act_repository "$OWNER"
  "$NAME"; fi` call site to check `act_repository`'s own exit status and
  stop immediately — naming repository creation as the failed action,
  before the `scratch_marker` write two steps below is ever attempted —
  mirroring the existing `act_scratch_marker` failure-handling pattern a
  few lines later in the same file (research.md D6, FR-013).
- [X] T025 [P] [US3] In
  `.github/scripts/e2e-provisioning-tests/gh_stub.py`'s `repo create`
  handler, add a `create_forbidden` failure-injection seam: if the target
  full name is already present in state (pre-seeded via `gh_state_set`
  before the repository "exists") with `create_forbidden: true`, write an
  HTTP-error-shaped message to stderr and return `1` without creating or
  overwriting the entry — extending the existing `edit_forbidden`/
  `secrets_forbidden`/`variables_forbidden` precedent rather than adding a
  new mechanism.
- [X] T026 [US3] Add a new case to
  `.github/scripts/e2e-provisioning-tests/t9_maintainer_feedback.sh` using
  the `create_forbidden` seam: assert the run exits `1`, its stderr names
  repository creation as the failed action (and never contains "failed to
  write the scratch marker"), and no `repo edit`/`secret set`/
  `label create` call was made. Depends on T024, T025.
- [X] T027 [P] [US3] Add a new case to
  `.github/scripts/e2e-provisioning-tests/t4_refuse_self.sh`: using the
  same `PATH`-shadowing `git` fixture T045 (in `t9_maintainer_feedback.sh`)
  already builds, export `GITHUB_REPOSITORY` naming the target itself and
  assert refusal with the FR-007 self-target message (not T045's "could
  not determine this repository" message) and zero `gh` calls (research.md
  D7, FR-014).
- [X] T028 [US3] In `.github/scripts/provision-e2e-target.sh`'s stderr
  summary block, add a one-line note after `app_installation`'s row —
  `  (confirmed via WC_APP_INSTALLATION_KNOWN_READY -- see docs/setup.md if
  this was not set intentionally)` — printed whenever that element's
  `outcome` is `ready` (research.md D5: the hint is the only way it is
  ever `ready`), so a false-ready report is traceable from the script's own
  output (research.md D8, FR-015). Depends on T004.
- [X] T029 [P] [US3] Add the D9 comment FR-017 requires to
  `.github/scripts/e2e-provisioning-tests/t9_maintainer_feedback.sh`'s
  T037/T044 block: state explicitly that the exported hint stands in for
  the dispatched readiness check's own token-mint proof of installation,
  does not exercise real JWT-only verification, and is why the local,
  maintainer-run path can never itself reach `app_installation: ready` —
  the exact limitation User Story 1 addresses. Depends on T012 (field
  renames must land in that block first).

### Tests for User Story 3

- [X] T030 [P] [US3] Extend
  `.github/scripts/e2e-provisioning-tests/t9_maintainer_feedback.sh`'s
  T043 hint-honoured case: assert stderr contains the D8 disclosure note
  after `WC_APP_INSTALLATION_KNOWN_READY=true` is exported (FR-015
  regression coverage). Depends on T028.
- [X] T031 [P] [US3] Document `WC_APP_INSTALLATION_KNOWN_READY` in
  `docs/setup.md`: name it, state that the generalized readiness-check
  workflow is its legitimate setter, and warn that a stray `true` value
  left in a maintainer's own shell produces a false-`ready` local report
  for `app_installation` only, never any other element (FR-016). Sequenced
  after T021 (same file).
- [X] T032 [P] [US3] Add the same documentation to `docs/adoption.md`
  (FR-016). Sequenced after T022 (same file).

**Checkpoint**: A failed repository creation names itself; the self-target
refusal via `GITHUB_REPOSITORY` and the failed-repository-creation reason
both have regression coverage; the honoured hint is disclosed at runtime,
documented, and its test-time stand-in is stated in the test itself.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T033 [P] Run `python .github/scripts/run-local-gates.py` and
  `python .github/scripts/verify-e2e-provisioning-single-home.py` (plus its
  `--self-test`), confirming the single-home gate still passes unchanged
  (plan.md Constraints, Constitution VIII) and every other PR-time gate is
  green.
- [X] T034 Run `bash .github/scripts/e2e-provisioning-tests/run-tests.sh`,
  confirm all nine suites pass against the rewritten scripts, and diff the
  result against T001's baseline to confirm every changed assertion is an
  intentional, accounted-for change from this feature.
- [X] T035 Walk `specs/069-scratch-readiness-reporting/quickstart.md`
  steps 1-7 (as much as is locally reproducible against a real disposable
  target) and confirm the verdicts/exit codes it documents match what the
  changed scripts actually produce (SC-001, SC-002, SC-004, SC-006,
  SC-008).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Not applicable (see above) — does not block
  anything.
- **User Story 1 (Phase 3)**: Can start after Setup. No dependency on
  User Story 2 or 3.
- **User Story 2 (Phase 4)**: Depends on User Story 1's *shipped shape*
  (T003-T006) — it corrects documents to describe the tri-state verdict
  User Story 1 produces, so it must describe what actually ships, not a
  provisional design (spec.md: "it depends on how User Story 1 resolves").
- **User Story 3 (Phase 5)**: Independent of User Story 1 and 2 for its
  `act_repository`/self-target-refusal work (T024-T027); its
  hint-disclosure work (T028-T030) depends on User Story 1's T004 (same
  stderr-rendering block); its documentation tasks (T031-T032) are
  sequenced after User Story 2's T021/T022 only because they edit the same
  two files, not because of a content dependency.
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### Within Each User Story

- User Story 1: T002 → T003 → {T004, T005, T006} → {T007-T013} (tests
  depend on the implementation tasks whose files they exercise).
- User Story 2: T014-T022 have no dependencies on each other (different
  files/sections) and can run in any order once User Story 1 has shipped;
  T023 (the consistency read-through) depends on all of them.
- User Story 3: T024 → T026 (needs T025's seam too); T027 is independent;
  T028 (depends on T004) → T030; T029 depends on T012 (User Story 1);
  T031/T032 depend on T021/T022 (User Story 2) only by same-file
  sequencing.

### Parallel Opportunities

- All of T007-T013 (User Story 1 tests) touch different files and can run
  in parallel once T003-T006 land.
- T018-T020 (the three contract-file merges) touch different files and can
  run in parallel.
- T025 and T027 (User Story 3) touch different files from T024 and from
  each other.
- T031 and T032 touch different files (`docs/setup.md` vs
  `docs/adoption.md`) and can run in parallel with each other, though each
  is sequenced after its own User-Story-2 counterpart.

---

## Parallel Example: User Story 1 tests

```bash
# Once T003 (assemble_report rewrite), T004 (stderr rendering), and T005
# (exit-code mapping) are all in place, launch every test-file update
# together:
Task: "Update t1_new_target.sh exit code and outcome/verdict field renames"
Task: "Update t2_idempotent.sh .ready -> .verdict renames"
Task: "Update t3_converge_after_install.sh exit code and outcome/verdict renames"
Task: "Update t5_refuse_foreign.sh .ready -> .outcome rename"
Task: "Update t8_container_image_pin.sh .ready -> .verdict/.outcome renames"
Task: "Update t9_maintainer_feedback.sh T036/T037/T038-T039/T043 renames"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (baseline).
2. Complete Phase 3: User Story 1 — this alone fixes the motivating defect
   (an unreachable all-clear verdict for `auto-release`) and is
   independently testable per its own Independent Test.
3. **STOP and VALIDATE**: run `run-tests.sh`, confirm the tri-state verdict
   and exit codes match research.md D2/D3 for both profiles.

### Incremental Delivery

1. Setup → User Story 1 (MVP: the verdict is reachable and correctly
   computed) → validate.
2. Add User Story 2 (the documentation now matches what User Story 1
   ships) → validate via its own Independent Test (read-through).
3. Add User Story 3 (true failure reasons, honest tests, hint disclosure)
   → validate via forced repository-creation failure and the two new
   regression cases.
4. Polish: full gate suite, full test suite, quickstart walk-through.

### Parallel Team Strategy

With multiple contributors, User Story 3's `act_repository`/self-target
work (T024, T025, T027) can start in parallel with User Story 1, since it
touches a different code path (the mutating pre-`assemble_report` guard
sequence) and has no shared-file conflict with T002-T006. User Story 3's
hint-disclosure work (T028-T030) and User Story 2 as a whole should wait
for User Story 1 to land first, per the Dependencies section above.

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to specific user story for traceability.
- This is a correction feature: no new file, directory, or test suite name
  is introduced anywhere in this task list — `run-tests.sh`'s existing
  `SUITES=(...)` line already runs every `t*.sh` file these tasks edit
  (plan.md: "Unchanged (already runs every t*.sh)").
- Commit after each task or logical group; re-run
  `.github/scripts/run-local-gates.py` before pushing (CLAUDE.md).

---

## Maintainer Feedback

- [X] MF001 In `.github/scripts/provision-e2e-target.sh`, add a `*) exit 1 ;;` default arm to the closing `case "$(jq -r .verdict <<<"$REPORT")"` statement (~line 307), so an `assemble_report` failure (empty/malformed `$REPORT`, no arm matches) fails the script instead of falling through to an implicit exit 0 (Constitution Principle VIII). Before this feature's T005 rewrite, the same situation exited 1.
- [X] MF002 Add a provisioning test (e.g. under `.github/scripts/e2e-provisioning-tests/`) that forces `assemble_report` to fail and asserts `provision-e2e-target.sh` exits non-zero, covering MF001's new default arm.
- [X] MF003 (optional) In `.github/workflows/auto-update-spec-kit-scratch-preflight.yml`'s readiness-check step (~line 154-156), branch the `::error::` message on `$rc` so the `unverified` case (rc=2) reads as "is unverified for" rather than "is not ready for", distinguishing it from the `not_clear` case (rc=1).
