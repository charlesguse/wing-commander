---

description: "Task list for Structured Clarification Questionnaires With a Single Content-and-Decision Artifact"
---

# Tasks: Structured Clarification Questionnaires With a Single Content-and-Decision Artifact

**Input**: Design documents from `/specs/032-structured-clarification-gate/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/clarification-schema.md, contracts/decision-points.md, contracts/watchdog-sentinel.md, quickstart.md

**Tests**: Not requested — this repo has no automated test suite for workflow YAML (plan.md's Testing note; consistent with specs 014/016/017/018/019). Validation is `quickstart.md`'s ten scenarios plus `actionlint`, folded into the checkpoints and Polish phase below.

**Organization**: `intake.yml` and `clarify.yml` each have exactly one agent step and one deterministic decision step that today drive BOTH the historical #109 failure (User Story 1) and the #159 failure (User Story 2) through the same three-line grep — there is no way to split "post the authored content" from "let the structured output, not the grep, pick the branch" into two separately-shippable code changes, because both are fixed by the same replacement of that one decision step. **User Story 1 (P1)** therefore delivers the full `--json-schema` + render + structured-decision + validation-failure rewrite of both files' agent and decision steps — this is what makes #109 (dropped questionnaire) structurally impossible and is independently testable per its own Independent Test. Because `clarify.yml`'s schema requires the `answered` discriminator from the moment it exists at all (a schema without it cannot express `none`, which is a MUST per FR-009), User Story 1's `clarify.yml` task already builds the *complete* `none`/`ready`/`needs-clarification` mapping — **User Story 4 (P2)**'s task is therefore verification-only, proving the mapping User Story 1 built satisfies FR-009's three-way split, not new code. **User Story 2 (P1)** is, likewise, already true by construction the moment User Story 1's decision step stops reading the grep at all (the marker literally cannot suppress a branch it is never consulted for) — its task is the #159 regression proof plus an explicit audit of the non-suppression guarantee (FR-011), not new code. **User Story 3 (P2)** is where the actual new code beyond User Story 1 lives: retaining the marker grep (tightened to the colon form, FR-008) as a read-only comparison appended to the same decision step, writing the `clarification-mismatch` step-summary line on disagreement, and the one-token watchdog sentinel addition.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Setup and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature (targeted edits to three existing reusable workflow files, per plan.md's Scale/Scope: "3 files touched... 0 new composite actions"), no `src/`/`tests/` split. All file paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Confirm the exact current step names, `id`s, and line numbers `contracts/decision-points.md` and `contracts/watchdog-sentinel.md` reference are still accurate, since `research.md`'s audit was captured during planning and the three workflow files may have shifted since.

- [X] T001 Re-read `.github/workflows/intake.yml` ("Create spec from issue" `id: agent`, "Check whether the spec still needs clarification" `id: clarification`, "Announce clarification needed", "Announce spec PR ready for review", "Fail on agent API error"), `.github/workflows/clarify.yml` ("Fold answers into the draft spec" `id: agent`, "Determine clarification follow-up outcome" `id: clarification`, "Announce remaining clarification questions", "Announce spec PR ready for review", "Fail on agent API error"), and `.github/workflows/watchdog.yml` ("Collect: step summaries" `id: collect-step-summary`, its `sentinels=` line). Confirm every step name, `id`, and the grep pattern (`\[NEEDS CLARIFICATION` bare-token, no trailing `\]`, per `research.md`'s current-state audit) still match `contracts/decision-points.md` and `contracts/watchdog-sentinel.md`. If anything has moved or been renamed, update the working inventory before T002 begins — every task below assumes this list is exhaustive and current. **Headless status:** confirmed by direct read of all three files — every step name/id and the bare-token grep pattern (line 611 of intake.yml, line 431 of clarify.yml pre-edit; sentinels line 618 of watchdog.yml) matched the contracts exactly; no drift found.

**Checkpoint**: The step-level inventory is confirmed current — editing can proceed without re-deriving it mid-task.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: N/A for this feature. `research.md`'s "Rendering is a deterministic bash+jq step, not a new composite action" decision rules out any new shared file, script, or composite action — every task below is a targeted edit inside one of the three files Setup just confirmed, so there is no separate blocking prerequisite beyond Phase 1's confirmation.

**Checkpoint**: No foundational tasks — proceed directly to User Story 1.

---

## Phase 3: User Story 1 - An authored questionnaire is always posted or visibly failed, never silently dropped (Priority: P1) 🎯 MVP

**Goal**: Both stages' agent steps emit a schema-validated `clarifications` array instead of freeform prose; a new deterministic step renders the unchanged `## Question N` markdown from that same array and feeds the unchanged callout steps; a missing/malformed structured result fails the run loudly instead of posting nothing.

