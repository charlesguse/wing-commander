---

description: "Task list for feature 049: Single home for the auto-release / auto-update shared idioms"
---

# Tasks: Single home for the auto-release / auto-update shared idioms

**Input**: Design documents from `/specs/049-single-home-release-idioms/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: Not explicitly requested. The byte-identity check FR-009 requires and the gate's own `--self-test` fixtures are generated as part of the normal implementation tasks below (they are the feature's acceptance mechanism, per constitution VIII), not a separate opt-in TDD pass.

**Organization**: Tasks are grouped by user story (spec.md priorities P1-P4) to enable independent implementation and testing of each story. Two artifacts — the shared verdict helper script and the Constitution VII clarification — are pulled into Foundational rather than User Story 3, because contracts/scoped-app-token.md and contracts/orphan-branch-reset.md design User Story 1's own `auto-release.yml` call sites to emit their failure verdict through that script from the moment they're wired; see Dependencies & Execution Order below for why.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US4)
- Line numbers cited below are today's (`main`, post-#317) positions, taken from research.md/data-model.md/contracts/; each edit within a phase that touches a file more than once shifts later line numbers in that same file, so locate sites by the step name in quotes, not by line number alone, once a prior task in the same phase has landed.

## Path Conventions

CI/CD pipeline infrastructure repository — no `src`/`tests` split. Paths below are repository-root-relative (`.github/`, `docs/`, `specs/`, `.specify/`), per plan.md's Project Structure.

---

## Phase 1: Setup

**Purpose**: Establish the baseline facts this feature's record corrections and byte-identity test depend on, before any shared-definition code is written.

- [X] T001 Confirm the working tree is rebased onto `main` past #317 (merged 2026-09-14T03:03:22Z) per FR-021, and record today's baseline facts that research.md D11 and the User Story 4 corrections depend on: `.github/scripts/verify-stage-shell-lint.py`'s `SHELL_EXEMPT` dict contains no `auto-release.yml` entry (only `watchdog.yml`, `auto-update-spec-kit.yml`, `pr-conversation.yml`), `.github/workflows/release.yml` has no `auto-release.yml` reference, and `docs/architecture.md` has zero `auto-release` mentions. No file changes — this is a verification gate before Phase 2 begins.
- [X] T002 [P] Capture the pre-refactor byte-identity fixture required by FR-009: for each of the 14 verdict-construction call sites in `.github/workflows/auto-release.yml` (the `poll` step's `write_verdict`/`emit_verdict` at lines 497-506, `config`×3, `reachable`×2, `reset`×2, `speckit-version`×1, `scaffold`×3, `kickoff`×2, `report` job's defensive fallback×1 — research.md D3's full list), record each site's exact `jq -n` program and one representative set of literal input values, plus that program's byte-for-byte JSON output for those inputs, into `specs/049-single-home-release-idioms/verdict-fixtures.md`. This is the "before" half of the diff T024 runs against the shipped script.

**Checkpoint**: Baseline facts are on record; the verdict-construction "before" state is captured for later byte-identity comparison.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Two artifacts every later phase either cites as prior art or calls directly.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Amend `.specify/memory/constitution.md` Principle VII ("Two Interfaces — The Published Contract and the Consuming Instrument") to add one sentence: underscore-prefixed directories under `.github/actions/` are internal to this repository and are not part of the published, adopter-pinned surface, and promoting one to the published surface later is a deliberate act in a future release, not a rename. Bump the document version 1.6.0 → 1.6.1 (`**Version**` line, `Last Amended` date) and stack a new Sync Impact Report comment block at the top of the file — "clarifications = PATCH" per the file's own Governance rule, matching every prior amendment's format — per FR-024 and research.md D10.
- [X] T004 [P] Create `.github/actions/_shared/auto-release-verdict.sh`: given `outcome`, `head`, `failing_check`, `expected`, `observed`, `evidence_url` as positional arguments, print one line of JSON — `{outcome, verified_head, failing_check, expected, observed, evidence_url}`, with `failing_check`/`expected`/`observed` coerced from empty string to JSON `null` — extracted verbatim from today's `write_verdict` (`auto-release.yml:497-506`'s `jq -n` program), invoked the same way `_shared/count-turns.sh` is (`bash .github/actions/_shared/auto-release-verdict.sh ...`, never sourced). No call site is rewired to use it yet — contracts/verdict-helper.md, research.md D3.

**Checkpoint**: The verdict helper and the constitutional basis for `_shared/` composites are in place. User story work can begin.

---

## Phase 3: User Story 1 - A fix to a shared idiom lands once (Priority: P1) 🎯 MVP

**Goal**: The scoped App-token mint, the orphan-branch force-reset, and the durable failure issue each have exactly one definition, consumed by both `auto-release.yml` and `auto-update-spec-kit.yml` at every site where they use that idiom today.

**Independent Test**: Change one observable detail in each shared home (an error message, a branch-naming clause, a label colour) and confirm both workflows' behaviour changes with a single edit, with no second copy of the changed text anywhere under `.github/workflows/`.

### Implementation for User Story 1

- [X] T005 [P] [US1] Create `.github/actions/_shared/scoped-app-token/action.yml`: inputs `app-id`, `private-key` (secrets, passed through), `owner`, `repo-name`, `check-default-branch` (`"true"`/`"false"`, default `"false"`); step 1 `uses: actions/create-github-app-token@v3` with `continue-on-error: true`, scoped to `owner`/`repositories: repo-name`; step 2 a `shell: bash` step reading step 1's `.outcome`/`.outputs.token` — on mint failure, `ok=false`, `failure-reason=token-mint-failed`, empty `token`; on mint success, run `gh repo view "$OWNER/$REPO_NAME"`, and when `check-default-branch: "true"` additionally require `--json defaultBranchRef` to report a non-empty name (publishing it as `default-branch`), else `ok=false`, `failure-reason=unreachable`; outputs `token`, `ok`, `default-branch`, `failure-reason` (`token-mint-failed`\|`unreachable`\|`""`) — builds no remediation message or verdict itself (FR-005) — contracts/scoped-app-token.md.
- [X] T006 [P] [US1] Create `.github/actions/_shared/orphan-branch-reset/action.yml`: inputs `token`, `repo` (`owner/name`), `branch`, `bot-name`, `bot-email`, `workdir`, `commit-message`; one `shell: bash` step reproducing verbatim today's detach→delete→orphan→drop-index→clear-tree→commit→force-push sequence (contracts/orphan-branch-reset.md's literal block): clone via a tokenised `https://x-access-token:${TOKEN}@github.com/${REPO}.git` URL (failure → `ok=false`, `failure-stage=clone`), `git remote set-url origin` back to the plain HTTPS URL *before the step ends* so the token is never left in `.git/config` (FR-002's load-bearing property), `git checkout --quiet --detach`, `git branch -D "$BRANCH"` (tolerating "doesn't exist"), `git checkout --quiet --orphan "$BRANCH"`, `git rm -rq --cached .`, `find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +`, `git commit --quiet --allow-empty -m "$COMMIT_MESSAGE"`, `git push --force --quiet` (failure → `ok=false`, `failure-stage=push`); outputs `ok`, `failure-stage` (`clone`\|`push`\|`""`). Everything after the placeholder commit (each caller's own content scaffolding) stays at the call site.
- [X] T007 [P] [US1] Create `.github/actions/_shared/durable-failure-issue/action.yml`: inputs `token`, `operation` (`report`\|`close`), `label`, `label-color`, `label-description`, `title` (report only), `body-file` (report only, a path the caller has already written — no `body:` string input), `close-comment` (close only); one `shell: bash` step, both operations sharing the lookup `gh issue list --repo "$GITHUB_REPOSITORY" --label "$LABEL" --state open --json number --jq '.[0].number // empty'`; `operation: report` — comment on the found issue (`action-taken=commented`) or idempotently `gh label create ... --force` then `gh issue create` (`action-taken=created`); `operation: close` — close the found issue with `close-comment` (`action-taken=closed`) or no-op (`action-taken=none`); outputs `issue-number`, `action-taken` — contracts/durable-failure-issue.md, research.md D4/D6 (comment rendering via `wing-commander-callout` stays at the call sites that use it today, unaffected).
- [X] T008 [US1] In `.github/workflows/auto-release.yml`'s `verify-e2e` job, replace the "Mint a scoped App token for the test repository" and "Confirm the test repository is reachable" steps (today lines 166-217) with one `uses: ./.github/actions/_shared/scoped-app-token` step (`check-default-branch: "true"`), followed by a short `run:` step that, on `ok != 'true'`, calls `bash .github/actions/_shared/auto-release-verdict.sh` (T004) with `failing_check`/`expected`/`observed` text keyed off `failure-reason` (one `if`/`elif` arm per `failure-reason` value, unchanged remediation wording from today, per FR-007) — contracts/scoped-app-token.md. Depends on: T004, T005.
- [X] T009 [US1] In `.github/workflows/auto-release.yml`'s `verify-e2e` job, replace the detach-through-push portion of the "reset" step (today lines 227-294) with `uses: ./.github/actions/_shared/orphan-branch-reset` (`workdir: e2e-test-repo`, `bot-name: wing-commander-auto-release[bot]`, `branch` = the job's already-resolved default branch), keeping the preceding issue/PR cleanup and following verdict-on-failure handling (reading `ok`/`failure-stage` into `bash .github/actions/_shared/auto-release-verdict.sh`, T004) as the job's own steps — contracts/orphan-branch-reset.md. Depends on: T004, T006. Sequential with T008 (same job, same file).
- [X] T010 [US1] In `.github/workflows/auto-release.yml`'s `report` job, rewire its three failure-report sites (verification failed, version collision, release dispatch failed — today lines 810-876) and its one success-path close site (today lines 848-852) to call `uses: ./.github/actions/_shared/durable-failure-issue` with `operation: report` (each site keeps composing its own `title` and body file) and `operation: close` (`close-comment: "Resolved: ${NEXT_VERSION} released."`, unchanged text) respectively — contracts/durable-failure-issue.md. Depends on: T007. Sequential with T008/T009 (same file).
- [X] T011 [US1] In `.github/workflows/auto-update-spec-kit.yml`'s `e2e-stage` job, replace the "Mint a scratch-repository App token" and "Resolve the scratch repository" steps (today lines ~1755-1784) with one `uses: ./.wing-commander-pipeline/.github/actions/_shared/scoped-app-token` step (`check-default-branch: "false"`, default; self-checkout path per research.md D2), followed by a short `run:` step that on `ok != 'true'` emits today's same two `::error::` messages and `exit 1` (unchanged text) — contracts/scoped-app-token.md. Depends on: T005.
- [X] T012 [US1] In `.github/workflows/auto-update-spec-kit.yml`'s `e2e-stage` job, replace the detach-through-push portion of the "Scaffold and force-push" step (today lines 1815-1850) with `uses: ./.wing-commander-pipeline/.github/actions/_shared/orphan-branch-reset` (`workdir: e2e-scratch`, `bot-name: ${{ steps.ctx.outputs.bot-slug }}[bot]`, `branch: auto-update-spec-kit/e2e-$ISSUE`), keeping the `uvx specify init` scaffolding and the real-content commit/push that follow it as the job's own steps — contracts/orphan-branch-reset.md. Depends on: T006. Sequential with T011 (same job, same file).
- [X] T013 [US1] In `.github/workflows/auto-update-spec-kit.yml`, rewire its four `auto-update:failed` report sites (rollback/health-check failed, verification failed, prepare failed, revert-merged summary — today lines 2542-2622, 2774-2799, 2811-2851, 2972-2991) to call `uses: ./.wing-commander-pipeline/.github/actions/_shared/durable-failure-issue` with `operation: report` only. Do **not** add an `operation: close` call at any of these four sites — `auto-update:failed` issues are closed only by a human today (`auto-update-spec-kit.yml:2970-2971`'s own comment), and FR-007 forbids retrofitting that behaviour change — research.md D5. Depends on: T007. Sequential with T011/T012 (same file).
- [X] T014 [US1] Run quickstart.md §2's verification: for each of the three shared homes, make one throwaway observable edit (the reachability-check remediation text in T005's action.yml, the detach clause in T006's action.yml, the label-create call in T007's action.yml) and confirm via `git grep` that the pre-edit text now appears nowhere else under `.github/workflows/` or `.github/actions/`; revert each throwaway edit. Depends on: T008-T013.

