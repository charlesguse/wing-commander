---

description: "Task list for Stage-Found Defect Filing Through a Deterministic Filing Step"
---

# Tasks: Stage-Found Defect Filing Through a Deterministic Filing Step

**Input**: Design documents from `specs/056-stage-found-defect-filing/`
(plan.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: FR-030/SC-009 require a checked-in fixture per shipped failure
branch. These are implementation deliverables (built alongside the
composite/gate they exercise, per research.md D14), not a spec-requested
TDD red/green cycle — no separate "write failing tests first" subsection is
used here.

**Organization**: Tasks are grouped by user story from `spec.md`. Because
this feature is one shared mechanism (a single new composite plus one
extended one) rather than independently deployable slices, later
user-story phases sometimes add a scoped, well-defined edit to a file an
earlier phase already created — each such task names exactly what is being
added and to which existing file.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

This is a GitHub Actions pipeline repository, not an application; "source"
is workflows (`.github/workflows/`), composite actions
(`.github/actions/`), gate scripts (`.github/scripts/`), and one new schema
directory (`.github/schemas/`). No frontend/backend split applies.

---

## Phase 1: Setup

**Purpose**: Establish the one checked-in artifact every later phase reads.

- [X] T001 Create `.github/schemas/stage-finding.schema.json` — a JSON
  Schema (draft 2020-12) document exactly per
  `contracts/stage-finding-schema.md`: top-level object,
  `required: ["title", "what", "evidence", "fingerprint_basis"]`,
  `additionalProperties: false`; `title`/`what` are `string, minLength: 1`;
  `evidence` requires `file_paths` (`array` of `string, minLength: 1`,
  `minItems: 1`) and allows optional `detail` (`string`),
  `additionalProperties: false`; `fingerprint_basis` requires
  `file_path` and `gate_or_artifact` (both `string, minLength: 1`),
  `additionalProperties: false`. `stage` and `run_url` are deliberately
  absent (FR-010: supplied by the filing composite's own inputs, never the
  proposal).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared infrastructure every user story's tasks build on — the
finding validator, and the two idioms (`durable-failure-issue`,
`outstanding-task-item`) promoted per FR-016/D8/D9 before any new composite
may call them.

**⚠️ CRITICAL**: No user story phase can complete until this phase is done.

- [X] T002 [P] Create `.github/scripts/verify-stage-finding-schema.py`
  exposing `validate_finding(obj: dict) -> tuple[bool, str]`. Generate its
  required-field/type checks by reading `.github/schemas/stage-finding.schema.json`
  at import time (research.md D5) rather than duplicating the field list as
  a second literal — no third-party JSON Schema library dependency,
  matching `verify-metrics-record-schema.py`'s existing hand-checked
  pattern. (depends on T001)
- [X] T003 `git mv .github/actions/_shared/durable-failure-issue
  .github/actions/wing-commander-durable-failure-issue` — a pure rename,
  no interface change; preserve the action.yml's existing inputs
  (`token`, `operation`, `label`, `label-color`, `label-description`,
  `title`, `body-file`, `close-comment`), outputs (`issue-number`,
  `action-taken`), and its "never templates a body itself" header comment
  (research.md D8).
- [X] T004 In `auto-release.yml`, repoint both `uses:` lines (the "File or
  update the failure issue" step and the "Close the failure issue on
  success" step, currently `./.github/actions/_shared/durable-failure-issue`)
  to `./.github/actions/wing-commander-durable-failure-issue`; no other
  input changes (byte-identical behavior). (depends on T003)
- [X] T005 In `auto-update-spec-kit.yml`, repoint the "File or update the
  auto-update:failed issue (rollback)" step's `uses:` line (currently
  `./.wing-commander-pipeline/.github/actions/_shared/durable-failure-issue`)
  to `./.wing-commander-pipeline/.github/actions/wing-commander-durable-failure-issue`;
  no other input changes. (depends on T003)
- [X] T006 [P] In `.github/scripts/verify-single-home-idioms.py`, repoint
  `DECLARED_HOMES["failure-issue"]` from
  `.github/actions/_shared/durable-failure-issue/action.yml` to
  `.github/actions/wing-commander-durable-failure-issue/action.yml`
  (research.md D8's "consequence": `check_promotion` already forbids any
  published stage or non-underscore composite from resolving `_shared/`,
  so a stale `DECLARED_HOMES` entry here would let a straggler on the old
  path go undetected). (depends on T003)
- [X] T007 [P] Create `.github/actions/wing-commander-outstanding-task-item/action.yml`
  per `contracts/wing-commander-outstanding-task-item.md`: required inputs
  `token`, `issue-number`, `phrase`, `artifact-url`; optional `context`
  (default `""`); one `shell: bash` step running
  `gh issue comment "$ISSUE_NUMBER" --body "- [ ] $PHRASE — $ARTIFACT_URL${CONTEXT:+ $CONTEXT}"`;
  no outputs (a failure to comment is the caller's to handle).
- [X] T008 In `pr-conversation.yml`, replace the "Post outstanding task
  item on the lifecycle issue" step's inline
  `gh issue comment "$ISSUE_NUMBER" --body "- [ ] $phrase — $ARTIFACT_URL (from PR #$PR_NUMBER)"`
  line with a `uses: ./.github/actions/wing-commander-outstanding-task-item`
  call, keeping the existing `case "$EFFECTIVE_CATEGORY"` phrase-selection
  switch unchanged and passing `phrase` from it, `issue-number` from
  `needs.classify-and-announce.outputs.issue-number`, `artifact-url` from
  `steps.act-result.outputs.artifact-url`, and
  `context: (from PR #${{ inputs.pr-number }})`. (depends on T007)
- [X] T009 [P] In `.github/scripts/verify-single-home-idioms.py`, add
  `DECLARED_HOMES["outstanding-task-item"] = ".github/actions/wing-commander-outstanding-task-item/action.yml"`
  and a `check_outstanding_task_item` function mirroring
  `check_failure_issue`'s shape (scan every subject file's step lists for
  the literal `gh issue comment ... "- [ ] "` pattern outside the declared
  home), registered in `ALL_CHECKS`; extend the script's `--self-test`
  scratch-file table with one entry that plants a second copy of this
  pattern, asserts it is caught, then asserts clean once removed. (depends
  on T007)

**Checkpoint**: Both idioms live at their promoted, single home; no
consumer remains on the retired `_shared/` path. All user story work below
can begin.

---

## Phase 3: User Story 2 - Code decides what gets filed, never the agent (Priority: P1)

**Goal**: The deterministic filing composite exists in full and is proven
correct by a checked-in fixture set, with no agent and no stage wiring
involved yet.

**Independent Test**: Feed `wing-commander-stage-findings/tests/run-tests.sh`
a fixture set — a well-formed finding, a malformed one, one that
duplicates an open issue, one that duplicates a closed issue, and more
findings than the cap — and confirm exactly the expected filings, appends,
and drops, each with its log line, without any agent running
(quickstart.md §1).

- [X] T010 [US2] Extend `.github/actions/wing-commander-durable-failure-issue/action.yml`
  with two new optional inputs, both no-op for a caller that omits them:
  `marker` (default `""` — a literal string the lookup additionally
  requires inside a candidate issue's body) and `state-scope` (default
  `open`; `open` \| `all`, meaningful only when `marker` is set). When
  `marker` is set, change the lookup's `gh issue list` call to
  `--state "$STATE_SCOPE"` and additionally filter for `body` containing
  `$marker` (plus fetch `state`); a match with `state == open` behaves as
  today (`commented`); a match with `state == closed` creates a new issue
  instead of commenting (FR-012 — never reopening a settled thread),
  exposing the matched issue's number via a new `matched-closed-issue`
  output, and setting `action-taken: created-linked-closed`. (depends on
  T003)
- [X] T011 [US2] Create `.github/actions/wing-commander-stage-findings/action.yml`
  with the full input list — `token`, `stage`, `enabled`, `channel-mode`
  (`fenced-block` \| `structured-array`), `execution-output-path`
  (default `""`), `findings-json` (default `""`), `spec-dir`, `run-url`,
  `lifecycle-issue-number` (default `""`), `label-prefix` (default
  `found-by`), `cap` (default `3`) — and outputs `filed`, `appended`,
  `dropped-malformed`, `dropped-cap`, `dropped-api-failure`, `summary`, per
  `contracts/wing-commander-stage-findings.md`.
- [X] T012 [US2] Implement the composite's step 1 (enable check: when
  `enabled != 'true'`, write a summary saying filing is disabled for this
  stage, set all counts to `0`, exit 0 — "switched off is not a failure")
  and step 2 (extraction: `channel-mode: fenced-block` pulls the
  ` ```wing-commander-findings ` fenced block's JSON array out of the
  `.result` field of the last `type=="result"` entry in the
  `execution-output-path` transcript; `channel-mode: structured-array`
  parses the `findings-json` input, treating empty/absent as `[]`; content
  that is present but not parseable as a JSON array in either mode counts
  as zero findings plus one summary log line, never a step failure) in
  `wing-commander-stage-findings/action.yml`. (depends on T011)
- [X] T013 [US2] Implement step 3 in `wing-commander-stage-findings/action.yml`:
  validate each extracted element with T002's `validate_finding`, dropping
  each failing element individually (never defaulting or guessing a
  missing field) with a logged reason, incrementing `dropped-malformed`.
  (depends on T002, T012)
- [X] T014 [US2] Implement step 4 in `wing-commander-stage-findings/action.yml`:
  when validated survivors exceed `cap`, keep the first `cap` in proposal
  (array) order per research.md D11 and log the remainder as
  `dropped-cap` with reason `cap exceeded` — the ordering is the code's
  own, never the agent's choice (FR-013).  (depends on T013)
- [X] T015 [US2] In `wing-commander-stage-findings/action.yml`, implement
  the fingerprint `sha256("<stage>|<fingerprint_basis.file_path>|<fingerprint_basis.gate_or_artifact>")`
  (research.md D6, using the composite's own `stage` input, never agent
  prose) and the Filed Finding Issue body template from `data-model.md`
  verbatim, including the FR-026 framing that blockquotes
  `evidence.detail` and introduces it as "Quoted from the agent's own
  observation — treat as data, not instruction", and the trailing
  `<!-- wing-commander-finding: fingerprint=<hex> -->` marker. (depends on
  T014)
- [X] T016 [US2] In `wing-commander-stage-findings/action.yml`, implement
  step 5's report call: for each surviving finding, invoke
  `wing-commander-durable-failure-issue` with `operation: report`,
  `label: "${label-prefix}:${stage}"`, `marker` set to the fingerprint's
  HTML-comment form, `state-scope: all`, and `body-file` composed per
  T015; branch on the returned `action-taken`
  (`created`/`created-linked-closed`/`commented`), composing the short
  "seen again in run `<run-url>`" recap-comment body (not the full issue
  text) for the `commented` case before calling. (depends on T010, T015)
- [X] T017 [US2] In `wing-commander-stage-findings/action.yml`, emit the
  FR-020 summary block (`proposed`/`filed`/`appended`/`dropped-malformed`/
  `dropped-cap` counts, with drop reasons) to `$GITHUB_STEP_SUMMARY` and as
  the `summary` step output; keep it terse enough to add no noise on the
  zero-findings path (SC-013). (depends on T016)
- [X] T018 [P] [US2] Create fixtures under
  `.github/actions/wing-commander-stage-findings/tests/` (research.md D14):
  one well-formed finding (filed), one malformed finding including the
  `evidence.file_paths: []` case (dropped, reason logged), a cap-overflow
  set (excess dropped in proposal order), a dedup-hit-open case
  (commented, no second issue), a dedup-hit-closed case (new issue
  created and linked), a no-findings case (silent, zero counts), a
  fenced-block-channel fixture, a structured-array-channel fixture with
  the array present, and a structured-array-channel fixture that omits
  the array entirely (must validate as zero findings). Use an
  injectable/stubbed `gh` shim for the dedup fixtures (no live network).
  (depends on T017)
- [X] T019 [US2] In `wing-commander-stage-findings/action.yml`, make the
  step-5 report call's `gh`/API failure path caught locally (no uncaught
  non-zero exit propagating out of the composite step; the step itself
  still exits 0), counted as `dropped-api-failure`, with the finding's
  `title`/`what` written verbatim to the step log (FR-025); add the
  matching API-failure fixture (stubbed `gh` shim returning non-zero) to
  the T018 fixture set, asserting the finding text is preserved in the
  captured log and the fixture harness still reports exit 0. (depends on
  T016, T018)
- [X] T020 [US2] Create `.github/actions/wing-commander-stage-findings/tests/run-tests.sh`,
  a harness that drives the composite's extraction/validation/cap/
  fingerprint logic and `verify-stage-finding-schema.py` directly against
  every T018/T019 fixture (no live network, no `uses:` invocation),
  printing one PASS line per fixture per quickstart.md §1's expected list.
  (depends on T019)
- [X] T021 [P] [US2] In `.github/scripts/verify-single-home-idioms.py`, add
  `DECLARED_HOMES["stage-findings"] = ".github/actions/wing-commander-stage-findings/action.yml"`
  and a `check_stage_findings` function fingerprinting the co-occurrence of
  the fingerprint formula (`sha256`/`stage`/`fingerprint_basis`) and the
  schema-validation call, registered in `ALL_CHECKS`; extend `--self-test`
  with a scratch-file entry planting a second copy of that co-occurrence
  and asserting it is caught, then clean once removed. (depends on T011)

**Checkpoint**: The filing composite is fully functional and proven
correct in isolation via `run-tests.sh`; nothing yet calls it from a real
stage run.

---

## Phase 4: User Story 1 - A defect a stage met on the way reaches the board (Priority: P1)

**Goal**: Wire the proposal channel and the now-complete composite into
all six published stages end to end.

**Independent Test**: Drive one stage run against a tree carrying a
deliberately planted defect outside that stage's task, and confirm an
issue exists afterwards carrying the description, evidence paths, run
URL, and stage-and-spec attribution line — with the stage's own output
unchanged from a run without the planted defect (quickstart.md §3).

- [X] T022 [P] [US1] Add the FR-003 findings paragraph (the stable
  substring "do not attempt to file it yourself", worded once per
  `contracts/stage-wiring.md` and reused verbatim across all six prompts,
  parameterized only by channel-mode) to `intake.yml`'s "Create spec from
  issue" (`id: agent`) prompt, using the structured-array clause ("the
  findings array of your structured result").
- [X] T023 [P] [US1] Add the same paragraph, structured-array clause, to
  `clarify.yml`'s clarify agent step's prompt.
- [X] T024 [P] [US1] Add the same paragraph, fenced-block clause (a fenced
  ` ```wing-commander-findings ` block in the final message), to both
  `plan.yml` agent steps (`agent-auto`, `agent-pr`).
