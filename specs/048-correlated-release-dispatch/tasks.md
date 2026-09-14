# Tasks: Correlated, atomic release dispatch

**Input**: Design documents from `/specs/048-correlated-release-dispatch/`
(spec.md, plan.md, research.md, data-model.md, contracts/, quickstart.md)

**Prerequisites**: plan.md, spec.md, research.md, data-model.md,
contracts/release-handover-contract.md, contracts/regression-gate.md,
quickstart.md — all present and read.

**Tests**: Not requested. This repository has no application-level test
framework for workflow YAML (plan.md "Testing"); correctness is
established by Gate 53's own `--self-test` fixtures (Polish phase) and by
manually driving the quickstart scenarios against a real or forked
repository (a User Story 3 task and a Polish task), consistent with
specs/045's and Gate 50/51's precedent.

**Organization**: Tasks are grouped by user story (spec.md's Story 1 and
Story 2, both P1; Story 3, P2). There is no `src`/`tests` tree — every
file path below is a workflow YAML file or a gate script under
`.github/scripts/`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Every task names the exact file, and the exact existing step/job/marker
  it changes, so no task requires guessing where to edit.

## ⚠️ Gate numbering note (read before T001)

research.md D7 and contracts/regression-gate.md both flagged "52 as of
this plan; re-check for a collision before claiming it." That collision
already happened: commit `1bd0ffc` (PR #325/#335, merged onto `main`
before this tasks.md was generated) registered Gate 52 as
`verify-auto-release-report.py` in `.github/workflows/lint-workflows.yml`
(line ~3167). **The gate this feature adds is Gate 53**, not Gate 52.
T001 makes this authoritative before any later task writes the number
into a file.

---

## Phase 1: Setup

- [X] T001 Confirm the next available gate number in
      `.github/workflows/lint-workflows.yml` by finding the highest
      `# Gate N —` marker before the "Gate 10 — the gates themselves are
      wired up" section. As of this writing that is Gate 52
      (`verify-auto-release-report.py`), so the number to use in T017,
      T018, and T019 below is **53** — re-run this check immediately
      before T018 if another spec's gate has landed on `main` in the
      meantime, and use whatever number is actually free instead of
      assuming 53 unconditionally.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The request/response shape both P1 stories build on —
neither story's acceptance scenarios can be demonstrated without these
in place first.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 In `.github/workflows/release.yml`, add two new optional
      `workflow_dispatch` inputs immediately after the existing
      `breaking-notes` input: `attempt-token` (`required: false`,
      `default: ""`, `type: string`, description noting internal use by
      an automatic dispatch, blank for a manual release) and `commit`
      (`required: false`, `default: ""`, `type: string`, description
      noting internal use naming the exact commit to release, blank to
      tag the branch tip as today) — per research.md D2 and
      data-model.md's Release request table. Add a one-line comment
      above the two new inputs pointing at
      `specs/048-correlated-release-dispatch/contracts/release-handover-contract.md`
      as the one place their contract is written (FR-019), matching the
      existing Gate 50/51 pointer-comment style already in this file.

- [X] T003 In `.github/workflows/release.yml`, add a top-level
      `run-name:` key (placed after the `name:` key, before `on:`):
      `run-name: "release ${{ inputs.version }} [attempt:${{ inputs.attempt-token }}]"`
      — per research.md D2 and data-model.md's Release run title table.
      Verify by inspection that a dispatch leaving `attempt-token` at its
      `""` default produces the literal title `release v1.4.0 [attempt:]`
      (FR-016): no real, non-empty token can ever equal the empty string
      inside the closing bracket.

- [X] T004 In `.github/workflows/release.yml`'s `Checkout` step, change
      `with:` from `fetch-depth: 0` alone to add
      `ref: ${{ inputs.commit || github.event.repository.default_branch }}`
      alongside `fetch-depth: 0` — per research.md D4 (empty `commit`
      must reproduce today's implicit default-branch checkout exactly,
      FR-015; a non-empty `commit` checks out that exact commit instead
      of the branch tip).

