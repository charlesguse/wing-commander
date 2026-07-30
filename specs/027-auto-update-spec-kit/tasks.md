---

description: "Task list for Auto-Update Spec Kit"
---

# Tasks: Auto-Update Spec Kit

**Input**: Design documents from `/specs/027-auto-update-spec-kit/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/auto-update-spec-kit-workflow.md, quickstart.md

**Tests**: Not requested — no automated test suite exists for any pipeline stage in this repository (plan.md's Testing section, matching `015-pipeline-watchdog/plan.md`'s same finding). Validation is manual, via `quickstart.md`'s fifteen scenarios, folded into each user-story phase's checkpoint and the Polish phase below.

**Organization**: This feature's total footprint is two new workflow files — `.github/workflows/auto-update-spec-kit.yml` (the reusable stage: `health-check` → `detect` → `settle` → `evaluate-path` → `prepare` → `verify` → `act`, plus `pr-merged` and `comment-reply` entry jobs) and its wrapper `.github/workflows/wing-commander-auto-update-spec-kit.yml` — no new `.specify/memory/*.json` config file (research.md's two "no new ledger" decisions). Because nearly every task edits `auto-update-spec-kit.yml`, `[P]` is used sparingly — only for tasks touching genuinely different files (the wrapper, and the Polish-phase docs).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature, no `src/`/`tests/` split (plan.md's Structure Decision). All file paths below are repo-root-relative.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the two new workflow files as correctly-wired skeletons — the scaffold every story's logic attaches to.

- [X] T001 Create `.github/workflows/auto-update-spec-kit.yml` as a `workflow_call`-only reusable stage skeleton (contracts/auto-update-spec-kit-workflow.md's Job contract): typed inputs `trigger` (required: `scheduled`\|`dispatch`\|`pr-merged`\|`comment-reply`), `pr-number`, `pr-merged`, `issue-number`, `comment-id`, `commenter-association`, `commenter-id`, `issue-author-id`, `stabilization-checks`, `model`; secrets `claude-code-oauth-token`, `anthropic-api-key`, `speckit-app-id`, `speckit-app-private-key`; top-level `permissions:` (`contents: write`, `issues: write`, `pull-requests: write`, `id-token: write`); `concurrency: { group: wing-commander-auto-update-spec-kit, cancel-in-progress: false }` (FR-015 — one active upgrade cycle at a time); nine empty job skeletons in dependency order — `health-check` (`if: inputs.trigger == 'scheduled' || inputs.trigger == 'dispatch'`), `detect` (`needs: health-check`), `settle` (`needs: detect`), `evaluate-path` (`needs: settle`), `prepare` (`needs: evaluate-path`), `verify` (`needs: prepare`), `act` (`needs: verify`), `pr-merged` (`if: inputs.trigger == 'pr-merged'`), `comment-reply` (`if: inputs.trigger == 'comment-reply'`) — each `runs-on: ubuntu-latest`.
- [X] T002 Create `.github/workflows/wing-commander-auto-update-spec-kit.yml` as the thin wrapper, matching contracts/auto-update-spec-kit-workflow.md's Trigger contract verbatim: `on.schedule` (`cron: "13 7 * * *"`), `on.workflow_dispatch: {}`, `on.pull_request.types: [closed]`, `on.issue_comment.types: [created]`; job-level `if: vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_PAUSED != 'true'` (the pause kill-switch, checked in the wrapper per `wing-commander-8-watchdog.yml`'s own corrected shape — never in the stage); permissions matching T001; calls `./.github/workflows/auto-update-spec-kit.yml` (`uses:` local path) resolving the typed `trigger` input from `github.event_name` plus `pr-number`/`pr-merged`/`issue-number`/`comment-id`/`commenter-association`/`commenter-id`/`issue-author-id` from `github.event.*`, `stabilization-checks` from `vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_STABILIZATION_CHECKS || '1'`, `model` from `vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_MODEL || 'claude-sonnet-5'`; secrets passthrough (`CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY`, `WING_COMMANDER_APP_ID`, `WING_COMMANDER_APP_PRIVATE_KEY`).

**Checkpoint**: Both workflow files parse and are wired end-to-end with empty job bodies — ready for Foundational steps.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Give the entry jobs the common boilerplate every job needs, implement the shared lightweight-verification logic both `health-check` and `verify` depend on, and wire the self-recognition guards and cross-job `needs`/`if:` graph the contract requires.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 In `.github/workflows/auto-update-spec-kit.yml`, add the bootstrap opener (preflight via `./.github/actions/wing-commander-preflight`, `actions/checkout@v4` with `persist-credentials: false`, `./.github/actions/wing-commander-context` for App-token auth — the same self-checkout dance every other stage performs) to the `health-check` job (the entry point for `scheduled`/`dispatch`) and to the `pr-merged` and `comment-reply` jobs (the entry points for their own triggers).
- [X] T004 Implement the shared lightweight-verification logic (FR-004's always-run tier, research.md's "no reusable smoke test exists yet" decision) as a step usable by both `health-check` (against the version currently pinned in `.specify/init-options.json` on `main`) and `verify` (against `prepare`'s candidate branch): in an isolated temporary worktree/checkout (never the real working tree), install the target version's `.specify/` artifacts using `.specify/init-options.json`'s existing recorded flags (`ai: claude`, `script: sh`, `ai_skills: true`) re-applied at the target version, then run `.specify/scripts/bash/check-prerequisites.sh` and `create-new-feature.sh --json` against a throwaway feature name and assert both exit `0` and produce the documented JSON shape; emit `{tier, lightweight.passed, end_to_end.passed, failure_detail}` per data-model.md's Verification result shape (`end_to_end.passed: null` for this step alone — Phase 3 adds the end-to-end tier).
- [X] T005 In `.github/workflows/auto-update-spec-kit.yml`, implement the self-recognition no-op guards (contract's Self-recognition contract): the `pr-merged` job's `if:` additionally requires the closed PR's body to contain `<!-- wing-commander-auto-update-spec-kit: version-bump -->` or `: revert` (via `gh pr view <pr-number> --json body`); the `comment-reply` job's `if:` additionally requires the commented-on issue's body to contain the settle-tracking marker `<!-- wing-commander-auto-update-spec-kit: candidate=` (via `gh issue view <issue-number> --json body`) — either guard failing exits the job immediately without writing anything, never assuming any other PR/issue in the repository belongs to this feature.
- [X] T006 Wire the remaining cross-job `needs`/`if:` graph in `.github/workflows/auto-update-spec-kit.yml` per contracts/auto-update-spec-kit-workflow.md: `health-check` failing sets a job output (e.g. `pinned-ok: false`) that routes `act` directly to its rollback branch and short-circuits `detect`/`settle`/`evaluate-path`/`prepare`/`verify` entirely for that run (`if: needs.health-check.outputs.pinned-ok == 'false'` on `act`, `if: needs.health-check.outputs.pinned-ok != 'false'` on `detect`); `evaluate-path` runs both when `settle` reports `settled` and when `comment-reply` (T005-guarded) reports a recognized maintainer choice, in both cases re-entering the same `prepare` → `verify` → `act` chain.

**Checkpoint**: Bootstrap, shared verification logic, self-recognition guards, and the job-skip/re-entry graph are wired — user story work can begin.

---

## Phase 3: User Story 1 - A newly released Spec Kit version is adopted automatically when it passes verification (Priority: P1) 🎯 MVP

**Goal**: The pipeline detects an eligible newer upstream Spec Kit release, waits for it to settle, evaluates the upgrade path, verifies it works, and opens a reviewable version-bump PR — with zero human action before review.

**Independent Test**: Simulate a new eligible upstream release, let the process run, and confirm it produces a lifecycle issue describing the detected version and a pull request bumping the pinned version, only after verification passes — `quickstart.md` Scenarios 1, 2, 3, 4, 5, 7, 14.

### Implementation for User Story 1

- [X] T007 [US1] In the `detect` job of `.github/workflows/auto-update-spec-kit.yml`, implement release discovery: `gh api repos/github/spec-kit/releases --paginate`, filter `prerelease == false` (spec's Assumptions — pre-releases out of scope), semver-sort, take the highest as `latest_upstream`; compare against the pinned `speckit_version` in `.specify/init-options.json`. Not newer → record "up to date" in the job summary, no issue, no PR (SC-007), workflow ends here (Scenario 1). Newer → compute `release_type` (`patch`\|`minor`\|`major`) from the semver delta, continue to `settle`.
- [X] T008 [US1] In the `settle` job, implement the core settle-tracking state machine (data-model.md's Settle-tracking marker, research.md's decision): `gh search issues --repo "$GITHUB_REPOSITORY" "\"wing-commander-auto-update-spec-kit:\" in:body" --json number,state,body` (quoted-phrase, no `--state`). Zero results → create a new open lifecycle issue with marker `<!-- wing-commander-auto-update-spec-kit: candidate=X.Y.Z observed=1 -->`, comment the detected version + release type + "waiting for the patch stream to settle," stop (Scenario 2). One open result with the same `candidate` and `observed < inputs.stabilization-checks` → increment `observed`, stop (Scenario 3, first half). One open result with the same `candidate` and `observed >= inputs.stabilization-checks` → "settled," continue to `evaluate-path` (Scenario 3, second half).
- [X] T009 [US1] In the `settle` job, implement the superseded-candidate branch (Edge Case, Scenario 4): one open result whose `candidate` differs from today's `latest_upstream` → update the marker to the new candidate, reset `observed=1`, comment explaining the supersession and why (FR-013), stop — no adoption happens this cycle.
- [X] T010 [US1] In the `settle` job, implement the remaining guard branches (FR-015, Scenario 11): one open result already marked `awaiting-decision=true` (US4's question state) → left untouched, at most a "still waiting" comment if the target changed underneath it; more than one open result carrying the marker → report as a data-integrity condition (never auto-resolved, mirroring `watchdog.yml`'s identical handling of its own dedup search), stop.
- [X] T011 [US1] Implement the `evaluate-path` job's `clean-bump` outcome (this task covers only that outcome — Phase 6/US4 adds `needs-migration` and `ambiguous-options`): `anthropics/claude-code-action@v1`, `model: ${{ inputs.model }}`, bounded `--max-turns`, `--allowedTools "Read,Grep,Bash(gh api:*),Bash(git diff:*)"`, `--disallowedTools "WebSearch,WebFetch,Write,Edit,Bash(git commit:*),Bash(git push:*)"`, structured output via `--json-schema` matching data-model.md's Upgrade decision record shape (`outcome`, `reasoning`, `sources`, `options`, `chosen_option`); prompt explicitly frames every fetched release-notes body (`gh api`, never live-browsed) as untrusted data, never instructions (constitution V); `clean-bump` → continue to `prepare`, recording reasoning + sources on the issue regardless of outcome (FR-013, Scenario 14).
- [X] T012 [US1] Implement the `prepare` job: deterministic — on a fresh branch, write the version-bump diff (`.specify/init-options.json`'s `speckit_version` and `wing-commander-preflight`'s `SPECKIT_SUPPORTED_VERSION` constant to the verified candidate version, plus whatever the candidate's own `.specify/` artifact regeneration produces for a clean bump); materialize the diff locally — no `git push` yet, so `verify` can validate it first.
- [X] T013 [US1] Implement the `verify` job's candidate path (`needs: prepare`): run T004's shared lightweight-verification step against the prepared branch (always); additionally, when `release_type != patch`, run the end-to-end tier — generate one disposable spec via the equivalent of the `/speckit-specify` flow in the same isolated worktree, assert the expected files land, then discard entirely (never committed, never touches the real `specs/` tree, never opens a real lifecycle issue) — output pass/fail + `failure_detail` per data-model.md's Verification result shape (Scenario 7's tiering).
- [X] T014 [US1] Implement the `act` job's pass path (this task covers only the success branch — Phase 4/US2 adds the failure branch): `git push` the prepared branch, open a version-bump PR (title `chore: bump Spec Kit to vX.Y.Z`; body states what was verified, `evaluate-path`'s reasoning + sources, and `Closes #<lifecycle-issue-number>`; PR body carries marker `<!-- wing-commander-auto-update-spec-kit: version-bump -->`), comment the PR link on the lifecycle issue — this feature never merges the PR itself (constitution V, FR-017, Scenario 5).

**Checkpoint**: User Story 1 is fully functional — `quickstart.md` Scenarios 1, 2, 3, 4, 5, 7, and 14 pass independently.

---

## Phase 4: User Story 2 - A broken upgrade is blocked or rolled back automatically and flagged for a human (Priority: P1)

**Goal**: A candidate that fails verification is never adopted; a regression discovered in an already-adopted version is automatically rolled back; either way a flagged lifecycle issue explains what happened.

**Independent Test**: Simulate an upstream release that fails verification, let the process run, and confirm the pinned version stays at (or returns to) the last known working version and a flagged lifecycle issue is raised — `quickstart.md` Scenarios 6, 8, 10.

### Implementation for User Story 2

- [X] T015 [US2] Implement the `health-check` job: for `trigger in [scheduled, dispatch]`, run T004's shared lightweight-verification step against the version currently pinned in `.specify/init-options.json` on `main`. Passes → set `pinned-ok: true`, continue to `detect` (T006's wiring). Fails → set `pinned-ok: false`, skip straight to `act`'s rollback branch this cycle (Scenario 8, step 1).
- [X] T016 [US2] Implement the `act` job's rollback path (from `health-check`'s failure, T006's `if:`): compute the prior pinned value via `git log -p -- .specify/init-options.json`, walking backward from HEAD to the most recent commit that changed `speckit_version` and reading the diff's removed line as the rollback target (research.md — no separate ledger); open a revert PR (title `revert: Spec Kit vX.Y.Z regression — restore vA.B.C`, marker `<!-- wing-commander-auto-update-spec-kit: revert -->`, no `Closes` keyword); open or reuse a flagged `auto-update:failed`-labeled issue explaining what the health check found and which version is now proposed as pinned again; comment the PR link there; workflow ends (Scenario 8, SC-004 — the issue text alone states which version failed, which is proposed, and what was detected).
- [X] T017 [US2] Implement the `verify` job's fail path and the `act` job's corresponding branch: on any verification failure (lightweight or, for minor/major, end-to-end), leave `.specify/init-options.json` unchanged (never push the prepared branch), comment `failure_detail` on the lifecycle issue via `wing-commander-callout` (`kind: info`), add the `auto-update:failed` label, leave the issue open (Scenario 6, FR-006/FR-010).
- [X] T018 [US2] Implement the shared label-creation step used by T016 and T017: `gh label create "auto-update:failed" --color E99695 --description "Spec Kit upgrade blocked or rolled back; needs maintainer attention" --force`, matching the existing `stage:stalled`/`rebase:blocked` flag-label convention — idempotent, safe to call every time (Scenario 10).

**Checkpoint**: User Stories 1 AND 2 both work independently — `quickstart.md` Scenarios 1–8, 10, 14 pass.

---

## Phase 5: User Story 3 - The lifecycle issue self-manages its state as the upgrade succeeds or fails (Priority: P2)

**Goal**: The lifecycle issue narrates the attempt as it progresses, closes itself on a successful merge, and stays open and flagged on failure — readable end-to-end without run logs.

**Independent Test**: Run one successful upgrade and one failing upgrade and confirm the successful run's issue ends closed while the failing run's ends open and flagged, each with a summary — `quickstart.md` Scenarios 9, 10.

### Implementation for User Story 3

- [ ] T019 [US3] Implement the `pr-merged` job (`trigger == 'pr-merged'`, `inputs.pr-merged == 'true'`, T005's marker guard passed): for a `version-bump`-marked PR, post one rich summary comment (adopted version, what was verified) to the lifecycle issue referenced by the PR's `Closes #N` — the issue is already closed by GitHub's own keyword-on-merge mechanism by the time this job runs (Scenario 9); for a `revert`-marked PR, post the equivalent summary to the still-open, still-flagged issue (no auto-close — a rollback is itself the failure outcome FR-010 wants visible). A PR closed without merging (`inputs.pr-merged == 'false'`) is a no-op — nothing to record.
- [ ] T020 [US3] Confirm (extending T012/T014) that the version-bump PR body's `Closes #<lifecycle-issue-number>` line is the *only* mechanism that closes the issue on the success path — the workflow never calls `gh issue close` directly, avoiding a race with a human closing it manually (research.md's rationale).
- [ ] T021 [US3] Desk-check every comment posted across `settle`/`evaluate-path`/`verify`/`act`/`pr-merged` (T007–T019) uses `wing-commander-callout` with `kind: action` only for the FR-012 question (T023) and `kind: info` for all routine narration, and that the `auto-update:failed` label (T018) is the sole visible flag mechanism — no busy label exists for the routine success path (SC-004).

**Checkpoint**: User Stories 1, 2, AND 3 all work independently — `quickstart.md` Scenarios 1–10, 14 pass.

---

## Phase 6: User Story 4 - Upgrade-path options are decided automatically when clear, or surfaced as questions when not (Priority: P2)

**Goal**: A clean upgrade path proceeds with recorded reasoning; a path needing more than a version bump routes to a human; genuinely ambiguous upstream options are posted as a question and resumed only from a verified maintainer's reply.

**Independent Test**: Present an upgrade with one clearly superior path and confirm it proceeds while recording reasoning; present one with genuinely ambiguous options and confirm it posts questions instead of choosing silently — `quickstart.md` Scenarios 12, 13, 14, 15.

### Implementation for User Story 4

- [ ] T022 [US4] Extend the `evaluate-path` job (T011) with the `needs-migration` outcome (FR-018): comment the reasoning + sources on the issue via `wing-commander-callout` (`kind: info`), apply no diff anywhere, workflow ends — never continues to `prepare`.
- [ ] T023 [US4] Extend the `evaluate-path` job with the `ambiguous-options` outcome (FR-012, SC-005, Scenario 12): post the options + reasoning + sources as a question via `wing-commander-callout` (`kind: action`), set the issue marker's `awaiting-decision=true` flag, workflow ends, awaiting a comment reply — no PR opens, no version is adopted, the issue is not closed.
- [ ] T024 [US4] Implement the `comment-reply` job's commenter-verification step (Scenario 13, constitution V): `contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), inputs.commenter-association) || inputs.commenter-id == inputs.issue-author-id` — the exact condition `wing-commander-2-clarify.yml` already uses. Fails → no-op: no comment, no error surfaced, silently ignored.
- [ ] T025 [US4] Implement the `comment-reply` job's question-state guard: the issue must carry the settle-tracking marker's `awaiting-decision=true` sub-marker (set by T023) — otherwise no-op (in addition to T005's marker-presence guard).
- [ ] T026 [US4] Implement the `comment-reply` job's interpretation step: `claude-haiku-4-5`, bounded `--max-turns`, read-only `--allowedTools "Read"`, structured output mapping the comment body onto one of the previously posted options, or `"unrecognized"` — the comment body is framed as untrusted data throughout (constitution V, Scenario 15). `"unrecognized"` → comment asking for a clearer reply, take no further action.
- [ ] T027 [US4] Implement the `comment-reply` job's resume step: a recognized choice → comment the human's decision (and whose call it was, per FR-013) on the issue, clear the `awaiting-decision` flag, then re-enter `prepare` (T012) → `verify` (T013) → `act` (T014/T016/T017) with the chosen path exactly as the `clean-bump` path would (T006's re-entry wiring).

**Checkpoint**: All four user stories are independently functional — the full `quickstart.md` scenario set (1–15) passes.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation consistency and end-to-end validation across the whole feature.

- [ ] T028 [P] Add an "Auto-Update Spec Kit" section to `docs/architecture.md` documenting the job shape (`health-check` → `detect` → `settle` → `evaluate-path` → `prepare` → `verify` → `act`, plus `pr-merged`/`comment-reply`), the four triggers, the settle-window mechanic (consecutive daily observations, no calendar window), tiered verification (lightweight always, end-to-end for minor/major), the self-recognition marker convention, and the `Closes #N`/`auto-update:failed` outcome-recording split — placed alongside `Rebase`'s maintenance-workflow section (not the numbered stage list), following `Stage 9 — Watchdog`'s section format.
- [ ] T029 [P] Add `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_PAUSED` (unset/not-paused), `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_STABILIZATION_CHECKS` (default `1`), and `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_MODEL` (default `claude-sonnet-5`) to `docs/setup.md`'s repository-variables table, mirroring `WING_COMMANDER_WATCHDOG_PAUSED`/`_SELF_DISPATCH_CAP`'s row format.
- [ ] T030 [P] Add an `auto-update-spec-kit.yml` row to `specs/010-reusable-pipeline/contracts/stage-interfaces.md` (inputs: `trigger`, `pr-number`, `pr-merged`, `issue-number`, `comment-id`, `commenter-association`, `commenter-id`, `issue-author-id`, `stabilization-checks`, `model`; outputs/side effects: lifecycle-issue comment/label, version-bump/revert PR — never merged), mirroring the other stage rows including `watchdog.yml`'s.
- [ ] T031 Validate `.github/workflows/auto-update-spec-kit.yml` and `.github/workflows/wing-commander-auto-update-spec-kit.yml` end-to-end: YAML parses (e.g. `python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))"` or actionlint if available) and every embedded `run:` script passes `bash -n` (matching `lint-workflows.yml`'s CI checks); cross-check every job against `contracts/auto-update-spec-kit-workflow.md`'s trigger, job, and self-recognition contracts.
- [ ] T032 Walk `specs/027-auto-update-spec-kit/quickstart.md`'s full 15-scenario set end-to-end against the finished workflow files, recording in the PR body which were exercised live (scratch `workflow_dispatch` runs / a fork with a deliberately lowered pinned version) versus desk-checked only — including Scenario 15 (untrusted content never treated as instructions), which has no dedicated implementation task above since it is a property of T011/T026's prompt framing rather than a separate code path.
- [ ] T033 Surface research.md's flagged maintainer-confirmation item in the feature's PR body and the transmittal comment on issue #153 (rather than silently assuming it): whether upstream Spec Kit's CLI exposes a dedicated upgrade/update command distinct from re-running `specify init` (which determines T012's exact regeneration command), and whether Spec Kit's release history shows any past breaking upgrade that would justify a longer default for `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_STABILIZATION_CHECKS` than this plan's one-settled-check default.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 (job skeletons must exist before adding steps to them) — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational. No dependency on other stories.
- **User Story 2 (Phase 4)**: Depends on Foundational AND User Story 1 (T016's rollback path reuses T012's prepare/PR-opening shape conceptually; T017 extends T013/T014's verify/act jobs with the failure branch those tasks left as a stub).
- **User Story 3 (Phase 5)**: Depends on User Story 1 AND User Story 2 (T019 reacts to the PRs T014/T016 open; T020/T021 desk-check comment/label conventions T007–T018 already established).
- **User Story 4 (Phase 6)**: Depends on User Story 1 (T022/T023 extend T011's `evaluate-path` job) AND User Story 2 (T027's resume re-enters T012/T013/T016/T017's chain).
- **Polish (Phase 7)**: Depends on all prior phases.

### User Story Dependencies

- **User Story 1 (P1)**: Independently implementable and testable after Foundational — the only story with no dependency on another story's write paths.
- **User Story 2 (P1)**: Builds on User Story 1's `prepare`/`verify`/`act` jobs (extending them with the failure/rollback branches); independently testable once its own phase completes (Scenarios 6, 8, 10 don't require Phases 5–6).
- **User Story 3 (P2)**: Builds on User Story 1's PR-opening (T014) and User Story 2's rollback/failure paths (T016/T017) — its `pr-merged` job has nothing to react to until both exist.
- **User Story 4 (P2)**: Extends User Story 1's `evaluate-path` job (T011) with its other two outcomes, and its resume step re-enters User Story 2's failure-aware `prepare`/`verify`/`act` chain — sequenced last because it depends on both.

### Within Each Story

- `detect` before `settle` before `evaluate-path` before `prepare` before `verify` before `act` (US1's internal order, per `contracts/auto-update-spec-kit-workflow.md`'s job sequence).
- `health-check` before the rest of the chain, with its failure short-circuiting directly to `act`'s rollback branch (US2's T015 before T016; T006's wiring).
- Commenter verification before the question-state guard before interpretation before resume (US4's T024 before T025 before T026 before T027).

### Parallel Opportunities

- T001 (stage skeleton) and T002 (wrapper) touch different files, but T002's wrapper resolves inputs that must match T001's declared contract — sequence T001 before T002 for correctness even though they're technically different files (no `[P]`, matching `015-pipeline-watchdog/tasks.md`'s identical call on its own two-file Setup phase).
- Within Phases 2–6, almost every task edits the same `auto-update-spec-kit.yml` file (different jobs or different steps within a job) — treat as sequential, not `[P]`, per this feature's file-concentration.
- T028, T029, and T030 (Polish, three different doc files) are parallel-safe with each other and with T031/T032/T033.

---

## Parallel Example: Polish Documentation

```bash
# Launch together — three different doc files:
Task: "Add an 'Auto-Update Spec Kit' section to docs/architecture.md"
Task: "Add the three new repo variables to docs/setup.md"
Task: "Add an auto-update-spec-kit.yml row to specs/010-reusable-pipeline/contracts/stage-interfaces.md"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Run `quickstart.md` Scenarios 1, 2, 3, 4, 5, 7, 14 independently
5. This alone delivers SC-001 and SC-007 — a maintainer no longer needs to manually check for or apply Spec Kit updates on the happy path, though nothing yet guards against a broken candidate (User Story 2 is equally P1 and should not be left out of a real rollout — see below)

### Incremental Delivery

1. Setup + Foundational → scaffold ready
2. Add User Story 1 → validate Scenarios 1, 2, 3, 4, 5, 7, 14 → the routine adoption path works
3. Add User Story 2 → validate Scenarios 6, 8, 10 → the safety net that makes Story 1 safe to leave unattended (both P1 — ship together for any real deployment, per spec.md's own framing: "An auto-updater that can quietly break the pipeline is worse than no auto-updater")
4. Add User Story 3 → validate Scenarios 9, 10 → the lifecycle issue narrates and self-closes/flags without a human reading run logs
5. Add User Story 4 → validate Scenarios 12, 13, 14, 15 → ambiguous upstream choices surface as questions instead of silent guesses
6. Polish → validate the full Scenario 1–15 sweep together

### Why User Story 2 should not ship without User Story 1, and vice versa

Spec.md states both are Priority P1 for exactly this reason: User Story 1's `prepare`/`verify`/`act` jobs are the same jobs User Story 2 extends with failure branches — there is no independent "safety net only" build, and shipping Story 1 alone (a working adoption path with no verified rollback/block behavior) would leave the pipeline able to quietly adopt a broken version, the outcome spec.md calls "worse than no auto-updater." Task-wise they are sequenced as separate phases only because each phase's tasks touch distinct branches of the same jobs, not because either is safe to deploy alone.
