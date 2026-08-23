---

description: "Task list for Watchdog Precision & Determinism Hardening"
---

# Tasks: Watchdog Precision & Determinism Hardening

**Input**: Design documents from `/specs/024-watchdog-precision-hardening/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/watchdog-spec-amendments-delta.md, quickstart.md

**Tests**: Not requested — no automated test suite exists for any pipeline stage in this repository (plan.md's Testing section, unchanged from spec 015). Validation is manual, via this feature's `quickstart.md` Scenarios A–I, folded into each user-story phase's checkpoint and the Polish phase below.

**Organization**: This is a retrospective correction to an already-shipped stage, not a new feature — every task below edits an already-existing file. The two files almost every task touches are `.github/workflows/watchdog.yml` (code) and `specs/015-pipeline-watchdog/spec.md` (the requirements being corrected); `[P]` is therefore used sparingly, the same discipline spec 015's own `tasks.md` applied, reserved for tasks against genuinely different files (`data-model.md`, `contracts/watchdog-workflow.md`, `quickstart.md`, and fully standalone deletions).

**Requirement-numbering scheme**: Per `research.md`'s "Open items intentionally deferred," this feature does not renumber `specs/015-pipeline-watchdog/spec.md`'s existing FR/SC identifiers out from under any cross-reference. Requirements that are amended keep their number; requirements whose entire subject is removed (the rung-1/rung-2 ladder) are marked **Removed** in place (a one-line note citing the superseding requirement) rather than deleted, so the numbering after them never shifts; genuinely new requirements are appended starting at **FR-026**. The map used throughout the tasks below:

| Spec 015 identifier | Disposition | Driven by (spec 024) |
|---|---|---|
| FR-002 (cite evidence) | Amended — validity condition added | FR-008 |
| FR-004 (no finding when nothing detected) | Amended — duty restated onto collectors | FR-002 |
| FR-007 (lightest-sufficient-rung selection) | **Removed** — no ladder remains | FR-014 |
| FR-008 (rung 2 — PR) | **Removed** | FR-014 |
| FR-009 (rung 3 — new issue) | Amended — becomes the sole remediation description | FR-014 |
| FR-010 (ambiguous-rung tie-break) | **Removed** | FR-014 |
| FR-011 (rung-1/rung-2 boundary + guardrail pointer) | **Removed** | FR-014 |
| FR-015 (create new only on no match) | Amended — excludes `unknown` | FR-018/FR-019 |
| FR-016 (stable fingerprint) | Amended — determinism + signal-id-only basis | FR-006/FR-007 |
| FR-017 (rung-1 allowlist guardrail) | **Removed** | FR-014 |
| FR-019 (veto/pause autonomous fixes) | Amended — "the watchdog's writes," not "autonomous fixes" | FR-014 |
| FR-020 (record every autonomous action) | Amended — generalized to include new suppression/failure report shapes | FR-014, FR-009, FR-019 (of spec 024's own numbering) |
| FR-021 (self-inspection, no special case) | Amended — "unexempted," not "identical mechanism" | FR-010/FR-011 |
| **FR-026 (new)** | Attribution invariant | FR-004/FR-005 |
| **FR-027 (new)** | Evidence-validity suppression behavior | FR-009 |
| **FR-028 (new)** | `unknown` dedup outcome | FR-018/FR-019 |
| **FR-029 (new)** | Bounded direct-read dedup lookup | FR-020 |
| SC-001 (100% detection) | Amended — restated verifiable | FR-016 |
| SC-007 (10-minute latency) | Amended — measured via `gh run view` vs. lifecycle-comment timestamps | FR-016 |
| **SC-008 (new)** | Precision criterion | FR-001/FR-015 |

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4, US5, US6, US7)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature, no `src/`/`tests/` split (plan.md's Structure Decision). All file paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: The one genuinely new GitHub-native primitive this feature introduces (research.md).

- [ ] T001 [P] Create the `disposition:confirmed` and `disposition:false-positive` repository labels (e.g. `gh label create disposition:confirmed --color 0E8A16 --description "Watchdog finding confirmed genuine by a maintainer"` and `gh label create disposition:false-positive --color B60205 --description "Watchdog finding confirmed false positive by a maintainer"`). These are maintainer-applied dispositions the precision criterion (FR-001 of spec 024) reads; the watchdog itself never writes them, so no lazy-creation code path is added (unlike `pipeline-defect`/`🐕 · <class>`, which the watchdog does write and therefore does lazily create).

**Checkpoint**: The label taxonomy the precision criterion depends on exists — ready for Foundational.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Collapse `watchdog.yml`'s `triage`/`act` rung ladder to the single remediation path FR-014 requires, and remove the tooling/spec debris that existed solely to support it, **before** any user-story phase edits the same job region (User Stories 3, 4, and 7 below all touch `triage`/`act`).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T002 [P] Delete `.specify/memory/watchdog-guardrails.json` in full — the config existed solely to gate rung 1, which no longer exists (FR-014 of spec 024).
- [ ] T003 In the `triage` job of `.github/workflows/watchdog.yml`, remove the `Check fix-class eligibility`, `Resolve propose-fix model`, `Compose tool args (watchdog.propose-fix)`, `Compute agent turn ceiling (propose-fix)`, `Propose fix`, `Compute agent run verdict (propose-fix)`, `Fail loud on non-healthy agent verdict (propose-fix)`, `Upload Claude execution log (propose-fix)`, `Agent run metrics summary (propose-fix)`, `Check propose-fix diff`, `Rung gate`, and `Upload propose-fix diff artifact` steps, and remove the workflow-level `propose-fix-model`/`propose-fix-max-turns` inputs (FR-014).
- [ ] T004 In the `act` job of `.github/workflows/watchdog.yml`, remove the `Download propose-fix diff`, `Commit fix and open PR (rung 2)`, and `Commit fix and open PR (rung 1)` steps; rename `Ensure pipeline-defect issue (rung 2/3)` to drop the rung framing and collapse its branching, together with `Determine write suppression`, so the sole remediation outcome is create/comment/reopen a `pipeline-defect` issue (depends on T003 — same file).
- [ ] T005 [P] Delete `.github/scripts/verify-watchdog-fix-commit.py` and remove Gate 17 from `.github/workflows/lint-workflows.yml`'s gate registry in full — its subject no longer exists once T003/T004 land (FR-014, Constitution VIII: a gate MUST NOT outlive the subject it checks).
- [ ] T006 [P] Delete the stale `specs/023-reliable-diagnose-verdict/` directory entirely (FR-017 of spec 024; git history remains the record — nothing is force-deleted from git).
- [ ] T007 [P] In `specs/015-pipeline-watchdog/quickstart.md`, retire Scenarios 5–7 (rung 1 auto-fix, rung-1-boundary fallback, pause switch as previously exercised against the rung boundary) — there is no rung 1/2 left to exercise.
- [ ] T008 In `specs/015-pipeline-watchdog/spec.md`, remove **User Story 3** ("Fix a truly minor problem on sight") in full — rung 1 no longer exists; reword **User Story 2**'s title and its rung-2/PR acceptance scenario to describe the single-issue path (create/comment/reopen only, no PR); reword **User Story 4**'s title and body to drop "the same ladder" framing in favor of "the same rules."
- [ ] T009 In `specs/015-pipeline-watchdog/spec.md`'s Requirements section, mark **FR-007**, **FR-008**, **FR-010**, and **FR-011** Removed in place (one-line note each, citing FR-014 of spec 024); amend **FR-009** to describe the sole remediation action without "rung 3" framing; amend **FR-019** to read "the watchdog's writes" rather than "autonomous fixes"; amend **FR-020** to generalize "autonomous action" to the new suppression/failure report shapes this feature adds; mark **FR-017** Removed in place — depends on T008 (same file).
- [ ] T010 In `specs/015-pipeline-watchdog/spec.md`'s Key Entities section, remove the "Guardrail configuration" entity (no successor — there is no longer an autonomous-write rung to guard) and amend "Triage decision" to describe the single dedup-selected branch — depends on T009 (same file).
- [ ] T011 In `specs/015-pipeline-watchdog/data-model.md` and `specs/015-pipeline-watchdog/contracts/watchdog-workflow.md`, apply the ladder-collapse edits from this feature's `contracts/watchdog-spec-amendments-delta.md` (`act` section: one branch selected by dedup outcome; "Removed entirely" list) — depends on T010, for consistency with the just-finalized spec.md wording.

**Checkpoint**: `watchdog.yml`'s `triage`/`act` jobs are a straight-line path (fingerprint → dedup → file/comment/reopen) with no rung machinery in code or in spec text; Gate 17 and its fixture, the guardrail config, and the stale 023 directory are gone — ready for user-story work.

---

## Phase 3: User Story 1 - Hold the watchdog to a measured precision bar (Priority: P1) 🎯 MVP

**Goal**: The watchdog's success criteria measure precision (how often filed findings are wrong), not only recall, with a numerator/denominator a maintainer can compute today.

**Independent Test**: Confirm the watchdog's success criteria now include a precision criterion stated against a real denominator (findings filed) with a numerator (findings a maintainer confirms as real), measurable against the existing run record.

### Implementation for User Story 1

- [ ] T012 [US1] In `specs/015-pipeline-watchdog/spec.md`, amend **FR-004** to place the false-positive-avoidance duty on the collectors that produce signals, not solely on `diagnose` (which sees only pre-computed signals and cannot know one is wrong).
- [ ] T013 [US1] In `specs/015-pipeline-watchdog/spec.md`'s Success Criteria section, amend **SC-001** so it is verifiable (states it depends on a labeled corpus of runs known to exhibit each problem class) and amend **SC-007** to state the latency measurement as `gh run view --json updatedAt` (run completion) against the watchdog's own lifecycle-issue report comment's `createdAt`, rather than leaving it unmeasured — depends on T012 (same file).
- [ ] T014 [US1] In `specs/015-pipeline-watchdog/spec.md`'s Success Criteria section, add new **SC-008**: numerator = distinct filed `pipeline-defect` issues, among the most recent 20, carrying `disposition:confirmed`; denominator = distinct filed `pipeline-defect` issues among the most recent 20; target ≥70%; not evaluated until at least 10 distinct findings exist, reported "not applicable" below that — depends on T013 (same file).
- [ ] T015 [P] [US1] In `specs/015-pipeline-watchdog/data-model.md`, add the Precision criterion entity (numerator, denominator, target, not-yet-applicable state, and the manual `gh issue list --label pipeline-defect --label disposition:confirmed` / `--label disposition:false-positive` computation) per this feature's own `data-model.md`.
- [ ] T016 [P] [US1] In `specs/015-pipeline-watchdog/quickstart.md`, add the precision-criterion validation scenario (fewer than 10 distinct findings ⇒ "not applicable"; once ≥10 exist, compute over the most recent 20) — this feature's `quickstart.md` Scenario E.

**Checkpoint**: A maintainer can compute the precision criterion against the filed-finding record today, with a defined not-yet-applicable state — independent of every other phase.

---

## Phase 4: User Story 2 - Require every signal to belong to the run it describes (Priority: P1)

**Goal**: Every collector — not just the two already patched — emits a signal about a run only when that run executed and owned the measured artifact.

**Independent Test**: Confirm the requirements state an attribution invariant that every collector must satisfy, and that a collector fed a run which did not execute, or which did not own the artifact being measured, emits no signal.

### Implementation for User Story 2

- [ ] T017 [US2] In the `collect` job of `.github/workflows/watchdog.yml`, add the attribution-invariant execution check to the `Collect: execution-output artifacts` step (denied-tool collector): early-exit with no signal emitted when the inspected run's `conclusion` is `skipped`/`cancelled`, reusing the check already present in `Collect: branch drift`/`Collect: spec-meta state vs. expected stage` (ownership is already implicit — the artifact is downloaded by this run's own id).
- [ ] T018 [US2] In the `collect` job, add the same execution check to the `Collect: step summaries` step, applied per-job (a job that itself never ran contributes no signal, even if sibling jobs in the same run did) — ownership is already inherent to the per-job API call.
- [ ] T019 [US2] In the `collect` job, add the same execution check to the `Collect: annotations` step, applied per-job, mirroring T018.
- [ ] T020 [P] [US2] In `specs/015-pipeline-watchdog/spec.md`, add new **FR-026**: a collector MUST emit a signal about a run only when the inspected run both executed and owned the artifact whose condition the signal describes — stated once, applying to all five collectors.
- [ ] T021 [P] [US2] In `specs/015-pipeline-watchdog/data-model.md`'s Signal entity, document the attribution invariant (executed/owned columns) and that before this feature only 2 of 5 collectors enforced it, after this feature all 5 do.
- [ ] T022 [P] [US2] In `specs/015-pipeline-watchdog/contracts/watchdog-workflow.md`'s `collect` section, amend the contract to state all five collector steps check attribution before emitting a signal.
- [ ] T023 [P] [US2] In `specs/015-pipeline-watchdog/quickstart.md`, add the attribution-invariant validation scenario (a skipped/cancelled run produces no finding from a newly-guarded collector) — this feature's `quickstart.md` Scenario A.

**Checkpoint**: All five collectors suppress signals for runs they cannot attribute; quickstart Scenario A passes.

---

## Phase 5: User Story 4 - Reject findings whose cited evidence is empty (Priority: P2)

**Note on ordering**: Although spec.md labels this P2 and User Story 3 (next phase) P1, research.md states an explicit, hard ordering constraint: "FR-008/FR-009 must land before FR-006/FR-007 can simplify to a single [fingerprint] path." This phase MUST be implemented before the next one — deleting the fingerprint's fallback branch is only safe once every finding reaching that step is guaranteed a valid signal id, which this phase's evidence-validity gate guarantees.

**Goal**: A finding whose cited facts are missing or malformed is suppressed before it ever reaches fingerprinting, dedup, or a write.

**Independent Test**: Confirm the evidence requirement now imposes a validity condition, and that a finding whose cited facts are empty or malformed is suppressed instead of filed.

### Implementation for User Story 4

- [ ] T024 [US4] In the `triage` job of `.github/workflows/watchdog.yml`, add a new `Evidence validity gate` step immediately before `Compute fingerprint`: for each Finding, check `evidence[].signalId` resolves to a signal this run's collectors actually emitted AND `normalizedFacts` carries every key required for `finding.class` (the per-class key list: `tool` for `denied-tool`, `branch` for `lost-progress`, `expected`/`actual` for `stage-mismatch`, etc.) AND none of those required values is null, empty string, or empty array; a Finding failing this check is marked `suppressed: invalid-evidence` and MUST NOT proceed to fingerprinting, dedup, or any write.
- [ ] T025 [US4] In `.github/workflows/watchdog.yml`'s lifecycle-issue reporting steps, add the "suppressed: invalid evidence" report shape for findings T024's gate rejects, distinct from "passed inspection" and "could not inspect this run" — depends on T024 (same file).
- [ ] T026 [US4] In `specs/015-pipeline-watchdog/spec.md`, amend **FR-002** to impose the validity condition (cited facts MUST be non-empty and conform to the expected shape for the finding's class) and add new **FR-027**: a finding whose cited facts are absent, empty, or malformed MUST be suppressed rather than filed, even if it references a valid run.
- [ ] T027 [P] [US4] In `specs/015-pipeline-watchdog/data-model.md`'s Finding entity, add the evidence-validity-gate `valid ⟺ ...` formula.
- [ ] T028 [P] [US4] In `specs/015-pipeline-watchdog/contracts/watchdog-workflow.md`'s `diagnose`/`triage` sections, amend the contract to state the new deterministic gate between `diagnose` and `triage`'s existing steps.
- [ ] T029 [P] [US4] In `specs/015-pipeline-watchdog/quickstart.md`, add the evidence-validity-gate validation scenario (a `denied-tool` finding with null `tool`/`denials` is suppressed before fingerprinting) — this feature's `quickstart.md` Scenario B.

**Checkpoint**: Findings with empty/malformed cited facts are suppressed, not filed; quickstart Scenario B passes; the fingerprint step's fallback precondition can no longer occur, unblocking the next phase.

---

## Phase 6: User Story 3 - Make finding identity deterministic, not merely stable (Priority: P1)

**Goal**: The same defect recurring across runs produces the exact same fingerprint, computed only from deterministic collector signal ids — never from model-authored text.

**Independent Test**: Confirm the fingerprint requirement demands determinism and that the basis is deterministic collector signals, not free-form model-authored text; inspecting one run twice yields byte-identical fingerprints.

### Implementation for User Story 3

- [ ] T030 [US3] In the `triage` job of `.github/workflows/watchdog.yml`'s `Compute fingerprint` step, delete the `normalizedFacts`-based fallback branch entirely, leaving `fingerprint = sha256(finding.class + "|signals:" + sorted-joined(valid cited signal ids))` as the sole, unconditional basis — safe only because T024's evidence-validity gate now guarantees every Finding reaching this step already carries at least one valid signal id (depends on T024).
- [ ] T031 [US3] In `specs/015-pipeline-watchdog/spec.md`, amend **FR-016** to require the fingerprint be *deterministic* (a pure function of stated inputs yielding an identical value on repeated computation) in addition to stable, and to require the basis be the deterministic collector signal ids rather than model-authored `normalizedFacts` text.
- [ ] T032 [P] [US3] In `specs/015-pipeline-watchdog/data-model.md`'s Fingerprint entity, replace the two-branch (primary/fallback) description with the single signal-id-only basis.
- [ ] T033 [P] [US3] In `specs/015-pipeline-watchdog/contracts/watchdog-workflow.md`'s `triage` section, amend the fingerprint contract clause to drop the fallback branch.
- [ ] T034 [P] [US3] In `specs/015-pipeline-watchdog/quickstart.md`, add the deterministic-fingerprint validation scenario (the same defect from two different runs yields byte-identical fingerprints and dedups to `match-open`) — this feature's `quickstart.md` Scenario C.

**Checkpoint**: Fingerprinting has exactly one basis; quickstart Scenario C passes; none of the nine historical duplicate issues could recur under this scheme.

---

## Phase 7: User Story 7 - Never let a failed dedup lookup masquerade as "nothing found" (Priority: P1)

**Goal**: A dedup lookup that cannot complete reports `unknown` and suppresses filing, instead of falling through to "nothing found, file it as new."

**Independent Test**: Confirm the requirements name an `unknown` dedup outcome distinct from `none`, that `unknown` suppresses filing, and that the lookup is a bounded direct read within a finding's class rather than a search-index query.

### Implementation for User Story 7

- [ ] T035 [US7] In the `triage` job of `.github/workflows/watchdog.yml`'s `Dedup search` step, replace `gh search issues "<marker> in:body" --state all` with `gh issue list --repo "$GITHUB_REPOSITORY" --label pipeline-defect --label "🐕 · ${FINDING_CLASS}" --state all --limit 200 --json number,state,body`, capturing stderr; a non-zero exit sets `outcome=unknown` explicitly (never `results='[]']`); on success, a local `jq` filter over `.body` for the exact `fingerprint=$FP` marker within that bounded result set determines `none`/`match-open`/`match-closed`/`data-integrity` as before.
- [ ] T036 [US7] In the `act` job of `.github/workflows/watchdog.yml`, add an `unknown`-outcome branch checked before the create/comment/reopen branches: `[ "$DEDUP_OUTCOME" = "unknown" ]` suppresses every write for that finding and posts "dedup lookup failed — finding suppressed, needs a maintainer's manual check" to the lifecycle issue, sharing no code path with the `none` (create-new) branch — depends on T035 and on T004 (Foundational's collapsed single-branch `act` structure).
- [ ] T037 [US7] In `specs/015-pipeline-watchdog/spec.md`, amend **FR-015** to exclude the `unknown` outcome from "create new only when a finding matches nothing" (a lookup that did not complete cannot be treated as "matches nothing"); add new **FR-028**: a fourth dedup outcome `unknown` — the lookup could not be completed, distinct from `none` — MUST suppress filing and MUST NOT share a code path with `none`; add new **FR-029**: the dedup lookup MUST be a bounded, strongly-consistent direct read scoped to the finding's class (`gh issue list --label`) rather than an eventually-consistent search index.
- [ ] T038 [P] [US7] In `specs/015-pipeline-watchdog/data-model.md`'s Dedup outcome entity, add the `unknown` row and the `gh issue list --label` lookup-mechanism description.
- [ ] T039 [P] [US7] In `specs/015-pipeline-watchdog/contracts/watchdog-workflow.md`'s `triage`/`act` sections, amend the dedup-lookup and remediation-branch contract clauses.
- [ ] T040 [P] [US7] In `specs/015-pipeline-watchdog/quickstart.md`, add the dedup-lookup-failure validation scenario (a forced `gh issue list` failure suppresses filing and reports the failure; restoring access resumes normal `none` → create behavior) — this feature's `quickstart.md` Scenario D.

**Checkpoint**: A broken dedup lookup produces zero duplicate issues and surfaces its own failure; quickstart Scenario D passes.

---

## Phase 8: User Story 5 - Amend the self-inspection requirement to match what was learned (Priority: P2)

**Goal**: FR-021 requires self-inspection be unexempted, not mechanism-identical — matching the already-shipped deterministic self-checker. Text-only; no code change (research.md — the shipped `wing-commander-8b-watchdog-self.yml` and self-dispatch-depth logic already satisfy the substance).

**Independent Test**: Confirm the self-inspection requirement is amended to require self-inspection be unexempted rather than identical in mechanism, and that it recognizes a deterministic checker as a valid, stronger form.

### Implementation for User Story 5

- [ ] T041 [US5] In `specs/015-pipeline-watchdog/spec.md`, amend **FR-021** to require self-inspection be *unexempted* (never skipped or softened for the watchdog's own runs) rather than requiring the inspection *mechanism* be identical to other stages', and to explicitly recognize a deterministic self-checker as a valid, stronger form of unexempted self-inspection.
- [ ] T042 [US5] In `specs/015-pipeline-watchdog/spec.md`'s User Story 4, reword the acceptance scenarios to describe "the same rules, unexempted" rather than "identical mechanism," consistent with the amended FR-021 — depends on T041 (same file; continues T008's earlier ladder-framing reword of this same story).
- [ ] T043 [P] [US5] In `specs/015-pipeline-watchdog/contracts/watchdog-workflow.md`, amend any self-inspection contract clause referencing FR-021's old "identical mechanism" wording to match the amended requirement.
- [ ] T044 [P] [US5] In `specs/015-pipeline-watchdog/quickstart.md`, add the self-inspection-requirement-text validation scenario (read the amended FR-021 next to the shipped deterministic self-checker's behavior and confirm no contradiction) — this feature's `quickstart.md` Scenario G.

**Checkpoint**: FR-021's text matches the shipped deterministic self-checker; quickstart Scenario G passes with zero code changes.

---

## Phase 9: User Story 6 - Write down the deterministic-judgment principle (Priority: P2)

**Goal**: The project's governing documents record that judgment gating a durable action belongs in deterministic code, not an agent's prompt — citable by a future reviewer.

**Independent Test**: Confirm the principle is stated in the appropriate governing document such that a reviewer can cite it when a future change places gating judgment in an agent prompt.

### Implementation for User Story 6

- [ ] T045 [US6] In `.specify/memory/constitution.md`, add **Principle IX**, immediately following Principle VIII, stating that judgment which gates a durable action (a filed finding, a fingerprint, a dedup outcome, an autonomous write) belongs in deterministic code, not an agent's prompt; cite this feature's five worked examples (the deterministic 8b self-checker, the already-shipped deterministic rung gate, signal-derived fingerprints, suppression pushed into collectors, an enum the model cannot leave) as prior art, following Principle VIII's own citation shape.
- [ ] T046 [US6] In `.specify/memory/constitution.md`, bump the constitution's version per its own amendment-versioning rule and record the Sync Impact Report entry for this change — depends on T045 (same file).
- [ ] T047 [P] [US6] In `specs/015-pipeline-watchdog/spec.md`'s Assumptions section, add a cross-reference citing Principle IX near the amended FR-002/FR-004/FR-016 evidence/fingerprint requirements this feature hardened.
- [ ] T048 [P] [US6] In `specs/015-pipeline-watchdog/quickstart.md`, add the principle-citability validation scenario (Principle IX is citable against a hypothetical future PR that asks `diagnose` to decide fingerprint uniqueness itself) — this feature's `quickstart.md` Scenario H.

**Checkpoint**: Principle IX exists, is versioned, and is citable; quickstart Scenario H passes.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Final consistency pass and end-to-end validation across every phase above.

- [ ] T049 [P] In `specs/015-pipeline-watchdog/quickstart.md`, add the stale-directory-removal validation scenario (`specs/023-reliable-diagnose-verdict/` no longer exists in the working tree; its git history remains queryable) — this feature's `quickstart.md` Scenario I.
- [ ] T050 Re-scan `specs/015-pipeline-watchdog/spec.md` for any remaining cross-reference to a Removed identifier (FR-007, FR-008, FR-010, FR-011, FR-017) or to "rung 1"/"rung 2"/"guardrail" language outside the Removed-marker notes themselves, and correct it (SC-009 of spec 024 — no requirement may describe machinery the watchdog no longer has).
- [ ] T051 Confirm `.github/workflows/lint-workflows.yml`'s gate registry no longer contains Gate 17 and that no remaining gate references `verify-watchdog-fix-commit.py` or `watchdog-guardrails.json`.
- [ ] T052 Execute `quickstart.md` Scenarios A–I end-to-end against a scratch spec/run (or as close as the harness permits) and record results, confirming each of this feature's seven named gaps is closed as described.
- [ ] T053 Re-score the retrospective's five historical false positives (#102, #104, #105, #112, #125) against the strengthened requirements — for each, identify the specific gap now closed (unattributable signal, empty evidence, or absent precision bar) that would have suppressed it — and record the mapping (SC-002 of spec 024).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS User Stories 3, 4, and 7 (all edit the `triage`/`act` region Foundational simplifies). User Stories 1, 2, 5, and 6 do not touch that region and could technically start in parallel with Foundational, but doing so risks merge conflicts against the same `watchdog.yml`/`spec.md` files Foundational also edits — sequential execution is recommended regardless.
- **User Story 4 (Phase 5) before User Story 3 (Phase 6)**: A hard technical dependency, not merely a suggested order — see Phase 5's ordering note. This is the one place priority label (P2 before P1) is overridden by a correctness requirement.
- **User Story 7 (Phase 7)**: Depends on Foundational's collapsed `act` job (T004) for its `unknown`-branch insertion (T036); otherwise independent of Phases 3–6.
- **User Stories 1, 2, 5, 6**: Each independent of the others once Foundational is complete.
- **Polish (Phase 10)**: Depends on all preceding phases.

### Parallel Opportunities

- All Setup tasks marked `[P]` can run in parallel (there is only one).
- Within Foundational, T002/T005/T006/T007 (four genuinely different, standalone files) can run in parallel with each other and with the T003→T004 `watchdog.yml` chain; T008→T009→T010→T011 is a sequential `spec.md`/data-model/contracts chain that should follow the code deletions.
- Within each user-story phase, the `data-model.md`/`contracts/watchdog-workflow.md`/`quickstart.md` tasks marked `[P]` can run in parallel with each other and with that phase's `spec.md`/`watchdog.yml` tasks, once the phase's code/spec-text tasks are far enough along to know what the docs should say.
- User Stories 1, 2, 5, and 6 can be worked in parallel by different contributors once Foundational is complete (each touches a disjoint region: precision text, three collectors, self-inspection text, constitution).

---

## Parallel Example: Foundational

```bash
# Launch the four standalone deletions together, alongside the watchdog.yml rung-removal chain:
Task: "Delete .specify/memory/watchdog-guardrails.json in full"
Task: "Delete .github/scripts/verify-watchdog-fix-commit.py and remove Gate 17 from lint-workflows.yml"
Task: "Delete specs/023-reliable-diagnose-verdict/ entirely"
Task: "Retire Scenarios 5-7 in specs/015-pipeline-watchdog/quickstart.md"
```

---

## Implementation Strategy

### MVP First

Because this feature is a bundled correction answered as one unit on issue #140, "MVP" here means the smallest set of phases that meaningfully raises precision, not a shippable product slice:

1. Complete Phase 1 (Setup) + Phase 2 (Foundational) — required for everything else.
2. Complete Phase 3 (US1, precision criterion) — the measurement the rest of the work is judged against.
3. Complete Phase 4 (US2, attribution) + Phase 5 (US4, evidence validity) + Phase 6 (US3, determinism) + Phase 7 (US7, dedup `unknown`) — **all four P1 stories**, in the dependency order above (US4 before US3). Note US4 is labeled P2 in spec.md but is a hard prerequisite for US3, so it is effectively part of this core.
4. **STOP and VALIDATE**: run `quickstart.md` Scenarios A–E against a scratch spec (Phase 10's T052, scoped to what's landed so far).

Phases 8–9 (US5 self-inspection text, US6 constitution principle) are governance/documentation corrections, fully independent of the precision-affecting code changes above, and can land before, after, or interleaved with them.

### Incremental Delivery

1. Setup + Foundational → the ladder is gone, the label taxonomy exists.
2. Add US1 → the precision bar is measurable (even before the other fixes raise the score).
3. Add US2 → all five collectors respect attribution.
4. Add US4 → US3 → deterministic, evidence-gated fingerprints; dedup starts actually recognizing recurrences.
5. Add US7 → a broken dedup lookup can no longer spam duplicates.
6. Add US5 + US6 → the spec text and governing documents catch up to what the code now does and why.
7. Polish → full quickstart pass, historical-false-positive re-scoring, final consistency sweep.

### Parallel Team Strategy

With multiple contributors: one completes Foundational alone (it touches the file every later phase depends on); once done, up to four contributors can take US1, US2, US5, and US6 in parallel, while a fifth works the US4 → US3 → US7 chain sequentially (it's one contributor's worth of tightly-coupled work in one file region).