**Checkpoint**: User Story 1 complete — each of the three idioms has exactly one definition, both workflows consume it at every site, and no second copy remains (FR-001 through FR-007). Independently testable and shippable as the MVP.

---

## Phase 4: User Story 2 - The next paste fails CI instead of review (Priority: P2)

**Goal**: A structural gate (Gate 52) fails the moment any of the three idioms, or the fail-infra verdict shape, is re-pasted anywhere under `.github/workflows/` or `.github/actions/` — including at a site that is neither known consumer — naming both the offending site and the shared home to call instead.

**Independent Test**: Add a fixture workflow that re-pastes each idiom, run the gate suite locally, confirm it fails and names the shared home; remove the fixture and confirm the suite passes.

### Implementation for User Story 2

- [X] T015 [US2] Create `.github/scripts/single-home-waivers.json`: same schema as `.github/scripts/stage-invariant-waivers.json` (a `"waivers"` list, each entry `{file, check, pattern, count, issue, reason}`, `check` one of `token-mint`\|`orphan-reset`\|`failure-issue`\|`verdict-shape`\|`promotion`), starting with an empty `"waivers": []` list and a `$comment` header block explaining the mechanism, mirroring `stage-invariant-waivers.json`'s own header — research.md D8, no waivers expected at merge time.
- [X] T016 [US2] Create `.github/scripts/verify-single-home-idioms.py` (Gate 52) with its four checks, each scanning every `.github/workflows/*.yml` and everything under `.github/actions/**` while excluding its own declared home: (1) **orphan-reset** — literal co-occurrence in one file of `checkout --quiet --orphan`, `git rm -rq --cached`, and the `find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf` clause, excluding `_shared/orphan-branch-reset/action.yml`; (2) **durable-failure-issue** — co-occurrence of a `gh label create ... --force` call and a `gh issue list ... --label "..." --state open --json number --jq '.[0].number // empty'`-shaped lookup, excluding `_shared/durable-failure-issue/action.yml`; (3) **verdict-shape** — a `jq` program whose text contains all six of `outcome`, `verified_head`, `failing_check`, `expected`, `observed`, `evidence_url`, excluding `_shared/auto-release-verdict.sh` and its call sites; (4) **token-mint** — YAML-parsed (never grepped, per Gate 51's own stated rationale): a job containing both a step with `continue-on-error: true` and `uses:` matching `actions/create-github-app-token@*`, and a later step in the same job whose `if:`/`env:`/`run:` references that step's `.outcome` output, excluding `_shared/scoped-app-token/action.yml`. Each failure emits `::error file=<path>::verify-single-home-idioms: <file>:<line>: <detail> -- see .github/actions/_shared/<home>` (FR-011). Fail loudly (non-zero exit, no silent pass) when zero `.github/workflows/*.yml` files are discovered or any of the four declared-home paths is missing on disk (FR-014). Load and stale-check `single-home-waivers.json` (T015) reusing `verify-stage-invariants.py`'s `load_waivers`/`check_waiver_shape`/`apply_waivers` shape (a waiver matching zero findings fails; a waiver whose matched count differs from its declared `count` fails) — contracts/single-home-gate.md, data-model.md, research.md D7/D8. Depends on: T004, T005, T006, T007, T015 (declared-home paths must exist for the fail-loud-on-missing-subject check to have real paths to verify against).
- [X] T017 [US2] Add the promotion-prevention pass to `.github/scripts/verify-single-home-idioms.py`: using `wc_published_stages.py`'s existing discovery, scan every `workflow_call`-only stage workflow and every `.github/actions/<name>` whose `<name>` does not start with `_` for any `uses:`/sourced-script reference resolving into an `_shared/` path (`./.wing-commander-pipeline/.github/actions/_shared/...` or `./.github/actions/_shared/...`); any hit fails, naming the resolving site and the internal path it reached (FR-025, research.md D9). Same file as T016, sequential.
- [X] T018 [US2] Add a `--self-test` flag to `.github/scripts/verify-single-home-idioms.py` with synthetic tempdir fixtures (Gate 47 style, since the real call sites cannot safely be mutated in place): (a) a clean tree with only the declared homes passes; (b) a second copy of each idiom in a synthetic third workflow — neither `auto-release.yml` nor `auto-update-spec-kit.yml` — fails and names both the fixture's offending `file:line` and the real shared home's path (FR-023's explicit bar); (c) a waived copy passes; (d) a stale waiver (zero matches, or a matched count differing from its declared `count`) fails; (e) a synthetic `workflow_call` stage and a synthetic non-underscore composite, each referencing `_shared/`, both fail the promotion check. Same file as T016/T017, sequential.
- [X] T019 [US2] Wire Gate 52 into `.github/workflows/lint-workflows.yml`'s existing sequential gate job, immediately after the Gate 51 steps (today ending ~line 3163): a "Gate 52 — each of the three cross-workflow idioms and the fail-infra verdict shape has exactly one home, and no published surface resolves an internal helper" step running `python .github/scripts/verify-single-home-idioms.py`, and a "Gate 52 self-test" step running `--self-test`, both `if: "!cancelled()"` (never `continue-on-error`, so it isn't suppressible by an unrelated gate sharing the job — FR-016). Confirm the job's existing trigger path filters already cover `.github/workflows/**` and `.github/actions/**`; add `.github/scripts/single-home-waivers.json` to the filter if it's scoped narrower than `.github/**` (FR-012, FR-013 — contracts/single-home-gate.md "Wiring"). No separate `run-local-gates.py` registration step — it derives Gate 52 automatically from this job, matching every other `verify-*.py` gate.
- [X] T020 [US2] Run the `review-step-gating` skill (CLAUDE.md) against the `if:` changes T019 makes to `.github/workflows/lint-workflows.yml` and fix any findings it surfaces.
- [X] T021 [US2] Run `python .github/scripts/verify-single-home-idioms.py --self-test` and confirm every fixture from T018 passes (quickstart.md §3); then run `python .github/scripts/verify-single-home-idioms.py` against the real, consolidated tree from User Story 1 and confirm zero findings. Depends on: T014 (US1's consolidation), T016-T019.

**Checkpoint**: User Story 2 complete — a third paste of any idiom now fails CI, naming the shared home to call instead (FR-010 through FR-016, FR-023, FR-025, FR-026).

---

## Phase 5: User Story 3 - The fail-infra verdict has one shape (Priority: P3)

**Goal**: `auto-release.yml`'s fail-infra verdict is constructed through the one helper (T004) at all 14 sites, with no hand-built `jq -n` verdict construction left anywhere in the workflow.

**Independent Test**: Add a field to the verdict in the single helper and confirm every emitting site in `auto-release.yml` carries it, with no hand-built `jq -n` verdict construction left.

### Implementation for User Story 3

- [X] T022 [US3] In `.github/workflows/auto-release.yml`'s `poll` step, replace `write_verdict`/`emit_verdict`'s inline `jq -n '{...}'` invocation (today lines 497-506) with a call to `bash .github/actions/_shared/auto-release-verdict.sh "$OUTCOME" "$HEAD_SHA" "$FAILING_CHECK" "$EXPECTED" "$OBSERVED" "$EVIDENCE_URL"` (T004), keeping the site's own `GITHUB_OUTPUT` heredoc framing (`echo 'verdict<<AUTO_RELEASE_VERDICT_EOF'` / `echo 'AUTO_RELEASE_VERDICT_EOF'`) unchanged — contracts/verdict-helper.md.
- [X] T023 [US3] Replace the remaining 10 hand-built `jq -n '{...}'` verdict sites in `.github/workflows/auto-release.yml` — `config`×3, `speckit-version`×1, `scaffold`×3, `kickoff`×2, `report` job's defensive fallback×1 (research.md D3's full list, minus the `reachable`×2 and `reset`×2 sites T008/T009 already migrated in User Story 1) — with calls to `bash .github/actions/_shared/auto-release-verdict.sh`, one edit per site, keeping each site's own literal arguments and `GITHUB_OUTPUT` framing unchanged (this is a refactor of construction, not content, per the spec's behaviour-preserving assumption) — contracts/verdict-helper.md. Depends on: T004. Sequential with T022 (same file).
- [X] T024 [US3] Write the byte-identity test (FR-009): using the pre-refactor fixtures captured in T002, run the shipped `auto-release-verdict.sh` for each of the 14 sites' captured literal inputs and diff its stdout against the pre-refactor `jq -n` output captured for the same inputs — zero diffs expected. House this test alongside Gate 52's self-test harness (`wc_shell_harness.run_step()`, the pattern `verify-metrics-summary-record-emission.py` already uses) per contracts/verdict-helper.md. Depends on: T002, T004, T022, T023.
- [X] T025 [US3] Run `git grep -n "outcome:" .github/workflows/auto-release.yml .github/actions` and confirm the only site defining the `{outcome, verified_head, failing_check, expected, observed, evidence_url}` shape is `_shared/auto-release-verdict.sh`, with every other match a call site invoking it or reading its output (quickstart.md §4). Depends on: T022-T024.

