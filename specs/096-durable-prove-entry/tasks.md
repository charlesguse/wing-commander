# Tasks: A Merged Fix Reaches Prove — The Prove Entry Survives a Displaced Queue Slot

**Input**: Design documents from `/specs/096-durable-prove-entry/`
(plan.md, research.md D1-D9, data-model.md, quickstart.md,
contracts/prove-path-concurrency.md, contracts/recovery-and-resume.md)

**Tests**: This feature's verification is deterministic gate scripts with
checked-in fixtures (Principle VIII, FR-018/FR-020), not a conventional
test suite. Gate/fixture tasks are listed inline with the implementation
task they verify, matching this repository's existing `verify-*.py`
convention.

**Gate numbering**: the highest gate number wired into
`.github/workflows/lint-workflows.yml` as of this branch is **Gate 127**
(`grep -noE "Gate [0-9]+" .github/workflows/lint-workflows.yml | sed -E
's/.*Gate ([0-9]+)/\1/' | sort -n | tail -1`). This feature adds two new
gates, numbered sequentially from the next free number: **Gate 128**
(`verify-board-prove-recovery.py`) and **Gate 129**
(`verify-prove-path-concurrency.py`, FR-018). Re-check this at
implementation time in case another in-flight branch has since claimed one
of these numbers (spec 060's own tasks.md needed three renumbering passes
for exactly this reason) and renumber every reference in this file if so.

**Line numbers**: every `board-loop.yml`/`board_prove.py`/
`board_item_marker.py` line number below was re-verified directly against
this branch's checked-out tree while this file was written (not carried
over from plan.md/research.md's own "Status update 2026-09-30" note
unchecked) — see the per-task citations. Re-verify again immediately
before editing, since Setup/Foundational tasks in this same file shift
later line numbers as they land.

**Limited file-level parallelism**: almost every task below edits one of
two files — `.github/workflows/board-loop.yml` (4563 lines) and
`.github/scripts/board_prove.py` — mirroring spec 060's own tasks.md note.
`[P]` is used only for genuinely separate new files with no ordering
conflict.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 (a merge reaches prove — prevention and recovery), US2
  (a merged fix is never re-triaged), US3 (the arrangement is gated), US4
  (the recovery is legible and costed) — ordered by priority (P1, P1, P2,
  P3) per spec.md.

## Path Conventions

GitHub Actions reusable-workflow pipeline, no `src`/`tests` split. Every
path below is relative to the repository root.

---

## Phase 1: Setup

- [X] T001 Confirm the gate-number reservation above is still accurate:
  `grep -noE "Gate [0-9]+" .github/workflows/lint-workflows.yml | sed -E
  's/.*Gate ([0-9]+)/\1/' | sort -n | tail -1` must show `127`. If it does
  not, shift every "Gate 128"/"Gate 129" reference in this file by the
  same offset before starting Phase 2/5.

---

## Phase 2: Foundational (marker mechanism, recovery module, dispatch input)

**Purpose**: the additive marker fields (research.md D4), the new
`board_prove_recovery.py` module's pure judgment functions (research.md
D5), and the new `directed-recovery` input's mere declaration (research.md
D6) are read or written by more than one user story phase below. Nothing
in this phase is independently observable yet — it is inert until Phase 3
wires it in.

**⚠️ CRITICAL**: No user story phase can begin until this phase's
checkpoint passes.

- [X] T002 `.github/scripts/board_item_marker.py`: `write_marker()`
  (`:139`) gains two keyword parameters with backward-compatible defaults:
  `outcome_reason=None, recovery_attempted=False` (research.md D4). Both
  are included unconditionally in the JSON payload the function already
  builds (`sort_keys=True` unchanged) so every existing positional call
  site keeps working and its marker simply carries
  `"outcome_reason": null, "recovery_attempted": false` alongside the five
  existing keys.
- [X] T003 `.github/scripts/board_item_marker.py`: `main()` (`:228-`)
  gains `--outcome-reason` (string, default `None`) and
  `--recovery-attempted` (`store_true`) arguments, threaded into the
  `write_marker()` call T002 extends.
