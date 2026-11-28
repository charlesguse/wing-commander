# Quickstart: validating the post-agent verdict

Prerequisites: the change merged or on a branch, `python .github/scripts/run-local-gates.py`
green, a test lifecycle issue with an implement run available.

## Local (deterministic)

1. Run the extended gates by name, e.g.
   `python3 .github/scripts/verify-gate-suite-credential-free.py --self-test`
   and the new `verify-implement-post-verdict.py --self-test`. Expect: the
   post job holds no write credential; the dispatch step exists once.
2. Run `python .github/scripts/run-local-gates.py` (outside an agent call).
   Expect all gates pass.

## In Actions (prove-after-merge)

1. Red case: on a test spec branch with all tasks checked and one failing
   gate, dispatch implement. Expect `gate-suite-implement-post` red,
   `implement-dispatch` records not converged, the lifecycle comment names
   the post-agent suite and the failing gate, and implement iteration N+1 is
   dispatched, not finalize (SC-002).
2. Green case: same branch with the gate fixed. Expect converged=true and
   finalize dispatched.
3. Unchecked tasks: expect `gate-suite-implement-post` skipped (SC-005).
4. Missing prerequisite: run with the pipeline checkout unavailable; expect
   not converged naming the missing prerequisite (SC-006).
5. Stall hand-off: expect the verdict marker comment before finalize runs and
   the verdict in the final PR body; a red verdict does not stop the hand-off
   (SC-007).
6. Read an agent transcript: no full-suite invocation (SC-003).

Contract details: [contracts/post-agent-verdict.md](contracts/post-agent-verdict.md);
data: [data-model.md](data-model.md).