**Independent Test**: Run a stage on an issue the agent will find genuinely ambiguous so it authors questions. Confirm the authored questions appear verbatim in the posted action callout. Then force the questionnaire artifact to be malformed and confirm the run surfaces a validation failure rather than posting nothing and reporting success.

### Implementation for User Story 1

- [X] T002 [P] [US1] In `.github/workflows/intake.yml`: (1) add `--json-schema '{"type":"object","properties":{"clarifications":{"type":"array","items":{"type":"object","properties":{"question":{"type":"string"},"context":{"type":["string","null"]},"options":{"type":"array","items":{"type":"object","properties":{"answer":{"type":"string"},"implications":{"type":["string","null"]}},"required":["answer"]}}},"required":["question"]}}},"required":["clarifications"]}'` to "Create spec from issue"'s `claude_args:` block (single-quoted, matching the `diagnose` precedent's quoting — `contracts/clarification-schema.md`); (2) replace step 7's "If spec.md still contains [NEEDS CLARIFICATION] markers: write each question... to `${{ runner.temp }}/intake-clarification.md`... Otherwise: write nothing" instruction with the intake agent-facing framing verbatim from `contracts/clarification-schema.md`'s "Agent-facing framing" section (return the `clarifications` array per the schema; empty array means no open questions; do not write a file); (3) add a new step "Render clarification questionnaire" immediately after "Check whether the spec still needs clarification" (created in this same task, see next point) and before "Announce clarification needed", gated `if: steps.lifecycle-gate.outputs.is-open == 'true' && steps.clarification.outputs.needed == 'true'`, implementing `contracts/clarification-schema.md`'s render algorithm in `bash`/`jq` to write `${{ runner.temp }}/intake-clarification.md` from the read-back `clarifications` array (one `## Question N` block per item, 1-indexed, options lettered A/B/C..., `Custom` row always last, `**Context**:` line omitted when context is null/absent, `implications` absent renders `—`); (4) rewrite "Check whether the spec still needs clarification" (`id: clarification`) to read back `${{ runner.temp }}/claude-execution-output.json` using `contracts/clarification-schema.md`'s extraction idiom (`agent_ok`/`raw` via `jq`, object-unwrapped to a `clarifications` array degrading non-conforming shapes to `[]` only after the validation-failure check in the next point has passed), and set `needed=true`/`needed=false` from that array's non-emptiness alone — delete the `grep -q '\[NEEDS CLARIFICATION'` line entirely from this step (the colon-form cross-check is reintroduced, appended to this same step, by T005); (5) extend "Fail on agent API error" (or add a new step immediately after it, before "Check whether the spec still needs clarification" runs) to also fail (`::error::` + `exit 1`) when `steps.agent.outcome == 'success'` but the terminal result's `agent_ok` check from point (4) is not `true` (missing file, missing terminal `result`, non-`success` subtype, or a `clarifications` key that fails to parse as an array) — this is FR-002, and it must run before the "Check whether..." step's `needed` computation depends on a coerced-empty array. Leave "Announce clarification needed" and "Announce spec PR ready for review" untouched (their `if:` conditions already key off `steps.clarification.outputs.needed`, unchanged). **Headless status:** implemented as specified — schema added to `claude_args:`, step 7's instruction replaced with the schema-return framing, "Render clarification questionnaire" added between the decision step and "Announce clarification needed", the decision step now reads back and counts the structured `clarifications` array only (no grep), and "Fail on agent API error" was relocated to immediately after the agent step and extended to check `agent_ok` plus the `clarifications` array shape. `actionlint` run against the finished file surfaced only pre-existing findings (`job_workflow_sha`, `deployment` key, `ls` SC2012) not introduced by this change.
- [X] T003 [P] [US1] In `.github/workflows/clarify.yml`: (1) add `--json-schema '{"type":"object","properties":{"answered":{"type":"boolean"},"clarifications":{"type":"array","items":{"type":"object","properties":{"question":{"type":"string"},"context":{"type":["string","null"]},"options":{"type":"array","items":{"type":"object","properties":{"answer":{"type":"string"},"implications":{"type":["string","null"]}},"required":["answer"]}}},"required":["question"]}}},"required":["answered","clarifications"]}'` to "Fold answers into the draft spec"'s `claude_args:` block; (2) replace step 6's "Write to `${{ runner.temp }}/clarify-followup.md`: which questions were resolved... if markers remain: restate ONLY the still-open questions" instruction with the clarify agent-facing framing verbatim from `contracts/clarification-schema.md`'s "Agent-facing framing" section (`answered: true`/`false` per whether step 2's early-STOP path was taken, `clarifications` empty when `answered` is `false`, otherwise the still-open questions after folding in the reply; do not write a file) — leave step 2's early-STOP `gh issue comment` behavior itself untouched (FR-014); (3) add a new step "Render clarification questionnaire" immediately after "Determine clarification follow-up outcome" (rewritten in this same task, see next point) and before "Announce remaining clarification questions", gated `if: steps.lifecycle-gate.outputs.is-open == 'true' && steps.clarification.outputs.outcome == 'needs-clarification'`, implementing the same render algorithm as T002's intake step (`contracts/clarification-schema.md`) to write `${{ runner.temp }}/clarify-followup.md` from the read-back `clarifications` array; (4) rewrite "Determine clarification follow-up outcome" (`id: clarification`) to read back the structured result with the same idiom as T002, then map per `data-model.md`'s Clarify read-back envelope table: `answered == false` → `outcome=none` (ignore `clarifications` entirely — do not check for a followup file's existence, that check is removed); `answered == true` and `clarifications` empty → `outcome=ready`; `answered == true` and `clarifications` non-empty → `outcome=needs-clarification`. Delete the `[ ! -f "$followup" ]` and `grep -q '\[NEEDS CLARIFICATION'` lines entirely from this step (the colon-form cross-check, scoped to `answered == true` only, is reintroduced by T006); (5) change "Announce spec PR ready for review"'s `body-file:` — since there is no longer a "which questions were resolved" narrative to show on the `ready` path, remove the `body-file: ${{ runner.temp }}/clarify-followup.md` line from this step entirely (matching `intake.yml`'s equivalent spec-PR-ready callout, which has never had a `body-file:`); (6) extend "Fail on agent API error" the same way T002 does, checking the clarify schema's required keys (`answered`, `clarifications`). **Headless status:** implemented as specified — schema (with `answered`) added, step 6's instruction replaced with the schema-return framing, "Render clarification questionnaire" added between the decision step and "Announce remaining clarification questions", the decision step now maps `answered`/`clarifications` per the read-back envelope table with no grep, the `body-file:` line was removed from "Announce spec PR ready for review", and "Fail on agent API error" was relocated to immediately after the agent step and extended to check `agent_ok` plus the `answered`/`clarifications` shape. `actionlint` run against the finished file surfaced only pre-existing findings not introduced by this change.