- [X] T004 [P] New module `.github/scripts/board_prove_recovery.py`
  (research.md D5), matching the one-`board_*.py`-module-per-concern
  convention:
  - `RECOVERY_DIRECTED_INPUT = "directed-recovery"` — the one spelling of
    the new `workflow_dispatch` input name (research.md D5/D6), imported
    by T006/T010/T019/T021 rather than re-typed.
  - `is_recoverable(marker)` — `True` iff `marker.get("step") == "prove"`
    and `marker.get("outcome_reason")` is exactly
    `board_prove_displacement.RECORDED_REASON` (imported, never a re-typed
    literal — FR-014/single-home) or the literal string `"uncorrelated"`,
    and `not marker.get("recovery_attempted")`. A marker with no
    `outcome_reason` key (every pre-feature marker) or a `failure`/
    `unfinished` reason matches neither literal and reads as "not
    recoverable" with no special case (FR-011c).
  - `find_recoverable_items(merged_prs_by_issue, comments_by_issue,
    open_issue_numbers, bot_login)` — filters `merged_prs_by_issue`'s rows
    (the `board-recent-merges-by-issue.json` shape: `{"issue": N, "pr": M,
    "merged_at": "..."}`) to issues present in `open_issue_numbers`, reads
    each one's newest marker via
    `board_item_marker.read_marker_with_timestamp(comments_by_issue[str(issue)],
    bot_login)`, and returns the `is_recoverable()` matches as a list of
    `{"issue": N, "merged_pr": M, "marker_created_at": "...",
    "outcome_reason": "..."}` dicts sorted oldest-`marker_created_at`-first
    (FR-011b fairness, matching `board_eligibility.select()`'s own
    fallback-scan ordering).
- [X] T005 [P] New Gate 128 — `.github/scripts/verify-board-prove-recovery.py`,
  wired into `.github/workflows/lint-workflows.yml` with `if:
  "!cancelled()"` immediately after the Gate 127 block. Fixtures (FR-020),
  both directions, exercising every marker shape data-model.md's "Board
  Item Marker" table lists: no `outcome_reason` key (pre-feature marker,
  not recoverable), `outcome_reason` one of `group-busy`/`not-started`/
  `unfinished`/`displaced`/`no-target`/`nothing-reaches`/`failure` (all not
  recoverable), `outcome_reason` == `board_prove_displacement.RECORDED_REASON`
  (recoverable), `outcome_reason == "uncorrelated"` (recoverable), either
  recoverable reason with `recovery_attempted: true` (not recoverable —
  FR-011a), and a `find_recoverable_items()` case with two candidate issues
  returning both in oldest-first order, and a case where one candidate is
  not in `open_issue_numbers` (excluded). Also extend this gate with
  `board_item_marker.py` round-trip fixtures for T002/T003's two new
  fields: write with each set, read back byte-for-byte; a marker written
  before this feature (five keys only) reads `outcome_reason=None,
  recovery_attempted=False` rather than raising.
- [X] T006 `.github/workflows/board-loop.yml`: add `directed-recovery`
  (string, default `""`) to the `workflow_dispatch.inputs` block, after
  `directed-pr` (`:65-69`) (research.md D6):
  ```yaml
        directed-recovery:
          description: "Directed proof run: this dispatch is recovering a previously displaced or uncorrelated proof (internal use, leave blank otherwise)"
          required: false
          default: ""
          type: string
  ```
  Declaration only — no job reads it yet (T019/T021 read it in Phase 6).
  Not read by `prove-gate`'s eligibility `if:`, which stays exactly as it
  resolves an ordinary directed `prove` dispatch today (FR-002: a recovery
  dispatch is, structurally, an ordinary directed `prove` dispatch).

**Checkpoint**: `board_item_marker.py` can carry the two new fields
round-trip; `board_prove_recovery.py`'s judgment functions are unit-gated;
`directed-recovery` exists as an input nothing reads yet. `python
.github/scripts/run-local-gates.py` passes, including Gate 128. Every user
story phase below builds on this.

---

## Phase 3: User Story 1 - A merge the loop made is proven, not stranded (Priority: P1) 🎯 MVP

**Goal**: the `pull_request: closed` prove path cannot be displaced by a
scheduled tick or another merge's own prove run (prevention, Q2 mechanism
A), and an item already stranded by a past displacement — or Q3's
`uncorrelated` case, which prevention does not address — is driven to
prove through spec 060's existing directed dispatch, at most once, without
waiting synchronously (recovery, Q3).

**Independent Test**: drive one board item to a merged fix PR while a
second entrant contends for `wing-commander-board-loop`, and confirm
`prove-gate`/`prove` still execute. Then, separately, take an issue already
carrying a displacement `prove` marker and let the recovery run: the issue
receives the proof outcome, never a fresh triage comment.

