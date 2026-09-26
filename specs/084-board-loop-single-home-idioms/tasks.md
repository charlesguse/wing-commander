---

description: "Task list for Single-home the remaining board-loop idioms"
---

# Tasks: Single-home the remaining board-loop idioms

**Input**: Design documents from `/specs/084-board-loop-single-home-idioms/`
**Prerequisites**: plan.md, spec.md, research.md (D1–D8), data-model.md, contracts/marker-write-entrypoint.md, contracts/pr-branch-resolution.md, contracts/single-home-gate-extension.md, quickstart.md

**Tests**: Not requested as a separate TDD pass. This feature's own coverage IS part of its deliverable (User Story 3 / FR-010–FR-013) — two new checks and their `--self-test` mutation fixtures inside the existing `verify-single-home-idioms.py` (Gate 60), not a new gate and not a `tests/` tree (this repository has none; its own gate scripts are the test suite).

**Organization**: Tasks are grouped by user story per spec.md's priorities (P1 marker-write, P2 PR-branch, P3 gate coverage). US1 and US2 touch disjoint files and are independently shippable; US3 depends on both, per spec.md's own "Why this priority" for User Story 3 ("It depends on User Stories 1 and 2 having declared homes to point at, so it is last").

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no ordering dependency on an incomplete task)
- **[Story]**: US1–US3 per spec.md's priorities
- Line numbers below are citations from research.md/data-model.md/contracts against baseline commit `e170077`, reconfirmed against the current tree as of this tasks.md's writing (Setup, T001). Board-loop.yml is edited by both US1 and US2; reconfirm a site's line number by its step name/`marker="$(python3` prefix immediately before editing it, since each preceding edit in the file shifts everything below it by a line or two.

## Path Conventions

Single project — this repository is a GitHub Actions workflow/gate tree, not an application with a `src`/`tests` split. All paths below are repository-root-relative:

- `.github/scripts/board_item_marker.py` — US1 (gains a CLI; `write_marker` body unchanged)
- `.github/workflows/board-loop.yml` — US1 (17 marker-write call sites across 6 jobs) and US2 (2 PR-branch call sites)
- `.github/actions/_shared/resolve-pr-branch/action.yml` (new) — US2
- `.github/scripts/verify-single-home-idioms.py` — US3 (Gate 60 extension: two new checks, two new `DECLARED_HOMES` entries, self-test fixtures)

---

## Phase 1: Setup

**Purpose**: Reconfirm the plan-time citations and baseline counts this feature depends on, against the actual current tree, before any edit begins.

- [X] T001 Reconfirm, against the current tree (not commit `e170077`): the marker-write call-site count and per-job breakdown (`grep -n "write_marker(" .github/workflows/board-loop.yml`, excluding the one comment mention at the top of the file — expect 17 call sites), which of the two spellings each site uses (`grep -c "sys.path.insert(0, '.github/scripts')"` for the working-tree spelling vs. the `wc-pristine/scripts` spelling for the pristine one), and the two PR-branch site line numbers (`grep -n 'Resolve the PR under' .github/workflows/board-loop.yml`). Record the reconfirmed per-job breakdown and line numbers for use in T003–T008 and T014–T015; note any drift from research.md's/spec.md's own cited counts (e.g., a job-name list or a downstream-reference count) as a task-stage observation, not something to silently correct in spec.md or plan.md.

**Checkpoint**: The exact call sites this feature moves are confirmed against the real tree before any edit.

---

## Phase 2: Foundational

No foundational tasks: the three idioms consolidate into three separate, non-overlapping files (`board_item_marker.py` for US1, `resolve-pr-branch/action.yml` for US2, `verify-single-home-idioms.py` for US3) with no new shared infrastructure between them. User Story 3's dependency is on User Story 1 and User Story 2 directly — see Dependencies below — not on a foundational layer.

---

## Phase 3: User Story 1 - The marker-write bootstrap has one home (Priority: P1) 🎯 MVP

**Goal**: Every board-loop job that writes a marker reaches `board_item_marker.py`'s rendering through one command-line entrypoint instead of retyping the `sys.path` + `board_item_marker` import bootstrap inline.

**Independent Test**: Change the marker's rendered output in its single home; confirm without editing `board-loop.yml` that every marker-writing step in every job emits the new output, and that the fix, review and readiness jobs still satisfy Gate 98's pristine-snapshot provenance rule.

