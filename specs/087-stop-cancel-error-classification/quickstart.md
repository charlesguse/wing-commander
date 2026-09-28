# Quickstart: Classify the cancel call's own error instead of racing a pre-read status

**Feature**: `087-stop-cancel-error-classification` | **Issue**: #621

This feature has no runtime UI; validation is entirely through checked-in
fixtures run locally, the same way CI runs them.

## Prerequisites

- Python 3 with `pyyaml` available (already a dependency of the existing
  gate scripts).
- `bash`, `jq` on `PATH` (the composite-shell fixture harness shells out to
  both — see `verify-board-stop-check.py`'s own prerequisite check).
- A checkout with this feature's changes applied: the new
  `.github/actions/_shared/cancel-already-terminal.sh`, the modified
  `.github/actions/wing-commander-board-stop-check/action.yml`, the
  one-line change in `.github/workflows/pr-conversation.yml`, and the
  extended `verify-board-stop-check.py` / `verify-single-home-idioms.py`.

## Validate the shared vocabulary script directly

```bash
# Already-terminal (exit 0 expected)
bash .github/actions/_shared/cancel-already-terminal.sh "HTTP 409: Conflict"
echo "exit=$?"   # expect 0

bash .github/actions/_shared/cancel-already-terminal.sh "Cannot cancel a workflow run that has already completed."
echo "exit=$?"   # expect 0

# Not already-terminal (exit 1 expected)
bash .github/actions/_shared/cancel-already-terminal.sh "HTTP 403: Resource not accessible by integration"
echo "exit=$?"   # expect 1

bash .github/actions/_shared/cancel-already-terminal.sh "permission denied for run id 4091234"
echo "exit=$?"   # expect 1 (bare 409 digits, no HTTP prefix — SC-002's third case)
```

## Run the composite's own gate

```bash
python3 .github/scripts/verify-board-stop-check.py
```
Expected: every fixture in `.github/scripts/tests/board-stop-check/`
passes, every `MUTATIONS` entry (including the new already-terminal
inversion) is caught, and `composite_shell_check()`'s new cases (already-
terminal / non-terminal failure / empty-stderr failure / bare-409 failure /
newline-in-error-text) each assert the matrix in
`contracts/gate-coverage-087.md`.

## Run the single-home gate

```bash
python3 .github/scripts/verify-single-home-idioms.py
```
Expected: the new `cancel-already-terminal` check passes on the shipped
tree, and (per its own self-test convention) a synthetic third-site
re-implementation of the vocabulary is caught by the same check's mutation
test.

## Run the full pre-push gate suite (CLAUDE.md)

```bash
python .github/scripts/run-local-gates.py
```
Expected: all gates green, including the two above — this is SC-005.

## Manual end-to-end sanity check (optional, not a substitute for the gates)

1. Dispatch `board-loop.yml` (or exercise `wing-commander-board-stop-check`
   in isolation via the composite's own inputs) against a board item whose
   stop-request marker names a run that has already completed.
2. Confirm the run's log/annotations show no `::warning::` for the cancel
   attempt, one plain informational line naming the target run, and the job
   still reports `paused=true` and exits successfully.
3. Repeat naming a run that genuinely fails to cancel (e.g. revoke the
   cancel-token's `actions: write` temporarily in a disposable test
   repository) and confirm a `::warning::` appears, naming the run and the
   error text, with no newlines or `::`-shaped text breaking the
   annotation.

This mirrors User Story 1 and User Story 2's acceptance scenarios in
`spec.md` and is the same kind of after-merge evidence CLAUDE.md's "Working
the issue board" section asks for on a fix to Actions-only behaviour: a
re-driven run with the outcome recorded on the PR or issue.
