---

description: "Task list for The Loop's Own Code Comes From a Trusted Commit — Composite Resolution in board-loop's Item-Branch Jobs"
---

# Tasks: The Loop's Own Code Comes From a Trusted Commit — Composite Resolution in board-loop's Item-Branch Jobs

**Input**: Design documents from `/specs/086-trusted-composite-resolution/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/trusted-copy-checkout.md, contracts/gate-99.md, contracts/documentation-updates.md, quickstart.md

**Tests**: Not requested. This feature has no application test suite — its
verification is Gate 99 itself (Phase 5) plus the local gate suite and the
quickstart.md drills (some of which need a real dispatched run against a
disposable/test repository and are called out as such rather than modeled
as checkbox tasks).

**Organization**: One workflow file (`.github/workflows/board-loop.yml`)
carries every job this feature touches, so tasks are grouped by user story
per spec.md, but within a story they are inherently sequential edits to the
same file (no `[P]` — a same-file edit is not safely parallelizable).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Line numbers cited below are as of `main` at the time this task list was
  written (research.md/contracts already reference the same file); if the
  file has moved on, locate steps by name (`Checkout`, `Checkout the PR
  branch`, `Snapshot helper scripts (before any agent runs)`) rather than
  by line number.

## Path Conventions

Single project (a GitHub Actions pipeline repository). All edits are under
`.github/` and the repository-root `.gitignore` — no `src/`/`tests/` tree
applies.

---

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 [P] Add a `.wc-pristine-repo/` entry to `.gitignore` so no `git
      add` invocation in any board-loop job — including the fixer and
      review-fixup agents' own `Bash(git add:*)` tool grant — can ever
      stage the sidecar into a board item's branch or pull request
      (FR-007; research.md D4; contracts/trusted-copy-checkout.md
      "Non-staging guarantee").

**Checkpoint**: `.gitignore` lists the sidecar path before any job gains a
checkout step that could populate it.

---

## Phase 2: Foundational (Blocking Prerequisites)

No tasks. The sidecar checkout is a fixed, repeated `actions/checkout@v5`
step shape (contracts/trusted-copy-checkout.md), not a shared script or
composite action — plan.md's Complexity Tracking records that extracting
it into a composite would need its own `uses:` reference, which begs the
exact resolution question this feature answers. There is nothing to build
once before per-job work begins beyond T001.

---

## Phase 3: User Story 1 - The loop's judging code cannot be edited by the branch it judges (Priority: P1) 🎯 MVP

**Goal**: Every job whose workspace holds board-item content at some point
— `fix` (resume path onward, and every post-agent step on both paths),
`review`, `readiness` — resolves the loop's own composites from a checkout
of this repository at `github.sha`, never from the item's own branch.

**Independent Test**: quickstart.md step 4 — on a disposable/test
repository, put a branch through `review`/`readiness` whose diff replaces
one of the loop's composites and one judging helper with a version that
would visibly misbehave; confirm the trusted behaviour runs, never the
branch's. Locally, `grep -n 'uses: \./\.github/actions/'
.github/workflows/board-loop.yml` returns no match inside the `fix`,
`review`, or `readiness` job bodies (quickstart.md step 2, partial).

### Implementation for User Story 1

- [ ] T002 [US1] In the `fix` job of `.github/workflows/board-loop.yml`,
      add the sidecar checkout step immediately after the existing
      "Snapshot helper scripts (before any agent runs)" step (~line 1761)
      and before "Fetch main / checkout the fix branch" — the step that
      switches the workspace to the item's own branch on the resume path.
      Exact shape (contracts/trusted-copy-checkout.md "Step shape"):
      `name: Checkout board-loop's own trusted copy (composites)`, `uses:
      actions/checkout@v5`, `with: ref: ${{ github.sha }}`, `path:
      .wc-pristine-repo`, `persist-credentials: false` — no
      `fetch-depth: 0`, no `token:`/`repository:` override, no
      `continue-on-error:` and no skipping `if:` (FR-002/FR-003/FR-006).
      Immediately follow it with the provenance line: `echo "board-loop:
      composites resolved from $(git -C .wc-pristine-repo rev-parse HEAD)
      at ref ${{ github.sha }}." >> "$GITHUB_STEP_SUMMARY"` (FR-013).
      Add a one-line comment above the step: "see this file's header for
      why every job does this" (placeholder until T024 writes the header;
      contracts/documentation-updates.md "Pointer sites").
