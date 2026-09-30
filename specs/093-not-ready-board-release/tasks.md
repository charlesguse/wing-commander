---

description: "Task list template for feature implementation"
---

# Tasks: A Not-Ready PR Releases the Board

**Input**: Design documents from `specs/093-not-ready-board-release/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/not-ready-hold.md, quickstart.md (all present)

**Tests**: This feature adds no new gate (FR-013) — every new rule is exercised by checked-in fixtures/`RESUME_CASES` entries in the two existing gates (`verify-board-eligibility.py` Gate 81, `verify-board-loop-resume-gating.py` Gate 97) plus mutation-testing self-tests. Fixture and mutation tasks are woven into each story's own phase, per FR-013's per-rule mapping, rather than a separate "tests" sub-phase — each rule and its proof ship together.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P1/P2/P3) to enable independent implementation and testing of each.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

Single project — this repository's own CI automation. All paths are repo-root-relative:
`.github/scripts/*.py`, `.github/scripts/tests/board-eligibility/in-flight/*`,
`.github/workflows/board-loop.yml`, `.github/actions/_shared/resolve-pr-branch/action.yml`,
`specs/057-autonomous-board-loop/contracts/*.md`, `specs/061-marker-owned-in-flight/contracts/*.md`.

---

## Phase 1: Setup

- [ ] T001 Run `.github/scripts/run-local-gates.py` (`python .github/scripts/run-local-gates.py`) to confirm a clean green baseline before any change in this feature — the reference point every new fixture and mutation in later phases is compared against (no file modified).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The marker shape, readiness classification, eligibility primitives, and count/head-sha plumbing every user story reads or writes. No selection or readiness *behavior* changes here — only the data these behaviors will consume.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T002 In `.github/scripts/board_readiness.py`, extend `evaluate_from_snapshot()`'s returned dict with a fourth field `unmet_class`: `"self-clearing"` when every rollup entry blocking `checks_green` is in a not-yet-concluded state (`QUEUED`, `IN_PROGRESS`, `PENDING`, `EXPECTED` — the same set `_checks_green()` already tests against, inverted), `"durable"` for any other unmet reason (a terminal failing check state, an empty rollup, an open finding, a backstop breach, or the kill switch), and `None` when `ready` is `True`. Derive this only from `snapshot["statusCheckRollup"]`'s own per-entry `state`/`conclusion` values already in hand (FR-005: "never from an agent's reading of them") — never a second `gh` call. See contracts/not-ready-hold.md's `board_readiness.py` section and research.md D2.
- [ ] T003 [P] In `.github/scripts/board_item_marker.py`, extend `write_marker(step, round, pr, branch, base_sha)` with three new optional trailing parameters: `nr_count=None` (int), `nr_head_sha=None` (str), `nr_class=None` (must be `"self-clearing"` or `"durable"` when not `None` — the two-value enum FR-005 defines; the caller, not this function, is responsible for never passing a third value). Serialize each into the JSON payload only when it is not `None` — an absent field, not a null-valued one, per data-model.md's Board Item Marker table, so every existing marker shape (and every marker with no not-ready record) stays byte-identical in every field that already existed. See contracts/not-ready-hold.md and research.md D1.
- [ ] T004 [P] In `.github/scripts/board_item_marker.py`'s `main()`, add `--nr-count` (type=int, default=None), `--nr-head-sha` (default=None), `--nr-class` (default=None) to the `argparse` parser, each independent of `--step` (no cross-validation like `--step stalled`'s `--issue`/`--add-label` pairing), and pass them through to `write_marker(...)` in the final `print(write_marker(...))` call.
- [ ] T005 In `.github/scripts/board_eligibility.py`, add module-level constant `NOT_READY_THRESHOLD = 3` (spec.md Assumptions — "Threshold value: 3 not-ready outcomes per PR", a value not a mechanism), a function `not_ready_record(marker)` returning `{"pr": int, "head_sha": str, "class": "self-clearing"|"durable", "count": int}` from `marker`'s `pr`/`nr_head_sha`/`nr_class`/`nr_count` fields, or `None` when `marker` is `None`, `marker.get("step") != "readiness"`, or any of the three `nr_*` fields is missing or malformed (FR-011 fail-safe: degrade to "no record", never guess a class or count), and a function `not_ready_handover_due(nr_count)` returning `True` when `nr_count >= NOT_READY_THRESHOLD` (FR-004(a)). See contracts/not-ready-hold.md.
- [ ] T006 In `.github/workflows/board-loop.yml`'s `select` job PR-lookup loop (the `while IFS= read -r pr_number` block, currently ~line 491-519, which already runs `gh api repos/:owner/:repo/pulls/:number` per `FIX_OR_LATER_STEPS` marker's PR), additionally extract `.head.sha` from the same already-fetched `board-lookup-pr.json` into a parallel `$RUNNER_TEMP/board-pr-head-sha-by-number.json` (same accumulation shape as `board-pr-state-by-number.json` beside it — no new `gh` call), and fold it into the `board_eligibility.py` stdin payload (the `jq -n ... > "$RUNNER_TEMP/board-eligibility-input.json"` step, ~line 522-530) as a new top-level key `pr_head_sha_by_number`. See research.md D4.
- [ ] T007 In `.github/workflows/board-loop.yml`'s resume step: (a) where the marker's own fields are parsed (~line 604-608, alongside `marker_round`/`marker_base_sha`), add `marker_nr_count="$(printf '%s' "$marker_json" | jq -r '.nr_count // 0')"`; (b) thread it through the `step_resolution_json` heredoc (~line 689-841) as a passthrough field `nr_count` (default `"0"`, never derived from anything but the marker — mirrors how `round`/`base_sha` already flow) so it survives every branch of that resolution unless a branch already resets `round`/`base_sha` to `"0"`/empty for a stale marker, in which case `nr_count` resets alongside them for the same reason (FR-022: an abandoned attempt's state must not leak into a fresh triage); (c) capture it into a step output `nr-count` beside the existing `round`/`base-sha` outputs (~line 869-870); (d) add `nr-count: ${{ steps.resume.outputs.nr-count }}` to the `select` job's `outputs:` block (~line 142-149, beside `round`/`base-sha`). See research.md D5.
- [ ] T008 [P] In `.github/actions/_shared/resolve-pr-branch/action.yml`, add an `nr-count` input (`required: false`, `default: ""`, described as "Pass-through only -- never derived from the PR itself", mirroring the existing `round` input) and a matching `nr-count` output, threaded through the composite's one `run:` step (`echo "nr-count=$NR_COUNT"` beside the existing `round=$ROUND` line) exactly as `round` already is. See research.md D5.

**Checkpoint**: Marker shape, readiness classification, eligibility primitives, and count/head-sha plumbing all exist. No selection or readiness behavior has changed yet — every existing fixture must still pass unchanged.

---

## Phase 3: User Story 1 - The board keeps draining past a PR the loop cannot finish (Priority: P1) 🎯 MVP (with US2)

**Goal**: A durable, unmoved-head not-ready item is excluded from both selection paths, so the board drains to a second eligible issue instead of re-selecting the same wedged item every run.

**Independent Test**: `python .github/scripts/verify-board-eligibility.py` — checked-in fixtures assert the held item is excluded and a second issue is selected instead. No live run needed.

### Implementation for User Story 1

- [ ] T009 [US1] In `.github/scripts/board_eligibility.py`, add `_not_ready_holds(marker, pr_state_by_number, pr_head_sha_by_number)`: returns `True` (held) when `not_ready_record(marker)` is not `None`, its `class` is `"durable"`, and `pr_head_sha_by_number.get(pr)` either is missing (unresolvable this run — FR-011's fail-safe also holds) or equals `head_sha` (unchanged head holds). Returns `False` otherwise — including when there is no not-ready record at all, a `"self-clearing"` record (FR-005: never held), or a durable record whose head has moved (admitted, not merely un-held — the resume step's own logic from T028 decides review vs. readiness, never this predicate). Mirrors `_awaiting_merge_holds()`/`_unowned_open_pr_holds()`'s existing shape beside it. See contracts/not-ready-hold.md.
- [ ] T010 [US1] In `.github/scripts/board_eligibility.py`'s `in_flight_candidate()` (~line 167-223), add one more skip condition alongside the existing `TERMINAL_STEPS`/`"prove"`/`AWAITING_MERGE_STEP` check (~line 209): when `step == "readiness"` and `_not_ready_holds(marker, pr_state_by_number, pr_head_sha_by_number)` is `True`, skip this issue (it is not a candidate) even though `pr_state_by_number.get(pr) == "OPEN"` would otherwise qualify it. `in_flight_candidate()` must call `_not_ready_holds()` explicitly here — it does not already call `_awaiting_merge_holds()`/`_unowned_open_pr_holds()` because the existing `OPEN` check happens to already exclude those cases, but an open, durable, unmoved-head PR is exactly the case that must be excluded despite passing that check.
- [ ] T011 [US1] In `.github/scripts/board_eligibility.py`'s `select()` oldest-first fallback (~line 263-297), add a call to `_not_ready_holds(pair[1], pr_state_by_number, pr_head_sha_by_number)` beside the existing `_awaiting_merge_holds()`/`_unowned_open_pr_holds()` calls (~line 290-293), skipping the issue when it returns `True` — one decision, both selection paths (FR-003/FR-004).
- [ ] T012 [P] [US1] Add fixture directory `.github/scripts/tests/board-eligibility/in-flight/not-ready-durable-unmoved-held/`, same four/five-file shape as `awaiting-merge-pr-open`: a `readiness` marker carrying a durable not-ready record, `pr_state_by_number` `OPEN`, `pr_head_sha_by_number` equal to `nr_head_sha` → `in_flight_candidate()` returns `(null, false)`; `select()` returns a second, newer eligible issue with no marker (US1 AS1).
- [ ] T013 [P] [US1] Add fixture directory `.github/scripts/tests/board-eligibility/in-flight/not-ready-durable-moved-admitted/`: same marker as T012's fixture, but `pr_head_sha_by_number` differs from `nr_head_sha` → that issue is admitted (`_not_ready_holds()` returns `False`), `select()` returns it, `multiple_found` is `false` (US1/US3 boundary case — the step this admission resolves to is verified separately by T031's Gate 97 case, not here).
- [ ] T014 [P] [US1] Add fixture directory `.github/scripts/tests/board-eligibility/in-flight/not-ready-self-clearing-not-held/`: a `readiness` marker with `nr_class: "self-clearing"`, head unchanged from `nr_head_sha` → that issue remains the in-flight candidate (never held, FR-005, US1 AS5).
- [ ] T015 [P] [US1] Add fixture directory `.github/scripts/tests/board-eligibility/in-flight/not-ready-head-unresolvable/`: a durable not-ready record whose PR is absent from `pr_head_sha_by_number` (lookup failed this run) → held, same excluded/second-issue-selected shape as T012 (FR-011 fail-safe).
- [ ] T016 [P] [US1] Add fixture directory `.github/scripts/tests/board-eligibility/in-flight/not-ready-two-held-one-eligible/`: two separate issues each with a durable, unmoved-head not-ready record, plus a third eligible issue with no marker → the third issue is selected; neither held item blocks the other or is itself selected (US1 AS4).
- [ ] T017 [US1] Correct `specs/061-marker-owned-in-flight/contracts/in-flight-detection.md` wherever it enumerates which steps make an item in-flight, to state that a `readiness` marker for which `_not_ready_holds()` is `True` is excluded from the candidate list (FR-014), pointing at `specs/093-not-ready-board-release/contracts/not-ready-hold.md` as the canonical statement rather than restating the full rule (CLAUDE.md).

**Checkpoint**: `python .github/scripts/verify-board-eligibility.py` passes every existing fixture plus all six new ones. US1 is independently functional and testable.

---

## Phase 4: User Story 2 - An unmet condition that will never clear itself reaches a human, once, named (Priority: P1) 🎯 MVP (with US1)

**Goal**: A durable not-ready outcome is recorded on every run; after 3 such outcomes on the same PR the item is hand­ed to a human once, named, under `board:stalled`; an unchanged not-ready comment is edited in place rather than duplicated.

**Independent Test**: `python .github/scripts/verify-board-loop-resume-gating.py --simulate` for the resume-side cases, plus driving the readiness decision with a durable fixture and asserting the handover artifacts (label, notice, terminal marker) match spec 057 FR-030's existing shape exactly.

### Implementation for User Story 2

- [ ] T018 [US2] In `.github/workflows/board-loop.yml`'s "Evaluate readiness" step (~line 3727-3759), capture the new `unmet_class` field `evaluate_from_snapshot()` now returns (T002) into `$RUNNER_TEMP/board-readiness-decision.json` alongside the existing decision fields, so the not-ready-report step below can read it without a second `board_readiness` call.
- [ ] T019 [US2] In `.github/workflows/board-loop.yml`'s "Report the unmet condition (not ready)" step's `env:` block (~line 3862-3877), add `NR_COUNT: ${{ needs.select.outputs.nr-count || needs.review.outputs.nr-count || 0 }}` and `NR_HEAD_SHA`/`NR_CLASS` sourced the same way — whichever of `select`'s or `review`'s outputs produced this run's readiness entry (mirrors the existing `PR_NUMBER: ${{ steps.pr.outputs.pr-number }}` dual-source pattern already in this job).
- [ ] T020 [US2] In the same step's not-ready branch (the `else` at ~line 3918-3922, "checks not green"/backstop-holds-true path — never the backstop-breach branch above it, which FR-012 keeps unchanged), before posting anything: read `head_sha="$(jq -r '.head_sha' "$RUNNER_TEMP/board-readiness-decision.json")"`, compute `new_count=$(( ${NR_COUNT:-0} + 1 ))`, and branch on `new_count -ge $NOT_READY_THRESHOLD` where `NOT_READY_THRESHOLD` is exposed from `.github/scripts/board_eligibility.py`'s `NOT_READY_THRESHOLD` (T005) the same way this file already imports symbolic step names — never a second hardcoded `3`.
- [ ] T021 [US2] Handover sub-branch (`new_count >= NOT_READY_THRESHOLD`, FR-004(a)/FR-008): call `board_item_marker.add_stalled_label()` (via the CLI's `--add-label board:stalled --issue "$ISSUE_NUMBER"`) *before* rendering any marker; on success render `--step stalled --pr "$PR_NUMBER" --nr-head-sha "$head_sha"` — this feature's own handover marker is the one `stalled` marker that carries `pr`/`nr_head_sha` (data-model.md, research.md D7), every other stall site keeps `pr: null`. Post one notice naming the unmet condition (`$unmet`), the PR, the head SHA measured, and that removing `board:stalled` is the sole condition that makes the item eligible again (US2 AS1). Fail the step loudly (`exit 1`) if the label add fails, matching every other `add_stalled_label()` call site's pattern in this file.
- [ ] T022 [US2] Non-handover sub-branch (`new_count < NOT_READY_THRESHOLD`): render `--step readiness --pr "$PR_NUMBER" --branch "$BRANCH" --nr-count "$new_count" --nr-head-sha "$head_sha" --nr-class "$unmet_class"` (reading `unmet_class` from T018's captured field), keeping the existing "Not ready on PR #%s: %s. Picked up again on a later run." body text.
- [ ] T023 [US2] FR-009 dedup (research.md D8): before posting the comment in T022's sub-branch, compare this run's `(PR_NUMBER, head_sha, unmet)` triple against the current marker's own recorded `(pr, nr_head_sha, unmet-reason-text-from-the-visible-comment-line)`. On an exact match, use `gh issue comment "$ISSUE_NUMBER" -R "$GITHUB_REPOSITORY" --edit-last --body "..."` (updating the embedded marker to the new `nr_count`) instead of appending a new comment; on any difference, post a new comment as today. At most one such comment MUST exist per (PR, head SHA, unmet condition) triple (FR-009).
- [ ] T024 [US2] In `.github/workflows/board-loop.yml`'s resume step, insert a new clause ahead of the existing generic `board:owned` fallback clause (the `elif pr_from_fallback:` at ~line 811-814): when `marker_step == "stalled"` and the marker carries both `pr` and `nr_head_sha` (this feature's own handover shape from T021) and the fallback recovers that same PR: resolve `step = "readiness"` when the recovered PR's current head equals `nr_head_sha` (the fallback's PR lookup already has `.head.sha` available), else fall through unchanged to the existing fallback clause (`step = "review"`). A `stalled` marker lacking either field (every other stall site) is unaffected and keeps resolving `"review"` via the unchanged existing clause (FR-015). See research.md D7, US2 AS3.
- [ ] T025 [P] [US2] In `.github/scripts/verify-board-loop-resume-gating.py`, add `RESUME_CASES` entries: this feature's own `stalled` handover marker (`pr`+`nr_head_sha` set), fallback-recovered PR head unmoved → `step = "readiness"`; same handover marker, head moved → `step = "review"`; a `stalled` marker from any other stall site (`pr` absent) → `step = "review"` unchanged (regression, FR-015).
- [ ] T026 [P] [US2] Add a fixture/simulation case proving FR-006's stand-down preservation (already true on `main` per research.md D9, "must be preserved, not built"): with `steps.killswitch-recheck.outputs.paused == 'true'`, the not-ready-report step (T019-T023) is not reached, so no marker is written and `nr_count` does not advance — assert this in the same style as the existing kill-switch coverage for this job.
- [ ] T027 [US2] Correct `specs/057-autonomous-board-loop/contracts/readiness-report.md`'s "A not-ready outcome leaves the marker as it was, so the next run picks the item up at `readiness` again" sentence (FR-014): replace it with a pointer to `specs/093-not-ready-board-release/contracts/not-ready-hold.md` as the canonical statement, and state explicitly that FR-067's "picked up again on a later run" is bounded by this feature's hold/threshold, not unconditional (the FR-067/FR-009 reconciliation FR-014 requires).

**Checkpoint**: `python .github/scripts/verify-board-loop-resume-gating.py --simulate` passes every existing case plus the new ones. Combined with US1, the board now both releases on the first not-ready outcome and guarantees eventual human handover — this is the feature's MVP.

---

## Phase 5: User Story 3 - A moved head brings the item back without a human (Priority: P2)

**Goal**: A held item is automatically re-admitted, at `review` (never `readiness`), the moment its PR's head moves — continuing rather than resetting the fix→review round budget — with no label removed by hand.

**Independent Test**: `python .github/scripts/verify-board-loop-resume-gating.py --simulate` — a fixture pair over the same held item (one with a matching head SHA, one with a different one) asserts opposite selection/resolution outcomes from the same decision.

### Implementation for User Story 3

- [ ] T028 [US3] In `.github/workflows/board-loop.yml`'s resume `step_resolution_json` heredoc (~line 689-841), insert a new clause checked before the existing `elif pr_from_marker and marker_step and (marker_step in PRE_FIX_STEPS or (marker_step in FIX_OR_LATER_STEPS and pr_state == "OPEN")):` clause (~line 787-791): when `marker_step == "readiness"`, the marker's `nr_class == "durable"`, and the live head SHA of the marker-recovered PR (already fetched into `board-marker-pr.json` at ~line 636, `.head.sha`) differs from the marker's `nr_head_sha` — resolve `step = "review"` (never `"readiness"`, FR-007), passing through `round_` unchanged (the value T007/T029 preserve, not reset to `"0"`). Every other case this existing clause already covers (no not-ready record, a self-clearing record, or a durable record whose head is unchanged) is unaffected and keeps resolving `step = marker_step` ("readiness"). Record which step was resumed to and why in the step's existing summary/note mechanism (spec 061 FR-014's provenance rule). See research.md D3, US3 AS1/AS2/AS3/AS4.
- [ ] T029 [US3] In `.github/workflows/board-loop.yml`'s review job, "Post the converged/stalled outcome and marker" step's `OUTCOME = converged` branch (~line 3298-3300): add `--round "$ROUND"` (the round it converged at — today's call omits `--round`, defaulting to 0) and `--nr-count "$NR_COUNT"` (sourced from `needs.select.outputs.nr-count`, carried through unchanged) to the `board_item_marker.py` invocation. See research.md D6/D5.
- [ ] T030 [US3] In `.github/workflows/board-loop.yml`'s review job, "Push the follow-up commit and advance the round" step (~line 3466-3479): add `--nr-count "$NR_COUNT"` to the `board_item_marker.py` invocation, carried through unchanged — the round already advances here (`next_round=$((CURRENT_ROUND + 1))`); the not-ready count does not (only readiness's own not-ready outcome advances it, per T020).
- [ ] T031 [P] [US3] In `.github/scripts/verify-board-loop-resume-gating.py`, add `RESUME_CASES` entries: a `readiness` marker with a durable, unmoved-head not-ready record → `step = "readiness"` (regression, now exercised with the new fields present rather than absent); the same marker with a moved head → `step = "review"`, with `round` equal to the marker's own preserved `round` value (not `"0"`).
- [ ] T032 [P] [US3] Add a fixture/case proving: a held item re-admitted on a moved head continues (never resets) its existing fix→review round budget (spec 057 FR-030) across the re-admission — verified by asserting the resolved `round` in T031's moved-head case reflects the marker's carried-forward value; and a held item whose *continued* round budget is already exhausted takes spec 057 FR-030's existing budget-exhausted handover unchanged, never a second, parallel handover beside it (FR-007/FR-012/SC-009, US3 AS5/AS6).
- [ ] T033 [US3] Correct `specs/061-marker-owned-in-flight/contracts/resume-recovery.md` (FR-014): add the re-admitted-at-`review` clause T028 implements to its step-resolution clause list (a re-admitted not-ready item resolves to `review`, not to the marker's own `readiness` step), and add the corresponding row to that contract's scenario table.

**Checkpoint**: All user stories should now be independently functional. A moved head recovers the item automatically; the round budget it consumes is bounded and shared with the not-ready threshold, never doubled.

---

## Phase 6: User Story 4 - Every new rule is provable at PR time (Priority: P3)

**Goal**: Every rule this feature adds fails its own gate when removed, with no live run and no red PR needed.

**Independent Test**: Run the gate suite locally; every added fixture and self-test mutation passes or fails on its own (SC-006).

### Implementation for User Story 4

- [ ] T034 [P] [US4] Prove `_not_ready_holds()` (T009-T011) is load-bearing: temporarily remove its call site from `.github/scripts/board_eligibility.py` (e.g. `git stash push .github/scripts/board_eligibility.py` after reverting the call), run `python .github/scripts/verify-board-eligibility.py`, confirm it FAILS naming one of T012/T015/T016's cases, then restore the call site (`git stash pop`). Leave no working-tree change behind.
- [ ] T035 [P] [US4] Prove `NOT_READY_THRESHOLD` (T005) is load-bearing: temporarily raise it to an arbitrarily large number, run `python .github/scripts/verify-board-eligibility.py` and `python .github/scripts/verify-board-loop-resume-gating.py`, confirm at least one checked-in case FAILS, then restore `NOT_READY_THRESHOLD = 3`.
- [ ] T036 [P] [US4] Add a self-test mutation to `.github/scripts/verify-board-loop-resume-gating.py` (FR-013's "the resume-gating gate's self-test... the not-ready site's record write is dropped from the workflow"): assert that when the not-ready-report step's marker write (T022) or its `board:stalled` handover branch (T021) is removed from `.github/workflows/board-loop.yml`, the gate's own self-test detects the drop and fails.
- [ ] T037 [US4] Run `python .github/scripts/run-local-gates.py` on the implementing branch; confirm every existing board-loop fixture — `awaiting-merge-*`, `breach-*`, `prove-no-pr`, `unowned-open-pr`, the forged-marker cases — still passes unchanged (FR-015/SC-008), and every gate in the suite is green.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T038 Run `python .github/scripts/verify-board-eligibility.py` and `python .github/scripts/verify-board-loop-resume-gating.py --simulate` directly (quickstart.md steps 2 and 4) as a final end-to-end confirmation that every new and existing case passes together, and record the local gate suite's clean run per quickstart.md step 1.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories. T006, T007, T008 touch `board-loop.yml`'s `select` job and `resolve-pr-branch/action.yml`; T002-T005 touch the three Python scripts independently.
- **User Stories (Phase 3-6)**: All depend on Foundational completion.
  - **US1 (Phase 3)** and **US2 (Phase 4)** are both P1 and mostly touch disjoint regions (US1: `board_eligibility.py`'s `in_flight_candidate()`/`select()` + eligibility fixtures + `in-flight-detection.md`; US2: `board-loop.yml`'s `readiness` job + one resume-step clause + `readiness-report.md`) — they can proceed in parallel.
  - **US3 (Phase 5)** depends on Foundational's T007/T008 (nr-count threading) and edits the *same* resume `step_resolution_json` region of `board-loop.yml` that US2's T024 also edits (different clauses, same heredoc) — land US2 before US3, or coordinate the two edits in one pass, to avoid a merge conflict on that block.
  - **US4 (Phase 6)** depends on US1, US2, and US3 all being implemented — it proves their rules are load-bearing, so it cannot run first.
- **Polish (Phase 7)**: Depends on all four user stories.

### Within Each User Story

- Production code before the fixtures/cases that exercise it (a fixture asserting behavior that does not exist yet is not a useful checkpoint).
- Fixtures before the contract correction that documents the now-implemented behavior (FR-014's corrections describe what T009-T033 actually built).

### Parallel Opportunities

- T003 and T004 (same file, additive/independent regions) may still be done as one edit; kept as separate tasks only because they touch different functions.
- All five T012-T016 fixture directories are `[P]` — independent directories, no shared file.
- T023 (US2's fixture set) and T029/T030 (US3's marker-writing edits) are `[P]` relative to each other.
- T034, T035, T036 (US4's three mutation proofs) are fully independent and `[P]`.

---

## Parallel Example: User Story 1

```bash
# After T009-T011 land, the five new fixture directories can be authored together:
Task: "Add fixture .github/scripts/tests/board-eligibility/in-flight/not-ready-durable-unmoved-held/"
Task: "Add fixture .github/scripts/tests/board-eligibility/in-flight/not-ready-durable-moved-admitted/"
Task: "Add fixture .github/scripts/tests/board-eligibility/in-flight/not-ready-self-clearing-not-held/"
Task: "Add fixture .github/scripts/tests/board-eligibility/in-flight/not-ready-head-unresolvable/"
Task: "Add fixture .github/scripts/tests/board-eligibility/in-flight/not-ready-two-held-one-eligible/"
```

---

## Implementation Strategy

### MVP First (User Story 1 + User Story 2 together)

FR-004 requires both mechanisms to ship together — "the loop MUST release a not-ready item by **both** mechanisms together" — so, unlike a typical single-P1-story MVP, this feature's MVP is Foundational + US1 + US2 combined:

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories).
3. Complete Phase 3 (US1) and Phase 4 (US2).
4. **STOP and VALIDATE**: `python .github/scripts/run-local-gates.py` green, Gate 81 and Gate 97 fixtures from both stories passing. A held item is skipped (US1) *and* is guaranteed to reach a human within 3 not-ready outcomes (US2) — the defect (an unbounded wedge with no handover) is fixed.
5. Deploy/demo if ready.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 + US2 together → MVP: the board drains past a wedged item and that item is guaranteed to reach a human.
3. Add US3 → moved-head items recover automatically, without a human removing a label.
4. Add US4 → every rule is proven load-bearing at PR time, satisfying SC-006 before merge.
5. Polish → final end-to-end confirmation across both gates.

### Parallel Team Strategy

With two developers (per CLAUDE.md's "keep concurrent local agents to two" guidance for this repository's own board loop):

1. Both complete Setup + Foundational together (or one developer owns it while the other reviews).
2. Once Foundational is done: Developer A takes US1 (`board_eligibility.py` + fixtures), Developer B takes US2 (`board-loop.yml` readiness job).
3. US3 starts once both US1 and US2 have landed, to avoid the `step_resolution_json` conflict noted above.
4. US4 starts once US1-US3 are all in place.

---

## Notes

- No new gate is added anywhere in this feature (FR-013) — every task above extends Gate 81 (`verify-board-eligibility.py`) or Gate 97 (`verify-board-loop-resume-gating.py`).
- `board_item_marker.add_stalled_label()`'s own canonical docstring is **not** edited by any task above (research.md D7/D10) — that generalization to every other stall site belongs to `specs/100-stalled-item-re-admission` (lifecycle issue #752), not yet built. T021's handover call site documents its own `--pr`/`--nr-head-sha` usage inline instead.
- [P] tasks = different files (or independent directories), no dependencies on each other.
- [Story] label maps each task to its user story for traceability back to spec.md.
- Commit after each task or logical group; stop at any checkpoint to validate a story independently.
