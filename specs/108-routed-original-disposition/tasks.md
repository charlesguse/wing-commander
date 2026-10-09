---

description: "Task list for Routed-Original Disposition"
---

# Tasks: Routed-Original Disposition

**Input**: Design documents from `/specs/108-routed-original-disposition/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md,
contracts/duplicate-disposition.md, contracts/eligibility-and-readmission-delta.md,
contracts/gate-93-check-3-delta.md, contracts/closed-without-landing-notice.md,
quickstart.md

**Tests**: Not explicitly requested as a separate suite. This repository has
no pytest tree; every gate/decision script is its own subject, verified by a
checked-in `--self-test` fixture set run through
`python .github/scripts/run-local-gates.py` (plan.md "Testing"). Those
self-test tasks are modeled inline, in the phase that adds the script they
cover.

**Organization**: Tasks are grouped by spec.md's three user stories. US1 and
US2 are both P1 (equal priority, per spec.md: US2 is "the risk US1
creates"), sequenced US1 first here since US2's eligibility carve-out reads
state US1's disposition writes. Most tasks are same-file edits to
`.github/workflows/board-loop.yml` or `.github/scripts/board_eligibility.py`
and are therefore sequential (no `[P]`); a few touch distinct new files and
are marked `[P]` accordingly.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Line numbers cited below are as of `main` at the time this task list was
  written; if the file has moved on, locate steps by name (step `name:`
  strings quoted below) rather than by line number.

## Path Conventions

Single project (a GitHub Actions pipeline repository). All edits are under
`.github/`, `docs/`, and `specs/057-autonomous-board-loop/contracts/` — no
`src/`/`tests/` tree applies.

## A design decision this list fixes (not left further to implementation)

contracts/duplicate-disposition.md leaves the module's name, packaging, and
exact CLI shape to tasks.md (its own header: "name TBD by tasks.md"), and
plan.md's Structure Decision explicitly defers whether the module gets its
own gate. This list resolves both, plus one gap the contract's own text
does not close (recorded in this run's `wing-commander-findings` block
rather than fixed in the contract itself, per CLAUDE.md — spec docs are
historical once a feature's final PR merges, but this feature has not
shipped yet, so its own contracts are still this stage's to interpret, not
to silently patch):

- **Module**: `.github/scripts/board_duplicate_disposition.py`, shaped like
  `board_item_marker.py`'s CLI (argparse, called directly with
  `python3 .github/scripts/board_duplicate_disposition.py ...` from a job
  with no agent step (`route`), or via the pre-agent snapshot path
  `python3 -I "$RUNNER_TEMP/wc-pristine/scripts/board_duplicate_disposition.py" ...`
  from a job that runs one (`fix`, `readiness`) — the same split every
  existing `board_item_marker.py`/`board_spec_request_body.py` call site in
  `board-loop.yml` already observes, enforced by Gate 98
  (`verify-board-loop-helper-provenance.py`). Because the module must post
  a comment only if one is not already present (FR-009), it performs steps
  1–4 and 7 of the contract's sequence itself via `subprocess.run(["gh",
  ...])` (the same pattern `board_item_marker.add_stalled_label()` already
  uses) rather than splitting "compute" from "post" the way
  `write_marker()` does — a rendered-then-posted split would need the
  caller to re-check presence itself, duplicating the idempotency
  pre-check. On success it writes two `$GITHUB_OUTPUT` keys:
  `disposed=true` and `needs-reciprocal-link=true|false` (whether the
  reciprocal cross-link comment on the spec-request is still missing) so
  the workflow step that follows it can gate the second
  `wing-commander-outstanding-task-item` call the same way the existing
  cross-link step is already gated on `steps.<id>.outputs.spec-url != ''`.
  On failure it prints `::error::` and exits 1 (never partial `$GITHUB_OUTPUT`).
- **Its own pre-check (step 1) is widened, not just as the contract states
  it**: the contract's step 1 describes reading only the *originating*
  issue's state/labels, but step 6's idempotency note ("skipped if step 1
  found this comment already present") only makes sense if step 1 also
  reads the **spec-request** issue's comments for the reciprocal-link
  marker. T003 below implements the wider check the contract's step 6
  assumes.
- **Gate packaging**: `board_duplicate_disposition.py` gets its own gate,
  `.github/scripts/verify-board-duplicate-disposition.py`, self-testing the
  module's own idempotency/failure-semantics table (FR-009/FR-010/FR-011) —
  this is a different subject from Gate 93 check 3 (which checks that
  `board-loop.yml`'s three sites *call* the module at all, FR-012), so
  giving it its own gate is not "a second gate over the same subject" the
  way FR-012 forbids; it mirrors this repository's existing one-gate-per-
  `board_*.py` convention (`board_prove.py`→`verify-board-prove.py`,
  `board_readiness.py`→`verify-board-readiness.py`,
  `board_route_backstop.py`→`verify-board-route-backstop.py`,
  `board_triage.py`→`verify-board-triage.py`). Gate 93 check 3 itself is
  extended, per FR-012, to require the module is *called* at each site
  (Phase 5 below) — it does not re-check the module's own internal
  behaviour.
- **Gate numbers**: the highest gate number registered in
  `lint-workflows.yml` as of this writing is 124 (with gaps at 107–113 and
  118 from prior renumbering). This list provisionally claimed Gate 125
  (`verify-board-duplicate-disposition.py`) and Gate 126
  (`verify-board-closed-without-landing.py`); both collided (Gate 125 with
  spec 062's own gate, Gate 126 registered twice for this branch's own two
  scripts) and were renumbered by maintainer review (fold leg-4) to
  **Gate 130** (`verify-board-duplicate-disposition.py`) and **Gate 131**
  (`verify-board-closed-without-landing.py`) — gate numbers collide across
  concurrently open branches routinely, and renumbering is a normal, cheap
  fix-up, never a reason to stall (per the precedent in spec 086's own
  tasks.md "Maintainer Feedback").

---

## Phase 1: Setup

No tasks. This is an existing repository; nothing needs project
initialization before the phases below can start.

---

## Phase 2: Foundational (Blocking Prerequisites)

No tasks. Unlike spec 086's file-wide `.gitignore` prerequisite, nothing
here is shared, blocking infrastructure for *both* US1 and US2: the marker
schema's additive `spec_request` key is only ever written by the module
US1 builds (T003) and is read generically (existing `json.loads` tolerance,
data-model.md) by the eligibility code US2 edits — no shared file needs
touching before either story's own work begins.

---

## Phase 3: User Story 1 - The board counts a routed request once (Priority: P1) 🎯 MVP

**Goal**: Filing a spec-request at any of the three sites (route's spec
verdict, fix's post-push backstop breach, readiness's backstop breach,
including its reuse-an-existing-spec-request path) closes the originating
issue as a duplicate of it (REST `state_reason: duplicate`), with a stated
reason, at the moment the spec-request exists — so exactly one open issue
represents the request afterward.

**Independent Test**: quickstart.md step 1 — route one eligible issue, then
`gh issue view` both the originating issue and the spec-request; the
originating issue is `CLOSED`, carries `disposition:duplicate`, and has a
comment naming the spec-request; the spec-request carries a new checklist
comment linking back. Repeat for the fix and readiness sites.

### Implementation for User Story 1

- [X] T001 [P] [US1] In `.github/scripts/board_item_marker.py`, extend
      `write_marker()` (lines 113–138) to accept an additional optional
      `spec_request=None` parameter; when not `None`, include
      `"spec_request": spec_request` in the JSON payload dict (line
      126–128) alongside the five existing keys, still `sort_keys=True`.
      Existing callers that omit the argument are unaffected (data-model.md
      "Board Item Marker": `spec_request` is additive and only ever
      populated by the disposition write).
- [X] T002 [P] [US1] In
      `.github/actions/wing-commander-board-labels/action.yml`, add a
      fourth `gh label create "disposition:duplicate" ... --force` call
      (after the existing `spec-request` block, ~line 64), following the
      exact shape of the three existing entries: `--color`/`--description`
      of your choosing consistent with the other `disposition:*` labels'
      style in `docs/setup.md`, `status=1` and an `::warning::` on failure,
      participating in the same "all creates always run" `status`
      accumulation the composite's header comment documents. Without this,
      `--add-label disposition:duplicate` 404s on any repo (including this
      one) where the label was never created by hand — this composite is
      the single home for board-loop.yml's own label creation (D1;
      #488/#493's precedent, per the composite's own header).
- [X] T003 [US1] Create `.github/scripts/board_duplicate_disposition.py`
      implementing `dispose_as_duplicate(originating_issue,
      spec_request_issue, spec_request_url, reason) -> bool`
      (contracts/duplicate-disposition.md "Operation shape") plus an
      argparse CLI (`--originating`, `--spec-request-issue`,
      `--spec-request-url`, `--reason`) mirroring `board_item_marker.py`'s
      own CLI conventions:
      1. **Pre-check** (widened per this file's design-decision section
         above): `gh issue view <originating> --json state,labels,comments`
         AND `gh issue view <spec_request_issue> --json comments` (both
         via subprocess, `GH_TOKEN`/`GITHUB_REPOSITORY` from the
         environment, matching `add_stalled_label()`'s own
         `os.environ.get("GITHUB_REPOSITORY")` pattern). Determine: is the
         originating issue already `CLOSED` + `disposition:duplicate`
         labelled + already carrying a reason/marker comment (recognize it
         the same way `board_item_marker.read_marker`'s marker-HTML-comment
         convention lets any reader find the loop's own posts — reuse
         `last_marker_match`/`is_loop_marker_author` via import from
         `board_item_marker`, matching this issue's `step: "duplicate"`);
         and does the spec-request already carry the reciprocal checklist
         comment (match on the `wing-commander-outstanding-task-item`
         composite's own rendered shape, `"- [ ] "` + the reciprocal phrase
         chosen in T005/T006/T007).
      2. **Close** (skip if already closed for any reason, per the edge
         case): `gh api -X PATCH repos/<owner>/<repo>/issues/<originating>
         -f state=closed -f state_reason=duplicate` (research.md D2 — never
         `gh issue close --reason`).
      3. **Label** (idempotent regardless of step 2's outcome): `gh issue
         edit <originating> --add-label disposition:duplicate`.
      4. **Reason + marker comment on the originating issue**, posted only
         if the pre-check found it absent: one `gh issue comment` whose
         body states `reason` and links `spec_request_url`, followed by
         `board_item_marker.write_marker("duplicate", round=0, pr=None,
         branch=None, base_sha=None, spec_request=spec_request_issue)`'s
         rendered text (T001's new parameter) — one comment, not two, per
         the contract's "never a second announcement convention."
      Any `gh` failure at steps 2–4 returns `False` immediately (no partial
      retry inside one call — the next run's own pre-check resumes where
      this one stopped, per the failure-semantics table). On success,
      `main()` writes `disposed=true` and
      `needs-reciprocal-link=<true|false>` (from the pre-check's spec-
      request-comment finding) to `$GITHUB_OUTPUT` and exits 0; on failure
      it prints `::error::` naming which step failed and exits 1 with no
      `$GITHUB_OUTPUT` written.
- [X] T004 [US1] In the `route` job's spec-verdict step (id `spec_request`,
      `.github/workflows/board-loop.yml`), replace lines 1905–1907 (the
      `#604` comment + `python3 .github/scripts/board_item_marker.py --step
      stalled --issue "$ISSUE_NUMBER" --add-label "board:stalled"` call)
      with a call to
      `python3 .github/scripts/board_duplicate_disposition.py --originating
      "$ISSUE_NUMBER" --spec-request-issue <issue number parsed from
      $spec_url> --spec-request-url "$spec_url" --reason "Routed to
      $spec_url"`, capturing its exit code and failing the step on
      non-zero (same `|| { echo "::error::..."; exit 1; }` shape as the
      call it replaces). Line 1908's `gh issue comment` call is now
      redundant with T003's own comment posting and is removed. Leave the
      create (line 1890) and its guard (line 1902) untouched — Gate 93's
      create-guard ordering is unaffected (contracts/duplicate-
      disposition.md "Guard interaction"). Leave the existing cross-link
      step (lines 1914–1922, `"Routed to spec-request"` phrase) unchanged.
      Add a new step immediately after it: `name: "Cross-link the
      originating issue onto the spec-request"`, `if:
      steps.spec_request.outputs.needs-reciprocal-link == 'true'`, `uses:
      ./.wc-pristine-repo/.github/actions/wing-commander-outstanding-task-item`,
      `with: token: ${{ env.WC_BOT_TOKEN }}`, `issue-number: <the
      spec-request's own issue number>`, `phrase: "Filed for the routed
      original"` (research.md D5's suggested phrase — reuse it verbatim so
      T020/T022's doc updates match code), `artifact-url:
      ${{ github.server_url }}/${{ github.repository }}/issues/${{
      needs.select.outputs.issue-number }}`.
- [X] T005 [US1] In the `fix` job's post-push-breach step (id
      `post-push-breach`), replace lines 2464–2469 (the `#530/#604` comment
      + `python3 -I "$RUNNER_TEMP/wc-pristine/scripts/board_item_marker.py"
      --step stalled ...` call + its trailing `gh issue comment`) with a
      call to `python3 -I
      "$RUNNER_TEMP/wc-pristine/scripts/board_duplicate_disposition.py"
      --originating "$ISSUE_NUMBER" --spec-request-issue <parsed from
      $spec_url> --spec-request-url "$spec_url" --reason "Post-push
      backstop breach on $PR_URL (measured=$measured)"` (same
      snapshot-path invocation every other helper-script call in this job
      already uses, Gate 98). Leave the existing cross-link step (lines
      2471–2479) unchanged; add the same new reciprocal-cross-link step
      pattern as T004, gated on `steps.post-push-breach.outputs.needs-
      reciprocal-link == 'true'`, `context: "(post-push backstop breach,
      measured=${{ steps.post-push-breach.outputs.measured }})"`.
