# Tasks: The Board Loop — A Scheduled Run Takes One Open Issue From Triage To Proven

**Input**: Design documents from `specs/057-autonomous-board-loop/`
(plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Prerequisites**: plan.md, spec.md, research.md, data-model.md,
contracts/, quickstart.md — all present and read in full.

**Tests**: This repository's own testing convention (plan.md "Testing")
is a script that is both the runtime decision and its own PR-time proof —
one script, two invocations (checked-in fixtures at PR time, live GitHub
data at runtime). There is no separate `tests/` tree for the new decision
scripts; each gate script's fixture set is created in the same task as the
script and is listed in that task's description. Composite-level fixtures
follow the existing `wing-commander-stage-findings/tests/` convention
(`run-tests.sh` beside the composite).

**Organization**: Tasks are grouped by user story (spec.md priorities) so
each story is independently testable per its own "Independent Test"
section. All of User Story 1–5 and 7 are Priority P1; User Story 6 is
Priority P2. Phases below place the P1 stories first, in spec.md's own
order, then the P2 story (User Story 6), matching the template's "priority
order" rule while keeping the causal pipeline order (prove is entered only
after a PR that readiness (US5) reported ready is merged by a human) and
the stop-handling story (US7) after the job bodies it gates (US1–US5)
exist.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on another
  incomplete task in this list)
- **[Story]**: Which user story this task belongs to (US1–US7); Setup,
  Foundational and Polish tasks carry no story label
- Every task names its exact file path

## Path Conventions

This is a GitHub Actions pipeline repository, not an application with
`src/`/`tests/` directories. New files live under `.github/workflows/`,
`.github/actions/`, `.github/scripts/` and `.github/schemas/`, matching
plan.md's Project Structure and this repository's existing layout.

---

## Phase 1: Setup

**Purpose**: The workflow skeleton and the one documentation change that
every later phase's fixtures/labels reference.

- [X] T001 [P] Create `.github/workflows/board-loop.yml` skeleton: header
  comment stating why this workflow is not a published stage (FR-062/
  FR-063, mirroring `auto-release.yml`'s own "it releases THIS repository,
  not an adopter's" wording), `on: schedule` (a PR-reviewed cron
  placeholder in `auto-release.yml`'s spirit), `workflow_dispatch: {}`, and
  `pull_request: types: [closed]` triggers, and
  `concurrency: { group: wing-commander-board-loop, cancel-in-progress: false }`
  (FR-048) — no jobs yet (contracts/board-loop-workflow.md).
- [X] T002 [P] Add a `board:stalled` row to `docs/setup.md`'s existing
  manual label table: applied by the loop on round-budget exhaustion
  (FR-030), a post-push backstop breach (FR-021), or an already-fixed
  hand-over (FR-012); cleared only by a human removing the label
  (contracts/labels-and-cross-links.md, research.md D22).

**Checkpoint**: The workflow file exists and can be edited by every later
phase; the label is documented before any task applies it.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Entry gates, issue selection, and the board-item marker —
every job in every later phase reads or writes through this layer before
it can act.

**⚠️ CRITICAL**: No user story's job wiring can be added to
`board-loop.yml` until this phase is complete.

- [X] T003 Add the entry-gate kill-switch check to `board-loop.yml`: the
  exact `if: vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'` idiom
  `auto-release.yml` already uses at every durable-action boundary
  (research.md D2), gating the `select` job.
- [X] T004 [P] Create `.github/scripts/board_stand_down.py` implementing
  the "an implement cycle is in flight" check named in
  contracts/board-loop-workflow.md's entry gate 2: `gh run list
  --workflow=implement.yml --status=in_progress --json databaseId`
  returning non-empty (research.md D16, FR-049).
- [X] T005 Wire entry gates 1 (T003) and 2 (T004) into `board-loop.yml`'s
  `select` job: on a pause, stand down and record the pause as a pause,
  not a failure (FR-046, SC-006); on an in-flight implement cycle, stand
  down and record it (FR-049); either way no agent is invoked and the run
  ends.
- [X] T006 [P] Create `.github/scripts/board_eligibility.py` with
  `classify_issue(issue, labeled_events)`, `is_excluded(issue)`, and
  `select(open_issues, labeled_events_by_issue)` exactly as specified in
  contracts/eligibility-and-selection.md (FR-006/FR-008/FR-009/FR-010):
  maintainer-authored/-labeled decided from `authorAssociation` and the
  `labeled` timeline event's `actor.login` (never label presence alone —
  the branch FR-008's answer exists for), pipeline-labeled from FR-006's
  fixed label list (`pipeline-defect` and the watchdog's other finding
  classes, `auto-update:*`, `auto-release:failed`, `found-by:*`)
  regardless of actor, and exclusion on `state == closed`, any
  `disposition:*` settled marker, `board:stalled`, or any `stage:*`/
  `spec:*` label.
- [X] T007 Create `.github/scripts/verify-board-eligibility.py` with the
  four FR-064-bullet-2 fixtures under
  `.github/scripts/tests/board-eligibility/` (maintainer-authored, no
  label → admitted `maintainer-authored`; maintainer-applied entry label →
  admitted `maintainer-labeled`; the identical label applied by the bot's
  own actor login → NOT admitted `ineligible`; a pipeline-only label
  (`pipeline-defect`) → admitted `pipeline-labeled` regardless of actor),
  asserting `classify_issue()`'s exact return value and failing loudly if
  any fixture file is missing.
- [X] T008 Register `verify-board-eligibility.py` as the next sequential
  `Gate N — board eligibility` step in `.github/workflows/lint-workflows.yml`
  (research.md D24) so `run-local-gates.py` picks it up automatically.
- [X] T009 Wire the `select` job in `board-loop.yml` to call
  `board_eligibility.py`'s `select()` against `gh issue list --json
  number,author,authorAssociation,labels,state,createdAt` and the
  per-candidate `labeled` timeline events; on no eligible issue, the job
  summary states "nothing to do", no further job runs, and no agent is
  invoked (SC-009); on a hit, the selected issue number is passed to every
  downstream job.
- [X] T010 [P] Create `.github/scripts/board_item_marker.py` with
  `read_marker(issue_comments) -> dict | None` and
  `write_marker(step, round, pr, branch, base_sha) -> str` implementing
  the HTML-comment shape
  (`<!-- wing-commander-board-item: {"step":...,"round":...,"pr":...,"branch":...,"base_sha":...} -->`)
  and edit-most-recent-status-comment semantics of
  contracts/board-item-marker.md.
- [X] T011 Wire the marker's read side into `board-loop.yml`: a resuming
  run reads the marker (T010) on the selected issue's most recent bot
  comment as a fast path only, then re-derives `branch` (`git ls-remote
  origin refs/heads/<branch>`), `pr` (`gh pr list --search "<issue_number>
  in:body" --json number,state`), and `step` (the PR's own live state and
  review-finding count) before any durable action, falling back to live
  state on a missing/unparsable/stale marker rather than to a second
  branch/PR or undefined behavior (FR-054).
