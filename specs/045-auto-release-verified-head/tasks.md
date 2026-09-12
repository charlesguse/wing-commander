---

description: "Task list template for feature implementation"
---

# Tasks: Auto-Release After Merged Features Pass a Scheduled End-to-End Verification

**Input**: Design documents from `/specs/045-auto-release-verified-head/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md,
contracts/auto-release-workflow.md, contracts/e2e-repository-wiring.md,
contracts/release-dispatch.md

**Tests**: No separate "Tests for User Story N" subsections are generated.
plan.md's own Testing section is explicit that this feature introduces no
new `.github/scripts/verify-*.py` gate (research.md D15) — a scheduled
workflow with live GitHub-side polling against a real test repository
cannot be meaningfully unit-tested in isolation. Verification is
`python .github/scripts/run-local-gates.py` (the existing, unchanged gate
suite — Phase 8) plus quickstart.md's six manual scenarios (Phase 8,
flagged where this headless session cannot execute them itself).

**Organization**: Tasks are grouped by user story to enable independent
implementation and testing of each story. This feature is a single new
workflow file (`.github/workflows/auto-release.yml`) built job-by-job, so
most tasks are sequential edits to that one file — [P] is reserved for
tasks touching a genuinely different file.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US5)
- Include exact file paths in descriptions

## Path Conventions

This repository has no `src/`/`tests/` application layout (plan.md Project
Structure) — its "source" is workflow YAML plus a small set of gate
scripts. This feature's footprint is one new workflow file, one existing
workflow's gate-membership array, and one documentation table.

---

## Phase 1: Setup

No setup tasks. This feature introduces no new language, dependency, or
toolchain — every piece is Bash/YAML/`jq`/`git`/`gh` this repository's
runners and gate scripts already use (plan.md Technical Context). The
scratch-repository reset technique, the `gh workflow run` dispatch idiom,
and the durable-issue dedup pattern are all reused inline from
`auto-update-spec-kit.yml`, not re-created (plan.md Structure Decision).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The workflow's own trigger/gating shell and the single
detection read every later job and every user story depends on
(research.md D4: "is there new work" and "has this head already been
auto-released" are answered by the same one read, so it cannot be split
per-story without duplicating it).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T001 Create `.github/workflows/auto-release.yml` with `name: "auto-release"`, `on.schedule` (`cron: "9 9 * * *"`, contracts/auto-release-workflow.md Triggers — a one-line, PR-reviewed knob per FR-002, not a repository variable) plus `workflow_dispatch: {}` (FR-005, no inputs), workflow-level `concurrency: { group: wing-commander-auto-release, cancel-in-progress: false }` (FR-023, research.md D14), and workflow-level `permissions: {}` (contracts/auto-release-workflow.md Permissions — every job below declares only what it individually needs).
- [X] T002 In `.github/workflows/auto-release.yml`, add the `detect` job (`permissions: { contents: read }`, `runs-on: ubuntu-latest`): checkout with `fetch-depth: 0`; resolve the latest release tag via `git tag --list 'v[0-9]*.[0-9]*.[0-9]*'` filtered to the strict `vX.Y.Z` shape (excluding the floating `vX` major tags per research.md D4) and sorted by semver (`sort -V`), taking the highest; resolve `tag_sha` via `git rev-parse "$tag"^{commit}` (the commit the tag points at, not the tag object's own SHA — data-model.md "Latest release tag"); resolve `head_sha` via `git rev-parse HEAD`. Emit job outputs `head-sha`, `tag-exists` (`false` when no such tag exists at all — FR-004), `latest-tag` (empty when `tag-exists` is `false`), and `has-new-work` (`true` iff `tag-exists` is `true` **and** `head_sha` != `tag_sha` — data-model.md "Unreleased head"; `false` whenever `tag-exists` is `false`, since there is no baseline to compare against, not an unconditional "new work" reading).

**Checkpoint**: Foundation ready — `detect`'s outputs are the one shared read every downstream job and every user story below conditions itself on.

---

## Phase 3: User Story 1 - Verified work on main reaches adopters without anyone remembering to tag (Priority: P1) 🎯 MVP

**Goal**: The full happy path — detect new work, drive it through the
published stages against the end-to-end test repository, compute the next
version, and dispatch `release.yml` to cut it.

**Independent Test**: Merge a trivial change to main, dispatch
`auto-release.yml` manually, and confirm a new non-breaking release tag
exists at that commit, created by `release.yml` itself, with the test
repository's lifecycle issue showing verification evidence for every
stage from intake through cleanup (spec.md User Story 1 Independent Test;
quickstart.md Scenario 2).

### Implementation for User Story 1

- [ ] T003 [US1] In `.github/workflows/auto-release.yml`, add the `verify-e2e` job (`if: needs.detect.outputs.has-new-work == 'true'`, `needs: detect`, `timeout-minutes:` a generous fixed constant sized for eight real stages of a single-file fixture to converge in one iteration — an implementation-time value, not a repository variable per plan.md Performance Goals). First steps: read `vars.WING_COMMANDER_AUTO_RELEASE_E2E_REPO`; when unset, set the job's verdict output to `fail-infra` (`failing_check`: "WING_COMMANDER_AUTO_RELEASE_E2E_REPO is unset") and skip the remaining steps via a step-scoped `if:`; otherwise mint a scoped App installation token via `actions/create-github-app-token@v3` with `client-id: ${{ secrets.speckit-app-id }}` / `private-key: ${{ secrets.speckit-app-private-key }}` and `owner`/`repositories` narrowed to the configured repo (mirroring `auto-update-spec-kit.yml`'s `scratch-token` step, `continue-on-error: true` then checking `steps.<id>.outcome`), then `gh repo view "$E2E_REPO" --json defaultBranchRef` with that token — either failure also yields `fail-infra`, naming the App-installation gap (research.md D11, contracts/e2e-repository-wiring.md "Reachability check", FR-011).
- [ ] T004 [US1] In the same `verify-e2e` job in `.github/workflows/auto-release.yml`, add a "close prior leftovers" step: using the scoped token, list and close any open issue and any open PR on the test repository (`gh issue list`/`gh pr list --repo "$E2E_REPO" --state open`) before the reset below — an orphan-reset default branch otherwise leaves a stale open PR pointing at history that no longer exists (research.md D6's consequence, contracts/e2e-repository-wiring.md step 2).
- [ ] T005 [US1] In the same job, add a "reset default branch" step reusing `auto-update-spec-kit.yml`'s orphan-branch force-reset git sequence (detach, delete local branch, `checkout --orphan`, remove tracked files, recreate) applied to the test repository's **default** branch itself, not a side branch (research.md D6/D7) — push with `git push --force` over a tokenized URL built from the scoped token, never `gh repo clone`/`gh auth setup-git` (research.md D7).
- [ ] T006 [US1] In the same job, add a "scaffold fixture" step: push `specify init` output pinned at this repository's own `SPECKIT_SUPPORTED_VERSION` (`.github/actions/wing-commander-preflight/action.yml`), plus the minimal wrapper set `docs/adoption.md` documents (`wing-commander-1-intake.yml` through `wing-commander-7-cleanup.yml`, plus `wing-commander-rebase.yml`), each `uses:` line rewritten to `charlesguse/wing-commander/.github/workflows/<stage>.yml@${{ needs.detect.outputs.head-sha }}` — the exact unreleased commit, never `@main` or a tag (research.md D7) — as one commit `chore: scaffold end-to-end verification fixture at <short-sha>`, force-pushed with the scoped token.
- [ ] T007 [US1] In the same job, add a "kick off trivial feature" pair of steps: `gh issue create --repo "$E2E_REPO"` with **no** `--label` flag, using the fixed, deterministic trivial-feature body from research.md D9 (e.g., "add a single new markdown file under `docs/` stating the verified commit and timestamp"), followed by a separate `gh issue edit <n> --repo "$E2E_REPO" --add-label spec-request` call — splitting creation and labeling is required for a genuine `labeled` event to fire (research.md D8, contracts/e2e-repository-wiring.md step 5).
- [ ] T008 [US1] In the same job, add a "poll to verdict" step: poll `gh issue view <n> --repo "$E2E_REPO" --json state,labels` on an interval, bounded by the job's own `timeout-minutes` (T003). On `state: CLOSED` with label `stage:done`, assert every intermediate `stage:{spec,clarify,plan,tasks,implement,review}` label appears somewhere in the issue's timeline (`gh api repos/$E2E_REPO/issues/<n>/timeline`) and that `spec.md`/`plan.md`/`tasks.md` are present in the merged implementation PR's tree (`gh api repos/$E2E_REPO/contents/specs/<slug>/...`); when every assertion holds, set the job's `verdict` output to the `pass` shape from data-model.md ("End-to-end verdict") with `outcome: pass`, `verified_head` = `needs.detect.outputs.head-sha`, `failing_check`/`expected`/`observed` all `null`. (research.md D10; the fail-* branches of this same step are T012, User Story 2.)
- [ ] T009 [US1] In `.github/workflows/auto-release.yml`, add the `decide-version` job (`needs: [detect, verify-e2e]`, `if:` the parsed `verdict.outcome == 'pass'` from `verify-e2e`'s output): enumerate merge commits with `git log <latest-tag>..<head_sha> --merges --format=%H`, extract each merged PR number from its merge/squash commit message (`Merge pull request #NNN` or the `(#NNN)` squash suffix — research.md D5), `gh pr view NNN --json labels` each and check for the fixed label `release:minor`; set `bump` to `minor` if any hit, else `patch` (FR-017/FR-017a/FR-017b — never a third value). Compute `next-version` by incrementing `latest-tag` on the minor or patch component only, never the major (FR-018). Compute `collision` via `git rev-parse -q --verify refs/tags/<next-version>` (data-model.md "Version decision"). Emit `next-version` and `collision` job outputs.
- [ ] T010 [US1] In `.github/workflows/auto-release.yml`, add the `dispatch-release` job (`needs: decide-version`, `if: needs.decide-version.outputs.collision == 'false'`, `permissions: { actions: write, contents: read }`): run `gh workflow run release.yml -f version=${{ needs.decide-version.outputs.next-version }} -f breaking=false -f breaking-notes=` with `GH_TOKEN: ${{ github.token }}` — the default `GITHUB_TOKEN`, never the wing-commander App token (research.md D12, the documented Gate 12 / issue #005 incident against the App token here). Then poll `gh run list --workflow=release.yml -b main --json databaseId,status,conclusion -L 1` and `gh run watch <id>` (or an equivalent poll) to that run's conclusion; emit `release-outcome` = `released` on `success`, else `failed` (FR-029 — `gh workflow run`'s own success only means the dispatch was accepted).
- [ ] T011 [US1] In `.github/workflows/auto-release.yml`, add the `report` job (`if: always()`, `needs: [detect, verify-e2e, decide-version, dispatch-release]`, reading whichever prior jobs actually ran): on `dispatch-release.outputs.release-outcome == 'released'`, write a `$GITHUB_STEP_SUMMARY` line `released ${{ needs.decide-version.outputs.next-version }}` (FR-030, contracts/release-dispatch.md Reporting).

**Checkpoint**: User Story 1 is fully functional and independently
testable — dispatch `auto-release.yml` against a merged trivial change and
confirm `release.yml` cuts the version this feature computed (quickstart.md
Scenario 2).

---

## Phase 4: User Story 2 - A failing end-to-end run blocks the release and says exactly what broke (Priority: P1)

**Goal**: Every non-pass outcome (verification failure, release-dispatch
failure, version collision) blocks the release, leaves the tag untouched,
and is reported in one durable, deduplicated issue naming what happened.

**Independent Test**: Force the end-to-end run to fail in a controlled way
and confirm zero tags/releases are created, the latest tag is
byte-identical to before, and a report alone — without opening run logs —
names the failing check and expected-vs-observed (spec.md User Story 2
Independent Test; quickstart.md Scenario 4).

### Implementation for User Story 2

- [ ] T012 [US2] In `.github/workflows/auto-release.yml`'s `verify-e2e` "poll to verdict" step (T008), add the remaining classifications from data-model.md "End-to-end verdict": `fail-timeout` when the poll never reaches a terminal state before `timeout-minutes` elapses (FR-012 "did not complete"); `fail-incomplete` when the issue reaches a terminal-but-not-done state (`stage:stalled`, or closed without `stage:done` — the `teardown-rejected` path) before timeout; `fail-wrong-output` when the terminal state is `stage:done` but an asserted artifact or intermediate `stage:*` label is missing (FR-012 "completed and produced the wrong output"). Each sets `failing_check`/`expected`/`observed` naming exactly what was checked (research.md D10).
- [ ] T013 [US2] In `.github/workflows/auto-release.yml`'s `report` job (T011), add the fail-* verdict path: on any `verify-e2e.outputs.verdict.outcome` other than `pass`, `gh issue list --label auto-release:failed --state open` on this repository; if one exists, append a comment naming the verified head, the failing check, and expected-vs-observed; if none, `gh issue create --label auto-release:failed --title "Auto-release verification failed at <short-sha>"` with that same body, classified as **infrastructure** (`fail-infra`) or **pipeline defect** (every other `fail-*` outcome) per FR-026/data-model.md "Failure report".
- [ ] T014 [US2] In the same `report` job, add the release-dispatch-failure path: on `dispatch-release.outputs.release-outcome == 'failed'`, file-or-update the same `auto-release:failed` issue (same dedup-by-label lookup as T013) with wording that distinguishes a **release failure** (the dispatched `release.yml` itself failed its own gates or tag creation) from a verification failure (FR-029).
- [ ] T015 [US2] In the same `report` job, add the version-collision path: on `decide-version.outputs.collision == 'true'`, write the `$GITHUB_STEP_SUMMARY` line `version collision: <next-version> already tagged` and file-or-update the same durable `auto-release:failed` issue naming the collision as its own distinct outcome — not a verification failure, not a release failure (FR-024, contracts/release-dispatch.md Reporting).
- [ ] T016 [US2] In the same `report` job, add the close-on-success path: on `dispatch-release.outputs.release-outcome == 'released'`, look up any open `auto-release:failed` issue (same `gh issue list --label auto-release:failed --state open` as T013) and close it with a comment naming the version that just shipped (data-model.md "Failure report", FR-028's dedup mirrored on resolution).

**Checkpoint**: User Stories 1 and 2 both work — a forced failure produces
zero tag/release changes and one legible, deduplicated issue; a subsequent
pass closes it (quickstart.md Scenario 4).

---

## Phase 5: User Story 3 - Nothing new on main costs nothing (Priority: P2)

**Goal**: When there is no new work (or no baseline tag at all), the run
ends legibly with zero agent invocations and zero writes — the mechanism
(Phase 2's `has-new-work`/`tag-exists` outputs gating every downstream
job's `if:`) already exists; this story finishes its user-facing half.

**Independent Test**: With main at exactly the latest release tag, run the
scheduled check and confirm it completes having invoked no agent, touched
no test repository, and created nothing, with the reason legible in the
run's own summary (spec.md User Story 3 Independent Test; quickstart.md
Scenario 1).

### Implementation for User Story 3

- [ ] T017 [US3] In `.github/workflows/auto-release.yml`'s `report` job (T011), add the no-new-work path: when `detect.outputs.has-new-work == 'false'` and `detect.outputs.tag-exists == 'true'`, write the `$GITHUB_STEP_SUMMARY` line `no new work since ${{ needs.detect.outputs.latest-tag }}` (FR-030, FR-003).
- [ ] T018 [US3] In the same `report` job, add the no-baseline path: when `detect.outputs.tag-exists == 'false'`, write a `$GITHUB_STEP_SUMMARY` line stating there is no release tag to compare against and nothing was cut, distinct in wording from T017's line (FR-004, FR-030).

**Checkpoint**: All three of Stories 1-3 work together — a no-op tick's
summary reads `no new work since <tag>` (or the no-baseline line) with
`verify-e2e`, `decide-version`, and `dispatch-release` all skipped in the
Actions UI (quickstart.md Scenario 1).

---

## Phase 6: User Story 4 - Breaking releases stay a deliberate human act (Priority: P2)

**Goal**: The automatic path is mechanically incapable of requesting a
breaking or major release — confirmed in the code already written by
Phase 3, not a new capability.

**Independent Test**: Confirm the automatic path has no way to request a
breaking release — the dispatched release is always non-breaking, and no
input path exists by which the scheduled run could set it otherwise
(spec.md User Story 4 Independent Test; quickstart.md Scenario 6).

### Implementation for User Story 4

- [ ] T019 [US4] In `.github/workflows/auto-release.yml`'s `dispatch-release` job (T010), confirm `-f breaking=false -f breaking-notes=` are literal, hardcoded values in the `gh workflow run` invocation — not read from any variable, label, or job output — and that no other step in the file sets or overrides them (FR-018/FR-019). If T010 was written any other way, fix it here.
- [ ] T020 [US4] In `.github/workflows/auto-release.yml`'s `decide-version` job (T009), confirm the `bump` computation has exactly two possible values (`patch`, `minor`) with no branch that can produce `major`, and that `next-version`'s increment never touches the major component (FR-018). If T009 was written any other way, fix it here.

**Checkpoint**: All four of Stories 1-4 hold — inspecting `dispatch-release`
and `decide-version` shows no code path, input, or label that produces a
breaking or major release (quickstart.md Scenario 6, by inspection).

---

## Phase 7: User Story 5 - A maintainer can pause the whole thing (Priority: P3)

**Goal**: A repository variable stops every job in the workflow from
starting at all.

**Independent Test**: Set the pause variable, run the scheduled check, and
confirm no job starts at all; clear it and confirm the next check behaves
normally (spec.md User Story 5 Independent Test; quickstart.md Scenario 5).

### Implementation for User Story 5

- [ ] T021 [US5] In `.github/workflows/auto-release.yml`, add `if: vars.WING_COMMANDER_AUTO_RELEASE_PAUSED != 'true'` to the `detect` job (T002) as a standalone condition, and AND it into the existing `if:` expression on `verify-e2e` (T003), `decide-version` (T009), and `dispatch-release` (T010); on the `report` job (T011) the combined condition becomes `if: always() && vars.WING_COMMANDER_AUTO_RELEASE_PAUSED != 'true'` so a paused repository still reports nothing rather than reporting a stale prior run (research.md D2, contracts/auto-release-workflow.md Kill switch, FR-006/SC-009). This is job-level, not a step-side write-suppression shim — the watchdog's own documented lesson (research.md D2) is that a stage-side-only check still bills for the jobs before it.

**Checkpoint**: All five user stories are independently functional — with
`WING_COMMANDER_AUTO_RELEASE_PAUSED` set, every job in the run shows
skipped in the Actions UI itself (quickstart.md Scenario 5).

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T022 [P] In `docs/setup.md`'s repository variable table (§3), add rows for `WING_COMMANDER_AUTO_RELEASE_PAUSED` (unset = not paused; `true` = kill switch, read job-level in `auto-release.yml` per T021 so no job starts at all) and `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` (unset; `OWNER/NAME` of the pre-created, maintainer-owned end-to-end test repository, same convention as `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_SCRATCH_REPO`), placed alongside the existing watchdog/auto-updater pause-switch rows and the auto-updater's scratch-repo row (plan.md Project Structure).
- [ ] T023 In `.github/workflows/release.yml`'s Gate 1a pass-2 closure check (~line 128-143), record the deliberate choice research.md D15 flags: `auto-release.yml` declares no `workflow_call`, so `wc_published_stages.py` does not derive it as a published stage and the closure check does not force it into either array — but given its shell (dynamic git/gh tag and PR-label parsing, an orphan-branch reset sequence, a polling loop) is the same shape as `watchdog.yml`/`auto-update-spec-kit.yml`/`pr-conversation.yml`, add `.github/workflows/auto-release.yml` to the `shell_exempt` array with a one-line comment giving the reason, rather than adding it to `shell_linted` untested in a release-blocking gate.
- [ ] T024 Run the `review-step-gating` skill (CLAUDE.md) against the finished `.github/workflows/auto-release.yml`, given the number of gated (`if:`) steps this design implies (pause check, no-op early exit, infra-unreachable early exit, timeout branch, dispatch-failure branch, version-collision branch — research.md D15) — fix any findings before the feature is considered done.
- [ ] T025 Run `python .github/scripts/run-local-gates.py` from the repository root and confirm it stays green with `.github/workflows/auto-release.yml` and the T023 `release.yml` change in place.
- [ ] T026 Manually validate quickstart.md's six scenarios (no-op, passing release, minor label, failing verification, kill switch, breaking-stays-manual) against a real onboarded end-to-end test repository. **Not completable by an unattended implementation session**: each scenario needs a live `gh workflow run`/`gh run watch`-style dispatch against GitHub Actions and a real maintainer-onboarded test repository, which this pipeline's own implement stage has no tool access to drive — flag this task for a human or a follow-up run with dispatch access, the same posture spec 043's tasks.md recorded for its own end-to-end validation task.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no tasks — proceed directly to Phase 2.
- **Foundational (Phase 2)**: T001-T002 must complete before any user story — every downstream job reads `detect`'s outputs.
- **User Story 1 (Phase 3)**: depends only on Foundational. T003-T011 are sequential (one file, one job built after another, each `needs:` the previous).
- **User Story 2 (Phase 4)**: depends on User Story 1 existing — T012 extends T008's same step; T013-T016 extend T011's same `report` job.
- **User Story 3 (Phase 5)**: depends on User Story 1 (T017-T018 extend T011's `report` job) — the underlying `has-new-work`/`tag-exists` gating it narrates is Foundational, already load-bearing since T003.
- **User Story 4 (Phase 6)**: depends on User Story 1 — T019 confirms/fixes T010, T020 confirms/fixes T009. No new job.
- **User Story 5 (Phase 7)**: depends on Stories 1-3's jobs existing (T021 amends every job's `if:`) — do this last among the workflow-file edits so no earlier task's `if:` needs rewriting twice.
- **Polish (Phase 8)**: depends on all five stories being complete; T023-T025 need the finished file's actual shell (research.md D15 explicitly defers the shell_exempt/shell_linted choice until then).

### Parallel Opportunities

- T001-T021 are effectively sequential — one workflow file, jobs building on each other's outputs. None are marked [P].
- T022 (`docs/setup.md`) and T023 (`release.yml`) touch different files from `auto-release.yml` and from each other, but both are documentation/registration steps best done after T001-T021 land, so they are listed sequentially rather than marked [P] to avoid implying they can start before the shell they describe exists.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 2 (T001-T002): trigger, gating shell, and the one shared
   detection read.
2. Complete Phase 3 (T003-T011): the full happy path exists.
3. **STOP and VALIDATE**: quickstart.md Scenario 2 — merge a trivial
   change, dispatch manually, confirm `release.yml` cuts the computed
   version at the verified head.
4. This alone is deployable in the sense the spec describes User Story 1:
   "detect, verify, dispatch" removes the manual step, even before failure
   reporting (Story 2), the no-op narration (Story 3), the Story 4
   inspection tasks, or the kill switch (Story 5) are layered on.

### Incremental Delivery

1. Foundational (Phase 2) → the shared detection read exists.
2. Story 1 (Phase 3) → a passing run cuts a release automatically.
3. Story 2 (Phase 4) → a failing run blocks the release and reports why,
   deduplicated.
4. Story 3 (Phase 5) → the no-op path's reasoning is legible without
   opening logs.
5. Story 4 (Phase 6) → inspection confirms no breaking/major path exists.
6. Story 5 (Phase 7) → the kill switch stops every job from starting.
7. Phase 8 → gate-suite registration, the `review-step-gating` pass, and
   manual end-to-end validation.

### Parallel Team Strategy

Given this is one workflow file built job-by-job, splitting Phase 3 across
multiple implementers would create same-file merge conflicts; one
implementer should take T001-T021 in order. Phase 8's T022 (docs) and T023
(release.yml) can be picked up by a second person once T001-T021 land,
since neither touches `auto-release.yml` itself.

---

## Notes

- [P] tasks = different files, no dependencies. Given this feature's
  single-workflow-file shape, most tasks here are intentionally
  unmarked — sequential edits to the same file, same job, or a job
  reading a previous job's outputs.
- [Story] label maps task to specific user story for traceability.
- Every task above names its exact file path and, where it extends a
  named step from an earlier task, which task and step it extends.
- Commit after each phase (or logical group within Phase 3) and re-run
  `python .github/scripts/run-local-gates.py`; stop at any checkpoint to
  validate a story independently per its quickstart.md scenario.
- Avoid: vague tasks, same-file conflicts run in parallel, and treating
  Phase 8's T023/T024 as skippable — CLAUDE.md requires both a gate
  suite pass and a `review-step-gating` pass before any change touching
  this many gated `if:` steps is pushed.
