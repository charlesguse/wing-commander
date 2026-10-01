---

description: "Task list template for feature implementation"
---

# Tasks: Name-Free Stage Identity for Watchdog Collectors

**Input**: Design documents from `/specs/099-name-free-stage-identity/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/,
quickstart.md (all present)

**Tests**: This feature has no application test suite — "tests" are the
repository's own checked-in gate scripts (`.github/scripts/verify-*.py`),
which FR-013/SC-006 require for every branch this feature introduces. They
are listed as regular implementation tasks below, not a separate
test-first phase, matching quickstart.md's "red gate mid-implementation,
green once its sites land" sequencing.

**Organization**: Tasks are grouped by user story per spec.md's priorities
(P1/P2/P3). This is a GitHub Actions workflow/composite-action repository,
not an application — every task names an exact file (and, where the file
has drifted from spec.md's own citations, the line numbers confirmed
fresh against the current branch).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Foundational and Setup tasks carry no story label; they block every story.

---

## Phase 1: Setup

- [X] T001 [P] Run `python .github/scripts/run-local-gates.py` from the
      repo root to confirm the pre-change baseline is green, so any gate
      failure introduced later is attributable to this feature.
- [X] T002 Re-confirm the next unclaimed gate number in
      `.github/workflows/lint-workflows.yml` immediately before claiming
      it for the FR-012 gate (T032/T033). As of this writing the highest
      claimed gate is 125 (header comment at lines 4611-4620, steps at
      4621-4626), making 126 the next number, but research.md R9 warns
      other specs may land concurrently on this repository's own board —
      re-grep for `Gate 1[0-9][0-9]` before committing to the number.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Compute the resolved stage identity once, in the one shared
home (FR-003), and expose it to every consumer. Both User Story 1 (the
FR-002 sites) and User Story 2 (the unresolved-stage reporting and the
FR-014 warning) read this output; nothing below can be built without it.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Add a new `id: name-fallback` step to
      `.github/actions/wing-commander-inspected-run-identity/action.yml`,
      immediately after the existing `id: stage` step (lines 285-318,
      which produces `record-stage`). The new step runs only when
      `steps.stage.outputs.record-stage` is empty, maps `inputs.run-name`
      through the data-model.md "Name-derived stage map" (exactly 9
      entries: `Wing Commander · 1 intake`→intake, `· 2 clarify`→clarify,
      `· 3 plan`→plan, `· 4 tasks`→tasks, `· 5 implement`→implement,
      `· 6 finalize`→finalize, `· 7 cleanup`→cleanup, `· rebase`→rebase,
      `· 9 pr conversation`→pr-conversation; `Wing Commander · 8 watchdog`
      is deliberately absent), and computes two step outputs:
      `resolved-stage` (`record-stage` if non-empty, else the name match,
      else empty) and `resolved-stage-source` (`record`, `name`, or empty).
      Implements contracts/resolved-stage-identity.md Rule 1 and
      data-model.md's Resolved stage identity / Name-derived stage map
      tables.
- [X] T004 Wire `resolved-stage` and `resolved-stage-source` into the
      composite's `outputs:` block (`.github/actions/wing-commander-
      inspected-run-identity/action.yml` lines 132-156, alongside the
      existing `record-stage` output at lines 151-156), sourced from
      T003's step. Must not add a second metrics-record download (Rule 3
      — both steps already read the same file at
      `$RUNNER_TEMP/spec-slug-metrics-record`) and must not change
      `record-stage`'s own value or type (Rule 4 — spec 109 keys
      `tool-denial` on it unchanged).
- [X] T005 Expose `resolved-stage`/`resolved-stage-source` as `collect`
      job outputs in `.github/workflows/watchdog.yml` (the job's
      `outputs:` block, lines 356-366), sourced from
      `steps.spec-slug.outputs.resolved-stage`/`-source` — the same
      composite invocation at lines 478-480 that already exposes `slug`,
      `spec-dir`, and `record-stage` to this job. This lets every later
      job (`diagnose`, `triage`, `act`) read
      `needs.collect.outputs.resolved-stage` the same way they already
      read `needs.collect.outputs.run-name`.

**Checkpoint**: `resolved-stage`/`resolved-stage-source` are computed once
and readable from any job. User Story 1 and User Story 2 work can now
proceed (in parallel, if staffed).

---

## Phase 3: User Story 1 - An adopter with their own wrapper names gets the same watchdog coverage (Priority: P1) 🎯 MVP

**Goal**: Every FR-002 site — the slug-fallback allowlist and the seven
`watchdog.yml` collector/guard sites — decides stage scope from the
resolved stage identity (or, for the slug-fallback, the record's own
spec-identity declaration) instead of matching the run's display name.

**Independent Test**: Drive one watchdog inspection against a run of a
wrapper whose display name shares no substring with the reference names,
where the underlying spec is in a state the spec-meta collector must
flag. The finding is filed. Repeat with the reference-named wrapper: the
same finding, same facts (SC-001).

### Spec-identity declaration infrastructure (serves the slug-fallback site only — FR-008/FR-008a/FR-008b)

- [X] T006 [US1] Add `spec.identity_is_own` (boolean, optional, additive)
      to the `spec` group of the `## Shape` fence in `specs/043-durable-
      metrics-record/contracts/metrics-record-schema.md` (the fence is at
      lines 21-84; the `spec` group's existing fields — `spec_dir`,
      `issue`, `identity_available` — are at lines 35-39). State FR-008a's
      reading explicitly: a schema-version-1 record predating this field
      MUST be read as `identity_is_own: false`. This is an additive
      change per that document's Rule 1 (lines 9-11): no existing field's
      name, type, or meaning changes.
- [X] T007 [US1] Update `.github/scripts/verify-metrics-record-schema.py`
      so `spec.identity_is_own` validates as an optional boolean —
      present as `true`/`false`, or absent — and its absence MUST NOT be
      reported as a schema violation (FR-008a). `REQUIRED_SPEC` (lines
      96-100) stays the required-fields dict for `spec_dir`/`issue`/
      `identity_available`; add `identity_is_own` as a new optional-field
      check alongside it.
- [X] T008 [P] [US1] Add three fixtures under `.github/scripts/fixtures/
      metrics-record-schema/`: one record with `spec.identity_is_own:
      true`, one with `false`, and one that omits the key entirely
      (representing a pre-feature record), proving T007 accepts all three
      and that the omitted case is read as FR-008a's `false`, not a schema
      failure.
- [X] T009 [US1] Add a required input `spec-identity-is-own`
      (`'true'`/`'false'`, no default) to `.github/actions/wing-commander-
      metrics-summary/action.yml`'s `inputs:` block (lines 23-174), thread
      it through the `render` step (`id: render`, lines 198-751) — the
      `emit_record()` jq args at lines 287-289 and the rendered `spec: {
      ... }` object at lines 334-338 — so the emitted record carries
      `spec.identity_is_own` verbatim, alongside `spec_dir`/`issue`/
      `identity_available`.
- [X] T010 [US1] Extend `.github/scripts/verify-metrics-summary-record-
      emission.py`'s `run_case` harness (lines 213-260) with cases
      asserting the rendered record carries `spec.identity_is_own`
      verbatim for both `spec-identity-is-own: 'true'` and `'false'`
      inputs.

### Call sites: every `wing-commander-metrics-summary` invocation declares its spec identity (SC-008) — depends on T009

- [X] T011 [P] [US1] Pass `spec-identity-is-own: 'true'` at the call site
      in `.github/workflows/intake.yml:987`.
- [X] T012 [P] [US1] Pass `spec-identity-is-own: 'true'` at the call site
      in `.github/workflows/clarify.yml:837`.
- [X] T013 [P] [US1] Pass `spec-identity-is-own: 'true'` at the call
      sites in `.github/workflows/plan.yml:1248,1290`.
- [X] T014 [P] [US1] Pass `spec-identity-is-own: 'true'` at the call
      sites in `.github/workflows/tasks.yml:1214,1259`.
- [X] T015 [P] [US1] Pass `spec-identity-is-own: 'true'` at the call
      sites in `.github/workflows/implement.yml:1150,1867,2562,2715`.
- [X] T016 [P] [US1] Pass `spec-identity-is-own: 'true'` at the call site
      in `.github/workflows/finalize.yml:851`.
- [X] T017 [P] [US1] Pass `spec-identity-is-own: 'false'` at the call
      site in `.github/workflows/watchdog.yml:2595`.
- [X] T018 [P] [US1] Pass `spec-identity-is-own: 'false'` at the call
      site in `.github/workflows/cleanup.yml:813`.
- [X] T019 [P] [US1] Pass `spec-identity-is-own: 'false'` at the call
      site in `.github/workflows/rebase.yml:819`.
- [X] T020 [P] [US1] Pass `spec-identity-is-own: 'false'` at the call
      sites in `.github/workflows/pr-conversation.yml:1078,2389`.
- [X] T021 [P] [US1] Pass `spec-identity-is-own: 'false'` at the call
      sites in `.github/workflows/board-loop.yml:905,1263,1640,2207,2804,
      3421,3946,4128,4543`.
- [X] T022 [P] [US1] Pass `spec-identity-is-own: 'false'` at the call
      site in `.github/workflows/lifecycle-review-gate.yml:666`.

### Slug-fallback conversion (the one FR-002 exception — FR-008)

- [X] T023 [US1] Replace the six-name slug-fallback case block in
      `.github/actions/wing-commander-inspected-run-identity/action.yml`
      (lines 206-209: `case "$RUN_NAME" in "Wing Commander · 1
      intake"|...|"Wing Commander · 6 finalize") record_fallback=true ;;
      esac`) with a read of the already-downloaded record's
      `spec.identity_is_own` field: trust `spec.spec_dir` (the slug
      source) only when that same record declares `identity_is_own:
      true`. Implements contracts/spec-identity-declaration.md Rule 3.
      Depends on T006 (schema field documented) and T009 (field actually
      emitted).

### FR-002 consumer sites in watchdog.yml (depends on T005)

- [X] T024 [US1] Convert branch-drift's push-expected-stage gate
      (`watchdog.yml:692-698`: `case "$RUN_NAME" in "Wing Commander · 3
      plan"|"...4 tasks"|"...5 implement") ;; *) skip ;; esac`) to switch
      on `needs.collect.outputs.resolved-stage` matching
      `plan`/`tasks`/`implement`. Add the third arm contracts/resolved-
      stage-identity.md Rule 2 requires: when
      `needs.collect.outputs.resolved-stage-source` is empty, skip AND
      append `{"collector":"collect-branch-drift","outcome":
      "unresolved"}` to `collector-outcomes.json` (same jq pattern already
      used at lines 864-865), instead of silently taking the existing
      `*)` out-of-scope path.
