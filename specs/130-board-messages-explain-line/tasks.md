# Tasks: Board loop messages explain the line

**Input**: `specs/130-board-messages-explain-line/` (plan.md, spec.md, research.md, data-model.md, contracts/message-parts.md, quickstart.md)

**Tests**: FR-008 requires a gate with checked-in fixtures; fixture and gate tasks are included. Run `python .github/scripts/run-local-gates.py` before pushing, and give workflow edits a pass from the `review-step-gating` skill (prose guidance, not a task).

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [x] T001 Read `.github/scripts/board_spec_request_body.py` (`fenced_section`), `.github/scripts/wc_session_record.py` and the review/PR steps of `.github/workflows/board-loop.yml` to confirm the hook points named in plan.md; no file changes.
- [x] T002 [P] Create fixture directory `.github/scripts/fixtures/board-message-parts/` with a README line naming the gate that reads it.

## Phase 2: Foundational

**Purpose**: the surface-independent renderer every story uses.

- [x] T003 Create `.github/scripts/wc_message_parts.py` with the part sets and part shape `{state, text}` per `data-model.md` `Explanation.parts` and `Review report.parts` (state values per `data-model.md` Explanation `state`), and `gap_text(part, kind)` per contracts/message-parts.md.
- [x] T004 In `.github/scripts/wc_message_parts.py` add fencing of agent/backlog text via `fenced_section` (FR-003a), the one-screen lead plus `<details>` overflow (FR-018, `data-model.md` Rendering rules), and the 57000 UTF-16 cap (contract guarantee 5).
- [x] T005 In `.github/scripts/wc_message_parts.py` add the CLI (`render-explanation|render-review|summary --in FILE --id ID`; exit 0 body on stdout, exit 2 on refusal) per contracts/message-parts.md.

**Checkpoint**: renderer callable standalone.

## Phase 3: User Story 1 - First comment explains the line (P1) 🎯 MVP

**Goal**: first loop comment and PR-body summary carry all explanation parts (FR-001–FR-004, FR-001a).
**Independent Test**: render the bl-b9677278 / #1202 fixture and read it against the owner-reviewed draft; every part filled or gap.

- [x] T006 [US1] Implement `render_explanation` in `.github/scripts/wc_message_parts.py`: all six parts always present, `options` may be state `follow`, `line` accepts issue title + `#N` (FR-001a).
- [x] T007 [US1] Implement `summary` mode in `.github/scripts/wc_message_parts.py`: fenced one-sentence issue plus what the PR does, pointing at the first comment; refuse and name any closing keyword (FR-004, spec 121 rule).
- [x] T008 [P] [US1] Add fixtures under `.github/scripts/fixtures/board-message-parts/`: full #1202 example, one per explanation part missing, no-code line, options-follow, fence/HTML injection, closing keyword, over-length.
- [x] T009 [US1] Wire the first comment and PR-body summary into the fix-PR opening step of `.github/workflows/board-loop.yml`, calling the renderer CLI (no pasted shell/jq; one-line fallback only), including a later "options" comment when state is `follow` before the PR is reported ready (FR-003).
- [x] T010 [US1] Add the one-line decision record with link to the explaining comment when a backlog line is ticked, in `.github/scripts/board_backlog_lines.py` (FR-017).

## Phase 4: User Story 2 - Review comment reports against the line's question (P1)

**Goal**: review comment has the five review parts and never a bare "No findings" (FR-005–FR-008a).
**Independent Test**: render review fixtures with and without findings; five parts present, identifier named.