### Prevention — the ordinary prove path's own concurrency group (research.md D1/D2)

- [X] T007 [US1] `.github/workflows/board-loop.yml`: `prove-gate`'s
  `concurrency.group:` expression (`:3986-3993`) gains a new middle branch,
  keyed by the merged PR's own number, between the existing directed
  branch and the trailing shared-group fallback — the directed branch
  (first `&&`/`||` pair) is preserved byte-for-byte (FR-004):
  ```yaml
      group: >-
        ${{ (github.event_name == 'workflow_dispatch' && inputs.directed-stage != '') &&
        'wing-commander-board-loop-directed-proof' ||
        (github.event_name == 'pull_request' && format('wing-commander-board-loop-prove-{0}', github.event.pull_request.number)) ||
        'wing-commander-board-loop' }}
  ```
- [X] T008 [US1] `.github/workflows/board-loop.yml`: `prove`'s
  `concurrency.group:` expression (`:4166-4173`) gets the **identical**
  raw text T007 wrote (Gate 129 / T017 below asserts the two jobs never
  desync, since `prove`'s `needs: prove-gate` requires they mean the same
  group).
- [X] T009 [US1] Guarantee-sentence edit (FR-005/FR-021, research.md D2/D9)
  — one content change, folded into three live sites, none of them a new
  sentence:
  1. `specs/060-self-redrive-concurrency/contracts/concurrency-groups.md`
     — replace "## The guarantee"'s blockquote with
     contracts/prove-path-concurrency.md's amended text (the "...or each
     other when they prove distinct merged items" clause); replace the
     "Groups, per job" table's `prove-gate`/`prove` row with
     contracts/prove-path-concurrency.md's table; remove the "What does
     not change" bullet about the hourly tick displacing a queued
     `pull_request: closed` run (now false).
  2. `specs/057-autonomous-board-loop/contracts/board-loop-workflow.md`'s
     "Concurrency" section — restate the same amended sentence and the
     updated per-job table.
  3. `.github/workflows/board-loop.yml`'s 8 per-job `concurrency:`
     comments (`select` `:135`, `triage` `:1010`, `route` `:1490`, `fix`
     `:1964`, `review` `:2513`, `readiness` `:3523`, `prove-gate` `:3985`,
     `prove` `:4165`) — replace the sentence verbatim in every one; Gate
     101 (`verify-concurrency-guarantee-statement.py`) diffs these 8
     blocks plus site 2 above against site 1's canonical text and needs no
     code change for a content-only edit (`EXPECTED_YAML_BLOCK_COUNT = 8`
     is unchanged — D1 adds no job). Also update the non-gated descriptive
     restatement at `board-loop.yml:82` for consistency (outside Gate
     101's own extraction, which only reads comments immediately preceding
     a `concurrency:` key).

### Recovery — a new step in `select` (research.md D3/D5/D6)

- [X] T010 [US1] `.github/workflows/board-loop.yml`: add a new step,
  "Recover a stranded prove (FR-011)", to the `select` job, placed
  immediately after "Fetch open issues and select the next board item"
  (id: `select`, currently `:324-571`) and before "Resume - read the board
  item marker and re-derive live state" (currently `:572`) — **see this
  run's `wing-commander-findings`: this placement differs from research.md
  D3/contracts/recovery-and-resume.md's stated "immediately after the
  existing displacement step", because the displacement step (`:216-301`)
  runs before `board-open-issues.json` exists (it is written by the
  `select`-id step itself, `:358`), and this new step's "is the issue
  still open" check (FR-011's edge case "the issue was closed by a human")
  needs that file already on disk rather than a second `gh` round trip.
  The displacement step's own two files
  (`$RUNNER_TEMP/board-recent-merges-by-issue.json`,
  `$RUNNER_TEMP/board-displacement-comments-by-issue.json`) are still on
  disk at this later point in the same job, so both inputs this step needs
  are available here.** Gated by the same `if:` the displacement and
  select steps already carry
  (`steps.killswitch.outputs.status != 'paused' &&
  steps.stand-down.outputs.status != 'in-flight'`, FR-012's re-check).
  Body:
  1. Read `board-recent-merges-by-issue.json` and
     `board-displacement-comments-by-issue.json`; build `open_issue_numbers`
     from `board-open-issues.json`'s `.[].number`.
  2. Call `board_prove_recovery.find_recoverable_items(merged_prs_by_issue,
     comments_by_issue, open_issue_numbers, bot_login)` (T004). Ownership
     (`board:owned`, head-in-this-repository) is inherited from the
     displacement step's own `gh pr list --label board:owned` query — no
     second ownership check (FR-013).
  3. If empty, no-op. Otherwise take the first (oldest) candidate; every
     other candidate is left untouched (FR-011b: still recoverable, not
     spent).
  4. Call `board_prove.directed_proof_group_busy(run_list_json,
     own_run_id=$GITHUB_RUN_ID)` against a fresh `gh run list
     --workflow=board-loop.yml --json databaseId,displayTitle,status -L
     20`. If busy: stop, write nothing durable, leave the item recoverable
     (FR-011a).
  5. If not busy: `gh workflow run board-loop.yml -f directed-stage=prove
     -f directed-issue=<issue> -f directed-pr=<merged_pr> -f
     directed-recovery=true`. **On that call's success** (before waiting
     for anything — this step never waits, research.md D3): write
     `python3 .github/scripts/board_item_marker.py --step prove
     --outcome-reason "<the candidate's own outcome_reason,
     unchanged>" --recovery-attempted` and post a comment naming that the
     displaced/uncorrelated proof is being recovered, distinct from spec
     060's own displacement comment (FR-014).
