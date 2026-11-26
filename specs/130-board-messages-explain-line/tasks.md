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
