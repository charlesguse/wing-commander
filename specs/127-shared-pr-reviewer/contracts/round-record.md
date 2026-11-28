# Contract: shared reviewer request and record (127)

Layer: consuming instrument. Not part of the published contract. Live: fixed like code.

## Dispatch
`wing-commander-shared-pr-reviewer.yml` `workflow_dispatch` inputs: `pr` (number, required), `dismissals` (JSON list of `{id, reason}`, optional, default `[]`; a value that is not JSON, not a list, or has an entry without an `id` and a `reason` ends the run in `prepare` with a summary refusal and no record). Runs only on the default branch; any other ref ends in the `guard` job with a summary refusal and no record. The callable `shared-pr-reviewer.yml` takes the same two inputs plus wrapper-supplied `default_branch`, models, turn limits, budget and paused flag (a pause only when the value is `true` in any letter case, with nothing around it: the one switch rule, so `1` and `yes` do not pause it; owner decision on #890, 2026-11-27); it declares only the secrets it uses.

## Record comment
Posted once per round by the `record` job as an issue comment on the PR, authored by the pipeline App. Body: one human header line, a findings table, then LAST:

    <!-- wing-commander-shared-review-round: {json} -->

Readers take only the last opener in a bot-authored body. A hand-off uses the same marker with `"kind": "handoff"` and no `verdict`. Fields: see data-model.md. A reader MUST ignore a record whose `run_id` fails confirmation (run id equals; path is the wrapper; default branch; completed success; calls this repository's `shared-pr-reviewer.yml`; artifact `shared-review-<head_sha>` exists), and one whose `verdict` differs from the verdict of the record inside that artifact (`record-<head_sha>.md`, which the `record` job writes from the same file it posts). An artifact whose record cannot be read has no verdict, so its record does not confirm. When the artifact is gone (listed as expired, past its 90 days, deleted, or a 404/410 on download), every reader drops the record as unconfirmed. When the download fails any other way, the reader stops rather than counting the record: the reviewer's `state` step exits non-zero and the round posts nothing, and the merge-evidence watch reports `review_round_record` as not-read. Neither reader ever counts an unread artifact as a match.

## Refusal / stop
Written only to the run summary: `refused: <reason>` or `paused`. Never a record.

## Invariants (each has a gate)
1. The marker name differs from `wing-commander-convergence-round`; `read_round_records` never returns a shared record.
2. No job that holds a secret runs PR code; `code-run` references no `secrets`/`vars` tokens.
3. Neither agent job has a write-capable token or web tools.
4. Verdict values are exactly the four above in the FR-014 order.
5. `purpose.answers.check_fails_without_fix` is decided by code from the staged run of the named check without the fix wherever that run settles it (data-model.md, Derived); a note in `notes` says when it overrides the checking job's answer.