- [X] T006 [US1] In the `readiness` job's `report-unmet` step, replace
      lines 3919–3922 (the `#530/#604` comment + `board_item_marker.py
      --step stalled` call) with the same
      `board_duplicate_disposition.py` call as T005 (snapshot path,
      `--reason` text distinguishing the fresh-create vs. `BREACH_RETRY`
      reuse branches the same way `breach_what`/`notice` already do at
      lines 3892–3906) — this one call site covers both the reuse path
      (`existing_spec_url`, line 3898) and the fresh-create path (line
      3911) since both converge into the same `spec_url` variable before
      reaching line 3919. Update line 3923's `body="$(printf '%s on PR
      ...'...)"` construction: the disposition module's own comment (T003)
      now carries the reason+marker, so this step no longer posts its own
      `gh issue comment` for the breach branch (keep the `else` branch at
      lines 3926–3929, the "Not ready" report, untouched — that path never
      files a spec-request and is out of this feature's scope). Leave the
      existing cross-link step (lines 3936–3944) unchanged; add the
      reciprocal-cross-link step gated on
      `steps.report-unmet.outputs.needs-reciprocal-link == 'true'`,
      `context: "(readiness backstop breach, measured=${{
      steps.report-unmet.outputs.measured }})"`.
- [X] T007 [US1] Create
      `.github/scripts/verify-board-duplicate-disposition.py` (Gate 130,
      renumbered from the provisional 125 by fold leg-4): a `--self-test`
      mode exercising
      contracts/duplicate-disposition.md's failure-semantics table as
      checked-in fixtures, each driving `dispose_as_duplicate()` against a
      stubbed `gh` (the same `run=` injection seam
      `add_stalled_label(issue_number, label, run=None)` already
      demonstrates) rather than a real repository:
      1. Already disposed (closed + labelled + both comments present) →
         no-op `True`, zero `gh` calls beyond the pre-check reads.
      2. Close call fails → `False`; a second attempt with the close now
         succeeding resumes from step 2 (FR-010).
      3. Close succeeds, label call fails → `False`; a second attempt
         re-enters at the label step, not a second close attempt.
      4. Close+label succeed, comment call fails → `False`; a second
         attempt posts only the missing comment.
      5. Everything succeeds already, called again → no-op `True`, no
         second comment (FR-009).
      6. Reciprocal-comment-only missing (originating issue fully disposed,
         spec-request never got its reciprocal comment — e.g. a prior run
         crashed between T003's step 4 and the caller's own reciprocal-
         link step) → `needs-reciprocal-link=true` on an otherwise no-op
         `True` return.
      Also assert the plain, no-fixture baseline: a bare `gh` stub that
      succeeds at every call produces `disposed=true`,
      `needs-reciprocal-link=true` end to end.
- [X] T008 [US1] Register Gate 130 in `.github/workflows/lint-workflows.yml`
      as two steps (mirroring Gate 103/104's placement pattern): `name:
      "Gate 130 — dispose_as_duplicate's idempotency and failure semantics
      (FR-009/FR-010/FR-011)"` running
      `python3 .github/scripts/verify-board-duplicate-disposition.py`, and
      a self-test sibling running the same script with `--self-test`, each
      `if: "!cancelled()"`.

**Checkpoint**: quickstart.md step 1's drill passes at all three sites —
one open issue per routed request, each linking to the other.

---

## Phase 4: User Story 2 - The loop's state survives the disposition (Priority: P1)

**Goal**: A disposed issue is never re-selected or treated as in-flight; a
maintainer's stop request on a still-active routed request is still read;
removing `board:stalled` alone never re-admits a disposed issue; reopening
the originating issue re-admits it exactly once, but only once its linked
spec-request has closed; a spec-request that closes without landing leaves
an idempotent notice on both issues naming reopening as the path back.

**Independent Test**: quickstart.md step 2 — on a disposed issue, remove
any label and confirm the next `select` run does not pick it; reopen it
while its spec-request is still open and confirm no second spec-request is
filed and it is not re-admitted; close the spec-request, reopen the
original again, and confirm `select` now admits it exactly once. Separately
(quickstart.md step 3), close a spec-request without a landed final PR and
confirm one idempotent notice appears on each issue.

### Implementation for User Story 2

- [X] T009 [US2] In `.github/scripts/board_eligibility.py`, add
      `"duplicate"` to `TERMINAL_STEPS` (line 81:
      `frozenset({"closed", "stalled", "proven"})` →
      `frozenset({"closed", "stalled", "proven", "duplicate"})`) — defence
      in depth for the window between a reopen and the loop's next run
      (contracts/eligibility-and-readmission-delta.md).
- [X] T010 [US2] In the same file, extend `is_excluded(issue)` (lines
      141–159) to `is_excluded(issue, spec_request_state_by_number=None)`:
      after the existing `state == "CLOSED"` check and the `STALLED_LABEL`
      check, when the *only* remaining exclusion reason found is a label
      `== "disposition:duplicate"` (not just any `DISPOSITION_PREFIX`
      match) AND the issue's `state` is `"OPEN"`, resolve its newest
      loop-authored marker (the caller already has this available the same
      way `in_flight_candidate()` does today — see T011) and, only when
      that marker's `step == "duplicate"` and carries a `spec_request` key,
      look up `spec_request_state_by_number.get(marker["spec_request"])`:
      `"CLOSED"` → return `(False, None)` (re-admitted, FR-006); `"OPEN"`
      or missing/unresolved → still return `(True, "disposition:duplicate")`
      (FR-006's last sentence — a reopen while the spec-request is still
      open must not re-admit). Every other exclusion path (plain closed,
      `board:stalled`, any other `disposition:*` value, `stage:*`/`spec:*`)
      is unaffected (contracts/eligibility-and-readmission-delta.md "Every
      OTHER exclusion reason").
- [X] T011 [US2] Thread the new parameter through the call chain in the
      same file: `in_flight_candidate()` (line 167, its `is_excluded(issue)`
      call at line 200) and `select()`'s fallback scan (line 263, its
      `is_excluded(issue)` call at line 283) both gain a
      `spec_request_state_by_number` parameter passed straight through to
      `is_excluded()`; `main()` (line 300) reads a new
      `spec_request_state_by_number` key from the stdin payload (default
      `{}` if absent, matching the existing tolerant-default style for
      `labeled_events_by_issue`/`comments_by_issue`) and passes it to both
      call sites. Each marker lookup needed by T010 is the same
      `read_marker_with_timestamp(comments_by_issue.get(number) or [],
      bot_login)` call `in_flight_candidate()`/`select()` already make per
      issue — reuse the already-computed marker rather than re-parsing.
- [X] T012 [US2] In `.github/workflows/board-loop.yml`'s `select` job step
      (the one building `board-eligibility-input.json`), after the
      PR-state-by-number resolution block (ends ~line 520) and before the
      final `jq -n` payload assembly (~lines 522–530), add a new block:
      for every issue in `board-open-issues.json` carrying label
      `disposition:duplicate` and OPEN state, read its comments (already
      fetched into `board-comments-by-issue.json` by the loop above) for
      the newest marker with `step == "duplicate"` and a `spec_request`
      field (a small inline `python3 -` block reusing
      `board_eligibility.read_marker_with_timestamp` the same way the
      existing `pr_numbers_to_check` block at lines 459–487 does for
      `FIX_OR_LATER_STEPS`), collect the distinct `spec_request` numbers,
      then for each do `gh issue view <n> --json state --jq .state` (fail
      the step on any error other than 404, same pattern as the PR-state
      lookup's `HTTP 404` tolerance at lines 493–503; on 404 record no
      entry) into `$RUNNER_TEMP/board-spec-request-state-by-number.json`.
      Extend the final `jq -n` call (lines 522–530) with
      `--slurpfile spec_request_states
      "$RUNNER_TEMP/board-spec-request-state-by-number.json"` and add
      `spec_request_state_by_number: $spec_request_states[0]` to the
      constructed object.
- [X] T013 [US2] Add three new `issue.json` + `timeline.json` fixture pairs
      under `.github/scripts/tests/board-eligibility/` (matching the
      existing directory convention) exercising
      contracts/eligibility-and-readmission-delta.md's fixtures 5–7:
      `duplicate-readmitted-spec-closed/` (OPEN, `disposition:duplicate`,
      newest marker `step: "duplicate"` naming a spec-request resolving
      `CLOSED` → admitted), `duplicate-not-readmitted-spec-open/` (same
      shape, spec-request resolving `OPEN` → NOT admitted),
      `duplicate-closed-issue-not-admitted/` (CLOSED issue carrying
      `disposition:duplicate` → NOT admitted via the ordinary first-branch
      exclusion, unaffected by the carve-out). Wire these into
      `verify-board-eligibility.py`'s existing fixture-pair harness the
      same way its current cases are enumerated, passing a
      `spec_request_state_by_number` alongside each new fixture's expected
      live spec-request state.
- [X] T014 [US2] Create `.github/scripts/board_closed_without_landing.py`
      implementing the detection in contracts/closed-without-landing-notice.md
      (research.md D8): given a list of CLOSED, `spec-request`-labelled,
      bot-authored issues and, for each, the `specs/<NNN-slug>/spec-meta.json`
      content whose `issue` field names it (or `None` if no such file
      exists), return the subset "closed without its work landing" — no
      matching `spec-meta.json`, or one whose `stage` never reached the
      finalize stage's terminal completed value (name the exact terminal
      string by reading `.github/scripts/board_item_marker.py`'s sibling
      finalize-stage scripts or `specs/006-finalize-stage/spec-meta.json`
      for the value this repository's own pipeline already writes on
      completion — do not invent a new one). Also implement the idempotent
      dual-notice text (one comment on the originating issue found via that
      spec-request's own `spec_request` marker field, one on the
      spec-request itself), each checked for presence via a recognizable
      HTML-comment marker before posting (mirroring
      `board_item_marker.MARKER_RE`'s own convention, per the contract's
      "Idempotency is checked the same way").
- [X] T015 [US2] In `.github/workflows/board-loop.yml`'s `select` job, add a
      new step immediately after the existing "Detect a merge whose proof
      run never started (FR-010b)" step (ends line 301, before the
      eligibility-input-building step that begins ~line 303), named e.g.
      `"Detect a spec-request that closed without landing (FR-017)"`, `if:
      steps.killswitch.outputs.status != 'paused' && steps.stand-down.outputs.status
      != 'in-flight'` (same guard as its sibling), gathering CLOSED
      `spec-request`-labelled issues authored by `$BOT_LOGIN` (`gh issue
      list --state closed --label spec-request --author "$BOT_LOGIN"`),
      each's linked `specs/<NNN-slug>/spec-meta.json` (checkout of `main`,
      same as every other content read in this job), and invoking
      `board_closed_without_landing.py` to post the notices.