**Checkpoint**: User Story 1 is fully functional — an authored questionnaire reaches the issue verbatim (or the run fails loudly on a malformed result) for both stages, matching `quickstart.md` Scenarios 1–3.

---

## Phase 4: User Story 2 - The party that read the document decides whether questions remain (Priority: P1)

**Goal**: Confirm the #159 failure mode (a spec whose prose names the bare marker token is misread as carrying open questions) cannot recur, and that the spec-PR-ready callout can never be suppressed by a competing clarification branch — both already true by construction once T002/T003 stop the decision steps from consulting the grep at all, but severe enough (per `spec.md`'s own framing) to warrant their own explicit proof.

**Independent Test**: Run the stage on a spec that mentions the bare `[NEEDS CLARIFICATION]` token in requirements prose but has no genuine unresolved markers, where the agent reports zero open questions. Confirm the ready-path callout (spec PR ready, with PR link) is posted and no "open questions" callout is posted.

### Implementation for User Story 2

- [X] T004 [US2] Audit `.github/workflows/intake.yml` and `.github/workflows/clarify.yml` as rewritten by T002/T003: confirm "Check whether the spec still needs clarification" / "Determine clarification follow-up outcome" contain no reference to `spec.md`'s marker text in the code path that sets `needed`/`outcome` (the only grep, if any is present yet, belongs to T005/T006's cross-check and must not feed `needed`/`outcome`), and confirm "Announce spec PR ready for review" in both files keeps its existing `if:` condition unchanged (`steps.clarification.outputs.needed == 'false'` / `steps.clarification.outputs.outcome == 'ready'`) so it can never be independently suppressed (FR-011). Then exercise `quickstart.md` Scenario 4's static form: use this feature's own `specs/032-structured-clarification-gate/spec.md` (which names `[NEEDS CLARIFICATION]` and `[NEEDS CLARIFICATION:` in prose repeatedly) as the reproduction case and confirm, by inspection of the rewritten decision steps, that a run against it with the agent reporting zero `clarifications` would compute `needed=false`/`outcome=ready` regardless of the prose mentions. Record in the PR body that the full live-run form of Scenario 4 (an actual dispatched `intake.yml`/`clarify.yml` run) should be exercised by a maintainer before merge — it requires a real issue dispatch this task cannot perform headlessly. **Headless status:** audited by inspection — as of T002/T003, neither decision step references `spec.md` at all yet (no grep is present until T005/T006, and even then FR-004 keeps it read-only); "Announce spec PR ready for review" in both files keeps its original `if:` condition, keyed off the same `needed`/`outcome` output the questionnaire branch reads, so it cannot be independently suppressed. Confirmed by inspection that a run against this feature's own `spec.md` (repeated `[NEEDS CLARIFICATION]`/`[NEEDS CLARIFICATION:` prose mentions) with the agent reporting zero `clarifications` computes `needed=false`/`outcome=ready` regardless, since the decision steps count only the structured array. This pipeline run opens no PR (it commits/pushes directly to the persistent spec branch); the live-run form of Scenario 4 against a real issue dispatch is deferred to maintainer review before merge.