- [X] T012 Wire the standard per-agent-step pattern into `board-loop.yml`:
  `wing-commander-context`'s App-token mint feeding `env.WC_BOT_TOKEN`, the
  post-agent credential-refresh triple (spec 052) via an `if: always()`
  step immediately after every agent step this feature adds, with every
  later step in the job reading the relayed variable rather than a raw
  earlier output (research.md D19), and `wing-commander-metrics-summary`
  immediately after every agent step with the correct
  `transcript-path`/`model`/`max-turns`/`ceiling` inputs (research.md D20,
  FR-047, SC-010).
- [X] T013 Add a `resolve-model` job to `board-loop.yml` reusing
  `wing-commander-9-pr-conversation.yml`'s model-tier resolution verbatim
  (default `vars.WING_COMMANDER_BOARD_LOOP_MODEL`, fallback
  `claude-sonnet-5`, escalated to `claude-opus-5` when the issue (for
  triage/route) or PR (for fix/review) carries `model:opus`) and
  `implement.yml`'s `Compute agent turn ceiling` step shape verbatim
  (research.md D18); declare the round-budget constant `5` (data-model.md
  "Configuration Constants") alongside, consumed by the review round loop
  (US4) and the round-budget-exhaustion checks (US4/US1/US2).
- [X] T014 Wire every job's closing step in `board-loop.yml` to post its
  outcome on the originating issue — the triage verdict and its evidence,
  the route and its reason, the PR, each review round's outcome, the
  readiness report or the unmet condition, the human merge, and the proof
  run, per whichever step that job represents (FR-044) — ending with the
  marker write (T010).

**Checkpoint**: The workflow can select an issue, stand down correctly,
and track/resume a board item's step. No board step (triage onward) is
implemented yet.

---

## Phase 3: User Story 1 - An issue its own evidence already answers is closed without a fix (Priority: P1) 🎯 MVP

**Goal**: Triage reads the cited run's execution-output record and current
`main`'s commits, and closes the issue on exactly one of two code-derived
grounds — never on an agent's unverified proposal.

**Independent Test**: Point the loop at a fixture issue citing a run whose
record carries a 429 rate-limit event, one turn, zero cost — confirm
closed with evidence quoted, nothing else created. Repeat with a genuine
failure (stays open), an "already fixed" proposal naming a real commit
(NOT closed, `board:stalled` applied, run ends for that item).

### Implementation for User Story 1