- [x] T011 [US2] Implement `render_review` in `.github/scripts/wc_message_parts.py`: five parts always present, identifier named, open findings listed under Open, never reduces to "No findings" (FR-006, FR-007).
- [x] T012 [P] [US2] Add review fixtures under `.github/scripts/fixtures/board-message-parts/`: no findings, with findings, one per part missing, non-string part, review-did-not-complete.
- [x] T013 [US2] Add `report: {asked, checked, decided, not_decided, open}` (each optional string) to the review agent's result schema and prompt in `.github/workflows/board-loop.yml`, and replace the bare "No findings." body with the renderer output; a failed or timed-out review posts "review did not complete" (Edge Cases).
- [x] T014 [US2] Create `.github/scripts/verify-board-message-parts.py` mode 1: render every fixture and fail when any rendered part is neither filled nor gap, or when output is a bare "No findings"; register it in the gate registry so `run-local-gates.py` runs it.

## Phase 5: User Story 3 - Fixed text tells the truth (P2)

**Goal**: every fixed-text message matches switch/class configuration and repository protections (FR-009–FR-011).
**Independent Test**: gate mode 2 enumerates auto-merge × kill switch × PR class with zero mismatches.

- [x] T015 [US3] Create `.github/scripts/board-fixed-messages.json` registering each fixed message with `id`, `source`, `variants[].when` (`auto_merge`, `kill_switch`, `pr_class`), `text` and `claims[]` per `data-model.md` Fixed-text message.
- [x] T016 [US3] Make fixed wording truthful in `.github/scripts/board_readiness.py` (merge/wait wording per auto-merge and class, stopped wording under kill switch) and `.github/scripts/board_prove.py` (replace "required checks" with what actually ran) (FR-009, FR-010).
- [x] T017 [US3] Add mode 2 to `.github/scripts/verify-board-message-parts.py`: enumerate the registry across all configurations, fail on a contradicted claim or an unregistered fixed message (FR-011); add a failing fixture for each branch.
- [x] T018 [P] [US3] Add a check in `.github/scripts/verify-board-message-parts.py` that the posting-time sources named by the registry still contain the registered text, so drift fails.

## Phase 6: Polish

- [x] T019 [P] Update `docs/reference.md` if any default, limit or switch description changed, per its stated rule.
- [x] T020 Add the "single home" check (no pasted renderer logic in workflows) to `.github/scripts/verify-board-message-parts.py`, per CLAUDE.md.
- [x] T021 Walk `specs/130-board-messages-explain-line/quickstart.md` against the fixtures and fix mismatches in code.

## Phase 7: Maintainer follow-up

- [ ] T022 [maintainer] After merge, re-drive one board-loop run on a backlog line and record on #1215 that the first comment, review comment and ticked-line record took the new path (`prove-after-merge`).

## Dependencies

- Phase 2 blocks all stories. US1 and US2 are independent after it (both extend the same module; do T006/T007 before T011 to avoid edit conflicts). US3 is independent of US1/US2 except sharing `verify-board-message-parts.py` (T014 before T017). T009 and T013 both edit `board-loop.yml`: sequence them. T022 last.

## Parallel examples

- T008 with T006/T007; T012 with T011; T018 with T016; T019 with T020.

## Strategy

MVP = Phases 1–3 (US1), since every later message depends on the explanation. Then US2 (removes the misleading "No findings"), then US3.

## Phase 8: Convergence

