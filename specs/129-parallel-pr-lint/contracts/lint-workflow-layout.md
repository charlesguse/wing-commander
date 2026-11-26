# Contract: `lint-workflows.yml` layout

Live contract (fixed like code). Enforced by `verify-lint-shard-layout.py` and `verify-lint-aggregate.py`.

1. Workflow `name` is `lint · workflows`; file is `lint-workflows.yml`.
2. Exactly one job has check-run name `lint` (the aggregate). No shard or other job carries that name.
3. Every PR-time job (`if` admits `pull_request`) other than the aggregate is listed in the aggregate's `needs`; the aggregate lists no job that does not exist.
4. Aggregate `if` evaluates true on `pull_request` even when a need failed, was cancelled or skipped (`always()`), and false on `push`, `schedule`, `workflow_dispatch`.
5. Aggregate concludes failure unless every needed job's result is `success`; it names each non-success job.
6. Step names across PR-time jobs are unique; a gate script invocation (script + args) appears in exactly one unit.
7. Every step except checkout carries a guard that survives an unrelated failure (`!cancelled()`); a self-test step may additionally require its paired gate step's outcome not `failure`, paired by step name.
8. `run-local-gates.py`'s derived list equals the union of gates over all units; the aggregate is exempt by name.
9. Non-PR events: all units and the aggregate are skipped; the run concludes from `names-and-tags` only.
