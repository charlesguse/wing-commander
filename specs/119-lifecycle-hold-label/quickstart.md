# Quickstart: validating the lifecycle hold

Prerequisites: a checkout of this branch; `python .github/scripts/run-local-gates.py`.

1. **Unit/fixture layer** (no Actions needed): run the new fixture suites
   (`wc_lifecycle_hold`, `wc_fold_analyze`, `wc_fold_drop`, `wc_dismissals`)
   and the full gate suite. Every FR-014 and FR-023 branch has a fixture;
   removing a branch must fail one.
2. **Hold respected** (US1): on a lifecycle in `stage:implement`, add
   `lifecycle:held`; dispatch implement → expect one status line on the
   issue, no commits, no `stage:stalled`. Trigger a fold → expect the
   "withheld" line and no implement dispatch.
3. **Strict stop** (US1): maintainer comments `/stop` on the lifecycle issue
   and on its PR → label added once, acknowledgement names the release.
   Prose containing "stop" and bot comments set nothing.
4. **Release** (US1/US3): remove the label → implement is dispatched with
   the next iteration and a release note appears. Removing another label
   does nothing.
5. **Analyze** (US2): fold a task contradicting a NON-NEGOTIABLE principle →
   label set, question with four answers posted, no dispatch. Ordinary task
   → no hold. Re-run the analyze job → fresh verdict, label untouched.
6. **Drop** (US3): comment `drop` + fold title line on the PR while held →
   own commit removes the task; remove label; next round reports zero
   recurrences for those findings.
7. **After merge**: re-drive one run per `prove-after-merge` and record the
   evidence on #1066.

Contracts: [contracts/hold-interfaces.md](contracts/hold-interfaces.md);
shapes: [data-model.md](data-model.md).
