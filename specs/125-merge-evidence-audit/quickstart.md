# Quickstart: validating the Merge Evidence Audit

Contracts: [contracts/merge-evidence-report.md](contracts/merge-evidence-report.md). Entities: [data-model.md](data-model.md).

## 1. Local gates (no network)

```
python .github/scripts/run-local-gates.py
python .github/scripts/verify-merge-evidence.py
```

Expect every fixture case to pass: one per kind, per condition, incomplete snapshot (FR-005), wrong-author and stale-head records (FR-009/010), no checks on a spec PR (FR-006), as-of-merge cut (FR-012), recorded vs reconstructed (FR-013), unpaired commit (FR-014), decision-record link (FR-015), ledger replace and prune, single-home and workflow-shape checks, and the FR-019 no-reader check. Until the corpus lands, SC-003 reports "not yet captured" under its exemption.

## 2. Dispatch the verdicts job from the default branch

`gh workflow run wing-commander-merge-evidence.yml -f job=verdicts`, then download the ledger (contract §1). Expect a record for each open PR's current head; confirm the head's check runs and statuses and the PR's labels and reviews are unchanged (SC-004).

## 3. Dispatch the audit

`gh workflow run wing-commander-merge-evidence.yml -f job=audit`, then `gh workflow run board-status.yml`. Expect the collapsed section listing every merge in 30 days with marks, plus unpaired commits.

## 4. Refusal and switch

Dispatch from another branch: expect an immediate failure, nothing read. Set `WING_COMMANDER_MERGE_EVIDENCE_PAUSED=true` and dispatch: expect a log line and no upload. Clear it.

## 5. Watching period

After merge, record the dispatch evidence on the PR; at 30 days the owner reviews the audit (FR-024).
