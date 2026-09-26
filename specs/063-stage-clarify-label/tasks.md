---

description: "Task list for feature implementation"
---

# Tasks: The Label Table Tells the Truth — `stage:clarify` Is Either Applied or Retired

**Input**: Design documents from `/specs/063-stage-clarify-label/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: spec.md requests no TDD approach; the tests present below (Gate 99's required `--self-test` fixtures, US2's harness-driven step checks) are requested directly by FR-007/FR-008/FR-015 and contracts/, not added speculatively.

**Organization**: Tasks are grouped by user story (US1, US2, US3, both P1/P2 per spec.md) plus one unlabeled Polish phase for the E2E assertion amendment (FR-005/FR-021), which spec.md does not assign to any of the three user stories.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1, US2, or US3 — omitted for Setup/Foundational/Polish tasks
- File paths are exact; line numbers are taken from research.md/data-model.md/contracts/, re-verified against this branch's HEAD in T001

## Phase 1: Setup

- [ ] T001 Re-verify, against the current HEAD of `spec/063-stage-clarify-label`, every anchor line number this plan cites before editing: `.github/workflows/intake.yml`'s `Check whether the spec still needs clarification` step (`id: clarification`, plan cites lines 990-1136) and `Render clarification questionnaire` (plan cites line 1142); `.github/workflows/clarify.yml`'s `Determine clarification follow-up outcome` step (`id: clarification`, plan cites lines 845-932) and the `wing-commander-chain-stop-notice` call's `stage-label: "stage:clarify"` input (plan cites line 1292); `.github/workflows/auto-release.yml`'s stage-label-timeline check (plan cites lines 1136-1158), `comments_json` read (plan cites line 1250), `markers_json`/`clarification_satisfied` reads (plan cites lines 1267-1275); `.github/workflows/lint-workflows.yml`'s highest existing gate number (plan cites Gate 98 at line ~4131, making 99 the next number). Note any drift found before T004 onward proceeds, since research.md records plan.md's own citations already drifted once since spec.md was drafted.

## Phase 2: Foundational

No blocking prerequisites apply: User Story 1's two workflow edits, User Story 2's validation of those edits, and User Story 3's new gate script touch disjoint files with no shared setup beyond T001's line-number check. Proceed directly to the user story phases.

---

## Phase 3: User Story 1 - The label table describes the pipeline that ships (Priority: P1) 🎯 MVP

**Goal**: Every documented lifecycle label either has a real writer or a recorded reason it doesn't. `stage:clarify` gets its writer: `intake.yml` and `clarify.yml` each gain a deterministic step, placed immediately after that stage's existing clarification-decision step, that applies `stage:clarify` while questions are open and flips it back to `stage:spec` when they're answered — reading only the same schema-validated decision output each stage's callout already reads (FR-013), never a second parse.

**Independent Test**: Read `docs/setup.md` § 4 against the shipped workflows and composite actions for every documented label; confirm each row names a real writer. Grep the shipped workflows/composites for `stage:clarify` and confirm every surviving reference (the clarify wrapper's disjunct, `plan.yml`'s two removal lines, `clarify.yml`'s `stage-label` input) now has something real to act on.

### Implementation for User Story 1

- [ ] T002 [US1] In `.github/workflows/intake.yml`, add a new step named `Flip stage label for clarification` immediately after `Check whether the spec still needs clarification` (`id: clarification`) and before `Render clarification questionnaire`, gated `if: steps.lifecycle-gate.outputs.is-open == 'true'`. Body (contracts/clarify-label-flip.md, research.md D2):
  ```bash
  if [ "$NEEDED" = "true" ]; then
    gh label create "stage:clarify" --color 1D76DB --description "Open clarification questions" --force
    if ! gh issue edit "$ISSUE" --add-label "stage:clarify"; then
      echo "::warning::wing-commander intake: could not add stage:clarify to issue #$ISSUE (the clarification questionnaire was still posted)." >> "$GITHUB_STEP_SUMMARY"
    fi
    gh issue edit "$ISSUE" --remove-label "stage:spec" 2>/dev/null || true
  elif [ "$SPECIFIED" = "true" ] && [ "$BLOCKED" != "true" ] && [ -n "$SPEC_DIR" ]; then
    gh issue edit "$ISSUE" --remove-label "stage:clarify" 2>/dev/null || true
  fi
  ```
  with env `NEEDED=steps.clarification.outputs.needed`, `SPECIFIED=steps.clarification.outputs.specified`, `BLOCKED=steps.clarification.outputs.blocked`, `SPEC_DIR=steps.created.outputs.spec-dir`, `ISSUE=inputs.issue-number`. Confirm by inspection that this step's fixed position is after the agent's own unconditional `stage:spec` add (inside the earlier agent step, line 689) and before `Label spec PR to match the issue` (FR-023's ordering — no runtime check, position only).

- [ ] T003 [US1] In `.github/workflows/clarify.yml`, add a new step named `Flip stage label for clarification` immediately after `Determine clarification follow-up outcome` (`id: clarification`), gated `if: steps.lifecycle-gate.outputs.is-open == 'true'`. Body (contracts/clarify-label-flip.md, research.md D3):
  ```bash
  case "$OUTCOME" in
    needs-clarification)
      gh label create "stage:clarify" --color 1D76DB --description "Open clarification questions" --force
      if ! gh issue edit "$ISSUE" --add-label "stage:clarify"; then
        echo "::warning::wing-commander clarify: could not add stage:clarify to issue #$ISSUE (the follow-up questionnaire was still posted)." >> "$GITHUB_STEP_SUMMARY"
      fi
      gh issue edit "$ISSUE" --remove-label "stage:spec" 2>/dev/null || true
      ;;
    ready)
      if [ "$BLOCKED" != "true" ]; then
        gh label create "stage:spec" --color 1D76DB --description "Spec drafted / awaiting review" --force
        if ! gh issue edit "$ISSUE" --add-label "stage:spec"; then
          echo "::warning::wing-commander clarify: could not add stage:spec to issue #$ISSUE (the spec PR was still announced ready)." >> "$GITHUB_STEP_SUMMARY"
        fi
        gh issue edit "$ISSUE" --remove-label "stage:clarify" 2>/dev/null || true
      fi
      ;;
    none|*)
      ;;
  esac
  ```
  with env `OUTCOME=steps.clarification.outputs.outcome`, `BLOCKED=steps.clarification.outputs.blocked`, `ISSUE=inputs.issue-number`.

- [ ] T004 [P] [US1] Correct the stale comment in `.github/scripts/verify-board-label-creation.py`-adjacent conventions is N/A here — instead, in `docs/architecture.md` (around line 372-374, the paragraph naming "the structural fix for #159"), add one clause naming the new label write as a second consumer of the same single derived output, alongside the callout (research.md D6: "Both callouts, and the stage-label write that now accompanies them, key off a single output...").

- [ ] T005 [P] [US1] In `docs/adoption.md`'s intake stage "Side effects" table row (the row reading `` `spec:NNN-slug` + `stage:spec` labels; clarification-questions or ready-for-review comment ``), append ", flipped to `stage:clarify` while clarification questions are open" so the row states the conditional outcome (research.md D6).

- [ ] T006 [P] [US1] In `docs/adoption.md`'s clarify stage "Side effects" table row (today lists no label effect), append "; `stage:clarify` applied on a follow-up question, or flipped back to `stage:spec` when the spec is ready for review" (research.md D6).

- [ ] T007 [US1] Confirm, by reading them fresh (not by assuming from spec.md's Overview table), that `docs/setup.md:146` (table row text), `docs/setup.md:175` (label-creation script), and `docs/architecture.md:355-357` (the trigger description) already read correctly under Direction A and need no edit (research.md D6) — record this confirmation rather than silently skipping, since an unnecessary edit is itself a drift risk.

**Checkpoint**: `stage:clarify` now has a real writer in both stages that can post or resolve a clarification questionnaire, and every FR-006 documentation site is consistent with that fact.

---

## Phase 4: User Story 2 - A requester's reply still reaches the clarify stage (Priority: P1)

**Goal**: Confirm the label change does not strand the one stage a human reply drives. `wing-commander-2-clarify.yml`'s trigger condition and its `docs/adoption.md:229` copy already admit `stage:clarify` (unchanged by this feature — T002/T003 make that disjunct reachable for the first time, not the condition itself); this phase proves the new flip steps behave exactly as contracted and that the reply path still works for an issue in flight at merge time.

**Independent Test**: Drive one clarification round end to end and confirm the reply-triggered clarify run starts and folds the answers, on both a fresh issue (`stage:clarify` alone) and one already carrying `stage:spec` when the change lands.

### Validation for User Story 2

- [ ] T008 [US2] Using `wc_shell_harness.py`'s `find_step`/stubbed-`gh` pattern (the same one `verify-clarification-gating.py` uses to extract and run `intake.yml`/`clarify.yml`'s named steps), drive `intake.yml`'s new `Flip stage label for clarification` step three ways and record the results for the implementation PR (quickstart.md §3.1-§3.3): (a) `NEEDED=true` — assert exactly one `gh label create stage:clarify ... --force`, one `--add-label stage:clarify`, one `--remove-label stage:spec`; (b) `NEEDED=false`, `SPECIFIED=true`, `BLOCKED=false`, `SPEC_DIR` non-empty — assert exactly one `--remove-label stage:clarify`, no `stage:clarify` add, no `stage:spec` add; (c) the stubbed `gh issue edit --add-label stage:clarify` forced to fail — assert the step itself exits 0 and `$GITHUB_STEP_SUMMARY` contains the `::warning::` line (FR-015).

- [ ] T009 [US2] Repeat T008's harness-driven approach against `clarify.yml`'s new step for its four reachable branches (quickstart.md §3.4): `OUTCOME=needs-clarification`; `OUTCOME=ready` with `BLOCKED=false`; `OUTCOME=ready` with `BLOCKED=true` (assert no label calls at all); `OUTCOME=none` (assert no label calls at all).

- [ ] T010 [US2] Run `python3 .github/scripts/verify-clarification-gating.py` (Gate 8) after T002/T003 land and confirm it neither gains nor loses a finding — it does not reference either new step's name, so its `wanted`-step extraction must be unaffected by construction (research.md D1, quickstart.md §3.5).

- [ ] T011 [US2] Compare `docs/adoption.md:229`'s wrapper condition against the shipped `wing-commander-2-clarify.yml:25` trigger condition byte-for-byte and confirm they still agree after T002/T003 (neither is touched by this feature — Acceptance Scenario 3).

- [ ] T012 [US2] After this feature merges, re-drive one full end-to-end run (`gh workflow run` on `auto-release.yml`'s dispatchable wrapper per `specs/055-unattended-e2e-gates/`) and confirm on the scratch lifecycle issue: `stage:clarify` appears in the label timeline while questions are open and is removed when they're answered, `stage:spec` is restored, and `wing-commander-2-clarify.yml`'s trigger fires on the reply while the issue carries `stage:clarify` alone (User Story 2 Acceptance Scenario 1; quickstart.md §5). Record the run link on the implementation PR or issue #483 per CLAUDE.md's "prove" step for Actions-only behavior.

**Checkpoint**: The reply-triggered clarify stage is proven to still fire correctly under the new label state, for both a fresh clarification and one already in flight at merge time (FR-004).

---

## Phase 5: User Story 3 - The rule has a home and a gate that can fail it (Priority: P2)

**Goal**: A checked-in, pull-request-time gate (Gate 99) enforces "every documented lifecycle label has a writer," derives both the documented and applied sets from the shipped repository rather than hardcoding either, and is demonstrated failing on the pre-change tree and passing on the post-change tree.

**Independent Test**: Run the gate on the pre-change tree (expect failure naming `stage:clarify`) and the post-change tree (expect pass); add a synthetic label row with no writer and confirm the gate goes red; add a synthetic exemption entry and confirm the gate passes with the reason readable next to the label.

### Implementation for User Story 3

- [ ] T013 [US3] Create `.github/scripts/verify-lifecycle-label-taxonomy.py` (Gate 99) with a documented-label-set scanner: every backtick-quoted `` `stage:[a-z-]+` `` token found anywhere in `docs/setup.md` (table rows, the label-creation script, and prose such as the "created on the fly" sentence), deduplicated, read fresh from the file on every run (data-model.md, contracts/lifecycle-label-taxonomy-gate.md).

- [ ] T014 [US3] In the same script, add an applied-label-set scanner over every `.github/workflows/*.yml` and `.github/actions/**/action.yml`: every literal `stage:[a-z-]+` token passed to `gh issue edit --add-label`/`--remove-label`, `gh issue create --label`/`-l`, or a REST `-f "labels[]=..."` call, reimplementing (not importing) Gate 90's (`verify-board-label-creation.py`) segmentation rules locally — comment stripping, `;`/`&&`/`||`/`|`/`$(` splitting, backslash-continuation joining, quote handling — and excluding a `--label`/`-l` argument to a read command (`gh issue list`, `gh search`) (research.md D7).

- [ ] T015 [US3] In the same script, add the exemption-registry loader for `.github/scripts/lifecycle-label-taxonomy-waivers.json`: fields `file`, `check` (fixed `"stage-label-writer"`), `pattern`, `count`, `issue`, `reason`; missing file → zero waivers; malformed JSON or a missing required field → hard failure naming the malformed entry (never a silent skip) — structurally identical to `stage-invariant-waivers.json`'s (Gate 31) `load_waivers()` convention.

- [ ] T016 [US3] In the same script, implement the verdict table from contracts/lifecycle-label-taxonomy-gate.md: PASS when every documented label is in the applied set or covered by a non-stale waiver; FAIL naming the label when a documented label is in neither set; FAIL (stale, either direction) when a waiver's `pattern` no longer matches or its `count` no longer matches the live documented-mention count; FAIL when a documented label has both a writer and a waiver entry. Wire a `--self-test` CLI flag alongside the default (real-tree) run mode, following this repository's `verify-*.py` convention.

- [ ] T017 [P] [US3] Implement Gate 99's seven required `--self-test` fixtures (contracts/lifecycle-label-taxonomy-gate.md): (1) a synthetic `docs/setup.md` documenting `stage:clarify` with no apply site anywhere → FAIL naming `stage:clarify` (the permanently pinned FR-008 regression fixture); (2) a documented label with a valid, exact waiver → PASS; (3) a stale waiver whose labeled deviation now has a writer → FAIL; (4) a waiver whose `count` no longer matches → FAIL; (5) a new documented label with no writer added to a synthetic `docs/setup.md` → FAIL naming the new label; (6) a workflow change that deletes the only apply site for a documented label → FAIL naming that label; (7) a malformed waivers file (missing required field) → FAIL naming the malformed entry, distinct from case 1/5.

- [ ] T018 [US3] Decide and create `.github/scripts/lifecycle-label-taxonomy-waivers.json`'s real (non-test) state: Direction A ships zero live exemptions, so this file is either left absent or created with an empty `"waivers": []` list plus a `$comment` block (matching `stage-invariant-waivers.json`'s documentation style) explaining that every documented `stage:*` label has a writer after this change.

- [ ] T019 [US3] Wire Gate 99 into `.github/workflows/lint-workflows.yml`: add a `Gate 99` `run:` step (`python3 .github/scripts/verify-lifecycle-label-taxonomy.py`) and a `Gate 99 self-test` `run:` step (`python3 .github/scripts/verify-lifecycle-label-taxonomy.py --self-test`), following the `Gate 98`/`Gate 98 self-test` two-step pattern immediately preceding them in the file (research.md D8).

- [ ] T020 [US3] Confirm `"docs/setup.md"` appears as an actual Python string literal (not only in a comment) in `verify-lifecycle-label-taxonomy.py`'s source, so Gate 10's `check_subject_triggers()` sees it, and confirm the literal is already covered by `lint-workflows.yml`'s `pull_request.paths:` filter (no filter edit expected — research.md D8).

- [ ] T021 [US3] Demonstrate FR-008/SC-002 on the implementation PR: `git stash` the `intake.yml`/`clarify.yml` changes from T002/T003, run `python3 .github/scripts/verify-lifecycle-label-taxonomy.py` and record the FAIL output naming `stage:clarify`, then `git stash pop` and re-run to record the PASS output against the real post-change tree (quickstart.md §§1-2).

- [ ] T022 [US3] Confirm `.github/scripts/run-local-gates.py` and `verify-gate-wiring.py` (Gate 10) both pick up Gate 99 automatically through `wc_gate_registry.py`'s filename-glob discovery, with no manifest edit anywhere else (FR-009, research.md D8).

**Checkpoint**: Gate 99 is demonstrated failing on the pre-change tree and passing on the post-change tree, registered in both `run-local-gates.py` and Gate 10, and its exemption mechanism is proven by fixture even though it holds zero live entries.

---

## Phase 6: Polish & Cross-Cutting Concerns — the E2E clarification-label assertion (FR-005, FR-021)

**Purpose**: FR-005 and FR-021 correct and extend `auto-release.yml`'s existing pass-path stage-label-timeline check. Neither is claimed by US1/US2/US3's acceptance scenarios in spec.md, but both are invariant/mandatory functional requirements (SC-007) that depend on T002/T003 already existing to have a real value to assert, so they run after the user-story phases.

- [ ] T023 In `.github/workflows/auto-release.yml`, replace the stale comment at the stage-label-timeline check (currently reading "stage:clarify is never applied as an issue label by any stage workflow ... requiring it here made a genuine pass impossible") with one stating the post-change, conditional truth: `stage:clarify` is applied while questions are open and cleared when they're answered, so it belongs in the timeline only on a run that actually posted a questionnaire (FR-005, research.md D5.1).

- [ ] T024 In the same script, move the existing `gh api issues/<n>/comments` read (`comments_json`) and the existing `auto-release-e2e-clarify-decision.sh markers` computation (`markers_json`) from their current position (after the existing `clarification_satisfied` check) to immediately after the `timeline`/`timeline_raw` read, before the label-timeline loop — a reordering of two existing reads, not a new `gh api` call. Leave the `author_id`/`clarification_satisfied` check at its current relative position, now consuming the already-computed `comments_json` instead of reading it a second time (research.md D5.2).

- [ ] T025 In the same script, add the `questionnaire_posted` boolean (`printf '%s' "$markers_json" | jq -e 'length > 0'`) and extend the label-timeline loop: when `questionnaire_posted=true`, add `stage:clarify` to `stages_to_check` and write "clarification-label assertion: asserting stage:clarify in the timeline (a questionnaire was posted this run)." to `$GITHUB_STEP_SUMMARY`; when `false`, leave `stages_to_check` unchanged (today's five stages) and write "clarification-label assertion: skipped -- no clarification questionnaire was posted this run." (FR-021, SC-007, contracts/e2e-clarification-label-assertion.md).

- [ ] T026 [P] Confirm Gate 66 (the two E2E gate-decision scripts' branch coverage) still passes unchanged after T023-T025 — this feature adds no new mode to `auto-release-e2e-clarify-decision.sh`, only new call sites of its existing `markers` mode (quickstart.md §4.4).

- [ ] T027 After the next full E2E run this feature's merge triggers, confirm its step summary reports "asserting stage:clarify" (not "skipped") and that `stage:clarify` is present in the scratch issue's timeline; record this on the implementation PR or issue #483 per CLAUDE.md's "prove" step for Actions-only behavior (quickstart.md §5.1 — this may be the same E2E run recorded under T012).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — T001 can start immediately.
- **Foundational (Phase 2)**: Empty — no blocking prerequisite beyond T001.
- **User Story 1 (Phase 3)**: Depends on T001. No dependency on User Story 2 or 3.
- **User Story 2 (Phase 4)**: Depends on User Story 1 (T002/T003 must exist before their behavior can be driven or their reachability confirmed).
- **User Story 3 (Phase 5)**: T013-T017 (the gate script and its self-test fixtures) are independent of User Story 1 and can start as soon as T001 completes. T021 (the live pre/post-change demonstration) additionally depends on T002/T003 (User Story 1) to produce a real post-change PASS.
- **Polish (Phase 6)**: Depends on User Story 1 (T002/T003) for `stage:clarify` to have a real timeline entry to assert.

### Within Each Phase

- T002 and T003 touch different files and can run in parallel with each other; T004-T006 (documentation) can all run in parallel with each other and with T002/T003.
- T008 and T009 depend on T002 and T003 respectively having landed.
- T013-T016 are sequential edits to the same new file; T017's fixtures depend on T013-T016 existing to test against; T018-T020 depend on T013-T017; T021 depends on T018-T020 and on T002/T003.
- T023, T024, and T025 are sequential edits to the same script region in `auto-release.yml`.

### Parallel Opportunities

- All Setup tasks marked [P] (none beyond T001 itself).
- T004, T005, T006 (documentation edits, User Story 1) in parallel with each other and with T002/T003.
- T017 (self-test fixtures) in parallel with other US3 work once T013-T016 land.
- T026 in parallel with T027 (Polish phase).

---

## Parallel Example: User Story 1

```bash
# Launch the two workflow edits and the three documentation edits together:
Task: "Add Flip stage label for clarification step to intake.yml (T002)"
Task: "Add Flip stage label for clarification step to clarify.yml (T003)"
Task: "Add architecture.md clause naming the label write as a second consumer (T004)"
Task: "Extend adoption.md's intake Side effects row (T005)"
Task: "Extend adoption.md's clarify Side effects row (T006)"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 — both Priority P1)