- [ ] T011 [US1] Follow quickstart.md Story 1 steps 1-3 (prevention
  rehearsal: a contended merge's `prove-gate`/`prove` still run; two
  merges' own prove runs never collide) and Story 1's "recovery half"
  steps 1-5 (a stranded item is dispatched, marked spent immediately, and
  the dispatched run's own comment states both the original condition and
  the recovery).

**Checkpoint**: The feature's own defect (spec.md "The deadlock") no
longer reproduces, and a merge already stranded by a past displacement is
driven to prove. User Story 1 is independently demonstrable here.

---

## Phase 4: User Story 2 - A merged fix is never re-triaged as if it were unfixed (Priority: P1)

**Goal**: an open issue whose loop-owned PR is MERGED and carries no proof
record is never resolved to `triage`, whether or not Phase 3's
displacement/recovery machinery has already touched it this tick.

**Independent Test**: with an issue carrying an `awaiting-merge` marker
whose PR resolves MERGED, run selection and resume against live-shaped
state. The item is not resolved to `triage`, and the three neighbouring
states (PR OPEN, PR CLOSED-unmerged, PR state unresolvable) each behave as
they do today.

- [X] T012 [US2] `.github/workflows/board-loop.yml`: the resume step's
  "resolved by number but not OPEN" clause (currently `:792-810`,
  `elif pr_from_marker and marker_step in FIX_OR_LATER_STEPS:` → always
  `step = "triage"`) splits on `pr_state` (research.md D7):
  ```python
            elif pr_from_marker and marker_step in FIX_OR_LATER_STEPS and pr_state == "MERGED":
                step = "prove"
                reason = "merged fix -- awaiting proof"
                pr_number = ""
                pr_state = ""
                branch = ""
                round_ = "0"
                base_sha = ""
            elif pr_from_marker and marker_step in FIX_OR_LATER_STEPS:
                step = "triage"
                reason = "stale marker -- recorded pr {0} is {1}, not open".format(
                    pr_number, pr_state)
                pr_number = ""
                pr_state = ""
                branch = ""
                round_ = "0"
                base_sha = ""
  ```
  The second clause is exactly today's code, now reached only for
  `pr_state == "CLOSED"` (unmerged) — FR-008's "falls to a fresh triage,
  unchanged". The first clause's `step = "prove"` is already a
  `FIX_OR_LATER_STEPS` member (`board_eligibility.py:80`) — no new step
  name (FR-009). Clearing every other field satisfies FR-007's "no branch,
  round or base SHA from the merged attempt leaks".
- [X] T013 [US2] `.github/scripts/verify-board-loop-resume-gating.py`
  (Gate 97): update `RESUME_CASES`' existing
  `("awaiting-merge, PR MERGED (issue still open) -> triage, FR-022
  cleared", ...)` case (currently `:886-888`) to expect `step = "prove"`
  instead of `step = "triage"`, retitled to name the new behaviour; leave
  the adjacent `("awaiting-merge, PR CLOSED -> triage, FR-022 cleared",
  ...)` case (`:883-885`) and the unrelated
  `("review, PR MERGED not board:owned -> triage, FR-022 cleared (#555)",
  ...)` case (`:923-926`, caught earlier by the `foreign` clause,
  untouched by T012) exactly as they are. Add a self-test mutation
  (`--self-test`) asserting that reverting T012's first clause back to
  `step = "triage"` is caught.
- [X] T014 [US2] Follow quickstart.md Story 2 steps 1-3: confirm the
  `MERGED` case resolves to `prove` with every abandoned-attempt field
  cleared, and that PR OPEN / CLOSED-unmerged / unresolvable each remain
  byte-identical to today.

**Checkpoint**: A merged-but-unproven issue is never re-triaged, with or
without Phase 3's displacement/recovery steps having run this tick. User
Stories 1 and 2 are both independently demonstrable here.

---

## Phase 5: User Story 3 - The concurrency arrangement is what a gate reads (Priority: P2)

**Goal**: which group `prove-gate`/`prove` join on a `pull_request` event,
and that the key distinguishes two merged items, is asserted against the
real `board-loop.yml`, not only described in a comment (spec.md "A rule
with no gate behind it").

**Independent Test**: run the gate against the real tree (it passes) and
against fixtures that put the `pull_request: closed` prove path back into
`wing-commander-board-loop`, that make the group key shared across
merges, and that desync `prove-gate` from `prove` (each fails, naming the
file and the property).

- [X] T015 [US3] `.github/scripts/board_prove.py`: extract
  `read_job_concurrency_group(workflow_path, job_name)` from
  `joins_directed_group()`'s (`:383-406`) inline "read a job's own
  `concurrency.group` text off the tree" step (research.md D8):
  ```python
  def read_job_concurrency_group(workflow_path, job_name):
      with open(workflow_path, encoding="utf-8") as fh:
          doc = yaml.safe_load(fh.read()) or {}
      job = (doc.get("jobs") or {}).get(job_name) or {}
      return (job.get("concurrency") or {}).get("group") or ""
  ```
  `joins_directed_group()`'s own workflow-level read is unchanged (a
  different shape — a *workflow*-level `concurrency:` block, for a future
  external dispatchable target); this function is additive.
- [X] T016 [US3] `.github/scripts/verify-board-prove.py` (Gate 89):
  extend with fixtures for `read_job_concurrency_group()` — reads
  `prove-gate`'s group text off a fixture `board-loop.yml`; reads a job
  with no `concurrency:` block (returns `""`); reads a job that does not
  exist (returns `""`).
- [X] T017 [US3] New Gate 129 — `.github/scripts/verify-prove-path-concurrency.py`
  (FR-018, research.md D8), asserting against the real `board-loop.yml`
  via `read_job_concurrency_group()` (T015):
  1. `prove-gate` and `prove`'s raw `pull_request`-branch group text is
     not the literal `wing-commander-board-loop`.
  2. That text contains the literal substring
     `github.event.pull_request.number`.
  3. `prove-gate` and `prove` resolve to identical raw group text.

  Fixtures (FR-020), both directions: the shipped `board-loop.yml` (pass);
  the `pull_request` branch reverted to `'wing-commander-board-loop'`
  (fail, naming the regression); the per-PR key replaced by a fixed string
  literal with no `.number` (fail); `prove-gate`/`prove` group text
  diverging (fail). Wire into `.github/workflows/lint-workflows.yml` with
  `if: "!cancelled()"`, immediately after Gate 128 (T005).
- [X] T018 [US3] Follow quickstart.md Story 5-equivalent (this spec's
  Story 3): run `python .github/scripts/run-local-gates.py` against the
  real tree (passes), then against each of T017's three fixture mutations
  (each fails, naming the broken property).

**Checkpoint**: The concurrency arrangement fails its own gate when
reverted, and that gate passes on the real tree. All three P1/P2 user
stories are independently demonstrable here.

---

## Phase 6: User Story 4 - The recovery is legible and costed on the issue (Priority: P3)

**Goal**: a maintainer reading only the lifecycle issue can tell that a
proof was displaced, that the loop recovered it, and what the recovery
cost — without reading a run log.

**Independent Test**: after a recovered prove, the issue carries the
displacement statement, the recovery statement, the proof outcome, and the
run's cost line under a label naming the recovery.

- [X] T019 [US4] `.github/workflows/board-loop.yml`: `prove`'s "Record the
  proof outcome" step (currently `:4421-4506`) reads
  `inputs.directed-recovery` and, on every comment arm (the `success` arm
  and each of the seven non-`success` arms in the `case "$reason" in ...
  esac` block, `:4459-4506`), appends one sentence when
  `inputs.directed-recovery == 'true'` naming that this proof was
  previously displaced/uncorrelated and has now been recovered — one
  shared string composed once (mirroring the existing `DIRECTED_ATTRIBUTION`
  env var pattern already on this step, `:4434-4442`), not eight separately
  worded copies (CLAUDE.md single-home, FR-014).
- [X] T020 [US4] Same step (T019): every `board_item_marker.py` CLI call
  in the `case` block (currently bare `--step prove`/`--step proven` at
  `:4461,4467,4472,4477,4482,4487,4492,4497,4502`) gains
  `--outcome-reason "$reason"` (the value `outcome_reason()` already
  computed for this run) on every non-`success` arm, and
  `--recovery-attempted` on every arm whenever
  `inputs.directed-recovery == 'true'` — so a later re-displacement of
  *this* run's own attempt cannot look like a fresh, unspent one
  (research.md D4's second bullet).
- [X] T021 [US4] `.github/workflows/board-loop.yml`: `prove`'s "Determine
  this run's outcome for the metrics record" step (currently
  `:4512-4541`) labels the run `"proof (recovered): <reason>"` instead of
  `"proof: <reason>"` (`:4539`) when `inputs.directed-recovery == 'true'`
  (FR-015) — distinct from every label spec 060's taxonomy already maps,
  no new `outcome_reason` enum value.
- [ ] T022 [US4] Follow quickstart.md Story 6-equivalent (this spec's
  Story 4): after a recovered prove, read the issue alone and confirm it
  states the original condition, the recovery, and the outcome in one
  read; confirm the run's cost line and metrics record are searchable by
  the distinct `"proof (recovered): ..."` label via
  `wing-commander-metrics-summary`.

**Checkpoint**: A recovered prove is fully auditable from the issue alone.
All four user stories are independently demonstrable.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T023 Fold the remaining FR-021 contract updates into their live
  homes (research.md D9; T009 already folded the concurrency-groups.md/
  board-loop-workflow.md guarantee-sentence edit):
  - `specs/057-autonomous-board-loop/contracts/prove-step.md`'s
    "Re-drive" section — describe the recovery entry
    (contracts/recovery-and-resume.md), reconciling with spec 060's own
    edit there so the contract carries one description, not two.
  - `specs/057-autonomous-board-loop/contracts/board-item-marker.md` —
    document the two new fields (T002/T003).
  - `specs/060-self-redrive-concurrency/contracts/directed-proof-run.md` —
    note the recovery dispatch as a `stage == "prove"` directed run
    carrying `directed-recovery` (T006).
  - `specs/060-self-redrive-concurrency/contracts/proof-outcome-taxonomy.md` —
    "Recording rule" section documents the new `outcome_reason` marker
    field (T020); no new taxonomy value.
- [X] T024 Run `python .github/scripts/run-local-gates.py` and confirm all
  gates pass on the real tree, including new Gates 128-129 and amended
  Gates 89/97/101.
- [X] T025 Confirm every gate this feature adds or amends fails on its own
  negative fixture when the behaviour it checks is mutated (Principle
  VIII, FR-020) — e.g. temporarily revert T007/T008's group back to the
  shared literal and confirm Gate 129 (T017) fails; temporarily revert
  T012's `MERGED` clause to `step = "triage"` and confirm Gate 97's
  self-test (T013) fails. Revert each mutation afterward via a matching
  Edit and confirm the revert is byte-identical to HEAD with `git diff`
  (spec 058/060 precedent — this run's tooling has no `git checkout`/`git
  restore`).
- [X] T026 Confirm SC-008: feed `find_recoverable_items()` (or a live
  rehearsal) an item whose marker already carries `recovery_attempted:
  true` and confirm a second `select` run does not dispatch again, and
  that a `failure`/`unfinished`-reason marker is never returned by
  `is_recoverable()`.
- [X] T027 Final full-suite confirmation: re-run `python
  .github/scripts/run-local-gates.py` after T023-T026 and confirm the gate
  count is unchanged from T024 (no gate silently dropped), and that
  `verify-gate-wiring.py` accounts for Gates 128 and 129.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup; BLOCKS every user story
  phase — T010 (US1) calls `board_prove_recovery.find_recoverable_items()`
  (T004) and writes the two new marker fields (T002/T003); T019/T020/T021
  (US4) read `inputs.directed-recovery` (T006) and write the same marker
  fields.
- **User Story 1 (Phase 3)**: depends on Phase 2. Its own two halves
  (prevention T007-T009, recovery T010) have no dependency on each other
  and could be sequenced either way, but both land in this phase because
  spec.md's own User Story 1 independent test exercises both.
- **User Story 2 (Phase 4)**: depends on Phase 2 only (T012 does not call
  `board_prove_recovery.py` or read the new marker fields — it only
  produces the `step = "prove"` marker shape T010/T019 already know how to
  read). Independent of Phase 3; does not need Phase 3 to have landed
  first, though both touch `board-loop.yml`'s resume/select job so land
  them as sequential edits to the same file.
- **User Story 3 (Phase 5)**: depends on Phase 3's T007/T008 (the gate
  asserts the arrangement T007/T008 create) — must land after Phase 3, not
  merely after Phase 2.
- **User Story 4 (Phase 6)**: depends on Phase 3's T010 (the dispatch that
  sets `directed-recovery=true`) and Phase 2's T006 (the input's
  existence). Independent of Phases 4-5.
- **Polish (Phase 7)**: depends on every phase above.

### Parallel Opportunities

Genuine `[P]` opportunities are rare (see "Limited file-level
parallelism" above): T004 (new module `board_prove_recovery.py`) and T005
(its gate) are the clearest, since both are new files nothing else in
Phase 2 touches until T010 (Phase 3) imports the module.

---

## Parallel Example: Phase 2 (Foundational)

```bash
# T004 and T005 touch only new, dedicated files -- can be drafted
# alongside T002/T003 (board_item_marker.py, a different file):
Task: "New module board_prove_recovery.py: is_recoverable(), find_recoverable_items()"
Task: "New Gate 128: verify-board-prove-recovery.py fixtures"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (marker fields, recovery module,
   `directed-recovery` input declaration).
3. Complete Phase 3: User Story 1 — the deadlock no longer reproduces, and
   a stranded merge is recovered.
4. **STOP and VALIDATE**: quickstart.md Story 1's live-run steps (both
   halves).

### Incremental Delivery

1. Setup + Foundational → the marker/module substrate exists and is
   gated, observable by nothing yet.
2. Add User Story 1 → the defect's own regression no longer reproduces,
   and a stranded merge is recovered (MVP).
3. Add User Story 2 → a merged fix is never re-triaged, independent of
   whether Story 1's recovery step has run.
4. Add User Story 3 → the arrangement Story 1 introduced is gated, not
   just commented.
5. Add User Story 4 → a recovered prove is auditable from the issue
   alone.
6. Polish → contract fold-ins and full-suite confirmation.

### Notes

- `[P]` tasks = different files, no dependencies (rare in this feature).
- `[Story]` label maps a task to its user story for traceability; tasks
  with no `[Story]` label in Phases 1, 2 and 7 are setup/foundational/
  cross-cutting.
- Commit after each task or logical group; re-run `python
  .github/scripts/run-local-gates.py` after every `board_prove.py`,
  `board_item_marker.py`, `board_prove_recovery.py` or `board-loop.yml`
  edit, since all four are gate-covered and edits compound quickly.
- Out of Scope (spec.md): no re-detection of displacement (Phase 3 reuses
  `board_prove_displacement.find_undetected_merges()`'s own output
  verbatim), no change to what `board_prove.py` decides is Actions-only,
  no change to the merge gate itself.

## Maintainer Feedback — FR-011 case (a) unreachable
- [ ] In board-loop.yml's displacement step (~:319, inside the `find_undetected_merges()` marker write), pass `--outcome-reason "$(printf '%s' "$row" | jq -r .recorded_reason)"` so the written `prove` marker carries `RECORDED_REASON`, sourced from `find_undetected_merges()` as the one home.
- [ ] Extend Gate 128 (`verify-board-prove-recovery.py`) to assert the displacement-step writer actually passes `--outcome-reason`, not just that the reader accepts it.


## Maintainer Feedback — directed prove-gate dispatch can never reach prove
- [ ] In `prove-gate` (board-loop.yml ~:4471), replace the invalid `gh pr view --json merged` field: on `workflow_dispatch`, run `gh api "repos/$GITHUB_REPOSITORY/pulls/$PR_NUMBER" > "$RUNNER_TEMP/board-prove-pr.json"` (fail loudly on error) and take `merged` from `.merged`.
- [ ] Fix `BOARD_PR_OWNED_JQ`'s ownership test (~:4496) to read off the fetched file instead of `.pull_request` on `$GITHUB_EVENT_PATH`, which is null on `workflow_dispatch`.
- [ ] Add a fixture driving the directed `workflow_dispatch` branch through `prove-gate` end to end.
- [ ] Reconcile `contracts/recovery-and-resume.md`'s "Dispatch" section, which currently claims live-state re-derivation this branch doesn't actually do.


## Maintainer Feedback — Gate 129 can't parse a three-arm prove concurrency expression
- [ ] Extend the Gate 129 / spec-cross-reference parser to accept an optional middle `format('<prefix>{0}', github.event.pull_request.number)` arm between the directed and ordinary arms, comparing its prefix against a new table column.
- [ ] Add self-test mutations: wrong middle-arm prefix, missing middle arm, unexpected middle arm.
- [ ] Update spec 089's `contracts/skill-drift-gate.md` step 4 to describe the three-arm shape.
- [ ] Add a "`pull_request: closed` group" column to spec 060's `concurrency-groups.md` holding `` `wing-commander-board-loop-prove-` `` (PR number noted outside the backticks), fixing the accidental brace-parsing in the ordinary column.

## Maintainer Feedback — Gate number collisions
- [ ] Renumber `verify-board-prove-recovery.py` from Gate 128 (colliding with spec 074's #821) to **Gate 136**.
- [ ] Renumber `verify-prove-path-concurrency.py` from Gate 129 (colliding with main's spec-cross-reference Gate 129 at lint-workflows.yml:4739) — either fold it into Gate 136 since Gate 89's byte-pin already covers FR-018, or give it **Gate 137** if still free.
- [ ] Update every citing location: lint-workflows.yml:4783/4793/4797/4805; both scripts' line-2 headers; verify-board-prove.py:127; tasks.md lines 17, 18, 58, 112, 147, 183, 369, 383, 465, 526.

## Maintainer Feedback — false displacement record from this PR's own new concurrency group
- [ ] In `select`'s displacement step (board-loop.yml :216-321), skip (defer to the next tick) any merge whose `board-loop.yml` `pull_request` run isn't `completed`, matched by `headBranch` to the PR's `headRefName`, so a merge mid-wait in its own new per-PR group isn't falsely reported as displaced.
- [ ] Add a fixture covering a merge whose own `pull_request` prove run is still in progress when the displacement step runs.
- [ ] Verify, once the FR-011 `--outcome-reason` fix lands, this skip also prevents a duplicate proof dispatch on the next tick (today's busy check only sees `[directed:` runs).

## Maintainer Feedback — resume step's MERGED step=prove path has no consumer
- [ ] In `board_eligibility.select()`'s fallback, hold fix-or-later markers whose PR is MERGED, next to the existing `prove` skip (FR-009), so the oldest such item stops being re-admitted every tick.
- [ ] Fix the stale docstrings at `board_eligibility.py:362` and `board_prove_displacement.py:8`.


## Maintainer Feedback — recovery step has no continue-on-error and sits in front of resume
- [ ] Add `continue-on-error: true` to the recovery step (board-loop.yml ~:837) plus an `::error::` annotation, following the closed-without-landing precedent at :340, so a persistent `gh` failure there doesn't fail `select` and stall the board every tick.
- [ ] Write the spent marker before dispatching, so a dispatch that succeeds but whose comment fails doesn't cause a duplicate dispatch on the next tick (SC-008).


## Maintainer Feedback — recovery never checks a maintainer stop request
- [ ] Split the recovery step into three: pick the candidate, run `wing-commander-board-stop-check` for that issue, then dispatch gated on `paused != 'true'` (FR-012), so the kill-switch read isn't minutes stale by dispatch time.

## Maintainer Feedback — two arms of the dispatched run don't record the recovery
- [ ] "Close the issue on the merge evidence alone" (board-loop.yml ~:4725) must write `proven` with `--recovery-attempted` and the recovery notice, matching the other success arm.
- [ ] Add a recovery variant to the metrics label at ~:4964 (FR-015).
- [ ] At ~:4777, fall back to `inputs.directed-pr` when `github.event.pull_request.number` is empty (`|| inputs.directed-pr`), matching `prove-gate`'s own pattern (FR-002).
