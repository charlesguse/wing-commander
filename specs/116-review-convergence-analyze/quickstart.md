# Quickstart: validating 116

Prerequisites: checkout with full history (`fetch-depth: 0`), Python 3.11+.

1. **Shared arithmetic parity (SC-003)**
   `python .claude/skills/review-until-clean/scripts/thrash_signals.py --self-test` and `python .github/scripts/wc_convergence.py decide --history <fixture> --json` over the same fixture give identical signals.
2. **Recurrence (SC-001)**: replay the #833 fixture through the partition; expect round not clean, no `success`, recurrence named.
3. **Stop rules (SC-002)**: replay #954 and #969 histories; expect `not-converging` at or before round 3; a round-2 fixture records signals without stopping; a round-4 healthy fixture continues; round 5 trip reports the budget as the reason.
4. **Analyze check (SC-004/005)**: run the composite fixtures — a constitution-conflicting fold task → `hold` with the question naming task and principle; an FR-contradicting task → `dispatch` with report; a malformed agent output → `hold` (`analyze-failed`).
5. **Gates (SC-007)**: `python .github/scripts/run-local-gates.py` — the two new gates pass on the tree and each failure fixture makes its gate fail.
6. **After merge**: re-drive one lifecycle review round and one fold via `gh workflow run` on the wrapper (`prove-after-merge`), confirming the run took the analyze step and recorded signals.

Contracts: [convergence-signals](contracts/convergence-signals.md), [fold-analyze](contracts/fold-analyze.md). Entities: [data-model](data-model.md).