**Checkpoint**: User Stories 1 AND 2 both hold — the ready path is posted correctly and is never suppressed by a competing branch, matching `quickstart.md` Scenario 4.

---

## Phase 5: User Story 3 - A content/decision disagreement is loud, not invisible (Priority: P2)

**Goal**: The marker grep is retained, tightened to the colon form, as a read-only cross-check appended to each decision step; a disagreement between it and the structured output writes a `clarification-mismatch` line to the run's step summary without ever changing which branch runs; the watchdog's sentinel set gains that token so a recurrence surfaces as a finding.

**Independent Test**: Construct a run where the marker cross-check and the structured output disagree (for example, genuine markers remain but the agent reported zero questions). Confirm a `clarification-mismatch` warning is written to the run's step summary and that a watchdog pass over the run surfaces it as a finding.

### Implementation for User Story 3

- [X] T005 [P] [US3] In `.github/workflows/intake.yml`, extend "Check whether the spec still needs clarification" (rewritten by T002) to append, after `needed` is computed: `marker=true` if `grep -q '\[NEEDS CLARIFICATION:' "$SPEC_DIR/spec.md"` else `marker=false` (colon-form, FR-008 — the trailing colon is what distinguishes a real marker `[NEEDS CLARIFICATION: <question>]` from a bare prose mention); if `marker` disagrees with `needed`'s underlying boolean (`clarifications` array non-empty), append to `$GITHUB_STEP_SUMMARY` the line `⚠️ clarification-mismatch: structured output reported clarifications=<empty|non-empty> but the colon-form marker scan found <a match|no match> in <spec-dir>/spec.md.` (the literal token `clarification-mismatch` MUST appear verbatim — `contracts/clarification-schema.md`, `contracts/watchdog-sentinel.md`). `marker`'s value MUST NOT be read anywhere else in this step or any downstream step (FR-004) — `needed`'s value, already set by T002, is untouched by this task. **Headless status:** implemented as specified — `SPEC_DIR` re-added as an env var, `needed`'s value captured into a local `structured` variable before the cross-check runs, the colon-form grep computes `marker` independently, and the mismatch line (with the literal `clarification-mismatch` token) is appended to `$GITHUB_STEP_SUMMARY` only on disagreement. `marker` is not read anywhere else. `actionlint` clean of new findings.
- [X] T006 [P] [US3] In `.github/workflows/clarify.yml`, extend "Determine clarification follow-up outcome" (rewritten by T003) with the same colon-form cross-check as T005, but only when `answered == true` (skip entirely when `outcome == 'none'` — `research.md`'s cross-check-scope decision: there is no post/don't-post decision for a disagreement to be about when the reply resolved nothing, and running it on every `none` run would fire routinely since the reply usually doesn't touch `spec.md`'s markers). Compare `marker` against `outcome == 'needs-clarification'`'s underlying boolean (`clarifications` non-empty); on disagreement, append the same `clarification-mismatch` step-summary line format as T005, run against the post-agent-edit `spec.md` (the checkout already reflects the agent's commit by this point in the job). **Headless status:** implemented as specified — `SPEC_DIR` (from `steps.ctx.outputs.spec-dir`) added as an env var, the cross-check is nested inside the `answered == true` branch only (never runs when `outcome == 'none'`), and the mismatch line matches T005's format exactly. `actionlint` clean of new findings.
- [X] T007 [P] [US3] In `.github/workflows/watchdog.yml`, in "Collect: step summaries" (`id: collect-step-summary`), change the `sentinels=` line from `sentinels='stalled|rejected|turn budget warning|could not inspect|denied|abandon'` to `sentinels='stalled|rejected|turn budget warning|could not inspect|denied|abandon|clarification-mismatch'` (`contracts/watchdog-sentinel.md` — the only edit this file needs; no other sentinel-handling, fingerprinting, or `diagnose`-prompt code changes, since the downstream machinery already keys off whichever alternation member matched, generically). **Headless status:** single-token edit applied at line 618 exactly as specified; no other lines in the step touched. `actionlint` clean of new findings (pre-existing SC2016/SC2129/deployment/job_workflow_sha findings elsewhere in the file are unrelated to this line).