**Checkpoint**: User Story 3 complete — the verdict is constructed in exactly one place; adding a field changes exactly one file (FR-008, FR-009).

---

## Phase 6: User Story 4 - The records describe the tree that shipped (Priority: P4)

**Goal**: `docs/architecture.md`, spec 045's `tasks.md`, and PR #317's finalize narrative each describe the tree that actually shipped, not a claim that drifted from it.

**Independent Test**: Read `docs/architecture.md` end to end and confirm every free-standing pipeline workflow has a section before "Reusability"; read specs/045's T023 and finalize narrative and confirm each claim is checkable against the merged tree.

### Implementation for User Story 4

- [X] T026 [P] [US4] Add a new `## Auto-Release` H2 section to `docs/architecture.md`, inserted after `## Private-image dogfood` (ends today line 1103) and before `## Reusability` (starts today line 1105), matching `## Private-image dogfood`'s depth (a Trigger paragraph + one prose block covering purpose and the wrapper/stage division, no bullet list, no bold run-in subsections — not the deeper `## Auto-Update Spec Kit` shape, and not published-stage depth, since `auto-release.yml` has no `workflow_call` contract). Content: trigger (`schedule`, `workflow_dispatch`, the `WING_COMMANDER_AUTO_RELEASE_PAUSED` kill switch per docs/setup.md); purpose (verify the latest merged features against a maintainer-onboarded end-to-end test repository before cutting a release); and a pointer to the three shared composites this workflow now consumes (`_shared/scoped-app-token`, `_shared/orphan-branch-reset`, `_shared/durable-failure-issue`) rather than re-describing their mechanics inline — contracts/records-corrections.md FR-017.
- [X] T027 [P] [US4] Correct `specs/045-auto-release-verified-head/tasks.md` T023 (today line 199): replace its current text (which directs adding `auto-release.yml` to the `shell_exempt` array and implies that happened) with a record of the finding — `auto-release.yml` triggers on `schedule`/`workflow_dispatch`, never `workflow_call`, so `wc_published_stages.py` never derives it as a published stage; Gate 48's closure check therefore never forces it into either `SHELL_LINTED` or `SHELL_EXEMPT`; no entry for it exists in `verify-stage-shell-lint.py`'s `SHELL_EXEMPT` dict or in `release.yml` today (confirmed against `origin/main` by T001), and none is required. Keep the task marked `[X]` — the task was "record the deliberate choice," and recording it correctly is what this feature finishes — contracts/records-corrections.md FR-018.
- [ ] T028 [US4] Edit PR #317's body via `gh pr edit 317 --body-file -` to correct its finalize narrative (`<!-- wing-commander-finalize:narrative:begin --> ... <!-- wing-commander-finalize:narrative:end -->` block): replace "all gate suite checks passing" with an accurate statement that CI on #317 failed Gate 12, then failed Gate 15, before eventually passing; replace the claim that `auto-release.yml` "was registered as shell_exempt in release.yml's Gate 1a" with the same finding T027 records (no registration exists or is required). No investigation into *why* Gate 12/Gate 15 failed is in scope. This is a metadata edit to a merged PR's description, not a new commit — it does not touch #317's merged commit history — contracts/records-corrections.md FR-019, FR-020. Depends on: T027 (same finding text, kept consistent). **Blocked**: this and every implement run to date has only `gh issue view`/`gh issue comment` in its allowed command list, not `gh pr edit`/`gh pr view` — a human with `gh pr edit` access must apply this edit.