1. Complete Phase 1: Setup (T001).
2. Complete Phase 3: User Story 1 — the two new flip steps and the documentation corrections. This alone closes FR-001/FR-002/FR-006 and makes `stage:clarify` a real, written label.
3. Complete Phase 4: User Story 2 — prove the reply-triggered clarify stage still fires under the new label state, including for an issue already mid-clarification at merge time (FR-004).
4. **STOP and VALIDATE**: both P1 stories are the minimum defensible fix — the label has a writer (US1) and the one human-reply-driven stage the change touches is proven unbroken (US2).

### Incremental Delivery

1. Setup → User Story 1 (label has a writer) → User Story 2 (reply path proven) → **MVP reached**.
2. Add User Story 3 (Gate 99) → the rule that "every documented label has a writer" is now enforced going forward, not just true today.
3. Add the Polish phase (T023-T027) → the E2E harness's own clarification gate stops reporting zero assertions and the stale comment recording the pre-change regression is corrected.

### Parallel Team Strategy

With two developers (this repository's own concurrency guidance caps concurrent local agents at two):

1. Developer A: User Story 1 (T002-T007), then Polish (T023-T027) once T002/T003 land.
1. Developer B: User Story 3's gate script (T013-T020), independent of User Story 1's edits until T021's live demonstration.
2. Either developer picks up User Story 2 (T008-T012) once User Story 1 lands.
