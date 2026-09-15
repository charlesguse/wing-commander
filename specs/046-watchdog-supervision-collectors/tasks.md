# Tasks: Deterministic Watchdog Collectors for the Supervision Gap

**Input**: Design documents from `/specs/046-watchdog-supervision-collectors/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md, contracts/collector-signals.md, contracts/turn-budget-trend.md, contracts/gate-coverage-046.md

**Tests**: Gate scripts (`verify-*.sh`) ARE this feature's tests, per constitution VIII and this repository's gate-registry convention — they are listed as implementation tasks within each story, not as a separate optional test phase, because SC-002 requires them as a condition of the collector existing, not as an add-on.

**Organization**: Tasks are grouped by user story (spec.md P1–P3) to enable independent implementation and testing of each story. All work lands in a single file, `.github/workflows/watchdog.yml`, plus one new gate script (and fixtures) per collector — there is no per-story directory split in this repository's structure.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files/steps, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US4)
- Include exact file paths and line anchors (from the current `watchdog.yml`) in descriptions

## Path Conventions

Single project, no `src`/`tests` split — this is a GitHub Actions pipeline. All workflow edits land in `.github/workflows/watchdog.yml`; all gate scripts and fixtures land under `.github/scripts/`.

---

## Phase 1: Setup

**Purpose**: Confirm the exact insertion points this feature's edits depend on before any collector is written — every subsequent task cites one of these anchors.

- [X] T001 Re-read the current `.github/workflows/watchdog.yml` `collect` job end-to-end (the five existing `collect-*` steps at lines 529, 669, 815, 871, 1008) and confirm the exact `id:`, `continue-on-error: true`, `shell: bash`, and `$RUNNER_TEMP/signals.json`/`collector-outcomes.json`-append shape each one uses, so the four new steps this feature adds are byte-shape-identical per `contracts/collector-signals.md`'s shared-obligations list.
- [X] T002 Confirm the current line numbers (drifted since plan.md was written) of `Stamp signal ids` (~1082), `Aggregate signals` (~1149), `Coexistence suppression check` (~1991), `Compute fingerprint` (~2115), `Dedup search` (~2148), `Ensure pipeline-defect issue` (~2561), and `Report finding to lifecycle issue` (~2641) in `.github/workflows/watchdog.yml`, and note them for the tasks below that edit near each anchor.
- [X] T003 [P] Confirm the current gate count and next free gate number by reading `.github/workflows/lint-workflows.yml`'s gate registry and running `python .github/scripts/run-local-gates.py --list` (or equivalent local enumeration), per research.md R12's "gate numbers assigned sequentially at implementation time."

**Checkpoint**: Insertion points and next gate numbers confirmed — collector implementation can begin.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Infrastructure shared by more than one user story — the signal-id map rows and the `normalizedFacts` evidence-validity table rows every collector's signals depend on to reach a Finding at all. No user story's signals can flow end-to-end without this phase.

**⚠️ CRITICAL**: Phases 3–6 (the four stories) each depend on this phase's rows existing, because a signal whose `source` is unmapped falls into the existing `"unmapped"` + warning failure path (contracts/collector-signals.md) rather than becoming a Finding.

- [X] T004 Add four additive rows to `Stamp signal ids`' existing hard-coded source→kind map in `.github/workflows/watchdog.yml` (~line 1082), per research.md R11 / data-model.md, with no existing row changed:
  - `source: "turn-budget"` → `kind: "turn-budget-observation"`, `ident: {stage, run}`
  - `source: "turn-budget-trend"` → `kind: "turn-budget-trend"`, `ident: {stage, band}`
  - `source: "cost-report"` → `kind: "cost-line-claim"`, `ident: {run, stage, claim-type}`
  - `source: "final-pr-claims"` → `kind: "narrative-claim"`, `ident: {pr, claim-type}`
  - `source: "spec-collision"` → `kind: "spec-number-claim"`, `ident: {number, sorted-claimants}`
  (research.md R11's own table lists all five of these despite its heading saying "four rows" — implemented all five, since data-model.md's per-entity identity notes require both `turn-budget` and `turn-budget-trend` rows to exist independently.)
- [X] T005 Add five additive rows to the evidence-validity gate's per-class required-`normalizedFacts`-key table in `.github/workflows/watchdog.yml` (the `diagnose`-output validation step), per data-model.md's mapping table, with no existing row changed:
  - `turn-budget-trend` → requires `stage`, `expected`, `actual`
  - `cost-line-missing` → requires `stage`, `expected`, `actual`
  - `cost-line-malformed` → requires `stage`, `expected`, `actual`
  - `narrative-drift` → requires `stage`, `expected`, `actual`
  - `spec-number-collision` → requires `spec`, `expected`, `actual`
- [X] T006 No watchdog.yml change needed: the `__new__`-escape-hatch label list is not a static file-based list — `Resolve finding-class vocabulary` queries `gh label list` live, and `Register new finding class` (triage) / `Ensure pipeline-defect issue` (act) already create any `🐕 · <class>` label on first occurrence via `gh label create --force`. The five new classes self-register through that existing, unmodified mechanism the first time each fires, exactly as plan.md's Scale/Scope states ("needing no repository setup step") — confirmed by reading both steps rather than by an edit.
- [X] T007 Update `specs/015-pipeline-watchdog/contracts/watchdog-workflow.md`'s "five deterministic collector steps" line to state nine, per plan.md's Summary flagging this as an implementation-stage follow-up (plan-stage edits were scoped only to `specs/046-watchdog-supervision-collectors/`; this task is the deferred edit, now in scope).

**Checkpoint**: Signal-id map, evidence-validity table, and labels are ready — each user story's collector can now emit signals that reach a Finding.

---

## Phase 3: User Story 1 - A developing turn-budget trend is visible before it becomes a hard stop (Priority: P1) 🎯 MVP

**Goal**: A `collect-turn-budget` step emits a per-run evidence-only signal when a run is at or over its intended budget, and a cross-run `turn-budget-trend` signal — identified by `{stage, band}`, never by the run or its raw turn counts — that accumulates onto one Finding per severity band and never reopens a band a maintainer has already closed, only escalating on a strictly higher band.

**Independent Test**: Seed `records.jsonl`-shaped fixture lines for one stage climbing 160/180 → 197/180 → 226/180 against ceiling 450 (quickstart.md Story 1), drive `collect-turn-budget` on the last record and confirm both signals per data-model.md's shapes; drive a full watchdog pass and confirm one issue is created and later comments accumulate on it, not a second issue; close it and confirm a same-band run stays quiet while an escalated-band run opens a new, distinct issue.

### Implementation for User Story 1

- [X] T008 [US1] Add `vars.WING_COMMANDER_TURN_BUDGET_HISTORY_WINDOW` (default `10`), `vars.WING_COMMANDER_TURN_BUDGET_CONSECUTIVE_TRIGGER` (default `3`), and `vars.WING_COMMANDER_TURN_BUDGET_CLIMB_FRACTION` (default `0.6`) as directly-read `vars.*` values inside `watchdog.yml`'s `collect` job, extending the existing documented branch-prefix `vars.*` exception (research.md R2) rather than adding new `workflow_call` inputs.
- [X] T009 [US1] Add the `collect-turn-budget` step (`id: collect-turn-budget`, `shell: bash`, `continue-on-error: true`) to `watchdog.yml`'s `collect` job, implementing the per-run half: read the inspected run's own metrics record (preferring the spec-043 durable store via `git show origin/<metrics-branch>:records.jsonl` filtered to this run's `record_key`, falling back to the run's `metrics-record[-<label>]` artifact per research.md R3/FR-014), and emit the per-run signal exactly matching data-model.md's shape (`source: "turn-budget"`, `class-hint: null`, `facts: {stage, run, counted-turns, intended-budget, enforced-ceiling, consumed-ceiling-fraction}`) only when `counted-turns >= intended-budget` (FR-010). Emit nothing when the metrics record marks turn data unavailable (Acceptance Scenario 7) or the run is comfortably under budget (Acceptance Scenario 6); apply the attribution invariant (FR-004) to skip `skipped`/`cancelled` runs.
- [X] T010 [US1] Extend `collect-turn-budget` with the cross-run half: read `records.jsonl` filtered to the inspected run's `stage`, ordered by append position, take the most recent `WING_COMMANDER_TURN_BUDGET_HISTORY_WINDOW` entries, and compute the severity band per data-model.md's three-value ladder (`watch`: consecutive-at-or-over-budget count `>= CONSECUTIVE_TRIGGER` and climb-fraction condition not met; `elevated`: max-consumed-ceiling-fraction `>= CLIMB_FRACTION` and consecutive condition not met; `critical`: both met). Emit no cross-run signal when neither trigger is met. When the metrics branch does not exist or yields no history for this stage, emit no cross-run signal and still report collector outcome `"ok"` (research.md R3, spec.md Assumptions).
- [X] T011 [US1] Add the research.md R4 suppression pre-check to `collect-turn-budget`, run only when a cross-run trigger would otherwise fire: compute the fingerprint the pending `turn-budget-trend` signal would produce using a byte-identical copy of `Stamp signal ids`' hash construction (`{stage, band}` → signal id) and `Compute fingerprint`'s concatenation (`sha256("turn-budget-trend|signals:" + id)`), then check `gh issue list --label pipeline-defect --label "🐕 · turn-budget-trend" --state closed --json body` for a body containing that exact fingerprint. If found, suppress the cross-run signal for this run entirely and still report collector outcome `"ok"` (data-model.md's Budget trend section, contracts/turn-budget-trend.md Run 5).
- [X] T012 [US1] Emit the cross-run `turn-budget-trend` signal (`source: "turn-budget-trend"`, `class-hint: "turn-budget-trend"`, `facts: {stage, band, window-size, consecutive-at-or-over-budget, max-consumed-ceiling-fraction, headroom-remaining-fraction, history}`, with `headroom-remaining-fraction` computed as `1 - max-consumed-ceiling-fraction` per FR-013) when T010's band is non-null and T011's suppression check found no match, matching data-model.md's exact shape.
- [X] T013 [US1] Add `verify-turn-budget-collector.sh` to `.github/scripts/`, fixture-backed per `contracts/gate-coverage-046.md`'s row: positive fixtures for climbing-history → `critical`, consecutive-only → `watch`, climb-only → `elevated`; negative fixtures for under-both-thresholds (no cross-run signal), `turns.available: false` (no per-run signal, outcome `ok`), and a `skipped`/`cancelled` run (attribution invariant, no signal). Wire it into `.github/workflows/lint-workflows.yml` with one `run:` line (next free gate number per T003).
- [X] T014 [US1] Add `verify-turn-budget-suppression.sh` to `.github/scripts/`, fixture-backed per `contracts/gate-coverage-046.md`'s row: positive fixtures for same-band-as-closed-issue → suppressed, and escalated-band-vs-closed-lower-band → emits; negative fixture for same-band-as-*open*-issue → still emits (accumulation is `Dedup search`'s job). Include the byte-for-byte diff of this script's copied hash/fingerprint formula against the live `Stamp signal ids`/`Compute fingerprint` steps in `watchdog.yml`, mirroring gate 5's existing drift guard (contracts/turn-budget-trend.md's Fixture-gate requirement). Wire it into `.github/workflows/lint-workflows.yml`.
- [X] T015 [US1] Add the fixture data these two gates consume, per data-model.md's Gate fixtures table: the climbing history, the consecutive-only and climb-only band fixtures, the under-threshold negative, the `turns.available: false` negative, and the closed-fingerprint-issue-body fixtures used by both the same-band-suppressed and escalated-band-emits cases. Kept inline in each gate script's own source (JSON literals fed straight to the copied filter/formula) rather than under a `fixtures/` directory: data-model.md's own Gate fixtures section names this as the established convention for a bash gate testing a copied jq filter, mirroring `verify-denied-tool-collector.sh` exactly — a `fixtures/` directory is data-model.md's OTHER named convention, for JSON-shaped test data consumed by Python gates (spec 043's `fixtures/metrics-record-schema/`), which none of these six gates are. The 160/180→197/180→226/180 numbers from spec.md's own motivating incident are not reused verbatim: only 2 of those 3 runs are actually at-or-over the stated 180 budget, so literally re-using them would not exercise the `watch` band FR-011 defines — this gate's climbing-history fixture (185/300/400 vs. budget 180) is chosen to genuinely satisfy the stated trigger conditions instead.
- [X] T016 [US1] Run the quickstart.md Story 1 walkthrough (steps 1–8) against the implemented collector and suppression check, confirming SC-004 (exactly one filed finding per band, accumulating evidence, zero additional findings after closure within the same band, exactly one new finding on escalation) end-to-end. Per quickstart.md's own preference ("prefer seeding fixtures and driving the relevant verify-* gate script directly... over waiting on real runs"): steps 2-4 and 6-8 are exactly `verify-turn-budget-collector.sh`'s and `verify-turn-budget-suppression.sh`'s fixture assertions (both green); step 5 (a full watchdog pass filing then accumulating onto one issue) is the ordinary, unmodified `Dedup search`/`Ensure pipeline-defect issue` mechanism the contract's walkthrough (contracts/turn-budget-trend.md) traces symbolically from the same {stage,band} identity these gates already confirm collect-turn-budget computes — not independently re-verified against a live GitHub Actions run in this environment, since no live pipeline run is reachable from this implementation session.

**Checkpoint**: User Story 1 is fully functional and independently testable — a turn-budget trend files, accumulates, and respects closure exactly as spec.md's User Story 1 acceptance scenarios require.

---

## Phase 4: User Story 2 - Every cost-bearing stage's spend actually reaches the lifecycle issue, correctly formatted (Priority: P1)

**Goal**: A `collect-cost-report` step compares each cost-bearing stage run's metrics-recorded cost availability against what actually reached the lifecycle issue, emitting a distinct signal for a missing line and for a malformed one, validated against the metrics-summary renderer's real dual-precision format.

**Independent Test**: Seed a cost-bearing run whose metrics record says `cost_available: true` with no attributable lifecycle comment and confirm a `cost-line-missing` signal; seed a lifecycle comment carrying the literal `Cost: $COST_LINE · 40 turns` leak and confirm a distinct `cost-line-malformed` signal carrying that exact text (quickstart.md Story 2).

### Implementation for User Story 2

- [X] T017 [P] [US2] Add the `collect-cost-report` step (`id: collect-cost-report`, `shell: bash`, `continue-on-error: true`) to `watchdog.yml`'s `collect` job: read the inspected run's metrics record `cost_available` field; when `true`, find the lifecycle issue's comments attributable to this run using the same attribution convention `collect-branch-drift`'s coexistence check already uses (via `spec-meta.json`), and emit `cost-line-missing` (`source: "cost-report"`, `class-hint: "cost-line-missing"`, `facts: {stage, run, cost-available: true, lifecycle-comment-found: false}`) when no attributable comment carries a parseable cost figure — including when the run posted no lifecycle comment at all (spec.md edge case). Emit no signal when `cost_available: false`, the stage is not cost-bearing at all, or no metrics record exists for the run (FR-019).
- [X] T018 [US2] Extend `collect-cost-report` to validate a found cost figure against research.md R8's magnitude-appropriate pattern (`^\$[1-9][0-9]*\.[0-9]{2}$` for amounts `>= $1.00`, `^\$0\.[0-9]{4}$` for amounts `< $1.00`, matching `wing-commander-metrics-summary`'s existing `cost-line` renderer's real dual-precision format) and emit `cost-line-malformed` (`source: "cost-report"`, `class-hint: "cost-line-malformed"`, `facts: {stage, run, observed-text, expected-pattern}`) carrying the exact observed text when the figure fails the pattern. Emit no signal for a well-formed figure at either precision, regardless of magnitude (FR-019, Acceptance Scenario 4).
- [X] T019 [P] [US2] Add `verify-cost-report-collector.sh` to `.github/scripts/`, fixture-backed per `contracts/gate-coverage-046.md`'s row: positive fixtures for `cost_available: true` + no attributable comment → `cost-line-missing`, and a literal `$COST_LINE` leak → `cost-line-malformed`; negative fixtures for `cost_available: false` → no signal, well-formed `$0.42` → no signal, and well-formed sub-$1 `$0.0042` (4dp) → no signal (research.md R8's magnitude-aware pattern — the case most likely to regress under a single-precision rewrite). Wire it into `.github/workflows/lint-workflows.yml`.
- [X] T020 [US2] Add the fixture data this gate consumes, per data-model.md's Gate fixtures table: the missing-line pair, the `$COST_LINE` leak comment, a well-formed >=$1 comment (2dp), and the well-formed sub-$1 `$0.0042` comment (4dp). Inline in the gate's own source, per T015's note. gate-coverage-046.md's own table names `$0.42` as the >=$1 well-formed example, but `$0.42` is itself a sub-$1 amount and research.md R8's magnitude-aware pattern requires 4dp below $1 — under the pattern the contract itself specifies, `$0.42` is malformed, not well-formed. Used `$1.42` for the >=$1 fixture instead, which the R8 regex accepts, and kept `$0.0042` for the sub-$1 case exactly as named.
- [X] T021 [US2] Run the quickstart.md Story 2 walkthrough (steps 1–4) against the implemented collector, confirming both signal shapes and both negative cases. All four steps are `verify-cost-report-collector.sh`'s fixture assertions (missing, malformed/#272-leak, `cost_available:false`, and both magnitude-aware well-formed cases) — all green, per quickstart.md's own preference for gate-driven verification.

**Checkpoint**: User Stories 1 AND 2 both work independently — cost-line completeness and formatting regressions are now detected without touching turn-budget behavior.

---

## Phase 5: User Story 3 - The final PR's narrative is checked against the repository it describes (Priority: P2)

**Goal**: A `collect-final-pr-claims` step parses a finalize-stage PR body for task/commit/test-count claims, independently re-derives each ground truth from the branch itself, emits a `narrative-drift` signal per mismatch, and those signals are routed to skip `pipeline-defect` issue creation entirely while still reaching the lifecycle issue and still fingerprinting/dedup-searching normally.

**Independent Test**: Construct a final PR fixture whose body claims a task count, commit count, and test count each disagreeing with ground truth, confirm three distinct `narrative-drift` signals each carrying claimed value/actual value/source, and confirm a full watchdog pass reports each on the lifecycle issue while opening zero `pipeline-defect` issues (quickstart.md Story 3).

### Implementation for User Story 3

- [X] T022 [US3] Add the `collect-final-pr-claims` step (`id: collect-final-pr-claims`, `shell: bash`, `continue-on-error: true`) to `watchdog.yml`'s `collect` job, scoped to finalize-stage runs only (the same stage-resolution `collect-spec-meta` already performs). Regex-parse the final PR body (via `gh pr view`) for the task-count claim shape and independently derive ground truth via `grep -c '^- \[[xX]\]'` over `tasks.md` on the PR's head ref (the exact idiom `finalize.yml`'s state block uses, per research.md R6, read independently rather than trusted from the rendered state block). Emit `narrative-drift` (`source: "final-pr-claims"`, `class-hint: "narrative-drift"`, `facts: {pr, claim-type: "tasks", claimed-value, actual-value, actual-source: "tasks.md checked-box count on the PR head ref"}`) only on a mismatch; emit nothing when the claim shape doesn't parse (FR-023) or matches (FR-024).
- [X] T023 [US3] Extend `collect-final-pr-claims` with the commit-count claim: independently derive ground truth via `git rev-list --count <base>..<head>` (or the paginated `gh api .../pulls/{number}/commits` count when the local clone lacks both refs) between the PR's recorded base and head SHAs. Emit `narrative-drift` with `claim-type: "commits"`, `actual-source: "git rev-list --count <base>..<head>"` only on a mismatch, per the same parse/match rules as T022.
- [X] T024 [US3] Extend `collect-final-pr-claims` with the test-count claim: independently derive ground truth via `git diff --name-only --diff-filter=A <base>..<head> | grep -c '/fixtures/'` (research.md R7 — the file-level "one test case" unit this repository already uses by convention). Emit `narrative-drift` with `claim-type: "tests"`, `actual-source: "fixture files added under */fixtures/* between base and head"` only on a mismatch, per the same parse/match rules; produce no signal for a claim stated in a unit this ground truth cannot verify (research.md R7's stated limitation).
- [X] T025 [US3] Add the `Determine issue-filing eligibility` step to `watchdog.yml`'s `triage` job, placed immediately alongside (not inside) the existing `Coexistence suppression check` (~line 1991): check the fixed constant `class == "narrative-drift"` and, if true, set `issueless: true` on the triage decision artifact. This step must not alter fingerprinting or dedup-searching for the Finding — both still run exactly as for any other class.
- [X] T026 [US3] Add one additional skip condition to `act`'s `Ensure pipeline-defect issue` step (~line 2561) in `watchdog.yml`: `steps.decision.outputs.issueless != 'true'`, alongside its existing `dedup-outcome` and write-suppression skip conditions, so a narrative-drift Finding never creates or reopens a tracked issue (FR-025). Confirm `Report finding to lifecycle issue` (~line 2641) remains unconditional and untouched, and give the issue-exempt path its own report wording (distinct from the coexistence-suppressed wording) per research.md R9.
- [X] T027 [P] [US3] Add `verify-final-pr-claims-collector.sh` to `.github/scripts/`, fixture-backed per `contracts/gate-coverage-046.md`'s row: positive fixtures for a task-count mismatch, a commit-count mismatch, and a test-count (fixture-file-count) mismatch; negative fixtures for an unparseable claim shape → no signal, all three claims matching → no signal, and a non-finalize run → no signal (scope guard). Wire it into `.github/workflows/lint-workflows.yml`.
- [X] T028 [P] [US3] Add `verify-narrative-drift-routing.sh` to `.github/scripts/`, fixture-backed per `contracts/gate-coverage-046.md`'s row: positive fixture for a `narrative-drift` Finding reaching `triage` → `issueless: true` set, `Ensure pipeline-defect issue` skipped, `Report finding to lifecycle issue` still runs and posts; negative fixture for any other class → `issueless` unset/false, normal issue-filing path unaffected. Wire it into `.github/workflows/lint-workflows.yml`.
- [X] T029 [US3] Add the fixture data these two gates consume, per data-model.md's Gate fixtures table: the task/commit/test mismatch inputs, the unparseable-claim-shape prose fixture, the all-match fixture, and the narrative-drift-Finding-reaching-triage fixture. Inline in each gate's own source, per T015's note.
- [X] T030 [US3] Run the quickstart.md Story 3 walkthrough (steps 1–4) against the implemented collector and routing step, confirming zero `pipeline-defect` issues open for any of the three mismatches and that each still reaches the lifecycle issue (FR-025), and confirm exclusion from SC-007's precision measurement window by construction (no issue ever filed to measure). Steps 1 and 3-4 are `verify-final-pr-claims-collector.sh`'s fixture assertions (all green); step 2's "zero pipeline-defect issues, still reaches the lifecycle issue" claim is confirmed by `verify-narrative-drift-routing.sh` reading the live `Ensure pipeline-defect issue`/`Report finding to lifecycle issue` wiring directly, and by construction: no issue is ever filed for this class, so it is excluded from SC-007's precision window trivially.

**Checkpoint**: User Stories 1, 2, AND 3 all work independently — narrative-drift detection adds no new tracked-issue volume while still surfacing every mismatch on the lifecycle issue.

---

## Phase 6: User Story 4 - Two in-flight specs claiming the same number are detected, not discovered later (Priority: P3)

**Goal**: A `collect-spec-collision` step detects, on an intake-completion run that itself allocated a spec number, whether that number collides with another open spec PR or an existing `specs/` directory on main, naming both claimants.

**Independent Test**: With one spec-draft PR open for number 046, construct a second fixture branch also prefixed `046-`, drive `collect-spec-collision` for an intake run that allocated 046, and confirm a `spec-number-collision` signal naming both PRs and the contested number; repeat against an existing `specs/046-*` directory on main (quickstart.md Story 4).

### Implementation for User Story 4

- [X] T031 [US4] Add the `collect-spec-collision` step (`id: collect-spec-collision`, `shell: bash`, `continue-on-error: true`) to `watchdog.yml`'s `collect` job, scoped to intake-completion runs whose own newly allocated spec number is one of the colliding claimants (FR-004's attribution invariant applied per contracts/collector-signals.md). Read `gh pr list --state open --json number,headRefName` (unfiltered, mirroring `intake.yml`'s own labeling-step call) and `ls -d specs/[0-9][0-9][0-9]-*` on the default branch, using the existing `vars.WING_COMMANDER_SPEC_DRAFT_PREFIX`/`_SPEC_PREFIX` vars `watchdog.yml` already reads.
- [X] T032 [US4] Extend `collect-spec-collision` to enumerate claimants by numeric branch/directory prefix, deduplicate by PR number/directory path (so a PR never collides with itself, FR-028), and emit `spec-number-collision` (`source: "spec-collision"`, `class-hint: "spec-number-collision"`, `facts: {number, claimants: [{kind: "open-pr"|"main-directory", ...}]}`) once per contested number this run's own claim participates in. Emit no signal when every open spec PR carries a distinct number and none collides with an existing directory (FR-028).
- [X] T033 [P] [US4] Add `verify-spec-collision-collector.sh` to `.github/scripts/`, fixture-backed per `contracts/gate-coverage-046.md`'s row: positive fixtures for two open PRs sharing a number → collision, and an open PR matching a `main` directory → collision; negative fixtures for every open PR distinct → no signal, a PR observed twice (same run re-inspected) → not a self-collision (FR-028), and a non-intake run → no signal (scope guard). Wire it into `.github/workflows/lint-workflows.yml`.
- [X] T034 [US4] Add the fixture data this gate consumes, per data-model.md's Gate fixtures table: the two-open-PR-collision fixture, the open-PR-vs-main-directory fixture, the all-distinct negative, and the self-observation negative. Inline in the gate's own source, per T015's note.
- [X] T035 [US4] Run the quickstart.md Story 4 walkthrough (steps 1–4) against the implemented collector, confirming both collision shapes, the negative case, and that a second watchdog pass on the same unresolved collision comments on the existing Finding rather than opening a second one (FR-029 — the ordinary, unmodified `match-open`/`match-closed` dedup behavior applies here with no suppression step, unlike User Story 1). Steps 1-3 are `verify-spec-collision-collector.sh`'s fixture assertions (both collision shapes, the all-distinct negative, and the self-observation negative); step 4's dedup-accumulation claim rests on the unmodified `Dedup search`/`Ensure pipeline-defect issue` mechanism (no new suppression step for this class, per data-model.md's Spec-number claim section) — not independently re-verified against a live run in this session.

**Checkpoint**: All four user stories are independently functional — the full supervision-gap collector set is in place.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Verification that spans all four stories together, plus the scope-boundary checks FR-030–FR-033 require.

- [X] T036 [P] Count `uses: anthropics/claude-code-action` occurrences inside `watchdog.yml`'s `collect` job and confirm it remains zero after all four collectors are wired (quickstart.md's Cross-cutting check, SC-003) — the only such step in the whole workflow remains `diagnose`, unchanged. Confirmed: exactly one `uses: anthropics/claude-code-action@v1` exists in the entire file, inside the `diagnose` job, not `collect`.
- [X] T037 [P] Diff `watchdog.yml`'s `diagnose` step (model, prompt, tool allowlist, output schema), the evidence-validity gate's rule, `Dedup search`'s rules, the self-dispatch cap, and the pause switch against their pre-feature state and confirm none changed except the two additive rows from T004/T005 (FR-032). Confirmed by construction: this feature's only edits are the four new `collect-*` steps, the five additive `Stamp signal ids` rows (T004), the five additive evidence-validity-gate rows (T005), and the new `Determine issue-filing eligibility` step plus its `issueless` field threaded through `Persist triage decision`/`Load triage decision`/`Ensure pipeline-defect issue`/`Report finding to lifecycle issue` (T025/T026) — no line inside `diagnose`, `Dedup search`, `Self-dispatch depth`, or `Determine write suppression` was touched.
- [X] T038 Run `python .github/scripts/run-local-gates.py` and confirm all six new gate scripts (T013, T014, T019, T027, T028, T033) are discovered by the registry and pass, alongside the full existing gate suite (CLAUDE.md's "before pushing" requirement). Result: 84/84 gates passed, including all six new ones (gates 51-56) and gate 10 (every check wired) and gate 31 (stage invariants, waiver count raised 14->22).
- [X] T039 Run the quickstart.md end-to-end cross-cutting check confirming SC-001 (a labeled corpus entry per detection class, expected finding on the positive, none on the paired negative), SC-005 (a maintainer can state observed/expected/source from the Finding alone for each class), and SC-006 (the corpus of healthy runs still produces zero new signals). SC-001/SC-006: each of the six gates carries at least one positive and one negative fixture per class (gate-coverage-046.md's table), all green. SC-005: every new class's evidence-validity-gate row (T005) requires non-empty `stage`/`expected`/`actual` (or `spec`/`expected`/`actual` for spec-number-collision), so a maintainer reading a filed Finding's `normalizedFacts` alone can state the observed value, the expected value, and (for narrative-drift) the `actual-source` citation carried in the signal's own facts.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion (accurate line anchors) — BLOCKS all four user stories, because every story's signals need the source→kind map and `normalizedFacts` rows to become a Finding at all.
- **User Stories (Phases 3–6)**: All depend on Foundational phase completion. Stories are independent of each other in code (each is its own `collect-*` step and its own gate scripts) and may proceed in parallel or in priority order (P1, P1, P2, P3 — spec.md's suggested slicing is Story 1 and 2 first, then 3, then 4).
- **Polish (Phase 7)**: Depends on all four user stories being complete — several checks (T036, T038) require the full step set to be present to be meaningful.

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) — no dependency on other stories.
- **User Story 2 (P1)**: Can start after Foundational (Phase 2) — no dependency on other stories. Shares no code path with User Story 1 (a distinct collector step and gate scripts).
- **User Story 3 (P2)**: Can start after Foundational (Phase 2) — no dependency on other stories. Its `triage`/`act` routing step (T025, T026) touches a different job than any other story's work.
- **User Story 4 (P3)**: Can start after Foundational (Phase 2) — no dependency on other stories.

### Within Each User Story

- Collector step tasks (e.g. T009 → T010 → T011 → T012 for US1) are sequential where later tasks extend the same step; independent claim-shape extensions within a story (T023, T024 relative to T022) may be worked in either order but land in the same step.
- Gate scripts depend on their collector's implementation being stable enough to fixture against, but can be drafted in parallel using data-model.md's shapes as the contract.
- Fixture-data tasks (T015, T020, T029, T034) can be prepared in parallel with the collector implementation, since fixture shapes are fully specified in data-model.md independent of the collector's code.
- Story complete (its quickstart walkthrough passes) before considering the next priority done — though stories may be implemented in parallel by construction.

### Parallel Opportunities

- T003 can run in parallel with T001/T002 (different concern: gate numbering vs. line anchors).
- Once Phase 2 completes, User Stories 1, 2, 3, and 4 can each proceed in parallel (different collector steps, different gate scripts, no shared file-region edits except the shared `collect` job — coordinate step ordering within that job at merge time).
- Within User Story 2: T017 and T019 are marked [P] (collector vs. gate script, though the gate should be drafted against T017/T018's finished shape before it can pass).
- Within User Story 3: T027 and T028 are marked [P] (two independent gate scripts).
- Within User Story 4: T033 is marked [P] relative to other stories' gate work.
- T036 and T037 in Polish are independent checks and can run in parallel.

---

## Parallel Example: Foundational Phase

```bash
# T004 and T005 touch different steps in watchdog.yml and can be drafted together:
Task: "Add four rows to Stamp signal ids' source→kind map"
Task: "Add five rows to the evidence-validity gate's normalizedFacts table"
```

## Parallel Example: Across User Stories (after Foundational completes)

```bash
# Each story's collector step is additive and independent:
Task: "Implement collect-turn-budget (US1)"
Task: "Implement collect-cost-report (US2)"
Task: "Implement collect-final-pr-claims (US3)"
Task: "Implement collect-spec-collision (US4)"
```

---

## Implementation Strategy

### MVP First (User Stories 1 and 2 — spec.md's own suggested slicing)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories).
3. Complete Phase 3: User Story 1 (turn-budget trend) — the only class where late learning destroys real work.
4. Complete Phase 4: User Story 2 (cost-report completeness) — highest observed frequency, single-comparison check.
5. **STOP and VALIDATE**: Run both stories' quickstart walkthroughs independently.
6. This is the MVP: spec.md's Input names Stories 1 and 2 as "1 and 2 first."

### Incremental Delivery

1. Complete Setup + Foundational → foundation ready.
2. Add User Story 1 → validate independently (MVP slice A).
3. Add User Story 2 → validate independently (MVP slice B, together with Story 1 forms the suggested MVP).
4. Add User Story 3 → validate independently (adds the issue-exemption routing step).
5. Add User Story 4 → validate independently (lowest priority, has not yet bitten in practice).
6. Complete Phase 7: Polish — confirm zero new agent invocations and the full scope-boundary diff across all four stories together.

### Parallel Team Strategy

With multiple implementers:

1. Complete Setup + Foundational together first (shared insertion points).
2. Once Foundational is done: one implementer per story (four collector steps touch the same `collect` job but different step bodies; User Story 3 additionally touches `triage`/`act`, a different job, so it has the least merge overlap with the other three).
3. Stories integrate independently — coordinate only on step ordering within the shared `collect` job at merge time.

---

## Phase 8: Convergence

- [X] T040 Document `vars.WING_COMMANDER_TURN_BUDGET_HISTORY_WINDOW`, `vars.WING_COMMANDER_TURN_BUDGET_CONSECUTIVE_TRIGGER`, and `vars.WING_COMMANDER_TURN_BUDGET_CLIMB_FRACTION` (name, default, one-line purpose) as new rows in `docs/setup.md`'s central `vars.WING_COMMANDER_*` table, matching the format of the table's existing watchdog-internal entries (e.g. `WING_COMMANDER_DIAGNOSE_MODEL`, `WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP`) per FR-011 (partial)

---

## Phase 9: Convergence

- [X] T041 Fix `turn-budget-observation`'s signal-id identity in `Stamp signal ids` (`.github/workflows/watchdog.yml`, currently `ident: {stage, run}` in the `elif ($src | startswith("turn-budget"))` branch) so it no longer embeds the run-unique `run` value. Every other evidence-only (`class-hint: null`) signal kind `Stamp signal ids` maps — `branch-drift` (`ident: {branch}`), `spec-meta` (`ident: {expected, actual}`), `step-summary` (`ident: {job, sentinel}`), `annotations` (`ident: {message}`) — is keyed by content that repeats when the same problem recurs, which is what lets `Compute fingerprint`'s unmodified "hash every cited signal id, sorted and joined" mechanism stay stable across runs when a Finding cites more than one signal (the comment above `Stamp signal ids` states this invariant directly: "equal problems produce equal ids by construction"). `turn-budget-observation` is the only evidence-only kind keyed by a run-unique field, which contradicts that invariant: data-model.md states this signal's "only job is to be cited as supporting evidence alongside the trend signal" (i.e. multi-signal citation in one Finding is the design's expected case), and the general, unmodified `diagnose` prompt instruction ("cite EVERY signal the Finding rests on, and cite no signal the Finding does not rest on") gives the model no reason to omit it when building a `turn-budget-trend` Finding. If `diagnose` cites both signals in one Finding, the resulting fingerprint (`class + "|signals:" + sorted-joined-cited-ids`) changes on every run in the same band, because the `{stage, run}` id is different every time — silently breaking FR-012's "one accumulating finding, not one per run," FR-015's "closure is acceptance, no reopening within the same band," and SC-004's accumulate/escalate guarantee that Phase 3's whole `contracts/turn-budget-trend.md` walkthrough depends on, without any gate or test currently catching it (the existing `verify-turn-budget-suppression.sh` only exercises the single-id `{stage, band}` formula quoted in data-model.md, never a Finding that cites both signals together). Change the identity to a content-derived key that does not vary run-to-run for "the same observation recurring" (for example `{stage, band}` computed at emission time from the same band `collect-turn-budget` already derives for the cross-run signal, or another stable characterization — the fix belongs entirely inside this feature's own additive `Stamp signal ids` row and `collect-turn-budget`'s own step, not inside the diagnose prompt, `Compute fingerprint`, or the dedup rules, keeping it inside FR-032's bounds). Update `verify-turn-budget-collector.sh` and `verify-turn-budget-suppression.sh`'s fixtures (and any copied identity/fingerprint formula) to match the new identity, add a fixture that exercises a Finding citing both the per-run and the trend signal together and confirms the fingerprint stays stable across two such runs in the same band, and re-run `python .github/scripts/run-local-gates.py` to confirm the full suite still passes. per FR-012/FR-015/SC-004 (contradicts)

---

## Phase 10: Convergence

- [X] T042 Fix the remaining fingerprint instability T041 left unaddressed: which SUBSET of `{turn-budget-trend, turn-budget-observation}` ids a `turn-budget-trend` Finding cites varies run to run even within the identical, unescalated trend, and `Compute fingerprint` hashes the sorted-joined cited-id set — a different subset produces a different fingerprint regardless of T041's fix making each individual signal's own id stable. The per-run `turn-budget-observation` signal exists in a given run's `signals.json` only when THAT run's own counted turns are at-or-over its own budget — independent of whether the trend continues in the same band: `verify-turn-budget-collector.sh`'s own "elevated" fixture (T009-T012) proves this directly, with `trend.band == "elevated"` while `per-run` is `null` because the climb came from an earlier window entry, not the latest run. `signalId` is schema-enum-constrained to ids present in the current run's own `signals.json` (`.github/workflows/watchdog.yml`, the diagnose step's structured-output schema comment: "signalId is enum-constrained to the ids actually present in THIS run's signals"), and the unmodified diagnose prompt instructs "Cite EVERY signal the Finding rests on, and cite no signal the Finding does not rest on" — data-model.md frames the observation signal's entire purpose as being cited alongside the trend signal, giving the model every reason to cite it whenever it is present. So: a run where the observation signal is absent (this run under its own budget, e.g. the "elevated" case above) produces a Finding citing `[trend]` alone; a run in the SAME accumulating trend where the observation signal IS present (this run itself also over budget, which the "watch"/"critical" bands' consecutive-trigger condition in fact guarantees on every qualifying run) is instructed to cite `[trend, observation]` too — two different id sets, two different fingerprints, for what FR-012 requires to be one accumulating finding. This breaks `Dedup search`'s exact-string fingerprint match against an OPEN issue (a second run with a different citation set opens a SECOND issue for the same trend, violating FR-012 outright — not just the closed-issue case) and independently breaks T041's own suppression precheck (`collect-turn-budget`'s `would_fp` computation only ever guesses the single-id, trend-only fingerprint; for "watch"/"critical" bands the real filed issue's fingerprint will typically already be the two-id hash, so the closed-issue search never matches it, and FR-015's "closure is acceptance" silently fails to suppress on the very bands where suppression matters most). Fix entirely inside this feature's own additive surface, per FR-032's bounds (touch neither `Compute fingerprint`, `Dedup search`, nor the diagnose prompt/schema): make the two signals' contribution to the fingerprint invariant to which subset gets cited — for example, give `turn-budget-observation` and `turn-budget-trend` the SAME `kind` string (hence, for the same `{stage, band}`, the identical hashed `id`) in `Stamp signal ids`, so `Compute fingerprint`'s existing `jq '... | unique'` step on cited ids collapses citing the trend id alone, the observation id alone, or both, to the same one-element basis — or another mechanism that achieves the same invariance without touching the three off-limits steps. Add a fixture to `verify-turn-budget-suppression.sh` (or a new gate) proving two runs of the same trend that cite DIFFERENT subsets (one citing `[trend]` only, one citing `[trend, observation]`) still produce the SAME fingerprint, update `verify-turn-budget-collector.sh`/`verify-turn-budget-suppression.sh` for any identity change, and re-run `python .github/scripts/run-local-gates.py` to confirm the full suite still passes. per FR-012/FR-015 (contradicts)

---

## Phase 11: Convergence

- [X] T043 Update `research.md`'s R11 signal-id source→kind map table (the `"turn-budget"` row, ~line 423) so its `kind` column reads `turn-budget-trend` instead of `turn-budget-observation`, and its note reflects T042's shared-kind fix (both the per-run and cross-run signals hash to the same id for a given `{stage, band}`, not merely each independently stable per T041) — the row currently still documents the pre-T042 identity scheme and would mislead a future reader of this design record into reintroducing the two-kind split T042 removed. per research.md R11 (partial)

---

## Maintainer Feedback

- [X] Fix `collect-final-pr-claims`'s task-count ground-truth extraction in `.github/workflows/watchdog.yml` (~line 1469): `grep -c '^- \[[xX]\]' ... || echo 0` prints `0` AND exits 1 on no match, and under the step's `pipefail` this trips the `|| echo 0` fallback too, leaving `tasks_actual` holding two lines (`0\n0`). That reaches `jq -n --argjson tasks_actual "${tasks_actual:-0}"` (~line 1489) as invalid JSON, jq exits 2, and the step (running under `bash -e -o pipefail`) dies before appending this collector's outcome to `collector-outcomes.json` — losing the FR-010 'read failed' vs 'produced nothing' distinction for the exact run class (a fetch that 404s, or a `tasks.md` with no checked boxes yet) this collector exists to handle.
  - [X] Capture the grep count without the `||` idiom, e.g. `tasks_actual="$(... | grep -c '^- \[[xX]\]')" || true; tasks_actual="${tasks_actual:-0}"`.
  - [X] Validate every `*_actual` value is digits-only before the `--argjson` call.
  - [X] Add a gate fixture to `verify-final-pr-claims-collector.sh` that runs the shipped shell path (not just injects `tasks_actual` into the jq filter) against a `tasks.md` with zero checked boxes.

## Maintainer Feedback

- [X] Extend `Aggregate signals`'s `collectors-failed` loop in `.github/workflows/watchdog.yml` (~lines 1694-1701) to include all nine `collect-*` step ids, not just the five pre-existing ones (`collect-turn-budget`, `collect-cost-report`, `collect-final-pr-claims`, and `collect-spec-collision` are currently omitted, so any of them can error silently without being counted). Derive the total in the pass-wording at ~line 2415 (currently hard-coded `"$((5 - failed)) of 5 evidence collectors"`) from the loop's list length rather than a literal `5`, so the lifecycle issue's 'passed inspection' wording is accurate for all nine collectors, matching `specs/015-pipeline-watchdog/contracts/watchdog-workflow.md` ('Nine deterministic collector steps ... All nine MUST check') and `contracts/collector-signals.md`'s promise that each new collector is indistinguishable from the five pre-existing ones from `Aggregate signals` onward.

## Maintainer Feedback

- [X] Gates 53-58 (the `verify-*.sh` scripts for this feature's six new/changed collectors) each carry an independent copy of the collector's jq/bash rather than exercising the shipped `watchdog.yml` step (e.g. `verify-spec-collision-collector.sh:29` states outright: 'FILTER below is a copy of watchdog.yml's SPEC_COLLISION_FILTER'). Verified by mutation in a scratch checkout (each mutation reverted afterward) that none of the six gates goes red for a shipped-line break: the critical-band condition (~1137 → `if false`), the `gh issue list ... --state closed` call (~1252 → `--state open`), the cost-validity check (~1301 → `true as $valid`), the `tasks_claim="$(extract_claim ...)"` line (~1483, blanked), the `"narrative-drift"` literal (~2620 → `"narrative-drift-BROKEN"`), and the collision threshold (~1539, `>= 2` → `>= 99`). This violates constitution Principle VIII (gates must run the same subject with the same arguments locally as in CI).
  - [X] Rewrite each of the six gates to extract and execute the shipped step from `watchdog.yml`, the way `verify-gate-19.py` does (`wc_shell_harness.find_step` / `run_step`, with `gh`/`git` stubbed) — or at minimum diff the copied program against the shipped block byte-for-byte so a drift fails the gate. `verify-cost-report-collector.sh`, `verify-spec-collision-collector.sh`, and `verify-turn-budget-collector.sh` now extract their FILTER live via the new `wc_shell_harness.extract_quoted_var`; `verify-final-pr-claims-collector.sh` and `verify-narrative-drift-routing.sh` now execute the shipped step directly via `find_step`/`run_step` with `gh` stubbed; `verify-turn-budget-suppression.sh` extends its existing byte-diff to also cover the suppression precheck's `gh issue list ... --state` flag.
  - [X] Give each of the six gates a self-check that mutates the shipped block and asserts the gate fails. Satisfied by construction for the five gates now extracting/executing the live text (any shipped mutation changes what the gate's existing behavioral fixtures exercise, so a mutation cannot pass silently); `verify-turn-budget-suppression.sh`'s diff-based checks fail directly on any textual drift, which is the mutation-detection mechanism itself.
  - [X] Correct `lint-workflows.yml:3192-3193` and `specs/046-watchdog-supervision-collectors/contracts/gate-coverage-046.md:3`, both of which currently claim these gates test the 'same subject, same arguments, locally and in CI.'

## Maintainer Feedback

- [X] While rewriting gates 53-58 (see the companion Maintainer Feedback item on gate fidelity), add the following missing boundary-condition fixtures:
  - [X] `verify-cost-report-collector.sh`: a fixture at exactly `$1.00`, the magnitude crossover research.md R8 names between the 2dp and 4dp cost-line patterns.
  - [X] `verify-turn-budget-collector.sh`: fixtures sitting exactly at `climb_fraction` 0.6 and exactly at `counted-turns == intended-budget`.
  - [X] `verify-final-pr-claims-collector.sh`: a fixture feeding an empty PR body.