- [ ] T003 [US1] In the `fix` job, rewrite every `uses:
      ./.github/actions/<name>` reference (14 call sites: two
      `wing-commander-context` calls at ~1774/1899, `wing-commander-board-labels`
      ~1783, `wing-commander-issue-context` at ~1835 and ~2131,
      `wing-commander-tool-args` ~1842, `wing-commander-turn-ceiling` ~1850,
      `wing-commander-refresh-remote` ~1908,
      `wing-commander-post-agent-credential-status` ~1915,
      `wing-commander-agent-verdict` ~1923, `wing-commander-metrics-summary`
      ~1931, `wing-commander-board-stop-check` ~1998, and two
      `wing-commander-outstanding-task-item` calls at ~2101/~2194) to `uses:
      ./.wc-pristine-repo/.github/actions/<name>` (FR-001; must land after
      T002 so the sidecar the rewritten references depend on already
      exists).
- [ ] T004 [US1] In the `review` job, add the same sidecar checkout +
      provenance step immediately after its own "Snapshot helper scripts
      (before any agent runs)" step (~line 2260), before the job's first
      composite reference — same exact shape and pointer comment as T002.
- [ ] T005 [US1] In the `review` job, rewrite every `uses:
      ./.github/actions/<name>` reference (23 call sites across the main
      review pass and the review-fixup leg: `wing-commander-context`,
      `wing-commander-board-labels`, `wing-commander-issue-context`,
      `wing-commander-tool-args`, `wing-commander-turn-ceiling`,
      `wing-commander-post-agent-credential-status`,
      `wing-commander-agent-verdict`, `wing-commander-metrics-summary`
      (first cluster, ~2273-2460), three `wing-commander-durable-failure-issue`
      calls and three `wing-commander-outstanding-task-item` calls
      interleaved, and `wing-commander-board-stop-check` (~2795-2871), then
      a second cluster for the review-fixup leg: `wing-commander-tool-args`,
      `wing-commander-turn-ceiling`, `wing-commander-context`,
      `wing-commander-refresh-remote`,
      `wing-commander-post-agent-credential-status`,
      `wing-commander-agent-verdict`, `wing-commander-metrics-summary`
      (~2976-3061)) to the sidecar-relative form (FR-001; after T004).
- [ ] T006 [US1] In the `readiness` job, add the same sidecar checkout +
      provenance step immediately after its own "Snapshot helper scripts
      (before any agent runs)" step (~line 3180) — same exact shape and
      pointer comment as T002.
- [ ] T007 [US1] In the `readiness` job, rewrite every `uses:
      ./.github/actions/<name>` reference (6 call sites:
      `wing-commander-context`, `wing-commander-board-labels`,
      `wing-commander-board-stop-check`, `wing-commander-issue-context`,
      `wing-commander-outstanding-task-item`, `wing-commander-metrics-summary`,
      ~3193-3481) to the sidecar-relative form (FR-001; after T006).

**Checkpoint**: `fix`, `review`, and `readiness` — the jobs whose workspace
holds board-item content — never resolve a composite from that workspace
again. This is the primary deliverable (Principle V; plan.md Constitution
Check).

---

## Phase 4: User Story 2 - Adding a composite to these jobs never breaks an item already in flight (Priority: P1)

**Goal**: Complete FR-011's uniform, allowlist-free coverage across every
remaining board-loop job (`select`, `triage`, `route`, `prove-gate`,
`prove`) so that no board-loop job — not just the three US1 touches —
carries a branch-age precondition for a future composite addition (SC-005),
and so Gate 99 (Phase 5) can enforce the rule as one unconditional
file-wide statement with no per-job list to maintain.