- [X] T025 [US1] Convert branch-drift's implement-only since-created
      baseline arms (`watchdog.yml:795` and `852`, each currently
      `[ "$RUN_NAME" = "Wing Commander · 5 implement" ]`) to test
      `[ "$resolved_stage" = "implement" ]` against
      `needs.collect.outputs.resolved-stage`.
- [X] T026 [US1] Convert branch-drift's stage label for the summary line
      (`watchdog.yml:866-870`: `case "$RUN_NAME" in "Wing Commander · 4
      tasks") stage_label="tasks" ;; "...5 implement")
      stage_label="implement" ;; esac`) to switch on `resolved-stage`
      instead of `$RUN_NAME`.
- [X] T027 [US1] Convert the spec-meta collector's expected-stage map
      (`watchdog.yml:1023-1034`: `case "$RUN_NAME" in "Wing Commander · 1
      intake") expected="spec" ;; ... esac`) to switch on `resolved-stage`
      — the FR-007 mapping itself is unchanged (intake→spec, plan→plan,
      tasks→tasks, implement→implement, finalize→review) — and add the
      unresolved third arm (distinct from the existing `*)` skip at lines
      1030-1033) per Rule 2.
- [X] T028 [US1] Convert final-pr-claims's finalize scope guard
      (`watchdog.yml:1705-1708`: `if [ "$RUN_NAME" != "Wing Commander · 6
      finalize" ]`) to test `[ "$resolved_stage" != "finalize" ]`, adding
      the unresolved third arm per Rule 2.
