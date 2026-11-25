# Quickstart: validating parallel PR lint

Prerequisites: a checkout of the implementing branch; `gh` access.

1. **Local suite**: `python .github/scripts/run-local-gates.py` — expect green, with the same gate count as before the change (294 plus the new layout/aggregate gates).
2. **Layout gates**: `python .github/scripts/verify-lint-shard-layout.py` and `python .github/scripts/verify-lint-aggregate.py`, each also with `--self-test`.
3. **Derivation equality (FR-005)**: the layout gate reports the derived list equals the union of units; add a dummy gate step to one shard and confirm the local runner lists it with no other edit.
4. **PR drill (SC-003, SC-005)** on a test PR touching a workflow: (a) all pass → check-run `lint` is success; (b) break one gate in one shard → that step fails, `lint` fails naming the shard; (c) cancel one shard → `lint` is not success.
5. **Non-PR events**: dispatch `lint-workflows.yml` on main; confirm units and `lint` are skipped and the run concludes success.
6. **Timing (SC-001)**: for ten green first-attempt PR runs compare `run_started_at` with the `lint` check-run's `completed_at`; each ≤ 10 min.
7. **Readers**: confirm `board_readiness` and `lifecycle_readiness` report ready only on the all-pass head (`prove-after-merge` skill).
