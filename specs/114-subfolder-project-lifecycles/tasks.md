# Tasks: Subfolder Project Lifecycles

**Input**: Design documents from `/specs/114-subfolder-project-lifecycles/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: The spec requires deterministic gates with checked-in accept and reject fixtures for every new validation (FR-019, FR-020, SC-006), so gate tasks are included. Gate numbers come from the next free ones in `.github/scripts/run-local-gates.py`.

**Organization**: Grouped by user story. Run `python .github/scripts/run-local-gates.py` before pushing (CLAUDE.md). Workflow comments are load-bearing: re-run the suite after any comment edit. A change touching an `if:`/`continue-on-error:` also gets the `review-step-gating` skill; a `container:` job or `run:` step in one gets `container-shell-safety`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 (full subfolder lifecycle), US2 (side-by-side isolation), US3 (root unchanged), US4 (graduation by copy), US5 (nesting)

## Phase 1: Setup (Verify Assumptions)

**Purpose**: Resolve the three assumptions research.md marks for early verification.

- [X] T001 Verify whether `anthropics/claude-code-action` honours a step `working-directory`, and which parent `CLAUDE.md`/settings files it loads from a subfolder; record the result in `specs/114-subfolder-project-lifecycles/research.md` D9 (decides working-directory vs Spec Kit project-root override)
- [X] T002 [P] Read `.github/workflows/intake.yml` (allocate-number, label-creation and branch-push steps) and record the exact insertion point for label-first creation (research D7)
- [X] T003 [P] Confirm `issue-number` is usable in a reusable workflow's job-level `concurrency.group` expression in `.github/workflows/intake.yml` (research D8)
- [X] T004 [P] Inventory every `claude-code-action` step holding `Edit`/`Write` and every root-only pattern (`specs/` scans, `.specify/`, constitution, `.claude/skills/speckit-*`, `.wing-commander-pipeline/`) across `.github/workflows/*.yml` and `.github/actions/**`; list them in `specs/114-subfolder-project-lifecycles/research.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The single home for project logic, plus the gate scaffolding. No story can start until this is done.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Create `.github/actions/_shared/project-name.sh` with subcommands `validate-path`, `check-folder`, `parse`, `spec-dir`, `slug-budget`, `next-number`, `validate-prefix` per `contracts/project-path-and-names.md` (grammar `^[a-z0-9][a-z0-9-]*$` per segment, no `specs` segment, no `^[0-9]{3}-` segment, length ≤ 28, no symlinked ancestor, real `.specify/`, `.claude/`, `.claude/skills/speckit-*`, `specs/`, `.specify/memory/constitution.md`; label budget `len(NNN-slug) ≤ 44 − len(P)`)
- [X] T006 Create composite `.github/actions/wing-commander-project/action.yml` sourcing `_shared/project-name.sh`; inputs `routing-label-prefix`, `issue-number`, `identity`; outputs `project`, `slug`, `spec-dir`, `spec-dir-rel`, `slug-qualified`, `slug-budget`; failure posts a callout on the lifecycle issue naming the folder
- [X] T007 [P] Create `.github/scripts/verify-project-path-grammar.py` with fixtures under `.github/scripts/fixtures/project-path-grammar/` (accept; reject: uppercase, space, `..`, absolute, empty segment, `specs` segment, `NNN-` segment, over 28 characters, symlinked dir, symlinked ancestor, symlinked `.specify/`, `.claude/`, `specs/`, constitution)
- [X] T008 [P] Create `.github/scripts/verify-project-name-parser.py` with fixtures under `.github/scripts/fixtures/project-name-parser/` covering `branch` (spec-draft, spec, implement with `-iterN`), `label`, `slug`, `spec-dir`, root and subfolder, same `(P, NNN-slug)` across kinds, malformed rejects (FR-007, FR-013)
- [X] T009 Register T007 and T008 gates in `.github/workflows/lint-workflows.yml` and `.github/scripts/run-local-gates.py` at the next free gate numbers
- [X] T010 [P] Create `.github/scripts/verify-project-single-home.py` (FR-020) with a reject fixture per root-only pattern under `.github/scripts/fixtures/project-single-home/`: hard-coded root spec-dir pattern, root-only `.specify/` or constitution path, root-only `specs/` scan, root-resolved `.claude/skills/speckit-*` path; register it in `lint-workflows.yml` and `run-local-gates.py` (initially scoped to files already converted; widen in T046)
- [X] T011 Make `.github/actions/_shared/read-spec-meta.sh` project-aware: accept a repository-relative spec directory `[P/]specs/<NNN-slug>` to locate the file, require the recorded `spec_dir` to be exactly `specs/<NNN-slug>`, fail on any project path; root output byte-identical (FR-007, FR-008, D14)
- [X] T012 [P] Make `.github/actions/wing-commander-spec-meta/action.yml` and `.github/actions/wing-commander-inspected-run-identity/action.yml` accept and emit the repository-relative spec directory (FR-007)
- [X] T013 [P] Make `.github/actions/wing-commander-context/action.yml` derive the spec directory through `wing-commander-project`/`parse` instead of root-only patterns (FR-007)
- [X] T014 [P] Make `.github/actions/_shared/classify-out-of-boundary-tasks.sh` and `.github/actions/wing-commander-write-boundary/` (+ `-lookup`) classify `P/specs/**` documents and `P/specs/*/contracts/**` like root equivalents (FR-007); extend `.github/scripts/verify-write-boundary.py` fixtures with subfolder accept/reject cases
- [X] T015 [P] Make `.github/actions/wing-commander-tasks-checkbox-count/action.yml` and `.github/actions/_shared/count-tasks-checkboxes.sh` take the repository-relative spec directory
- [X] T016 Make `.github/actions/wing-commander-preflight/action.yml` take the `project` output and check `.specify/`, `.claude/skills/speckit-*`, constitution and the real-entry rule inside the folder, naming the folder and the missing piece; version drift reads `P/.specify/init-options.json` (FR-005, D15)
- [X] T017 [P] Make the fold-queue actions (`wing-commander-fold-queue-admit`, `-claim-dispatch`, `-ledger`, `-release`), `.github/actions/_shared/fold-queue-*.sh` and `wing-commander-chain-stop-notice` accept the repository-relative spec directory with root values unchanged

**Checkpoint**: One parser, one resolver, project-aware shared actions. Root outputs byte-identical.

---

## Phase 3: User Story 1 - Full lifecycle in a subfolder (Priority: P1) 🎯 MVP

**Goal**: Route an issue to `ideas/alpha` and carry it intake → cleanup entirely inside that folder.

**Independent Test**: In a test repo with a root project and one subfolder project, run a routed issue to cleanup. Spec, plan, tasks and code live under the folder, agents read the folder's constitution, and no agent-authored change lies outside it.

### Gates for User Story 1

- [X] T018 [P] [US1] Create `.github/scripts/verify-intake-routing.py` with fixtures under `.github/scripts/fixtures/project-intake-routing/`: label count 0/1/≥2, missing folder, non-Spec-Kit folder, routing-prefix validation (malformed shape; overlap with `spec:`, `stage:`, `model:`, `board:`, `disposition:`, findings family, `route-out-of-boundary`, `spec-request`, `spec-proposal`, `spec-`; too long), re-run refusal pair (routing on refuses with and without a `node:` label; routing off unchanged), label-first ordering, over-budget slug (FR-001, FR-003, FR-014, FR-023)
- [X] T019 [P] [US1] Create `.github/scripts/verify-subfolder-containment.py` with fixtures under `.github/scripts/fixtures/project-containment/`: `P=a/b` write to `a/.claude/` denied; denies for root `.claude/`, `.git/`, `P/.claude/`, `P/**/.claude/`; denies hold with `no-write-paths` overridden; change outside `P` fails the guard; moving a nested folder or editing a child-index README inside `P` passes; every Edit/Write `claude-code-action` step consumes `tool-args` (FR-021, FR-022)
- [X] T020 [P] [US1] Create `.github/scripts/verify-pipeline-checkout-containment.py` with fixtures under `.github/scripts/fixtures/project-checkout-containment/`: read-only grant under working directory `P` still names the workspace-root `.wing-commander-pipeline/`; repository tooling grants (`.github/scripts/run-local-gates.py`) resolve to the workspace root; branch tracking `P/.wing-commander-pipeline/x` is refused (FR-025)
- [X] T021 [US1] Register T018–T020 gates in `.github/workflows/lint-workflows.yml` and `.github/scripts/run-local-gates.py`

### Implementation for User Story 1

- [X] T022 [US1] Add optional input `routing-label-prefix` (default `''`) to `.github/workflows/intake.yml`; add a deterministic step that validates the prefix (`project-name.sh validate-prefix`), reads live labels via `gh issue view <issue-number> --json labels`, counts `node:` labels, and invokes `wing-commander-project`; two or more labels refuse with a lifecycle-issue callout and create nothing (FR-001, FR-023). Skipped entirely when the prefix is empty
- [X] T023 [US1] In `.github/workflows/intake.yml` add the re-run refusal (issue already has any `spec:` label, routing on only) per `contracts/routing-and-intake.md`
- [X] T024 [US1] In `.github/workflows/intake.yml` compute the slug budget deterministically and pass it to the intake agent prompt; after the agent writes, check the slug against the budget; create the `spec:P/<NNN-slug>` label before the first branch push; fail loudly on overflow (routing on and `P` non-empty only) (FR-014, D7)
- [X] T025 [US1] Make `.github/workflows/intake.yml` create the spec-draft branch `<prefix>P/<NNN-slug>` and write `spec-meta.json` with project-relative `spec_dir`, real `spec_branch`; emit the repository-relative `spec-dir` output (root unchanged)
- [X] T026 [US1] Extend `.github/actions/wing-commander-tool-args/` to derive the project-aware denies (root `.claude/**`, `.git/**`, each proper ancestor `E/.claude/**`, `P/.claude/**`, `P/**/.claude/**`) into the single `no-write-paths` definition, and make all trusted-checkout and repository-tooling grants absolute under `${GITHUB_WORKSPACE}` (FR-022, FR-025, D10, D11)
- [X] T027 [P] [US1] Create composite `.github/actions/wing-commander-containment/action.yml`: given the pre-agent SHA and `P`, fail the stage with a callout listing any changed path (committed or working tree) outside `P/`; skip for root lifecycles (FR-021)
- [X] T028 [US1] Add the pipeline-checkout guard check that refuses a branch tracking `**/.wing-commander-pipeline/**` at any depth (`git ls-files`); locate the guard via `grep -rn pipeline-checkout .github/` (FR-025)
- [X] T029 [US1] Wire `wing-commander-project`, project-aware preflight and the project working directory (per T001 outcome) and containment guard into `.github/workflows/intake.yml`
- [X] T030 [P] [US1] Wire the same into `.github/workflows/clarify.yml`: derive `(P, slug)` from the lifecycle identity, run preflight in `P`, agent working directory `P`, containment guard, project-aware paths in prompts and allowed-tools
- [X] T031 [P] [US1] Same wiring in `.github/workflows/plan.yml`; the plan→tasks hand-off and the manual-restart `slug` input take `P/<NNN-slug>`; document the input form in the input description
- [X] T032 [P] [US1] Same wiring in `.github/workflows/tasks.yml`; restart `slug` takes `P/<NNN-slug>`
- [X] T033 [P] [US1] Same wiring in `.github/workflows/implement.yml`; branch `<impl-prefix>P/<NNN-slug>-iterN`; `spec_dir` input and hand-offs take `P/specs/<NNN-slug>`
- [X] T034 [P] [US1] Same wiring in `.github/workflows/finalize.yml`; `spec_dir` takes the repository-relative form
- [X] T035 [P] [US1] Same wiring in `.github/workflows/rebase.yml`, `.github/workflows/pr-conversation.yml` (act and act.fold agents) and `.github/workflows/cleanup.yml`
- [X] T036 [US1] Add the stale-folder check: each later stage re-validates the recorded folder on the ref it works from (`project-name.sh check-folder`) and fails naming the folder if missing or no longer a Spec Kit project; add reject fixtures to T018's gate
- [ ] T037 [US1] Run `python .github/scripts/run-local-gates.py`; then apply `review-step-gating` and `container-shell-safety` passes to the edited workflows

**Checkpoint**: US1 independently functional: a routed lifecycle runs end to end inside its folder.

---

## Phase 4: User Story 2 - Side-by-side projects without collisions (Priority: P1)

**Goal**: Per-project numbering, names and concurrency; watchdog and fold-cycle guard attribute runs correctly.

**Independent Test**: Two projects both producing `001-login` have distinct branches, labels and groups, run in parallel, and each run is attributed to the right lifecycle.

- [X] T038 [P] [US2] Create `.github/scripts/verify-project-numbering.py` with fixtures under `.github/scripts/fixtures/project-numbering/`: per-project start at `001`, highest of `P/specs/` and anchored `refs/heads/<prefix>P/<NNN-slug>` refs, nested and sibling refs not counted, root counts only refs with no `/` after the prefix, number never reissued after branch teardown, project-scoped spec-collision check ignores another project's `004` (FR-009, FR-010); register in `lint-workflows.yml` and `run-local-gates.py`
- [X] T039 [US2] Replace the inline "Allocate feature number" scan in `.github/workflows/intake.yml` with `project-name.sh next-number <P>` (root reproduces today's numbers)
- [X] T040 [US2] Split intake concurrency in `.github/workflows/intake.yml`: numbering group `wing-commander-intake` (root) / `wing-commander-intake/P`; when routing is on, a gate job holds `wing-commander-intake-issue/<issue-number>` (`cancel-in-progress: false`) and runs the prefix check, label count and re-run refusal; the numbering job `needs:` it (FR-012, D8). Add the two-concurrent-intakes-different-projects model (fake `gh`) to T018's gate
- [X] T041 [US2] Make per-spec concurrency groups `wing-commander-<repository-relative spec dir>` in `.github/workflows/clarify.yml`, `plan.yml`, `tasks.yml`, `implement.yml`, `finalize.yml`, `rebase.yml` (root names unchanged)
- [X] T042 [US2] Make `.github/workflows/cleanup.yml` list and delete branches and labels by anchored full refnames within the finishing lifecycle's project namespace only (FR-015)
- [X] T043 [P] [US2] Make `.github/workflows/watchdog.yml` resolve project and lifecycle through the shared parser (no prefix-encoded project, no wrapper-input dependence, no project-ignoring defaults) and scope the spec-collision collector to `P/specs/` (FR-013, D13)
- [X] T044 [P] [US2] Make `.github/workflows/fold-cycle-guard.yml` resolve project and lifecycle through the shared parser; `spec_dir` restart input takes the repository-relative form
- [X] T045 [US2] Add watchdog/fold-cycle-guard accept/reject fixtures (same `NNN-slug` in two projects attributed to the right one) to `.github/scripts/fixtures/project-name-parser/` and extend `.github/scripts/verify-watchdog-resolved-stage-consumers.py` if needed
- [X] T046 [US2] Widen `.github/scripts/verify-project-single-home.py` to every stage workflow and composite under `.github/actions/**`; fix any remaining root-only pattern it finds

**Checkpoint**: US1 and US2 work together; no shared names across projects.

---

## Phase 5: User Story 3 - Root adopters unchanged (Priority: P1)

**Goal**: Byte-identical root behaviour and an additive-only interface.

**Independent Test**: This repository's lifecycle on the new version, unchanged wrappers, yields identical spec paths, branches, labels, groups and numbers.

- [X] T047 [P] [US3] Add a root-compat fixture set under `.github/scripts/fixtures/project-root-compat/` (root names for each kind, empty `P`, a pre-feature `spec-meta.json` passing the self-identity check, routing-off intake unchanged) and cover it in `verify-project-name-parser.py` and `verify-intake-routing.py` (FR-016, SC-003)
- [X] T048 [P] [US3] Add an interface-delta check (extend an existing interface-contract gate if present, else a small section of `verify-intake-routing.py`) asserting no input, secret or output of any stage workflow was removed or renamed and every new input has a root-reproducing default (FR-017)
- [ ] T049 [US3] Diff-review every edited workflow and composite for root-path byte-identity; confirm this repository's wrappers need no edit; run `python .github/scripts/run-local-gates.py`

**Checkpoint**: Root behaviour proven unchanged.

---

## Phase 6: User Story 4 - Graduation by copying (Priority: P2)

**Goal**: A copied project folder works as a root adopter with no edits.

**Independent Test**: Copy a completed subfolder project to a fresh root; its `spec-meta.json` files pass the self-identity check and numbering continues its own sequence.

- [X] T050 [P] [US4] Add copy-out fixtures under `.github/scripts/fixtures/project-graduation/`: a project folder with `spec-meta.json` (`spec_dir = specs/<NNN-slug>`, `spec_branch` unresolvable) passing at `P/specs/...` and again at root; a record carrying `P/specs/...` rejected; next-number continues the project's own sequence
- [X] T051 [US4] Extend the spec-meta self-identity gate (locate with `grep -rln spec-meta .github/scripts/verify-*.py`; create `.github/scripts/verify-spec-meta-self-identity.py` if absent) to run both rules over the T050 fixtures (FR-008); register if new
- [X] T052 [US4] Confirm no check requires `spec_branch` to resolve after teardown or graduation (grep `spec_branch` across `.github/`), fixing any that do

**Checkpoint**: Graduation proven by fixtures.

---

## Phase 7: User Story 5 - Nested projects (Priority: P3)

**Goal**: Projects at any depth within the 28-character cap are distinct and isolated.

**Independent Test**: `a/` and `a/b/` each use their own Spec Kit state and specs; `a/b/` and `c/b/` have distinct names.

- [X] T053 [P] [US5] Add nested fixtures (`a`, `a/b`, `a/b/c` three levels; `a/b` vs `c/b`; last-segment-not-used) to `verify-project-path-grammar.py`, `verify-project-name-parser.py` and `verify-project-numbering.py` (FR-004, SC-005)
- [X] T054 [US5] Confirm `project-name.sh check-folder` resolves the nearest enclosing project's state for `a/b` (own `.specify/` and constitution, not `a/`'s) and that the enclosing project's numbering scan excludes `a/b/specs/`; add fixtures

**Checkpoint**: All stories independently functional.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T055 [P] Add a "Multiple projects in one repository" section to `docs/adoption.md` covering FR-018 (a)–(d): `routing-label-prefix`, widening the plan wrapper (and tasks `pr` mode) path filter to `**/specs/**`, one `node:<path>` label per project, restart forms (`slug=P/<NNN-slug>` vs `spec_dir=P/specs/<NNN-slug>`); parent instruction files may reach a subfolder agent; `extra-allowed-tools` repository paths resolve to the workspace root; keep root instructions valid
- [ ] T056 Prepare the constitution amendment 2.4.0 → 2.5.0 (Principle VI artifact list, Principle V `.claude/` deny scope, Operational Constraints spec-path and branch bullets) as a SEPARATE human-merged PR, not on this branch; Sync Impact Report moved to the top of `.specify/memory/constitution-history.md` in the same commit; note the ordering (amendment lands no later than the lifecycle PR) on lifecycle issue #1020 (FR-024)
- [X] T057 Check no waiver register cites a tracker this work changes (`grep -rnE '"#N"|issue *= *\([^)]*\bN\b' .github/scripts/`) and update any new waiver entries
- [ ] T058 Run the `specs/114-subfolder-project-lifecycles/quickstart.md` validation scenarios
- [ ] T059 Run `python .github/scripts/run-local-gates.py` to green; re-run after any comment edits; then `prove-after-merge` on one re-driven routed run

---

## Dependencies & Execution Order

- **Phase 1** → **Phase 2** (blocks all stories). T005 before T006–T017; T009 after T007/T008; T011 before T012.
- **US1 (Phase 3)** after Phase 2. T022→T023→T024→T025 (same file, sequential); T026/T027/T028 before T029–T035; T036 after T030–T035.
- **US2 (Phase 4)** after Phase 2; touches `intake.yml` so sequence after T022–T025. T039/T040 sequential with US1 intake edits.
- **US3 (Phase 5)** after US1 and US2 workflow edits (final byte-identity review).
- **US4, US5** after Phase 2; fixtures can proceed in parallel with US1/US2.
- **Polish** last. T056 is independent and can run any time but ships separately.

### Parallel Opportunities

- Phase 1: T002, T003, T004 together.
- Phase 2: T007, T008, T010, T012, T013, T014, T015, T017 together after T005/T006.
- US1: gates T018–T020 together; per-workflow wiring T030–T035 together (different files).
- US2: T038, T043, T044 together.
- US4/US5 fixture tasks T050, T053 in parallel.

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 and Phase 2.
2. Phase 3 (US1): a routed lifecycle runs inside a folder with containment.
3. Validate US1 independently; US3 root-compat checks (T047–T049) should run before any merge, since a root regression breaks every adopter.

### Incremental Delivery

Add US2 (isolation) → US3 (compat proof) → US4 (graduation) → US5 (nesting) → Polish. Ship the constitution amendment (T056) as its own human-merged PR.

## Notes

- Total: 59 tasks. Setup 4 (T001–T004), Foundational 13 (T005–T017), US1 20 (T018–T037), US2 9 (T038–T046), US3 3 (T047–T049), US4 3 (T050–T052), US5 2 (T053–T054), Polish 5 (T055–T059).
- Do not edit this spec's spec.md, plan.md or research.md after merge except as T001/T004 research notes in this open PR.
- Never reference private downstream consumers in code, comments, commits or docs.

## Maintainer Feedback

- [ ] M001 Complete every remaining unchecked task in this spec's tasks.md (T001, T018, T021, T026, T029–T038, T040–T054, T056–T059), including the per-stage wiring (T029–T036, T040–T046) so Story 1 works end to end. (Maintainer request on PR #1022)
- [X] M002 Fix Gate 121: in job `intake`, step `Create spec from issue`, render the canonical commit-message scratch-path guidance by invoking `wing-commander-commit-message-guidance` in an earlier step of the job and interpolating its output into that prompt.
- [X] M003 Fix `verify-write-boundary.py`: run it locally to identify the failing scenario (likely from the project-aware deny composition in `wing-commander-tool-args`, T026/T027) and make the composed denies agree with the single no-write-paths definition (spec 090 / FR-022).
- [ ] M004 Keep root-level adopters byte-identical (FR-016) and run `python .github/scripts/run-local-gates.py` until all gates are green.

## Maintainer Feedback: Continue Implementation

Source: maintainer comment on PR #1022, asking implement to continue the in-scope work. The last cycle stopped after one partial step on T018 and used 15 of its 180 turns.

- [X] MF001 Use each cycle's turn budget to complete as many remaining tasks as it allows. Check off each task in this file as soon as it is complete so that every cycle registers progress and the loop does not end on "no further progress". (PR #1022)
- [X] MF002 Finish T018 first, before any other remaining task. (PR #1022)
- [X] MF003 Then do the per-stage wiring, in order: T029, T033, T034, T035, T040, T042, T043, T044, T045, T046. T036 and T041, which M001 also covers, belong to this wiring phase too. (PR #1022)
- [ ] MF004 Then do the remaining gates and fixtures: T021, T026, T037, T038, T047, T048, T049, T050, T051, T052, T053, T054. (PR #1022)
- [ ] MF005 Then do T001, T056, T057, T058, T059 and M001–M004. T056, the constitution amendment, stays a separate human-merged PR and does not land on this branch. (PR #1022)
- [X] MF006 For large workflow files (`implement.yml`, `intake.yml`, `cleanup.yml`), make a focused edit for each task instead of holding back a whole-file rewrite until it is complete. A task that lands partially may be committed with a progress note next to it in this file, and the next cycle continues it. (PR #1022)
- [ ] MF007 After each cycle's edits, keep `python .github/scripts/run-local-gates.py` green, and keep root-level behaviour byte-identical (FR-016). (PR #1022)

## Phase 9: Convergence

- [X] T060 Make the routing-on re-run refusal race-safe across the whole intake, not just the `routing-gate` job: a second intake for the same issue, queued behind the per-issue group, must still refuse after the first passes its gate but before the first creates its `spec:` label (for example a claim the gate records on the issue and the refusal also reads), with the model in `.github/scripts/verify-intake-routing.py` extended to cover that interleaving per FR-003 / FR-012 (partial)
- [X] T061 In `.github/workflows/intake.yml`, create the `spec:P/<NNN-slug>` label and check the slug against the budget in deterministic code before any branch exists (for example a pre-push hook installed for the agent's checkout, like pr-conversation's run-attribution hook), so an over-budget slug fails with no branch pushed; cover it in Gate 162 per FR-014 (partial)
- [X] T062 Apply the FR-021 containment guard (or a documented, gated scope check) to the subfolder agents in `.github/workflows/pr-conversation.yml` (act, act.fold) and `.github/workflows/cleanup.yml`, and extend `verify-subfolder-containment.py` so every Edit/Write agent in a project-wired job is covered per FR-021 (partial)
- [X] T063 Add subfolder fixtures to `.github/scripts/verify-rebase-discover-selection.py` (a `spec/P/NNN-slug` branch selected with `spec_dir=P/specs/NNN-slug`, its project-relative spec-meta accepted, `project` and slash-free `artifact_key` emitted) and to `.github/scripts/verify-spec-collision-collector.sh` (another project's `NNN` is no claimant) per FR-019 / SC-006 (partial)

## Phase 10: Convergence

- [X] T064 Make `.github/actions/wing-commander-publish-stranded-commits` take the lifecycle's project and refuse to push stranded commits that touch any path outside it (through `_shared/containment.sh`), wiring the project into every stage's "Publish stranded commits (post-agent)" call, so a failed containment check can no longer be published by the rescue that runs after it on `!cancelled()`; cover it in `verify-subfolder-containment.py` or Gate 123 per FR-021 (partial)

## Phase 11: Convergence

- [X] T065 Make intake's "Publish stranded commits (post-agent)" rescue in `.github/workflows/intake.yml` honour the label-first rule for a subfolder project: `wc_harden_git_env` sets `core.hooksPath=/dev/null`, so the label-first pre-push hook (`_shared/intake-pre-push.sh`) never runs on that push, and a branch the agent could not push itself reaches the remote with no slug-budget check and no `spec:P/<NNN-slug>` label created first; run the same deterministic check-and-create (or refuse the rescue) before it pushes, and cover the rescue path in Gate 162 per FR-014 (partial)

## Phase 12: Convergence

- [X] T066 Replace the inline name splitting in `.github/actions/wing-commander-inspected-run-identity/action.yml` (head-branch prefix and `-iterN` stripping, metrics-record `[P/]specs/` to slug, slug to spec dir), `.github/workflows/watchdog.yml`'s spec-collision collector (`own_project="${SLUG%/*}"`) and `.github/workflows/rebase.yml`'s discover step (`project="${slug%/*}"`) with `_shared/project-name.sh parse`, so the watchdog and fold-cycle guard identify project and lifecycle through the one shared parser, and extend `verify-project-single-home.py` with a reject fixture for an inline project split per FR-013 (partial)
  - Progress (cycle 13): inspected-run-identity and the watchdog collector done (it now reads `project`/`lifecycle-slug` outputs); the reject fixtures and the `inline-project-split` pattern added. Rebase `discover` remains -- see MF-21's note.
  - Progress (cycle 14): rebase `discover` now reads every in-flight branch's names from `wing-commander-project`'s new `identities-json` batch mode (`names-json`); its `INLINE_SPLIT_ALLOWED` entry is gone and Gate `verify-rebase-discover-selection.py` drives the shipped list and batch steps.


## Maintainer Feedback: Code review of #1022 at `87ae553`

Source: maintainer comment on PR #1022 (five fresh-session reviewers plus an adversarial verification pass). Fix in the order below. Lint is currently red on Gate 12 and Gate 60.

### Blocker

- [X] MF-01 [Review #1] In `wing-commander-containment/action.yml` (~:45), exclude only the root trusted checkout from the untracked listing with the anchored pathspec `-- ':/' ':(exclude,top).wing-commander-pipeline'`. Do not use an unanchored `--exclude`. Leave both `git diff` legs unfiltered so a committed gitlink is still flagged
- [X] MF-02 [Review #1] Append `/.wing-commander-pipeline/` to `.git/info/exclude` after the consumer checkout (closes #1030)
- [X] MF-03 [Review #1] Gate 160 case: an untracked nested git repo at `.wing-commander-pipeline/` plus a change only inside `P` must pass

### Major

- [X] MF-04 [Review #2, Gate 12, FR-014] Make `_shared/intake-pre-push.sh` validate only (ref shape, allocated number, slug budget, containment) and record the validated slug under `$RUNNER_TEMP`. Remove its `gh` calls (~:65, ~:67)
- [X] MF-05 [Review #2, FR-014] Move `spec:P/<slug>` label creation, the issue label add and the hardened push into a deterministic post-agent intake step (or `wing-commander-publish-stranded-commits` via its `label-first-*` inputs) under a declared token
- [X] MF-06 [Review #2, FR-014] For routed intake, deny `Bash(git push --no-verify:*)` and `Bash(git push -n:*)`
- [X] MF-07 [Review #3, Gate 60] Add `install-pre-push` mode (copy helpers from `$GITHUB_ACTION_PATH/../_shared`, write the hook, set `core.hooksPath`) and `filter` mode (rebase manifest) to `wing-commander-containment`
- [X] MF-08 [Review #3, Gate 60] Route `pr-conversation.yml` (~:2225), `rebase.yml` (~:1022) and `intake.yml` (~:754-756) through those modes, and widen Gate 60 to catch the `shared=` variable indirection
- [X] MF-09 [Review #4] Add `--no-renames` to both diff legs. Add reject fixtures for a committed move into `P`, a staged move into `P`, and a delete outside `P` paired with a near-identical add inside `P`
- [X] MF-10 [Review #5] Install the containment pre-push hook (MF-07) before clarify, plan (auto/pr), tasks (auto/pr), implement (cycle/retry) and finalize agents
- [X] MF-11 [Review #5] Make the post-agent guard also diff from `git merge-base origin/<default-branch> HEAD`, so an earlier pushed violation is caught after a restart
- [X] MF-12 [Review #6, FR-006] Add a deterministic project paragraph (like intake's) to the clarify, plan, tasks, implement, finalize and pr-conversation act prompts, pointing reads at `P/.specify/memory/constitution.md`, `P/.specify/extensions.yml` and `P/.claude/skills/<name>/SKILL.md`. Gate that every project-wired prompt carries it
- [X] MF-13 [Review #7, FR-023] Add a `findings-label-prefix` input to `wing-commander-project`, pass it from intake, and drive Gate 162 through that input with a `found-by:` reject case
- [X] MF-14 [Review #8, FR-005] Resolve the project first and pass `project:` to the preflights in `clarify.yml` (~:425) and pr-conversation (~:603, ~:1857). Gate that every `require-speckit: "true"` preflight in a project-wired job passes `project:`
- [X] MF-15 [Review #9, FR-007] Make the classifier in `wing-commander-stage-findings/action.yml` (~:252) recognise `P/specs/NNN-...` and `P/specs/*/contracts/`, with fixtures
- [X] MF-16 [Review #10] Expose the exact branch from 'Resolve created spec' and find the spec PR with `gh pr list --head "$BRANCH"` instead of the `$SPEC_DRAFT_PREFIX$NUM-` match (`intake.yml` ~:1607). Add a gate case

### Minor

- [X] MF-17 [Review #11] In `containment.sh` (~:51) use `git log --format= --name-only --no-renames -c ...` so merge commits are checked. Add an evil-merge fixture
- [X] MF-18 [Review #12] Subtract `Bash(gh api:*)` in `wing-commander-tool-args` for non-empty project on pr-conversation act, re-granting only needed endpoints. If not feasible, record it as an accepted gap in `contracts/containment-and-trusted-checkout.md`
- [X] MF-19 [Review #13] `check-folder`: test `.specify/memory`, `.specify/scripts` and each `SKILL.md` for symlinks. Add fixtures for a symlinked memory dir, skills dir and skill file
- [X] MF-20 [Review #14] Routing must refuse instead of falling back to the root: bare routing label (`node:`), failed `gh issue view`, leading `/` or `//`. Strip `-iterN` only for implement branches. Add fixtures for each
- [ ] MF-21 [Review #15, T066] Replace every remaining inline project/slug split (incl. `read-spec-meta.sh`, plan, tasks, rebase) with `project-name.sh parse`. Anchor rebase's `ls-remote` to `refs/heads/${SPEC_PREFIX}`
  - Progress (cycle 13): done for `read-spec-meta.sh`, `wing-commander-context`, `wing-commander-inspected-run-identity`, intake's "Resolve created spec", implement/finalize spec identity and stalled jobs, clarify's stalled job, all three cleanup arms, rebase's abandon arm and the watchdog collector (new `project-name.sh names`); `ls-remote` anchored. Gate 159 now fails any `inline-project-split`. Still inline, as counted allowances in `verify-project-single-home.py` (`INLINE_SPLIT_ALLOWED`): the one-step pre-jobs with no pipeline checkout (plan and tasks `resolve-spec`, cleanup `select`, pr-conversation `resolve-identity`), rebase `discover`'s per-branch loop and implement's credential-free gate-suite job. Converting them needs a pipeline checkout in each pre-job (or a batch mode of `wing-commander-project` for discover).
  - Progress (cycle 14): rebase `discover` converted through the new batch mode (T066). Still allowed: plan and tasks `resolve-spec`, cleanup `select`, pr-conversation `resolve-identity` (one-step pre-jobs with no pipeline checkout, whose outputs name the next job's concurrency group) and implement's credential-free gate-suite job.
- [X] MF-22 [Review #16] Add the stale-folder re-check after checkout in pr-conversation act and act.fold, rebase and cleanup
- [X] MF-23 [Review #17] Add a `release-claim` job (`if: always()`, no concurrency group) so `spec-intake-claimed` is released when a pending intake is cancelled
- [X] MF-24 [Review #18, FR-016] Restore root byte-identity: drop the added blank lines around `routing-notes` in the root intake prompt, and add `name: rebase (${{ matrix.slug }}, ${{ matrix.spec_dir }}, ${{ matrix.issue }})` to the rebase matrix
- [X] MF-25 [Review #19] Widen Gate 159's root-spec-dir pattern beyond slug-named variables and normalise Windows path separators
- [X] MF-26 [Review #20] In `docs/adoption.md`, list every rejected overlap family: `spec:`, `stage:`, `model:`, `board:`, `disposition:`, the findings prefix, `route-out-of-boundary`, `spec-request`, `spec-proposal`

### Then

- [ ] MF-27 Run T037, T049 and T058, and keep `python .github/scripts/run-local-gates.py` green (T056 is tracked separately in #1032)

## Phase 13: Convergence

- [X] T067 In `.github/workflows/intake.yml`, fail the intake job loudly, naming the refusal, when a routed subfolder intake's "Label first (subfolder project)" step or its "Publish stranded commits (post-agent)" push refuses a branch the agent committed (both are `continue-on-error`, so today an over-budget or misnumbered branch ends as a green run whose only trace is "intake produced no spec"), and cover the refused-rescue path in Gate 162 per FR-014 (partial)

## Maintainer Feedback: Code review of #1022 at `b8b2c7c` (round 2)

Source: maintainer issue-comment on PR #1022 (round-2 review; 18 of 20 round-1 items confirmed fixed). Lint is red on Gate 38 and Gate 12.

### Major

- [X] MF-28 [R2 #1, Gate 38] In `.github/actions/wing-commander-containment/action.yml` (~:96), stop reading `github.event.repository.default_branch` inside the composite. Add a `default-branch` input and pass it from every check-mode caller, using the branch that job already resolves. When the input is empty, resolve the branch in-step with `git ls-remote --symref origin HEAD` (the idiom `implement.yml` uses). Fail closed if neither gives a branch.
- [X] MF-29 [R2 #2, Gate 12] In `.github/workflows/rebase.yml` (~:390-396), 'Resolve in-flight branch names' calls `wing-commander-project` without a token. Pass `token: ${{ steps.ctx.outputs.token }}`, as the other call in the same workflow does.
- [X] MF-30 [R2 #3, FR-014] Close the label-first bypass. For routed subfolder intake, append `Bash(git push:*)` to the agent's disallowed list so the agent cannot push at all. Remove the `Bash(git push -n:*)` deny (`-n` means `--dry-run`) and the now-redundant `--no-verify` prefix deny. The post-agent label-first step re-runs the check, creates the label, then pushes. Update the routing notes to say the agent does not push.
  - Done (cycle 15) through a new tool-args `project-deny-tools` input. The `--no-verify` deny is redundant only for intake (covered there by `Bash(git push:*)`); it stays in `HOOK_BYPASS_DENIES` for the other subfolder stages, whose agents still push.
- [X] MF-31 [R2 #3, FR-014] In `intake.yml`, when `created-ref` found a slug but `label-first` produced none, the branch reached the remote without label-first. Fail loudly through the refused-publish path, and cover it in Gate 162.
- [X] MF-32 [R2 #4, containment] Export `GIT_NO_REPLACE_OBJECTS=1` in `_shared/containment.sh`, in the containment check-mode run block and in `wc_harden_git_env`. Run check mode under the hardened git env.
- [X] MF-33 [R2 #4, containment] Compute the containment base from a trusted SHA: a hardened `git ls-remote origin refs/heads/<default>`, fetched if missing, instead of the agent-rewritable `origin/<default>` or `--not --remotes`. Use the same base in the pre-push leg, diffing against `merge-base(<trusted default SHA>, local_sha)`. This also closes the gap where already-remote content arrives through a merge or reset.
- [X] MF-34 [R2 #5, containment] Treat the pre-push hook as advisory, because `core.hooksPath` and the `$RUNNER_TEMP` helper copies can be overwritten through `git log`/`git diff --output=<path>`. Enforce containment in the hardened post-agent step instead, running helper copies taken before the agent step and kept out of the agent's reach. Add `.wing-commander-pipeline/` to the subfolder no-write set.
- [X] MF-35 [R2 #5] Update `specs/114-subfolder-project-lifecycles/contracts/containment-and-trusted-checkout.md` to say plainly what the pre-push hook does and does not guarantee, and where containment is actually enforced.

### Minor

- [X] MF-36 [R2 #6] On every subfolder-capable 'Publish stranded commits (post-agent)' step, add `&& steps.containment.outcome != 'failure'` to the `!cancelled()` guard so a failed containment check never triggers a rescue push. Root lifecycles (where the containment step is skipped) stay unchanged. Get a `review-step-gating` pass on this change.
- [X] MF-37 [R2 #7, FR-014] In `_shared/intake-pre-push.sh`, validate the slug grammar through `project-name.sh parse slug`, on top of the existing number, `/` and length checks. Add a reject fixture for `001-Bad_Slug`.
- [X] MF-38 [R2 #8, FR-016] In `.github/actions/wing-commander-stage-findings/action.yml` (~:267-272), take the nested `<prefix>/specs/NNN-*` branch only when `<prefix>/.specify` exists on the checkout and is not a symlink. Add fixtures, including a root-only adopter path such as `e2e/specs/001-login.spec.ts` that must not be treated as a spec document.
  - Fixtures added to `stage-findings-tests/run_fixtures.py`; `run-tests.sh` is not on cycle 15's command allowlist, so they were not executed in this run -- CI's lint-workflows run is their first execution.
- [X] MF-39 [R2 #9] Expose a `claim-released` output from intake's in-job release step. Let the `release-claim` job run whenever intake did not succeed and did not release the claim itself, including when the intake job fails before any step runs.
- [X] MF-40 [R2 #10, Gate 60] Widen the Gate 60 regex to also match a trailing `_shared/` and a parent-directory variable followed by `/_shared/`, with self-test fixtures for each.
- [X] MF-41 [R2 #11, MF-21] Route the remaining inline splits (plan/tasks resolve-spec, cleanup select, pr-conversation resolve-identity, implement gate-suite) through `project-name.sh parse`, then remove their `INLINE_SPLIT_ALLOWED` entries and close MF-21. If a site must stay inline, record why here and leave MF-21 open with a follow-up issue.
  - Recorded (cycle 15): all five stay inline, so MF-21 stays open. Why: plan and tasks `resolve-spec`, cleanup `select` and pr-conversation `resolve-identity` are `permissions: {}` one-step pre-jobs with no pipeline checkout. Their `spec-dir` output names the next job's concurrency group, so it must exist before any job that has a checkout starts. The parser is reachable only through `wing-commander-project` (Gate 60 bars a published stage from `_shared/`), and that needs the trusted pipeline checkout: `job_workflow_sha` or `pipeline-ref` resolution, plus a token with `contents: read` for a private pipeline repository. That widens a deliberately permission-less job. Implement's gate-suite job is credential-free by design, and `wing-commander-project`'s `gh` call sites need a declared token (Gate 12). Each site validates the name's shape first, and the job that acts on the value re-reads it through `wing-commander-project`, which refuses any name the split would read differently (`verify-project-single-home.py`, `INLINE_SPLIT_ALLOWED`). The follow-up issue could not be filed from this run; it was reported in the cycle-15 implement findings block so the board files it.
- [ ] MF-42 After each cycle, keep `python .github/scripts/run-local-gates.py` green (Gate 12, Gate 38 and Gate 60 especially) and keep root behaviour byte-identical (FR-016). (PR #1022)

## Maintainer Feedback: Code review of #1022 at `38172fe` (round 3)

Source: maintainer issue-comment on PR #1022 (round-3 review). All of round 2 is fixed except MF-36, which landed but broke Gate 122. Lint is red on Gate 23 and Gate 122.

### Major

- [X] MF-43 [R3 #1, Gate 23] In `.github/actions/wing-commander-containment/action.yml` (~:188), replace the literal `helpers=(containment.sh project-name.sh …)` array. Gate 23's first-word tokenizer reads `project-name.sh` as an image tool. Build the array another way, e.g. `read -ra helpers <<< "containment.sh project-name.sh intake-pre-push.sh git-push-hardening.sh"`. Leave the `cp "${helpers[@]/#/$shared/}"` lines unchanged, and do not add anything to `required-tools.txt`.
- [X] MF-44 [R3 #2, Gate 122] In `.github/scripts/verify-agent-push-credential-helper.py` `check_job`, accept the 'Publish stranded commits' `if:` when it either equals the re-mint's `if:` exactly or equals `remint_if + " && steps.<cid>.outcome != 'failure'"`. `<cid>` must be a step in the same post-agent window that uses `wing-commander-containment` in check mode. Reject every other suffix, and add self-test mutations for the rejected forms. Keep the requirement in `verify-subfolder-containment.py` that the clause is present.
- [X] MF-45 [R3 #3, FR-014] In `.github/workflows/intake.yml` (~:1108), append `&& steps.containment.outcome != 'failure'` to the label-first step's `if:`, so a failed containment check never leaves an orphan `spec:P/<slug>` label that makes the routing gate refuse every re-run. In that case `refused-publish` must stay silent, so the containment failure is the only red. Get a `review-step-gating` pass on the change.
- [X] MF-46 [R3 #4, containment] The check, label-first, publish-stranded and hardened-push composites under `./.wing-commander-pipeline/` are agent-writable through `git log/diff --output=<path>`. In every subfolder-capable job, add a step directly after the agent step and before any `./.wing-commander-pipeline` composite, gated on a non-empty project. The step runs `rm -rf -- .wing-commander-pipeline`, then re-runs the job's pipeline checkout at the same pinned ref (`steps.pipeline-ref.outputs.ref`). Add a gate asserting that this re-checkout comes before the first post-agent pipeline composite in every subfolder-capable job.
- [X] MF-47 [R3 #5, FR-014] Stop intake publishing whatever branch the agent leaves checked out. From intake, pass `branch: <spec-draft-prefix>P/<label-first slug>` to publish-stranded, and skip the publish when the slug is empty. In publish-stranded, when `LF_ISSUE` is set: always run label-first, require a non-empty slug, and require the branch to equal `$LF_PREFIX$PROJECT/$LF_SLUG`. Drop the skip that relies on agent-writable refs (HEAD == `refs/remotes/origin/$branch`, and `HEAD --not --remotes == 0`).
  - Done (cycle 16). The `--not --remotes` skip lived in `wing-commander-label-first`; it now counts commits past the default branch's tip from `containment.sh trusted-base` (new `default-branch` input) and fails closed when that tip cannot be resolved.
- [X] MF-48 [R3 #6, containment] Close the other-ref push bypass for subfolder stages whose agents keep `Bash(git push:*)`. Before each subfolder agent, record a hardened `git ls-remote origin 'refs/heads/*'` snapshot. After the agent, run `containment.sh pre-push <P> <trusted tip>` over every ref that was created or moved. Fail and name the offending refs, after filtering out refs that other lifecycles' concurrent runs legitimately moved.
  - Done (cycle 16). `install-pre-push` writes `remote-heads.before` into its read-only helpers dir. Check mode, when it has `helpers-dir`, tests every created or moved head whose tip this checkout holds. That filter excludes concurrent runs' moves, because their commits were never fetched here. The residual gaps are listed in the contract.

### Minor

- [X] MF-49 [R3 #7] Add `Bash(gh label create:*)`, `Bash(gh issue edit:*)` and `Bash(gh pr create:*)` to intake's `project-deny-tools` for routed intake, keeping `gh issue comment`. The pipeline already applies the label and opens the PR.
- [X] MF-50 [R3 #8] In `.github/actions/_shared/containment.sh` (~:70), make the ref match exact. `git ls-remote origin "refs/heads/$branch"` also matches `<x>/refs/heads/<default>`, so filter with `awk -v r="refs/heads/$branch" '$2==r'`, and add a fixture for the suffix-collision case.
- [X] MF-51 [R3 #9] Update the release-claim comment in `.github/workflows/intake.yml` (~:1872-1881) to say that a failed in-job release inside an otherwise successful intake is not retried.
- [X] MF-52 [R3 #10] In `specs/114-subfolder-project-lifecycles/contracts/containment-and-trusted-checkout.md`, resolve the conflict between :37 and :49. Drop "a step the agent cannot touch", state what MF-46's re-checkout guarantees, and list any residual gap plainly.
- [ ] MF-53 After each cycle, keep `python .github/scripts/run-local-gates.py` green (especially Gate 12, Gate 23, Gate 38, Gate 60 and Gate 122) and keep root behaviour byte-identical (FR-016). (PR #1022)
