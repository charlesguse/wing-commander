# Tasks: Gate 59 resolves the dispatch idiom wherever it lives

**Input**: Design documents from `/specs/081-composite-aware-dispatch-gate/`
(plan.md, research.md, data-model.md, quickstart.md,
contracts/resolving-gate.md, contracts/dispatch-and-wait-outputs.md)

**Tests**: This feature's verification is deterministic gate scripts and
shell-execution harnesses with checked-in fixtures (Constitution VIII,
FR-007, FR-015, FR-025), not a conventional test suite. Gate/harness tasks
are listed inline with the implementation task they verify, matching this
repository's existing `verify-*.py`/`.sh` convention rather than a
separate TDD phase.

**Gate numbering**: the highest gate number wired into
`.github/workflows/lint-workflows.yml` as of this branch is Gate 98
(`grep -n "Gate [0-9]\{2,3\} —" .github/workflows/lint-workflows.yml`).
This feature's one new gate is **Gate 99** (research.md D8). Re-check
this at implementation time in case another in-flight branch has since
claimed it, and renumber if so.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on an
  incomplete task)
- **[Story]**: US1 (Gate 59 resolves through composites), US2 (the
  composite's widened outcome contract), US3 (the repoint and
  single-home enforcement)

## Path Conventions

GitHub Actions CI/CD pipeline infrastructure, no `src`/`tests` split.
Every path below is relative to the repository root.

---

## Phase 1: Setup

- [X] T001 Confirm the gate-number reservation above is still accurate:
  `grep -n "Gate 9[0-9]" .github/workflows/lint-workflows.yml` must show
  nothing above Gate 98. If it does, shift "Gate 99" to the next free
  number everywhere it appears in this file before starting Phase 4
  (User Story 3).

---

## Phase 2: Foundational

None. User Story 1 (the gate script) and User Story 2 (the composite and
its harness) touch disjoint files and share no prerequisite — both can
start immediately after Phase 1 and proceed in parallel. The one real
ordering constraint is a *story* dependency, not a blocking foundation:
**User Story 3 depends on both User Story 1 and User Story 2 being
complete** — the repoint it performs only passes Gate 59 once checks 3/5
resolve through composites (US1), and it only has the outputs it needs
to reproduce `report`'s six facts once the composite is widened (US2).
Do not start Phase 4 until Phases 3's and 3b's checkpoints both pass.

---

## Phase 3: User Story 1 - The gate follows the idiom into a composite (Priority: P1) 🎯 MVP

**Goal**: Gate 59 (`verify-correlated-release-dispatch.py`) resolves
checks 3 (correlation) and 5 (wait-before-tag-read) against
`auto-release.yml`'s `dispatch-release` job's own steps plus the shell of
any local composite those steps call, one level deep — so a pure
relocation of that shell passes and a deletion or weakening still fails,
from either location. Check 4 (tag-state) stays scoped to the job's own
text only (FR-027) and fails if found only in a composite.

