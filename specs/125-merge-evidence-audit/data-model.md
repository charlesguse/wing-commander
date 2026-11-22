# Data Model: The Merge Evidence Audit

## Ledger (`merge-evidence-ledger` artifact, `ledger.json`)

```
{ "schema": 1, "written_at": <UTC>, "written_by_run": <run id>,
  "records": { "<pr>@<head sha>": VerdictRecord, ... } }
```

- Replace rule: a later run for the same `(pr, head)` replaces the entry (FR-011).
- Prune rule: kept while the PR is open and for 31 days after merge; dropped 7 days after a close without merge (research D2).
- A ledger that is present but unparseable fails the run; an absent one starts empty and is logged.

## VerdictRecord

| Field | Meaning |
|---|---|
| `pr`, `head` | PR number and the head commit the verdict describes |
| `kind` | `bump` / `board-fix` / `final` / `spec` / `maintainer` |
| `kind_facts` | the facts that decided the kind (branch, author, markers) |
| `rule_applied` | which "checks green" rule: `all-statuses` (board loop kinds) or `without-gate-status` (final) |
| `complete` | boolean snapshot completeness |
| `not_read` | list of what could not be read |
| `conditions` | ordered list of Condition |
| `first_unmet` | name of the first condition not `met`, or null |
| `reported` | list of Reported records (maintainer-account comments) |
| `computed_at` | UTC time |

## Condition

`{name, result: met|unmet|not-read, reason}` — `reason` is one line, required unless `met`.

Order: `checks_green_with_gate_suite` (every kind, FR-006), then the kind's own: bump → `verification_confirmed`; board-fix → `review_verdict_at_head`, `zero_open_findings`; final → `gate_round_at_head`, `round_clean`, `zero_open_in_scope`, `no_unresolved_changes_requested`, `no_hold_label`; spec/maintainer → `review_round_record`.

## Reported record

`{url, author, kind: pass-report|decision-record|other, created_at}` — listed, never counted (FR-009). A comment starting `**Session decision (` is kind `decision-record` (FR-015).

## Audit entry

| Field | Meaning |
|---|---|
| `pr`, `kind`, `merged_commit`, `last_head`, `merged_at`, `merged_by` | merge facts |
| `verdict_as_of_merge` | VerdictRecord shape, computed from the time-cut snapshot |
| `mark` | `recorded` if a ledger entry for `(pr, last_head)` has `computed_at <= merged_at`; else `reconstructed` |
| `prior_record_result` | shown beside the verdict only when the ledger record differs in result or first unmet |
| `decision_record` | linked URL or null |

## Unpaired commit

`{sha, author, committer, committed_at}` for each first-parent commit on `main` in the window that is no merged PR's `merge_commit_sha`.

## Section (`merge-evidence-section` artifact)

`{status, built_at, window: {start, end}, entries, unpaired, open_verdicts, counts}` with the shortened names-only form chosen by the writer when over size.
