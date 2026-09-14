---

description: "Task list template for feature implementation"
---

# Tasks: Rate-limited agent verdict

**Input**: Design documents from `/specs/047-rate-limited-verdict/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: This repository has no application test suite (plan.md
"Testing"). Its test surface is the deterministic gates in
`lint-workflows.yml` (Gate 22, Gate 36, and the new Gate 51) plus their
own self-test/mutation phases (constitution VIII) — those gate tasks
are this feature's tests and are ordered after the code they exercise,
matching how every prior spec in this repository has extended these
gates.

**Organization**: Tasks are grouped by user story (US1/US2/US3, spec.md
priorities P1/P2/P3) so each can be delivered and verified independently
per its own Independent Test.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no ordering dependency on another unfinished task)
- **[Story]**: US1, US2, or US3 — omitted for Setup/Foundational/Polish

## Path Conventions

Single-project CI/CD feature — no `src`/`tests` split. All paths are
repository-root-relative, matching plan.md's Project Structure.

---

## Phase 1: Setup

**Purpose**: Obtain the ground-truth transcript shapes this feature's
gate fixtures must be built from, before any synthetic case is authored.

- [X] T001 Pull the real `execution-output` artifacts named in issue
  #306/#300 (the three 2026-09-12 rate-limited runs and the one
  2026-08-28 rate-limited run) and the 2026-09-08 binary-not-found runs
  from #278, and record each one's exact `rate_limit_event` /
  terminal-`result` field shape (which of `status`, `rateLimitType`,
  `resetsAt`, `terminal_reason`, `api_error_status` each run actually
  carries, per research.md R1's "risk carried forward to tasks/implement").
  This shape is the ground truth T003's Gate 22 `CASES` entries in
  `.github/scripts/verify-agent-verdict.py` and T006's Gate 36 fixtures
  in `.github/scripts/verify-watchdog-run-failure-paths.sh` must be built
  from — not a hand-authored approximation (SC-004).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The one shared classifier every user story depends on
(FR-006's single-home rule) and the gate that proves it. No user story
task can start until this phase is complete.

**⚠️ CRITICAL**: US1, US2, and US3 all read `verdict` and
`rate-limit-reset` from this composite's output — none of their steps
can be written, let alone tested, before it exists.

- [X] T002 In `.github/actions/wing-commander-agent-verdict/action.yml`'s
  "Classify agent run verdict" step (the `run:` block containing the
  existing `if [ "$subtype" = "error_max_turns" ]` / `elif [ "$is_error" =
  "true" ]` chain, roughly lines 80-151), add the new `rate-limited`
  branch **after** the `error_max_turns` check and **before** the
  existing generic `is_error`/subtype fallthrough
  (contracts/agent-verdict-extension.md's exact ordering):
  `rate_limit_evidence_present` = `(result_json.terminal_reason ==
  "api_error" AND result_json.api_error_status == 429)` OR (the
  transcript contains any `.type=="rate_limit_event"` record), evaluated
  against the same already-open transcript file (FR-002: no second file
  read, no network call). Fires when the terminal record is already a
  failure (`is_error=="true"` OR `subtype != "success"`) AND
  `rate_limit_evidence_present`. Add the new `rate-limit-reset` output
  (declared in the action's `outputs:` block and set in this same step):
  "the `rate_limit_event` record's `resetsAt` value verbatim when present
  and non-empty, else the literal string `unknown`" (data-model.md),
  computed from the **last** matching record, "Empty string for every
  verdict other than `rate-limited`" (data-model.md) — never epoch-zero,
  never fabricated (spec.md edge case). Update the `verdict` output's
  description string to `"healthy | exhausted | rate-limited | failed |
  unclassifiable"` and add new `reason` prose for the new case (e.g.
  `"usage window (five_hour) exhausted, resets at 2026-09-14T18:00:00Z"`
  or `"...resets at unknown"`). Keep the step's unconditional `exit 0`
  contract, and leave every existing verdict's classification
  byte-for-byte unchanged for every transcript shape that does not meet
  this new condition (FR-001, FR-002, FR-003, FR-004, FR-005, FR-006).