- [x] T023 Have the fix agent's result schema and prompt in `.github/workflows/board-loop.yml` supply the explanation parts (`code`, `issue`, `why_it_matters`, `options`, `what_this_pr_does`) so the "Explain the line on the PR (fix)" step fills them instead of leaving gaps, and post the later `options` comment when state is `follow`, per FR-001/FR-003 (partial)
- [x] T024 Hold readiness in `.github/scripts/board_readiness.py` while the loop's first comment says the options follow and no later loop options comment lists them, read back from the PR's own comments by the first-line markers `wc_message_parts.py` writes (research.md D4; owner decision on #890), with a human-readable reason; "Evaluate readiness" in `.github/workflows/board-loop.yml` passes the PR's comments (unreadable comments hold readiness). Fixtures in `.github/scripts/tests/board-readiness/options-*` (owed and missing, owed and posted, not owed, another author's options comment, unreadable)

## Review Gate Round 1 Findings

- [x] Review finding: Closing keyword in fixer explanation aborts the whole fix PR

  In board-loop.yml 'Open the PR', a summary refusal (exit 2) from wc_message_parts.py hits exit 1 after the branch is pushed, so agent prose like 'fixes #12' stops the PR from opening; open without the summary and warn instead.

  - .github/workflows/board-loop.yml

  Detail: A fixer 'what_this_pr_does' of 'Fixes #1202 by rendering the parts' makes summary exit 2, then exit 1, and no PR is opened.

- [x] Review finding: Gate 165 comment header altered and Gate 175 inserted out of order

  lint-workflows.yml changes '# Gate 165 — specs/115-...' to '# Gate 165— ...', dropping a space; workflow comments are byte-compared by gates, so restore the original text and place the new block in order.

  - .github/workflows/lint-workflows.yml

  Detail: A gate that parses the '# Gate NNN —' headers may fail or skip Gate 165's block.

- [x] Review finding: Options-owed readiness hold is opt-in via pr_comments=None

  evaluate_from_snapshot defaults pr_comments=None, meaning clear, and evaluate() and main never pass comments, so those callers report ready while the promised options comment is missing; make it required or fail closed.

  - .github/scripts/board_readiness.py

  Detail: A PR whose first comment says options=follow gets ready: true from evaluate() or the CLI.

- [x] Review finding: Failed options comment post leaves PR held with no retry

  If the options comment post fails, the step only warns and exits 0, and readiness holds durably as 'owed'. Nothing reposts it, so the PR never becomes ready; add a retry, reorder the posts, or say which step to repeat.

  - .github/workflows/board-loop.yml
  - .github/scripts/board_readiness.py

  Detail: A transient gh pr comment failure on the second post leaves options=follow with no options comment.

- [x] Review finding: _cap truncates body without closing open fences or details

  wc_message_parts._cap hard-cuts at a UTF-16 offset, which can leave a code fence or <details> block open before the '(truncated)' marker; close any open fence or details block after cutting.

  - .github/scripts/wc_message_parts.py

  Detail: A body just over 57000 units cut mid-fence renders the rest of the comment, including the marker line, inside a code block.

- [x] Review finding: Incidental whitespace edit 'in_scope =[f for f' in workflow

  An unrelated whitespace change in the findings-writing Python snippet in board-loop.yml risks byte-compare gate drift; revert to 'in_scope = [f ...'.

  - .github/workflows/board-loop.yml

- [x] Review finding: render_review called with findings=[] shows Open as 'not provided'

  A review that has findings still renders the Open part as 'not provided -- the author did not provide it' unless the agent filled it; pass the real kept findings or render Open from their count.

  - .github/workflows/board-loop.yml

  Detail: With 2 in-scope findings and no 'open' from the agent, the comment says Open: not provided above the findings list.

- [x] Review finding: tick_record claims explanation is in first PR comment without guarantee

  board_backlog_lines.tick_record says the explanation is in the first comment on the PR, but the Explain step can be skipped on failure with only a warning; post the record only when the explaining comment exists, or link to it.

  - .github/scripts/board_backlog_lines.py

  Detail: If the explain step fails, the backlog record still points at an unrelated or empty first comment.

## Review Gate Round 2 Findings

- [x] Review finding: options hold never fires via evaluate() (author.login vs login)

  board_readiness.evaluate reads gh pr view comments where author is author.login, but options_comment_owed only reads login or user.login, so every comment is skipped and options state is always clear, failing open.

  - .github/scripts/board_readiness.py

  Detail: Workflow inline path maps .user.login and works; evaluate(pr) entry point does not.

- [x] Review finding: Review comment can say 'Nothing open' above in-scope findings

  The code only fills the open part with the real finding count when the agent's open part is empty, so an agent-written 'Nothing open.' stands next to a non-empty findings list.

  - .github/workflows/board-loop.yml

  Detail: Set or append the in-scope finding line whenever kept_count is non-zero.

- [x] Review finding: CLOSING_RE misses 'GH-N' and filler-word closing forms

  The closing-keyword check does not match 'fixes GH-12' or 'closes the issue #12', so agent prose with a closing reference can reach the PR body and auto-close an issue on merge.

  - .github/scripts/wc_message_parts.py

- [x] Review finding: PR summary always points at a first comment that may not exist

  The summary says the full explanation is in the first comment, but the explain step can skip or fail to post it with only a warning, or another comment can land first.

  - .github/scripts/wc_message_parts.py

- [x] Review finding: board_readiness main() defaults missing pr_comments to unreadable

  main() treats a missing pr_comments key as COMMENTS_UNREADABLE, while evaluate_from_snapshot treats it as None (skip). Old-shape payloads become durably not-ready with a misleading reason.

  - .github/scripts/board_readiness.py

- [x] Review finding: normalize_part accepts state 'follow' for non-options parts

  A 'follow' state on parts other than options renders 'options follow in a later comment' though no options comment is owed.

  - .github/scripts/wc_message_parts.py

- [x] Review finding: Dead parts dict in render_incomplete_review

  render_incomplete_review builds a parts dict that is never used and then deletes it, which is leftover code.

  - .github/scripts/wc_message_parts.py

## Review Gate Round 3 Findings

- [x] Review finding: Review comment can say 'Nothing open.' above a list of in-scope findings

  The Compose step only fills Open when the agent's `open` is empty and calls render_review with [], so a non-empty kept_count can sit under 'Nothing open.'; the ticked Round 2 fix is not in the diff.

  - .github/workflows/board-loop.yml

  Detail: Always set or append the finding line to open when kept_count is non-zero, or pass the real findings to render_review, and add a fixture.

- [x] Review finding: Options hold fails open when bot_login is empty

  options_comment_owed skips all comments when bot_login is falsy, and evaluate() defaults BOT_LOGIN to '' (or the bogus '[bot]'), so readiness reports ready with the options comment still owed.

  - .github/scripts/board_readiness.py

  Detail: Treat an empty or bogus bot_login as unreadable when pr_comments is a list, and require a login in evaluate().

- [x] Review finding: tick_record posted as a separate comment, contrary to research.md D6

  Every tick-fixed posts a separate comment on the backlog issue, but D6 chose a suffix on the line itself, so FR-017 is not met as designed.

  - .github/scripts/board_backlog_lines.py

  Detail: Carry the record and a link to the explaining comment in the line's tick annotation, or update the design decision.

- [x] Review finding: pr_title fallback for what_this_pr_does is closing-keyword-checked

  A title like 'Fix #1202: ...' used as the fallback makes render_summary refuse it, so the PR opens with no summary and only a warning.

  - .github/scripts/wc_message_parts.py

  Detail: Exempt the title fallback from the closing-keyword check, or build the summary without the title.

- [x] Review finding: Gate 176 block inserted between Gate 165 blocks, out of order

  The new Gate 176 block sits between Gate 165 blocks although the Round 1 task said to place it in order; gates byte-compare workflow comments.

  - .github/workflows/lint-workflows.yml

  Detail: Move the block to its numeric position.

- [x] Review finding: Injection check in check_body only tests the literal '<script'

  The loop over text parts never uses its loop variable and tests the string '<script' against the whole body, so other leaked HTML outside the fence passes the gate.

  - .github/scripts/verify-board-message-parts.py

  Detail: Test each user text against the body outside fences instead of the fixed payload.

## Review Gate Round 4 Findings

- [x] Review finding: Agent summary text can stop the backlog-line fix PR from opening

  The summary is appended to pr_body before the closing-keyword check, which exits 1 using board_backlog_lines.closing_keyword_hits, a different matcher from CLOSING_RE. Any hit leaves a pushed branch with no PR. Run the check on the base body first and fatally, then run it on the body with the summary and drop the summary on a hit.

  - .github/workflows/board-loop.yml

  Detail: check-closing-keywords now runs on the combined pr_body, including agent-written text

- [x] Review finding: A failed first options comment leaves readiness reading 'clear'

  When the first gh pr comment is refused or fails, the step exits 0 and no marker is left on the PR. If the fixer asked for follow options, readiness then reads 'clear' and the PR proceeds toward merge with no explanation. Post a minimal marker comment, or fail the step.

  - .github/workflows/board-loop.yml

  Detail: The failure path warns and exits 0 with no readable marker

- [x] Review finding: board_readiness.evaluate() depends on an unset BOT_LOGIN

  evaluate() takes bot_login from os.environ BOT_LOGIN, and no caller was changed to set it. An empty value makes _options_state return 'unreadable', so readiness is held for every PR this entry point evaluates. Take bot_login as a parameter, or confirm that no caller uses evaluate().

  - .github/scripts/board_readiness.py

- [x] Review finding: options_clear is missing from the CONDITIONS tuple

  The new options_clear readiness condition is not in CONDITIONS, which verify-board-merge.py imports as READINESS_CONDITIONS. Gates that enumerate the conditions will not cover the options hold.

  - .github/scripts/board_readiness.py

- [x] Review finding: The tick-fixed request's pr field is never read

  The tick-fixed request now carries a pr field, but board_backlog_lines.py passes only line_id, detail and url to bbe._operations. The field is ignored. Wire it through or revert the hunk.

  - .github/workflows/board-loop.yml

## Maintainer Feedback (review of head 568c9717)

- [ ] MF001 FR-017/T010/T022: Build the ticked-line record in `board_backlog_lines.py` (restore `tick_record()`, add research.md D6's `decided: ... (link)` suffix). Wire the merge path (board-loop.yml ~6934) to use it instead of `detail: "by #N"`. Add a fixture that fails without it.
- [ ] MF002 Story 3 (FR-009, FR-011, SC-003): Change `board_readiness.py` wording. The ready report (board-loop.yml ~5948) must say whether the loop will merge, or that the PR waits for a human and why (scenarios 1-2), or that the loop is stopped (scenario 4). Register the readiness, stand-down and hold notes in `board-fixed-messages.json`. Make the gate's FR-011 list complete and checked rather than opt-in on `# fixed-message:` tags. Add a fixture with an untagged message that fails the gate.
- [ ] MF003 "Explain the line on the PR (fix)" (board-loop.yml ~3874): Replace `exit 1` after three failed first comments with a warning, or gate the later steps with `!cancelled()`. The route backstop re-check, cross-link and issue marker must still run. Add a self-test.
- [ ] MF004 Gate 176 `check_body`: Check the text after each label, not just the bold label. Add one fixture per mutation: gap text dropped; every filled part rendered as a gap; `CLOSING_RE` without its `GH-N` and URL forms; the fix-class transient claim swapped to `board_merges_next_run`.
- [ ] MF005 Compose step (board-loop.yml ~4760): When `kept_count == 0` and the reviewer left out the report block, `render_review({}, id, [])` must say nothing is open (Story 2 scenario 1, FR-005) rather than show five "not provided" gaps. Add a fixture.
- [ ] MF006 Review body size: Subtract the `render_review` block from the findings budget `(57000 - len(tail)) // len(shown)`. Cap review-report parts as `AGENT_PART_CAP` caps explanation parts. Add a test that a worst-case body stays at or under 65,536 characters.
- [ ] MF007 `board_readiness.evaluate()`: Remove it, or wire in a caller and compare the GraphQL `author.login` correctly (an App login has no `[bot]` suffix). Add a test for the chosen path.
- [ ] MF008 Empty options comment: When the fixer says options follow but supplies no text, render a gap in the first comment. Do not post an "Options: not provided" comment that clears the hold. Add a fixture.
- [ ] MF009 Gate numbering: Renumber this PR's board-message gate past main's highest number (main has Gate 176, `verify-skill-scripts.py`). Update the `lint-shard-8` step names and put the number in the script's docstring so Gate 174's duplicate check sees it. Run `python .github/scripts/run-local-gates.py`.
