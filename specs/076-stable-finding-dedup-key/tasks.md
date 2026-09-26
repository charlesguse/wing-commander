# Tasks: A Stage-Finding Dedup Key That Does Not Drift With Agent Wording

**Input**: Design documents from `/specs/076-stable-finding-dedup-key/`
**Prerequisites**: plan.md, research.md, data-model.md, contracts/anchor-verification.md, contracts/gates.md, quickstart.md

**Tests**: This feature's "tests" are the checked-in fixture harness
(`.github/scripts/stage-findings-tests/run_fixtures.py`, run via Gate 71 —
`bash .github/scripts/stage-findings-tests/run-tests.sh`) and gate self-tests
— there is no separate test framework. Fixture tasks below are listed inside
each user story because FR-010/FR-011 require them as the story's own proof,
not as a pre-implementation TDD step.

**Organization**: Tasks are grouped by user story per spec.md's priorities
(US1 P1, US2 P1, US3 P2, US4 P3). All four stories exercise one shared
mechanism (the anchor check and two key shapes), built once in the
Foundational phase — spec.md's own Clarifications section states the same
thing: "one defect can hold at most two board items," which is a single
piece of logic, not four separable behaviors.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an
  incomplete task)
- **[Story]**: US1/US2/US3/US4, per spec.md
- Every task names its exact file path(s)

## Path Conventions