**Independent Test**: `python3 .github/scripts/verify-correlated-release-dispatch.py --self-test`
passes its full fixture matrix, and a plain run against the current,
unrepointed tree still passes — this story ships before any shell
actually moves (spec.md's own framing: "the waiver above it has a path
to removal, even if no shell has moved yet").

### Implementation for User Story 1

- [X] T002 [US1] In `.github/scripts/verify-correlated-release-dispatch.py`,
  add a composite-resolution helper implementing research.md D3's
  three-outcome rule for a `uses: ./.github/actions/<name>` reference
  reached from the `dispatch-release` job's steps, one level deep: (a)
  the referenced `action.yml` does not exist on disk → hard fail,
  `::error::` naming the exact unresolvable path, never a pass and never
  read as "the invariant was deleted" (FR-004); (b) the path resolves and
  its `runs.steps[*].run` shell (or a further local `uses:` inside it)
  contains the checked construct → return that shell text tagged with
  the composite's own path; (c) the path resolves, the construct is
  absent from that level, AND the resolved composite's own steps contain
  a further local `uses:` to a *second* composite → hard fail,
  `::error::` naming that second-level reference as unresolved (the gate
  never opens a third file). Accept an injectable `resolve` mapping
  (composite path → text) so the self-test never touches real files
  (contracts/resolving-gate.md "Self-test fixture shape"); when omitted,
  resolve from the filesystem.
- [X] T003 [US1] Add corpus construction per research.md D1: walk
  `auto-release.yml`'s `dispatch-release` job's step list in file order.
  A `run:` step contributes its own text tagged
  `auto-release.yml:<line>`. A `uses:` step matching a local-composite
  reference (`./.github/actions/<name>`) is resolved via T002's helper
  and its shell spliced in at that position, tagged with the composite's
  own path. Any other `uses:` (e.g. `actions/checkout@v5`) contributes
  nothing. Build this spliced corpus for checks 3 and 5. Separately,
  build a check-4-only corpus containing *only* the job's own `run:`
  text (research.md D4, FR-027) — check 4 must never see composite text,
  for either its positive check (`TAG_REV_PARSE` present) or its
  forbidden-construct scan (`gh run watch`, `.conclusion`).
- [X] T004 [US1] Update `correlation_step_errors` (check 3) and
  `wait_before_tag_read_errors` (check 5) in
  `.github/scripts/verify-correlated-release-dispatch.py` to search T003's
  spliced corpus instead of `auto_lines`, keeping each check's existing
  substring/window logic and failure wording byte-for-byte unchanged
  (contracts/resolving-gate.md step 4 — only what text each check looks
  in changes, never what it looks for or how it phrases a failure).
  `tag_state_outcome_errors` (check 4) keeps searching only the job's own
  text (T003's check-4-only corpus).
- [X] T005 [US1] Add pass-path attribution (FR-005, research.md D2): when
  checks 3 or 5 pass, record which tagged source (`auto-release.yml` or
  the resolved composite's path) satisfied it, and have `run_gate()`
  print one line per check naming that location, e.g. "Gate 59: check 3
  (correlation) satisfied in
  .github/actions/wing-commander-dispatch-and-wait/action.yml". Check 4
  is always attributed to `auto-release.yml` (FR-027). This is additive
  to the existing pass-path `print()` — no existing failure-message
  wording changes.
- [X] T006 [US1] Give `contract_errors()` a `resolve=None` parameter and
  thread it through to T003's corpus construction; when `run_gate()`
  calls it with `resolve=None`, T002's helper falls back to reading
  `action.yml` files from the repository root.
- [X] T007 [US1] Add two new in-memory self-test fixtures per research.md
  D5: `CLEAN_COMPOSITE` (a resolved composite's shell text carrying
  checks 3 and 5's allowed constructs — the correlation loop's
  `createdAt`/token match and the `gh run view ... --json status` wait)
  and `CLEAN_AUTO_VIA_COMPOSITE` (a `dispatch-release` job whose
  correlation/wait step is a `uses:` reference to that composite instead
  of the inline `run:` `CLEAN_AUTO` carries today), wired through T002's
  injectable `resolve` mapping so no real file is touched.
- [X] T008 [US1] Extend `self_test()` in
  `.github/scripts/verify-correlated-release-dispatch.py` with the six
  new fixture cases from research.md D5's matrix, each asserted to fail
  naming only its own clause (SC-003) except the passing case:
  (a) clean, checks 3 & 5 relocated into `CLEAN_COMPOSITE` — passes,
  proving SC-001's first half;
  (b) check 3 weakened, composite-resolved — fails, recency clause only;
  (c) check 5 weakened, composite-resolved — fails, mid-flight-read
  clause only;
  (d) check 4's shell relocated into a composite, otherwise unweakened —
  fails, tag-state clause only (User Story 1 Acceptance Scenario 7,
  proving SC-001's second half);
  (e) the job's `uses:` names a composite path that does not exist —
  fails loudly naming that path, never a pass (SC-004);
  (f) the job's composite resolves but itself defers to a second-level
  `uses:` with no construct at the first level — fails loudly naming the
  second-level reference.
  The self-test now covers ten cases total (four existing, six new).
- [X] T009 [US1] Update the module docstring of
  `.github/scripts/verify-correlated-release-dispatch.py` per FR-024:
  document that checks 3 and 5 resolve through a called local composite
  one level deep, name which locations the gate searches, and state that
  check 4 stays scoped to the job's own text only (research.md D4) — so
  the next maintainer who moves this shell learns the rule from the gate
  itself.
- [X] T010 [US1] Run
  `python3 .github/scripts/verify-correlated-release-dispatch.py --self-test`
  and confirm all ten cases (T008) pass; then run
  `python3 .github/scripts/verify-correlated-release-dispatch.py`
  against the current, unrepointed tree and confirm it still passes
  (Acceptance Scenario 1 — the gate changes what it can see, not what is
  shipped today).

**Checkpoint**: Gate 59 resolves through composites for checks 3 and 5,
enforces check 4 job-only, and its self-test proves every branch on
checked-in fixtures. User Story 1 is independently shippable here — the
`single-home-waivers.json` entry now has a path to removal even though no
shell has moved yet.

---

## Phase 3b: User Story 2 - The shared composite carries the full dispatch outcome (Priority: P2)

**Goal**: `wing-commander-dispatch-and-wait/action.yml` additively widens
its outputs to carry the six facts `auto-release.yml`'s `report` job
reads today (dispatch-rejected, correlation as found/ambiguous/
not-observed, the correlated run's id, and the request time), plus a
caller-settable bounded wait on the uncorrelated path — with its two
existing outputs (`run-url`, `conclusion`) unchanged in name and meaning.

**Independent Test**: `bash .github/scripts/dispatch-and-wait-tests/run-tests.sh`
executes the composite's own shipped shell against a stubbed `gh` across
found/ambiguous/not-observed/dispatch-rejected/wait-exhausted, asserting
every declared output for each case — usable by `board-loop.yml`'s prove
job the day it lands, before any repoint happens.

### Implementation for User Story 2

- [ ] T011 [US2] Add the `uncorrelated-wait-seconds` input (default
  `"0"`) to `.github/actions/wing-commander-dispatch-and-wait/action.yml`'s
  `inputs:` block (contracts/dispatch-and-wait-outputs.md) — a bounded
  wait applied only when `correlation` never reaches `found`, so a
  caller reading state the dispatched run was expected to change can
  avoid reading it mid-flight. Default `0` preserves every existing
  caller's behaviour unchanged (FR-014).
- [ ] T012 [US2] Add four new outputs to the composite's `outputs:`
  block — `dispatch-rejected`, `correlation`, `correlated-run-id`,
  `request-time` — each sourced from `steps.watch.outputs.*` alongside
  the existing `run-url`/`conclusion` (data-model.md, FR-011, FR-026:
  each fact its own named output, no caller ever parses a structured
  value to read one).
- [ ] T013 [US2] Rewrite the composite's "Dispatch and correlate" step
  shell in `action.yml` to: (a) set `dispatch-rejected=true` and skip the
  correlation search entirely when `gh workflow run` itself fails
  (currently only echoes `::error::` and falls through); (b) track
  `correlation` explicitly as one of `found`/`ambiguous`/`not-observed`
  rather than only deriving emptiness on `run-url` (FR-011, FR-012 — never
  collapsed, never resolved by picking the most recent match); (c) emit
  `correlated-run-id` alongside `run-url` whenever `correlation` is
  `found`; (d) capture and emit `request-time` (ISO-8601) set before the
  dispatch call, reported in every case including `not-observed`; (e)
  after the terminal-status wait, when `correlation` never reached
  `found`, sleep the new `uncorrelated-wait-seconds` input's value before
  returning (FR-014).
- [ ] T014 [US2] Add the FR-028 deferred-hook paragraph to the composite's
  header comment (research.md D7): state that a generic post-wait
  verification hook — a caller-supplied "does the state I expected to
  change actually show it" check — was considered and deliberately
  deferred; this composite stays generic; a future caller needing that
  shape should extend the composite's contract rather than paste a second
  verification copy. Leave the existing "auto-release.yml is NOT yet
  repointed... T054" paragraph in place for now — User Story 3 removes it
  once the repoint actually lands.
- [ ] T015 [US2] Widen
  `.github/scripts/dispatch-and-wait-tests/run-tests.sh` (Gate 88) per
  contracts/dispatch-and-wait-outputs.md's scenario table: extend
  `run_case`/its assertions so the four existing scenarios
  (found/ambiguous/absent/timeout) also assert `dispatch-rejected`
  (`false`), `correlation` (`found`/`ambiguous`/`not-observed` per
  scenario), `correlated-run-id` (set only when `found`), and
  `request-time` (always set). Add two new scenarios: `dispatch-rejected`
  (stub `gh workflow run` failing → `dispatch-rejected=true`,
  `correlation=not-observed`, no correlation search performed) and
  `uncorrelated-wait honored` (set `uncorrelated-wait-seconds` and assert
  the composite's own shell actually delays before returning — e.g. by
  having the stub record a timestamp the test compares before/after).
- [ ] T016 [US2] Run
  `bash .github/scripts/dispatch-and-wait-tests/run-tests.sh` and confirm
  all six scenarios (T015) pass; confirm `board-loop.yml`'s existing
  prove-job call site, which reads only `run-url`/`conclusion` and omits
  `uncorrelated-wait-seconds`, needs no edit (SC-009).

**Checkpoint**: The composite's outputs contract carries every fact
`report` needs, proven by execution against a stubbed `gh`, with its
existing two outputs unchanged. User Story 2 is independently shippable
here — usable by `board-loop.yml` today, before any repoint.

---

## Phase 4: User Story 3 - auto-release.yml reaches the idiom through its one home (Priority: P3)

**Goal**: `auto-release.yml`'s `dispatch-release` job is repointed at the
shared composite, its `report` job produces byte-identical
maintainer-facing output for every dispatch outcome, the tag-state
invariant gains a runtime proof (Gate 99), the `dispatch-and-wait` waiver
is removed, and Gate 60 starts failing if the inline copy ever returns.

**Depends on**: Phase 3 (User Story 1 — Gate 59 must resolve through
composites before this repoint can pass it) and Phase 3b (User Story 2 —
the repoint reads outputs that exist only once the composite is widened).

**Independent Test**: the composite's behavioural harness (T016), the new
runtime harness proving the tag-state invariant by execution (T019), and
the release-dispatch gate against the repointed tree (T026) all pass; the
waiver is gone and Gate 60 is green (T022); Gate 60 fails on a fixture
where the inline copy is restored (already proven by Gate 60's own
existing structural scan, per research.md D10).

### Implementation for User Story 3

- [ ] T017 [US3] Split `auto-release.yml`'s `dispatch-release` job's
  single "Dispatch release.yml and correlate its run" step (currently
  `.github/workflows/auto-release.yml:1465-1576`) into two steps per
  research.md D9:
  1. **"Dispatch and correlate release.yml"** — a
     `uses: ./.github/actions/wing-commander-dispatch-and-wait` step
     minting the attempt token (`${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}`,
     unchanged), passing `workflow-file: release.yml`,
     `workflow-inputs` carrying `version`, `breaking: false`,
     `breaking-notes: ""`, `commit` (`VERIFIED_HEAD`),
     `attempt-token: <token>`, and `uncorrelated-wait-seconds: "90"`
     (preserving today's fixed 90-second uncorrelated-path wait exactly).
  2. **"Decide release outcome from tag state"** — a `run:` step that
     reads step 1's `correlated-run-url`/`conclusion`/`correlation`/
     `correlated-run-id`/`request-time`/`dispatch-rejected` outputs as
     passthrough env vars (never recomputed) plus `VERSION`/
     `VERIFIED_HEAD`, independently `git fetch`/`rev-parse`-compares the
     tag against `VERIFIED_HEAD` exactly as the current inline shell does
     (today's lines 1561-1567), and writes the job's own `outputs:`
     block from these values (FR-019, FR-027 — the tag-state decision
     never reads the composite's `conclusion` or any run-status value as
     an input to the *decision*, only to the *passthrough*).
- [ ] T018 [US3] Update `dispatch-release`'s `outputs:` block
  (currently `.github/workflows/auto-release.yml:1442-1457`) so each
  output is a passthrough of step 2's own output, keeping every name
  unchanged (`correlation`, `correlated-run-id`, `correlated-run-url` —
  sourced from step 1's `run-url` — `tag-matches`, `request-time`,
  `dispatch-rejected`) per FR-018. Confirm the `report` job (needs
  `dispatch-release`, reads these six names at
  `auto-release.yml:1624-1632`) requires no edit.
- [ ] T019 [US3] Create
  `.github/scripts/verify-auto-release-tag-state-runtime.py` (Gate 99),
  following Gate 67's shape
  (`.github/scripts/verify-auto-release-credential-step.py`): use
  `wc_shell_harness.find_step` to extract `dispatch-release`'s "Decide
  release outcome from tag state" step (T017) from `auto-release.yml`,
  then `run_step` to execute it with a stubbed `git` on `PATH` for three
  scenarios — tag present and pointing at `VERIFIED_HEAD` (`tag-matches`
  must be `true`), tag present but pointing elsewhere (`tag-matches` must
  be `false`), tag absent (`tag-matches` must be `false`) — proving
  FR-025's tag-state invariant at runtime, not just resolving its text.
  Add a mutation-kill fixture (matching Gate 67's `MUTATIONS` precedent)
  that swaps the tag comparison for a run-conclusion check and confirms
  the suite then fails.
- [ ] T020 [US3] Wire Gate 99 into
  `.github/workflows/lint-workflows.yml`'s PR-time gate job, immediately
  after Gate 98's step, with `if: "!cancelled()"` (the same sequential
  convention every other gate uses — never `continue-on-error`). No new
  `paths:` entry is needed: the existing PR-time trigger already covers
  `.github/workflows/**` and `.github/scripts/**`
  (`lint-workflows.yml:19-29`). Confirm `run-local-gates.py` and
  `verify-gate-wiring.py` pick it up automatically.
- [ ] T021 [US3] Remove the `.github/workflows/auto-release.yml` /
  `dispatch-and-wait` entry (issue #408) from
  `.github/scripts/single-home-waivers.json` — the entry whose `reason`
  field states "Remove this waiver when T054 lands" (research.md D10,
  FR-020).
- [ ] T022 [US3] Run `python3 .github/scripts/verify-single-home-idioms.py`
  and confirm it passes with zero `dispatch-and-wait` waivers — Gate 60's
  existing `check_dispatch_and_wait` structural scan (unchanged code,
  `.github/scripts/verify-single-home-idioms.py:501-518`) now finds no
  inline copy left in `auto-release.yml` because T017 moved it (FR-021).
- [ ] T023 [US3] Remove the composite's header-comment paragraph stating
  `auto-release.yml`'s `dispatch-release` job is "NOT yet repointed" (the
  T054-blocker note, `.github/actions/wing-commander-dispatch-and-wait/action.yml:10-17`)
  now that T017 has landed the repoint (research.md D7).
- [ ] T024 [US3] In `specs/057-autonomous-board-loop/tasks.md`, mark T054
  and the second half of T056 done: change both from `- [ ]` to `- [X]`
  and replace each task's blocker note with a one-line pointer to this
  feature (`specs/081-composite-aware-dispatch-gate`), per this
  repository's canonical-pointer convention (FR-023, research.md D11).
- [ ] T025 [US3] Add a note to
  `specs/048-correlated-release-dispatch/contracts/regression-gate.md`'s
  "five checks" table stating that checks 3 and 5 now resolve through a
  called composite (pointing at
  `specs/081-composite-aware-dispatch-gate/contracts/resolving-gate.md`),
  and that runtime proof for all three invariants now exists (pointing at
  Gate 88 and Gate 99) — superseding that document's "does not
  re-implement or simulate" Non-goals framing for checks 3 and 5 only
  (FR-023, research.md D11).
- [ ] T026 [US3] Run `python .github/scripts/run-local-gates.py` and
  confirm every gate passes on the repointed tree, including Gate 59
  (T002-T010), Gate 88 (T015), and the new Gate 99 (T019), with no gate
  skipped, waived, or newly excluded (SC-007).
- [ ] T027 [US3] Side-by-side report-text comparison (quickstart.md
  step 4): for each of released / branch-advanced / dispatch-failed /
  dispatched-but-no-tag, diff the `report` job's rendered summary before
  and after the repoint using the same fixed inputs. Confirm zero
  differences (FR-018, SC-005).
- [ ] T028 [US3] After this feature's PR merges, re-drive
  `auto-release.yml` once (`gh workflow run auto-release.yml` —
  `workflow_dispatch: {}` with no required inputs, research.md D12) and
  record the resulting run's URL and outcome on the PR or lifecycle issue
  #595, per CLAUDE.md's "prove" step (FR-022, SC-008). NOT DONE until
  merge — this is the one step in this feature that cannot be proven
  before the tree lands on `main`.

**Checkpoint**: All three user stories are shipped. The repository
contains exactly one copy of the dispatch-correlate-wait idiom, Gate 60
enforces that with zero waivers, and the full PR-time gate suite is green
with nothing newly excluded.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T029 [P] Confirm SC-009: diff
  `.github/actions/wing-commander-dispatch-and-wait/action.yml`'s inputs
  and outputs against pre-feature `main` (`git diff origin/main --
  .github/actions/wing-commander-dispatch-and-wait/action.yml`) — every
  existing input/output name and meaning is unchanged; only the five new
  entries from User Story 2 (T011, T012) are additions.
- [ ] T030 [P] Confirm FR-009: `git diff origin/main --
  .github/scripts/verify-correlated-release-dispatch.py` shows no edits
  inside `run_name_errors` or `tag_time_check_errors` (checks 1 and 2,
  `release.yml`-only) — their behaviour and failure messages are
  untouched by this feature.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: None — see Phase 2's note. Phases 3 and 3b
  may proceed in any order or in parallel once Phase 1 completes.
- **User Story 1 (Phase 3)** and **User Story 2 (Phase 3b)**: Each
  depends only on Setup. No dependency on each other — disjoint files.
- **User Story 3 (Phase 4)**: Depends on BOTH Phase 3 and Phase 3b
  completing (their checkpoints must pass first).
- **Polish (Phase 5)**: Depends on Phase 4.

### Within Each User Story

- User Story 1's tasks (T002-T009) mostly edit the same file in sequence
  (each builds on the prior task's helper/corpus); T010 validates the
  whole story.
- User Story 2's tasks (T011-T014) edit the composite in sequence; T015
  (the harness) depends on T011-T014's shape; T016 validates the story.
- User Story 3's tasks are a single sequential chain: the repoint (T017,
  T018) must land before the new runtime gate can extract its subject
  step (T019), before that gate can be wired (T020), before the waiver
  removal is honest (T021, T022), before the header/provenance notes are
  accurate (T023-T025), before final validation (T026-T028).

### Parallel Opportunities

- Phase 3 (User Story 1) and Phase 3b (User Story 2) can be worked by
  two people/agents at once — no shared file, no shared task.
- T029 and T030 (Polish) are independent of each other.

---

## Parallel Example: Phase 3 vs Phase 3b

```bash
# After Phase 1 (Setup) completes, start both stories at once:
Task: "T002-T010 — Gate 59 resolves through composites (.github/scripts/verify-correlated-release-dispatch.py)"
Task: "T011-T016 — widen the dispatch-and-wait composite's outputs (.github/actions/wing-commander-dispatch-and-wait/action.yml, .github/scripts/dispatch-and-wait-tests/run-tests.sh)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 3: User Story 1.
3. **STOP and VALIDATE**: Gate 59's ten-case self-test passes; a plain
   run against the current tree still passes.
4. This alone unblocks the `single-home-waivers.json` entry's path to
   removal, even before any shell moves — the MVP is the gate stopping
   being a pin on one file's text.

### Incremental Delivery

1. Setup → Foundation confirmed (none needed).
2. User Story 1 → validate independently → Gate 59 resolves through
   composites (MVP).
3. User Story 2 (can land before or in parallel with US1) → validate
   independently → the composite's contract is usable by any caller,
   including `board-loop.yml`, immediately.
4. User Story 3 (only after both US1 and US2 checkpoints pass) →
   validate independently → the repoint lands, the waiver is gone, Gate
   60 is fully armed.
5. Polish → confirm nothing outside this feature's declared scope moved.

### Parallel Team Strategy

With two developers/agents:

1. Both complete Setup together (trivial, T001 alone).
2. Developer/Agent A: User Story 1 (Phase 3).
   Developer/Agent B: User Story 2 (Phase 3b).
3. Once both checkpoints pass, either takes User Story 3 (Phase 4) —
   it is a single sequential chain, not further parallelizable.
