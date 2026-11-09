---

description: "Task list for Board Loop Works Maintenance Backlog Lines"
---

# Tasks: Board Loop Works Maintenance Backlog Lines

**Input**: Design documents from `specs/121-board-backlog-line-items/` (plan.md, spec.md, research.md, data-model.md, contracts/backlog-lines.md, quickstart.md)

**Prerequisites**: plan.md, spec.md

**Tests**: The spec (FR-019) requires a checked-in fixture a gate exercises for every new branch, so fixture and gate tasks are included. Write the fixtures first and watch them fail.

**Organization**: Grouped by user story. Run `python .github/scripts/run-local-gates.py` after each phase; keep the gates green throughout (guidance, not a task). Workflow comments are load-bearing (gates byte-compare them), so treat comment edits as code edits. A change touching an `if:`, `continue-on-error:` or failing step in `board-loop.yml` also gets a pass from the `review-step-gating` skill; a `run:` step inside a `container:` job gets `container-shell-safety`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallel (different files, no dependencies)
- **[Story]**: user story (US1..US4)

## Path Conventions

Scripts in `.github/scripts/`, fixtures in `.github/scripts/tests/board-backlog-lines/` and `.github/scripts/tests/board-backlog-edit/`, workflows in `.github/workflows/`.

---

## Phase 1: Setup

- [x] T001 Read `.github/scripts/board_item_marker.py`, `board_eligibility.py`, `board_merge.py` (`FIX_BRANCH_RE`), `board_triage.py`, `board_duplicate_disposition.py` and the hold/route/close/prove sites in `.github/workflows/board-loop.yml`; list each site in a scratch note inside the PR description (no file written) so later tasks cite them.
- [x] T002 [P] Create empty fixture directories with a `README.md` each: `.github/scripts/tests/board-backlog-lines/README.md` and `.github/scripts/tests/board-backlog-edit/README.md`.
- [x] T003 Find how existing `verify-*.py` gates are registered (gate registry used by `.github/scripts/run-local-gates.py` and `.github/workflows/lint-workflows.yml`) and note the registration pattern to follow in T006 and T011.

---

## Phase 2: Foundational (blocks all stories)

**Purpose**: the pure line module, the single-home edit helper, and the marker `line` key.

- [x] T004 Create `.github/scripts/board_backlog_lines.py` with `parse_lines(body)` per data-model.md: only column-0 `- [ ] `/`- [x] ` lines outside fenced blocks, blockquotes and nested/indented checkboxes; annotation grammar `[wc:<id> <state>( <detail>)?]` parsed into `id`, `state`, `text` (text excludes the token). Stdlib only; CLI reads JSON on stdin and prints JSON (exit 0 on a decision, 2 on malformed input).
- [x] T005 [P] Add fixtures under `.github/scripts/tests/board-backlog-lines/` for parsing: fenced block, blockquote, nested checkbox, indented checkbox, ticked line, annotated line, empty body, comment-looking text.
- [x] T006 Create `.github/scripts/verify-board-backlog-lines.py` that loads every fixture in `.github/scripts/tests/board-backlog-lines/` and asserts expected output; register it in the gate registry per T003 and in its trigger paths.
- [x] T007 Create `.github/scripts/board_backlog_edit.py` with `edit(issue, apply_fn, verify_fn, *, fetch, write, max_attempts=5) -> Result` per contracts/backlog-lines.md: fetch, apply (`None` → `stand_down`), write, re-fetch and `verify_fn`; loop on a dropped change; on exhaustion leave the body as last fetched and return `failed` (never a forced write). Add the CLI `--issue N --op <name> --line-id ID [--detail TEXT]` using `gh`.
- [x] T008 [P] Add fixtures under `.github/scripts/tests/board-backlog-edit/` with injected `fetch`/`write` scenarios: concurrent append plus unrelated tick between read and re-read (both survive, SC-003), later writer drops the change (read-back re-applies), line ticked/deleted (stand down, no write), retries exhausted (body unchanged, `failed`).
- [x] T009 Create `.github/scripts/verify-board-backlog-edit.py` running the T008 fixtures, plus a single-home scan failing if any other script or workflow under `.github/` runs `gh issue edit` with a body for the backlog issue (FR-024); register it per T003.
- [x] T010 Edit `.github/scripts/board_item_marker.py` to read and write an optional `line` key; edit `.github/scripts/board_eligibility.py` so issue-path readers ignore markers carrying `line`, and only App-authored markers are read. Add fixtures to `.github/scripts/tests/board-backlog-lines/` for a line-keyed marker round trip and the issue-path ignoring it.
- [x] T011 Run `python .github/scripts/run-local-gates.py` and fix failures in the above.

