# Tasks: Review Loops That Notice They Aren't Converging, and an Analyze Check Before Folded Review Tasks Reach Implement

**Input**: Design documents from `specs/116-review-convergence-analyze/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/convergence-signals.md, contracts/fold-analyze.md, quickstart.md

**Tests**: Required. Constitution VIII and FR-019/SC-007 demand a checked-in fixture for every gate failure branch; SC-001..SC-004 demand replay fixtures.

**Organization**: Grouped by user story. US5 is out of scope (FR-020) and has no tasks.

## Format: `[ID] [P?] [Story] Description`

## Path Conventions

Repository is CI/CD tooling: scripts in `.github/scripts/`, composites in `.github/actions/`, workflows in `.github/workflows/`. Before pushing: `python .github/scripts/run-local-gates.py`. Workflow comments are load-bearing; re-run the gate suite after any comment edit. Do not edit `.claude/skills/speckit-*`. Never reference private downstream consumers.

---

## Phase 1: Setup

- [X] T001 Read `.claude/skills/review-until-clean/scripts/thrash_signals.py`, `.github/scripts/verify-metrics-summary-record-emission.py`, `.github/actions/wing-commander-fold-commit/action.yml`, `.github/actions/wing-commander-fold-dispatch/action.yml` and the gate registry used by `.github/scripts/run-local-gates.py`, and note the conventions to follow (no file changes)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared module that Stories 1, 2 and 4 all call.

- [X] T002 Create `.github/scripts/wc_convergence.py` by moving the attribution (`Origins`/`blame_commits`), churn and growth arithmetic from `.claude/skills/review-until-clean/scripts/thrash_signals.py`; expose `measure(base, heads, findings, cwd)` and `validate_line(path, line, head, cwd)` per contracts/convergence-signals.md; `validate_line` returns true only when `1 <= line <= lines(file@head)`; classify merges from the freshly fetched base as `main`, not loop-written (research D2)
- [X] T003 Add to `.github/scripts/wc_convergence.py` the single `THRESHOLDS = {min_round: 3, self_inflicted_share: 0.5, consecutive_churn_rounds: 2, growth_ratio: 0.5}` table, `classify_recurrence(findings, ledger)` (dismissed fingerprints never match), `decide(history, thresholds=THRESHOLDS)` returning `{signals, tripped, stop, reason}` (tripped ⊆ {count-not-falling, self-inflicted, recurrence, churn-streak, growth}; empty before round 3; round 1 signals zero; unattributable findings excluded from share numerator and denominator), `render_handoff(decision)` producing the comment with marker `<!-- wing-commander-not-converging: round=N -->`, per-round table, unattributable count and open findings, and the CLI `decide --history <json> --base <ref> [--json]`
- [X] T004 [P] Create unit tests in `.github/scripts/wc_convergence_tests/` covering each FR-006 rule, round-2 record-only, round-1 zeros, unattributable and invalid-line handling, main-merge exclusion, zero-findings round, dismissed-list non-recurrence, and port the `--self-test` cases of `thrash_signals.py`
- [X] T005 Make `.claude/skills/review-until-clean/scripts/thrash_signals.py` a thin caller of `wc_convergence` that keeps its flags and `--self-test`; update `.claude/skills/review-until-clean/SKILL.md` to point at the shared module (if the stage is denied writes under `.claude/`, flag this task for a human maintainer per research D10 rather than working around it)

**Checkpoint**: One module answers all arithmetic; stories can start.

---

## Phase 3: User Story 1 - A recurring finding is never reported as a clean round (P1) 🎯 MVP

**Goal**: A finding re-raised after being folded or fixed is classified `recurrence`, keeps the round non-clean, and is named.

**Independent Test**: Replay #833's case: a round whose only finding matches an earlier folded fingerprint is not `clean`, posts no `success`, and names the recurrence.

- [X] T006 [P] [US1] Add replay fixture for #833 (round 2 folds F, round 3 raises only F) plus a fresh-only-findings fixture under `.github/scripts/wc_convergence_tests/fixtures/` and tests asserting SC-001 and acceptance scenario 2 (unchanged behaviour)
- [X] T007 [US1] In `.github/workflows/lifecycle-review-gate.yml` extend the `disposition` partition step to call `wc_convergence.classify_recurrence` against the persisted `folded_fingerprints` ledger instead of dropping matches; a round with a recurrence does not resolve `clean`, posts no `success` status, keeps the finding open (re-fold or carry) and names it on the lifecycle issue; persist the resolved-finding ledger additively in the round marker (data-model.md)
- [X] T008 [US1] In `.github/workflows/board-loop.yml` record fixed-finding fingerprints in the PR round marker and classify recurrences the same way, naming them on the PR and not resolving the round clean
- [X] T009 [US1] Update any existing `verify-*.py` gate or fixture that byte-compares the changed workflow regions, and run `python .github/scripts/run-local-gates.py`

**Checkpoint**: False green removed (MVP).

---

## Phase 4: User Story 2 - Loops stop early when they stop converging (P1)

**Goal**: Both loops compute signals each round and, from round 3, stop with `not-converging` and the standard hand-off.

**Independent Test**: Replay #954 and #969 histories: each stops at or before round 3; each FR-006 rule trips on its own fixture.

- [X] T010 [P] [US2] Add replay fixtures from the #954 and #969 round histories and per-rule trip fixtures in `.github/scripts/wc_convergence_tests/fixtures/`, with tests for SC-002 and acceptance scenarios 1–8 (including budget and not-converging on round 5 naming the budget and still listing signals)
- [X] T011 [P] [US2] Add optional `line` (integer ≥ 1, not part of the fingerprint) to the reviewer finding schemas of both loops in `.github/workflows/lifecycle-review-gate.yml` and `.github/workflows/board-loop.yml`; where a schema sits in a published composite, keep it optional
- [X] T012 [US2] In `.github/workflows/lifecycle-review-gate.yml` persist each round's record (head SHA, finding fingerprint/file/line/attributable, count) in the round marker, call `wc_convergence decide`, and on `stop` take the existing budget-exhaustion hand-off with stall reason `not-converging` and `render_handoff` output; PR left open and unmerged; budget (`LIFECYCLE_REVIEW_ROUND_BUDGET`) unchanged and still wins
- [X] T013 [US2] Do the same in `.github/workflows/board-loop.yml` for review rounds (fixup commits as the loop's own commits, `BOARD_LOOP_ROUND_BUDGET` unchanged)
- [X] T014 [US2] Ensure the `not-converging` stall reason is accepted wherever stall reasons are enumerated (labels, re-eligibility rule, watchdog/board-status parsing, existing gates) by grepping `.github/` for the existing budget stall reason and extending each site
- [X] T015 [US2] Run `python .github/scripts/run-local-gates.py`; apply `review-step-gating` skill to the changed `if:` conditions

**Checkpoint**: Both loops stop early; US1 + US2 deliver the observed-failure fixes.

---

## Phase 5: User Story 4 - One home for the convergence arithmetic (P2)

**Goal**: A second copy of the arithmetic fails a gate.

**Independent Test**: Skill and loops give identical signals on one history; reintroducing a copy fails the gate.

- [X] T016 [P] [US4] Create `.github/scripts/verify-convergence-single-home.py` that fails when blame/churn/diff-size arithmetic or the threshold literals appear in a workflow, composite or skill outside `wc_convergence.py` (and the allowed thin callers), in the manner of `verify-metrics-summary-record-emission.py`
- [X] T017 [P] [US4] Add checked-in fixtures for every failure branch of the gate (copied arithmetic in a workflow, in a composite, in a skill script, a duplicate threshold literal) and a passing fixture in a `verify-convergence-single-home-fixtures/` directory beside the gate, following existing fixture layout
- [X] T018 [US4] Add a parity test in `.github/scripts/wc_convergence_tests/` asserting the skill's `thrash_signals.py` and the module's CLI emit identical signals on the same history (SC-003)
- [X] T019 [US4] Register the gate in the gate registry and in `.github/workflows/lint-workflows.yml` so `run-local-gates.py` runs it; run the full suite

---

## Phase 6: User Story 3 - A folded task that contradicts the spec reaches the owner before implement (P2)

**Goal**: Analyze runs between fold-commit and fold-dispatch on both paths; only a constitution conflict or a failed check holds.

**Independent Test**: Constitution-conflicting fold task is held with a question naming task and principle; FR-contradicting task without a constitution conflict is dispatched with the report linked.

- [X] T020 [P] [US3] Create the deterministic decision script (in `.github/actions/wing-commander-fold-analyze/` or `.github/actions/_shared/` if reused) that validates the agent JSON schema `{"findings":[{severity,category,fold_task,location,principle,detail}]}`, decides `hold` iff any finding has `category == constitution-conflict` or the step failed/mismatched schema, else `dispatch`, and renders `report-markdown` and `question-markdown` (names the task and, for constitution conflicts, the principle; options: amend the spec / drop the fold task / proceed anyway, or proceed anyway / retry the check for `analyze-failed`)
- [X] T021 [P] [US3] Add fixture tests beside the composite in the style of `wing-commander-fold-queue-*-tests/run-tests.sh`: constitution conflict → hold (SC-004), FR contradiction only → dispatch with report (SC-005), inconsistency/duplication → dispatch, no findings → dispatch, malformed JSON → hold analyze-failed, empty fold section → skipped
- [X] T022 [US3] Create `.github/actions/wing-commander-fold-analyze/action.yml` per contracts/fold-analyze.md: inputs spec-dir, fold-ref-before, fold-ref-after, folded-json, credentials, optional max-turns (bounded default 12); skip when fold section has no tasks; run `anthropics/claude-code-action` with model `claude-sonnet-5-5`, `--max-turns`, tools restricted to Read/Grep/Glob, prompt invoking `/speckit-analyze` scoped to the new fold section with spec text framed as data; outputs decision, hold-reason, report-markdown, question-markdown; any `run:` step sets `shell: bash` (apply `container-shell-safety`)
- [X] T023 [US3] Add optional additive outputs to `.github/actions/wing-commander-fold-commit/action.yml` (fold-section range / before and after refs) needed by the analyze composite; no rename or removal
- [X] T024 [US3] Wire the composite between `wing-commander-fold-commit` and `wing-commander-fold-dispatch` in `.github/workflows/lifecycle-review-gate.yml` (`disposition`) and `.github/workflows/pr-conversation.yml` (`act` path); call `fold-dispatch` only when `decision != hold`; link the report on the lifecycle issue when dispatching; on hold post the question with marker `<!-- wing-commander-fold-hold: fold=<id> -->` on the lifecycle issue
- [X] T025 [US3] Implement hold release: a maintainer-authorized answer comment (reuse pr-conversation's existing authorization) handled as *proceed* → dispatch, *drop* → deterministic commit removing the fold section's tasks then dispatch, *amend* → wait for the spec amendment then dispatch on next lifecycle trigger, *retry* → rerun the check; place the handler in `.github/workflows/pr-conversation.yml` or a small dedicated wrapper job (research D9)
- [X] T026 [P] [US3] Create `.github/scripts/verify-fold-analyze-wiring.py` asserting the composite sits between fold-commit and fold-dispatch in both callers, declares model `claude-sonnet-5-5`, a `--max-turns`, a read-only tool list, and `shell: bash` in container jobs; add a checked-in fixture per failure branch
- [X] T027 [US3] Register `verify-fold-analyze-wiring.py` in the gate registry and `.github/workflows/lint-workflows.yml`; update existing `verify-fold-*.py` gates and fixtures for the new step; run `python .github/scripts/run-local-gates.py`

---

## Phase 7: Polish & Cross-Cutting

- [X] T028 [P] Run the scenarios in `specs/116-review-convergence-analyze/quickstart.md` and record any divergence
- [X] T029 [P] Update live docs that describe the loops' stop reasons or the fold flow (grep `docs/` and README for "round budget" and "fold-dispatch")
- [X] T030 Final pass: `python .github/scripts/run-local-gates.py`; apply `review-step-gating` and `container-shell-safety` skills to workflow/composite changes

---

## Dependencies & Execution Order

- Phase 2 blocks all stories (T002 → T003 → T004/T005).
- US1 (Phase 3) needs T003. US2 needs T003 and shares the two workflows with US1, so do US1 first (T007/T008 before T012/T013).
- US4 needs T002–T005; independent of US1/US2 otherwise.
- US3 needs only Setup; it touches `lifecycle-review-gate.yml` and `pr-conversation.yml`, so sequence T024 after T012 to avoid conflicts.
- Polish last.

## Parallel Opportunities

- T004 with T005; T006 with T010 with T011; T016 with T017; T020, T021, T026 are independent files.
- US3 can proceed in parallel with US1/US2 apart from the shared-workflow tasks.

## Implementation Strategy

- **MVP**: Phase 1 + 2 + US1 (T001–T009): removes the false green.
- Next: US2 (observed thrash), then US4 (gate), then US3 (analyze).
- Out of scope: US5 / part 3 (FR-020).

## Review Gate Round 1 Findings

- [X] Review finding: Re-fold of an unimplemented fold counts as recurrence

  A finding folded earlier is re-folded and counted as a recurrence even when its fold was held, blocked or dropped, so the loop can stop as not-converging against a stalled pipeline.

  - .github/workflows/lifecycle-review-gate.yml

  Detail: The partition step no longer skips in-scope findings whose fingerprint is in folded_fps. If the fold is held or dropped and the next round re-raises the finding, the recurrence and count-not-falling rules trip.

- [X] Review finding: Fixed WC_EOF heredoc delimiter allows output injection

  _write_outputs frames multi-line values with a fixed WC_EOF delimiter and no escaping, so a value from an issue comment marker can inject extra step outputs.

  - .github/scripts/wc_fold_hold.py

  Detail: State fields such as folded_json, spec_dir and spec_branch come from an issue comment marker. A newline followed by WC_EOF closes the heredoc early and the rest parses as new outputs such as action=proceed. Use a random delimiter.

- [X] Review finding: Open hold with empty fold_id is invisible

  An open hold whose state has an empty or missing fold_id renders as an empty string, the joined list collapses to none, and dispatch proceeds past an open hold.

  - .github/actions/wing-commander-fold-open-holds/action.yml
  - .github/scripts/wc_fold_hold.py

  Detail: other_open_holds returns h.get('fold_id') or ''. The composite then writes open-holds=none, and decide.py sees no open holds. Ids joined with ',' also cannot carry a comma.

- [X] Review finding: Stage mode omits project, so analyze reads wrong paths

  The stage mode is called without project, so for a project lifecycle the analyze instructions point at root-level skill and constitution paths and the read-only agent finds nothing.

  - .github/workflows/lifecycle-review-gate.yml
  - .github/workflows/wing-commander-fold-hold.yml

  Detail: With the prefix empty, the agent looks for .claude/skills/... and .specify/memory/constitution.md at the repository root. It returns no constitution-conflict findings, so a conflicting fold dispatches instead of holding. The retry stage in wing-commander-fold-hold.yml has the same omission. The pr-conversation caller does pass project.

- [X] Review finding: fold-decide can be dropped by concurrency queueing

  fold-decide joins the per-spec concurrency group with cancel-in-progress false, but GitHub still cancels an older pending run when newer ones queue, so a committed fold may never be dispatched.

  - .github/workflows/lifecycle-review-gate.yml

  Detail: If two or more runs queue behind a running job, the oldest pending fold-decide is cancelled. The report job then only says the fold-decide job did not complete.

- [X] Review finding: Malformed round record crashes compute_history

  read_round_records checks only that findings is a list, not that its entries are dicts, and it accepts a bool as round, so a malformed record makes evaluate raise.

  - .github/scripts/wc_convergence.py

  Detail: A record like {"round": true, "findings": ["a"]} passes validation, then compute_history calls f.get on a string. The same bad record is re-read every run, so the loop is stuck until the review is removed.

- [X] Review finding: Invalid optional line drops the whole finding

  The schema rejects the finding outright when the optional line is 0, negative or non-integer, so a real in-scope finding is lost and the round is marked not clean.

  - .github/schemas/board-review-finding.schema.json

  Detail: The fixtures valid-line-zero-dropped.json and valid-line-not-integer-dropped.json lock this in. validate_line already treats a bad line as unattributable, so the finding could be kept with line set to null.

- [X] Review finding: Empty array expansion under set -u on old bash

  "${failed[@]}" on an empty array under set -u is an unbound-variable error on bash older than 4.4, and decide mode runs in a caller-supplied container.

  - .github/actions/wing-commander-fold-analyze/action.yml

  Detail: On an image with bash 4.2 or 4.3, failed=() is empty when the agent succeeded, and the decide step aborts. Use ${failed[@]+"${failed[@]}"} or a string flag.

- [X] Review finding: Recurrence baseline assumes the first record is round 1

  Growth, churn and share are computed from the earliest loaded record even when it is not round 1, so rule evaluation depends on which reviews survive.

  - .github/scripts/wc_convergence.py

  Detail: If the first record is round 3, first_size comes from round 3's head and growth reads 0.0. growth and churn-streak underreport, and no missing-rounds warning is surfaced.

- [X] Review finding: Tick-pairing logic duplicated with cross-directory import

  _ticks in wc_fold_hold.py re-implements the git diff -U0 hunk parsing that decide.fold_section already does, and the module imports the generic name decide from an actions directory via sys.path.

  - .github/scripts/wc_fold_hold.py

  Detail: A fix to one parser will not reach the other. This conflicts with the repo rule that shared logic has one home, and the generic module name risks a collision.

## Review Gate Round 2 Findings

- [X] Review finding: Current round findings omit pending re-raised findings that earlier rounds include

  In lifecycle-review-gate.yml the current round's findings drop re-raised findings still pending in tasks.md (pending_fps), while earlier rounds' records include them, so the count-not-falling signal can fail to trip and the loop can run past non-convergence.

  - .github/workflows/lifecycle-review-gate.yml

  Detail: Around line 1245: current['findings'] excludes pending_fps, but the comment claims it matches earlier records.

- [ ] Review finding: thrash_signals --history cannot supply a ledger so recurrence is always empty

  thrash_signals.py --history calls compute_history with a None ledger and has no --ledger flag, so the skill's view reports 'converging' on histories where the loop trips recurrence, defeating the single-home comparison (SC-003).

  - .claude/skills/review-until-clean/scripts/thrash_signals.py

  Detail: Around line 262.

- [X] Review finding: Churn-streak rule cannot trip at min_round 3

  Round 2 churn is always 0 because no commit in H0..H1 can carry a passN label, so the two-consecutive-round churn streak effectively starts at round 4, not round 3 as the thresholds imply.

  - .github/scripts/wc_convergence.py

  Detail: Around line 375.

- [X] Review finding: Hold resolution uses >= on one-second timestamps

  A resolved marker and a newer state marker for the same fold id in the same second make the new hold read as already resolved, so open-holds reports none and a fold dispatches past a real hold.

  - .github/scripts/wc_fold_hold.py

  Detail: Around line 115: r_stamp >= stamp; order by comment id or use a strict compare with a tiebreak.

- [X] Review finding: other_open_holds drops holds with an empty fold_id when except id is empty

  With the default empty except-fold-id, a state marker with an empty fold_id is filtered as the caller's own hold, so open-holds returns none and a dispatch goes past an unanswered hold.

  - .github/scripts/wc_fold_hold.py

  Detail: Around line 132.

- [X] Review finding: drop_tasks restores ticks on the first matching line, not the original position

  When tasks.md has identical task lines in different sections, restoring a tick replaces the first equal line anywhere in the file, so the wrong task is re-ticked and work is redone or skipped.

  - .github/scripts/wc_fold_hold.py

  Detail: Around line 259.

- [X] Review finding: inert() escapes only angle brackets so agent text keeps live mentions and commands

  Agent-written detail posted under the App identity can still ping teams via @mentions and include /fold-hold lines, which makes the owner question hard to tell from the real instruction line.

  - .github/actions/wing-commander-fold-analyze/decide.py

  Detail: Around line 116; ANSWER_RE is line-anchored but quoted detail is not neutralised.

- [X] Review finding: compute_history spawns many redundant git subprocesses per round

  git show, git blame and diff_size run per finding and per round and are recomputed on every evaluate, including diff_size(base, heads[0]) for i=0, adding latency; caching per (head, path) would cut it.

  - .github/scripts/wc_convergence.py

  Detail: Around line 300; roughly 250 show and 250 blame calls at 50 findings over 5 rounds.

## Review Gate Round 3 Findings

- [X] Review finding: compute_history lets a git merge-base failure abort the whole evaluation

  diff_size() runs outside a try, so a missing merge-base (shallow fetch or unrelated history) raises SystemExit instead of degrading to git_ok=False.

  - .github/scripts/wc_convergence.py

  Detail: _resolve_heads only checks that head_sha resolves; merge-base failure kills the partition and board-loop convergence steps every run.

- [X] Review finding: fold-analyze block() turns a skipped decision into an analyze-failed hold

  When the open-holds read is empty, block(result, None) re-decides a tasks==0 'skipped' fold as a hold and asks the owner a spurious question.

  - .github/actions/wing-commander-fold-analyze/decide.py

  Detail: The guard should leave 'skipped' untouched.

  Reverted in review-until-clean pass 6: already refuted in passes 2–4 (an unread open-holds list holds a `skipped` fold too, since nothing vouches no hold is open); the change broke test_decide_step_holds_when_the_open_holds_were_never_read.

- [X] Review finding: Pending-fold check silently ignores a missing tasks.md

  The pending-title check swallows OSError on a relative SPEC_DIR/tasks.md, so re-raised findings with a pending fold are counted as recurrences and can falsely stop the loop as not-converging.

  - .github/workflows/lifecycle-review-gate.yml

  Reverted to fail closed in review-until-clean pass 6: reading every folded finding as pending let #833's recurrence resolve clean (FR-003, SC-001); the unreadable file now only warns.

- [ ] Review finding: Fold-hold release blocked by another hold can strand the earlier fold

  A proceed/drop answered for a newer hold B while older hold A is open is recorded as resolved but dispatches nothing. If A is later dropped or amended, B's fold has no dispatch path.

  - .github/workflows/wing-commander-fold-hold.yml

- [ ] Review finding: Empty fold id or ref is reported as tasks=0 and dispatched unchecked

  The analyze stage outputs tasks=0 when fold_id or the BEFORE/AFTER refs are empty, so fold-decide returns 'skipped' and dispatches implement with no analysis, contradicting the failed-check-holds rule.

  - .github/workflows/pr-conversation.yml
  - .github/actions/wing-commander-fold-analyze/action.yml

- [ ] Review finding: Inconsistent project-prefix handling for SPEC_DIR in fold-analyze instructions

  Skill and constitution paths get the project prefix but $SPEC_DIR and the git diff pathspec do not. In a project-scoped lifecycle the diff can come back empty and the fold is skipped.

  - .github/actions/wing-commander-fold-analyze/action.yml

- [ ] Review finding: fold-analyze job body is pasted into three workflows

  About 90 lines of run/agent steps are duplicated across lifecycle-review-gate, wing-commander-fold-hold and pr-conversation, against the CLAUDE.md 'one home' rule.

  - .github/workflows/lifecycle-review-gate.yml
  - .github/workflows/wing-commander-fold-hold.yml
  - .github/workflows/pr-conversation.yml

- [ ] Review finding: thrash_signals reports 'none tripped' when self-inflicted share was never evaluated

  history_from_report gives only the latest round a self-inflicted share. With no --finding at the right head the share is None and the output reads as converging.

  - .claude/skills/review-until-clean/scripts/thrash_signals.py

- [X] Review finding: count-not-falling trips on 0>=0 and on non-adjacent rounds

  latest.count >= prev.count treats two zero-finding rounds as not falling, and compares against history[-2] even when a round record is missing.

  - .github/scripts/wc_convergence.py

  Detail: Require adjacency (prev.round == latest.round-1) and a non-zero count.
