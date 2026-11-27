# merge-evidence fixtures

Synthetic cases for `verify-merge-evidence.py` (specs/125-merge-evidence-audit).
`_base.json` holds one snapshot per kind; each `verdict-*/case.json` and
`audit-*/case.json` names a `base`, a shallow `patch` over it, and what it
`expect`s. A `maintainer` case may add `shared_review`, a list of rounds
(`round`, `head_sha`, `verdict`, `run_id`, optional `author: "owner"` and
`created_at`)
posted as the shared reviewer posts them. It may also add
`shared_review_runs`, mapping each run id to overrides of a run that
confirms its record, or to null for a run that does not exist. A run id the
map leaves out was not read.

`sc003/` holds the SC-003 replay (tasks.md T029), never written by the
implement stage:

- `corpus.json` is `wc_merge_evidence.py capture --bot-login
  'wing-commander-bot[bot]' --start 2026-10-15T00:00:00Z --end
  2026-11-17T00:00:00Z`: each merge's facts and its `_merged_snapshot()`
  before the as-of-merge cut, without the kind the capture assigned, so the
  replay runs `cut_snapshot()` and `assign_kind()` itself.
- `expected.json` is a hand lookup made without `wc_merge_evidence.py` or any
  condition code. The replay never writes it, and it is never changed to
  match the replay.