**Checkpoint**: parse, edit helper and marker key exist and are gated.

---

## Phase 3: User Story 4 - Concurrent writers never lose edits (Priority: P1)

**Goal**: every backlog edit by the loop or a session goes through the one helper, with retries and read-back.

**Independent Test**: the T008 fixtures plus a CLI run of `board_backlog_edit.py` against stubbed fetch/write shows the other writer's changes survive.

- [x] T012 [US4] Implement in `.github/scripts/board_backlog_lines.py` the annotation functions `annotate(body, line_id, state, detail)`, `tick(body, line_id, annotation)`, `clear_note(...)` returning `None` for a missing, duplicated or already-ticked id (FR-016, duplicate-id edge case); detail sanitised to one line.
- [x] T013 [P] [US4] Add fixtures for each annotation state (`in-progress`, `in-progress PR #N`, `held`, `proposal`, `fixed`, `evidence`, `fixed` with `not-proven: <reason> [run](url)` and its later replacement), duplicate id, missing id, already ticked.
- [x] T014 [US4] Wire the CLI edit subcommands `claim`, `progress`, `hold`, `route-proposal`, `tick-evidence`, `tick-fixed`, `note-proof` in `board_backlog_lines.py` so each goes through `board_backlog_edit.edit()`; report a stand-down or failure as a comment on the backlog issue (FR-016, FR-015).
- [x] T015 [US4] Edit `CLAUDE.md` section "Working the issue board": add the rule that sessions edit the Maintenance backlog body only through `python .github/scripts/board_backlog_edit.py`, never a blind whole-body write.

**Checkpoint**: US4 independently verifiable by the gates.

---

## Phase 4: User Story 1 - Idle loop fixes one backlog line (Priority: P1) 🎯 MVP

**Goal**: with no eligible issue and the switch on, the loop claims a line, works it through the existing pipeline, and ticks it when its PR merges.

**Independent Test**: fixtures for selection, ids, branch/title, keyword checks, then the quickstart.md walkthrough.