**Independent Test**: quickstart.md step 5 — cut an item branch from a
commit predating one of the composites `review`/`readiness` reference (or
delete that composite's directory on the test branch), drive it through
`review` and `readiness`, and confirm both complete rather than failing to
locate the action. (This scenario is already satisfied by Phase 3's
implementation; this phase's own check is the file-wide grep below, which
confirms the same guarantee extends to every other job so a future job
added to this file inherits it automatically.)

### Implementation for User Story 2

- [ ] T008 [US2] In the `select` job, add the sidecar checkout +
      provenance step immediately after its initial "Checkout" step (~line
      103) — these jobs have no helper-script snapshot to sit beside
      (research.md D2), so the sidecar checkout follows the job's own
      first checkout directly.
- [ ] T009 [US2] In the `select` job, rewrite its 2 `uses:
      ./.github/actions/...` references (`wing-commander-context` ~141,
      `wing-commander-metrics-summary` ~748) to the sidecar-relative form
      (after T008).
- [ ] T010 [US2] In the `triage` job, add the sidecar checkout +
      provenance step immediately after its initial "Checkout" step (~line
      849).
- [ ] T011 [US2] In the `triage` job, rewrite its 10 `uses:
      ./.github/actions/...` references (~857-1140) to the
      sidecar-relative form (after T010).
- [ ] T012 [US2] In the `route` job, add the sidecar checkout + provenance
      step immediately after its initial "Checkout" step (~line 1272).
- [ ] T013 [US2] In the `route` job, rewrite its 11 `uses:
      ./.github/actions/...` references (~1279-1509) to the
      sidecar-relative form (after T012).
- [ ] T014 [US2] In the `prove-gate` job, add the sidecar checkout +
      provenance step immediately after its initial "Checkout" step (~line
      3517).
- [ ] T015 [US2] In the `prove-gate` job, rewrite its 1 `uses:
      ./.github/actions/...` reference (`wing-commander-context` ~3524) to
      the sidecar-relative form (after T014).
- [ ] T016 [US2] In the `prove` job, add the sidecar checkout + provenance
      step immediately after its initial "Checkout" step (~line 3658).
- [ ] T017 [US2] In the `prove` job, rewrite its 5 `uses:
      ./.github/actions/...` references (~3665-3837) to the
      sidecar-relative form (after T016).
- [ ] T018 [US2] Confirm `resolve-model` gains no checkout step and no
      rewrite: it carries zero `uses: ./.github/actions/...` references
      today and none are added by this feature (research.md D3) — leave it
      untouched and note that Gate 99's rule (b) applies to it automatically,
      with no gate edit, the day it ever gains one.

**Checkpoint**: `grep -n 'uses: \./\.github/actions/'
.github/workflows/board-loop.yml` returns zero matches anywhere in the
file (quickstart.md step 2, full run). Every job that resolves a composite
does so from `.wc-pristine-repo`; no per-job allowlist exists anywhere in
this feature's own code.

---

## Phase 5: User Story 3 - A gate keeps the rule true after this session (Priority: P2)

**Goal**: A registered, self-testing gate (Gate 99) fails when any
reference in `board-loop.yml` resolves from the workspace instead of the
trusted copy, when the trusted-copy checkout is missing or misplaced, or
when it is not fail-closed — so a future edit that reintroduces the defect
is caught mechanically rather than relying on review.

**Independent Test**: Acceptance Scenarios 1-3 of User Story 3 — the gate
passes on the shipped workflow; a mutation that reintroduces a
workspace-resolved reference, or one that drops/reorders the trusted-copy
checkout, makes the gate fail and name the offending job and reference.

### Implementation for User Story 3

- [ ] T019 [US3] Create `.github/scripts/verify-board-loop-composite-provenance.py`
      (Gate 99) implementing, over `.github/workflows/board-loop.yml` and
      this repository's own `.gitignore` (contracts/gate-99.md "Rules"):
      (a) no line anywhere in the file matches `uses:
      ./.github/actions/` (the raw, workspace-relative form) —
      file-wide and unconditional, no per-job allowlist (FR-001, FR-011);
      (b) every job containing a `uses:
      ./.wc-pristine-repo/.github/actions/...` reference contains the
      canonical `Checkout board-loop's own trusted copy (composites)` step
      at a step index lower than every such reference, every
      `wing-commander-context` call, and every
      `anthropics/claude-code-action@` step in that same job (FR-002,
      FR-011); (c) that step's `with.ref` is exactly `${{ github.sha }}`
      (FR-003); (d) that step carries no `continue-on-error: true` and no
      `if:` that could skip it while a dependent reference still runs
      (FR-006); (e) `.gitignore` contains an entry matching
      `.wc-pristine-repo` (FR-007). Follow the existing
      `verify-board-loop-helper-provenance.py` (Gate 98) module's own
      conventions (`wc_shell_harness` imports, `WORKFLOW` constant, `yaml`
      parsing) where they transfer, but do not inherit its `JOBS = (...)`
      per-job-allowlist shape (research.md D5) — Gate 99 has no such tuple.
- [ ] T020 [US3] Add a `--self-test` mode to the same script implementing
      the 7 mutations of research.md D7 / data-model.md "Gate 99 Fixture
      Set", each asserted caught and attributed to its own rule, plus a
      baseline assertion that the unmutated, shipped file is clean first:
      1. reintroduce one raw `uses:
         ./.github/actions/wing-commander-context` in a job that currently
         uses the sidecar form — must fail, naming the job and the line;
      2. move the sidecar checkout step to after a composite reference in
         one job — must fail;
      3. drop the sidecar checkout step entirely from a job that still
         carries a `.wc-pristine-repo`-relative reference — must fail;
      4. change the sidecar checkout's `ref:` to a literal branch name (or
         blank it) — must fail;
      5. add `continue-on-error: true` to the sidecar checkout step — must
         fail;
      6. remove the `.gitignore` entry for the sidecar path — must fail;
      7. widen the file-wide ban in rule (a) to tolerate a second exempted
         pattern — must fail, proving the rule admits no allowlist
         (FR-010, read onto Gate 99's own design per contracts/gate-99.md
         "Self-test").