- [X] T016 [US2] Create
      `.github/scripts/verify-board-closed-without-landing.py` (Gate 131,
      renumbered from the provisional 126 by fold leg-4) with a
      `--self-test` covering: (a) a spec-request closed
      with `spec-meta.json` `stage` short of the finalize terminal value →
      both notices posted; (b) the same run repeated → no second notice on
      either issue (idempotency, FR-017); (c) a spec-request with no
      `spec-meta.json` naming it at all → still counted as "closed without
      landing"; (d) a spec-request whose `spec-meta.json` DID reach the
      terminal stage → no notice.
- [X] T017 [US2] Register Gate 131 in `.github/workflows/lint-workflows.yml`
      the same two-step way as T008.

**Checkpoint**: quickstart.md steps 2 and 3 both pass — disposed-issue
state (re-admission, in-flight, stop-request reads) behaves as specified,
and closed-without-landing notices are idempotent on both issues.

---

## Phase 5: User Story 3 - A gate holds every spec-request site to the rule (Priority: P2)

**Goal**: Gate 93 check 3 fails when any spec-request site omits the
disposition call, and fails (not passes vacuously) when it finds zero
spec-request sites at all.

**Independent Test**: quickstart.md step 0 — a fixture workflow with a
spec-request site that never calls `board_duplicate_disposition.py` fails
Gate 93 by name; the real `board-loop.yml` (post-Phase-3) passes; a
zero-site fixture still fails.

