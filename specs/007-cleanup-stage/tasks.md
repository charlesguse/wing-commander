---

description: "Task list for Cleanup Stage — Lifecycle Teardown on Final Merge or Draft Rejection"
---

# Tasks: Cleanup Stage — Lifecycle Teardown on Final Merge or Draft Rejection

**Input**: Design documents from `/specs/007-cleanup-stage/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cleanup-workflow.md

**Tests**: Not included — not explicitly requested in the feature specification. This is a CI/CD workflow feature with no automated test suite (per plan.md's Testing section); validation is manual, via `quickstart.md`'s eight scenarios, folded into the User Story 3 and Polish phases below.

**Organization**: This feature's only "application code" is `.github/workflows/speckit-7-cleanup.yml` (a stub becoming three independently-gated jobs) plus two edits elsewhere for FR-013's consolidation. Because almost every task edits the same single YAML file, `[P]` is used sparingly — only for tasks that touch genuinely different files.

## Path Conventions

Single-project CI/CD feature, no `src/`/`tests/` split (per plan.md's Structure Decision). All file paths below are repo-root-relative.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Setup, Foundational, and Polish tasks carry no story label

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Turn the stub `cleanup` job into three empty, correctly-gated job skeletons — the scaffold every outcome's logic attaches to.

- [X] T001 In `.github/workflows/speckit-7-cleanup.yml`: replace the stub's single `cleanup` job with three empty job skeletons — `teardown-done`, `teardown-rejected`, `mark-stalled` — each carrying the job-level `if:` gate from `contracts/cleanup-workflow.md`'s "Job gates" section (`teardown-done`: `merged == true && base.ref == 'main' && head.ref starts with 'spec/'`; `teardown-rejected`: `merged == false && base.ref == 'main' && head.ref starts with 'spec-draft/'`; `mark-stalled`: `merged == false` AND (`base.ref == 'main' && head.ref starts with 'spec/'` OR `base.ref != 'main' && head.ref starts with 'plan/'|'tasks/'|'impl/'`)), `runs-on: ubuntu-latest`, least-privilege `permissions:` (`contents: write`, `pull-requests: write`, `issues: write`, `id-token: write`), and `concurrency: { group: speckit-cleanup-<slug-expr>, cancel-in-progress: false }` per job (matching the per-spec-group idiom used by `speckit-3-plan.yml`/`speckit-4-tasks.yml`). Update the file's header comment to describe the implemented three-outcome design instead of "STUB". Extend recognized head-ref prefixes to include `tasks/*` (the stub currently omits it — contract's Trigger contract note).

**Checkpoint**: `speckit-7-cleanup.yml` has three empty jobs, each firing on exactly the right event shape and no other — verifiable by inspecting the `if:` conditions against `data-model.md`'s outcome-resolution table.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Give every job the common boilerplate (repo checkout, App-token context) its own outcome logic needs before any refusal/write step can run.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 In `.github/workflows/speckit-7-cleanup.yml`, add to the `teardown-done` job: a bootstrap `actions/checkout@v4` step (`persist-credentials: false`) followed by the `./.github/actions/speckit-context` step (`id: ctx`, `app-id`/`private-key` from `secrets.SPECKIT_APP_ID`/`secrets.SPECKIT_APP_PRIVATE_KEY`) — the same two-step opener every other stage uses.
- [X] T003 In `.github/workflows/speckit-7-cleanup.yml`, add the identical bootstrap-checkout + `speckit-context` opener to the `teardown-rejected` job.
- [X] T004 In `.github/workflows/speckit-7-cleanup.yml`, add the identical bootstrap-checkout + `speckit-context` opener to the `mark-stalled` job.

**Checkpoint**: All three jobs can authenticate as the speckit App and have the repo checked out — foundation ready for outcome-specific logic.

---

## Phase 3: User Story 1 - A merged specification closes its own lifecycle automatically (Priority: P1) 🎯 MVP

**Goal**: Merging a specification's final PR (`spec/NNN-slug → main`) deletes its pipeline branches, advances its lifecycle label to `stage:done`, and closes its lifecycle issue with a written completion summary — with zero human action.

**Independent Test**: Merge a scratch specification's final PR and verify (per `quickstart.md` Scenario 1) that all its pipeline branches are gone, the lifecycle issue is closed with a completion-summary comment, and its label reads `stage:done`.

### Implementation for User Story 1

- [X] T005 [US1] In the `teardown-done` job of `.github/workflows/speckit-7-cleanup.yml`, implement the refusal contract's "Resolve and validate spec identity" step (`contracts/cleanup-workflow.md`'s Refusal contract, FR-009): derive `slug` by stripping the `spec/` prefix from `head.ref`, validate it against `^[0-9]{3}-[a-z0-9][a-z0-9-]*$`; checkout `spec/$slug` as the speckit-bot App token; verify `specs/$slug/spec.md` and `specs/$slug/spec-meta.json` both exist and `spec-meta.json`'s `issue`/`spec_dir` fields are non-empty with `spec_dir` matching `specs/$slug`. On any failure: `::error::`, a `$GITHUB_STEP_SUMMARY` line, and `gh pr comment $PR_NUMBER --body "⚠️ ..."` (never a lifecycle-issue comment), then stop the job — no branch deletion, label change, or issue write.
- [X] T006 [US1] In the `teardown-done` job, implement the idempotency check (`contracts/cleanup-workflow.md` step 1, FR-011): `gh issue view $issue --json state --jq .state`; if already `CLOSED`, skip the completion-summary, close-with-comment, and label-flip steps (T007–T008) — branch deletion (T009) still runs unconditionally.
- [X] T007 [US1] In the `teardown-done` job, implement the completion-summary step (FR-005, data-model.md's Completion summary section): `anthropics/claude-code-action@v1` on `claude-haiku-4-5` with `--allowedTools "Read,Glob,Grep,Bash(git log:*),Bash(git diff:*),Bash(git show:*),Write"`, `--disallowedTools "WebSearch,WebFetch"`, no `git commit`/`git push`/`gh` access, bounded `--max-turns`; on a checkout of `main`, diff `${{ github.event.pull_request.merge_commit_sha }}^1..${{ github.event.pull_request.merge_commit_sha }}` and write a narrative to a temp file. On outright failure (action fails, or the file is missing/empty afterward), fall back to the literal sentence "Specification merged (automated summary unavailable)." rather than blocking the rest of the job.
- [X] T008 [US1] In the `teardown-done` job, implement: `gh issue close $issue --comment "$(cat <summary temp file>)"` (atomic close-with-comment, FR-004/FR-005); `gh label create "stage:done" --force`; `gh issue edit $issue --add-label "stage:done"`; then read the issue's current labels (`gh issue view --json labels`) and remove whichever `stage:*` label (other than `stage:done` itself) is present (FR-003).
- [X] T009 [US1] In the `teardown-done` job, implement the branch-deletion step (FR-002, always attempted independent of T006's skip): delete `spec-draft/$slug`, `spec/$slug`, `plan/$slug`, `tasks/$slug`, and any `impl/$slug-iter*` branches (discovered via `git ls-remote --heads origin "impl/$slug-iter*"`); each deletion treats a "ref not found" failure as success (FR-011).

**Checkpoint**: User Story 1 is fully functional — `quickstart.md` Scenario 1 passes independently of every other phase below.

---

## Phase 4: User Story 2 - A rejected draft specification is torn down cleanly (Priority: P2)

**Goal**: Closing a specification's draft PR (`spec-draft/NNN-slug → main`) without merging deletes the draft branch, strips the stage and identity labels, and comments that the specification was rejected — leaving the lifecycle issue open.

**Independent Test**: Close a scratch specification's draft PR unmerged and verify (per `quickstart.md` Scenario 2) that the draft branch is deleted, both labels are gone, a rejection comment is posted, and the issue stays open.

### Implementation for User Story 2

- [X] T010 [US2] In the `teardown-rejected` job of `.github/workflows/speckit-7-cleanup.yml`, implement the refusal contract's identity step (FR-009): derive `slug` by stripping the `spec-draft/` prefix from `head.ref`, validate it against the slug regex; checkout `spec-draft/$slug` as the speckit-bot App token; verify `specs/$slug/spec.md` and `specs/$slug/spec-meta.json` exist with valid `issue`/`spec_dir`. On any failure: `::error::`, step summary, `gh pr comment $PR_NUMBER`, then stop — no writes.
- [X] T011 [US2] In the `teardown-rejected` job, implement the idempotency check (FR-011): is the `spec:$slug` label still present on the issue (`gh issue view --json labels`)? If already absent, skip the comment and label-removal steps (T012) — branch deletion (T013) still runs.
- [X] T012 [US2] In the `teardown-rejected` job, implement: `gh issue comment $issue --body "..."` stating the specification was rejected (FR-008), **without** closing the issue (FR-014); then `gh issue edit $issue --remove-label "spec:$slug"` and remove whichever `stage:*` label is currently present (FR-007).
- [X] T013 [US2] In the `teardown-rejected` job, implement the branch-deletion step (FR-006): delete `spec-draft/$slug` only (the sole branch that exists at the draft stage), tolerating "ref not found" as success.

**Checkpoint**: User Stories 1 AND 2 both work independently — `quickstart.md` Scenarios 1 and 2 both pass.

---

## Phase 5: User Story 4 - A rejected-after-build or abandoned-stage specification is marked stalled, not destroyed (Priority: P3)

**Goal**: Closing a specification's final PR unmerged, or closing one of its plan/tasks/implementation PRs unmerged, marks the specification `stage:stalled`, leaves every branch intact, and comments a rejection notice with a full-teardown runbook — never destroying built work.

**Independent Test**: Close a scratch specification's final PR (or a plan/tasks PR) unmerged and verify (per `quickstart.md` Scenarios 3 and 4) that the stage label reads `stage:stalled`, all branches remain, and the issue carries a stalled comment with teardown instructions — and that only `speckit-7-cleanup.yml` posts it (Scenario 4's "confirm only one stalled comment appears").

**Note**: This phase also retires the two workflows' now-redundant `stalled` jobs (FR-013's consolidation), since leaving them running alongside `mark-stalled` would produce a duplicate comment the moment either lands — the two changes must ship together.

### Implementation for User Story 4

- [X] T014 [US4] In the `mark-stalled` job of `.github/workflows/speckit-7-cleanup.yml`, implement the refusal contract's identity step (FR-009, FR-010): derive `slug` by stripping whichever prefix matched (`spec/`, `plan/`, `tasks/`, or `impl/` — for `impl/`, also strip a trailing `-iterN` suffix) from `head.ref`, validate the slug regex; for the non-final arm (`plan/`/`tasks/`/`impl/`), additionally verify `github.event.pull_request.base.ref == "spec/$slug"` exactly (research.md's decision — the coarse job-level gate only checked `base.ref != 'main'`), refusing if it doesn't match. Checkout `spec/$slug` — the PR's own head for the final arm, the PR's base for the non-final arm — as the speckit-bot App token; verify `specs/$slug/spec.md` and `specs/$slug/spec-meta.json` exist with valid `issue`/`spec_dir`. On any failure: `::error::`, step summary, `gh pr comment $PR_NUMBER`, then stop — no writes.
- [X] T015 [US4] In the `mark-stalled` job, implement the idempotency check (FR-011): does the issue's current stage label already read `stage:stalled`? If so, skip the `spec-meta.json` commit, label flip, and comment steps (T016–T017).
- [X] T016 [US4] In the `mark-stalled` job, implement the `spec-meta.json` write (FR-012/FR-013's storage decision): set `.stage = "stalled"` in `specs/$slug/spec-meta.json`, `git add` it, and commit + push directly onto `spec/$slug` — guarded by `git diff --cached --quiet` (a no-op write when already `"stalled"` must not fail the job), matching the retired jobs' own guard.
- [X] T017 [US4] In the `mark-stalled` job, implement: `gh label create "stage:stalled" --force`; `gh issue edit $issue --add-label "stage:stalled"`; remove whichever prior `stage:*` label was present (never touching `spec:$slug`); then `gh issue comment $issue --body "..."` stating which PR (final, or plan/tasks/impl) was closed unmerged, that the specification is now stalled with branches intact, and the full-teardown runbook (FR-015: a link to the closed PR and to `docs/architecture.md`'s Stage 6 section, plus literal `git push origin --delete <branch>` / `gh label` / `gh issue edit` commands scoped to this specification's own remaining branches — `spec/$slug`, `plan/$slug`, `tasks/$slug`, any `impl/$slug-iter*`). No branch deletion happens on this path.
- [X] T018 [P] [US4] Remove the `stalled` job from `.github/workflows/speckit-3-plan.yml` (FR-013's consolidation — `mark-stalled`'s non-final arm now owns `plan/*` PRs closed unmerged).
- [X] T019 [P] [US4] Remove the `stalled` job from `.github/workflows/speckit-4-tasks.yml` (FR-013's consolidation — `mark-stalled`'s non-final arm now owns `tasks/*` PRs closed unmerged).

**Checkpoint**: User Stories 1, 2, AND 4 all work independently, and exactly one "stalled" comment appears per closed non-final PR — `quickstart.md` Scenarios 1–4 all pass.

---

## Phase 6: User Story 3 - The stage acts only on the pull requests it owns, and never fails on already-clean state (Priority: P3)

**Goal**: Confirm the robustness properties already built into every job above — unowned PRs produce no action, owned PRs resolve identity from the payload (never guessed), already-clean state is treated as success, and repeated events don't duplicate writes.

**Independent Test**: Deliver close events for unowned PRs and a re-delivered owned event, and verify (per `quickstart.md` Scenarios 6–8) no action is taken on the unowned events and no duplication occurs on the repeat.

**Note**: Unlike US1/US2/US4, this story adds no new job or write path of its own — FR-009 (identify, don't guess), FR-010 (ownership gating), and FR-011 (idempotency) are implemented as part of every job's own contract in Phases 3–5 (the job-level `if:` gates from T001, the refusal steps from T005/T010/T014, and the idempotency checks from T006/T011/T015). This phase is the validation pass spec.md itself frames US3 as ("a robustness layer on top of the two core teardown behaviors") — it is sequenced last because Scenario 6's mismatched-base case and Scenario 7's stalled-idempotency case exercise the `mark-stalled` job built in Phase 5.

### Validation for User Story 3

- [X] T020 [US3] Run `quickstart.md` Scenario 6 against the implemented workflow: close an ordinary, unrelated PR (case 1) and a PR headed `plan/foo` but targeting `main` instead of a `spec/*` branch (case 2); verify no branch deletion, label change, or issue comment occurs in either case, and that case 2's refusal is reported via `gh pr comment` (per T014's base-ref check) rather than silently ignored.
- [X] T021 [US3] Run `quickstart.md` Scenario 7 against the implemented workflow: immediately after each of Scenarios 1–4 completes, re-deliver (or re-run) the same close event; verify each job finds its target state already reached (issue closed / label absent / label already `stage:stalled`), re-attempts branch deletion harmlessly where applicable, and posts no duplicate comment (`gh issue view <N> --json comments` shows the same count as before the replay).
- [X] T022 [US3] Run `quickstart.md` Scenario 8 against the implemented workflow: push a branch `spec/999-does-not-exist` with no corresponding `specs/999-does-not-exist/` directory, open a PR to `main`, and close it; verify the refusal step fails loudly (`::error::`, step summary) and comments on the pull request itself (never a lifecycle issue, since none can be resolved), with no branch deleted and no label changed anywhere.

**Checkpoint**: All four user stories are independently verified — the full `quickstart.md` scenario set (1–4, 6–8) passes.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final consistency checks across the whole feature.

- [X] T023 [P] Cross-check `docs/architecture.md`'s Stage 6 section against the implemented `speckit-7-cleanup.yml` (job names, outcome table, retired-jobs note) and correct it only if the implementation diverged from what it already documents (plan.md's Project Structure notes no changes are expected).
- [X] T024 [P] Confirm `docs/setup.md`'s label table and `gh label create` bootstrap commands already cover `stage:done` and `stage:stalled` (both already present as of this plan) — no edit expected, verification only.
- [X] T025 Run `quickstart.md` Scenario 5 (a plan PR merging normally into `spec/NNN-slug`) end-to-end and confirm `speckit-7-cleanup.yml` takes no action at all — the tasks stage's own trigger is what reacts, unchanged (FR-013 acceptance scenario 4).
- [X] T026 Run the complete `quickstart.md` scenario set (1–8) end-to-end, back-to-back, against one or more freshly-created scratch specifications, confirming every acceptance scenario in spec.md and every success criterion (SC-001–SC-007) holds together, not just in isolation.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 (job skeletons must exist before adding steps to them) — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational. No dependency on other stories.
- **User Story 2 (Phase 4)**: Depends on Foundational. No dependency on other stories (independent of Phase 3, even though both edit the same file — sequence for merge convenience, not correctness).
- **User Story 4 (Phase 5)**: Depends on Foundational. No dependency on Phases 3–4's job logic, but T018/T019's consolidation should land in the same change as T014–T017 (research.md — leaving the old `stalled` jobs in place while `mark-stalled` exists would double-post comments).
- **User Story 3 (Phase 6)**: Validation only — depends on Phases 3, 4, AND 5 being complete (T020's case 2 and T021's stalled-replay check exercise the `mark-stalled` job from Phase 5).
- **Polish (Phase 7)**: Depends on all prior phases.

### User Story Dependencies

- **User Story 1 (P1)**: Independently implementable and testable after Foundational.
- **User Story 2 (P2)**: Independently implementable and testable after Foundational.
- **User Story 4 (P3)**: Independently implementable and testable after Foundational.
- **User Story 3 (P3)**: Validates properties of US1/US2/US4; sequenced after all three land, unlike a typical independent story.

### Within Each Story

- Refusal/identity step before idempotency check before writes before branch deletion (each job's own internal order, per `contracts/cleanup-workflow.md`).
- `teardown-done`/`teardown-rejected`/`mark-stalled` job step-sequences are each self-contained and touch only their own job block within `speckit-7-cleanup.yml`.

### Parallel Opportunities

- Within Phase 1, none — one skeleton edit to one file.
- Within Phase 2, T002–T004 touch three different job blocks in the same file; safe to work through sequentially, not truly parallel-safe as a same-file edit.
- T018 and T019 are the only genuinely parallel-safe pair (different files: `speckit-3-plan.yml` vs `speckit-4-tasks.yml`).
- T023 and T024 (Polish, different files) can run in parallel with each other and with T025/T026.

---

## Parallel Example: User Story 4's Consolidation

```bash
# Launch both retirements together — different files, no shared state:
Task: "Remove the stalled job from .github/workflows/speckit-3-plan.yml"
Task: "Remove the stalled job from .github/workflows/speckit-4-tasks.yml"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Run `quickstart.md` Scenario 1 independently
5. This alone delivers SC-001/SC-002 — the pipeline's most common outcome (a merged final PR) already tears itself down automatically

### Incremental Delivery

1. Setup + Foundational → scaffold ready
2. Add User Story 1 → validate Scenario 1 → mergeable increment (MVP)
3. Add User Story 2 → validate Scenario 2 → mergeable increment
4. Add User Story 4 (implementation + consolidation together, per its Note) → validate Scenarios 3 and 4 → mergeable increment
5. Add User Story 3 (validation pass across everything built so far) → validate Scenarios 6–8
6. Polish → validate Scenario 5 and the full 1–8 sweep together

### Why User Story 4's two consolidation tasks (T018, T019) ship with its job logic (T014–T017)

FR-013 is explicit that the cleanup stage becomes the *sole* owner of "non-final pipeline PR closed unmerged." Landing `mark-stalled`'s non-final arm without retiring `speckit-3-plan.yml`/`speckit-4-tasks.yml`'s existing `stalled` jobs (or vice versa) would make a single closed `plan/NNN-slug` PR fire two independently-worded stalled comments — the exact failure research.md's Finding calls out. This is the one place in this feature where a "story" is not safely shippable as a partial increment.