- [X] T025 [P] [US1] Add the same fenced-block-clause paragraph to both
  `tasks.yml` agent steps (`agent-auto`, `agent-pr`).
- [X] T026 [P] [US1] Add the same fenced-block-clause paragraph to
  `implement.yml`'s "Implement and converge (cycle)" and "Implement and
  converge (retry at escalation model)" agent steps.
- [X] T027 [P] [US1] Add the same fenced-block-clause paragraph to
  `finalize.yml`'s "Summarize changes and remaining work" (`id: summarize`)
  agent step.
- [X] T028 [US1] Add an optional `findings` array property to `intake.yml`'s
  inline `--json-schema` literal, default/absent meaning zero findings,
  leaving the existing required `specified`/`clarifications` properties and
  their validation unchanged (FR-007).
- [X] T029 [US1] Add an optional `findings` array property to `clarify.yml`'s
  inline `--json-schema` literal, leaving the existing required
  `answered`/`clarifications` properties and their validation unchanged
  (FR-007).
- [X] T030 [US1] Add three `workflow_call.inputs` to each of `intake.yml`,
  `clarify.yml`, `plan.yml`, `tasks.yml` (`findings-filing-enabled`
  boolean default `false`, `findings-label-prefix` string default
  `found-by`, `findings-cap` number default `3`) and the same three inputs
  with `findings-filing-enabled` default `true` to `implement.yml` and
  `finalize.yml`, per `data-model.md`'s "Stage Filing Configuration" and
  FR-001a (identical shape across all six, differing only in that one
  default).
