# Contract: FR-007, FR-008, FR-009a, SC-001–SC-003, SC-007, SC-008 — gate coverage

`research.md` D7/D8 give the design; this contract pins down which gate
proves which requirement.

## `verify-board-stop-check.py` (MODIFIED — the composite's own gate)

Already the single home for `wing-commander-board-stop-check`'s cancel-guard
coverage (its own docstring). Extended, not replaced:

- `STUB_GH` gains the ability to make `gh run cancel` fail with a
  configurable stderr string per test case (today it always exits 0).
- New/extended cases (table below) drive `run_shell_cases()`/`_run_shell_case()`
  and assert, per case: exit status, `paused` output, whether a
  `::warning::`-shaped line appears, whether the informational line
  appears, and — for the already-terminal case — that no `::warning::`
  appears at all (the negative assertion SC-001 requires).
- A new mutation (alongside the existing "cancel guard disabled" mutation in
  `composite_shell_check()`) inverts the already-terminal classification —
  e.g. swapping `cancel-already-terminal.sh`'s exit code, or the `if`/`else`
  branch bodies — and must be caught by at least one of the new cases
  (FR-008, SC-003).

| Case | `gh run cancel` | Expected `::warning::`? | Expected informational line? | Expected `paused` |
|---|---|---|---|---|
| Successful cancellation (existing) | exit 0 | no | no | `true` |
| Already-terminal refusal | exit 1, stderr `HTTP 409: Conflict` | no | yes | `true` |
| Non-terminal (permission) failure | exit 1, stderr `HTTP 403: Resource not accessible` | yes, names run + error text | no | `true` |
| Empty-stderr failure | exit 1, stderr `` | yes (FR-004's "empty or unrecognised" clause) | no | `true` |
| Bare-409-without-prefix failure | exit 1, stderr `permission denied for run id 4091234` | yes — must NOT be classified already-terminal (SC-002 third case) | no | `true` |
| Newline/workflow-command-shaped error text | exit 1, stderr containing `\n` and a `::warning::`-shaped substring | exactly one `::warning::` annotation, no forged second annotation (SC-008) | no | `true` |

The existing `EXPECTED_FILES` fixture set (`maintainer-stop.json` through
`forged-run-line-in-own-comment.json`) and the existing `SHELL_CASES`
(ownership/unreadable/completed/forged-marker/no-stop) are unchanged inputs
and must keep passing unmodified — SC-004.

## `verify-single-home-idioms.py` (MODIFIED — FR-009a)

See `contracts/cancel-already-terminal-script.md`'s "Gate coverage" section
for the full description. Summary: new `DECLARED_HOMES["cancel-already-terminal"]`
entry, new structural check registered in `CHECK_NAMES` alongside
`"board-stop-check"`, a mutation/fixture proving a third-site
re-implementation of the vocabulary is caught (SC-007).

## `lint-workflows.yml` / `run-local-gates.py`

No new gate ID. Both modified gates (`verify-board-stop-check.py`,
`verify-single-home-idioms.py`) are already registered call sites; this
feature changes their bodies, not the registry. `python
.github/scripts/run-local-gates.py` (CLAUDE.md's own pre-push instruction)
covers both without a lint-workflows.yml edit.

## Requirement → proof map

| Requirement | Proven by |
|---|---|
| FR-001, FR-002, SC-006 | `board-stop-check-classification.md`'s diff description + a fixture asserting `gh run cancel` runs regardless of a `completed` stub status (the existing "a completed run is not cancelled" case is about the *ownership* guard, not status — no case today asserts status alone would have blocked a cancel; the new already-terminal case exercises the post-attempt path instead) |
| FR-003, FR-004, SC-001, SC-002 | New `verify-board-stop-check.py` cases table above |
| FR-005 | `cancel-already-terminal-script.md`'s matching rule + the bare-409 case |
| FR-007 | The full new-cases table, all outcome branches |
| FR-008, SC-003 | New mutation in `verify-board-stop-check.py` |
| FR-009, FR-009a, SC-007 | `verify-single-home-idioms.py` extension |
| FR-010 | Informational-line assertion (no `::...::` prefix) in the already-terminal case |
| FR-011, SC-008 | Newline/workflow-command case |
| SC-004 | Existing fixtures/cases unchanged and re-run |
| SC-005 | `python .github/scripts/run-local-gates.py` (CLAUDE.md pre-push gate) |
