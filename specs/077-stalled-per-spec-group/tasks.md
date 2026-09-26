---

description: "Task list template for feature implementation"
---

# Tasks: The Stall Mark Waits Its Turn — pr-conversation's Survivor Job Joins the Per-Spec Concurrency Group

**Input**: Design documents from `/specs/077-stalled-per-spec-group/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md, contracts/ (all present)

**Tests**: This feature's "tests" are the repository's `verify-*.py` gate scripts and manual condition-table re-derivation quickstart.md specifies — no separate test framework applies. SC-008 explicitly requires the widened Gate 80 acceptance to be proven "by cases in the gate's own tests, not by the gate passing over the repository alone," so the self-test cases below are first-class implementation tasks, not an optional add-on. SC-003's admission-condition case-by-case check has no new automated harness specced (unlike spec 041's Gate 28/33) — quickstart.md §3 treats it as a read-and-compare verification, so it is captured below as a verification task rather than a new script.

**Organization**: Tasks are grouped by user story per spec.md's priorities. Foundational work (the new `resolve-identity` job and `classify-and-announce`'s rewire onto it) is shared by every story and therefore lives in Phase 2, not inside any one story — US2's own Acceptance Scenario 1 ("the entry job also fails or is skipped") depends on `classify-and-announce`'s toleration clause existing before US2's own tasks can be verified, and US1's Independent Test (Gate 80 passing) depends on `resolve-identity` existing before `stalled` can reference it.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1/US2 = P1, US3 = P2, US4 = P3, per spec.md

## Path Conventions

This repository is a GitHub Actions pipeline component — no `src`/`tests` split. All paths are relative to the repository root: `.github/workflows/**`, `.github/scripts/**`, `specs/**`.

---

## Phase 1: Setup

**Purpose**: Establish a clean baseline before any edit, so a later gate failure is attributable to this feature.

- [X] T001 Run `python .github/scripts/run-local-gates.py` once against the unmodified tree and confirm it is fully green (including Gate 80, `verify-spec-branch-push-concurrency.py`, which today passes only because of the `pr-conversation.yml`/`stalled` waiver this feature removes). Record any pre-existing red gate before touching `.github/workflows/pr-conversation.yml` — nothing below should be blamed on a failure that already existed.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Give `pr-conversation.yml` the `resolve-identity` job every downstream story depends on, and move `classify-and-announce` onto it. Neither task delivers user-visible value alone, but both are load-bearing for US1's concurrency fix and US2's admission-tolerance guarantee: US2's Acceptance Scenario 1 ("the entry job also fails or is skipped") requires `classify-and-announce`'s own `if:` to already skip on a failed `resolve-identity`, which only this phase wires in.

**⚠️ CRITICAL**: No user story task can be verified until this phase is complete.

- [X] T002 In `.github/workflows/pr-conversation.yml`, add a new job `resolve-identity` immediately after `verify-image-prerequisites` and before `classify-and-announce` (today's job order: `verify-image-prerequisites` at `:245`, `classify-and-announce` at `:334`), per contracts/resolve-identity-job.md: `runs-on`/`container`/`environment` copied verbatim from `classify-and-announce`'s own blocks (`:337-348`); `needs: verify-image-prerequisites`; `if: "!cancelled() && needs.verify-image-prerequisites.result != 'failure'"`; `permissions: {pull-requests: read, contents: read}` (no `contents: write`, no `issues: write` — this job never posts or pushes); a single step, `id: identity`, that is `classify-and-announce`'s current "Resolve PR identity and check qualification" step (`:464-529`) relocated byte-for-byte — same `env:` block, same `run:` script, same two behavioral branches (API-read failure: `::error::` + `reason` output + `exit 1`, `:497-505`; non-qualifying PR: `qualifies=false`, empty `slug`/`spec-dir`, step-summary line, no `exit 1`, `:507-529`); `outputs: {qualifies, slug, spec-dir, default-branch, reason}` all sourced from `steps.identity.outputs.*` (research.md D1, D2).
- [X] T003 In `.github/workflows/pr-conversation.yml`'s `classify-and-announce` job, rewire it onto `resolve-identity` (research.md D1, data-model.md's `classify-and-announce` table):
  1. Delete the "Resolve PR identity and check qualification" step (`:464-529`, now living in `resolve-identity` per T002) and the now-orphaned "Report identity-resolution refusal on the PR" comment + step (`:531-543`) — that callout can only ever fire from the deleted step's `refused` output, and Story 2/FR-006's stall notice is its replacement.
  2. Change `needs: verify-image-prerequisites` (`:351`) to `needs: [verify-image-prerequisites, resolve-identity]`, and widen `if:` (`:352`) to `"!cancelled() && needs.verify-image-prerequisites.result != 'failure' && needs.resolve-identity.result != 'failure'"` (FR-005's second half — a failed API read in `resolve-identity` must skip this job outright rather than let it read empty outputs as "this PR does not qualify," the failure mode FR-011 forbids).
  3. In the job's `outputs:` block (`:369-373`), change `qualifies`/`spec-dir`/`slug`/`default-branch` from `steps.identity.outputs.*` to `needs.resolve-identity.outputs.*`; change `refusal-reason` (`:415`) from `${{ steps.identity.outputs.reason || steps.preflight.outputs.reason || steps.meta.outputs.reason }}` to `${{ steps.preflight.outputs.reason || steps.meta.outputs.reason }}` (dropping the first term — `preflight`/`meta` refusals are untouched by this feature, FR-014).
  4. Replace every remaining `steps.identity.outputs.X` reference inside this job's own steps with `needs.resolve-identity.outputs.X`: the `qualifies == 'true'` gates at `:548, 570, 581, 595, 632, 639, 654, 664, 689, 771, 796, 810, 829, 836, 1004, 1040, 1057, 1070, 1081, 1424`; the `SPEC_DIR` env values at `:598, 1147`; the prompt text references at `:854, 872` (FR-009, FR-010 — same values, same gating, new source).
  5. Rewrite the stale concurrency comment (`:358-365`, "Serialized per-PR, not per-spec-dir: spec-dir isn't knowable until the PullRequestIdentity step below runs inside this job...") to state the real reason this job stays per-PR now that `resolve-identity` publishes `spec-dir` before this job's own concurrency is even evaluated: it never itself pushes to `spec/<slug>` — only `act` does, through its own group (research.md D7 item 1).

**Checkpoint**: `resolve-identity` exists and `classify-and-announce` consumes it exclusively; the entry job's behavior is unchanged for every PR (verified in US3/US4 below), and it now skips outright rather than misreporting a failed identity lookup as a non-qualifying PR.

---

## Phase 3: User Story 1 - A stall mark never lands mid-rebase (Priority: P1) 🎯 MVP

**Goal**: `pr-conversation.yml`'s `stalled` job joins the canonical per-specification concurrency group, so its `spec-meta.json` push is ordered against every other writer of the same `spec/NNN-slug` branch.

**Independent Test**: Gate 80 (`verify-spec-branch-push-concurrency.py`) passes with the `pr-conversation.yml`/`stalled` waiver deleted; the job's declared group is read and compared against the canonical spelling every other writer of that branch declares.

### Implementation for User Story 1

- [X] T004 [US1] In `.github/workflows/pr-conversation.yml`'s `stalled` job, rewire `needs:`/`if:`/`concurrency:` (`:3040-3063`) per contracts/stalled-job-concurrency.md: change `needs: [verify-image-prerequisites, classify-and-announce]` to `needs: [verify-image-prerequisites, resolve-identity, classify-and-announce]`; add `needs.resolve-identity.result == 'failure'` as a fourth arm inside the parenthesized group of the `if:` (`:3042-3048`), alongside the existing `verify-image-prerequisites`-failure/`classify-and-announce`-failure/`classify-and-announce`-skipped arms — leave the outer `needs.verify-image-prerequisites.result != 'failure' && !cancelled()` guard and the trailing `needs.classify-and-announce.outputs.refusal-reason == ''` guard unchanged (FR-014); replace `concurrency.group` (`:3062`, today `wing-commander-pr-conversation-pr-${{ inputs.pr-number }}`) with `wing-commander-${{ needs.resolve-identity.outputs.spec-dir }}${{ needs.resolve-identity.outputs.spec-dir == '' && format('pr-conversation-pr-{0}', inputs.pr-number) || '' }}` (research.md D3 — two adjacent `${{ }}` blocks, not one `format(...)` call, so the qualifying case stays textually identical to Gate 80's existing canonical spelling).
- [X] T005 [P] [US1] Delete the `.github/workflows/pr-conversation.yml`/`stalled` entry from `.github/scripts/spec-branch-push-waivers.json` (the entry whose `reason` cites "steps.identity" and "Tracked on #437") in the same change as T004 (FR-003) — Gate 80 stale-checks every waiver, so leaving it in place after the job joins the group fails the gate on its own.
- [X] T006 [P] [US1] Amend `specs/013-serialize-rebase-stages/contracts/concurrency-groups.md`: add the `pr-conversation.yml` / `stalled` row to the Members table (`:28-40`), immediately after the `tasks.yml` `stalled`/`stalled-approved` row, using the exact text from contracts/stalled-job-concurrency.md's "Members table row to add" section (FR-004); add a new "`resolve-identity` job contract (new, `pr-conversation.yml` only)" subsection alongside the existing `resolve-spec` job contract subsection (`:68-92`), documenting the one respect it differs (an API read against `pr-number`, not pure string derivation over a declared `head-ref`/`slug` input) per contracts/resolve-identity-job.md — do not duplicate the full contract text, per this same document's own "not duplicated here" rule (`:53-56`).
- [X] T007 [P] [US1] In `.github/scripts/verify-spec-branch-push-concurrency.py`, add `PR_CONVERSATION_STALLED_FALLBACK_GROUP_RE` (the exact regex from contracts/gate-80-fallback-spelling.md, with the `([\w-]+)`/`\1` backreference requiring the identical `needs.<job>` name in both halves) near `PER_SPEC_GROUP_RE` (`:88-91`); widen `evaluate()`'s acceptance check (`:213`, `if isinstance(group, str) and PER_SPEC_GROUP_RE.match(group.strip()):`) to also accept `PR_CONVERSATION_STALLED_FALLBACK_GROUP_RE.match(group.strip())` — an `or` added to the one branch, not a rewrite (research.md D5, FR-018).
- [X] T008 [US1] In `.github/scripts/verify-spec-branch-push-concurrency.py`'s `self_test()` (`:299-360`), add the six cases from contracts/gate-80-fallback-spelling.md's table, using the existing `case(...)`/`_job()`/`RUN_PUSH` fixtures: (1) the exact fallback spelling, no waiver, passes; (2) the same shape with a mismatched `needs.<job>` name across the two halves still fails (defeats the backreference); (3) the bare `wing-commander-` constant still fails; (4) a near-miss literal (`pr-conversation-{0}`, missing `-pr-`) still fails; (5) a near-miss identifier (`inputs.pr_number`, underscore) still fails; (6) the three existing spellings (`GOOD_GROUP`/`MATRIX_GROUP`/`NEEDS_GROUP`) still pass, unchanged (Constitution VIII — the widening is additive, proven by fixture, not by the repository merely passing). Run `python3 .github/scripts/verify-spec-branch-push-concurrency.py --self-test` and confirm every case, old and new, passes.

**Checkpoint**: Gate 80 passes over the repository with the waiver gone (SC-001), the survivor job's declared group is the canonical per-spec spelling for a qualifying PR, `concurrency-groups.md` lists it, and Gate 80's own self-test proves both the acceptance and its near-miss floor (SC-008). This is the MVP — the defect spec.md opens with is fixed.

---

## Phase 4: User Story 2 - A stalled run still reports itself when identity cannot be resolved (Priority: P1)

**Goal**: When `resolve-identity` itself fails (an unreadable `gh` response), the survivor job still runs, still posts its stall notice to the PR, and joins the per-PR fallback group rather than a degenerate or guessed one.

**Independent Test**: The survivor job's `if:` condition and its post target are read against the three upstream states of `resolve-identity` (success, failure, skipped) crossed with `classify-and-announce`'s own states, and checked to admit the job in every case it is admitted today.

### Implementation for User Story 2

- [X] T009 [US2] In `.github/workflows/pr-conversation.yml`'s `stalled` job, rewrite the "Resolve PR identity independently" step (`id: identity`, `:3123-3147`) and its preceding "Independent identity re-derivation (research.md D6, pr-conversation row)..." comment (`:3115-3122`) per research.md D4: drop the `head_ref`-derivation half entirely (the `gh pr view ... headRefName` call and the `${head_ref#"$SPEC_PREFIX"}` strip, `:3137-3140`) — that identity now comes from `needs.resolve-identity.outputs.slug`/`spec-dir` — and keep only the lifecycle-issue lookup (`gh api ... contents/$SPEC_DIR/spec-meta.json ...`, `:3141`), rewiring its `env:` to `SPEC_DIR: ${{ needs.resolve-identity.outputs.spec-dir }}` and `SPEC_BRANCH: ${{ inputs.spec-prefix }}${{ needs.resolve-identity.outputs.slug }}`, keeping `id: issue-lookup`, `continue-on-error: true`, and `if: needs.classify-and-announce.outputs.refusal-reason == '' && needs.resolve-identity.outputs.spec-dir != ''` (there is nothing to look up when `spec-dir` is empty). Rewrite the preceding comment to describe the derivation-only-prerequisite shape (D6 above) in place of the independent-re-derivation shape it currently describes (research.md D7 item 2).
  Then rewire the `wing-commander-chain-stop-notice` call (`:3169-3183`): `spec-dir: ${{ needs.resolve-identity.outputs.spec-dir }}`, `spec-branch: ${{ inputs.spec-prefix }}${{ needs.resolve-identity.outputs.slug }}`, `issue-number: ${{ steps.issue-lookup.outputs.issue-number || inputs.pr-number }}` (keeping the existing PR-number fallback — Story 2's scenario is exactly when this fallback is load-bearing, unlike `tasks.yml`'s equivalent step which has none).
  Also rewrite the job's header comment (`:3034-3039`, "Survivor job (the #224 idiom, research.md D4): watches classify-and-announce only...") to state that this job now also watches `resolve-identity`'s own result (T004's widened `if:`), not only `classify-and-announce`'s.
- [X] T010 [US2] Read the shipped `stalled` job's `if:` string (from T004) against data-model.md's "Survivor-job condition table" and confirm, for each reachable `(resolve-identity, classify-and-announce)` outcome pair — success/success (not admitted), success/failure (admitted), success/skipped (admitted), success-with-`qualifies=false`/success (not admitted), failure/skipped (admitted, Story 2's case), skipped/skipped (admitted) — that the verdict matches what today's `if:` produces for the same `classify-and-announce` outcome (SC-003). This is quickstart.md §3's read-and-compare check, not a new gate script; re-derive it from the literal merged `if:` string, not from data-model.md's table alone.

**Checkpoint**: A `resolve-identity` failure is visible (the job is red, not silently reporting an empty head ref as success), the survivor job still runs and posts to `inputs.pr-number`, the chain-stop-notice composite receives an empty `spec-dir` and takes its existing "record could not be updated" branch, and the survivor job's concurrency group resolves to the per-PR fallback rather than the degenerate `wing-commander-` constant (FR-005, FR-006, FR-008).

---

## Phase 5: User Story 3 - A PR the stage does not act on stays silent (Priority: P2)

**Goal**: A non-qualifying PR (a `fix/` branch, a `plan/` branch, a `spec-draft/` branch) still produces zero comments and zero failed jobs after `resolve-identity` is introduced ahead of `classify-and-announce`.

**Independent Test**: Exercise head refs that are not `spec/NNN-slug` and confirm the new prerequisite job completes without failing the run and without posting anything, and that the entry job reaches the same qualification verdict it reaches today.

### Implementation for User Story 3

- [X] T011 [US3] Confirm, without further code changes, that T002's relocated step preserves the original non-qualifying branch exactly (`qualifies=false`, empty `slug`/`spec-dir`, a `GITHUB_STEP_SUMMARY` line, no `::error::`, no `exit 1`) and that `resolve-identity` therefore stays green and silent for a `fix/`, `plan/`, `tasks/`, or `spec-draft/` head ref (FR-007). Confirm every `needs.resolve-identity.outputs.qualifies == 'true'` gate T003(4) rewired in `classify-and-announce` — including `act`'s own `needs.classify-and-announce.outputs.qualifies == 'true'` gates at `:1489, 2586, 2769`, which thread through unchanged from `needs.resolve-identity.outputs.qualifies` — still short-circuits identically for such a PR, producing no reply, no comment, and no failed job (FR-009, SC-004).

**Checkpoint**: A non-qualifying PR's silence is provably unchanged (SC-004).

---

## Phase 6: User Story 4 - The identity derivation has one home (Priority: P3)

**Goal**: The `spec/NNN-slug` head-ref-prefix strip and slug-format check exist in exactly one place in `pr-conversation.yml` after this change.

**Independent Test**: Search the stage file for the head-ref prefix strip and slug-format check; confirm each appears once.

### Implementation for User Story 4

- [X] T012 [US4] Grep `.github/workflows/pr-conversation.yml` for the head-ref-prefix-strip/slug-format-check pattern (`${head_ref#"$SPEC_PREFIX"}` combined with the `^[0-9]{3}-[a-z0-9][a-z0-9-]*$` regex) and confirm it now appears exactly once — inside `resolve-identity`'s relocated step (T002) — down from the two full derivations that existed before this feature (`classify-and-announce`'s own step, deleted in T003; `stalled`'s own step, deleted in T009) (FR-012, SC-005).
- [X] T013 [US4] Enumerate every reference to `classify-and-announce`'s identity-shaped job outputs that existed before this change — T003(4)'s full in-job list, plus every downstream `needs.classify-and-announce.outputs.{qualifies,spec-dir,slug,default-branch}` read at `:1489, 1966, 1977, 1999, 2002, 2224, 2586, 2695, 2769` — and confirm each still resolves to the identical value: the job output names are unchanged, only their source (`needs.resolve-identity.outputs.*` instead of `steps.identity.outputs.*`) moved (FR-009, FR-010).

**Checkpoint**: The slug derivation has one home; every existing downstream reference to the entry job's identity outputs is unchanged.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T014 [P] Amend `specs/041-implement-stall-notice/research.md` D6 (FR-019): rewrite the `pr-conversation` row (`:237`) and add the derivation-only-prerequisite clause to the decision text above the table (`:225-229`), using this feature's own research.md D6 section as the source text — cross-check both against the then-current content of `specs/041-implement-stall-notice/research.md` in case it has drifted since this feature's research was written (SC-009).
- [ ] T015 [P] Run the `container-shell-safety` skill against the new `resolve-identity` job (T002) — it adds a `container:` block to a job, which CLAUDE.md requires a pass from that skill before merge.
- [ ] T016 [P] Run the `review-step-gating` skill against every `if:`/`concurrency:` edit this feature makes (T003's toleration clause, T004's widened `if:` and `concurrency.group`, T009's guard clause) — CLAUDE.md requires this pass for any change touching an `if:`, and the plan's Assumptions section calls it out explicitly for the widened admission condition; confirm in particular that the widened `if:` cannot admit `stalled` on a healthy run and that the group expression cannot silently produce the bare `wing-commander-` constant for any reachable value of `needs.resolve-identity.outputs.spec-dir`.
- [ ] T017 Run `python .github/scripts/run-local-gates.py` (the full PR-time gate suite) and confirm it is fully green, including the comment gates that byte-compare the concurrency-block and identity-derivation comments rewritten in T003, T004, and T009 (SC-006).
- [ ] T018 Execute quickstart.md's validation sequence end-to-end (§1 self-test, §2 repository-wide Gate 80 pass, §3 condition-table re-derivation, §4 full gate suite) and confirm every step passes together, not just individually.
- [ ] T019 Post-merge, re-drive one real `pr-conversation` run per quickstart.md §5 — a PR on `spec/<slug>` stalled mid-cycle while an implement or rebase run holds `wing-commander-specs/<slug>`, and separately a PR whose head ref does not parse as `spec/NNN-slug` — and record the run URL(s) as SC-007's evidence on the pull request or lifecycle issue #581, per CLAUDE.md's "a fix to behaviour that only runs in Actions is proven after merge by re-driving one run."

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001)**: No dependencies.
- **Foundational (T002-T003)**: T003 depends on T002 (it reads `needs.resolve-identity.outputs.*`, which must exist first). Both BLOCK every user story task.
- **User Story 1 (T004-T008)**: Depends on Foundational. T004 (the workflow edit) is the anchor; T005/T006/T007 touch different files and have no dependency on each other's completion, only on T004's final group-string text (already fixed by research.md D3, quoted verbatim in each). T008 depends on T007 (same file, adds cases alongside the pattern T007 introduces).
- **User Story 2 (T009-T010)**: Depends on T004 (T009's guard clause and T010's condition table both require `resolve-identity` already present in `stalled`'s `needs:`).
- **User Story 3 (T011)**: Depends only on Foundational (T002-T003) — it verifies `classify-and-announce`/`resolve-identity` behavior, not `stalled`'s. It has no dependency on US1/US2 and may be done in parallel with either.
- **User Story 4 (T012-T013)**: Depends on T003 (classify-and-announce's own step deleted) and T009 (stalled's own step deleted) — "exactly one occurrence" is only true once both deletions have landed.
- **Polish (T014-T019)**: T014-T016 depend only on the specific task they check and may run as soon as that task lands. T017 depends on every prior task. T018 depends on T017. T019 depends on merge.

### Parallel Opportunities

- Within US1, T005 (waivers.json), T006 (concurrency-groups.md), and T007 (gate script pattern) touch three different files and can be done in parallel once T004's group-string text is fixed (it already is, from research.md D3).
- T011 (US3) can be done in parallel with US1 (T004-T008) and US2 (T009-T010) — it depends only on the Foundational phase.
- T014, T015, T016 (Polish) touch three different files/checks and can be done in parallel once their respective source tasks (T002-T009) have landed.

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Setup (T001) + Foundational (T002-T003).
2. Complete User Story 1 (T004-T008).
3. **STOP and VALIDATE**: run `python3 .github/scripts/verify-spec-branch-push-concurrency.py --self-test` and `python3 .github/scripts/verify-spec-branch-push-concurrency.py` — confirm Gate 80 passes with the waiver gone. The defect spec.md opens with is now fixed.

### Incremental Delivery

1. Setup + Foundational → `resolve-identity` exists, `classify-and-announce` reads from it exclusively.
2. User Story 1 → `stalled` joins the per-spec group; Gate 80 passes with no waiver (MVP).
3. User Story 2 → the notice survives a failed `resolve-identity`, provably case by case.
4. User Story 3 → a non-qualifying PR's silence is provably unchanged (can run any time after Foundational).
5. User Story 4 → the derivation's single-home property is provably true.
6. Polish → cross-spec documentation, the two skill passes CLAUDE.md requires, the full gate suite, and the post-merge drill.
