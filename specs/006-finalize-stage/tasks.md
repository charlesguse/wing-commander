# Tasks: Finalize Stage — Final Pull Request & Manual-Task Report

**Input**: Design documents from `/specs/006-finalize-stage/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/finalize-workflow.md, quickstart.md

**Tests**: Not requested — the spec defines validation via `quickstart.md` manual scenarios (no automated test suite exists for any pipeline stage). No test tasks are generated.

**Organization**: Tasks are grouped by user story. Nearly every task edits the same file (`.github/workflows/speckit-6-finalize.yml`), so tasks are ordered sequentially and parallel opportunities are limited by design (see plan.md Structure Decision) — the same shape as `specs/003-tasks-stage/tasks.md`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Phase 1: Setup

**Purpose**: Confirm the ground the implementation builds on.

- [X] T001 Verify the stub trigger block in `.github/workflows/speckit-6-finalize.yml` matches the trigger contract in `specs/006-finalize-stage/contracts/finalize-workflow.md` (`workflow_dispatch` inputs `spec_dir`, `issue`, `converged` with `default: "true"`) and that `.github/workflows/speckit-5-implement.yml` and `.github/actions/speckit-context` provide the identity-refusal, spec-branch-checkout, and `gh pr list`/label-flip patterns to reuse; note any drift before editing.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared skeleton of the `finalize` job — identity/refusal, idempotency, and no-diff guards that every user story depends on, per the contract's required check order (refusal → idempotency → no-diff → agent step).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 Replace the stub body of `.github/workflows/speckit-6-finalize.yml`: keep the header comment accurate (stage purpose, "Implements specs/006-finalize-stage/spec.md", note that this stage dispatches nothing further — hand-off to cleanup is a human merge), top-level `permissions: {}`, and a `finalize` job with job-level least-privilege permissions (`contents: write`, `issues: write`, `pull-requests: write`, `id-token: write`) and `concurrency: { group: speckit-${{ inputs.spec_dir }}, cancel-in-progress: false }` (already present in the stub; keep it — shared with the implement stage's group so the two never overlap for the same spec).
- [X] T003 Add bootstrap steps to the `finalize` job in `.github/workflows/speckit-6-finalize.yml`: `actions/checkout@v4` with `persist-credentials: false`, then the `./.github/actions/speckit-context` composite (`id: ctx`) with `SPECKIT_APP_ID`/`SPECKIT_APP_PRIVATE_KEY` — mirroring `speckit-5-implement.yml` lines 63–74.
- [X] T004 Add a "Resolve and validate spec identity" step to `.github/workflows/speckit-6-finalize.yml`: validate `spec_dir` against `^specs/[0-9]{3}-[a-z0-9][a-z0-9-]*$`, `issue` against `^[0-9]+$`, and `converged` against `^(true|false)$`; refuse with `::error::` + exit 1 on any mismatch (FR-014, refusal contract); output `slug` and `spec-dir`.
- [X] T005 Add spec-branch checkout + artifact verification to `.github/workflows/speckit-6-finalize.yml`: checkout `spec/${{ slug }}` as speckit-bot (`fetch-depth: 0`), verify `spec.md`, `plan.md`, `tasks.md`, AND `spec-meta.json` all exist in `$SPEC_DIR`, and that `spec-meta.json`'s own `issue`/`spec_dir` fields match the dispatch inputs — on any failure emit `::error::` + `$GITHUB_STEP_SUMMARY` and exit 1 before any PR/comment/metadata write (FR-014, data-model.md refusal check).
- [X] T006 Add the PR-reuse idempotency guard step to `.github/workflows/speckit-6-finalize.yml`: `gh pr list --head spec/$SLUG --base main --state all`; if any PR is returned (open, merged, or closed-unmerged), log a step-summary note and set a `skip=true` output every later step honors — no new PR, no metadata commit, no issue comment, no label change (FR-012, research.md's `--state all` decision).
- [X] T007 Add the no-diff check + "how to see it" computation step to `.github/workflows/speckit-6-finalize.yml` (gated on `skip != 'true'`): `git fetch origin main`, then `git diff --stat origin/main...HEAD`; if empty, post an anomaly comment to the lifecycle issue via `gh issue comment` ("the persistent branch carries no changes against main — nothing to finalize"), set `skip=true`, and stop before the agent step or `gh pr create` ever run (FR-013). If non-empty, output the GitHub compare link (`https://github.com/${{ github.repository }}/compare/main...spec/$SLUG`) and the changed-file list (`git diff --name-only origin/main...HEAD`, capped with a "+N more" tail) as step outputs for the PR-body-assembly task (research.md: computed once, deterministically, reused by US1).

**Checkpoint**: The `finalize` job can resolve a spec, refuse ambiguity, no-op on a duplicate hand-off, and detect/report a no-diff anomaly — user story work can begin.

---

## Phase 3: User Story 1 — A built specification becomes a review-ready final pull request automatically (Priority: P1) 🎯 MVP