- [x] T016 [US1] In `board_backlog_lines.py` add `resolve_backlog(open_issues, bot_login)` (FR-002: exactly one open `disposition:tracking` issue titled "Maintenance backlog…", maintainer or App author; ambiguity returns `(None, reason)`) and `select_line(body, *, claimed_ids)` (topmost unchecked, un-annotated).
- [x] T017 [P] [US1] Add fixtures: two backlog candidates (ambiguous), none, closed, renamed, wrong author, empty body, no unchecked lines, topmost chosen, identical-text lines, annotated lines skipped.
- [x] T018 [US1] In `board_backlog_lines.py` add `selection_gate(env)` (FR-023/FR-025): refuses unless `backlog_lines_switch` is exactly `true`, refuses when `loop_paused`, refuses when the `### X.` section of `constitution_text` lacks `Maintenance backlog line`, and refuses when `constitution_text` is `None`. Add fixtures: amended text, unamended text, unreadable file, switch off/`True`/empty, paused.
- [x] T019 [US1] Add `mint_id(body)` (`bl-` + 8 hex, never present in body, matches `[a-z0-9-]{1,40}`), `branch_for(issue, line_id)` (asserts full `FIX_BRANCH_RE` match imported from `board_merge.py`) and `title_for(text, prefix="Fix: ")` (strip annotation, collapse whitespace, truncate with `…` so `len(prefix + text) <= 200`). Fixtures: distinct ids give distinct branches, 300-character line text, text containing a closing keyword.
- [x] T020 [US1] Add `closing_keyword_hits(title, body, commit_messages)` (case-insensitive `close[sd]?|fix(e[sd])?|resolve[sd]?` followed by `#N`, `owner/repo#N` or a full issue URL) and `render_line_text_for_body(text)` (code span with `#` references defanged); CLI `check-closing-keywords`. Fixtures: each keyword form in title, body and a commit message; a clean set; line text "Fix #747's …" rendered carrying no keyword.
- [x] T021 [US1] Edit `.github/workflows/board-loop.yml` select job: when no eligible issue is waiting, call `board_backlog_lines.py select` (with the variable `WING_COMMANDER_BOARD_BACKLOG_LINES`, the pause flag and the default-branch `constitution.md` read fresh), claim via `claim`, and emit the item descriptor outputs (`item_kind`, `item_number`, `line_id`, `line_text`, `branch`, `pr_title`) per data-model.md; with the switch off and nothing claimed behaviour stays identical (FR-020). A claimed line counts as the current item (FR-006). One-line refusal reason goes to the run summary.
- [x] T022 [US1] Edit `board-loop.yml` jobs downstream of select to carry `item_kind`/`line_id`: use `branch` and `pr_title` from the descriptor instead of `fix/<issue>-<slug>` and the issue title; pass only the line text, framed as untrusted defect-description data, into each agent prompt (FR-007, FR-008); the resume step checks the marker's branch against the line-derived branch.
- [x] T023 [US1] Edit `board-loop.yml` fix and review-fixup push steps and the PR-open step: run `check-closing-keywords` on the title and branch commit messages before every push and on title and body at PR creation, and on all three before merge; on a hit, hold the line with a closing-keyword reason (FR-017). The PR body carries `Backlog line: #<backlog-issue> <line-id>` and the rendered line text, never `Fixes #N`. Update the progress annotation to `in-progress PR #N` once a PR exists (FR-010).
- [x] T024 [US1] Edit `board-loop.yml` prove and merge paths (FR-011, FR-021): find a line-born PR's item from the `Backlog line:` reference plus the line-keyed marker (the `pull_request: closed` prove entry, the missed-proof detection, resume recovery of an open `board:owned` PR); on merge call `tick-fixed`; the prove arms that close the item issue must not close the backlog issue and instead record the outcome with `note-proof` ("not proven: <reason>" plus run link when the prove job has one). This handling is not gated by the switch or claim state (FR-020, FR-023).
- [x] T025 [P] [US1] Add fixtures for the PR-body reference matching (line-born PR found; issue-born PR unaffected; reference present but no marker) and for the switch-off path (no new claim, claimed line still worked, merge still ticked); extend `verify-board-backlog-lines.py` to run them.
- [x] T026 [P] [US1] Edit `.github/workflows/board-status.yml` to show `WING_COMMANDER_BOARD_BACKLOG_LINES` beside the other board switches and to name the current line (backlog issue plus line id) when a line is the work item (FR-018, FR-023); update any run-summary text in `board-loop.yml` that names the current issue.
- [x] T027 [US1] Run `python .github/scripts/run-local-gates.py`; perform a `review-step-gating` pass over the `board-loop.yml` changes.

**Checkpoint**: MVP — a fix-shaped line goes claim → PR → tick.

---

## Phase 5: User Story 2 - Close or route a line without a fix PR (Priority: P2)

**Goal**: triage close grounds tick the line with evidence; an already-fixed proposal is held; spec-shaped lines become a `spec-proposal` pointer.

**Independent Test**: the three-line scenario in spec.md US2.

