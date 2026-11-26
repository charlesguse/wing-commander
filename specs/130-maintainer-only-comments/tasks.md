---

description: "Task list for spec 130: comment-triggered stages act only on maintainers"
---

# Tasks: Comment-Triggered Stages Act Only on Maintainers

**Input**: Design documents from `/specs/130-maintainer-only-comments/`

**Prerequisites**: plan.md, spec.md, research.md (D1–D7), data-model.md, contracts/comment-author-rule.md, quickstart.md

**Tests**: Required by this repository's review rule. Every change task names the gate check, mutant or harness case that fails without it. The new gate (T003) is written first and fails on today's tree.

**Organization**: Tasks are grouped by user story, so each story can be built and tested on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1, US2 or US3 from spec.md

---

## Phase 1: Setup

- [X] T001 Build the inventory and record it under "Notes" in `specs/130-maintainer-only-comments/tasks.md`. It covers every live site that admits a comment by identity or describes the issue-author exception, across `.github/workflows/`, `.github/actions/` (including `_shared/`), `.github/scripts/`, `docs/` and `specs/*/contracts/`. Expected sites are plan.md's Source Code list plus `verify-clarification-gating.py`, `verify-issue-context-single-home.py`, `verify-diagnose-shadow-acts-on-nothing.py`, the four auto-release e2e decision gates, and the specs/029 `notice-callout.md`, specs/055 and specs/057 contracts. Also record the next free gate number from `.github/workflows/lint-workflows.yml`.

---

## Phase 2: Foundational (blocks every story)

- [X] T002 Write the gate `.github/scripts/verify-maintainer-only-comments.py` (FR-010, research D7, contract `contracts/comment-author-rule.md`).
  - Checks (a)–(f), plus the single-home check for the relay paragraph's literal.
  - `--self-test` gets one mutant per check. Each mutant reintroduces the exception, or moves the literal into a second file, and must be caught.
  - The maintainer set is read from data-model.md "Maintainer set". Do not restate it.
  - Run the gate on today's tree. It MUST fail on (a), (c), (d), (e) and (f), and on (b)'s missing step. That proves the gate sees today's behaviour.
- [X] T003 Register the gate in `.github/workflows/lint-workflows.yml` under the number recorded in T001. (`docs/reference.md` lists loops, defaults and switches, not gates, so there is no row to add.) Fails without it: `run-local-gates.py` does not list the gate.

**Checkpoint**: the new gate exists and is red. Story work turns it green.

---

## Phase 3: User Story 1 — A non-maintainer's reply does not steer clarify (P1) 🎯 MVP

**Goal**: only a maintainer's comment starts or feeds a clarify run (FR-001, FR-005, FR-006, FR-007, FR-008).

**Independent Test**: quickstart §2 (clarify check step, relay composite) and §3 steps 2–3.

- [X] T004 [US1] In `.github/workflows/wing-commander-2-clarify.yml`:
  - remove the issue-author clause from the job `if:`;
  - rewrite the header and gate comments to state maintainers-only.

  Fails without it: gate check (a) and its mutant.
- [X] T005 [US1] In `.github/workflows/clarify.yml`, add the comment-author check step (research D1) right after "Checkout pipeline repository (shared composite actions)".
  - It reads data-model.md Comment.user.type and Comment.author_association by the `comment-id` input.
  - Add its `maintainer == 'true'` condition to "Check lifecycle issue state" and to "Note closed lifecycle and stop".
  - Fails without it:
    - gate check (b) and its mutant;
    - a harness case in the gate's self-test that runs the step against a fake `gh`. `OWNER` and `COLLABORATOR` must give `true`; `NONE`, `CONTRIBUTOR` and a `Bot` user must give `false`; a failed read must fail the step.