- [X] T031 [US1] Add a "File findings from this run" step to `intake.yml`'s
  job immediately after the "Resolve created spec" (`id: created`) step:
  `if: ${{ !cancelled() && steps.created.outcome != 'skipped' }}`,
  `continue-on-error: true`, `uses: ./.github/actions/wing-commander-stage-findings`,
  `channel-mode: structured-array`, and the remaining `with:` values per
  `contracts/wing-commander-stage-findings.md`'s call-site wiring (token,
  stage, enabled, findings-json, spec-dir, run-url, lifecycle-issue-number,
  label-prefix, cap). (depends on T011, T028, T030)
- [X] T032 [US1] Same step, after `clarify.yml`'s "Determine clarification
  follow-up outcome" (`id: clarification`) step, `channel-mode:
  structured-array`. (depends on T011, T029, T030)
- [X] T033 [US1] Same step, after whichever of `plan.yml`'s "Verify plan
  committed (auto)" / "Verify plan PR and flip stage label" steps ran,
  `channel-mode: fenced-block`, `execution-output-path` pointed at plan's
  `claude-execution-output.json`. (depends on T011, T030)
- [X] T034 [US1] Same step, after whichever of `tasks.yml`'s "Verify tasks
  committed (auto)" / "Verify tasks PR (pr)" steps ran, `channel-mode:
  fenced-block`. (depends on T011, T030)
- [X] T035 [US1] Same step, after `implement.yml`'s "Consolidate final
  outcome" (`id: final`) step, `channel-mode: fenced-block` (research.md
  D1: the one attribution surface for the combined implement⟲converge
  turn). (depends on T011, T030)
- [X] T036 [US1] Same step, after `finalize.yml`'s "Verify agent output"
  (`id: verify-agent-output`) step, `channel-mode: fenced-block`. (depends
  on T011, T030)
- [X] T037 [P] [US1] Pass the three new inputs through as declared `with:`
  values in `wing-commander-1-intake.yml`'s call into `intake.yml`.
  (depends on T030)
- [X] T038 [P] [US1] Same pass-through in `wing-commander-2-clarify.yml`'s
  call into `clarify.yml`. (depends on T030)
- [X] T039 [P] [US1] Same pass-through in `wing-commander-3-plan.yml`'s
  call into `plan.yml`. (depends on T030)
- [X] T040 [P] [US1] Same pass-through in both call sites of
  `wing-commander-4-tasks.yml` (generate and approved modes) into
  `tasks.yml`. (depends on T030)
- [X] T041 [P] [US1] Same pass-through in `wing-commander-5-implement.yml`'s
  call into `implement.yml`. (depends on T030)
- [X] T042 [P] [US1] Same pass-through in `wing-commander-6-finalize.yml`'s
  call into `finalize.yml`. (depends on T030)
- [X] T043 [US1] Create `.github/scripts/verify-stage-findings-wiring.py`
  (FR-031): for each of the six stage workflows named in
  `contracts/stage-wiring.md`, fail loudly — naming the stage and which
  side is missing — if exactly one of {the
  `wing-commander-stage-findings` `uses:` step, the FR-003 paragraph's
  stable substring in the agent step's prompt} is present without the
  other, checked identically regardless of that stage's
  `findings-filing-enabled` default (FR-001a); fail loudly, not
  vacuously, if a named workflow file cannot be found at all. (depends on
  T022-T027, T031-T036)
- [X] T044 [P] [US1] Add fixtures for `verify-stage-findings-wiring.py`
  (FR-030): a checked-in copy of one stage workflow with the step present
  and the paragraph absent, and the mirror case, each asserted to fail;
  assert the real six workflows pass post-implementation. (depends on
  T043)
- [X] T045 [US1] Register `verify-stage-findings-wiring.py` as a new
  PR-time gate step in `lint-workflows.yml` (Gate 72 — Gate 71 was taken
  by this branch's own earlier registration of the
  wing-commander-stage-findings fixture harness; renumbered the same way
  Gate 60 documents, mirroring Gate 60's registration shape) so
  `run-local-gates.py` picks it up automatically. (depends on T043)

**Checkpoint**: A real dispatched stage run now proposes, files, and
labels a finding end to end; User Story 1's independent test is
satisfiable.

---

## Phase 5: User Story 4 - Filing never costs the stage its outcome (Priority: P1)

**Goal**: Confirm, at the stage-integration level, that the call-site
gating added in Phase 4 actually satisfies FR-022–FR-025, per this
repository's own `review-step-gating` skill requirement for any change
touching an `if:`/`continue-on-error:`.

**Independent Test**: Force the filing step to fail (deny its API call) on
an otherwise healthy stage run and confirm the stage's outcome, declared
outputs, and lifecycle transition are identical to a run where filing
succeeded — and that the failure is visible in the run's own summary
(quickstart.md §4).

- [ ] T046 [US4] Run the `review-step-gating` skill over the six "File
  findings from this run" steps added in T031-T036, confirming: the
  `if: ${{ !cancelled() && steps.<read-back>.outcome != 'skipped' }}`
  condition correctly distinguishes a cancelled run (must not file) from
  a run whose agent step failed or exhausted its budget before reaching
  the read-back (must not be converted into a filing) per FR-024; the
  step's own `continue-on-error: true` cannot strand any reporter that
  reads `always()` downstream. Fix any findings the skill surfaces in the
  same six steps. (depends on T031-T036)
- [ ] T047 [US4] Execute quickstart.md §4's failure-tolerance drill against
  a disposable/test repository (pass a token with no issue-creation
  permission to `wing-commander-stage-findings` for one run) and confirm:
  the stage's own outcome, declared outputs, and lifecycle transition are
  identical to a run where filing succeeded; the failure and the unfiled
  finding's title/what are visible in the run's log and summary (FR-025);
  the stage is not reported red because of it (FR-022). Record the
  result. (depends on T019, T045)

**Checkpoint**: Filing failure is provably inert to every in-scope stage's
own outcome.

---

## Phase 6: User Story 3 - The lifecycle issue shows what the run spun off (Priority: P2)

**Goal**: Every filing (or dedup append) becomes visible from the
lifecycle issue and from wherever a maintainer already scans run
outcomes, without opening the board.

**Independent Test**: Drive one stage run that files a finding, then read
only the lifecycle issue and confirm it names what was spun off and links
it, without opening the run or the board.

- [X] T048 [US3] In `wing-commander-stage-findings/action.yml`'s step 5,
  after an `action-taken` of `created` or `created-linked-closed`, call
  `wing-commander-outstanding-task-item` (only when
  `lifecycle-issue-number` is non-empty) with phrase "a defect was filed
  by the `<stage>` stage" and `context: (run $RUN_URL)`; after `commented`,
  call it with phrase "a defect met by the `<stage>` stage was recorded on
  an existing issue"; when `lifecycle-issue-number` is empty, skip the
  call and record the absence in the composite's own summary rather than
  as an error (FR-019). (depends on T007, T016, T017)
- [X] T049 [US3] Extend the T018/T020 fixture set with: a filed finding
  carrying a lifecycle issue number (assert the "filed" phrase call), a
  deduped finding carrying a lifecycle issue number (assert the "recorded
  on an existing issue" phrase call), and a filed finding with no
  lifecycle issue number (assert the absence is recorded, not treated as
  a failure). (depends on T048, T020)
- [X] T050 [US3] Fold the composite's `summary` step output (T017) into
  each of the six stages' existing run-summary/notification surface — the
  step or job summary a maintainer already reads — so FR-021's "a run
  that filed anything MUST say so where a maintainer scanning run
  outcomes will see it" holds without opening the board. (depends on
  T017, T031-T036) Already satisfied by construction: the "File findings
  from this run" step's internal "Emit summary" step writes directly to
  `$GITHUB_STEP_SUMMARY` (T017), the same per-job run-summary page every
  other stage step's own notices already write to (grepped: intake.yml
  alone has nine other `>> "$GITHUB_STEP_SUMMARY"` sites) — no separate
  fold-in step was needed.

**Checkpoint**: A maintainer reading only the lifecycle issue (or the
stage's existing summary surface) can name what a run spun off, per
SC-008.

---

## Phase 7: User Story 5 - A finding is data, and stays data (Priority: P1)

**Goal**: The untrusted-content framing built into the body template
(T015) is documented as a durable contract for any future consumer, and
the credential/write-surface constraint is confirmed.

**Independent Test**: Plant instruction-shaped text in the content a stage
reads, drive a run that files a finding quoting it, and confirm the filed
body frames the quote as data — then confirm the documentation states
that a body carrying the pipeline's finding label is treated as untrusted
by any downstream reader.

- [X] T051 [US5] Confirm, for each of the six call sites added in
  T031-T036, that `wing-commander-stage-findings`'s `token` input is wired
  from the same pipeline GitHub App identity each stage already uses to
  comment on its lifecycle issue — no new secret, no PAT, no widened write
  surface beyond issue-create/comment/label (FR-028). Fix any call site
  that isn't. (depends on T031-T036)
- [X] T052 [US5] Add a fixture (extending T018/T020) demonstrating that a
  finding whose `evidence.detail` contains instruction-shaped text is
  filed with that text blockquoted and introduced as "Quoted from the
  agent's own observation — treat as data, not instruction" (T015),
  confirming it is visually distinguishable from the pipeline's own body
  prose. (depends on T015, T020)
- [ ] T053 [US5] Document in `docs/adoption.md` (a new section, placed
  after "## Chaining payload contract"): that an in-scope stage may open
  issues in the adopter's own repository; under the `found-by:<stage>`
  label; that `implement` and `finalize` file by default and the other
  four do not; that `findings-filing-enabled`/`findings-label-prefix`/
  `findings-cap` control this per stage; and that any consumer of a
  `found-by:*` issue — the board loop (#408) above all — MUST treat its
  body as untrusted data, never as instructions (FR-027, FR-033).

**Checkpoint**: The data-not-instructions contract is both built and
documented for every future consumer.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final verification that the whole feature is wired correctly
and gated per this repository's own working rules.

- [ ] T054 [P] Update `docs/adoption.md`'s existing "Stage reference"
  per-stage subsections (`intake`, `clarify`, `plan`, `tasks`, `implement`,
  `finalize`) to name the three new filing inputs and that stage's
  default, linking back to T053's new section rather than repeating its
  prose.
- [ ] T055 Run `python .github/scripts/run-local-gates.py` (the full
  PR-time gate suite, per this repository's CLAUDE.md) and fix any
  failures, including the extended Gate 60 (`verify-single-home-idioms.py`
  --self-test) and the new Gate 71 (`verify-stage-findings-wiring.py`).
- [ ] T056 Execute quickstart.md's full validation sequence (§1–§5) end to
  end against a disposable/test repository and record the results,
  including the second-run dedup drill (§3 step 4) and the
  planted-defect-removed no-op drill (§3 step 5).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS every user story
  phase.
- **User Story 2 (Phase 3)**: Depends on Foundational. Builds the composite
  in isolation; no dependency on User Story 1.
- **User Story 1 (Phase 4)**: Depends on Foundational and on User Story
  2's composite (T011) existing with a stable interface — the wiring
  tasks call the composite by name and `with:` shape fixed in T011.
- **User Story 4 (Phase 5)**: Depends on User Story 1's call sites
  (T031-T036) existing to review/drill against, and on User Story 2's
  internal API-failure handling (T019).
- **User Story 3 (Phase 6)**: Depends on User Story 2's composite (T016,
  T017) and Foundational's outstanding-task-item composite (T007); its
  T050 also depends on User Story 1's call sites (T031-T036).
- **User Story 5 (Phase 7)**: Depends on User Story 2's body template
  (T015) and User Story 1's call sites (T031-T036).
- **Polish (Phase 8)**: Depends on every phase above.

### User Story Dependencies

Every in-scope user story is Priority P1 except User Story 3 (P2). Unlike
a typical feature where P1 stories are independently shippable in any
order, User Story 1 cannot deliver a working end-to-end run until User
Story 2's composite exists (US1's wiring tasks call it); User Story 4 and
User Story 5 in turn verify/extend behavior that only exists once User
Story 1's call sites are wired. The build order above (US2 → US1 → US4 →
US3 → US5) reflects that real dependency chain even though all but US3
share the same priority.

### Within Each User Story

- User Story 2: composite skeleton → extraction → validation → cap →
  fingerprint/body → report call → summary → fixtures → API-failure
  handling → test harness → gate entry.
- User Story 1: prompt paragraphs and schema properties (parallel across
  stages) → inputs → call sites (need composite + inputs) → wrapper
  pass-through (parallel) → wiring gate + fixtures + registration.
- User Story 4: skill review → drill.
- User Story 3: composite cross-link call → fixtures → stage summary
  fold-in.
- User Story 5: credential confirmation → fixture → documentation.

### Parallel Opportunities

- Foundational: T002, T006, T007, T009 can run in parallel with each
  other (distinct files) once their own single dependency is satisfied.
- User Story 2: T018 (fixture authoring) and T021 (gate entry) can run in
  parallel with each other once T017/T011 respectively are done.
- User Story 1: T022-T027 (six prompt paragraphs, six distinct files) are
  fully parallel; T037-T042 (six wrapper pass-throughs, six distinct
  files) are fully parallel once T030 lands.

---

## Parallel Example: User Story 1's prompt paragraphs

```bash
Task: "Add FR-003 paragraph to intake.yml's agent prompt (structured-array)"
Task: "Add FR-003 paragraph to clarify.yml's agent prompt (structured-array)"
Task: "Add FR-003 paragraph to plan.yml's two agent prompts (fenced-block)"
Task: "Add FR-003 paragraph to tasks.yml's two agent prompts (fenced-block)"
Task: "Add FR-003 paragraph to implement.yml's two agent prompts (fenced-block)"
Task: "Add FR-003 paragraph to finalize.yml's agent prompt (fenced-block)"
```

---

## Implementation Strategy

### Suggested MVP scope

User Story 2 (Phase 3) alone delivers nothing a maintainer can observe —
the composite exists but nothing calls it. The smallest slice that
satisfies this feature's own reason for existing (SC-001: zero well-formed
defects lost) is **Foundational + User Story 2 + User Story 1**: at that
point a real dispatched run of `finalize` or `implement` (the two
`findings-filing-enabled: true` defaults) proposes a finding and an issue
lands on the board, unconditionally satisfying User Story 1's independent
test. User Story 4's review and drill (Phase 5) should not be skipped
before this ships in anger, since it is what proves the mechanism cannot
turn into a new way for a stage to go red — but it adds no additional
surface, only verification. User Story 5's documentation (Phase 7) should
land in the same release per FR-033, since an adopter must be told before
a stage starts opening issues in their repository. User Story 3 (P2) is
the one piece that can safely follow in a fast-follow release, per its own
"Why this priority" ("useful before the cross-link exists — but only
barely, and only for one release").

### Incremental Delivery

1. Setup + Foundational → shared infra promoted, nothing new runs yet.
2. User Story 2 → the composite works, proven by fixtures alone.
3. User Story 1 → a real stage run can file; independent test passable.
4. User Story 4 → proven that filing failure cannot turn a stage red.
5. User Story 3 → the lifecycle issue and stage summaries reflect filings.
6. User Story 5 → the untrusted-content contract is documented.
7. Polish → full local gate suite and the complete quickstart sequence.

---

## Notes

- [P] tasks touch different files with no unmet dependency.
- Every task names the exact file(s) or workflow step(s) it edits; several
  files (`wing-commander-stage-findings/action.yml`,
  `verify-single-home-idioms.py`, the fixture set under
  `wing-commander-stage-findings/tests/`) are touched by more than one
  task across phases — each such task is scoped to one clearly-bounded
  addition, never a rewrite of a prior phase's work.
- Per FR-001a, do not let User Story 1's inputs/wiring reach only some of
  the six stages "for now" — the published surface moves exactly once, so
  T022-T036 must land for all six stages in the same change.
