# Contract: Gate 34 (new) and Gate 35 (new)

Gate numbers are provisional — confirm against
`.github/workflows/lint-workflows.yml`'s actual highest `Gate N —` in use
at implementation time (research.md D13; highest at plan time is Gate 33,
`lint-workflows.yml:2836`). Renumber both gates together if either slot is
taken by an intervening merge; do not renumber only one.

## Gate 34 — a review folds every leg once and dispatches once; a dead leg says so

**File**: `.github/scripts/verify-fold-dispatch-once.py`, exercising
`pr-conversation.yml`'s `dispatch-once` and `report-fold-outcomes` jobs
(contracts/fold-dispatch-once.md).

**Wiring**: picked up automatically by `wc_gate_registry.py`'s filename
convention (`verify-*.py` under `.github/scripts/`, invoked by a `run:` in
a new `lint-workflows.yml` step) — Gate 10 (existing, unmodified) asserts
this wiring is complete in both directions.

**Mechanism**: `wc_shell_harness.py`'s `find_job`/`find_step`/`run_step`
against the shipped `run:` text of `dispatch-once`'s and
`report-fold-outcomes`'s steps, supplying upstream values
(`base-sha`, `classifications`, a synthetic `gh api .../jobs` response, a
synthetic git history) as env vars / stubbed `gh`/`git` executables on
`PATH`, following Gate 14/Gate 30's established shape — real git commands
against a small real repo where the harness needs commit/log evidence
(D6's `fold(<id>):` grep), stubbed `gh` where only the shape of the API
response matters (the jobs list).

**Required scenarios (FR-018)**:
1. Three in-scope legs, all fold cleanly → `dispatch-once` computes exactly
   one `gh workflow run` invocation; `report-fold-outcomes` posts nothing.
2. A review arriving mid-cycle (modelled as `act`'s `environment:` wait) →
   no fold, no dispatch, until the harness's modelled cycle "finishes."
3. A leg cancelled before folding (job `conclusion=cancelled`, no
   `fold(<id>):` evidence) → `report-fold-outcomes` posts a comment naming
   it "not folded."
4. A leg whose fold commit landed but whose job `conclusion` is not
   `success` → reported "partly folded," distinct wording from scenario 3.
5. A held leg whose `confirm-timeout-minutes` bound expires → the other,
   ready legs' folds are still dispatched; the held item is reported per
   FR-005a, not silently dropped.
6. A review with zero in-scope items (all question/no-action) → zero
   dispatches, zero failure reports.
7. Every leg healthy → `report-fold-outcomes` posts nothing (US2 AS5).

**Required mutations (FR-019)**:
- Revert D1 (restore a per-leg dispatch call) — scenario 1 must then show
  more than one dispatch.
- Revert D6's dual-signal check to job-conclusion-only — scenario 4 must
  then misclassify as healthy (proving the fold-evidence cross-check is
  load-bearing).
- Revert D6's dual-signal check to fold-evidence-only — scenario 3 must
  then misclassify as healthy if a spurious fold-evidence line is present
  (proving the job-conclusion cross-check is load-bearing).
- Remove `report-fold-outcomes`'s `if: always()` (replace with the job's
  implicit default) — scenario 3 must then produce no report at all when
  `act` itself fails.

A fifth, reflexive check (Gate 34 itself present and wired, per Gate 25's
own pattern) satisfies FR-020 for this gate.

## Gate 35 — finalize refreshes an open final PR, and only an open one

**File**: `.github/scripts/verify-finalize-refresh.py`, exercising
`finalize.yml`'s tri-state guard and refresh path
(contracts/finalize-refresh.md).

**Wiring**: same filename-convention pickup as Gate 34; Gate 10 asserts it.

**Mechanism**: follows `verify-stall-restart-runbook.py`'s (Gate 14) real-
git-repo-plus-local-bare-remote shape — needed because the fold-log
append (D9a) and the PR-body preserve/regenerate split (D9) have real
commit/push and real existing-body-read/write side effects a transcript-
only harness cannot honestly exercise. `gh` calls are captured via a
stub executable on `PATH` recording each invocation's arguments (matching
Gate 14/Gate 30's established stub shape); git itself is real.

**Required scenarios (FR-018)**:
1. Existing **open** PR, one prior fold-log entry, a new fold since →
   asserts: metadata committed to `stage: review`, `stage:review` label
   present and any `stage:implement` label removed, re-review requested
   from `spec-meta.json`'s `pending_re_review_from`, PR body's state block
   regenerated, prose outside the delimiters preserved verbatim, one new
   fold-log entry appended, the prior entry unchanged.
2. Existing **merged** PR → asserts: no PR edit, no metadata commit, no
   label change, no re-review request, a lifecycle-issue comment naming
   "merged."
3. Existing **closed, not merged** PR → same assertions as scenario 2, with
   the comment naming "closed" (FR-009a's distinct wording).
4. A re-review request that fails (stubbed `gh pr edit --add-reviewer`
   returns non-zero) → asserts the remaining refresh effects (metadata,
   labels, body) still occur, and the failure is stated on the lifecycle
   issue (FR-010b), and the job does not fail.
5. Repeat refresh, no intervening fold (tip SHA unchanged from the fold log's
   most recent entry) → asserts no new fold-log entry, no duplicate
   re-review request, no duplicate lifecycle-issue comment (FR-010a).
6. No existing PR (`pr-state == 'none'`) → asserts exactly today's create
   path runs, byte-for-byte unchanged from before this feature (FR-017),
   and the machine-owned region is written fresh with an empty fold log.

**Required mutations (FR-019)**:
- Revert D7 (restore the boolean `skip` guard) — scenario 1 must then show
  no refresh occurring (regression to "skip on any existing PR").
- Revert D9's preserve-outside-delimiters logic to full-body overwrite —
  scenario 1's prose-preservation assertion must then fail.
- Revert D9a's idempotency check (always append) — scenario 5 must then
  show a duplicate fold-log entry.
- Remove the `pr-state == 'merged' || pr-state == 'closed'` guard on the
  refresh-only steps — scenario 2 or 3 must then show a metadata commit
  or label change occurring against a merged/closed PR.

A fifth, reflexive check (Gate 35 itself present and wired) satisfies
FR-020 for this gate.

## FR-021 — job-suppression gate (Gate 15)

No change to Gate 15 is required. `pr-conversation.yml`'s two new jobs use
`if: always()` at the job-`needs:` level, a status-check function Gate 15
already recognizes as safe. `finalize.yml`'s new conditions
(`steps.guard.outputs.pr-state == '...'`) are step-level, within a single
job, and never appear in a `needs.<job>.outputs`/`.result` comparison —
Gate 15's `needs:`-graph walk does not examine step-level `if:` at all, so
these conditions are outside its domain and require no widening.
