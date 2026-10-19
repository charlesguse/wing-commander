# Quickstart: validating 116

Prerequisites: checkout with full history (`fetch-depth: 0`), Python 3.11+.

1. **Shared arithmetic parity (SC-003)**
   `python .claude/skills/review-until-clean/scripts/thrash_signals.py --self-test` and `python .github/scripts/wc_convergence.py decide --history <fixture> --json` over the same fixture give identical signals.
2. **Recurrence (SC-001)**: replay the #833 fixture through the partition; expect round not clean, no `success`, recurrence named.
3. **Stop rules (SC-002)**: replay #954 and #969 histories; expect `not-converging` at or before round 3; a round-2 fixture records signals without stopping; a round-4 healthy fixture continues; round 5 trip reports the budget as the reason.
4. **Analyze check (SC-004/005)**: moved to #1066 with Story 3.
5. **Gates (SC-007)**: `python .github/scripts/run-local-gates.py` — the new gate passes on the tree and each failure fixture makes it fail.
6. **After merge**: re-drive one lifecycle review round via `gh workflow run` on the wrapper (`prove-after-merge`), confirming the run recorded its round record and signals.

Contract: [convergence-signals](contracts/convergence-signals.md). Entities: [data-model](data-model.md).
