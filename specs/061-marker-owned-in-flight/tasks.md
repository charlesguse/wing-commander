---

description: "Task list template for feature implementation"
---

# Tasks: The Loop Recognizes Its Own Work — In-Flight Detection Reads the Board Item Marker

**Input**: Design documents from `/specs/061-marker-owned-in-flight/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/,
quickstart.md (all present)

**Tests**: FR-012 makes the ten checked-in fixtures a hard functional
requirement of this feature (they are User Story 3's own deliverable, not
optional test coverage) — they are scheduled as that story's phase below.

**Organization**: Tasks are grouped by user story to enable independent
implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Single repository, `.github/`-only tooling change (plan.md "Project
Structure" / "Structure Decision") — no `src/`/`tests/` application tree.
All paths below are repository-root-relative.

---

## Phase 1: Setup

**Purpose**: The one prerequisite this feature needs that has no code
dependency and must exist before the fix step's first post-feature run
(spec Assumptions: "The ownership label exists in the repository... before
first use").

- [X] T001 [P] Add `board:owned` to `docs/setup.md`'s label table (alongside
  `board:stalled`, ~line 155) — "Applied by the board loop (`board-loop.yml`)
  to every pull request it opens, at creation time, marking it as the
  loop's own (FR-013) — read only by resume's ownership-label fallback
  (FR-007), never an eligibility input" — and add `gh label create
  board:owned --color 0E8A16 --description "Board loop: this PR was
  opened by board-loop.yml"` to the label-creation quick script (~line 183),
  per contracts/ownership-label.md "Prerequisites" and research.md D6.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The one piece of shared machinery both User Story 1 (the
in-flight decision) and User Story 3 (that decision's fixtures) depend on.
User Story 2 (resume) does not use it — contracts/resume-recovery.md's PR
recovery and step resolution keep using plain `read_marker()`.

**⚠️ CRITICAL**: T003 (User Story 1) cannot start until this phase is done.

- [X] T002 Add `read_marker_with_timestamp(issue_comments)` to
  `.github/scripts/board_item_marker.py`, returning `(created_at, marker)`
  for the newest well-formed marker found by the same scan `read_marker()`
  already performs, or `None` when none is found (data-model.md
  "`board_item_marker.py` addition", contracts/in-flight-detection.md).
  Refactor `read_marker()` into a thin wrapper over it
  (`pair = read_marker_with_timestamp(c); return pair[1] if pair else None`)
  so every existing call site's return shape (a marker dict or `None`) is
  unchanged (D7). Do not change `write_marker()` or the marker's JSON shape
  (Out of Scope).

**Checkpoint**: Foundation ready — User Story 1 can now be implemented.

---

## Phase 3: User Story 1 - An unrelated open fix PR no longer hijacks the loop (Priority: P1) 🎯 MVP

**Goal**: `select()` consults a new `in_flight_candidate()` — reading only
the board item marker, never pull request bodies — before falling through
to the existing oldest-first eligibility scan. The old repository-wide
`gh pr list ... capture("Fixes #...")` shortcut is deleted outright.

**Independent Test**: With an open pull request whose body cites an
eligible issue, and no board item marker anywhere on the board, run the
loop and confirm the selected issue is the one the oldest-first
eligibility scan returns, not the one the pull request cites (spec.md US1
Acceptance Scenario 1; full live replay is quickstart.md §3, SC-001/SC-003).

### Implementation for User Story 1

- [X] T003 [US1] Add `PRE_FIX_STEPS = frozenset({"triage", "route"})`,
  `FIX_OR_LATER_STEPS = frozenset({"fix", "review", "readiness", "prove"})`,
  `TERMINAL_STEPS = frozenset({"closed", "stalled", "proven"})`, and
  `in_flight_candidate(open_issues, comments_by_issue, pr_state_by_number)
  -> tuple[int | None, bool]` to `.github/scripts/board_eligibility.py`,
  exactly per contracts/in-flight-detection.md and data-model.md "In-Flight
  Candidate": for each open issue, skip if `is_excluded()` is `(True, _)`
  (FR-003/D8, the same single exclusion function `select()`'s existing scan
  uses — never a second, parallel exclusion rule); read the newest marker
  via `read_marker_with_timestamp()` (T002), skip if none or unparsable;
  skip if the marker's `step` is in `TERMINAL_STEPS`; if `step` is in
  `PRE_FIX_STEPS`, it is a candidate on the step alone (FR-002 bullet 1); if
  `step` is in `FIX_OR_LATER_STEPS`, it is a candidate only when
  `marker["pr"]` is a key of `pr_state_by_number` with value `"OPEN"`
  (FR-002 bullet 2), otherwise skipped (the stale-marker disqualification).
  Among all candidates found, return the one with the lexicographically
  greatest marker `created_at` (ISO-8601 sorts lexicographically) as
  `issue_number`; `multiple_found` is `True` when more than one issue
  qualified (FR-005), regardless of which one issue `issue_number` names.
  Never raise on missing/malformed input (issue with no comments, marker
  missing a field, non-integer `pr`) — degrade to "not a candidate" per
  `read_marker()`'s own existing contract.

- [X] T004 [US1] Extend `select()` in `.github/scripts/board_eligibility.py`
  to the signature `select(open_issues, labeled_events_by_issue,
  comments_by_issue, pr_state_by_number)`: call `in_flight_candidate()`
  (T003) first; when it returns an `issue_number` (not `None`), return it
  immediately; otherwise fall through to the existing oldest-first /
  `classify_issue()` / `is_excluded()` scan, byte-for-byte unchanged
  (FR-004, contracts/in-flight-detection.md, data-model.md "Extended
  `select()` signature").

- [X] T005 [US1] Update `main()` in `.github/scripts/board_eligibility.py`
  to also read `comments_by_issue` and `pr_state_by_number` from the stdin
  JSON payload (keyed the same way `labeled_events_by_issue` already is —
  issue numbers as string keys, coerced to `int`) and pass them through to
  `select()` (T004).

- [X] T006 [US1] In `board-loop.yml`'s "Fetch open issues and select the
  next board item" step (~line 154), extend the per-issue `gh api
  .../issues/$number/comments` call's `--jq` projection (~line 204) to also
  extract `body`, alongside the `login`/`association`/`created_at` it
  already keeps, and accumulate the result per issue into a
  `board-comments-by-issue.json` map the same way `board-labeled-events.json`
  is already accumulated (~lines 224-233) — one API round-trip continues to
  serve both purposes (research.md D3).

- [X] T007 [US1] [P] In the same step, after `board-comments-by-issue.json`
  is assembled (T006), add a narrow second pass: scan it in Python for
  markers naming a step in `FIX_OR_LATER_STEPS` and a `pr` number (reusing
  `board_item_marker.read_marker_with_timestamp()` and
  `board_eligibility.FIX_OR_LATER_STEPS`), then resolve exactly those PR
  numbers' state via `gh api repos/$GITHUB_REPOSITORY/pulls/<n> --jq
  .state` into a `pr_state_by_number` map — never a `gh pr list` call, never
  a body or text search (FR-001, research.md D3).

- [X] T008 [US1] Delete the unrestricted in-flight shortcut block in
  `board-loop.yml` (~lines 240-263: the `in_flight_issue="$(gh pr list
  --repo ... capture("Fixes #...")` call and its inline `is_excluded`
  Python subprocess) outright. Add `comments_by_issue` and
  `pr_state_by_number` (T006/T007) to the JSON payload built for
  `board_eligibility.py`'s stdin (~lines 235-238) and remove the
  now-redundant `issue_number="$in_flight_issue"` branch so
  `python3 .github/scripts/board_eligibility.py` (T005) is the run's only
  source of the selected issue number (FR-001/FR-004).

- [X] T009 [US1] Add one canonical comment directly above
  `in_flight_candidate()`/`select()` in `.github/scripts/board_eligibility.py`
  stating that the in-flight decision lives here and only here (FR-011,
  CLAUDE.md's single-home rule), for any future call site to point back at
  rather than re-deriving the rule inline.

**Checkpoint**: User Story 1 is independently functional — `select()` no
longer reads any pull request body, and the old shortcut is gone.

---

## Phase 4: User Story 2 - Resume recovers the loop's own item, or declares it fresh (Priority: P1)

**Goal**: Resume recovers branch/PR from the marker, re-validated live;
falls back to a `board:owned`-labeled, issue-citing PR only when no usable
marker exists; and always resolves `step` to one of the loop's named
steps — never empty.

**Independent Test**: Run the loop against an issue with no marker and a
repository containing an unrelated open pull request that cites it;
confirm the run proceeds through triage rather than reporting every job
`skipped` (spec.md US2 Independent Test; SC-002).

### Implementation for User Story 2

- [X] T010 [US2] In `board-loop.yml`'s "Push and open the PR" step (~line
  1299), add `--label board:owned` to the existing `gh pr create` call
  (contracts/ownership-label.md "Write") — one call, one API round-trip, so
  no window exists between "PR exists" and "PR is labeled" for a run to die
  inside (FR-013).

- [X] T011 [US2] Replace `board-loop.yml`'s "Resume" step's PR recovery
  (~line 320, the `gh pr list --repo "$GITHUB_REPOSITORY" --search
  "$ISSUE_NUMBER in:body" --state all` call) with, per
  contracts/resume-recovery.md "PR recovery": (1) when the marker names a
  `pr` number, resolve it directly via `gh api
  repos/$GITHUB_REPOSITORY/pulls/<n> --jq '{number, state}'` — treat a 404
  as "not found" and continue to (2); (2) otherwise, the FR-007 fallback:
  `gh api repos/$GITHUB_REPOSITORY/issues -X GET --paginate -f state=open
  -f labels=board:owned --jq '{number, body}'`, filtered in code to bodies
  matching `(?:Fixes|fixes) #$ISSUE_NUMBER\b`; (3) otherwise, no PR is
  adopted and `pr`/`pr-state` stay empty. Never widen either lookup by PR
  title, author, or head-branch naming convention (FR-007).

- [X] T012 [US2] Rewrite the "Resume" step's `step` derivation (replacing
  the `step="$marker_step"; if [ -z "$branch" ] && [ -z "$pr_number" ];
  then step="triage"; fi` rule at ~lines 326-329) with the four-clause
  priority order from contracts/resume-recovery.md "Step resolution": (1)
  the marker names a `pr` that resolves (pre-fix: no `pr` required;
  fix-or-later: resolved state `== OPEN`) → `step` = the marker's own step;
  (2) no marker-named `pr` resolved, but the FR-007 fallback (T011) recovers
  an open `board:owned` PR citing this issue → `step` = `"review"`; (3) no
  `pr` resolved by (1) or (2), but `branch` is re-derived (the existing
  `git ls-remote` check) → `step` = `"fix"`; (4) neither a `pr` nor a
  `branch` resolved → `step` = `"triage"` (FR-008). `step` must never be
  empty in any branch.

- [X] T013 [US2] In the same step, record in `$GITHUB_STEP_SUMMARY` (matching
  this job's existing `echo "board-loop: ..." >> "$GITHUB_STEP_SUMMARY"`
  idiom): when clause 2 of T012 fires, that the PR was recovered via the
  `board:owned` label fallback rather than a marker (FR-014); and when
  clause 4 fires because a marker was present but disqualified (a
  fix-or-later marker whose `pr` state was not `OPEN`, or a marker whose
  branch and PR are both gone) rather than simply absent, that this
  happened and why (FR-009).

**Checkpoint**: User Stories 1 AND 2 both work independently — no run can
select an issue and leave `step` empty.

---

## Phase 5: User Story 3 - The rule has a home and a gate that can fail it (Priority: P2)

**Goal**: `in_flight_candidate()` is covered by ten checked-in fixtures
under Gate 81 (`verify-board-eligibility.py`), so a future change to the
rule fails a gate rather than a scheduled run three weeks later.

**Independent Test**: Run the repository's PR-time gate suite against a
deliberately broken in-flight rule and confirm a gate fails (spec.md US3
Independent Test; SC-004).

### Fixtures for User Story 3 (FR-012)

Each case is a directory under
`.github/scripts/tests/board-eligibility/in-flight/<case>/` containing
`open_issues.json`, `comments_by_issue.json`, `pr_state_by_number.json`,
and `expected.json` (`{"issue_number": <int|null>, "multiple_found":
<bool>}`), per contracts/in-flight-detection.md's fixture list:

- [X] T014 [P] [US3] Create fixture case `no-marker` — no issue anywhere
  carries a marker → `{"issue_number": null, "multiple_found": false}`.
- [X] T015 [P] [US3] Create fixture case `pre-fix-no-pr` — marker at
  `route`, no `pr` recorded → that issue, `multiple_found: false`.
- [X] T016 [P] [US3] Create fixture case `fix-or-later-pr-open` — marker at
  `review`, recorded PR state `OPEN` → that issue, `false`.
- [X] T017 [P] [US3] Create fixture case `fix-or-later-pr-closed` — marker
  at `review`, recorded PR state `CLOSED` (not merged) →
  `{"issue_number": null, "multiple_found": false}`.
- [X] T018 [P] [US3] Create fixture case `fix-or-later-pr-merged` — marker
  at `readiness`, recorded PR state `MERGED` → `(null, false)`.
- [X] T019 [P] [US3] Create fixture case `terminal-step` — marker at
  `proven` → `(null, false)`.
- [X] T020 [P] [US3] Create fixture case `excluded-issue` — marker at
  `route` on an issue that also carries the `board:stalled` label →
  `(null, false)` (proves FR-003's shared exclusion path).
- [X] T021 [P] [US3] Create fixture case `unparsable-marker` — a comment
  containing a marker-shaped HTML comment whose JSON body does not parse →
  `(null, false)`.
- [X] T022 [P] [US3] Create fixture case `two-non-terminal` — two open,
  non-excluded issues, each carrying a non-terminal, qualifying marker with
  different `created_at` timestamps → the newer marker's issue, `true`.
- [X] T023 [P] [US3] Create fixture case `unrelated-pr-no-marker` — an
  eligible issue with no marker, plus `pr_state_by_number` populated for an
  unrelated open PR whose body cites that issue → `(null, false)` — proves
  the decision never reads PR body text (FR-001).

### Gate wiring for User Story 3

- [X] T024 [US3] Extend `.github/scripts/verify-board-eligibility.py` with a
  second fixture loop (mirroring its existing `classify_issue` loop's
  "fail loudly, non-zero exit, `::error::` annotation if any of the four
  files is missing" pattern, not a new mechanism) that, for each of the ten
  `in-flight/<case>/` directories (T014-T023), loads all four files, calls
  `in_flight_candidate()` (T003) with them, and asserts the result equals
  `expected.json`'s `{"issue_number", "multiple_found"}` (depends on T003,
  T014-T023).

- [X] T025 [US3] Run `python3 .github/scripts/run-local-gates.py` and
  confirm Gate 81 passes all ten new cases plus the four existing
  `classify_issue` cases. Then, per quickstart.md §1, temporarily edit
  `in_flight_candidate()` to admit an issue with no marker (e.g. `return
  open_issues[0]["number"], False` unconditionally), re-run the same
  command, confirm Gate 81 fails naming the `no-marker` case, and revert
  the edit (SC-004; depends on T024).

**Checkpoint**: All user stories are independently functional and the
in-flight decision is gate-covered.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Whole-suite verification and this repository's own
before-pushing requirements (CLAUDE.md).

- [X] T026 [P] Run `python3 .github/scripts/run-local-gates.py` (the full
  PR-time gate suite, per CLAUDE.md "Before pushing") across every touched
  file (`board_eligibility.py`, `board_item_marker.py`, `board-loop.yml`,
  `verify-board-eligibility.py`, `docs/setup.md`) and fix any fallout.

- [X] T027 Statically verify, against contracts/resume-recovery.md's
  decision table, that every branch of T012's rewritten step-resolution
  logic in `board-loop.yml` assigns one of `triage`/`fix`/`review`/the
  marker's own step and none leaves `step` unset (quickstart.md §2,
  SC-002) — the live end-to-end replays in quickstart.md §3-§5 need a
  disposable repository and a real dispatched run, so they are out of
  scope for this local verification and are proven post-merge per
  CLAUDE.md's "re-drive one run" rule.

- [X] T028 Since this change touches `if:` conditions and a `run:` step in
  `board-loop.yml` (T006-T013), give it a pass from the
  `review-step-gating` skill per CLAUDE.md, before this feature's
  implementation is proposed for review.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: No dependencies on Setup; BLOCKS User Story 1
  (T003 needs `read_marker_with_timestamp()`).
- **User Story 1 (Phase 3)**: Depends on Foundational (T002). Independent
  of User Story 2.
- **User Story 2 (Phase 4)**: Depends on Setup (T001, for the label to
  exist) for a fully working runtime path, but its code changes (T010-T013)
  have no code dependency on User Story 1's files — the two stories touch
  disjoint parts of `board-loop.yml` (the `select` job's data-gathering
  step vs. the `resume` step and the `fix` job's PR-create step) and can be
  implemented in either order or in parallel.
- **User Story 3 (Phase 5)**: Depends on User Story 1 (T003's
  `in_flight_candidate()` must exist before it can be fixture-tested) —
  not independent of US1 the way US2 is, per FR-011/FR-012's design.
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### Within Each User Story

- US1: T003 → T004 → T005; T006 → T007 → T008 (T008 also needs T005); T009
  can run any time after T003.
- US2: T010 is independent; T011 → T012 → T013.
- US3: T014-T023 (fixture data) are independent of each other and of T003
  itself (plain JSON files); T024 needs T003 and all of T014-T023; T025
  needs T024.

### Parallel Opportunities

- T001 (Setup) and T002 (Foundational) can run in parallel — different
  files.
- Within US1: T006 and T007-in-isolation cannot run in parallel with each
  other (same step, sequential edits), but T003 (Python) and T006 (YAML)
  touch different files and can proceed in parallel before T008 unifies
  them.
- Within US2: T010 can run in parallel with all of US1 and with T011-T012
  (different steps in the same file — apply with care if the same agent
  edits `board-loop.yml` serially).
- All ten of US3's fixture tasks (T014-T023) are mutually [P] — different
  directories, no shared file.

---

## Parallel Example: User Story 3

```bash
# Launch all ten fixture-case tasks together (different directories):
Task: "Create fixture case no-marker under .github/scripts/tests/board-eligibility/in-flight/no-marker/"
Task: "Create fixture case pre-fix-no-pr under .../in-flight/pre-fix-no-pr/"
Task: "Create fixture case fix-or-later-pr-open under .../in-flight/fix-or-later-pr-open/"
# ... (T017-T023 similarly)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) + Phase 2 (Foundational).
2. Complete Phase 3 (User Story 1) — this alone fixes the reported defect's
   mis-selection half (SC-001/SC-003).
3. **STOP and VALIDATE**: confirm `select()` never touches a PR body
   (T003-T009), independent of whether resume or the fixtures exist yet.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. Add User Story 1 → the mis-selection half of the reported defect is
   fixed.
3. Add User Story 2 → the empty-step/silent-skip half is fixed; both halves
   of the live failure (run 35839986595) are now addressed.
4. Add User Story 3 → the fix is gate-covered so it cannot silently regress
   (Constitution VIII).
5. Polish → whole-suite verification and this repository's own
   before-pushing gate.

## Notes

- `[P]` tasks touch different files (or, for the fixture cases, different
  directories) with no dependency between them.
- Every task above names its exact file path(s) per this repository's
  existing `board_eligibility.py`/`board-loop.yml`/`verify-board-eligibility.py`
  structure — no new module, gate number, or directory beyond the
  `in-flight/` fixture subdirectory FR-012 asks for.
- Commit after each task or logical group of tasks, consistent with this
  repository's small-PR, gate-verified workflow.

## Phase 7: Convergence

- [X] T029 Record in the select job's `$GITHUB_STEP_SUMMARY` whether an
  in-flight board item marker (rather than the oldest-first fallback)
  decided the selected issue, and whether more than one issue qualified as
  in-flight, per FR-005 and spec.md US1 AS1/AS3 ("the right answer for the
  right reason, and the run's record says the marker is why"). The
  underlying decision (`in_flight_candidate()`) already returns
  `multiple_found` and is fixture-verified; the gap is that nothing between
  it and `$GITHUB_STEP_SUMMARY` surfaces that value or the marker-vs-fallback
  provenance — `board_eligibility.py`'s `main()` prints only the selected
  issue number, and `board-loop.yml`'s select step only echoes
  `board-loop: selected issue #$issue_number.` (missing)
