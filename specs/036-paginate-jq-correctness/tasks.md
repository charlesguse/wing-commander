---

description: "Task list for Multi-Page `gh api` Reads Return What They Claim, and a Gate Keeps Them That Way"
---

# Tasks: Multi-Page `gh api` Reads Return What They Claim, and a Gate Keeps Them That Way

**Input**: Design documents from `/specs/036-paginate-jq-correctness/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/pagination-shape-gate.md, contracts/watchdog-read-outcome.md, quickstart.md

**Tests**: Requested — FR-012 requires all three fixed sites to gain executable multi-page coverage, and FR-009 requires the new static gate to carry its own self-test. Harness/gate tasks are folded into the user-story phase that introduces the behavior they cover (the story that fixes a site also gets that site's test), not deferred to a separate testing phase.

**Organization**: This feature's footprint is three modified workflow files (`.github/workflows/watchdog.yml`, `.github/workflows/auto-update-spec-kit.yml`, `.github/workflows/lint-workflows.yml`), two new gate scripts (`verify-gate-18.py`, `verify-gate-19.py`), the existing `auto-update-spec-kit-tests/` harness extended in place, and one doc correction (`docs/agent-friendly-workflows.md`). No new workflow file, no new source directory (plan.md's Structure Decision). Because several tasks edit the same file (`watchdog.yml` in particular), `[P]` is used only where two tasks genuinely touch different files or disjoint regions with no ordering dependency.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US5)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature, no `src/`/`tests/` split. All file paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Establish the FR-005/SC-007 "identical behavior below the page boundary" baseline every fix in this feature must not disturb, and confirm the gate numbers this feature claims are actually free.

- [ ] T001 Run `python3 .github/scripts/run-local-gates.py` and `bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh` against the current branch tip and confirm both are clean. Re-confirm research.md D2's grep-derived gate roster (`lint-workflows.yml` currently uses Gates 1-17, nothing numbered 18 or higher) so this feature's "Gate 18" and "Gate 19" naming is safe to claim.

**Checkpoint**: Baseline is green; Gate 18/19 numbering is free.

---

## Phase 2: Foundational (Blocking Prerequisites)

**No blocking prerequisites.** The five user stories touch disjoint or only lightly-overlapping regions of `watchdog.yml`, `auto-update-spec-kit.yml`, `lint-workflows.yml`, and the `auto-update-spec-kit-tests/` harness; the one real cross-story dependency (User Story 5 extends the same `watchdog.yml` collector steps User Stories 1 and 3 fix first) is recorded as an explicit task-level dependency in Phase 7 rather than a shared foundation. User story work can begin directly after Phase 1.

---

## Phase 3: User Story 1 - The watchdog reports annotation evidence from a job that has more than one page of it (Priority: P1) 🎯 MVP

**Goal**: Every warning- and failure-level annotation from every page of every job in the inspected run reaches the evidence set, and the evidence gathered by earlier collectors is preserved.

**Independent Test**: Drive the shipped annotation-collection step against a response spanning more than one page, and confirm that every warning- and failure-level annotation appears in the evidence set handed to the diagnosis step — and that the evidence already gathered by earlier collectors is still there too.

### Implementation for User Story 1

- [ ] T002 [US1] Rewrite `.github/workflows/watchdog.yml`'s `Collect: annotations` step (`id: collect-annotations`, ~lines 727-747) per research.md D1. Change the jobs-listing read (line 740) to stream: `gh api "repos/$GITHUB_REPOSITORY/actions/runs/$RUN_ID/jobs" --paginate --jq '.jobs[]' 2>/dev/null | jq -s '.'`, capturing the `gh api` call's own exit status via bash's `${PIPESTATUS[0]}` immediately after the pipeline (not `$?`, which would report `jq`'s exit code) so User Story 5's outcome tracking can consume it without re-deriving it; fall back to `[]` only when the captured JSON is empty. Update the downstream loop (line 742) from `.jobs[]?.id` to `.[]?.id`. Change the annotations read (line 743) to stream: `gh api "repos/$GITHUB_REPOSITORY/check-runs/$job_id/annotations" --paginate --jq '.[] | select(.annotation_level=="warning" or .annotation_level=="failure") | {source:"annotations","class-hint":null,facts:{level:.annotation_level,message:.message}}' 2>/dev/null | jq -s '.'`, removing the now-redundant separate `jq -c '[ .[]? | ... ]'` pass (line 744), and likewise capture its own `${PIPESTATUS[0]}`. Keep the accumulate-into-`entries` and final merge into `signals.json` (lines 745-747) unchanged.
- [ ] T003 [P] [US1] Create `.github/scripts/verify-gate-19.py` (research.md D5), modeled on `verify-sentinel-collector.py`'s (Gate 9) structure: use `wc_shell_harness.find_step`/`run_step` to extract `watchdog.yml`'s `Collect: annotations` step at run time (no second copy); stub `gh` to answer only `*/jobs` and `*/check-runs/*/annotations` from fixture files, erroring loudly on any other path; give the annotations fixture the ability to represent a multi-page response as N concatenated JSON array documents (the same "N concatenated documents" byte shape D4 gives the auto-update harness — see T007). Cover at least these scenarios: (a) one job, annotations spanning 2 pages — every warning/failure annotation from both pages reaches `signals.json` exactly once (Acceptance Scenario 1); (b) evidence contributed by collectors that ran earlier is unchanged and still present afterward (Acceptance Scenario 2); (c) several jobs, each spanning more than one page — annotations from every job are present and no job's annotations displace another's (Acceptance Scenario 3); (d) a job with fewer annotations than one page — output identical to today's pre-fix behavior (Acceptance Scenario 4, FR-005); (e) a job with genuinely zero warning/failure annotations — evidence set unchanged, and the run is not reported as a failed read (Acceptance Scenario 5); (f) a page boundary landing exactly on the last item (second page empty) — output identical to the single-page case, no trailing empty element (Edge Cases). Close with a MUTATIONS section (matching Gate 9's `mut_*` pattern) that reintroduces the pre-fix array-collecting `--jq '[...]'` form and asserts the suite then fails to collect page-2 annotations (FR-009/Acceptance Scenario 7).
- [ ] T004 [US1] Wire `verify-gate-19.py` into `.github/workflows/lint-workflows.yml`'s `lint` job as a single step named `Gate 19 — the watchdog's annotation collector sees every page` (`run: python3 .github/scripts/verify-gate-19.py`), placed after Gate 17 in the existing numbered sequence — a single-step shape matching Gate 9/17's precedent (no separate self-test step; the mutation checks are embedded in the script itself, research.md D5). Confirm `python3 .github/scripts/run-local-gates.py` and `verify-gate-wiring.py` (Gate 10) pick it up automatically with no manifest edit (`wc_gate_registry.py`'s naming-convention discovery).

**Depends on**: T004 depends on T003 (the step must exist before it can be wired); T003's fix-shape scenarios depend on T002 having landed so the extracted step is the fixed one.

**Checkpoint**: Annotation evidence is complete across pages; Gate 19 proves it and can detect a regression.

---

## Phase 4: User Story 2 - Spec Kit release detection resolves exactly one latest version once upstream passes the page boundary (Priority: P1)

**Goal**: Detection resolves exactly one, highest, eligible version and release-note assembly produces a single well-formed collection, both correct for an upstream release list of any length.

**Independent Test**: Drive the shipped detection step against an upstream release list long enough to span more than one page and confirm it yields one version string, that it's the highest eligible stable release, and that the release-note bundle it assembles is a single well-formed collection covering exactly the releases between the pinned and candidate versions.

### Implementation for User Story 2

- [ ] T005 [US2] Rewrite `.github/workflows/auto-update-spec-kit.yml`'s `Compare pinned version against latest eligible upstream release` step (`id: compare`, line 425) per research.md D1: `releases_json="$(gh api repos/github/spec-kit/releases --paginate --jq '.[] | select(.prerelease == false)' 2>/dev/null | jq -s '.')"`. Drop the now-redundant `select(.prerelease == false)` from the downstream filter (line 426) — the per-item filter already excludes prereleases page-by-page — keeping `sort_by(.tag_name | ltrimstr("v") | split(".") | map(tonumber? // 0)) | last // empty` otherwise unchanged.
- [ ] T006 [P] [US2] Rewrite `.github/workflows/auto-update-spec-kit.yml`'s `Fetch candidate release notes` step (`id: notes`, line 835) the same way: `releases_json="$(gh api repos/github/spec-kit/releases --paginate --jq '.[] | select(.prerelease == false)' 2>/dev/null | jq -s '.')"`. Drop the now-redundant `select(.prerelease == false)` from the downstream filter (lines 840-843), keeping the `$pinned`/`$candidate` range `select` unchanged.
- [ ] T007 [US2] Generalize `.github/scripts/auto-update-spec-kit-tests/gh_stub.py`'s `spec-kit/releases` branch (research.md D4): when `--paginate` is present in `argv`, split the loaded fixture array into chunks of `PAGE_SIZE = 30` and, for each chunk, call the existing `emit()` (applying `--jq` per chunk exactly as `gh` does server-side), writing directly to stdout with no added separator — reproducing the real N-concatenated-JSON-documents shape. When `--paginate` is absent, keep today's single-`emit()`-call behavior unchanged.
- [ ] T008 [US2] Extend `t1_detect.sh`'s `mkfixture` (or add a sibling builder) to produce a fixture of more than 30 releases, and add scenarios asserting: `detect` resolves exactly one version identifier from the multi-page list (Acceptance Scenario 1); the newest eligible release lands on a page after the first and is still the one selected — build the fixture so the highest stable tag is not on page 1 (Acceptance Scenario 2); newest-releases-are-prereleases are excluded regardless of which page they fall on (Acceptance Scenario 3); a single-page list still produces today's outcome unchanged (Acceptance Scenario 5, FR-005).
- [ ] T009 [P] [US2] Create `.github/scripts/auto-update-spec-kit-tests/t10_notes.sh` (research.md D5's sibling for `evaluate-path`'s `Fetch candidate release notes` step — no existing suite drives it today). Model its structure on `t1_detect.sh`'s `mkfixture`/`run_step`/`out`/`check` pattern: a `notes()` helper that seeds `releases_file` plus `pinned`/`candidate` env, runs the extracted `notes` step, and reads `$RUNNER_TEMP/release-notes.json`. Scenarios: a single-page fixture producing the correct release-note bundle (regression baseline); a >30-release fixture spanning a page boundary, asserting the resulting bundle is a single well-formed JSON array containing exactly the eligible releases strictly above pinned and at-or-below candidate — and nothing else — regardless of which page each boundary release falls on (Acceptance Scenario 4).
- [ ] T010 [US2] Add `t10_notes.sh` to `.github/scripts/auto-update-spec-kit-tests/run-tests.sh`'s `SUITES` array (currently `t1_detect.sh t2_settle.sh t3_healthcheck.sh t4_verify.sh t5_act.sh t6_reply.sh t7_gating.py t8_scaffold.sh t9_prepare.sh`).

**Depends on**: T007 before T008/T009's multi-page scenarios (the stub must be page-aware before a >1-page fixture means anything); T008/T009's multi-page assertions depend on T005/T006 having landed (the pre-fix steps would fail them by design — that's the point, but the *passing* suite depends on the fix).

**Checkpoint**: Release detection is deterministic across the page boundary; both auto-update sites are covered by the existing harness, extended.

---

## Phase 5: User Story 3 - A reviewer cannot merge a new instance of this defect (Priority: P1)

**Goal**: A repository-wide static check fails, naming file and line, on any paginated read that is not safe by construction — including the two watchdog reads that are correct today only by consumer accident — and the check is wired into the gate registry with its own self-test.

**Independent Test**: Introduce each broken shape into a workflow file in turn and confirm the check fails, naming the offending location; then confirm it passes on the repository as it stands after User Stories 1 and 2 have landed and the two accidentally-safe watchdog reads have been rewritten.

### Implementation for User Story 3

- [ ] T011 [US3] Rewrite the accidentally-safe jobs-listing read in `.github/workflows/watchdog.yml`'s `Collect: step summaries` step (`id: collect-step-summary`, ~lines 661-671; research.md D1, FR-011, FR-018): change line 665 to `jobs_json="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$RUN_ID/jobs" --paginate --jq '.jobs[]' 2>/dev/null | jq -s '.')"`, capturing `${PIPESTATUS[0]}` the same way T002 does. Update the downstream loop and per-id lookups (lines 667-669) from `.jobs[]?.id` / `.jobs[] | select(...)` to `.[]?.id` / `.[] | select(...)`, preserving identical job ids for a single-page run (FR-018).
- [ ] T012 [US3] Write Gate 18's detection logic as a `python3 - <<'PYEOF'` step named `Gate 18 — <short description>` in `lint-workflows.yml`'s `lint` job, in the same numbered sequence as Gates 15-17 (research.md D2), scanning: every `run:` block in every `.github/workflows/*.yml`/`*.yaml` file; every `run:` block in every `.github/actions/**/action.yml` composite action; the text of every checked-in shell/Python script the repository ships (contracts/pagination-shape-gate.md's Scope — excluding the transient `.wing-commander-pipeline/` checkout). For every `gh api ... --paginate` invocation found, apply contracts/pagination-shape-gate.md's Detection rule verbatim: FAIL (`array-collecting`) when a `--jq` filter's outermost result wraps in `[...]`; FAIL (`no-filter`) when no `--jq` is present at all, regardless of what the consumer downstream does with the result; PASS otherwise (`streaming-json`/`non-json-lines`); flip a FAIL to PASS only when a comment containing the literal token `wc-pagination-exempt:` followed by non-whitespace text appears on the same line as the call or the line immediately preceding it — a bare `wc-pagination-exempt` with no reason does not exempt. Emit one `::error file=<path>,line=<N>::` per failing site naming the file, line, which rule fired, and the required correct form (`gh api "<path>" --paginate --jq '.[] | <per-item filter>' | jq -s '.'`); exit 1 if any fail, exit 0 otherwise.
- [ ] T013 [US3] Immediately follow T012's step with `Gate 18 self-test — the detector actually detects` (`run: python3 .github/scripts/verify-gate-18.py`), the same adjacency Gates 15/16 use.
- [ ] T014 [US3] Create `.github/scripts/verify-gate-18.py` (research.md D2, modeled on `verify-gate-16.py`'s `extract_gate()`/`CASES`/`main()` structure): `extract_gate()` pulls Gate 18's own source from the shipped `lint-workflows.yml` at runtime via the step whose name starts with `"Gate 18"` and excludes `"self-test"`. Build the `CASES` fixture table straight from contracts/pagination-shape-gate.md's table: the T067 array-collecting shape (FAIL, mentions `array-collecting`); no `--jq` on an array endpoint (FAIL, `no-filter`); no `--jq` on an object endpoint / `{"jobs":[...]}` shape (FAIL regardless of consumer tolerance, FR-011); `--jq '.[] | {...}'` piped to `jq -s '.'` (PASS); `--jq '.[] | [.a,.b] | @tsv'` (PASS, non-JSON lines); a literal `[` inside a filter but not at the top level, e.g. `select(.x == ["a"])` (PASS — anchors on outermost shape only); a same-line `# wc-pagination-exempt: <reason>` on a FAIL-shaped call (PASS); a bare `# wc-pagination-exempt` with no reason (still FAIL); the same FAIL shape inside a composite action's `action.yml` (FAIL, proves reach beyond `.github/workflows/`); the same FAIL shape inside a checked-in `.sh` file (FAIL, proves reach beyond workflow/action YAML); and the five sites' shipped fix (T002, T005, T006, T011, and the annotations rewrite in T002) as they read after this feature lands (PASS — the regression case: reverting any one of the fixes must make this fixture FAIL again).

**Depends on**: T013/T014 depend on T012 (the self-test extracts T012's shipped source); T014's regression-case fixture depends on T002, T005, T006, and T011 having already landed.

**Checkpoint**: Gate 18 detects every broken shape, passes on the fixed repository, is wired into the registry, and self-tests. `python3 .github/scripts/run-local-gates.py` is clean.

---

## Phase 6: User Story 4 - The failure is named where a maintainer will meet it (Priority: P2)

**Goal**: A maintainer reading either Gate 18's failure output or the repository's workflow-authoring guidance can rewrite an offending call correctly without reconstructing pagination semantics from scratch.

**Independent Test**: Have someone unfamiliar with the defect read only the check's failure message and confirm they can rewrite the offending call correctly without further help.

### Implementation for User Story 4

- [ ] T015 [P] [US4] Replace `docs/agent-friendly-workflows.md`'s stale `gh api --paginate` bullet (lines 194-195, research.md D7 — currently "`gh api --paginate` breaks on `/jobs`: it concatenates JSON documents and jq chokes downstream. Use `?per_page=100`.") with the correct, general rule: `--paginate` applies `--jq` per page and concatenates the outputs, so any filter must emit one JSON value per line (`--jq '.[] | ...'`) and the caller slurps once with `jq -s '.'` if it needs a single array — never a filter that itself wraps results in `[...]`, and never no `--jq` at all on an array/object endpoint. Keep it in the same "Mechanics that bite agents specifically" list, immediately above the "Checklist for a new agent-bearing workflow" section (line ~211).

**Checkpoint**: A maintainer reading the doc before writing a new paginated call sees the correct form (FR-014, Acceptance Scenario 2). Gate 18's failure output (T012) already satisfies Acceptance Scenario 1 by construction — no separate task needed for it.

---

## Phase 7: User Story 5 - The watchdog says when it could not see, instead of behaving as though there was nothing to see (Priority: P2)

**Goal**: Every one of the watchdog's five collectors distinguishes a failed read from a legitimately empty one; the run still reaches a verdict; the diagnosis step is told which collectors could not be trusted.

**Independent Test**: Make one collector's read fail while the others succeed, and confirm the run still produces a verdict, that the failed collector is named as untrusted in what the diagnosis step reads, and that a collector which genuinely found nothing is not named.

### Implementation for User Story 5

- [ ] T016 [US5] Add per-collector read-outcome tracking to all five `.github/workflows/watchdog.yml` collectors (research.md D6), each collector appending one `{"collector": "<step-id>", "outcome": "ok"|"failed"}` line to a new `$RUNNER_TEMP/collector-outcomes.json` (same accumulate-and-`jq`-merge pattern `signals.json` already uses) at the end of its step, `failed` iff any read captured below was non-zero this run:
  - `collect-execution-output` (~line 399): the existing `if ! GH_TOKEN=... gh run download ...; then ...; exit 0; fi` already distinguishes success from failure but currently treats every failure identically to "no artifact found." Use the already-captured `$RUNNER_TEMP/eo-dl.log` to distinguish gh's genuine not-found condition (empty/no-match — `ok`) from any other failure (permission, network, rate-limit — `failed`) before the step's early `exit 0`.
  - `collect-branch-drift` (~line 506): capture `git fetch`'s own exit code immediately after the call (replacing the current `2>/dev/null || true`, ~line 558) rather than discarding it; treat a fetch failure caused by the ref genuinely no longer existing (branch already torn down) as `ok`, any other fetch failure as `failed`.
  - `collect-spec-meta` (~line 585): this collector performs no read of its own — it only compares already-resolved step outputs (`META_STAGE`, `RUN_CONCLUSION`) — so it always emits `outcome: "ok"`; do not invent a read here.
  - `collect-step-summary` (~line 636): extend T011's `${PIPESTATUS[0]}`-captured jobs-listing outcome, plus the per-job log read (~line 670, already `2>/dev/null || true`) — capture that call's own exit status too.
  - `collect-annotations` (~line 727): reuse T002's `${PIPESTATUS[0]}`-captured outcomes for both the jobs-listing and annotations reads.

  Never derive `outcome` from the step's own overall shell exit code — the steps run under `set -uo pipefail`, no `-e`, deliberately (FR-017).
- [ ] T017 [US5] Fold `$RUNNER_TEMP/collector-outcomes.json` into a new `aggregate`-step (`watchdog.yml:837-861`) output: `steps.aggregate.outputs.untrusted-collectors` = the deduplicated JSON array of every `collector` name whose `outcome` is `"failed"`, `[]` when every collector's reads all succeeded (today's behavior for every historical run — FR-005/SC-007). Leave the existing `collectors-failed` integer output and its step-exit-code-based counting (lines 841-849) unchanged — `untrusted-collectors` is additive (contracts/watchdog-read-outcome.md).
- [ ] T018 [US5] Add `untrusted-collectors: ${{ steps.aggregate.outputs.untrusted-collectors }}` to the `collect` job's `outputs:` block (`watchdog.yml:227-234`), alongside the existing five outputs, unchanged (contracts/watchdog-read-outcome.md — the one FR-015-authorized widening).
- [ ] T019 [US5] In the `diagnose` job, add a step writing `needs.collect.outputs.untrusted-collectors` to `${{ runner.temp }}/watchdog-untrusted-collectors.json`, mirroring the existing `signals` materialization (~line 982): `env: UNTRUSTED: ${{ needs.collect.outputs.untrusted-collectors }}` / `run: printf '%s' "$UNTRUSTED" > "${{ runner.temp }}/watchdog-untrusted-collectors.json"`.
- [ ] T020 [US5] Extend the `diagnose` agent's prompt (~line 1126, same untrusted-data framing already applied to `watchdog-signals.json`) with one additional instruction: read `watchdog-untrusted-collectors.json` and, when it names one or more collectors, state in the verdict which kinds of evidence could not be gathered this run — never to reweigh or discard any signal that did arrive (Out of Scope: diagnostic reasoning is untouched).
- [ ] T021 [US5] Extend `verify-gate-19.py` (T003) with a failure-injection scenario (quickstart item 7): make one of `collect-annotations`'s `gh api` calls fail via the stub, and assert the resulting `collector-outcomes.json` entry for `collect-annotations` reads `"outcome": "failed"` — not merely an empty `signals.json` contribution.
- [ ] T022 [P] [US5] Add executable coverage (extending an existing suite that already exercises `watchdog.yml`'s `aggregate`/`diagnose` wiring, or a small dedicated addition alongside it) confirming: one collector's read fails while the other four succeed → the run still reaches a verdict, `evidence-available` stays `true`, `untrusted-collectors` names exactly the failed collector, and the successful collectors' evidence in `signals` is intact (Acceptance Scenario 3); when every read succeeds, `untrusted-collectors` is `[]` and nothing else changes (Acceptance Scenario 4, FR-005/SC-007).

**Depends on**: T016 depends on T002 and T011 (extends the outcome-capture pattern they establish to the remaining collectors); T017 depends on T016; T018 depends on T017; T019 and T020 depend on T018; T021 depends on T003 and T016.

**Checkpoint**: Every evidence read distinguishes failed from empty; `diagnose` is told which collectors are untrusted; a partial failure still reaches a verdict.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Whole-repository validation once every story has landed.

- [ ] T023 [P] Run `python3 .github/scripts/run-local-gates.py` and confirm every PR-time gate — including the new Gate 18 and Gate 19 — passes cleanly against the repository as it stands after all five user stories land (quickstart.md step 2, SC-004).
- [ ] T024 [P] Run the quickstart.md "reintroduce a broken shape" drill (step 3): temporarily revert the `collect-annotations` step to its pre-fix shape, confirm `run-local-gates.py` fails naming `watchdog.yml` and the offending line with error text alone sufficient to write the fix back (SC-006), then restore the file.
- [ ] T025 Run `bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh` (full suite) and `python3 .github/scripts/verify-gate-19.py` to confirm nothing else regressed (quickstart.md steps 4-6).
- [ ] T026 Confirm no published stage's declared `workflow_call` inputs, outputs, or secrets other than `watchdog.yml`'s new `untrusted-collectors` output were widened (FR-015): diff `watchdog.yml`'s and `auto-update-spec-kit.yml`'s `on: workflow_call` blocks against the pre-feature versions.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Empty — no blocking prerequisites beyond Setup.
- **User Stories (Phase 3-7)**: All can start once Phase 1 completes. US1 (Phase 3), US2 (Phase 4), and US4 (Phase 6) have no dependencies on each other and can proceed fully in parallel. US3 (Phase 5) depends on US1's and US2's fixes (T002, T005, T006) having landed only for its final regression-case fixture (T014) — its gate logic and self-test scaffolding (T012, T013) can be built in parallel with US1/US2. US5 (Phase 7) depends on US1's (T002) and US3's (T011) collectors already carrying `${PIPESTATUS[0]}`-captured read outcomes before it extends the pattern to the remaining collectors.
- **Polish (Phase 8)**: Depends on all five user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: No dependencies on other stories.
- **User Story 2 (P1)**: No dependencies on other stories.
- **User Story 3 (P1)**: Its gate logic is independent; its final "passes on the fixed repository" regression case depends on User Stories 1 and 2's fixes, plus its own T011 rewrite.
- **User Story 4 (P2)**: No dependencies on other stories.
- **User Story 5 (P2)**: Depends on User Story 1 (T002) and User Story 3 (T011) for the collectors it extends.

### Within Each User Story

- Gate/harness scaffolding can often proceed before the site it will validate is fixed, but the scenario that proves the fix depends on the fix landing first.
- Story complete before moving to the next priority, per the Implementation Strategy below.

### Parallel Opportunities

- T001 (Setup) has no parallel counterpart — it's a single verification task.
- Once Setup completes, User Stories 1, 2, and 4 (Phases 3, 4, 6) can proceed fully in parallel — they touch disjoint files/regions.
- Within User Story 1: T003 (new `verify-gate-19.py`) can be drafted in parallel with T002 (the `watchdog.yml` rewrite it will validate), though its "fix" scenarios only pass once T002 lands.
- Within User Story 2: T006 and T009 are marked `[P]` — different regions/files from the tasks around them.
- Within User Story 5: T022 is marked `[P]` — a different file/suite from T016-T021's sequential `watchdog.yml` edits.

---

## Parallel Example: Setup Complete, Stories Begin

```bash
# Launch independent user stories together once T001 passes:
Task: "US1 — rewrite watchdog.yml's Collect: annotations step (T002)"
Task: "US2 — rewrite auto-update-spec-kit.yml's compare step (T005)"
Task: "US4 — replace the stale docs bullet (T015)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 3: User Story 1 — this alone stops the single most damaging defect (annotation evidence silently dropped past page 1, indistinguishable from "nothing to report").
3. **STOP and VALIDATE**: Run `verify-gate-19.py` independently; confirm it passes and its mutation check fails on the pre-fix shape.

### Recommended MVP: All Three P1 Stories

Spec.md frames the three P1 stories as one unit ("the three fixes are worth one run each; the gate is worth every future run") — User Story 1 alone fixes the worst site, but User Stories 2 and 3 are equally P1 and time-sensitive (upstream is already near the release-list page boundary) and the gate is what stops a fourth site ever landing. Deliver Phases 3-5 together before considering this feature's core value shipped.

### Incremental Delivery

1. Complete Setup → baseline confirmed.
2. Add User Story 1 → validate via `verify-gate-19.py` → most damaging site fixed.
3. Add User Story 2 → validate via `t1_detect`/`t10_notes` → release detection deterministic.
4. Add User Story 3 → validate via `verify-gate-18.py` and `run-local-gates.py` → future instances of this defect class are blocked at review time.
5. Add User Story 4 → doc corrected, no executable validation needed beyond a read-through.
6. Add User Story 5 → validate via the extended `verify-gate-19.py` scenario and T022 → failed reads are now visible to the diagnosis step.
7. Phase 8 Polish → whole-repository sweep.

---

## Notes

- `[P]` tasks touch different files or disjoint regions with no ordering dependency on other unfinished tasks.
- `[Story]` label maps each task to its user story for traceability.
- Several tasks share `watchdog.yml`; where two tasks touch the same step or adjacent steps, the dependency is called out explicitly rather than marked `[P]`.
- Every fix task's correctness is ultimately checked by the harness/gate task in the same story (T002↔T003/T004, T005-T006↔T007-T010, T011-T012↔T013-T014) — do not consider a story's implementation tasks done until its own validation task passes.
- Reverting any one of the three original fixes (T002's annotations rewrite, T005, T006) must fail its story's own test, not only Gate 18 (FR-012).