- [X] T003 Extend Gate 22 (`.github/scripts/verify-agent-verdict.py`,
  the `CASES` list and its mutation phase) with the three cases FR-016
  requires, built from T001's real field shapes: (1) a terminal 429
  rejection → `verdict: rate-limited`, `reason` names the window and
  reset time, `rate-limit-reset` carries the reset time verbatim; (2) a
  `rate_limit_event` mid-transcript followed by a successful terminal
  `result` (`subtype: "success"`, `is_error: false`) → `verdict: healthy`
  (spec.md edge case "a 429 the runtime recovered from" — a
  `rate_limit_event` anywhere in the transcript must never demote an
  otherwise-successful run); (3) a terminal `result` with `is_error:
  true`, `terminal_reason: "api_error"`, `api_error_status: 500` (or any
  non-429 value) and no `rate_limit_event` record anywhere → `verdict:
  failed`, unchanged reason text (429-specific corroboration must not
  widen to any API error). Add a mutation for the new branch (e.g.
  dropping the `error_max_turns`-before-`rate-limited` ordering, or the
  429-status check) and confirm the existing mutations still fire
  unchanged. Depends on T002 (extends the step this gate exercises) and
  T001 (fixture ground truth).

**Checkpoint**: The classifier emits `rate-limited` and
`rate-limit-reset` correctly and Gate 22 proves it under mutation. Every
user story phase below can now begin.

---

## Phase 3: User Story 1 - The maintainer is not paged for a usage-window outage (Priority: P1) 🎯 MVP

**Goal**: A rate-limited watchdog diagnose step is reported as a usage
outage, not a crash, and the stage-8b verifier stays green for it alone
while still filing for anything it doesn't explain.

**Independent Test**: Replay an execution-output artifact from a known
429 run through the verdict classifier and the stage-8b verification
path, and confirm the reported outcome names the usage window and its
reset time, and that no `pipeline-defect` issue is created.

### Implementation for User Story 1

