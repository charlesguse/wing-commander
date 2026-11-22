# Contract: merge evidence reports

Layer: consuming instrument; not part of the `workflow_call` published contract. Live: fix like code.

## 1. Reading the current verdict for a pull request (FR-018)

```
gh run list --workflow wing-commander-merge-evidence.yml --branch main --status success --limit 1 --json databaseId
gh run download <databaseId> -n merge-evidence-ledger -D <empty dir>
jq '.records["<pr>@<head>"]' <dir>/ledger.json
```

The reader MUST compare `<head>` with the PR's current `headRefOid`. No record for the current head means "not yet computed", never "met". `written_at` shows how old the ledger is.

## 2. Ledger invariants

- Exactly one record per `(pr, head)`; a later run replaces it.
- A record never counts evidence naming another commit (FR-010), never counts a maintainer-account record (FR-009), and never reports `met` for a condition that depended on a part not read (FR-005).
- No record, artifact or section is a check run or commit status, and no merge job reads any of them (FR-017, FR-019).

## 3. Audit section in "Board status"

A collapsed `<details>` block: header (window, built time, watching-period end, the note that owner and session merges are not told apart); one line per merged PR — `#N kind merged_commit as-of-merge result, first unmet, merged by, recorded|reconstructed` plus linked decision record; then "reached main without a pull request"; then open PRs' latest verdicts naming their heads. Statuses `never`, `paused`, `failed`, `unreadable` replace the body with a one-line notice. Over size: names-only form with a "shortened" line, every entry still present.

## 4. Workflow surface

- Triggers: `schedule` hourly (`7 * * * *`) and daily (`41 5 * * *`); `workflow_dispatch` with one input `job`.
- Refuses before reading anything on a non-default ref; writes nothing while `WING_COMMANDER_MERGE_EVIDENCE_PAUSED` is set.
- Permissions are read-only; artifacts: `merge-evidence-ledger`, `merge-evidence-section`.