- [X] T015 [P] [US1] Create `.github/scripts/board_triage.py` with
  `check_rate_limit(run_transcript_path)` delegating to
  `wing-commander-agent-verdict`'s existing rate-limited classifier (spec
  047, research.md D4 — never a second parse of `rate_limit_event`/
  `api_error_status`), `check_action_bump(run_commit_sha, workflow_files)`
  (NEW: for each workflow file, diffs its `uses: owner/action@ref` lines
  as pinned at the run's commit against the same file's lines on current
  `main`, returning `{workflow_file, action_ref, run_pin, main_pin}` for
  the first divergent pin where `main`'s is newer, else `None`), and
  `triage(issue, cited_run)` returning the `TriageVerdict` shape from
  data-model.md "Triage Verdict" — read-only until the return value
  (FR-011), closing only on the two grounds (FR-012), returning
  `outcome: handover` (never a close) with the proposal and named commit
  recorded when the agent proposes "already fixed on `main`" (FR-012's
  explicit deferral), returning `outcome: proceed, ground:
  evidence_unavailable` when the cited run's transcript cannot be fetched
  — expired artifact, missing run, API error (FR-014) — and returning
  `outcome: proceed` with no ground when the issue cites no run at all
  (edge case, spec.md).
- [X] T016 [US1] Create `.github/scripts/verify-board-triage.py` with the
  six FR-064-bullet-1 fixtures under `.github/scripts/tests/board-triage/`
  (429 present → `closed, rate_limit`; 429 absent, genuine failure →
  `proceed`; cited run's artifact expired/missing → `proceed,
  evidence_unavailable`; `main` ahead of the run's action pin → `closed,
  action_bump`; pins equal → `proceed`; agent proposes "already fixed on
  `main`" naming a real commit → NOT closed, `handover` with
  `board:stalled` applied and the proposal+commit recorded), asserting the
  exact `TriageVerdict` fields per fixture.
- [X] T017 [US1] Register `verify-board-triage.py` as the next sequential
  `Gate N — board triage` step in `.github/workflows/lint-workflows.yml`.
- [X] T018 [US1] Add the `triage` job to `board-loop.yml`: a
  triage-propose agent step (read-only tool allowlist, web tools never per
  FR-057, the issue body and non-maintainer comments framed as data only
  per FR-055/FR-056, never naming a downstream consumer of this repository
  per FR-058) whose proposal feeds `board_triage.py`'s `triage()` for the
  gated verdict (Principle IX); on `outcome: closed`, quote the evidence's
  own fields verbatim in the closing comment (FR-013) and end the run for
  that item with no branch/PR/label beyond the close (FR-015); on
  `outcome: handover`, record the proposal and named commit, apply
  `board:stalled`, and end the run; on `outcome: proceed`, continue to the
  `route` job (Phase 4).
- [X] T019 [US1] Wire the disagreement-recording path in the `triage` job:
  when the triage-propose agent proposes a close the gate's re-derivation
  does not support (e.g. "just a rate limit" against a record with no
  rate-limit evidence), nothing is closed and the disagreement is recorded
  verbatim on the issue (edge case, spec.md).

**Checkpoint**: The loop can autonomously close a rate-limited or
action-bump issue, hand over an "already fixed" proposal, and otherwise
proceed to route — independently testable and deployable as a
triage-only increment.

---

## Phase 4: User Story 2 - Shape decides the route, and code has the last word (Priority: P1)

**Goal**: The agent proposes fix-shaped or spec-shaped; a deterministic
size-and-path-plus-contract-widening backstop can only narrow that
proposal, never widen it, both before any push and again on the final
diff.

**Independent Test**: Feed the router a fix-shaped fixture under
threshold (routes to fix), a spec-shaped fixture (routes to
`spec-request`, no branch cut), and a fixture where the agent proposes
"fix-shaped" for a change that breaches the board's backstop (re-routed to
`spec-request`, reason names the threshold and measured value); confirm a
contract-widening fixture routes to `spec-request` regardless of size.

### Implementation for User Story 2

- [X] T020 [P] [US2] Extract `pr-conversation.yml`'s `classify-and-announce`
  inline `jq` size/path check into a new composite
  `.github/actions/wing-commander-size-path-backstop/action.yml` taking
  `file-changes` (required JSON, the same shape
  `drafted-content.file-changes` already produces), `max-files` (default
  `3`), `max-lines` (default `40`), and returning `over-threshold`,
  `measured-files`, `measured-lines` (research.md D5).
- [ ] T021 [US2] Repoint `pr-conversation.yml`'s `classify-and-announce`
  job at `wing-commander-size-path-backstop`, passing no `max-files`/
  `max-lines` override, so its existing behavior is byte-identical
  (research.md D5).
  **BLOCKED (2026-09-22, cycle 2)**: the inline jq this task repoints sits
  inside a per-classification-leg `map()` pipeline that also rewrites
  `category`/`drafted-content` on the over-threshold branch, and
  pr-conversation.yml has no existing behavioral test harness (unlike Gate
  4's auto-update-spec-kit-tests) to prove a refactor byte-identical before
  it ships. Repointing this specific call site blind, under this cycle's
  turn budget, was judged too large a regression risk to a live, production
  routing decision to attempt without one. The composite itself
  (`wing-commander-size-path-backstop/action.yml`) is built and is
  board-loop.yml's own route job's single home for the formula (T020,
  T023, T028); a waiver in `single-home-waivers.json` (`size-path-backstop`
  check, `pr-conversation.yml`) records pr-conversation.yml's own call site
  as the known, temporary exception, with a pointer back to this task.
  Recommended follow-up: add a behavioral harness for
  `classify-and-announce` (mirroring Gate 4's extraction-and-execution
  approach) in its own change, THEN repoint this call site against it.
- [X] T022 [P] [US2] Create
  `.github/actions/wing-commander-size-path-backstop/tests/run-tests.sh`
  with fixtures covering under/over threshold independently by files and
  by lines, parameterized rather than hardcoding either caller's numbers
  (research.md D26).
- [X] T023 [P] [US2] Create `.github/scripts/board_route_backstop.py` with
  `contract_widened(diff_paths, diff_text)` (research.md D6: returns the
  subset of `diff_paths` touching a `workflow_call:` `inputs:`/`outputs:`
  block of any `.github/workflows/*.yml`, or the `inputs:`/`outputs:` keys
  of any `wing-commander-*` composite's `action.yml` — a structural check,
  independent of size), `route(agent_proposal, file_changes,
  board_max_files, board_max_lines)` (calls
  `wing-commander-size-path-backstop` with the board's own thresholds, ORs
  in `contract_widened()`, narrows `fix`→`spec` only, never widens —
  FR-017), and `route_final_diff(route_decision, final_diff)` (FR-021:
  re-applies `route()` to the pushed branch's final diff; on a newly
  introduced breach the branch/PR are left open under a notice, never
  deleted).
- [X] T024 [US2] Declare the board's own size-and-path backstop thresholds
  (`BOARD_MAX_FILES`/`BOARD_MAX_LINES` — a separate PR-reviewed constant,
  distinct from `pr-conversation.yml`'s 3/40, same narrow-only shape) as
  checked-in constants in `board-loop.yml`, passed to
  `board_route_backstop.py` (data-model.md "Configuration Constants").
- [X] T025 [US2] Create `.github/scripts/verify-board-route-backstop.py`
  with the four FR-064-bullet-3 fixtures under
  `.github/scripts/tests/board-route-backstop/` (under threshold → `fix`;
  over threshold by files → `spec-request`, reason names the measured
  files and the threshold; contract-widening diff, small otherwise →
  `spec-request` regardless of size; post-push final-diff breach →
  branch/PR left open with a notice, `spec-request` filed,
  `board:stalled` applied, nothing deleted).
- [X] T026 [US2] Register `verify-board-route-backstop.py` as the next
  sequential `Gate N — board route backstop` step in
  `.github/workflows/lint-workflows.yml`.
- [ ] T027 [P] [US2] Add `wing-commander-size-path-backstop` to
  `.github/scripts/verify-single-home-idioms.py`'s `DECLARED_HOMES`,
  pointing at `.github/actions/wing-commander-size-path-backstop/action.yml`,
  failing if the inline `jq` threshold logic reappears pasted a second
  time or if `pr-conversation.yml`'s call site still resolves the old
  inline path.
  **PARTIALLY DONE, BLOCKED on T021 (2026-09-22, cycle 2)**: the
  `DECLARED_HOMES` entry, the `check_size_path_backstop` structural scan
  (a third paste anywhere else in the tree fails Gate 60), and its
  `--self-test` coverage are done. The second half -- failing when
  `pr-conversation.yml`'s call site still resolves the old inline path --
  cannot land honestly while T021 itself is blocked (see its note): doing
  so would fail Gate 60 on every PR, including PRs with no relation to this
  feature, until a human lands T021. A `single-home-waivers.json` entry
  (`size-path-backstop` check, `pr-conversation.yml`, issue #408) records
  pr-conversation.yml's own occurrence as the named, temporary exception
  instead; removing that waiver is the completion signal for both T021 and
  the rest of this task.
- [X] T028 [US2] Add the `route` job to `board-loop.yml`: a route-propose
  agent step (read-only tools, issue body/comments framed as data) whose
  `fix`/`spec` proposal feeds `board_route_backstop.py`'s `route()`; on
  `spec-request`, create the `spec-request` artifact, cross-link the
  originating issue to it via `wing-commander-outstanding-task-item`
  (research.md D9) with the `Routed to spec-request` phrase
  (contracts/labels-and-cross-links.md), and end the run with no branch
  cut (FR-021); on `fix`, continue to the `fix` job (Phase 5); any
  re-route names the breached threshold and the measured value (FR-020).
- [ ] T029 [US2] Wire `route_final_diff()` (T023) into `board-loop.yml`
  after the fix step's push (Phase 5, T034), before the PR is reported
  ready: on a newly introduced breach, leave the branch/PR open under a
  notice pointing at the spun-off `spec-request`, apply `board:stalled`,
  and record the breach and both links on the issue (FR-021) — never
  delete the branch or PR.

**Checkpoint**: Fix-shaped and spec-shaped issues route correctly before
any push, and a late breach on the final diff re-routes rather than
merging or deleting work.

---

## Phase 5: User Story 3 - A fix-shaped issue becomes a green PR from fresh `main` (Priority: P1)

**Goal**: The fixer works from a `main` fetched in the same run, the full
local gate suite must be green before anything is pushed, and the PR and
issue cross-link each other.

**Independent Test**: Drive one run against a fixture issue describing a
one-file defect; confirm the branch was cut from a `main` fetched at run
time, the gate suite ran and was green before the push, the PR exists
citing the issue, and the issue carries the PR link. Repeat with a
locally-failing gate suite: nothing pushed, no PR opened, the failing gate
named on the issue.

### Implementation for User Story 3

- [ ] T030 [P] [US3] Add the `fix` job's second-branch/PR guard to
  `board-loop.yml`: before fetching `main`, re-derive live GitHub state
  (T011) for an existing branch/PR already associated with the issue; if
  one exists, skip the fetch/branch/push steps and resume at whatever step
  the existing PR's state implies (review or readiness) rather than
  cutting a second branch (FR-054, contracts/fix-step.md).
- [ ] T031 [US3] Add the `fix` job's fetch-and-branch steps: `git fetch
  origin main` fresh in this run, record `base-sha` as a step output the
  same way `implement.yml`'s `steps.base.outputs.base-sha` already does
  (research.md D7), then `git checkout -b fix/<issue_number>-<slug>
  <base-sha>` (FR-022/FR-023).
- [ ] T032 [US3] Add the fixer agent step to the `fix` job: model tier and
  turn ceiling from T013, write/push tool allowlist per research.md D23
  (web tools never, per FR-057), only maintainer-association content
  reaching the fixer as a directive — everything else framed as data
  (FR-055/FR-056) — and never naming a downstream consumer of this
  repository (FR-058), followed by the credential-refresh/metrics-summary
  pattern (T012).
- [ ] T033 [US3] Add the gate-suite step to the `fix` job: `python3
  .github/scripts/run-local-gates.py`, the exact CI invocation
  (research.md D8, FR-025); on non-zero exit, stop before any push,
  comment the failing gate's name on the issue, and open no PR (FR-024).
- [ ] T034 [US3] Add the push-and-PR step to the `fix` job: on a green
  gate suite, push the branch, open the PR with a body citing the
  originating issue (FR-026), and comment the PR link on the issue via
  `wing-commander-outstanding-task-item` with the `Fix opened` phrase
  (research.md D9, contracts/labels-and-cross-links.md).
- [ ] T035 [US3] Verify the mid-failure resume path: a run ending between
  the branch cut (T031) and the PR open (T034) leaves a branch with no PR;
  confirm the next run's guard (T030) finds the branch and re-enters the
  fixer step (T032) on the existing branch, never cutting a second one
  (contracts/fix-step.md "Failure mid-step").

**Checkpoint**: A fix-shaped issue reliably becomes a green, PR-linked
branch from fresh `main`, and an interrupted run resumes rather than
duplicating work.

---

## Phase 6: User Story 4 - A review the maintainer can read, on the PR (Priority: P1)

**Goal**: A context-isolated reviewer posts a GitHub-visible review with
schema-validated findings; in-scope findings are fixed and re-reviewed
on the same PR, out-of-scope findings become their own cross-linked
issues, and round-budget exhaustion stalls rather than merges.

**Independent Test**: Drive a fixture PR with one in-scope and one
out-of-scope defect. Confirm a PR review object exists carrying both, the
reviewer's invocation shared none of the fixer's context, the in-scope
finding is fixed by a later commit and re-reviewed, the out-of-scope
finding exists as its own issue carrying `Found by the code review of #N`,
and the PR diff never contains the out-of-scope fix.

### Implementation for User Story 4

- [ ] T036 [P] [US4] Create
  `.github/schemas/board-review-finding.schema.json` exactly as specified
  in contracts/review-and-findings.md: a JSON array whose items require
  `title` (string, `maxLength: 120`), `what` (string), `evidence` (object
  requiring `file_paths`, optional `detail`), `in_scope` (boolean), and
  `fingerprint_basis` (object requiring `file_path`, `gate_or_artifact`),
  `additionalProperties: false` at every object level.
- [ ] T037 [US4] Create
  `.github/scripts/verify-board-review-finding-schema.py` as a
  hand-written validator (D5-style, no third-party JSON Schema library)
  exposing `validate_finding()`, with fixtures: one well-formed finding
  (validates) and one per omitted required field (`title`, `what`,
  `evidence.file_paths`, `in_scope`, `fingerprint_basis`) — each rejected
  with the missing field named, under
  `.github/scripts/tests/board-review-finding-schema/`.
- [ ] T038 [US4] Register `verify-board-review-finding-schema.py` as the
  next sequential `Gate N — board review finding schema` step in
  `.github/workflows/lint-workflows.yml`.
- [ ] T039 [US4] Add the `review` job to `board-loop.yml`: a reviewer
  agent step run as a separate job with no shared transcript, memory, or
  prompt continuation from the fixer's invocation (FR-028, research.md
  D10), prompt input limited to the PR diff, the originating issue's body
  (framed as data), and the fix's own commit messages, read-only/
  PR-comment tool allowlist (web tools never, per FR-057; never naming a
  downstream consumer per FR-058); extracts the
  ` ```wing-commander-review-findings ` fenced block from the `.result`
  field of the last `type=="result"` transcript entry
  (contracts/review-and-findings.md "Channel").
- [ ] T040 [US4] Wire the reviewer's finding-posting step: `gh api
  repos/:owner/:repo/pulls/:number/reviews -f event=COMMENT -F
  body=@review-body.md` — never `APPROVE`/`REQUEST_CHANGES`, which GitHub
  rejects from the PR's own author identity (FR-029, research.md D10) —
  followed by the credential-refresh/metrics-summary pattern (T012).
- [ ] T041 [US4] Wire `verify-board-review-finding-schema.py`'s
  `validate_finding()` (T037) into the `review` job to filter malformed
  findings out of the extracted block, dropped and logged (same
  discipline as spec 056's D5/D11).
- [ ] T042 [US4] Wire the in-scope round loop in `board-loop.yml`: each
  `in_scope: true` finding triggers a fixer follow-up commit on the same
  branch (reusing the fixer step, T032), increments the round count in the
  marker (T010), and re-runs the `review` job (T039) against the new head
  (FR-031) — repeating until zero open in-scope findings or the round
  budget (T013, 5) is spent.
- [ ] T043 [US4] Wire out-of-scope filing in the `review` job: each
  `in_scope: false` finding is filed via
  `wing-commander-durable-failure-issue` with `operation: report`,
  `label: found-by:board-review`, `marker:
  sha256("<issue>|<norm(title)>|<norm(file_path)>")` (research.md D12,
  same `norm` rule as spec 056's D6), `comment-body-file` carrying `Found
  by the code review of #<PR>` plus the quoted finding blockquoted as
  untrusted data (FR-032, FR-059), cross-linked from the originating issue
  via `wing-commander-outstanding-task-item` and never held against the
  PR's readiness.
- [ ] T044 [US4] Wire round-budget exhaustion in the `review` job: when
  the round budget (T013) is spent with in-scope findings still open,
  leave the PR open and unmerged, post a stall notice on the issue naming
  the remaining findings, and apply `board:stalled` (FR-030) — the notice
  states that removing the label is the sole re-eligibility condition
  (FR-010).

**Checkpoint**: Every fix PR carries a GitHub-visible review; in-scope
findings converge or the item stalls visibly; out-of-scope findings become
their own issues without widening the PR.

---

## Phase 7: User Story 5 - The loop never calls a PR ready unless it can prove it (Priority: P1)

**Goal**: Every readiness condition is re-derived against the PR's exact
head SHA; the loop reports ready or names the unmet condition, and never
merges, approves, or enables auto-merge.

**Independent Test**: Run the readiness check against one fixture per
refusal branch (stale check summary, no checks, open findings, backstop
breach, kill switch set) and confirm each refuses with its own named
reason; run an all-clear fixture and confirm ready is reported with no
merge performed.

### Implementation for User Story 5

- [ ] T045 [P] [US5] Create `.github/scripts/board_readiness.py` with
  `evaluate(pr_number) -> ReadinessDecision` fetching `gh pr view
  <pr_number> --json headRefOid,statusCheckRollup` fresh at evaluation
  time (never a value captured earlier in the run — FR-036) and
  evaluating, in order: checks green on `head_sha` (every rollup entry
  belongs to `head_sha`; an empty rollup is `checks_green: false` —
  FR-037); the gate suite green on that same `head_sha`, read as the
  `lint-workflows` entry within that same fresh rollup, never a second
  local re-run (research.md D13); zero open `in_scope: true` findings
  (FR-033); the size-and-path backstop holding on the final diff, re-read
  from `route_final_diff()`'s own result rather than recomputed
  (contracts/readiness-report.md condition 4); and the kill switch clear,
  checked again at this exact moment (FR-051). `ready: true` only when all
  five hold.
- [ ] T046 [US5] Create `.github/scripts/verify-board-readiness.py` with
  the six FR-064-bullet-4 fixtures under
  `.github/scripts/tests/board-readiness/` (stale check summary over a
  newer head → not ready, SHA mismatch named; no checks at all on the head
  → not ready; one open in-scope finding → not ready, count named; final
  diff breaches the backstop → routes to `spec-request`, not merely "not
  ready"; kill switch set → not ready, stand-down recorded; all five
  conditions hold → ready, report posted, no merge performed).
- [ ] T047 [US5] Register `verify-board-readiness.py` as the next
  sequential `Gate N — board readiness` step in
  `.github/workflows/lint-workflows.yml`.
- [ ] T048 [US5] Add the `readiness` job to `board-loop.yml`, entered once
  the `review` job (T042) reaches zero open in-scope findings: calls
  `board_readiness.py`'s `evaluate()` (T045) against the current PR.
- [ ] T049 [US5] Wire the `ready: true` path in the `readiness` job: post
  a readiness report on the PR naming `head_sha` and each condition's
  result, record the same on the issue, and state that a human merge is
  awaited (FR-066) — never merge, approve, or enable auto-merge anywhere
  in the job's own API calls (FR-068).
- [ ] T050 [US5] Wire the `ready: false` path in the `readiness` job:
  leave the PR open, name `unmet_reason` on the issue (FR-067); for a
  final-diff backstop breach specifically, route through
  `board_route_backstop.py`'s `route_final_diff()` (T029) rather than
  merely reporting not-ready (contracts/readiness-report.md fixture 4);
  the item is picked up again on a later run, never polled in a loop.

**Checkpoint**: Readiness is reported or refused solely on re-derived
head-SHA evidence, and the loop performs no merge, approval, or
auto-merge anywhere.

---

## Phase 8: User Story 7 - One item at a time, and one human action stops it (Priority: P1)

**Goal**: A maintainer stop comment halts an in-flight item before its
next durable action, retargeting `pr-conversation.yml`'s existing `stop`
procedure to the issue thread; a human closing the issue mid-loop stops it
the same way.

**Independent Test**: Post a maintainer stop comment on an in-flight item
and confirm the loop halts before its next durable action and records
where it stopped. Close the issue mid-loop and confirm the same. (The
concurrency-queuing and kill-switch behaviors this story also names are
already structurally in place from Phase 1/T001 and Phase 2/T003, T005,
T012 — verified, not re-implemented, in Phase 10's quickstart drill.)

### Implementation for User Story 7

- [ ] T051 [P] [US7] Create the stop-comment handling procedure in
  `board-loop.yml`, reusing `pr-conversation.yml`'s existing `stop`
  procedure retargeted from a PR thread to the issue thread (research.md
  D17): scan the issue's own comments for the loop's most recent status
  comment carrying a `**Run:**` URL, extract and `gh run cancel` that run
  ID, skip the current run's own announcement by `GITHUB_RUN_ID`, gated by
  the same maintainer-association check `pr-conversation.yml` already uses
  (FR-052).
- [ ] T052 [US7] Wire the stop-comment check (T051) and a fresh issue
  `state` re-fetch as a gate re-checked immediately before every durable
  action across the `triage` (T018), `route` (T028), `fix` (T034),
  `review` (T040/T043), and `readiness` (T049) jobs in `board-loop.yml` —
  not only at job start (FR-051) — recording where the loop stopped
  whether the stop came from a maintainer comment (FR-052) or the human
  closing the issue (FR-053).

**Checkpoint**: A maintainer's stop comment or issue close halts the loop
at its next durable action, with the stop point recorded, across every job
phases 3–7 added.

---

## Phase 9: User Story 6 - Behaviour that only runs in Actions is proven before the issue closes (Priority: P2)

**Goal**: A human's merge of a readiness-reported PR resumes the loop at
the prove step via `pull_request: closed`; Actions-only behaviour is
re-driven through a dispatched run before the issue closes.

**Independent Test**: Merge a fixture fix PR that changes a
`.github/workflows/**` file; confirm the resume path re-drives a run and
closes the issue citing the run URL and outcome. Repeat with a failing
proof run (issue stays open), a docs-only merge (no re-drive, issue closes
on merge evidence alone), and a PR closed without merging (no proof run
dispatched, issue stays open).

### Implementation for User Story 6

- [ ] T053 [P] [US6] Extract `auto-release.yml`'s `dispatch-release` job
  (attempt-token correlation, `gh workflow run` + poll-by-title-and-
  timestamp, wait on `status` to `completed`, verify the durable side
  effect independent of the run's own conclusion) into
  `.github/actions/wing-commander-dispatch-and-wait/action.yml`,
  parameterized by `workflow-file`, `workflow-inputs` (JSON, passed as
  `-f` pairs), `attempt-token`, and `poll-attempts`/
  `poll-interval-seconds` (defaulted to `auto-release.yml`'s existing
  values), returning `run-url` and `conclusion` (research.md D14).
- [ ] T054 [US6] Repoint `auto-release.yml`'s `dispatch-release` job at
  `wing-commander-dispatch-and-wait`, preserving its existing dispatch
  behavior (attempt-token, correlate-by-title, poll `status` to
  `completed`, verify the tag independently) unchanged.
- [ ] T055 [P] [US6] Create
  `.github/actions/wing-commander-dispatch-and-wait/tests/run-tests.sh`
  with fixtures covering successful correlation, ambiguous/absent
  correlation (empty `run-url`), and poll-budget exhaustion
  (`conclusion: timeout`).
- [ ] T056 [P] [US6] Add `wing-commander-dispatch-and-wait` to
  `.github/scripts/verify-single-home-idioms.py`'s `DECLARED_HOMES`,
  pointing at `.github/actions/wing-commander-dispatch-and-wait/action.yml`,
  failing if the correlation/poll block reappears pasted a second time or
  if `auto-release.yml`'s call site still resolves the old inline path.
- [ ] T057 [P] [US6] Create `.github/scripts/board_prove.py` deciding
  `actions_only` from the merged PR's changed paths (research.md D15):
  `docs/**`/`specs/**`-only, or `.github/scripts/verify-*.py`-only
  (already proven by that PR's own required checks) →
  `actions_only: false` with the reason recorded; any other changed path
  → `actions_only: true`.
- [ ] T058 [US6] Add the `prove` entry gate to `board-loop.yml`'s
  `pull_request: closed` trigger path: fires only when the closing PR's
  body cites an issue this loop selected (the marker, T010) and
  `github.event.pull_request.merged == true`; a closed-not-merged PR is
  recorded on the issue and the prove step is never entered (FR-041, User
  Story 6 scenario 5).
- [ ] T059 [US6] Add the `prove` job to `board-loop.yml`: resumes the item
  at the prove step rather than re-selecting it from the top (FR-041),
  calls `board_prove.py` (T057) to decide `actions_only`; when false,
  closes the issue on the merge evidence alone with the reason recorded
  (FR-041 scenario 4).
- [ ] T060 [US6] Wire the `actions_only: true` re-drive path in the
  `prove` job: call `wing-commander-dispatch-and-wait` (T053) against the
  wrapper workflow that can dispatch the changed behavior, record
  `run-url`/`conclusion` on the PR or issue via
  `wing-commander-outstanding-task-item` with the `Re-driven to prove the
  fix` phrase (FR-042, contracts/labels-and-cross-links.md); on `success`,
  close the issue citing the run URL and outcome (FR-043); on
  `failure`/`timeout`, leave the issue open carrying the run URL; on an
  uncorrelated dispatch (`run-url` empty), leave the issue open carrying
  that fact.

**Checkpoint**: A merged fix that changes Actions-only behaviour is proven
by a re-driven run before its issue closes; every other merged fix closes
on recorded merge evidence alone.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end gate wiring and the quickstart drills that only
make sense once every job exists.

- [ ] T061 [P] Run `python .github/scripts/verify-single-home-idioms.py`
  and `python .github/scripts/run-local-gates.py` against the real
  workflow/composite tree (quickstart.md step 2), confirming both
  repointed call sites (`pr-conversation.yml` →
  `wing-commander-size-path-backstop`, `auto-release.yml` →
  `wing-commander-dispatch-and-wait`) resolve correctly and every new gate
  from Phases 2–7 and 9 is reachable through the auto-derived list
  (FR-065).
- [ ] T062 [P] Confirm each new gate script fails loudly rather than
  passing vacuously when its subject file is missing or a fixture is
  absent (Principle VIII), by temporarily inverting one fixture's expected
  verdict per script (quickstart.md step 1) and reverting after
  confirming the failure names the mismatched fixture.
- [ ] T063 Run the quickstart.md validation drills for User Stories 1–5
  and 7 (steps 3–7, 9) against fixture issues/PRs in a disposable/test
  repository and record each outcome.
- [ ] T064 Run the quickstart.md User Story 6 drill (step 8) in a
  disposable/test repository: a merged Actions-only fix resumes via
  `pull_request: closed`, a dispatched run URL and outcome are recorded,
  and the issue closes citing them; repeat for a failing proof run, a
  docs-only merge, and a closed-not-merged PR.
- [ ] T065 Run the quickstart.md untrusted-content drill (step 10): plant
  instruction-shaped text in a non-maintainer comment on an in-flight item
  and confirm it never reaches the fixer as a directive (FR-056) and never
  affects the board-item marker (T010).

**Checkpoint**: All ten quickstart sections pass; every gate is registered
and provably able to fail.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS every user story
  phase (no job can be added to `board-loop.yml` before selection, the
  entry gates, and the marker mechanism exist).
- **User Story 1 (Phase 3)**: Depends on Foundational only. Can ship alone
  as a triage-only increment (see Implementation Strategy).
- **User Story 2 (Phase 4)**: Depends on Foundational and on User Story 1
  existing as the job that hands off to `route` (T018 → T028), though its
  own scripts/composite (T020–T027) have no code dependency on US1.
- **User Story 3 (Phase 5)**: Depends on Foundational and on User Story 2
  handing off to `fix` (T028 → T030).
- **User Story 4 (Phase 6)**: Depends on Foundational and on User Story 3
  producing a PR to review (T034 → T039).
- **User Story 5 (Phase 7)**: Depends on Foundational and on User Story 4
  reaching zero open findings (T042 → T048).
- **User Story 7 (Phase 8)**: Depends on Foundational and on the job
  bodies from User Stories 1–5 existing (T052 re-checks the stop gate
  inside those jobs); its own new artifact (T051) has no code dependency
  on US1–US5.
- **User Story 6 (Phase 9)**: Depends on Foundational and, causally, on
  User Story 5 having produced a mergeable PR for a human to merge; its
  own scripts/composite (T053–T057) have no code dependency on US1–US5 or
  US7 and could be built earlier if staffed separately.
- **Polish (Phase 10)**: Depends on every phase above.

### Within Each Phase

- A gate script (e.g. `board_triage.py`, T015) precedes its
  `verify-board-*.py` counterpart (T016), which precedes that gate's
  registration in `lint-workflows.yml` (T017).
- A composite extraction (e.g. T020) precedes repointing its existing
  caller (T021) and precedes the `DECLARED_HOMES` entry that enforces the
  repoint (T027).
- Job-wiring tasks that edit `board-loop.yml` within the same phase are
  sequential (same file); new standalone script/schema/composite files are
  marked `[P]`.

### Parallel Opportunities

- All Setup tasks (T001, T002) are `[P]`.
- Within Foundational: T004, T006, T010 are `[P]` (independent new files).
- Within each user-story phase, the first new script/schema/composite file
  task is `[P]`; job-wiring tasks that edit `board-loop.yml` are not,
  since they share that one file within a phase.
- User Story 6 (Phase 9)'s four new-file tasks (T053, T055, T056, T057)
  are mutually `[P]`.

---

## Parallel Example: Foundational

```bash
# Launch the three independent new-file tasks together:
Task: "Create .github/scripts/board_stand_down.py per research.md D16"
Task: "Create .github/scripts/board_eligibility.py per contracts/eligibility-and-selection.md"
Task: "Create .github/scripts/board_item_marker.py per contracts/board-item-marker.md"
```

## Parallel Example: User Story 6

```bash
# Launch all four independent new-file tasks together:
Task: "Extract wing-commander-dispatch-and-wait composite from auto-release.yml's dispatch-release job"
Task: "Create wing-commander-dispatch-and-wait/tests/run-tests.sh fixtures"
Task: "Add wing-commander-dispatch-and-wait to verify-single-home-idioms.py's DECLARED_HOMES"
Task: "Create .github/scripts/board_prove.py per research.md D15"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL — blocks every story).
3. Complete Phase 3: User Story 1.
4. **STOP and VALIDATE**: run `verify-board-eligibility.py`,
   `verify-board-triage.py`, and quickstart.md step 3 against fixtures.
5. Deploy: the loop now autonomously closes rate-limited and
   action-bump-stale issues and hands over "already fixed" proposals —
   spec.md's own "Why this priority" for US1: an issue closed here costs
   no fix, no review, and no merge.

### Incremental Delivery

1. Setup + Foundational → the workflow can select and track an item.
2. + User Story 1 → triage-only autonomous closes (MVP).
3. + User Story 2 → shape-decided routing to fix or `spec-request`.
4. + User Story 3 → fix PRs open from fresh `main`, gated on a green
   local suite.
5. + User Story 4 → every fix PR gets a GitHub-visible, converging review.
6. + User Story 5 → readiness is reported (never merged) on re-derived
   head-SHA evidence.
7. + User Story 7 → a maintainer stop comment or issue close halts an
   in-flight item cleanly.
8. + User Story 6 → Actions-only fixes are re-proven after a human's
   merge before their issue closes.
9. Phase 10 → full gate-registry and quickstart validation.

Each step is independently testable per its own "Independent Test" above,
and each preserves every previous step's behavior — none narrows or
removes an earlier story's guarantee.

## Maintainer Feedback

- [ ] Resume implementation of `057-autonomous-board-loop` and complete every currently-unchecked task, T012 through T065, in the order listed in this file, checking each one off in the same commit that lands it (PR #451 review comment from @charlesguse).
- [ ] Do not defer any task to a later cycle while the current cycle's turn budget remains. If a task is genuinely blocked, name the specific task and the blocker on the lifecycle issue (#408) instead of silently deferring it.
- [ ] Run `python .github/scripts/run-local-gates.py` and confirm it is green before every push made in this cycle.