- [ ] T021 [US3] Register Gate 99 in `.github/workflows/lint-workflows.yml`
      as two steps immediately after Gate 98's block, using exactly the
      comment and step names in contracts/gate-99.md (the `# Gate 99 —
      ...` comment block, `Gate 99 — every uses: ./.github/actions/
      reference in board-loop.yml resolves from the trusted copy, never
      the workspace`, and `Gate 99 self-test — ...`), each with `if:
      "!cancelled()"` and calling the script from T019/T020 with and
      without `--self-test`.
- [ ] T022 [US3] Append one sentence to Gate 98's existing comment block in
      `.github/workflows/lint-workflows.yml` (immediately before Gate 99's
      own block) pointing at Gate 99 for the composite half of the same
      provenance property (FR-014; contracts/documentation-updates.md
      "Pointer sites"). Do not otherwise edit Gate 98's scope, allowlist,
      or self-test (spec.md Out of Scope).

**Checkpoint**: `python3
.github/scripts/verify-board-loop-composite-provenance.py` and the same
command with `--self-test` both exit 0 against the shipped tree; `python3
.github/scripts/run-local-gates.py` and `verify-gate-wiring.py` pick up
both new steps automatically, with no manifest edit beyond T021/T022
(contracts/gate-99.md "Reachability"; SC-004).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: FR-014's documentation pointers and the final integration
checks that span every phase above.