- [X] T005 [P] In `.github/workflows/auto-release.yml`'s
      `dispatch-release` job, at the top of the "Dispatch release.yml and
      wait for its conclusion" step (rename it to reflect its new role,
      e.g. "Dispatch release.yml and correlate its run"), mint
      `token="${{ github.run_id }}-${{ github.run_attempt }}"` and
      capture `request_time="$(date -u +%s)"` immediately before the
      existing `gh workflow run release.yml` call, then add
      `-f "attempt-token=${token}"` and `-f "commit=${VERIFIED_HEAD}"` to
      that call (`VERIFIED_HEAD` is already the step's
      `needs.detect.outputs.head-sha`) — per research.md D1/D2 and
      data-model.md's Release request table. `github.run_id` is unique
      across the repository's entire run history and `github.run_attempt`
      distinguishes a manual re-run of the same `auto-release.yml` run,
      so no counter or random value is needed to satisfy FR-002a.

- [X] T006 In `.github/workflows/auto-release.yml`'s `dispatch-release`
      job, add an `actions/checkout` step (this job has none today;
      `fetch-depth: 0`, `persist-credentials: false`, matching the style
      of the `detect` and `decide-version` jobs' own checkout steps) so
      the job has a local repository with an `origin` remote, then — after
      the dispatch call succeeds, independent of whatever the correlation
      search (Phase 3) finds — add the tag-state check from research.md
      D5: `git fetch origin "refs/tags/${VERSION}:refs/tags/${VERSION}" --quiet 2>/dev/null || true`,
      then set a `tag-matches` job output to `true` only if
      `git rev-parse -q --verify "refs/tags/${VERSION}^{commit}"` succeeds
      AND that commit equals `$VERIFIED_HEAD` (`VERSION` is the step's
      existing `needs.decide-version.outputs.next-version`). Add
      `tag-matches` to the job's `outputs:` block. Per data-model.md's
      Tag state entity: this is a fresh fetch performed after dispatch,
      never a value read before it, and it is compared against the
      commit *this attempt* verified, never the branch tip (FR-007a).

**Checkpoint**: `release.yml` accepts and titles on the new inputs, tags
the requested commit when one is supplied, and `dispatch-release` can
independently tell whether this attempt's version tag landed on its own
verified head. Both user stories build directly on this.

---

## Phase 3: User Story 1 - An automatic release never reports on a run it did not cause (Priority: P1) 🎯 MVP

**Goal**: The automatic attempt identifies the release run it caused by
evidence (title token + time bound), never by recency, and reports
"released" from tag state rather than from a run it may have
misidentified.

**Independent Test**: Start a manual release dispatch and an automatic
attempt so both have a run in flight; confirm the automatic run's report
names only its own run under any outcome, and that a foreign run is never
adopted.

### Implementation for User Story 1

- [X] T007 [US1] In `.github/workflows/auto-release.yml`'s
      `dispatch-release` step (T005/T006), replace the existing
      run-discovery loop —
      `gh run list --workflow=release.yml -b main --json databaseId,status,conclusion -L 1 --jq '.[0].databaseId // empty'`
      — with the correlation poll from research.md D3: on each iteration
      (same ~60s-budget/5s-interval shape as today, per D9) call
      `gh run list --workflow=release.yml --json databaseId,displayTitle,createdAt,url -L 20`,
      then filter the rows to those whose `displayTitle` contains the
      exact substring `[attempt:${token}]` (the token minted in T005)
      **and** whose `createdAt` (parsed with
      `date -u -d "$createdAt" +%s`) is strictly greater than
      `$request_time` (captured in T005).

- [X] T008 [US1] From T007's filtered rows, set a `correlation` job
      output to exactly one of `found` (exactly one match — also set
      `correlated-run-id`/`correlated-run-url` outputs from that row's
      `databaseId`/`url`), `ambiguous` (two or more matches — FR-004), or
      `not-observed` (zero matches once the poll budget elapses — FR-005).
      Add `correlation`, `correlated-run-id`, and `correlated-run-url` to
      the job's `outputs:` block, replacing the current
      `release-outcome`/`release-run-id` outputs. Remove the now-unused
      `gh run watch "$run_id" --exit-status` call — research.md D5
      explicitly rejects a run's `conclusion` as the source of the
      release verdict.

- [X] T009 [US1] Rewrite `.github/workflows/auto-release.yml`'s `report`
      job to read `needs.dispatch-release.outputs.tag-matches` (T006)
      as the *only* input to the `released` decision, regardless of
      `needs.dispatch-release.outputs.correlation` (T008) — per FR-007
      and data-model.md's Release outcome table. When `tag-matches` is
      `true`, close the standing `auto-release:failed` issue exactly as
      today's `close_failure_on_success` does, independent of whether a
      correlated run was found. Replace the job's `RELEASE_OUTCOME`/
      `RELEASE_RUN_ID` env vars and the branches keyed on
      `released`/`stale-head`/`tip-unresolved`/`failed` with ones keyed
      on `TAG_MATCHES`/`CORRELATION`/`CORRELATED_RUN_ID`/
      `CORRELATED_RUN_URL` (this task covers only the `released` branch;
      US2 below covers the `false` branch's `branch-advanced`/
      `release-failed` split).

- [X] T010 [US1] In the `report` job's `released` branch (T009), link the
      correlated run only when `CORRELATION == found` (using
      `CORRELATED_RUN_ID`/`CORRELATED_RUN_URL` from T008) and otherwise
      state "released ${NEXT_VERSION} — own run not correlated"; when
      `CORRELATION` is `ambiguous` or `not-observed`, append that as
      diagnostic wording on whichever primary outcome T009/T012 produced
      (never a competing verdict, and never on its own when
      `tag-matches` is `true`) — per FR-006 and data-model.md's
      `correlation-ambiguous`/`correlation-not-observed` rows. The
      standing-failure-issue body's existing fields gain one new line:
      "Correlated run" — the log-link URL when `found`, or the literal
      string "not correlated (see tag state below)" otherwise.

**Checkpoint**: A manual dispatch and an automatic attempt racing each
other never cross-contaminate reports; "released" is decided from tag
state alone. User Story 1 is independently testable now.

---

## Phase 4: User Story 2 - A tag only ever lands on a verified head (Priority: P1)

**Goal**: `release.yml` refuses to create any tag unless the branch tip,
re-read live at the moment of tagging, still equals the commit it was
asked to release — closing the merge-in-the-window gap — and
`auto-release.yml` reports that refusal as the expected "branch advanced"
outcome rather than a failure.

**Independent Test**: Request a release naming a commit that is no
longer the branch tip; confirm no tag and no release are created, and
that the refusal names both the requested commit and the observed tip.

### Implementation for User Story 2

**⚠️ Check-2 ordering note (discovered during implement)**: research.md D7,
contracts/regression-gate.md, and data-model.md all describe Gate 53's
check 2 as requiring the tag-time `git ls-remote` comparison's line number
to be *after* the "Create tags" step marker. Taken literally that would
require the refusal to run once tags already exist, which contradicts
FR-010/FR-011/FR-014 ("refuses -- creating no exact tag") and this very
task's own placement (the step sits between "Validate version and plan
tags" and "Create tags", so it runs, and appears in the file, *before*
"Create tags"). T016's gate script implements the invariant that is
actually correct and actually true of the shipped code — the comparison
runs after full validation and before any tag mutation — documented in
the script's own docstring, rather than the literal "after Create tags"
wording. Flagging here for whoever reviews this PR.

