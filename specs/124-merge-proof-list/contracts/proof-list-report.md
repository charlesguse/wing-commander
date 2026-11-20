# Contract: the proof list's report section

Layer: consuming instrument. Live contract; a gate (`verify-proof-list.py`) reads it.

## Location
A collapsed `<details>` section of the open `disposition:tracking` issue titled "Board status", written only by `wc_board_status.py publish`.

```
<!-- wc-proof-list:begin built="<UTC ISO>" status="built|failed|paused" last-good="<UTC ISO>|never" -->
<details><summary>Proof list — built <date> (window 30 days)</summary>
...
</details>
<!-- wc-proof-list:end -->
```

## Content when `status="built"`
1. Per-state counts for states 1–5, the aged-out count, the set-apart run count, and "shortened" if applicable.
2. A table of states 4 and 5: commit, PR, state, reaching workflows; for state 5, per workflow the count of finished runs by event and conclusion and the earliest and latest run link.
3. No wording that says proven / not proven / passed / failed about a change.

## Content otherwise
`status="failed"` or `"paused"`: one line saying so and the date of the last good build (or "there has never been one"). No list.

## Rules
- Rewrites by `board-status.yml` carry the block forward unchanged.
- A refused run (non-default ref) changes nothing.
- Entries are never dropped for size; shortening order: full → names-only → build fails (status `failed`).

## Kill switch
`vars.WING_COMMANDER_PROOF_LIST_PAUSED == 'true'` stands the workflow down; the section shows the paused notice.

## Workflow permissions
`contents: read`, `actions: read`, `pull-requests: read`, `issues: write`; no agent, no dispatch, no comment/label/close call anywhere in the workflow or its scripts (asserted by the gate).
