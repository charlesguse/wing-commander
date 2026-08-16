---

description: "Task list for Auto-Update Declines to Re-Propose a Candidate Whose PR Is Already Open"
---

# Tasks: Auto-Update Declines to Re-Propose a Candidate Whose PR Is Already Open

**Input**: Design documents from `/specs/035-auto-update-pr-guard/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/auto-update-pr-guard.md, quickstart.md

**Tests**: Requested by the spec itself — FR-016/User Story 5 require the executable scenario harness (`.github/scripts/auto-update-spec-kit-tests/`) to cover the guard's routing decisions and `act`'s pre-push check, and SC-005 requires that removing the guard fails at least one harness assertion. Narration *content* (the step summary and tracking-issue text, User Story 2) has no dedicated harness file in `plan.md`'s Project Structure — it is verified by the Polish phase's live/desk-check sweep, the same split `specs/032-structured-clarification-gate/tasks.md` used for scenarios that need a real GitHub dispatch.

**Organization**: Tasks are grouped by user story per `spec.md`'s priorities. User Stories 1 and 2 are both P1 and together are this feature's MVP: US1 makes the guard actually skip the billed steps (the entire cost this feature removes), and US2 makes that skip legible on the tracking issue and in the run summary — a silent no-op is, per the spec's own framing, "barely better than the red run it replaced." User Story 3 (P2) requires no new code (the guard's own "read the PR's open/closed state, hold nothing else" design already makes resumption automatic) and is therefore an audit task. User Story 4 (P3) is the independent `act`-side leftover-branch diagnosis. User Story 5 (P3) is the harness coverage that makes US1/US4's behaviour provable and durable against regression.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US5)
- Setup and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature: one existing reusable workflow file gains one new step in each of two of its jobs (per plan.md's Scale/Scope), and its existing Python/Bash test harness gains scenarios. No `src/`/`tests/` split. All paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Confirm the exact step names, `id`s, and line numbers `contracts/auto-update-pr-guard.md` and `research.md` reference are still accurate, since that audit was captured during planning and `.github/workflows/auto-update-spec-kit.yml` (2770 lines) may have shifted since.

- [X] T001 Re-read `.github/workflows/auto-update-spec-kit.yml`'s `evaluate-path` job — "Resolve entry context" (`id: entry`, ~line 781), "Fetch candidate release notes" (`id: notes`, ~line 826), "Decide upgrade path" (`id: decide`, ~line 846, the first Claude-billed step), "decide-outcome" (~line 934) — and its `act` job — "Open version-bump PR" (~line 2237), its self-marker write (~line 2281), `needs.prepare.outputs.branch`. Confirm every step name, `id`, and line number still matches `contracts/auto-update-pr-guard.md` and `research.md`. If anything has moved or been renamed, update the working inventory before T002 begins — every task below assumes this list is exhaustive and current.

**Checkpoint**: The step-level inventory is confirmed current — editing can proceed without re-deriving it mid-task.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: N/A for this feature. Every implementation task below is a targeted edit inside `evaluate-path` or `act`, using only `gh`/`jq`/`git` calls this file already makes elsewhere (research.md's "Primary Dependencies" note: every new call this feature adds — `gh pr list`, `--head` — reuses idioms already present verbatim in this file). There is no new shared script, composite action, or config file for any story to depend on.

**Checkpoint**: No foundational tasks — proceed directly to User Story 1.

---

## Phase 3: User Story 1 - A settled candidate that already has an open PR costs nothing (Priority: P1) 🎯 MVP

**Goal**: Before `evaluate-path`'s first Claude-billed step, a new guard step asks whether this feature already has a matching open version-bump pull request. When one exists, the run skips `notes`, `decide`, `prepare`, `e2e-stage`, `verify`, and `act` entirely and still concludes as a success.

**Independent Test**: With an open version-bump PR carrying this feature's marker for the settled candidate, trigger the workflow and confirm the billed judgment and end-to-end stages never start, no branch is pushed, and the run concludes successfully.

### Implementation for User Story 1

- [X] T002 [US1] In `.github/workflows/auto-update-spec-kit.yml`'s `evaluate-path` job, add a new step "Guard against an already-open version-bump PR" (`id: guard`), inserted between "Resolve entry context" and "Fetch candidate release notes": under `set -uo pipefail`, call `gh pr list --repo "$GITHUB_REPOSITORY" --state open --json number,body,headRefName`, capturing failure explicitly (never `|| echo '[]'` — research.md's "don't know means don't act" lesson, copied from `settle`'s own #167-vs-#162 incident) — on failure, emit `skip=true`/`reason=lookup-failed` and `exit 0` without proceeding. On success, filter to PRs whose `body` contains the literal marker `<!-- wing-commander-auto-update-spec-kit: version-bump -->` (never the revert marker, FR-013), extract each match's candidate from `headRefName` via `sub("^auto-update-spec-kit/v"; "")` (FR-002/FR-003, recognition by marker, extraction by branch name), and set: `skip=false` when zero matches; `skip=true`/`reason=already-open` when exactly one match whose candidate equals `$CANDIDATE`; `skip=true`/`reason=queued-behind` when exactly one match with a different candidate (FR-011); `skip=true`/`reason=multiple-matches` when more than one match (FR-014, never choosing one). Always emit `matches=<jq-compacted JSON array of {number, candidate}>`.
- [X] T003 [US1] In the same file: add `&& steps.guard.outputs.skip != 'true'` to the existing `if:` conditions of "Fetch candidate release notes" (`notes`) and "Decide upgrade path" (`decide`), so neither runs when the guard fires (FR-004 — the judgment step itself, not just its outcome, is skipped). Extend `decide-outcome`, ahead of its existing `RESUMED` branch, with a new branch that sets `outcome=guard-skip` when `steps.guard.outputs.skip == 'true'`, forwarding `steps.guard.outputs.reason` and `steps.guard.outputs.matches` as its own outputs — no new job output is declared; `prepare`'s existing `outcome == 'clean-bump'` gate already treats any other value (including this new one) as "do not run," which transitively skips `e2e-stage`/`verify`/`act` (research.md's "reuse the existing outcome switch" decision — no `if:` on any downstream job changes). (Depends on T002.)

**Checkpoint**: User Story 1 is fully functional — a matching open PR stops the chain before any billed step runs, and the run still concludes green, matching `quickstart.md` Scenarios 1, 2, 5, and 6.

---

## Phase 4: User Story 2 - A maintainer can tell at a glance why nothing happened (Priority: P1)

**Goal**: A guarded run's step summary and the tracking issue both name the candidate and the blocking pull request, narrated once per blocking PR with a last-checked marker refreshed on every guarded run — so "nothing happened today" reads as a deliberate decision.

**Independent Test**: Trigger a guarded run and confirm that, reading only the run's step summary — and separately, reading only the tracking issue — a maintainer can state which candidate version was skipped, which pull request it is waiting on, and that the skip was intentional.

### Implementation for User Story 2

- [X] T004 [US2] In `.github/workflows/auto-update-spec-kit.yml`'s `evaluate-path` job, add a new step gated on `steps.decide-outcome.outputs.outcome == 'guard-skip'`: (1) write a `$GITHUB_STEP_SUMMARY` line naming the candidate, the blocking PR number(s), and the reason (`already-open` / `queued-behind` / `multiple-matches` / `lookup-failed`) per FR-006; (2) when `reason` is `already-open` or `queued-behind` **and** the tracking issue's settle marker's existing `guard-pr` sub-field differs from the matched PR number (or is absent), post one `wing-commander-callout` comment (`kind: info`) narrating the skip and rewrite the marker's `guard-pr=<number>` and `guard-checked=<UTC timestamp, date -u +%Y-%m-%dT%H:%MZ>` sub-fields, using the same `marker_line`/`new_marker`/`sed "s|$marker_line|$new_marker|"` idiom `settle` already uses (data-model.md, FR-007); (3) when `guard-pr` already matches the current blocker, refresh only `guard-checked` — no second narration comment (FR-007's "no guarded run may add a second narration entry... however long it stays open"); (4) when `reason` is `multiple-matches`, post a warning every run and write nothing to the marker, matching `settle`'s own `count > 1` precedent of never maintaining dedup state for a data-integrity condition (research.md). This step MUST NOT change the pinned Spec Kit version, the existing PR/branch, or the settle counter (FR-008). (Depends on T003.)

**Checkpoint**: User Stories 1 and 2 both hold — the guard fires, and its reason is legible from the step summary and the tracking issue alone, matching `quickstart.md` Scenario 3. This is the MVP.

---

## Phase 5: User Story 3 - Work resumes on its own once the PR is resolved (Priority: P2)

**Goal**: Confirm that merging or closing the blocking PR requires no manual state clearing — the guard (T002-T003) holds no state of its own beyond what `gh pr list --state open` returns each run, so a resolved PR simply stops being a match.

**Independent Test**: With a guarded run recorded, resolve the PR (once by merging, once by closing unmerged) and confirm the next run behaves correctly in each case without any human touching state.

### Implementation for User Story 3

- [X] T005 [US3] Audit `.github/workflows/auto-update-spec-kit.yml` as edited by T002-T004: confirm the guard step (T002) sits after "Resolve entry context," the step that already unifies both the freshly-settled (`needs.settle.outputs.settled == 'true'`) and resumed-maintainer-decision (`needs.comment-reply.outputs.resumed == 'true'`) entry paths — so the guard fires identically on either entry point with no additional gating needed (FR-012). Confirm the guard's only input is that run's own `gh pr list --state open` result (T002) and that T004's marker write (`guard-pr`/`guard-checked`) is never read as a *gate* anywhere in the file — only as narration state — so a merged or closed PR silently stops matching with no latch to reset, no label to remove, and no issue edit required beforehand (FR-009). Record this confirmation in the PR body; the live-run form (dispatching against a real merged PR, and separately a real closed-unmerged PR) is deferred to maintainer review before merge, per `quickstart.md` Scenarios 7-9.

**Checkpoint**: User Story 3 holds by construction — resuming after the PR resolves needs zero manual steps (SC-004), confirmed by audit.

---

## Phase 6: User Story 4 - A leftover branch fails loudly and legibly, not cryptically (Priority: P3)

**Goal**: `act`'s "Open version-bump PR" step gains its own pre-push check, independent of `evaluate-path`'s guard, so a branch left behind by a failed run or a closed-unmerged PR declines with a message naming the blocker and the remedy instead of a raw non-fast-forward push rejection.

**Independent Test**: Leave a branch named for the candidate on the consumer repository with no open PR pointing at it, run the chain through to the PR-opening step, and confirm it fails with a message that names the branch and the remedy, without overwriting the branch's contents.

### Implementation for User Story 4

- [X] T006 [US4] In `.github/workflows/auto-update-spec-kit.yml`'s `act` job, add a new step "Check for a pre-existing branch or pull request" (`id: preflight`), immediately before "Open version-bump PR" and under that step's existing `if:` gate (`needs.health-check.outputs.pinned-ok != 'false' && needs.prepare.result == 'success' && needs.verify.outputs.passed == 'true'`): under `set -uo pipefail`, run `git ls-remote --exit-code origin "refs/heads/$BRANCH"` (the exact idiom `plan.yml`/`tasks.yml`/`intake.yml`/`cleanup.yml`/`rebase.yml` already use). When the branch does not exist, emit `blocked=false`. When it exists, look up `gh pr list --repo "$GITHUB_REPOSITORY" --head "$BRANCH" --state open --json number --jq '.[0].number // empty'`; emit `blocked=true` and `reason="pr #$existing_pr already proposes this candidate"` when an open PR is found, else `blocked=true` and `reason="branch $BRANCH already exists with no open PR — delete it and re-dispatch"` (FR-015). This is a second, independent check from `evaluate-path`'s guard — it exists for the residual case where `evaluate-path` correctly found no open PR (so the run proceeded) but a leftover branch remains from a prior run that failed after pushing, or a PR closed unmerged with its branch left behind (research.md).
- [X] T007 [US4] In the same file: add `&& steps.preflight.outputs.blocked != 'true'` to "Open version-bump PR"'s existing `if:` condition, so it never pushes or calls `gh pr create` when blocked. Add a new step gated on `steps.preflight.outputs.blocked == 'true'` that writes a `$GITHUB_STEP_SUMMARY` line and a `wing-commander-callout` issue comment naming the blocking branch or PR and the remedy (FR-015), then exits 0 — a decline, not a failure, so the job still concludes as a success. No force-push is introduced anywhere in this task (FR-018, Out of Scope). (Depends on T006.)

**Checkpoint**: User Story 4 holds — a leftover branch (with or without a stray open PR) fails legibly instead of surfacing a raw push rejection, matching `quickstart.md` Scenarios 10 and 11, and the branch's contents are never overwritten (SC-006).

---

## Phase 7: User Story 5 - The guard is asserted by the executable harness (Priority: P3)

**Goal**: The executable scenario harness gains coverage for: a target branch that already exists, a pull request that already exists, and the routing decision that skips the billed stages — so a future edit that weakens or removes the guard fails a check instead of surviving until the next unreviewed PR.

**Independent Test**: Run the workflow's scenario harness and confirm it exercises, and can fail on, each of: the guard skipping the chain when a matching PR is open, the chain proceeding when none is open, the PR-opening step meeting a pre-existing branch, and the PR-opening step meeting a pre-existing pull request.

### Implementation for User Story 5

- [X] T008 [US5] In `.github/scripts/auto-update-spec-kit-tests/gh_stub.py`, add a `gh pr list` handler under `cmd == "pr"` (today only `create`/`view` exist at ~line 256, confirmed absent — `pr list` currently falls through to "gh stub: unhandled command"). Support `--state`, `--head`, and `--json` filters against the stub's existing `s["prs"]` map, mirroring `issue list`'s existing filtering shape (`opt(argv, "--state", "open")`, sort/filter, `emit([...], argv)`). Treat every stub PR as implicitly `state == "open"` unless a future scenario needs otherwise (sufficient for every scenario T010 adds — no closed-PR modelling required); `headRefName` reads from the `head` field `pr create` already writes.
- [X] T009 [P] [US5] In `.github/scripts/auto-update-spec-kit-tests/t7_gating.py`, add: a `step_scenario` for `evaluate-path`'s own steps (new — today only `act` gets step-level assertions via `act_steps`) asserting the guard step (T002) suppresses "Fetch candidate release notes" and "Decide upgrade path" when `steps.guard.outputs.skip == 'true'`, and that both run when `skip == 'false'`; a `scenario` asserting a `guard-skip` outcome yields the same `{"prepare": False, "verify": False, "act": False}` job-level matrix the existing `ambiguous-options` scenario already asserts (~line 209); and a `scenario` asserting the ordinary "no matching PR" case proceeds through `prepare`/`verify`/`act` exactly as the existing `clean-bump` scenario does (~line 176). This task is independent of T008 — `t7_gating.py` evaluates `if:` expressions statically and makes no `gh` calls.
- [ ] T010 [US5] In `.github/scripts/auto-update-spec-kit-tests/t5_act.sh`, add two new scenarios exercising T006/T007's preflight step against a real git repo + bare origin and the `gh` stub, following the file's existing `build`/`remote_refs`/`check`/`check_contains` pattern: (1) a pre-existing remote branch `auto-update-spec-kit/v$CANDIDATE` with no open PR — assert `blocked=true`, zero push (`remote_refs()`), zero PR created, the step exits 0, and the summary/log names the branch and the remedy; (2) the same branch with an open PR already seeded via T008's stub referencing it — assert the same, with the message naming the PR instead. (Depends on T006, T007, T008.)
- [ ] T011 [US5] Verify SC-005 (removing the guard fails the harness): temporarily remove `&& steps.guard.outputs.skip != 'true'` from "Fetch candidate release notes"/"Decide upgrade path" (or the `guard-skip` branch from `decide-outcome`), run `bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh t7_gating`, and confirm T009's new assertions fail. Separately, remove T007's `steps.preflight.outputs.blocked != 'true'` clause from "Open version-bump PR," run `bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh t5_act`, and confirm T010's new assertions fail. Restore both clauses afterward and re-run the full suite (`bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh`) to confirm it passes clean. (Depends on T009, T010.)

**Checkpoint**: User Story 5 holds — `quickstart.md` Scenario 12 passes, and `run-tests.sh` (the hard merge gate `lint-workflows.yml` already runs) exercises every FR-016 state.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and the remaining validation sweep that isn't specific to one story.

- [ ] T012 [P] Add a bullet to `docs/architecture.md`'s existing "Auto-Update Spec Kit" section (~lines 808-911) describing the new guard step and its `guard-skip` outcome value, and a note in that section's "Self-recognition" paragraph that the guard also reads *other* open pull requests' version-bump markers, not only its own PRs' markers (research.md's noted docs impact; `docs/adoption.md`'s per-stage job-count table is unaffected since the guard is a step, not a job).
- [ ] T013 Run `bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh` (full suite) and `actionlint` (plus `yamllint` if available) against the finished `.github/workflows/auto-update-spec-kit.yml`; confirm no new findings beyond this file's pre-existing ones, following the discipline `specs/032-structured-clarification-gate/tasks.md`'s T009 established. Sweep `quickstart.md`'s remaining scenarios not exercised by T009-T011 — Scenarios 3, 4, 5, 6, and 7 need a real GitHub PR/issue dispatch (narration content, one-time-comment dedup, the queued-behind wording, a simulated lookup failure, and the resumed-maintainer-decision entry point) and are deferred to maintainer review before merge; Scenario 11 (`act`'s defense-in-depth backstop for a state `evaluate-path`'s guard should already have caught) can be desk-checked by inspection of T006. Record in the PR body which were exercised live versus desk-checked only.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: N/A — no tasks, nothing blocks User Story 1 beyond Setup's confirmation.
- **User Story 1 (Phase 3)**: Depends on Setup (T001 confirms the exact step names/lines T002/T003 edit).
- **User Story 2 (Phase 4)**: Depends on User Story 1 (T004 reads `steps.guard.outputs.*` and `steps.decide-outcome.outputs.outcome`, both created by T002/T003).
- **User Story 3 (Phase 5)**: Depends on User Story 1 and User Story 2 (T005 audits the finished mechanism, including T004's marker write, to confirm no state needs clearing).
- **User Story 4 (Phase 6)**: Independent of User Stories 1-3 — different job (`act` vs `evaluate-path`), no shared step outputs. May proceed at any point after Setup.
- **User Story 5 (Phase 7)**: Depends on User Story 1 (T009 tests T002/T003's routing) and User Story 4 (T010 tests T006/T007's preflight check).
- **Polish (Phase 8)**: Depends on all prior phases.

### User Story Dependencies

- **User Story 1 (P1)**: No dependency on other stories — this is (half of) the MVP.
- **User Story 2 (P1)**: Depends on User Story 1's outputs existing; no dependency on User Story 3, 4, or 5. The other half of the MVP.
- **User Story 3 (P2)**: Depends on User Stories 1 and 2 (it audits the finished mechanism); no dependency on User Story 4 or 5.
- **User Story 4 (P3)**: No dependency on any other story.
- **User Story 5 (P3)**: Depends on User Story 1 (routing coverage) and User Story 4 (preflight coverage); no dependency on User Story 2 or 3.

### Same-file ordering (not story dependencies, but real ordering constraints)

- `.github/workflows/auto-update-spec-kit.yml` is edited by T002, T003 (US1, `evaluate-path`), T004 (US2, `evaluate-path`), and T006, T007 (US4, `act`) — the `evaluate-path` edits (T002→T003→T004) must land in that order since each reads outputs the previous one created; the `act` edits (T006→T007) are similarly ordered but touch a different job and may proceed independently of the `evaluate-path` chain.
- `.github/scripts/auto-update-spec-kit-tests/gh_stub.py` (T008) has no code dependency on the workflow edits — it may proceed any time after Setup, but T010 needs it in place first.
- `.github/scripts/auto-update-spec-kit-tests/t7_gating.py` (T009) only needs T002/T003 to exist (it reads `if:` expressions from the finished file) and does not depend on T008.
- `.github/scripts/auto-update-spec-kit-tests/t5_act.sh` (T010) needs T006, T007, and T008 all in place first.

### Parallel Opportunities

- T009 (`t7_gating.py`) can run in parallel with T008 (`gh_stub.py`) — different files, T009 has no `gh`-stub dependency.
- T012 (docs) is parallel-safe with everything in Phase 7 — it only reads the finished workflow file's shape, not its test coverage.
- Within Phase 6, T006/T007 (US4) can be worked in parallel with Phase 3-5 (US1-3) since they touch a different job in the same file — coordinate to avoid a merge conflict, but there is no output dependency either way.

---

## Parallel Example: User Story 5

```bash
# Launch together — independent of each other:
Task: "Add a gh pr list handler to gh_stub.py"
Task: "Add evaluate-path routing scenarios to t7_gating.py"
# T010 (t5_act.sh) waits on both T008 and T006/T007 before it can start.
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Complete Phase 1: Setup (confirm the step-level inventory)
2. Complete Phase 3: User Story 1 (the guard fires and the billed steps stop)
3. Complete Phase 4: User Story 2 (the skip is legible on the issue and in the summary)
4. **STOP and VALIDATE**: Run `quickstart.md` Scenarios 1, 2, 3, 5, 6 against the finished wiring
5. This alone closes SC-001 (zero Claude-billed stages while a PR is open), SC-002 (zero failed scheduled runs), and SC-003 (a maintainer can state what happened from the summary alone) — every remaining phase hardens or diagnoses further, not the core fix

### Incremental Delivery

1. Setup → step inventory confirmed
2. Add User Story 1 → validate the guard fires and skips the billed steps → mergeable increment (the quota fix, unverified narration)
3. Add User Story 2 → validate Scenario 3 → MVP complete (the quota fix, with legible narration)
4. Add User Story 3 → audit resumption → confidence increment (no manual step needed after merge/close)
5. Add User Story 4 → validate Scenarios 10-11 → mergeable increment (leftover branches fail loudly, independent of the guard)
6. Add User Story 5 → validate Scenario 12 (SC-005) → durability increment (a weakened guard now fails CI)
7. Polish → docs bullet, full suite + lint, remaining scenario sweep

### Why User Stories 1 + 2 together are the MVP

The spec assigns both P1: US1 alone stops the billed spend but leaves a maintainer unable to tell a deliberate skip from a stall (the spec's own words: "barely better than the red run it replaced"). Shipping US1 without US2 saves the same quota but breaks this project's operating principle that the lifecycle of any automated decision is legible from the issue alone (plan.md's Constitution III). US3-US5 are correctness hardening (no state to clear, ever) and durability (a harness that catches regression) on top of an MVP that is already complete once both P1 stories land.