- [X] T004 [US1] In `.github/workflows/watchdog.yml`'s `diagnose` job,
  give the existing "Read back diagnose outcome" step (`id:
  diagnose-outcome`, the `if [ "${{ steps.diagnose.outcome }}" !=
  "success" ] || [ "$agent_ok" != "true" ]` chain, roughly lines
  1701-1759) a new branch checked **before** the existing
  `diagnose-failed` test: `if steps.diagnose-verdict.outputs.verdict ==
  'rate-limited': outcome = rate-limited` (ordering is load-bearing per
  contracts/watchdog-reporting.md — a rate-limited rejection also fails
  the pre-existing `agent_ok` test). Add a new "Report 'rate-limited' to
  lifecycle issue" step, sibling of the existing "Report 'diagnose
  failed' to lifecycle issue" (~line 1833) and "Report 'passed
  inspection' to lifecycle issue" (~line 1801) steps, same `if:
  steps.diagnose-outcome.outputs.outcome == 'rate-limited'` gate and same
  two delivery paths (comment on the lifecycle issue when set, else
  `$GITHUB_STEP_SUMMARY`). The body must (FR-007/FR-008/FR-009): state
  plainly that the usage window was exhausted; name the reset time from
  `steps.diagnose-verdict.outputs.rate-limit-reset` (already `"unknown"`
  when absent — never re-derived here); state the run was therefore
  **not inspected** (not a clean bill of health); never use the words
  "failed" or "crashed"; be visually distinguishable at a glance from the
  "diagnose failed" report (different leading emoji/heading, different
  prose, not a shared string with one word swapped); link the inspected
  run. Leave the existing "Fail loud on non-healthy agent verdict" step
  untouched — it still fires for `rate-limited` (FR-015), keeping the
  diagnose *step* red while the job and run stay green via the existing
  `continue-on-error: true`.

- [X] T005 [US1] In `.github/scripts/verify-watchdog-run.sh`, add one new
  evidence read alongside the existing checks 3/4 block (the `step()`
  calls near lines 100-139): `c="$(step diagnose 'Report "rate-limited"
  to lifecycle issue')"; rate_limited=false; [ -n "$c" ] && [ "$c" !=
  "skipped" ] && rate_limited=true` (same evidence-reading pattern
  already used for `diagnose-failed`/`could-not-inspect` — no new API
  call, the `jobs_json` fetch already covers this step). Suppress check 7
  (~line 179, "diagnose execution log has no successful terminal result
  record...") when `rate_limited=true`, replacing the `reason` call with
  a `note` call ("diagnose execution log has no successful terminal
  result — expected, rate-limited run") — text and condition otherwise
  unchanged (FR-010). Suppress only the **floor** breach of check 2's
  duration band (~line 91, `if [ "$duration" -lt "$floor" ]`) the same
  way when `rate_limited=true`; the **ceiling** breach (~line 93, `elif
  [ "$duration" -gt "$ceiling" ]`) is never suppressed (FR-010, FR-011,
  US1 Acceptance Scenario 4). Check 3 needs no code change — the
  "diagnose failed" reporter it reads is skipped by construction once
  T004 lands (mutual exclusion). Every other check (1, the ceiling arm of
  2, 3, 4, 5, 6, 8) stays fully live, so a rate-limited run with an
  independent defect still fails the job for that defect alone
  (FR-011). If the `gh`/API read for the new step lookup fails,
  `rate_limited` must resolve to `false` (fail safe — an unreadable
  evidence read must never silently suppress a real reason). Depends on
  T004 (reads that step's exact name).

- [X] T006 [US1] Extend Gate 36
  (`.github/scripts/verify-watchdog-run-failure-paths.sh`) with the four
  fixtures contracts/verifier-suppression.md requires, built from T001's
  real field shapes where applicable: (1) rate-limited diagnose, nothing
  else wrong → verifier exits 0, no `pipeline-defect` issue
  created/commented; (2) rate-limited diagnose **and** an unrelated red
  job → verifier exits 1, `fail_reasons` contains only the unrelated
  reason, and the `pipeline-defect` issue is filed/commented mentioning
  only that reason; (3) rate-limited diagnose **and** a stalled diagnose
  job (duration over the ceiling) → verifier exits 1 for the stall alone,
  proving the ceiling arm is unaffected by the floor-arm suppression; (4)
  a `gh` stub failure (the existing `GH_STUB_FAIL` shape from PR #168) on
  the new `step diagnose 'Report "rate-limited"...'` lookup →
  `rate_limited` resolves to `false` and the run is verified by its
  pre-existing rules, not silently passed. Depends on T004 and T005.

**Checkpoint**: A rate-limited watchdog run reports as a usage outage,
never a crash, and stage-8b stays green for it alone while still failing
for any unrelated defect (SC-001, SC-002).

---

## Phase 4: User Story 2 - The uninspected run is still on the record (Priority: P2)

**Goal**: Suppressing the `pipeline-defect` filing does not suppress the
fact that a run went uninspected — it accumulates on one durable,
non-triage-bearing issue per exhausted window.

**Independent Test**: Drive two rate-limited runs inside one window and
confirm both appear on a single `usage-limit`-labelled issue, each naming
the run and its reset time, with no second issue opened and nothing
carrying the `pipeline-defect` label.

### Implementation for User Story 2

- [X] T007 [US2] In `.github/workflows/watchdog.yml`'s `diagnose` job, add
  a new "Ensure usage-limit issue" step, sibling of T004's "Report
  'rate-limited'..." step and gated on the same `if:
  steps.diagnose-outcome.outputs.outcome == 'rate-limited'` condition
  (research.md R5, FR-012/FR-013): (1) `gh label create usage-limit
  --color ... --description "Watchdog: a run went uninspected because the
  usage window was exhausted" --force` (idempotent, mirrors the existing
  `pipeline-defect` label bootstrap); (2) `gh issue list --label
  usage-limit --state open --json number --jq '.[0].number // empty'` —
  "the ENTIRE dedup key is 'does an open `usage-limit` issue currently
  exist,' no fingerprint" (contracts/watchdog-reporting.md); (3) if found,
  `gh issue comment <number>` appending one bullet (run URL, reset time
  from `steps.diagnose-verdict.outputs.rate-limit-reset`, "went
  uninspected"); (4) if not found, `gh issue create --label usage-limit
  --title "watchdog: usage window exhausted" --body <first bullet>`; (5)
  on a failed `gh issue list` (network/API error), do **not** create a
  new issue — "a failed search is not evidence of absence, skip filing
  rather than risk a duplicate" (same discipline as the existing
  `pipeline-defect` dedup, citing #167/#169). This step never touches the
  `pipeline-defect` label and never runs the existing
  fingerprint/dedup machinery in `triage`/`act`. Register this step (and
  T004's report step) as the seed entries of `EXEMPT_SITES` when T012
  authors it (data-model.md's "Exemption registry"). Depends on T004
  (same job, same `if:` gate, natural sibling addition).

**Checkpoint**: Every rate-limited run is discoverable via a single
`usage-limit` label filter, one issue per exhausted window, never mixed
into `pipeline-defect` triage (SC-003).

---

## Phase 5: User Story 3 - Every stage names the outcome the same way (Priority: P3)

**Goal**: Every agent-bearing stage — not just the watchdog — names a
rate-limited transcript as `rate-limited` in its summary and durable
metrics record, keeps failing loud for it in control flow, and stops
short of filing or commenting about it as a failure.

**Independent Test**: Feed a rate-limited transcript to the metrics
summary a non-watchdog stage produces, and confirm it names the outcome
as rate-limited rather than degrading it to an unclassified or failed
outcome.

### Implementation for User Story 3

- [X] T008 [P] [US3] In
  `.github/actions/wing-commander-metrics-summary/action.yml`'s
  outcome-resolution statement (`case "$VERDICT" in
  healthy|exhausted|failed|unclassifiable) ...`, ~line 468), add
  `rate-limited` as a fifth accepted literal mapped straight through
  (`outcome_val="$VERDICT"`). Do **not** extend the action's standalone
  fallback classifier (the branch used only when no `verdict` input is
  supplied at all) — research.md R3: that would create the second copy
  of the detection FR-006 forbids, for a code path every in-scope call
  site already bypasses by passing `verdict` explicitly. The rendered
  `**Verdict**: %s — %s` line needs no other change; it renders whatever
  it is handed (FR-014).

- [X] T009 [P] [US3] Author
  `.github/scripts/verify-rate-limited-exemption.py` (Gate 51), following
  `.github/scripts/verify-gate-23.py`'s existing YAML-parsed-never-grepped
  template. It must walk every step, in every job, in every
  `.github/workflows/*.yml` file, and find every step whose `run:` body
  contains `gh issue create`, `gh issue comment`, or `gh pr comment` (a
  plain substring/regex test over the parsed `run:` string) **and** whose
  own `if:`, or an enclosing job's `if:`, textually references
  `.outputs.verdict` (covers both `steps.<id>.outputs.verdict` and
  `needs.<job>.outputs.verdict` shapes). For each discovered site, PASS
  if `(file, step name)` is in a small `EXEMPT_SITES` constant seeded
  with T004's `'Report "rate-limited" to lifecycle issue'` and T007's
  `'Ensure usage-limit issue'` steps (data-model.md's "Exemption
  registry" — "Grows only when a future feature adds a new sanctioned
  rate-limited-aware issue/comment writer"); PASS if the site's own `if:`
  condition, parsed as a boolean expression, provably excludes the
  literal `rate-limited` (a `!= 'rate-limited'` term ANDed into the
  condition, or an equivalent allow-list none of whose values is
  `rate-limited`); otherwise FAIL, naming the file and step (FR-015b).
  Add a self-test fixture (matching Gate 6/7/12/23's precedent): a
  synthetic workflow file with (a) a correctly-narrowed site (must PASS),
  (b) a correctly-registered `EXEMPT_SITES` site (must PASS), and (c) a
  site gated on `verdict != 'healthy'` alone with no exclusion and no
  registration (must FAIL, by name) — proving the gate can fail its own
  subject (constitution VIII).

- [X] T010 [US3] Wire Gate 51 into `.github/workflows/lint-workflows.yml`'s
  `lint` job, immediately after the existing Gate 50 steps (~line 3138-
  3150): a "Gate 51 — every verdict-gated issue/comment write excludes
  rate-limited or is a registered handler" step running `python3
  .github/scripts/verify-rate-limited-exemption.py`, plus its self-test
  invocation. Confirm Gate 10 (`wc_gate_registry.py`'s convention check)
  passes for the new script in the same PR (it fails on any orphaned
  `verify-*.py`). Depends on T009.

- [X] T011 [P] [US3] Run Gate 51 (from T010) against the repository and
  fix every non-watchdog site it reports. Two candidates are already
  known (research.md R7 — not an exhaustive list; Gate 51's own run is
  authoritative): `finalize.yml`'s "Verify agent output"/"Announce
  finalize failure (agent output)" chain (~lines 800-824), which today
  posts a failure-describing comment whenever
  `steps.summarize-verdict.outputs.verdict != 'healthy'` — narrow this so
  a `rate-limited` verdict does not set `failed=true`/does not trigger
  that comment, while the separate, unchanged "Fail loud on non-healthy
  agent verdict" step (~line 725) keeps failing the job for it (FR-015);
  and `cleanup.yml`'s "Resolve completion summary (with fallback)"/"Close
  lifecycle issue and flip label" chain (~lines 796-825), which renders a
  generic "automated summary unavailable" fallback whenever
  `steps.summarize-verdict.outputs.verdict != "healthy"` before closing
  the lifecycle issue — this fallback text must not read as a crash for a
  `rate-limited` run (FR-015a). Fix any additional site Gate 51 reports
  that research.md did not anticipate. Depends on T010 (needs the gate to
  confirm each fix).

- [X] T012 [US3] Confirm (no code expected) that every stage's existing
  "Fail loud on non-healthy agent verdict" step is unmodified by T008-
  T011: `rate-limited` is not `healthy`, so each one still fails its job
  for it exactly as for `exhausted`/`failed`/`unclassifiable`, and no
  `needs`-gate anywhere starts reading a rate-limited stage as completed
  (FR-015). Feed Scenario 1's fixture through a non-watchdog stage's
  metrics summary (e.g. `clarify.yml`'s `agent`/`agent-verdict`/metrics-
  summary trio) and confirm: the run summary and durable metrics record
  both name `rate-limited` (FR-014); the "Fail loud" step still fires and
  the job still ends failed (FR-015); and nowhere does an issue or
  comment land beyond the run's own log and step summary (FR-015a).
  Depends on T008 and T011.

**Checkpoint**: Every agent-bearing stage names a rate-limited transcript
consistently, keeps failing loud in control flow, and files or comments
nothing extra about it.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and the full local gate suite this repository
requires before any push (CLAUDE.md "Before pushing").

- [ ] T013 [P] Update `docs/architecture.md`'s existing verdict-vocabulary
  paragraph (currently "a `wing-commander-agent-verdict` step classifies
  each run (healthy/exhausted/failed/unclassifiable) from the transcript
  alone", ~line 233-239) to list `rate-limited` in the same enumeration,
  and add one sentence naming Gate 22's three new cases and the new Gate
  51, immediately after the existing Gate 22/23 sentence (FR-017).
  Depends on T003 (Gate 22's new cases) and T010 (Gate 51 exists).

- [ ] T014 Run `python .github/scripts/run-local-gates.py` (the full
  PR-time gate suite, per CLAUDE.md) and confirm it passes, including
  Gate 22, Gate 36, and the new Gate 51, and that no other gate regresses
  (SC-005). Then walk quickstart.md's twelve scenarios end to end as a
  final sign-off, confirming each still matches its documented expected
  outcome. Depends on every task above.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup (T001's real fixture
  shapes feed T003) — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational only.
- **User Story 2 (Phase 4)**: Depends on Foundational; T007 additionally
  depends on T004 (same watchdog job, sibling `if:` gate).
- **User Story 3 (Phase 5)**: Depends on Foundational only for T008/T009;
  T010-T012 chain within the phase as noted per-task.
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### User Story Dependencies

- **US1 (P1)**: No dependency on US2 or US3 — independently testable
  after Foundational alone.
- **US2 (P2)**: Its single task (T007) is written as a sibling addition
  to US1's T004 in the same file/job, so implement it immediately after
  US1 lands; it does not depend on US1's verifier changes (T005/T006).
- **US3 (P3)**: Independent of US1 and US2's implementation — needs only
  the Foundational classifier. T011's fixes reference candidates outside
  the watchdog entirely.

### Parallel Opportunities

- T008 and T009 (different files: `wing-commander-metrics-summary/action.yml`
  vs. the new Gate 51 script) can run in parallel once Foundational is
  done.
- T013 can be drafted in parallel with T014 once its own dependencies
  (T003, T010) are met, since they touch different files.
- US1 and US3 can be staffed in parallel by different people once
  Foundational is done (US2's single task is small enough to fold into
  the same person's US1 work, given its file/sibling dependency on T004).

---

## Parallel Example: User Story 3

```bash
# Once Foundational (T002/T003) is done, these two have no ordering dependency:
Task: "Add rate-limited to the outcome allow-list in wing-commander-metrics-summary/action.yml"
Task: "Author verify-rate-limited-exemption.py (Gate 51) with its self-test fixture"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001).
2. Complete Phase 2: Foundational (T002-T003) — CRITICAL, blocks every
   story.
3. Complete Phase 3: User Story 1 (T004-T006).
4. **STOP and VALIDATE**: replay the real evidence artifacts through the
   classifier and stage-8b verifier (US1's Independent Test); confirm
   SC-001/SC-002.
5. This alone removes the entire cost the issue is paying (zero
   `pipeline-defect` filings, zero red stage-8b runs, a one-report
   diagnosis) — every later phase is refinement, per spec.md's own
   priority rationale.

### Incremental Delivery

1. Setup + Foundational → the shared classifier is trustworthy and
   gate-proven.
2. Add US1 → validate independently → the watchdog stops paging
   maintainers for usage outages (MVP).
3. Add US2 → validate independently → uninspected runs stay on the
   record without re-entering defect triage.
4. Add US3 → validate independently → every other stage names the
   outcome the same way and cannot silently reintroduce a failure filing.
5. Polish → documentation matches shipped behavior, full gate suite is
   green (SC-005), ready to push per CLAUDE.md.

## Notes

- [P] tasks touch different files with no ordering dependency on an
  unfinished task.
- This repository's "tests" are its deterministic gates (Gate 22, Gate
  36, Gate 51) and their own self-test/mutation phases — there is no
  separate application test suite to write first.
- Every task that touches `.github/workflows/*.yml` should get a pass
  from the `review-step-gating` skill before merge (CLAUDE.md), since
  every task in Phases 3-5 adds or edits an `if:` condition.
- Commit after each task or logical group; stop at any checkpoint to
  validate a story independently before moving to the next priority.
