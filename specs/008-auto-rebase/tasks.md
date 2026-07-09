---

description: "Task list for Auto-Rebase — Keep In-Flight Spec Branches Current With the Main Line"
---

# Tasks: Auto-Rebase — Keep In-Flight Spec Branches Current With the Main Line

**Input**: Design documents from `/specs/008-auto-rebase/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/rebase-workflow.md

**Tests**: No automated test suite exists for any pipeline stage (research.md
D8); validation is `quickstart.md`'s 13 scenarios run by hand. No test tasks
are generated; quickstart validation is folded into each phase's own
checkpoint plus a final full-suite pass.

**Organization**: This feature is a single artifact —
`.github/workflows/speckit-rebase.yml` — going from a "not implemented" stub
to a `discover` → matrixed `rebase` pipeline (plan.md's Project Structure).
There is no `src/`/`tests/` split; every task edits this one file (or, for
validation tasks, exercises it against scratch branches). Tasks are still
grouped by user story per the contract's own step numbering
(`contracts/rebase-workflow.md`) so each story's slice can be reviewed and
validated on its own even though they land in the same file.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (independent edits or reads; here, mostly
  independent validation runs — most implementation tasks touch the same
  file sequentially and are not marked [P])
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Every task names the exact section of `.github/workflows/speckit-rebase.yml`
  it edits, keyed to `contracts/rebase-workflow.md`'s step numbers

## Path Conventions

Single project, CI/CD-only feature. The only file under edit:

- `.github/workflows/speckit-rebase.yml`

Reused, unchanged: `.github/actions/speckit-context` (App-token auth).

---

## Phase 1: Setup

**Purpose**: Replace the stub's placeholder body with the real job skeleton
and confirm the trigger contract carries over unchanged.

- [X] T001 In `.github/workflows/speckit-rebase.yml`, remove the stub's single
      "Not yet implemented" step and its `rebase:` job body, keeping the
      header comment (updated to describe the real two-job design), `name:`,
      `permissions: {}` at the workflow level, and the existing trigger block
      (`on.push.branches: [main]`, `on.schedule.cron: "17 4 * * *"`) verbatim
      per `contracts/rebase-workflow.md`'s Trigger contract (research.md D7).

**Checkpoint**: Workflow file parses as valid YAML with an empty `jobs:` map
ready for Phase 2.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The `discover` job's branch-selection core and the `rebase`
job's shared checkout/rebase-attempt skeleton — every user story's rebase
outcome (clean, AI-resolved, or abandoned) is routed from this same
mid-rebase state, so it must exist before any story's own behavior can be
added.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 In `.github/workflows/speckit-rebase.yml`, add the `discover` job:
      `runs-on: ubuntu-latest`, `if: ${{ !endsWith(github.actor, '[bot]') }}`
      (FR-009 loop guard, unchanged from the stub, research.md D7),
      `permissions: { contents: read, issues: read }`, an output
      `branches: ${{ steps.select.outputs.branches }}`, a bootstrap
      `actions/checkout@v4` step (`persist-credentials: false`), and a
      `speckit-context` step (`uses: ./.github/actions/speckit-context`) for
      the App token, per `contracts/rebase-workflow.md`'s `discover` job
      contract.
- [X] T003 In the `discover` job, add a step that runs
      `git ls-remote --heads origin 'spec/*'` to list candidate slugs
      (research.md D1, contract step 1).
- [X] T004 In the same or a following `discover` step, for each candidate
      slug read `git show spec/<slug>:specs/<slug>/spec-meta.json` (the
      branch's own tip, never `main` — research.md D1); exclude a candidate
      whose file is missing, unparseable, or whose `.spec_dir` does not equal
      `specs/<slug>` (self-identity check, same idiom as
      `speckit-7-cleanup.yml`), emitting an `::warning::` line and a
      `$GITHUB_STEP_SUMMARY` line naming the branch and the reason (spec.md
      edge case: "must record why rather than acting blindly on an
      unidentified specification"; contract step 2).
- [X] T005 In the same step, exclude any surviving candidate whose
      `spec-meta.json` reads `.stage == "stalled"` — silently, no warning
      (FR-002; this is routine, not an error condition; contract step 2).
- [X] T006 In the `discover` job, add a step that emits the surviving
      `{slug, spec_dir, issue}` triples as a JSON array via
      `echo "branches=$json" >> "$GITHUB_OUTPUT"`; an empty array is a valid,
      successful output (FR-010's "no in-flight branches" case, contract
      step 4). Do not add the `rebase:blocked` dedup filter here yet — that
      is T022 (US3), added once the escalation marker it reads exists.
- [X] T007 In `.github/workflows/speckit-rebase.yml`, add the `rebase` job
      skeleton: `needs: discover`,
      `strategy: { fail-fast: false, matrix: { include: ${{ fromJson(needs.discover.outputs.branches) }} } }`,
      `concurrency: { group: speckit-rebase-${{ matrix.slug }}, cancel-in-progress: false }`,
      `runs-on: ubuntu-latest`,
      `permissions: { contents: write, issues: write }` (data-model.md D2;
      zero matrix entries ⇒ zero job runs ⇒ workflow still succeeds, FR-010).
- [X] T008 In the `rebase` job, add the `speckit-context` step for the App
      token, then check out `spec/${{ matrix.slug }}` with `fetch-depth: 0`
      (populates `refs/remotes/origin/spec/<slug>` at its current tip — the
      `--force-with-lease` comparison value), then a scoped
      `git fetch origin main:refs/remotes/origin/main` — **never** a bare
      `git fetch origin` afterward in any later step, which would silently
      refresh the lease and defeat FR-011 (research.md D3, contract step 2).
- [X] T009 In the `rebase` job, add a step that records
      `before=$(git rev-parse HEAD)` and then runs `git rebase origin/main`,
      capturing its exit code without failing the step
      (`continue-on-error` or an explicit `|| true` plus captured status) so
      later steps can branch on clean/conflict/error (contract step 3).

**Checkpoint**: `discover` selects the correct branch set (minus dedup) and
`rebase` checks out each branch, fetches `main` only, and attempts the rebase.
Neither job publishes anything yet — safe to merge/test in isolation before
any story's publish/AI/escalation logic exists.

---

## Phase 3: User Story 1 - In-flight spec branches stay current with the main line automatically (Priority: P1) 🎯 MVP

**Goal**: When a rebase applies with no conflicts, publish the rebased branch
with `--force-with-lease`; when it's already current, do nothing.

**Independent Test**: With one or more in-flight `spec/NNN-slug` branches
present, advance `main` (no conflicts) and verify each is rebased and
force-pushed to the rebased result, and that a branch already current is left
untouched with no spurious update.

### Implementation for User Story 1

- [X] T010 [US1] In the `rebase` job, add the clean-exit branch (`git rebase`
      from T009 exited 0): compute `after=$(git rev-parse HEAD)`; if
      `after == before`, log "already current" and stop — no push, no
      comment (Acceptance Scenario 1.3, data-model.md's `before == after`
      outcome row).
- [X] T011 [US1] In the same branch, when `after != before`, run
      `git push --force-with-lease origin HEAD:refs/heads/spec/${{ matrix.slug }}`
      (FR-004, contract step 4).
- [X] T012 [US1] Handle the push's outcome: on success, log it (done — later
      stories add the `rebase:blocked` label removal here, T017); on
      rejection (remote moved since checkout), log via `::warning::`/step
      summary and exit the step successfully (exit 0) with **no** lifecycle
      comment (FR-011, contract step 4 "Rejected" branch).
- [ ] T013 [US1] Validate against `quickstart.md` Scenario 1 (clean rebase
      behind main) and Scenario 2 (already current, no-op): create a scratch
      `spec/NNN-slug` branch, advance `main` with a non-conflicting commit,
      trigger the workflow, and confirm the branch's tip is a rebase of its
      prior work with no lifecycle-issue comment; re-run immediately with no
      further `main` advance and confirm the tip SHA is byte-for-byte
      unchanged.

**Checkpoint**: User Story 1 is fully functional and independently
testable/deployable as the MVP — the common case (clean rebase) now runs
end-to-end with zero human action.

---

## Phase 4: User Story 2 - Conflicting rebases are resolved by an AI assistant, scoped to the rebase alone (Priority: P2)

**Goal**: When the rebase stops on conflicts, an AI assistant resolves only
those conflicts (no unrelated edits, verified deterministically), then the
result is published the same way as a clean rebase.

**Independent Test**: Create an in-flight branch whose changes conflict with
`main` in a reconcilable way, advance `main`, and verify the AI-assisted
resolution reconciles only the in-progress rebase and the branch is updated
to the resolved result.

### Implementation for User Story 2

- [X] T014 [US2] In the `rebase` job, add the conflict branch (T009's rebase
      exited nonzero with `git status` showing `rebase-merge`/`rebase-apply`
      in progress): before running the agent, capture
      `pre_tip` = `git rev-list --reverse origin/main..HEAD` — the ordered
      commit sequence about to be replayed (research.md D4, contract step 5).
- [X] T015 [US2] Add the `anthropics/claude-code-action@v1` step on the same
      runner: `--model claude-sonnet-5` (constitution II's implementation
      tier), a bounded `--max-turns`,
      `--allowedTools "Read,Edit,Grep,Glob,Bash(git status:*),Bash(git diff:*),Bash(git add:*),Bash(git rebase --continue:*),Bash(git rebase --abort:*)"`,
      `--disallowedTools "WebSearch,WebFetch"`, `continue-on-error: true`.
      Prompt: resolve only the in-progress rebase's conflicts, one stop at a
      time (`git status` → inspect conflict markers → edit only
      conflict-marked files → `git add` → `git rebase --continue`), append
      each stop's `git diff --name-only --diff-filter=U` output to a
      manifest file before resolving it, and `git rebase --abort` rather
      than leaving a half-resolved stop if genuinely stuck; never
      `git commit`, `git push`, or any `gh` command (research.md D4, contract
      step 5).
- [X] T016 [US2] Add a deterministic post-step (`if: always()`, guarded on
      "the conflict branch was taken") that: treats the rebase as failed if
      `rebase-merge`/`rebase-apply` is still present or the agent step
      errored/timed out; otherwise computes `post_tip` the same way as
      `pre_tip` and requires same length/order against `pre_tip`; then,
      pairwise per commit, requires the `post_tip` commit's
      `git show --name-only` file set to be a subset of (the corresponding
      `pre_tip` commit's original file set **union** the manifest file from
      T015) — any file outside that union is a scope-check failure (D4,
      contract step 6).
- [X] T017 [US2] On scope-check pass, publish exactly as US1's T011/T012
      (`git push --force-with-lease origin HEAD:refs/heads/spec/${{ matrix.slug }}`,
      same lease/no-comment-on-rejection handling); on success, if the
      lifecycle issue currently carries label `rebase:blocked`, remove it
      (auto-recovery — forward reference to US3's T020 label; a no-op
      before US3 exists since the label is never yet added) (FR-006,
      research.md D6).
- [ ] T018 [US2] Validate against `quickstart.md` Scenario 3 (conflicting
      rebase the AI resolves): advance `main` with a commit that edits the
      same lines a scratch branch already changed in a reconcilable way,
      trigger the workflow, and confirm the branch is rebased and
      force-pushed, `git diff` between the resolved commit and its
      pre-rebase original (restricted to files outside the actual conflict
      set) is empty, and no lifecycle-issue comment appears.

**Checkpoint**: User Stories 1 AND 2 both work independently — clean rebases
publish directly, and reconcilable conflicts are resolved and published by
the AI step with a verified, scope-limited diff.

---

## Phase 5: User Story 3 - Unresolvable rebases escalate to a human without corrupting the branch (Priority: P3)

**Goal**: When a rebase cannot be completed even with AI assistance, abandon
it (branch untouched, `git rebase --abort`) and escalate to the
specification's lifecycle issue with a dedup-able SHA marker.

**Independent Test**: Create an in-flight branch whose conflicts the AI
cannot resolve, advance `main`, and verify the attempt is abandoned, the
branch is left identical to its pre-attempt state, and a comment asking for
human help is posted to the lifecycle issue.

### Implementation for User Story 3

- [X] T019 [US3] In the `rebase` job, add the abandonment branch — reached
      when: the initial `git rebase` (T009) errors outright and is not a
      conflict stop, the agent step (T015) errors/times out/self-aborts, or
      the post-step scope check (T016) fails: run `git rebase --abort` if a
      rebase is still in progress; no push is attempted on this path under
      any circumstance (FR-007, research.md D5, contract step 6 "Fail"
      branch).
- [X] T020 [US3] Add the escalation step (runs only when T019's branch was
      taken): re-read `specs/${{ matrix.slug }}/spec-meta.json`'s `.issue`
      from `pre_tip` (re-derived, not reused from `discover`, since a long
      agent turn can separate the two reads — research.md D6). If it
      resolves: `gh issue comment` with a human-readable ask for help plus
      the marker
      `<!-- speckit-rebase: blocked branch-sha=<pre_tip> main-sha=<origin/main tip> -->`;
      `gh label create rebase:blocked --force`; `gh issue edit --add-label
      rebase:blocked` (FR-008, FR-013, contract step 7).
- [X] T021 [US3] In the same escalation step, when the issue cannot be
      resolved or is inconsistent, skip the comment entirely and log why via
      `::warning::` and `$GITHUB_STEP_SUMMARY` only — no comment, no label,
      no further action on that branch this run (spec.md edge case; contract
      step 7 "does not resolve" branch).
- [X] T022 [US3] Back in the `discover` job (extending T006), add the FR-012
      dedup check: for each surviving candidate, if its lifecycle issue
      carries label `rebase:blocked`, run
      `gh issue view <issue> --json comments` and find the most recent
      comment matching the marker regex
      `<!-- speckit-rebase: blocked branch-sha=([0-9a-f]+) main-sha=([0-9a-f]+) -->`;
      compare `branch-sha` against `git ls-remote origin spec/<slug>`'s
      current tip and `main-sha` against `git rev-parse origin/main`. Both
      equal → exclude the candidate from this run's matrix entirely (no
      agent turn, no comment); either differs → keep it (research.md D6,
      contract step 3).
- [ ] T023 [US3] Validate against `quickstart.md` Scenario 4 (unresolvable
      conflict → abandon + escalate: branch tip byte-for-byte unchanged,
      issue gets a comment with the SHA marker and label `rebase:blocked`),
      Scenario 5 (repeated stall against an unchanged pair is excluded from
      the matrix with no new comment), and Scenario 6 (the stall clears and
      the branch is re-attempted once either the branch or `main` changes,
      with the label removed on a subsequent success).

**Checkpoint**: All three core rebase outcomes (clean, AI-resolved,
abandoned) are implemented and independently verifiable; an abandoned
rebase never corrupts a branch and never re-escalates against an unchanged
stall.

---

## Phase 6: User Story 4 - The stage runs safely across many branches and its own triggers (Priority: P3)

**Goal**: Confirm and validate the robustness guarantees layered on top of
the three core behaviors: per-branch isolation, no looping on the pipeline's
own pushes, nightly schedule independent of push activity, and quiet success
when there is nothing to do.

**Independent Test**: With several in-flight branches present, advance `main`
(including an advance from the pipeline's own automation) and separately let
the nightly schedule fire, and verify every branch is considered, an
automation-originated advance does not trigger action, branches with nothing
to rebase are left unchanged, and each branch's outcome is independent of the
others.

### Implementation for User Story 4

- [X] T024 [US4] Confirm `.github/workflows/speckit-rebase.yml`'s trigger
      block (`on.push.branches: [main]`, `on.schedule.cron: "17 4 * * *"`,
      from T001) and the `discover` job's
      `if: ${{ !endsWith(github.actor, '[bot]') }}` gate (from T002) are
      both present and unchanged from the stub — this single condition is
      already FR-009's loop guard on `push` events (the pipeline's own
      writes all land through the `speckit-bot` App,
      `<bot-slug>[bot]`) and a no-op filter on `schedule` events, so FR-001's
      nightly run always proceeds regardless (research.md D7). No new code
      is needed beyond T001/T002 — this task is a verification checkpoint,
      not a new edit.
- [ ] T025 [US4] [P] Validate against `quickstart.md` Scenario 9 (zero
      `spec/*` branches: `discover` reports an empty branch list, `rebase`
      shows zero matrix entries, no error, no comment anywhere) and Scenario
      8 (a branch marked `"stage": "stalled"` never appears in the `rebase`
      matrix, even against a would-be-conflicting `main` advance).
- [ ] T026 [US4] [P] Validate against `quickstart.md` Scenario 10 (a push to
      `main` made through the App-token identity does not start/visibly
      skips `discover`) and Scenario 11 (manually firing the workflow the
      same way the `schedule` trigger would still brings in-flight branches
      current, identical in effect to a push-triggered run).
- [ ] T027 [US4] [P] Validate against `quickstart.md` Scenario 7 (a
      legitimate commit pushed directly to a `spec/NNN-slug` branch while a
      run is in flight causes that run's `--force-with-lease` push to be
      rejected, the concurrent commit survives untouched, and no
      lifecycle-issue comment appears) and Scenario 12 (two scratch
      specifications, one clean and one unresolvably conflicting against the
      same `main` advance, both handled in one workflow run with neither
      matrix job's outcome affecting the other) and Scenario 13 (a branch
      whose `spec-meta.json` has an invalid/mismatched `.issue` is excluded
      at `discover` time with a step-summary explanation, never acted on).

**Checkpoint**: All four user stories are independently functional and
validated; the stage is safe to run unattended on a busy repository.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final consistency checks that span every story.

- [ ] T028 [P] Run `lint-workflows.yml`'s own checks locally against
      `.github/workflows/speckit-rebase.yml` (YAML parses via `yaml.safe_load`
      and every `run:` block passes `bash -n` after neutralizing
      `${{ ... }}` expressions) before opening the eventual review PR, since
      that workflow gates every PR touching `.github/workflows/**`.
- [X] T029 [P] Cross-check the finished workflow against
      `docs/architecture.md`'s "Auto-rebase (`speckit-rebase.yml`, stub)"
      section (trigger, clean/conflict/stuck design summary) — update that
      section only if the implementation diverges from what it already
      documents; per plan.md, no changes are expected beyond what
      research.md's SHA-marker/dedup mechanism adds as detail.
- [ ] T030 Run the full `quickstart.md` scenario suite (all 13 scenarios) end
      to end in one pass against a fresh set of scratch specifications, to
      confirm nothing in a later story's implementation regressed an earlier
      one (e.g. US3's escalation step didn't break US1's clean-path
      no-comment guarantee).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user
  stories (the `discover`/`rebase` skeleton and mid-rebase state every story
  branches from).
- **User Story 1 (Phase 3)**: Depends on Foundational only. This is the MVP.
- **User Story 2 (Phase 4)**: Depends on Foundational; its publish step
  (T017) reuses US1's push logic (T011/T012), so implement after US1.
- **User Story 3 (Phase 5)**: Depends on Foundational; its abandonment
  branch (T019) is reached from both the plain rebase-error path (available
  after Foundational) and the AI scope-check failure path (available after
  US2), so implement after US2 for a fully exercisable failure surface. Its
  discover-side dedup (T022) also reads the label T020 writes, so within
  this phase T020/T021 precede T022.
- **User Story 4 (Phase 6)**: Depends on Foundational (T024 only reconfirms
  T001/T002); its validation tasks (T025-T027) exercise the fully-assembled
  workflow, so they are most meaningfully run after US1-US3 are in place,
  though T024 itself has no code dependency on US2/US3.
- **Polish (Phase 7)**: Depends on all four user stories being complete.

### Within This Feature

Because every task edits the same single file
(`.github/workflows/speckit-rebase.yml`), implementation tasks are
sequential in the order listed (T001 → T030) rather than parallelizable
across stories — there is no "different files, no dependencies" split for
the edits themselves. Only the validation tasks (marked `[P]`) can run
concurrently with each other, since each spins up independent scratch
branches/runs.

### Parallel Opportunities

- T025, T026, T027 (US4's quickstart validation scenarios) can run in
  parallel with each other once US1-US3 are implemented — each exercises a
  different scratch-branch scenario against the same finished workflow.
- T028 and T029 (Polish) can run in parallel — one is a local lint pass, the
  other a documentation cross-check.

---

## Parallel Example: User Story 4 validation

```bash
# Once US1-US3 are implemented, run these independently:
Task: "Validate quickstart.md Scenario 9 (no branches) and Scenario 8 (stalled excluded)"
Task: "Validate quickstart.md Scenario 10 (loop protection) and Scenario 11 (nightly schedule)"
Task: "Validate quickstart.md Scenario 7 (concurrent update) and Scenario 12 (isolation) and Scenario 13 (unidentifiable issue)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001).
2. Complete Phase 2: Foundational (T002-T009) — CRITICAL, blocks all stories.
3. Complete Phase 3: User Story 1 (T010-T013).
4. **STOP and VALIDATE**: Run Scenarios 1 and 2 (T013) — clean rebases now
   publish automatically with no human action, the stage's entire reason for
   existing.
5. This MVP alone already delivers SC-001/SC-002 for the common (no
   conflict) case and can be merged/observed in production before US2-US4
   land.

### Incremental Delivery

1. Setup + Foundational → skeleton ready, nothing published yet.
2. Add User Story 1 → validate (Scenarios 1-2) → MVP: clean rebases publish
   automatically.
3. Add User Story 2 → validate (Scenario 3) → reconcilable conflicts also
   publish automatically via scoped AI resolution.
4. Add User Story 3 → validate (Scenarios 4-6) → unresolvable conflicts fail
   safe and escalate, with dedup against repeat noise.
5. Add User Story 4 → validate (Scenarios 7-13) → the whole stage is
   confirmed safe to run unattended across many branches and both triggers.
6. Polish (T028-T030) → lint, docs cross-check, full-suite regression pass.

### Suggested MVP Scope

**User Story 1 only** (T001-T013): the clean-rebase publish path is the
stage's entire reason for existing per spec.md ("Why this priority" — drift
is the problem this stage exists to solve); everything else (US2's AI
resolution, US3's escalation, US4's robustness hardening) is additive safety
and coverage on top of that core loop.

---

## Notes

- [P] tasks here mark independent **validation** runs, not independent code
  edits — every implementation task shares one file and is applied in order.
- Every task names the exact contract step (`contracts/rebase-workflow.md`)
  and/or research.md decision (D1-D8) it implements, so no task requires
  additional context beyond this file, plan.md, and the design docs.
- Commit after each phase (or logical group within a phase); each checkpoint
  above is a safe point to stop and validate independently before continuing.
- No task edits any file outside `.github/workflows/speckit-rebase.yml`
  except T029's conditional, unlikely-to-be-needed `docs/architecture.md`
  touch-up.
