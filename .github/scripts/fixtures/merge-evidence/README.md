# merge-evidence fixtures

Synthetic cases for `verify-merge-evidence.py` (specs/125-merge-evidence-audit).
`_base.json` holds one snapshot per kind; each `verdict-*/case.json` and
`audit-*/case.json` names a `base`, a shallow `patch` over it, and what it
`expect`s.

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