### Implementation for User Story 3

- [X] T018 [US3] In
      `.github/scripts/verify-issue-context-single-home.py`'s
      `check_spec_request_bodies()` (lines 1106–1307), add
      `_has_disposition_call(where, lines, create_idx)`
      (contracts/gate-93-check-3-delta.md): for each spec-request create
      site the existing per-site loop already walks, scan the lines after
      `_create_guard_problems()`'s own exit point for a call matching
      `board_duplicate_disposition\.py` (covering both the direct
      `.github/scripts/board_duplicate_disposition.py` form T004 uses and
      the `$RUNNER_TEMP/wc-pristine/scripts/board_duplicate_disposition.py`
      snapshot form T005/T006 use — one regex, two acceptable prefixes). If
      absent, append a problem in the same `f"{where}: ..."` shape every
      other problem in this function already uses. The existing `sites ==
      0` vacuous-pass guard (lines 1302–1306) is unchanged and needs no new
      code (FR-012's third clause is already met).
- [X] T019 [US3] Extend the self-test harness's
      `_site_fixture()`/`_create_guard_cases()` (lines 1346–1475) and
      `_self_test_spec_request_sites()`'s case list (lines 1478–1592) with
      the four fixtures contracts/gate-93-check-3-delta.md names: (1) a
      good site (create → guard → disposition call → cross-link → marker)
      passes; (2) create-guard-only, no disposition call anywhere in the
      step, fails and names the site; (3) a disposition call placed BEFORE
      the create guard's exit point, exercising the existing guard-ordering
      check rather than a new redundant one; (4) confirm the real
      `board-loop.yml` (post-Phase-3/T004–T006) passes with `check_repo()`
      unchanged (no new dispatcher line — `check_spec_request_bodies(BOARD_LOOP)`
      at line 1313 already covers it).

**Checkpoint**: `python3 .github/scripts/verify-issue-context-single-home.py`
and its `--self-test` both pass against the shipped tree; a mutation
matching any of T019's bad fixtures fails by name.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: FR-014's documentation updates (the contract text a gate
reads, per CLAUDE.md, so these remain live and are fixed like code) and the
final integration check.

- [X] T020 [P] In `docs/setup.md`'s label table (~line 172), add a new row
      for `disposition:duplicate` immediately after the existing
      `disposition:false-positive` row, describing it as applied by the
      board loop at spec-request time, re-admitted only by reopening the
      originating issue once its linked spec-request has closed (never by
      label removal alone). Edit the existing `board:stalled` row's clause
      "excludes the issue from selection until a human removes the label,
      the sole condition that re-admits it" to add: "...except a disposed
      (`disposition:duplicate`) issue, which is re-admitted only by a
      maintainer reopening it once its linked spec-request has closed
      (FR-006)." Add a matching `gh label create disposition:duplicate
      ...` line to the quick-script block (~line 199), matching T002's
      chosen color/description.
- [X] T021 [P] In
      `specs/057-autonomous-board-loop/contracts/eligibility-and-selection.md`:
      update the `is_excluded()` code-shape block (lines 15–18) to add the
      `spec_request_state_by_number` parameter and one sentence describing
      the carve-out; update the "Exclusion rule (FR-010)" prose (lines
      41–47) to state that a `disposition:duplicate`-labelled OPEN issue is
      the one exception, re-admitted once its linked spec-request
      resolves closed. This is a live contract (CLAUDE.md:
      `verify-board-eligibility.py` reads the behaviour it describes), so
      this edit is required, not historical-record cleanup.
- [X] T022 [P] In
      `specs/057-autonomous-board-loop/contracts/labels-and-cross-links.md`:
      edit the `board:stalled` row's "Cleared by" column (the "sole
      condition FR-010 reads for re-eligibility" phrase) the same way as
      T020; add a new row to the "New label" table for `disposition:duplicate`
      (applied when: a spec-request is filed for this issue; cleared by:
      never programmatically). Add a new row to the cross-links table:
      `| Reciprocal spec-request link | Filed for the routed original |`
      matching T004's chosen phrase exactly.
- [X] T023 Run `python .github/scripts/run-local-gates.py` (the full
      PR-time gate suite, per CLAUDE.md "Before pushing") and confirm every
      gate — including the newly registered Gate 130/131 (renumbered from
      the provisional 125/126 by fold leg-4) and the extended Gate 93 —
      passes on the shipped tree.

**Not modeled as tasks** — quickstart.md's live drills that need a real
dispatched run against a disposable/test repository (never this one): the
stop-request-mid-flight drill (User Story 2, "Stop request mid-flight"),
the reopen-and-reroute drill (User Story 2, "Reopen"), and the
closed-without-landing drill's own throwaway-repo caveat (quickstart.md
step 3, "never on a real request"). These are manual validation to run
after this feature merges, noted here for the implementer rather than
silently skipped.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup / Foundational**: Empty — Phase 3 can start immediately.
- **User Story 1 (Phase 3)**: No dependency on Phase 4/5. This is the MVP.
- **User Story 2 (Phase 4)**: T009–T013 (eligibility) are independent of
  Phase 3's own edits (different functions in the same file, and a
  different job's step in `board-loop.yml`), but T010's carve-out is only
  ever exercised once T003–T006 actually write the `disposition:duplicate`
  label + `step: "duplicate"` marker it reads — sequenced after Phase 3
  here so the full round-trip (dispose → carve-out reads it) is testable
  end to end without a stubbed marker. T014–T017 (closed-without-landing)
  are independent of T009–T013 (different script, different job step) and
  could run in parallel with them if staffed separately.
- **User Story 3 (Phase 5)**: Depends on Phase 3 (T004–T006 must exist for
  T019's "real board-loop.yml passes" fixture to actually pass).
- **Polish (Phase 6)**: T020–T022 depend on the phrase/label choices made
  in T002/T004 (must match exactly). T023 depends on every prior phase.

### Parallel Opportunities

- T001 (`board_item_marker.py`) and T002 (`wing-commander-board-labels/action.yml`)
  are different files and can run in parallel; T003 depends on T001 (needs
  the extended `write_marker()` signature) but not on T002 (label creation
  is a runtime precondition, not a code dependency of the module itself).
- T014–T017 (closed-without-landing) can run in parallel with T009–T013
  (eligibility carve-out) — different scripts, different workflow step.
- T020, T021, T022 (three different doc/contract files) can run in
  parallel with each other, and with T023 only once T001–T019 are all
  complete (T023 runs the full suite).
- Every other task is a sequential edit to a file (or region of a file)
  an earlier task in its own phase already touched.

---

## Parallel Example: Foundational edits within User Story 1

```bash
# T001 and T002 touch different files and can be done together:
Task: "Extend write_marker() with an optional spec_request parameter"
Task: "Add disposition:duplicate to wing-commander-board-labels/action.yml"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 3 (T001–T008): the primary deliverable — SC-001, SC-002's
   three-site coverage, SC-004's reciprocal link.
2. **STOP and VALIDATE**: quickstart.md step 1 against a disposable/test
   repository if one is available; otherwise confirm via the gate suite
   (T007/T008) plus a read-through of the three edited sites.

### Incremental Delivery

1. User Story 1 (Phase 3) → the board-size defect is fixed at the source.
2. User Story 2 (Phase 4) → the disposed state is provably safe to leave in
   place (re-admission, in-flight exclusion, closed-without-landing notice).
3. User Story 3 (Phase 5) → the rule cannot silently regress at a fourth
   future site.
4. Polish (Phase 6) → documentation matches shipped behaviour, full local
   gate suite green.

---

## Notes

- `[P]` tasks touch different files with no dependency on an incomplete
  task; everything else is a sequential edit to `board-loop.yml`,
  `board_eligibility.py`, or `verify-issue-context-single-home.py` and is
  ordered accordingly.
- `[Story]` labels map every Phase 3/4/5 task to spec.md's User Story 1, 2,
  or 3; Setup, Foundational, and Polish carry no story label.
- Commit after each phase, or more often — `board-loop.yml` is large enough
  that one commit per site's wiring task keeps the diff reviewable.
- Two design gaps found while grounding this list in the contracts (the
  missing `wing-commander-board-labels/action.yml` entry for the new label,
  and step 1's under-specified scope relative to step 6's own idempotency
  note) are resolved here rather than left ambiguous, and are also recorded
  in this run's `wing-commander-findings` block per this stage's own
  instructions, since they are gaps in already-accepted contract text, not
  new scope this list invented.

---

## Phase 7: Convergence

- [X] T024 Update `.github/scripts/board_item_marker.py`'s
      `add_stalled_label()` docstring: it still names route's spec verdict,
      fix's post-push-breach, and readiness's backstop breach among "every
      board-loop.yml stall site" the function is the canonical statement
      for, but T004–T006 removed those three call sites entirely,
      replacing them with `board_duplicate_disposition.py` (they no longer
      apply `board:stalled` or render a `stalled` marker at all). Drop the
      three from the enumeration, per FR-014 (contradicts).

## Maintainer Feedback

- [X] Fix `is_excluded()`'s re-admission carve-out (`.github/scripts/board_eligibility.py:186`) so a re-admitted issue (disposition:duplicate label present, linked spec-request resolved CLOSED) stays re-admitted once a later route/fix/review marker becomes the newest marker, instead of falling back to excluded because the carve-out only fires while the newest marker's step is still `duplicate`. Remove or reset the exclusion basis on re-admission rather than gating solely on the newest marker's step. Add a checked-in fixture: issue re-admitted, then a new triage or fix marker posted, still not excluded (FR-005, FR-006, FR-007, SC-005).
      Fixed by resolving `duplicate_marker` via a new
      `board_item_marker.find_latest_marker_matching()` helper that scans
      every comment for the newest `step=="duplicate"` marker specifically,
      independent of the issue's overall-newest marker; threaded through
      `in_flight_candidate()`/`select()` (board_eligibility.py) and the
      `select` job's own `spec_request_numbers_to_check` resolution
      (board-loop.yml). New fixture:
      `.github/scripts/tests/board-eligibility/in-flight/
      duplicate-readmitted-then-reworked/`.

## Maintainer Feedback

- [X] In `board_duplicate_disposition.py`, read the originating/spec-request issue's comments via REST (`gh api repos/{owner}/{repo}/issues/{n}/comments --paginate`, which nests `user`) instead of `gh issue view --json comments` (GraphQL `author`, no `user.type`), so `is_loop_marker_author()` actually matches the loop's own comments in production instead of never matching and re-posting the reason comment on every call (FR-003, FR-004, FR-009).
- [X] Make the duplicate-comment/reciprocal-link pre-check match on `marker.get("spec_request") == spec_request_issue`, not just `step == "duplicate"`, so a re-route to a new spec-request after re-admission posts its own reason comment and marker naming the new spec-request instead of being treated as already-disposed.
- [X] Update `verify-board-duplicate-disposition.py`'s stubbed `gh` fixtures to return the real REST comment shape (`user.login`/`user.type`) instead of the GraphQL/`author`-shaped stub that currently hides this bug.
      Added `_fetch_comments()` (REST, `gh api .../comments --paginate`)
      alongside the existing `_view_issue()` (`gh issue view --json
      state,labels`, no longer `,comments`); `_has_own_duplicate_comment()`
      now takes `spec_request_issue` and matches on it. New regression
      case 7 (re-route to a new spec-request) and a new self-test baseline
      (`_baseline_idempotent_via_real_fetch()`) exercise the real fetch
      path with REST-shaped stub data, not an injected pre-built dict.

## Maintainer Feedback

- [X] Narrow the closed-without-landing scan (`.github/workflows/board-loop.yml` ~line 316, `board_closed_without_landing.py:39-48`) to only consider spec-requests named by a `step=duplicate` marker (reuse `originating_by_spec_request`) instead of every closed, bot-authored `spec-request` issue — the current scope would post false FR-017 notices on closed spec-requests the loop never filed under this feature's disposition (#768, #605, #577, #574, #502, #487, #549). (FR-016, FR-017)
      Fixed in the `select` job's closed-without-landing step: the loop
      building `spec_requests` now `continue`s when `originating_by_
      spec_request.get(number)` is `None`, so only a spec-request this
      feature's own disposition filed reaches `board_closed_without_
      landing.py`.

## Maintainer Feedback

- [X] Add `continue-on-error: true` to the "Detect a spec-request that closed without landing (FR-017)" step in `.github/workflows/board-loop.yml` (~line 308), or move it to run after `select`, so a lasting comment failure (a locked issue, a 403) doesn't skip `select` on every scheduled run — keep the `::error::` annotations for visibility.
      Added `continue-on-error: true` to the step (its own `::error::`
      annotations are unchanged). Reviewed against the `review-step-gating`
      skill: no step in this job reads `steps.closed-without-landing.*`
      (grep-confirmed), so nothing downstream is stranded by tolerating
      this step's failure; Gate 24 reports no new finding.

## Maintainer Feedback

- [X] Renumber this PR's two gates off the colliding Gate 125/126 (Gate 126 is currently registered twice in `lint-workflows.yml`, once for `verify-board-duplicate-disposition.py` and once for `verify-board-closed-without-landing.py`; Gate 125 collides with spec 062's lifecycle-review-gate gate) to **Gate 130** (`verify-board-duplicate-disposition.py`) and **Gate 131** (`verify-board-closed-without-landing.py`), updating `lint-workflows.yml`'s step names/comments, the gate scripts' own self-identifying text, tasks.md, and any contract/doc referencing the provisional numbers — leaving 126/127 to spec 091, 128 to spec 074, 129 to spec 089, and 132 to spec 109.
      `lint-workflows.yml` renumbered (no self-identifying gate number text
      existed in either `.py` gate script itself, so nothing there needed
      updating); every other Gate 125/126 mention in this file and in
      docs/architecture.md was checked — docs/architecture.md's own
      "Gate 125" (line 733) names spec 062's real, uncollided gate and was
      left untouched.

## Maintainer Feedback

- [X] Reorder `dispose_as_duplicate()` in `board_duplicate_disposition.py:185-204` so the `disposition:duplicate` label and the reason/marker comment are applied *before* the close, not after. Today the order is close, then label, then comment; if the close succeeds and the `gh issue edit --add-label` call fails, the issue ends up CLOSED with no label and no marker. `is_excluded()` returns `"closed"` first (`board_eligibility.py:193`), so no later run ever selects it to retry, the route/fix/readiness `::error::` texts claiming "a later run resumes from its own pre-check" are false for this case, and the FR-017 closed-without-landing scan can't find it either since the label is missing. Left alone, a maintainer reopening the issue routes it again and can file a second spec-request while the first is still open, violating FR-006 and FR-010. Update `contracts/duplicate-disposition.md`'s failure-semantics table to reflect the new step order. (FR-006, FR-010, FR-017)
      Fixed: `dispose_as_duplicate()` now runs label, then comment, then
      close (was close, label, comment); `verify-board-duplicate-
      disposition.py`'s cases 2-4 and `contracts/duplicate-disposition.md`'s
      sequence/failure-semantics table updated to match the new order.

## Maintainer Feedback

- [X] Single-home violation: the select step's inline `python3 - <<PYEOF` block in `board-loop.yml` (~lines 678-712) re-implements `board_eligibility._find_duplicate_marker()` -- the same `disposition:duplicate` label check, the same `find_latest_marker_matching()` call, and the same predicate -- as a second, drifting copy instead of calling the module. **Fix:** add a public helper to `board_eligibility.py` (e.g. one that returns the spec-request numbers to resolve for a given set of open issues/comments) and have the heredoc call it, deleting the inline copy, per CLAUDE.md's "Shared logic has exactly one home" rule.
      Fixed: added `board_eligibility.spec_request_numbers_to_resolve()`,
      reusing `_find_duplicate_marker()`; the heredoc now imports and calls
      it instead of reimplementing the label check/marker scan inline.

## Maintainer Feedback

- [X] Wrap the two unchecked `gh issue list` calls in the "Detect a spec-request that closed without landing" step (`board-loop.yml:325`, `:354`) in `if ! ...; then echo "::error::..."; exit 1; fi`, matching the per-issue comment fetches directly below them. The step runs under `set -uo pipefail` (no `-e`): if the call at `:354` fails, the scan finishes "successfully" having posted nothing for that run; if the call at `:325` fails, it crashes with an unhandled traceback instead of a clean `::error::`. (FR-017)
      Fixed: both `gh issue list` calls are now wrapped in `if ! ...; then
      echo "::error::..."; exit 1; fi`.


## Maintainer Feedback

- [X] Make the per-issue comment fetch loops in the closed-without-landing step (`board-loop.yml` ~lines 341, 361) `continue` past a single failed fetch (tracking an error count) instead of exiting the whole step on the first failure, so one bad fetch doesn't skip every other spec-request or disposed issue in that run. Fail the step at the end if any errors were recorded, so the failure is still visible. (FR-017)
      Fixed: both loops now `continue` past a failed fetch, incrementing a
      `fetch_errors` counter; the step exits 1 after posting notices for
      everything that did resolve, only if `fetch_errors` is nonzero.