- [X] T011 [US2] In `.github/workflows/release.yml`, insert a new step
      immediately before "Create tags" (after "Validate version and plan
      tags" has already run, so a stale-head request still gets full
      linting first), gated `if: inputs.commit != ''`: read
      `current_tip="$(git ls-remote origin refs/heads/main | cut -f1)"`
      live, and if it does not exactly equal `inputs.commit`, print an
      `::error::` line naming both the requested commit and the observed
      tip, then `exit 1` — creating no exact tag, no floating major tag,
      and publishing no release. Per research.md D4 and FR-010/FR-010a/
      FR-012/FR-014: this is a single equality check (no ancestry walk),
      it refuses identically whether `commit` is an ancestor, was
      force-pushed away, or was never on the branch, and leaving `commit`
      empty skips this step entirely (FR-015, unchanged manual behavior).
      `main` stays a literal here per research.md D6 (this workflow is
      not a published stage). Add a one-line comment pointing at
      `specs/048-correlated-release-dispatch/contracts/release-handover-contract.md`
      (FR-019).

- [X] T012 [US2] In `.github/workflows/auto-release.yml`'s `report` job,
      when T009's `TAG_MATCHES` is `false`, add the second independent
      read from research.md D5: `git ls-remote origin refs/heads/main`
      (report has no checkout — use the explicit-URL form,
      `git ls-remote https://github.com/${GITHUB_REPOSITORY}.git refs/heads/main | cut -f1`,
      so no new checkout step is needed in this job) compared against
      `$HEAD_SHA` (the verified head). Report `branch-advanced` (do
      **not** file or update the standing `auto-release:failed` issue —
      same class as today's `stale-head` skip, FR-013) when they differ;
      report `release-failed` (file/update the issue, classified
      "pipeline defect") when they still match.

- [X] T013 [US2] In `.github/workflows/auto-release.yml`'s
      `dispatch-release` step, remove the pre-dispatch short-circuit that
      reads `gh api "repos/${GITHUB_REPOSITORY}/commits/main"` and exits
      early with `release-outcome=tip-unresolved` or
      `release-outcome=stale-head` before calling `gh workflow run`. This
      check predates T011's tag-time refusal and T006/T012's tag-state
      classification, both of which now supersede it (the whole point of
      this feature is replacing "prevented only by the window being
      short" with real enforcement, per spec.md's Overview) — keeping it
      would let a second, divergent "is the head stale" answer exist
      alongside T011/T012's authoritative one. After this change,
      `dispatch-release` always attempts the dispatch (passing
      `commit=${VERIFIED_HEAD}` per T005) whenever it runs at all; if
      `main` truly moved before dispatch, T011 refuses the tag and
      T012 reports `branch-advanced` exactly as if the move had happened
      after dispatch instead.

- [X] T014 [US2] In the `report` job's `branch-advanced` output line
      (T012), name both the verified head that was requested and the
      tip observed at report time (mirroring T011's refusal wording,
      FR-012) instead of the current generic "main advanced past the
      verified head" sentence, so a maintainer can conclude "the branch
      moved on" from the report alone without opening run logs (SC-004).

**Checkpoint**: Both P1 guarantees hold independently. A commit named by
a request is either the one tagged, or nothing is tagged and the report
says why.

---

## Phase 5: User Story 3 - The maintainer's manual release path keeps working unchanged (Priority: P2)

**Goal**: A maintainer dispatching `release.yml` by hand, supplying only
today's three inputs, sees no new required field, no new refusal, and no
chance of being mistaken for an automatic attempt.

**Independent Test**: Dispatch `release.yml` supplying only `version`,
`breaking`, `breaking-notes`; confirm it behaves exactly as it does
today.

### Implementation for User Story 3

- [X] T015 [US3] Work through `specs/048-correlated-release-dispatch/quickstart.md`
      Scenario 3 against the shipped `.github/workflows/release.yml`
      (real dispatch on a fork/test repository if available, otherwise a
      careful read-through of the merged YAML against each of Story 3's
      three acceptance scenarios): confirm a dispatch supplying only the
      pre-existing three inputs tags the branch tip with no new refusal
      firing (T011's step never runs, since `inputs.commit` is `""`),
      produces the title `release <version> [attempt:]`, and cannot ever
      be matched by an automatic attempt's correlation search (T007) —
      no real, non-empty token equals the empty string between the
      colon and the closing bracket. No code changes are expected in
      this phase (research.md D10): this task exists to confirm T002/
      T004/T011's designs jointly deliver FR-015–FR-017 without a
      separate mechanism.

**Checkpoint**: All three user stories are independently demonstrated.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: The deterministic regression gate (FR-018/SC-005) and the
end-to-end validation the individual stories' checkpoints above don't
cover on their own.

- [X] T016 [P] Create `.github/scripts/verify-correlated-release-dispatch.py`
      following Gate 50/51's shape (a `scan()` function returning
      `(checked_count, failures)`, a `main()` printing `::error::` lines
      and summarizing, plain-text/regex checks over the raw YAML text —
      not a YAML-semantic diff, per contracts/regression-gate.md).
      Implement the four checks from research.md D7 /
      contracts/regression-gate.md, each naming exactly the FR-018
      clause it guards:
      1. `.github/workflows/release.yml` declares a `run-name:` that
         references both `inputs.version` and `inputs.attempt-token`.
      2. `.github/workflows/release.yml` contains a
         `git ls-remote origin refs/heads/main` comparison (or
         equivalent) whose line number is *after* the "Create tags" step
         marker line (catches the check being removed, or moved before
         checkout into a request-time check).
      3. `.github/workflows/auto-release.yml`'s correlation step
         references a `createdAt` (or equivalent time) field *and* an
         attempt-token match in the same step (catches recency-only or
         token-only selection).
      4. `.github/workflows/auto-release.yml`'s outcome computation
         reads a `refs/tags/` comparison (`git rev-parse` /
         `rev-parse -q --verify` against a tag ref) to decide `released`,
         rather than a run's `conclusion`/`status` field.
      This gate names `.github/workflows/release.yml` and
      `.github/workflows/auto-release.yml` directly (not the derived
      published-stage set — research.md D6).

- [X] T017 Add a `--self-test` mode to
      `.github/scripts/verify-correlated-release-dispatch.py` (T016),
      matching Gate 50/51's `check()`/`fixture()` helper shape: one
      in-memory "clean" fixture pair (a `run-name:` with the token, a
      correctly-ordered `ls-remote` check, a correlation step matching
      both token and `createdAt`, a `released` decision reading a tag
      comparison) asserted to pass with zero findings, plus one mutated
      fixture per check above (dropped token, tag-time check removed or
      reordered before "Create tags", token-only/recency-only
      correlation, outcome read from run conclusion instead of a tag),
      each asserted to fail naming only its own check's FR-018 clause
      and the offending line — per contracts/regression-gate.md's
      Self-test fixture shape and Constitution VIII.

- [X] T018 Register the new gate in `.github/workflows/lint-workflows.yml`
      as two steps immediately after Gate 51's self-test step (using the
      gate number confirmed in T001 — 53 unless T001's re-check found a
      collision), matching every existing gate's two-step pattern: a
      `# Gate <N> — ...` comment explaining what regression it prevents
      and why (matching the prose style of the Gate 50–52 comments
      immediately above it), a step running
      `python3 .github/scripts/verify-correlated-release-dispatch.py`,
      and a step running it again with `--self-test`, both gated
      `if: "!cancelled()"`.

- [X] T019 Run `python .github/scripts/run-local-gates.py` and confirm
      the new gate (T016–T018) is picked up automatically with no
      separate registration in that script (it derives its list from
      `lint-workflows.yml`), per FR-018 and contracts/regression-gate.md.

- [X] T020 [P] Add code comments at each remaining new mechanism this
      feature introduces — the correlation poll and tag-state check in
      `.github/workflows/auto-release.yml`'s `dispatch-release` job
      (T005–T008), and the outcome computation in its `report` job
      (T009–T010, T012, T014) — pointing at
      `specs/048-correlated-release-dispatch/contracts/release-handover-contract.md`
      as the one canonical contract for what each promises (FR-019),
      matching the pointer-comment style T002/T011 already establish in
      `release.yml`. Do not restate the contract's content in the
      comments — point at it.

- [ ] T021 Work through `specs/048-correlated-release-dispatch/quickstart.md`
      Scenarios 1 and 2 against the shipped workflows (on a fork or test
      repository able to dispatch both workflows), confirming: an
      automatic attempt never adopts a foreign/manual run under any
      dispatch ordering, including the same-version-retry edge case
      (Scenario 1, Acceptance Scenario 4); and the tag-time refusal fires
      only when the branch has genuinely advanced past the requested
      commit, including the queued-behind-another-release-run case
      (Scenario 2, step 5). Record the outcome (pass/fail per step) for
      the PR description.

      **Not run this cycle**: this implementation run's tooling has no
      `gh workflow run`/dispatch access (or a fork/test repository), so
      Scenarios 1 and 2 could not be driven for real. T015's manual-path
      scenario was instead validated by a read-through against the
      shipped YAML (see its own note). A maintainer with dispatch access
      should run this task for real before merge.

- [X] T022 Run `python .github/scripts/run-local-gates.py` (the full
      PR-time gate suite) and confirm it passes end to end, per
      CLAUDE.md's "Before pushing" instruction and SC-006 (no existing
      release behaviour — lint gates, tag-collision refusal, breaking-
      release rules, release-notes structure — regresses).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — confirms the gate number before
  anything writes it into a file (needed by T018, informational for T016).