### Implementation for User Story 1

- [X] T002 [US1] In `.github/scripts/board_item_marker.py`, add an `argparse`-based `main()` and an `if __name__ == "__main__":` guard (contracts/marker-write-entrypoint.md, research.md D2/D3). Flags: `--step` (required, string — accepts a literal step name or the symbolic tokens `BREACH_STEP`/`AWAITING_MERGE_STEP`), `--round` (optional, `type=int`, default `0`), `--pr` (optional, `type=int`, default `None`), `--branch` (optional, string, default `None`), `--base-sha` (optional, string, default `None`). Add a `_resolve_step(value)` helper that, only when `value` is exactly `"BREACH_STEP"` or `"AWAITING_MERGE_STEP"`, imports `AWAITING_MERGE_STEP`/`BREACH_STEP` from `board_eligibility` (`.github/scripts/board_eligibility.py:77-78`) and returns the matching constant, otherwise returns `value` unchanged — the caller's YAML never hardcodes the literal `"breach"`/`"awaiting-merge"` string (research.md D3). `main()` calls `print(write_marker(_resolve_step(args.step), args.round, args.pr, args.branch, args.base_sha))` — `write_marker` itself (line 110) is not modified (FR-005).
- [X] T003 [US1] In `board-loop.yml`'s `triage` job (1 site, working-tree spelling), replace the inline `python3 -c "import sys; sys.path.insert(0, '.github/scripts'); from board_item_marker import write_marker; print(write_marker(...))"` call with `python3 .github/scripts/board_item_marker.py --step ... [--round ...] [--pr ...] [--branch ...] [--base-sha ...]`, translating each positional `write_marker` argument to its matching flag (an argument of `None` becomes an omitted flag, never `--pr None`). Depends on T002.
- [X] T004 [US1] In `board-loop.yml`'s `route` job (1 site, working-tree spelling), apply the same replacement as T003. Depends on T002.
- [X] T005 [US1] In `board-loop.yml`'s `fix` job (4 sites, pristine spelling — the `stalled` marker before a branch exists, the post-push `review`-step marker carrying `branch`/`base_sha`, the post-push-breach marker resolving `BREACH_STEP` via `from board_eligibility import BREACH_STEP`, and a second `stalled` marker), replace each inline `python3 -I -c "import os, sys; sys.path.insert(0, os.path.join(os.environ['RUNNER_TEMP'], 'wc-pristine', 'scripts')); from board_item_marker import write_marker; ..."` call (and, for the breach site, its extra `from board_eligibility import BREACH_STEP` line) with `python3 -I "$RUNNER_TEMP/wc-pristine/scripts/board_item_marker.py" --step ... [--round ...] [--pr ...] [--branch ...] [--base-sha ...]`, passing `--step BREACH_STEP` (the symbolic token, not the literal string) at the breach site. Depends on T002.
- [X] T006 [US1] In `board-loop.yml`'s `review` job (5 sites, pristine spelling — a `readiness`-step marker with no `base_sha`, three `stalled` markers, and the round-advance `review`-step marker that reads `NEXT_ROUND`/`PR_NUMBER`/`BRANCH` from the shell environment), apply the same CLI replacement as T005, passing `--round "$NEXT_ROUND"` at the round-advance site (its only site among the 17 with a non-default `--round`). Depends on T002.
- [X] T007 [US1] In `board-loop.yml`'s `readiness` job (2 sites, pristine spelling — the ready-report marker resolving `AWAITING_MERGE_STEP` via `from board_eligibility import AWAITING_MERGE_STEP`, and a `stalled` marker), apply the same CLI replacement as T005, passing `--step AWAITING_MERGE_STEP` (the symbolic token) at the ready-report site. Depends on T002.
- [X] T008 [US1] In `board-loop.yml`'s `prove` job (4 sites, working-tree spelling — `proven`/`prove`/`proven`/`prove` markers), apply the same CLI replacement as T003. Depends on T002.
- [X] T009 [US1] For each of the 17 call sites T003–T008 replaced, confirm byte-identity (FR-003, quickstart.md step 4): run the inline call it replaced (`python3 -c "import sys; sys.path.insert(0, '.github/scripts'); from board_item_marker import write_marker; print(write_marker(<its exact args>))"`) and the new CLI invocation with the equivalent flags side by side, and confirm the two stdout strings are identical for every site, including the two that resolve `BREACH_STEP`/`AWAITING_MERGE_STEP` and the one that passes an explicit `--round`. Depends on T003, T004, T005, T006, T007, T008.
- [X] T010 [US1] Confirm SC-001 (quickstart.md step 2): `grep -c "sys.path.insert(0, '.github/scripts')" .github/workflows/board-loop.yml` and the pristine-spelling equivalent both report `0` remaining inline bootstraps, and `grep -c "board_item_marker.py" .github/workflows/board-loop.yml` reports 17 (one CLI invocation per former call site). Depends on T003, T004, T005, T006, T007, T008.