- [x] T028 [US2] Edit `board-loop.yml` triage handling so that for a line the deterministic close grounds (API 429, upstream action bump from `board_triage.py`) call `tick-evidence` with the evidence quoted and open no PR; an agent-proposed "already fixed on main" records the proposal and commit and calls `hold` with the triage-handover reason (never a tick) (FR-012, FR-014).
- [x] T029 [US2] Edit `board-loop.yml` route, fix post-push backstop breach and readiness forced-breach retry sites: for a line, file a `spec-proposal` (never `spec-request`) with a title from `title_for` (FR-007), call `route-proposal` to annotate the line, cross-link on the proposal, skip `board_duplicate_disposition.py` for lines (FR-013), and add the proposal to the Roadmap "Proposed" list as the issue path does.
- [x] T030 [P] [US2] Add fixtures for the evidence tick, the already-fixed hold, the proposal annotation, and selection skipping each of them afterwards; extend `verify-board-backlog-lines.py`.

**Checkpoint**: US2 passes independently.

---

## Phase 6: User Story 3 - Hold a line it cannot finish (Priority: P2)

**Goal**: every site that adds `board:stalled` to an issue instead annotates the line as held with the same reason text.

**Independent Test**: line needing a workflow edit with `WING_COMMANDER_BOARD_CAN_PUSH_WORKFLOWS` off is held and not reselected.

- [x] T031 [US3] Edit `board-loop.yml` at every site that adds `board:stalled` (triage handover, red gate suite at fix, workflow-scope hold, size-and-path backstop, unreadable/malformed/out-of-budget review round, not-ready handover, maintainer stop request recorded on the backlog issue, closing-keyword refusal): for `item_kind == line` call `hold` with the same reason and never label the backlog issue (FR-014, FR-017). The hold releases the board.
- [x] T032 [US3] Add the stand-down path: at each re-derivation, a line that is ticked, deleted or no longer matches its id (or whose id is duplicated) makes the loop stop without writing, leave any open PR for a maintainer, and comment on the backlog issue (FR-016).
- [x] T033 [P] [US3] Add fixtures for each hold reason string, hold removal making the line eligible again, and the stand-down cases; extend `verify-board-backlog-lines.py`.
- [x] T034 [US3] Add a check to `verify-board-backlog-lines.py` that no `board-loop.yml` step labels, closes or retitles the backlog issue for `item_kind == line` (FR-017, SC-005).

**Checkpoint**: all stories functional.

---

## Phase 7: Polish & Cross-Cutting

