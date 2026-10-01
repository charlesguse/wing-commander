---

description: "Task list for Watchdog Dedup That Survives Partial Signal Overlap and Class Fan-Out"
---

# Tasks: Watchdog Dedup That Survives Partial Signal Overlap and Class Fan-Out

**Input**: Design documents from `/specs/109-watchdog-finding-fanout/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/watchdog-dedup-fanout-delta.md, quickstart.md

**Tests**: Requested, and structured as its own user story rather than a cross-cutting phase — User Story 4 (P2) is this feature's dedicated fixture story (FR-020–FR-022, Constitution VIII): every fixture is checked in with a mutation the PR-time gate suite must be shown to fail under, wired as a new numbered gate. See that phase's ordering note below — it is a P2 label carrying a hard prerequisite on the P1 stories, the same override spec 024's own tasks.md applied to its User Story 4.

**Organization**: Almost every code task edits one of two files — `.github/workflows/watchdog.yml` (the `collect`/`triage`/`act` jobs) or `.github/workflows/implement.yml` (the two cycle-outcome read-back legs) — so `[P]` is used sparingly, the same discipline spec 024's own `tasks.md` applied: reserved for tasks against genuinely different files (`implement.yml` vs. `watchdog.yml`, the new gate script, and the four `specs/015-pipeline-watchdog/*` amendment files).

## Requirement-numbering scheme (spec 015 amendment map, FR-023/FR-024)

Per FR-023/FR-024, `specs/015-pipeline-watchdog/spec.md`'s dedup requirements are amended in place; genuinely new requirements are appended after its current highest identifier (**FR-029**), following spec 024's own precedent of appending rather than renumbering. Nothing below is marked Removed — this feature is purely additive to spec 015's requirement set.

| Spec 015 identifier | Disposition | Driven by (spec 109) |
|---|---|---|
| FR-012 (check open and closed) | Amended — states the two-mechanism check: exact-fingerprint (unchanged) plus, for open issues only, overlap matching | FR-001, FR-030 (new) |
| FR-013 (comment, never duplicate) | Amended — covers both exact and overlap open-issue matches; names FR-031's multi-match naming | FR-007, FR-031 (new) |
| FR-014 (reopen closed) | Amended — reopening is exact-fingerprint-only; partial overlap against a closed issue never reopens | FR-006 |
| FR-015 (create only on no match) | Amended — "matches nothing" now spans both mechanisms | FR-004 |
| FR-016 (deterministic, stable fingerprint) | Amended — notes the one-issue-per-defect mapping is now achieved jointly with FR-030's accumulated matchable set, not by the per-occurrence fingerprint alone | FR-002, FR-016 |
| **FR-030 (new)** | Overlap matching within a class: any shared signal id on an open issue is a match; equality not required; never crosses the class label | FR-001, FR-002 |
| **FR-031 (new)** | Multi-match resolution: lowest-numbered open match only, others named, never merged/closed/relabeled | FR-007 |
| **FR-032 (new)** | Matchable id set: union of every occurrence's cited ids, capped at 30 most-recently-added distinct ids, recorded readably | FR-003, FR-008 |
| **FR-033 (new)** | The FR-009 gate-suite filing condition (converging cycle never files; stalled/finalize-red always does; undeterminable state files) | FR-009, FR-010 |
| **FR-034 (new)** | Legibility: matched/new ids readable without opening the run; report distinguishes overlap from exact and multi-match from single-match | FR-017, FR-018 |
| **FR-035 (new)** | The per-`{stage, tool}` `tool-denial` separation (#266) recorded as deliberate, not an inconsistency | FR-013, FR-024 |
| FR-020 (record every write/suppression) | Amended — adds the FR-033 suppression to the already-itemized list (invalid-evidence, failed dedup lookup, paused/capped) | FR-011, FR-019 |
| FR-028 (`unknown` dedup outcome) | Amended — extends `unknown` to a truncated candidate set (`count == limit`), not only a lookup error | FR-016 |
| Key Entities: Fingerprint, Triage decision | Amended; **Matchable id set**, **Occurrence**, **Gate-suite finding**, **Converging implement cycle** added | Key Entities |

## Gate-numbering scheme

The self-test script is `.github/scripts/verify-watchdog-overlap-fanout.py`, wired in `.github/workflows/lint-workflows.yml` as **Gate 125** — the next free number after Gate 124 (`lint-workflows.yml`'s highest allocated gate at the time this task list was written; confirmed by grep for `Gate \d+` across that file). Per Gate 120's own renumbering-precedent comment and issue #660 (cross-spec gate-numbering collisions), re-grep before wiring: if another in-flight spec has since claimed 125, take the next free number and update this file's references accordingly — do not silently reuse a collided number.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)
- Foundational and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature, no `src/`/`tests/` split (plan.md's Structure Decision). All file paths below are repo-root-relative.

---

## Phase 1: Setup

No standalone Setup tasks. This feature introduces no new GitHub-native primitive needing pre-creation (unlike spec 024's `disposition:*` labels) — every deliverable is a workflow-file, script, or spec-text edit, captured in the phases below.

---

## Phase 2: Foundational (Blocking Prerequisites)

No prerequisite is shared by more than one user story. User Stories 1 and 2 edit adjacent-but-disjoint regions of the same two files (`watchdog.yml`'s `triage`/`act` jobs; `implement.yml`'s two cycle-outcome legs) — sequenced relative to each other in Dependencies below, not gated by a separate phase. User Story 4 (self-test) depends on both having landed. User Story 5 (spec-015 text) is independent of all code and can proceed at any time. User Story 3 (deliberate separations) requires no code change at all (research.md's own decision) — its correctness rests on User Story 1 never widening the `tool-denial` id projection, verified by User Story 4's fixture.

---

## Phase 3: User Story 1 - One recurring failure accumulates on one issue even when the citation set moves (Priority: P1) 🎯 MVP

**Goal**: An open issue matches a later finding of the same class on any shared signal id, not only an identical citation set.

**Independent Test**: Replay the three runs behind #729, #732 and #765 in order against a clean tracker. The first files one issue; the second and third comment on it. No second issue is created.

### Implementation for User Story 1

- [X] T001 [US1] In the `triage` job's `Compute fingerprint` step (`.github/workflows/watchdog.yml`), expose the already-computed `valid` array (the cross-checked, sorted cited ids currently discarded after producing `basis`) as a new step output `cited-ids` (sorted, comma-joined) — later steps read it instead of recomputing the evidence/signals cross-check.
- [X] T002 [US1] In the `triage` job's `Dedup search` step, add `comments` to the `--json number,state,body` field list (→ `--json number,state,body,comments`) in the `gh issue list` call, and add the truncation guard from FR-016 of spec 109 / FR-028 of spec 015: when `count(results) == 200` (the `--limit 200` ceiling), set `outcome=unknown` before any exact or overlap matching logic runs — never falling through to `none` (depends on nothing new; the exact-fingerprint block above it is unchanged).
- [X] T003 [US1] In the same `Dedup search` step, after the existing unchanged exact-fingerprint block (`match-open`/`match-closed`/`data-integrity`, same priority and mechanism as today), add the overlap branch: for every **open** candidate not already the exact match, compute its matchable id set as the union of the ids in its body's `<!-- wing-commander-watchdog: signal-ids=... -->` marker and every comment's same marker (from the `comments` field T002 added), capped at the 30 most-recently-added distinct ids — oldest evicted first, in occurrence order (body, then comments oldest→newest) — with the literal `30` named in a comment at the point it is applied (FR-008 of spec 109). Intersect each candidate's capped set with `CITED_IDS` (T001's new env var). Any candidate with a non-empty intersection is a match; when one or more match, sort by issue number ascending and set `outcome=overlap`, `issue-number=<lowest>`, `matched-on=<the lowest-numbered match's own intersection, sorted, comma-joined>`, and `other-matches=<comma-joined remaining issue numbers, sorted ascending>`. When neither the exact block nor this branch matches anything, `outcome=none` as today.
- [X] T004 [US1] In `Persist triage decision`, add `CITED_IDS` (T001), `DEDUP_MATCHED_ON` and `DEDUP_OTHER_MATCHES` (T003) to the persisted JSON (`cited-ids`, `matched-on`, `other-matches` fields, per data-model.md's Triage decision shape), and extend the accepted `dedup` values to include `overlap`.
- [X] T005 [US1] In the `act` job's `Ensure pipeline-defect issue` step: on the `none` branch, add a second marker line to the created issue body, `<!-- wing-commander-watchdog: signal-ids=<CITED_IDS> -->`, additive alongside the unchanged `fingerprint=` marker (FR-002/FR-003 of spec 109). On the `match-open`/`match-closed`/new `overlap` branches, add the same marker to the recurrence comment body, plus a human-readable line stating which ids matched and which are new — `new-ids = CITED_IDS − DEDUP_MATCHED_ON` (empty for an exact match, since the whole cited set matched) — e.g. "Matched on `<ids>`. New to this issue: `<ids>` (none)." When `DEDUP_OTHER_MATCHES` is non-empty, add a line naming them: "Also matches #n2, #n3 (not merged — a maintainer can combine them by hand)." Never write to any issue named in `other-matches`. This step's existing `if:` exclude-list (`dedup != 'data-integrity' && dedup != 'unknown'`, plus the other unrelated exclusions) needs no change — `overlap` already passes through unchanged.
- [X] T006 [US1] In `Report finding to lifecycle issue`, extend the `case "$DEDUP_OUTCOME"` action-naming block with an `overlap)` arm: "**Action**: recurrence of #$ISSUE_NUMBER (partial signal overlap) — commented." — distinct wording from the existing exact-match `match-open` arm (FR-018 of spec 109) — and append the other-matches names when present.

**Checkpoint**: Replaying #729/#732/#765's citation sets produces one issue and two recurrence comments; a disjoint citation set still files new (Acceptance Scenario 2).

---

## Phase 4: User Story 2 - A converging implement cycle's red gate suite never reaches the board (Priority: P1)

**Goal**: A gate-suite finding whose red suite belongs to a converging implement cycle is never filed; a stalled or finalize-still-red one is filed as normal.

**Independent Test**: Replay run 36484099706's finding set against a clean tracker, with that run's implement cycle recorded as feeding a further cycle. No `pipeline-defect` issue is created for its gate-suite findings; each is reported to the lifecycle issue under a named write-suppression outcome.

### Implementation for User Story 2

- [X] T007 [P] [US2] In `.github/workflows/implement.yml`, immediately after the "Read back cycle outcome" step (`id: outcome`), add a new step "Record cycle outcome for watchdog (cycle)" that runs whenever "Read back cycle outcome" ran (same `if:` guard: `steps.lifecycle-gate.outputs.is-open == 'true' && steps.guard.outputs.skip != 'true'`) and writes `{"converged": <steps.outcome.outputs.converged>, "handoff": <steps.outcome.outputs.handoff>, "gate-suite-outcome": <"pass"|"fail"|"skipped", from steps.gate-suite-cycle.outputs.outcome, "skipped" when that step did not run>, "gate-suite-first-failure": <steps.gate-suite-cycle.outputs.first-failure, or null>}` to `${{ runner.temp }}/wing-commander-cycle-outcome.json`, then uploads it via `actions/upload-artifact@v6` as `wing-commander-cycle-outcome`, `if-no-files-found: warn`. An upload failure here MUST NOT fail the `implement` job (mirrors how `Persist triage decision` in `watchdog.yml` never gates its own job).
- [X] T008 [US2] In `implement.yml`, add the matching "Record cycle outcome for watchdog (retry)" step immediately after "Read back retry outcome" (`id: retry-outcome`), same shape as T007 but reading `steps.retry-outcome.outputs.*` and `steps.gate-suite-retry.outputs.*`, uploading to the same artifact name `wing-commander-cycle-outcome` — mutually exclusive with T007's upload within one job run, since at most one of the two legs' "Read back ... outcome" steps actually runs per attempt (same file as T007; not marked `[P]` against it).
- [X] T009 [US2] In the `collect` job of `.github/workflows/watchdog.yml`, add a sixth collector, "Collect: cycle outcome", mirroring "Collect: execution-output artifacts"' attribution-guarded `gh run download ... -p 'wing-commander-cycle-outcome*'` pattern: a missing artifact (not an implement run, the run predates this feature, or the upload itself never happened) is a successful empty contribution — record no cycle-outcome state, never fail the step. When present, record its four fields as new `collect` job outputs (e.g. `cycle-outcome-converged`, `cycle-outcome-handoff`, `cycle-outcome-gate-suite-outcome`, `cycle-outcome-gate-suite-first-failure`) for `triage` to consume — add these to the `collect` job's `outputs:` block.
- [X] T010 [US2] In the same "Collect: cycle outcome" step, when `gate-suite-outcome == "fail"`, append one entry to `signals.json`: `{source:"gate-suite","class-hint":null,facts:{"first-failure":<normalized text>}}`, using the same `jq -c --argjson new ... '. + $new' "$RUNNER_TEMP/signals.json"` append convention every other collector step already uses.
- [X] T011 [US2] In `Stamp signal ids`'s kind-mapping `jq` program, add a new `elif ($src | startswith("gate-suite"))` branch (alongside the existing `spec-collision`/`final-pr-claims` branches) projecting to `{kind: "gate-suite-failure", ident: {"first-failure": ($fx["first-failure"] // "" | ascii_downcase)}}`.
- [X] T012 [US2] Add `meta-stage` and `stalled-label` to the `collect` job's `outputs:` block (`${{ steps.spec-slug.outputs.meta-stage }}` / `${{ steps.spec-slug.outputs.stalled-label }}`) — already computed inside `collect` for the branch-drift/spec-meta collectors' own internal use, but not currently surfaced to `triage`, which T013 needs.
- [X] T013 [US2] In the `triage` job, add a new step "Gate-suite filing condition" immediately after `Compute fingerprint` and before `Dedup search`, gated by the same `if:` both already share (`steps.suppress.outputs.suppressed != 'true' && steps.evidence-gate.outputs.valid != 'false'`): read `CITED_IDS` (T001) and `needs.collect.outputs.signals`; if every one of this finding's cited ids has `signal-kind == "gate-suite-failure"` AND `needs.collect.outputs.cycle-outcome-converged == 'false'` AND `needs.collect.outputs.cycle-outcome-handoff == 'false'` AND neither `needs.collect.outputs.meta-stage == 'stalled'` nor `needs.collect.outputs.stalled-label == 'true'` (T009/T012), set `outcome=converging-gate-suite`; otherwise emit no outcome (falls through to normal dedup).
- [X] T014 [US2] Add `&& steps.gate-suite-condition.outputs.outcome != 'converging-gate-suite'` to `Dedup search`'s existing `if:` condition, so the FR-009 suppression skips dedup entirely rather than running it and discarding the result (contract: "does NOT run steps 4-5").
- [X] T015 [US2] In `Persist triage decision`, record `dedup=converging-gate-suite` when T013's step produced that outcome, bypassing the normal `DEDUP_OUTCOME`/`DEDUP_ISSUE` reads (which are unset on this path).
- [X] T016 [US2] Add `steps.decision.outputs.dedup != 'converging-gate-suite'` to `act`'s `Ensure pipeline-defect issue` step's existing `if:` exclude-list (alongside `data-integrity`/`unknown`) — no write for this outcome.
- [X] T017 [US2] In `Report finding to lifecycle issue`, add a new branch checked before the existing `case "$DEDUP_OUTCOME"` block (same priority tier as the `unknown`/`WRITE_SUPPRESSED` checks) for `DEDUP_OUTCOME = converging-gate-suite`: report under its own wording, e.g. "_Converging implement cycle's red gate suite — the next cycle is already going to fix this; not filed (FR-009)._" — never the `data-integrity`/`unknown` phrasing (FR-011/FR-019 of spec 109).

**Checkpoint**: Replaying run 36484099706's finding set with `converged=false, handoff=false` files zero issues and reports six named suppressions; the same set with `stalled=true`, or `handoff=true`, or no cycle-outcome artifact at all, files all six normally.

---

## Phase 5: User Story 3 - Deliberate separations survive the change (Priority: P1)

**Goal**: The `tool-denial` per-`{stage, tool}` separation (#266) is unaffected by User Story 1's overlap matching.

**Independent Test**: Replay the three runs behind #761, #764 and #780. All three issues are filed, separately, exactly as today.

**Note**: Per research.md, this requires **no code change** — `Stamp signal ids` already keys `tool-denial` ids by `{stage, tool}` (#266), so two denial findings from different pairs cite disjoint ids by construction and T003's overlap branch (which only ever matches on a *shared* id) cannot merge them. Although spec.md ranks this story P1 alongside US1/US2, its own text states the correctness bound "must be specified and fixture-checked before either story ships, not after" — the actual proof is User Story 4's automated fixture (T026/T029 below), not this phase. Treat those as a hard prerequisite for calling US1/US2 shippable, the same kind of priority-label override spec 024's own tasks.md applied to its User Story 4.

### Implementation for User Story 3

- [X] T018 [US3] In `specs/015-pipeline-watchdog/quickstart.md`, add the `{stage, tool}` separation validation scenario (three distinct denial pairs replayed produce three separate issues with pairwise-disjoint matchable id sets) — this feature's own `quickstart.md` Scenario E.

**Checkpoint**: Nothing in `Stamp signal ids`' `tool-denial` branch changed by T001–T017; the guarantee is documented and awaits T026/T029's automated proof.

---

## Phase 6: User Story 4 - The self-test proves it, and a mutation breaks it (Priority: P2)

**Goal**: A checked-in, mutation-tested fixture suite exercises the overlap match, the multi-match resolution, the FR-009 converging/stalled/finalize-red arms, and the preserved `{stage, tool}` separation — registered in the PR-time gate suite.

**Independent Test**: Revert the matching rule to exact-set equality and run the PR-time gate suite. It fails, and names the overlap fixture.

**Ordering**: Depends on User Stories 1 and 2 (T001–T017) having landed — every fixture here executes the real shipped steps those tasks create, per `verify-act-dedup-guard.py`'s established pattern (extract the real step(s) from the workflow, run them through `wc_shell_harness`, assert the real outcome).

### Implementation for User Story 4

- [X] T019 [US4] Create `.github/scripts/verify-watchdog-overlap-fanout.py` (module docstring stating WHY, per `verify-act-dedup-guard.py`'s convention): extracts the real `Compute fingerprint`, `Dedup search`, and `Gate-suite filing condition` steps from the `triage` job of `.github/workflows/watchdog.yml` via `yaml.safe_load` + `wc_shell_harness` (`ensure_jq`, `resolve_bash`, `run_step`), executing them against stubbed `gh issue list`/artifact input.
- [X] T020 [US4] Add the **overlap fixture** (quickstart Scenario A) to that script: three sequential findings of one class citing `{A,B}`, then `{A,C,D}`, then `{D}` alone, against a growing stub issue/comment list. Assert the first computes `outcome=none` (issue body would carry `signal-ids=A,B`); the second computes `outcome=overlap` against that issue with `matched-on=[A]`/new-ids `[C,D]`; the third — citing only `D`, which was recorded only in the second occurrence's comment, never the original body — still computes `outcome=overlap` against the same issue (proves the matchable-set union reads comments, not only the body).
- [X] T021 [US4] Add the **disjoint-set fixture** (quickstart Scenario B / Acceptance Scenario 2 of US1): a finding citing `{E,F}` against the Scenario A issue (matchable set `{A,C,D}` after two occurrences) computes `outcome=none`.
- [X] T022 [US4] Add the **chained multi-match fixture** (quickstart Scenario F / FR-007 of spec 109): two open issues, X (lower number) citing `{A,B}`, Y (higher number) citing `{B,C}`; a finding citing `{A,C}` must compute `outcome=overlap`, `issue-number=X`, `other-matches=[Y]`, and never `data-integrity`.
- [X] T023 [US4] Add the **closed-issue-overlap fixture** (quickstart Scenario G / FR-006 of spec 109): a closed issue with matchable set `{A,B}`; a finding citing `{A,C}` computes `outcome=none` (not reopened, not commented) — contrasted with an exact-fingerprint match against a closed issue, which still reopens it unchanged.
- [X] T024 [US4] Add the **truncation fixture** (quickstart Scenario H / FR-016 of spec 109): a stubbed `gh issue list` response with exactly 200 entries; assert `outcome=unknown` regardless of whether any of the 200 would otherwise have matched.
- [X] T025 [US4] Add the **30-id cap fixture** (FR-008 of spec 109): an issue accumulated across occurrences citing 31 distinct ids; assert the oldest (31st-most-recent) id no longer counts toward a match (a finding citing only that id computes `outcome=none`), while the 30 most recent still do.
- [X] T026 [US4] Add the **`{stage, tool}` separation fixture** (quickstart Scenario E / User Story 3): three findings from three distinct `{stage, tool}` `tool-denial` pairs; assert three separate `outcome=none` results with pairwise-disjoint matchable id sets — the automated proof User Story 3's Checkpoint awaits.
- [X] T027 [US4] Extract and exercise the `Gate-suite filing condition` step (T013) and `Dedup search`'s new exclusion (T014): fixtures for (a) six gate-suite-only findings with `converged=false, handoff=false, stalled=false` → `outcome=converging-gate-suite` for all six, `Dedup search` never invoked; (b) the same six with `stalled=true` (label or spec-meta stage) → filed normally; (c) the same six with `handoff=true` → filed normally; (d) the same six with no cycle-outcome artifact at all (undeterminable state) → filed normally; (e) a run mixing four gate-suite-only findings with one `tool-denial` finding → only the four are suppressed (quickstart Scenario D / Acceptance Scenario 5 of US2).
- [X] T028 [US4] For every fixture in T020–T027, add the companion **mutation** this feature's own subject must be shown to fail under (FR-022 of spec 109; Constitution VIII): reverting `Dedup search`'s overlap branch to exact-set equality (breaks T020/T021/T022/T025); reverting the FR-009 condition to "always file" (breaks T027); reverting the `tool-denial` id projection to a shared, coarser key (breaks T026). Each mutation is asserted to make its affected fixture(s) fail.
- [X] T029 [US4] Wire `verify-watchdog-overlap-fanout.py` into `.github/workflows/lint-workflows.yml`'s gate registry as **Gate 125** (per the Gate-numbering scheme above): a `Gate 125 —` step running `python3 .github/scripts/verify-watchdog-overlap-fanout.py`, and a `Gate 125 self-test —` step running the same script's `--self-test` mode (mirroring Gate 120's two-step shape), both `if: "!cancelled()"`.
- [X] T030 [US4] Confirm `python3 .github/scripts/run-local-gates.py` auto-discovers Gate 125 via `wc_gate_registry`'s derivation from `lint-workflows.yml` (its module docstring states the gate list is derived, not manually registered — no direct edit to `run-local-gates.py` is needed) and that it runs the identical subject/arguments locally as in CI (FR-022 of spec 109, SC-005).

**Checkpoint**: `python3 .github/scripts/run-local-gates.py verify-watchdog-overlap-fanout` passes; reverting overlap matching, the FR-009 condition, or the `tool-denial` keying each independently fails it and names the broken fixture.

---

## Phase 7: User Story 5 - The governing requirement says what the code does (Priority: P3)

**Goal**: `specs/015-pipeline-watchdog/{spec.md,data-model.md,contracts/watchdog-workflow.md,quickstart.md}` state the matching rule this feature ships (FR-023/FR-024).

**Independent Test**: Read FR-012–FR-016 with no other context and predict what happens when a finding cites a superset of an open issue's ids. The prediction matches the shipped behaviour.

**Note**: Independent of all code phases — can proceed in parallel with User Stories 1/2/3/4 once their behavior is settled enough to describe accurately (recommended after Phase 3/4, so the text describes shipped, not planned, behavior).

### Implementation for User Story 5

- [X] T031 [US5] In `specs/015-pipeline-watchdog/spec.md`, amend **FR-012** to state the two-mechanism check before filing: exact-fingerprint match across open+closed issues (unchanged), and, for open issues only, overlap matching on any shared signal id within the finding's class (cites new FR-030).
- [X] T032 [US5] In `specs/015-pipeline-watchdog/spec.md`, add new **FR-030**: overlap matching within a class — an open `pipeline-defect` issue carrying the finding's class label and citing any signal id the finding cites is a match; equality of the cited sets is not required; matching never crosses the class label — depends on T031 (same file).
- [X] T033 [US5] In `specs/015-pipeline-watchdog/spec.md`, add new **FR-031**: when more than one open issue matches, the watchdog attaches the occurrence to the lowest-numbered match only, names the others by number, and never merges, closes, or relabels any of them — depends on T032 (same file).
- [X] T034 [US5] In `specs/015-pipeline-watchdog/spec.md`, add new **FR-032**: an issue's matchable id set is the union of every occurrence's cited ids, capped at 30 most-recently-added distinct ids (oldest evicted first), recorded in a form a later run can read back without inspecting the original run — depends on T033 (same file).
- [X] T035 [US5] In `specs/015-pipeline-watchdog/spec.md`, amend **FR-013** to cover both the exact-match and overlap-match open-issue cases, and to name FR-031's multi-match naming behavior — depends on T034 (same file).
- [X] T036 [US5] In `specs/015-pipeline-watchdog/spec.md`, amend **FR-014** to state reopening a closed issue happens only on an exact fingerprint match — a partial overlap against a closed issue never reopens it — depends on T035 (same file).
- [X] T037 [US5] In `specs/015-pipeline-watchdog/spec.md`, amend **FR-015** so "matches nothing" spans both mechanisms: no exact hit anywhere, and no open issue's matchable set overlaps — depends on T036 (same file).
- [X] T038 [US5] In `specs/015-pipeline-watchdog/spec.md`, amend **FR-016** to note the one-issue-per-recurring-defect mapping this requirement promises is now achieved jointly by the per-occurrence fingerprint (still exact, still the closed-issue reopen path) and FR-030's accumulated matchable set — the fingerprint alone no longer carries that mapping guarantee once the cited subset moves — depends on T037 (same file).
- [X] T039 [US5] In `specs/015-pipeline-watchdog/spec.md`, add new **FR-033**: the watchdog MUST NOT file for a gate-suite finding whose red suite belongs to a converging implement cycle, filing it only when the cycle stalled or reached finalize still red; the condition MUST be decided from deterministic cycle-outcome state, defaulting to filing when that state is undeterminable — depends on T038 (same file).
- [X] T040 [US5] In `specs/015-pipeline-watchdog/spec.md`, add new **FR-034**: a maintainer reading a filed issue or its comments MUST be able to determine which ids caused a match and which are new, without opening the run; the lifecycle-issue report MUST distinguish overlap from exact recurrence and multi-match from single-match — depends on T039 (same file).
- [X] T041 [US5] In `specs/015-pipeline-watchdog/spec.md`, add new **FR-035**: the per-`{stage, tool}` keying of `tool-denial` signal ids (#266) MUST be preserved as a deliberate separation — denials from different stages, or different tools within a stage, accumulate on separate issues by construction, and a reopen means a regression in that specific stage; record this as the deliberate design choice it is, not an inconsistency, citing #266 — depends on T040 (same file).
- [X] T042 [US5] In `specs/015-pipeline-watchdog/spec.md`'s Key Entities section, add **Matchable id set**, **Occurrence**, **Gate-suite finding**, and **Converging implement cycle** entities (per this feature's own `data-model.md`), and amend the **Fingerprint** and **Triage decision** entities to reflect the two-mechanism matching and the new `overlap`/`converging-gate-suite` branches — depends on T041 (same file).
- [X] T043 [US5] In `specs/015-pipeline-watchdog/data-model.md`, fold in this feature's own `data-model.md` additions in full (Signal — `gate-suite-failure` kind; Cycle outcome; Occurrence record; Matchable id set; Dedup outcome — `converging-gate-suite`; Triage decision — updated shape; State transition — updated slice), per `contracts/watchdog-dedup-fanout-delta.md`.
- [X] T044 [P] [US5] In `specs/015-pipeline-watchdog/contracts/watchdog-workflow.md`, apply this feature's `contracts/watchdog-dedup-fanout-delta.md` in full (the `collect`/`implement.yml`/`triage`/`act` amended-contract clauses) — a different file from T031–T043's `spec.md`/`data-model.md` chain, can run in parallel with T043 once both are drafting from the same finalized delta.
- [X] T045 [P] [US5] In `specs/015-pipeline-watchdog/quickstart.md`, append this feature's own `quickstart.md` Scenarios A–D and F–I as new numbered scenarios (Scenario E already added by T018), additive to the existing 015 scenario list — a different file, can run in parallel with T043/T044.

**Checkpoint**: A reviewer reading amended FR-012–FR-016 (plus new FR-030–FR-035) alone correctly predicts the outcome for a superset, subset, disjoint, and chained-overlap citation set (SC-008).

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final consistency pass across every phase above.

- [X] T046 Re-scan `specs/015-pipeline-watchdog/spec.md`, `data-model.md`, `contracts/watchdog-workflow.md`, and `quickstart.md` for any cross-reference broken by the FR-030–FR-035 additions or the FR-012–FR-016/FR-020/FR-028 amendments (a stale FR number, a reworded requirement no longer matching a Key Entity's description) and correct it — the same sweep discipline spec 024's own T050 applied.
- [X] T047 Confirm `.github/workflows/lint-workflows.yml`'s gate registry has no duplicate or collided Gate 125 entry (re-grep `Gate \d+` per the Gate-numbering scheme note) and that Gate 10 (`verify-gate-wiring.py`) passes with the new gate wired.
- [X] T048 Run `python3 .github/scripts/run-local-gates.py` end-to-end and confirm every gate (including the pre-existing dedup gates, Gate 120 and `verify-act-dedup-guard.py`) still passes alongside the new Gate 125 — no regression in the exact-match/closed-issue path this feature leaves unchanged.
- [X] T049 Confirm no task above closes, relabels, comments on, or consolidates any of #729, #732, #765, #708–#713 (FR-025 of spec 109) — this feature is go-forward only; those issues remain for the owner to triage by hand.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** / **Foundational (Phase 2)**: Empty — no blocking prerequisites.
- **User Story 1 (Phase 3)**: No dependency on any other story; can start immediately. T001→T002→T003→T004→T005→T006 is a strictly sequential chain (every task edits the same `triage`/`act` step region of `watchdog.yml`).
- **User Story 2 (Phase 4)**: Independent of User Story 1's *content*, but both chains land inside the same `triage`/`act` jobs of `watchdog.yml` — implement User Story 1 first to avoid a same-region merge conflict, even though the two behaviors do not logically depend on each other. T007/T008 (`implement.yml`) can proceed in parallel with User Story 1's `watchdog.yml` chain (different file); T009–T017 (`watchdog.yml`) should follow User Story 1's chain.
- **User Story 3 (Phase 5)**: No code dependency (research.md: no change needed) — T018 can proceed at any time, but the story's actual correctness proof is User Story 4's T026/T029.
- **User Story 4 (Phase 6)**: Depends on User Stories 1 and 2 (T001–T017) — every fixture executes their real shipped steps.
- **User Story 5 (Phase 7)**: Independent of all code; recommended after Phase 3/4 so the amended text describes shipped, not planned, behavior.
- **Polish (Phase 8)**: Depends on all preceding phases.

### Parallel Opportunities

- T007 (`implement.yml`, cycle leg) can run in parallel with User Story 1's entire `watchdog.yml` chain.
- Within User Story 5, T044 (`contracts/watchdog-workflow.md`) and T045 (`quickstart.md`) can run in parallel with each other and with the T031→…→T043 `spec.md`/`data-model.md` chain, once that chain is far enough along to know what the docs should say.
- User Story 3's T018 (`quickstart.md`) can run in parallel with anything — it depends on nothing.

---

## Parallel Example: User Story 2 kickoff

```bash
# Launch the implement.yml leg alongside User Story 1's watchdog.yml chain:
Task: "Add 'Record cycle outcome for watchdog (cycle)' after 'Read back cycle outcome' in implement.yml"
Task: "In watchdog.yml's Compute fingerprint step, expose the valid cited-ids array as a new output"
```

---

## Implementation Strategy

### MVP First

Per spec.md, User Stories 1, 2, and 3 are all P1 — and User Story 3's own text makes it a correctness *bound* on the other two ("must be specified and fixture-checked before either story ships, not after"), so the practical MVP is all three P1 stories plus the specific User Story 4 fixture (T026/T029) that proves User Story 3 holds:

1. Complete Phase 3 (User Story 1) — the overlap-matching engine.
2. Complete Phase 4 (User Story 2) — the gate-suite filing condition.
3. Complete T018 (User Story 3's doc scenario) and T019–T029 (enough of User Story 4 to prove all three P1 stories, including the `{stage, tool}` separation fixture).
4. **STOP and VALIDATE**: `python3 .github/scripts/run-local-gates.py verify-watchdog-overlap-fanout` passes; the three quickstart scenarios for #729/#732/#765, run 36484099706, and #761/#764/#780 all match spec.md's stated outcomes.

Phase 7 (User Story 5, governing-document text) and the remainder of Phase 6/Phase 8 can land after, following the MVP.

### Incremental Delivery

1. User Story 1 → partial-overlap matching alone (no gate-suite awareness yet) — already collapses #729/#732/#765.
2. Add User Story 2 → run 36484099706's six-class fan-out stops reaching the board.
3. Add User Story 4's fixtures → both are proven, not merely claimed, and the `{stage, tool}` separation is proven undisturbed.
4. Add User Story 5 → FR-012–FR-016 and the amended spec 015 documents describe the shipped rule.
5. Polish → full consistency sweep, FR-025 compliance confirmed.

### Parallel Team Strategy

With two contributors (this run's shared-usage-window constraint caps concurrent local agents at two — see CLAUDE.md): one takes the User Story 1 → User Story 2 `watchdog.yml` chain sequentially (T001–T017, same file throughout); the other takes `implement.yml` (T007–T008) first, then User Story 5's spec-015 amendment chain (T031–T045) once enough of the first contributor's work has landed to describe accurately. User Story 4's fixture work (T019–T030) is a natural third slice once both code chains are done.

## Review Gate Round 1 Findings

- [X] Review finding: cycle/retry cycle-outcome artifacts collide under one name

  implement.yml's new (cycle) and (retry) 'Record/Upload cycle outcome for watchdog' steps both upload artifact name wing-commander-cycle-outcome and both run in the same job when a retry fires, so the retry leg's upload silently fails and watchdog reads stale pre-retry converged/handoff/gate-suite-outcome state.

  - .github/workflows/implement.yml

  Detail: 'Read back cycle outcome' (id: outcome) runs whenever steps.lifecycle-gate.outputs.is-open=='true' && steps.guard.outputs.skip!='true' (i.e. essentially every active job run); 'Read back retry outcome' (id: retry-outcome) runs additionally whenever steps.retry.outcome is 'success' or 'failure' -- these are not mutually exclusive, contradicting the PR's own comment above the (retry) upload step. Elsewhere in the same file the established convention for artifacts producible twice per job (claude-execution-output-cycle/-retry, metrics-record-cycle/-retry, see implement.yml ~lines 1135-1167 and 1895-1926) uses distinct suffixed names specifically to avoid this; a nearby comment at implement.yml:2384 confirms the team already knows 'upload-artifact v4+ refuses a name that already exists' in one run.

- [X] Review finding: stale collector-count wording in Gate 19 fixture

  verify-gate-19.py's AGGREGATE_CASES still say 'the other eight succeeded' and 'all nine collector STEPS outright error' after this PR bumped COLLECTOR_IDS from 9 to 10 entries by adding collect-cycle-outcome.

  - .github/scripts/verify-gate-19.py

  Detail: COLLECTOR_IDS now has 10 entries (collect-cycle-outcome added) but the 'name'/'why' strings in the second and third AGGREGATE_CASES entries were not updated from nine/eight to ten/nine.

## Review Gate Round 2 Findings

- [X] Review finding: Load triage decision never forwards cited-ids/matched-on/other-matches

  The act job's Load triage decision step (watchdog.yml:3686-3726, id: decision) reads the persisted triage-decision JSON but never echoes cited-ids, matched-on, or other-matches to $GITHUB_OUTPUT in either branch, even though Ensure pipeline-defect issue and Report finding to lifecycle issue consume steps.decision.outputs.cited-ids/.matched-on/.other-matches (watchdog.yml:3852-3854, 3959).

  - .github/workflows/watchdog.yml

  Detail: Persist triage decision (around line 3461-3502) writes cited-ids/matched-on/other-matches into watchdog-triage-decision.json, but Load triage decision (3692-3703 found-artifact branch, 3706-3724 missing-artifact fallback) has no echo line for any of the three fields, so steps.decision.outputs.cited-ids/.matched-on/.other-matches are always empty.

## Review Gate Round 3 Findings

- [X] Review finding: gh issue list --json comments can silently truncate an issue's matchable id set

  The new overlap-matching Dedup search step reads comments via gh issue list --json comments, which this repo's own Gate 112 treats as unreliable for nested comment data (first-page-only GraphQL read) everywhere else, but Gate 112's regex only catches gh issue|pr view, not gh issue list, so this new read has no guard and no consuming test exercises real gh pagination.

  - .github/workflows/watchdog.yml
  - .github/scripts/verify-lifecycle-merge-preconditions.py
  - specs/109-watchdog-finding-fanout/research.md

  Detail: Dedup search's new --json number,state,body,comments call (watchdog.yml, 'Dedup search' step) only guards total issue count (total_count -eq 200 -> outcome=unknown), not per-issue comment count; research.md's 'Decision: Overlap matching reads every candidate's accumulated id set from ONE bulk gh issue list call' asserts gh issue list --json comments 'returns each candidate's full comment list' without qualification, the same assumption Gate 112/#826 exists to forbid for gh issue|pr view --json comments.

- [X] Review finding: Two new collect job outputs are declared but never consumed

  collect job outputs cycle-outcome-gate-suite-outcome and cycle-outcome-gate-suite-first-failure are wired from the new collect-cycle-outcome step but no step in triage or act reads needs.collect.outputs.cycle-outcome-gate-suite-outcome or ...-first-failure anywhere in the repo.

  - .github/workflows/watchdog.yml

  Detail: watchdog.yml lines 377-378 declare the outputs; repo-wide grep for both exact strings finds only their own declaration/assignment line, no consumer. The gate-suite-failure fact that matters for filing logic already reaches Gate-suite filing condition and diagnose via the gate-suite-failure signal pushed into signals.json.

- [X] Review finding: Redundant join-then-split round trip in the overlap-matching jq pipeline

  The new matchable-id computation in Dedup search joins each occurrence's scanned ids into a comma string with join(",") and then immediately splits that same string back apart with split(",") on the next line, a no-op serialize/deserialize with no effect besides obscuring the pipeline.

  - .github/workflows/watchdog.yml

  Detail: map([scan("signal-ids=([^ ]+)")] | map(.[0]) | join(",")) immediately followed by map(split(",") | map(select(length>0))) inside the overlap_matches jq program in the 'Dedup search' step.