**Checkpoint**: All three of User Stories 1, 2, and 3 hold — a genuine disagreement is loud (`quickstart.md` Scenario 5) and a prose-only mention stays quiet (Scenario 4's mismatch-count check reads `0`), and the watchdog sentinel is present exactly once (Scenario 8).

---

## Phase 6: User Story 4 - Clarify's three outcomes stay distinct (Priority: P2)

**Goal**: Confirm clarify's `none` outcome (the agent's early-STOP path) is never reinterpreted as an empty-array `ready`, and that `ready`/`needs-clarification` are each reached correctly — the mapping itself was already built by T003 (a schema carrying `answered` cannot exist without this mapping), so this story is proof, not new code.

**Independent Test**: Run clarify on a reply that answers none of the open questions (the early-STOP path). Confirm no clarification-questionnaire callout and no spec-PR-ready callout are posted, and that the absent questionnaire is treated as `none`, not as an empty-array `ready`.

### Implementation for User Story 4

- [X] T008 [US4] Audit `.github/workflows/clarify.yml` as rewritten by T003: confirm "Determine clarification follow-up outcome" maps `answered == false` to `outcome=none` unconditionally (ignoring whatever `clarifications` holds), and that neither "Announce remaining clarification questions" (`if: outcome == 'needs-clarification'`) nor "Announce spec PR ready for review" (`if: outcome == 'ready'`) can fire when `outcome == 'none'`; confirm step 2's early-STOP `gh issue comment` (FR-014) is unchanged by T003's prompt edit. Record in the PR body that the live-run form of `quickstart.md` Scenarios 6 (early-STOP reply → `none`, neither callout, only the agent's own comment) and 7 (full resolution → `ready`; partial resolution → `needs-clarification` listing only the still-open questions) should be exercised by a maintainer against a real clarify dispatch before merge — this task can confirm the mapping by code inspection but not by a live agent run. **Headless status:** confirmed by inspection — "Determine clarification follow-up outcome" (clarify.yml, `id: clarification`) sets `outcome=none` from the `if [ "$answered" != "true" ]` branch alone, before `clarifications`/the cross-check are ever consulted; "Announce remaining clarification questions" and "Announce spec PR ready for review" keep their `needs-clarification`/`ready` `if:` conditions, so neither can fire when `outcome == 'none'`. Step 2's early-STOP `gh issue comment` instruction is untouched — only step 6's file-write instruction was replaced by T003. This run opens no PR; the live-run form of Scenarios 6–7 against a real clarify dispatch is deferred to maintainer review before merge.

**Checkpoint**: All four user stories hold — clarify's three outcomes are each reached correctly and `none` is never conflated with `ready`.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Validate the finished workflow files and sweep the remaining `quickstart.md` scenarios that aren't specific to one story.

- [X] T009 [P] Validate `.github/workflows/intake.yml`, `.github/workflows/clarify.yml`, and `.github/workflows/watchdog.yml` parse as valid YAML and their embedded `run:` scripts pass shell syntax checking, matching `.github/workflows/lint-workflows.yml`'s own CI checks (`yamllint` + `actionlint`, which runs `shellcheck` over every `run:` block) — run locally with whatever of that tooling is available in this headless run, or note which checks are deferred to `lint-workflows.yml`'s own CI pass on the PR. **Headless status:** `actionlint` run over all three finished files in one invocation — every finding is pre-existing (`job_workflow_sha` property-not-defined, unrelated `deployment` mapping-key warning, an `ls` SC2012 info and, in `watchdog.yml`, SC2016/SC2129 info findings far from this feature's edits); none of this feature's added `run:` blocks produced a new finding. `yamllint` was also run; it reports the repo's pre-existing 80-column `line-length` style violations pervasively across all three files (confirmed pre-existing by diffing against the pre-implementation commit — e.g. `intake.yml` line 22, untouched by this feature, already exceeded 80 characters) plus two pre-existing `document-start`/`truthy` warnings unrelated to this feature's edits; `lint-workflows.yml`'s actual CI gate (`.github/workflows/lint-workflows.yml`) does not run `yamllint` at all — it does its own Python YAML-parse + `bash -n` check, which this task cannot invoke headlessly (`python3` not allowlisted) and is deferred to that workflow's own CI pass on the PR.
- [X] T010 Run `quickstart.md`'s remaining scenarios not already covered by T004/T008's audits: Scenario 2 (static grep confirming a validation-failure path exists in both files, positioned before the questionnaire/spec-PR-ready steps — `grep -n "clarifications" .github/workflows/intake.yml .github/workflows/clarify.yml`), Scenario 3 (zero authored questions → zero clarification-questionnaire callouts, live-run), Scenario 8 (`grep -n "sentinels=" .github/workflows/watchdog.yml` returns exactly one match ending in `clarification-mismatch`), Scenario 9 (`grep -n "NEEDS CLARIFICATION" .github/workflows/intake.yml .github/workflows/clarify.yml` shows only the colon-form cross-check lines T005/T006 added — no code path turns marker text into a `clarifications`-shaped value, confirming FR-007 is satisfied by omission), and Scenario 10 (a full dogfooded live run: intake → clarify → resolution, confirming no `clarification-mismatch` line appears on an ordinary well-behaved run and the `## Question N` blocks are byte-for-byte unchanged from before this feature, FR-010). Scenarios 2, 8, and 9 are static and can run headlessly now; Scenarios 3 and 10 require a live pipeline dispatch — record in the PR body which were exercised live versus desk-checked only, per the same discipline `specs/019-next-step-callouts/tasks.md`'s T013 used. **Headless status:** Scenario 2 confirmed — both `intake.yml` and `clarify.yml` contain a "Fail on agent API error" `agent_ok`/`clarifications`-shape check with `::error::`/`exit 1`, positioned immediately after the agent step and before the decision/render/announce steps. Scenario 8 confirmed — `grep -n "sentinels=" .github/workflows/watchdog.yml` returns exactly one match (line 618), ending `...abandon|clarification-mismatch`. Scenario 9 confirmed — the only `NEEDS CLARIFICATION` matches beyond this feature's colon-form cross-check lines (intake.yml:656, clarify.yml:477) are pre-existing agent-prompt references to the spec-editing task itself (intake.yml:520,523; clarify.yml:384,390), never a code path that turns marker text into a `clarifications`-shaped value. Scenarios 3 and 10 require a live pipeline dispatch and are deferred to maintainer review before merge — this run opens no PR, so that verification note lives here instead of a PR body.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: N/A — no tasks, nothing blocks User Story 1 beyond Setup's confirmation.
- **User Story 1 (Phase 3)**: Depends on Setup (T001 confirms the exact step names/lines T002/T003 edit).
- **User Story 2 (Phase 4)**: Depends on User Story 1 (T004 audits the code T002/T003 wrote — there is nothing to audit before it exists).
- **User Story 3 (Phase 5)**: Depends on User Story 1 (T005/T006 extend the same decision steps T002/T003 rewrote; T007 is independent of both but is grouped here since it is meaningless without T005/T006 ever producing the sentinel it matches).
- **User Story 4 (Phase 6)**: Depends on User Story 1 (T008 audits the `answered` mapping T003 wrote).
- **Polish (Phase 7)**: Depends on all prior phases.

### User Story Dependencies

- **User Story 1 (P1)**: No dependency on User Stories 2, 3, or 4 — this is the MVP.
- **User Story 2 (P1)**: Depends on User Story 1's code existing (it audits that code); no dependency on User Story 3 or 4.
- **User Story 3 (P2)**: Depends on User Story 1's code existing (it extends that code); no dependency on User Story 2 or 4.
- **User Story 4 (P2)**: Depends on User Story 1's code existing (it audits that code); no dependency on User Story 2 or 3.

### Same-file ordering (not story dependencies, but real ordering constraints)

- `.github/workflows/intake.yml` is edited by T002 (US1) then T005 (US3) — T005 must land after T002 since it extends the exact step T002 rewrites. T004 (US2) and T009/T010 (Polish) only read the finished file.
- `.github/workflows/clarify.yml` is edited by T003 (US1) then T006 (US3) — same ordering constraint. T004, T008 (US2/US4) and T009/T010 (Polish) only read the finished file.
- `.github/workflows/watchdog.yml` is edited only by T007 (US3) — independent of the other two files, may proceed at any point after T001.
- T002 and T003 touch different files and may proceed in parallel with each other.
- T005 and T006 touch different files (each extending its own story-1 step) and may proceed in parallel with each other and with T007.

### Parallel Opportunities

- T002 (`intake.yml`) and T003 (`clarify.yml`) can run in parallel — different files, both User Story 1.
- T005, T006, and T007 (User Story 3) can all run in parallel with each other — three different files.
- T009 and T010 (Polish) are parallel-safe with each other since both only read the finished files.

---

## Parallel Example: User Story 1

```bash
# Launch together — two different files, same schema+render+decision+validation-failure pattern:
Task: "Rewrite intake.yml's agent step (--json-schema, prompt) and decision step (structured-only needed, render step, validation failure)"
Task: "Rewrite clarify.yml's agent step (--json-schema with answered, prompt) and decision step (answered-aware outcome mapping, render step, validation failure)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (confirm the step-level inventory)
2. Complete Phase 3: User Story 1 (both files' schema/render/decision/validation-failure rewrite)
3. **STOP and VALIDATE**: Run `quickstart.md` Scenarios 1–3 against the finished wiring
4. This alone closes the #109 class (SC-001) and, as a structural side effect, the #159 class (SC-002) and the `none`/`ready`/`needs-clarification` split (SC-007) — every remaining phase is proof and hardening, not new mechanism

### Incremental Delivery

1. Setup → step inventory confirmed
2. Add User Story 1 → validate Scenarios 1–3 → mergeable increment (MVP: both #109 and #159's underlying mechanism are fixed)
3. Add User Story 2 → validate Scenario 4 → confidence increment (the #159 fix is explicitly proven, not just structurally implied)
4. Add User Story 3 → validate Scenarios 5 and 8 → mergeable increment (disagreements are now loud and watchdog-visible)
5. Add User Story 4 → validate Scenarios 6–7 → confidence increment (the three-way clarify split is explicitly proven)
6. Polish → validate the full Scenario 1–10 sweep, plus lint

### Why User Story 1 alone is the MVP

FR-001/FR-002/FR-003/SC-001 together name the dropped-questionnaire failure (#109) as the confirmed, currently-live core defect this feature exists to close, and closing it (by construction, per this feature's single-artifact design) simultaneously removes the grep as a gating mechanism at all — which is what User Story 2 needs, and what makes User Story 4's three-way split expressible in the first place. User Stories 2, 3, and 4 make that fix *provable* (regression scenario, disagreement visibility, outcome-split proof) and *durable against recurrence* (the watchdog sentinel), which matters, but does not on its own change what a maintainer sees on the happy path.

## Post-review corrections (code review of PR #175)

Six findings against the shipped implementation, fixed on this branch. Each
supersedes the corresponding "Headless status" claim above where they
disagree.

- **T005/T006 + `contracts/watchdog-sentinel.md` (highest severity):** the
  `clarification-mismatch` line was written only to `$GITHUB_STEP_SUMMARY`,
  but `watchdog.yml`'s `Collect: step summaries` greps **job logs**, and
  GitHub does not mirror the summary file into the log. The one-token
  sentinel addition therefore matched nothing that is ever written, leaving
  User Story 3 / FR-012 / SC-004 inert. Both stages now `echo` the identical
  line to stdout as well; the contract's "GitHub mirrors step-summary writes
  into the log" justification was false and has been replaced.
- **T002:** intake's relocated validation gate exited before "Resolve
  created spec" and "Label spec PR to match the issue", so an agent that
  created the spec, branch and PR but lost its terminal result left an
  unlabeled orphan PR and posted no callout. Split into "Validate agent
  result" (runs where the gate was, publishes `valid`, exits 0) and "Fail on
  invalid agent result" (the job's last step, `exit 1`). The clarification
  step is now gated on `valid == 'true'`, so the coerced-empty read FR-002
  guards against is still impossible. `clarify.yml` has no side effects
  after its gate and keeps the single in-place `exit 1`.
- **T002:** "Check whether the spec still needs clarification" was still
  gated on `steps.created.outputs.spec-dir != ''`, inherited from when the
  decision read `spec.md`. A failed branch push made `needed` empty and
  dropped an authored questionnaire silently — the exact failure class this
  feature exists to remove. The gate is gone; only the cross-check (which
  reads a file) is guarded on a spec dir, and the spec-PR-ready callout
  gains its own `spec-dir != ''` so the no-spec path stays callout-free.
- **T002/T003 render algorithm:** `["A"…"J"][.key]` yields `null` past the
  10th option and jq interpolates it as the literal string `null`. The
  schema sets no `maxItems`, so the letter table now runs A–Z with an
  ordinal fallback beyond it.
- **T002/T003 render algorithm:** `answer` and `implications` were
  interpolated into markdown table cells unescaped — a `|` in an answer
  shifts the row's columns and a newline in `implications` truncates the
  table. Both are now escaped (`|` → `\|`, newline runs → `<br>`).
  `question` and `context` render outside the table and are untouched.
- **Not a code change (T010, Scenario 10):** the PR body's "byte-for-byte
  unchanged `## Question N` blocks" claim is slightly stronger than what
  ships — the heading drops the skill's `: [Topic]` suffix, a deviation
  `contracts/clarification-schema.md` documents and justifies (the schema
  carries no `topic` field).
