# Tasks: The Proof Run Can Actually Start — Self Re-Drive vs. the Board Loop's Own Concurrency Group

**Input**: Design documents from `/specs/060-self-redrive-concurrency/`
(plan.md, research.md D1-D9, data-model.md, quickstart.md,
contracts/directed-proof-run.md, contracts/concurrency-groups.md,
contracts/proof-outcome-taxonomy.md)

**Tests**: This feature's verification is deterministic gate scripts with
checked-in fixtures (Principle VIII, FR-020/FR-021), not a conventional
test suite. Gate/fixture tasks are listed inline with the implementation
task they verify, matching this repository's existing `verify-*.py`
convention.

**Gate numbering**: the highest gate number wired into
`.github/workflows/lint-workflows.yml` as of this branch is **Gate 89**
(`grep -n "Gate " .github/workflows/lint-workflows.yml`). This feature
amends Gate 89 (`verify-board-prove.py`) in place and adds three new gates.
Originally numbered sequentially from Gate 90 (Gate 90 for
`verify-concurrency-guarantee-statement.py`/SC-006, Gate 91 for
`verify-directed-proof-no-item-conflict.py`/FR-017, Gate 92 for
`verify-board-prove-displacement.py`/FR-010b, later renumbered in place to
Gate 99 for a first collision), those three collided a second time with
gates main had since claimed (Gate 90 = every applied label has a matching
gh label create, #488/#493; Gate 91 = auto-release.yml's pass-path specs/
fallback, #482) and with PR #463's own in-flight Gate 99. Per the
maintainer's PR #490 review (2026-09-25), they are renumbered to **Gate
100** (`verify-concurrency-guarantee-statement.py`, SC-006), **Gate 101**
(`verify-directed-proof-no-item-conflict.py`, FR-017), and **Gate 102**
(`verify-board-prove-displacement.py`, FR-010b) everywhere they appear.
Re-check this at implementation time in case another in-flight branch has
since claimed one of these numbers, and renumber every reference in this
file if so.

**Limited file-level parallelism**: unlike a feature that touches many
independent workflow files, almost every task below edits one of two
files — `.github/workflows/board-loop.yml` (2811 lines, one file) and
`.github/scripts/board_prove.py` — which is this feature's own
single-home discipline (CLAUDE.md), not an oversight. `[P]` is used only
where a task adds a genuinely separate new file with no ordering conflict
against its phase's other tasks; most tasks in this file are sequential
edits to one of those two files and are intentionally not marked `[P]`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 (proof run starts), US2 (distinct no-proof reasons),
  US5 (concurrency guarantee), US3 (abandoned-dispatch accountability),
  US4 (board-helper reachability) — ordered by priority (P1, P1, P1, P2,
  P2) per spec.md, not by the spec's own US1-US5 numbering, which
  interleaves priorities.

## Path Conventions

GitHub Actions reusable-workflow pipeline, no `src`/`tests` split. Every
path below is relative to the repository root.

---

## Phase 1: Setup

- [X] T001 Confirm the gate-number reservation above is still accurate:
  `grep -n "Gate 9[0-9]" .github/workflows/lint-workflows.yml` must show
  nothing above Gate 89. If it does, shift every "Gate 9x" reference in
  this file by the same offset before starting Phase 4/6/7.

---

## Phase 2: Foundational

**Why this phase is unusually large**: spec.md's own analysis is explicit
that "every other story in this spec is a consequence of getting
[Story 1] right" — there is no way to build a partial version of the
directed-proof-run mechanism (workflow_dispatch inputs, per-job
concurrency split, job gating, the pre-dispatch checks) for just one
story, because Stories 2, 3, 4 and 5 all observe and check that exact
same shared substrate. This phase builds the whole mechanism; each story
phase after it adds that story's own specific behaviour/gate on top of an
already-working mechanism (contracts/directed-proof-run.md,
contracts/concurrency-groups.md, research.md D1-D4).

**⚠️ CRITICAL**: No user story phase can begin until this phase's
checkpoint passes.

### `board_prove.py` — the directed-stage and concurrency-occupancy functions (research.md D1, D2, D4)

- [X] T002 `.github/scripts/board_prove.py`: add a module-level
  `aimable_jobs = frozenset({"triage", "review", "readiness", "prove"})`
  constant (research.md D2). Comment inline why `select`, `route`, `fix`
  are excluded: `select`'s own job body *is* the item-picking logic (a
  directed run of it would either pick nothing or violate FR-002's "MUST
  NOT select a board item"); `route` can push a branch/PR for the
  size-and-path backstop's post-push breach case, and `fix` exists to
  open the fix PR — both are mutating actions FR-002 forbids. This
  constant is read directly (never re-derived) by Gate 101 (T040)'s
  structural assertion.
- [X] T003 `.github/scripts/board_prove.py`: add
  `scan_job_uses_graph(workflow_path)` (research.md D1): parse the one
  checked-out workflow file with `yaml.safe_load`, walk
  `doc["jobs"][job]["steps"]` per job (joining each step's own `run:`/
  `uses:` text into one string before matching), apply the existing
  `WORKFLOW_REF_RE`/`COMPOSITE_REF_RE` to each job's own text. Returns
  `{job_name: sorted(referenced_paths)}`. Leave an explicit call site for
  T045's script-import pass (Phase 7) rather than duplicating the regex
  set — this function and `scan_dispatchable_and_uses_graph()` should
  share the resolution helper T045 adds, not each carry their own copy.
- [X] T004 `.github/scripts/board_prove.py`: add
  `directed_stage(changed_paths, job_uses_graph, aimable_jobs)` (research.md
  D1): intersects `changed_paths` against each aimable job's referenced
  set from `job_uses_graph`. Exactly one aimable job's set intersects →
  that job. More than one does (a shared helper like
  `board_item_marker.py`) → break the tie by pipeline order,
  latest-stage-wins: `prove` > `readiness` > `review` > `triage`. None
  does → `None` (FR-010a's "no directed run reaches the changed
  behaviour"). Only meaningful when the caller already knows
  `redrive_target()`'s chosen workflow is `board-loop.yml`.
- [X] T005 `.github/scripts/board_prove.py`: add
  `joins_directed_group(target_workflow_path, target_job, aimable_jobs)`
  (research.md D4, FR-001 static check): for the self-target case (target
  basename is `board-loop.yml` and `target_job in aimable_jobs`) return
  `True` by construction — true once T009 ships, and this check exists so
  a future edit narrowing or removing the group split fails loudly rather
  than silently reintroducing the deadlock. For any other target, read
  that workflow's own `concurrency:` block text off the checked-out tree
  and confirm its group name is neither `wing-commander-board-loop` nor
  `wing-commander-board-loop-directed-proof` (FR-004: correctness for a
  target outside the caller's own group).
- [X] T006 `.github/scripts/board_prove.py`: add
  `directed_proof_group_busy(run_list_json)` (research.md D4, FR-001a
  dynamic check): parse
  `gh run list --workflow=board-loop.yml --json databaseId,displayTitle,status -L 20`
  JSON; return `True` if any row's `status` is not `completed` and its
  `displayTitle` contains the literal `[directed:` marker T008 embeds.

### `board-loop.yml` — dispatch surface and concurrency split (research.md D1, D3, D4)

- [X] T007 `.github/workflows/board-loop.yml`: add
  `directed-stage` (string, default `""`), `directed-issue` (string,
  default `""`), `directed-pr` (string, default `""`) to the
  `workflow_dispatch.inputs` block (~lines 19-32), alongside
  `attempt-token`. Descriptions per contracts/directed-proof-run.md's
  input table.
- [X] T008 `.github/workflows/board-loop.yml`: widen `run-name:` (line 36)
  so a directed dispatch's own run carries a second, distinct token:
  `${{ inputs.attempt-token && format('board-loop [attempt:{0}]',
  inputs.attempt-token) || 'board-loop' }}${{ inputs.directed-stage != ''
  && format(' [directed:{0}]', inputs.directed-stage) || '' }}`
  (research.md D4). T006's `directed_proof_group_busy()` depends on this
  exact `[directed:` substring.
- [X] T009 `.github/workflows/board-loop.yml`: replace the workflow-level
  `concurrency:` block (lines 40-46) with per-job blocks (research.md D3,
  contracts/concurrency-groups.md "Groups, per job"):
  - `select`, `triage`, `route`, `fix`, `review`, `readiness`:
    `concurrency: {group: wing-commander-board-loop, cancel-in-progress: false}`.
  - `prove-gate`, `prove`:
    `concurrency: {group: ${{ (github.event_name == 'workflow_dispatch' &&
    inputs.directed-stage != '') && 'wing-commander-board-loop-directed-proof'
    || 'wing-commander-board-loop' }}, cancel-in-progress: false}`.

  Every block's own comment states the FR-016 guarantee sentence
  verbatim (contracts/concurrency-groups.md "The guarantee"): "One board
  item is in flight repository-wide. A directed proof run, which selects
  no board item and opens no fix PR, is the only run permitted to
  overlap an ordinary board-loop run. Every other pair of board-loop.yml
  runs queues rather than races or cancels." Gate 100 (T038) diffs this
  text byte-for-byte against contracts/concurrency-groups.md and
  board-loop-workflow.md (T039), so do not paraphrase it.
- [X] T010 `.github/workflows/board-loop.yml`: `select`'s `if:` (line 84)
  gains `&& inputs.directed-stage == ''` (contracts/directed-proof-run.md
  "Job gating").

### `board-loop.yml` — threading a directed issue/PR through jobs that lose `select`'s outputs

`select` being skipped for a directed dispatch (T010) is not, by itself,
sufficient wiring: `resolve-model`, `triage`, `review`, and `readiness`
all carry `needs:` on `select` (directly or transitively via
`resolve-model`/`fix`), and GitHub's default `success()` wrapping on a
job-level `if:` means a *skipped* `needs:` job still cascades a skip to
every job that merely adds a boolean guard without also naming
`!cancelled()` and `needs.<X>.result != 'failure'` — the same
entry-job/survivor-job shape this repository's own Gate 15 (its
"status-function walk") already checks for other workflows. Each task
below both threads the directed issue/PR through the job's own step
bodies AND fixes the `if:` shape so a directed dispatch does not silently
cascade-skip. See this run's `wing-commander-findings` for the two ways
this differs from what research.md D1/contracts/directed-proof-run.md's
"Job gating" section states.

- [X] T011 `.github/workflows/board-loop.yml`: `resolve-model`'s `if:`
  (line 598, currently `needs.select.outputs.issue-number != ''`) becomes
  `!cancelled() && needs.select.result != 'failure' &&
  (needs.select.outputs.issue-number != '' || inputs.directed-issue != '')`.
  Its `ISSUE_NUMBER` env (line 610) becomes
  `${{ needs.select.outputs.issue-number || inputs.directed-issue }}`.
  `resolve-model` is a hard `needs:` dependency of `triage`/`route`/
  `fix`/`review`; without this fix a directed `triage`/`review` dispatch
  never gets a model tier and cascade-skips.
- [X] T012 `.github/workflows/board-loop.yml`: `triage`'s `if:` (line 664)
  becomes `!cancelled() && needs.select.result != 'failure' &&
  needs.resolve-model.result != 'failure' &&
  ((needs.select.outputs.issue-number != '' && needs.select.outputs.step
  == 'triage') || inputs.directed-stage == 'triage') &&
  vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'`. Every
  `ISSUE_NUMBER: ${{ needs.select.outputs.issue-number }}` reference
  inside this job's own steps (re-grep `needs.select.outputs.issue-number`
  within the `triage:` job's line range — T007-T011 shift line numbers)
  becomes `${{ needs.select.outputs.issue-number || inputs.directed-issue }}`.
- [X] T013 `.github/workflows/board-loop.yml`: add one new step, reused
  by `review` and `readiness` (T014/T015) — name it "Resolve directed PR
  from the issue marker" — gated
  `if: !cancelled() && inputs.directed-stage != '' &&
  (inputs.directed-stage == 'review' || inputs.directed-stage == 'readiness')`.
  It reads the directed issue's comments with the same
  `gh api .../issues/$ISSUE_NUMBER/comments --paginate --jq '.[] |
  {created_at, body}' | jq -s '.'` call the `select` job's own "Resume"
  step already makes (~line 358-388), then calls
  `board_item_marker.read_marker(comments)` and outputs `.pr`. This is
  this file's own resolution of a gap contracts/directed-proof-run.md
  leaves open (`directed-pr` is documented as `prove`-only, but
  `review`/`readiness` genuinely need a PR number to act on): the marker
  already records the associated PR (`write_marker`'s own `pr` field), so
  reading it is the deterministic, code-derived source Principle IX
  requires — never a second dispatch input. Add this step once (e.g. at
  the top of `review`, reused by `readiness` via its own `needs:` on
  `review`'s outputs where possible, or duplicated verbatim into
  `readiness` if job boundaries don't allow reuse — whichever keeps
  CLAUDE.md's single-home rule cleanest is this task's own call).
- [X] T014 `.github/workflows/board-loop.yml`: `review`'s `if:` (lines
  1638-1642) becomes `!cancelled() && needs.select.result != 'failure' &&
  needs.resolve-model.result != 'failure' && needs.fix.result != 'failure'
  && ((needs.fix.result == 'success' && needs.fix.outputs.pr-number != '')
  || (needs.select.outputs.step == 'review' && needs.select.outputs.pr !=
  '') || inputs.directed-stage == 'review') &&
  vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'`. Its "Resolve the PR
  under review" step's `PR_NUMBER` (line 1657) becomes
  `${{ needs.fix.outputs.pr-number || needs.select.outputs.pr ||
  steps.resolve-directed-pr.outputs.pr }}` (T013's step id). Every other
  `needs.select.outputs.issue-number` reference inside this job (re-grep
  within its own line range) becomes
  `${{ needs.select.outputs.issue-number || inputs.directed-issue }}`.
- [X] T015 `.github/workflows/board-loop.yml`: `readiness`'s `if:` (lines
  2253-2257) becomes `!cancelled() && needs.select.result != 'failure' &&
  needs.review.result != 'failure' &&
  ((needs.review.result == 'success' && needs.review.outputs.outcome ==
  'converged') || (needs.select.outputs.step == 'readiness' &&
  needs.select.outputs.pr != '') || inputs.directed-stage == 'readiness')
  && vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'`. Its "Resolve the PR
  under readiness" step's `PR_NUMBER` (line 2269) becomes
  `${{ needs.review.outputs.pr-number || needs.select.outputs.pr ||
  steps.resolve-directed-pr.outputs.pr }}`. Every other
  `needs.select.outputs.issue-number` reference inside this job becomes
  `${{ needs.select.outputs.issue-number || inputs.directed-issue }}`.
- [X] T016 `.github/workflows/board-loop.yml`: `prove-gate`'s `if:` (line
  2489) becomes `(github.event_name == 'pull_request' ||
  (github.event_name == 'workflow_dispatch' && inputs.directed-stage ==
  'prove')) && vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'`
  (contracts/directed-proof-run.md "Job gating" — `prove-gate` has no
  `needs:` on `select`, so no cascade-skip fix is needed here). Its
  "Resolve the originating issue and decide whether prove is entered"
  step (line 2518): on the `workflow_dispatch` path, `issue_number` comes
  directly from `inputs.directed-issue` (never regex-extracted from a PR
  body a directed run may not even have), and `PR_NUMBER`/`MERGED` come
  from `inputs.directed-pr` and a live
  `gh pr view "$PR_NUMBER" --json merged --jq .merged` re-check — never
  trusting the dispatch inputs blindly, exactly as the `pull_request`
  event path already re-derives from `github.event.pull_request.*`
  (Principle IX, Constitution V). The marker-membership check
  (`has_marker`) is unchanged — it still confirms the caller-supplied
  issue really is a board item before `eligible` can be `true`.
- [X] T017 `.github/workflows/board-loop.yml`: `prove`'s job body —
  every `PR_NUMBER: ${{ github.event.pull_request.number }}` reference
  (currently lines 2640, 2694, 2746) becomes
  `${{ github.event.pull_request.number || inputs.directed-pr }}`.

### `board-loop.yml` — the `decide`/busy-check/redrive wiring inside `prove` (FR-001/FR-001a/FR-002/FR-002a)

- [X] T018 `.github/workflows/board-loop.yml`: extend the `prove` job's
  "Decide whether this merge needs a re-driven run, and which" step
  (~line 2636): after computing `target`/`target_reason` via
  `redrive_target()`, when `target == "board-loop.yml"` also call
  `directed_stage(changed_paths, scan_job_uses_graph(".github/workflows/board-loop.yml"),
  aimable_jobs)` (T003/T004/T002) and write a new `directed-stage` output
  (empty when `target != "board-loop.yml"` or `directed_stage()` returns
  `None`).
- [X] T019 `.github/workflows/board-loop.yml`: add a new step "Check
  whether the directed proof group is busy" right after the `decide`
  step, gated `if: steps.decide.outputs.actions-only == 'true' &&
  steps.decide.outputs.directed-stage != '' &&
  steps.killswitch-recheck.outputs.paused != 'true'`: runs
  `gh run list --workflow=board-loop.yml --json
  databaseId,displayTitle,status -L 20`, feeds the JSON to
  `directed_proof_group_busy()` (T006), outputs `busy`.
- [X] T020 `.github/workflows/board-loop.yml`: "Re-drive the changed
  behaviour to prove the fix" step's `if:` (lines 2708-2711) gains
  `&& steps.busy-check.outputs.busy != 'true'` (T019's step id — name it
  `busy-check`). Its `with:` block gains a `workflow-inputs` entry (the
  composite's existing generic JSON input — Out of Scope forbids changing
  the composite itself):
  `workflow-inputs: ${{ steps.decide.outputs.directed-stage != '' &&
  toJSON({ 'directed-stage': steps.decide.outputs.directed-stage,
  'directed-issue': needs.prove-gate.outputs.issue-number, 'directed-pr':
  steps.decide.outputs.directed-stage == 'prove' &&
  github.event.pull_request.number || '' }) || '{}' }}`. An external,
  non-`board-loop.yml` target (FR-004) continues to pass no directed
  inputs at all, unchanged.

### Gate 89 — fixtures for every function this phase adds

- [X] T021 Extend Gate 89 (`.github/scripts/verify-board-prove.py`) with
  fixtures for `directed_stage()` (T004): one case per aimable job, one
  none-of-the-aimable-jobs-match case (→ `None`), one tie-break case (a
  helper referenced by both `review` and `readiness` → `readiness`
  wins), each in both directions (FR-020).
- [X] T022 Extend Gate 89 with fixtures for `joins_directed_group()`
  (T005): self-target true-by-construction case, an external target
  sharing `wing-commander-board-loop` (must return `False`), an external
  target with its own distinct group (must return `True`), each in both
  directions.
- [X] T023 Extend Gate 89 with fixtures for `directed_proof_group_busy()`
  (T006): empty run list (`False`), a `[directed:` row with `status:
  in_progress` (`True`), a `[directed:` row with `status: completed`
  (`False`), an unrelated non-directed row (`False`), each in both
  directions.
- [X] T024 Extend Gate 89's real-tree assertion (FR-021 partial): read
  `board-loop.yml`'s own `prove-gate`/`prove` `concurrency.group:`
  expression off the checked-out tree (T009) and assert it differs
  literally from `select`'s (or any of `triage`/`route`/`fix`/`review`/
  `readiness`'s) group expression — the check research.md D4 says must
  exist "so a future edit narrowing or removing the split fails loudly
  rather than silently reintroducing the deadlock."

**Checkpoint**: A directed dispatch of `board-loop.yml` can start while
its dispatching run is alive, reach `triage`/`review`/`readiness`/`prove`
with a correctly sourced issue/PR number, and the pre-dispatch checks
(FR-001/FR-001a) prevent a dispatch that cannot win. `python
.github/scripts/run-local-gates.py` passes, including Gate 89's
extensions. Every user story phase below builds on this.

---

## Phase 3: User Story 1 - A merged Actions-only fix gets a proof run that can actually start (Priority: P1) 🎯 MVP

**Goal**: confirm, end-to-end, that the mechanism Phase 2 built actually
resolves "The deadlock" (spec.md) for the case FR-022 makes mandatory —
a change to the `prove` step itself.

**Independent Test**: merge a PR that changes only Actions-only behaviour
reachable from the loop, and observe that the proof run leaves the
queued state and that its terminal conclusion is recorded on the issue
(spec.md).

- [ ] T025 [US1] Follow quickstart.md Story 1 steps 1-5: merge a scratch
  fix whose changed path resolves (via T004's `directed_stage()`) to the
  `prove` job specifically (e.g. a change to `board_prove.py` itself, or
  to the "Record the proof outcome" step). Confirm the `decide` step's
  `directed-stage` output is `prove`, the busy-check reports `busy:
  false`, the dispatched run's `status` moves out of `queued` **while the
  dispatching run is still in progress**, and it reaches a terminal
  conclusion inside the wait budget with the issue recording the run URL
  and conclusion (success → closes; failure → stays open).
- [ ] T026 [US1] Confirm (verify only, no wiring change expected) that
  the existing "Cross-link the proof run onto the originating issue" step
  (`if: steps.redrive.outputs.run-url != ''`) fires unchanged for a
  directed dispatch.

**Checkpoint**: The feature's own defect (spec.md "The deadlock") no
longer reproduces for the one changed-stage case FR-022 requires be
provable. User Story 1 is independently demonstrable here.

---

## Phase 4: User Story 2 - A proof that could not be produced says why, in terms a maintainer can act on (Priority: P1)

**Goal**: the two-branch (`run-url` empty / not empty) outcome recording
Phase 2 left unchanged becomes the eight-reason taxonomy
contracts/proof-outcome-taxonomy.md specifies, and a displaced *prove
run itself* (no `prove` job ever existed to record anything) is detected
separately.

**Independent Test**: force each no-proof condition and read the issue
comment for each; each must name its own distinct condition (spec.md).

### The `outcome_reason` taxonomy (research.md D6)

- [X] T027 [US2] `.github/scripts/board_prove.py`: add
  `outcome_reason(...)` — a pure function taking the busy-check result
  (T019), the composite's `run-url`/`conclusion` outputs, the T028/T029
  disambiguation reads, and `redrive_target()`/`directed_stage()`'s own
  results — returning one of `group-busy` / `not-started` / `unfinished`
  / `displaced` / `uncorrelated` / `no-target` / `nothing-reaches` /
  `success` / `failure` per contracts/proof-outcome-taxonomy.md's exact
  table.
- [X] T028 [US2] `.github/workflows/board-loop.yml`: add a step
  immediately after `wing-commander-dispatch-and-wait` returns, gated
  `if: steps.redrive.outputs.conclusion == 'timeout'`, calling
  `gh run view <correlated-run-id> --json status,startedAt` once to
  distinguish `not-started` (status never left `queued`) from
  `unfinished` (`startedAt` set) — Out of Scope forbids changing the
  composite itself, so this read happens in the wrapper, once, right
  after the composite returns (research.md D6). Extract the run id from
  `steps.redrive.outputs.run-url`.
- [X] T029 [US2] `.github/workflows/board-loop.yml`: the `displaced`
  branch (correlation returned empty `run-url`) reuses T019's `gh run
  list` payload (already fetched for the busy-check) rather than a
  second call — confirming no matching row exists at all is what
  distinguishes `displaced` (evicted from the pending slot) from
  `uncorrelated` (ambiguous correlation, two or more matching titles).
- [X] T030 [US2] `.github/workflows/board-loop.yml`: rewrite "Record the
  proof outcome" (~line 2741) to call `outcome_reason()` (T027) instead
  of the current two-branch shell `if`, and post the distinct issue
  comment contracts/proof-outcome-taxonomy.md's "Recording rule"
  specifies for whichever of the eight reasons applies — every
  non-`success` reason leaves the issue open (FR-008) carrying a
  `write_marker('prove', ...)` marker, exactly as today's two branches
  already do.
- [X] T031 [US2] `.github/workflows/board-loop.yml`: rewrite "Determine
  this run's outcome for the metrics record" (~line 2775) to map each
  `outcome_reason` value to its own `run-label` per
  contracts/proof-outcome-taxonomy.md's "Cost line / metrics record
  label" table, replacing the current `proof run uncorrelated` catch-all
  (FR-012).

### FR-010b — the prove run itself can be displaced before it exists (research.md D8)

- [X] T032 [P] [US2] New module `.github/scripts/board_prove_displacement.py`:
  `find_undetected_merges(merged_prs, issues_by_number)` — given the
  repo's recently-merged, loop-labeled fix PRs (the same `Fixes #N` +
  board-item-marker convention `prove-gate` already reads) and each
  cited issue's current marker history, returns issues whose most
  recently merged PR left no later `prove`/`proven` marker and no
  proof-outcome comment (the signature of a `pull_request: closed` run
  displaced from its pending slot before `prove-gate`/`prove` ever ran).
- [X] T033 [US2] `.github/workflows/board-loop.yml`: add a new early
  step to the `select` job, after the entry gates and before the picking
  logic (research.md D8 — `select` runs on every non-`pull_request`
  trigger, so no new schedule/workflow/concurrency-group is needed),
  calling `find_undetected_merges()` (T032) and posting `"prove run
  displaced"` (data-model.md's `recorded_reason`) on any issue it finds,
  without gating `select`'s own proceed/no-op decision.
- [X] T034 [P] [US2] New Gate 102 (renumbered from Gate 92, then Gate 99;
  PR #490 review, 2026-09-25) —
  `.github/scripts/verify-board-prove-displacement.py`, wired into
  `.github/workflows/lint-workflows.yml` with `if: "!cancelled()"`.
  Fixtures for `find_undetected_merges()` in both directions: a merged
  PR whose issue carries a later `prove`/`proven` marker → not flagged;
  one with no later marker and no proof-outcome comment → flagged
  (FR-020).

### Coverage and contract fold-in

- [X] T035 [US2] Extend Gate 89 with fixtures for `outcome_reason()`
  (T027): one fixture per each of the eight values, in both directions
  (FR-020), including the `not-started`-vs-`unfinished` distinction
  (T028) and the `displaced`-vs-`uncorrelated` distinction (T029) as
  their own explicit cases (SC-003).
- [X] T036 [US2] Update
  `specs/057-autonomous-board-loop/contracts/prove-step.md`'s "Re-drive"
  section (FR-019, research.md D9): replace the three-branch
  success/failure-or-timeout/uncorrelated table with a pointer to
  `specs/060-self-redrive-concurrency/contracts/proof-outcome-taxonomy.md`'s
  eight-reason table, and fold in
  `contracts/directed-proof-run.md`'s mechanism description under a new
  "Directed proof run" subsection.
- [ ] T037 [US2] Follow quickstart.md Story 2: force `group-busy` (a
  manual concurrent dispatch), `no-target` (a merge touching only a
  `select`-only-referenced helper), and `nothing-reaches` (a merge
  touching a path nothing scans); confirm each issue comment names its
  own distinct condition. `not-started`/`unfinished`/`displaced` are
  confirmed at the fixture level only (T035), per quickstart's own note
  that they are not independently forceable without a runner-capacity
  artifice.

**Checkpoint**: All eight `outcome_reason` values render as distinct,
named issue comments, and a prove run displaced before it ever started is
also detected and recorded. User Stories 1 and 2 are both independently
demonstrable here.

---

## Phase 5: User Story 5 - One board item in flight is still a guarantee a maintainer can rely on (Priority: P1)

**Goal**: the FR-016 guarantee sentence is identical across
`board-loop.yml`'s comments, `contracts/board-loop-workflow.md`, and
`contracts/concurrency-groups.md`, checked by a gate; and the one new
overlap FR-002 permits (a directed proof run alongside the run that
dispatched it) is proven, not merely argued, to never let the two runs
collide on the same issue.

**Independent Test**: state the post-change guarantee and exercise the
pairs it permits and the pairs it forbids (spec.md).

- [X] T038 [US5] New Gate 100 (renumbered from Gate 90; PR #490 review,
  2026-09-25) —
  `.github/scripts/verify-concurrency-guarantee-statement.py` (SC-006),
  wired into `lint-workflows.yml` with `if: "!cancelled()"`: diffs the
  FR-016 sentence (contracts/concurrency-groups.md "The guarantee") that
  T009 placed in `board-loop.yml`'s per-job `concurrency:` comments
  against `specs/057-autonomous-board-loop/contracts/board-loop-workflow.md`'s
  "Concurrency" section (T039), failing if either drifts from the
  canonical text in `contracts/concurrency-groups.md`.
- [X] T039 [US5] Update
  `specs/057-autonomous-board-loop/contracts/board-loop-workflow.md`'s
  "Concurrency" section (FR-019, research.md D9) to restate the FR-016
  sentence and the per-job group table from
  `contracts/concurrency-groups.md`, replacing the single workflow-level
  block it currently documents.
- [X] T040 [US5] New Gate 101 (renumbered from Gate 91; PR #490 review,
  2026-09-25) —
  `.github/scripts/verify-directed-proof-no-item-conflict.py` (FR-017,
  research.md D7), wired into `lint-workflows.yml` with `if:
  "!cancelled()"`:
  1. A structural assertion reading `aimable_jobs` (T002) directly from
     `board_prove.py` and failing if it contains any of `{"select",
     "route", "fix"}` — this is also the check FR-011 (User Story 3)
     relies on for its own "holds by construction" claim; do not add a
     second, redundant assertion for FR-011 (T043 cross-references this
     one instead).
  2. A fixture extending `.github/scripts/tests/board-eligibility/in-flight/`
     with a new case: an open issue carrying a `step: prove` marker while
     a concurrent `select()` call runs over the same issue set, asserting
     `select()` never returns that issue — the specific case FR-017 names
     ("the issue being proven is still open... while its proof run is in
     flight").
- [ ] T041 [US5] Follow quickstart.md Story 5: while a directed proof run
  is in flight (from T025), trigger the hourly schedule tick manually and
  confirm the schedule run's `select` either picks a different issue or
  queues in `wing-commander-board-loop`, never races the directed run for
  the same issue, and neither run closes an issue the other is acting on.

**Checkpoint**: The one-board-item-in-flight guarantee is stated
identically in three places and checked by a gate; the one overlap this
feature introduces is proven, not merely asserted, not to violate it.

---

## Phase 6: User Story 3 - A dispatch the loop abandoned does not quietly become someone else's board iteration (Priority: P2)

**Goal**: any comment a directed proof run posts names itself as one and
names the merge it proves, and the abandoned-dispatch cost is visible in
the loop's existing metrics record — both on top of the by-construction
guarantee Gate 101 (T040) already checks.

**Independent Test**: dispatch a proof run, let the caller stop waiting,
and check both that the dispatched run's eventual behaviour is accounted
for and that its origin is recoverable from the issue or the run itself
(spec.md).

- [X] T042 [US3] `.github/workflows/board-loop.yml`: every comment a
  directed proof run posts to the issue it acts on — `triage`'s
  close/proceed comments, `review`'s findings comment, `readiness`'s
  report comment, `prove`'s outcome comment (T030) — states it is a
  directed proof run and names the merge/PR it is proving (FR-011,
  contracts/directed-proof-run.md "Attribution"). Compose one attribution
  string (gated on `inputs.directed-stage != ''`) and prepend it, rather
  than writing four separately-worded copies (CLAUDE.md single-home).
- [X] T043 [US3] Cross-reference note (no new code): FR-011's "selects no
  board item"/"opens no fix PR" claims are exactly the properties Gate 101
  (T040) checks structurally. This task exists only so a future reader
  does not add a second, redundant gate for the same property.
- [X] T044 [US3] Confirm that T031's metrics-record `run-label` mapping
  (FR-012) makes an abandoned proof dispatch's cost visible under a label
  naming its condition (e.g. `proof: group-busy`, `proof: displaced`)
  rather than folded into a generic label — verify against the fixtures
  T035 already added; no new fixture expected here.

**Checkpoint**: A directed proof run the caller gave up on is
attributable from the issue and the run itself, and its cost is visible
in the loop's existing metrics record.

---

## Phase 7: User Story 4 - A board helper script a merge changed is reachable (Priority: P2)

**Goal**: `scan_dispatchable_and_uses_graph()` and `scan_job_uses_graph()`
resolve the `sys.path.insert(0, ".github/scripts")` + `from X import Y`
module-loading idiom most board helpers actually use, so a
board-helper-only merge is routed to a real re-drive target instead of
"nothing reaches this change" (research.md D5). FR-014's own ordering
constraint — "MUST NOT ship ahead of FR-002" — is satisfied by this
phase landing after Phase 2.

**Independent Test**: take a merged PR whose changed paths are only a
board helper script and check the recorded re-drive decision against the
reachability rule the feature adopts (spec.md).

- [X] T045 `.github/scripts/board_prove.py`: add a `SCRIPT_IMPORT_RE`
  pass shared by `scan_dispatchable_and_uses_graph()` and
  `scan_job_uses_graph()` (T003) (research.md D5): within any step's
  `run:` text that also contains `sys.path.insert(0, ".github/scripts")`
  (or the single-quoted form), match `from (\w+) import`/`import (\w+)`
  and resolve each captured name to `.github/scripts/<module>.py` if that
  file exists.
- [X] T046 [US4] `.github/scripts/board_prove.py`: build the transitive
  closure over first-party helper-imports-helper (research.md D5): parse
  each `.github/scripts/board_*.py` file's own top-level `from X import
  Y`/`import X` lines (regex is sufficient — first-party, uniform import
  style, no AST needed) so a helper imported by another resolved helper
  is captured too.
- [X] T047 [US4] `.github/scripts/board_prove.py`: apply the same
  `SCRIPT_IMPORT_RE` pass to `.github/actions/**/action.yml` composite
  files' own `run:` steps (FR-014's third clause: "helpers executed
  inside a composite the workflow uses").
- [X] T048 [US4] Extend Gate 89's real-tree assertion (FR-021,
  completing T024): assert every `.github/scripts/board_*.py` file
  resolves to at least one job in `board-loop.yml`'s job-uses-graph
  (`scan_job_uses_graph`, T003/T045/T046) — the exact assertion FR-014
  requires.
- [X] T049 [US4] Extend Gate 89 with fixtures for the script-import
  resolution (T045/T046/T047), both directions: a step whose `run:` text
  loads a module via the `sys.path.insert` + `from X import Y` idiom
  resolves to `X.py`; a bare string that happens to contain a module name
  outside that idiom does NOT resolve (negative case); a
  helper-imports-helper chain resolves transitively; a composite's own
  `run:` step resolves.
- [ ] T050 [US4] Follow quickstart.md Story 4: merge a scratch PR
  changing only `.github/scripts/board_item_marker.py` and confirm the
  `decide` step's `reason` output cites a real executing job rather than
  "nothing reaches this change," and that a second, independent run over
  the identical merge chooses the same target (FR-015's determinism).

**Checkpoint**: A board-helper-only merge is routed to a real,
deterministic re-drive target. All five user stories are independently
demonstrable.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T051 Run `python .github/scripts/run-local-gates.py` and confirm
  all gates pass on the real tree, including amended Gate 89 and new
  Gates 90-92.
- [X] T052 Confirm every gate this feature adds or amends fails on its
  own negative fixture when the behaviour it checks is mutated (SC-008)
  — e.g. temporarily widen `aimable_jobs` (T002) to include `"fix"` and
  confirm Gate 101 (T040) fails; temporarily point `prove-gate`'s directed
  branch at `wing-commander-board-loop` instead of the
  `-directed-proof` group and confirm Gate 100 (T038) fails. Revert each
  mutation afterward via a matching Edit (this run's tooling has no
  `git checkout`/`git restore`; confirm the revert with `git diff` is
  byte-identical to HEAD before moving on, mirroring spec
  058-per-job-minute-floor's T022 precedent).
- [X] T053 `grep -rn "wing-commander-board-loop" docs/` (and any other
  documented description of the board loop's concurrency behaviour, e.g.
  `docs/architecture.md`) and update any prose that still describes the
  single workflow-level block this feature replaces (T009).
- [X] T054 Final full-suite confirmation: re-run
  `python .github/scripts/run-local-gates.py` after T051-T053's edits and
  confirm the count is unchanged from T051 (no gate silently dropped),
  and that `verify-gate-wiring.py` accounts for Gates 90, 91, and 92.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup; BLOCKS every user story
  phase — see this phase's own "why this phase is unusually large" note.
- **User Story 1 (Phase 3)**: depends only on Phase 2.
- **User Story 2 (Phase 4)**: depends on Phase 2; independent of Phase 3
  (does not require Phase 3's own validation to have run, only the
  mechanism it validates).
- **User Story 5 (Phase 5)**: depends on Phase 2 (specifically T009's
  concurrency comments and T002's `aimable_jobs`); independent of Phases
  3-4.
- **User Story 3 (Phase 6)**: depends on Phase 2 and on Gate 101 (T040,
  Phase 5) for its own cross-reference (T043); depends on T030/T031
  (Phase 4) for T044's verification.
- **User Story 4 (Phase 7)**: depends on Phase 2 (FR-014 "MUST NOT ship
  ahead of FR-002," research.md D5) — must not land before Phase 2, but
  has no dependency on Phases 3-6.
- **Polish (Phase 8)**: depends on every phase above.

### Within Phase 2 (Foundational)

`board_prove.py`'s functions (T002-T006) can be written before
`board-loop.yml`'s wiring (T007-T020), since the wiring calls them, but
both live in the same two files respectively — treat each group as
sequential internally.

### Parallel Opportunities

Genuine `[P]` opportunities are rare in this feature (see the
"Limited file-level parallelism" note above): T032 (new module
`board_prove_displacement.py`) and T034 (its gate) are the clearest,
since they touch no file any other Phase-4 task touches until T033 wires
the new module into `board-loop.yml`.

---

## Parallel Example: Phase 4 (User Story 2)

```bash
# T032 and T034 touch only new, dedicated files -- can be drafted
# alongside T027 (board_prove.py's outcome_reason(), a different file):
Task: "New module board_prove_displacement.py: find_undetected_merges()"
Task: "New Gate 102: verify-board-prove-displacement.py fixtures"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL — this is most of the
   feature's actual mechanism).
3. Complete Phase 3: User Story 1 — confirm the deadlock no longer
   reproduces for the `prove` stage.
4. **STOP and VALIDATE**: quickstart.md Story 1's live-run steps.

### Incremental Delivery

1. Setup + Foundational → the mechanism exists and gates pass.
2. Add User Story 1 → the defect's own regression test passes (MVP).
3. Add User Story 2 → every no-proof condition names itself distinctly.
4. Add User Story 5 → the concurrency guarantee is gated, not just
   documented.
5. Add User Story 3 → an abandoned dispatch is attributable and its cost
   is visible.
6. Add User Story 4 → a board-helper-only merge is reachable.
7. Polish → full-suite confirmation and documentation sweep.

### Notes

- `[P]` tasks = different files, no dependencies (rare in this feature —
  see above).
- `[Story]` label maps a task to its user story for traceability; tasks
  with no `[Story]` label in Phases 2 and 7 are foundational/shared
  (Phase 7's T045/T047 are shared scanning infrastructure feeding both
  `scan_dispatchable_and_uses_graph()` and `scan_job_uses_graph()`, so
  they carry no single story label even though the phase is US4's).
- Commit after each task or logical group; re-run
  `python .github/scripts/run-local-gates.py` after every `board_prove.py`
  or `board-loop.yml` edit, since both files are gate-covered and edits
  compound quickly.

---

## Phase 9: Convergence

- [ ] T055 Update `.claude/skills/spec-cross-reference/SKILL.md`'s
  "Over-rated" example (lines 23-28), which still describes
  `group: wing-commander-board-loop` as "applied to every trigger in the
  file" — the single workflow-level block T009 replaced with per-job
  groups. Restate it in terms of the per-job split (the refutation itself
  still stands: a directed proof run selects no board item and opens no
  fix PR, and every other pair of runs still queues) and point at
  `specs/060-self-redrive-concurrency/contracts/concurrency-groups.md`.
  Found by T053's sweep, which could not write under `.claude/` in that
  run's permission set. Per FR-016 (contradicts).

---

## Maintainer Feedback (PR #490 review, 2026-09-25, @charlesguse)

- [x] Renumber this branch's "Gate 90" (the concurrency guarantee sentence, SC-006/FR-016) to **Gate 100** everywhere it appears: the `lint-workflows.yml` step name and comment header, the gate script's docstring and any printed gate prefix, and any spec/contract text (e.g. `specs/060-self-redrive-concurrency/contracts/`) that cites it. Collides with main's existing Gate 90 ("every applied label has a matching gh label create", #488/#493).
- [x] Renumber this branch's "Gate 91" (the directed proof run never conflicts with the item it is proving, FR-017) to **Gate 101** everywhere it appears, same scope as above. Collides with main's existing Gate 91 (auto-release.yml pass-path specs/ fallback, #482).
- [x] Renumber this branch's "Gate 99" (board loop prove-displacement detects a merge whose proof run never started, FR-010b) to **Gate 102** everywhere it appears, same scope as above. Collides with the Gate 99 claimed by PR #463 (converged means no task is left).
- [x] Re-run `python .github/scripts/run-local-gates.py` after the renumber and confirm a clean pass before the next push. (151/151 passed.)

---

## Maintainer Feedback (PR #490 review, 2026-09-25, @charlesguse)

- [ ] Finish T055 (still unchecked): update `.claude/skills/spec-cross-reference/SKILL.md`'s "Over-rated" example (lines 23-28), which still describes `group: wing-commander-board-loop` as "applied to every trigger in the file" — the single workflow-level block T009 replaced with per-job groups. Restate it in terms of the per-job split (the refutation itself still stands) and point at `specs/060-self-redrive-concurrency/contracts/concurrency-groups.md`.