- [X] T006 [US1] In `.github/workflows/clarify.yml`, remove `Bash(gh issue view:*)` from "Compose tool args (clarify)" `default-allowed-tools` (research D6). Fails without it: gate check (f) and its mutant.
- [X] T007 [P] [US1] Create `.github/actions/wing-commander-requester-relay-note/action.yml` (research D3).
  - Inputs: `issue-number`, `token`, `body-file`.
  - It reads data-model.md Issue.author_association and appends the one relay paragraph when the author is outside the maintainer set, or when the read fails.
  - Fails without it: harness cases in the gate's self-test (`NONE` appends exactly once; `OWNER` leaves the file byte-identical; a failed read appends), and the single-home check.
- [X] T008 [US1] Call the T007 composite on the body file before posting, in two places:
  - `.github/workflows/intake.yml`, "Announce clarification needed" (`intake-clarification.md`);
  - `.github/workflows/clarify.yml`, "Announce remaining clarification questions" (`clarify-followup.md`).

  Fails without it: a gate check that both callout steps are preceded by the composite on the same body file, with a mutant that drops one.
- [X] T009 [P] [US1] Remove the author clause and its author-id parameter from `.github/actions/_shared/auto-release-e2e-clarify-decision.sh`.
  - Remove `.github/workflows/auto-release.yml`'s two issue-author-id reads and their `fail_infra_on_read` path (research D5).
  - Update `specs/055-unattended-e2e-gates/contracts/gate-decision-scripts.md` and the e2e decision gates found in T001.
  - Fails without it: gate check (e) and its mutant, and the e2e decision gates' fixtures. A maintainer-answered fixture stays satisfied; a non-maintainer-author fixture becomes unsatisfied.

**Checkpoint**: gate checks (a), (b), (e) and (f) are green, and the relay harness passes.

---

## Phase 4: User Story 2 — Agents read only maintainers' comments (P2)

**Goal**: the shared comment trust filter and intake's callout follow the rule (FR-003, FR-004).

**Independent Test**: quickstart §2, comment filter.

- [X] T010 [P] [US2] In `.github/actions/wing-commander-issue-context/action.yml`:
  - remove the identity clause from the qualifying, excluded and staging filters;
  - drop the unused `AUTHOR_ID` read;
  - keep the data-model.md Outputs (`qualifying-count`, `excluded-human-count`, `comments-file`) and their formats unchanged;
  - update the header comment.

  Fails without it: gate check (c) and its mutant, and a harness case with comments from a maintainer, a non-maintainer author and a bot. Only the maintainer's comment is staged, and `excluded-human-count=1`. Update `verify-issue-context-single-home.py`'s fixtures to match.
- [X] T011 [US2] In `.github/workflows/intake.yml`, change the "did not qualify" callout to "not from a maintainer" (FR-004). Update `specs/029-intake-issue-comments/contracts/notice-callout.md` and `contracts/comment-trust-gate.md`. Fails without it: the callout-text assertion in `verify-clarification-gating.py`, or the gate T001 finds pinning that text, updated to the new wording.

**Checkpoint**: gate check (c) is green, and SC-003 holds (maintainer-only fixtures are byte-identical).

---

## Phase 5: User Story 3 — The Spec Kit updater follows the rule (P3)

**Goal**: FR-002.

**Independent Test**: spec.md US3 acceptance scenarios, run through the gate's harness on the `comment-reply` job's `if:`.

- [X] T012 [P] [US3] In `.github/workflows/auto-update-spec-kit.yml`:
  - remove the `issue-author-id` comparison from the `comment-reply` job `if:`;
  - describe the `issue-author-id` input as accepted and ignored (research D2);
  - update the comment above the job.

  Fails without it: gate check (d) and its mutant.
- [X] T013 [US3] Stop passing `issue-author-id` from `.github/workflows/wing-commander-auto-update-spec-kit.yml`, and update `specs/027-auto-update-spec-kit/contracts/auto-update-spec-kit-workflow.md`. Fails without it: the gate's wrapper scan, check (a).