- [x] T035 [P] Walk through `specs/121-board-backlog-line-items/quickstart.md` against the fixtures and correct any command that no longer matches the implemented CLI.
- [x] T036 Run `python .github/scripts/run-local-gates.py` to green; perform `review-step-gating` (and `container-shell-safety` if a `container:` job was touched) over all `.github/workflows/` changes; confirm no private downstream names appear anywhere.
- [x] T037 Confirm `.specify/memory/constitution.md` is not edited by this PR (FR-022; the amendment is the separate PR #1115).

---

## Phase 8: Maintainer follow-up

- [ ] T038 [maintainer] Merge the Principle X constitution amendment PR (#1115) before this feature's final PR; confirm the `### X.` section contains `Maintenance backlog line` exactly once.
- [ ] T039 [maintainer] After merge, set repository variable `WING_COMMANDER_BOARD_BACKLOG_LINES=true` when ready to enable line claims.
- [ ] T040 [maintainer] Re-drive one `board-loop.yml` run with an unchecked line on #889 and record the evidence (claim, PR, tick) on the PR or issue #1080 (`prove-after-merge` skill).

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 (blocks all) → US4 (Phase 3) → US1 (Phase 4) → US2 and US3 (Phases 5, 6, can run in parallel after US1's workflow plumbing T021–T024) → Polish → Maintainer follow-up.
- Tasks T021–T024, T028, T029, T031 all edit `board-loop.yml`, so they are sequential, not [P].
- T005/T008, T013, T017, T025/T026, T030, T033 are fixture or separate-file tasks and can run alongside their neighbours.

## Parallel Example

```text
T005 fixtures (board-backlog-lines) alongside T008 fixtures (board-backlog-edit)
T025 PR-reference fixtures alongside T026 board-status.yml edit
```

## Implementation Strategy

MVP is Phases 1–4 (Foundational, US4 and US1): the shared edit helper protects #889 and one fix-shaped line goes end to end. Then add US2 (clearing stale and design-shaped lines), then US3 (holds), then polish. The feature stays dark until the maintainer follow-up in Phase 8.

## Review Gate Round 1 Findings

- [x] Review finding: resolve_backlog crashes on real author shape

  resolve_backlog tests `author not in allowed` with a string set, but gh issue snapshots carry author as {"login": ...}, so a dict raises TypeError (unhashable) instead of refusing with a reason.

  - .github/scripts/board_backlog_lines.py

  Detail: board_eligibility.py documents author as {login}; fixtures only use string authors.

- [x] Review finding: Generated title can contain closing keyword

  title_for builds `Fix: <line text>`; line text starting with #N makes CLOSING_RE match (FR-017 says the title never contains a closing keyword), which would close unrelated issues or cause refusal.

  - .github/scripts/board_backlog_lines.py

  Detail: e.g. line `#747 flaky gate` gives `Fix: #747 flaky gate`; no fixture covers a title built from line text containing a reference.

- [x] Review finding: edit() reports STAND_DOWN after own write landed

  If a write landed but the read-back verify was false (stale read), the retry finds the line already changed, apply returns None, and edit reports STAND_DOWN. The caller then wrongly believes another editor made the change.

  - .github/scripts/board_backlog_edit.py

  Detail: The retry loop should check verify on the freshly fetched body before re-applying.

- [x] Review finding: note-proof cannot carry a run link

  note_proof takes a url, but the _operations dispatcher and CLI never pass one, so the `[run](url)` suffix required by T024 is never written. No operation clears a not-proven note after a later proof succeeds.

  - .github/scripts/board_backlog_edit.py

- [x] Review finding: annotate/claim lack state preconditions

  annotate overwrites any existing annotation, and claim/annotate accept any state. A stale progress op can un-hold a held line, or release can clear another run's claim.

  - .github/scripts/board_backlog_lines.py

  Detail: The unused allow_new and only_unannotated parameters suggest the guards were never implemented.

- [x] Review finding: select_line claimed_ids filter is dead code

  `line['id'] is None and line['id'] not in claimed_ids` reduces to `None not in claimed_ids`, so the claimed_ids parameter excludes nothing.

  - .github/scripts/board_backlog_lines.py

- [x] Review finding: loop_paused truthiness vs string env value

  selection_gate treats loop_paused by truthiness, but the pause variable reaches workflows as the string 'true' or 'false'. The string 'false' is truthy, so the gate would report the loop as paused.

  - .github/scripts/board_backlog_lines.py

  Detail: _switch_on uses exact-'true' semantics; fixtures use only Python booleans.

- [x] Review finding: Multi-line comments and mismatched fences yield phantom lines

  parse_lines tracks only a single fence toggle, ignoring marker type and length. It also does not handle multi-line HTML comments, so checkboxes inside them become selectable, contradicting 'comments are never read'.

  - .github/scripts/board_backlog_lines.py

  Detail: Only the single-line `<!-- -->` form has a fixture.

- [x] Review finding: New board-loop step can fail select job while feature is dark

  The 'Record the backlog-line switch' step has no continue-on-error, so an import or syntax failure in either helper fails the select job on every run, contradicting FR-020 (a dark switch changes nothing).

  - .github/workflows/board-loop.yml

- [x] Review finding: Duplicated gh closures and aggressive newline stripping

  gh_fetch and gh_write are duplicated as closures inside main(), so fixes can drift. The fetch strips all trailing newlines, and CRLF bodies get mixed line endings, which rewrites parts of a body that a concurrent editor may own.

  - .github/scripts/board_backlog_edit.py

## Review Gate Round 2 Findings

- [x] Review finding: Read-back verify ignores detail/note text

  verify() checks only state and checked flag, so progress/hold/route-proposal/note-proof/repeated tick pass read-back even when a concurrent writer dropped the written text.

  - .github/scripts/board_backlog_edit.py

  Detail: A line already in-progress annotated with PR #7 is restored by a concurrent whole-body write; verify still returns True and edit() returns APPLIED.

- [x] Review finding: resolve_backlog compares state to lowercase 'open'

  gh returns state OPEN/CLOSED, so against real gh JSON every issue is skipped and no backlog is ever resolved; fixtures use lowercase so gates stay green.

  - .github/scripts/board_backlog_lines.py

  Detail: issue.get('state','open') != 'open' rejects 'OPEN'; the result is 'no open Maintenance backlog issue'.

- [x] Review finding: CLI edit path exits 0 on failed and misses gh errors

  board_backlog_lines.py CLI prints the edit() result and exits 0 even for 'failed', and does not catch the RuntimeError that _gh raises; board_backlog_edit.py exits 1 for the same result.

  - .github/scripts/board_backlog_lines.py
  - .github/scripts/board_backlog_edit.py

  Detail: A workflow step piping an op into the CLI passes when retries are exhausted, so the tick is silently lost. The contract's 'release' subcommand is also rejected as an unknown op.

- [x] Review finding: Maintainer author check is login-set only

  resolve_backlog accepts the author only if it is in maintainer_logins (default empty) or is the bot; author_association is never checked, so the default two-arg call rejects the human-owned backlog.

  - .github/scripts/board_backlog_lines.py

  Detail: resolve_backlog(open_issues, bot_login) rejects issue #889 authored by the owner.

- [x] Review finding: Line markers still visible to matching marker readers

  Only find_latest_marker skips line-keyed markers; find_markers_matching and find_latest_marker_matching still return them, so issue-path readers such as board_eligibility can read a backlog line marker as an issue marker.

  - .github/scripts/board_item_marker.py

  Detail: board_eligibility.py:255 uses find_latest_marker_matching with a predicate that does not test 'line'; the fixture tests cover only read_marker.

- [x] Review finding: Line rewrites normalize whitespace and move tokens

  annotate/claim/tick rebuild the line from whitespace-collapsed text, so user-owned content is altered and the token moves to the end, which clobbers concurrent human edits.

  - .github/scripts/board_backlog_lines.py

  Detail: Double spaces are collapsed and a mid-line token moves to the end after clear_note or annotate.

- [x] Review finding: note_proof strips maintainer's own [run] link

  note_proof removes any [run](...) link from the line text, including one the maintainer wrote, and no op clears the not-proven note once a later proof succeeds.

  - .github/scripts/board_backlog_lines.py

  Detail: The data-model's 'fixed + not-proven -> fixed' transition has no implementing op; tick refuses a checked line.

- [x] Review finding: Closing-keyword defang misses GH-N references

  title_for inserts U+200B after '#' before a digit, but CLOSING_RE and the defang do not cover GH-N, which GitHub also treats as an issue reference, so FR-017 can be bypassed.

  - .github/scripts/board_backlog_lines.py

  Detail: A line saying 'Fixes GH-747' passes through unchanged and can close issue 747 on merge.

- [x] Review finding: Single-home scan for backlog body edits is easy to evade

  The scan matches only a single-line 'gh issue edit ... --body' that contains the word 'backlog', so multi-line run blocks, gh api PATCH, or --body-file on a line without 'backlog' evade it.

  - .github/scripts/verify-board-backlog-edit.py

  Detail: FR-024 'no other file edits the backlog body' goes unenforced for those forms.