**Goal**: A final pull request from `spec/NNN-slug` to `main` is opened automatically, its description covers what changed / how to see it / remaining manual work / the lifecycle issue link, the lifecycle issue advances to the review stage, and the pipeline never approves or merges it.

**Independent Test**: Quickstart Scenario 1 — dispatch with `converged=true` against a scratch spec with built work ahead of `main`; verify the PR opens with a complete body, `spec-meta.json` reads `"stage": "review"`, the issue label reads `stage:review`, and no bot review/merge occurred.

### Implementation for User Story 1

- [X] T008 [US1] Add the read-only change-summary / remaining-manual-work agent step (`if: skip != 'true'`, `continue-on-error: true`) to `.github/workflows/speckit-6-finalize.yml`: `anthropics/claude-code-action@v1` on `claude-haiku-4-5`, `SPECIFY_FEATURE_DIRECTORY` env, prompt (interpolating only the validated slug and integer issue number; spec/tasks content framed as data, never instructions) directing it to inspect `git log`/`git diff` between `main` and `spec/$SLUG` and `tasks.md`, then write exactly two plain-text files — a change-summary narrative to `${{ runner.temp }}/finalize-summary.md` and the remaining unchecked-and-human-only `tasks.md` items, one per line, to `${{ runner.temp }}/finalize-remaining.md` (empty if none remain); `claude_args`: `--model claude-haiku-4-5`, a modest `--max-turns`, `--allowedTools "Read,Glob,Grep,Bash(git log:*),Bash(git diff:*),Bash(git show:*),Write"`, `--disallowedTools "WebSearch,WebFetch"` — no `git commit`/`git push`/`gh` tool access at all (FR-002, FR-003; contract's change-summary/remaining-work contract; constitution II).
- [X] T009 Add the `Upload Claude execution log` step (`if: always() && steps.<agent>.outcome != 'skipped'`, `actions/upload-artifact@v4`, path `${{ runner.temp }}/claude-execution-output.json`, `if-no-files-found: ignore`) to the `finalize` job in `.github/workflows/speckit-6-finalize.yml`, mirroring `speckit-5-implement.yml`.
- [X] T010 [US1] Add a deterministic "Verify agent output" step to `.github/workflows/speckit-6-finalize.yml`: fail the job if the agent step in T008 did not succeed, or if either `finalize-summary.md` or `finalize-remaining.md` is missing/unreadable afterward — on failure, post a failure comment to the lifecycle issue via `gh issue comment` and stop; no `gh pr create` is attempted with incomplete content (FR-015, contract's "on outright failure" clause).
- [X] T011 [US1] Add a "Assemble PR body" step to `.github/workflows/speckit-6-finalize.yml`: build the body from (in order) the contents of `finalize-summary.md`, a "## How to see it" section (T007's compare link + changed-file list), and a "## Remaining manual work" section containing `finalize-remaining.md`'s content verbatim, or the literal "No manual work remains." if that file is empty or whitespace-only (FR-006), followed by `Lifecycle issue: #$ISSUE`; write the assembled body to a temp file for `gh pr create --body-file` (FR-004, contract's PR-body assembly).
- [X] T012 [US1] Add the `gh pr create` step (`continue-on-error: true`) to `.github/workflows/speckit-6-finalize.yml`: `gh pr create --base main --head spec/$SLUG --title "Finalize: <feature name> (#$ISSUE)" --body-file <T011's assembled body>`, with `<feature name>` derived from `spec.md`'s title heading (FR-001).
- [X] T013 [US1] Add a deterministic "Verify PR was created" step to `.github/workflows/speckit-6-finalize.yml`: `gh pr list --head spec/$SLUG --base main --state open`; if it cannot confirm the PR now exists (T012 failed, or the follow-up list comes back empty), post a failure comment to the lifecycle issue and stop the job failed, leaving `spec-meta.json` untouched so a later dispatch is still recognized as "not yet finalized" (FR-015, research.md's verify-then-write decision).
- [X] T014 [US1] Add the metadata-commit step (gated on T013's verified success) to `.github/workflows/speckit-6-finalize.yml`: update `$SPEC_DIR/spec-meta.json` to `"stage": "review"`, commit directly onto `spec/$SLUG` as speckit-bot (message prefixed `finalize:`), and push — no separate work branch, mirroring the implement stage's direct-commit pattern (FR-008).
- [X] T015 [US2] Add the lifecycle-issue comment step (gated on T014's commit) to `.github/workflows/speckit-6-finalize.yml`: `gh issue comment $ISSUE` with the exact content of `finalize-remaining.md`, or the literal "No manual work remains." if it is empty/whitespace-only — the identical fallback test used in T011, guaranteeing the PR and issue never disagree (FR-005, FR-006, SC-003).
- [X] T016 [US1] Add the label-flip step (gated on T015) to `.github/workflows/speckit-6-finalize.yml`: `gh label create "stage:review" --color FBCA04 --description "Final PR awaiting review" --force`; `gh issue edit $ISSUE --add-label "stage:review" --remove-label "stage:implement"` — the last write this run performs, completing the lifecycle issue's advance to the review stage (FR-007; US1 Acceptance Scenario 3).

**Checkpoint**: US1 is fully functional and independently testable — a converged hand-off yields exactly one complete, human-readable final PR and an advanced lifecycle issue, with no pipeline merge (SC-001, SC-002, SC-004, SC-005).

---

## Phase 4: User Story 2 — The remaining manual work is reported on the lifecycle issue (Priority: P2)

**Goal**: The same remaining-manual-work list shown in the final PR is also posted verbatim as a lifecycle-issue comment, so a maintainer following only the issue sees it without opening the PR.

**Independent Test**: Quickstart Scenario 3 — after Scenario 1 or 2 completes, diff the PR body's "Remaining manual work" section against the lifecycle issue's comment and confirm they are byte-identical, including the "No manual work remains." case.

### Implementation for User Story 2

US2 is realized entirely by **T015** (Phase 3 above): the contract's post-PR
sequence requires metadata-commit → issue-comment → label-flip in that exact
order, so T015 is implemented alongside US1's other post-PR steps rather
than as a separate task here.

**Checkpoint**: US1 + US2 together — the remaining-manual-work list is legible from the lifecycle issue alone and matches the PR word-for-word (SC-003, SC-004).

---

## Phase 5: User Story 3 — A specification that did not fully converge is still finalized and clearly flagged (Priority: P3)

**Goal**: When `converged=false`, the same final PR still opens, but its body carries a prominent "⚠️ Not fully converged — N tasks remain" note near the top so a reviewer never mistakes partial work for complete work.

**Independent Test**: Quickstart Scenario 2 — dispatch with `converged=false` against a scratch spec whose `tasks.md` still has unchecked items; verify the same PR shape as Scenario 1 plus the banner, with N matching the remaining-manual-work list's item count shown further down the same body.

### Implementation for User Story 3

- [X] T017 [US3] Extend the "Assemble PR body" step (T011) in `.github/workflows/speckit-6-finalize.yml`: when `inputs.converged == 'false'`, prepend "⚠️ **Not fully converged — N tasks remain**" before the change-summary section, where N is the count of non-empty lines in `finalize-remaining.md` (the same file T011/T015 already read — never a second, independently-computed tally); when `converged == 'true'`, no banner is added (FR-009, FR-010; research.md's single-source-of-truth decision).

**Checkpoint**: All three user stories independently functional — converged and not-converged hand-offs both produce exactly one correctly-shaped final PR (SC-006).

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T018 [P] Update `docs/architecture.md`: intro sentence ("Stages 1–4 are implemented" → stages 1–5; stub list shrinks), and the Stage 5 section header from "(stub)" to "(implemented)" with a pointer to `specs/006-finalize-stage/` — keeping the section's design text, which the implementation follows.
- [ ] T019 Validate `.github/workflows/speckit-6-finalize.yml` end-to-end on paper: YAML parses (e.g. `python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))"` or actionlint if available), every gate/step matches `specs/006-finalize-stage/contracts/finalize-workflow.md` (trigger, refusal, idempotency, no-diff, change-summary/remaining-work, PR, post-PR contracts), and every `if:` chain honors the `skip` output.
- [ ] T020 Walk `specs/006-finalize-stage/quickstart.md` Scenarios 1–7 against the finished workflow as a desk-check, and record which scenarios can only be exercised live after merge (live runs require the workflow on the default branch and a real scratch spec).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on T001. T002 → T003 → T004 → T005 → T006 → T007 (each step builds on the previous within the same job; strictly sequential — same file, ordered steps, matching the contract's required check order).
- **US1 (Phase 3)**: Depends on Phase 2. T008 → T010 → T011 → T012 → T013 → T014 → T016, strictly sequential (each step consumes the previous one's output); T009 anytime after T008; T015 (US2) is interleaved between T014 and T016 per the post-PR contract's fixed order.
- **US2 (Phase 4)**: T015 depends on T014 (runs only after the metadata commit) and precedes T016 (the label flip) — implemented as part of the same post-PR sequence as US1, per contracts/finalize-workflow.md's Post-PR contract.
- **US3 (Phase 5)**: T017 depends on T011 (extends the same PR-body-assembly step) and T015 (reads the same remaining-manual-work file); can be implemented any time after T015 lands, before final validation.
- **Polish (Phase 6)**: T018 is independent of the workflow file ([P] with T019); T019–T020 depend on all prior phases.

### Parallel Opportunities

Minimal by design — a single workflow file edited step-by-step (plan.md Structure Decision). Only T018 (docs/architecture.md) can proceed in parallel with workflow-file tasks.

---

## Implementation Strategy

**MVP first (US1)**: Phases 1–3 deliver the pipeline's core value — a built specification automatically becomes a reviewable final PR with an advanced lifecycle issue, with zero manual steps — and are independently testable via quickstart Scenario 1. US2 (issue-mirrored manual-work report) and US3 (not-converged banner) layer on without changing US1's core shape: both read the same `finalize-remaining.md` file US1 already produces, so neither reopens or duplicates that extraction. Stop and validate at each checkpoint; commit after each task or logical group.