- [X] T029 [US1] Convert spec-collision's intake scope guard
      (`watchdog.yml:1829-1832`: `if [ "$RUN_NAME" != "Wing Commander · 1
      intake" ]`) to test `[ "$resolved_stage" != "intake" ]`, adding the
      unresolved third arm per Rule 2.
- [X] T030 [US1] Convert the watchdog's self-inspection cascade guard
      (`watchdog.yml:3507`: `if: needs.collect.outputs.run-name == 'Wing
      Commander · 8 watchdog'`) to `if: needs.collect.outputs.resolved-
      stage == 'watchdog'`. Self-inspection's own record always carries
      `stage: watchdog` (spec.md Edge Cases: "Self-inspection"), so
      `record-stage` never falls through to the name fallback here and no
      unresolved arm is needed at this single site.

### Verification (FR-012, FR-013, SC-001, SC-002, SC-006, SC-008)

- [X] T031 [US1] Add `.github/scripts/verify-watchdog-resolved-stage-
      consumers.py`, a new fixture-driven gate script (following the
      `find_step`/`run_step` harness pattern `verify-metrics-summary-
      record-emission.py`'s `run_case` already uses), proving for each of
      T024-T030's seven sites: a renamed wrapper and the reference-named
      wrapper produce identical outcomes for the same underlying record
      (SC-001); the unresolved third arm fires only when `resolved-stage-
      source` is empty; and research.md R7's fixture rows are covered —
      record with no stage (`stage_available: false`), a missing record
      entirely, an unrecognised display name with no record, and a
      record-vs-name disagreement (record wins, per FR-009).
- [X] T032 [US1] Add `.github/scripts/verify-no-reference-name-stage-
      match.py` (Gate 126 — re-verify the number per T002) implementing
      contracts/stage-identity-name-gate.md: scan `watchdog.yml` and
      `wing-commander-inspected-run-identity/action.yml` for the ten
      reference display-name literals (`"Wing Commander · 1 intake"`
      through `"· 9 pr conversation"`, `"· rebase"`, and `"· 8
      watchdog"`) used inside a gating shell conditional (`case`/`if`)
      outside the `id: name-fallback` step (T003); scan every
      `wing-commander-metrics-summary` call site (T011-T022's 12 files)
      for a literal `spec-identity-is-own:` key (SC-008). Fail loudly —
      not "0 violations" — if either target file is unreadable or the
      `name-fallback` step cannot be located. Include a `--self-test` flag
      covering contract Fixtures 1-5 (clean pass; a reintroduced match
      outside `name-fallback`; a match inside `name-fallback`, which
      passes; a metrics-summary call site missing the key; the
      `name-fallback` step renamed/removed, which errors).
- [X] T033 [US1] Wire Gate 126 into `.github/workflows/lint-workflows.yml`:
      a `- name: "Gate 126 — ..."` step (`if: "!cancelled()"`, `run:
      python3 .github/scripts/verify-no-reference-name-stage-match.py`)
      immediately followed by a `"Gate 126 self-test — ..."` step running
      the same script with `--self-test`, matching Gate 124/125's
      convention (lines 4604-4626) including a header comment citing this
      spec (#750) and the number-allocation rationale.

**Checkpoint**: User Story 1 is fully functional and independently
testable — renamed and reference-named wrappers produce identical
watchdog findings, and Gate 126 fails loudly if any FR-002 site regresses
to name-matching.

---

## Phase 4: User Story 2 - A maintainer can tell when stage identity was not resolved (Priority: P2)

**Goal**: When no source (record or name) yields a stage, the watchdog
says so in its report, and warns specifically about an unrecognised
display name only when the run otherwise looks like a pipeline stage run.

**Independent Test**: Inspect a run that emitted no metrics record and
carries an unrecognised display name. The inspection's own report names
the collectors that could not run, and the top-level verdict is not an
unqualified clean bill of health (SC-003).

- [X] T034 [US2] Extend the `aggregate` step (`watchdog.yml:2001-2042`) to
      compute a new `stage-unresolved-collectors` output (names + count)
      from `collector-outcomes.json` entries with `outcome=="unresolved"`
      — added alongside, not merged into, the existing `untrusted` jq
      filter at lines 2033-2034, which continues to select only
      `outcome=="failed"` (FR-005 forbids folding the third state into
      the second).
- [X] T035 [US2] Add `stage-unresolved-collectors` to the `collect` job's
      `outputs:` block (`watchdog.yml:356-366`), alongside
      `collectors-failed`/`untrusted-collectors`.
- [X] T036 [US2] Extend both existing deterministic report strings — the
      "Report 'could not inspect'" step (`watchdog.yml:2046-2060`, body at
      line 2055) and the "Report 'passed inspection'" step
      (`watchdog.yml:2076-2101`, bodies at lines 2093 and 2095) — to
      append "; N evidence class(es) not examined because the inspected
      run's stage could not be identified" whenever
      `stage-unresolved-collectors`'s count is non-zero, so SC-003's
      "unqualified pass" never reaches the lifecycle issue.
- [X] T037 [US2] Extend the `collect-execution-output` step
      (`watchdog.yml:515-653`) to emit a new `claude-execution-output-
      found` output (`true`/`false`, from the existing `found` variable
      computed at line 650) — no additional artifact download (R6;
      FR-004 budgets only the metrics-record download, not this one, but
      forbids growing either).
- [X] T038 [US2] Add a new step in the `collect` job implementing the
      FR-014 name warning: fires only when
      `needs.collect.outputs.resolved-stage-source` is empty AND
      `steps.collect-execution-output.outputs.claude-execution-output-
      found` is `true`. Does not fire when the stage resolved (regardless
      of display name) or when no execution-output artifact was found
      (regardless of display name) — T003's 9-stage name-fallback
      coverage already keeps this repository's own reference-named
      cleanup/rebase/pr-conversation runs from triggering it (FR-014a).
- [X] T039 [P] [US2] Extend T031's `verify-watchdog-resolved-stage-
      consumers.py` (or add a sibling script) with fixture coverage
      proving: the FR-014 warning fires exactly once when the stage is
      unresolved and the execution-output artifact was found; it does not
      fire when the stage resolved; and it does not fire when no
      execution-output artifact was found — matching spec.md's US2
      acceptance scenarios 2-5 and SC-007.

**Checkpoint**: User Stories 1 and 2 both work independently — an
unresolved stage is never silently reported as a clean pass, and the name
warning fires exactly where FR-014/FR-014a intend.

---

## Phase 5: User Story 3 - The adoption docs state exactly what still depends on a name (Priority: P3)

**Goal**: `docs/adoption.md` states, in one place, that wrapper display
names are free-form and which behavior (if any) still reads them.

**Independent Test**: Read `docs/adoption.md` alone and answer "may I
rename my wrappers, and what do I lose?" without opening `watchdog.yml`
(SC-005).

- [X] T040 [US3] Add a new subsection to `docs/adoption.md` directly after
      "A wrapper-owned feature needs a wrapper change too" (lines
      612-639), stating: wrapper display names are free-form for all ten
      stages; the sole behavior that still reads one is the FR-009
      fallback, active only when a run leaves no metrics record (expired
      or missing artifact, early failure, cancellation); every
      reference-named example wrapper already shown in this document
      continues to work unchanged either way (FR-011, research.md R8).

**Checkpoint**: All three user stories are independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T041 Run `python .github/scripts/run-local-gates.py` end-to-end and
      confirm every gate — including the new Gate 126 — is green, per
      CLAUDE.md's pre-push gate suite and quickstart.md step 1.
- [ ] T042 After this feature's implementation PR merges, re-drive one
      watchdog inspection (`gh workflow run` on the stage-8 wrapper)
      against a run of a temporarily renamed duplicate wrapper, confirm
      its findings match an inspection of the reference-named wrapper for
      the same underlying run (SC-001), and record the run URL and
      outcome as evidence on the PR or lifecycle issue #750 — CLAUDE.md's
      rule for behavior that only runs in Actions, and quickstart.md step
      6.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS every user story —
  `resolved-stage`/`resolved-stage-source` must exist before any FR-002
  site can be converted (US1) or any unresolved-stage reporting can be
  added (US2).
- **User Story 1 (Phase 3)**: Depends on Foundational. Independent of
  US2/US3.
- **User Story 2 (Phase 4)**: Depends on Foundational only (not on US1's
  FR-002 site conversions — T034-T039 read `collector-outcomes.json`'s
  shape and `resolved-stage-source`, both already available after
  Foundational). Can proceed in parallel with US1 if staffed, though
  T034's "unresolved" entries only start appearing in practice once US1's
  T024/T027/T028/T029 land.
- **User Story 3 (Phase 5)**: No code dependency on US1/US2 — the
  documentation states the design's fixed rules, which Foundational's R1
  decision (recorded in research.md) already settled. Can start anytime
  after Foundational.
- **Polish (Phase 6)**: T041 depends on all desired stories being
  complete; T042 depends on the implementation PR having merged.

### Within User Story 1

- T006 → T007 → T008 (schema field before validation before fixtures)
- T009 depends on T006 (the field must be documented before an action
  input writes it)
- T011-T022 depend on T009 (the input must exist before call sites pass
  it)
- T023 depends on T006 and T009
- T024-T030 depend on T005 (Foundational) only — independent of the
  spec-identity-declaration work (T006-T023), since they read
  `resolved-stage`, not `spec.identity_is_own`
- T031 depends on T024-T030 (it tests their behavior)
- T032 depends on T003 (needs `id: name-fallback` to exist as the
  permitted exception site) and on T011-T022 (scans their `with:` blocks)
- T033 depends on T032

### Parallel Opportunities

- T011-T022 (12 call-site tasks, one per workflow file) are fully
  parallel.
- T024-T030 (7 FR-002 site conversions, all within `watchdog.yml` but at
  disjoint line ranges) can be worked in parallel by different
  contributors, though as edits to one file they will need to be
  reconciled at commit time.
- US2's T034-T039 can proceed in parallel with US1's Phase 3 once
  Foundational is done.
- US3's T040 can proceed in parallel with everything once Foundational
  (really, just research.md's already-settled R8 decision) is available.

---

## Parallel Example: User Story 1 call sites

```bash
Task: "Pass spec-identity-is-own: 'true' in .github/workflows/intake.yml:987"
Task: "Pass spec-identity-is-own: 'true' in .github/workflows/clarify.yml:837"
Task: "Pass spec-identity-is-own: 'false' in .github/workflows/cleanup.yml:813"
Task: "Pass spec-identity-is-own: 'false' in .github/workflows/board-loop.yml:905,1263,1640,2207,2804,3421,3946,4128,4543"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational — the composite's
   `resolved-stage` computation).
2. Complete Phase 3 (User Story 1): spec-identity declaration
   infrastructure, all 12 call sites, the slug-fallback conversion, all
   seven FR-002 site conversions, and Gate 126.
3. **STOP and VALIDATE**: run the local gate suite; confirm SC-001
   (identical outcomes for renamed vs. reference-named wrappers) and
   SC-002 (Gate 126 green) hold.
4. This alone closes the defect spec.md opens with — a renamed wrapper
   now gets full watchdog coverage.

### Incremental Delivery

1. Setup + Foundational → shared `resolved-stage` identity ready.
2. Add User Story 1 → validate independently → this is the MVP.
3. Add User Story 2 → unresolved stages are reported, not silently passed.
4. Add User Story 3 → the documentation question is answerable without
   reading a workflow file.
5. Polish: full gate-suite confirmation, then the post-merge Actions
   re-drive CLAUDE.md requires for this Actions-only behavior.

---

## Notes

- [P] tasks touch different files and carry no unresolved dependency on
  each other.
- Every FR-002 site conversion (T024-T030) and the slug-fallback
  conversion (T023) are two independent changes to different parts of the
  same composite/workflow files — do not conflate the two mechanisms
  (`resolved-stage` vs. `spec.identity_is_own`); contracts/resolved-
  stage-identity.md Rule 1's "no re-derivation" applies to the former
  only.
- Commit after each task or logical group; re-run
  `python .github/scripts/run-local-gates.py` before any push per
  CLAUDE.md.
- T042 cannot be completed until after merge — it is listed here so it is
  not forgotten, per CLAUDE.md's rule for Actions-only behavior, not as
  work the implement stage can close out pre-merge.

## Maintainer Feedback

- [ ] **Gate numbering (blocks merge).** This feature takes Gates 138 and 139, not 133/134 (held by specs 090 and 100) or the script's stale "Gate 126" comment. Renumber:
  - [ ] `lint-workflows.yml:4783-4799` → Gate 138, including the comment's stale reservation list
  - [ ] `lint-workflows.yml:4801-4816` → Gate 139
  - [ ] `verify-no-reference-name-stage-match.py:2`, `:236`, `:360`
  - [ ] `tasks.md:251,266,267,269,276,364,451,454`
  - [ ] optionally `contracts/stage-identity-name-gate.md` and `plan.md:148`

## Maintainer Feedback

- [ ] **Resolved-stage consumers gate is broken (blocks merge).** `verify-watchdog-resolved-stage-consumers.py:109`'s `resolve_stage()` runs the composite's real stage step, which needs `$GITHUB_REPOSITORY` under `set -u`; locally the "missing record entirely" and "unrecognised display name, no record" rows fail, and in CI the same rows only pass because a real `gh run download 1 --repo … ` with `GH_TOKEN=x` fails — contradicting the docstring at :91-95, which says the download is skipped.
  - [ ] Put a `gh` stub on `PATH` (the `wc_gh_capture`/`path_prepend` convention)
  - [ ] Set `GITHUB_REPOSITORY` in `env_extra`
  - [ ] Add a `--self-test` mode
  - [ ] Correct the docstring at :91-95

## Maintainer Feedback

- [ ] **FR-014 warning step can take down the whole inspection (blocks merge).** `watchdog.yml:679-694` runs `gh issue comment` with no `continue-on-error`, ahead of all eight collectors, `signal-ids` and `aggregate`, which use the implicit `success()`. If the comment fails, every collector, aggregate, both reports and diagnose are skipped.
  - [ ] Add `continue-on-error: true`, or better, fold the warning into the aggregate report text