**Checkpoint**: At this point, every board-loop marker write reaches `board_item_marker.py` through the CLI entrypoint, with byte-identical output to today's, and 0 inline bootstraps remain.

---

## Phase 4: User Story 2 - PR-branch resolution has one home (Priority: P2)

**Goal**: The `review` and `readiness` jobs both resolve their PR through one internal composite instead of each retyping the `gh pr view … headRefName` read and the `GITHUB_OUTPUT` write.

**Independent Test**: Change the resolution behaviour in its single home; confirm both the review and readiness jobs check out the same ref they would have, and that neither job's `run:` block still contains the `gh pr view … headRefName` read.

### Implementation for User Story 2

- [ ] T011 [US2] Create `.github/actions/_shared/resolve-pr-branch/action.yml` (contracts/pr-branch-resolution.md, research.md D4). Header comment states, matching `orphan-branch-reset/action.yml`'s and `scoped-app-token/action.yml`'s own canonical sentence, that this composite is internal — never resolved by a `workflow_call`-only stage or a published composite; Gate 60's promotion-prevention check enforces this; `board-loop.yml` is its only caller (FR-009). Inputs: `pr-number` (required), `token` (required, passed as `GH_TOKEN`), `round` (optional, default `""`, pass-through only — FR-007). A single `shell: bash` step, `env: REPO: ${{ github.repository }}`, running `set -euo pipefail; branch="$(gh pr view "$PR_NUMBER" -R "$REPO" --json headRefName --jq .headRefName)"; if [ -z "$branch" ]; then echo "::error::resolve-pr-branch: PR #$PR_NUMBER resolved an empty head branch" >&2; exit 1; fi; { echo "pr-number=$PR_NUMBER"; echo "branch=$branch"; echo "round=$ROUND"; } >> "$GITHUB_OUTPUT"` (FR-008 — a failed `gh pr view` aborts under `set -e`; a successful-but-empty read is caught explicitly; neither case silently writes an empty `branch=`). Outputs: `pr-number` (echoes the input), `branch` (`steps.<id>.outputs.branch` of the shell step), `round` (echoes the input).
- [ ] T012 [US2] In `board-loop.yml`'s `review` job, replace the "Resolve the PR under review" step (`id: pr`, currently emitting `set -uo pipefail; branch="$(gh pr view "$PR_NUMBER" -R "$GITHUB_REPOSITORY" --json headRefName --jq .headRefName)"; { echo "pr-number=$PR_NUMBER"; echo "branch=$branch"; echo "round=$ROUND"; } >> "$GITHUB_OUTPUT"`) with `uses: ./.github/actions/_shared/resolve-pr-branch`, `id: pr` (unchanged), `with: pr-number: ${{ needs.fix.outputs.pr-number || needs.select.outputs.pr }}`, `token: ${{ github.token }}`, `round: ${{ needs.select.outputs.round || 0 }}`. The step remains the first step of the job, before `actions/checkout@v5` (research.md D4 — the composite needs no checkout of its own). Depends on T011.
- [ ] T013 [US2] In `board-loop.yml`'s `readiness` job, replace the "Resolve the PR under readiness" step (`id: pr`, the same shape as T012 minus the `round` output) with `uses: ./.github/actions/_shared/resolve-pr-branch`, `id: pr` (unchanged), `with: pr-number: ${{ needs.review.outputs.pr-number || needs.select.outputs.pr }}`, `token: ${{ github.token }}` (no `round` input — the readiness job has none today, per spec.md's Assumptions, and this composite call omits it, taking the `""` default). Depends on T011.
- [ ] T014 [US2] Grep every `steps.pr.outputs.pr-number`, `steps.pr.outputs.branch`, and (in the `review` job only) `steps.pr.outputs.round` reference downstream of T012/T013's steps in both jobs, and confirm each still resolves — the `id: pr` and the three output names are unchanged, so no downstream reference needs editing; this is a confirmation pass, not an edit. Depends on T012, T013.
- [ ] T015 [US2] Confirm SC-002 (quickstart.md step 2): `grep -c 'gh pr view .* --json headRefName --jq' .github/workflows/board-loop.yml` reports `0`, and `grep -c 'uses: ./.github/actions/_shared/resolve-pr-branch' .github/workflows/board-loop.yml` reports `2`. Depends on T012, T013.