**Checkpoint**: All four user stories complete. `docs/architecture.md`, spec 045's `tasks.md`, and PR #317's narrative all describe the tree that shipped (FR-017 through FR-020).

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Whole-tree validation once every story has landed.

- [X] T029 Run `python .github/scripts/run-local-gates.py` from the repository root and confirm every gate passes, including Gate 52 and its self-test step, with Gate 52 listed among the gates the script ran (confirming registry reachability — constitution VIII, FR-012) — quickstart.md §1, SC-004.
- [X] T030 [P] Diff the set of non-underscore-prefixed directory names directly under `.github/actions/` before and after this feature's changes and confirm it is identical — no new published composite added, none removed or renamed (quickstart.md §5, SC-008).
- [X] T031 Run this PR's code review (CLAUDE.md's "every fix PR gets a code review before merge") and fix its findings in this same PR; if the review surfaces a bug outside this feature's scope, file it as a new issue carrying the line "Found by the code review of #326" rather than widening this PR.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories. T004 (the verdict helper) is pulled forward from User Story 3 because contracts/scoped-app-token.md and contracts/orphan-branch-reset.md design User Story 1's own `auto-release.yml` call sites (T008, T009) to emit their failure verdict through it from the moment they're wired — without T004 landing first, T008/T009 would have nothing to call.
- **User Story 1 (Phase 3)**: Depends on Foundational. No dependency on User Story 2, 3, or 4.
- **User Story 2 (Phase 4)**: Depends on Foundational (T004) and on User Story 1's three composites (T005-T007) existing on disk, since Gate 52's fail-loud-on-missing-subject check (FR-014) needs all four declared-home paths to be real files. Per spec.md's own priority ordering (P1 before P2), User Story 1 is complete before User Story 2 begins, so this is satisfied by sequencing alone.
- **User Story 3 (Phase 5)**: Depends on Foundational (T004) and on T002 (Setup, for the byte-identity fixture). Its remaining-10-sites scope (T023) is written to avoid re-touching the `reachable`/`reset` sites User Story 1 already migrated (T008, T009), so it has no hard dependency on User Story 1 completing beyond not double-editing those four sites — sequencing after Phase 3 avoids the conflict.
- **User Story 4 (Phase 6)**: Depends on Setup (T001, for the baseline facts T027/T028 record) only. Independent of User Stories 1-3's code changes — could run in parallel with them if staffed, though it is sequenced last here to match spec.md's priority order.
- **Polish (Phase 7)**: Depends on all four user stories being complete.