Single project — this repository's own CI/CD pipeline. No `src/`/`tests/`
split; "source" is `.github/actions/`, `.github/scripts/`, `.github/workflows/`,
and the `specs/056-stage-found-defect-filing/` document this feature amends
in place (plan.md's Project Structure).

---

## Phase 1: Setup

- [ ] T001 Verify baseline facts against the current tree before assigning
  any new identifier (this repository's own T001 convention — see
  `verify-single-home-idioms.py`'s module docstring on why a claim about the
  tree is not the same as the tree). Confirm, and note any drift found: (a)
  the highest gate number already registered in
  `.github/workflows/lint-workflows.yml` (Gate 98 as of this writing — the
  new gate in T024 takes the next free number, not necessarily 99, if
  another spec landed one first); (b) the FR-003 paragraph's occurrence
  count per stage workflow via
  `grep -rc "do not attempt to file it yourself" .github/workflows/*.yml`
  (expected: `intake.yml`, `clarify.yml`, `finalize.yml` — 1 each;
  `plan.yml`, `tasks.yml`, `implement.yml` — 2 each; 9 total); (c) that
  `.github/actions/wing-commander-stage-findings/action.yml`'s "Extract,
  validate, cap, and prepare findings" step still computes the single-shape
  `fingerprint = sha256("<stage>|<norm(file_path)>|<norm(gate_or_artifact)>")`
  immediately before writing each survivor's `-marker` output, matching
  `specs/056-stage-found-defect-filing/data-model.md`'s "Fingerprint"
  section — this is the exact code and doc this feature's Foundational phase
  replaces.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The anchor check and the two key shapes it produces (FR-001
through FR-008) — every user story's independent test assumes this
mechanism already exists and only adds fixtures or gates on top of it.

**⚠️ CRITICAL**: No user story task can be verified until this phase is done.

- [ ] T002 In `.github/actions/wing-commander-stage-findings/action.yml`'s
  "Extract, validate, cap, and prepare findings" step (the inline Python
  block), add the anchor-verification logic from
  `contracts/anchor-verification.md` steps 1-4: resolve
  `fingerprint_basis.file_path` relative to the step's own working
  directory (the same tree `evidence.file_paths` is implicitly read
  against, research.md D3); if the resolved path does not exist, is not a
  regular file, or cannot be read, the anchor is unverifiable; otherwise
  compute `norm(gate_or_artifact)` by reusing the existing
  `normalize_basis()` helper already defined in this step (do not add a
  second copy of the normalization regex); if that normalized value is
  empty, the anchor is unverifiable (research.md D1 — an all-punctuation
  anchor is not a usable key component); otherwise compute
  `norm(file_text)` from the file's full content and test
  `norm(gate_or_artifact) in norm(file_text)` — contained means the anchor
  verifies, not contained means unverifiable. Position-independence: the
  test only needs containment, never the offset (Edge Cases).
- [ ] T003 In the same step, depends on T002: replace the single
  three-segment fingerprint with the two shapes from research.md D2 —
  when the anchor verifies, `with-anchor key =
  sha256("anchor|<stage>|<norm(file_path)>|<norm(gate_or_artifact)>")`
  (using the already-normalized value from T002's step-4 computation, not
  the raw agent-supplied string); when it does not,
  `fallback key = sha256("fallback|<stage>|<norm(file_path)>")`. Both
  literal tags (`anchor|`, `fallback|`) must appear verbatim in the shipped
  code, since T021's gate later checks for them by string match.
- [ ] T004 In the same step, depends on T002/T003: when an anchor is
  unverifiable, append one line to the existing `notes` list (FR-006,
  research.md D4) naming the finding's title, the anchor value that failed,
  the file path it was checked against, and that the finding was keyed via
  the FR-007 fallback route rather than dropped. Do not add a new
  run-summary counter or field — `notes` is the only carrier, matching the
  existing `dropped (malformed): ...` / `dropped (cap exceeded): ...` line
  convention.
- [ ] T005 In the same file's `compose_recap()` function, implement FR-008:
  the text used as `comment-body-file` when a finding appends to an
  already-open issue must include that finding's own `title` and `what`,
  not only the current `"Seen again in run {0}.\n".format(RUN_URL)`. Every
  distinct defect that lands on a shared (fallback-keyed) issue must stay
  legible from the issue body alone.
- [ ] T006 Depends on T003: amend
  `specs/056-stage-found-defect-filing/data-model.md`'s "Fingerprint"
  section in place — replace the single-formula statement with both shapes
  from T003 (fenced, mechanically extractable: keep the block a `norm()`
  line plus the two tagged formula lines, immediately under the existing
  "## Fingerprint" heading, since T021's gate identifies the block that
  way), state the anchor-verification rule (a cross-reference to this
  feature's Key Anchor entity is enough — this file does not restate
  research.md/contracts/anchor-verification.md in full, per this
  document's own no-second-copy rule), and add FR-014's compatibility note
  (an issue filed under the pre-076 single-shape formula carries a marker
  that matches neither new shape; its next encounter files once under
  whichever shape that encounter now produces — no migration is performed).

**Checkpoint**: The composite now produces with-anchor and fallback keys,
records rejections, and appends carry full descriptions. Every story below
proves a slice of this behavior with fixtures or gates.

---

## Phase 3: User Story 1 - The same defect met twice reaches one issue (Priority: P1) 🎯 MVP

**Goal**: An agent that re-describes one anchored defect in different words
across runs still produces exactly one key.

**Independent Test** (spec.md): Two runs of one stage meeting one defect,
titles/what differing in wording, both anchoring on the same file text with
differing punctuation/case/spacing — exactly one key results.

- [ ] T007 [US1] In
  `.github/scripts/stage-findings-tests/run_fixtures.py`, add a fixture
  function (e.g. `case_anchor_wording_variance_shares_one_key`) proving
  FR-010's first case / SC-002's first clause: write one temp fixture file
  whose content contains a quotable line (e.g. a heading or gate name);
  prepare two findings with differing `title` and `what`, whose
  `fingerprint_basis.gate_or_artifact` values quote that same line with
  different punctuation, capitalisation, and spacing (both verified as
  contained via `norm()`), and the same `fingerprint_basis.file_path`;
  assert both survivors' `-marker` outputs are identical with-anchor keys.
- [ ] T008 [US1] In the same file, amend the existing
  `case_fingerprint_ignores_punctuation_case_and_spacing` per research.md
  D8: keep its first assertion (punctuation/case/spacing variants share one
  fingerprint), but replace its third finding and its "a different word
  gives a different fingerprint" assertion — which proved exactly the
  pre-076 behavior this feature removes — with a finding whose
  `gate_or_artifact` does not occur (even normalized) in the fixture file's
  content, and assert it now takes the FR-007 fallback key rather than a
  third distinct with-anchor key. Do not delete the case silently (SC-002
  requires both the same-key and different-key directions to stay proven);
  keep the amendment visible in the diff and its docstring/comment updated
  to say why.
- [ ] T009 [US1] Add T007's and T008's function(s) to the `CASES` list in
  `.github/scripts/stage-findings-tests/run_fixtures.py` so Gate 71
  (`bash .github/scripts/stage-findings-tests/run-tests.sh`) exercises them.

**Checkpoint**: Wording drift on a verified anchor no longer moves the key;
run Gate 71 to confirm.

---

## Phase 4: User Story 2 - The key is computed or checked, never taken on trust (Priority: P1)

**Goal**: Every key component is either derived by code or checked against
the tree; a check that fails is recorded, never silently trusted.

**Independent Test** (spec.md): Feed the filing step fixtures directly (no
agent, no `gh`): differently-worded findings sharing one anchor produce one
key; findings naming genuinely different anchors produce two; an
unverifiable anchor takes the stated fallback with the reason recorded.

- [ ] T010 [US2] In `run_fixtures.py`, add a fixture function (e.g.
  `case_two_verifiable_anchors_key_apart`) proving FR-010's second case:
  two findings in one fixture file naming two genuinely different,
  both-verifiable anchors (e.g. two distinct headings both present in the
  file) produce two distinct with-anchor keys.
- [ ] T011 [US2] Add a fixture function (e.g.
  `case_unverifiable_anchor_is_rejected_and_recorded`) proving FR-006: a
  finding whose `gate_or_artifact` does not occur in its named file is not
  filed under that value; assert the resulting state's `notes` list
  contains a line naming the finding's title, the anchor value, the file
  checked, and that it was keyed via the fallback route — and assert no new
  run-summary counter/field was added (the existing
  `filed`/`appended`/`dropped_*` set is unchanged, per research.md D4).
- [ ] T012 [US2] Add a fixture function (e.g.
  `case_key_is_rederivable_from_recorded_inputs`) proving FR-002 /
  Acceptance Scenario 2: run the "prepare" step twice, in two independent
  temp directories, with byte-identical finding input (including the same
  fixture file content); assert the two runs' `-marker` outputs are
  identical.
- [ ] T013 [US2] Add T010-T012's function(s) to the `CASES` list in
  `run_fixtures.py`.

**Checkpoint**: Rejections are logged with a reason and a route, and keys
reproduce deterministically from recorded inputs; run Gate 71 to confirm.

---

## Phase 5: User Story 3 - A defect with nothing quotable still reaches the board (Priority: P2)

**Goal**: A finding with no verifiable anchor still reaches the board under
the FR-007 fallback, never silently dropped, and stays individually
legible when it shares an issue with another unanchorable defect.

**Independent Test** (spec.md): A finding about a nonexistent file, and one
about an existing file with nothing quotable, each still reach the board
(filed or appended, never dropped), each readable in full.

- [ ] T014 [US3] In `run_fixtures.py`, add a fixture function (e.g.
  `case_anchor_absent_from_existing_file_takes_fallback`) proving the
  contracts/anchor-verification.md fixture table's third row: a finding
  whose `fingerprint_basis.file_path` names a fixture file that exists but
  whose content does not contain (even normalized) the finding's
  `gate_or_artifact` takes the FR-007 fallback key.
- [ ] T015 [US3] Add a fixture function (e.g.
  `case_two_unanchorable_findings_share_fallback_key`) proving FR-011: two
  such absent-anchor findings in the same fixture file produce the same
  fallback key.
- [ ] T016 [US3] Add a fixture function (e.g.
  `case_fallback_and_with_anchor_keys_do_not_collide`) proving FR-011's
  "does not collide" clause and the Edge Cases entry on the
  anchored/unanchored split: one fallback-keyed finding and one
  with-anchor-keyed finding in the same fixture file produce distinct
  keys.
- [ ] T017 [US3] Add a fixture function (e.g.
  `case_anchor_normalizing_to_empty_takes_fallback`) proving the Edge
  Cases entry / research.md D1: a `gate_or_artifact` made only of
  punctuation/whitespace (normalizes to the empty string) takes the
  fallback key, and the with-anchor key's third segment is never an empty
  string.
- [ ] T018 [US3] Add a fixture function (e.g.
  `case_missing_named_file_takes_fallback`) proving
  contracts/anchor-verification.md's last fixture-table row and User Story
  3's own independent test: `fingerprint_basis.file_path` naming a path
  that does not exist anywhere under the working directory takes the
  fallback key rather than failing the step.
- [ ] T019 [US3] Add a fixture function (e.g.
  `case_fallback_issue_append_carries_each_findings_own_text`) exercising
  T005's `compose_recap()` change in the context FR-007/FR-008 name: for
  an unanchorable finding, assert the recap file the "prepare" step writes
  contains that finding's own `title` and `what` verbatim (not only "Seen
  again in run ..."), so that when two distinct unanchorable defects later
  share one fallback-keyed issue (already proven generically able to
  dedup by `case_dedup_hit_open_comments_not_duplicates`), each remains
  individually legible from the issue body per SC-005.
- [ ] T020 [US3] Add T014-T019's function(s) to the `CASES` list in
  `run_fixtures.py`.

**Checkpoint**: Unanchorable findings never vanish, and a shared fallback
issue stays readable defect-by-defect; run Gate 71 to confirm.

---

## Phase 6: User Story 4 - The change is provable without a five-run drill (Priority: P3)

**Goal**: A gate fails at PR time if the shipped key rule diverges from its
one canonical statement, or if this feature's key composition silently
converges with (or further diverges from) spec 057's own, and the agent
prompt sentence describing the rule matches it everywhere it is repeated.

**Independent Test** (spec.md): Run the local gate suite on a tree where the
key rule changed in code but not in the data model, or not in the prompt
sentence, and confirm a gate fails.

- [ ] T021 [US4] Create `.github/scripts/verify-dedup-key-canonical-rule.py`
  implementing `check_canonical_rule_sync` (FR-012, contracts/gates.md):
  import `find_step` from `.github/scripts/wc_shell_harness.py` (the same
  helper `.github/scripts/stage-findings-tests/run_fixtures.py` already
  uses — do not re-derive a second YAML-extraction routine) to read the
  shipped "Extract, validate, cap, and prepare findings" step out of
  `.github/actions/wing-commander-stage-findings/action.yml`; read
  `specs/056-stage-found-defect-filing/data-model.md`'s "Fingerprint"
  section and extract the fenced formula block T006 wrote (the block
  immediately under that heading); assert every literal the doc's formula
  names — the `norm()` regex, the `anchor|` and `fallback|` tags, and each
  shape's pipe-delimited segment order — appears verbatim in the extracted
  step text. Fail loudly, naming which literal is missing and from which
  side, on any divergence; fail loudly (never "0 checked, pass") if either
  source file is missing or the fenced block cannot be found.
- [ ] T022 [US4] In the same script, add `check_composition_split` (FR-015,
  contracts/gates.md): extract this feature's own formula as in T021, and
  spec 057's `sha256("<issue>|<norm(title)>|<norm(file_path)>")` formula
  from `.github/workflows/board-loop.yml`'s "Prepare out-of-scope findings
  for filing" step (same `find_step` technique). Fail if the two extracted
  formula strings are textually identical (guards silent convergence), or
  if either formula is missing its own distinguishing ingredient — this
  feature's `anchor|`/`fallback|` tag, or spec 057's issue-number segment
  (guards further, undocumented divergence). The failure message must name
  FR-015 as the reason the two are required to keep differing.
- [ ] T023 [US4] Add `--self-test` fixtures to
  `verify-dedup-key-canonical-rule.py`, per contracts/gates.md: a scratch
  copy of the action file with one shape tag changed (asserted to fail,
  naming that tag); a scratch copy of the data-model.md fenced block with
  the `norm()` line altered (asserted to fail); a scratch `board-loop.yml`
  step whose formula is edited to match this feature's byte-for-byte
  (asserted to fail as "converged"); a scratch step missing the
  issue-number segment (asserted to fail as "diverged"); the real files,
  post-implementation, asserted to pass (mirrors `verify-single-home-idioms.py`'s
  self-test shape).
- [ ] T024 [US4] Register the new gate in
  `.github/workflows/lint-workflows.yml`, next to the existing spec-056
  Gate 71/72 entries: pick the next free gate number in the real tree (see
  T001; do not hardcode 99 if another spec has since taken it, per this
  repository's own renumbering convention documented in
  `verify-single-home-idioms.py`'s module docstring), and add both
  `run: python3 .github/scripts/verify-dedup-key-canonical-rule.py` and its
  `--self-test` companion step, each guarded by `if: "!cancelled()"`
  matching every neighboring gate's shape. No change to
  `.github/scripts/run-local-gates.py` is needed — its gate list is derived
  automatically from this file.
- [ ] T025 [US4] Extend
  `.github/scripts/verify-stage-findings-wiring.py` (FR-013,
  contracts/gates.md): add a second stable substring alongside the existing
  `PARAGRAPH_SUBSTRING` check — the clause stating that
  `gate_or_artifact` must occur verbatim in the file the finding names, and
  that a value which does not still reaches the board under a fallback
  route rather than being dropped — checked in the same six stage prompts,
  using the same `with.prompt`-scoped scan `has_paragraph_in_prompt`
  already uses (never a whole-file substring scan, per that gate's own
  docstring rationale). Add a mirrored self-test pair (a prompt carrying
  the FR-003 paragraph but not this new clause fails, naming the stage),
  alongside the existing `selftest_paragraph_without_step_fails`-style
  fixtures.
- [ ] T026 [US4] In `.github/workflows/clarify.yml`, beside its existing
  FR-003 findings paragraph (the "do not attempt to file it yourself..."
  block), add the FR-013 sentence describing the settled anchor rule (the
  value must occur verbatim in the named file; a value that does not still
  reaches the board via the fallback route, never silently dropped) and,
  per this repository's Gate 47 canonical-comment discipline, the marker
  comment `(canonical copy; do not condense)` citing issue #569, stating
  the rule this sentence encodes.
- [ ] T027 [P] [US4] In `.github/workflows/intake.yml`, beside its one
  FR-003 paragraph occurrence, add the same FR-013 sentence T026 added to
  clarify.yml and a `-- see clarify.yml` pointer comment (Gate 47).
- [ ] T028 [P] [US4] In `.github/workflows/finalize.yml`, beside its one
  FR-003 paragraph occurrence, add the same FR-013 sentence and a
  `-- see clarify.yml` pointer comment.
- [ ] T029 [P] [US4] In `.github/workflows/plan.yml`, beside each of its two
  FR-003 paragraph occurrences, add the same FR-013 sentence and a
  `-- see clarify.yml` pointer comment.
- [ ] T030 [P] [US4] In `.github/workflows/tasks.yml`, beside each of its
  two FR-003 paragraph occurrences, add the same FR-013 sentence and a
  `-- see clarify.yml` pointer comment.
- [ ] T031 [P] [US4] In `.github/workflows/implement.yml`, beside each of
  its two FR-003 paragraph occurrences, add the same FR-013 sentence and a
  `-- see clarify.yml` pointer comment.

**Checkpoint**: `python .github/scripts/run-local-gates.py` fails on a
deliberately reintroduced drift (data model vs. code, or the two key
compositions converging) and passes clean otherwise; the six prompts and
Gate 47 agree.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T032 Run `python .github/scripts/run-local-gates.py` and
  `bash .github/scripts/stage-findings-tests/run-tests.sh` directly against
  the full implementation (quickstart.md steps 1-2); confirm every gate,
  including the new one from T021-T024 and the extended one from T025,
  passes clean.
- [ ] T033 Follow quickstart.md step 2's mutation drill: temporarily change
  one shape tag in `action.yml` without updating data-model.md and confirm
  `verify-dedup-key-canonical-rule.py` fails naming the missing literal;
  separately, temporarily make `board-loop.yml`'s formula byte-identical to
  this feature's and confirm the same script fails naming FR-015; revert
  both mutations afterward.

---

## Dependencies & Execution Order

- **Setup (T001)**: No dependencies.
- **Foundational (T002-T006)**: Depends on T001. T002 → T003 → T004; T005 is
  independent of T003/T004 but lives in the same file/step; T006 depends on
  T003 (needs the settled formula strings). **Blocks all user stories.**
- **User Story 1 (T007-T009)**: Depends on Foundational. T007 and T008 are
  independent additions to the same file; T009 depends on both.
- **User Story 2 (T010-T013)**: Depends on Foundational. Independent of US1
  (different fixture functions); T010-T012 independent of each other, T013
  depends on all three.
- **User Story 3 (T014-T020)**: Depends on Foundational and on T005
  specifically (T019 exercises `compose_recap()`). Independent of US1/US2;
  T014-T019 independent of each other, T020 depends on all six.
- **User Story 4 (T021-T031)**: T021-T024 depend on Foundational (T003 for
  the formula literals, T006 for the doc's fenced block) but not on
  US1-US3's fixtures. T025 depends on Foundational (needs the sentence text
  decided in T026). T026 must land before T027-T031 (they point at it).
  T027-T031 are mutually parallel (five different files).
- **Polish (T032-T033)**: Depends on every prior phase.

### Parallel Opportunities

- T027, T028, T029, T030, T031 (five different workflow files) once T026 has
  landed.
- Across stories: once Foundational is done, US1/US2/US3's fixture-writing
  tasks touch the same file (`run_fixtures.py`) and are best done by one
  contributor in sequence to avoid merge conflicts, even though they are
  logically independent of each other.

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Setup (T001) and Foundational (T002-T006) — this alone
   implements FR-001 through FR-008.
2. Complete User Story 1 (T007-T009) and run Gate 71 to confirm wording
   drift no longer moves the key for an anchored finding.
3. **STOP and VALIDATE**: the five-run drill from #424, replayed by hand
   once, should now converge on one issue.

### Incremental Delivery

1. Setup + Foundational → the mechanism exists.
2. User Story 1 → the headline promise (FR-011 of spec 056) is fixture-proven.
3. User Story 2 → determinism and rejection-logging are fixture-proven.
4. User Story 3 → the fallback route is fixture-proven; nothing is silently
   dropped.
5. User Story 4 → the whole thing is gated, so the next drift fails CI
   instead of needing another five-run drill.