- **Foundational (Phase 2)**: No dependency on Phase 1's outcome; T002 →
  T003 → T004 are sequential (same file, `.github/workflows/release.yml`);
  T005 → T006 are sequential (same file/job,
  `.github/workflows/auto-release.yml`'s `dispatch-release`); T005/T006
  can run in parallel with T002–T004 (different files). **BLOCKS all user
  stories.**
- **User Story 1 (Phase 3)**: Depends on Foundational (needs T002/T003's
  inputs+title and T005/T006's token/tag-matches). T007 → T008 → T009 →
  T010 are sequential (same job/file).
- **User Story 2 (Phase 4)**: Depends on Foundational (needs T004's
  conditional checkout ref and T006's `tag-matches`). T011 (release.yml)
  can be done in parallel with User Story 1's phase (different file from
  T007–T010). T012 → T013 → T014 depend on T009's `report`-job rewrite
  landing first (same job, avoids re-diverging the outcome logic) and on
  T006's `tag-matches`.
- **User Story 3 (Phase 5)**: Depends on Foundational + User Story 2
  (T011/T004) being in place; it is validation-only, no new code.
- **Polish (Phase 6)**: T016 → T017 → T018 → T019 are sequential (same
  new file, then its registration); both depend on User Story 1 and User
  Story 2 being implemented (the gate checks for patterns those phases
  introduce). T020 depends on all workflow edits (T002–T014) being final.
  T021 depends on User Story 1 + User Story 2. T022 runs last.

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational — no dependency on
  User Story 2.
- **User Story 2 (P1)**: Can start after Foundational — no dependency on
  User Story 1. The two guarantees are independent by design (spec.md:
  "fixing correlation does not narrow this window, and fixing this
  window does not stop a foreign run being adopted"), though both edit
  the same `report` job, so landing them as two sequential passes over
  that job (rather than two developers editing it simultaneously) avoids
  merge conflicts.
- **User Story 3 (P2)**: A consequence of how Foundational + User Story 2
  are built (research.md D10), not a separate implementation — validated
  only.

### Within Each User Story

- User Story 1: correlation poll → correlation outcome classification →
  report's `released` decision → report's log-link wording.
- User Story 2: release.yml's tag-time refusal (independent of the
  report-job changes) → report's `branch-advanced`/`release-failed`
  classification (depends on Foundational's `tag-matches`) → removing
  the superseded pre-dispatch shortcut → refusal wording.

### Parallel Opportunities

- T005/T006 (`auto-release.yml`) can run in parallel with T002–T004
  (`release.yml`) in Foundational.
- T011 (`release.yml`, User Story 2) can run in parallel with T007–T010
  (`auto-release.yml`, User Story 1) once Foundational is complete.
- T016 (new gate script) and T020 (comment pointers) touch different
  files and can run in parallel once the phases they check/reference are
  otherwise complete.

---

## Parallel Example: Foundational phase

```bash
# Launch together once Phase 1 (Setup) is done:
Task: "release.yml: add attempt-token and commit inputs, run-name, conditional checkout ref (T002-T004)"
Task: "auto-release.yml: mint attempt-token/request_time, add checkout + tag-matches check to dispatch-release (T005-T006)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (confirm the gate number).
2. Complete Phase 2: Foundational (CRITICAL — blocks both P1 stories).
3. Complete Phase 3: User Story 1.
4. **STOP and VALIDATE**: work through quickstart.md Scenario 1 against a
   test dispatch.
5. This alone fixes the correlation defect (spec.md's "the failure that
   corrupts the record") even before Story 2's tag-time refusal lands.

### Incremental Delivery

1. Setup + Foundational → both guarantees' shared infrastructure ready.
2. Add User Story 1 → validate independently (quickstart Scenario 1) →
   the correlation defect is fixed.
3. Add User Story 2 → validate independently (quickstart Scenario 2) →
   the tag-time window is closed.
4. Add User Story 3's validation pass → confirm the manual path never
   moved.
5. Add Polish (Gate 53 + its self-test + full comment pointers + full
   quickstart pass + the full local gate suite) → FR-018/SC-005's
   regression protection is in place before merge.

### Parallel Team Strategy

With two people (this repository's own concurrency note — CLAUDE.md caps
concurrent local agents at two):

1. Both complete Setup + Foundational together (small, sequential,
   fast).
2. Once Foundational is done: one person takes User Story 1
   (`auto-release.yml`'s `dispatch-release`/correlation), the other takes
   User Story 2's `release.yml` half (T011) — genuinely parallel, no
   shared file until User Story 2's `report`-job tasks (T012–T014), which
   should wait for User Story 1's `report`-job rewrite (T009) to land
   first.
3. Either person picks up Polish once both stories are in.

---

## Phase 7: Convergence

**Purpose**: `/speckit-converge` found two spec clauses tasks.md's original
Phase 3/4 tasks did not fully carry through into the shipped `report` job.
Both are wording/plumbing additions to the same job; neither requires
touching `release.yml` or Gate 53.

- [X] T023 Surface the request time in the report's ambiguous/not-observed
      diagnostic wording per FR-006 (partial). `dispatch-release`'s "watch"
      step already computes `request_time` (an epoch second, T005) but
      never exposes it as a job output. Add a human-readable job output
      (e.g. `request-time`, formatted with
      `date -u -d "@$request_time" +"%Y-%m-%dT%H:%M:%SZ"`) alongside
      `correlation`/`tag-matches`/`correlated-run-id`/`correlated-run-url`,
      thread it into the `report` job's env, and include it in the
      `correlation_note` wording whenever `CORRELATION` is `ambiguous` or
      `not-observed` — FR-006 requires the report "name the version
      requested and the time of the request", and today's wording names
      only the version. Update Gate 52's self-test
      (`.github/scripts/verify-auto-release-report.py`) scenarios that
      exercise `ambiguous`/`not-observed` to assert the new wording.

- [X] T024 Distinguish "the dispatch was rejected outright" from "the
      dispatch succeeded but no run was found" per SC-004 (partial).
      `dispatch-release`'s "watch" step (T007) sets no distinct signal
      when the `gh workflow run release.yml` call itself fails, versus
      when it succeeds but the correlation poll times out with zero
      matches — both currently collapse to `correlation=not-observed`
      with identical report wording, but SC-004 lists "release failed",
      "request rejected", and "run not observed" as three separately
      distinguishable outcomes. Add a `dispatch-rejected` job output
      (`true`/`false`, set before attempting correlation at all) and have
      the `report` job word that case distinctly (e.g. "the dispatch was
      rejected outright" rather than "own run was not observed within the
      correlation window") whenever `DISPATCH_REJECTED` is `true`. Update
      Gate 52's self-test with a scenario covering the rejected-dispatch
      case and confirm it fails on a mutation that drops the new
      distinction.

**Checkpoint**: Run `python .github/scripts/run-local-gates.py` again
after T023/T024 land — Gate 52's self-test must still pass 83/83 alongside
everything else.