### Within Each User Story

- User Story 1: the three composites (T005-T007) can be built in parallel; each workflow's call-site rewiring (T008-T010 for `auto-release.yml`, T011-T013 for `auto-update-spec-kit.yml`) is sequential within its own file since steps in the same job/file conflict; the two workflows' rewiring can proceed in parallel with each other.
- User Story 2: the gate script grows across T016-T018 in one file, so those three are sequential; T015 (waiver file) and T016 have a soft ordering only (T016 loads the waiver file's shape but doesn't require content); T019-T021 depend on the finished script.
- User Story 3: T022 and T023 both edit `auto-release.yml` and must be sequential; T024 depends on both landing.
- User Story 4: T026 and T027 touch different files and are independent; T028 restates T027's finding, so it follows T027.

### Parallel Opportunities

- T002 (Setup) can run alongside T001.
- T005, T006, T007 (the three composite actions, User Story 1) touch three different new files and can run in parallel.
- T026 and T027 (User Story 4, different files) can run in parallel.
- T030 (Polish) can run alongside T029.
- User Story 4 (Phase 6) has no code dependency on User Stories 1-3 and could be worked in parallel with them by a second contributor, despite being sequenced last in this list to match spec.md's priority order.

---

## Parallel Example: User Story 1

```bash
# Launch the three new composite actions together:
Task: "Create .github/actions/_shared/scoped-app-token/action.yml per contracts/scoped-app-token.md"
Task: "Create .github/actions/_shared/orphan-branch-reset/action.yml per contracts/orphan-branch-reset.md"
Task: "Create .github/actions/_shared/durable-failure-issue/action.yml per contracts/durable-failure-issue.md"

# Once those land, the two workflows' rewiring can proceed in parallel:
Task: "Rewire auto-release.yml's three idiom sites (T008-T010)"
Task: "Rewire auto-update-spec-kit.yml's eight idiom sites (T011-T013)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (constitution clarification + verdict helper — CRITICAL, blocks all stories).
3. Complete Phase 3: User Story 1 — the three idioms consolidate, both workflows consume the shared homes.
4. **STOP and VALIDATE**: run quickstart.md §2 (T014) — a one-line edit to each shared home changes both workflows' behaviour, and no second copy remains.
5. This is CLAUDE.md's own stated cost the issue exists to remove, delivered and independently checkable without the enforcement gate, the verdict cleanup, or the record corrections.

### Incremental Delivery

1. Setup + Foundational → verdict helper and constitutional basis ready.
2. Add User Story 1 → validate independently (quickstart §2) → this is the MVP.
3. Add User Story 2 → validate independently (quickstart §3, §7) → the consolidation now has a shelf life beyond the next session.
4. Add User Story 3 → validate independently (quickstart §4) → the verdict's blast radius drops from 14 files to 1.
5. Add User Story 4 → validate independently (quickstart §6) → the two records describe the tree that shipped.
6. Phase 7 (Polish) → whole-tree validation: `run-local-gates.py` green, published surface unchanged, code review passed.

### Parallel Team Strategy

With two contributors (CLAUDE.md's own stated cap on concurrent local agents during this pipeline's implement stage):

1. Both complete Setup + Foundational together (small, sequential-dependency-heavy phase).
2. Once Foundational is done: Contributor A takes User Story 1 (the MVP, and the prerequisite for User Story 2's declared-home files); Contributor B takes User Story 4 (no code dependency on A's work, per Dependencies above) in parallel, then joins A for User Story 2 once User Story 1's composites land, then either takes User Story 3.
3. Phase 7 runs once both have merged their stories' work.
