# Quickstart: validating Bounded, Idempotent spec-request Filing

This feature has no user-facing surface to click through — it changes
`.github/workflows/board-loop.yml`'s internal filing logic and three
`.github/scripts/board_*.py` modules. Validation is: unit-level fixture
tests for the new/extended modules, the repository's own gate suite, and
one end-to-end drive of the board loop against a disposable test issue.

## Prerequisites

- A checkout with implementation complete (`board_spec_request_filing.py`
  added; `board_item_marker.py`, `board_spec_request_body.py`,
  `board-loop.yml`, and `verify-issue-context-single-home.py` updated per
  `contracts/`).
- `gh` authenticated against a repository where you can open issues and
  where the `spec-request` label exists (or, for User Story 2's negative
  path, does not).

## 1. Unit-level validation (no GitHub calls)

Run the new/extended modules' own fixture tests, alongside the existing
board-loop suite:

```
python .github/scripts/run-local-gates.py
```

This is the same command CLAUDE.md's "Before pushing" section already
requires and is derived from `lint-workflows.yml` itself, so a pass here
is a pass in CI. Confirm specifically:

- `verify-board-eligibility.py`-style fixtures under
  `.github/scripts/tests/board-spec-request-filing/` cover:
  `find_existing()` matching an open and a closed prior spec-request
  (FR-003), ignoring one authored by a non-bot account (Edge Case:
  "maintainer filed by hand"), picking the oldest of two matches (FR-004),
  and respecting the reopen-scoped `since` (FR-003's reopen exception).
  `record_attempt()` covers below-cap (`stall: false`) and at-cap
  (`stall: true`) at the boundary (`attempts == budget`).
- Gate 93's new check 6 fixtures (`contracts/gate-spec-request-single-
  home.md`) fail for each of: no lookup step, a hand-rolled increment, and
  a second budget constant name.

## 2. Idempotency — Independent Test for User Story 1

Acceptance Scenario 1 (spec.md): drive the loop on an issue for which a
`spec-request` already exists carrying the originating-issue footer.

1. Open a throwaway issue in the test repository; label it so the board
   loop's entry gate admits it (Constitution V).
2. By hand (simulating an interrupted prior run), open a second issue
   labeled `spec-request` whose body ends with
   `\n\n---\nOriginating issue: <server>/<repo>/issues/<N>` and is authored
   by the loop's own bot account (or, for a true end-to-end run, let a
   first pass file it deliberately).
3. Dispatch the board loop against the original issue
   (`gh workflow run board-loop.yml -f directed-issue=<N> ...` per the
   directed-run mechanism `contracts/board-loop-workflow.md` already
   documents) so it reaches a spec verdict.
4. Confirm: no new `spec-request` issue is created; the cross-link comment
   and the closing comment on issue N both name the *existing* issue's
   URL; the run's record states "reused", not "filed" (FR-006).

Repeat with the interruption at each post-create write (label, comment) to
exercise SC-003's "every post-create write position" — confirm the second
run always completes the unfinished writes against the *same* spec-request
rather than filing a second one.

## 3. Bounded retries — Independent Test for User Story 2

1. In a disposable test repository (or a branch of the board loop pointed
   at one), remove the `spec-request` label so every create deterministically
   fails the #514 URL-shape guard.
2. Seed the board with the target issue and one other, unrelated eligible
   issue.
3. Run the board loop three times (or however many scheduled ticks it
   takes to reach the cap). Confirm:
   - Attempts 1 and 2: the run fails loudly (red), no comment, no label,
     no cross-link (SC-007) — checked directly on the issue's comment list
     via `gh issue view <N> --json comments,labels`.
   - Attempt 3: `board:stalled` is added, a give-up comment appears
     stating no spec-request was filed, the attempt count, and the last
     failure, and the run reports green (SC-001: at most 3 attempts, 6
     agent invocations for triage+route across the runs that reached it).
4. On the next run, confirm the *other* eligible issue is selected and
   worked (SC-002) — the capped issue is not the in-flight candidate.

## 4. Recoverability — Independent Test for User Story 3

1. Restore the `spec-request` label (clearing the cause of the failure).
2. Remove `board:stalled` from the capped issue.
3. Confirm the next run selects it, `spec_request_attempts` starts fresh
   (a subsequent failure is again "attempt 1", not "attempt 4" — SC-006),
   and a successful filing this time produces exactly one `spec-request`.

## 5. Cross-site consistency

Repeat step 2 or 3 with the failure/duplicate condition triggered instead
at the fix job's post-push breach and at readiness's *ordinary* backstop
breach (the entry spec 100 explicitly defers to this feature) — confirm
identical behavior at all three sites, satisfying FR-017/SC-005.