**Checkpoint**: At this point, both PR-branch resolution sites reach the composite, downstream references are unbroken, and a failed or empty resolution now fails loudly (FR-008) instead of silently checking out the default branch.

---

## Phase 5: User Story 3 - Every consolidated board-loop idiom is gated (Priority: P3)

**Goal**: A re-paste of the marker-write bootstrap or the PR-branch read at a new site fails a gate naming its declared home; the kill-switch/stop-request recheck's existing gate is reconfirmed rather than re-built.

**Independent Test**: For each of the three idioms, introduce a re-paste at a new site in a scratch copy of the tree and confirm the gate fails; remove it and confirm the gate passes.

### Implementation for User Story 3

- [ ] T016 [US3] In `.github/scripts/verify-single-home-idioms.py`'s `DECLARED_HOMES` dict, add two entries with a dated/issue-cited comment in the style of the existing `board-stop-check` entry: `"marker-write": ".github/scripts/board_item_marker.py"` and `"pr-branch": ".github/actions/_shared/resolve-pr-branch/action.yml"` (contracts/single-home-gate-extension.md; `CHECK_NAMES` derives from `DECLARED_HOMES` automatically, no separate edit needed). Depends on T002, T011.
- [ ] T017 [P] [US3] Add a `MARKER_WRITE_FRAGMENTS` tuple (`"sys.path.insert"`, `"board_item_marker"`, `"write_marker"`) alongside the existing per-idiom fragment tuples (e.g. `BOARD_STOP_CHECK_FRAGMENTS`), and a `check_marker_write(root=".")` function modeled directly on `check_board_stop_check` (file-wide co-occurrence, excluding the declared home's own path/directory): for each file in `all_subject_files(root)` other than the home, if all fragments in `MARKER_WRITE_FRAGMENTS` are present in the file's text, record a `Finding` at the first fragment's offset. Wire it into `ALL_CHECKS["marker-write"]`. Verified (research.md D6) against the current tree: only `board-loop.yml` (removed by US1) and one comment in `wing-commander-board-stop-check/action.yml` (mentions `board_item_marker` but neither of the other two fragments) reference the module — no false positive, no waiver needed. Depends on T016.
- [ ] T018 [P] [US3] Add a `check_pr_branch(root=".")` function modeled on `check_failure_issue`/`check_token_mint` (per-step co-occurrence via the existing `_step_lists(doc)` helper): for each step's `run:` text in each subject file other than the declared home, if it contains all of `"gh pr view"`, `"headRefName"`, `'echo "pr-number='`, `'echo "branch='`, record a `Finding`. Wire it into `ALL_CHECKS["pr-branch"]`. Verified (research.md D5) against the current tree: `pr-conversation.yml`'s two structurally similar `headRefName` reads (neither writes the `pr-number=`/`branch=` pair) and every other `headRefName` reference elsewhere in the fleet (`watchdog.yml`, `auto-release.yml`, `wing-commander-7-cleanup.yml`, `intake.yml`, `auto-update-spec-kit.yml`) do not match this fragment combination. Depends on T016.
- [ ] T019 [US3] Extend `_clean_tree(root)` with a minimal valid `.github/scripts/board_item_marker.py` (a stub `write_marker` plus the `main()`/CLI guard from T002's shape) and a minimal valid `.github/actions/_shared/resolve-pr-branch/action.yml`, so the synthetic "clean tree" `selftest_clean_tree_passes()` continues to pass with both new declared homes present alongside the eight existing ones. Depends on T017, T018.
- [ ] T020 [US3] In `run_selftest()`, add `selftest_third_paste_fails("marker-write", <a new synthetic workflow path>, <the old sys.path.insert + board_item_marker + write_marker bootstrap text>)` and `selftest_third_paste_fails("pr-branch", <a new synthetic workflow path>, <the old gh pr view + headRefName + GITHUB_OUTPUT pr-number/branch text>)`, mechanically identical in shape to the 13 existing `selftest_third_paste_fails` calls (FR-012/Constitution VIII — every failure branch proven by a checked-in fixture, not a manual demonstration). Depends on T019.
- [ ] T021 [US3] Re-verify (do not modify) `check_board_stop_check` and its existing `selftest_third_paste_fails("board-stop-check", ...)` call still pass on the current tree (research.md D1: this idiom's declared home and structural gate already exist from commit `98ee260`, an ancestor of the spec's own `e170077` triage baseline — FR-011's "MUST gain such a check" and User Story 3's Acceptance Scenario 1 are pre-satisfied). Record this confirmation as the evidence for AS1/FR-011/SC-004's third idiom; do not add a new `DECLARED_HOMES` entry or check function for it. Depends on T020.
- [ ] T022 [US3] Run `python3 .github/scripts/verify-single-home-idioms.py --self-test` (quickstart.md step 5) and confirm all checks pass, including the two new ones and the existing generic waiver-interaction cases (`selftest_waived_copy_passes`, `selftest_stale_waiver_fails`), which cover `marker-write`/`pr-branch` for free since `apply_waivers`/`check_waiver_shape` are check-agnostic. Depends on T021.

**Checkpoint**: All three idioms — marker-write, pr-branch, and (pre-existing) board-stop-check — now fail a gate when re-pasted at a new site, naming their declared home.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Confirm the feature-wide invariants no single story's gate fully covers on its own.

- [ ] T023 Run `python .github/scripts/run-local-gates.py` (FR-017, CLAUDE.md's own instruction, quickstart.md step 3) and confirm the full PR-time gate suite passes, including Gate 60 (bare and `--self-test`) and Gate 98 (`verify-board-loop-helper-provenance.py`, both bare and its own self-test) — SC-007. No source change to Gate 98 is expected: its `ALLOWED_PYTHON_ARGS_RE` already permits `python3 -I "$RUNNER_TEMP/wc-pristine/scripts/<name>.py"`, and its `HELPER_IMPORT_RE` only scans for a `from`/`import` line in the caller's own `run:` text, which the CLI invocation never contains.
- [ ] T024 [P] Confirm SC-008: `.github/scripts/single-home-waivers.json` still has its original 6 entries (`token-mint`, `failure-issue`, `promotion`, `size-path-backstop`, `dispatch-and-wait`, `stage-findings`) — 0 new waiver entries added for this feature's own consolidation.
- [ ] T025 [P] Confirm Constitution VII / FR-009: `resolve-pr-branch` stays under `.github/actions/_shared/`, is never referenced from a published (non-underscore) composite or a `workflow_call`-only stage, and Gate 60's `check_promotion` continues to pass with no changes needed.
- [ ] T026 Confirm FR-016: the consolidation changes no observable board-loop behaviour except FR-008's one deliberate exception (PR-branch resolution now fails loudly on a failed or empty read instead of silently checking out the default branch) — same markers written at the same points, same refs checked out otherwise, same jobs pausing on the same stop signals.
- [ ] T027 Record, on lifecycle issue #607, that quickstart.md step 6 (a post-merge re-drive of one scheduled `board-loop.yml` run, confirming status-comment markers are unchanged, the review/readiness jobs check out the expected PR branch, and Gate 98's provenance check is green on that run) remains a manual post-merge confirmation per CLAUDE.md's "a fix to behaviour that only runs in Actions is proven after merge by re-driving one run" rule — not part of this feature's own gate suite, and not blocking this feature's completion.

**Checkpoint**: The full local gate suite is green, no new waiver was needed, the published/internal boundary held, and the post-merge proof step is recorded as outstanding rather than silently skipped.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — confirms citations and baseline counts before any edit.
- **Foundational (Phase 2)**: None — see note above.
- **User Story 1 (Phase 3)**: Depends on Setup. No dependency on User Story 2.
- **User Story 2 (Phase 4)**: Depends on Setup. No dependency on User Story 1 — different jobs' steps, different new file.
- **User Story 3 (Phase 5)**: Depends on User Story 1 (T002, the declared home `check_marker_write` points at and the fact that the 17 inline sites are gone before the check is added) and User Story 2 (T011, the declared home `check_pr_branch` points at) — see spec.md's own "Why this priority" for User Story 3.
- **Polish (Phase 6)**: Depends on User Story 1, User Story 2, and User Story 3 all being complete.

### User Story Dependencies

- **US1 (P1)**: Can start immediately after Setup. No dependency on US2.
- **US2 (P2)**: Can start immediately after Setup, in parallel with US1 — disjoint jobs in the same file, plus one new file.
- **US3 (P3)**: Depends on both US1 and US2 being complete — adding `check_marker_write` or `check_pr_branch` before the corresponding consolidation lands would immediately fail Gate 60 against the still-inline call sites.

### Within Each User Story

- US1: the CLI entrypoint (T002) before any call-site edit (T003–T008); all six jobs' edits before the byte-identity and count confirmations (T009, T010).
- US2: the composite (T011) before either call-site edit (T012, T013); both edits before the downstream-reference and count confirmations (T014, T015).
- US3: the two `DECLARED_HOMES` entries (T016) before either check function (T017, T018); both check functions before the self-test fixture additions (T019, T020); the board-stop-check reconfirmation (T021) can run any time after T020 but is listed last to close out the story's three-idiom scope; the full `--self-test` run (T022) last.

### Parallel Opportunities

- T017 and T018 (US3's two new check functions) can be written in parallel once T016 lands — different fragment tuples, different functions, no shared line.
- T024 and T025 (Polish) can run in parallel with each other and with T023/T026.
- US1 (T002–T010) and US2 (T011–T015) can proceed in parallel once Setup is complete — disjoint jobs in `board-loop.yml`, plus one new file for US2; only within `board-loop.yml` itself should the two lines of work coordinate to avoid clobbering each other's edits in the same file.

---

## Parallel Example: User Story 3's two new checks

```bash
# Launch both new check functions together, once T016 (DECLARED_HOMES entries) lands:
Task: "Add MARKER_WRITE_FRAGMENTS + check_marker_write, file-wide co-occurrence (T017)"
Task: "Add check_pr_branch, per-step co-occurrence via _step_lists (T018)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 3: User Story 1 (the marker-write CLI entrypoint and all 17 call sites).
3. **STOP and VALIDATE**: Run T009's byte-identity comparisons and T010's count confirmation; this alone closes SC-001 and SC-003, the largest and highest-risk consolidation, even before US2/US3 land.

### Incremental Delivery

1. Setup → confirm baseline counts and line citations.
2. Add US1 (marker-write) → validate independently (T009/T010) — SC-001/SC-003/SC-006 hold for the marker-write idiom.
3. Add US2 (PR-branch) → validate independently (T014/T015) — SC-002 holds, and FR-008's loud-failure behaviour is in place.
4. Add US3 (gate coverage) → validate via `--self-test` (T022) — SC-004 holds for all three idioms, including the pre-existing board-stop-check.
5. Polish (Phase 6) → run the full local gate suite, confirm no new waiver, record the post-merge proof step.

### Suggested Team Split

With parallel capacity: one line of work on US1 (marker-write, `board_item_marker.py` + 6 jobs), one on US2 (PR-branch composite + 2 jobs) — both can proceed simultaneously after Setup, converging at US3's gate extension once both declared homes exist.

---

## Notes

- [P] tasks touch different files, or (T017/T018) different functions with no shared line in the same file.
- US1 and US2 are independent of each other but both feed US3, which cannot be added before either lands without immediately failing Gate 60 against the still-duplicated sites it would be scanning for.
- The board-stop-check idiom (research.md D1) needs no new code in this feature — T021 is a reconfirmation task, not an implementation task, and exists so User Story 3's third-idiom scope has recorded evidence rather than an assumption.
- No new gate number is introduced; every new check and self-test fixture extends the existing Gate 60 (`verify-single-home-idioms.py`), per FR-015.
- Commit after each task or logical group, consistent with this repository's existing per-task commit discipline on the implementation stage.