**Checkpoint**: the new gate passes on the whole tree, and `--self-test` catches every mutant.

---

## Phase 6: Polish and cross-cutting

- [X] T014 [P] Update `docs/adoption.md` (lines near 166, 238–244, 1535 and 1560) and `docs/architecture.md` (near 392, 455 and 1326) to the maintainers-only rule (FR-009).
  - Include the published behaviour change: clarify now checks the comment itself (FR-006).
  - Explain why adopters should not add `gh issue view` back through `extra-allowed-tools` (research D6).
- [X] T015 [P] Update the remaining live contracts to the rule (FR-009): `specs/010-reusable-pipeline/contracts/stage-interfaces.md`, `specs/033-pr-conversation-commands/contracts/wrapper-gate.md` (its "unlike clarify" contrast) and `specs/057-autonomous-board-loop/contracts/triage.md`.
- [X] T016 [P] Rewrite the workflow comments that contrast pr-conversation with clarify and intake in `.github/workflows/pr-conversation.yml` (near 730) and `.github/workflows/wing-commander-9-pr-conversation.yml` (near 12). Re-run Gate 47 (`verify-comment-canonical-pointers.py`).
- [X] T017 Run quickstart §1, the new gate and every gate T001 listed, then `run-local-gates.py` filtered as usual. Compare each failure with an `origin/main` worktree, and record the results in `specs/130-maintainer-only-comments/tasks.md` "Notes". Confirm FR-011 from the diff: no edit to intake's `spec-request` entry, to pr-conversation's actor gate, or to Principle X's board-loop entry.
- [X] T018 Run the `review-step-gating` skill on the `if:` changes in `.github/workflows/clarify.yml`, `.github/workflows/auto-update-spec-kit.yml` and `.github/workflows/wing-commander-2-clarify.yml`. Run the `container-shell-safety` skill on the new `run:` step in clarify's container job.
- [ ] T019 Review the local branch with separate local sessions until a pass comes back clean (the review-until-clean procedure, without a PR). Fix each real finding with a test that fails without it.
  - [X] T019a [US3] After review pass 4 (owner's decision, 2026-11-25): in `.github/workflows/auto-update-spec-kit.yml`'s `comment-reply` job, stage only the issue body, the pipeline's own comments and maintainers' comments for the agent, and accept a chosen option only when it is a label the pipeline posted (FR-002). Update `contracts/comment-author-rule.md` and `specs/027-auto-update-spec-kit/contracts/auto-update-spec-kit-workflow.md`. Fails without it: `auto-update-spec-kit-tests/t6_reply.sh`'s six "spec 130" checks (the stub now lists an issue's comments in the REST shape).
  - [X] T019b After review pass 4: `.github/scripts/wc_board_status.py` counts a clarify answer only from a maintainer, as clarify acts on no other reply. Fails without it: `verify-board-status.py`'s "the issue's own author who is not a maintainer answers nothing (spec 130)".
  - [X] T019c After review pass 4 (owner's decision, 2026-11-25): `.claude/skills/answer-from-precedent/SKILL.md` no longer says the clarify wrapper admits the requester. No gate reads it.
  - [X] T019d [US3] After review pass 5: the `comment-reply` read-back refuses a multi-line chosen value (FR-002). Fails without it: `t6_reply.sh`'s "a multi-line choice holding a posted label -> not recognized".
  - [X] T019e [US3] After review pass 5 (owner's decision, 2026-11-25): evaluate-path's ambiguous-options question records its option labels on its last line, and the `comment-reply` read-back accepts only a label the newest question records, never re-reading the rendered option list (FR-002). `auto-update-spec-kit-tests/extract.py` now extracts the `wing-commander-callout` composite, so t6 posts the question through it. Update `contracts/comment-author-rule.md` and `specs/027-auto-update-spec-kit/contracts/auto-update-spec-kit-workflow.md`. Fails without it: `t6_reply.sh`'s "an earlier question's labels and another callout's record do not count" and "the question's record holds exactly its labels".
- [ ] T020 Run the scratch-repository proof (quickstart §3) in `charlesguse/wing-commander-auto-release-scratch`, outside auto-release's 09:09 UTC run, and restore the wrapper pins afterwards. Record the evidence in `specs/130-maintainer-only-comments/tasks.md` "Notes".
- [ ] T021 Prepare the publish:
  - Re-check the number 130 against open pipeline branches, and rename the directory and branch if it is taken.
  - Add `specs/130-maintainer-only-comments/spec-meta.json`, pointing at a neutrally titled tracking issue opened at publish time (precedent: spec 037 and #216).
  - Push one PR whose title names the behaviour change (research D2): clarify's own check, and the Spec Kit updater's narrower reply context (FR-002). The owner merges it, after PR #1194.
- [ ] T022 After merge (prove-after-merge, quickstart §4): show the next auto-release e2e passing its clarification step (SC-004), and one real clarify run with `maintainer=true`. Record both on the PR.

---

## Dependencies and execution order

- T001 → T002 → T003. Then US1, US2 and US3 can run in any order.
- Within US1, T005 → T006 → T008, because they share `clarify.yml`. T007 must precede T008. T004 and T009 are independent.
- US2: T010 and T011 are independent.
- US3: T012 → T013.
- Polish: T014–T016 in parallel once the stories land. Then T017 → T018 → T019 → T020 → T021 → T022.

## Parallel examples

- After T003: T004, T007, T009, T010 and T012 touch different files.
- In polish: T014, T015 and T016.

## Implementation strategy

- MVP is US1: the clarify path, including the stage-side check and the relay text.
- US2 and US3 follow in the same local branch.
- Nothing is pushed until T021. One PR carries spec plus code.

## Notes

(T001 inventory, T017 gate results and T020 scratch evidence are recorded here.)

### T001 inventory (2026-11-24)

- **Gate number:** 172. Gate 171 is claimed by open PR #1184; re-check at T021.
- **Code:**
  - `wing-commander-2-clarify.yml` (if: and header);
  - `clarify.yml` (new check, grant, follow-up relay);
  - `intake.yml` (callout text at ~816, the comment at ~776, first-question relay);
  - `auto-update-spec-kit.yml` (comment-reply if:, the comment at ~3466, the `issue-author-id` and `commenter-id` input descriptions);
  - `wing-commander-auto-update-spec-kit.yml` (stops passing `issue-author-id` and `commenter-id`);
  - `wing-commander-issue-context/action.yml` (three filters, header and input description);
  - `_shared/auto-release-e2e-clarify-decision.sh` with `auto-release.yml` (author-id parameter and reads);
  - `board-loop.yml` agent prompts at ~2087, ~2564 and ~3286 ("or one from the issue's own author"; lines ~575 and ~1961 are Principle X's maintainer-authorship entry, unchanged);
  - `pr-conversation.yml` ~730 and `wing-commander-9-pr-conversation.yml` ~11–12 (the "unlike clarify/intake" contrast).
- **Gates and fixtures:**
  - `verify-issue-context-trust-filter.py` (Gate 96: author fixture and mutation invert);
  - `verify-auto-release-e2e-gate-decisions.py`, plus the other e2e decision gates that call the script;
  - `auto-update-spec-kit-tests/t7_gating.py`;
  - `verify-clarification-gating.py`;
  - `verify-gate-106.py`;
  - `fixtures/project-root-compat/interface.json`.
- **Docs:** `docs/adoption.md`, `docs/architecture.md`, `docs/reference.md` (one line).
- **Live contracts:**
  - specs/010 `stage-interfaces.md`;
  - specs/027 `auto-update-spec-kit-workflow.md`;
  - specs/029 `comment-trust-gate.md` and `notice-callout.md`;
  - specs/032 `decision-points.md` and `clarification-schema.md`;
  - specs/033 `wrapper-gate.md` and `reusable-pr-conversation.md`;
  - specs/055 `gate-decision-scripts.md`;
  - specs/057 `triage.md`;
  - specs/063 `e2e-clarification-label-assertion.md`;
  - specs/115 `board-merge.md`.

  Each is checked at T015, and changed only where it describes the exception as current behaviour.

### T018 review skills (2026-11-24)

- **review-step-gating:**
  - Gate 24: 0 failures.
  - `stranded-steps.py`, compared with origin/main: the only new entry is the relay step. It is stranded only together with the callout it feeds, which has the same `if:` (Gate 179 (g)); that is clarify's hard-exit-in-place design.
  - A refused comment ends the clarify job successfully, so `stalled` does not fire.
  - Low note, kept by design: a failed comment read fails the job and `stalled` posts its notice, like any infrastructure failure.
- **container-shell-safety:**
  - Gate 43: pass.
  - `unpinned-container-steps.py`: 0 unpinned steps in clarify.yml and intake.yml. The new check step's bash constructs are covered by the workflow-level `shell: bash -e {0}`, and the relay composite pins `shell: bash`.

### Gates run by hand during T002–T016

| Gate | Result |
|---|---|
| Gate 179 | pass; self-test catches all 12 mutants |
| Gate 66 (e2e decisions) | pass, plus self-test |
| Gate 115 (poll credential) | pass, plus self-test |
| Gate 91 (specs fallback) | pass |
| Spec Kit tests | 574 passed |
| board-merge gate | pass |
| Gate 47 (canonical pointers) | pass, plus self-test |
| Gate 113 / 141 / 116 | pass (constitution PR) |

Same failures as origin/main (Windows-only): Gate 96 (3 file-staging cases under `/tmp`), Gate 93 self-test (1), `verify-auto-release-gate-waits-for-stage.py` (5), `verify-clarification-gating.py` (symlink privilege). On this tree, Gate 96's count assertions pass and its re-added author-clause mutation is caught.

### Rebase and renumber (2026-11-24, before review pass 1)

- Rebased onto origin/main 08c9495e (was ec1fd4ac). One conflict: main's own Gate 172 (#1196, lint's concurrency gate) sits where this branch registered its gate; both blocks are kept.
- Renumbered this spec's gate 172 -> 174 (PR #1184 claims 171, PR #1205 claims 173) and the spec 129 -> 130 (open spec PR #1199 holds `specs/129-parallel-pr-lint`). Only this branch's lines changed. The T017 numbers below were taken before the rebase and name the gate by its old number.
- Renumbered this spec's gate 174 -> 179 at the merge of main (2026-11-26): main's Gate 174 is the sharded lint layout gate, and open PRs #1236 and #1271 claim 176 to 178. This file's other mentions of the gate now read 179.

### T017 gate comparison (2026-11-24)

- **What ran:** 150 gate scripts (210 gate labels) that read a changed file, run with `run-local-gates.py --jobs 3` on this branch and on origin/main (ec1fd4ac) in parallel.
- **Main:** 32 failures, all from this Windows machine.
- **Branch, first run:** the same 32 plus 5 of its own:
  - Gate 27 (`verify-stage-tool-lists.py` and its self-test): the specs/010 contract still listed clarify's `Bash(gh issue view:*)`. Fixed in the contract.
  - Gate 126 (`verify-gh-api-error-capture.py`): the new check step's `gh api` capture needed an explicit failure path. Fixed with `if ! info=...; then ... exit 1; fi`.
  - Gate 106 (`verify-gate-106.py` and its self-test): its preamble marker was the removed `author_id=""` line. It now names the next line, so the extracted preamble is unchanged except for the removed block.
- **After the fixes:** all five pass, and Gate 179 passes with every mutant caught. No other gate fails only on this branch.