- [ ] T023 Append the canonical trusted-copy-rule paragraph to
      `.github/workflows/board-loop.yml`'s existing file header (today
      lines 1-13): what the sidecar is (a checkout of this repository at
      `github.sha` into `.wc-pristine-repo`, never `./.github/actions/...`
      directly), why (established before any credential mint and any agent
      step, gitignored so no `git add` can stage it into an item's
      branch), that it sits alongside — not instead of — the existing
      `$RUNNER_TEMP/wc-pristine` helper-script/schema snapshot (#583),
      naming Gate 98 and Gate 99 as the two halves of the same provenance
      property, and pointing at
      `specs/086-trusted-composite-resolution/{spec.md,plan.md,research.md}`
      the way the existing header already points at spec 057's own
      documents (FR-014; contracts/documentation-updates.md "Canonical
      statement"). This is the one place the rule's rationale is written
      in prose.
- [ ] T024 Revisit the one-line pointer comment placed above each of the 8
      sidecar checkout steps (added inline during T002/T004/T006/T008/T010/T012/T014/T016)
      and confirm each reads "see this file's header for why every job
      does this" with no restated rationale, now that T023 has written the
      header they point at (contracts/documentation-updates.md "Pointer
      sites").
- [ ] T025 [P] Append one sentence to
      `.github/actions/wing-commander-context/action.yml`'s header, after
      the existing "Verified self-checkout snippet" block: board-loop.yml
      is not a published stage and is not called through this composite's
      `pipeline-repo`/OIDC mechanism at all — it resolves its own
      composites the same way, from its own repository at `github.sha`;
      see board-loop.yml's own header (FR-014;
      contracts/documentation-updates.md "Pointer sites").
- [ ] T026 Run the `.gitignore` negative check from quickstart.md step 3:
      `mkdir .wc-pristine-repo && touch .wc-pristine-repo/probe && git add
      -A && git status --porcelain` shows nothing staged for that path,
      then `rm -rf .wc-pristine-repo` to clean up; separately confirm `git
      check-ignore -v .wc-pristine-repo` reports the `.gitignore` match
      from T001.
- [ ] T027 Run `python .github/scripts/run-local-gates.py` (the full PR-time
      gate suite, per CLAUDE.md "Before pushing") and confirm every gate,
      including Gate 98 (unchanged) and Gate 99 (new), passes on the
      shipped tree (quickstart.md step 1, final integration check;
      SC-004).

**Not modeled as tasks** — quickstart.md steps 4-6 (User Story 1's
judging-surface-rewrite drill, User Story 2's old/deleted-composite drill,
and the SC-002/SC-006 byte-identical-behaviour and no-sidecar-in-PR spot
check) each need a real dispatched run of `board-loop.yml` against a
disposable/test repository the implementer owns — never against this
repository. These are manual validation drills to run after this feature
merges, not local-gate-checkable work, and are noted here for the
implementer rather than skipped silently.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — T001 can start immediately, and in
  parallel with everything else (different file).
- **Foundational (Phase 2)**: Empty — nothing blocks Phase 3 beyond T001
  existing before any job's checkout step is exercised.
- **User Story 1 (Phase 3)**: Depends on Setup (T001) only conceptually
  (FR-007 must hold before `fix`'s later commits are safe); no code
  dependency. This is the MVP phase.
- **User Story 2 (Phase 4)**: Independent of Phase 3's content — a
  different set of jobs in the same file — but sequenced after Phase 3 here
  so the file's edit history reads as "item-branch jobs first, then the
  rest," matching spec.md's own framing of the item-branch jobs as the
  primary exposure.
- **User Story 3 (Phase 5)**: Depends on Phases 3 and 4 being complete —
  Gate 99 rule (a) is a file-wide, unconditional ban with no allowlist, so
  it cannot pass the shipped file (T027) until every `uses:
  ./.github/actions/...` reference anywhere in `board-loop.yml` has been
  rewritten.
- **Polish (Phase 6)**: Depends on Phases 3-5 all being complete (T023
  names Gate 98 and Gate 99 both; T027 runs the full suite including Gate
  99).

### Within Each Job (Phases 3-4)

- The sidecar checkout task for a job (e.g., T002) must land before that
  same job's rewrite task (e.g., T003) — the rewritten references must
  have something to resolve from.

### Parallel Opportunities

- T001 (`.gitignore`) can run in parallel with every other task (different
  file).
- T025 (`wing-commander-context/action.yml` header) can run in parallel
  with T023/T024 (`board-loop.yml` header and pointer comments) — different
  file.
- No other task pair is safely parallel: every task in Phases 3-5 and
  T023/T024 edits `.github/workflows/board-loop.yml`, and T019/T020 (same
  new script) and T021/T022 (same `lint-workflows.yml` region) are each a
  sequential pair.

---

## Parallel Example: Setup alongside User Story 1

```bash
# T001 and T002 touch different files and can be done together:
Task: "Add .wc-pristine-repo/ entry to .gitignore"
Task: "Add the sidecar checkout step to the fix job in board-loop.yml"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001).
2. Complete Phase 3: User Story 1 (T002-T007) — `fix`, `review`,
   `readiness` resolve composites from the trusted copy. This alone closes
   the trust-boundary defect (Principle V) that motivated this feature.
3. **STOP and VALIDATE**: `grep -n 'uses: \./\.github/actions/'
   .github/workflows/board-loop.yml` shows no match inside `fix`,
   `review`, or `readiness`; run quickstart.md step 4 against a
   disposable/test repository if one is available.

### Incremental Delivery

1. Setup (T001) → Foundational (none) → ready.
2. User Story 1 (T002-T007) → trust boundary closed for the item-branch
   jobs → the primary deliverable is live.
3. User Story 2 (T008-T018) → every remaining job carries the same
   guarantee → no board-loop job has a branch-age precondition anywhere.
4. User Story 3 (T019-T022) → Gate 99 registered and self-tested → the
   rule cannot silently regress.
5. Polish (T023-T027) → documentation matches shipped behaviour, and the
   full local gate suite is green.

---

## Notes

- `[P]` tasks touch different files with no dependency on an incomplete
  task; everything else in this feature is a sequential edit to one of
  three files (`board-loop.yml`, the new Gate 99 script, `lint-workflows.yml`)
  and is ordered accordingly.
- `[Story]` labels map every Phase 3/4/5 task to spec.md's User Story 1, 2,
  or 3; Setup and Polish carry no story label per the checklist format
  rules.
- Verify with `git status --porcelain` after T026's negative-staging drill
  that nothing under `.wc-pristine-repo/` is tracked, before cleaning up.
- Commit after each phase, or more often; `board-loop.yml` is large enough
  that one commit per job's pair of tasks (checkout + rewrite) keeps the
  diff reviewable.
- Stop at any checkpoint to confirm the guarantee that phase claims before
  moving to the next.
